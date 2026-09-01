"""What the trajectories show, as against what the pipeline declared.

`P3-20` stage 2. An evaluation's identity covers what a project declares, so it cannot see a
prompt that changes without anyone changing the code. Dogfood #4's `_overlaps` sorted a list by
frequency and let ties fall back to set iteration order, which Python randomises per process, so
one example produced a different prompt in every process at one `prompt_version`. **15 of 102
rollouts differed between two evaluations for that reason and no other**, and part of the spread
across four model arms was that rather than the arms. Every prompt was in the trajectory and
nothing compared them.

Nothing here decides whether a difference is a defect: a tool holding state across rollouts
produces one legitimately, and that project had such a tool.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    AgentNode,
    Budget,
    Cassette,
    Deterministic,
    LLMNode,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    Trajectory,
    prompt_differences,
    tool,
)
from simple_agents.errors import ConfigurationError
from simple_agents.evaluation.runner import EvalSuite
from simple_agents.models import ModelIdentity, fake_response

from schemas import Answer

BUDGET = Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None)
NODE_BUDGET = Budget(max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=None)

from test_eval_identity_and_failures import EXACT, build_prompt, two_examples

_asked: list[str] = []


def counting_prompt(inputs: dict, ctx) -> str:
    """A prompt that is not a function of the example alone, which is the defect being read."""
    _asked.append(inputs["question"])
    return f"Answer the question: {inputs['question']} [{len(_asked)}]"


def citing_prompt(inputs, ctx) -> str:
    return f"Answer the question, citing the catalogue: {inputs['question']}"


@tool(name="look_up", side_effect_class=SideEffectClass.READ_ONLY)
def look_up(query: str) -> str:
    """Search the collection. Returns matching entries."""
    return "Kirkwall ships from Leeds."


class Answering:
    """Answers whatever it is asked, so a rollout finishes without a script per prompt."""

    def identity(self):
        return ModelIdentity(
            backend="self_hosted", request_model="fake-model", model_revision="0" * 40
        )

    def complete(self, request):
        asked = request.messages[-1]["content"]
        expected = "Kirkwall" if "Leeds" in asked else "Alan Reid"
        return fake_response(content=f'{{"answer": "{expected}", "source": "doc"}}')


def _suite(pipeline: Pipeline) -> EvalSuite:
    return EvalSuite(pipeline, two_examples(), answer="answer", matches=EXACT)


def _evaluate(pipeline: Pipeline, at: Path, k: int = 3, **envelope) -> Path:
    _suite(pipeline).run(
        envelope=RunEnvelope(run_dir=str(at), cassette=Cassette.off(), **envelope),
        model=Answering(),
        split="held_out",
        k=k,
        seed=41,
        concurrency=1,
    )
    return next((Path(at) / "eval").glob("eval_*"))


def _llm(prompt, **kwargs) -> Pipeline:
    return Pipeline(
        [LLMNode(prompt, output_schema=Answer, node_id="extract", **kwargs)], budget=BUDGET
    )


class TestInsideOneEvaluation:
    """k rollouts of one example send one prompt to a node whose prompt is the example's."""

    def test_identical_prompts_are_not_reported(self, tmp_path) -> None:
        found = prompt_differences(_evaluate(_llm(build_prompt), tmp_path))

        assert found["differing"] == []
        assert found["rollouts"] == 6
        assert found["compared"] == 2
        assert found["unreadable"] == 0

    def test_a_prompt_that_is_not_the_example_s_is_reported(self, tmp_path) -> None:
        _asked.clear()

        found = prompt_differences(_evaluate(_llm(counting_prompt), tmp_path))

        assert [(e["example"], e["node"], e["distinct"]) for e in found["differing"]] == [
            ("q1", "extract", 3),
            ("q2", "extract", 3),
        ]
        assert sorted(sum(found["differing"][0]["prompts"].values(), [])) == [
            "q1-0",
            "q1-1",
            "q1-2",
        ]
        assert all(e["across_runs"] is False for e in found["differing"])

    def test_only_the_first_call_of_a_node_execution_is_compared(self, tmp_path) -> None:
        """A later call in an agentic loop carries what the model said, not the example."""
        agent = Pipeline(
            [
                AgentNode(
                    build_prompt,
                    output_schema=Answer,
                    node_id="hunt",
                    tools=[look_up],
                    budget=NODE_BUDGET,
                )
            ],
            budget=BUDGET,
        )

        found = prompt_differences(_evaluate(agent, tmp_path, k=2))

        # Two examples, one node execution each, whatever the model did inside the loop.
        assert found["compared"] == 2
        assert found["differing"] == []

    def test_a_run_that_kept_no_payloads_is_counted_rather_than_compared(self, tmp_path) -> None:
        """An evaluation refuses a sampled trajectory, so this arises over ordinary runs."""
        pipeline = _llm(build_prompt)
        written = []
        for run_id in ("q1-0", "q1-1"):
            written.append(
                pipeline.run(
                    {"question": "Which retailer ships from Leeds?"},
                    envelope=RunEnvelope(
                        run_dir=str(tmp_path),
                        cassette=Cassette.off(),
                        trajectory=Trajectory.sampled(0.0),
                    ),
                    model=Answering(),
                    run_id=run_id,
                    seed=41,
                )
            )

        found = prompt_differences(written[0].paths.root.parent)

        assert found["rollouts"] == 2
        assert found["unreadable"] == 2
        assert found["compared"] == 0
        assert found["differing"] == []


class TestBetweenTwoEvaluations:
    """The change no declaration can reach: the data a node reads, moving underneath it."""

    def test_a_moved_prompt_is_reported_against_the_earlier_evaluation(self, tmp_path) -> None:
        early = _evaluate(_llm(build_prompt), tmp_path / "early", k=1)
        later = _evaluate(_llm(citing_prompt), tmp_path / "later", k=1)

        found = prompt_differences(later, against=early)

        assert [(e["example"], e["distinct"], e["across_runs"]) for e in found["differing"]] == [
            ("q1", 2, True),
            ("q2", 2, True),
        ]
        assert found["rollouts"] == 4

    def test_two_evaluations_of_one_pipeline_report_nothing(self, tmp_path) -> None:
        first = _evaluate(_llm(build_prompt), tmp_path / "first", k=1)
        second = _evaluate(_llm(build_prompt), tmp_path / "second", k=1)

        assert prompt_differences(second, against=first)["differing"] == []

    def test_a_version_declared_alike_over_a_moved_source_is_named(self, tmp_path) -> None:
        """Both evaluations file under one id, so nothing in the identity separates them."""
        early = _evaluate(_llm(build_prompt, prompt_version="v1"), tmp_path / "early", k=1)
        later = _evaluate(_llm(citing_prompt, prompt_version="v1"), tmp_path / "later", k=1)
        assert early.name == later.name

        found = prompt_differences(later, against=early)

        assert [(d["where"], d["version"]) for d in found["declarations"]] == [
            ("prompt 'extract'", "v1")
        ]
        was, now = found["declarations"][0]["source"]
        assert was != now

    def test_two_evaluations_under_one_directory_name_are_told_apart(self, tmp_path) -> None:
        """A held declaration files both under one name, which is the case this exists for."""
        early = _evaluate(_llm(build_prompt, prompt_version="v1"), tmp_path / "early", k=1)
        later = _evaluate(_llm(citing_prompt, prompt_version="v1"), tmp_path / "later", k=1)
        assert early.name == later.name

        found = prompt_differences(later, against=early)

        assert [(e["example"], e["distinct"], e["across_runs"]) for e in found["differing"]] == [
            ("q1", 2, True),
            ("q2", 2, True),
        ]
        assert sorted(sum(found["differing"][0]["prompts"].values(), [])) == [
            f"{early}/q1-0",
            f"{later}/q1-0",
        ]

    def test_a_directory_compared_with_itself_is_refused(self, tmp_path) -> None:
        one = _evaluate(_llm(build_prompt), tmp_path, k=1)

        with pytest.raises(ConfigurationError) as raised:
            prompt_differences(one, against=one)

        assert "nothing to compare" in str(raised.value)

    def test_nothing_is_named_where_the_declaration_moved_with_the_source(self, tmp_path) -> None:
        early = _evaluate(_llm(build_prompt, prompt_version="v1"), tmp_path / "early", k=1)
        later = _evaluate(_llm(citing_prompt, prompt_version="v2"), tmp_path / "later", k=1)

        assert prompt_differences(later, against=early)["declarations"] == []

    def test_a_deterministic_body_is_read_the_same_way(self, tmp_path) -> None:
        def read_early(inputs: dict, ctx) -> dict:
            return {"answer": "Kirkwall" if "Leeds" in inputs["question"] else "Alan Reid"}

        def read_rebuilt(inputs: dict, ctx) -> dict:
            answer = "Kirkwall" if "Leeds" in inputs["question"] else "Alan Reid"
            return {"answer": answer, "read_from": "characterisations"}

        def reading(fn) -> Pipeline:
            return Pipeline([Deterministic(fn, node_id="read", version="v1")], budget=BUDGET)

        early = _evaluate(reading(read_early), tmp_path / "early", k=1)
        later = _evaluate(reading(read_rebuilt), tmp_path / "later", k=1)

        found = prompt_differences(later, against=early)

        assert [d["where"] for d in found["declarations"]] == ["node 'read'"]


class TestItReadsADirectoryAndNothingElse:
    def test_a_directory_of_evaluations_is_refused(self, tmp_path) -> None:
        """An empty report over the wrong level would read as agreement."""
        _evaluate(_llm(build_prompt), tmp_path, k=1)

        with pytest.raises(ConfigurationError) as raised:
            prompt_differences(tmp_path)

        assert "evaluation directories rather than rollouts" in str(raised.value)

    def test_a_tool_built_by_hand_with_no_version_is_still_read(self, tmp_path) -> None:
        """`Tool(version=None)` is invisible to the stamp, and this is what sees it."""
        early = _evaluate(_llm(build_prompt), tmp_path / "early", k=1)
        later = _evaluate(_llm(build_prompt), tmp_path / "later", k=1)
        for at, body in ((early, "one"), (later, "two")):
            for manifest in at.glob("**/manifest.json"):
                held = json.loads(manifest.read_text(encoding="utf-8"))
                held["tools"] = [{"name": "look_up", "version": None, "derived": f"sha256:{body}"}]
                manifest.write_text(json.dumps(held), encoding="utf-8")

        found = prompt_differences(later, against=early)

        assert [(d["where"], d["version"]) for d in found["declarations"]] == [
            ("tool 'look_up'", None)
        ]

    def test_the_against_side_is_refused_the_same_way(self, tmp_path) -> None:
        one = _evaluate(_llm(build_prompt), tmp_path / "one", k=1)
        _evaluate(_llm(citing_prompt), tmp_path / "two", k=1)

        with pytest.raises(ConfigurationError) as raised:
            prompt_differences(one, against=tmp_path / "two")

        assert "evaluation directories rather than rollouts" in str(raised.value)

    def test_a_directory_with_no_runs_reads_as_empty(self, tmp_path) -> None:
        found = prompt_differences(tmp_path)

        assert found == {
            "run_dir": str(tmp_path),
            "against": None,
            "rollouts": 0,
            "compared": 0,
            "unreadable": 0,
            "differing": [],
            "declarations": [],
        }
