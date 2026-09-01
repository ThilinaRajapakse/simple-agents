"""A figure that is one total over another, and what a comparison does with it.

The arithmetic is fixed by hand before the code runs: two examples contributing 1 of 10 and 1
of 2 make 2 of 12, and the mean of their two ratios is 0.30. Every test that names a number
names one of those.

The end-to-end tests run a real pipeline against a scripted client, because what `over` decides
is which rollouts the runner calls the two halves on, which a hand-built results object cannot
show.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import ConfigurationError
from simple_agents.evaluation import Over, ProjectRatio, paired_ratio_ci, ratio_ci
from simple_agents.evaluation.compare import compare
from simple_agents.evaluation.metrics import Metric, aggregate, metrics_over
from simple_agents.evaluation.outcomes import Outcome, RolloutOutcome
from simple_agents.evaluation.results import EvalResults

from test_project_metrics import run


def rollouts(*pairs: tuple[str, float, float]) -> list[RolloutOutcome]:
    """One rollout per (example id, numerator, denominator)."""
    return [
        RolloutOutcome(
            example_id=example_id,
            rollout=index,
            seed=index,
            outcome=Outcome.CORRECT,
            ratios={"share": (numerator, denominator)},
        )
        for index, (example_id, numerator, denominator) in enumerate(pairs)
    ]


def share(**kwargs) -> ProjectRatio:
    return ProjectRatio(
        name="share",
        definition="the counted things, over what they are out of",
        numerator=lambda s: 0,
        denominator=lambda s: 0,
        **kwargs,
    )


# -- the interval ----------------------------------------------------------------------------


class TestTheRatioIsNotTheMean:
    """The quantity a project asks for when the thing counted is not the rollout.

    Three of five dogfoods computed one of these by hand and printed it, because a mean over
    examples is the only figure the library could report.
    """

    def test_it_pools_the_two_totals(self) -> None:
        assert ratio_ci([[(1, 10)], [(1, 2)]], resamples=500).point == pytest.approx(2 / 12)

    def test_the_mean_over_examples_is_a_different_number(self) -> None:
        """0.30 against 0.167. Both are defensible; they are not the same quantity."""
        by_example = [1 / 10, 1 / 2]
        assert sum(by_example) / 2 == pytest.approx(0.30)
        assert ratio_ci([[(1, 10)], [(1, 2)]], resamples=500).point != pytest.approx(0.30)

    def test_k_rollouts_of_one_example_travel_together(self) -> None:
        """The resampling unit is the example, so the interval reports n examples, not n rollouts."""
        interval = ratio_ci([[(1, 5), (1, 5)], [(1, 1), (0, 1)]], resamples=500)
        assert interval.n == 2
        assert interval.k == 2

    def test_a_ratio_on_a_bound_gets_wilson_rather_than_zero_width(self) -> None:
        """Every resample draws the same value, so a percentile interval would read as certain."""
        interval = ratio_ci([[(0, 10)], [(0, 7)]], resamples=500)
        assert interval.point == 0.0
        assert interval.high > 0.0
        assert "Wilson" in interval.method

    def test_the_pairwise_numbers_this_item_came_from(self) -> None:
        """Dogfood #5's 40 comparisons: 7 preferred each way, 26 preferring neither."""
        over_all = ratio_ci([[(w, 1)] for w in [1] * 7 + [0] * 33], resamples=2000)
        with_a_preference = ratio_ci([[(w, 1)] for w in [1] * 7 + [0] * 7], resamples=2000)
        assert over_all.point == pytest.approx(0.175)
        assert with_a_preference.point == pytest.approx(0.5)
        assert over_all.n == 40 and with_a_preference.n == 14


class TestWhatTheIntervalRefuses:
    """Each refusal names `ratio_ci` and what to pass instead."""

    def test_a_flat_sequence(self) -> None:
        with pytest.raises(ConfigurationError, match="flat sequence"):
            ratio_ci([0.5, 0.2])

    def test_no_examples(self) -> None:
        with pytest.raises(ConfigurationError, match="no examples"):
            ratio_ci([])

    def test_an_example_that_never_ran(self) -> None:
        with pytest.raises(ConfigurationError, match="no rollouts"):
            ratio_ci([[(1, 2)], []])

    def test_something_that_is_not_a_pair(self) -> None:
        with pytest.raises(ConfigurationError, match="two numbers"):
            ratio_ci([[(1,)]])

    def test_a_negative_denominator(self) -> None:
        with pytest.raises(ConfigurationError, match="negative denominator"):
            ratio_ci([[(1, -2)]])

    def test_a_denominator_that_sums_to_nothing(self) -> None:
        with pytest.raises(ConfigurationError, match="denominators sum to 0"):
            ratio_ci([[(0, 0)], [(0, 0)]])

    def test_too_few_resamples(self) -> None:
        with pytest.raises(ConfigurationError, match="below 100"):
            ratio_ci([[(1, 2)]], resamples=10)


class TestThePairedDifference:
    """How far one ratio moved from another, over the same examples."""

    def test_it_subtracts_the_two_pooled_ratios(self) -> None:
        moved = paired_ratio_ci([[(1, 10)], [(1, 2)]], [[(3, 10)], [(1, 2)]], resamples=500)
        assert moved.point == pytest.approx(4 / 12 - 2 / 12)

    def test_no_change_reads_as_zero(self) -> None:
        same = [[(1, 10)], [(1, 2)]]
        assert paired_ratio_ci(same, same, resamples=500).point == 0.0

    def test_two_sides_of_different_lengths_are_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="line up"):
            paired_ratio_ci([[(1, 2)]], [[(1, 2)], [(1, 2)]])


# -- the declaration -------------------------------------------------------------------------


class TestWhatTheDeclarationRefuses:
    def test_a_name_one_of_the_eight_rates_has(self) -> None:
        with pytest.raises(ConfigurationError, match="one of the eight rates"):
            ProjectRatio(
                name="recall", definition="d", numerator=lambda s: 1, denominator=lambda s: 1
            )

    def test_a_numerator_that_is_not_callable(self) -> None:
        with pytest.raises(ConfigurationError, match="needs numerator="):
            ProjectRatio(name="x", definition="d", numerator=5, denominator=lambda s: 1)

    def test_a_total_with_neither_a_denominator_nor_a_declared_reason(self) -> None:
        """The default is to declare a denominator; the census is the exception, not the escape."""
        with pytest.raises(ConfigurationError, match="no denominator"):
            ProjectRatio(name="x", definition="d", numerator=lambda s: 1)

    def test_an_empty_reason(self) -> None:
        with pytest.raises(ConfigurationError, match="empty no_interval"):
            ProjectRatio(
                name="x",
                definition="d",
                numerator=lambda s: 1,
                denominator=lambda s: 1,
                no_interval="  ",
            )

    def test_a_blank_reason_with_no_denominator_gets_the_denominator_message(self) -> None:
        """The guard that fires is the one whose message says what to pass."""
        with pytest.raises(ConfigurationError, match="no denominator"):
            ProjectRatio(name="x", definition="d", numerator=lambda s: 1, no_interval="  ")

    def test_a_census_is_accepted_with_its_reason(self) -> None:
        declared = ProjectRatio(
            name="x",
            definition="d",
            numerator=lambda s: 1,
            no_interval="a count over this run, not an estimate",
        )
        assert declared.estimated is False


# -- what the figure reports -----------------------------------------------------------------


class TestWhatAggregationProduces:
    def test_the_two_totals_and_the_interval(self) -> None:
        figure = aggregate(
            rollouts(("a", 1, 10), ("b", 1, 2)),
            {"a": False, "b": False},
            project=[share()],
            resamples=500,
        )["share"]
        assert (figure.numerator, figure.denominator) == (2, 12)
        assert figure.value == pytest.approx(2 / 12)
        assert figure.interval is not None
        assert figure.estimated is True

    def test_a_census_reports_its_number_and_no_interval(self) -> None:
        figure = aggregate(
            rollouts(("a", 40, 0), ("b", 7, 0)),
            {"a": False, "b": False},
            project=[
                ProjectRatio(
                    name="share",
                    definition="d",
                    numerator=lambda s: 0,
                    no_interval="a count over this run, not an estimate",
                )
            ],
            resamples=500,
        )["share"]
        assert figure.numerator == 47
        assert figure.interval is None
        assert figure.value == 47.0
        assert figure.estimated is False
        assert "not an estimate" in figure.reason

    def test_a_denominator_that_summed_to_nothing_reports_no_value(self) -> None:
        figure = aggregate(
            rollouts(("a", 0, 0), ("b", 0, 0)),
            {"a": False, "b": False},
            project=[share()],
            resamples=500,
        )["share"]
        assert figure.interval is None
        assert figure.value is None
        assert "no ratio to take" in figure.reason

    def test_it_round_trips_through_the_results_file(self, tmp_path: Path) -> None:
        figure = aggregate(
            rollouts(("a", 1, 10), ("b", 1, 2)),
            {"a": False, "b": False},
            project=[share()],
            resamples=500,
        )["share"]
        back = Metric.from_record(figure.to_record())
        assert (back.numerator, back.denominator) == (2, 12)
        assert back.estimated is True
        assert back.population == figure.population


class TestWhatTheReportPrints:
    """A figure with no interval still has a number, and a share still has its counts.

    The first live run printed `undefined: a count over this run` for a figure whose value was
    34, because a metric with no interval had never had one before.
    """

    def _report(self, figure: Metric) -> str:
        return EvalResults(
            eval_id="e",
            created_at="t",
            config={"n": 1, "k": 1},
            metrics={figure.name: figure},
            nodes={},
            rollouts=(),
        ).report()

    def test_a_census_prints_its_number_and_its_reason(self) -> None:
        line = self._report(
            Metric(
                name="cities_listed",
                definition="d",
                population="all rollouts",
                rollouts=6,
                examples=3,
                numerator=34,
                estimated=False,
                unit="cities",
                reason="a count over this run, not an estimate of a rate",
            )
        )
        assert "34 cities" in line
        assert "not an estimate of a rate" in line
        assert "undefined" not in line

    def test_a_figure_with_no_value_still_reads_as_undefined(self) -> None:
        """An empty population reports no value, which is a different thing from a census."""
        line = self._report(
            Metric(
                name="recall",
                definition="d",
                population="rollouts where a value exists",
                rollouts=0,
                examples=0,
                reason="No rollouts fall under it.",
            )
        )
        assert "undefined" in line

    def test_a_share_prints_the_two_totals_behind_it(self) -> None:
        """7 of 14 cannot be read as the whole picture unless the counts are on the line."""
        figure = aggregate(
            rollouts(("a", 1, 10), ("b", 1, 2)),
            {"a": False, "b": False},
            project=[share()],
            resamples=500,
        )["share"]
        assert "(2 of 12)" in self._report(figure)


class TestWhatAComparisonDoes:
    """A ratio pairs on the two counts each rollout recorded, not on a per-rollout score.

    Pairing it the way a mean is paired finds nothing, and the first attempt reported "no
    shared example falls under this denominator on both sides" for examples that were on both
    sides. The figure was visible and the reason was false.
    """

    def _results(self, *pairs: tuple[str, float, float]) -> EvalResults:
        outcomes = tuple(rollouts(*pairs))
        return EvalResults(
            eval_id="e",
            created_at="t",
            config={"n": 2, "k": 1},
            metrics=aggregate(outcomes, {"a": False, "b": False}, project=[share()], resamples=300),
            nodes={},
            rollouts=outcomes,
            examples={"a": {}, "b": {}},
        )

    def test_it_reports_the_difference_of_the_two_pooled_ratios(self) -> None:
        change = compare(
            self._results(("a", 1, 10), ("b", 1, 2)),
            self._results(("a", 3, 10), ("b", 1, 2)),
            resamples=500,
        ).metrics["share"]
        assert change.before == pytest.approx(2 / 12)
        assert change.after == pytest.approx(4 / 12)
        assert change.difference is not None
        assert "difference of two ratios" in change.difference.method

    def test_a_census_reports_both_numbers_and_withholds_a_verdict(self) -> None:
        counted = ProjectRatio(
            name="share", definition="d", numerator=lambda s: 0, no_interval="a count over this run"
        )

        def built(*pairs):
            outcomes = tuple(rollouts(*pairs))
            return EvalResults(
                eval_id="e",
                created_at="t",
                config={"n": 2, "k": 1},
                metrics=aggregate(
                    outcomes, {"a": False, "b": False}, project=[counted], resamples=300
                ),
                nodes={},
                rollouts=outcomes,
                examples={"a": {}, "b": {}},
            )

        change = compare(
            built(("a", 1, 0), ("b", 1, 0)), built(("a", 3, 0), ("b", 1, 0)), resamples=500
        ).metrics["share"]
        assert (change.before, change.after) == (2.0, 4.0)
        assert change.moved is None
        assert "count over each run" in change.reason
        assert "not a measured change" in change.reason


class TestAGroupedCell:
    """Every figure again over one cell of a grouping, recomputed from the rollouts' own counts."""

    def test_a_ratio_is_recomputed_rather_than_reported_undefined(self) -> None:
        outcomes = rollouts(("a", 1, 10), ("b", 1, 2))
        whole = aggregate(outcomes, {"a": False, "b": False}, project=[share()], resamples=300)

        cell = metrics_over(outcomes, {"a": False, "b": False}, like=whole, resamples=300)

        assert cell["share"].value == pytest.approx(2 / 12)
        assert (cell["share"].numerator, cell["share"].denominator) == (2, 12)

    def test_a_census_keeps_its_reason_through_the_recompute(self) -> None:
        counted = ProjectRatio(
            name="share", definition="d", numerator=lambda s: 0, no_interval="a count over this run"
        )
        outcomes = rollouts(("a", 1, 0), ("b", 1, 0))
        whole = aggregate(outcomes, {"a": False, "b": False}, project=[counted], resamples=300)

        cell = metrics_over(outcomes, {"a": False, "b": False}, like=whole, resamples=300)

        assert cell["share"].value == 2.0
        assert cell["share"].estimated is False
        assert cell["share"].reason == "a count over this run"


# -- end to end ------------------------------------------------------------------------------


def picks(s) -> int:
    """A count over the answer: how many words it holds."""
    return len(str(s.answer).split())


class TestThroughAnEvaluation:
    """What the runner records, because `over` decides which rollouts the halves are called on."""

    def _run(self, tmp_path: Path, declared: ProjectRatio) -> EvalResults:
        return run(tmp_path, metrics=[declared])

    def test_the_pairs_travel_in_the_results_file(self, tmp_path: Path) -> None:
        results = self._run(
            tmp_path,
            ProjectRatio(
                name="words",
                definition="words in the answer, over rollouts",
                numerator=picks,
                denominator=lambda s: 1.0,
            ),
        )
        written = json.loads(results.write(tmp_path / "out.json").read_text())
        assert all("words" in r["ratios"] for r in written["rollouts"])
        assert written["metrics"]["words"]["numerator"] is not None

    def test_a_comparison_needs_neither_the_labels_nor_the_functions(self, tmp_path: Path) -> None:
        declared = ProjectRatio(
            name="words",
            definition="words in the answer, over rollouts",
            numerator=picks,
            denominator=lambda s: 1.0,
        )
        results = self._run(tmp_path, declared)
        path = results.write(tmp_path / "out.json")

        read_back = EvalResults.read(path)

        assert read_back.metrics["words"].numerator == results.metrics["words"].numerator
        assert read_back.rollouts[0].ratios["words"] == results.rollouts[0].ratios["words"]

    def test_over_asserted_leaves_out_the_rollouts_that_put_no_value_forward(
        self, tmp_path: Path
    ) -> None:
        """Two of the three examples abstain, so an asserted-only figure covers fewer rollouts."""
        everything = self._run(
            tmp_path / "all",
            ProjectRatio(
                name="words",
                definition="d",
                numerator=picks,
                denominator=lambda s: 1.0,
                over=Over.ALL,
            ),
        )
        asserted = self._run(
            tmp_path / "asserted",
            ProjectRatio(
                name="words",
                definition="d",
                numerator=picks,
                denominator=lambda s: 1.0,
                over=Over.ASSERTED,
            ),
        )
        assert asserted.metrics["words"].rollouts < everything.metrics["words"].rollouts


class TestARubricWithNamedAxes:
    """Shape F2: one answer scores accurate and badly written, and both show.

    Per-criterion figures already shipped, one condition at a time. What was missing was the
    roll-up: `Scoring` carried the outcome and not the verdict, so a figure could not read
    which conditions were met and average them per axis.
    """

    def _verdict(self):
        from simple_agents.evaluation.scoring import Verdict

        return Verdict(
            grade=0.5,
            met=2,
            total=4,
            parts={
                "accuracy.facts": True,
                "accuracy.no_invention": True,
                "style.brevity": False,
                "style.plain": False,
            },
        )

    def test_a_figure_can_roll_the_criteria_up_per_axis(self) -> None:
        from simple_agents.evaluation import Example
        from simple_agents.evaluation.scoring import Scoring

        scoring = Scoring(
            answer="a long jargony but accurate answer",
            expected=None,
            example=Example(id="q1", inputs={}, expected=None, split="dev"),
            rollout=0,
            seed=0,
            verdict=self._verdict(),
        )

        def axis(s, prefix):
            parts = {k: met for k, met in s.verdict.parts.items() if k.startswith(prefix)}
            return sum(1 for met in parts.values() if met) / len(parts)

        assert axis(scoring, "accuracy.") == 1.0
        assert axis(scoring, "style.") == 0.0

    def test_a_scoring_built_without_one_carries_none(self) -> None:
        """`matches` and a criterion's check decide the verdict, so they cannot read it."""
        from simple_agents.evaluation import Example
        from simple_agents.evaluation.scoring import Scoring

        scoring = Scoring(
            answer="a",
            expected=None,
            rollout=0,
            seed=0,
            example=Example(id="q", inputs={}, expected=None, split="dev"),
        )
        assert scoring.verdict is None


class TestARatioPerNode:
    """A ratio is reportable per node, which is where a figure like `unreadable_pages` belongs.

    It was refused at the declaration until P3-53, on the reading that nothing recorded two
    totals per node. `NodeObservation.ratios` records them, so the refusal is gone and the
    figure is summed over the rollouts that reached the node rather than averaged.
    """

    def _declared(self) -> ProjectRatio:
        return ProjectRatio(
            name="words_per_node",
            definition="words in this node's output, over its rollouts",
            numerator=lambda s: float(len(str(s.answer).split())),
            denominator=lambda s: 1.0,
            over=Over.ALL,
        )

    def test_it_is_accepted_and_reported(self, tmp_path: Path) -> None:
        results = run(tmp_path, node_metrics={"extract": [self._declared()]})

        figure = results.nodes["extract"].metrics["words_per_node"]
        assert figure.numerator is not None
        assert figure.denominator is not None
        assert figure.value == pytest.approx(figure.numerator / figure.denominator)

    def test_it_sums_rather_than_averaging(self, tmp_path: Path) -> None:
        """The pairs the rollouts contributed add up to the two totals the figure reports."""
        results = run(tmp_path, node_metrics={"extract": [self._declared()]})

        pairs = [
            r.nodes["extract"].ratios["words_per_node"]
            for r in results.rollouts
            if "extract" in r.nodes and "words_per_node" in r.nodes["extract"].ratios
        ]
        figure = results.nodes["extract"].metrics["words_per_node"]
        assert pairs
        assert figure.numerator == pytest.approx(sum(n for n, _ in pairs))
        assert figure.denominator == pytest.approx(sum(d for _, d in pairs))

    def test_the_pairs_travel_in_the_results_file(self, tmp_path: Path) -> None:
        results = run(tmp_path, node_metrics={"extract": [self._declared()]})
        path = results.write(tmp_path / "out.json")

        written = json.loads(path.read_text())
        recorded = [
            r["nodes"]["extract"]["ratios"] for r in written["rollouts"] if "extract" in r["nodes"]
        ]
        assert any("words_per_node" in one for one in recorded)

        read_back = EvalResults.read(path)
        assert (
            read_back.nodes["extract"].metrics["words_per_node"].numerator
            == results.nodes["extract"].metrics["words_per_node"].numerator
        )

    def test_a_mean_per_node_still_reports_as_a_mean(self, tmp_path: Path) -> None:
        from simple_agents.evaluation import ProjectMetric

        results = run(
            tmp_path,
            node_metrics={
                "extract": [ProjectMetric(name="overlap", definition="d", score=lambda s: 0.5)]
            },
        )
        figure = results.nodes["extract"].metrics["overlap"]
        assert figure.numerator is None
        assert figure.interval is not None


def words(s) -> float:
    """One numerator: how many words the answer holds."""
    return float(len(str(s.answer).split()))


def triple_words(s) -> float:
    """Another, differing in source, so the two record different versions."""
    return float(len(str(s.answer).split())) * 3.0


def one_each(s) -> float:
    return 1.0


class TestComparingARatio:
    """`compare()` over a ratio, end to end and per node.

    Both were found by reading rather than by the suite: a per-node ratio was paired on
    `scores`, where a ratio records nothing, so every one reported "no shared example falls
    under the denominator on both sides" with every example on both sides. And `_version` read
    the `version` key, which a `ProjectRatio` does not write, so a numerator could be rewritten
    between two evaluations and the comparison would call the difference a real change.
    """

    def _ratio(self, numerator, name: str = "words") -> ProjectRatio:
        return ProjectRatio(
            name=name,
            definition="words in the answer, over rollouts",
            numerator=numerator,
            denominator=one_each,
            over=Over.ALL,
        )

    def test_a_per_node_ratio_is_paired_on_the_pairs_it_recorded(self, tmp_path) -> None:
        before = run(tmp_path / "a", node_metrics={"extract": [self._ratio(words)]})
        after = run(tmp_path / "b", node_metrics={"extract": [self._ratio(words)]})

        change = compare(before, after).nodes["extract"].metrics["words"]

        assert change.examples > 0
        assert change.reason is None
        assert change.difference is not None

    def test_a_per_node_ratio_that_moved_reports_the_difference(self, tmp_path) -> None:
        """The figure triples, and the comparison says so rather than finding nothing to pair."""
        before = run(tmp_path / "a", node_metrics={"extract": [self._ratio(words)]})
        after = run(tmp_path / "b", node_metrics={"extract": [self._ratio(triple_words)]})

        change = compare(before, after).nodes["extract"].metrics["words"]

        assert change.after == pytest.approx(change.before * 3.0)
        assert change.difference.point == pytest.approx(change.after - change.before)

    def test_an_edited_numerator_withholds_the_verdict_end_to_end(self, tmp_path) -> None:
        before = run(tmp_path / "a", metrics=[self._ratio(words)])
        after = run(tmp_path / "b", metrics=[self._ratio(triple_words)])

        change = compare(before, after).metrics["words"]

        assert change.rule_moved is not None
        assert change.moved is None
        assert "The rule that scored this figure changed" in change.verdict_reason

    def test_an_edited_numerator_withholds_it_per_node_too(self, tmp_path) -> None:
        before = run(tmp_path / "a", node_metrics={"extract": [self._ratio(words)]})
        after = run(tmp_path / "b", node_metrics={"extract": [self._ratio(triple_words)]})

        change = compare(before, after).nodes["extract"].metrics["words"]

        assert change.rule_moved is not None
        assert change.moved is None

    def test_an_unedited_ratio_reports_no_rule_change(self, tmp_path) -> None:
        before = run(tmp_path / "a", metrics=[self._ratio(words)])
        after = run(tmp_path / "b", metrics=[self._ratio(words)])

        assert compare(before, after).metrics["words"].rule_moved is None

    def test_the_two_halves_are_named_in_the_reason(self, tmp_path) -> None:
        """A ratio has a version per half, so the sentence has to say which one is which."""
        before = run(tmp_path / "a", metrics=[self._ratio(words)])
        after = run(tmp_path / "b", metrics=[self._ratio(triple_words)])

        reason = compare(before, after).metrics["words"].verdict_reason

        assert "numerator" in reason and "denominator" in reason
