"""A figure that is one total over another, and what one rollout contributes to it.

A project metric is a mean over examples: each example counts once whatever it returned. That
is the wrong shape wherever the thing being counted is not the rollout. An agent returning 10
picks with 1 from the backlist and another returning 2 picks with 1 have contributed 2 of 12,
and the mean of their two ratios is 0.30.

``docs/evaluation.md`` §11 is the surface of record. The declaration is
:class:`ProjectRatio`; the interval it takes is :func:`~simple_agents.evaluation.ratio_ci`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from ..errors import ConfigurationError

if TYPE_CHECKING:
    from .compare import MetricChange
from ..records.manifest import source_version
from ..schema import Unknown
from .intervals import (
    DEFAULT_CONFIDENCE,
    DEFAULT_RESAMPLES,
    paired_ratio_ci,
    ratio_ci,
)
from .judgements import JudgementMissing
from .metrics import (
    METRIC_DEFINITIONS,
    score_of,
    scores_this_rollout,
    RATE,
    Metric,
    Over,
    _causes,
    _OVER_POPULATIONS,
    inside,
)
from .outcomes import RolloutOutcome
from .scoring import Scoring

__all__ = [
    "ProjectRatio",
    "figures_for",
    "is_ratio",
    "ratio_of",
    "ratio_pairs",
    "ratio_metric",
    "ratio_changes",
    "refuse_a_bare_total",
    "ratios_over",
]


def refuse_a_bare_total(name: str, *, has_denominator: bool, no_interval: str | None) -> None:
    """A count reported as though it were a rate is the failure FT-06 exists for.

    Called wherever a ratio figure is declared, so the rule reaches a figure over pairs on the
    same terms as one over rollouts.
    """
    if not has_denominator and not (no_interval or "").strip():
        raise ConfigurationError(
            f"{name!r} declares no denominator, so it is a total rather than a ratio and there "
            f"is nothing for an interval to be computed over. A total reported as though it "
            f"were a rate is the failure FT-06 exists for.\n"
            f"Pass a denominator returning 1.0 to report it per unit, which is the better "
            f"answer wherever the count is out of something. Where it genuinely is a census "
            f"over this run, say so: no_interval='a count over this run, not an estimate'."
        )
    if no_interval is not None and not no_interval.strip():
        raise ConfigurationError(
            f"{name!r} was given an empty no_interval. The reason is printed in place of the "
            f"interval and read by the conformance check, so a figure declaring no interval "
            f"has to say what it is instead.\n"
            f"Pass no_interval='a count over this run, not an estimate of a rate'."
        )


@dataclass(frozen=True, slots=True)
class ProjectRatio:
    """A figure the project computes as one total over another, reported beside the eight rates.

    Reach for this where the thing counted is not the rollout. ``numerator`` and ``denominator``
    each take a :class:`~simple_agents.evaluation.Scoring` and return that rollout's
    contribution to the two totals, which are summed over the population and divided::

        backlist = ProjectRatio(
            name="backlist_share",
            definition="picks from the backlist, over all picks",
            numerator=lambda s: len([p for p in s.answer.picks if p.backlist]),
            denominator=lambda s: len(s.answer.picks),
        )

        results.metrics["backlist_share"].numerator     # 118
        results.metrics["backlist_share"].value         # 0.175

    **This is not the mean of each example's own ratio.** 10 picks with 1 from the backlist and
    2 picks with 1 give 2 of 12; their mean is 0.30. A figure where each example counts once is
    a :class:`~simple_agents.evaluation.ProjectMetric`.

    The interval resamples examples, so k rollouts of one example travel together.

    Declarable per node as well, through ``EvalSuite(node_metrics=...)``, where the two totals
    are summed over the rollouts that reached the node and carry a label for it.

    ``no_interval`` declares the figure a count over this run rather than an estimate, and holds
    the reason printed in place of an interval. Such a figure reports its totals and has its
    verdict withheld by a comparison. Declare a ``denominator`` wherever there is one::

        ProjectRatio(name="dropped", definition="candidates dropped",
                     numerator=lambda s: s.answer.dropped,
                     no_interval="a count over this run, not an estimate of a rate")

    Raises :class:`~simple_agents.errors.ConfigurationError` for a name one of the eight rates
    has, for a half that is not callable or returns something other than a number, for a total
    declaring neither a denominator nor ``no_interval``, and for an empty ``no_interval``.
    """

    name: str
    definition: str
    numerator: Callable[[Scoring], float]
    denominator: Callable[[Scoring], float] | None = None
    over: Over = Over.ALL
    unit: str | None = RATE
    no_interval: str | None = None

    def __post_init__(self) -> None:
        if self.name in METRIC_DEFINITIONS:
            raise ConfigurationError(
                f"{self.name!r} is one of the eight rates every evaluation reports, and the "
                f"results file holds one entry per name, so one of the two would be reported "
                f"and the other dropped.\n"
                f"Name this one for what it is over: 'backlist_share', 'win_rate'. The eight "
                f"are {', '.join(METRIC_DEFINITIONS)}."
            )
        for role, fn in (("numerator", self.numerator), ("denominator", self.denominator)):
            if fn is None and role == "denominator":
                continue
            if not callable(fn):
                raise ConfigurationError(
                    f"ProjectRatio({self.name!r}) needs {role}=, a function taking a Scoring "
                    f"and returning this rollout's contribution to the {role}.\n"
                    f"Pass {role}=lambda s: len(s.answer.picks). The answer is s.answer, the "
                    f"label is s.expected, the example is s.example, and what the run recorded "
                    f"is at s.trajectory."
                )
        if not isinstance(self.over, Over):
            raise ConfigurationError(
                f"ProjectRatio({self.name!r}) was given over={self.over!r}. Pass one of "
                f"Over.ASSERTED, Over.VALUE_EXISTS or Over.ALL."
            )
        refuse_a_bare_total(
            self.name,
            has_denominator=self.denominator is not None,
            no_interval=self.no_interval,
        )

    @property
    def population(self) -> str:
        """The sentence a report prints after the n, derived from ``over``."""
        return _OVER_POPULATIONS[self.over]

    @property
    def estimated(self) -> bool:
        """Whether the figure is a reading an interval speaks for."""
        return self.no_interval is None

    def to_record(self) -> dict[str, Any]:
        """What a results file records about the declaration, beside the number.

        Both functions are versioned, so a comparison can tell that either half of the ratio
        moved between two evaluations.
        """
        numerator = source_version(self.numerator)
        denominator = source_version(self.denominator) if self.denominator is not None else {}
        return {
            "name": self.name,
            "definition": self.definition,
            "population": self.population,
            "over": self.over.value,
            "unit": self.unit,
            "kind": "ratio",
            "no_interval": self.no_interval,
            "numerator_version": numerator.get("version"),
            "numerator_source": numerator.get("source"),
            "denominator_version": denominator.get("version"),
            "denominator_source": denominator.get("source"),
        }


def ratio_of(
    metric: ProjectRatio, scoring: Scoring, *, asserted: bool
) -> tuple[float, float] | None:
    """What one rollout contributes to ``metric``, or ``None`` where it is outside it.

    Returns the pair the two totals are summed from. A rollout outside the population under
    ``Over.ASSERTED`` contributes nothing at all; one outside it under ``Over.VALUE_EXISTS``
    contributes zero to both, since it is inside the figure and put no value forward.
    """
    if not scores_this_rollout(metric, scoring, asserted=asserted):
        if isinstance(scoring.expected, Unknown) or metric.over is Over.ASSERTED:
            return None
        return (0.0, 0.0)
    numerator = _counted(metric, metric.numerator, scoring, "numerator")
    if numerator is None:
        return None
    if metric.denominator is None:
        return (numerator, 0.0)
    denominator = _counted(metric, metric.denominator, scoring, "denominator")
    if denominator is None:
        return None
    if denominator < 0:
        raise ConfigurationError(
            f"Metric {metric.name!r} returned a denominator of {denominator} scoring rollout "
            f"{scoring.rollout} of example {scoring.example.id!r}. A denominator counts what "
            f"the numerator is out of, so it cannot be below zero.\n"
            f"Return 0 for a rollout that contributes nothing to this figure."
        )
    return (numerator, denominator)


def _counted(
    metric: ProjectRatio,
    fn: Callable[[Scoring], float],
    scoring: Scoring,
    role: str,
) -> float | None:
    try:
        value = fn(scoring)
    except JudgementMissing:
        # As a mean's score: the figure asked for a judgement nothing has made, so the rollout
        # leaves this figure for now and the request is collected.
        return None
    except Exception as exc:
        raise ConfigurationError(
            f"Metric {metric.name!r} raised {type(exc).__name__} in its {role} scoring rollout "
            f"{scoring.rollout} of example {scoring.example.id!r}: {exc}\n"
            f"Both halves are called once per rollout in the figure's population, so each has "
            f"to return a number for every one of them. Declare over=Over.ASSERTED to leave "
            f"out the rollouts that put no value forward."
        ) from exc
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not isinstance(value, (int, float)):
        raise ConfigurationError(
            f"Metric {metric.name!r} returned {value!r} from its {role} scoring rollout "
            f"{scoring.rollout} of example {scoring.example.id!r}. Each half of a ratio is a "
            f"number, summed over the population and then divided.\n"
            f"Return a count: numerator=lambda s: len(s.answer.picks)."
        )
    return float(value)


def ratio_pairs(
    outcomes: Sequence[RolloutOutcome],
    names: Sequence[str],
    *,
    population: Callable[[RolloutOutcome], bool] = inside,
    node_id: str | None = None,
) -> dict[str, dict[str, list[tuple[float, float]]]]:
    """Each ratio figure's recorded per-rollout pairs, keyed by name then by example id.

    Read off the rollouts rather than recomputed, so a results file carries its own numbers and
    a comparison between two of them needs neither the labels nor the scoring functions.

    ``node_id`` reads the pairs one node contributed rather than the rollout's own, which is
    where a ratio declared through ``node_metrics`` records them.
    """
    by_example: dict[str, list[RolloutOutcome]] = {}
    for rollout in outcomes:
        if population(rollout):
            by_example.setdefault(rollout.example_id, []).append(rollout)

    found: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for name in names:
        per_example: dict[str, list[tuple[float, float]]] = {}
        for example_id, rollouts in by_example.items():
            pairs = [
                (float(held[name][0]), float(held[name][1]))
                for r in sorted(rollouts, key=lambda r: r.rollout)
                for held in (_ratios_on(r, node_id),)
                if name in held
            ]
            if pairs:
                per_example[example_id] = pairs
        found[name] = per_example
    return found


def _ratios_on(rollout: RolloutOutcome, node_id: str | None) -> Mapping[str, Any]:
    """The pairs this rollout recorded, for the whole run or for one node of it."""
    if node_id is None:
        return rollout.ratios
    observed = rollout.nodes.get(node_id)
    return observed.ratios if observed is not None else {}


@dataclass(frozen=True, slots=True)
class RatioShape:
    """What a ratio figure reports, apart from the numbers: a declaration or a figure like it.

    A grouped cell recomputes a figure it has no declaration for, so both routes supply this.
    """

    name: str
    definition: str
    population: str
    unit: str | None
    no_interval: str | None
    has_denominator: bool

    def __post_init__(self) -> None:
        refuse_a_bare_total(
            self.name, has_denominator=self.has_denominator, no_interval=self.no_interval
        )

    @property
    def estimated(self) -> bool:
        return self.no_interval is None


def is_ratio(metric: Metric) -> bool:
    """Whether a computed figure is a ratio of two totals rather than a mean over examples."""
    return metric.numerator is not None or not metric.estimated


def shape_of(metric: Metric) -> RatioShape:
    """The shape of an already-computed ratio, for recomputing it over a subset of rollouts."""
    return RatioShape(
        name=metric.name,
        definition=metric.definition,
        population=metric.population,
        unit=metric.unit,
        no_interval=None if metric.estimated else metric.reason,
        has_denominator=metric.denominator is not None,
    )


def ratios_over(
    outcomes: Sequence[RolloutOutcome],
    *,
    like: Mapping[str, Metric],
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> dict[str, Metric]:
    """Every ratio figure in ``like``, recomputed over these rollouts alone.

    The pairs are read off the rollouts, so a grouped cell needs neither the declaration nor
    the two functions.
    """
    names = [name for name, metric in like.items() if is_ratio(metric)]
    pairs = ratio_pairs(outcomes, names)
    return {
        name: ratio_metric(
            declared=shape_of(like[name]),
            grouped=list(pairs[name].values()),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
        )
        for name in names
    }


def ratio_metric(
    *,
    declared: "ProjectRatio | RatioShape",
    grouped: list[list[tuple[float, float]]],
    confidence: float,
    resamples: int,
    seed: int,
    left_out: Mapping[str, int] | None = None,
) -> Metric:
    """One ratio figure: its two totals, and the interval around their quotient."""
    left_out = dict(left_out or {})
    common: dict[str, Any] = {
        "name": declared.name,
        "definition": declared.definition,
        "population": declared.population,
        "unit": declared.unit,
        "over": getattr(declared, "over", None) and declared.over.value,
        "left_out": left_out,
        "estimated": declared.estimated,
    }
    if not grouped:
        unanswered = f" {_causes(left_out)} are outside it." if left_out else ""
        return Metric(
            rollouts=0,
            examples=0,
            reason=f"No rollouts fall under {declared.population}, so this figure has no "
            f"denominator.{unanswered}",
            **common,
        )

    counted: dict[str, Any] = {
        "rollouts": sum(len(rollouts) for rollouts in grouped),
        "examples": len(grouped),
        "numerator": sum(num for rollouts in grouped for num, _ in rollouts),
    }
    has_denominator = getattr(declared, "has_denominator", None)
    if has_denominator is None:
        has_denominator = declared.denominator is not None
    if has_denominator:
        counted["denominator"] = sum(den for rollouts in grouped for _, den in rollouts)

    reason = _why_no_interval(declared, counted.get("denominator"))
    if reason is not None:
        return Metric(reason=reason, **counted, **common)
    return Metric(
        interval=ratio_ci(grouped, confidence=confidence, resamples=resamples, seed=seed),
        **counted,
        **common,
    )


def _why_no_interval(
    declared: "ProjectRatio | RatioShape", denominator: float | None
) -> str | None:
    """Why this figure reports no interval, or ``None`` where it reports one."""
    if declared.no_interval is not None:
        return declared.no_interval
    if denominator is None:
        return "a total over this run, declared with no denominator."
    if denominator <= 0:
        return (
            f"Nothing was counted under {declared.population}: the denominator of this figure "
            f"summed to {denominator:g}, so there is no ratio to take."
        )
    return None


def figures_for(
    declared: Sequence[Any], scoring: Scoring, *, asserted: bool
) -> tuple[dict[str, float], dict[str, tuple[float, float]]]:
    """Every project figure for one rollout: the means as scores, the ratios as pairs.

    A ratio carries two numbers because it is summed rather than averaged, so one score per
    rollout could not hold it.
    """
    scores: dict[str, float] = {}
    ratios: dict[str, tuple[float, float]] = {}
    for metric in declared:
        if isinstance(metric, ProjectRatio):
            pair = ratio_of(metric, scoring, asserted=asserted)
            if pair is not None:
                ratios[metric.name] = pair
            continue
        value = score_of(metric, scoring, asserted=asserted)
        if value is not None:
            scores[metric.name] = value
    return scores, ratios


def ratio_changes(
    before: Any,
    after: Any,
    shared: tuple[str, ...],
    *,
    confidence: float,
    resamples: int,
    seed: int,
    node_id: str | None = None,
    rules: Mapping[str, Any] | None = None,
) -> dict[str, MetricChange]:
    """How each ratio figure moved, paired example by example on the two arms' own counts.

    A ratio is summed rather than averaged, so pairing it on per-rollout scores finds nothing:
    the two counts live in ``rollouts[].ratios``, and in ``rollouts[].nodes[].ratios`` for one
    declared per node. The difference is between the two pooled ratios, taken inside each
    resample of the examples.

    ``node_id`` compares the figures one node carries. ``rules`` names the figures whose two
    halves were versioned differently on the two sides, which a difference between them cannot
    be separated from.
    """
    held_before = before.nodes[node_id].metrics if node_id is not None else before.metrics
    held_after = after.nodes[node_id].metrics if node_id is not None else after.metrics
    names = [
        name
        for name, metric in held_before.items()
        if is_ratio(metric) and name in held_after and is_ratio(held_after[name])
    ]
    if not names:
        return {}
    before_pairs = ratio_pairs(before.rollouts, names, node_id=node_id)
    after_pairs = ratio_pairs(after.rollouts, names, node_id=node_id)

    changed: dict[str, MetricChange] = {}
    for name in names:
        both = [
            example_id
            for example_id in shared
            if example_id in before_pairs[name] and example_id in after_pairs[name]
        ]
        changed[name] = _one_ratio_change(
            name=name,
            before=held_before[name],
            after=held_after[name],
            left=[before_pairs[name][e] for e in both],
            right=[after_pairs[name][e] for e in both],
            confidence=confidence,
            resamples=resamples,
            seed=seed,
            rule_moved=(rules or {}).get(name),
        )
    return changed


def _one_ratio_change(
    *,
    name: str,
    before: Any,
    after: Any,
    left: list[list[tuple[float, float]]],
    right: list[list[tuple[float, float]]],
    confidence: float,
    resamples: int,
    seed: int,
    rule_moved: Any = None,
) -> MetricChange:
    """One ratio's two values and the interval on their difference, or why there is none."""
    from .compare import MetricChange

    common = {
        "name": name,
        "definition": after.definition or before.definition,
        "before": before.value,
        "after": after.value,
        "before_examples": len(left),
        "after_examples": len(right),
        "rule_moved": rule_moved,
    }
    if not left:
        return MetricChange(
            examples=0,
            reason=f"No shared example carries counts for {name} on both sides, so there is "
            f"nothing to pair.",
            **common,
        )
    # A figure the project declared un-estimated has no interval on either side, so a
    # difference between them is a difference of two counts and carries no verdict.
    if not (before.estimated and after.estimated):
        return MetricChange(
            examples=len(left),
            reason=f"{name} is a count over each run rather than an estimate of a rate, so "
            f"the difference between the two is not a measured change.",
            **common,
        )
    try:
        difference = paired_ratio_ci(
            left, right, confidence=confidence, resamples=resamples, seed=seed
        )
    except ConfigurationError as exc:
        return MetricChange(examples=len(left), reason=str(exc).splitlines()[0], **common)
    return MetricChange(examples=len(left), difference=difference, **common)
