"""Confidence intervals over k rollouts of n examples, and over a count of judgements.

A metric reported as a bare percentage hides its own sample size, so 87% over 15 examples reads
identically to 87% over 1,500 and invites version comparisons the data cannot support (FT-06).

**The resampling unit is the example, not the rollout.** Two rollouts of one example are two
samples of the same question and move together, so resampling k×n rollouts as though they were
k×n independent observations produces an interval narrower than the data supports. The narrowing
grows with k, and nothing about the reported number reveals it. :func:`bootstrap_ci` therefore
takes the rollouts grouped by example and cannot be handed a flat list by accident.

Two functions, and which one to reach for::

    bootstrap_ci([[1, 1, 0], [0, 0, 0]])   # scores from rollouts the agent ran
    wilson_ci(4, 4)                        # judgements made by hand, no rollouts

A set where every example scored the same gives a resampling method nothing to read: every
resample draws the same value, both percentile endpoints land on it, and the interval comes
back zero width, so 30 of 30 correct would report the true rate as certainly 100%. Where those
identical scores are 0 or 1 the quantity is a proportion, so :func:`bootstrap_ci` returns
Wilson's interval instead and records that in ``method``. A set whose scores are all identical
and not 0 or 1, including a paired difference that is zero on every example, still reports zero
width, and that means the sample holds no variation rather than that the value is certain.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Any, Sequence

from ..errors import ConfigurationError

__all__ = [
    "Interval",
    "bootstrap_ci",
    "ratio_ci",
    "paired_ratio_ci",
    "wilson_ci",
    "rollout_noise",
    "MIN_RESAMPLES",
]

# Below this the percentile the interval is read at falls between too few resampled values for
# the endpoints to mean anything, and the interval varies run to run more than the data does.
MIN_RESAMPLES = 100

DEFAULT_RESAMPLES = 2000
DEFAULT_CONFIDENCE = 0.95
METHOD = "percentile bootstrap, resampling examples"
WILSON_METHOD = "Wilson score interval on a proportion"
RATIO_METHOD = "percentile bootstrap on a ratio of totals, resampling examples"
PAIRED_RATIO_METHOD = "percentile bootstrap on the difference of two ratios, resampling examples"
POOLED_WILSON_METHOD = "Wilson score interval on the pooled counts"


@dataclass(frozen=True, slots=True)
class Interval:
    """A metric, the range the data supports for it, and what that range was computed from.

    ``point`` is the estimate: the mean over examples of each example's mean over its rollouts,
    so every example counts once whatever k it was run at. ``low`` and ``high`` are its
    endpoints::

        interval.point       # 0.65
        interval.low         # 0.48
        interval.high        # 0.80
        interval.n           # 20 examples, which is what was resampled
        interval.k           # 5 rollouts each, or None when it varied
        interval.method      # which calculation produced the endpoints

    A wide interval is a finding about the sample size rather than a reason to drop the
    interval.

    ``method`` names how the endpoints were computed, because two calculations produce them.
    ``resamples`` and ``seed`` describe the resampling and are ``0`` where none happened.
    """

    point: float
    low: float
    high: float
    n: int
    k: int | None
    confidence: float
    resamples: int
    seed: int
    method: str = METHOD

    @property
    def width(self) -> float:
        return self.high - self.low

    def excludes(self, value: float) -> bool:
        """Whether ``value`` falls outside the interval.

        ``interval.excludes(0)`` on a difference between two versions is the question of
        whether the change moved the metric by more than the sampling supports.
        """
        return value < self.low or value > self.high

    def to_record(self) -> dict[str, Any]:
        """What a results file stores. Every key always present."""
        return {
            "point": self.point,
            "low": self.low,
            "high": self.high,
            "n": self.n,
            "k": self.k,
            "confidence": self.confidence,
            "resamples": self.resamples,
            "seed": self.seed,
            "method": self.method,
        }

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> Interval:
        """Rebuild an interval from a results file."""
        return cls(
            point=float(raw["point"]),
            low=float(raw["low"]),
            high=float(raw["high"]),
            n=int(raw["n"]),
            k=None if raw.get("k") is None else int(raw["k"]),
            confidence=float(raw["confidence"]),
            resamples=int(raw["resamples"]),
            seed=int(raw["seed"]),
            method=str(raw.get("method", METHOD)),
        )


def bootstrap_ci(
    by_example: Sequence[Sequence[float]],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> Interval:
    """A confidence interval for a metric measured over k rollouts of each of n examples.

    ``by_example`` holds one inner sequence per example, containing that example's score on
    each rollout. Scores are usually 1 and 0 for a rollout that was correct and one that was
    not, and any numbers work::

        bootstrap_ci([[1, 1, 0], [0, 0, 0], [1, 1, 1]], seed=41)

    Examples are resampled with replacement, the rollouts inside an example travel together,
    and the interval is read off the percentiles of the resampled estimates. ``seed`` makes
    the interval reproducible and is recorded on it.

    Raises :class:`~simple_agents.errors.ConfigurationError` for an empty set, an example with
    no rollouts, or a resample count too small for the endpoints to mean anything.
    """
    outer = list(by_example)
    _refuse_unusable(outer, confidence=confidence, resamples=resamples)
    grouped = [list(rollouts) for rollouts in outer]

    per_example = [sum(rollouts) / len(rollouts) for rollouts in grouped]
    n = len(per_example)
    counts = {len(rollouts) for rollouts in grouped}

    k = counts.pop() if len(counts) == 1 else None

    if set(per_example) <= {0.0, 1.0} and len(set(per_example)) == 1:
        # Every example scored the same, and that score is 0 or 1. Resampling draws the same
        # value however many times it runs, so the percentile endpoints both land on it and the
        # interval reads as zero width: 30 of 30 correct would report [1.000, 1.000]. The
        # quantity is a proportion over n examples, so the interval that answers it is Wilson's.
        return replace(
            wilson_ci(int(sum(per_example)), n, confidence=confidence),
            k=k,
            resamples=resamples,
            seed=seed,
        )

    rng = random.Random(seed)
    estimates = [sum(per_example[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)]
    low, high = _percentiles(estimates, confidence)

    return Interval(
        point=sum(per_example) / n,
        low=low,
        high=high,
        n=n,
        k=k,
        confidence=confidence,
        resamples=resamples,
        seed=seed,
    )


def paired_ratio_ci(
    before: Sequence[Sequence[tuple[float, float]]],
    after: Sequence[Sequence[tuple[float, float]]],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> Interval:
    """A confidence interval for how far one ratio moved from another, over the same examples.

    ``before`` and ``after`` hold one inner sequence per example, aligned so that index i is
    the same example on both sides. Each resample draws examples once and reads both arms on
    the draw, so an example that is simply hard cancels::

        paired_ratio_ci([[(1, 10)], [(1, 2)]], [[(3, 10)], [(1, 2)]])   # 4/12 - 2/12

    The point estimate is the difference of the two pooled ratios. The mean over examples of
    each example's own difference is a different quantity, for the reason :func:`ratio_ci`
    gives.

    Raises :class:`~simple_agents.errors.ConfigurationError` where the two sides are different
    lengths, and for anything :func:`ratio_ci` refuses.
    """
    left, right = _aligned(before, after, confidence=confidence, resamples=resamples)
    paired = [(_totals(a), _totals(b)) for a, b in zip(left, right)]
    n = len(paired)
    point = _difference(paired, range(n))

    rng = random.Random(seed)
    estimates = []
    for _ in range(resamples):
        drawn = [rng.randrange(n) for _ in range(n)]
        value = _difference(paired, drawn)
        if value is not None:
            estimates.append(value)
    if point is None or len(estimates) < MIN_RESAMPLES:
        raise ConfigurationError(
            f"paired_ratio_ci could not take a difference: {len(estimates)} of {resamples} "
            f"resamples had a denominator on both sides, and the whole set "
            f"{'did' if point is not None else 'did not'}.\n"
            f"A figure one arm never counted has nothing to pair against. Compare the arms "
            f"that both report it."
        )
    low, high = _percentiles(estimates, confidence)
    counts = {len(rollouts) for rollouts in left} | {len(rollouts) for rollouts in right}
    return Interval(
        point=point,
        low=low,
        high=high,
        n=n,
        k=counts.pop() if len(counts) == 1 else None,
        confidence=confidence,
        resamples=resamples,
        seed=seed,
        method=PAIRED_RATIO_METHOD,
    )


def _totals(rollouts: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """One example's two sums."""
    return (sum(n for n, _ in rollouts), sum(d for _, d in rollouts))


def _aligned(
    before: Sequence[Sequence[tuple[float, float]]],
    after: Sequence[Sequence[tuple[float, float]]],
    *,
    confidence: float,
    resamples: int,
) -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]]:
    """The two arms as lists, refused unless they line up and each is usable on its own."""
    left = [list(rollouts) for rollouts in before]
    right = [list(rollouts) for rollouts in after]
    if len(left) != len(right):
        raise ConfigurationError(
            f"paired_ratio_ci was given {len(left)} example(s) before and {len(right)} after. "
            f"A paired difference reads both arms on the same example, so the two sides line "
            f"up index by index.\n"
            f"Pass the shared examples, in one order, from both evaluations."
        )
    _refuse_unusable_pairs(left, confidence=confidence, resamples=resamples)
    _refuse_unusable_pairs(right, confidence=confidence, resamples=resamples)
    return left, right


def _difference(
    paired: Sequence[tuple[tuple[float, float], tuple[float, float]]],
    drawn: Any,
) -> float | None:
    """The two pooled ratios over one draw of examples, subtracted, or ``None`` if undefined."""
    before_n = before_d = after_n = after_d = 0.0
    for index in drawn:
        (bn, bd), (an, ad) = paired[index]
        before_n += bn
        before_d += bd
        after_n += an
        after_d += ad
    if before_d <= 0 or after_d <= 0:
        return None
    return after_n / after_d - before_n / before_d


def wilson_ci(successes: int, n: int, *, confidence: float = DEFAULT_CONFIDENCE) -> Interval:
    """A confidence interval for a proportion: ``successes`` out of ``n`` tries.

    Reach for this where each example is judged right or wrong once and there are no rollouts
    to resample, which is what hand labelling produces::

        wilson_ci(4, 4)      # point 1.0, interval 0.51 to 1.0
        wilson_ci(37, 50)    # point 0.74, interval 0.60 to 0.84

    ``bootstrap_ci`` is for a metric measured over k rollouts of each of n examples, and is
    what an ``EvalSuite`` reports. This one takes two counts, so it needs no rollouts, no seed
    and no resampling.

    The interval never runs outside 0 to 1 and never reads as zero width, including at
    ``successes == n``, where a bare proportion would say 100% and a percentile bootstrap would
    say the true rate is certainly 100%.

    Raises :class:`~simple_agents.errors.ConfigurationError` for ``n`` of zero, a negative
    count, more successes than tries, or a confidence outside 0 to 1.
    """
    if n <= 0:
        raise ConfigurationError(
            f"wilson_ci(successes={successes}, n={n}) was given no tries. A proportion over "
            f"nothing is not a wide interval, it is no measurement.\n"
            f"Pass the number judged: wilson_ci(4, 4)."
        )
    if successes < 0 or successes > n:
        raise ConfigurationError(
            f"wilson_ci(successes={successes}, n={n}) counts more successes than tries, or a "
            f"negative number of them. `successes` is how many of the `n` were correct.\n"
            f"Pass wilson_ci(4, 4) for four of four."
        )
    if not 0.0 < confidence < 1.0:
        raise ConfigurationError(
            f"wilson_ci(confidence={confidence}) takes a fraction between 0 and 1, exclusive. "
            f"Pass confidence=0.95 for the conventional interval."
        )

    z = _z_for(confidence)
    p = successes / n
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    spread = z * math.sqrt(p * (1.0 - p) / n + z * z / (4 * n * n)) / denominator
    # At p of 0 and 1 the algebra puts an endpoint exactly on the bound and floating point puts
    # it a fraction inside, which would report an unbeaten agent as not quite reaching 1.0.
    low = 0.0 if successes == 0 else max(0.0, centre - spread)
    high = 1.0 if successes == n else min(1.0, centre + spread)
    return Interval(
        point=p,
        low=low,
        high=high,
        n=n,
        k=None,
        confidence=confidence,
        resamples=0,
        seed=0,
        method=WILSON_METHOD,
    )


def ratio_ci(
    by_example: Sequence[Sequence[tuple[float, float]]],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> Interval:
    """A confidence interval for a ratio of two totals, resampling examples.

    ``by_example`` holds one inner sequence per example, containing that example's
    ``(numerator, denominator)`` on each rollout. The point estimate is every numerator summed
    over every denominator summed::

        ratio_ci([[(1, 10)], [(1, 2)]])      # 2 / 12, and not the mean of 0.1 and 0.5

    Reach for this where the thing counted is not the rollout: picks inside an answer, pages a
    run read, pairs a judge decided. :func:`bootstrap_ci` is the figure where each example
    counts once whatever it returned.

    Examples are resampled with replacement and both sums are taken inside each resample, so k
    rollouts of one example travel together. A ratio of 0 or 1 is Wilson's on the pooled counts
    instead, and ``method`` says which calculation produced the endpoints.

    Raises :class:`~simple_agents.errors.ConfigurationError` for an empty set, an example with
    no rollouts, a pair that is not two numbers, a negative denominator, a summed denominator
    of zero, or a resample count too small for the endpoints to mean anything.
    """
    # Validated before anything is converted: a flat sequence is what the guard exists to name,
    # and converting it first raises TypeError from inside a comprehension instead.
    _refuse_unusable_pairs(list(by_example), confidence=confidence, resamples=resamples)
    outer = [list(rollouts) for rollouts in by_example]

    per_example = [(sum(n for n, _ in rollouts), sum(d for _, d in rollouts)) for rollouts in outer]
    counts = {len(rollouts) for rollouts in outer}
    k = counts.pop() if len(counts) == 1 else None
    total_numerator = sum(num for num, _ in per_example)
    total_denominator = sum(den for _, den in per_example)
    if total_denominator <= 0:
        raise ConfigurationError(
            f"ratio_ci was given {len(per_example)} example(s) whose denominators sum to "
            f"{total_denominator:g}. A ratio over nothing is not a wide interval, it is no "
            f"measurement.\n"
            f"A figure whose denominator can be empty reports no value and says why, which is "
            f"what a metric does with an empty denominator. Check what the denominator counts: "
            f"ratio_ci([[(1, 10)], [(1, 2)]])."
        )

    pooled = _pooled(total_numerator, total_denominator, confidence=confidence)
    if pooled is not None:
        return replace(pooled, k=k, resamples=resamples, seed=seed, method=POOLED_WILSON_METHOD)

    estimates = _resampled_ratios(per_example, resamples=resamples, seed=seed)
    low, high = _percentiles(estimates, confidence)
    return Interval(
        point=total_numerator / total_denominator,
        low=low,
        high=high,
        n=len(per_example),
        k=k,
        confidence=confidence,
        resamples=resamples,
        seed=seed,
        method=RATIO_METHOD,
    )


def _pooled(numerator: float, denominator: float, *, confidence: float) -> Interval | None:
    """Wilson's on the two totals where the ratio sits on a bound, and ``None`` otherwise.

    At 0 or 1 every resample draws the same value, so both percentile endpoints land on it and
    the interval reads as zero width: 0 of 673 would report the true rate as certainly zero.
    """
    if numerator / denominator not in (0.0, 1.0):
        return None
    whole = float(numerator).is_integer() and float(denominator).is_integer()
    if not whole or not 0 <= numerator <= denominator:
        return None
    return wilson_ci(int(numerator), int(denominator), confidence=confidence)


def _resampled_ratios(
    per_example: Sequence[tuple[float, float]], *, resamples: int, seed: int
) -> list[float]:
    """One ratio per resample, drawing examples with replacement and summing both sides.

    A resample that drew only examples contributing nothing to the denominator has no ratio and
    is left out, so a set where that is common has too few to read percentiles off.
    """
    rng = random.Random(seed)
    n = len(per_example)
    estimates: list[float] = []
    for _ in range(resamples):
        drawn_numerator = 0.0
        drawn_denominator = 0.0
        for _ in range(n):
            num, den = per_example[rng.randrange(n)]
            drawn_numerator += num
            drawn_denominator += den
        if drawn_denominator > 0:
            estimates.append(drawn_numerator / drawn_denominator)
    if len(estimates) < MIN_RESAMPLES:
        raise ConfigurationError(
            f"ratio_ci drew {len(estimates)} usable resample(s) out of {resamples}: the rest "
            f"drew only examples whose denominators are zero, so no ratio could be taken over "
            f"them.\n"
            f"Most of this set contributes nothing to the denominator. Report the figure over "
            f"the examples that do, or raise resamples above {DEFAULT_RESAMPLES}."
        )
    return estimates


def _refuse_unusable_pairs(grouped: list[Any], *, confidence: float, resamples: int) -> None:
    """The same guards as a mean, over pairs, and the messages name ``ratio_ci``."""
    if not grouped:
        raise ConfigurationError(
            "ratio_ci was given no examples. An interval over nothing is not a wide interval, "
            "it is no measurement. Pass one inner sequence per example, holding that example's "
            "(numerator, denominator) on each rollout."
        )
    for index, rollouts in enumerate(grouped):
        _refuse_unusable_example(rollouts, index)
    if not 0.0 < confidence < 1.0:
        raise ConfigurationError(
            f"ratio_ci(confidence={confidence}) takes a fraction between 0 and 1, exclusive. "
            f"Pass confidence=0.95 for the conventional interval."
        )
    if resamples < MIN_RESAMPLES:
        raise ConfigurationError(
            f"ratio_ci(resamples={resamples}) is below {MIN_RESAMPLES}. The endpoints are "
            f"percentiles of the resampled estimates, so too few of them makes the interval "
            f"vary between runs more than the data does.\n"
            f"Pass resamples={DEFAULT_RESAMPLES}, which is the default, or higher."
        )


def _refuse_unusable_example(rollouts: Any, index: int) -> None:
    """One example's pairs: that it is a group, that it ran, and that each pair is two numbers."""
    if not isinstance(rollouts, (list, tuple)):
        raise ConfigurationError(
            f"ratio_ci was given a flat sequence: index {index} holds {rollouts!r} rather than "
            f"one example's rollouts. Resampling those as though each were an independent "
            f"observation produces an interval narrower than the data supports.\n"
            f"Group them by example: ratio_ci([[(1, 10)], [(1, 2)]])."
        )
    if not rollouts:
        raise ConfigurationError(
            f"ratio_ci was given an example with no rollouts, at index {index}. An example that "
            f"was never run has no counts, and counting it as zero would report a failure the "
            f"agent was never given the chance to have.\n"
            f"Drop the examples that did not run, or run them."
        )
    for pair in rollouts:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ConfigurationError(
                f"ratio_ci was given {pair!r} at example index {index}. Each rollout "
                f"contributes two numbers, the numerator and the denominator it adds to the "
                f"totals.\n"
                f"Pass pairs: ratio_ci([[(1, 10)], [(1, 2)]])."
            )
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in pair):
            raise ConfigurationError(
                f"ratio_ci was given {pair!r} at example index {index}, which is not two "
                f"numbers. A numerator and a denominator are counts or amounts.\n"
                f"Pass numbers: ratio_ci([[(1, 10)], [(1, 2)]])."
            )
        if pair[1] < 0:
            raise ConfigurationError(
                f"ratio_ci was given a negative denominator, {pair[1]!r}, at example index "
                f"{index}. A denominator counts what the numerator is out of, so it cannot be "
                f"below zero.\n"
                f"A rollout that contributes nothing to this figure passes (0, 0)."
            )


def rollout_noise(by_example: Sequence[Sequence[float]]) -> float | None:
    """How far this figure moves when the same examples are run again, as a standard deviation.

    The interval answers a different question: it resamples **examples**, holding each
    example's mean over its own rollouts fixed, so it says how much the figure would move on a
    different sample of examples. This says how much it moves on *these* examples, because the
    agent is stochastic and k rollouts of one example do not agree::

        rollout_noise([[1, 1, 0], [1, 1, 1], [0, 0, 1]])   # 0.0785

    Each example's rollouts are one sample of that example's own rate, so the variance of the
    figure is the sum of each example's variance over its k, divided by n squared. ``None``
    where every example ran once, which leaves no within-example variation to read, and 0.0
    where every example's rollouts agreed with each other.

    A difference between two runs smaller than this is not a difference: it is what one
    configuration produces twice.
    """
    grouped = [list(rollouts) for rollouts in by_example]
    if not grouped or all(len(rollouts) < 2 for rollouts in grouped):
        return None
    total = 0.0
    for rollouts in grouped:
        if len(rollouts) < 2:
            continue
        mean = sum(rollouts) / len(rollouts)
        variance = sum((score - mean) ** 2 for score in rollouts) / (len(rollouts) - 1)
        total += variance / len(rollouts)
    return math.sqrt(total) / len(grouped)


def _z_for(confidence: float) -> float:
    """The two-sided normal quantile for ``confidence``, by bisection on ``math.erf``.

    Wilson's interval needs one number out of the normal distribution and the standard library
    has no inverse CDF, so it is inverted here rather than by taking a dependency.
    """
    target = (1.0 + confidence) / 2.0
    low, high = 0.0, 40.0
    for _ in range(200):
        middle = (low + high) / 2.0
        if 0.5 * (1.0 + math.erf(middle / math.sqrt(2.0))) < target:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _percentiles(estimates: list[float], confidence: float) -> tuple[float, float]:
    """The two endpoints, read off the sorted resampled estimates.

    Indices are taken by rounding outward, so an interval never reads narrower than the
    resample count can support.
    """
    ordered = sorted(estimates)
    last = len(ordered) - 1
    tail = (1.0 - confidence) / 2.0
    low = ordered[max(0, math.floor(tail * len(ordered)))]
    high = ordered[min(last, math.ceil((1.0 - tail) * len(ordered)) - 1)]
    return low, high


def _refuse_unusable(grouped: list[Any], *, confidence: float, resamples: int) -> None:
    if not grouped:
        raise ConfigurationError(
            "bootstrap_ci was given no examples. An interval over nothing is not a wide "
            "interval, it is no measurement. Pass one inner sequence per example, holding "
            "that example's score on each rollout."
        )
    flat = [i for i, rollouts in enumerate(grouped) if not isinstance(rollouts, (list, tuple))]
    if flat:
        raise ConfigurationError(
            f"bootstrap_ci was given a flat sequence of scores: index {flat[0]} holds "
            f"{grouped[flat[0]]!r} rather than one example's rollouts. Resampling those as "
            f"though each were an independent observation produces an interval narrower than "
            f"the data supports, and nothing about the number would reveal it.\n"
            f"Group them by example: bootstrap_ci([[1, 1, 0], [0, 0, 0]]). One score per "
            f"example is bootstrap_ci([[0.5], [0.3]])."
        )
    unusable = [
        i
        for i, rollouts in enumerate(grouped)
        for score in rollouts
        if not isinstance(score, (int, float))
    ]
    if unusable:
        raise ConfigurationError(
            f"bootstrap_ci was given a score that is not a number, at example index "
            f"{unusable[0]}. Each inner sequence holds that example's score on each rollout, "
            f"usually 1 and 0 for a rollout that was correct and one that was not.\n"
            f"Pass floats: bootstrap_ci([[1.0, 0.0], [1.0, 1.0]])."
        )
    empty = [i for i, rollouts in enumerate(grouped) if not rollouts]
    if empty:
        raise ConfigurationError(
            f"bootstrap_ci was given {len(empty)} example(s) with no rollouts, at index "
            f"{empty[0]}. An example that was never run has no score, and counting it as zero "
            f"would report a failure the agent was never given the chance to have.\n"
            f"Drop the examples that did not run, or run them."
        )
    if not 0.0 < confidence < 1.0:
        raise ConfigurationError(
            f"bootstrap_ci(confidence={confidence}) takes a fraction between 0 and 1, "
            f"exclusive. Pass confidence=0.95 for the conventional interval."
        )
    if resamples < MIN_RESAMPLES:
        raise ConfigurationError(
            f"bootstrap_ci(resamples={resamples}) is below {MIN_RESAMPLES}. The endpoints are "
            f"percentiles of the resampled estimates, so too few of them makes the interval "
            f"vary between runs more than the data does.\n"
            f"Pass resamples={DEFAULT_RESAMPLES}, which is the default, or higher."
        )
