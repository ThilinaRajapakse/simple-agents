"""Budgets: four axes, always declared, `None` meaning unbounded.

A pipeline that can call a model must declare a budget. Any axis may be ``None``:
``Budget(max_steps=20, max_tokens=None, max_cost=None, max_wall_clock_ms=None)`` bounds steps
and leaves the other three open. Omitting the budget entirely is refused.

Records carry all four keys, so a reader can distinguish a run that stopped early from one
that was never constrained. ``docs/pipeline.md`` §5 covers the axes and what narrowing does.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .errors import CallerFacingError

__all__ = ["Budget", "BudgetExceeded", "NodeBudgetExceeded", "Spend", "AXIS_FIELDS"]

# Recorded axis name -> (Budget field, Spend field). Spelled out rather than derived from the
# name: the `max_wall_clock` axis is stored as `max_wall_clock_ms`.
AXIS_FIELDS: dict[str, tuple[str, str]] = {
    "max_steps": ("max_steps", "steps"),
    "max_tokens": ("max_tokens", "tokens"),
    "max_cost": ("max_cost", "cost"),
    "max_wall_clock": ("max_wall_clock_ms", "wall_clock_ms"),
}


class BudgetExceeded(CallerFacingError):
    """A budget axis was exhausted.

    For an ``AgentNode`` this is ordinary termination, caught by the loop and recorded in the
    ``termination`` field rather than propagated. It reaches the caller only when the
    run-level budget is exhausted, which leaves the remaining nodes unexecuted.
    """

    def __init__(self, axis: str, limit: float, spent: float) -> None:
        self.axis = axis
        self.limit = limit
        self.spent = spent
        super().__init__(
            f"Run budget exhausted on {axis}: limit {limit}, spent {spent}. "
            f"The run stopped early and its results are incomplete. Either raise {axis} on "
            f"the Pipeline budget, reduce the work the pipeline does, or set {axis}=None to "
            f"leave this axis unbounded."
        )


class NodeBudgetExceeded(BudgetExceeded):
    """A node's own budget was exhausted across the items of a fan-out.

    The run has budget left, so this stops the node rather than the run: the items already
    finished are kept, the ones that had not started do not run, and each of those is
    collected as a failed item saying so. Raised only where a fan-out node declared
    ``budget=``, which is the total across its items.
    """

    def __init__(self, axis: str, limit: float, spent: float) -> None:
        self.axis = axis
        self.limit = limit
        self.spent = spent
        CallerFacingError.__init__(
            self,
            f"Node budget exhausted on {axis}: limit {limit}, spent {spent}. The items of "
            f"this fan-out have spent the whole of what the node declared, so the ones left "
            f"did not run and are collected as failures.\n"
            f"Raise {axis} on the node's budget=, lower budget_per_item= so each item takes "
            f"less of it, or set {axis}=None on budget= to bound the node by the run alone.",
        )


@dataclass(frozen=True, slots=True)
class Spend:
    """What has been consumed so far. Mirrors the budget axes."""

    steps: int = 0
    tokens: int = 0
    cost: float | None = None
    wall_clock_ms: int = 0

    def plus(
        self,
        *,
        steps: int = 0,
        tokens: int = 0,
        cost: float | None = None,
        wall_clock_ms: int = 0,
    ) -> Spend:
        # `cost` stays None until a costed call is made. None means "not measured", which
        # is not the same as zero.
        if cost is None:
            new_cost = self.cost
        else:
            new_cost = cost if self.cost is None else self.cost + cost
        return Spend(
            steps=self.steps + steps,
            tokens=self.tokens + tokens,
            cost=new_cost,
            wall_clock_ms=self.wall_clock_ms + wall_clock_ms,
        )

    def to_record(self) -> dict[str, int | float | None]:
        """The four axes as plain data. ``cost`` is ``null`` where nothing costed has run,
        which is not the same as zero."""
        return {
            "steps": self.steps,
            "tokens": self.tokens,
            "cost": self.cost,
            "wall_clock_ms": self.wall_clock_ms,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Spend:
        """A spend rebuilt from :meth:`to_record`::

        Spend.from_record({"steps": 3, "tokens": 900, "cost": None,
                           "wall_clock_ms": 1200})
        """
        return cls(
            steps=int(record["steps"]),
            tokens=int(record["tokens"]),
            cost=record["cost"],
            wall_clock_ms=int(record["wall_clock_ms"]),
        )


@dataclass(frozen=True, slots=True)
class Budget:
    """A limit on each of four axes. ``None`` on an axis means unbounded.

    All four arguments are required. There is no default, so an axis cannot be set by
    omission::

        Budget(max_steps=8, max_tokens=50_000, max_cost=None, max_wall_clock_ms=120_000)

    Passed to a ``Pipeline`` it bounds the whole run and depletes as nodes execute. Passed
    to an ``AgentNode`` it caps that node. A node is held to whichever is tighter.

    One step is one model call, whichever node kind makes it, and ``max_steps`` is exact: the
    step is taken before the call. ``max_tokens``, ``max_cost`` and ``max_wall_clock_ms`` are
    measured by what a call turns out to consume and are checked between nodes, so a run can
    pass them by what was already in flight; bound one call with ``max_output_tokens`` on the
    node. ``max_wall_clock_ms`` is elapsed time while the run is executing, so it counts waiting
    as well as working and counts nothing while a run is suspended.
    """

    max_steps: int | None
    max_tokens: int | None
    max_cost: float | None
    max_wall_clock_ms: int | None

    @classmethod
    def unbounded(cls) -> Budget:
        """Every axis unbounded.

        Correct for a pipeline of `Deterministic` nodes, which cannot call a model.
        """
        return cls(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None)

    @property
    def is_unbounded(self) -> bool:
        return all(
            axis is None
            for axis in (self.max_steps, self.max_tokens, self.max_cost, self.max_wall_clock_ms)
        )

    def remaining(self, spend: Spend) -> Budget:
        """What is left of this budget after ``spend``. Unbounded axes stay unbounded."""
        return Budget(
            max_steps=None if self.max_steps is None else max(0, self.max_steps - spend.steps),
            max_tokens=None if self.max_tokens is None else max(0, self.max_tokens - spend.tokens),
            max_cost=(
                None
                if self.max_cost is None
                else max(0.0, self.max_cost - (spend.cost if spend.cost is not None else 0.0))
            ),
            max_wall_clock_ms=(
                None
                if self.max_wall_clock_ms is None
                else max(0, self.max_wall_clock_ms - spend.wall_clock_ms)
            ),
        )

    def narrowed_by(self, other: Budget | None) -> Budget:
        """The per-axis minimum of this budget and ``other``.

        A node is bound by whichever is tighter, its own cap or what remains of the run. An
        unbounded axis on either side yields the other side's value, so a node can narrow what
        the run allows but not widen it. The result is recorded as the node's ``budget``.
        """
        if other is None:
            return self

        def tighter(a: float | int | None, b: float | int | None) -> float | int | None:
            if a is None:
                return b
            if b is None:
                return a
            return min(a, b)

        return Budget(
            max_steps=tighter(self.max_steps, other.max_steps),  # type: ignore[arg-type]
            max_tokens=tighter(self.max_tokens, other.max_tokens),  # type: ignore[arg-type]
            max_cost=tighter(self.max_cost, other.max_cost),  # type: ignore[arg-type]
            max_wall_clock_ms=tighter(  # type: ignore[arg-type]
                self.max_wall_clock_ms, other.max_wall_clock_ms
            ),
        )

    def exceeded_by(self, spend: Spend) -> str | None:
        """The name of the first axis ``spend`` exceeds, or ``None`` if within budget.

        Axis names match the ``termination`` values used in trajectory records, so a caller
        can record the answer directly.
        """
        if self.max_steps is not None and spend.steps >= self.max_steps:
            return "max_steps"
        if self.max_tokens is not None and spend.tokens >= self.max_tokens:
            return "max_tokens"
        if self.max_cost is not None and spend.cost is not None and spend.cost >= self.max_cost:
            return "max_cost"
        if self.max_wall_clock_ms is not None and spend.wall_clock_ms >= self.max_wall_clock_ms:
            return "max_wall_clock"
        return None

    def to_record(self) -> dict[str, int | float | None]:
        """The ``budget`` object as it appears on a trajectory record.

        All four keys always present; ``null`` means unbounded on that axis.
        """
        return {
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "max_cost": self.max_cost,
            "max_wall_clock_ms": self.max_wall_clock_ms,
        }

    def replace(self, **changes: int | float | None) -> Budget:
        return replace(self, **changes)  # type: ignore[arg-type]
