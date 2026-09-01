"""Bootstrap intervals, checked against sets whose right answer the test already knows.

The test that matters is `test_correlated_rollouts_widen_the_interval`. Everything else here
verifies the code; that one verifies the method, because an interval computed over rollouts
rather than examples looks exactly as authoritative as a correct one.
"""

from __future__ import annotations

import random

import pytest

from simple_agents import ConfigurationError
from simple_agents.evaluation.intervals import bootstrap_ci, wilson_ci


def naive_ci(flat: list[float], *, resamples: int, seed: int, confidence: float = 0.95):
    """A bootstrap that treats every rollout as its own independent observation.

    Written here rather than shipped, because it is the mistake `bootstrap_ci`'s signature
    exists to make unavailable.
    """
    rng = random.Random(seed)
    size = len(flat)
    estimates = sorted(
        sum(flat[rng.randrange(size)] for _ in range(size)) / size for _ in range(resamples)
    )
    tail = (1.0 - confidence) / 2.0
    return estimates[int(tail * resamples)], estimates[int((1.0 - tail) * resamples) - 1]


# -- the one that proves the method -------------------------------------------------------


def test_correlated_rollouts_widen_the_interval() -> None:
    """Twenty examples, each answered the same way on all five rollouts.

    There are 20 independent observations here, not 100. A bootstrap over the 100 rollouts
    reports an interval about sqrt(5) too narrow, and nothing about the number says so.
    """
    by_example = [[1.0] * 5 if i % 2 == 0 else [0.0] * 5 for i in range(20)]
    flat = [score for rollouts in by_example for score in rollouts]

    clustered = bootstrap_ci(by_example, resamples=2000, seed=41)
    low, high = naive_ci(flat, resamples=2000, seed=41)

    assert clustered.point == pytest.approx(0.5)
    assert (low + high) / 2 == pytest.approx(0.5, abs=0.05)
    assert clustered.width > (high - low) * 1.8


def test_independent_rollouts_do_not_widen_it_much() -> None:
    """The correction is a property of the data, not a constant the library adds.

    Where rollouts within an example vary as much as examples do, clustering and not
    clustering agree closely.
    """
    rng = random.Random(7)
    by_example = [[float(rng.random() < 0.5) for _ in range(5)] for _ in range(60)]
    flat = [score for rollouts in by_example for score in rollouts]

    clustered = bootstrap_ci(by_example, resamples=2000, seed=41)
    low, high = naive_ci(flat, resamples=2000, seed=41)

    assert clustered.width < (high - low) * 1.5


# -- coverage -----------------------------------------------------------------------------


def test_the_interval_covers_the_proportion_it_was_drawn_from() -> None:
    """Nominal 95% intervals over sets drawn from a known proportion, at a fixed seed."""
    truth = 0.6
    rng = random.Random(2026)
    covered = 0
    trials = 150

    for trial in range(trials):
        by_example = [[float(rng.random() < truth)] for _ in range(40)]
        interval = bootstrap_ci(by_example, resamples=300, seed=trial)
        covered += interval.low <= truth <= interval.high

    assert covered / trials >= 0.88, f"covered {covered} of {trials}"


def test_the_width_is_near_the_analytic_one_for_a_known_proportion() -> None:
    """At p=0.5 over n examples the 95% half-width is about 1.96 * sqrt(p(1-p)/n)."""
    by_example = [[1.0] if i % 2 == 0 else [0.0] for i in range(400)]

    interval = bootstrap_ci(by_example, resamples=2000, seed=41)

    analytic = 2 * 1.96 * (0.25 / 400) ** 0.5
    assert interval.width == pytest.approx(analytic, rel=0.15)


# -- properties ---------------------------------------------------------------------------


def test_the_same_seed_gives_the_same_interval_and_a_different_one_does_not() -> None:
    # Distinct per-example means, so the resampled estimates are dense enough that two seeds
    # land on different percentiles. Coarse data can give two seeds the same endpoints.
    by_example = [[i / 30.0] * 4 for i in range(30)]

    first = bootstrap_ci(by_example, resamples=500, seed=41)
    again = bootstrap_ci(by_example, resamples=500, seed=41)
    other = bootstrap_ci(by_example, resamples=500, seed=42)

    assert (first.low, first.high) == (again.low, again.high)
    assert (first.low, first.high) != (other.low, other.high)
    assert first.seed == 41


def test_a_set_where_every_example_scored_the_same_does_not_claim_certainty() -> None:
    """Resampling identical values reads as zero width, which asserts what n cannot support.

    This asserted `width == 0.0` until a project reported four of four hand labels as
    [1.000, 1.000], which is a claim of certainty from four judgements (FT-06).
    """
    interval = bootstrap_ci([[1.0, 1.0]] * 12, resamples=200, seed=41)

    assert interval.point == 1.0
    assert interval.width > 0.0
    assert interval.low < 1.0
    assert interval.high == 1.0
    assert "Wilson" in interval.method


def test_an_agent_that_never_succeeded_does_not_report_a_certain_zero() -> None:
    interval = bootstrap_ci([[0.0]] * 30, resamples=200, seed=41)

    assert interval.point == 0.0
    assert interval.low == 0.0
    assert interval.high > 0.0


def test_a_set_with_variation_is_still_the_percentile_bootstrap() -> None:
    interval = bootstrap_ci([[1.0]] * 29 + [[0.0]], resamples=2000, seed=41)

    assert "resampling examples" in interval.method


def test_every_example_counts_once_whatever_k_it_ran_at() -> None:
    """One example run 100 times does not outvote ninety-nine run once."""
    by_example = [[0.0] * 100] + [[1.0] for _ in range(99)]

    interval = bootstrap_ci(by_example, resamples=500, seed=41)

    assert interval.point == pytest.approx(0.99)
    assert interval.k is None


def test_k_is_reported_when_every_example_ran_the_same_number_of_times() -> None:
    interval = bootstrap_ci([[1.0, 0.0, 1.0] for _ in range(10)], resamples=200, seed=41)

    assert interval.k == 3
    assert interval.n == 10


def test_the_record_carries_what_the_interval_was_computed_from() -> None:
    record = bootstrap_ci([[1.0], [0.0], [1.0]], resamples=200, seed=41).to_record()

    assert set(record) == {
        "point",
        "low",
        "high",
        "n",
        "k",
        "confidence",
        "resamples",
        "seed",
        "method",
    }
    assert record["resamples"] == 200
    assert "resampling examples" in record["method"]


def test_excludes_answers_whether_a_difference_moved():
    by_example = [[1.0] for _ in range(40)]

    interval = bootstrap_ci(by_example, resamples=200, seed=41)

    assert interval.excludes(0.0) is True
    assert interval.excludes(1.0) is False


# -- refusals -----------------------------------------------------------------------------


def test_an_empty_set_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        bootstrap_ci([])

    assert "no measurement" in str(raised.value)


def test_an_example_with_no_rollouts_is_refused_rather_than_scored_zero() -> None:
    with pytest.raises(ConfigurationError) as raised:
        bootstrap_ci([[1.0], [], [0.0]])

    assert "index 1" in str(raised.value)
    assert "never given the chance" in str(raised.value)


def test_too_few_resamples_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        bootstrap_ci([[1.0], [0.0]], resamples=20)

    assert "below 100" in str(raised.value)


def test_a_confidence_outside_zero_to_one_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        bootstrap_ci([[1.0], [0.0]], confidence=95)

    assert "between 0 and 1" in str(raised.value)


# -- wilson_ci ----------------------------------------------------------------------------


def test_wilson_reports_an_interval_where_a_bare_proportion_reports_certainty() -> None:
    """Four of four judged correct. The rate could be anywhere above about half."""
    interval = wilson_ci(4, 4)

    assert interval.point == 1.0
    assert interval.low == pytest.approx(0.51, abs=0.01)
    assert interval.high == 1.0
    assert interval.n == 4
    assert interval.k is None


def test_wilson_narrows_as_the_count_grows_at_the_same_rate() -> None:
    widths = [wilson_ci(n, n).width for n in (4, 10, 20, 50)]

    assert widths == sorted(widths, reverse=True)


def test_wilson_never_runs_outside_zero_to_one() -> None:
    for successes, n in ((0, 1), (0, 5), (1, 1), (5, 5), (3, 7)):
        interval = wilson_ci(successes, n)
        assert 0.0 <= interval.low <= interval.point <= interval.high <= 1.0


def test_wilson_records_which_calculation_produced_it() -> None:
    record = wilson_ci(37, 50).to_record()

    assert record["method"] == "Wilson score interval on a proportion"
    assert record["resamples"] == 0
    assert record["low"] == pytest.approx(0.604, abs=0.001)
    assert record["high"] == pytest.approx(0.841, abs=0.001)


def test_wilson_refuses_no_tries() -> None:
    with pytest.raises(ConfigurationError) as raised:
        wilson_ci(0, 0)

    assert "no tries" in str(raised.value)


def test_wilson_refuses_more_successes_than_tries() -> None:
    with pytest.raises(ConfigurationError) as raised:
        wilson_ci(5, 4)

    assert "more successes than tries" in str(raised.value)
