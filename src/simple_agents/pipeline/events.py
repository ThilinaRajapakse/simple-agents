"""What a run hands back and reports while it moves: the result, and per-node events."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence
from ..envelope import RunPaths
from ..nodes import Node


@dataclass(slots=True)
class RunResult:
    """What one completed run produced, and where its artifacts were written.

    Only returned by a run that finished. A run stopped by the run budget raises
    :class:`BudgetExceeded`, which carries ``axis``, ``limit`` and ``spent``; the manifest of
    that run records ``outcome`` as ``stopped_early`` and names the axis::

        result.output           # what the last node returned
        result.cost             # {"value": ..., "currency": ..., "basis": ..., ...}
        result.tokens           # the four token classes, summed over the run
        result.manifest         # the whole manifest, already parsed
    """

    run_id: str
    output: Any
    paths: RunPaths
    seed: int
    manifest: dict[str, Any]

    @property
    def trajectory_path(self) -> Path:
        return self.paths.trajectory

    @property
    def manifest_path(self) -> Path:
        return self.paths.manifest

    @property
    def outcome(self) -> str:
        """``completed``. A run that did not finish raises instead of returning a result, and
        its manifest records ``error`` or ``stopped_early``."""
        return str(self.manifest["outcome"])

    @property
    def cost(self) -> dict[str, Any]:
        """Derived cost. ``value`` is ``None`` when the run declared no cost basis."""
        return dict(self.manifest["totals"]["cost"])

    @property
    def tokens(self) -> dict[str, Any]:
        """The four token classes, summed over the run. There is no total: a class the
        backend left unknown cannot be added, and summing the rest would report less than
        was spent."""
        return dict(self.manifest["totals"]["tokens"])


@dataclass(frozen=True, slots=True)
class NodeEvent:
    """One thing the executor did, for a caller watching a run in progress.

    ``phase`` is ``started``, ``completed``, ``skipped``, ``failed`` or ``item``. ``route`` is
    filled on ``completed`` and names where the output went, so a caller can follow the path::

        def show(event: NodeEvent) -> None:
            print(f"{event.phase:<9} {event.node_id}")

        pipeline.run(inputs, model=client, on_progress=show)

    An ``item`` event fires as each item of a fan-out finishes, carrying its ``item_index``,
    the ``item_total`` it is one of, and its ``error`` where it failed. A fan-out hands its
    whole result to the next node when the last item is done, so this is what a caller writes
    each item on rather than waiting::

        def store(event: NodeEvent) -> None:
            if event.phase == "item" and event.error is None:
                db.write(event.node_id, event.item_index)

    It is a phase of its own, so a caller counting ``completed`` events counts nodes.
    ``item_index`` is a position in the whole collection, so a resumed fan-out announces the
    items it still had to do and their indices are where they were. ``item_already_done`` is
    how many were finished before this pass began, so a display counting events reaches
    ``item_total`` on a resumed fan-out rather than ending short by that many. All three are
    ``None`` on every other phase.

    Raised nowhere and awaited by nothing: an exception from the callback ends the run like any
    other, so a progress display that fails does not pass silently.
    """

    phase: str
    node_id: str
    node_kind: str
    attempt: int = 1
    iteration: int | None = None
    route: tuple[str, ...] = ()
    error: dict[str, Any] | None = None
    item_index: int | None = None
    item_total: int | None = None
    item_already_done: int | None = None


def _announce(
    on_progress: Callable[[NodeEvent], None] | None,
    phase: str,
    node_id: str,
    node: Node,
    *,
    attempt: int = 1,
    iteration: int | None = None,
    route: Sequence[str] = (),
    error: dict[str, Any] | None = None,
) -> None:
    """Tell a watching caller what the executor just did. A container announces nothing."""
    from .core import Pipeline

    if on_progress is None or isinstance(node, Pipeline):
        return
    on_progress(
        NodeEvent(
            phase=phase,
            node_id=node_id,
            node_kind=node.node_kind,
            attempt=attempt,
            iteration=iteration,
            route=tuple(route),
            error=error,
        )
    )
