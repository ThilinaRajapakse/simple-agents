"""What the runs a project has made spent and produced nothing with.

Every other check reads the newest run. This reads every run the pipeline as it now stands has
made, because one run does not show this: a project spending a quarter of its calls on
executions that produce nothing can have nine runs in ten come back clean.

The counts come from each run's ``manifest.json``, where the run wrote them when it ended, so
the cost of reading grows with the number of runs rather than with their size. FT-35 gates on
one figure here and the report's note prints the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..envelope import ABANDONED, RunHandle, narrowed, runs
from ..records.manifest import DEFAULT_ROLE

__all__ = ["Scope", "UnfinishedAcross", "unfinished_across"]

# The manifest format that first carried all five figures of `unfinished`. A run written
# before it recorded the same executions and no count of them, or counted them without what
# they spent, so it is named as unread rather than counted as clean.
COUNTS_FROM = (0, 31)

_FIGURES = (
    "executions",
    "items",
    "without_tool_calls",
    "model_calls",
    "model_calls_without_tool_calls",
)


@dataclass(frozen=True, slots=True)
class Scope:
    """Which of a project's runs a check reads, as the command line narrows it.

    ``role`` and ``live`` filter the way :func:`~simple_agents.runs` does, ``since`` takes runs
    that started at or after an ISO timestamp, and ``last`` keeps the newest that many::

        Scope(since="2026-08-14", last=500)

    Everything left unset reads every run of the project's agent.
    """

    role: str | None = None
    live: bool | None = None
    since: str | None = None
    last: int | None = None

    def narrowed_by(self) -> dict[str, Any]:
        """What was passed, for the report to name. Empty where nothing narrowed it."""
        declared = {
            "role": self.role,
            "live": self.live,
            "since": self.since,
            "last": self.last,
        }
        return {name: value for name, value in declared.items() if value is not None}


# Evaluated once: `Scope` is frozen, so one default instance is safe to share.
_EVERY_RUN = Scope()


@dataclass(frozen=True, slots=True)
class UnfinishedAcross:
    """The units of work that produced nothing, over the runs one pipeline made.

    ``read`` is how many runs the counts are over and ``found`` how many are under the
    directory, and the counts between them say where the rest went: ``other_role`` declare a
    role other than ``role``, ``unreadable`` carry a manifest nothing could parse,
    ``still_running`` have not written what they produced yet, ``abandoned`` never will because
    their process ended first, ``other_pipeline`` were made by
    a pipeline that has since changed, and ``without_counts`` are older than the counts.
    ``scoped`` is what the filters left, so a scope of its own accounts for ``found - scoped``.

    ``nodes`` holds the five figures per node, summed over the runs read. ``waived`` names the
    nodes declaring ``allow_unfinished=True``, which is what turns FT-35 off for one node.
    """

    where: str
    role: str = DEFAULT_ROLE
    found: int = 0
    scoped: int = 0
    read: int = 0
    other_role: int = 0
    unreadable: int = 0
    still_running: int = 0
    abandoned: int = 0
    other_pipeline: int = 0
    without_counts: int = 0
    fingerprint: str | None = None
    nodes: dict[str, dict[str, int]] = field(default_factory=dict)
    waived: frozenset[str] = frozenset()
    narrowed_by: dict[str, Any] = field(default_factory=dict)

    def covered(self) -> str:
        """One sentence naming what these figures are over, for a message that carries them.

        A figure over a scoped set of runs reads as a figure over the project unless it says
        otherwise, so every message carrying one carries this.
        """
        of = f" of the {self.found:,}" if self.found != self.read else ""
        narrowed = ", ".join(f"{name} {value}" for name, value in self.narrowed_by.items())
        parts = [f"{self.read:,}{of} run(s) under {self.where}/"]
        # Noun phrases, so a count of one reads the same as a count of many.
        if self.other_role:
            parts.append(f"{self.other_role:,} under another role")
        if self.unreadable:
            parts.append(f"{self.unreadable:,} whose manifest nothing could read (FT-13)")
        if self.still_running:
            parts.append(
                f"{self.still_running:,} that had not finished, so nothing says yet what they "
                f"produced"
            )
        if self.abandoned:
            parts.append(
                f"{self.abandoned:,} whose process ended before writing an outcome, so "
                f"nothing will ever say what they produced"
            )
        if self.other_pipeline:
            parts.append(f"{self.other_pipeline:,} made by a pipeline this one has changed since")
        if self.without_counts:
            parts.append(
                f"{self.without_counts:,} written before the manifest carried these counts, "
                f"unread rather than clean"
            )
        if narrowed:
            parts.append(f"narrowed by {narrowed}")
        return ", ".join(parts)

    def spinning(self) -> dict[str, dict[str, int]]:
        """The nodes that spent a whole allowance without acting, and are not waived."""
        return {
            node_id: counts
            for node_id, counts in self.nodes.items()
            if counts["without_tool_calls"] and node_id not in self.waived
        }

    def produced_nothing(self) -> dict[str, dict[str, int]]:
        """The nodes with a unit of work that ended without an output, waived or not.

        Wider than :meth:`spinning`: a cap that binds after real work is the cap doing its job,
        which is why this reports and that gates.
        """
        return {
            node_id: counts
            for node_id, counts in self.nodes.items()
            if counts["executions"] or counts["items"]
        }


def _nothing_finished(
    *,
    where: str,
    role: str,
    every: list[Any],
    selected: list[Any],
    parsed: list[Any],
    other_role: int,
    scope: Any,
) -> UnfinishedAcross:
    """The report for a scope where no run recorded an outcome.

    A run with no outcome is one of two things and they are not the same statement, so the two
    are counted apart: one may still produce something and the other never will.
    """
    gone = [handle for handle in parsed if handle.liveness == ABANDONED]
    return UnfinishedAcross(
        where=where,
        role=role,
        found=len(every),
        scoped=len(selected),
        other_role=other_role,
        unreadable=len(selected) - len(parsed),
        still_running=len(parsed) - len(gone),
        abandoned=len(gone),
        narrowed_by=scope.narrowed_by(),
    )


def unfinished_across(run_dir: str | Path, scope: Scope = _EVERY_RUN) -> UnfinishedAcross:
    """Read the counts every run of one pipeline recorded, and sum them per node.

    ::

        found = unfinished_across("runs/", Scope(since="2026-08-14"))
        found.spinning()      # {'look_closer': {'without_tool_calls': 188, ...}}
        print(found.covered())

    **Which pipeline is the newest finished run's**, by the ``behaviour_fingerprint`` each run
    records: a prompt, a tool or a budget that changed moves it, so a project that has fixed
    the node is measured on the runs made since the fix rather than on the ones that prompted
    it.

    Opens no trajectory. A run this cannot read the counts of is counted under the reason it
    could not: ``unreadable``, ``still_running``, ``other_pipeline`` or ``without_counts``.
    """
    root = Path(run_dir)
    where = root.name or str(root)
    role = scope.role or DEFAULT_ROLE
    # Read once and narrow, rather than reading every manifest twice: a project can hold
    # thousands, and both figures below are over the same directory.
    every = runs(root, nested=True)
    selected = narrowed(every, role=role, live=scope.live, since=scope.since, last=scope.last)
    other_role = sum(1 for handle in every if handle.role != role)
    if not selected:
        return UnfinishedAcross(
            where=where,
            role=role,
            found=len(every),
            other_role=other_role,
            narrowed_by=scope.narrowed_by(),
        )

    # A manifest nothing could parse says nothing about which pipeline made the run or what it
    # produced, so it names no pipeline here and is counted on its own.
    parsed = [handle for handle in selected if handle.unreadable is None]
    # A run writes what it produced when it ends, whatever it ends on, so one still executing
    # carries an empty block rather than a clean one. It is counted in none of the figures.
    # `_latest_run` prefers a finished run for the same reason.
    finished = [handle for handle in parsed if handle.outcome is not None]
    if not finished:
        return _nothing_finished(
            where=where,
            role=role,
            every=every,
            selected=selected,
            parsed=parsed,
            other_role=other_role,
            scope=scope,
        )

    fingerprint = finished[0].manifest.get("behaviour_fingerprint")
    pool = [
        handle for handle in finished if handle.manifest.get("behaviour_fingerprint") == fingerprint
    ]
    readable = [handle for handle in pool if _carries_counts(handle)]
    # A run with no outcome is one of two things and they are not the same statement, so the
    # two are counted apart here as they are where nothing finished: one may still produce
    # something and the other never will.
    gone = [handle for handle in parsed if handle.liveness == ABANDONED]

    nodes: dict[str, dict[str, int]] = {}
    for handle in readable:
        for node_id, counts in (handle.manifest.get("unfinished") or {}).items():
            if not isinstance(counts, dict):
                continue
            running = nodes.setdefault(str(node_id), dict.fromkeys(_FIGURES, 0))
            for name in _FIGURES:
                value = counts.get(name)
                running[name] += int(value) if isinstance(value, int) else 0

    return UnfinishedAcross(
        where=where,
        role=role,
        found=len(every),
        scoped=len(selected),
        read=len(readable),
        other_role=other_role,
        unreadable=len(selected) - len(parsed),
        still_running=len(parsed) - len(finished) - len(gone),
        abandoned=len(gone),
        other_pipeline=len(finished) - len(pool),
        without_counts=len(pool) - len(readable),
        fingerprint=str(fingerprint) if isinstance(fingerprint, str) else None,
        nodes=dict(sorted(nodes.items())),
        # Read off the newest run in the pool. Every run in it recorded the same
        # `behaviour_fingerprint`, and a node's waiver is part of what that digest covers, so
        # all of them declare what this one declares.
        waived=_waived(pool[0]) if pool else frozenset(),
        narrowed_by=scope.narrowed_by(),
    )


def _carries_counts(handle: RunHandle) -> bool:
    """Whether this run's manifest is new enough to hold the counts.

    A run older than that recorded the executions and no count of them. Reading its absent
    block as an empty one would report a project that spun as one that did not.
    """
    parts = str(handle.manifest.get("format_version") or "").split(".")
    try:
        return (int(parts[0]), int(parts[1])) >= COUNTS_FROM
    except (IndexError, ValueError):
        return False


def _waived(handle: RunHandle) -> frozenset[str]:
    """The nodes this run declared ``allow_unfinished=True`` on."""
    return frozenset(
        str(entry.get("node_id"))
        for entry in handle.manifest.get("nodes") or []
        if isinstance(entry, dict) and entry.get("allow_unfinished")
    )
