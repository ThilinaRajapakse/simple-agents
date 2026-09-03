"""The k-rollout runner, end to end over a real pipeline.

`TestEvalSafety` is the reason this item exists: `tools.py` and FT-20 both said, in the present
tense, that the eval runner refuses a tool whose effects reach outside the run, and until now
nothing did.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from simple_agents import (
    Prompt,
    runs,
    AgentNode,
    Budget,
    Cassette,
    ConfigurationError,
    DeclaredCost,
    Deterministic,
    FakeModelClient,
    LLMNode,
    PacedClient,
    Pipeline,
    PriceBasis,
    RunEnvelope,
    SideEffectClass,
    SimpleAgentsWarning,
    Unknown,
    tool,
)
from simple_agents.evaluation import evaluation_dir, Example, ExampleSet, Outcome
from simple_agents.evaluation.metrics import METRIC_DEFINITIONS
from simple_agents.evaluation.results import EVAL_FORMAT_VERSION, EvalResults
from simple_agents.evaluation.runner import EvalSuite
from simple_agents.models import ToolCallRequest, fake_response

from schemas import Answer

BUDGET = Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None)
EXACT = lambda s: s.answer == s.expected


def build_prompt(inputs, ctx):
    return Prompt.user("Answer the question: {question}", question=inputs["question"])


def one_node_pipeline() -> Pipeline:
    return Pipeline([LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET)


class ScriptedClient:
    """Answers from a mapping of question to payload, so a rollout is deterministic.

    `FakeModelClient` returns queued responses in order, which cannot serve rollouts that run
    on separate threads or in an order the test does not fix.
    """

    def __init__(self, answers: dict[str, str], request_model: str | None = None) -> None:
        self.answers = answers
        self.calls = 0
        self.request_model = request_model

    def identity(self):
        base = FakeModelClient().model_identity
        if self.request_model is None:
            return base
        return replace(base, request_model=self.request_model)

    def complete(self, request):
        self.calls += 1
        asked = request.messages[-1]["content"]
        for question, payload in self.answers.items():
            if question in asked:
                return fake_response(content=payload)
        raise AssertionError(f"nothing scripted for {asked!r}")


ANSWERS = {
    "Which retailer ships from Leeds?": '{"answer": "Kirkwall", "source": "doc"}',
    "Who founded Northgate?": '{"answer": "Alan Reid", "source": "doc"}',
    "When did Kirkwall open?": '{"answer": {"type": "unknown", "reason": "no date"}}',
}


def three_examples(split: str = "held_out") -> ExampleSet:
    return ExampleSet(
        [
            Example(
                id="q1",
                inputs={"question": "Which retailer ships from Leeds?"},
                expected="Kirkwall",
                split=split,
            ),
            Example(
                id="q2",
                inputs={"question": "Who founded Northgate?"},
                expected="Alan Blair",
                split=split,
            ),
            Example(
                id="q3",
                inputs={"question": "When did Kirkwall open?"},
                expected=Unknown(reason="the collection gives no date"),
                split=split,
            ),
        ]
    )


def suite(examples: ExampleSet | None = None, **kwargs) -> EvalSuite:
    return EvalSuite(
        one_node_pipeline(),
        examples if examples is not None else three_examples(),
        answer="answer",
        matches=EXACT,
        **kwargs,
    )


# -- FT-03 --------------------------------------------------------------------------------


class TestContaminatedSplitsAreRefusedBeforeTheRolloutsAreSpent:
    """Measured on dogfood #1: 150 rollouts were paid for and then discarded.

    The report is written into the results file either way, so without this a project reads
    that its number was measured over a contaminated split off a file it produced by running
    the whole evaluation.
    """

    def _split_sharing_a_source(self) -> ExampleSet:
        return ExampleSet(
            [
                Example(
                    id="q1",
                    inputs={"question": "Which retailer ships from Leeds?"},
                    expected="Kirkwall",
                    split="held_out",
                    source="doc:kirkwall-history",
                ),
                Example(
                    id="q2",
                    inputs={"question": "When did it open?"},
                    expected="1994",
                    split="dev",
                    source="doc:kirkwall-history",
                ),
            ]
        )

    def test_it_refuses_and_names_the_pair_and_what_the_run_would_have_cost(self, tmp_path) -> None:
        built = suite(self._split_sharing_a_source(), contamination_threshold=0.8)

        with pytest.raises(ConfigurationError) as caught:
            built.run(
                envelope=RunEnvelope(run_dir=str(tmp_path)),
                model=ScriptedClient({}),
                split="held_out",
                k=5,
            )

        message = str(caught.value)
        assert "1 pair(s)" in message
        assert "doc:kirkwall-history" in message
        assert "5 rollout(s)" in message
        assert not list(tmp_path.glob("eval_*"))

    def test_allow_contaminated_split_measures_over_it_anyway(self, tmp_path) -> None:
        built = suite(self._split_sharing_a_source(), contamination_threshold=0.8)

        results = built.run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=ScriptedClient({"Which retailer ships from Leeds?": "Kirkwall"}),
            split="held_out",
            k=1,
            seed=41,
            allow_contaminated_split=True,
        )

        assert results.contamination.clean is False

    def test_a_suite_with_no_threshold_runs_the_check_it_was_never_given(self, tmp_path) -> None:
        built = suite(self._split_sharing_a_source())

        results = built.run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=ScriptedClient({"Which retailer ships from Leeds?": "Kirkwall"}),
            split="held_out",
            k=1,
            seed=41,
        )

        assert results.contamination is None


class TestPacingForTheRolloutsInFlight:
    """Dogfood #1 run 2 took nine rate-limit errors unpaced, then two more at the floor of 1."""

    def _hosted(self) -> Any:
        client = ScriptedClient(ANSWERS)
        client.identity = lambda: replace(FakeModelClient().model_identity, backend="hosted_api")
        return client

    def test_an_unpaced_hosted_client_running_rollouts_at_once_warns(self, tmp_path) -> None:
        built = EvalSuite(one_node_pipeline(), three_examples(), answer="answer", matches=EXACT)

        with pytest.warns(SimpleAgentsWarning, match="does not pace"):
            built.run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=self._hosted(),
                split="held_out",
                k=1,
                seed=41,
                concurrency=4,
            )

    def test_it_says_nothing_at_concurrency_one_or_against_a_local_backend(self, tmp_path) -> None:
        built = EvalSuite(one_node_pipeline(), three_examples(), answer="answer", matches=EXACT)

        with warnings.catch_warnings():
            warnings.simplefilter("error", SimpleAgentsWarning)
            built.run(
                envelope=RunEnvelope(run_dir=tmp_path / "serial"),
                model=self._hosted(),
                split="held_out",
                k=1,
                seed=41,
                concurrency=1,
            )
            built.run(
                envelope=RunEnvelope(run_dir=tmp_path / "local"),
                model=ScriptedClient(ANSWERS),
                split="held_out",
                k=1,
                seed=41,
                concurrency=4,
            )

    def test_a_paced_client_takes_the_concurrency_as_its_floor(self, tmp_path) -> None:
        client = PacedClient(self._hosted())
        built = EvalSuite(one_node_pipeline(), three_examples(), answer="answer", matches=EXACT)

        assert client.request_floor == 1

        built.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=client,
            split="held_out",
            k=1,
            seed=41,
            concurrency=4,
        )

        assert client.request_floor == 4

    def test_a_floor_the_caller_chose_is_not_overridden(self, tmp_path) -> None:
        client = PacedClient(self._hosted(), min_remaining_requests=10)
        built = EvalSuite(one_node_pipeline(), three_examples(), answer="answer", matches=EXACT)

        built.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=client,
            split="held_out",
            k=1,
            seed=41,
            concurrency=4,
        )

        assert client.request_floor == 10


class TestOneEvaluationPerDirectory:
    """Dogfood #1 run 2 re-ran an evaluation and every per-node count doubled."""

    def test_running_twice_into_one_directory_is_refused(self, tmp_path) -> None:
        built = EvalSuite(one_node_pipeline(), three_examples(), answer="answer", matches=EXACT)
        run = lambda: built.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        run()

        with pytest.raises(ConfigurationError) as raised:
            run()

        message = str(raised.value)
        assert "already holds an evaluation's rollouts" in message
        assert "appends to" in message

    def test_a_different_model_writes_elsewhere_and_is_not_refused(self, tmp_path) -> None:
        """Two arms of a model comparison are two evaluations, not one re-run."""
        built = EvalSuite(one_node_pipeline(), three_examples(), answer="answer", matches=EXACT)

        first = built.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS, request_model="small"),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )
        second = built.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS, request_model="medium"),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        assert first.eval_id != second.eval_id


# -- FT-20 --------------------------------------------------------------------------------


class TestEvalSafety:
    """The check item 5's session B ran by hand, now the runner's own."""

    def spending_pipeline(self) -> Pipeline:
        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=DeclaredCost(currency="USD", per_call=0.005),
        )
        def paid_search(query: str) -> str:
            """Search through a paid provider. Returns the results."""
            raise AssertionError("a rollout must never execute this")

        return Pipeline(
            [
                AgentNode(
                    build_prompt,
                    tools=[paid_search],
                    output_schema=Answer,
                    node_id="hunt",
                    budget=Budget(
                        max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=BUDGET,
        )

    def test_a_rollout_over_a_spends_money_tool_is_refused(self, tmp_path) -> None:
        spending = EvalSuite(
            self.spending_pipeline(), three_examples(), answer="answer", matches=EXACT
        )

        with pytest.raises(ConfigurationError) as raised:
            spending.run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=ScriptedClient(ANSWERS),
                split="held_out",
                k=5,
            )

        message = str(raised.value)
        assert "paid_search" in message
        assert "spends_money" in message
        assert "15 rollout(s) (3 examples × 5)" in message
        assert "may call it more than once" in message
        assert "max_spend" in message
        assert "Cassette.replay" in message

    def test_nothing_runs_before_the_refusal(self, tmp_path) -> None:
        """The tool body raises if reached, and so would the model client."""
        run_dir = tmp_path / "runs"
        spending = EvalSuite(
            self.spending_pipeline(), three_examples(), answer="answer", matches=EXACT
        )

        with pytest.raises(ConfigurationError):
            spending.run(
                envelope=RunEnvelope(run_dir=run_dir),
                model=FakeModelClient(responses=[]),
                split="held_out",
                k=2,
            )

        assert not run_dir.exists()

    def test_an_irreversible_tool_is_refused_too(self, tmp_path) -> None:
        @tool(side_effect_class=SideEffectClass.IRREVERSIBLE)
        def place_order(sku: str) -> str:
            """Place an order for one item. Returns the order reference."""
            raise AssertionError("a rollout must never execute this")

        pipeline = Pipeline(
            [
                AgentNode(
                    build_prompt,
                    tools=[place_order],
                    output_schema=Answer,
                    node_id="order",
                    budget=Budget(
                        max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=BUDGET,
        )

        with pytest.raises(ConfigurationError) as raised:
            EvalSuite(pipeline, three_examples(), answer="answer", matches=EXACT).run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=ScriptedClient(ANSWERS),
                split="held_out",
                k=2,
            )

        assert "irreversible" in str(raised.value)

    def test_replaying_lets_it_run_because_the_tool_is_served_from_the_file(self, tmp_path) -> None:
        """Replay never executes a filed tool, so the k×n repetitions never happen."""
        cassette = tmp_path / "c.jsonl"
        cassette.write_text("")
        spending = EvalSuite(
            self.spending_pipeline(), three_examples(), answer="answer", matches=EXACT
        )

        # A miss still stops the run, which is what a cassette recorded from a different
        # pipeline should do. What matters here is that the refusal above did not fire.
        results = spending.run(
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.replay(cassette)),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=2,
            concurrency=1,
        )

        # A miss is `no_response`: the recording held no answer, so nothing measured the agent.
        assert all(r.outcome is Outcome.NO_RESPONSE for r in results.rollouts)
        assert results.metrics["accuracy"].left_out == {"no_response": 6}

    def test_a_spending_tool_on_a_deterministic_node_is_refused_too(self, tmp_path) -> None:
        """A tool called at a fixed point runs once per rollout the same as a chosen one."""

        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=DeclaredCost(currency="USD", per_call=0.005),
        )
        def paid_search(query: str) -> str:
            """Search through a paid provider. Returns the results."""
            raise AssertionError("a rollout must never execute this")

        def look_things_up(inputs, ctx):
            return ctx.call_tool("paid_search", query=inputs["question"])

        pipeline = Pipeline(
            [
                Deterministic(look_things_up, node_id="search", tools=[paid_search]),
                LLMNode(build_prompt, output_schema=Answer, node_id="extract"),
            ],
            budget=BUDGET,
        )

        with pytest.raises(ConfigurationError) as raised:
            EvalSuite(pipeline, three_examples(), answer="answer", matches=EXACT).run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=ScriptedClient(ANSWERS),
                split="held_out",
                k=5,
            )

        message = str(raised.value)
        assert "paid_search" in message
        assert "spends_money" in message
        assert "15 rollout(s) (3 examples × 5)" in message
        assert "may call it more than once" in message
        assert "max_spend" in message

    def test_a_tool_on_a_deterministic_node_is_in_the_results_config(self, tmp_path) -> None:
        """The results file and the manifest name the same tools (FT-15)."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def look_up(query: str) -> str:
            """Search the collection. Returns matching passages."""
            return "Kirkwall ships from Leeds."

        def search_then_answer(inputs, ctx):
            ctx.call_tool("look_up", query=inputs["question"])
            return inputs

        pipeline = Pipeline(
            [
                Deterministic(search_then_answer, node_id="search", tools=[look_up]),
                LLMNode(build_prompt, output_schema=Answer, node_id="extract"),
            ],
            budget=BUDGET,
        )

        results = EvalSuite(pipeline, three_examples(), answer="answer", matches=EXACT).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=1,
            concurrency=1,
        )

        assert [t["name"] for t in results.config["tools"]] == ["look_up"]
        assert results.config["tools"][0]["side_effect_class"] == "read_only"

    def test_a_read_only_tool_and_a_workspace_write_are_allowed(self, tmp_path) -> None:
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def look_up(query: str) -> str:
            """Search the collection. Returns matching passages."""
            return "Kirkwall ships from Leeds."

        pipeline = Pipeline(
            [
                AgentNode(
                    build_prompt,
                    tools=[look_up],
                    output_schema=Answer,
                    node_id="hunt",
                    budget=Budget(
                        max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=BUDGET,
        )

        results = EvalSuite(pipeline, three_examples(), answer="answer", matches=EXACT).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=AgentClient(),
            split="held_out",
            k=2,
            concurrency=1,
        )

        assert results.n == 3


class AgentClient:
    """Calls the tool once, then finishes with the same answer every time."""

    def identity(self):
        return FakeModelClient().model_identity

    def complete(self, request):
        if not any(m.get("role") == "tool" for m in request.messages):
            return fake_response(
                tool_calls=[ToolCallRequest(id="c1", name="look_up", arguments={"query": "leeds"})]
            )
        return fake_response(
            tool_calls=[
                ToolCallRequest(
                    id="c2",
                    name="finish",
                    arguments={"answer": "Kirkwall", "source": "doc"},
                )
            ]
        )


# -- rollouts and seeds -------------------------------------------------------------------


class TestRollouts:
    def test_each_example_runs_k_times_and_every_rollout_is_recorded(self, tmp_path) -> None:
        results = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=4,
        )

        assert len(results.rollouts) == 12
        assert results.k == 4
        assert results.n == 3
        assert sorted({r.example_id for r in results.rollouts}) == ["q1", "q2", "q3"]

    def test_every_rollout_has_its_own_seed_derived_from_the_evaluations(self, tmp_path) -> None:
        first = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path / "a"),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=3,
            seed=41,
        )
        again = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path / "b"),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=3,
            seed=41,
        )
        other = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path / "c"),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=3,
            seed=42,
        )

        seeds = [r.seed for r in first.rollouts]
        assert len(set(seeds)) == 9
        assert seeds == [r.seed for r in again.rollouts]
        assert seeds != [r.seed for r in other.rollouts]

    def test_a_seed_is_generated_and_recorded_when_none_is_given(self, tmp_path) -> None:
        results = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=2,
        )

        assert isinstance(results.config["seed"], int)
        assert results.config["bootstrap"]["seed"] == results.config["seed"]

    def test_every_rollout_leaves_a_trajectory_that_can_be_opened(self, tmp_path) -> None:
        results = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=2,
        )

        for rollout in results.rollouts:
            assert Path(rollout.trajectory).exists()
            assert rollout.run_id

    def test_rollouts_write_under_one_directory_named_for_the_evaluation(self, tmp_path) -> None:
        results = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=2,
        )

        assert (evaluation_dir(tmp_path, results.eval_id) / "q1-0").is_dir()
        assert (evaluation_dir(tmp_path, results.eval_id) / "q3-1").is_dir()

    def test_only_the_named_split_runs(self, tmp_path) -> None:
        mixed = ExampleSet(
            [
                Example(
                    id="d1",
                    inputs={"question": "Which retailer ships from Leeds?"},
                    expected="Kirkwall",
                    split="dev",
                ),
                Example(
                    id="h1",
                    inputs={"question": "Who founded Northgate?"},
                    expected="Alan Reid",
                    split="held_out",
                ),
            ]
        )

        results = suite(mixed).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=2,
        )

        assert {r.example_id for r in results.rollouts} == {"h1"}

    def test_a_rollout_that_raised_is_failed_and_carries_its_error(self, tmp_path) -> None:
        def explode(inputs, ctx):
            raise RuntimeError("the corpus is unreadable")

        broken = EvalSuite(
            Pipeline([Deterministic(explode, node_id="load")], budget=BUDGET),
            three_examples(),
            answer="answer",
            matches=EXACT,
        )

        results = broken.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=2,
            concurrency=1,
        )

        assert all(r.outcome is Outcome.FAILED for r in results.rollouts)
        assert "unreadable" in results.rollouts[0].error["message"]
        assert results.metrics["failure_rate"].value == 1.0

    def test_answer_takes_a_function_as_well_as_a_field_name(self, tmp_path) -> None:
        results = EvalSuite(
            one_node_pipeline(),
            three_examples(),
            answer=lambda output: output.answer,
            matches=EXACT,
        ).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=1,
        )

        assert results.metrics["accuracy"].value == pytest.approx(2 / 3)


# -- what comes out -----------------------------------------------------------------------


class TestResults:
    def run_one(self, tmp_path, **kwargs) -> EvalResults:
        return suite(**kwargs.pop("suite_kwargs", {})).run(
            envelope=RunEnvelope(
                run_dir=tmp_path,
                cost_basis=PriceBasis(
                    currency="USD", input_uncached_per_mtok=1.0, output_per_mtok=2.0
                ),
            ),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=3,
            seed=41,
            **kwargs,
        )

    def test_the_three_answers_are_sorted_into_three_different_outcomes(self, tmp_path) -> None:
        """q1 is right, q2 asserts the wrong name, q3 abstains where absence is correct."""
        results = self.run_one(tmp_path)

        by_example = {r.example_id: r.outcome for r in results.rollouts}
        assert by_example["q1"] is Outcome.CORRECT
        assert by_example["q2"] is Outcome.FALSE_CONFIDENCE
        assert by_example["q3"] is Outcome.CORRECT_ABSTENTION

    def test_false_confidence_and_recall_are_reported_separately(self, tmp_path) -> None:
        results = self.run_one(tmp_path)

        assert results.metrics["false_confidence_rate"].value == pytest.approx(1 / 3)
        assert results.metrics["recall"].value == pytest.approx(0.5)
        assert results.metrics["recall"].interval.n == 2
        assert results.metrics["accuracy"].interval.n == 3

    def test_every_metric_carries_an_interval_with_its_n_and_k(self, tmp_path) -> None:
        results = self.run_one(tmp_path)

        interval = results.metrics["accuracy"].interval
        assert interval.k == 3
        assert interval.low <= interval.point <= interval.high

    def test_per_node_metrics_name_the_node(self, tmp_path) -> None:
        results = self.run_one(tmp_path)

        assert set(results.nodes) == {"extract"}
        assert results.nodes["extract"].executions == 9
        assert results.nodes["extract"].model_calls == 9
        assert results.nodes["extract"].absent_outputs == 3

    def test_the_config_says_what_was_measured(self, tmp_path) -> None:
        results = self.run_one(tmp_path)

        config = results.config
        assert config["split"] == "held_out"
        assert (config["k"], config["n"], config["seed"]) == (3, 3, 41)
        assert config["example_set"]["content_hash"].startswith("ex_")
        assert config["example_set"]["absent_proportion"] == pytest.approx(1 / 3)
        # The manifest's own node entries, so a variant comparison can name what differed.
        assert config["nodes"] == [
            {
                "node_id": "extract",
                "node_kind": "llm",
                "successors": [],
                "route": None,
                "consultation_route": None,
                "loop": None,
                "on_error": None,
                "retry": None,
                "schema": "sha256:220e748d69ffc27c",
                "accepts": None,
                "planned": False,
                "touches": [],
                "allow_unknown": True,
                "context_builder": {"name": "AppendAll", "config": {"max_input_tokens": None}},
                "stream": False,
                "model": None,
                "sampling": {"temperature": None, "max_output_tokens": None, "extra": {}},
                "tools": [],
                "finish_check": None,
                "node_budget": None,
                "node_budget_per_item": None,
                "fan_out": {"over": None, "keep": [], "max_failures": None},
            }
        ]
        assert config["cost_basis"]["kind"] == "price"
        # An evaluation records its rollouts, and the config says the mode they ran under
        # rather than the one the caller's envelope declared.
        assert config["cassette"]["mode"] == "record"

    def test_the_config_carries_the_prompt_versions_a_regression_is_traced_through(
        self, tmp_path
    ) -> None:
        results = self.run_one(tmp_path)

        assert results.config["prompts"]["extract"]["source"] == "derived"
        assert results.config["prompts"]["extract"]["version"].startswith("sha256:")

    def test_totals_sum_the_tokens_and_derive_the_cost(self, tmp_path) -> None:
        results = self.run_one(tmp_path)

        assert results.totals["tokens"]["input_uncached"] == 90
        assert results.totals["cost"]["currency"] == "USD"
        assert results.totals["cost"]["value"] > 0

    def test_contamination_is_recorded_when_a_threshold_is_configured(self, tmp_path) -> None:
        results = self.run_one(tmp_path, suite_kwargs={"contamination_threshold": 0.8})

        assert results.contamination.threshold == 0.8
        assert results.contamination.clean is True

    def test_contamination_is_absent_when_no_threshold_was_given(self, tmp_path) -> None:
        assert self.run_one(tmp_path).contamination is None

    def test_the_file_round_trips(self, tmp_path) -> None:
        results = self.run_one(tmp_path)
        path = results.write(tmp_path / "results.json")

        read_back = EvalResults.read(path)

        assert json.loads(path.read_text())["eval_format_version"] == EVAL_FORMAT_VERSION
        assert read_back.eval_id == results.eval_id
        assert read_back.config == results.config
        assert len(read_back.rollouts) == len(results.rollouts)
        assert read_back.metrics["recall"].value == results.metrics["recall"].value
        assert read_back.nodes["extract"].model_calls == 9
        assert read_back.scores_by_example() == results.scores_by_example()

    def test_absence_survives_the_round_trip(self, tmp_path) -> None:
        path = self.run_one(tmp_path).write(tmp_path / "results.json")

        abstained = [r for r in EvalResults.read(path).rollouts if r.example_id == "q3"]

        assert all(isinstance(r.answer, Unknown) for r in abstained)

    def test_the_report_carries_an_interval_beside_every_rate(self, tmp_path) -> None:
        """No line of it can be quoted as a bare percentage (FT-06)."""
        report = self.run_one(tmp_path).report()

        for name in METRIC_DEFINITIONS:
            line = next(l for l in report.splitlines() if l.strip().startswith(name))
            assert "%" in line
            assert "[" in line and "]" in line
            assert "n=" in line

    def test_the_report_names_the_nodes_and_how_they_ended(self, tmp_path) -> None:
        report = self.run_one(tmp_path).report()

        assert "extract" in report
        assert "llm" in report
        assert "3 example(s) x 3 rollout(s)" in report
        assert "resampling examples" in report

    def test_an_undefined_rate_says_so_rather_than_printing_zero(self, tmp_path) -> None:
        absent_only = ExampleSet(
            [
                Example(
                    id="q3",
                    inputs={"question": "When did Kirkwall open?"},
                    expected=Unknown(reason="no date"),
                    split="held_out",
                )
            ]
        )
        results = suite(absent_only).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=2,
        )

        line = next(l for l in results.report().splitlines() if "recall" in l)

        assert "undefined" in line
        assert "no denominator" in line

    def test_reading_a_file_of_another_version_is_refused(self, tmp_path) -> None:
        path = tmp_path / "old.json"
        path.write_text(
            json.dumps({"eval_format_version": "0.0", "eval_id": "e", "created_at": ""})
        )

        with pytest.raises(ConfigurationError) as raised:
            EvalResults.read(path)

        assert "0.0" in str(raised.value)


# -- refusals -----------------------------------------------------------------------------


class TestRefusals:
    def test_the_update_cassette_mode_is_refused(self, tmp_path) -> None:
        """A number from a mixture of live and replayed calls says which was which nowhere."""
        with pytest.raises(ConfigurationError) as raised:
            suite().run(
                envelope=RunEnvelope(
                    run_dir=tmp_path, cassette=Cassette.update(tmp_path / "c.jsonl")
                ),
                model=ScriptedClient(ANSWERS),
                split="held_out",
                k=2,
            )

        assert "Cassette.update" in str(raised.value)
        assert "Cassette.replay" in str(raised.value)

    def test_matches_has_no_default(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            EvalSuite(one_node_pipeline(), three_examples(), answer="answer", matches=None)

        assert "decision about the task" in str(raised.value)

    def test_k_below_one_is_refused_and_k_of_one_runs(self, tmp_path) -> None:
        """FT-05 is a check, not a refusal: k=1 can be legitimate at temperature 0."""
        with pytest.raises(ConfigurationError):
            suite().run(
                envelope=RunEnvelope(run_dir=tmp_path / "a"),
                model=ScriptedClient(ANSWERS),
                split="held_out",
                k=0,
            )

        results = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path / "b"),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=1,
        )

        assert results.k == 1

    def test_two_example_ids_that_would_share_a_directory_are_refused(self, tmp_path) -> None:
        colliding = ExampleSet(
            [
                Example(
                    id="q/1",
                    inputs={"question": "Which retailer ships from Leeds?"},
                    expected="Kirkwall",
                    split="held_out",
                ),
                Example(
                    id="q 1",
                    inputs={"question": "Who founded Northgate?"},
                    expected="Alan Reid",
                    split="held_out",
                ),
            ]
        )

        with pytest.raises(ConfigurationError) as raised:
            suite(colliding).run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=ScriptedClient(ANSWERS),
                split="held_out",
                k=1,
            )

        assert "overwrite each other" in str(raised.value)

    def test_an_unknown_split_is_refused_before_anything_runs(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            suite().run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=ScriptedClient(ANSWERS),
                split="test",
                k=2,
            )

        assert "no split called 'test'" in str(raised.value)


# -- parallelism --------------------------------------------------------------------------


class TestConcurrency:
    def test_running_in_parallel_gives_the_same_results_as_running_serially(self, tmp_path) -> None:
        serial = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path / "s"),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=4,
            seed=41,
            concurrency=1,
        )
        parallel = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path / "p"),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=4,
            seed=41,
            concurrency=8,
        )

        assert [r.to_record()["outcome"] for r in serial.rollouts] == [
            r.to_record()["outcome"] for r in parallel.rollouts
        ]
        assert [r.seed for r in serial.rollouts] == [r.seed for r in parallel.rollouts]
        assert serial.metrics["accuracy"].value == parallel.metrics["accuracy"].value

    def test_parallel_rollouts_record_into_one_cassette_without_losing_calls(
        self, tmp_path
    ) -> None:
        cassette_path = tmp_path / "c.jsonl"

        results = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(cassette_path)),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=6,
            seed=41,
            concurrency=8,
        )

        # Each rollout has its own seed, so each is a distinct key: 3 examples x 6 rollouts.
        assert len(Cassette.replay(cassette_path).variants()) == 18
        assert len(results.rollouts) == 18

    def test_a_recorded_evaluation_replays_with_no_client_at_all(self, tmp_path) -> None:
        cassette_path = tmp_path / "c.jsonl"
        live = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=3,
            seed=41,
        )

        offline = FakeModelClient(responses=[])
        replayed = suite().run(
            envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)),
            model=offline,
            split="held_out",
            k=3,
            seed=41,
        )

        assert offline.requests == []
        assert replayed.metrics["accuracy"].value == live.metrics["accuracy"].value
        assert replayed.nodes["extract"].replayed_calls == 9


class TestPerNodeReachAndAccuracy:
    """A node in a graph does not run on every rollout, so every figure it carries has a reach.

    The branch is decided by the answer the model gave, so which rollouts reach `verify` is a
    property of the run rather than of the test.
    """

    def _pipeline(self) -> Pipeline:
        def classify(inputs, ctx):
            return inputs

        def pick(output, ctx):
            # A found answer goes for verification; an absent one goes straight to the report.
            return "report" if isinstance(output.answer, Unknown) else "verify"

        def verify(inputs, ctx):
            return Prompt.user("Confirm this answer: {answer}", answer=inputs.answer)

        def report(inputs, ctx):
            if isinstance(inputs, dict) or hasattr(inputs, "fired"):
                found = inputs["verify"] if "verify" in inputs.fired else inputs["extract"]
                return found
            return inputs

        return Pipeline(
            [
                LLMNode(
                    build_prompt,
                    output_schema=Answer,
                    node_id="extract",
                    successors=["verify", "report"],
                    route=pick,
                ),
                LLMNode(verify, output_schema=Answer, node_id="verify", successors=["report"]),
                Deterministic(report, node_id="report", successors=[]),
            ],
            budget=BUDGET,
        )

    def _examples(self) -> ExampleSet:
        return ExampleSet(
            [
                Example(
                    id="found",
                    inputs={"question": "Which retailer ships from Leeds?"},
                    expected="Kirkwall",
                    split="held_out",
                    expected_by_node={"extract": "Kirkwall"},
                ),
                Example(
                    id="absent",
                    inputs={"question": "When did Kirkwall open?"},
                    expected=Unknown(reason="no date"),
                    split="held_out",
                    expected_by_node={"extract": Unknown(reason="no date")},
                ),
            ]
        )

    def _suite(self, **extra) -> EvalSuite:
        return EvalSuite(
            self._pipeline(),
            self._examples(),
            answer=lambda output: output.answer if hasattr(output, "answer") else output,
            matches=EXACT,
            **extra,
        )

    def _client(self) -> ScriptedClient:
        return ScriptedClient(
            {
                **ANSWERS,
                "Confirm this answer:": '{"answer": "Kirkwall", "source": "doc"}',
            }
        )

    def test_a_node_on_one_arm_reaches_only_the_rollouts_routed_to_it(self, tmp_path):
        results = self._suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=self._client(),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

        assert results.nodes["extract"].reached == 4
        assert results.nodes["verify"].reached == 2
        assert results.nodes["verify"].runs == 4
        assert results.nodes["verify"].reach.interval.point == pytest.approx(0.5)

    def test_reach_is_recorded_on_every_rollout(self, tmp_path):
        results = self._suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=self._client(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        by_example = {r.example_id: r for r in results.rollouts}
        assert by_example["found"].nodes["verify"].reached is True
        assert by_example["absent"].nodes["verify"].reached is False

    def test_per_node_accuracy_is_reported_where_the_example_labels_the_node(self, tmp_path):
        results = self._suite(
            node_matches={"extract": lambda s: s.answer.get("answer") == s.expected}
        ).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=self._client(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        accuracy = results.nodes["extract"].accuracy
        assert accuracy is not None
        assert accuracy.rollouts == 2
        assert accuracy.interval.point == pytest.approx(1.0)
        assert results.nodes["verify"].accuracy is None

    def test_the_recorded_output_is_what_a_node_matcher_sees(self, tmp_path):
        seen: list = []

        self._suite(node_matches={"extract": lambda s: seen.append(s.answer) or True}).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=self._client(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        # Plain recorded data, read back from the trajectory, rather than the `Answer` object.
        assert all(isinstance(output, dict) for output in seen)
        assert {"answer", "source"} <= set(seen[0])

    def test_a_label_and_the_output_it_is_compared_against_arrive_in_one_shape(self, tmp_path):
        """Both sides of a node matcher, on the example whose answer is absent.

        The label is an ``Unknown`` and the recorded output holds the tagged object. If only
        one side is decoded, a matcher comparing them stops matching and the accuracy drops
        with nothing raising, which is why this asserts the pair rather than either alone.
        """
        pairs: list[tuple] = []

        results = self._suite(
            node_matches={
                "extract": lambda s: (
                    pairs.append((s.answer, s.expected)) or s.answer.get("answer") == s.expected
                )
            }
        ).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=self._client(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        absent = [(output, expected) for output, expected in pairs if isinstance(expected, Unknown)]
        assert len(absent) == 1
        output, expected = absent[0]
        assert isinstance(output["answer"], Unknown)
        assert output["answer"] == expected
        assert results.nodes["extract"].accuracy.interval.point == pytest.approx(1.0)

    def test_node_matches_naming_no_node_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._suite(node_matches={"typo": EXACT})
        message = str(exc.value)
        assert "node_matches names 'typo'" in message
        assert "'extract', 'report', 'verify'" in message

    def test_the_results_config_carries_the_edges_and_the_routes(self, tmp_path):
        results = self._suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=self._client(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        nodes = {n["node_id"]: n for n in results.config["nodes"]}
        assert nodes["extract"]["successors"] == ["verify", "report"]
        assert nodes["extract"]["route"]["source"] == "derived"
        assert nodes["report"]["route"] is None


# -- reading the answer off the output ----------------------------------------------------


class TestAnswerExtraction:
    def _pipeline_returning(self, payload) -> Pipeline:
        def report(inputs, ctx):
            return payload

        return Pipeline([Deterministic(report, node_id="report")])

    def _one_example(self, expected) -> ExampleSet:
        return ExampleSet([Example(id="q1", inputs={}, expected=expected, split="held_out")])

    def test_a_dict_output_is_read_by_key(self, tmp_path) -> None:
        results = EvalSuite(
            self._pipeline_returning({"answer": "Kirkwall", "notes": "from the report"}),
            self._one_example("Kirkwall"),
            answer="answer",
            matches=EXACT,
        ).run(envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=1)

        assert results.metrics["accuracy"].value == 1.0

    def test_a_key_the_output_does_not_carry_refuses_rather_than_failing_every_rollout(
        self, tmp_path
    ) -> None:
        with pytest.raises(ConfigurationError) as exc:
            EvalSuite(
                self._pipeline_returning({"verdict": "Kirkwall"}),
                self._one_example("Kirkwall"),
                answer="answer",
                matches=EXACT,
            ).run(envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=1)

        assert "verdict" in str(exc.value)
        assert "answer=" in str(exc.value)

    def test_a_field_the_schema_does_not_carry_refuses_naming_the_fields(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as exc:
            EvalSuite(one_node_pipeline(), three_examples(), answer="respnse", matches=EXACT).run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=ScriptedClient(ANSWERS),
                split="held_out",
                k=1,
            )

        assert "answer" in str(exc.value)

    def test_an_output_that_is_a_reported_absence_is_the_answer(self, tmp_path) -> None:
        results = EvalSuite(
            self._pipeline_returning(Unknown(reason="nothing found")),
            self._one_example(Unknown(reason="absent")),
            answer="answer",
            matches=EXACT,
        ).run(envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=1)

        assert results.rollouts[0].outcome is Outcome.CORRECT_ABSTENTION


class TestARolloutIsNeverLive:
    """A project whose envelope is the one it ships with would otherwise evaluate into its
    own live runs, and `runs(live=True)` would return rollouts that are not the project's own."""

    def test_the_rollouts_of_a_live_envelope_are_not_live(self, tmp_path) -> None:
        suite = EvalSuite(one_node_pipeline(), three_examples(), answer="answer", matches=EXACT)
        suite.run(
            envelope=RunEnvelope(run_dir=tmp_path, live=True),
            model=ScriptedClient(ANSWERS),
            split="held_out",
            k=1,
        )

        assert runs(tmp_path, nested=True)
        assert runs(tmp_path, nested=True, live=True) == []
