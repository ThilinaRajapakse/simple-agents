"""What an evaluation is filed under, and what it does with a rollout that raised.

Two defects from the 2026-08-13 checkpoint, both of which let a number describe something that
never ran.

`eval_id` hashed the graph's shape and nothing about the configuration walked over it, so four
edits produced a byte-identical directory name: `temperature`, `max_output_tokens`,
`allow_unknown`, and the pipeline budget. Adding or removing a tool did too. A variant sweep
then refused its own leading example after paying for a baseline arm, `resume_from` mixed
rollouts across a temperature change, and `rescore` scored rollouts a different configuration
produced.

`_rollout` caught every exception and scored `failed`, so a suite running against a model id the
backend no longer served reported `failure_rate` 1.0 with complete intervals and no refusal.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from simple_agents.pipeline.recording import _node_entries
from simple_agents.builtins import Reply, Shelved

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    Cassette,
    ConfigurationError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    Tool,
    tool,
)
from simple_agents.builtins.consult import ModelReader, consult
from simple_agents.records.cassette import CassetteMiss
from simple_agents.errors import (
    CallerFacingError,
    RunSuspended,
    SimpleAgentsWarning,
    Suspend,
)
from simple_agents.evaluation import Example, ExampleSet, Outcome
from simple_agents.evaluation.runner import EvalSuite
from simple_agents.models import ModelIdentity, fake_response

from schemas import Answer

BUDGET = Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None)
EXACT = lambda s: s.answer == s.expected

ANSWERS = {
    "Which retailer ships from Leeds?": '{"answer": "Kirkwall", "source": "doc"}',
    "Who founded Northgate?": '{"answer": "Alan Reid", "source": "doc"}',
}


def build_prompt(inputs, ctx):
    return Prompt.user("Answer the question: {question}", question=inputs["question"])


class Scripted:
    """Answers from a mapping of question to payload, so a rollout is deterministic."""

    def __init__(self, request_model: str = "fake-model") -> None:
        self.request_model = request_model

    def identity(self):
        return ModelIdentity(
            backend="self_hosted", request_model=self.request_model, model_revision="0" * 40
        )

    def complete(self, request):
        asked = request.messages[-1]["content"]
        for question, payload in ANSWERS.items():
            if question in asked:
                return fake_response(content=payload)
        raise AssertionError(f"nothing scripted for {asked!r}")


def two_examples(split: str = "held_out") -> ExampleSet:
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
                expected="Alan Reid",
                split=split,
            ),
        ]
    )


def look_up() -> Tool:
    return Tool(
        name="look_up",
        description="Search the collection. Returns matching entries.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        side_effect_class=SideEffectClass.READ_ONLY,
        fn=lambda query: "Kirkwall ships from Leeds.",
    )


def suite_over(pipeline: Pipeline) -> EvalSuite:
    return EvalSuite(pipeline, two_examples(), answer="answer", matches=EXACT)


def eval_id_of(pipeline: Pipeline) -> str:
    return suite_over(pipeline)._eval_id(41, "held_out", 3, Scripted())


class TestTheEvalIdSeparatesWhatWasMeasured:
    """Each of these produced a byte-identical `eval_id` before the checkpoint."""

    def _baseline(self, **kwargs) -> Pipeline:
        return Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract", **kwargs)],
            budget=BUDGET,
        )

    def test_the_same_pipeline_twice_is_one_directory(self) -> None:
        assert eval_id_of(self._baseline()) == eval_id_of(self._baseline())

    @pytest.mark.parametrize(
        "moved",
        [
            {"temperature": 0.7},
            {"max_output_tokens": 64},
            {"allow_unknown": False},
            {"extra": {"guided_json": True}},
        ],
    )
    def test_a_moved_sampling_parameter_names_another_directory(self, moved) -> None:
        assert eval_id_of(self._baseline()) != eval_id_of(self._baseline(**moved))

    def test_a_moved_pipeline_budget_names_another_directory(self) -> None:
        tighter = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
            budget=Budget(max_steps=3, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None),
        )

        assert eval_id_of(self._baseline()) != eval_id_of(tighter)

    def _agent(self, **kwargs) -> Pipeline:
        declared = {
            "tools": [],
            "budget": Budget(max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=None),
            **kwargs,
        }
        return Pipeline(
            [AgentNode(build_prompt, output_schema=Answer, node_id="hunt", **declared)],
            budget=BUDGET,
        )

    def test_a_tool_added_to_an_agent_node_names_another_directory(self) -> None:
        assert eval_id_of(self._agent()) != eval_id_of(self._agent(tools=[look_up()]))

    def test_a_node_budget_names_another_directory(self) -> None:
        tighter = Budget(max_steps=2, max_tokens=1_000, max_cost=None, max_wall_clock_ms=None)

        assert eval_id_of(self._agent()) != eval_id_of(self._agent(budget=tighter))

    def test_the_graph_fingerprint_stays_a_digest_of_shape(self) -> None:
        """It answers whether stored state can be walked, so a temperature is outside it."""
        assert (
            self._baseline().graph_fingerprint()
            == self._baseline(temperature=0.7).graph_fingerprint()
        )


class TestTheBehaviourFingerprintCoversWhatDecidesTheOutput:
    """What a project stamps a stored result with, so a stale one is a query.

    `docs/shipping.md` §6. Every case here is one where a stored result would otherwise be
    indistinguishable from one the current pipeline produced.
    """

    def _baseline(self, **kwargs) -> Pipeline:
        return Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract", **kwargs)],
            budget=BUDGET,
        )

    def test_the_same_pipeline_twice_stamps_the_same_value(self) -> None:
        assert self._baseline().behaviour_fingerprint(
            model=Scripted()
        ) == self._baseline().behaviour_fingerprint(model=Scripted())

    @pytest.mark.parametrize(
        "moved",
        [
            {"temperature": 0.7},
            {"max_output_tokens": 64},
            {"allow_unknown": False},
            {"prompt_version": "v2"},
        ],
    )
    def test_a_moved_configuration_moves_it(self, moved) -> None:
        assert self._baseline().behaviour_fingerprint(model=Scripted()) != self._baseline(
            **moved
        ).behaviour_fingerprint(model=Scripted())

    def test_an_edited_prompt_moves_it_and_leaves_the_graph_fingerprint_alone(self) -> None:
        """The case a project stamping with `graph_fingerprint` could not see."""

        def build_prompt_v2(inputs: dict) -> str:
            return Prompt.user("Answer, in one sentence: {question}", question=inputs["question"])

        edited = Pipeline(
            [LLMNode(build_prompt_v2, output_schema=Answer, node_id="extract")],
            budget=BUDGET,
        )

        assert edited.graph_fingerprint() == self._baseline().graph_fingerprint()
        assert edited.behaviour_fingerprint(
            model=Scripted()
        ) != self._baseline().behaviour_fingerprint(model=Scripted())

    def test_a_moved_pipeline_budget_moves_it(self) -> None:
        tighter = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
            budget=Budget(max_steps=3, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None),
        )

        assert tighter.behaviour_fingerprint(
            model=Scripted()
        ) != self._baseline().behaviour_fingerprint(model=Scripted())

    def test_a_tool_taken_off_a_node_moves_it(self) -> None:
        def agent_with(tools) -> Pipeline:
            return Pipeline(
                [
                    AgentNode(
                        build_prompt,
                        output_schema=Answer,
                        node_id="hunt",
                        tools=tools,
                        budget=Budget(
                            max_steps=4,
                            max_tokens=10_000,
                            max_cost=None,
                            max_wall_clock_ms=None,
                        ),
                    )
                ],
                budget=BUDGET,
            )

        assert agent_with([]).behaviour_fingerprint(model=Scripted()) != agent_with(
            [look_up()]
        ).behaviour_fingerprint(model=Scripted())

    def test_the_run_records_what_the_pipeline_computes(self, tmp_path) -> None:
        """A stored result and the run that produced it join on this value."""
        pipeline = self._baseline()
        pipeline.run(
            {"question": "Which retailer ships from Leeds?"},
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=Scripted(),
            seed=41,
        )
        manifest = json.loads(
            next(Path(tmp_path).glob("**/manifest.json")).read_text(encoding="utf-8")
        )

        assert manifest["behaviour_fingerprint"] == pipeline.behaviour_fingerprint(model=Scripted())
        assert manifest["behaviour_fingerprint"] != manifest["graph_fingerprint"]


class TestTheStampCoversTheModelAndTheTools:
    """Three things that decide what a pipeline produces and were outside the stamp.

    Each is recorded in the manifest and none moved `behaviour_fingerprint`, so a project
    following `docs/shipping.md` §6 stamped a stored row with a value that did not move when
    the thing that produced it did.
    """

    def _pipeline(self, tools=(), model=None) -> Pipeline:
        return Pipeline(
            [
                AgentNode(
                    build_prompt,
                    output_schema=Answer,
                    node_id="hunt",
                    tools=list(tools),
                    model=model,
                    budget=Budget(
                        max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=BUDGET,
        )

    def test_the_client_the_run_is_given_moves_it(self) -> None:
        """A project swaps a cheap model for the production one and keeps the same graph."""
        pipeline = self._pipeline()

        assert pipeline.behaviour_fingerprint(
            model=Scripted("cheap/model")
        ) != pipeline.behaviour_fingerprint(model=Scripted("strong/model"))

    def test_a_tool_body_moves_it(self) -> None:
        """The tool keeps its name, its description and its schema, and returns other data."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="look_up")
        def shorter(query: str) -> str:
            """Search the collection. Returns matching entries."""
            return "Kirkwall ships from Leeds."

        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="look_up")
        def longer(query: str) -> str:
            """Search the collection. Returns matching entries."""
            return "Kirkwall ships from Leeds, and from Stromness on Fridays."

        assert shorter.name == longer.name
        assert shorter.parameters == longer.parameters
        assert shorter.version != longer.version
        assert self._pipeline([shorter]).behaviour_fingerprint(model=Scripted()) != self._pipeline(
            [longer]
        ).behaviour_fingerprint(model=Scripted())

    def test_a_consultation_reader_moves_it(self) -> None:
        """The one library-owned model call a `Deterministic` node can carry (P3-12)."""
        cheap = Scripted("cheap/model")

        def ask(question: str) -> str:
            return Prompt.user("yes")

        def with_reader(reader) -> Pipeline:
            return Pipeline(
                [LLMNode(build_prompt, output_schema=Answer, node_id="extract", model=cheap)],
                budget=BUDGET,
                tools=[consult(ask, answered_by="end_user", read=reader)],
            )

        by_model = with_reader(ModelReader(model=Scripted("strong/model")))
        by_prompt = with_reader(
            ModelReader(model=cheap, instructions="Pick one of {options} for {answer}.")
        )
        baseline = with_reader(ModelReader(model=cheap))

        assert baseline.behaviour_fingerprint() != by_model.behaviour_fingerprint()
        assert baseline.behaviour_fingerprint() != by_prompt.behaviour_fingerprint()
        assert baseline.graph_fingerprint() == by_model.graph_fingerprint()

    def test_none_of_it_moves_the_graph_fingerprint(self) -> None:
        """It answers whether stored state can be walked, and none of this bears on that."""
        assert (
            self._pipeline(model=Scripted("cheap/model")).graph_fingerprint()
            == self._pipeline(model=Scripted("strong/model")).graph_fingerprint()
        )

    def test_a_pipeline_whose_nodes_declare_their_own_needs_no_client(self) -> None:
        own = self._pipeline(model=Scripted())

        assert own.behaviour_fingerprint() == own.behaviour_fingerprint(
            model=Scripted("something/else")
        )

    def test_a_stamp_that_would_not_cover_the_model_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            self._pipeline().behaviour_fingerprint()

        message = str(raised.value)
        assert "'hunt'" in message
        assert "behaviour_fingerprint(model=client)" in message

    def test_a_run_stamps_what_it_was_given(self, tmp_path) -> None:
        """The join `docs/shipping.md` §6 asks a project to make, end to end."""
        pipeline = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET
        )
        client = Scripted("cheap/model")
        pipeline.run(
            {"question": "Which retailer ships from Leeds?"},
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=client,
            seed=41,
        )
        manifest = json.loads(
            next(Path(tmp_path).glob("**/manifest.json")).read_text(encoding="utf-8")
        )

        assert manifest["behaviour_fingerprint"] == pipeline.behaviour_fingerprint(model=client)
        assert manifest["behaviour_fingerprint"] != pipeline.behaviour_fingerprint(
            model=Scripted("strong/model")
        )


class TestRescoreRefusesAMovedConfiguration:
    """`graph_fingerprint` cannot see a temperature, so rescore scored rollouts it never ran."""

    def _run_at(self, tmp_path: Path, **kwargs) -> Path:
        pipeline = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract", **kwargs)],
            budget=BUDGET,
        )
        suite_over(pipeline).run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=Scripted(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )
        return next((Path(tmp_path) / "eval").glob("eval_*"))

    def test_rollouts_run_at_another_temperature_are_refused(self, tmp_path) -> None:
        eval_dir = self._run_at(tmp_path)
        hotter = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract", temperature=0.7)],
            budget=BUDGET,
        )

        with pytest.raises(ConfigurationError) as caught:
            suite_over(hotter).rescore(run_dir=eval_dir, split="held_out")

        message = str(caught.value)
        assert "ran under a different configuration" in message
        assert "nodes.extract.sampling.temperature" in message
        assert "0.7" in message

    def test_rollouts_run_under_another_budget_are_refused(self, tmp_path) -> None:
        eval_dir = self._run_at(tmp_path)
        tighter = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
            budget=Budget(max_steps=3, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None),
        )

        with pytest.raises(ConfigurationError) as caught:
            suite_over(tighter).rescore(run_dir=eval_dir, split="held_out")

        assert "budget.max_steps" in str(caught.value)

    def test_the_same_configuration_is_scored(self, tmp_path) -> None:
        eval_dir = self._run_at(tmp_path)
        pipeline = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
            budget=BUDGET,
        )

        results = suite_over(pipeline).rescore(run_dir=eval_dir, split="held_out")

        assert results.metrics["accuracy"].value == 1.0

    def test_a_run_directory_recording_no_configuration_is_scored(self, tmp_path) -> None:
        """A run written by an earlier version records none of it, and is not refused."""
        eval_dir = self._run_at(tmp_path)
        for manifest_path in eval_dir.glob("**/manifest.json"):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for key in ("nodes", "containers", "budget"):
                manifest.pop(key, None)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        pipeline = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract", temperature=0.7)],
            budget=BUDGET,
        )

        results = suite_over(pipeline).rescore(run_dir=eval_dir, split="held_out")

        assert results.metrics["accuracy"].value == 1.0


class TestResumeFromRunsOnTheDefaultRecordingPath:
    """`docs/evaluation.md` §6.5 shows an ordinary envelope, and `Cassette.record`
    refused its own file."""

    def _pipeline(self) -> Pipeline:
        return Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
            budget=BUDGET,
        )

    def test_the_documented_call_runs(self, tmp_path) -> None:
        suite = suite_over(self._pipeline())
        arguments = {"split": "held_out", "k": 2, "seed": 41, "concurrency": 1}
        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=Scripted(),
            **arguments,
        )
        eval_dir = next((Path(tmp_path) / "eval").glob("eval_*"))
        cassette = eval_dir / "cassette.jsonl"
        assert cassette.exists() and cassette.stat().st_size > 0
        # One example's rollouts are removed, the way a kill part-way through leaves them.
        for directory in sorted(eval_dir.glob("q2-*")):
            for entry in sorted(directory.rglob("*"), reverse=True):
                entry.unlink() if entry.is_file() else entry.rmdir()
            directory.rmdir()

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=Scripted(),
            resume_from=str(eval_dir),
            **arguments,
        )

        assert len(results.rollouts) == 4
        assert results.metrics["accuracy"].value == 1.0

    def test_the_evaluations_own_recording_is_continued_not_replaced(self, tmp_path) -> None:
        """The rollouts that already ran keep the calls they bought."""
        suite = suite_over(self._pipeline())
        arguments = {"split": "held_out", "k": 1, "seed": 41, "concurrency": 1}
        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=Scripted(),
            **arguments,
        )
        eval_dir = next((Path(tmp_path) / "eval").glob("eval_*"))
        before = (eval_dir / "cassette.jsonl").read_text(encoding="utf-8")

        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=Scripted(),
            resume_from=str(eval_dir),
            **arguments,
        )

        after = (eval_dir / "cassette.jsonl").read_text(encoding="utf-8")
        assert after.startswith(before)

    def test_record_false_still_resumes(self, tmp_path) -> None:
        suite = suite_over(self._pipeline())
        arguments = {"split": "held_out", "k": 1, "seed": 41, "concurrency": 1, "record": False}
        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=Scripted(),
            **arguments,
        )
        eval_dir = next((Path(tmp_path) / "eval").glob("eval_*"))

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=Scripted(),
            resume_from=str(eval_dir),
            **arguments,
        )

        assert len(results.rollouts) == 2


# -- D3: different answers per failure class ------------------------------------------------


class Dead:
    """A backend answering 404, the way a model id the provider retired does."""

    def identity(self):
        return FakeModelClient().model_identity

    def complete(self, request):
        raise CallerFacingError(
            "http://localhost:8002/v1/chat/completions has no such model or endpoint "
            "(404: model not found)."
        )


class Garbled:
    """A backend that answers, with something the declared schema does not accept."""

    def identity(self):
        return FakeModelClient().model_identity

    def complete(self, request):
        return fake_response(content="not json at all")


def stop_here(inputs, ctx):
    raise Suspend(waiting_for="which depot the question is about")


class TestAFailureIsSortedByWhetherAnythingWasMeasured:
    def _run(self, tmp_path, client, pipeline: Pipeline | None = None):
        pipeline = pipeline or Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
            budget=BUDGET,
        )
        return suite_over(pipeline).run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=client,
            split="held_out",
            k=3,
            seed=41,
            concurrency=1,
        )

    def test_a_backend_that_never_answers_scores_no_response(self, tmp_path) -> None:
        results = self._run(tmp_path, Dead())

        assert all(r.outcome is Outcome.NO_RESPONSE for r in results.rollouts)

    def test_the_rates_are_undefined_rather_than_a_failure_rate_of_one(self, tmp_path) -> None:
        """Nine consecutive 404s used to report `failure_rate` 1.0 with complete intervals."""
        results = self._run(tmp_path, Dead())

        for metric in results.metrics.values():
            assert metric.interval is None
            assert metric.value is None
        assert results.metrics["failure_rate"].left_out == {"no_response": 6}
        assert "6 rollout(s) that got no response" in results.metrics["accuracy"].reason

    def test_the_count_is_beside_every_rate(self, tmp_path) -> None:
        results = self._run(tmp_path, Dead())

        for name in ("accuracy", "recall", "failure_rate", "precision_when_asserting"):
            assert results.metrics[name].left_out["no_response"] > 0

    def test_a_response_the_schema_rejected_is_an_ordinary_failure(self, tmp_path) -> None:
        """The backend answered, so what the agent did with the answer is the measurement."""
        results = self._run(tmp_path, Garbled())

        assert all(r.outcome is Outcome.FAILED for r in results.rollouts)
        assert results.metrics["failure_rate"].value == 1.0
        assert results.metrics["failure_rate"].left_out == {}

    def test_a_budget_a_rollout_passed_is_an_ordinary_failure(self, tmp_path) -> None:
        results = self._run(
            tmp_path,
            Scripted(),
            pipeline=Pipeline(
                [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
                budget=Budget(
                    max_steps=0, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None
                ),
            ),
        )

        assert all(r.outcome is Outcome.FAILED for r in results.rollouts)

    def test_a_replay_with_no_entry_scores_no_response(self, tmp_path) -> None:
        empty = tmp_path / "nothing.jsonl"
        empty.write_text("")
        pipeline = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
            budget=BUDGET,
        )

        results = suite_over(pipeline).run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.replay(empty)),
            model=Scripted(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
            allow_mixed_cassette=True,
        )

        assert all(r.outcome is Outcome.NO_RESPONSE for r in results.rollouts)
        assert all(r.error and r.error["type"] == CassetteMiss.__name__ for r in results.rollouts)

    def test_a_suspension_reaches_the_caller(self, tmp_path) -> None:
        """`docs/evaluation.md` §7.4 promised this; the bare except scored it `failed`."""
        pipeline = Pipeline(
            [
                Deterministic(stop_here, node_id="ask"),
                LLMNode(build_prompt, output_schema=Answer, node_id="extract"),
            ],
            budget=BUDGET,
        )

        with pytest.raises(RunSuspended) as caught:
            self._run(tmp_path, Scripted(), pipeline=pipeline)

        assert caught.value.waiting_for == "which depot the question is about"
        assert Path(caught.value.state_path).exists()

    def test_a_configuration_error_ends_the_evaluation_on_the_first_rollout(self, tmp_path) -> None:
        """It fails identically everywhere, so the other k x n are not paid for."""
        calls: list[int] = []

        class Counting(Scripted):
            def complete(self, request):
                calls.append(1)
                return super().complete(request)

        suite = EvalSuite(
            Pipeline(
                [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
                budget=BUDGET,
            ),
            two_examples(),
            answer="no_such_field",
            matches=EXACT,
        )

        with pytest.raises(ConfigurationError) as caught:
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
                model=Counting(),
                split="held_out",
                k=3,
                seed=41,
                concurrency=1,
            )

        assert "no_such_field" in str(caught.value)
        assert len(calls) == 1


class TestNoResponseLeavesEveryDenominator:
    def test_a_partly_dead_backend_reports_over_what_was_measured(self, tmp_path) -> None:
        class Flaky(Scripted):
            def complete(self, request):
                if "Northgate" in request.messages[-1]["content"]:
                    raise CallerFacingError("returned 503 after 4 attempt(s).")
                return super().complete(request)

        pipeline = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
            budget=BUDGET,
        )

        results = suite_over(pipeline).run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=Flaky(),
            split="held_out",
            k=3,
            seed=41,
            concurrency=1,
        )

        assert results.metrics["accuracy"].value == 1.0
        assert results.metrics["accuracy"].rollouts == 3
        assert results.metrics["accuracy"].left_out == {"no_response": 3}
        assert "less 3 that got no response" in results.report()

    def test_the_written_file_carries_the_count(self, tmp_path) -> None:
        class Flaky(Scripted):
            def complete(self, request):
                if "Northgate" in request.messages[-1]["content"]:
                    raise CallerFacingError("returned 503 after 4 attempt(s).")
                return super().complete(request)

        pipeline = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
            budget=BUDGET,
        )
        results = suite_over(pipeline).run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=Flaky(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        written = json.loads(results.write(tmp_path / "results.json").read_text())

        assert written["metrics"]["accuracy"]["left_out"] == {"no_response": 1}
        assert written["eval_format_version"] == "0.32"


class TestAFanOutItemThatNeverReachedTheBackend:
    """A fan-out collects a failed item rather than raising, so the run completes.

    Where the fan-out is what produces the answer, a rate-limited item reads as the agent
    declining: `failure_rate` is 0.00 and the rollout leaves the denominator of any figure
    declared `Over.ASSERTED`, which is how an arm that answered least reported the highest
    number (`DF4-D3`).
    """

    @staticmethod
    def _suite(tmp_path, client):
        def spread(inputs, ctx):
            return {"questions": [inputs["question"]]}

        def ask(inputs, ctx):
            return Prompt.user("Answer the question: {questions}", questions=inputs["questions"])

        pipeline = Pipeline(
            [
                Deterministic(spread, node_id="spread"),
                LLMNode(ask, output_schema=Answer, over="questions", node_id="extract"),
            ],
            budget=BUDGET,
        )
        suite = EvalSuite(
            pipeline,
            two_examples(),
            answer=lambda output: (
                output.outcomes[0].value.answer if output.outcomes[0].ok else None
            ),
            matches=EXACT,
        )
        return suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=client,
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

    def test_an_item_the_backend_never_answered_is_counted(self, tmp_path) -> None:
        class Flaky(Scripted):
            def complete(self, request):
                if "Northgate" in request.messages[-1]["content"]:
                    raise CallerFacingError("returned 503 after 4 attempt(s).")
                return super().complete(request)

        results = self._suite(tmp_path, Flaky())

        lost = {r.example_id: r.unreached_items for r in results.rollouts}
        assert lost == {"q1": 0, "q2": 1}

    def test_an_item_that_failed_on_a_reply_is_not_counted(self, tmp_path) -> None:
        class Malformed(Scripted):
            def complete(self, request):
                if "Northgate" in request.messages[-1]["content"]:
                    return fake_response(content="not json")
                return super().complete(request)

        results = self._suite(tmp_path, Malformed())

        # The backend answered; the agent produced no answer from what it was given, which is
        # a different thing and is what `failed` already covers.
        assert {r.example_id: r.unreached_items for r in results.rollouts} == {
            "q1": 0,
            "q2": 0,
        }

    def test_two_fan_outs_in_one_rollout_do_not_stand_in_for_each_other(self, tmp_path) -> None:
        class DeadOnFirst(Scripted):
            def __init__(self):
                super().__init__()
                self.seen = 0

            def complete(self, request):
                self.seen += 1
                if self.seen == 1:
                    raise CallerFacingError("returned 503 after 4 attempt(s).")
                return super().complete(request)

        def spread(inputs, ctx):
            return {"questions": [inputs["question"]]}

        def ask(inputs, ctx):
            return Prompt.user("Answer the question: {questions}", questions=inputs["questions"])

        def again(inputs, ctx):
            return {"questions": ["Who founded Northgate?"]}

        pipeline = Pipeline(
            [
                Deterministic(spread, node_id="spread"),
                LLMNode(ask, output_schema=Answer, over="questions", node_id="first"),
                Deterministic(again, node_id="again"),
                LLMNode(ask, output_schema=Answer, over="questions", node_id="second"),
            ],
            budget=BUDGET,
        )
        suite = EvalSuite(
            pipeline,
            two_examples(),
            answer=lambda output: (
                output.outcomes[0].value.answer if output.outcomes[0].ok else None
            ),
            matches=EXACT,
        )

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=DeadOnFirst(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        # An index is a position within one fan-out, so both nodes have an item 0. The one
        # that died is in `first`, and `second` answering its own item 0 does not cover it.
        assert {r.example_id: r.unreached_items for r in results.rollouts} == {
            "q1": 1,
            "q2": 0,
        }

    def test_the_count_survives_the_results_file(self, tmp_path) -> None:
        class Flaky(Scripted):
            def complete(self, request):
                if "Northgate" in request.messages[-1]["content"]:
                    raise CallerFacingError("returned 503 after 4 attempt(s).")
                return super().complete(request)

        results = self._suite(tmp_path, Flaky())
        written = json.loads(results.write(tmp_path / "results.json").read_text())

        counted = {r["example_id"]: r["unreached_items"] for r in written["rollouts"]}
        assert counted == {"q1": 0, "q2": 1}


# -- P3-20: what the identity declares -------------------------------------------------------

STORE = {
    "Which retailer ships from Leeds?": "Kirkwall",
    "Who founded Northgate?": "Alan Reid",
}


def read_the_store(inputs: dict, ctx) -> dict:
    return {"answer": STORE[inputs["question"]]}


def read_the_store_rebuilt(inputs: dict, ctx) -> dict:
    return {"answer": STORE[inputs["question"]], "read_from": "characterisations"}


@tool(name="look_up", side_effect_class=SideEffectClass.READ_ONLY)
def look_up_early(query: str) -> str:
    """Search the collection. Returns matching entries."""
    return "Kirkwall ships from Leeds."


@tool(name="look_up", side_effect_class=SideEffectClass.READ_ONLY)
def look_up_edited(query: str) -> str:
    """Search the collection. Returns matching entries."""
    return "Kirkwall ships from Leeds, and nowhere else, per the 2026 index."


@tool(name="look_up", side_effect_class=SideEffectClass.READ_ONLY, version="v1")
def look_up_declared(query: str) -> str:
    """Search the collection. Returns matching entries."""
    return "Kirkwall ships from Leeds."


@tool(name="look_up", side_effect_class=SideEffectClass.READ_ONLY, version="v1")
def look_up_declared_edited(query: str) -> str:
    """Search the collection. Returns matching entries."""
    return "Kirkwall ships from Leeds, and nowhere else, per the 2026 index."


def _agent_over(tool_) -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                build_prompt,
                output_schema=Answer,
                node_id="hunt",
                tools=[tool_],
                budget=Budget(
                    max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=None
                ),
            )
        ],
        budget=BUDGET,
    )


def _reading(fn, version=None) -> Pipeline:
    return Pipeline([Deterministic(fn, node_id="read", version=version)], budget=BUDGET)


class TestABodyEditIsSeenWhereNoVersionWasDeclared:
    """Three edits that changed what was measured and named the same evaluation directory.

    Each is a change the library can read off the source, so nothing has to be declared for it
    to be traced. The re-run was refused as a used directory, which named the wrong cause, and
    a resume appended the new rollouts to the old ones.
    """

    def test_an_edited_tool_body_names_another_directory(self) -> None:
        assert eval_id_of(_agent_over(look_up_early)) != eval_id_of(_agent_over(look_up_edited))

    def test_an_edited_deterministic_body_names_another_directory(self) -> None:
        assert eval_id_of(_reading(read_the_store)) != eval_id_of(_reading(read_the_store_rebuilt))

    def test_an_edited_deterministic_body_moves_the_stamp(self) -> None:
        """A `Deterministic` node decides what the pipeline produces and moved nothing."""
        assert (
            _reading(read_the_store).behaviour_fingerprint()
            != _reading(read_the_store_rebuilt).behaviour_fingerprint()
        )

    def test_it_leaves_the_graph_fingerprint_alone(self) -> None:
        """The shape did not move, so stored state can still be walked."""
        assert (
            _reading(read_the_store).graph_fingerprint()
            == _reading(read_the_store_rebuilt).graph_fingerprint()
        )

    def test_the_same_body_twice_is_one_directory(self) -> None:
        assert eval_id_of(_reading(read_the_store)) == eval_id_of(_reading(read_the_store))


class TestADeclaredVersionGovernsAndTheHashRecordsTheEdit:
    """Declaring a version is what stops a cosmetic edit moving every figure.

    It was also what switched off the only automatic trace, because the hash was discarded
    rather than recorded beside it. `_warn_a_moved_declaration` is what reads it back.
    """

    def test_a_declared_node_version_holds_the_directory_over_an_edit(self) -> None:
        assert eval_id_of(_reading(read_the_store, version="v1")) == eval_id_of(
            _reading(read_the_store_rebuilt, version="v1")
        )

    def test_a_declared_node_version_holds_the_stamp_over_an_edit(self) -> None:
        assert (
            _reading(read_the_store, version="v1").behaviour_fingerprint()
            == _reading(read_the_store_rebuilt, version="v1").behaviour_fingerprint()
        )

    def test_a_declared_tool_version_holds_both_over_an_edit(self) -> None:
        assert eval_id_of(_agent_over(look_up_declared)) == eval_id_of(
            _agent_over(look_up_declared_edited)
        )
        assert _agent_over(look_up_declared).behaviour_fingerprint(Scripted()) == _agent_over(
            look_up_declared_edited
        ).behaviour_fingerprint(Scripted())

    def test_the_hash_is_recorded_beside_a_declared_node_version(self) -> None:
        early = _reading(read_the_store, version="v1").manifest_nodes()[0]["fn"]
        edited = _reading(read_the_store_rebuilt, version="v1").manifest_nodes()[0]["fn"]

        assert early["version"] == edited["version"] == "v1"
        assert early["source"] == "declared"
        assert early["derived"] != edited["derived"]

    def test_the_hash_is_recorded_beside_a_declared_tool_version(self) -> None:
        early = _agent_over(look_up_declared).manifest_tools()[0]
        edited = _agent_over(look_up_declared_edited).manifest_tools()[0]

        assert early["version"] == edited["version"] == "v1"
        assert early["derived"] != edited["derived"]

    def test_a_node_holding_state_keeps_its_version_while_the_run_runs(self) -> None:
        """A `Deterministic` body is versioned by its source alone, and this is why.

        A node holding state across its own calls is ordinary. Rendering what it closed over
        into the version would move the stamp mid-run, and a project joins its stored results
        on that value.
        """
        seen = {"calls": 0}

        def counts(inputs, ctx):
            seen["calls"] += 1
            return inputs

        pipeline = _reading(counts)
        before = pipeline.behaviour_fingerprint()
        seen["calls"] = 7

        assert pipeline.behaviour_fingerprint() == before
        assert pipeline.manifest_nodes()[0]["fn"]["source"] == "derived"

    def test_a_prompt_holding_state_keeps_its_version_while_the_run_runs(self) -> None:
        """The same for a prompt, which is where a project is most likely to hold a cache.

        A prompt's version covers what it closed over, so rendering that on every read moved
        the stamp when nothing about the pipeline had changed. It is taken once, when the node
        is declared.
        """
        cache = {"hits": 0}

        def build(inputs, ctx):
            cache["hits"] += 1
            return Prompt.user("Answer the question: {question}", question=inputs["question"])

        pipeline = Pipeline(
            [LLMNode(build, output_schema=Answer, node_id="extract")], budget=BUDGET
        )
        before = pipeline.behaviour_fingerprint(Scripted())
        cache["hits"] = 7

        assert pipeline.behaviour_fingerprint(Scripted()) == before

    def test_a_route_holding_state_keeps_its_version_too(self) -> None:
        """Every node kind and `Pipeline` declare their route through one path, so one snapshot
        covers all of them."""
        seen: list[str] = []

        def route(output, ctx):
            seen.append("x")
            return "extract"

        node = LLMNode(
            build_prompt,
            output_schema=Answer,
            node_id="first",
            successors=["extract", "other"],
            route=route,
        )
        before = node.route_entry
        seen.append("y")

        assert node.route_entry == before
        assert before["version"].startswith("sha256:")

    def test_an_undeclared_version_is_the_hash_and_carries_no_second_copy(self) -> None:
        """A second copy would make a comparison name one edit twice."""
        entry = _reading(read_the_store).manifest_nodes()[0]["fn"]

        assert entry == {"version": entry["version"], "source": "derived"}
        assert entry["version"].startswith("sha256:")


class TestAHeldDeclarationIsReportedWhenTheSourceMoved:
    """The one change nothing else traces, because everything else reads the declaration."""

    def _run(self, tmp_path: Path, pipeline: Pipeline) -> Path:
        suite_over(pipeline).run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=Scripted(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )
        return next((Path(tmp_path) / "eval").glob("eval_*"))

    def test_rescoring_over_an_edited_body_warns_and_scores(self, tmp_path) -> None:
        eval_dir = self._run(tmp_path, _reading(read_the_store, version="v1"))
        edited = suite_over(_reading(read_the_store_rebuilt, version="v1"))

        with pytest.warns(SimpleAgentsWarning) as caught:
            results = edited.rescore(run_dir=eval_dir, split="held_out")

        message = str(caught[0].message)
        assert "node 'read'" in message
        assert "'v1' held" in message
        assert results is not None

    def test_an_unedited_body_says_nothing(self, tmp_path) -> None:
        eval_dir = self._run(tmp_path, _reading(read_the_store, version="v1"))
        same = suite_over(_reading(read_the_store, version="v1"))

        with warnings.catch_warnings():
            warnings.simplefilter("error", SimpleAgentsWarning)
            same.rescore(run_dir=eval_dir, split="held_out")

    def test_an_edited_body_with_no_declaration_is_refused_rather_than_reported(
        self, tmp_path
    ) -> None:
        """No declaration means the identity moved, so the rollouts are another evaluation's."""
        eval_dir = self._run(tmp_path, _reading(read_the_store))

        with pytest.raises(ConfigurationError) as raised:
            suite_over(_reading(read_the_store_rebuilt)).rescore(run_dir=eval_dir, split="held_out")

        assert "ran under a different configuration" in str(raised.value)


def _engaged(question, options, about):
    """A channel that asks whoever is on the site."""
    return Reply("yes", chose=None)


def _in_the_background(question, options, about):
    """The same product, unattended."""
    return Shelved(reason="the site is unattended")


class TestTheStampDoesNotMoveWithTheChannel:
    """Which channel a run asks through is a fact about the run, not about the pipeline.

    `P3-45`. Measured on dogfood #5: a product built one channel for a person on the site and
    another for a background refresh, so every slate built from a click reported itself stale
    the instant it was written.
    """

    def _asking(self, channel, **kwargs) -> Pipeline:
        return Pipeline(
            [
                Deterministic(
                    lambda i, c: i,
                    node_id="ask",
                    tools=[consult(channel, name="ask_reader", **kwargs)],
                )
            ],
            budget=BUDGET,
        )

    def test_two_channels_over_one_pipeline_stamp_the_same(self) -> None:
        assert (
            self._asking(_engaged, answered_by="end_user").behaviour_fingerprint()
            == self._asking(_in_the_background, answered_by="end_user").behaviour_fingerprint()
        )

    def test_a_channel_that_stops_reaching_a_person_moves_it(self) -> None:
        """`answered_by` stays in, so shipping on a stand-in is still visible in the stamp."""
        assert (
            self._asking(_engaged, answered_by="end_user").behaviour_fingerprint()
            != self._asking(_engaged, answered_by="nobody").behaviour_fingerprint()
        )

    def test_the_channel_still_keys_the_cassette(self) -> None:
        """Two channels are two things to record, which the stamp is a separate question from."""
        versions = {
            tool["version"]
            for pipeline in (
                self._asking(_engaged, answered_by="end_user"),
                self._asking(_in_the_background, answered_by="end_user"),
            )
            for tool in _node_entries(pipeline)[2]
        }

        assert len(versions) == 2

    def test_the_channel_still_separates_two_runs_on_a_resume(self, tmp_path) -> None:
        """The stamp and the resume comparison are different questions about one version."""
        stopping = Pipeline(
            [
                Deterministic(lambda i, c: i, node_id="first"),
                Deterministic(
                    lambda i, c: i,
                    node_id="ask",
                    suspend_before=True,
                    tools=[consult(_engaged, name="ask_reader", answered_by="end_user")],
                ),
            ],
            budget=BUDGET,
        )
        other = Pipeline(
            [
                Deterministic(lambda i, c: i, node_id="first"),
                Deterministic(
                    lambda i, c: i,
                    node_id="ask",
                    suspend_before=True,
                    tools=[consult(_in_the_background, name="ask_reader", answered_by="end_user")],
                ),
            ],
            budget=BUDGET,
        )
        envelope = RunEnvelope(run_dir=tmp_path / "runs")
        assert stopping.behaviour_fingerprint() == other.behaviour_fingerprint()
        with pytest.raises(RunSuspended):
            stopping.run({}, envelope=envelope, run_id="r1")

        with pytest.raises(CallerFacingError) as raised:
            other.resume("r1", envelope=envelope)

        assert "tools.ask_reader" in str(raised.value)
        waived = other.resume("r1", envelope=envelope, accept_changed=["tools.ask_reader"])
        assert waived.manifest["resume_waivers"] == ["tools.ask_reader"]

    def test_an_ordinary_tools_version_still_moves_it(self) -> None:
        """Only a consultation tool's version comes out, read off `answered_by`."""

        def one(version):
            @tool(side_effect_class=SideEffectClass.READ_ONLY, name="look", version=version)
            def look(query: str) -> str:
                """Look something up."""
                return query

            return Pipeline(
                [Deterministic(lambda i, c: i, node_id="ask", tools=[look])], budget=BUDGET
            )

        assert one("v1").behaviour_fingerprint() != one("v2").behaviour_fingerprint()


class TestAMisconfigurationInsideAFanOut:
    """`plan.md` §2.1's own measurement: a fanned-out node whose configuration is wrong ran
    every rollout and scored each of them, because the item collected the failure."""

    def _suite(self) -> EvalSuite:
        def spread(inputs, ctx):
            return {"questions": [inputs["question"]]}

        def ask(inputs, ctx):
            # Declared no tools, so this is wrong before the first rollout starts.
            return ctx.call_tool("look_up", query="x")

        pipeline = Pipeline(
            [
                Deterministic(spread, node_id="spread", successors=["extract"]),
                LLMNode(ask, output_schema=Answer, node_id="extract", over="questions"),
            ],
            budget=BUDGET,
        )
        return EvalSuite(pipeline, two_examples(), answer="answer", matches=EXACT)

    def test_it_stops_on_the_first_rollout_rather_than_scoring_every_one(self, tmp_path):
        with pytest.raises(ConfigurationError) as caught:
            self._suite().run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=Scripted(),
                split="held_out",
                k=2,
            )

        assert "declared no tools" in str(caught.value)


class TestAFailedRolloutWithAStepThatReturnedAString:
    def test_the_fan_out_reader_passes_over_a_non_mapping_output(self) -> None:
        """A fixed step may return a string; a failed rollout is still classified.

        Found live: a `Deterministic` returning the run's input crashed every failed rollout
        of the evaluation with `AttributeError` inside the fan-out item count.
        """
        from simple_agents.evaluation.outcomes import _unreached_items_in

        records = [
            {"record_type": "node_execution", "record_id": "r1", "outputs": "France"},
            {"record_type": "node_execution", "record_id": "r2", "outputs": ["a", "b"]},
            {"record_type": "node_execution", "record_id": "r3", "outputs": None},
            {
                "record_type": "node_execution",
                "record_id": "r4",
                "outputs": {"items": [{"index": 0, "error": {"type": "x"}}]},
            },
            {
                "record_type": "model_call",
                "parent_id": "r4",
                "error": {"type": "x"},
                "content": None,
            },
        ]
        assert _unreached_items_in(records) >= 0
