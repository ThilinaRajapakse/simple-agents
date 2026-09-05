"""What a directory of runs did, as text and as a record.

``simple-agents report`` prints this. It reads the run directories the envelope wrote and the
trajectories inside them, imports no project code and makes no network call.

A figure over many runs is only as good as what it says it covers, so every report names how
many runs it read of how many are there, and what narrowed it.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..cost import DEVICE_SECONDS, Cost, CostBases, basis_from_manifest
from ..envelope import ABANDONED, RUNNING, RunHandle, narrowed, runs as runs_under
from ..evaluation.per_node import NodeMetrics, per_node, unfinished_lines
from ..records.trajectory import read_trajectory

__all__ = ["RunsReport", "report_over_runs"]

# How wide the node column is allowed to grow before the figures stop lining up. A delegated
# node carries its whole path, and one long id would otherwise indent every row after it.
_NODE_WIDTH = 28


@dataclass(frozen=True, slots=True)
class RunsReport:
    """What the runs under one directory did, per node.

    Produced by :func:`report_over_runs`::

        report = report_over_runs("runs/", role="agent")
        print(report.text())
        report.nodes["hunt"].unfinished_model_calls

    ``read`` is how many runs the figures are over and ``found`` how many are under the
    directory, so a scoped report says what it left out. ``unread`` names the runs whose
    trajectory could not be read: they are in ``found``, in no figure here, and named in the
    text so the two numbers account for each other.
    """

    root: str
    read: int
    found: int
    narrowed_by: dict[str, Any] = field(default_factory=dict)
    started: tuple[str, str] | None = None
    outcomes: dict[str, int] = field(default_factory=dict)
    roles: dict[str, int] = field(default_factory=dict)
    sliced: int = 0
    """How many of the runs read were made by a slice of a pipeline rather than a whole one.

    A rung keeps the node ids of the pipeline it came from and runs under the same role, so its
    figures sit in this table beside the agent's own with nothing separating them. The node it
    starts at ran on every rollout of the rung and on some share of the agent's, which makes
    `reach` and every count over it a different figure with the same name."""

    live: int = 0
    scripted_left_out: int = 0
    """How many runs under the directory answered from a script rather than from a backend.

    Left out of every figure by default, since they spent nothing and their answers were
    written rather than produced. One project's report counted 1,846 such calls as spend and
    read 318 of their fan-out items as work that produced nothing. ``--scripted`` includes
    them and this is what says how many are being left out."""

    nodes: dict[str, NodeMetrics] = field(default_factory=dict)
    spend: dict[str, float] = field(default_factory=dict)
    spend_is_floor: bool = False
    unpriced_runs: int = 0
    unpriced_calls: int = 0
    basis_reason: str | None = None
    unread: tuple[str, ...] = ()
    tools: dict[str, tuple[int, int]] = field(default_factory=dict)
    """Per tool: the runs that registered it, and the runs that called it. A capability
    registered across a directory and called in few of its runs is visible here and nowhere
    else, since a per-node count says how many calls a node made rather than to what."""

    @property
    def model_calls(self) -> int:
        """Model calls over every node, including the ones the nodes' tools made."""
        return sum(node.model_calls for node in self.nodes.values())

    @property
    def tool_calls(self) -> int:
        """Tool calls over every node."""
        return sum(node.tool_calls for node in self.nodes.values())

    def to_record(self) -> dict[str, Any]:
        """The report as data, which is what ``--json`` prints."""
        return {
            "root": self.root,
            "runs": {
                "read": self.read,
                "found": self.found,
                "narrowed_by": self.narrowed_by,
                "started": list(self.started) if self.started else None,
                "outcomes": self.outcomes,
                "roles": self.roles,
                "sliced": self.sliced,
                "live": self.live,
                "scripted_left_out": self.scripted_left_out,
                "unread": list(self.unread),
            },
            "totals": {
                "model_calls": self.model_calls,
                "tool_calls": self.tool_calls,
                "spend": self.spend,
                "spend_is_floor": self.spend_is_floor,
                "unpriced_runs": self.unpriced_runs,
                "unpriced_calls": self.unpriced_calls,
                "cost_basis": self.basis_reason,
            },
            "nodes": {node_id: node.to_record() for node_id, node in self.nodes.items()},
            "tools": {
                name: {"registered_in": registered, "called_in": called}
                for name, (registered, called) in self.tools.items()
            },
        }

    def text(self) -> str:
        """The report as it reads on a terminal."""
        lines = [f"simple-agents report: {self.root}", ""]
        lines.extend(self._covered())
        lines.extend(self._unread())
        if self.nodes:
            lines.append("")
            lines.extend(self._table())
            if self.basis_reason:
                lines += ["", f"  {self.basis_reason}"]
        lines.extend(self._tools())
        return "\n".join(lines)

    def _tools(self) -> list[str]:
        """Each registered tool, and how much of the directory ever called it."""
        if not self.tools:
            return []
        width = max(len(name) for name in self.tools)
        lines = ["", f"  {'tool':<{width}}  {'registered in':>13}  {'called in':>9}"]
        for name, (registered, called) in sorted(
            self.tools.items(), key=lambda item: (-item[1][1], item[0])
        ):
            lines.append(f"  {name:<{width}}  {registered:>13,}  {called:>9,}")
        return lines

    def _unread(self) -> list[str]:
        """The runs no figure here covers, named rather than left out silently."""
        if not self.unread:
            return []
        named = ", ".join(self.unread[:3])
        rest = f" and {len(self.unread) - 3} more" if len(self.unread) > 3 else ""
        return [
            f"  {len(self.unread)} run(s) recorded no trajectory this could read, so no "
            f"figure here covers them: {named}{rest}."
        ]

    def _activity_line(self) -> str:
        """The calls and the money, with the money saying whether it is a floor.

        A run whose total could not be derived contributes what it did measure, so the figure
        is `at least` and the calls missing from it are named beside it.
        """
        floor = "at least " if self.spend_is_floor else ""
        spend = ", ".join(
            f"{floor}{amount:.4f} {currency}".strip()
            for currency, amount in sorted(self.spend.items())
        )
        # A manifest written before the call counts existed carries no `unpriced_calls`, so
        # the run count is all there is to say and saying `0 call(s)` would be false.
        if self.unpriced_calls:
            unpriced = (
                f", {self.unpriced_calls:,} call(s) in {self.unpriced_runs:,} run(s) could "
                f"not be priced"
            )
        elif self.unpriced_runs:
            unpriced = f", {self.unpriced_runs:,} run(s) whose cost could not be measured"
        else:
            unpriced = ""
        return (
            f"  {self.model_calls:,} model call(s), {self.tool_calls:,} tool call(s)"
            + (f", {spend}" if spend else "")
            + unpriced
        )

    def _covered(self) -> list[str]:
        """What was read, before any figure derived from it."""
        of = f" of {self.found:,}" if self.found != self.read else ""
        when = f", {self.started[0][:10]} to {self.started[1][:10]}" if self.started else ""
        narrowed = ", ".join(f"{name} {value}" for name, value in self.narrowed_by.items())
        lines = [f"  {self.read:,}{of} run(s){when}" + (f", {narrowed}" if narrowed else "")]
        if not self.read:
            lines.append(self._why_nothing_was_read())
            return lines
        lines.append(self._activity_line())
        if self.outcomes:
            lines.append(
                "  "
                + ", ".join(f"{name} {count:,}" for name, count in sorted(self.outcomes.items()))
            )
        # Every role is read unless one was named, so a report over a project that ran a
        # labelling pass says how many of these runs were not the agent's.
        if len(self.roles) > 1:
            lines.append(
                "  roles: "
                + ", ".join(f"{name} {count:,}" for name, count in sorted(self.roles.items()))
            )
        # Same hazard as a mixed `roles`, and it does not show there: a rung runs under the
        # role the agent does and keeps its node ids.
        if self.sliced:
            lines.append(
                f"  {self.sliced:,} of them made by a slice of a pipeline, whose node "
                f"figures are over that slice rather than over the whole graph"
            )
        if self.live:
            lines.append(f"  {self.live:,} of them made by an end user")
        if self.scripted_left_out:
            lines.append(
                f"  {self.scripted_left_out:,} run(s) whose model answered from a script are "
                f"left out, and `--scripted` includes them"
            )
        return lines

    def _why_nothing_was_read(self) -> str:
        """The line under a report over no runs at all.

        A project whose runs were scripted has runs, and a report saying only that it read none
        sends a reader to check the path they gave.
        """
        if self.scripted_left_out == self.found and self.found:
            return (
                "  Every run under this path answered from a script, so no figure here is "
                "over anything. `--scripted` reads them: "
                "`simple-agents report <path> --scripted`."
            )
        if self.scripted_left_out:
            return (
                f"  No figure here is over anything: {self.scripted_left_out:,} of the "
                f"{self.found:,} run(s) under this path answered from a script and "
                f"`--scripted` reads those, and the rest were left out by the filters or "
                f"could not be read."
            )
        return (
            "  No figure here is over anything. `simple-agents report <path>` reads a run "
            "directory, a directory of runs, or an evaluation's results file."
        )

    def _cost(self, node: NodeMetrics) -> str:
        """What this node's model calls cost, or why no figure is derived for it.

        A node's own reason is printed where there is one. Where the runs disagreed about the
        basis there is no reason on the node to print, since nothing was derived at all, and
        the line under the table is what says so.
        """
        if self.basis_reason is not None:
            return "unknown"
        return node.cost.describe() if node.cost is not None else "unknown"

    def _table(self) -> list[str]:
        width = min(max(len(node_id) for node_id in self.nodes), _NODE_WIDTH)
        lines = [
            f"  {'node':<{width}}  {'kind':<13} {'execs':>7} {'calls':>7} {'tools':>7} "
            f"{'unfinished':>12} {'its calls':>10}  cost"
        ]
        for node_id, node in self.nodes.items():
            # A node that made no model call spent nothing on one, which is not the same as a
            # cost that could not be measured. `tool spend` reads `-` for the same reason.
            cost = "-" if not node.model_calls else self._cost(node)
            lines.append(
                f"  {node_id:<{width}}  {node.node_kind:<13} {node.executions:>7,} "
                f"{node.model_calls:>7,} {node.tool_calls:>7,} "
                f"{_share(node.unfinished_executions, node.executions):>12} "
                f"{node.unfinished_model_calls:>10,}  {cost}"
            )
            lines.extend(f"  {'':<{width}}  {line}" for line in unfinished_lines(node))
        return lines


def _share(part: int, whole: int) -> str:
    """A count with what it is of, or nothing at all where it is zero.

    A share that rounds to nothing prints as under one percent, because a count beside `0%`
    reads as a rounding error rather than as one execution in two hundred.
    """
    if not part:
        return "-"
    if not whole:
        return f"{part:,}"
    share = part / whole
    return f"{part:,} ({share:.0%})" if share >= 0.005 else f"{part:,} (<1%)"


def report_over_runs(
    run_dir: str | os.PathLike[str],
    *,
    role: str | None = None,
    live: bool | None = None,
    pipeline: str | None = None,
    trigger: str | None = None,
    scripted: bool | None = False,
    since: str | None = None,
    last: int | None = None,
) -> RunsReport:
    """Read every run under a directory and report what each node did.

    ::

        from simple_agents.cli.reporting import report_over_runs

        print(report_over_runs("runs/", role="agent").text())

    Reads runs at any depth, so a directory holding evaluations is read as the rollouts inside
    them. ``role``, ``live``, ``pipeline``, ``trigger``, ``scripted``, ``since`` and ``last``
    narrow it the way :func:`~simple_agents.runs` does, and the report names what they left out. A run whose
    model answered from a script is left out unless ``scripted`` says otherwise, and the
    report says how many those were.

    Cost is derived against the basis the runs recorded, where every run read recorded the same
    one. Where they differ, each node's cost reports unknown and the report says why.
    """
    root = Path(run_dir)
    # Everything, so `found` counts what is under the directory and the scripted runs can be
    # counted before they are left out. `narrowed` is what applies the filters.
    found = runs_under(root, nested=True, scripted=None)
    selected = narrowed(
        found,
        role=role,
        live=live,
        pipeline=pipeline,
        trigger=trigger,
        scripted=scripted,
        since=since,
        last=last,
    )
    # Every figure below is over the runs this could read, so a run whose trajectory is
    # unreadable is in none of them rather than in some, and the basis is the one those runs
    # were priced against rather than one a run contributing no figure declared.
    paired, unread = _readable(selected)
    readable = [handle for handle, _ in paired]
    records = [run for _, run in paired]
    basis, reason = _shared_basis(readable)
    nodes = per_node(records, cost_basis=basis)
    started = sorted(
        stamp for handle in readable if (stamp := str(handle.manifest.get("started_at") or ""))
    )
    return RunsReport(
        root=str(root),
        read=len(readable),
        found=len(found),
        narrowed_by=_what_narrowed_it(role, live, pipeline, trigger, scripted, since, last),
        started=(started[0], started[-1]) if started else None,
        outcomes=_counted(_ended(handle) for handle in readable),
        roles=_counted(handle.role for handle in readable),
        sliced=sum(1 for handle in readable if handle.manifest.get("slice")),
        live=sum(1 for handle in readable if handle.live),
        scripted_left_out=(
            sum(1 for handle in found if handle.scripted) if scripted is False else 0
        ),
        nodes=nodes,
        spend=_spend(readable),
        spend_is_floor=_is_floor(readable),
        unpriced_runs=sum(1 for handle in readable if _cost_of(handle) is None),
        unpriced_calls=sum(_cost_record(handle).unpriced_calls for handle in readable),
        basis_reason=reason,
        unread=unread,
        tools=_tool_reach(paired),
    )


def _tool_reach(
    paired: list[tuple[RunHandle, list[Mapping[str, Any]]]],
) -> dict[str, tuple[int, int]]:
    """Per tool, the runs that registered it and the runs that called it at least once.

    Registration comes from the manifest and calls from the trajectory, so a tool a project
    built and then stopped reaching is a gap between two numbers rather than an absence.

    **A consultation tool writes no ``tool_call``.** It writes a ``consultation``, which carries
    no tool name, so its reach is joined on ``reaches`` instead: the manifest says which tools
    ask a person and which answerer each asks, and the record says which answerer was asked. A
    question answered in a later process is two records and counts once, which is the record
    whose ``answers`` is ``null``.
    """
    registered: Counter[str] = Counter()
    called: Counter[str] = Counter()
    for handle, run in paired:
        declared = [
            tool
            for tool in (handle.manifest.get("tools") or [])
            if isinstance(tool, Mapping) and tool.get("name")
        ]
        registered.update(str(tool["name"]) for tool in declared)

        used = {
            str(record.get("tool_name"))
            for record in run
            if record.get("record_type") == "tool_call" and record.get("tool_name")
        }
        asked = {
            record.get("reaches")
            for record in run
            if record.get("record_type") == "consultation" and record.get("answers") is None
        }
        for tool in declared:
            name = str(tool["name"])
            if tool.get("answered_by") is not None and tool.get("reaches") in asked:
                called[name] += 1
            elif name in used:
                called[name] += 1
    return {name: (registered[name], called[name]) for name in sorted(registered)}


def _readable(
    selected: list[RunHandle],
) -> tuple[list[tuple[RunHandle, list[Mapping[str, Any]]]], tuple[str, ...]]:
    """Each run paired with its records, and the names of the runs that could not be read.

    A directory of runs accumulates a run that was interrupted mid-write, and one unreadable
    file is not a reason to report nothing about the other three thousand.

    The pairing is returned rather than two lists to be zipped, because a caller reading a
    manifest against its own trajectory cannot recover the correspondence from a run id: ids
    carry a timestamp to the second and a random suffix, and nothing refuses a repeat.
    """
    read: list[tuple[RunHandle, list[Mapping[str, Any]]]] = []
    unread: list[str] = []
    for handle in selected:
        try:
            read.append((handle, list(read_trajectory(handle.trajectory_path))))
        except (OSError, json.JSONDecodeError):
            unread.append(handle.run_id)
    return read, tuple(unread)


def _shared_basis(selected: Iterable[RunHandle]) -> tuple[CostBases | None, str | None]:
    """The cost basis every run read was written with, and a reason where there is not one.

    Cost is derived from the token counts against a basis, and the runs carry the basis their
    envelope declared. One basis over all of them prices every call the way the run itself
    priced it. Two different ones cannot be reduced to a figure per node, so each node's cost
    reports unknown and the reason says so rather than a number being derived against whichever
    basis was read last.
    """
    blocks = {
        json.dumps(handle.manifest.get("cost_basis"), sort_keys=True, default=str)
        for handle in selected
    }
    if not blocks:
        return None, None
    if len(blocks) > 1:
        return None, (
            f"The runs read were written against {len(blocks)} different cost bases, so no "
            f"figure per node is derived from them. The spend above is what each run recorded "
            f"for itself. Narrow with --since or --last to a period with one basis."
        )
    declared = json.loads(blocks.pop())
    basis = basis_from_manifest(declared)
    if basis is None and not declared:
        return None, (
            "These runs recorded no cost basis, so each node's cost is unknown. "
            "RunEnvelope(cost_basis=...) is what a run is priced against (FT-27)."
        )
    if basis is None:
        # A basis of a kind this version does not write, or one missing a rate it needs. Saying
        # they recorded none would send a reader to declare what they already declared.
        return None, (
            f"These runs recorded a cost basis this library cannot price against, of kind "
            f"{str(declared.get('kind'))!r}, so each node's cost is unknown. The run's own "
            f"total, printed above, is what it computed when it ran."
        )
    return basis, None


def _narrowed_by(**filters: Any) -> dict[str, Any]:
    """The filters that were applied, named for the report, with the ones left off dropped."""
    return {name: value for name, value in filters.items() if value is not None}


def _what_narrowed_it(
    role: str | None,
    live: bool | None,
    pipeline: str | None,
    trigger: str | None,
    scripted: bool | None,
    since: str | None,
    last: int | None,
) -> dict[str, Any]:
    """The filters the report names, which is every one the caller set.

    Leaving scripted runs out is the default and the header says how many those were on its
    own line, so naming it here too would put `scripted False` on every report that narrowed
    nothing.
    """
    return _narrowed_by(
        role=role,
        live=live,
        pipeline=pipeline,
        trigger=trigger,
        scripted=scripted if scripted is not False else None,
        since=since,
        last=last,
    )


def _ended(handle: RunHandle) -> str:
    """How one run ended, as the outcome line counts it.

    A run whose manifest could not be parsed records no outcome and is not a run still
    executing, which is what an unread `outcome` would otherwise read as. A run that recorded
    no outcome is counted by what its liveness says: a process that was killed leaves the
    manifest it wrote at the start, and reading that as `still running` a week later says
    something that will never become true.
    """
    if handle.unreadable is not None:
        return "unreadable manifest"
    if handle.outcome is not None:
        return handle.outcome
    return {ABANDONED: "abandoned", RUNNING: "still running"}.get(
        handle.liveness or "", "outcome not recorded"
    )


def _counted(values: Iterable[str]) -> dict[str, int]:
    counted: dict[str, int] = {}
    for value in values:
        counted[value] = counted.get(value, 0) + 1
    return counted


def _spend(selected: Iterable[RunHandle]) -> dict[str, float]:
    """What the runs cost, summed per currency out of what each recorded for itself.

    A run whose total could not be derived contributes the floor it did measure, so an
    evaluation that met a rate limit part way through is in this figure rather than absent
    from it. `_is_floor` says whether any run contributed one, which is what makes the printed
    figure read `at least`. Device-seconds are their own unit and are summed apart from money.
    """
    totals: dict[str, float] = {}
    for handle in selected:
        cost = _cost_record(handle)
        value = cost.value if cost.value is not None else cost.measured
        if value is None:
            continue
        unit = _unit_of(handle, cost)
        totals[unit] = totals.get(unit, 0.0) + value
    return totals


def _unit_of(handle: RunHandle, cost: Cost) -> str:
    """What one run's figure is denominated in.

    A `DeviceBasis` carries no currency, because device time is not money, so its unit is the
    device the basis named. Without this a run priced in device-seconds is summed under an
    empty unit and prints as a bare number.
    """
    basis = handle.manifest.get("cost_basis") or {}
    if basis.get("kind") == "device":
        return str(basis.get("device") or DEVICE_SECONDS)
    return str(cost.currency or "")


def _cost_record(handle: RunHandle) -> Cost:
    """One run's recorded cost figure, read back off its manifest."""
    return Cost.from_record((handle.manifest.get("totals") or {}).get("cost"))


def _is_floor(selected: Iterable[RunHandle]) -> bool:
    """Whether any run contributed a floor rather than a total, so the sum is a floor too."""
    return any(
        cost.value is None and cost.measured is not None
        for cost in (_cost_record(handle) for handle in selected)
    )


def _cost_of(handle: RunHandle) -> float | None:
    """What one run recorded that it cost, or ``None`` where nothing could be measured."""
    value = _cost_record(handle).value
    return float(value) if isinstance(value, (int, float)) else None
