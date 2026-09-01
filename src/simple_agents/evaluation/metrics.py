"""The eight rates an evaluation reports, and `ProjectMetric` for one the project computes itself.

The two that get conflated are the point of this module. `false_confidence_rate` is how often
the agent asserted a value that was wrong; `recall` is how often it failed to find a value that
existed. One accuracy number covering both hides the dangerous failure behind the harmless one
(FT-10), so each is named for what it is over and carries an interval computed from that subset
alone.

`partially_correct_rate` is the same separation one level down, for an answer key whose parts
can be met separately. An answer meeting two of three conditions is neither right nor a
confident wrong value, and reporting it as either is the averaging FT-10 exists to prevent.
`graded_accuracy` is `accuracy` with those answers scoring the share they met, so the two
figures differ only where a rollout was partly right.

The eight are functions of the rollout and of whether the example expects absence. A
`ProjectMetric` is a function of the answer. A per-criterion figure is a function of one
criterion's verdict, and `criterion_metrics` builds those.

Every interval resamples examples rather than rollouts, which ``intervals.py`` explains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from ..errors import ConfigurationError
from ..records.manifest import source_version
from ..schema import Unknown
from .intervals import (
    DEFAULT_CONFIDENCE,
    DEFAULT_RESAMPLES,
    Interval,
    bootstrap_ci,
    rollout_noise,
)
from .judgements import JudgementMissing
from .outcomes import Outcome, RolloutOutcome, causes_of
from .scoring import Scoring

if TYPE_CHECKING:
    from .ratios import ProjectRatio

__all__ = [
    "Metric",
    "METRIC_DEFINITIONS",
    "Over",
    "ProjectMetric",
    "RATE",
    "aggregate",
    "criterion_absences",
    "criterion_metrics",
    "criterion_scores",
    "unanswered_rollouts",
]

# A metric's ``unit`` when it is a rate, which is what a report prints as a percentage.
RATE = "rate"

# name -> (what the rate is over, which rollouts count in the denominator, what each scores,
# which examples the figure is over whatever their rollouts did).
# `absence` says whether the example's own correct answer is that the value is not there.
# A scorer takes the whole rollout rather than its outcome, because `graded_accuracy` reads
# the verdict and every other one reads the outcome alone.
_Included = Callable[[RolloutOutcome, bool], bool]
_Scored = Callable[[RolloutOutcome, bool], float]
_Population = Callable[[bool], bool]

_ALL: _Included = lambda rollout, absence: True

NO_RESPONSE = "no_response"
"""The cause that leaves a rollout with no answer to score, either way."""

LEFT_OUT_CAUSES = {
    NO_RESPONSE: "that got no response",
    "unanswered_consultation": "whose question went unanswered",
    "unreached_items": "whose items never reached the backend",
    "left_the_slice": "that took a path this slice does not hold",
}
"""What each cause is called wherever a figure says what it left out."""


def inside(rollout: RolloutOutcome) -> bool:
    """Whether this rollout measured the agent, so a rate is computed over it."""
    return not causes_of(rollout)


def scorable(rollout: RolloutOutcome) -> bool:
    """Whether it produced an answer at all, which a rollout the backend ignored did not."""
    return rollout.outcome.measured


_EVERY_EXAMPLE: _Population = lambda absence: True
_WHERE_A_VALUE_EXISTS: _Population = lambda absence: not absence


def _is(outcome: Outcome) -> _Scored:
    return lambda rollout, absence: 1.0 if rollout.outcome is outcome else 0.0


_SPECS: dict[str, tuple[str, _Included, _Scored, _Population]] = {
    "accuracy": (
        "all rollouts",
        _ALL,
        lambda rollout, absence: 1.0 if rollout.outcome.succeeded else 0.0,
        _EVERY_EXAMPLE,
    ),
    "graded_accuracy": (
        "all rollouts",
        _ALL,
        lambda rollout, absence: rollout.graded_score,
        _EVERY_EXAMPLE,
    ),
    "false_confidence_rate": (
        "all rollouts",
        _ALL,
        _is(Outcome.FALSE_CONFIDENCE),
        _EVERY_EXAMPLE,
    ),
    "partially_correct_rate": (
        "all rollouts",
        _ALL,
        _is(Outcome.PARTIALLY_CORRECT),
        _EVERY_EXAMPLE,
    ),
    "recall": (
        "rollouts of examples where a value exists",
        lambda rollout, absence: not absence,
        _is(Outcome.CORRECT),
        _WHERE_A_VALUE_EXISTS,
    ),
    "abstention_rate": (
        "all rollouts",
        _ALL,
        lambda rollout, absence: (
            1.0
            if rollout.outcome in (Outcome.MISSED, Outcome.CORRECT_ABSTENTION)
            and not rollout.asserted
            else 0.0
        ),
        _EVERY_EXAMPLE,
    ),
    "failure_rate": (
        "all rollouts",
        _ALL,
        _is(Outcome.FAILED),
        _EVERY_EXAMPLE,
    ),
    "precision_when_asserting": (
        "rollouts that asserted an answer",
        lambda rollout, absence: rollout.asserted,
        _is(Outcome.CORRECT),
        _EVERY_EXAMPLE,
    ),
}

METRIC_DEFINITIONS: dict[str, str] = {
    "accuracy": "right answers, counting a right report of absence, over all rollouts",
    "graded_accuracy": "right answers with partial credit, counting a right report of absence, "
    "over all rollouts",
    "false_confidence_rate": "rollouts that asserted a wrong answer, meeting none of its "
    "answer key or missing a condition the key declared required, over all rollouts. An answer "
    "that fell short only by saying nothing is not one of these",
    "partially_correct_rate": "rollouts that asserted an answer meeting part of its answer key, "
    "over all rollouts",
    "recall": "rollouts that found the right value, over rollouts of examples where a value exists",
    "abstention_rate": "rollouts that reported absence, over all rollouts",
    "failure_rate": "rollouts that produced no answer at all, over all rollouts",
    "precision_when_asserting": "rollouts that asserted the right value, over rollouts that "
    "asserted anything",
}

CRITERION_POPULATION = "rollouts judged against this criterion"


@dataclass(frozen=True, slots=True)
class Metric:
    """One measured figure, what it is over, and the interval around it.

    ``population`` is the sentence naming which rollouts the figure covers, such as
    ``"rollouts of examples where a value exists"``. ``numerator`` and ``denominator`` are the
    two totals behind a figure that is a ratio of them, and both are ``None`` for a figure that
    is a mean over examples::

        results.metrics["accuracy"].population       # 'all rollouts'
        results.metrics["backlist_share"].numerator  # 118
        results.metrics["backlist_share"].denominator  # 673

    ``interval`` is ``None`` in two cases, and ``reason`` says which. The population is empty:
    recall over a split where every answer is absent is not zero, it is undefined, and
    reporting zero would read as the agent finding nothing. Or the project declared that this
    figure has no interval, which is what a count over one run is::

        results.metrics["false_confidence_rate"].interval.point   # 0.08
        results.metrics["recall"].reason                          # None, or why it is absent

    ``estimated`` is whether the figure is a reading the interval speaks for. It is ``False``
    for a figure the project declared un-intervalable, which is a census over the run rather
    than an estimate of anything, and a report prints one so it cannot be quoted as a
    measurement. A comparison shows such a figure and withholds its verdict.

    ``unit`` is ``RATE`` for a figure between 0 and 1, which a report prints as a percentage.
    A project metric measured in something else names it, and one that is a bare number passes
    ``None``::

        results.metrics["span_f1"].unit             # 'rate', printed 71.4%
        results.metrics["cost_per_answer"].unit     # 'USD',  printed 0.000153 USD
    """

    name: str
    definition: str
    population: str
    rollouts: int
    examples: int
    interval: Interval | None = None
    reason: str | None = None
    unit: str | None = RATE
    numerator: float | None = None
    denominator: float | None = None
    estimated: bool = True
    over: str | None = None
    """Which rollouts the figure was computed over, as the ``Over`` that decided it.

    ``population`` is the same fact in words. This is the value a reader can compare between
    two files without parsing a sentence, and ``None`` for the eight rates, whose denominators
    are fixed::

        results.metrics["span_f1"].over        # 'asserted'
    """
    left_out: dict[str, int] = field(default_factory=dict)
    """Rollouts this figure would have been over that did not measure the agent, by cause.

    They are outside ``rollouts`` and outside the interval. A denominator that shrank without
    saying so reads as a measurement over the whole split, so the counts travel with every
    figure and ``report()`` prints them on every line::

        results.metrics["accuracy"].left_out
        # {'no_response': 9, 'unanswered_consultation': 5}

    ``no_response`` is the backend never answering, ``unanswered_consultation`` a question that
    went to a channel meant to answer it and did not, and ``unreached_items`` a fan-out item
    that died on a call the backend never answered.
    """

    including_left_out: Interval | None = None
    """The same figure with the left-out rollouts counted as they scored, or ``None``.

    ``None`` where nothing was left out for a reason that leaves an answer to score, which is
    every cause but ``no_response``: a rollout the backend never answered has no answer to
    count either way. Reported so the narrower figure cannot be read without the wider one::

        results.metrics["accuracy"].interval.point             # 0.947, over 95
        results.metrics["accuracy"].including_left_out.point   # 0.900, over 100
    """

    rollout_noise: float | None = None
    """How far this figure moves when the same examples are run again, as a standard deviation.

    The interval is over which examples were drawn; this is over the agent being stochastic on
    the examples it has, which no interval reports and which a comparison has to be read
    against::

        results.metrics["accuracy"].interval.width    # 0.14, from resampling examples
        results.metrics["accuracy"].rollout_noise     # 0.017, from the k rollouts of each

    ``None`` where every example ran once, which leaves nothing within an example to read. A
    difference between two runs smaller than this is what one configuration produces twice, and
    ``compare`` withholds its verdict there.
    """

    absent: int = 0
    """Rollouts that did not meet this condition because they asserted nothing about it.

    Only ever set on a per-criterion figure. They are unmet, so they are inside ``rollouts``
    and inside the interval, and the count says how much of the shortfall is silence rather
    than error. Silence where the criterion declares ``expects_absence`` met the condition and
    is not a shortfall, so it is not counted here::

        results.criteria["po_number"].interval.point   # 0.61
        results.criteria["po_number"].absent           # 12
    """

    @property
    def value(self) -> float | None:
        """The figure, or ``None`` where it is undefined.

        The point estimate where there is an interval. Where the project declared that the
        figure has none, this is the ratio of the two totals, or the numerator alone for a
        figure that is a count::

            results.metrics["dropped"].value       # 47.0, and interval is None
        """
        if self.interval is not None:
            return self.interval.point
        if self.numerator is None:
            return None
        if self.denominator is None:
            return float(self.numerator)
        if self.denominator == 0:
            return None
        return float(self.numerator) / float(self.denominator)

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "definition": self.definition,
            "population": self.population,
            "over": self.over,
            "unit": self.unit,
            "rollouts": self.rollouts,
            "examples": self.examples,
            "left_out": dict(sorted(self.left_out.items())),
            "including_left_out": (
                self.including_left_out.to_record() if self.including_left_out is not None else None
            ),
            "absent": self.absent,
            "rollout_noise": self.rollout_noise,
            "interval": self.interval.to_record() if self.interval is not None else None,
            "reason": self.reason,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "estimated": self.estimated,
        }

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> Metric:
        """Rebuild a metric from a results file."""
        interval = raw.get("interval")
        return cls(
            name=str(raw["name"]),
            definition=str(raw.get("definition", "")),
            population=str(raw.get("population", "")),
            over=raw.get("over"),
            rollouts=int(raw.get("rollouts", 0)),
            examples=int(raw.get("examples", 0)),
            interval=Interval.from_record(interval) if interval else None,
            reason=raw.get("reason"),
            unit=raw["unit"] if "unit" in raw else RATE,
            left_out={str(k): int(v) for k, v in (raw.get("left_out") or {}).items()},
            including_left_out=(
                Interval.from_record(raw["including_left_out"])
                if raw.get("including_left_out")
                else None
            ),
            absent=int(raw.get("absent", 0)),
            rollout_noise=(
                None if raw.get("rollout_noise") is None else float(raw["rollout_noise"])
            ),
            numerator=(None if raw.get("numerator") is None else float(raw["numerator"])),
            denominator=(None if raw.get("denominator") is None else float(raw["denominator"])),
            estimated=bool(raw.get("estimated", True)),
        )


class Over(str, Enum):
    """Which rollouts a project metric is a figure over.

    Under ``ASSERTED`` and ``VALUE_EXISTS`` the library reads absence on both sides, so
    ``score`` is only ever handed two asserted values.
    """

    ASSERTED = "asserted"
    """Rollouts that put a value forward, of examples whose label is a value.

    Reads as "when it answered, how close was it". A rollout that reported absence or produced
    nothing leaves the denominator.
    """

    VALUE_EXISTS = "value_exists"
    """Every rollout of an example whose label is a value.

    Reads as "how close was it, overall". A rollout that reported absence or produced nothing
    scores 0.0 and ``score`` is not called for it.
    """

    ALL = "all"
    """Every rollout, absence included.

    ``score`` is handed whatever the rollout produced, so ``predicted`` may be ``Unknown`` or
    ``None`` and ``expected`` may be ``Unknown``.
    """


_OVER_POPULATIONS: dict[Over, str] = {
    Over.ASSERTED: "rollouts that asserted a value, of examples where a value exists",
    Over.VALUE_EXISTS: "rollouts of examples where a value exists",
    Over.ALL: "all rollouts",
}


@dataclass(frozen=True, slots=True)
class ProjectMetric:
    """A figure the project computes from the answer, reported beside the eight rates.

    ``score`` takes a :class:`~simple_agents.evaluation.Scoring` and returns a number. It is the
    same object every other scoring rule is given, so a figure over the answer alone reads
    ``s.answer``, one over the question reads ``s.example``, and one over what the run did reads
    ``s.trajectory``::

        span_f1 = ProjectMetric(
            name="span_f1",
            definition="token overlap between the asserted answer and the label",
            score=lambda s: token_f1(s.answer, s.expected),
        )

        suite = EvalSuite(pipeline, examples, answer="answer", matches=exact,
                          metrics=[span_f1])
        results.metrics["span_f1"].interval.point

    ``over`` says which rollouts the figure is over, and whether ``score`` ever meets an
    absence. ``unit`` is ``RATE`` for a figure between 0 and 1; a metric in something else
    names it, so a report prints ``0.000153 USD`` rather than ``0.0%``.

    The figure is a mean over examples, which is what the interval is taken over. A ratio of
    two totals is a different quantity, and ``results.totals`` carries both of its parts.

    ``score`` is versioned by a hash of its source and of what it closes over, so an edit
    appears in a comparison and the comparison withholds its verdict. A constant read from
    module level is outside that hash, and so is what a file the function opens holds.

    Raises :class:`~simple_agents.errors.ConfigurationError` for a name one of the eight rates
    already has, and for a ``score`` returning something other than a number.
    """

    name: str
    definition: str
    score: Callable[[Scoring], float]
    over: Over = Over.VALUE_EXISTS
    unit: str | None = RATE

    def __post_init__(self) -> None:
        if self.name in METRIC_DEFINITIONS:
            raise ConfigurationError(
                f"{self.name!r} is one of the eight rates every evaluation reports, and the "
                f"results file holds one entry per name, so one of the two would be reported "
                f"and the other dropped.\n"
                f"Name this one for what it is over: 'span_f1', 'within_tolerance'. The eight "
                f"are {', '.join(METRIC_DEFINITIONS)}."
            )
        if not callable(self.score):
            raise ConfigurationError(
                f"ProjectMetric({self.name!r}) needs score=, a function taking a Scoring and "
                f"returning a number.\n"
                f"Pass score=lambda s: token_f1(s.answer, s.expected). The answer is s.answer, "
                f"the label is s.expected, the example is s.example, and what the run recorded "
                f"is at s.trajectory."
            )
        if not isinstance(self.over, Over):
            raise ConfigurationError(
                f"ProjectMetric({self.name!r}) was given over={self.over!r}. Pass one of "
                f"Over.ASSERTED, Over.VALUE_EXISTS or Over.ALL."
            )

    @property
    def population(self) -> str:
        """The sentence a report prints after the n, derived from ``over``."""
        return _OVER_POPULATIONS[self.over]

    def to_record(self) -> dict[str, Any]:
        """What a results file records about the declaration, beside the number.

        The version is what lets a comparison tell that the scoring rule moved between two
        evaluations.
        """
        return {
            "name": self.name,
            "definition": self.definition,
            "population": self.population,
            "over": self.over.value,
            "unit": self.unit,
            **source_version(self.score),
        }


def score_of(metric: ProjectMetric, scoring: Scoring, *, asserted: bool) -> float | None:
    """What one rollout contributes to ``metric``, or ``None`` where it is not in the denominator.

    ``asserted`` is whether a value was put forward, which is ``rollout.asserted`` end
    to end and whether a node's output holds an absence when the figure is per node.

    Absence is read here, so ``score`` is handed two asserted values under every ``Over`` but
    ``ALL``.
    """
    if scores_this_rollout(metric, scoring, asserted=asserted):
        return _scored(metric, scoring)
    if metric.over is Over.VALUE_EXISTS and not isinstance(scoring.expected, Unknown):
        return 0.0
    return None


def scores_this_rollout(metric: Any, scoring: Scoring, *, asserted: bool) -> bool:
    """Whether the project's own function is called for this rollout, or ``over`` decides it.

    ``metric`` is a ``ProjectMetric`` or a ``ProjectRatio``: what this reads is the ``over``
    each declares. Under every ``Over`` but ``ALL`` a rollout that put no value forward is
    decided without the function, so a figure built entirely from such rollouts describes
    ``over`` rather than the answers. That is what a do-nothing baseline produces on a figure
    measuring what the agent refrained from::

        scores_this_rollout(avoided_share, scoring, asserted=False)   # False
    """
    if metric.over is Over.ALL:
        return True
    return asserted and not isinstance(scoring.expected, Unknown)


def _scored(metric: ProjectMetric, scoring: Scoring) -> float | None:
    try:
        value = metric.score(scoring)
    except JudgementMissing:
        # The figure asked for a judgement nothing has made. The rollout leaves this metric's
        # denominator for now and the request is collected, so one pass names every judgement
        # outstanding; `EvalSuite.run` refuses before any of this is reported.
        return None
    except Exception as exc:
        raise ConfigurationError(
            f"Metric {metric.name!r} raised {type(exc).__name__} scoring rollout "
            f"{scoring.rollout} of example {scoring.example.id!r}: {exc}\n"
            f"Its score function is called once per rollout in its denominator, so it has to "
            f"return a number for every one of them. Declare over=Over.ASSERTED to leave out "
            f"the rollouts that put no value forward."
        ) from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(
            f"Metric {metric.name!r} returned {value!r} scoring rollout {scoring.rollout} of "
            f"example {scoring.example.id!r}. A metric is a number, averaged over examples and "
            f"resampled for its interval.\n"
            f"Return a float. A comparison that is already yes-or-no belongs in matches=, "
            f"which decides whether the rollout was correct."
        )
    return float(value)


def project_scores(
    outcomes: Sequence[RolloutOutcome],
    names: Sequence[str],
    *,
    population: Callable[[RolloutOutcome], bool] = inside,
) -> dict[str, dict[str, list[float]]]:
    """Each project metric's recorded per-rollout scores, keyed by name then by example id.

    The scores are read off the rollouts rather than recomputed, so a results file carries its
    own numbers and a comparison between two of them needs neither the label nor the scoring
    function. An example whose rollouts all fell outside a metric's denominator is absent from
    it rather than scoring zero.

    A rollout that got no answer out of the backend is outside every denominator, so it is
    left out here too.
    """
    by_example: dict[str, list[RolloutOutcome]] = {}
    for rollout in outcomes:
        if population(rollout):
            by_example.setdefault(rollout.example_id, []).append(rollout)

    found: dict[str, dict[str, list[float]]] = {}
    for name in names:
        per_example: dict[str, list[float]] = {}
        for example_id, rollouts in by_example.items():
            scores = [
                float(r.scores[name])
                for r in sorted(rollouts, key=lambda r: r.rollout)
                if name in r.scores
            ]
            if scores:
                per_example[example_id] = scores
        found[name] = per_example
    return found


def unanswered_rollouts(
    outcomes: Sequence[RolloutOutcome], expects_absence: Mapping[str, bool]
) -> dict[str, dict[str, int]]:
    """How many rollouts each metric left out, keyed by metric name and then by cause.

    A denominator that shrank without saying so reads as a measurement over the whole split::

        unanswered_rollouts(results.rollouts, results.expects_absence)["recall"]
        # {'no_response': 6}

    Counted over the examples the metric's figure is over, so ``recall`` counts only the
    examples where a value exists.
    """
    counted: dict[str, dict[str, int]] = {}
    for name, (_, _, _, over) in _SPECS.items():
        counted[name] = _by_cause(outcomes, expects_absence, over)
    return counted


def _by_cause(
    outcomes: Sequence[RolloutOutcome],
    expects_absence: Mapping[str, bool],
    over: _Population,
) -> dict[str, int]:
    """The causes that left rollouts out of one population, and how many each left out."""
    found: dict[str, int] = {}
    for rollout in outcomes:
        if inside(rollout):
            continue
        if not over(bool(expects_absence.get(rollout.example_id, False))):
            continue
        for cause in causes_of(rollout):
            found[cause] = found.get(cause, 0) + 1
    return found


def unanswered_for(
    metric: "ProjectMetric | ProjectRatio",
    outcomes: Sequence[RolloutOutcome],
    expects_absence: Mapping[str, bool],
) -> dict[str, int]:
    """The same counts for one project metric, read off its ``over``."""
    over = _EVERY_EXAMPLE if metric.over is Over.ALL else _WHERE_A_VALUE_EXISTS
    return _by_cause(outcomes, expects_absence, over)


def scores_by_metric(
    outcomes: Sequence[RolloutOutcome],
    expects_absence: Mapping[str, bool],
    *,
    population: Callable[[RolloutOutcome], bool] = inside,
) -> dict[str, dict[str, list[float]]]:
    """Each metric's per-rollout scores, keyed by metric name and then by example id.

    An example contributes to a metric only where its rollouts fall inside that metric's
    denominator, so an example the agent never asserted on is absent from
    ``precision_when_asserting`` rather than scoring zero there::

        scores = scores_by_metric(results.rollouts, {"q1": False, "q2": True})
        scores["recall"]["q1"]   # [1.0, 0.0, 1.0]

    This is what an interval is taken over and what a comparison between two evaluations pairs
    on, so both read the same numbers.

    A rollout that got no answer out of the backend is outside every denominator here, and
    :func:`unanswered_rollouts` counts what was left out.
    """
    by_example: dict[str, list[RolloutOutcome]] = {}
    for rollout in outcomes:
        if population(rollout):
            by_example.setdefault(rollout.example_id, []).append(rollout)

    found: dict[str, dict[str, list[float]]] = {}
    for name, (_, included, scored, _) in _SPECS.items():
        per_example: dict[str, list[float]] = {}
        for example_id, rollouts in by_example.items():
            absence = bool(expects_absence.get(example_id, False))
            scores = [
                scored(r, absence)
                for r in sorted(rollouts, key=lambda r: r.rollout)
                if included(r, absence)
            ]
            if scores:
                per_example[example_id] = scores
        found[name] = per_example
    return found


def aggregate(
    outcomes: Sequence[RolloutOutcome],
    expects_absence: Mapping[str, bool],
    *,
    project: Sequence["ProjectMetric | ProjectRatio"] = (),
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> dict[str, Metric]:
    """The eight rates over a set of rollouts, and any project metric beside them, keyed by name.

    ``expects_absence`` says, for each example id, whether its correct answer is that the
    value is not there. That is what separates a right abstention from a missed value::

        metrics = aggregate(results.rollouts, {"q1": False, "q2": True}, seed=41)
        metrics["recall"].value

    A metric in ``project`` is aggregated from the scores already recorded on each rollout, so
    the scoring function is not called again here.

    Rollouts are grouped by example, and each metric's interval is computed over the examples
    that its denominator includes. A rollout that got no answer out of the backend is in none
    of them, and every metric carries the count of those it left out.
    """
    scores = scores_by_metric(outcomes, expects_absence)
    unanswered = unanswered_rollouts(outcomes, expects_absence)
    # The same figure over the rollouts that produced an answer, including the ones left out
    # for a reason that leaves one, so the narrower number cannot be read without the wider.
    wider = scores_by_metric(outcomes, expects_absence, population=scorable)

    metrics: dict[str, Metric] = {}
    for name, (population, _, _, _) in _SPECS.items():
        metrics[name] = _metric(
            name=name,
            definition=METRIC_DEFINITIONS[name],
            population=population,
            grouped=list(scores[name].values()),
            including=list(wider[name].values()),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
            left_out=unanswered[name],
        )

    metrics.update(
        _project_metrics(
            outcomes,
            expects_absence,
            project=project,
            confidence=confidence,
            resamples=resamples,
            seed=seed,
        )
    )
    return metrics


def _project_metrics(
    outcomes: Sequence[RolloutOutcome],
    expects_absence: Mapping[str, bool],
    *,
    project: Sequence[Any],
    confidence: float,
    resamples: int,
    seed: int,
) -> dict[str, Metric]:
    """Every figure the project declared, whether it is a mean over examples or a ratio."""
    # Imported here rather than at module level: a ratio is declared in terms of this module's
    # `Metric` and `Over`, so the two halves genuinely refer to each other.
    from .ratios import ProjectRatio, ratio_metric, ratio_pairs

    means = [m for m in project if isinstance(m, ProjectMetric)]
    ratios = [m for m in project if isinstance(m, ProjectRatio)]

    names = [m.name for m in means]
    recorded = project_scores(outcomes, names)
    also = project_scores(outcomes, names, population=scorable)
    found = {
        declared.name: _metric(
            name=declared.name,
            definition=declared.definition,
            population=declared.population,
            grouped=list(recorded[declared.name].values()),
            including=list(also[declared.name].values()),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
            unit=declared.unit,
            over=declared.over.value,
            left_out=unanswered_for(declared, outcomes, expects_absence),
        )
        for declared in means
    }

    pairs = ratio_pairs(outcomes, [m.name for m in ratios])
    for declared in ratios:
        found[declared.name] = ratio_metric(
            declared=declared,
            grouped=list(pairs[declared.name].values()),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
            left_out=unanswered_for(declared, outcomes, expects_absence),
        )
    return found


def metrics_over(
    outcomes: Sequence[RolloutOutcome],
    expects_absence: Mapping[str, bool],
    *,
    like: Mapping[str, Metric],
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> dict[str, Metric]:
    """The same figures over a subset of rollouts, keyed by name.

    ``like`` is a set of figures already computed, and every project metric it names is
    computed again here from the scores the rollouts carry. Each figure takes its definition,
    population and unit from the one it is named after, so a subset reports what the whole
    reported::

        cell = metrics_over(shelve_rollouts, results.expects_absence, like=results.metrics)
        cell["accuracy"].interval.point

    The eight rates are always present. A project metric whose scoring function is not at hand
    needs none: its per-rollout scores were written when the evaluation ran.
    """
    metrics = aggregate(
        outcomes, expects_absence, confidence=confidence, resamples=resamples, seed=seed
    )
    # Imported here for the reason `_project_metrics` gives: the two halves refer to each other.
    from .ratios import is_ratio, ratios_over

    metrics.update(
        ratios_over(outcomes, like=like, confidence=confidence, resamples=resamples, seed=seed)
    )
    names = [name for name in like if name not in _SPECS and not is_ratio(like[name])]
    recorded = project_scores(outcomes, names)
    also = project_scores(outcomes, names, population=scorable)
    for name in names:
        declared = like[name]
        over = (
            _EVERY_EXAMPLE
            if declared.population == _OVER_POPULATIONS[Over.ALL]
            else _WHERE_A_VALUE_EXISTS
        )
        metrics[name] = _metric(
            name=name,
            definition=declared.definition,
            population=declared.population,
            grouped=list(recorded[name].values()),
            including=list(also[name].values()),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
            unit=declared.unit,
            left_out=_by_cause(outcomes, expects_absence, over),
        )
    return metrics


def criteria_over(
    outcomes: Sequence[RolloutOutcome],
    *,
    like: Mapping[str, Metric],
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> dict[str, Metric]:
    """One figure per condition over a subset of rollouts, keyed by criterion id.

    ``like`` is the set already computed, and each condition takes its text from there, so a
    subset says what was measured rather than only which id::

        criteria_over(shelve_rollouts, like=results.criteria)["not_read"].interval.point
    """
    scores = criterion_scores(outcomes)
    absences = criterion_absences(outcomes)
    return {
        name: _metric(
            name=name,
            definition=like[name].definition,
            population=CRITERION_POPULATION,
            grouped=list(scores.get(name, {}).values()),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
            absent=absences.get(name, 0),
        )
        for name in like
    }


def criterion_scores(
    outcomes: Sequence[RolloutOutcome],
    *,
    population: Callable[[RolloutOutcome], bool] = inside,
) -> dict[str, dict[str, list[float]]]:
    """Each criterion's per-rollout verdicts, keyed by criterion id then by example id.

    The shape an interval is taken over and what a comparison between two evaluations pairs
    on, as :func:`scores_by_metric` is for the eight rates::

        criterion_scores(results.rollouts)["under_400_pages"]["q4"]   # [1.0, 0.0, 1.0]

    A rollout judged against no criterion contributes nothing: one that abstained, failed, or
    never got an answer out of the backend carries no verdict. A rollout that did not meet a
    condition because it asserted nothing about it scores 0.0 for that condition, as any other
    unmet condition does; how many did that is :func:`criterion_absences`.
    """
    by_example: dict[str, list[RolloutOutcome]] = {}
    for rollout in outcomes:
        if population(rollout):
            by_example.setdefault(rollout.example_id, []).append(rollout)

    found: dict[str, dict[str, list[float]]] = {}
    for example_id, rollouts in by_example.items():
        for rollout in sorted(rollouts, key=lambda r: r.rollout):
            if rollout.verdict is None:
                continue
            for criterion_id, met in rollout.verdict.parts.items():
                found.setdefault(criterion_id, {}).setdefault(example_id, []).append(
                    1.0 if met is True else 0.0
                )
    return found


def criterion_absences(outcomes: Sequence[RolloutOutcome]) -> dict[str, int]:
    """How many scored rollouts left each criterion unmet by saying nothing, by criterion id.

    Inside that criterion's denominator, and unmet, so this says how much of the shortfall is
    the agent saying nothing rather than the agent being wrong. A criterion declaring
    ``expects_absence`` is met by silence, so silence there is not counted::

        criterion_absences(results.rollouts)["po_number"]   # 12
    """
    found: dict[str, int] = {}
    for rollout in outcomes:
        if not inside(rollout) or rollout.verdict is None:
            continue
        for criterion_id in rollout.verdict.absent:
            found[criterion_id] = found.get(criterion_id, 0) + 1
    return found


def criterion_metrics(
    outcomes: Sequence[RolloutOutcome],
    texts: Mapping[str, str],
    named_by_example: Mapping[str, Sequence[str]],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> dict[str, Metric]:
    """How often each criterion was met, keyed by criterion id.

    One figure per condition, over the rollouts that were judged against it, with its own
    interval and its own n. The criterion's text is its definition, so a report says what was
    measured rather than only which id::

        results.criteria["not_already_read"].interval.point   # 0.61
        results.criteria["not_already_read"].definition       # 'a book the reader has not read'

    A criterion two examples both name is one figure over both of them. This is what makes a
    decomposed answer key worth writing: the grade says how much of the key an answer met, and
    these say which part of it the agent keeps missing.

    A rollout that abstained, failed, or did not measure the agent was judged against no
    criterion and is outside every one of these. ``left_out`` carries the causes of the last of
    those, over the examples naming that criterion.

    ``absent`` carries how many of the rollouts inside the figure did not meet the condition
    because they asserted nothing about it. They are unmet and inside the denominator, so a
    figure of 0.61 with 12 absences says the agent was wrong about this condition less often
    than the shortfall suggests and silent about it more often. Silence that met a condition
    declaring ``expects_absence`` is not a shortfall and is not counted.
    """
    scores = criterion_scores(outcomes)
    wider = criterion_scores(outcomes, population=scorable)
    absences = criterion_absences(outcomes)
    found: dict[str, Metric] = {}
    for criterion_id, text in texts.items():
        named = named_by_example
        found[criterion_id] = _metric(
            name=criterion_id,
            definition=text,
            population=CRITERION_POPULATION,
            grouped=list(scores.get(criterion_id, {}).values()),
            including=list(wider.get(criterion_id, {}).values()),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
            left_out=_causes_of(
                [
                    rollout
                    for rollout in outcomes
                    if criterion_id in (named.get(rollout.example_id) or ())
                ]
            ),
            absent=absences.get(criterion_id, 0),
        )
    return found


def _causes_of(outcomes: Sequence[RolloutOutcome]) -> dict[str, int]:
    """The causes that left any of these rollouts outside a denominator, and how many each."""
    found: dict[str, int] = {}
    for rollout in outcomes:
        for cause in causes_of(rollout):
            found[cause] = found.get(cause, 0) + 1
    return found


def _metric(
    *,
    name: str,
    definition: str,
    population: str,
    grouped: list[list[float]],
    confidence: float,
    resamples: int,
    seed: int,
    unit: str | None = RATE,
    over: str | None = None,
    left_out: dict[str, int] | None = None,
    including: list[list[float]] | None = None,
    absent: int = 0,
) -> Metric:
    left_out = dict(left_out or {})
    common: dict[str, Any] = {
        "name": name,
        "definition": definition,
        "population": population,
        "unit": unit,
        "over": over,
        "left_out": left_out,
        "absent": absent,
        # Taken before the undefined branch: a figure whose whole denominator was left out is
        # where the wider one is the only number there is, and dropping it there would report
        # nothing at all about rollouts that did produce answers.
        "including_left_out": (
            bootstrap_ci(including, confidence=confidence, resamples=resamples, seed=seed)
            if including and including != grouped
            else None
        ),
    }
    if not grouped:
        unanswered = f" {_causes(left_out)} are outside it." if left_out else ""
        return Metric(
            rollouts=0,
            examples=0,
            reason=f"No rollouts fall under {population}, so this figure has no "
            f"denominator.{unanswered}",
            **common,
        )
    return Metric(
        rollouts=sum(len(scores) for scores in grouped),
        examples=len(grouped),
        interval=bootstrap_ci(grouped, confidence=confidence, resamples=resamples, seed=seed),
        rollout_noise=rollout_noise(grouped),
        **common,
    )


def _causes(left_out: Mapping[str, int]) -> str:
    """The causes and their counts, as words, for a figure that has no denominator left.

    The total is printed only where there is more than one cause, since with one it is the
    same number twice.
    """
    named = ", ".join(
        f"{count} rollout(s) {LEFT_OUT_CAUSES.get(cause, cause)}"
        for cause, count in sorted(left_out.items())
    )
    if len(left_out) < 2:
        return named
    return f"{sum(left_out.values())} rollout(s) did not measure the agent: {named}"
