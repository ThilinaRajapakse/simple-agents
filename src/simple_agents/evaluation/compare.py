"""Whether a change moved a metric, or whether the difference is sampling.

Two point estimates invite a comparison the data does not support: 62% against 68% over twenty
examples is a difference the same agent produces twice in a row. What answers the question is
an interval on the **paired difference**, example by example, which cancels the fact that some
examples are simply harder than others and leaves the effect of the change.

The pairing is on the example id, so the comparison refuses two evaluations computed over
different example sets rather than reporting a number that mixes a change to the agent with a
change to what it was asked.
"""

from __future__ import annotations

import math
import textwrap
from functools import partial
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any

from ..errors import ConfigurationError
from .intervals import (
    DEFAULT_CONFIDENCE,
    DEFAULT_RESAMPLES,
    Interval,
    _z_for,
    bootstrap_ci,
)
from .declared import config_differences
from .metrics import (
    METRIC_DEFINITIONS,
    criterion_scores,
    project_scores,
    scores_by_metric,
)
from .per_node import ACCURACY_DEFINITION, REACH_DEFINITION, node_scores
from .ratios import ratio_changes
from .results import EvalResults

__all__ = [
    "COMPARISON_FORMAT_VERSION",
    "against_baseline",
    "MetricChange",
    "NodeChange",
    "Comparison",
    "compare",
    "MINIMUM_EXAMPLES_FOR_A_VERDICT",
]

# JSON, in the `comparison_format_version` field of a written comparison. A comparison nested
# inside a variant sweep carries it too, so a reader can date either file.
COMPARISON_FORMAT_VERSION = "0.1"


PAIRED_METHOD = "percentile bootstrap, resampling examples, on the paired difference"


# Examples, not rollouts: the resampling unit is the example, and k rollouts of one example
# travel together. Below this the interval's endpoints come from too few distinct resamples to
# carry a verdict, and where every example moves the same way the interval has zero width and
# reads as certainty. `moved` is `None` there rather than `True` or `False`.
MINIMUM_EXAMPLES_FOR_A_VERDICT = 20


@dataclass(frozen=True, slots=True)
class MetricChange:
    """One metric before, after, and whether the difference is larger than the sampling.

    ``difference`` is an interval on the per-example change, so ``moved`` is the question of
    whether it excludes zero::

        change = comparison.metrics["false_confidence_rate"]
        change.before, change.after      # 0.04, 0.16
        change.difference.low            # 0.03
        change.moved                     # True

    ``moved`` is ``None`` where the metric was measured over fewer than
    ``MINIMUM_EXAMPLES_FOR_A_VERDICT`` examples, and ``verdict_reason`` says so. The delta and
    the interval are still reported; what is withheld is the claim that the difference is real.

    ``rule_moved`` holds the two versions of the function that scored the figure, where they
    differ between the two evaluations. That also withholds the verdict: the two sides were
    scored by different rules, so the difference is between the rules as much as between the
    agents.

    ``before_examples`` and ``after_examples`` are how many shared examples fell under the
    metric's denominator on each side. They differ for a metric whose denominator depends on
    what the agent did, such as ``precision_when_asserting`` or a project metric declared
    ``Over.ASSERTED``, and ``population_note`` then says so: ``before`` and ``after`` are over
    different sets of examples and ``difference`` is over the ones in both.
    """

    name: str
    definition: str
    before: float | None
    after: float | None
    examples: int
    difference: Interval | None = None
    reason: str | None = None
    rule_moved: list[Any] | None = None
    before_examples: int = 0
    after_examples: int = 0
    rollout_noise: float | None = None
    """How far this difference moves between two runs of one configuration, as a deviation.

    Each side's figure moves when its own examples are run again, because the agent is
    stochastic, and neither side's interval is over that. The two are independent, so the
    difference's own deviation is the root of the sum of their squares::

        change.difference.point    # -0.040
        change.rollout_noise       # 0.024, so ±0.047 at 95%

    ``None`` where neither side ran an example more than once. A difference inside this is
    what running the same thing twice produces, so ``moved`` is withheld rather than reported
    ``True``, and ``verdict_reason`` says so.
    """

    @property
    def inside_the_noise(self) -> bool:
        """Whether this difference is no larger than running the same configuration twice.

        Read at the difference's own confidence, so this and the interval beside it are the
        same kind of claim. A difference of zero is inside the noise and is not in doubt: what
        this changes is a difference the interval would otherwise attribute to the change.
        """
        if self.difference is None or not self.rollout_noise:
            return False
        return abs(self.difference.point) <= self.noise_half_width

    @property
    def noise_half_width(self) -> float:
        """How far this difference has to be from zero to be more than rollout noise."""
        if self.difference is None or not self.rollout_noise:
            return 0.0
        return _z_for(self.difference.confidence) * self.rollout_noise

    @property
    def moved(self) -> bool | None:
        """Whether the interval on the difference excludes no change at all.

        ``None`` where nothing supports a verdict: no shared examples carry the metric, too
        few do for the interval to answer, the rule that scored the two sides is not the same
        rule, or the interval excludes zero over a difference no larger than what one
        configuration produces twice. ``reason`` or ``verdict_reason`` says which.

        A difference whose interval already includes zero is ``False`` whatever the noise: the
        answer is that nothing moved, and the noise is why rather than a doubt about it.
        """
        if self.difference is None:
            return None
        if self.rule_moved is not None:
            return None
        if self.difference.n < MINIMUM_EXAMPLES_FOR_A_VERDICT:
            return None
        if not self.difference.excludes(0.0):
            return False
        return None if self.inside_the_noise else True

    @property
    def verdict_reason(self) -> str | None:
        """Why ``moved`` is ``None``, or ``None`` when it carries a verdict.

        In the order :attr:`moved` decides, so the reason given is the one that withheld the
        verdict rather than another that also applies.
        """
        if self.moved is not None or self.difference is None:
            return None
        if self.rule_moved is not None:
            return (
                f"The rule that scored this figure changed between the two evaluations, "
                f"{self.rule_moved[0]} to {self.rule_moved[1]}, so the two sides were scored "
                f"differently and the difference is between the rules as much as between the "
                f"agents. Re-run the earlier evaluation under the current rule and compare "
                f"that."
            )
        if self.difference.n < MINIMUM_EXAMPLES_FOR_A_VERDICT:
            return (
                f"{self.difference.n} example(s) carry this metric and a verdict needs "
                f"{MINIMUM_EXAMPLES_FOR_A_VERDICT}. The interval is reported and the "
                f"difference between the two runs is real; whether it would hold on other "
                f"examples is what this many cannot say. Where every example moves the same "
                f"way the interval has zero width, which reads as certainty and is the sample "
                f"having no variation to resample."
            )
        return (
            f"The interval on this difference excludes zero, and the difference is "
            f"{self.difference.point:+.3f} against ±{self.noise_half_width:.3f} that two "
            f"runs of one configuration produce on these same examples. A difference this "
            f"size is what running the same thing twice gives, so it is not attributable "
            f"to the change. Raise k, widen the example set, or read this as unmoved."
        )

    @property
    def population_note(self) -> str | None:
        """Why ``before`` and ``after`` are not two readings of one quantity, or ``None``.

        A metric whose denominator depends on the agent's own behaviour covers a different set
        of examples on each side, so its two point estimates can move while every example in
        both moves by nothing. ``difference`` is the paired change and is the figure to read.
        """
        if self.before_examples == self.after_examples:
            return None
        return (
            f"{self.name} covered {self.before_examples} of the shared examples in the earlier "
            f"evaluation and {self.after_examples} in the later one, because its denominator "
            f"depends on what the agent did. So `before` and `after` are over different sets "
            f"of examples and the gap between them is partly which examples fell under the "
            f"metric. `difference` is over the {self.examples} in both, and is the change."
        )

    @property
    def delta(self) -> float | None:
        """The point estimate of the change, positive when the metric rose."""
        return self.difference.point if self.difference is not None else None

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "definition": self.definition,
            "before": self.before,
            "after": self.after,
            "examples": self.examples,
            "before_examples": self.before_examples,
            "after_examples": self.after_examples,
            "population_note": self.population_note,
            "moved": self.moved,
            "rollout_noise": self.rollout_noise,
            "verdict_reason": self.verdict_reason,
            "rule_moved": self.rule_moved,
            "difference": (self.difference.to_record() if self.difference is not None else None),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class NodeChange:
    """One node's reach and accuracy, before and after.

    ``reach`` is reported beside ``accuracy`` always, because a per-node number that moved
    because routing sent fewer rollouts through the node is a different finding from one that
    moved because the node got worse::

        change = comparison.nodes["verify"]
        change.reach.moved        # True: fewer rollouts reach it now
        change.accuracy.moved     # False: it is as right as it was, on fewer runs

    ``metrics`` holds the project metrics declared for this node, compared the same way::

        change.metrics["span_f1"].delta
    """

    node_id: str
    reach: MetricChange
    accuracy: MetricChange | None = None
    metrics: dict[str, MetricChange] = field(default_factory=dict)

    @property
    def moved(self) -> bool | None:
        """Whether any figure moved, or ``None`` where none of them carries a verdict."""
        verdicts = [
            self.reach.moved,
            self.accuracy.moved if self.accuracy else False,
            *(change.moved for change in self.metrics.values()),
        ]
        if any(v is True for v in verdicts):
            return True
        return None if any(v is None for v in verdicts) else False

    def to_record(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "reach": self.reach.to_record(),
            "accuracy": self.accuracy.to_record() if self.accuracy is not None else None,
            "metrics": {name: c.to_record() for name, c in self.metrics.items()},
        }


@dataclass(frozen=True, slots=True)
class Comparison:
    """What changed between two evaluations, and what changed about the evaluations.

    ``moved`` names the metrics whose interval on the difference excludes zero. ``changed``
    names what differed in configuration, so a moved metric has a candidate cause rather than
    only a number::

        comparison = compare(before, after)
        comparison.moved              # ['false_confidence_rate']
        comparison.undecided          # ['recall']: too few examples carry it
        comparison.moved_nodes        # ['verify']
        comparison.changed            # {'prompts.hunt': ['sha256:9f2c…', 'sha256:41ab…']}
    """

    metrics: dict[str, MetricChange]
    shared: tuple[str, ...]
    only_before: tuple[str, ...]
    only_after: tuple[str, ...]
    changed: dict[str, list[Any]]
    nodes: dict[str, NodeChange] = field(default_factory=dict)
    criteria: dict[str, MetricChange] = field(default_factory=dict)
    """How each criterion moved, keyed by criterion id, for a decomposed answer key.

    Kept apart from ``metrics`` rather than mixed into it, so a criterion id can be anything
    the project finds readable without colliding with a rate or a project metric::

        comparison.criteria["not_already_read"].delta   # +0.18
        comparison.moved_criteria                       # ['not_already_read']

    A criterion only one side names has nothing to pair against and is absent here.
    """

    groups: dict[Any, "Comparison"] = field(default_factory=dict)
    """The same comparison over each cell of a grouping, keyed by the cell's value.

    Filled by ``compare(before, after, group_by=...)`` and empty otherwise. A change that
    helped one kind of example and hurt another reports no movement pooled, because the
    prevalence of the two cancels them::

        comparison = compare(before, after, group_by="label")
        comparison.metrics["accuracy"].moved            # False, pooled
        comparison.groups["shelve"].metrics["accuracy"].delta   # +0.21
        comparison.groups["skip"].metrics["accuracy"].delta     # -0.19

    Each cell is a full comparison over its own examples, so it carries its own verdict and
    withholds one where the cell is too small (``MINIMUM_EXAMPLES_FOR_A_VERDICT``). A cell's
    own ``groups`` is empty; grouping does not nest.
    """

    @property
    def moved(self) -> list[str]:
        """The metrics whose difference excludes zero, over enough examples to say so.

        A metric measured over too few examples is in ``undecided`` rather than here.
        """
        return [name for name, change in self.metrics.items() if change.moved is True]

    @property
    def undecided(self) -> list[str]:
        """The metrics that carry no verdict: too few examples, or none at all.

        ``metrics[name].verdict_reason`` says how many it had and how many it needed, and
        ``metrics[name].reason`` covers one with no examples to pair.
        """
        return [name for name, change in self.metrics.items() if change.moved is None]

    @property
    def moved_criteria(self) -> list[str]:
        """The criteria whose difference excludes zero, over enough examples to say so."""
        return [name for name, change in self.criteria.items() if change.moved is True]

    @property
    def moved_nodes(self) -> list[str]:
        """The nodes whose reach or accuracy moved."""
        return [node_id for node_id, change in self.nodes.items() if change.moved is True]

    @property
    def population_changed(self) -> list[str]:
        """The metrics that covered different examples on each side.

        Their ``before`` and ``after`` are not two readings of one quantity, and
        ``metrics[name].population_note`` says which figure to read instead.
        """
        return [name for name, change in self.metrics.items() if change.population_note is not None]

    def report(self) -> str:
        """The comparison as text, for reading rather than parsing::

            print(compare(before, after).report())

        Every metric with both point estimates, the paired difference and its interval, and
        whether it moved. A metric with no verdict prints why, and one whose denominator moved
        prints its ``population_note``, so a table read off this cannot show two point
        estimates over different sets of examples as though they were two readings of one.
        """
        width = max((len(name) for name in self.metrics), default=0)
        lines = [
            f"{len(self.shared)} shared example(s)",
            "",
            f"  {'metric':<{width}}  {'before':>7}    {'after':>7}  {'change':>7}  "
            f"{'interval':<18}  verdict",
        ]
        for name, change in self.metrics.items():
            verdict = {True: "moved", False: "no", None: "undecided"}[change.moved]
            band = (
                f"[{change.difference.low:+.3f}, {change.difference.high:+.3f}]"
                if change.difference is not None
                else "-"
            )
            lines.append(
                f"  {name:<{width}}  {_point(change.before)} -> {_point(change.after)}  "
                f"{_point(change.delta, signed=True)}  {band:<18}  {verdict}"
            )
            for note in (change.verdict_reason, change.population_note):
                if note:
                    lines += [f"  {'':<{width}}  {line}" for line in _wrapped(note)]

        if self.nodes:
            lines += ["", "  node        reach                 accuracy"]
            for node_id, change in self.nodes.items():
                lines.append(
                    f"  {node_id:<11} {_point(change.reach.delta, signed=True):<21} "
                    f"{_point(change.accuracy.delta if change.accuracy else None, signed=True)}"
                )

        if self.only_before or self.only_after:
            lines += [
                "",
                f"  {len(self.only_before)} example(s) only in the earlier evaluation, "
                f"{len(self.only_after)} only in the later one",
            ]
        if self.changed:
            lines += ["", "  configuration differences:"]
            lines += [f"    {key}: {value}" for key, value in sorted(self.changed.items())]
        return "\n".join(lines)

    def to_record(self) -> dict[str, Any]:
        """What a comparison writes out.

        Every figure it computed, including the per-criterion changes and each cell of a
        grouping, so a reader of the file sees what a reader of the object sees.
        """
        return {
            "comparison_format_version": COMPARISON_FORMAT_VERSION,
            "shared_examples": len(self.shared),
            "only_before": list(self.only_before),
            "only_after": list(self.only_after),
            "changed": self.changed,
            "moved": self.moved,
            "undecided": self.undecided,
            "moved_criteria": self.moved_criteria,
            "moved_nodes": self.moved_nodes,
            "population_changed": self.population_changed,
            "metrics": {name: c.to_record() for name, c in self.metrics.items()},
            "criteria": {name: c.to_record() for name, c in self.criteria.items()},
            "nodes": {node_id: c.to_record() for node_id, c in self.nodes.items()},
            "groups": {str(value): cell.to_record() for value, cell in self.groups.items()},
        }


def compare(
    before: EvalResults,
    after: EvalResults,
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
    allow_different_sets: bool = False,
    group_by: str | None = None,
) -> Comparison:
    """Whether the metrics moved between two evaluations, on the examples both ran.

    ::

        comparison = compare(
            EvalResults.read("evals/results/held-out-v2.json"),
            EvalResults.read("evals/results/held-out-v3.json"),
        )
        for name in comparison.moved:
            change = comparison.metrics[name]
            print(name, change.before, "->", change.after, change.difference.point)

    Each example's mean is taken over its own rollouts on each side, the difference is taken
    per example, and the interval is a bootstrap over those differences. An example present on
    only one side is left out and named.

    Two evaluations computed over different example sets are refused, because the difference
    would mix a change to the agent with a change to what it was asked. Pass
    ``allow_different_sets=True`` where the sets genuinely differ and only the shared examples
    are wanted.

    ``group_by`` names a property of the example, and fills ``groups`` with the same comparison
    over each of its cells. A pooled difference hides a change that helped one kind of example
    and hurt another::

        comparison = compare(before, after, group_by="label")
        comparison.groups["skip"].metrics["accuracy"].delta

    ``EvalResults.groupable()`` says which keys an evaluation carries.
    """
    _refuse_mismatched_sets(before, after, allow_different_sets=allow_different_sets)

    project = _project_names(before, after)
    before_scores = _all_scores(before.rollouts, before.expects_absence, project)
    after_scores = _all_scores(after.rollouts, after.expects_absence, project)

    before_ids = {r.example_id for r in before.rollouts}
    after_ids = {r.example_id for r in after.rollouts}
    shared = tuple(sorted(before_ids & after_ids))
    if not shared:
        raise ConfigurationError(
            f"These two evaluations share no examples: {len(before_ids)} in the earlier one "
            f"and {len(after_ids)} in the later one, with no id in both. There is nothing to "
            f"pair, so no difference can be attributed to the change.\n"
            f"Compare evaluations run over the same example set, or the same split of it."
        )

    rules, criterion_rules = _rules(before, after)
    change = partial(_change, shared=shared, confidence=confidence, resamples=resamples, seed=seed)
    # Built first, because a ratio is paired on its recorded totals rather than on scores and
    # `_change` would report one as having nothing to pair.
    ratios = ratio_changes(
        before,
        after,
        shared,
        confidence=confidence,
        resamples=resamples,
        seed=seed,
        rules=rules,
    )
    metrics = {
        name: change(
            name=name,
            before=before_scores.get(name, {}),
            after=after_scores.get(name, {}),
            before_metric=before.metrics.get(name),
            after_metric=after.metrics.get(name),
            rule_moved=rules.get(name),
            definition=_definition_of(name, before, after),
        )
        for name in (*METRIC_DEFINITIONS, *project)
        if name not in ratios
    }
    metrics.update(ratios)

    before_criteria = criterion_scores(before.rollouts)
    after_criteria = criterion_scores(after.rollouts)
    criteria = {
        name: change(
            name=name,
            before=before_criteria.get(name, {}),
            after=after_criteria.get(name, {}),
            before_metric=before.criteria.get(name),
            after_metric=after.criteria.get(name),
            rule_moved=criterion_rules.get(name),
            definition=(after.criteria[name].definition or before.criteria[name].definition),
        )
        for name in before.criteria
        if name in after.criteria
    }

    return Comparison(
        metrics=metrics,
        criteria=criteria,
        shared=shared,
        only_before=tuple(sorted(before_ids - after_ids)),
        only_after=tuple(sorted(after_ids - before_ids)),
        changed=config_differences(before.config, after.config),
        nodes=_nodes(before, after, shared, confidence=confidence, resamples=resamples, seed=seed),
        groups=(
            _by_group(
                before,
                after,
                group_by,
                shared,
                confidence=confidence,
                resamples=resamples,
                seed=seed,
            )
            if group_by is not None
            else {}
        ),
    )


def _by_group(
    before: EvalResults,
    after: EvalResults,
    key: str,
    shared: tuple[str, ...],
    *,
    confidence: float,
    resamples: int,
    seed: int,
) -> dict[Any, Comparison]:
    """One comparison per cell, over the shared examples that fall in it.

    The cells come from the later evaluation, which is the one whose grouping a reader is
    asking about, and an example only the earlier one carries was already out of ``shared``.
    """
    inside_both = set(shared)
    cells: dict[Any, Comparison] = {}
    for value, example_ids in after.groups(key).items():
        wanted = inside_both & set(example_ids)
        if not wanted:
            continue
        cells[value] = compare(
            _only(before, wanted),
            _only(after, wanted),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
            allow_different_sets=True,
        )
    return cells


def _only(results: EvalResults, example_ids: set[str]) -> EvalResults:
    """The same evaluation over one cell of its examples."""
    return replace(
        results,
        rollouts=tuple(r for r in results.rollouts if r.example_id in example_ids),
        examples={k: v for k, v in results.examples.items() if k in example_ids},
    )


def against_baseline(
    results: EvalResults,
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> dict[str, MetricChange]:
    """Whether the agent beat what doing nothing would have scored, figure by figure.

    Paired example by example, as a comparison between two versions is, so an example that is
    simply hard cancels on both sides and what is left is the agent::

        for name, change in against_baseline(results).items():
            print(name, change.delta, change.moved)

    ``before`` on each change is the floor and ``after`` is the agent, so a positive ``delta``
    is the agent ahead. Empty where the suite declared no ``baseline=``. A figure whose
    interval does not clear zero is one the evaluation cannot separate from not trying, which
    is a finding about the measure rather than about the agent.

    ``results.baseline_unscored`` names the figures whose ``before`` the project's own score
    function never saw, so their ``delta`` is against the declaration rather than against an
    answer (`docs/evaluation.md` §4.2).
    """
    if not results.baseline:
        return {}
    floor = results.baseline_metrics(confidence=confidence, resamples=resamples, seed=seed)
    absence = results.expects_absence
    project = tuple(name for name in results.metrics if name not in METRIC_DEFINITIONS)
    doing_nothing = _all_scores(results.baseline, absence, project)
    agent = _all_scores(results.rollouts, absence, project)
    shared = tuple(sorted({r.example_id for r in results.baseline}))
    # A ratio is summed rather than averaged, so its halves are in `ratios` and pairing it on
    # scores finds none: it reported every one as having nothing to pair, over a floor and an
    # agent that both carried it. The rule is the same on both sides, since one evaluation
    # scored them, so no ratio here has a rule to report as moved.
    ratios = ratio_changes(
        SimpleNamespace(metrics=floor, rollouts=results.baseline),
        SimpleNamespace(metrics=results.metrics, rollouts=results.rollouts),
        shared,
        confidence=confidence,
        resamples=resamples,
        seed=seed,
    )
    changed = {
        name: _change(
            name=name,
            before=doing_nothing.get(name, {}),
            after=agent.get(name, {}),
            shared=shared,
            before_metric=floor.get(name),
            after_metric=results.metrics.get(name),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
            definition=_definition_of(name, results, results),
        )
        for name in (*METRIC_DEFINITIONS, *project)
        if name not in ratios
    }
    changed.update(ratios)
    return changed


def _all_scores(rollouts: Any, absence: Any, project: tuple[str, ...]) -> dict[str, Any]:
    """Per-example scores for the eight rates and the project metrics together."""
    return {**scores_by_metric(rollouts, absence), **project_scores(rollouts, project)}


def _project_names(before: EvalResults, after: EvalResults) -> tuple[str, ...]:
    """The project metrics both evaluations report, in the order the earlier one declared them.

    A metric only one side carries has nothing to pair against, and the declaration that added
    or dropped it is already in ``changed`` through ``config.metrics``.
    """
    shipped = set(METRIC_DEFINITIONS)
    return tuple(name for name in before.metrics if name not in shipped and name in after.metrics)


def _definition_of(name: str, before: EvalResults, after: EvalResults) -> str:
    """What the metric says it is, taken from either file, since one may not carry it."""
    if name in METRIC_DEFINITIONS:
        return METRIC_DEFINITIONS[name]
    for results in (after, before):
        metric = results.metrics.get(name)
        if metric is not None and metric.definition:
            return metric.definition
    return ""


def _rules(
    before: EvalResults, after: EvalResults
) -> tuple[dict[str, list[Any]], dict[str, list[Any]]]:
    """Each figure whose scoring rule differs between the two evaluations, and both versions.

    The eight are scored by ``matches`` and by the checks behind whatever criteria the example
    set names, and those decide every outcome the eight read. A project metric is scored by its
    own function. Any of them moving means the two sides were not scored the same way, which a
    difference between them cannot be separated from.

    Returned as two mappings, one keyed by metric name and one by criterion id, because a
    criterion id is the project's own word and may be anything.
    """
    found: dict[str, list[Any]] = {}
    criteria: dict[str, list[Any]] = {}
    earlier = _version(before.config.get("matches"))
    later = _version(after.config.get("matches"))
    if earlier != later:
        for name in METRIC_DEFINITIONS:
            found[name] = [earlier, later]

    # A criterion's check decides an outcome exactly as `matches` does, so one moving moves
    # every rate as well as that criterion's own figure.
    before_criteria = dict(before.config.get("criteria") or {})
    after_criteria = dict(after.config.get("criteria") or {})
    for criterion_id, entry in before_criteria.items():
        if criterion_id not in after_criteria:
            continue
        was, now = _decider(entry), _decider(after_criteria[criterion_id])
        if was != now:
            criteria[criterion_id] = [was, now]
            for name in METRIC_DEFINITIONS:
                found.setdefault(name, [was, now])

    # Every judgement the numbers rested on, whatever figure read it. A criterion's entry
    # above covers a judged condition; this covers a judged figure that is not one, such as a
    # project metric or a node label, which has no entry of its own to compare.
    was = _judgements(before)
    now = _judgements(after)
    if was != now:
        for name in METRIC_DEFINITIONS:
            found.setdefault(name, [was, now])

    declared_before = _declared(before)
    declared_after = _declared(after)
    for name, version in declared_before.items():
        if name in declared_after and declared_after[name] != version:
            found[name] = [version, declared_after[name]]
    return found, criteria


def _declared(results: EvalResults) -> dict[str, Any]:
    """The version of each project metric's score function, off the results file."""
    return {
        str(entry.get("name")): _version(entry)
        for entry in (results.config.get("metrics") or [])
        if isinstance(entry, dict)
    }


def _version(entry: Any) -> Any:
    """What identifies the rule behind one declaration, for comparing two evaluations.

    A ``ProjectRatio`` records a version per half and no ``version`` of its own, so reading
    that key alone reported every ratio as unmoved however its numerator was edited.
    """
    if not isinstance(entry, dict):
        return None
    if entry.get("kind") == "ratio":
        # One string rather than the pair, because `verdict_reason` prints both sides of this
        # into a sentence and a tuple renders there as a tuple.
        return (
            f"numerator {entry.get('numerator_version')}, "
            f"denominator {entry.get('denominator_version')}"
        )
    return entry.get("version")


def _judgements(results: EvalResults) -> Any:
    """The digest of every judgement one evaluation's numbers rested on, or ``None``."""
    entry = results.config.get("judgements")
    return entry.get("judgements") if isinstance(entry, dict) else None


def _decider(entry: Any) -> Any:
    """What decided one criterion, in a form two evaluations can be compared on.

    A coded condition is its check's version. A judged one has no check, and what its figure
    rests on is the judgements, so the digest of them is read instead. A re-judged set, a
    verdict corrected by hand and a different judge each move it, and each withholds the
    verdict on every rate as a moved ``matches`` does.

    **A reworded condition moves it too, without the text being compared.** The condition's
    text is the question the judge was asked and is inside the key each judgement is filed
    under, so rewording it leaves every judgement unfindable, the evaluation cannot be scored
    until they are made again, and the new set has a different digest. There is no pair of
    results files whose judgements agree and whose question does not.
    """
    if not isinstance(entry, dict):
        return None
    if entry.get("decided") == "judged":
        return entry.get("judgements")
    return entry.get("version")


def _nodes(
    before: EvalResults,
    after: EvalResults,
    shared: tuple[str, ...],
    *,
    confidence: float,
    resamples: int,
    seed: int,
) -> dict[str, NodeChange]:
    """Reach and accuracy per node, for the nodes both evaluations ran.

    A node present on one side only is left out: there is nothing to pair it against, and its
    appearance or removal is already in ``changed`` through ``config.nodes``.
    """
    found: dict[str, NodeChange] = {}
    change = partial(_change, shared=shared, confidence=confidence, resamples=resamples, seed=seed)
    for node_id in before.nodes:
        if node_id not in after.nodes:
            continue
        reach = change(
            name="reach",
            before=node_scores(before.rollouts, node_id, kind="reach"),
            after=node_scores(after.rollouts, node_id, kind="reach"),
            before_metric=before.nodes[node_id].reach,
            after_metric=after.nodes[node_id].reach,
            definition=REACH_DEFINITION,
        )
        accuracy_before = node_scores(before.rollouts, node_id, kind="accuracy")
        accuracy_after = node_scores(after.rollouts, node_id, kind="accuracy")
        accuracy = (
            change(
                name="accuracy",
                before=accuracy_before,
                after=accuracy_after,
                before_metric=before.nodes[node_id].accuracy,
                after_metric=after.nodes[node_id].accuracy,
                definition=ACCURACY_DEFINITION,
            )
            if accuracy_before or accuracy_after
            else None
        )
        rules = _node_rules(before, after, node_id)
        # A ratio is summed rather than averaged, so its two counts are in `ratios` and pairing
        # it on scores finds none: it reported every one as having nothing to pair.
        ratios = ratio_changes(
            before,
            after,
            shared,
            confidence=confidence,
            resamples=resamples,
            seed=seed,
            node_id=node_id,
            rules=rules,
        )
        metrics = {
            name: change(
                name=name,
                before=node_scores(before.rollouts, node_id, kind=name),
                after=node_scores(after.rollouts, node_id, kind=name),
                before_metric=before.nodes[node_id].metrics.get(name),
                after_metric=after.nodes[node_id].metrics.get(name),
                definition=before.nodes[node_id].metrics[name].definition,
                rule_moved=rules.get(name),
            )
            for name in before.nodes[node_id].metrics
            if name in after.nodes[node_id].metrics and name not in ratios
        }
        metrics.update(ratios)
        found[node_id] = NodeChange(
            node_id=node_id, reach=reach, accuracy=accuracy, metrics=metrics
        )
    return found


def _node_rules(before: EvalResults, after: EvalResults, node_id: str) -> dict[str, list[Any]]:
    """Each of this node's project metrics whose scoring function differs between the two."""
    earlier = {
        str(entry.get("name")): _version(entry)
        for entry in ((before.config.get("node_metrics") or {}).get(node_id) or [])
        if isinstance(entry, dict)
    }
    later = {
        str(entry.get("name")): _version(entry)
        for entry in ((after.config.get("node_metrics") or {}).get(node_id) or [])
        if isinstance(entry, dict)
    }
    return {
        name: [version, later[name]]
        for name, version in earlier.items()
        if name in later and later[name] != version
    }


def _change(
    *,
    name: str,
    before: dict[str, list[float]],
    after: dict[str, list[float]],
    shared: tuple[str, ...],
    before_metric: Any,
    after_metric: Any,
    confidence: float,
    resamples: int,
    seed: int,
    definition: str | None = None,
    rule_moved: list[Any] | None = None,
) -> MetricChange:
    paired = [
        [_mean(after[example_id]) - _mean(before[example_id])]
        for example_id in shared
        if example_id in before and example_id in after
    ]
    definition = definition if definition is not None else METRIC_DEFINITIONS[name]
    before_value = getattr(before_metric, "value", None)
    after_value = getattr(after_metric, "value", None)
    # How many shared examples the metric covered on each side. These differ where the
    # denominator depends on the agent's behaviour, which is what `population_note` reports.
    before_examples = sum(1 for example_id in shared if example_id in before)
    after_examples = sum(1 for example_id in shared if example_id in after)

    if not paired:
        return MetricChange(
            name=name,
            definition=definition,
            before=before_value,
            after=after_value,
            examples=0,
            reason=(
                f"No shared example falls under {name}'s denominator on both sides, so there "
                f"is nothing to pair."
            ),
            rule_moved=rule_moved,
            before_examples=before_examples,
            after_examples=after_examples,
        )

    interval = bootstrap_ci(paired, confidence=confidence, resamples=resamples, seed=seed)
    # The larger of the two sides, because a difference has to clear the noisier of the runs it
    # was taken between. A figure one side does not report contributes nothing rather than zero.
    noises = [
        getattr(metric, "rollout_noise", None)
        for metric in (before_metric, after_metric)
        if getattr(metric, "rollout_noise", None) is not None
    ]
    combined = math.sqrt(sum(noise**2 for noise in noises)) if noises else None
    return MetricChange(
        name=name,
        definition=definition,
        before=before_value,
        after=after_value,
        examples=len(paired),
        rule_moved=rule_moved,
        before_examples=before_examples,
        after_examples=after_examples,
        rollout_noise=combined,
        difference=Interval(
            point=interval.point,
            low=interval.low,
            high=interval.high,
            n=interval.n,
            k=None,
            confidence=interval.confidence,
            resamples=interval.resamples,
            seed=interval.seed,
            method=PAIRED_METHOD,
        ),
    )


def _refuse_mismatched_sets(
    before: EvalResults, after: EvalResults, *, allow_different_sets: bool
) -> None:
    if allow_different_sets:
        return
    earlier = (before.config.get("example_set") or {}).get("content_hash")
    later = (after.config.get("example_set") or {}).get("content_hash")
    if earlier == later:
        return
    shared = {r.example_id for r in before.rollouts} & {r.example_id for r in after.rollouts}
    raise ConfigurationError(
        f"These two evaluations were computed over different example sets: {earlier} and "
        f"{later}, sharing {len(shared)} example id(s). A difference between them mixes a "
        f"change to the agent with a change to what it was asked, and the reader cannot tell "
        f"which moved the number.\n"
        f"Re-run the earlier evaluation against the current set, or pass "
        f"allow_different_sets=True to compare the shared examples and accept that the sets "
        f"differ."
    )


def _mean(scores: list[float]) -> float:
    return sum(scores) / len(scores)


def _point(value: float | None, *, signed: bool = False) -> str:
    """One figure as the report prints it, or a dash where there is none."""
    if value is None:
        return f"{'-':>7}"
    return f"{value:>+7.3f}" if signed else f"{value:>7.3f}"


def _wrapped(note: str, width: int = 84) -> list[str]:
    """A note broken into lines the report can indent under a metric."""
    return textwrap.wrap(note, width=width) or [""]
