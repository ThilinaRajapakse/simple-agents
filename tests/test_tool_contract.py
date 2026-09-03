"""The tool contract: the registry, the cost declaration, and the two library-filled handles.

The keying tests here are the load-bearing ones. A tool is served from the cassette under its
name, version, arguments and how many times that same call has already been made, and a tool
taking a handle is re-run instead. Both exist so a replayed run writes the records the live run
wrote, which is what everything downstream reads.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    Deterministic,
    Cassette,
    DeclaredCost,
    FakeModelClient,
    ModelHandle,
    ModelFacingError,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    ToolRegistry,
    Workspace,
    read_trajectory,
    tool,
)
from simple_agents.errors import ConfigurationError
from simple_agents.models import TokenUsage, ToolCallRequest, fake_response
from simple_agents.nodes.agent import MAX_IDENTICAL_FINISH_REJECTIONS
from simple_agents.tools import derived_version

from schemas import Answer
from conftest import run_path, RUN_ID


def _prompt(inputs, ctx):
    return Prompt.user("go")


def _finish(answer: str = "done", source: str | None = None) -> ToolCallRequest:
    return ToolCallRequest(id="f", name="finish", arguments={"answer": answer, "source": source})


def _call(name: str, **arguments) -> ToolCallRequest:
    return ToolCallRequest(id=f"c_{name}", name=name, arguments=arguments)


def _tokens(output: int = 5) -> TokenUsage:
    return TokenUsage(
        input_uncached=10,
        input_cache_read=0,
        input_cache_write=0,
        cache_ttl=None,
        output=output,
    )


def _agent(tools, **kwargs) -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                _prompt,
                tools=tools,
                output_schema=Answer,
                budget=Budget.unbounded(),
                **kwargs,
            )
        ],
        budget=Budget.unbounded(),
    )


def _records(trajectory, record_type: str) -> list[dict]:
    return [r for r in read_trajectory(trajectory) if r["record_type"] == record_type]


# -----------------------------------------------------------------------------------------
# The cost declaration
# -----------------------------------------------------------------------------------------


class TestDeclaredCost:
    def test_a_figure_without_a_currency_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            DeclaredCost(per_call=0.005)

        assert "currency" in str(exc.value)

    def test_a_spending_tool_must_declare_what_it_costs(self):
        """An evaluation runs k×n rollouts, so the bill is knowable before the run."""
        with pytest.raises(ConfigurationError) as exc:

            @tool(side_effect_class=SideEffectClass.SPENDS_MONEY)
            def paid_search(query: str) -> str:
                """Search a paid index."""
                return ""

        assert "SPENDS_MONEY" in str(exc.value)
        assert "DeclaredCost" in str(exc.value)

    def test_a_read_only_tool_needs_no_declaration(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def free(query: str) -> str:
            """Search a local index."""
            return ""

        assert free.declared_cost is None

    def test_an_untyped_declaration_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:

            @tool(
                side_effect_class=SideEffectClass.READ_ONLY,
                declared_cost={"per_call": 0.005},
            )
            def free(query: str) -> str:
                """Search a local index."""
                return ""

        assert "DeclaredCost" in str(exc.value)

    def test_the_record_always_carries_all_four_keys(self):
        declared = DeclaredCost(currency="USD", per_call=0.005)

        assert declared.to_record() == {
            "currency": "USD",
            "per_call": 0.005,
            "latency_ms": None,
            "max_per_call": None,
        }


# -----------------------------------------------------------------------------------------
# The registry
# -----------------------------------------------------------------------------------------


def _named(name: str):
    @tool(side_effect_class=SideEffectClass.READ_ONLY, name=name)
    def fn(query: str) -> str:
        """Search the documents."""
        return "found"

    return fn


class TestToolRegistry:
    def test_it_refuses_a_duplicate_name(self):
        registry = ToolRegistry([_named("search")])

        with pytest.raises(ConfigurationError) as exc:
            registry.add(_named("search"))

        assert "already holds a tool named 'search'" in str(exc.value)

    def test_it_refuses_the_reserved_name(self):
        with pytest.raises(ConfigurationError) as exc:
            ToolRegistry([_named("finish")])

        assert "reserved" in str(exc.value)

    def test_it_refuses_something_that_is_not_a_tool(self):
        with pytest.raises(ConfigurationError) as exc:
            ToolRegistry().add(lambda query: "")  # type: ignore[arg-type]

        assert "@tool(" in str(exc.value)

    def test_an_unregistered_name_lists_what_is_registered(self):
        registry = ToolRegistry([_named("search")])

        with pytest.raises(ConfigurationError) as exc:
            registry.get("lookup")

        assert "Registered: search" in str(exc.value)

    def test_an_agent_node_accepts_a_registry(self, envelope, trajectory):
        registry = ToolRegistry([_named("search")])
        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_call("search", query="q")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )

        _agent(registry).run({}, envelope=envelope, run_id=RUN_ID, seed=41, model=client)

        assert [r["tool_name"] for r in _records(trajectory, "tool_call")] == [
            "search",
            "finish",
        ]

    def test_the_manifest_reports_the_declarations(self):
        registry = ToolRegistry(
            [_named("search")],
        )

        (entry,) = registry.to_manifest()

        assert entry["name"] == "search"
        assert entry["side_effect_class"] == "read_only"
        assert entry["declared_cost"] is None
        assert entry["re_executed"] is False
        # Undeclared, so derived from the function's source (`tools.derived_version`).
        assert entry["version"].startswith("sha256:")


# -----------------------------------------------------------------------------------------
# Occurrence in the key
# -----------------------------------------------------------------------------------------


class TestOccurrenceKeying:
    """A tool answering differently at two moments replays as two answers, not one twice."""

    def _clock_pipeline(self, readings: list[str]):
        remaining = list(readings)

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def clock() -> str:
            """The current time. Takes no arguments."""
            return remaining.pop(0)

        return _agent([clock])

    def _client(self):
        return FakeModelClient(
            responses=[
                fake_response(tool_calls=[_call("clock")]),
                fake_response(tool_calls=[_call("clock")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )

    def test_two_identical_calls_record_two_entries(self, tmp_path):
        cassette = tmp_path / "clock.jsonl"
        env = RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(cassette))

        self._clock_pipeline(["09:00", "09:10"]).run(
            {}, envelope=env, run_id=RUN_ID, seed=41, model=self._client()
        )

        stored = [json.loads(line) for line in cassette.read_text().splitlines()]
        clock_entries = [e for e in stored if e["request"].get("tool_name") == "clock"]
        assert [e["response"]["value"] for e in clock_entries] == ["09:00", "09:10"]
        assert len({e["key"] for e in clock_entries}) == 2

    def test_replay_serves_each_reading_in_turn(self, tmp_path):
        cassette = tmp_path / "clock.jsonl"
        # One pipeline for both runs. The readings are consumed by the recording, so the clock
        # raises IndexError if the replay reaches its body, which is what this asserts. Two
        # pipelines built over different readings are two tools: what a tool closed over is in
        # its version, and its version is in the cassette key.
        pipeline = self._clock_pipeline(["09:00", "09:10"])
        recording = RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(cassette))
        pipeline.run({}, envelope=recording, run_id="live", seed=41, model=self._client())

        replaying = RunEnvelope(run_dir=tmp_path, cassette=Cassette.replay(cassette))
        pipeline.run({}, envelope=replaying, run_id="replayed", seed=41, model=self._client())

        served = [
            r["outputs"]
            for r in _records(run_path(tmp_path, "replayed", "trajectory.jsonl"), "tool_call")
            if r["tool_name"] == "clock"
        ]
        assert served == ["09:00", "09:10"]


# -----------------------------------------------------------------------------------------
# The handles
# -----------------------------------------------------------------------------------------


class TestHandleAnnotations:
    def test_a_handle_is_not_offered_to_the_model(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def summarise(model: ModelHandle, text: str) -> str:
            """Summarise a passage."""
            return ""

        assert set(summarise.parameters["properties"]) == {"text"}
        assert summarise.handles == {"model": ModelHandle}
        assert summarise.re_executed is True

    def test_a_tool_without_a_handle_is_not_re_executed(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def look_up(query: str) -> str:
            """Search the documents."""
            return ""

        assert look_up.re_executed is False

    def test_a_handle_with_a_spending_class_is_refused(self):
        """A re-run tool acts again on every replay, so it may not spend or destroy."""
        with pytest.raises(ConfigurationError) as exc:

            @tool(
                side_effect_class=SideEffectClass.IRREVERSIBLE,
                declared_cost=DeclaredCost(currency="USD", per_call=0.01),
            )
            def wipe(workspace: Workspace, path: str) -> str:
                """Delete something."""
                return ""

        assert "re-run during replay" in str(exc.value)
        assert "only through the handles it was given" in str(exc.value)

    def test_a_workspace_tool_may_declare_writes(self):
        @tool(side_effect_class=SideEffectClass.WRITES)
        def save(workspace: Workspace, path: str, content: str) -> str:
            """Write a note into the run's workspace."""
            workspace.write_text(path, content)
            return path

        assert save.re_executed is True

    def test_the_refusal_for_an_unannotated_parameter_names_the_handles(self):
        with pytest.raises(ConfigurationError) as exc:

            @tool(side_effect_class=SideEffectClass.READ_ONLY)
            def look_up(query):
                """Search the documents."""
                return ""

        assert "ModelHandle, Workspace or Memory" in str(exc.value)


class TestWorkspaceHandle:
    def test_it_refuses_a_path_outside_the_workspace(self, tmp_path):
        workspace = Workspace(root=tmp_path)

        with pytest.raises(ModelFacingError) as exc:
            workspace.resolve("../escaped.txt")

        assert "outside the run's workspace" in str(exc.value)

    def test_a_missing_file_is_a_model_facing_failure_listing_what_is_there(self, tmp_path):
        workspace = Workspace(root=tmp_path)
        workspace.write_text("notes.txt", "hello")

        with pytest.raises(ModelFacingError) as exc:
            workspace.read_text("other.txt")

        assert "notes.txt" in str(exc.value)

    def test_a_replayed_run_writes_its_own_files(self, tmp_path):
        """The write re-runs, so a later step reading the workspace finds it."""

        @tool(side_effect_class=SideEffectClass.WRITES)
        def save(workspace: Workspace, path: str, content: str) -> str:
            """Write a note into the run's workspace. Returns the path written."""
            workspace.write_text(path, content)
            return path

        def client():
            return FakeModelClient(
                responses=[
                    fake_response(tool_calls=[_call("save", path="notes.txt", content="hello")]),
                    fake_response(tool_calls=[_finish()]),
                ]
            )

        cassette = tmp_path / "save.jsonl"
        _agent([save]).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(cassette)),
            run_id="live",
            seed=41,
            model=client(),
        )
        _agent([save]).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.replay(cassette)),
            run_id="replayed",
            seed=41,
            model=client(),
        )

        assert (run_path(tmp_path, "replayed", "workspace") / "notes.txt").read_text() == "hello"

    def test_a_re_executed_tool_is_never_stored(self, tmp_path):
        @tool(side_effect_class=SideEffectClass.WRITES)
        def save(workspace: Workspace, path: str, content: str) -> str:
            """Write a note into the run's workspace. Returns the path written."""
            workspace.write_text(path, content)
            return path

        cassette = tmp_path / "save.jsonl"
        _agent([save]).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(cassette)),
            run_id=RUN_ID,
            seed=41,
            model=FakeModelClient(
                responses=[
                    fake_response(tool_calls=[_call("save", path="notes.txt", content="hello")]),
                    fake_response(tool_calls=[_finish()]),
                ]
            ),
        )

        stored = [json.loads(line) for line in cassette.read_text().splitlines()]
        assert [e["request"].get("tool_name") for e in stored if e["kind"] == "tool_call"] == []

        record = next(
            r
            for r in _records(run_path(tmp_path, RUN_ID, "trajectory.jsonl"), "tool_call")
            if r["tool_name"] == "save"
        )
        assert record["re_executed"] is True
        assert record["cassette_key"] is None


class TestModelHandle:
    """A model call inside a tool is recorded, budgeted and replayed like any other."""

    def _extracting_tool(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def extract(model: ModelHandle, text: str) -> str:
            """Pull the headline figure out of a passage."""
            return (
                model.complete(Prompt.user("Extract the figure from: {text}", text=text)).content
                or ""
            )

        return extract

    def _client(self):
        return FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[_call("extract", text="revenue was 4m")], tokens=_tokens()
                ),
                fake_response(content="4m", tokens=_tokens(output=3)),
                fake_response(tool_calls=[_finish()], tokens=_tokens()),
            ]
        )

    def test_the_nested_call_hangs_off_the_tool_call(self, envelope, trajectory):
        _agent([self._extracting_tool()]).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        tool_call = next(
            r for r in _records(trajectory, "tool_call") if r["tool_name"] == "extract"
        )
        nested = [
            r
            for r in _records(trajectory, "model_call")
            if r["parent_id"] == tool_call["record_id"]
        ]
        assert len(nested) == 1
        assert nested[0]["outputs"]["content"] == "4m"

    def test_a_child_is_written_before_its_parent(self, envelope, trajectory):
        _agent([self._extracting_tool()]).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        tool_call = next(
            r for r in _records(trajectory, "tool_call") if r["tool_name"] == "extract"
        )
        nested = next(
            r
            for r in _records(trajectory, "model_call")
            if r["parent_id"] == tool_call["record_id"]
        )
        assert nested["sequence"] < tool_call["sequence"]

    def test_the_nested_call_charges_a_step(self, envelope, trajectory):
        """One step is one model call, wherever the call was made from."""
        pipeline = Pipeline(
            [
                AgentNode(
                    _prompt,
                    tools=[self._extracting_tool()],
                    output_schema=Answer,
                    budget=Budget(
                        max_steps=2, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=Budget.unbounded(),
        )

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client())

        node = _records(trajectory, "node_execution")[0]
        assert node["termination"] == "max_steps"

    def test_the_replayed_run_writes_the_same_records(self, tmp_path):
        cassette = tmp_path / "extract.jsonl"
        _agent([self._extracting_tool()]).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(cassette)),
            run_id="live",
            seed=41,
            model=self._client(),
        )
        _agent([self._extracting_tool()]).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.replay(cassette)),
            run_id="replayed",
            seed=41,
            model=self._client(),
        )

        def shape(run_id: str) -> list[tuple[str, str]]:
            return [
                (r["record_type"], r.get("tool_name") or r.get("node_id") or "model")
                for r in read_trajectory(run_path(tmp_path, run_id, "trajectory.jsonl"))
            ]

        assert shape("replayed") == shape("live")

    def test_the_replayed_nested_call_came_from_the_cassette(self, tmp_path):
        cassette = tmp_path / "extract.jsonl"
        _agent([self._extracting_tool()]).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(cassette)),
            run_id="live",
            seed=41,
            model=self._client(),
        )
        _agent([self._extracting_tool()]).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.replay(cassette)),
            run_id="replayed",
            seed=41,
            # No responses left: a live call would raise rather than being served.
            model=FakeModelClient(responses=[]),
        )

        replayed = _records(run_path(tmp_path, "replayed", "trajectory.jsonl"), "model_call")
        assert all(r["replayed"] for r in replayed)


# -----------------------------------------------------------------------------------------
# The finish check
# -----------------------------------------------------------------------------------------


class TestFinishCheck:
    def _client(self):
        return FakeModelClient(
            responses=[
                fake_response(tool_calls=[_call("read", doc_id="a")]),
                fake_response(tool_calls=[_finish(answer="yes", source="b")]),
                fake_response(tool_calls=[_finish(answer="yes", source="a")]),
            ]
        )

    def _reader(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def read(doc_id: str) -> str:
            """Read one document by id."""
            return f"contents of {doc_id}"

        return read

    @staticmethod
    def _cited_what_it_read(answer, ctx) -> str | None:
        opened = {c.arguments["doc_id"] for c in ctx.tool_calls if c.name == "read" and c.ok}
        if answer.source is not None and answer.source not in opened:
            return (
                f"Source {answer.source!r} was cited but never read. Read it, or cite one that was."
            )
        return None

    def test_a_rejected_answer_goes_back_to_the_model(self, envelope, trajectory):
        result = _agent([self._reader()], finish_check=self._cited_what_it_read).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        assert result.output.source == "a"
        finishes = [r for r in _records(trajectory, "tool_call") if r["tool_name"] == "finish"]
        assert len(finishes) == 2
        assert finishes[0]["error"]["class"] == "model_facing"
        assert "never read" in finishes[0]["error"]["message"]

    def test_the_node_still_terminates_on_finish(self, envelope, trajectory):
        _agent([self._reader()], finish_check=self._cited_what_it_read).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        assert _records(trajectory, "node_execution")[0]["termination"] == "finish"

    def test_a_check_returning_none_accepts_the_answer(self, envelope):
        result = _agent([self._reader()], finish_check=lambda answer, ctx: None).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        assert result.output.source == "b"

    def test_the_check_sees_only_calls_already_made(self, envelope):
        seen: list[tuple[str, ...]] = []

        def record_what_it_saw(answer, ctx) -> str | None:
            seen.append(tuple(c.name for c in ctx.tool_calls))
            return None

        _agent([self._reader()], finish_check=record_what_it_saw).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        assert seen == [("read",)]

    def test_the_check_sees_a_call_made_in_the_turn_it_is_judging(self, envelope):
        """A turn may carry several calls, and the model chooses their order.

        Session 2 of the item 7 checkpoint met a model issuing four in one turn. A check
        asking what this run read has to see the read that arrived beside the `finish`.
        """
        seen: list[tuple[str, ...]] = []

        def record_what_it_saw(answer, ctx) -> str | None:
            seen.append(tuple(c.name for c in ctx.tool_calls))
            return None

        client = FakeModelClient(
            responses=[
                # `finish` first, the read second. The library runs them the other way round.
                fake_response(
                    tool_calls=[_finish(answer="yes", source="a"), _call("read", doc_id="a")]
                )
            ]
        )
        _agent([self._reader()], finish_check=record_what_it_saw).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=client
        )

        assert seen == [("read",)]

    def test_the_check_sees_what_a_tool_returned(self, envelope):
        results: list[Any] = []

        def record_results(answer, ctx) -> str | None:
            results.extend(c.result for c in ctx.tool_calls if c.name == "read")
            return None

        _agent([self._reader()], finish_check=record_results).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        assert results == ["contents of a"]

    def test_the_check_sees_the_answers_it_has_already_refused(self, envelope):
        """Without this a check cannot tell its first refusal from its fourth.

        Both item 7 checkpoint sessions built a check that refused an answer the model
        believed it had already given, and both produced a loop the model could not escape.
        """
        seen: list[int] = []

        def refuse_once_then_relent(answer, ctx) -> str | None:
            seen.append(len(ctx.finish_attempts))
            if ctx.finish_attempts:
                return None
            return "Not good enough. Try again."

        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_finish(answer="yes")]),
                fake_response(tool_calls=[_finish(answer="yes")]),
            ]
        )
        result = _agent([self._reader()], finish_check=refuse_once_then_relent).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=client
        )

        assert seen == [0, 1]
        assert result.output.answer == "yes"

    def test_the_same_answer_refused_repeatedly_stops_the_node(self, envelope, trajectory):
        """The library breaks the loop rather than spending the whole step budget on it.

        Session 2's question 29 sent one payload fourteen times against a check that refused
        every one, exhausted `max_steps`, and returned nothing. Terminating says why.
        """
        client = FakeModelClient(
            responses=[fake_response(tool_calls=[_finish(answer="yes")]) for _ in range(10)]
        )
        result = _agent([self._reader()], finish_check=lambda answer, ctx: "No.").run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=client
        )

        assert result.output is None
        node = _records(trajectory, "node_execution")[0]
        assert node["termination"] == "finish_rejected"
        finishes = [r for r in _records(trajectory, "tool_call") if r["tool_name"] == "finish"]
        assert len(finishes) == MAX_IDENTICAL_FINISH_REJECTIONS

    def test_a_different_answer_each_time_is_not_capped(self, envelope):
        """The cap counts one payload refused over and over, not refusals in general."""
        attempts: list[int] = []

        def accept_the_third(answer, ctx) -> str | None:
            attempts.append(len(ctx.finish_attempts))
            return None if answer.answer == "third" else "Try another."

        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_finish(answer="first")]),
                fake_response(tool_calls=[_finish(answer="second")]),
                fake_response(tool_calls=[_finish(answer="third")]),
            ]
        )
        result = _agent([self._reader()], finish_check=accept_the_third).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=client
        )

        assert attempts == [0, 1, 2]
        assert result.output.answer == "third"


# -----------------------------------------------------------------------------------------
# A tool called at a fixed point
# -----------------------------------------------------------------------------------------


def _fixed(fn, tools, **kwargs) -> Pipeline:
    return Pipeline(
        [Deterministic(fn, node_id="step", tools=tools, **kwargs)], budget=Budget.unbounded()
    )


def _charging_tool(calls: list[str]):
    @tool(
        side_effect_class=SideEffectClass.SPENDS_MONEY,
        name="charge_the_card",
        version="1",
        declared_cost=DeclaredCost(currency="GBP", per_call=40.0),
    )
    def charge_the_card(amount: str) -> str:
        """Charge the customer's card. Returns the transaction id."""
        calls.append(amount)
        return f"txn-{len(calls)}"

    return charge_the_card


class TestAToolCalledAtAFixedPoint:
    """`Deterministic(tools=...)` and `ctx.call_tool`, for a call the builder decided on.

    Before this the whole tool contract was reachable only from inside an `AgentNode`, so a
    step that has to call a tool either paid a model call to decide something already decided
    or called the function directly, which records nothing.
    """

    def test_the_call_is_recorded_with_its_class_and_its_cost(self, envelope, trajectory):
        calls: list[str] = []

        _fixed(
            lambda inputs, ctx: ctx.call_tool("charge_the_card", amount="40.00"),
            [_charging_tool(calls)],
        ).run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        (record,) = _records(trajectory, "tool_call")
        assert calls == ["40.00"]
        assert record["tool_name"] == "charge_the_card"
        assert record["tool_version"] == "1"
        assert record["side_effect_class"] == "spends_money"
        assert record["inputs"] == {"amount": "40.00"}
        assert record["outputs"] == "txn-1"
        assert record["declared_cost"]["per_call"] == 40.0

    def test_the_record_hangs_off_the_node_that_made_it(self, envelope, trajectory):
        _fixed(
            lambda inputs, ctx: ctx.call_tool("charge_the_card", amount="40.00"),
            [_charging_tool([])],
        ).run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        (node,) = _records(trajectory, "node_execution")
        (call,) = _records(trajectory, "tool_call")
        assert call["parent_id"] == node["record_id"]

    def test_a_replay_serves_it_rather_than_spending_again(self, tmp_path):
        """The point of recording it: k rollouts of an evaluation charge the card once."""
        cassette = tmp_path / "c.json"
        calls: list[str] = []

        def run(mode):
            return _fixed(
                lambda inputs, ctx: ctx.call_tool("charge_the_card", amount="40.00"),
                [_charging_tool(calls)],
            ).run(
                {}, envelope=RunEnvelope(run_dir=tmp_path / mode.mode.value, cassette=mode), seed=41
            )

        first = run(Cassette.record(cassette))
        assert calls == ["40.00"]

        second = run(Cassette.replay(cassette))

        assert calls == ["40.00"], "the replayed run must not charge the card again"
        assert second.output == first.output
        replayed = [
            r["replayed"]
            for r in read_trajectory(second.paths.trajectory)
            if r["record_type"] == "tool_call"
        ]
        assert replayed == [True]

    def test_a_workspace_tool_is_re_run_and_writes_into_the_new_run(self, tmp_path):
        @tool(side_effect_class=SideEffectClass.WRITES, name="save_receipt")
        def save_receipt(workspace: Workspace, text: str) -> str:
            """Write the receipt into the run's workspace. Returns the path."""
            workspace.write_text("receipt.txt", text)
            return "receipt.txt"

        def run(where):
            return _fixed(
                lambda inputs, ctx: ctx.call_tool("save_receipt", text="txn-1"),
                [save_receipt],
            ).run({}, envelope=RunEnvelope(run_dir=tmp_path / where), seed=41)

        first, second = run("one"), run("two")

        # Each run wrote the file into its own fresh directory, which is what re-running
        # rather than serving a stored value buys: a later step reading it finds it there.
        assert (first.paths.workspace / "receipt.txt").read_text() == "txn-1"
        assert (second.paths.workspace / "receipt.txt").read_text() == "txn-1"
        assert first.paths.workspace != second.paths.workspace
        (call,) = [
            r for r in read_trajectory(second.paths.trajectory) if r["record_type"] == "tool_call"
        ]
        assert (call["re_executed"], call["replayed"]) == (True, False)

    def test_a_failing_tool_raises_rather_than_coming_back_as_an_observation(self, envelope):
        """No model is choosing this call, so there is nobody to hand the failure to."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="never_stocked")
        def never_stocked(sku: str) -> str:
            """Look a product up. Fails when the SKU is not stocked."""
            raise ModelFacingError(f"No product with SKU {sku!r}.")

        with pytest.raises(ModelFacingError) as exc:
            _fixed(
                lambda inputs, ctx: ctx.call_tool("never_stocked", sku="A1"), [never_stocked]
            ).run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        assert "No product with SKU 'A1'" in str(exc.value)

    def test_a_failing_tool_still_leaves_the_call_on_the_record(self, envelope, trajectory):
        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="never_stocked")
        def never_stocked(sku: str) -> str:
            """Look a product up. Fails when the SKU is not stocked."""
            raise ModelFacingError("No product with that SKU.")

        with pytest.raises(ModelFacingError):
            _fixed(
                lambda inputs, ctx: ctx.call_tool("never_stocked", sku="A1"), [never_stocked]
            ).run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        (record,) = _records(trajectory, "tool_call")
        assert record["error"]["class"] == "model_facing"
        assert record["outputs"] is None

    def test_a_node_that_declared_no_tools_refuses_the_call(self, envelope):
        with pytest.raises(ConfigurationError) as exc:
            _fixed(lambda inputs, ctx: ctx.call_tool("anything"), []).run(
                {}, envelope=envelope, run_id=RUN_ID, seed=41
            )

        assert "declared no tools" in str(exc.value)
        assert "Deterministic(fn, tools=[anything])" in str(exc.value)

    def test_a_name_the_node_did_not_declare_lists_what_it_did(self, envelope):
        with pytest.raises(ConfigurationError) as exc:
            _fixed(lambda inputs, ctx: ctx.call_tool("lookup"), [_charging_tool([])]).run(
                {}, envelope=envelope, run_id=RUN_ID, seed=41
            )

        assert "It declared charge_the_card" in str(exc.value)

    def test_a_model_handle_tool_is_refused_on_this_node_kind(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="summarise")
        def summarise(model: ModelHandle, text: str) -> str:
            """Summarise a passage in one sentence."""
            return ""

        with pytest.raises(ConfigurationError) as exc:
            Deterministic(lambda inputs, ctx: None, node_id="step", tools=[summarise])

        assert "ModelHandle" in str(exc.value)
        assert "FT-07" in str(exc.value)

    def test_two_tools_with_one_name_are_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            Deterministic(
                lambda inputs, ctx: None,
                node_id="step",
                tools=[_charging_tool([]), _charging_tool([])],
            )

        assert "more than one tool named charge_the_card" in str(exc.value)

    def test_the_node_reports_its_tools_to_the_manifest(self, envelope, manifest_path):
        _fixed(
            lambda inputs, ctx: ctx.call_tool("charge_the_card", amount="40.00"),
            [_charging_tool([])],
        ).run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        manifest = json.loads(manifest_path.read_text())
        assert [t["name"] for t in manifest["tools"]] == ["charge_the_card"]
        assert manifest["nodes"][0]["tools"] == ["charge_the_card"]

    def test_the_node_is_still_recorded_as_making_no_model_call(self, envelope, trajectory):
        """FT-07 reads `deterministic` as a node that did not sample, so the seed stays null."""
        _fixed(
            lambda inputs, ctx: ctx.call_tool("charge_the_card", amount="40.00"),
            [_charging_tool([])],
        ).run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        (node,) = _records(trajectory, "node_execution")
        assert (node["node_kind"], node["seed"]) == ("deterministic", None)
        assert _records(trajectory, "model_call") == []


# -----------------------------------------------------------------------------------------
# The version a tool carries when its author declared none
# -----------------------------------------------------------------------------------------


class TestTheDerivedVersion:
    """A tool's version is in its cassette key, so an edited body misses rather than serving.

    Nothing had ever recorded one: before this, `version` was `None` on every tool anyone had
    written, and the resume guard comparing `tools.<name>.version` could not fire.
    """

    def _priced(self, price: str, version: str | None = None):
        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="price_of", version=version)
        def price_of(sku: str) -> str:
            """Look up the shelf price of a product by its SKU."""
            return price

        return price_of

    def test_a_declared_version_is_kept(self):
        assert self._priced("40", version="2").version == "2"

    def test_an_undeclared_version_is_hashed_from_the_source(self):
        assert self._priced("40").version.startswith("sha256:")

    def test_two_tools_built_from_one_function_are_separated(self):
        """They shared a version until 2026-08-19, and the version is in the cassette key.

        Two tools of one name and one version answering the same arguments key alike, so a call
        recorded against the first was served as the second's answer.
        """
        assert self._priced("40").version != self._priced("55").version

    def test_a_function_whose_source_cannot_be_read_records_nothing(self):
        assert derived_version(eval("lambda sku: sku")) is None

    def test_an_edited_body_changes_it(self):
        """The two functions share a name, so only reading the source separates them."""

        def before():
            def price_of(sku: str) -> str:
                return "40"

            return price_of

        def after():
            def price_of(sku: str) -> str:
                return "55"

            return price_of

        one, two = before(), after()

        assert one.__name__ == two.__name__ == "price_of"
        assert derived_version(one) != derived_version(two)

    def test_it_covers_data_the_function_closed_over(self):
        """Same source, different captured data, and only the capture separates them."""

        def build(table: dict[str, str]):
            def price_of(sku: str) -> str:
                return table[sku]

            return price_of

        assert derived_version(build({"a": "40"})) != derived_version(build({"a": "55"}))

    def test_what_it_does_not_cover_is_data_read_at_call_time(self):
        """A file or a store the function opens is outside it. Declare `version=` for that."""

        def price_of(sku: str) -> str:
            return open("prices.txt").read()

        assert derived_version(price_of) == derived_version(price_of)


class TestAnArgumentTheModelInvented:
    """An argument no tool takes is a guess, and a guess costs one step rather than the run.

    Dogfood #3 lost two rollouts to this: the model called `find_book(year=...)` and then
    `discover(subjects=...)`, neither of which existed. The schema validation passed both,
    because it ignored keys it did not know, and the `TypeError` from the function was
    classified as caller-facing (`dev-docs/runs/dogfood-3/findings.md` DF3-D2).
    """

    def _derived(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def find_book(title: str, author: str = "") -> dict:
            """Identify one book by title. Returns what the catalogue holds."""
            return {"title": title, "author": author}

        return find_book

    def _declared(self, fn):
        return tool(
            side_effect_class=SideEffectClass.READ_ONLY,
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        )(fn)

    def test_a_derived_schema_refuses_it_to_the_model_rather_than_raising(self):
        with pytest.raises(ModelFacingError) as caught:
            self._derived().call({"title": "Piranesi", "year": 2020})

        assert "['year']" in str(caught.value)
        assert "['author', 'title']" in str(caught.value)

    def test_a_declared_schema_refuses_it_too(self):
        """The two ways of declaring a tool behaved differently, and one had no check at all."""

        def find_book(title: str) -> dict:
            """Identify one book by title."""
            return {"title": title}

        with pytest.raises(ModelFacingError) as caught:
            self._declared(find_book).call({"title": "Piranesi", "year": 2020})

        assert "['year']" in str(caught.value)

    def test_a_function_taking_kwargs_receives_it_and_may_report_it_back(self):
        """The guard dogfood #3 built by hand, which this must not break."""

        def find_book(title: str, **extra) -> dict:
            """Identify one book by title."""
            return {"title": title, "ignored_arguments": sorted(extra)}

        assert self._declared(find_book).call({"title": "Piranesi", "year": 2020}) == {
            "title": "Piranesi",
            "ignored_arguments": ["year"],
        }

    def test_the_schema_offered_to_the_model_is_unchanged(self):
        """The refusal is the library's, not the backend's.

        Adding `additionalProperties: false` to what a backend is sent is a separate question
        with no measurement behind it, so the wire schema stays as it was.
        """
        assert "additionalProperties" not in self._derived().parameters

    def test_a_declared_schema_the_function_cannot_receive_is_refused_at_build_time(self):
        with pytest.raises(ConfigurationError) as caught:

            @tool(
                side_effect_class=SideEffectClass.READ_ONLY,
                parameters={
                    "type": "object",
                    "properties": {"title": {"type": "string"}, "year": {"type": "integer"}},
                },
            )
            def find_book(title: str) -> dict:
                """Identify one book by title."""
                return {"title": title}

        assert "['year']" in str(caught.value)

    def test_a_handle_is_not_an_argument_the_model_may_supply(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def summarise(text: str, model: ModelHandle) -> str:
            """Summarise the text. Returns one paragraph."""
            return text

        with pytest.raises(ModelFacingError):
            summarise.call({"text": "a", "model": "something the model made up"})

    def test_a_wrong_type_still_reports_the_type_and_not_the_name(self):
        """The name check runs first, so it must not swallow what the validator says."""
        with pytest.raises(ModelFacingError) as caught:
            self._derived().call({"title": 4})

        assert "does not match its schema" in str(caught.value)
