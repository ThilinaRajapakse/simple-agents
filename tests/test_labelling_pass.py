"""The labelling pass in `docs/evaluation.md` §1.4, executed rather than read.

The block that stood here before this file ran the pipeline once per candidate. It worked, and
three things about it were wrong and nothing failed: `max_cost` bounded one candidate rather
than the pass, 60 candidates cost 60 run directories, and the pass was written where the
conformance checks read it as a run of the agent. So the shape the document teaches is run
here, over a fan-out large enough for the per-item claims to mean something.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from simple_agents import (
    Prompt,
    Budget,
    Cassette,
    FakeModelClient,
    LLMNode,
    Maybe,
    Pipeline,
    PriceBasis,
    RunEnvelope,
    docs_path,
    fake_response,
    runs,
)
from simple_agents.conformance.artifacts import _latest_run, runs_by_pipeline
from simple_agents.evaluation import Label, read_labels, write_labels

from conftest import run_path

PRICES = PriceBasis(currency="USD", input_uncached_per_mtok=0.4, output_per_mtok=2.0)
VERDICT = json.dumps(
    {
        "reasoning": "no passage states it.",
        "answerable": False,
        "answer": {"type": "unknown", "reason": "not stated"},
    }
)


class Verdict(BaseModel):
    reasoning: str = Field(description="Whether any passage states an answer.")
    answerable: bool = Field(description="true only if a passage states it outright.")
    answer: Maybe[str] = Field(description="The answering span, or unknown.")


def build_label_prompt(inputs, ctx):
    candidate = inputs["candidates"]
    return Prompt.user(
        "Question: {question}\n\nPassages:\n{passages}",
        question=candidate["question"],
        passages=candidate["passages"],
    )


@pytest.fixture
def candidates() -> list[dict]:
    return [
        {"id": f"q{i}", "question": f"question {i}?", "passages": f"passage {i}"} for i in range(60)
    ]


def label_pass(run_dir: Path, candidates: list[dict]):
    """§1.4's pipeline and envelope, with a scripted backend in place of the live one."""
    label = Pipeline(
        [
            LLMNode(
                build_label_prompt,
                output_schema=Verdict,
                node_id="label",
                over="candidates",
                temperature=0.0,
            )
        ],
        budget=Budget(
            max_steps=len(candidates),
            max_tokens=400_000,
            max_cost=1.00,
            max_wall_clock_ms=1_800_000,
        ),
    )
    env = RunEnvelope(
        run_dir=str(run_dir),
        cost_basis=PRICES,
        role="labelling",
        cassette=Cassette.record(str(run_dir.parent / "cassettes" / "labels.jsonl")),
    )
    client = FakeModelClient(
        responses=[fake_response(VERDICT)] * (len(candidates) + 4), scripted=False
    )
    return label.run({"candidates": candidates}, model=client, envelope=env)


def test_the_whole_pass_is_one_run(tmp_path: Path, candidates) -> None:
    result = label_pass(tmp_path / "runs", candidates)

    assert len(result.output.outcomes) == 60
    assert list(result.output.failures) == []
    assert len(list((tmp_path / "runs").iterdir())) == 1


def test_the_pass_has_one_cost_and_one_model_pin(tmp_path: Path, candidates) -> None:
    """What the per-candidate shape spread across sixty manifests."""
    result = label_pass(tmp_path / "runs", candidates)

    assert result.manifest["counts"]["model_call"] == 60
    assert result.manifest["totals"]["cost"]["value"] > 0
    assert result.manifest["models"]["configured"]["request_model"]


def test_the_budget_bounds_the_pass_rather_than_one_candidate(tmp_path: Path, candidates) -> None:
    """`max_steps` counts every item, which is the claim the document makes about `over=`."""
    with pytest.raises(Exception) as caught:
        label = Pipeline(
            [
                LLMNode(
                    build_label_prompt,
                    output_schema=Verdict,
                    node_id="label",
                    over="candidates",
                )
            ],
            budget=Budget(max_steps=1, max_tokens=400_000, max_cost=1.00, max_wall_clock_ms=60_000),
        )
        label.run(
            {"candidates": candidates},
            model=FakeModelClient(responses=[fake_response(VERDICT)] * 64, scripted=False),
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs"), cost_basis=PRICES),
        )

    assert "max_steps" in str(caught.value)


def test_the_pass_is_not_read_as_a_run_of_the_agent(tmp_path: Path, candidates) -> None:
    """The finding B2 exists for: §1.4 writes into `runs/`, beside the agent's own runs."""
    project = tmp_path / "project"
    (project / "runs").mkdir(parents=True)
    label_pass(project / "runs", candidates)

    assert runs(project / "runs", role="labelling")
    assert runs(project / "runs", role="agent") == []
    assert _latest_run(project, runs_by_pipeline(project)) is None


def test_a_label_carries_the_run_that_decided_it(tmp_path: Path, candidates) -> None:
    """§1.5's block, over §1.4's result."""
    result = label_pass(tmp_path / "runs", candidates)

    write_labels(
        tmp_path / "evals" / "labels.jsonl",
        [
            Label(
                id=outcome.item["id"],
                verdict=outcome.value.answerable,
                reason=outcome.value.reasoning,
                decided_by=result.manifest["models"]["configured"]["request_model"],
                run_id=result.run_id,
            )
            for outcome in result.output.outcomes
            if outcome.error is None
        ],
    )

    labels = read_labels(tmp_path / "evals" / "labels.jsonl")
    assert len(labels) == 60
    assert labels["q0"].run_id == result.run_id
    assert run_path(tmp_path / "runs", result.run_id, "manifest.json").exists()


def test_the_document_still_teaches_this_shape() -> None:
    """The prose and the code above move together, or this file pins the wrong thing."""
    section = (Path(docs_path()) / "evaluation.md").read_text(encoding="utf-8")
    block = section[section.index("### 1.4 A label a model wrote") :]
    block = block[: block.index("### 1.5")]

    assert 'over="candidates"' in block
    assert 'role="labelling"' in block
    assert "max_steps=len(candidates)" in block
    assert "result.output.failures" in block
