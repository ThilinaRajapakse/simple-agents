"""A progress display for a run or an evaluation.

A run and an evaluation both report what they are doing through a callback, and until now
each project wrote its own display over it. This is that display, so a builder watching a
long run passes one object rather than writing one.
"""

from __future__ import annotations

import threading
from typing import Any

from tqdm.auto import tqdm

__all__ = ["ProgressBar"]


class ProgressBar:
    """A terminal progress display, for either callback that reports what is running.

    Pass it wherever a run or an evaluation takes a reporter::

        pipeline.run(inputs, model=client, on_progress=ProgressBar())
        suite.run(envelope=env, model=client, split="held_out", k=3, on_rollout=ProgressBar())

    **An evaluation gets a bar**, because the number of rollouts is known before the first one
    starts, so it carries a proportion and a time remaining. **A run gets a counter**, because
    loops and routes decide how many nodes run while it is running and there is no total to
    count against. **A fan-out inside a run gets its own bar** as soon as its first item lands,
    since the node announces how many items it has.

    ``desc`` labels the display where several run at once. ``leave`` decides whether a finished
    display stays on screen. ``file`` is where it is written, and defaults to standard error.

    Nothing is written where that stream is not a terminal, so a run under CI or piped to a
    file is unchanged. Call :meth:`close` when the display is finished with, or use it as a context
    manager, which closes it however the block ends::

        with ProgressBar() as bar:
            pipeline.run(inputs, model=client, on_progress=bar)

    An exception raised in here ends the run, the way any callback's does, so it does as little
    as possible.
    """

    def __init__(self, *, desc: str | None = None, leave: bool = True, file: Any = None) -> None:
        self._desc = desc
        self._leave = leave
        self._file = file
        self._lock = threading.Lock()
        self._nodes: Any = None
        self._rollouts: Any = None
        self._items: dict[str, Any] = {}
        self._failed: dict[str, int] = {}

    def __call__(self, event: Any) -> None:
        """Take one report. The two kinds are told apart by what they carry."""
        if getattr(event, "phase", None) is not None:
            self._node_event(event)
        else:
            self._rollout(event)

    def __enter__(self) -> ProgressBar:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close every display this opened. Safe to call more than once."""
        with self._lock:
            bars = [self._nodes, self._rollouts, *self._items.values()]
            self._nodes = self._rollouts = None
            self._items = {}
            self._failed = {}
        for bar in bars:
            if bar is not None:
                bar.close()

    def _open(self, **kwargs: Any) -> Any:
        """One display, disabled where the stream it would write to is not a terminal."""
        return tqdm(disable=None, leave=self._leave, file=self._file, **kwargs)

    # -- a run ---------------------------------------------------------------------------

    def _node_event(self, event: Any) -> None:
        if event.phase == "item":
            self._item(event)
            return
        with self._lock:
            if self._nodes is None:
                self._nodes = self._open(total=None, unit=" nodes", desc=self._desc or "run")
            if event.phase == "started":
                self._nodes.set_postfix_str(event.node_id, refresh=False)
                return
            self._nodes.update(1)
            done = self._items.pop(event.node_id, None)
        if done is not None:
            done.close()

    def _item(self, event: Any) -> None:
        """One item of a fan-out, counted, and its failures said out loud.

        The bar is seeded with the items a resumed fan-out finished on an earlier pass, since
        those are announced by nothing and the bar would otherwise end short by that many.
        A failed item counts as done, because the work happened, and the running count of
        failures sits beside the bar: an item that failed is not an item that succeeded, and
        a bar that reaches its total over nothing but failures says the node worked.
        """
        with self._lock:
            bar = self._items.get(event.node_id)
            if bar is None:
                bar = self._items[event.node_id] = self._open(
                    total=event.item_total, unit=" items", desc=event.node_id
                )
                already = getattr(event, "item_already_done", None) or 0
                if already:
                    bar.update(already)
                self._failed[event.node_id] = 0
            if event.error is not None:
                self._failed[event.node_id] += 1
                bar.set_postfix_str(f"{self._failed[event.node_id]} failed", refresh=False)
            bar.update(1)

    # -- an evaluation -------------------------------------------------------------------

    def _rollout(self, progress: Any) -> None:
        with self._lock:
            if self._rollouts is None:
                self._rollouts = self._open(
                    total=progress.total,
                    unit=" rollouts",
                    desc=self._desc or progress.eval_id,
                )
            # Set rather than increment: `finished` counts what was resumed from disk as well,
            # so a resumed evaluation starts part-way rather than counting from zero.
            self._rollouts.n = progress.finished
            self._rollouts.set_postfix_str(_outcomes(progress), refresh=False)
            self._rollouts.refresh()


def _outcomes(progress: Any) -> str:
    """The counts and the spend, for the end of the line."""
    parts = [f"{count} {name}" for name, count in sorted(progress.outcomes.items())]
    if progress.cost is not None:
        spent = f"{progress.cost:.4g}"
        parts.append(f"{spent} {progress.currency}" if progress.currency else spent)
    return ", ".join(parts)
