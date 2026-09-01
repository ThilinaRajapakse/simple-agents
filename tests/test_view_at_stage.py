"""One project rendered at each stage, which is how a complex pipeline is read before it runs.

The six fixtures are one project per *shape*, and the only complex one is at `measure`. What a
builder sees at `build`, on a pipeline with a route, a loop, a fan-out, a failure path and a
nested pipeline, was viewable nowhere. `scripts/view_at_stage.py` derives each stage by taking
something away from the project's own directory, so no second copy of the graph exists to drift.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from view_at_stage import STAGES, _brief_at, build  # noqa: E402

BRANCHING = ROOT / "tests" / "fixtures" / "view_projects" / "branching"


@pytest.fixture(scope="module")
def stages(tmp_path_factory) -> dict[str, dict]:
    from simple_agents.view import assemble

    out = tmp_path_factory.mktemp("stages")
    made = build(BRANCHING, out, sorted(STAGES))
    return {stage: assemble(project) for stage, project, _page in made}


def declared(data: dict) -> list[dict]:
    return [p for p in data["pipelines"] if p["origin"] == "declared"]


class TestTheSamePipelineAtEachStage:
    def test_every_stage_draws_the_same_graph(self, stages) -> None:
        """The graph is the one thing that does not change, so nothing here can drift."""
        shapes = {
            stage: sorted(n["id"] for p in declared(data) for n in p["nodes"])
            for stage, data in stages.items()
        }

        assert len(set(map(tuple, shapes.values()))) == 1
        assert len(next(iter(shapes.values()))) == 13

    def test_the_stage_is_what_the_page_says_it_is(self, stages) -> None:
        assert {stage: data["stage"] for stage, data in stages.items()} == {
            "shape": "shape",
            "build": "build",
            "measure": "measure",
        }


class TestWhatEachStageHasToOverlay:
    def test_shape_has_no_run_and_no_evaluation(self, stages) -> None:
        held = stages["shape"]

        assert all(p["over_runs"] is None for p in declared(held))
        assert not (held["measured"] or {}).get("path")
        assert held["walks"]["walks"] == {}

    def test_build_has_the_runs_and_no_evaluation(self, stages) -> None:
        held = stages["build"]

        assert sum(p["over_runs"]["runs"] for p in declared(held) if p["over_runs"]) == 2
        assert all(p["over_rollouts"] is None for p in declared(held))
        assert not (held["measured"] or {}).get("path")

    def test_measure_has_both(self, stages) -> None:
        held = stages["measure"]
        triage = next(p for p in declared(held) if p["name"] == "triage")

        assert triage["over_runs"]["runs"] == 2
        assert triage["over_rollouts"]["runs"] == 16
        assert (held["measured"] or {}).get("path")

    def test_an_evaluations_rollouts_leave_with_it(self, stages) -> None:
        """They live under `runs/` and are the evaluation's record, not the project's."""
        assert stages["build"]["rollouts"]["runs"] == 0
        assert stages["measure"]["rollouts"]["runs"] == 32


class TestWhatTheDrawingSaysWithNothingToOverlay:
    def test_the_findings_at_shape_are_about_the_code_alone(self, stages) -> None:
        heads = [f["head"] for f in stages["shape"]["findings"]]

        assert "dedupe: not built." in heads
        # Nothing here has run, so no finding may be read out of a run or an evaluation.
        # Matched on the phrases a run overlay produces rather than on the word "run",
        # which a question named for the builder can carry.
        assert not any(
            phrase in head
            for head in heads
            for phrase in ("last run", "the evaluation", "edges untaken", "unmeasured")
        )

    def test_a_store_still_says_who_reaches_it_and_through_what(self, stages) -> None:
        handbook = next(r for r in stages["shape"]["resources"] if r["name"] == "handbook")

        assert handbook["access_count"] == 0
        assert [t["name"] for t in handbook["through"]] == [
            "handbook_lookup",
            "store_passage",
        ]
        assert handbook["through"][0]["code"]["where"]["at"] == "agent.py:49"

    def test_a_direction_no_run_has_settled_stays_undeclared(self, stages) -> None:
        """`inbox` reads as directed at `measure` because a run recorded it, and not before."""
        at_shape = next(r for r in stages["shape"]["resources"] if r["name"] == "inbox")
        at_measure = next(r for r in stages["measure"]["resources"] if r["name"] == "inbox")

        assert at_shape["unknown"] == ["triage/intake"] and at_shape["readers"] == []
        assert at_measure["readers"] == ["triage/intake"] and at_measure["unknown"] == []


class TestTheBriefIsMovedAndNotRewritten:
    def test_the_stage_moves_and_everything_else_stays(self) -> None:
        held = _brief_at('tier = "evaluated"\nstage = "measure"\nfoo = 1\n', "shape")

        assert 'stage = "shape"' in held
        assert 'tier = "evaluated"' in held and "foo = 1" in held

    def test_a_brief_naming_no_stage_gains_one(self) -> None:
        assert _brief_at('tier = "prototype"\n', "build").startswith('stage = "build"')

    def test_a_results_file_the_brief_names_leaves_with_the_evaluation(self) -> None:
        held = _brief_at('tier = "evaluated"\nresults = "evals/results/x.json"\n', "build")

        assert "results" not in held
