"""The results artifact: what an evaluation reported, and everything needed to check it.

A results file is written once and read many times: by whoever reads the number, by the
conformance checks, and by a later comparison between two versions. It therefore carries the
configuration the number came from as well as the number, so a reader can tell what was
measured without the code that measured it.

Current version: ``0.32``, in the ``eval_format_version`` field. A file written at or
above ``EVAL_FORMAT_FLOOR`` is read, and a figure that cannot be derived from an older one
says so rather than reporting nothing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..cost import Cost
from ..errors import ConfigurationError
from .examples import ContaminationReport, Overlap
from .intervals import DEFAULT_CONFIDENCE, DEFAULT_RESAMPLES, _z_for
from .metrics import (
    LEFT_OUT_CAUSES,
    NO_RESPONSE,
    RATE,
    Metric,
    criteria_over,
    inside,
    metrics_over,
)
from .outcomes import RolloutOutcome
from .per_node import NodeMetrics, unfinished_lines

__all__ = ["EVAL_FORMAT_FLOOR", "EVAL_FORMAT_VERSION", "EvalResults", "Group"]

EVAL_FORMAT_VERSION = "0.32"

EVAL_FORMAT_FLOOR = "0.28"
"""The oldest results file this library reads.

A results file is additive by default, so a field this version writes is absent from an
older one rather than different in it, and every reader here supplies a default. What a
break costs is why: re-running an evaluation to replace a file costs k rollouts of real
spend, and a suspension and a results file are the two formats where that is true.

The floor moves only where a change is not additive, and a file below it is refused with
the message saying to re-run. A figure the older file cannot carry is reported as
underivable against ``EvalResults.format_version`` rather than as absent.
"""


# What each figure needs the file to be, for `EvalResults.carries`. A figure added in a version
# is absent from every file written before it, and absent is not the same answer as zero.
_ARRIVED_IN = {
    "node_ratios": (0, 29),
    "slice": (0, 29),
    "stores": (0, 30),
    "pipeline": (0, 31),
    "pairs": (0, 32),
}


def _as_pair(version: str) -> tuple[int, int]:
    """One version as two integers, or ``(-1, -1)`` for anything that is not one."""
    parts = str(version).split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return (-1, -1)
    return (int(parts[0]), int(parts[1]))


def _within_the_floor(version: str) -> bool:
    """Whether a file of this version is one this library reads.

    Between :data:`EVAL_FORMAT_FLOOR` and :data:`EVAL_FORMAT_VERSION`. A newer file is refused
    too: it may carry a field this version reads differently.
    """
    found = _as_pair(version)
    if found == (-1, -1):
        return False
    return _as_pair(EVAL_FORMAT_FLOOR) <= found <= _as_pair(EVAL_FORMAT_VERSION)


@dataclass(frozen=True, slots=True)
class Group:
    """One cell of a figure grouped by a property of the example.

    ``value`` is what the examples in this cell share, ``examples`` how many fell in it, and
    ``metrics`` and ``criteria`` are the same figures the whole evaluation reports, over these
    rollouts alone::

        cell = results.grouped("label")["shelve"]
        cell.examples                              # 23
        cell.metrics["accuracy"].interval.point    # 0.91

    Every figure carries its own n, and a comparison withholds a verdict on a cell too small
    to support one, so a thin cell reports its figure and declines to claim a difference.
    """

    value: Any
    examples: int
    metrics: dict[str, Metric] = field(default_factory=dict)
    criteria: dict[str, Metric] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvalResults:
    """What one evaluation produced.

    ``config`` says what was measured: the registered pipeline's name, the split, k, the seed,
    the example set's content hash, the pipeline's nodes and their prompt versions, the model,
    the cost basis, and the cassette mode. ``examples`` says what each example expected, which
    is what separates a right abstention from a missed value. ``rollouts`` holds every
    individual run with its seed and its trajectory path::

        results.metrics["false_confidence_rate"].interval.point
        results.nodes["hunt"].model_calls
        [r.trajectory for r in results.rollouts if r.outcome.value == "false_confidence"]

        results.write("evals/results/held-out-v3.json")
        earlier = EvalResults.read("evals/results/held-out-v2.json")
    """

    eval_id: str
    created_at: str
    config: dict[str, Any]
    metrics: dict[str, Metric]
    nodes: dict[str, NodeMetrics]
    rollouts: tuple[RolloutOutcome, ...]
    examples: dict[str, dict[str, Any]] = field(default_factory=dict)
    criteria: dict[str, Metric] = field(default_factory=dict)
    totals: dict[str, Any] = field(default_factory=dict)
    contamination: ContaminationReport | None = None
    baseline: tuple[RolloutOutcome, ...] = ()
    """What an agent that did nothing would have scored, one entry per example.

    Filled where the suite declared ``baseline=``, and empty otherwise. Scored by the same
    ``matches`` and the same conditions as the agent, over the examples that ran, so the floor
    cannot describe a split that was rebalanced away or one an evaluation only part scored::

        results.baseline_metrics()["accuracy"].interval.point   # 0.76
        results.metrics["accuracy"].interval.point              # 0.82

    Held as rollouts rather than as figures so the agent can be paired against it example by
    example, which is what ``against_baseline`` reports.
    """

    baseline_unscored: tuple[str, ...] = ()
    """Project figures no baseline answer reached, so their floor is a property of ``over``.

    A figure declared over rollouts that asserted a value decides one that asserted nothing
    without calling the project's own function. A do-nothing baseline asserts nothing on every
    example, so a figure measuring what the agent refrained from reports a floor describing the
    declaration: 0.0 for a mean, and undefined for a ratio, whose two totals are both zero.
    ``report()`` says so where the floor would be, and ``over=Over.ALL`` is what scores such a
    figure::

        results.baseline_unscored        # ('avoided_share',)
    """

    pairs: tuple[dict[str, Any], ...] = ()
    """The judged pairs, where this file is a session of them rather than rollouts.

    Filled by ``paired_results`` and empty on an evaluation that ran a pipeline. Each entry
    carries the two things shown, ``a`` and ``b``, what each was an instance of, ``a_arm`` and
    ``b_arm``, the ``verdict`` recorded, who decided it and when. ``config["kind"]`` is
    ``"pairs"`` on such a file and ``config["verdicts"]`` says what each verdict means::

        results.config["contest"]                 # ['baseline', 'variant']
        [p["verdict"] for p in results.pairs]     # ['a', 'both_good', 'b', ...]
    """

    path: Path | None = None
    format_version: str = EVAL_FORMAT_VERSION
    """The version of the file this was read from, and the current version for a fresh result.

    A figure added after that version is absent from the file rather than empty in it, so a
    reader that has to tell the two apart reads this::

        results.format_version              # '0.28'
        results.carries("node_ratios")      # False: the file predates them
    """

    def carries(self, figure: str) -> bool:
        """Whether the file this was read from is new enough to hold ``figure``.

        The named figures are ``node_ratios``, a ``ProjectRatio`` reported per node, and
        ``slice``, what the evaluated pipeline is a slice of, both of which arrived in
        ``0.29``; ``stores``, what each store the pipeline reaches did during the rollouts,
        which arrived in ``0.30``; ``pipeline``, which registered pipeline was measured,
        which arrived in ``0.31``; and ``pairs``, the judged pairs a session filed with
        ``paired_results``, which arrived in ``0.32``. A file written before one holds it not
        at all, which is a different answer from a project having declared none::

            if not results.carries("node_ratios"):
                print(f"read from {results.format_version}, which records no per-node ratio")

        An unknown name is ``True``: a figure this library does not version is one every file
        it reads carries.
        """
        arrived = _ARRIVED_IN.get(figure)
        if arrived is None:
            return True
        return _as_pair(self.format_version) >= arrived

    @property
    def k(self) -> int:
        """Rollouts per example."""
        return int(self.config.get("k", 0))

    @property
    def n(self) -> int:
        """Examples in the split that was run."""
        return int(self.config.get("n", 0))

    @property
    def expects_absence(self) -> dict[str, bool]:
        """Which examples had absence as their correct answer, keyed by id."""
        return {
            example_id: bool(entry.get("expects_absence"))
            for example_id, entry in self.examples.items()
        }

    def baseline_metrics(
        self,
        *,
        confidence: float = DEFAULT_CONFIDENCE,
        resamples: int = DEFAULT_RESAMPLES,
        seed: int = 0,
    ) -> dict[str, Metric]:
        """The same figures over the do-nothing answers, keyed by name.

        Empty where the suite declared no ``baseline=``. Every figure the agent reports has one
        here, computed from the same conditions over the same split, so a headline can be read
        against what not trying would have scored::

            results.baseline_metrics()["accuracy"].interval.point

        A measure the agent could not beat is not a measure, and this is what says which it is.
        """
        if not self.baseline:
            return {}
        return metrics_over(
            self.baseline,
            self.expects_absence,
            like=self.metrics,
            confidence=confidence,
            resamples=resamples,
            seed=seed,
        )

    def groups(self, key: str) -> dict[Any, tuple[str, ...]]:
        """The example ids under each value of ``key``, keyed by that value.

        ``key`` is a field of the stored example entry or a key of its ``metadata``, so
        ``"split"``, ``"source"``, ``"label"`` and anything the project carried all group::

            results.groups("label")     # {'shelve': ('q1', 'q4'), 'skip': ('q2',)}

        An example with no value under ``key`` is in no cell. Raises
        :class:`~simple_agents.errors.ConfigurationError` where no example carries it.
        """
        found: dict[Any, list[str]] = {}
        for example_id, entry in self.examples.items():
            value = _group_value(entry, key)
            if value is not None:
                found.setdefault(value, []).append(example_id)
        if not found:
            self._refuse_an_ungroupable_key(key)
        return {value: tuple(sorted(ids)) for value, ids in found.items()}

    def _refuse_an_ungroupable_key(self, key: str) -> None:
        """Why nothing could be grouped by ``key``, which is two different problems."""
        held = [
            (entry.get("metadata") or {}).get(key)
            for entry in self.examples.values()
            if key in (entry.get("metadata") or {})
        ]
        if held:
            kinds = sorted({type(value).__name__ for value in held})
            raise ConfigurationError(
                f"{len(held)} example(s) carry {key!r} and none of them is a single value: "
                f"the values are {', '.join(kinds)}. A cell is named by its value, so a list "
                f"or a mapping cannot name one.\n"
                f"Carry the property a figure is grouped by as a string, a number or a bool, "
                f"such as metadata={{{key!r}: 'fantasy'}}. Groupable here: "
                f"{', '.join(self.groupable()) or 'nothing'}."
            )
        raise ConfigurationError(
            f"No example in this evaluation carries {key!r}, so there is nothing to group "
            f"by. Groupable here: {', '.join(self.groupable()) or 'nothing'}.\n"
            f"A figure is grouped by a field of the example or a key of its metadata. Put "
            f"the property on the example set as Example(..., metadata={{{key!r}: ...}}) "
            f"and run the evaluation again, or group by one of the above."
        )

    def groupable(self) -> tuple[str, ...]:
        """Every key a figure can be grouped by in this evaluation, sorted.

        The stored fields of an example entry and every key of its metadata::

            results.groupable()    # ('genre', 'label', 'source', 'split')
        """
        keys: set[str] = set()
        for entry in self.examples.values():
            keys.update(k for k in _GROUPABLE_FIELDS if entry.get(k) is not None)
            keys.update(str(k) for k in (entry.get("metadata") or {}))
        return tuple(sorted(keys))

    def grouped(
        self,
        key: str,
        *,
        confidence: float = DEFAULT_CONFIDENCE,
        resamples: int = DEFAULT_RESAMPLES,
        seed: int = 0,
    ) -> dict[Any, Group]:
        """Every figure this evaluation reports, over each cell of ``key``, keyed by its value.

        A pooled figure moves with the mix of examples under it, so an agent that improved on
        one kind and lost ground on another reports no change at all where the two cancel::

            for value, cell in results.grouped("label").items():
                print(value, cell.metrics["accuracy"].interval.point, cell.examples)

        ``key`` is a field of the example entry or one of its metadata keys, and
        :meth:`groupable` says which. The cells are computed from the rollouts the file already
        holds, so a grouping can be chosen after the evaluation ran.
        """
        absence = self.expects_absence
        by_example = self.groups(key)
        cells: dict[Any, Group] = {}
        for value, example_ids in by_example.items():
            wanted = set(example_ids)
            rollouts = [r for r in self.rollouts if r.example_id in wanted]
            cells[value] = Group(
                value=value,
                examples=len(example_ids),
                metrics=metrics_over(
                    rollouts,
                    absence,
                    like=self.metrics,
                    confidence=confidence,
                    resamples=resamples,
                    seed=seed,
                ),
                criteria=criteria_over(
                    rollouts,
                    like=self.criteria,
                    confidence=confidence,
                    resamples=resamples,
                    seed=seed,
                ),
            )
        return cells

    def scores_by_example(self) -> dict[str, list[float]]:
        """Each example's per-rollout scores, in rollout order.

        The shape a bootstrap takes, and what a comparison between two evaluations pairs on. A
        rollout that did not measure the agent is left out, as it is left out of every rate, so
        an example whose rollouts all went that way carries no entry.
        """
        grouped: dict[str, list[RolloutOutcome]] = {}
        for rollout in self.rollouts:
            if inside(rollout):
                grouped.setdefault(rollout.example_id, []).append(rollout)
        return {
            example_id: [r.score for r in sorted(rollouts, key=lambda r: r.rollout)]
            for example_id, rollouts in grouped.items()
        }

    def to_json(self) -> dict[str, Any]:
        """The file, as it is written."""
        return {
            "eval_format_version": EVAL_FORMAT_VERSION,
            "eval_id": self.eval_id,
            "created_at": self.created_at,
            "config": self.config,
            "examples": self.examples,
            "metrics": {name: m.to_record() for name, m in self.metrics.items()},
            "criteria": {name: m.to_record() for name, m in self.criteria.items()},
            "nodes": {node_id: m.to_record() for node_id, m in self.nodes.items()},
            "totals": self.totals,
            "contamination": (
                self.contamination.to_record() if self.contamination is not None else None
            ),
            "rollouts": [r.to_record() for r in self.rollouts],
            "baseline": [r.to_record() for r in self.baseline],
            "baseline_unscored": list(self.baseline_unscored),
            "pairs": [dict(p) for p in self.pairs],
        }

    def report(self, *, group_by: str | None = None) -> str:
        """The results as text, for reading rather than parsing.

        Every rate with its interval and the n it was computed over, then the per-node table,
        then what the numbers came from. ``group_by`` adds every figure again over each cell
        of a property of the example, which is what a pooled figure hides::

            print(results.report())
            print(results.report(group_by="label"))

        The interval travels with every figure, so no line of this can be quoted as a bare
        percentage (FT-06). A rate with no denominator says so rather than printing zero.
        """
        width = max(len(name) for name in self.metrics) if self.metrics else 0
        lines = self._header_lines() + self._metric_lines(width)
        lines += self._criteria_lines()
        lines += self._node_lines()
        if group_by is not None:
            lines += self._group_lines(group_by, width)
        lines += self._trailer_lines()
        return "\n".join(lines)

    def _header_lines(self) -> list[str]:
        """The header: what ran, and the incomplete warning where the split did not."""
        if self.config.get("kind") == "pairs":
            contest = " v ".join(str(arm) for arm in self.config.get("contest") or [])
            judges = ", ".join(str(who) for who in self.config.get("decided_by") or []) or "?"
            return [
                f"{self.n} judged pair(s) over {self.config.get('units', '?')} unit(s), "
                f"{contest or 'no contest named'}, decided by {judges}"
                f"{' blind' if self.config.get('blind') else ''}",
                "",
            ]
        lines = [
            f"{self.n} example(s) x {self.k} rollout(s) on split "
            f"{self.config.get('split', '?')!r}, seed {self.config.get('seed', '?')}",
            "",
        ]
        # Named `incomplete` rather than `partial`, which in an evaluation now means an answer
        # that met part of its answer key.
        incomplete = self.config.get("incomplete")
        if incomplete:
            lines[1:1] = [
                f"  INCOMPLETE: scored {incomplete['rollouts_scored']} of "
                f"{incomplete['rollouts_expected']} rollout(s), over "
                f"{incomplete['examples_scored']} of {incomplete['examples_in_split']} "
                f"example(s) in this split. Every figure below is over what ran, not over the "
                f"split.",
            ]
        return lines

    def _metric_lines(self, width: int) -> list[str]:
        """One line per end-to-end figure, with its floor beneath it where one exists."""
        lines: list[str] = []
        floor = self.baseline_metrics()
        for name, metric in self.metrics.items():
            if metric.interval is None:
                lines.append(f"  {name:<{width}}  {_uncounted(metric)}")
                lines.extend(_also(metric, width))
                continue
            lines.append(
                f"  {name:<{width}}  {_figure(metric)}  n={metric.interval.n} over "
                f"{metric.population}{_unanswered(metric)}{_rerun(metric)}"
            )
            lines.extend(_also(metric, width))
            lines.extend(
                _floor(
                    metric,
                    floor.get(name),
                    width,
                    unscored=name if name in self.baseline_unscored else None,
                )
            )
        return lines

    def _criteria_lines(self) -> list[str]:
        """One line per criterion, and who or what decided a judged one."""
        lines: list[str] = []
        if self.criteria:
            criterion_width = max(len(name) for name in self.criteria)
            lines += ["", "  criteria met"]
            for name, metric in self.criteria.items():
                if metric.interval is None:
                    lines.append(f"    {name:<{criterion_width}}  undefined: {metric.reason}")
                    lines.extend(_also(metric, criterion_width, indent=4))
                    continue
                absent = f", {metric.absent} asserted nothing" if metric.absent else ""
                lines.append(
                    f"    {name:<{criterion_width}}  {_figure(metric)}  "
                    f"n={metric.interval.n}{absent}  {metric.definition}"
                    f"{_unanswered(metric)}"
                )
                lines.extend(_also(metric, criterion_width, indent=4))
                judged = _judged_by(self.config, name)
                if judged:
                    lines.append(f"    {'':<{criterion_width}}  {judged}")
        return lines

    def _node_lines(self) -> list[str]:
        """The per-node table, one row per node with its figures beneath it."""
        lines: list[str] = []
        if self.nodes:
            lines += [
                "",
                "  node        kind          reach                execs  calls  tools  "
                "model cost           tool spend",
            ]
            for node_id, node in self.nodes.items():
                cost = node.cost.describe() if node.cost is not None else "unknown"
                spend = _tool_spend(node)
                lines.append(
                    f"  {node_id:<11} {node.node_kind:<13} {_reach(node):<20} "
                    f"{node.executions:>5} {node.model_calls:>6} {node.tool_calls:>6}  "
                    f"{cost:<20} {spend}"
                )
                lines.extend(f"  {'':<11} {line}" for line in unfinished_lines(node))
                for label, figure in (
                    ("accuracy", node.accuracy),
                    *sorted(node.metrics.items()),
                ):
                    if figure is None or figure.interval is None:
                        continue
                    lines.append(
                        f"  {'':<11} {label}: {_figure(figure).strip()} over {figure.interval.n}"
                    )
                if node.terminations:
                    ended = ", ".join(f"{k} {v}" for k, v in sorted(node.terminations.items()))
                    lines.append(f"  {'':<11} ended: {ended}")
                if node.consultation_resolutions:
                    asked = ", ".join(
                        f"{k} {v}" for k, v in sorted(node.consultation_resolutions.items())
                    )
                    lines.append(f"  {'':<11} consulted: {asked}")
                if node.consultation_answered_by:
                    by = ", ".join(
                        f"{k} {v}" for k, v in sorted(node.consultation_answered_by.items())
                    )
                    lines.append(f"  {'':<11} answered by: {by}")

        return lines

    def _group_lines(self, group_by: str, width: int) -> list[str]:
        """Every end-to-end figure again, over each cell of a property of the example."""
        lines: list[str] = []
        cells = self.grouped(group_by)
        outside = len(self.examples) - sum(cell.examples for cell in cells.values())
        carries = f", {outside} example(s) carry no {group_by}" if outside else ""
        lines += ["", f"  by {group_by}{carries}"]
        for value, cell in sorted(cells.items(), key=lambda pair: str(pair[0])):
            lines.append(f"    {value} ({cell.examples} example(s))")
            for name, metric in cell.metrics.items():
                if metric.interval is None:
                    lines.append(f"      {name:<{width}}  undefined: {metric.reason}")
                    continue
                lines.append(f"      {name:<{width}}  {_figure(metric)}  n={metric.interval.n}")
        return lines

    def _trailer_lines(self) -> list[str]:
        """What the numbers came from: outcomes, interval methods, contamination, spend."""
        lines: list[str] = []
        outcomes: dict[str, int] = {}
        for rollout in self.rollouts:
            outcomes[rollout.outcome.value] = outcomes.get(rollout.outcome.value, 0) + 1
        # A session of judged pairs has no rollouts and so no outcomes line.
        if outcomes:
            lines += ["", "  " + ", ".join(f"{k} {v}" for k, v in sorted(outcomes.items()))]

        # One line per calculation present, because a metric whose examples all scored the same
        # is a proportion and carries Wilson's interval rather than the resampled one. Naming
        # only the first metric's method would describe the whole report by one of its rows.
        methods: dict[str, int] = {}
        for metric in self.metrics.values():
            if metric.interval is not None:
                methods[metric.interval.method] = metric.interval.resamples
        for method, resamples in methods.items():
            counted = f", {resamples} resamples" if resamples else ""
            lines.append(f"  intervals: {method}{counted}")
        if self.contamination is not None:
            found = (
                "clean"
                if self.contamination.clean
                else f"{len(self.contamination.pairs)} overlapping pair(s)"
            )
            lines.append(f"  contamination at threshold {self.contamination.threshold}: {found}")
        cassette = (self.config.get("cassette") or {}).get("mode")
        if cassette:
            lines.append(f"  calls: {cassette}")
        return lines + self._spend_lines()

    def _spend_lines(self) -> list[str]:
        """What the evaluation cost, and what part of it could not be measured.

        Printed rather than left in the file because an evaluation that failed part way is the
        one whose bill is worth reading, and it is the one whose total is `null`.
        """
        cost = self.totals.get("cost") or {}
        if not cost:
            return []
        currency = cost.get("currency") or ""
        if cost.get("value") is not None:
            return [f"  spend: {cost['value']:.4f} {currency}".rstrip()]
        return _partial_spend_lines(cost, currency)

    def write(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        directory: str | os.PathLike[str] = "evals/results",
        overwrite: bool = False,
    ) -> Path:
        """Write the results file, creating parent directories, and return where it went.

        Called with no path it names the file after the evaluation, under ``directory``, so two
        runs cannot collide::

            results.write()                                  # evals/results/eval_a1226bc.json
            results.write("evals/results/held-out-v3.json")   # a name chosen by the project

        **A path that already holds a results file is refused**, because a results file is the
        only durable record of a measurement and the rollouts behind an overwritten one may no
        longer be scoreable: the pipeline moves, and `rescore` refuses a graph that has changed
        (FT-15). Pass ``overwrite=True`` to replace one.
        """
        target = Path(directory) / f"{self.eval_id}.json" if path is None else Path(path)
        if target.exists() and target.stat().st_size > 0 and not overwrite:
            raise ConfigurationError(
                f"{str(target)!r} already holds a results file, and a results file is the "
                f"only durable record of a measurement. The rollouts behind it may not be "
                f"scoreable again, because rescoring is refused once the pipeline has "
                f"changed, so replacing it can lose a number that cannot be rebuilt.\n"
                f"Call results.write() with no path to name the file after this evaluation, "
                f"pass a path that does not exist, or pass overwrite=True to replace it."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_json(), indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        return target

    @classmethod
    def read(cls, path: str | os.PathLike[str]) -> EvalResults:
        """Read a results file back, rebuilding the metrics, the nodes and the rollouts."""
        target = Path(path)
        if not target.exists():
            raise ConfigurationError(
                f"No results file at {target}. An evaluation writes one with "
                f"results.write('evals/results/held-out-v3.json')."
            )
        raw = json.loads(target.read_text(encoding="utf-8"))
        version = str(raw.get("eval_format_version", ""))
        if not _within_the_floor(version):
            raise ConfigurationError(
                f"{target} is eval format {version or 'unversioned'} and this library reads "
                f"{EVAL_FORMAT_FLOOR} to {EVAL_FORMAT_VERSION}. Re-run the evaluation to "
                f"produce a file this version reads."
            )
        contamination = raw.get("contamination")
        return cls(
            eval_id=str(raw["eval_id"]),
            created_at=str(raw["created_at"]),
            format_version=version,
            config=dict(raw.get("config") or {}),
            metrics={
                name: Metric.from_record(record)
                for name, record in (raw.get("metrics") or {}).items()
            },
            criteria={
                name: Metric.from_record(record)
                for name, record in (raw.get("criteria") or {}).items()
            },
            nodes={
                node_id: NodeMetrics.from_record(record)
                for node_id, record in (raw.get("nodes") or {}).items()
            },
            rollouts=tuple(
                RolloutOutcome.from_record(record) for record in raw.get("rollouts") or []
            ),
            examples={str(k): dict(v) for k, v in (raw.get("examples") or {}).items()},
            totals=dict(raw.get("totals") or {}),
            contamination=_contamination(contamination),
            baseline=tuple(
                RolloutOutcome.from_record(record) for record in raw.get("baseline") or []
            ),
            baseline_unscored=tuple(str(name) for name in raw.get("baseline_unscored") or []),
            pairs=tuple(dict(p) for p in raw.get("pairs") or []),
            path=target,
        )


_GROUPABLE_FIELDS = ("split", "source", "label")


def _group_value(entry: dict[str, Any], key: str) -> Any:
    """One example's value under a grouping key, or ``None`` where it carries none."""
    if key in _GROUPABLE_FIELDS:
        return entry.get(key)
    value = (entry.get("metadata") or {}).get(key)
    return value if isinstance(value, (str, int, float, bool)) else None


def _judged_by(config: dict[str, Any], criterion_id: str) -> str:
    """Who decided a judged condition, for the line under its figure.

    Empty for a condition code decided. A figure a model decided and one a regex decided are
    different claims, and the count of hand corrections beside it says how much of it a person
    had already disagreed with.
    """
    entry = (config.get("criteria") or {}).get(criterion_id)
    if not isinstance(entry, dict) or entry.get("decided") != "judged":
        return ""
    deciders = entry.get("decided_by") or {}
    if not isinstance(deciders, dict) or not deciders:
        return "judged"
    named = ", ".join(f"{who} {count}" for who, count in deciders.items())
    return f"judged: {named}"


def _figure(metric: Metric) -> str:
    """One metric's point estimate and interval, printed in whatever the metric is measured in.

    A rate reads as a percentage. Anything else reads as the number, with its unit after it, so
    a cost does not print as ``0.0%``.
    """
    interval = metric.interval
    if interval is None:
        return "undefined"
    # The two totals behind a ratio, so a share is never read without the counts it came from.
    counts = (
        f" ({metric.numerator:.4g} of {metric.denominator:.4g})"
        if metric.numerator is not None and metric.denominator is not None
        else ""
    )
    if metric.unit == RATE:
        return f"{interval.point:6.1%}  [{interval.low:.1%}, {interval.high:.1%}]{counts}"
    suffix = f" {metric.unit}" if metric.unit else ""
    return f"{interval.point:.4g}{suffix}  [{interval.low:.4g}, {interval.high:.4g}]{counts}"


def _uncounted(metric: Metric) -> str:
    """A figure with no interval: its number where it has one, and why it has no interval.

    A count over one run is not undefined. It reports the total and the reason the project
    declared, so the line carries the number and cannot be read as an estimate of a rate.
    """
    if metric.value is None:
        return f"undefined: {metric.reason}"
    unit = f" {metric.unit}" if metric.unit and metric.unit != RATE else ""
    counted = f"{metric.value:.4g}{unit}"
    if metric.denominator is not None:
        counted = f"{counted}, {metric.numerator:.4g} of {metric.denominator:.4g}"
    return f"{counted}  ({metric.reason})"


def _floor(
    metric: Metric, baseline: Metric | None, width: int, *, unscored: str | None = None
) -> list[str]:
    """What an agent that did nothing scored on this figure, under the figure itself.

    Under it rather than beside it, so a headline is never read without the number it has to
    clear, and so a figure whose interval reaches its own floor says so on the line.

    ``unscored`` is the figure's name where the project's own function never saw this floor,
    which is what a figure over rollouts that asserted a value reports for a baseline that
    asserts nothing. A mean of those is 0.0 and a ratio of them is undefined, so the reason is
    printed whether or not there is a number above it.
    """
    lines: list[str] = []
    if baseline is not None and baseline.interval is not None and metric.interval is not None:
        # Direction-neutral: `false_confidence_rate` and `failure_rate` are better low, and the
        # finding is the same either way, that this figure does not tell the two apart.
        reached = (
            "  not separated from it"
            if metric.interval.low <= baseline.interval.point <= metric.interval.high
            else ""
        )
        lines.append(
            f"  {'':<{width}}  {_figure(baseline)}  doing nothing, over "
            f"{baseline.interval.n} example(s){reached}"
        )
    if unscored:
        lines += [
            f"  {'':<{width}}  the baseline asserted nothing, so {unscored} was not called for it.",
            f"  {'':<{width}}  over=Over.ALL is what scores a figure about refraining.",
        ]
    return lines


def _rerun(metric: Metric) -> str:
    """The half-width of this figure's rollout noise, or nothing where there is none.

    On the figure's own line, at the same confidence as the interval beside it, so the two can
    be read against each other: the interval is over which examples were drawn and this is over
    running the same ones again.
    """
    noise, interval = metric.rollout_noise, metric.interval
    if not noise or interval is None:
        return ""
    half = _z_for(interval.confidence) * noise
    if metric.unit == RATE:
        return f", rerun ±{half:.1%}"
    return f", rerun ±{half:.4g}"


def _unanswered(metric: Metric) -> str:
    """What this figure left out, and why, or nothing to say.

    Printed on the figure's own line rather than once at the foot, because a rate read on its
    own is a rate whose denominator has to say what it is over (FT-06).
    """
    return "".join(
        f", less {count} {LEFT_OUT_CAUSES.get(cause, cause)}"
        for cause, count in sorted(metric.left_out.items())
        if count
    )


def _also(metric: Metric, width: int, indent: int = 2) -> list[str]:
    """The same figure with the left-out rollouts counted, where any could be counted.

    Under the figure rather than beside it, so the narrower number is never read alone and
    neither line is a bare percentage (FT-06).
    """
    wider = metric.including_left_out
    if wider is None:
        return []
    counted = sum(count for cause, count in metric.left_out.items() if cause != NO_RESPONSE)
    if metric.unit == RATE:
        figure = f"{wider.point:6.1%}  [{wider.low:.1%}, {wider.high:.1%}]"
    else:
        suffix = f" {metric.unit}" if metric.unit else ""
        figure = f"{wider.point:.4g}{suffix}  [{wider.low:.4g}, {wider.high:.4g}]"
    return [
        f"{' ' * indent}{'':<{width}}  {figure}  "
        f"n={wider.n}, with the {counted} left out above counted as scored"
    ]


def _reach(node: NodeMetrics) -> str:
    """A node's reach as text, with its interval, so no line reads as a bare rate (FT-06)."""
    if node.reach is None or node.reach.interval is None:
        return f"{node.reached}/{node.runs}"
    interval = node.reach.interval
    return f"{interval.point:5.1%} [{interval.low:.0%},{interval.high:.0%}]"


def _tool_spend(node: NodeMetrics) -> str:
    """What this node's tools cost, as text. A sum over calls, so it carries no interval."""
    if node.tool_spend is None:
        return "-"
    return f"{node.tool_spend:.6f} over {node.paid_tool_calls} call(s)"


def _contamination(raw: Any) -> ContaminationReport | None:
    if not isinstance(raw, dict):
        return None
    return ContaminationReport(
        threshold=float(raw.get("threshold", 0.0)),
        compared=int(raw.get("compared", 0)),
        pairs=tuple(
            Overlap(
                left=str(p["left"]),
                right=str(p["right"]),
                left_split=str(p["left_split"]),
                right_split=str(p["right_split"]),
                kind=str(p["kind"]),
                detail=str(p.get("detail", "")),
                similarity=p.get("similarity"),
            )
            for p in raw.get("pairs") or []
        ),
    )


def _partial_spend_lines(cost: dict[str, Any], currency: str) -> list[str]:
    """The spend line for an evaluation whose total could not be derived.

    What priced is a floor and is printed as one; what did not is counted in calls and named
    by the nodes those calls were in.
    """
    unpriced = cost.get("unpriced_nodes") or []
    missing = int(cost.get("unpriced_calls") or 0)
    if not unpriced and not missing:
        return []
    measured = cost.get("measured")
    amount = (
        "nothing that could be measured"
        if measured is None
        else f"at least {measured:.4f} {currency}".strip()
    )
    calls = int(cost.get("priced_calls") or 0) + missing
    of_calls = f"{missing:,} of {calls:,} call(s)" if calls else f"{missing:,} call(s)"
    where = f" in {', '.join(unpriced)}" if unpriced else ""
    return [
        f"  spend: {amount}, and {of_calls}{where} could not be priced. "
        f"The total is unknown rather than this figure."
    ]


def totals_of(nodes: dict[str, NodeMetrics]) -> dict[str, Any]:
    """Tokens, model cost and tool spend over every node, with an unmeasured class left so.

    Each record belongs to exactly one node, so summing the per-node figures counts every call
    once. ``cost`` is model spend; ``tool_spend`` is what the tools were charged.

    ``cost.value`` is ``null`` where any call could not be measured, because a call that raised
    before the backend answered has no token count and an unmeasured count is not zero.
    ``cost.measured`` is what the calls that did price came to and ``cost.unpriced_calls``
    counts the ones left out of it, so an evaluation that failed part way still says what it
    spent. ``cost.unpriced_nodes`` names the nodes those calls were in::

        totals["cost"]["value"]           # None
        totals["cost"]["measured"]        # 5.5024
        totals["cost"]["unpriced_calls"]  # 54
        totals["cost"]["unpriced_nodes"]  # ['judge_candidates', 'survey_pool']

    **``measured`` is a floor and never the total.** A node whose every call priced still makes
    the run's total unknown if another node's did not, and the figure to report is ``value``.
    """
    tokens: dict[str, Any] = {}
    for metrics in nodes.values():
        for name, value in metrics.tokens.items():
            current = tokens.get(name, 0)
            if isinstance(current, dict):
                continue
            if isinstance(value, dict):
                tokens[name] = value
            else:
                tokens[name] = current + value

    running: Cost | None = None
    unpriced: list[str] = []
    for node_id, metrics in sorted(nodes.items()):
        if metrics.cost is None:
            continue
        running = metrics.cost if running is None else running.plus(metrics.cost)
        if metrics.cost.value is None:
            unpriced.append(node_id)

    spend: float | None = None
    paid_calls = 0
    spend_currency: str | None = None
    for metrics in nodes.values():
        if metrics.tool_spend is None:
            continue
        spend = (spend or 0.0) + metrics.tool_spend
        paid_calls += metrics.paid_tool_calls
        spend_currency = spend_currency or metrics.tool_spend_currency

    return {
        "tokens": tokens,
        # `measured` and the call counts come off the figure itself, which accumulates them
        # per call: a node holding one unpriced call among fifty is unpriced, and the other
        # forty-nine are still in the floor.
        "cost": {
            **(running or Cost(value=None, currency=None, basis=None)).to_record(),
            "unpriced_nodes": unpriced,
        },
        "tool_spend": {
            "amount": spend,
            # From the tool spend rather than the model cost: a pipeline of `Deterministic`
            # nodes calling a paid tool makes no model call, and an amount with no unit
            # cannot be summed or compared.
            "currency": spend_currency,
            "calls": paid_calls,
        },
    }
