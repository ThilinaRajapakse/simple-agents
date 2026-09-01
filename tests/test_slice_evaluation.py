"""A rung evaluated: what it is run on, what leaves its figures, and reading an older file.

`entering` and the format floor are here rather than beside the slice itself, because both are
about what an evaluation does with one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import Budget, ConfigurationError, Deterministic, Join, Pipeline, RunEnvelope
from simple_agents.evaluation import EvalSuite, Example, ExampleSet, Outcome
from simple_agents.evaluation.results import (
    EVAL_FORMAT_FLOOR,
    EVAL_FORMAT_VERSION,
    EvalResults,
)


def select(value, ctx) -> dict:
    return {"picked": (value.get("pool") or ["none"])[0]}


def judge(value, ctx) -> dict:
    return {"answer": value["picked"]}


def apologise(value, ctx) -> dict:
    return {"answer": "sorry"}


def present(value: Join, ctx) -> dict:
    return {"answer": value["judge"]["answer"], "absent": sorted(value.absent)}


def recommender(route=lambda output, ctx: "judge") -> Pipeline:
    return Pipeline(
        [
            Deterministic(select, node_id="select", successors=["judge", "apologise"], route=route),
            Deterministic(judge, node_id="judge", successors=["present"]),
            Deterministic(apologise, node_id="apologise", successors=["present"]),
            Deterministic(present, node_id="present", successors=[]),
        ],
        budget=Budget.unbounded(),
    )


def examples() -> ExampleSet:
    return ExampleSet(
        [
            Example(
                id=f"q{i}",
                inputs={"pool": [answer]},
                expected=answer,
                split="held_out",
                expected_by_node={"select": {"picked": answer}, "judge": {"answer": answer}},
            )
            for i, answer in enumerate(["a", "b", "c"])
        ]
    )


class TestWhatARungIsRunOn:
    def test_entering_takes_the_label_for_the_node_that_was_cut_off(self) -> None:
        rung = recommender().slice(start="judge")

        found = list(examples().entering(rung))

        assert [e.inputs for e in found] == [{"picked": "a"}, {"picked": "b"}, {"picked": "c"}]

    def test_a_join_of_the_labels_where_the_first_node_has_two_predecessors(self) -> None:
        rung = recommender().slice(start="present")
        labelled = ExampleSet(
            [
                Example(
                    id="q1",
                    inputs={},
                    expected="a",
                    split="held_out",
                    expected_by_node={"judge": {"answer": "a"}, "apologise": {"answer": "s"}},
                )
            ]
        )

        inputs = list(labelled.entering(rung))[0].inputs

        assert isinstance(inputs, Join)
        assert dict(inputs) == {"judge": {"answer": "a"}, "apologise": {"answer": "s"}}

    def test_an_example_with_no_label_for_the_cut_node_is_left_out(self) -> None:
        rung = recommender().slice(start="judge")
        mixed = ExampleSet(
            [
                Example(
                    id="q1",
                    inputs={},
                    expected="a",
                    split="held_out",
                    expected_by_node={"select": {"picked": "a"}},
                ),
                Example(id="q2", inputs={}, expected="b", split="held_out"),
            ]
        )

        assert [e.id for e in mixed.entering(rung)] == ["q1"]

    def test_a_prefix_cut_nothing_off_its_first_node(self) -> None:
        rung = recommender().slice(end="judge")

        assert [e.inputs for e in examples().entering(rung)] == [e.inputs for e in examples()]

    def test_a_whole_pipeline_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="not a slice"):
            examples().entering(recommender())

    def test_a_set_that_labels_none_of_it_is_refused(self) -> None:
        rung = recommender().slice(start="judge")
        bare = ExampleSet([Example(id="q1", inputs={}, expected="a", split="held_out")])

        with pytest.raises(ConfigurationError) as caught:
            bare.entering(rung)

        assert "no example in this set carries a label" in str(caught.value)


class TestARungThroughAnEvaluation:
    def _run(self, tmp_path: Path, rung: Pipeline, chosen: ExampleSet) -> EvalResults:
        suite = EvalSuite(rung, chosen, answer="answer", matches=lambda s: s.answer == s.expected)
        return suite.run(
            envelope=RunEnvelope(run_dir=tmp_path / "runs"),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

    def test_it_reports_the_eight_rates_like_any_pipeline(self, tmp_path: Path) -> None:
        rung = recommender().slice(start="judge")

        results = self._run(tmp_path, rung, examples().entering(rung))

        assert results.metrics["accuracy"].value == pytest.approx(1.0)
        assert set(results.nodes) == {"judge", "present"}

    def test_the_results_file_says_which_rung_it_is(self, tmp_path: Path) -> None:
        whole = recommender()
        rung = whole.slice(start="judge")

        results = self._run(tmp_path, rung, examples().entering(rung))

        recorded = results.config["slice"]
        assert recorded["of"] == whole.graph_fingerprint()
        assert recorded["nodes"] == ["judge", "present"]

    def test_a_whole_pipeline_records_null(self, tmp_path: Path) -> None:
        results = self._run(tmp_path, recommender(), examples())

        assert results.config["slice"] is None

    def test_a_rollout_that_left_the_slice_is_outside_every_figure(self, tmp_path: Path) -> None:
        rung = recommender(route=lambda output, ctx: "apologise").slice(
            nodes=["select", "judge", "present"]
        )

        results = self._run(tmp_path, rung, examples())

        assert all(r.outcome is Outcome.LEFT_THE_SLICE for r in results.rollouts)
        assert results.metrics["accuracy"].left_out == {"left_the_slice": 3}
        assert results.metrics["accuracy"].rollouts == 0

    def test_the_node_that_reached_the_boundary_counts_it(self, tmp_path: Path) -> None:
        rung = recommender(route=lambda output, ctx: "apologise").slice(
            nodes=["select", "judge", "present"]
        )

        results = self._run(tmp_path, rung, examples())

        assert results.nodes["select"].terminations["left_the_slice"] == 3


class TestReadingAnOlderResultsFile:
    """A results file is additive by default, so re-making one costs k rollouts of real spend."""

    def _written(self, tmp_path: Path) -> Path:
        suite = EvalSuite(
            recommender(),
            examples(),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
        )
        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path / "runs"),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )
        return results.write(tmp_path / "out.json")

    def test_the_floor_is_below_the_version_this_library_writes(self) -> None:
        assert EVAL_FORMAT_FLOOR < EVAL_FORMAT_VERSION

    def test_a_file_at_the_floor_is_read(self, tmp_path: Path) -> None:
        path = self._written(tmp_path)
        written = json.loads(path.read_text())
        written["eval_format_version"] = EVAL_FORMAT_FLOOR
        for rollout in written["rollouts"]:
            for observed in (rollout.get("nodes") or {}).values():
                observed.pop("ratios", None)
        written["config"].pop("slice", None)
        path.write_text(json.dumps(written))

        read_back = EvalResults.read(path)

        assert read_back.format_version == EVAL_FORMAT_FLOOR
        assert read_back.metrics["accuracy"].value is not None

    def test_it_says_which_figures_that_file_predates(self, tmp_path: Path) -> None:
        path = self._written(tmp_path)
        written = json.loads(path.read_text())
        written["eval_format_version"] = EVAL_FORMAT_FLOOR
        path.write_text(json.dumps(written))

        read_back = EvalResults.read(path)

        assert read_back.carries("node_ratios") is False
        assert read_back.carries("slice") is False
        assert read_back.carries("accuracy") is True

    def test_a_current_file_carries_everything(self, tmp_path: Path) -> None:
        read_back = EvalResults.read(self._written(tmp_path))

        assert read_back.format_version == EVAL_FORMAT_VERSION
        assert read_back.carries("node_ratios") is True

    def test_a_file_below_the_floor_is_refused(self, tmp_path: Path) -> None:
        path = self._written(tmp_path)
        written = json.loads(path.read_text())
        written["eval_format_version"] = "0.20"
        path.write_text(json.dumps(written))

        with pytest.raises(ConfigurationError, match="Re-run the evaluation"):
            EvalResults.read(path)

    def test_a_newer_file_is_refused_too(self, tmp_path: Path) -> None:
        path = self._written(tmp_path)
        written = json.loads(path.read_text())
        written["eval_format_version"] = "9.9"
        path.write_text(json.dumps(written))

        with pytest.raises(ConfigurationError, match="Re-run the evaluation"):
            EvalResults.read(path)
