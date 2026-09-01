"""How much of a run overlaps, and what happens to work in flight when something stops.

A run overlaps three kinds of work: the arms of a branch, the items of a fan-out, and the tool
calls inside one turn. All three go through :class:`WorkPool`, which holds the run's ceiling and
the drain rule, so there is one place where a stop means the same thing.

``Pipeline.run(concurrency=N)`` bounds calls in flight, not units of work. A unit that is waiting
for the units below it holds no slot, so a fan-out nested inside a branch arm cannot deadlock
against its own parent.

**Draining is what a stop does.** Work already running finishes, is recorded and is charged;
work not yet started does not start.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Sequence

__all__ = ["WorkPool", "UnitOutcome"]


class _Unstarted:
    """The value a unit returns when the pool had already stopped starting work."""


@dataclass(frozen=True, slots=True)
class UnitOutcome:
    """What became of one unit of work.

    ``started`` is ``False`` for a unit the pool never began, which is a unit to run later
    rather than one that failed::

        outcome.started and outcome.error is None    # it ran and produced `value`
        outcome.started and outcome.error is not None # it ran and raised
        not outcome.started                          # nothing happened, and nothing was charged
    """

    index: int
    started: bool
    value: Any = None
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.started and self.error is None


@dataclass
class WorkPool:
    """The run's ceiling on calls in flight, and the drain rule every unit stops under.

    Built by the run rather than by a caller. ``ceiling`` is what
    ``Pipeline.run(concurrency=...)`` was given, and 1 means nothing overlaps: units run in the
    calling thread, in order, exactly as they did before this existed.

    ``map`` runs units and returns one :class:`UnitOutcome` each, in the order they were given,
    whatever order they ran in::

        outcomes = pool.map([lambda: read(page) for page in pages], limit=8,
                            stops_on=lambda exc: isinstance(exc, Suspend))

    ``limit`` is what the node declared, and the effective width is the smaller of it and the
    ceiling. ``stops_on`` names the failures that stop the rest: when one is raised, units not
    yet started do not start, and units already running finish and are collected.
    """

    ceiling: int = 1
    _slots: threading.BoundedSemaphore = field(init=False, repr=False)
    _held: threading.local = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.ceiling = max(1, int(self.ceiling))
        self._slots = threading.BoundedSemaphore(self.ceiling)
        self._held = threading.local()

    @contextmanager
    def slot(self) -> Iterator[None]:
        """Hold one of the run's slots for the duration of a call to a backend.

        A thread that already holds one does not take a second, so a tool that calls a model
        through a handle does not wait for a slot its own caller is holding.
        """
        if self.ceiling == 1 or getattr(self._held, "holding", False):
            yield
            return
        self._slots.acquire()
        self._held.holding = True
        try:
            yield
        finally:
            self._held.holding = False
            self._slots.release()

    def map(
        self,
        units: Sequence[Callable[[], Any]],
        *,
        limit: int | None = None,
        stops_on: Callable[[BaseException], bool] | None = None,
    ) -> list[UnitOutcome]:
        """Run ``units`` and collect what became of each, in the order given."""
        width = 1 if limit is None else max(1, min(int(limit), self.ceiling))
        if width == 1 or len(units) <= 1:
            return self._in_order(units, stops_on)
        return self._overlapped(units, width, stops_on)

    def _in_order(
        self,
        units: Sequence[Callable[[], Any]],
        stops_on: Callable[[BaseException], bool] | None,
    ) -> list[UnitOutcome]:
        """Every unit in the calling thread, stopping where one says to."""
        outcomes: list[UnitOutcome] = []
        stopped = False
        for index, unit in enumerate(units):
            if stopped:
                outcomes.append(UnitOutcome(index=index, started=False))
                continue
            try:
                outcomes.append(UnitOutcome(index=index, started=True, value=unit()))
            except BaseException as exc:  # noqa: BLE001 - handed back to the caller
                outcomes.append(UnitOutcome(index=index, started=True, error=exc))
                if stops_on is not None and stops_on(exc):
                    stopped = True
        return outcomes

    def _overlapped(
        self,
        units: Sequence[Callable[[], Any]],
        width: int,
        stops_on: Callable[[BaseException], bool] | None,
    ) -> list[UnitOutcome]:
        """Up to ``width`` units at once, draining on the first failure that stops the rest.

        The unit that stopped and every unit already running are collected. A unit that had not
        begun returns without doing anything, so nothing it would have spent is spent.
        """
        stopping = threading.Event()

        def guarded(unit: Callable[[], Any]) -> Any:
            if stopping.is_set():
                return _Unstarted
            try:
                return unit()
            except BaseException as exc:  # noqa: BLE001 - re-raised through the future
                if stops_on is not None and stops_on(exc):
                    stopping.set()
                raise

        with ThreadPoolExecutor(max_workers=width) as pool:
            pending = [pool.submit(guarded, unit) for unit in units]
            outcomes: list[UnitOutcome] = []
            for index, future in enumerate(pending):
                try:
                    value = future.result()
                except BaseException as exc:  # noqa: BLE001 - handed back to the caller
                    outcomes.append(UnitOutcome(index=index, started=True, error=exc))
                    continue
                if value is _Unstarted:
                    outcomes.append(UnitOutcome(index=index, started=False))
                else:
                    outcomes.append(UnitOutcome(index=index, started=True, value=value))
        return outcomes
