"""Per-node metrics, read out of the trajectories the rollouts wrote.

One end-to-end score reports that the agent got worse and nothing about where, leaving hand
bisection through prompt edits as the way to localize a regression (FT-08). These numbers are
per `node_id`, so a change in tokens, cost, failures or how a node terminated names the node it
happened in.

Most of what is here needs no labels and is available on every run. Accuracy is the exception:
it is reported for a node the example set labels through ``Example.expected_by_node``, over the
rollouts that reached that node.

A node in a graph does not run on every rollout, so ``reach`` is reported beside every other
number it carries. A node that ran 40 times out of 100 has all its other figures over those 40.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..cost import Cost, CostBasis, duration_seconds, total_cost
from ..envelope import runs as runs_under
from ..schema import Unknown
from ..records.trajectory import read_trajectory
from .intervals import DEFAULT_CONFIDENCE, DEFAULT_RESAMPLES
from .metrics import RATE, Metric, ProjectMetric, _metric
from .outcomes import RolloutOutcome
from .ratios import ProjectRatio, ratio_metric

__all__ = [
    "NodeMetrics",
    "node_metrics",
    "node_scores",
    "per_node",
    "node_rates",
    "unfinished_lines",
    "unfinished_work",
]

REACH_DEFINITION = "rollouts in which this node ran, over all rollouts"
ACCURACY_DEFINITION = (
    "rollouts where this node's output matched its label, over rollouts that reached it and "
    "carry one"
)

_TOKEN_FIELDS = ("input_uncached", "input_cache_read", "input_cache_write", "output")

UNFINISHED: frozenset[str] = frozenset(
    {"max_steps", "max_tokens", "max_cost", "max_wall_clock", "finish_rejected"}
)
"""Terminations that end a unit of work without an output.

An ``AgentNode`` produces its output from a ``finish`` call, so a loop that stopped on a budget
axis or on a finish its own check kept rejecting returns ``None`` to the node after it.
``error`` is not here, since ``errors`` counts those; nor is ``skipped``, which never ran, nor
``suspended``, which continues in another process, nor ``max_iterations``, which is a cycle
running out around a node that completed.
"""


@dataclass(slots=True)
class NodeMetrics:
    """What one node did across every rollout of an evaluation.

    ``model_calls`` counts the calls made inside the node's tools as well as the ones it made
    itself, because a node's spend includes what its tools spent::

        results.nodes["hunt"].model_calls / results.nodes["hunt"].executions   # calls per run
        results.nodes["hunt"].terminations    # {'finish': 47, 'max_steps': 3}

    ``tool_spend`` is what this node's tool calls cost, over the ``paid_tool_calls`` that bought
    something, and is ``None`` where none did. It is a sum, and carries no interval.
    ``absent_outputs`` counts executions whose output reported an absence anywhere in it.
    ``consultation_resolutions`` says how the questions this node asked ended and
    ``consultation_answered_by`` who the channel said answers, so an evaluation whose questions
    went to a fixed string is separable from one measured against a person::

        results.nodes["hunt"].consultation_resolutions   # {'answered': 5, 'declined': 28}
        results.nodes["hunt"].consultation_answered_by   # {'simulated': 33}

    ``consultation_misreadings`` counts the answers where the channel said which option it had
    picked and ``consult(match=...)`` read a different one, or none::

        results.nodes["hunt"].consultation_misreadings   # 24

    ``runs`` is how many rollouts were observed and ``reached`` how many ran this node, which
    is what every other figure here is over. ``reach`` is that as a rate with an interval::

        results.nodes["verify"].reach.interval.point    # 0.42
        results.nodes["verify"].executions              # over the 42 rollouts that reached it

    ``executions`` can exceed ``reached`` where the node sits inside a bounded cycle and runs
    more than once in a rollout. A skipped node is counted under ``terminations['skipped']``.

    ``metrics`` holds the figures declared for this node through
    ``EvalSuite(node_metrics=...)``, keyed by name. A ``ProjectMetric`` reports a mean over the
    rollouts and a ``ProjectRatio`` its two totals::

        results.nodes["hunt"].metrics["span_f1"].interval.point            # 0.83
        results.nodes["hunt"].metrics["unreadable_pages"].numerator        # 118
    """

    node_id: str
    node_kind: str
    runs: int = 0
    reached: int = 0
    executions: int = 0
    errors: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    paid_tool_calls: int = 0
    tool_spend: float | None = None
    tool_spend_currency: str | None = None
    consultations: int = 0
    consultation_resolutions: dict[str, int] = field(default_factory=dict)
    consultation_answered_by: dict[str, int] = field(default_factory=dict)
    consultation_misreadings: int = 0
    resource_reads: dict[str, int] = field(default_factory=dict)
    """Accesses this node's own code recorded as reads, by resource name.

    A resource reached through a tool is counted in ``tool_calls``. This counts the ones a
    node recorded with ``ctx.record_access`` (`docs/trajectory-format.md` §4.5)::

        results.nodes["gather"].resource_reads    # {'catalogue': 41}
    """

    resource_writes: dict[str, int] = field(default_factory=dict)
    """The same for accesses the node recorded as writes."""

    delegations: int = 0
    replayed_calls: int = 0
    wall_clock_ms: int = 0
    absent_outputs: int = 0
    unfinished_executions: int = 0
    """Executions of this node that ended without producing an output.

    An ``AgentNode`` produces its output from a ``finish`` call, so an execution that stopped
    on a budget axis or on a ``finish`` its own check kept rejecting returns ``None`` to the
    node after it. The run completes and records no error::

        results.nodes["hunt"].unfinished_executions   # 90, of 102 executions
    """

    unfinished_items: int = 0
    """Fan-out items of this node that ended the same way.

    A separate unit of work from an execution: a fan-out whose items all stopped that way
    completed normally and records no termination of its own. Read from what the node
    recorded, so a run whose payloads were dropped by sampling reports none.
    """

    unfinished_without_tool_calls: int = 0
    """Those of the two above that made no tool call, no consultation and no delegation.

    The loop spent its whole allowance without once acting, so nothing it did survives it.
    Inside an ``AgentNode`` all three reach the model as tool declarations in one namespace,
    so this counts a model that chose none of them at any step::

        results.nodes["hunt"].unfinished_without_tool_calls   # 88, of the 90 above
    """

    unfinished_model_calls: int = 0
    """What the executions and items above spent, which is what the node bought nothing with.

    Read against ``model_calls`` for the share of this node's spend that produced no output::

        node = results.nodes["hunt"]
        node.unfinished_model_calls / node.model_calls   # 0.92
    """

    unfinished_model_calls_without_tool_calls: int = 0
    """What the units that never acted spent, of ``unfinished_model_calls``.

    The narrower of the two figures: a loop that produced nothing and never called a tool,
    consulted or delegated spent this on nothing at all::

        results.nodes["hunt"].unfinished_model_calls_without_tool_calls   # 3,384

    This is what FT-35 gates on. A unit of work that acted and then ran out is in
    ``unfinished_model_calls`` and not here.
    """

    empty_responses: int = 0
    """Model calls that came back with no content and no tool call.

    The call was paid for and returned nothing to act on. A reasoning model that spends its
    whole output ceiling on the chain of thought answers this way, and so does one cut off by
    ``max_output_tokens`` before it wrote anything::

        results.nodes["hunt"].empty_responses   # 3, of 40 calls

    Read from what the call recorded, so a run whose payloads were dropped by sampling reports
    none. Reasoning is not content: a call carrying a chain of thought and nothing else is one
    of these, which is what the figure is for.
    """

    delegations_out_of_budget: int = 0
    """Subtasks this node sent that ran the delegated pipeline out of its own budget.

    The subtask came back as an observation rather than an answer, so what it spent bought a
    report of failure. Read against ``delegations``, which counts every subtask sent::

        results.nodes["orchestrate"].delegations_out_of_budget   # 4, of 11 subtasks
    """

    tools_that_never_succeeded: dict[str, int] = field(default_factory=dict)
    """Tools this node called where every call failed, and how many calls each took.

    A tool that answered nothing all run is a declaration the model could not use or a
    dependency that was down, and the model was handed an error each time and carried on::

        results.nodes["hunt"].tools_that_never_succeeded   # {'document_search': 7}

    A tool that failed and later succeeded is absent, so this names the ones that never worked.
    ``finish`` appears where a node's own check rejected every answer it was offered.
    """

    terminations: dict[str, int] = field(default_factory=dict)
    tokens: dict[str, Any] = field(default_factory=dict)
    cost: Cost | None = None
    reach: Metric | None = None
    accuracy: Metric | None = None
    metrics: dict[str, Metric] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """What a results file stores for this node."""
        return {
            "node_id": self.node_id,
            "node_kind": self.node_kind,
            "runs": self.runs,
            "reached": self.reached,
            "reach": self.reach.to_record() if self.reach is not None else None,
            "accuracy": self.accuracy.to_record() if self.accuracy is not None else None,
            "metrics": {name: m.to_record() for name, m in self.metrics.items()},
            "executions": self.executions,
            "errors": self.errors,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "paid_tool_calls": self.paid_tool_calls,
            "tool_spend": self.tool_spend,
            "tool_spend_currency": self.tool_spend_currency,
            "consultations": self.consultations,
            "consultation_resolutions": dict(sorted(self.consultation_resolutions.items())),
            "consultation_answered_by": dict(sorted(self.consultation_answered_by.items())),
            "consultation_misreadings": self.consultation_misreadings,
            "resource_reads": dict(sorted(self.resource_reads.items())),
            "resource_writes": dict(sorted(self.resource_writes.items())),
            "delegations": self.delegations,
            "replayed_calls": self.replayed_calls,
            "wall_clock_ms": self.wall_clock_ms,
            "absent_outputs": self.absent_outputs,
            "unfinished_executions": self.unfinished_executions,
            "unfinished_items": self.unfinished_items,
            "unfinished_without_tool_calls": self.unfinished_without_tool_calls,
            "unfinished_model_calls": self.unfinished_model_calls,
            "unfinished_model_calls_without_tool_calls": (
                self.unfinished_model_calls_without_tool_calls
            ),
            "empty_responses": self.empty_responses,
            "delegations_out_of_budget": self.delegations_out_of_budget,
            "tools_that_never_succeeded": dict(sorted(self.tools_that_never_succeeded.items())),
            "terminations": dict(sorted(self.terminations.items())),
            "tokens": dict(self.tokens),
            "cost": (self.cost or Cost(value=None, currency=None, basis=None)).to_record(),
        }

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> NodeMetrics:
        """Rebuild one node's metrics from a results file."""
        cost = raw.get("cost") or {}
        reach = raw.get("reach")
        accuracy = raw.get("accuracy")
        return cls(
            node_id=str(raw["node_id"]),
            node_kind=str(raw.get("node_kind", "unknown")),
            runs=int(raw.get("runs", 0)),
            reached=int(raw.get("reached", 0)),
            reach=Metric.from_record(reach) if reach else None,
            accuracy=Metric.from_record(accuracy) if accuracy else None,
            metrics={
                str(name): Metric.from_record(entry)
                for name, entry in (raw.get("metrics") or {}).items()
            },
            executions=int(raw.get("executions", 0)),
            errors=int(raw.get("errors", 0)),
            model_calls=int(raw.get("model_calls", 0)),
            tool_calls=int(raw.get("tool_calls", 0)),
            paid_tool_calls=int(raw.get("paid_tool_calls", 0)),
            tool_spend=raw.get("tool_spend"),
            tool_spend_currency=raw.get("tool_spend_currency"),
            consultations=int(raw.get("consultations", 0)),
            consultation_resolutions=dict(raw.get("consultation_resolutions") or {}),
            consultation_answered_by=dict(raw.get("consultation_answered_by") or {}),
            consultation_misreadings=int(raw.get("consultation_misreadings", 0)),
            resource_reads={
                str(name): int(count) for name, count in (raw.get("resource_reads") or {}).items()
            },
            resource_writes={
                str(name): int(count) for name, count in (raw.get("resource_writes") or {}).items()
            },
            delegations=int(raw.get("delegations", 0)),
            replayed_calls=int(raw.get("replayed_calls", 0)),
            wall_clock_ms=int(raw.get("wall_clock_ms", 0)),
            absent_outputs=int(raw.get("absent_outputs", 0)),
            unfinished_executions=int(raw.get("unfinished_executions", 0)),
            unfinished_items=int(raw.get("unfinished_items", 0)),
            unfinished_without_tool_calls=int(raw.get("unfinished_without_tool_calls", 0)),
            unfinished_model_calls=int(raw.get("unfinished_model_calls", 0)),
            unfinished_model_calls_without_tool_calls=int(
                raw.get("unfinished_model_calls_without_tool_calls", 0)
            ),
            empty_responses=int(raw.get("empty_responses", 0)),
            delegations_out_of_budget=int(raw.get("delegations_out_of_budget", 0)),
            tools_that_never_succeeded={
                str(name): int(count)
                for name, count in (raw.get("tools_that_never_succeeded") or {}).items()
            },
            terminations=dict(raw.get("terminations") or {}),
            tokens=dict(raw.get("tokens") or {}),
            cost=Cost.from_record(cost),
        )


def node_metrics(
    run_dir: str | os.PathLike[str],
    *,
    role: str | None = None,
    live: bool | None = None,
    scripted: bool | None = False,
    since: str | None = None,
    last: int | None = None,
    cost_basis: CostBasis | None = None,
) -> dict[str, NodeMetrics]:
    """What every node did across the runs under a directory, read from what they wrote.

    Nothing here imports the project's pipeline, so this reads runs from another process or
    another terminal. An evaluation reports the same figures for its own rollouts; this is how
    they are read over runs an evaluation did not make::

        from simple_agents import node_metrics

        found = node_metrics("runs/")
        found["hunt"].unfinished_executions    # ended without producing an output
        found["hunt"].unfinished_model_calls   # what those spent

    Every run at any depth is read, so a directory holding evaluations is read as the rollouts
    inside them. ``role``, ``live`` and ``scripted`` filter the same way
    :func:`~simple_agents.runs` does, so a run whose model answered from a script is left out
    unless ``scripted=None``; ``since`` takes runs that started at or after an ISO timestamp,
    matched as text, and ``last`` keeps the newest that many of what the others left::

        node_metrics("runs/", role="agent", since="2026-08-14", last=500)

    Reading fewer runs reports figures over fewer runs, and ``runs`` on each result says how
    many were read.

    ``cost_basis`` is what cost is derived against, as on the envelope that wrote the runs.
    Without one, each node's ``cost`` reports unknown, and every other figure is unaffected.
    """
    found = runs_under(
        Path(run_dir), nested=True, role=role, live=live, scripted=scripted, since=since, last=last
    )
    return per_node(
        (read_trajectory(handle.trajectory_path) for handle in found),
        cost_basis=cost_basis,
    )


def per_node(
    runs: Iterable[Iterable[Mapping[str, Any]]], *, cost_basis: CostBasis | None = None
) -> dict[str, NodeMetrics]:
    """Metrics per node, accumulated over the trajectories of every rollout.

    Each item of ``runs`` is one rollout's records, in the order they were written::

        per_node((read_trajectory(p) for p in paths), cost_basis=env.cost_basis)

    A model call made inside a tool is attributed to the node that called the tool, since its
    ``parent_id`` is the tool call and the tool call's parent is the node.
    """
    found: dict[str, NodeMetrics] = {}
    # Every call each node made to each tool, over all the runs together. A tool that failed in
    # one rollout and worked in the next did not fail every time, and a per-run count could not
    # say so.
    tried: dict[tuple[str, str], list[int]] = {}
    observed = 0
    for records in runs:
        observed += 1
        _accumulate(list(records), found, cost_basis, tried)
    for metrics in found.values():
        metrics.runs = observed
    _name_failed_tools(tried, found)
    return found


def reached_in(records: Iterable[Mapping[str, Any]]) -> set[str]:
    """The nodes that ran in one rollout, which is not every node in the pipeline.

    A node that was skipped emits a record and is not here, which is what separates a node that
    ran and produced nothing from one no path reached.
    """
    return {
        str(record.get("node_id"))
        for record in records
        if record.get("record_type") == "node_execution" and record.get("termination") != "skipped"
    }


def node_scores(rollouts: Any, node_id: str, *, kind: str) -> dict[str, list[float]]:
    """One node's per-example scores, in rollout order, for one figure it carries.

    ``kind`` is ``reach``, ``accuracy``, or the name of a project metric declared for the node.
    A rollout that carries no observation for the node did not reach it. For everything but
    ``reach``, only the rollouts that reached the node and carry a figure are included, so an
    example the node never ran on is absent rather than scoring zero.
    """
    grouped: dict[str, list[Any]] = {}
    for rollout in rollouts:
        grouped.setdefault(rollout.example_id, []).append(rollout)

    found: dict[str, list[float]] = {}
    for example_id, group in grouped.items():
        ordered = sorted(group, key=lambda r: r.rollout)
        if kind == "reach":
            found[example_id] = [
                1.0 if r.nodes.get(node_id) and r.nodes[node_id].reached else 0.0 for r in ordered
            ]
            continue
        if kind == "accuracy":
            scores = [
                1.0 if r.nodes[node_id].matched else 0.0
                for r in ordered
                if node_id in r.nodes and r.nodes[node_id].matched is not None
            ]
        else:
            scores = [
                float(r.nodes[node_id].scores[kind])
                for r in ordered
                if node_id in r.nodes and kind in r.nodes[node_id].scores
            ]
        if scores:
            found[example_id] = scores
    return found


def node_rates(
    nodes: Mapping[str, NodeMetrics],
    rollouts: Sequence[RolloutOutcome],
    *,
    project: Mapping[str, Sequence[ProjectMetric]] | None = None,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> None:
    """Fill ``reach``, ``accuracy`` and the project metrics on each node.

    All of them resample examples rather than rollouts, like every other interval the library
    reports, so two rollouts of one example do not count as two independent observations.
    ``accuracy`` is left ``None`` for a node no example labels.

    ``project`` names the figures declared per node. Their scores are read off the rollouts
    rather than recomputed here, and a ``ProjectRatio`` is summed from the pairs each rollout
    contributed rather than averaged.
    """
    by_example: dict[str, list[RolloutOutcome]] = {}
    for rollout in rollouts:
        by_example.setdefault(rollout.example_id, []).append(rollout)

    for node_id, declared in (project or {}).items():
        if node_id not in nodes:
            continue
        for metric in declared:
            if isinstance(metric, ProjectRatio):
                nodes[node_id].metrics[metric.name] = ratio_metric(
                    declared=metric,
                    grouped=_pairs_by_example(by_example, node_id, metric.name),
                    confidence=confidence,
                    resamples=resamples,
                    seed=seed,
                )
                continue
            nodes[node_id].metrics[metric.name] = _rate(
                name=metric.name,
                definition=metric.definition,
                population=(
                    f"{metric.population}, of the rollouts that reached this node and carry "
                    f"a label for it"
                ),
                grouped=list(node_scores(rollouts, node_id, kind=metric.name).values()),
                confidence=confidence,
                resamples=resamples,
                seed=seed,
                unit=metric.unit,
            )

    for node_id, metrics in nodes.items():
        metrics.reach = _rate(
            name="reach",
            definition=REACH_DEFINITION,
            population="all rollouts",
            grouped=list(node_scores(rollouts, node_id, kind="reach").values()),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
        )
        labelled = list(node_scores(rollouts, node_id, kind="accuracy").values())
        metrics.accuracy = (
            _rate(
                name="accuracy",
                definition=ACCURACY_DEFINITION,
                population="rollouts that reached this node and carry a label for it",
                grouped=labelled,
                confidence=confidence,
                resamples=resamples,
                seed=seed,
            )
            if labelled
            else None
        )


def _pairs_by_example(
    by_example: Mapping[str, Sequence[RolloutOutcome]], node_id: str, name: str
) -> list[list[tuple[float, float]]]:
    """One list of ``(numerator, denominator)`` pairs per example, empty lists dropped.

    A ratio is summed rather than averaged, so what an example contributes is its rollouts'
    pairs. Grouping by example is what makes k rollouts of one example travel together in a
    resample, as they do for every other figure.
    """
    grouped = [
        [
            rollout.nodes[node_id].ratios[name]
            for rollout in group
            if node_id in rollout.nodes and name in rollout.nodes[node_id].ratios
        ]
        for group in by_example.values()
    ]
    return [pairs for pairs in grouped if pairs]


def _rate(
    *,
    name: str,
    definition: str,
    population: str,
    grouped: list[list[float]],
    confidence: float,
    resamples: int,
    seed: int,
    unit: str | None = RATE,
) -> Metric:
    return _metric(
        name=name,
        definition=definition,
        population=population,
        grouped=[scores for scores in grouped if scores],
        confidence=confidence,
        resamples=resamples,
        seed=seed,
        unit=unit,
    )


def _accumulate(
    records: list[Mapping[str, Any]],
    found: dict[str, NodeMetrics],
    basis: CostBasis | None,
    tried: dict[tuple[str, str], list[int]],
) -> None:
    by_id = {str(r.get("record_id")): r for r in records}
    node_ids = {
        record_id: str(record.get("node_id"))
        for record_id, record in by_id.items()
        if record.get("record_type") == "node_execution"
    }
    kinds = {
        str(r.get("node_id")): str(r.get("node_kind"))
        for r in records
        if r.get("record_type") == "node_execution"
    }
    owner = _owners(by_id, node_ids)

    calls: dict[str, list[Mapping[str, Any]]] = {}
    for record_id, record in by_id.items():
        node_id = owner.get(record_id)
        if node_id is None:
            continue
        metrics = found.setdefault(
            node_id, NodeMetrics(node_id=node_id, node_kind=kinds.get(node_id, "unknown"))
        )
        _count(record, metrics)
        if record.get("record_type") == "model_call":
            calls.setdefault(node_id, []).append(record)

    _count_unfinished(by_id, node_ids, found)
    _count_tool_outcomes(by_id, owner, tried)

    for node_id, made in calls.items():
        spent = total_cost(made, basis)
        current = found[node_id].cost
        found[node_id].cost = spent if current is None else current.plus(spent)

    # Once per rollout, whatever the node did in it. A node inside a bounded cycle runs several
    # times and was reached once.
    for node_id in reached_in(records):
        if node_id in found:
            found[node_id].reached += 1


def _count_unfinished(
    by_id: Mapping[str, Mapping[str, Any]],
    node_ids: Mapping[str, str],
    found: dict[str, NodeMetrics],
) -> None:
    """Add the unfinished figures onto the metrics of each node that has any."""
    for node_id, counts in _unfinished_in(by_id, node_ids).items():
        metrics = found.get(node_id)
        if metrics is None:
            continue
        metrics.unfinished_executions += counts["executions"]
        metrics.unfinished_items += counts["items"]
        metrics.unfinished_without_tool_calls += counts["without_tool_calls"]
        metrics.unfinished_model_calls += counts["model_calls"]
        metrics.unfinished_model_calls_without_tool_calls += counts[
            "model_calls_without_tool_calls"
        ]


def _count_tool_outcomes(
    by_id: Mapping[str, Mapping[str, Any]],
    owner: Mapping[str, str],
    tried: dict[tuple[str, str], list[int]],
) -> None:
    """Add one run's tool calls, and how many of them failed, to the running counts."""
    for record_id, record in by_id.items():
        if record.get("record_type") != "tool_call":
            continue
        node_id = owner.get(record_id)
        if node_id is None:
            continue
        seen = tried.setdefault((node_id, str(record.get("tool_name"))), [0, 0])
        seen[0] += 1
        if record.get("error") is not None:
            seen[1] += 1


def _name_failed_tools(
    tried: Mapping[tuple[str, str], list[int]], found: dict[str, NodeMetrics]
) -> None:
    """Name the tools a node called that never once answered, over every run read.

    A tool that failed and later succeeded is not one of these, and later can be in another
    run: read per run, a tool that worked in the second rollout would still be reported as
    having failed every time in the first.
    """
    for (node_id, tool_name), (calls, failed) in tried.items():
        metrics = found.get(node_id)
        if metrics is not None and calls == failed:
            metrics.tools_that_never_succeeded[tool_name] = calls


def unfinished_work(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    """Per node, the units of work that ended without an output and what they spent.

    A unit is one execution of a node, or one item of a fan-out. Both produced nothing, since
    an ``AgentNode`` produces its output from a ``finish`` call. Nodes with nothing to report
    are absent, so an empty result is a run in which every unit of work produced something::

        unfinished_work(read_trajectory("runs/run_7f2a/trajectory.jsonl"))
        # {'hunt': {'executions': 1, 'items': 0, 'without_tool_calls': 1,
        #           'model_calls': 18, 'model_calls_without_tool_calls': 18}}

    ``model_calls`` is every call underneath those units, including the ones their tools made.
    ``without_tool_calls`` counts the units that made no tool call, no consultation and no
    delegation, which is a loop that spent its allowance without once acting, and
    ``model_calls_without_tool_calls`` is what those spent. FT-35 gates on the last of these
    and each run's manifest carries the block (``docs/run-envelope.md`` §2.8).
    """
    by_id = {str(r.get("record_id")): r for r in records}
    node_ids = {
        record_id: str(record.get("node_id"))
        for record_id, record in by_id.items()
        if record.get("record_type") == "node_execution"
    }
    return _unfinished_in(by_id, node_ids)


def _unfinished_in(
    by_id: Mapping[str, Mapping[str, Any]], node_ids: Mapping[str, str]
) -> dict[str, dict[str, int]]:
    """The counts themselves, over records already indexed by their id."""
    found: dict[str, dict[str, int]] = {}

    def counts(node_id: str) -> dict[str, int]:
        return found.setdefault(
            node_id,
            {
                "executions": 0,
                "items": 0,
                "without_tool_calls": 0,
                "model_calls": 0,
                "model_calls_without_tool_calls": 0,
            },
        )

    inside = _executions(by_id, node_ids)
    spent: dict[tuple[str, Any], int] = {}
    acted: dict[tuple[str, Any], int] = {}
    for record_id, record in by_id.items():
        holder = inside.get(record_id)
        if holder is None or holder == record_id:
            continue
        kind = record.get("record_type")
        # An item's calls are its own. Outside a fan-out every record carries `None` here, so
        # one key covers both cases and the execution's own total needs no second pass.
        key = (holder, record.get("item_index"))
        if kind == "model_call":
            spent[key] = spent.get(key, 0) + 1
        elif kind in ("tool_call", "consultation", "delegation"):
            acted[key] = acted.get(key, 0) + 1

    for record_id, node_id in node_ids.items():
        record = by_id[record_id]
        if str(record.get("termination") or "") in UNFINISHED:
            here = counts(node_id)
            here["executions"] += 1
            here["model_calls"] += spent.get((record_id, None), 0)
            if not acted.get((record_id, None)):
                here["without_tool_calls"] += 1
                here["model_calls_without_tool_calls"] += spent.get((record_id, None), 0)
        # A tool call has named its item since trajectory format 0.26. On an older record
        # the calling item is unknown, and its items are left out of the figure that counts
        # a unit of work that never acted rather than being reported as inert.
        attributable = _at_least(record.get("format_version"), (0, 26))
        for item in _items_of(record.get("outputs")):
            if str(item.get("termination") or "") not in UNFINISHED:
                continue
            index = item.get("index")
            here = counts(node_id)
            here["items"] += 1
            here["model_calls"] += spent.get((record_id, index), 0)
            if attributable and not acted.get((record_id, index)):
                here["without_tool_calls"] += 1
                here["model_calls_without_tool_calls"] += spent.get((record_id, index), 0)
    return found


def unfinished_lines(node: NodeMetrics) -> list[str]:
    """What one node spent and produced nothing with, as lines under its row in a report.

    One line per figure that is not zero, indented by whatever prints them, so a node that
    finished everything it started carries none::

        unfinished_lines(results.nodes["hunt"])
        # ['produced nothing: 93 unit(s) of work, 3 of them fan-out item(s), spending ...',
        #  '88 of those 93 made no tool call, consultation or delegation, spending ...']

    Every report of these figures prints these lines, so the two cannot drift, and each names
    what its figure is over. `docs/evaluation.md` §5.
    """
    units = node.unfinished_executions + node.unfinished_items
    lines = []
    if units:
        # A unit is an execution or a fan-out item, and the spend covers both, so the count
        # this figure is over is the two together rather than the executions alone.
        items = (
            f", {node.unfinished_items:,} of them fan-out item(s)" if node.unfinished_items else ""
        )
        lines.append(
            f"produced nothing: {units:,} unit(s) of work{items}, spending "
            f"{node.unfinished_model_calls:,} of {node.model_calls:,} model call(s)"
        )
    if node.unfinished_without_tool_calls:
        lines.append(
            f"{node.unfinished_without_tool_calls:,} of those {units:,} made no tool call, "
            f"consultation or delegation, spending "
            f"{node.unfinished_model_calls_without_tool_calls:,} model call(s) (FT-35)"
        )
    if node.empty_responses:
        lines.append(f"{node.empty_responses:,} call(s) came back with no content and no tool call")
    if node.delegations_out_of_budget:
        lines.append(
            f"{node.delegations_out_of_budget:,} of {node.delegations:,} subtask(s) ran the "
            f"delegated pipeline out of budget"
        )
    if node.tools_that_never_succeeded:
        named = ", ".join(
            f"{name} {count:,}" for name, count in sorted(node.tools_that_never_succeeded.items())
        )
        lines.append(f"tools whose every call failed: {named}")
    return lines


def _at_least(version: Any, wanted: tuple[int, int]) -> bool:
    """Whether a record declares this format version or a later one."""
    parts = str(version or "").split(".")
    try:
        return (int(parts[0]), int(parts[1])) >= wanted
    except (IndexError, ValueError):
        return False


def _items_of(outputs: Any) -> list[Mapping[str, Any]]:
    """The fan-out entries a node recorded, and nothing where it did not fan out.

    A run whose payloads were dropped by sampling records ``not_recorded`` here, which holds
    no items and is not a node that produced none.
    """
    if not isinstance(outputs, Mapping):
        return []
    items = outputs.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def _executions(
    by_id: Mapping[str, Mapping[str, Any]], node_ids: Mapping[str, str]
) -> dict[str, str]:
    """Which node execution each record happened inside, by its own ``record_id``.

    ``_owners`` answers which node, which is the same walk over ``parent_id``; this keeps the
    execution, so two executions of one node in a cycle stay apart.
    """
    resolved: dict[str, str] = {}
    for record_id in by_id:
        current = record_id
        for _ in range(len(by_id) + 1):
            if current in node_ids:
                resolved[record_id] = current
                break
            parent = by_id.get(current, {}).get("parent_id")
            if parent is None:
                break
            current = str(parent)
    return resolved


def _owners(by_id: Mapping[str, Mapping[str, Any]], node_ids: Mapping[str, str]) -> dict[str, str]:
    """Which node each record happened inside, following ``parent_id`` up to a node record.

    A model call made inside a tool has that tool call as its parent, so the walk takes two
    steps rather than one and the tokens land on the node whose tool spent them.
    """
    resolved: dict[str, str] = {}
    for record_id in by_id:
        current = record_id
        for _ in range(len(by_id) + 1):
            if current in node_ids:
                resolved[record_id] = node_ids[current]
                break
            parent = by_id.get(current, {}).get("parent_id")
            if parent is None:
                break
            current = str(parent)
    return resolved


def _count(record: Mapping[str, Any], metrics: NodeMetrics) -> None:
    kind = record.get("record_type")
    if kind == "node_execution":
        termination = record.get("termination")
        # A node the run stopped inside is two records, and the second names the first.
        # `docs/trajectory-format.md` §3 says both describe one logical execution, so counting
        # them means counting the ones where `resumed_from` is null.
        if termination != "skipped" and record.get("resumed_from") is None:
            metrics.executions += 1
        if record.get("error"):
            metrics.errors += 1
        if termination:
            metrics.terminations[str(termination)] = (
                metrics.terminations.get(str(termination), 0) + 1
            )
        elapsed = _elapsed_ms(record)
        if elapsed is not None:
            metrics.wall_clock_ms += elapsed
        if holds_absence(record.get("outputs")):
            metrics.absent_outputs += 1
    elif kind == "model_call":
        metrics.model_calls += 1
        if returned_nothing(record):
            metrics.empty_responses += 1
        if record.get("replayed"):
            metrics.replayed_calls += 1
        _add_tokens(record.get("tokens") or {}, metrics.tokens)
    elif kind == "tool_call":
        metrics.tool_calls += 1
        spent = record.get("spent")
        if isinstance(spent, Mapping) and isinstance(spent.get("amount"), (int, float)):
            metrics.tool_spend = (metrics.tool_spend or 0.0) + float(spent["amount"])
            metrics.paid_tool_calls += 1
            metrics.tool_spend_currency = metrics.tool_spend_currency or spent.get("currency")
    elif kind == "consultation":
        # A question answered in a later process is two records, and the second names the
        # first. Counting both would report one question twice, so only the asking record is
        # counted here and the answering one supplies the resolution it ended on.
        if record.get("answers") is None:
            metrics.consultations += 1
        resolution = str(record.get("resolution") or "pending")
        metrics.consultation_resolutions[resolution] = (
            metrics.consultation_resolutions.get(resolution, 0) + 1
        )
        answered_by = record.get("answered_by")
        if answered_by is not None:
            metrics.consultation_answered_by[str(answered_by)] = (
                metrics.consultation_answered_by.get(str(answered_by), 0) + 1
            )
        declared = record.get("declared_choice")
        if declared is not None and declared != record.get("chose"):
            metrics.consultation_misreadings += 1
    elif kind == "resource_access":
        side = (
            metrics.resource_writes
            if record.get("direction") == "write"
            else metrics.resource_reads
        )
        name = str(record.get("resource") or "?")
        side[name] = side.get(name, 0) + 1
    elif kind == "delegation":
        # A subtask the run stopped inside is two records, and the second names the first.
        # Counting both would report one subtask twice, which is the rule a consultation
        # already follows above. `budget` can only land on the record that ended the subtask,
        # so the figure below needs no such guard.
        if record.get("resumed_from") is None:
            metrics.delegations += 1
        if record.get("termination") == "budget":
            metrics.delegations_out_of_budget += 1


def returned_nothing(record: Mapping[str, Any]) -> bool:
    """Whether a model call came back with no content and no tool call.

    Reasoning is not content. A call that spent its whole output ceiling on a chain of thought
    returned nothing the loop can act on, which is what this reports.

    Three kinds of call are not one of these. One whose payloads the run did not keep, since
    what it returned cannot be read. And an embedding or a rerank, which record what came back
    in their own shape and have no content to be missing: a call with neither field is not a
    completion at all.
    """
    outputs = record.get("outputs")
    if not isinstance(outputs, Mapping) or outputs.get("type") == "not_recorded":
        return False
    if "content" not in outputs and "tool_calls" not in outputs:
        return False
    return not outputs.get("content") and not outputs.get("tool_calls")


def _add_tokens(reported: Mapping[str, Any], running: dict[str, Any]) -> None:
    """Sum one call's counts into the running total, keeping an unmeasured class unmeasured.

    A class the backend reported as unknown makes that class unknown for the node. Adding zero
    in its place would report a total lower than what was spent.
    """
    for name in _TOKEN_FIELDS:
        value = reported.get(name)
        current = running.get(name, 0)
        if isinstance(current, dict):
            continue
        if isinstance(value, dict) and value.get("type") == "unknown":
            running[name] = {
                "type": "unknown",
                "reason": value.get("reason") or "reported as unknown",
            }
        elif isinstance(value, (int, float)):
            running[name] = current + int(value)


def _elapsed_ms(record: Mapping[str, Any]) -> int | None:
    seconds = duration_seconds(record)
    return int(seconds * 1000) if seconds is not None else None


def holds_absence(value: Any) -> bool:
    """Whether a reported absence appears anywhere in a node's output.

    A node returns a schema object, so an absence sits in one of its fields rather than being
    the whole value. Both forms of that field count: the ``Unknown`` a decoded output carries,
    and the tagged object a record holds on disk::

        holds_absence({"answer": Unknown(reason="not published")})            # True
        holds_absence({"answer": {"type": "unknown", "reason": "..."}})       # True
    """
    if isinstance(value, Unknown):
        return True
    if isinstance(value, Mapping):
        if value.get("type") == "unknown":
            return True
        return any(holds_absence(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(holds_absence(item) for item in value)
    return False
