"""How far a figure moves when the same examples are run again, and what a comparison does.

An interval resamples examples, holding each example's mean over its own rollouts fixed, so it
says how much the figure would move on a different sample of examples. It says nothing about
running these same examples again, which moves the figure too because the agent is stochastic.
Dogfood #4 measured that by hand at three times the cost of one evaluation; the same number is
in the rollouts one evaluation already records.
"""

from __future__ import annotations

import math

import pytest

from simple_agents.evaluation import EvalResults, Outcome, compare
from simple_agents.evaluation.intervals import rollout_noise
from simple_agents.evaluation.metrics import aggregate
from simple_agents.evaluation.outcomes import RolloutOutcome


class TestTheNumberItself:
    def test_it_is_the_deviation_of_the_figure_from_within_example_variation(self) -> None:
        """Each example's rollouts are one sample of that example's own rate."""
        # Two examples split 2/1 and 1/2, one unanimous. Each split has variance 1/3 over 3
        # rollouts, so the figure's variance is (1/3/3 + 1/3/3 + 0) / 9.
        noise = rollout_noise([[1, 1, 0], [1, 0, 0], [1, 1, 1]])

        assert noise == pytest.approx(math.sqrt(2 / 9) / 3)

    def test_a_set_whose_rollouts_all_agreed_has_none_of_it(self) -> None:
        assert rollout_noise([[1, 1, 1], [0, 0, 0]]) == 0.0

    def test_one_rollout_per_example_leaves_nothing_to_read(self) -> None:
        """At k=1 there is no within-example variation, and zero would be a claim."""
        assert rollout_noise([[1], [0], [1]]) is None

    def test_it_is_reported_where_the_interval_reads_as_certainty(self) -> None:
        """Every example scoring alike gives resampling nothing, and the rollouts still moved."""
        rollouts = tuple(
            RolloutOutcome(
                example_id=f"q{i}",
                rollout=j,
                seed=j,
                outcome=Outcome.CORRECT if j else Outcome.FALSE_CONFIDENCE,
            )
            for i in range(10)
            for j in range(3)
        )
        metric = aggregate(rollouts, {f"q{i}": False for i in range(10)}, seed=41)["accuracy"]

        assert metric.interval.width == pytest.approx(0.0)
        assert metric.rollout_noise > 0.0

    def test_it_survives_the_results_file(self) -> None:
        from simple_agents.evaluation.metrics import Metric

        metric = Metric(
            name="accuracy",
            definition="d",
            population="all rollouts",
            rollouts=9,
            examples=3,
            rollout_noise=0.017,
        )

        assert Metric.from_record(metric.to_record()).rollout_noise == pytest.approx(0.017)

    def test_a_file_written_before_this_carries_none(self) -> None:
        from simple_agents.evaluation.metrics import Metric

        record = Metric(
            name="accuracy",
            definition="d",
            population="all rollouts",
            rollouts=9,
            examples=3,
            rollout_noise=0.017,
        ).to_record()
        del record["rollout_noise"]

        assert Metric.from_record(record).rollout_noise is None


def a_run(per_example: list[list[float]]) -> EvalResults:
    rollouts = tuple(
        RolloutOutcome(
            example_id=f"q{i}",
            rollout=j,
            seed=j,
            outcome=Outcome.CORRECT if score else Outcome.FALSE_CONFIDENCE,
            answer="x",
        )
        for i, scores in enumerate(per_example)
        for j, score in enumerate(scores)
    )
    absence = {f"q{i}": False for i in range(len(per_example))}
    return EvalResults(
        eval_id="e",
        created_at="2026-01-01T00:00:00.000Z",
        config={"split": "dev", "k": len(per_example[0]), "n": len(per_example), "seed": 41},
        metrics=aggregate(rollouts, absence, seed=41),
        nodes={},
        rollouts=rollouts,
        examples={
            f"q{i}": {
                "split": "dev",
                "expects_absence": False,
                "absent_parts": [],
                "source": None,
                "metadata": {},
            }
            for i in range(len(per_example))
        },
    )


class TestWhatAComparisonDoesWithIt:
    def _pair(self, before: list[list[float]], after: list[list[float]]):
        return compare(a_run(before), a_run(after)).metrics["accuracy"]

    def test_the_difference_carries_both_sides_combined(self) -> None:
        """Two independent runs, so the difference's deviation is the root of the sum."""
        before = [[1.0, 1.0, 0.0]] * 25 + [[0.0, 0.0, 0.0]] * 5
        after = [[1.0, 1.0, 0.0]] * 26 + [[0.0, 0.0, 0.0]] * 4
        change = self._pair(before, after)

        expected = math.sqrt(
            a_run(before).metrics["accuracy"].rollout_noise ** 2
            + a_run(after).metrics["accuracy"].rollout_noise ** 2
        )
        assert change.rollout_noise == pytest.approx(expected)

    def test_a_difference_inside_the_noise_withholds_the_verdict(self) -> None:
        """The interval excludes zero and the difference is what one run gives twice."""
        # Four of thirty examples lose one rollout and the rest are unchanged. Few enough
        # movers that the resample rarely draws none of them, so the interval clears zero;
        # small enough against what the rollouts themselves do that it is not a finding.
        before = [[1.0, 1.0, 0.0]] * 30
        after = [[1.0, 1.0, 0.0]] * 26 + [[1.0, 0.0, 0.0]] * 4
        change = self._pair(before, after)

        assert change.difference.excludes(0.0), "the interval alone would report a move"
        assert change.inside_the_noise is True
        assert change.moved is None
        assert "what running the same thing twice gives" in change.verdict_reason

    def test_a_difference_clear_of_the_noise_still_moves(self) -> None:
        before = [[0.0, 0.0, 0.0]] * 30
        after = [[1.0, 1.0, 1.0]] * 30
        change = self._pair(before, after)

        assert change.moved is True
        assert change.inside_the_noise is False

    def test_a_difference_of_nothing_is_not_moved_rather_than_undecided(self) -> None:
        """Zero is inside the noise and is not in doubt: the answer is that nothing moved."""
        both = [[1.0, 1.0, 0.0]] * 30
        change = self._pair(both, both)

        assert change.inside_the_noise is True
        assert change.moved is False
        assert change.verdict_reason is None

    def test_the_reason_is_the_one_that_withheld_the_verdict(self) -> None:
        """Found on a live run: two conditions applied and the wrong one was reported.

        Thirteen examples is under the threshold for any verdict, and the difference was also
        inside the noise. `moved` was withheld for the first and `verdict_reason` named the
        second, so the reader was told to raise k when no k would have helped.
        """
        before = [[1.0, 1.0, 0.0]] * 13
        after = [[1.0, 1.0, 0.0]] * 9 + [[1.0, 0.0, 0.0]] * 4
        change = self._pair(before, after)

        assert change.difference.n < 20
        assert change.inside_the_noise is True, "both conditions apply to this pair"
        assert change.moved is None
        assert "13 example(s) carry this metric" in change.verdict_reason
        assert "running the same thing twice" not in change.verdict_reason

    def test_two_runs_at_k_one_carry_no_noise_and_the_verdict_stands(self) -> None:
        before = [[0.0]] * 30
        after = [[1.0]] * 30
        change = self._pair(before, after)

        assert change.rollout_noise is None
        assert change.inside_the_noise is False
        assert change.moved is True
