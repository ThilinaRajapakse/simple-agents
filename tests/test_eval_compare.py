"""Comparing two evaluations, and refusing the comparisons that mean nothing.

Built from results objects assembled in the test rather than from real runs, so the answer the
comparison should give is fixed before the code runs.
"""

from __future__ import annotations

import pytest

from simple_agents import ConfigurationError
from simple_agents.evaluation import Outcome, RolloutOutcome
from simple_agents.evaluation.outcomes import NodeObservation
from simple_agents.evaluation.per_node import NodeMetrics, node_rates
from simple_agents.evaluation.compare import compare
from simple_agents.evaluation.metrics import aggregate
from simple_agents.evaluation.results import EvalResults


def results(
    outcomes: dict[str, list[Outcome]],
    *,
    absence: set[str] = frozenset(),
    content_hash: str = "ex_fixed",
    config: dict | None = None,
) -> EvalResults:
    """A results object over handcrafted outcomes, one list of rollouts per example."""
    rollouts = tuple(
        RolloutOutcome(example_id=example_id, rollout=index, seed=100 + index, outcome=outcome)
        for example_id, sequence in outcomes.items()
        for index, outcome in enumerate(sequence)
    )
    expects = {example_id: example_id in absence for example_id in outcomes}
    return EvalResults(
        eval_id="eval_test",
        created_at="2026-07-29T09:00:00.000Z",
        config={"example_set": {"content_hash": content_hash}, **(config or {})},
        metrics=aggregate(rollouts, expects, resamples=200, seed=41),
        nodes={},
        rollouts=rollouts,
        examples={
            example_id: {"split": "held_out", "expects_absence": example_id in absence}
            for example_id in outcomes
        },
    )


def flat(outcome: Outcome, examples: int, k: int, start: int = 1) -> dict[str, list[Outcome]]:
    return {f"q{i}": [outcome] * k for i in range(start, examples + start)}


# -- a change that moved ------------------------------------------------------------------


def test_an_agent_that_got_worse_everywhere_reports_a_moved_metric() -> None:
    before = results(flat(Outcome.CORRECT, 20, 3))
    after = results(flat(Outcome.FALSE_CONFIDENCE, 20, 3))

    comparison = compare(before, after, resamples=500, seed=41)

    accuracy = comparison.metrics["accuracy"]
    assert accuracy.before == 1.0
    assert accuracy.after == 0.0
    assert accuracy.delta == pytest.approx(-1.0)
    assert accuracy.moved is True
    assert "accuracy" in comparison.moved
    assert "false_confidence_rate" in comparison.moved


def test_the_same_agent_twice_reports_nothing_moved() -> None:
    pattern = [
        [Outcome.CORRECT, Outcome.CORRECT],
        [Outcome.MISSED, Outcome.CORRECT],
        [Outcome.FALSE_CONFIDENCE, Outcome.MISSED],
        [Outcome.CORRECT, Outcome.CORRECT],
    ]
    outcomes = {f"q{i}": pattern[i % len(pattern)] for i in range(24)}

    comparison = compare(results(outcomes), results(outcomes), resamples=500, seed=41)

    assert comparison.moved == []
    assert comparison.undecided == []
    assert comparison.metrics["accuracy"].moved is False
    assert comparison.metrics["accuracy"].delta == pytest.approx(0.0)


def test_a_small_change_does_not_count_as_moved() -> None:
    """One example of twenty-four flipping is what the same agent produces twice in a row."""
    before = {f"q{i}": [Outcome.CORRECT] for i in range(1, 25)}
    after = {**before, "q1": [Outcome.FALSE_CONFIDENCE]}

    comparison = compare(results(before), results(after), resamples=1000, seed=41)

    change = comparison.metrics["accuracy"]
    assert change.before > change.after
    assert change.moved is False
    assert change.difference.low <= 0.0 <= change.difference.high


def test_too_few_examples_withhold_the_verdict_rather_than_denying_it() -> None:
    """Every example moving the same way gives an interval of zero width.

    That reads as certainty and is the sample having no variation to resample, so the delta
    and the interval are reported and the claim that the difference is real is not.
    """
    before = {f"q{i}": [Outcome.CORRECT] for i in range(1, 4)}
    after = {f"q{i}": [Outcome.FALSE_CONFIDENCE] for i in range(1, 4)}

    comparison = compare(results(before), results(after), resamples=1000, seed=41)

    change = comparison.metrics["accuracy"]
    assert change.moved is None
    assert change.delta == pytest.approx(-1.0)
    assert change.difference.low == change.difference.high
    assert comparison.moved == []
    assert "accuracy" in comparison.undecided
    assert "3 example(s)" in change.verdict_reason
    assert "needs 20" in change.verdict_reason


def test_a_single_example_never_carries_a_verdict() -> None:
    """The degenerate case: one example, one rollout, an interval of zero width."""
    comparison = compare(
        results({"q1": [Outcome.CORRECT]}),
        results({"q1": [Outcome.FALSE_CONFIDENCE]}),
        resamples=1000,
        seed=41,
    )

    assert comparison.metrics["accuracy"].moved is None


def test_the_pairing_cancels_examples_being_harder_than_others() -> None:
    """Half the examples are never answered on either side, and the rest all improve.

    Unpaired, the two point estimates differ by the same amount; paired, the interval is over
    the change alone and excludes zero.
    """
    hard = {f"h{i}": [Outcome.MISSED] * 3 for i in range(1, 11)}
    before = {**hard, **{f"e{i}": [Outcome.MISSED] * 3 for i in range(1, 11)}}
    after = {**hard, **{f"e{i}": [Outcome.CORRECT] * 3 for i in range(1, 11)}}

    comparison = compare(results(before), results(after), resamples=1000, seed=41)

    change = comparison.metrics["accuracy"]
    assert change.delta == pytest.approx(0.5)
    assert change.moved is True
    assert change.difference.low > 0.0


def test_false_confidence_and_recall_move_independently() -> None:
    """An agent that stops abstaining trades recall for false confidence, and both are named."""
    before = {f"q{i}": [Outcome.MISSED] for i in range(1, 21)}
    after = {
        **{f"q{i}": [Outcome.CORRECT] for i in range(1, 11)},
        **{f"q{i}": [Outcome.FALSE_CONFIDENCE] for i in range(11, 21)},
    }

    comparison = compare(results(before), results(after), resamples=500, seed=41)

    assert comparison.metrics["recall"].delta == pytest.approx(0.5)
    assert comparison.metrics["false_confidence_rate"].delta == pytest.approx(0.5)
    assert comparison.metrics["abstention_rate"].delta == pytest.approx(-1.0)


# -- what the difference is attributed to -------------------------------------------------


def test_what_changed_in_the_configuration_is_named() -> None:
    before = results(
        flat(Outcome.CORRECT, 10, 2),
        config={"prompts": {"hunt": {"version": "sha256:aaa"}}, "k": 2},
    )
    after = results(
        flat(Outcome.FALSE_CONFIDENCE, 10, 2),
        config={"prompts": {"hunt": {"version": "sha256:bbb"}}, "k": 2},
    )

    comparison = compare(before, after, resamples=500, seed=41)

    assert comparison.changed["prompts.hunt.version"] == ["sha256:aaa", "sha256:bbb"]
    assert "k" not in comparison.changed


def test_a_metric_with_no_shared_denominator_carries_no_verdict() -> None:
    """Nothing was asserted on either side, so there is no precision to compare and no
    claim that it did not move."""
    before = results(flat(Outcome.MISSED, 6, 2))
    after = results(flat(Outcome.MISSED, 6, 2))

    comparison = compare(before, after, resamples=200, seed=41)
    change = comparison.metrics["precision_when_asserting"]

    assert change.difference is None
    assert change.moved is None
    assert "nothing to pair" in change.reason
    assert "precision_when_asserting" in comparison.undecided


def test_a_metric_covering_different_examples_on_each_side_says_so() -> None:
    """`precision_when_asserting` is over what the agent asserted, which the agent changed.

    Measured on dogfood #1: the point estimate rose 0.385 to 0.474 while every example under
    the metric on both sides moved by nothing, because the seven that left the denominator
    were the ones scoring zero.
    """
    before = results({"e1": [Outcome.CORRECT], "e2": [Outcome.FALSE_CONFIDENCE]})
    after = results({"e1": [Outcome.CORRECT], "e2": [Outcome.MISSED]})

    change = compare(before, after, resamples=200, seed=41).metrics["precision_when_asserting"]

    assert (change.before, change.after) == (0.5, 1.0)
    assert (change.before_examples, change.after_examples, change.examples) == (2, 1, 1)
    assert change.difference.point == 0.0
    assert "covered 2 of the shared examples" in change.population_note


def test_the_report_prints_the_population_note_without_being_asked() -> None:
    """Dogfood #1 run 2 wrote its own printer and left the note out of it."""
    before = results({"e1": [Outcome.CORRECT], "e2": [Outcome.FALSE_CONFIDENCE]})
    after = results({"e1": [Outcome.CORRECT], "e2": [Outcome.MISSED]})

    printed = compare(before, after, resamples=200, seed=41).report()

    assert "covered 2 of the shared examples" in printed
    assert "precision_when_asserting" in printed
    assert "verdict" in printed


def test_the_report_carries_an_interval_beside_every_point_estimate() -> None:
    """No line of it can be quoted as a bare change (FT-06)."""
    before = results(flat(Outcome.CORRECT, 4, 2))
    after = results(flat(Outcome.MISSED, 4, 2))

    printed = compare(before, after, resamples=200, seed=41).report()

    for line in printed.splitlines():
        if line.startswith("  accuracy"):
            assert "[" in line and "]" in line


def test_a_metric_whose_denominator_is_the_label_reports_no_population_note() -> None:
    """`recall` is over examples where a value exists, which the agent cannot change."""
    before = results(flat(Outcome.CORRECT, 4, 2))
    after = results(flat(Outcome.MISSED, 4, 2))

    comparison = compare(before, after, resamples=200, seed=41)

    assert comparison.metrics["recall"].population_note is None
    assert "recall" not in comparison.population_changed


def test_the_record_carries_the_interval_and_what_moved() -> None:
    comparison = compare(
        results(flat(Outcome.CORRECT, 24, 2)),
        results(flat(Outcome.MISSED, 24, 2)),
        resamples=500,
        seed=41,
    )

    record = comparison.to_record()

    assert record["shared_examples"] == 24
    assert "accuracy" in record["moved"]
    assert record["metrics"]["accuracy"]["difference"]["method"].endswith(
        "on the paired difference"
    )


# -- refusals -----------------------------------------------------------------------------


def test_two_different_example_sets_are_refused() -> None:
    before = results(flat(Outcome.CORRECT, 5, 2), content_hash="ex_one")
    after = results(flat(Outcome.CORRECT, 5, 2), content_hash="ex_two")

    with pytest.raises(ConfigurationError) as raised:
        compare(before, after)

    assert "different example sets" in str(raised.value)
    assert "allow_different_sets=True" in str(raised.value)


def test_different_sets_may_be_compared_on_their_shared_examples_when_asked() -> None:
    before = results(flat(Outcome.CORRECT, 5, 2), content_hash="ex_one")
    after = results(
        {**flat(Outcome.CORRECT, 5, 2), "q9": [Outcome.MISSED] * 2}, content_hash="ex_two"
    )

    comparison = compare(before, after, allow_different_sets=True, resamples=200, seed=41)

    assert len(comparison.shared) == 5
    assert comparison.only_after == ("q9",)
    assert comparison.only_before == ()


def test_two_evaluations_sharing_no_example_are_refused() -> None:
    before = results(flat(Outcome.CORRECT, 3, 2, start=1), content_hash="ex_one")
    after = results(flat(Outcome.CORRECT, 3, 2, start=90), content_hash="ex_two")

    with pytest.raises(ConfigurationError) as raised:
        compare(before, after, allow_different_sets=True)

    assert "share no examples" in str(raised.value)
    assert "nothing to pair" in str(raised.value)


# -- per node -----------------------------------------------------------------------------


def with_nodes(reach: dict[str, list[bool]], matched: dict[str, list] | None = None) -> EvalResults:
    """A results object whose rollouts carry per-node observations for one node, `verify`."""
    matched = matched or {}
    rollouts = tuple(
        RolloutOutcome(
            example_id=example_id,
            rollout=index,
            seed=100 + index,
            outcome=Outcome.CORRECT,
            nodes={
                "verify": NodeObservation(
                    reached=ran,
                    matched=(matched.get(example_id) or [None] * len(sequence))[index],
                )
            },
        )
        for example_id, sequence in reach.items()
        for index, ran in enumerate(sequence)
    )
    nodes = {"verify": NodeMetrics(node_id="verify", node_kind="llm")}
    node_rates(nodes, rollouts, resamples=200, seed=41)
    return EvalResults(
        eval_id="eval_test",
        created_at="2026-07-29T09:00:00.000Z",
        config={"example_set": {"content_hash": "ex_fixed"}},
        metrics=aggregate(rollouts, dict.fromkeys(reach, False), resamples=200, seed=41),
        nodes=nodes,
        rollouts=rollouts,
        examples={e: {"split": "held_out", "expects_absence": False} for e in reach},
    )


def test_a_node_that_stopped_being_reached_reports_a_moved_reach() -> None:
    before = with_nodes({f"q{i}": [True, True] for i in range(1, 22)})
    after = with_nodes({f"q{i}": [False, False] for i in range(1, 22)})

    comparison = compare(before, after, resamples=400, seed=41)

    assert comparison.moved_nodes == ["verify"]
    assert comparison.nodes["verify"].reach.moved is True
    assert comparison.nodes["verify"].reach.delta == pytest.approx(-1.0)


def test_a_node_reached_as_often_reports_nothing_moved() -> None:
    reach = {f"q{i}": [True, False] for i in range(1, 22)}

    comparison = compare(with_nodes(reach), with_nodes(reach), resamples=400, seed=41)

    assert comparison.moved_nodes == []
    assert comparison.nodes["verify"].reach.moved is False


def test_reach_is_reported_beside_accuracy_so_a_moved_number_has_a_named_cause() -> None:
    """`verify` is as right as it was, on half the rollouts. Only reach moved."""
    reached_everywhere = {f"q{i}": [True, True] for i in range(1, 22)}
    reached_half = {f"q{i}": [True, False] for i in range(1, 22)}
    right = {f"q{i}": [True, True] for i in range(1, 22)}
    right_where_reached = {f"q{i}": [True, None] for i in range(1, 22)}

    comparison = compare(
        with_nodes(reached_everywhere, right),
        with_nodes(reached_half, right_where_reached),
        resamples=400,
        seed=41,
    )

    change = comparison.nodes["verify"]
    assert change.reach.moved is True
    assert change.accuracy is not None
    assert change.accuracy.moved is False
    assert change.accuracy.before == pytest.approx(1.0)
    assert change.accuracy.after == pytest.approx(1.0)


def test_the_record_carries_the_per_node_changes() -> None:
    before = with_nodes({f"q{i}": [True, True] for i in range(1, 22)})
    after = with_nodes({f"q{i}": [False, False] for i in range(1, 22)})

    record = compare(before, after, resamples=400, seed=41).to_record()

    assert record["moved_nodes"] == ["verify"]
    assert record["nodes"]["verify"]["reach"]["moved"] is True
    assert record["nodes"]["verify"]["accuracy"] is None


class TestWhatAWrittenComparisonHolds:
    """Every figure it computed. `criteria` and `groups` were computed and then dropped on write.

    A project with a decomposed answer key read per-criterion movement off the object and found
    none of it in the file, and `docs/evaluation.md` §10.4 called it "the full comparison
    record".
    """

    def test_it_carries_its_own_format_version(self) -> None:
        from simple_agents.evaluation.compare import COMPARISON_FORMAT_VERSION, Comparison

        record = Comparison(
            metrics={}, shared=(), only_before=(), only_after=(), changed={}
        ).to_record()
        assert record["comparison_format_version"] == COMPARISON_FORMAT_VERSION

    def test_it_carries_the_criteria_and_the_grouped_cells(self) -> None:
        from simple_agents.evaluation.compare import Comparison

        record = Comparison(
            metrics={}, shared=(), only_before=(), only_after=(), changed={}
        ).to_record()
        assert "criteria" in record
        assert "moved_criteria" in record
        assert "groups" in record
