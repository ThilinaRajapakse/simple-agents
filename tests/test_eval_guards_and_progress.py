"""What an evaluation refuses to run, and what it reports while it runs.

Three findings from the 2026-08-13 checkpoint. A contaminated-split refusal fired on a pair
from two splits the evaluation was not measuring, and said the pair fell on both sides of the
split it was. The `Cassette.update` refusal named no way past itself while the library's own
sweeps passed one. And every progress snapshot carried `cost=None`, so the callback that exists
to say what a run is costing could not.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from simple_agents import (
    Cassette,
    ConfigurationError,
    LLMNode,
    Pipeline,
    RunEnvelope,
)
from simple_agents.cost import PriceBasis
from simple_agents.evaluation import Example, ExampleSet
from simple_agents.evaluation.progress import RolloutProgress
from simple_agents.evaluation.runner import EvalSuite

from schemas import Answer
from test_eval_identity_and_failures import BUDGET, EXACT, Scripted, build_prompt

BASIS = PriceBasis(currency="USD", input_uncached_per_mtok=1.0, output_per_mtok=2.0)


def pipeline() -> Pipeline:
    return Pipeline([LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET)


def question(example_id: str, text: str, *, split: str, source: str | None = None) -> Example:
    return Example(
        id=example_id,
        inputs={"question": text},
        expected="Kirkwall",
        split=split,
        source=source,
    )


LEEDS = "Which retailer ships from Leeds?"
NORTHGATE = "Who founded Northgate?"


class TestTheContaminatedSplitRefusal:
    """Only an overlap that can reach the number being measured stops the run."""

    def suite(self, examples: ExampleSet) -> EvalSuite:
        return EvalSuite(
            pipeline(),
            examples,
            answer="answer",
            matches=EXACT,
            contamination_threshold=0.8,
        )

    def test_an_overlap_between_two_other_splits_does_not_stop_the_run(self, tmp_path) -> None:
        """A dev/scratch pair cannot leak into a held_out number."""
        examples = ExampleSet(
            [
                question("held1", LEEDS, split="held_out"),
                question("dev1", NORTHGATE, split="dev"),
                question("scratch1", NORTHGATE, split="scratch"),
            ]
        )

        results = self.suite(examples).run(
            envelope=RunEnvelope(run_dir=tmp_path, cost_basis=BASIS),
            model=Scripted(),
            split="held_out",
            k=1,
            seed=41,
        )

        assert results.contamination.clean is False
        assert [p.kind for p in results.contamination.pairs] == ["near_duplicate"]

    def test_an_overlap_reaching_the_measured_split_stops_it(self, tmp_path) -> None:
        examples = ExampleSet(
            [
                question("held1", LEEDS, split="held_out"),
                question("dev1", LEEDS, split="dev"),
            ]
        )

        with pytest.raises(ConfigurationError) as raised:
            self.suite(examples).run(
                envelope=RunEnvelope(run_dir=tmp_path, cost_basis=BASIS),
                model=Scripted(),
                split="held_out",
                k=1,
                seed=41,
            )

        assert "fall on both sides of this split" in str(raised.value)
        assert "held1" in str(raised.value)

    def test_the_whole_report_is_recorded_even_where_nothing_was_refused(self, tmp_path) -> None:
        """What was found is on file whether or not it stopped the run."""
        examples = ExampleSet(
            [
                question("held1", LEEDS, split="held_out"),
                question("dev1", NORTHGATE, split="dev", source="doc:northgate"),
                question("scratch1", NORTHGATE, split="scratch", source="doc:northgate"),
            ]
        )

        results = self.suite(examples).run(
            envelope=RunEnvelope(run_dir=tmp_path, cost_basis=BASIS),
            model=Scripted(),
            split="held_out",
            k=1,
            seed=41,
        )

        kinds = sorted(p.kind for p in results.contamination.pairs)
        assert kinds == ["near_duplicate", "shared_source"]


class TestTheMixedCassetteRefusal:
    def suite(self) -> EvalSuite:
        return EvalSuite(
            pipeline(),
            ExampleSet([question("held1", LEEDS, split="held_out")]),
            answer="answer",
            matches=EXACT,
        )

    def test_the_refusal_names_the_way_past_it(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            self.suite().run(
                envelope=RunEnvelope(
                    run_dir=tmp_path, cassette=Cassette.update(tmp_path / "c.jsonl")
                ),
                model=Scripted(),
                split="held_out",
                k=1,
                seed=41,
            )

        assert "allow_mixed_cassette=True" in str(raised.value)

    def test_the_override_runs_it(self, tmp_path) -> None:
        results = self.suite().run(
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.update(tmp_path / "c.jsonl")),
            model=Scripted(),
            split="held_out",
            k=1,
            seed=41,
            allow_mixed_cassette=True,
        )

        assert len(results.rollouts) == 1


class TestProgressReportsWhatTheRunIsCosting:
    def run_watching(self, tmp_path, **kwargs) -> list[RolloutProgress]:
        seen: list[RolloutProgress] = []
        EvalSuite(
            pipeline(),
            ExampleSet(
                [
                    question("held1", LEEDS, split="held_out"),
                    question("held2", NORTHGATE, split="held_out"),
                ]
            ),
            answer="answer",
            matches=EXACT,
        ).run(
            envelope=RunEnvelope(run_dir=tmp_path, **kwargs),
            model=Scripted(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
            on_rollout=seen.append,
        )
        return seen

    def test_the_cost_accumulates_as_rollouts_land(self, tmp_path) -> None:
        seen = self.run_watching(tmp_path, cost_basis=BASIS)

        assert len(seen) == 2
        assert seen[0].cost is not None and seen[0].cost > 0
        assert seen[1].cost > seen[0].cost
        assert seen[1].currency == "USD"

    def test_progress_is_kept_on_disk_beside_the_rollouts(self, tmp_path) -> None:
        """A page following the evaluation reads a denominator the runner declared and the
        outcomes scored so far, so it invents neither."""
        import json

        self.run_watching(tmp_path, cost_basis=BASIS)
        [progress] = list(Path(tmp_path).glob("eval/*/progress.json"))
        held = json.loads(progress.read_text())
        assert held["total"] == 2 and held["finished"] == 2
        assert sum(held["outcomes"].values()) == 2
        assert held["cost"] > 0 and held["currency"] == "USD"
        assert held["updated_at"]

    def test_describe_prints_the_figure_with_its_unit(self, tmp_path) -> None:
        line = self.run_watching(tmp_path, cost_basis=BASIS)[-1].describe()

        assert "USD" in line
        assert "2/2 rollouts" in line

    def test_a_cost_below_a_hundredth_of_a_cent_does_not_print_as_zero(self) -> None:
        """A figure that prints as 0.0000 reads as free, and a real run costs this little."""
        snapshot = RolloutProgress(
            eval_id="eval_x",
            finished=2,
            total=2,
            resumed=0,
            outcomes={"correct": 2},
            cost=1.2e-05,
            elapsed_s=1.0,
            remaining_s=None,
            latest=None,
            currency="USD",
        )

        assert "1.2e-05 USD" in snapshot.describe()

    def test_a_run_with_no_cost_basis_reports_no_cost(self, tmp_path) -> None:
        """None means nothing could be priced, which is not the same as zero."""
        seen = self.run_watching(tmp_path)

        assert [p.cost for p in seen] == [None, None]
        assert seen[-1].currency is None
        assert "USD" not in seen[-1].describe()
