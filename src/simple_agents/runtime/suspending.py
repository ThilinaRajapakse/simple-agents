"""Capturing a run's state at the moment it suspends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
from ..context import FinishAttempt, ToolCallSummary
from ..errors import CallerFacingError, Suspend
from .calls import _is_plain


@dataclass(frozen=True, slots=True)
class _Stop:
    """One node that stopped, and what it is waiting for."""

    node_id: str
    suspend: Suspend


class _Suspending(Exception):
    """Carries a suspension up through the walk, collecting a frame at each level.

    A pipeline nested inside another catches this, adds its own frame in front, and re-raises,
    so the state reaching ``run`` holds the stack outermost first. Never seen by a caller:
    ``run`` turns it into :class:`RunSuspended`.

    ``stops`` holds every node that stopped at the level being left, which is more than one
    where arms that were overlapping stopped together. ``node_state`` is what the node that
    stopped was holding. It is taken by the first frame to collect it and is then set again by
    any agent node further up that was mid-execution, so each level's state lands on that
    level's frame.
    """

    def __init__(self, suspend: Suspend, node_id: str) -> None:
        self.suspend = suspend
        self.node_id = node_id
        self.node_state = suspend.node_state
        self.stops: list[_Stop] = [_Stop(node_id=node_id, suspend=suspend)]
        self.frames: list[dict[str, Any]] = []
        # The `delegation` record for a subtask the run stopped inside, which the resumed
        # subtask's record names as the one it continues. `None` where no delegate was in
        # flight.
        self.delegation_record_id: str | None = None
        super().__init__(suspend.waiting_for)

    def take_node_state(self) -> dict[str, Any] | None:
        """The state waiting to be put on a frame, removed so no second frame claims it."""
        state, self.node_state = self.node_state, None
        return state


def _captured(
    *,
    messages: list[dict[str, Any]],
    made: list[ToolCallSummary],
    finish_attempts: list[FinishAttempt],
    calls: int,
    tokens: int,
    cost: float | None,
    step: int,
    elapsed_ms: int,
    pending: Any,
    remaining: Sequence[Any],
    asked_at: str,
    asked_record_id: str | None,
    occurrence: int | None,
    node_id: str,
    sent: dict[str, int] | None = None,
) -> dict[str, Any]:
    """What an ``AgentNode`` held when a run stopped inside it.

    ``elapsed_ms`` is what the node has spent working rather than a start time, so the clock
    restarts on resume and the wait is charged to nothing.

    A tool result has no declared schema, so it has to be plain data to survive the stop. The
    refusal names the tool rather than the node, because that is what has to change.
    """
    for summary in made:
        if not _is_plain(summary.result):
            raise CallerFacingError(
                f"Node {node_id!r} suspended, and tool {summary.name!r} had returned a "
                f"{type(summary.result).__name__}, which cannot cross a suspend point. A "
                f"finish check reads what each tool returned, so the value has to survive "
                f"the stop, and a tool declares no schema for the library to rebuild it "
                f"from.\n"
                f"Return plain data from {summary.name!r}: a string, a number, a boolean, or "
                f"a list or dict of those."
            )
    return {
        "messages": [dict(message) for message in messages],
        "made": [
            {"name": s.name, "arguments": s.arguments, "ok": s.ok, "result": s.result} for s in made
        ],
        "finish_attempts": [
            {"arguments": a.arguments, "rejection": a.rejection} for a in finish_attempts
        ],
        "calls": calls,
        "tokens": tokens,
        "cost": cost,
        "step": step,
        "elapsed_ms": elapsed_ms,
        "asked_at": asked_at,
        "asked_record_id": asked_record_id,
        "occurrence": occurrence,
        # How many subtasks each delegation had been sent, so `max_calls` bounds one execution
        # rather than each half of one that stopped and continued.
        "sent": dict(sent or {}),
        "pending": pending.to_record(),
        "remaining": [c.to_record() for c in remaining],
    }
