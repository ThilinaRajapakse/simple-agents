"""What an evaluation reports about itself while it runs.

``RolloutProgress`` is the snapshot ``on_rollout=`` receives after every rollout, and the
runner keeps the same figures on disk as ``progress.json`` beside the rollouts, so a reader
elsewhere (``simple-agents view --serve``) follows the evaluation with the denominator the
runner declared and the outcomes it scored, and invents neither.
"""

from __future__ import annotations

import json
import os
import threading
import time
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from ..errors import SimpleAgentsWarning
from ..envelope import ABANDONED, MANIFEST_NAME, rollouts_under
from ..records.trajectory import utc_now
from .outcomes import RolloutOutcome

__all__ = ["PROGRESS_NAME", "RolloutProgress", "progress_of"]

PROGRESS_NAME = "progress.json"
"""The file an evaluation keeps current beside its rollouts while it runs."""


@dataclass(frozen=True, slots=True)
class RolloutProgress:
    """How far through an evaluation is, as one rollout finishes.

    An evaluation writes its results file at the end and nothing before it, so without this a
    run of any length reports nothing until it is over::

        suite.run(..., on_rollout=lambda p: print(p.describe()))
        # 12/33 rollouts, 4 correct, 1 failed, 0.0412 USD, ~18m left

    ``finished`` counts every rollout accounted for, including any resumed from disk, which
    ``resumed`` counts separately. ``elapsed_s`` and ``remaining_s`` are ``None`` on the first
    rollout, which has nothing to extrapolate from, and ``remaining_s`` extrapolates from the
    rate so far rather than promising anything.

    ``cost`` is what the rollouts so far were priced at, read off each one's manifest as it
    lands, and ``currency`` is the unit they were priced in. Both are ``None`` where no rollout
    could be priced, which is a run with no cost basis, and ``cost`` counts the rollouts that
    could be where only some were.
    """

    eval_id: str
    finished: int
    total: int
    resumed: int
    outcomes: Mapping[str, int]
    cost: float | None
    elapsed_s: float | None
    remaining_s: float | None
    latest: RolloutOutcome
    currency: str | None = None

    def describe(self) -> str:
        """One line, for printing while an evaluation runs."""
        parts = [f"{self.finished}/{self.total} rollouts"]
        parts += [f"{count} {name}" for name, count in sorted(self.outcomes.items())]
        if self.cost is not None:
            # `.4g` rather than a fixed four places: an evaluation of a few rollouts on a
            # cheap model costs less than 0.0001, and a figure that prints as 0.0000 reads
            # as free.
            spent = f"{self.cost:.4g}"
            parts.append(f"{spent} {self.currency}" if self.currency else spent)
        if self.remaining_s is not None:
            parts.append(f"~{round(self.remaining_s / 60)}m left")
        return ", ".join(parts)


def _priced_at(outcome: RolloutOutcome) -> tuple[float | None, str | None]:
    """What one rollout was priced at, off its own manifest, or ``(None, None)``.

    Read from disk rather than carried on the outcome: the price is derived from the whole
    run and the manifest is where the run records it. A rollout that ran under no cost basis,
    or one whose manifest cannot be read, is unpriced rather than zero.
    """
    if not outcome.trajectory:
        return None, None
    try:
        manifest = json.loads(
            (Path(outcome.trajectory).parent / MANIFEST_NAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None, None
    cost = ((manifest.get("totals") or {}).get("cost")) or {}
    value = cost.get("value")
    if not isinstance(value, (int, float)):
        return None, None
    return float(value), cost.get("currency")


class _Progress:
    """Accumulates what has finished, and calls the project's ``on_rollout`` with it.

    Rollouts finish on several threads, so the counter is guarded. A callback that raises
    would take down an evaluation that is otherwise fine, so it is reported as a warning and
    the evaluation carries on.
    """

    def __init__(
        self,
        *,
        total: int,
        resumed: int,
        report: Callable[[RolloutProgress], None] | None,
        eval_id: str,
        write_to: Path | None = None,
    ) -> None:
        self.total = total
        self.resumed = resumed
        self.report = report
        self.eval_id = eval_id
        self.write_to = write_to
        self.finished = 0
        self.outcomes: dict[str, int] = {}
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.cost = 0.0
        self.priced = 0
        self.currency: str | None = None
        self._write(None)

    def _write(self, snapshot: RolloutProgress | None) -> None:
        """The evaluation's progress, on disk beside its rollouts, for a reader elsewhere.

        Written at the start with the declared total and after every rollout lands, so a
        page following the evaluation reads a denominator the runner declared and the
        outcomes scored so far, and invents neither. Replaced whole each time, so a reader
        never meets a half-written file.
        """
        if self.write_to is None:
            return
        held = {
            "eval_id": self.eval_id,
            "finished": snapshot.finished if snapshot else self.finished,
            "total": self.total,
            "resumed": self.resumed,
            "outcomes": dict(snapshot.outcomes) if snapshot else dict(self.outcomes),
            "cost": snapshot.cost if snapshot else None,
            "currency": snapshot.currency if snapshot else None,
            "elapsed_s": snapshot.elapsed_s if snapshot else 0.0,
            "remaining_s": snapshot.remaining_s if snapshot else None,
            "updated_at": utc_now(),
        }
        try:
            self.write_to.mkdir(parents=True, exist_ok=True)
            target = self.write_to / PROGRESS_NAME
            staged = target.with_suffix(".json.tmp")
            staged.write_text(json.dumps(held, ensure_ascii=False), encoding="utf-8")
            os.replace(staged, target)
        except OSError:
            return

    def saw(self, outcome: RolloutOutcome, *, replayed: bool = False) -> RolloutOutcome:
        if self.report is None and self.write_to is None:
            return outcome
        spent, currency = _priced_at(outcome)
        with self.lock:
            self.finished += 1
            self.outcomes[outcome.outcome.value] = self.outcomes.get(outcome.outcome.value, 0) + 1
            if spent is not None:
                self.cost += spent
                self.priced += 1
                self.currency = self.currency or currency
            ran = self.finished - self.resumed
            elapsed = time.monotonic() - self.started
            left = self.total - self.finished
            snapshot = RolloutProgress(
                eval_id=self.eval_id,
                finished=self.finished,
                total=self.total,
                resumed=self.resumed,
                outcomes=dict(self.outcomes),
                cost=self.cost if self.priced else None,
                currency=self.currency,
                elapsed_s=None if replayed else elapsed,
                remaining_s=(None if replayed or ran < 1 or not left else elapsed / ran * left),
                latest=outcome,
            )
            self._write(snapshot)
        if self.report is None:
            return outcome
        try:
            self.report(snapshot)
        except Exception as exc:  # a project's callback, and not worth losing an evaluation to
            warnings.warn(
                f"on_rollout raised {type(exc).__name__}: {exc}. The evaluation continues, "
                f"and nothing about the rollouts changes. Catch what the callback can raise.",
                SimpleAgentsWarning,
                stacklevel=2,
            )
        return outcome


def progress_of(run_dir: str | os.PathLike[str], *, expected: int | None = None) -> dict[str, Any]:
    """How far an evaluation has got, read from its directory while it is still running.

    Nothing here imports the project's pipeline or example set, so this reads an evaluation
    from another process or another terminal::

        progress_of("runs/eval/eval_a1226bc495df", expected=33)
        # {'run_dir': 'runs/eval/eval_a1226bc495df', 'finished': 12, 'running': 2,
        #  'abandoned': 0, 'expected': 33, 'done': False,
        #  'outcomes': {'correct': 8, 'wrong': 3, 'failed': 1},
        #  'cost': 0.0412, 'currency': 'USD', 'unpriced': 0,
        #  'started_at': '...', 'elapsed_s': 1840.2, 'remaining_s': 3220.4}

    Every outcome that finished is counted under ``outcomes``, keyed by the value of
    :class:`~simple_agents.evaluation.Outcome`. There is no top-level key per outcome.

    ``expected`` is examples times k, which the caller knows and the directory does not.
    Without it ``expected``, ``remaining_s`` and ``done`` are ``None``: a directory holding 12
    rollouts cannot say whether that is all of them.

    ``running`` counts rollouts still in flight and ``abandoned`` counts the ones whose process
    ended before they wrote an outcome, which is `RunHandle.liveness`'s reading
    (``docs/run-envelope.md`` §8.3). Both have no ``ended_at``, and only one of them will ever
    get one. ``cost`` sums what the finished rollouts priced and ``unpriced`` counts the ones
    that could not be, the same split :func:`~simple_agents.evaluation.results.totals_of` reports.
    """
    handles = rollouts_under(run_dir)
    finished = [h for h in handles if h.manifest.get("ended_at") is not None]
    gone = [h for h in handles if h.liveness == ABANDONED]
    started = sorted(str(h.manifest.get("started_at") or "") for h in handles)
    ended = sorted(str(h.manifest.get("ended_at") or "") for h in finished)
    outcomes, cost, unpriced, currency = _finished_totals(finished)
    elapsed = _seconds_between(started[0] if started else None, ended[-1] if ended else None)
    rate = elapsed / len(finished) if elapsed and finished else None
    left = None if expected is None else max(0, expected - len(finished))
    return {
        "run_dir": str(run_dir),
        "finished": len(finished),
        "running": len(handles) - len(finished) - len(gone),
        "abandoned": len(gone),
        "expected": expected,
        "done": None if expected is None else len(finished) >= expected,
        "outcomes": outcomes,
        "cost": cost if cost or not unpriced else None,
        "currency": currency,
        "unpriced": unpriced,
        "started_at": started[0] if started else None,
        "elapsed_s": elapsed,
        "remaining_s": None if rate is None or left is None else rate * left,
    }


def _finished_totals(finished: list[Any]) -> tuple[dict[str, int], float, int, str | None]:
    """The finished rollouts' outcome counts, summed cost, unpriced count and currency.

    A rollout whose manifest prices nothing counts in ``unpriced`` rather than as zero, and
    ``currency`` is the first one any manifest names.
    """
    cost, unpriced = 0.0, 0
    outcomes: dict[str, int] = {}
    currency: str | None = None
    for handle in finished:
        outcome = str(handle.manifest.get("outcome") or "unknown")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        held = (handle.manifest.get("totals") or {}).get("cost") or {}
        value = held.get("value")
        if isinstance(value, (int, float)):
            cost += float(value)
        else:
            unpriced += 1
        currency = currency or held.get("currency")
    return outcomes, cost, unpriced, currency


def _seconds_between(first: str | None, last: str | None) -> float | None:
    """Wall clock between two ISO timestamps, or ``None`` where either is missing."""
    if not first or not last:
        return None
    try:
        start = datetime.fromisoformat(first.replace("Z", "+00:00"))
        end = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (end - start).total_seconds())
