"""What a paid tool call cost, as against what the tool charges.

`declared_cost` is the price and belongs on every call the tool made. `spent` is the bill, and
a call that reached the price without buying anything carries `null`. Measured on dogfood #2:
354 paid calls declaring $1.770, of which 263 reached a vendor.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents.errors import CallerFacingError

from simple_agents.pipeline.recording import _node_entries
from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    Cassette,
    DeclaredCost,
    Deterministic,
    FakeModelClient,
    ModelFacingError,
    ModelHandle,
    PriceBasis,
    Pipeline,
    RunEnvelope,
    RunSuspended,
    SideEffectClass,
    SpendMeter,
    read_trajectory,
    tool,
)
from simple_agents.models import ToolCallRequest, fake_response

from schemas import Answer
from conftest import run_path, RUN_ID

PAID = DeclaredCost(currency="USD", per_call=0.005, latency_ms=800)


def _prompt(inputs, ctx):
    return Prompt.user("find it")


def _calls(*names: str):
    """One scripted response per tool call, then a finish."""
    responses = [
        fake_response(
            tool_calls=[ToolCallRequest(id=f"c{i}", name=name, arguments={"query": "tee"})]
        )
        for i, name in enumerate(names)
    ]
    responses.append(
        fake_response(
            tool_calls=[ToolCallRequest(id="cf", name="finish", arguments={"answer": "52cm"})]
        )
    )
    return FakeModelClient(responses=responses)


def _pipeline(paid_tool):
    node = AgentNode(
        _prompt,
        tools=[paid_tool],
        output_schema=Answer,
        allow_unknown=False,
        budget=Budget(max_steps=10, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )
    return Pipeline(
        [node],
        budget=Budget(max_steps=10, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )


def _paid_calls(trajectory: Path) -> list[dict]:
    return [
        r
        for r in read_trajectory(trajectory)
        if r["record_type"] == "tool_call" and r["side_effect_class"] == "spends_money"
    ]


@tool(side_effect_class=SideEffectClass.SPENDS_MONEY, declared_cost=PAID, version="1")
def search(query: str) -> list[dict]:
    """Search the web. Costs money on every call."""
    return [{"title": "Ridge Tee", "url": "https://shop.test/a"}]


@tool(side_effect_class=SideEffectClass.SPENDS_MONEY, declared_cost=PAID, version="1")
def refusing_search(query: str) -> list[dict]:
    """Search the web. Refuses when the run's own ceiling is spent."""
    raise ModelFacingError("This run's search budget is spent.", retryable=False)


class TestWhatACallSpent:
    def test_a_call_that_reached_the_provider_records_what_it_cost(
        self, envelope, trajectory
    ) -> None:
        _pipeline(search).run({}, envelope=envelope, run_id=RUN_ID, model=_calls("search"))

        [call] = _paid_calls(trajectory)
        assert call["spent"] == {"currency": "USD", "amount": 0.005, "source": "declared"}

    def test_the_declaration_is_on_the_record_whether_or_not_the_call_paid_it(
        self, envelope, trajectory
    ) -> None:
        """A reader asking what the tool charges gets an answer on every call it made."""
        _pipeline(refusing_search).run(
            {}, envelope=envelope, run_id=RUN_ID, model=_calls("refusing_search")
        )

        [call] = _paid_calls(trajectory)
        assert call["declared_cost"] == {
            "currency": "USD",
            "per_call": 0.005,
            "latency_ms": 800,
            "max_per_call": None,
        }
        assert call["spent"] is None

    def test_a_call_that_failed_bought_nothing(self, envelope, trajectory) -> None:
        _pipeline(refusing_search).run(
            {}, envelope=envelope, run_id=RUN_ID, model=_calls("refusing_search")
        )

        [call] = _paid_calls(trajectory)
        assert call["error"] is not None
        assert call["spent"] is None

    def test_a_call_served_from_a_cassette_bought_nothing(self, tmp_path: Path) -> None:
        """The replay is where evaluations live, and it makes no request at all."""
        cassette = tmp_path / "tape.jsonl"

        live = RunEnvelope(run_dir=tmp_path / "live", cassette=Cassette.record(cassette))
        _pipeline(search).run({}, envelope=live, run_id=RUN_ID, model=_calls("search"))
        [recorded] = _paid_calls(run_path(tmp_path / "live", RUN_ID, "trajectory.jsonl"))

        again = RunEnvelope(run_dir=tmp_path / "again", cassette=Cassette.replay(cassette))
        _pipeline(search).run({}, envelope=again, run_id=RUN_ID, model=_calls("search"))
        [replayed] = _paid_calls(run_path(tmp_path / "again", RUN_ID, "trajectory.jsonl"))

        assert recorded["spent"]["amount"] == 0.005
        assert replayed["replayed"] is True
        assert replayed["declared_cost"] == recorded["declared_cost"]
        assert replayed["spent"] is None

    def test_a_tool_declaring_no_price_reports_no_spend(self, envelope, trajectory) -> None:
        @tool(side_effect_class=SideEffectClass.READ_ONLY, version="1")
        def look_up(query: str) -> str:
            """Look a term up locally. Costs nothing."""
            return "52cm"

        _pipeline(look_up).run({}, envelope=envelope, run_id=RUN_ID, model=_calls("look_up"))

        [call] = [
            r
            for r in read_trajectory(trajectory)
            if r["record_type"] == "tool_call" and r["tool_name"] == "look_up"
        ]
        assert call["declared_cost"] is None
        assert call["spent"] is None


class TestTheTotalTheseFieldsSupport:
    def test_summing_the_declaration_counts_calls_that_bought_nothing(
        self, envelope, trajectory
    ) -> None:
        """DF2-D2's arithmetic, in miniature: three calls, one of them paid for."""
        _pipeline(refusing_search).run(
            {},
            envelope=envelope,
            run_id=RUN_ID,
            model=_calls("refusing_search", "refusing_search", "refusing_search"),
        )
        refused = _paid_calls(trajectory)

        declared = sum(c["declared_cost"]["per_call"] for c in refused)
        spent = sum(c["spent"]["amount"] for c in refused if c["spent"])

        assert len(refused) == 3
        assert declared == pytest.approx(0.015)
        assert spent == 0.0


class TestACostLimitAgainstAFigureThatIsABound:
    """`max_cost` under a compute basis whose backend reported no concurrency.

    The figure is the whole device charged to one request, which is as much as the batch
    factor over what the call cost. Ending the run beats terminating against it: the work
    discarded is paid for again on the re-run.
    """

    def _run(self, tmp_path: Path, *, max_cost: float | None):
        from simple_agents import ComputeBasis, LLMNode

        def prompt(inputs, ctx):
            return Prompt.user("go")

        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=ComputeBasis(
                currency="USD", device="H100-80GB", device_count=1, hourly_rate=2.69
            ),
        )
        client = FakeModelClient(
            responses=[
                fake_response(content=json.dumps({"answer": "52cm"}), concurrent_requests=None)
            ]
        )
        pipeline = Pipeline(
            [LLMNode(prompt, output_schema=Answer, allow_unknown=False)],
            budget=Budget(
                max_steps=4,
                max_tokens=None,
                max_cost=max_cost,
                max_wall_clock_ms=None,
            ),
        )
        return pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client)

    def test_the_run_ends_naming_the_flag_that_makes_the_figure_exact(self, tmp_path: Path) -> None:
        with pytest.warns(Warning):
            with pytest.raises(CallerFacingError) as caught:
                self._run(tmp_path, max_cost=0.005)

        message = str(caught.value)
        assert "upper bound" in message
        assert "report_concurrency=True" in message
        assert "max_wall_clock_ms" in message

    def test_without_a_cost_limit_the_bound_is_recorded_and_nothing_stops(
        self, tmp_path: Path
    ) -> None:
        result = self._run(tmp_path, max_cost=None)

        manifest = json.loads((run_path(tmp_path, RUN_ID, "manifest.json")).read_text())
        assert str(result.outcome).endswith("completed")
        assert manifest["totals"]["cost"]["is_upper_bound"] is True

    def test_the_run_says_at_the_start_that_the_limit_may_not_hold(self, tmp_path: Path) -> None:
        """Read before any call, so nothing has been spent when it is seen."""
        with pytest.warns(Warning, match="compute basis"):
            with pytest.raises(CallerFacingError):
                self._run(tmp_path, max_cost=0.005)

    def test_the_refused_run_still_records_the_call_it_made(self, tmp_path: Path) -> None:
        """The refusal is about not enforcing the limit, not about not recording the call.

        It raised before `observe_model` and `observe_tokens`, so the manifest carried
        `counts.model_call: 1` beside an empty `models.observed` and four zero token totals,
        for a run whose trajectory holds the call. A reader auditing the spend got zero.
        """
        with pytest.warns(Warning):
            with pytest.raises(CallerFacingError):
                self._run(tmp_path, max_cost=0.005)

        manifest = json.loads((run_path(tmp_path, RUN_ID, "manifest.json")).read_text())
        records = list(read_trajectory(run_path(tmp_path, RUN_ID, "trajectory.jsonl")))
        calls = [r for r in records if r["record_type"] == "model_call"]

        assert manifest["counts"]["model_call"] == len(calls) == 1
        assert [m["calls"] for m in manifest["models"]["observed"]] == [1]
        assert manifest["totals"]["tokens"] == {
            key: calls[0]["tokens"][key]
            for key in ("input_uncached", "input_cache_read", "input_cache_write", "output")
        }
        assert manifest["outcome"] == "error"


PAID_VARIABLE = DeclaredCost(currency="USD", per_call=0.002, max_per_call=0.02)


class TestAToolThatReportsWhatItSpent:
    """`SpendMeter`, the seventh clause of the tool contract.

    A tool holding one is authoritative: what it reports is what the call cost, and reporting
    nothing means it cost nothing. That is how a cache hit inside a tool body, which the
    library cannot see from outside, reaches `spent: null`.
    """

    def _cached_search(self, served: list[bool]):
        answers = list(served)

        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=PAID,
            name="search",
            version="1",
        )
        def search(meter: SpendMeter, query: str) -> list[dict]:
            """Search the web. Costs money unless the answer is already stored."""
            if answers.pop(0):
                return [{"title": "stored", "url": "https://shop.test/a"}]
            meter.spend(0.005)
            return [{"title": "fresh", "url": "https://shop.test/a"}]

        return search

    def test_a_cache_hit_inside_the_tool_reports_no_spend(self, envelope, trajectory) -> None:
        """The $0.300 of dogfood #2's overstatement the declaration could not reach."""
        search = self._cached_search([False, True])

        _pipeline(search).run(
            {}, envelope=envelope, run_id=RUN_ID, model=_calls("search", "search")
        )

        fresh, stored = _paid_calls(trajectory)
        assert fresh["spent"] == {"currency": "USD", "amount": 0.005, "source": "measured"}
        assert stored["spent"] is None
        assert stored["declared_cost"]["per_call"] == 0.005

    def test_a_metered_tool_is_still_served_from_the_cassette(self, tmp_path: Path) -> None:
        """A meter reaches nothing outside the run, so it does not force re-execution."""
        search = self._cached_search([False])
        assert search.re_executed is False

        cassette = tmp_path / "tape.jsonl"
        live = RunEnvelope(run_dir=tmp_path / "live", cassette=Cassette.record(cassette))
        _pipeline(search).run({}, envelope=live, run_id=RUN_ID, model=_calls("search"))

        again = RunEnvelope(run_dir=tmp_path / "again", cassette=Cassette.replay(cassette))
        _pipeline(search).run({}, envelope=again, run_id=RUN_ID, model=_calls("search"))

        [replayed] = _paid_calls(run_path(tmp_path / "again", RUN_ID, "trajectory.jsonl"))
        assert replayed["replayed"] is True
        assert replayed["spent"] is None

    def test_a_handle_that_re_executes_is_still_refused_on_a_paid_tool(self) -> None:
        from simple_agents.errors import ConfigurationError

        with pytest.raises(ConfigurationError) as caught:

            @tool(side_effect_class=SideEffectClass.SPENDS_MONEY, declared_cost=PAID)
            def summarise(model: ModelHandle, text: str) -> str:
                """Summarise a passage."""
                return ""

        assert "ModelHandle" in str(caught.value)
        assert "re-run during replay" in str(caught.value)

    def test_a_negative_amount_is_refused(self) -> None:
        from simple_agents.errors import ConfigurationError

        with pytest.raises(ConfigurationError):
            SpendMeter(_spend=lambda amount, currency, source: None).spend(-1.0)


class TestTheCallIsRefusedBeforeItIsMade:
    """`max_cost` is checked against the most a call can cost, so the limit holds exactly."""

    def _pipeline_with(self, paid_tool, max_cost: float | None):
        node = AgentNode(
            _prompt,
            tools=[paid_tool],
            output_schema=Answer,
            allow_unknown=False,
            budget=Budget(max_steps=10, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        return Pipeline(
            [node],
            budget=Budget(
                max_steps=10,
                max_tokens=None,
                max_cost=max_cost,
                max_wall_clock_ms=None,
            ),
        )

    def _envelope(self, tmp_path: Path) -> RunEnvelope:
        from simple_agents import PriceBasis

        return RunEnvelope(
            run_dir=tmp_path,
            cost_basis=PriceBasis(
                currency="USD", input_uncached_per_mtok=3.0, output_per_mtok=15.0
            ),
        )

    def test_a_call_the_limit_cannot_afford_is_refused_to_the_model(self, tmp_path: Path) -> None:
        """The run continues and the model is told, rather than the run being killed."""

        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=PAID_VARIABLE,
            name="search",
            version="1",
        )
        def search(query: str) -> list[dict]:
            """Search the web. The price varies with the request."""
            return [{"title": "t", "url": "https://shop.test/a"}]

        self._pipeline_with(search, max_cost=0.01).run(
            {},
            envelope=self._envelope(tmp_path),
            run_id=RUN_ID,
            model=_calls("search"),
        )

        [call] = _paid_calls(run_path(tmp_path, RUN_ID, "trajectory.jsonl"))
        assert call["spent"] is None
        assert "costs up to 0.020000" in call["error"]["message"]
        assert "Do not call it again" in call["error"]["message"]

    def test_a_ceiling_the_limit_can_afford_goes_through(self, tmp_path: Path) -> None:
        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=PAID_VARIABLE,
            name="search",
            version="1",
        )
        def search(query: str) -> list[dict]:
            """Search the web. The price varies with the request."""
            return [{"title": "t", "url": "https://shop.test/a"}]

        self._pipeline_with(search, max_cost=1.0).run(
            {},
            envelope=self._envelope(tmp_path),
            run_id=RUN_ID,
            model=_calls("search"),
        )

        [call] = _paid_calls(run_path(tmp_path, RUN_ID, "trajectory.jsonl"))
        assert call["error"] is None
        assert call["spent"]["amount"] == 0.002

    def test_a_ceiling_below_the_per_call_price_is_refused_at_construction(self) -> None:
        from simple_agents.errors import ConfigurationError

        with pytest.raises(ConfigurationError) as caught:
            DeclaredCost(currency="USD", per_call=0.02, max_per_call=0.002)

        assert "more than the most a call can cost" in str(caught.value)


class TestToolSpendDepletesTheCostLimit:
    """One axis for all money. Tool spend was 1.9x model spend on dogfood #2."""

    def test_a_paid_tool_charges_the_run(self, tmp_path: Path) -> None:
        from simple_agents import PriceBasis

        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=PriceBasis(
                currency="USD", input_uncached_per_mtok=3.0, output_per_mtok=15.0
            ),
        )
        node = AgentNode(
            _prompt,
            tools=[search],
            output_schema=Answer,
            allow_unknown=False,
            budget=Budget(max_steps=10, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        result = Pipeline(
            [node],
            budget=Budget(max_steps=10, max_tokens=None, max_cost=1.0, max_wall_clock_ms=None),
        ).run({}, envelope=envelope, run_id=RUN_ID, model=_calls("search", "search"))

        # Two searches at $0.005, plus three model calls priced from their tokens.
        charged = json.loads(result.manifest_path.read_text())["totals"]["charged_cost"]
        assert charged == pytest.approx(0.010 + 0.000315, abs=1e-6)

    def test_two_currencies_in_one_run_are_refused(self, tmp_path: Path) -> None:
        from simple_agents import PriceBasis
        from simple_agents.errors import ConfigurationError

        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=DeclaredCost(currency="EUR", per_call=0.005),
            name="euro_search",
            version="1",
        )
        def euro_search(query: str) -> list[dict]:
            """Search a provider billing in euros."""
            return []

        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=PriceBasis(
                currency="USD", input_uncached_per_mtok=3.0, output_per_mtok=15.0
            ),
        )

        with pytest.raises(ConfigurationError) as caught:
            _pipeline(euro_search).run(
                {}, envelope=envelope, run_id=RUN_ID, model=_calls("euro_search")
            )

        assert "more than one currency" in str(caught.value)
        assert "EUR: tool 'euro_search'" in str(caught.value)
        assert "USD: the cost basis" in str(caught.value)

    def test_a_currency_declared_in_a_nested_pipelines_registry_is_refused_too(
        self, tmp_path: Path
    ) -> None:
        """`Pipeline(tools=)` was read on the pipeline the run was started with and no other.

        The same tool was refused when the top pipeline held it and accepted one level down.
        """
        from simple_agents import Deterministic, PriceBasis, ToolRegistry
        from simple_agents.errors import ConfigurationError

        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=DeclaredCost(currency="EUR", per_call=0.005),
            name="euro_search",
            version="1",
        )
        def euro_search(query: str) -> list[dict]:
            """Search a provider billing in euros."""
            return []

        inner = Pipeline(
            [Deterministic(lambda inputs, ctx: inputs, node_id="hunt", successors=[])],
            budget=Budget.unbounded(),
            node_id="research",
            tools=ToolRegistry([euro_search]),
        )
        pipeline = Pipeline(
            [inner, Deterministic(lambda inputs, ctx: inputs, node_id="report", successors=[])],
            budget=Budget.unbounded(),
        )
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=PriceBasis(
                currency="USD", input_uncached_per_mtok=3.0, output_per_mtok=15.0
            ),
        )

        with pytest.raises(ConfigurationError) as caught:
            pipeline.run({}, envelope=envelope, run_id=RUN_ID)

        assert "EUR: tool 'euro_search'" in str(caught.value)
        # And it reaches the manifest as a tool the project declared and gave to no node.
        assert [(entry["name"], entry["offered"]) for entry in _node_entries(pipeline)[2]] == [
            ("euro_search", False)
        ]

    def test_a_pipeline_that_only_spends_through_a_tool_needs_no_cost_basis(
        self, tmp_path: Path
    ) -> None:
        """No model call, so there is nothing a basis would price."""
        from simple_agents import Deterministic

        def buy(inputs, ctx):
            return {"answer": ctx.call_tool("search", query="tee")}

        pipeline = Pipeline(
            [Deterministic(buy, tools=[search])],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=0.10, max_wall_clock_ms=None),
        )

        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)

        charged = json.loads(result.manifest_path.read_text())["totals"]["charged_cost"]
        assert charged == pytest.approx(0.005)


class TestAReportedCurrency:
    """A meter reports a figure that is added to the run's totals, so it has one currency.

    `Pipeline` refuses two declared currencies before the run. A `SpendMeter` was introduced
    to supersede a declaration and was not covered by it, so a tool reporting 100 JPY under a
    USD basis reached `charged_cost` as 100 and depleted `max_cost` by it, with no warning.
    """

    def _tool_reporting(self, amount: float, currency: str | None, *, declared=PAID):
        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=declared,
            name="search",
            version="1",
        )
        def search(meter: SpendMeter, query: str) -> list[dict]:
            """Search a vendor. Costs money."""
            meter.spend(amount, currency=currency)
            return [{"title": "a", "url": "https://shop.test/a"}]

        return search

    def _run(self, paid_tool, envelope):
        return _pipeline(paid_tool).run(
            {}, envelope=envelope, run_id=RUN_ID, model=_calls("search")
        )

    def test_a_currency_the_cost_basis_does_not_use_is_refused(self, tmp_path: Path) -> None:
        priced = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=PriceBasis(currency="USD", input_uncached_per_mtok=0.4, output_per_mtok=2.0),
        )
        with pytest.raises(CallerFacingError) as caught:
            self._run(self._tool_reporting(100.0, "JPY"), priced)

        message = str(caught.value)
        assert "reported spend in JPY" in message
        assert "the run's cost basis is in USD" in message
        assert "charged_cost" in message and "max_cost" in message

    def test_a_currency_the_tool_did_not_declare_is_refused(self, tmp_path: Path) -> None:
        """No cost basis, so the declaration is what the figure has to agree with."""
        with pytest.raises(CallerFacingError) as caught:
            self._run(self._tool_reporting(100.0, "JPY"), RunEnvelope(run_dir=tmp_path))

        assert "declared_cost of 'search'" in str(caught.value)

    def test_two_currencies_inside_one_call_are_refused(self, envelope) -> None:
        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=PAID,
            name="search",
            version="1",
        )
        def search(meter: SpendMeter, query: str) -> list[dict]:
            """Search two vendors. Costs money."""
            meter.spend(0.005, currency="USD")
            meter.spend(7.0, currency="EUR")
            return [{"title": "a", "url": "https://shop.test/a"}]

        with pytest.raises(CallerFacingError) as caught:
            self._run(search, envelope)

        assert "an earlier spend reported by 'search'" in str(caught.value)

    def test_the_currency_the_run_uses_is_accepted(self, envelope, trajectory) -> None:
        self._run(self._tool_reporting(0.004, "USD"), envelope)

        assert self._spent_by_search(trajectory) == [
            {"currency": "USD", "amount": 0.004, "source": "measured"}
        ]

    def test_reporting_no_currency_still_takes_the_declared_one(self, envelope, trajectory) -> None:
        """The parameter is optional, and omitting it is the ordinary case."""
        self._run(self._tool_reporting(0.004, None), envelope)

        assert self._spent_by_search(trajectory) == [
            {"currency": "USD", "amount": 0.004, "source": "measured"}
        ]

    @staticmethod
    def _spent_by_search(trajectory) -> list:
        """`finish` is a tool call too, and it buys nothing."""
        return [
            r["spent"]
            for r in read_trajectory(trajectory)
            if r["record_type"] == "tool_call" and r["tool_name"] == "search"
        ]


class TestARunWithNoCostBasis:
    """The run fixes its currency on the first figure, because nothing else can.

    A pipeline whose only spend is a paid tool needs no cost basis, so a run can reach its
    first money figure with nothing to check it against. The basis and a tool's own
    `declared_cost` cover every other case; this is the one left, and both tools reporting a
    figure they never declared is what reaches it.
    """

    def _metered(self, name: str, amount: float, currency: str):
        @tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version="1")
        def fetch(meter: SpendMeter, q: str) -> str:
            """Fetch from a vendor. Free on a cache hit, so the meter reports the misses."""
            meter.spend(amount, currency=currency)
            return name

        return fetch

    def _pipeline(self, first_tool, second_tool, **second):
        def first(inputs, ctx):
            return ctx.call_tool(first_tool.name, q="x")

        def second_fn(inputs, ctx):
            return ctx.call_tool(second_tool.name, q="x")

        return Pipeline(
            [
                Deterministic(first, node_id="first", tools=[first_tool], successors=["second"]),
                Deterministic(second_fn, node_id="second", tools=[second_tool], **second),
            ],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=1000.0, max_wall_clock_ms=None),
        )

    def test_a_second_tool_reporting_another_currency_is_refused(self, tmp_path: Path) -> None:
        pipeline = self._pipeline(
            self._metered("fetch_jp", 100.0, "JPY"), self._metered("fetch_us", 5.0, "USD")
        )
        with pytest.raises(CallerFacingError) as caught:
            pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)

        message = str(caught.value)
        assert "reported spend in USD" in message
        assert "the spend reported by 'fetch_jp' is in JPY" in message

    def test_one_currency_across_two_tools_is_accepted(self, tmp_path: Path) -> None:
        pipeline = self._pipeline(
            self._metered("fetch_a", 0.30, "USD"), self._metered("fetch_b", 0.20, "USD")
        )
        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)

        assert result.manifest["totals"]["tool_spend"] == {
            "amount": pytest.approx(0.50),
            "currency": "USD",
            "calls": 2,
            "source": "measured",
        }

    def test_the_fixed_currency_survives_a_suspension(self, tmp_path: Path) -> None:
        """The spend it belongs to is restored, so the currency has to be restored with it."""
        pipeline = self._pipeline(
            self._metered("fetch_jp", 100.0, "JPY"),
            self._metered("fetch_us", 5.0, "USD"),
            suspend_before=True,
        )
        envelope = RunEnvelope(run_dir=tmp_path)
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID)

        with pytest.raises(CallerFacingError) as caught:
            pipeline.resume(RUN_ID, envelope=envelope)

        assert "the spend reported by 'fetch_jp' is in JPY" in str(caught.value)
