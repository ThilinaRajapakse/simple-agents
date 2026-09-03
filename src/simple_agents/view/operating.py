"""What a shipped project is doing right now, and what it has done since.

Six records a live project leaves behind, all on disk and none of them read by the page until
this: the suspensions a run stopped at, the questions a background run shelved, whether a run
with no outcome is still going, the conversations runs are turns of, what each day's runs cost,
and the tool calls that ended throttled.

::

    held = read_operating(".")
    held["now"]["waiting"]            # runs stopped waiting on a person
    [s["waiting_for"] for s in held["stuck"]]

``None`` where the project has no live run, which is every project that has not shipped: the
figures here are what real traffic did, and a development run is not that.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["read_operating"]

# How many live runs' trajectories are opened to count throttles. A throttle that the library
# waited out and then succeeded leaves no record at all; what is counted is a tool call whose
# attempts were spent, which is recorded as an error naming the type.
MOST_TRAJECTORIES = 200


def _moment(value: Any) -> datetime | None:
    try:
        held = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return held if held.tzinfo else held.replace(tzinfo=timezone.utc)


def _day(value: Any) -> str:
    return str(value or "")[:10]


def _how_long(since: Any, now: datetime) -> str:
    """How long ago something was, in the words a person uses for it."""
    held = _moment(since)
    if held is None:
        return ""
    seconds = max(0.0, (now - held).total_seconds())
    if seconds < 90:
        return f"{round(seconds)} s"
    if seconds < 5400:
        return f"{round(seconds / 60)} min"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} h"
    return f"{round(seconds / 86400)} d"


def _throttled(path: Path) -> bool:
    """Whether one run's trajectory holds a call that ended throttled.

    Scanned as text rather than parsed: the question is whether the word is in the file, and a
    trajectory can be large. A throttle the library waited out and then succeeded is not in
    here, because nothing records it.
    """
    try:
        with path.open("r", encoding="utf-8") as held:
            return any('"Throttled"' in line for line in held)
    except OSError:
        return False


def _cost_of(manifest: dict[str, Any]) -> tuple[float, str | None]:
    held = (manifest.get("totals") or {}).get("cost") or {}
    value = held.get("value")
    return (float(value) if isinstance(value, (int, float)) else 0.0), held.get("currency")


def _ended(manifest: dict[str, Any]) -> str:
    """Which of the three a day's bar counts this run under."""
    outcome = str(manifest.get("outcome") or "")
    if outcome in ("completed", "complete", "finished"):
        return "finished"
    if outcome in ("error", "failed"):
        return "failed"
    return "stopped"


def _stuck(root: Path, now: datetime) -> list[dict[str, Any]]:
    """Every run that stopped and is waiting, with what it waits for and for how long."""
    from ..pipeline import Pipeline

    found = []
    for state in Pipeline.suspensions(root / "runs"):
        until = state.resume_not_before
        found.append(
            {
                "run": state.run_id,
                "node_id": state.node_id,
                "waiting_for": state.waiting_for,
                "options": state.options or [],
                "since": state.suspended_at,
                "waited": _how_long(state.suspended_at, now),
                "until": until,
                "on": "a clock" if until else "a person",
                "ready": bool(getattr(state, "ready", False)),
            }
        )
    return sorted(found, key=lambda one: str(one["since"]))


def _shelved(root: Path, now: datetime) -> list[dict[str, Any]]:
    """Every question a background run left outstanding."""
    from ..pipeline import Pipeline

    return [
        {
            "prompt": question.prompt,
            "about": question.about,
            "run": question.run_id,
            "node_id": question.node_id,
            "options": question.options or [],
            "reason": question.reason,
            "asked_at": question.asked_at,
            "waited": _how_long(question.asked_at, now),
        }
        for question in Pipeline.shelved(root / "runs")
    ]


def _conversations(handles: list[Any]) -> list[dict[str, Any]]:
    """The conversations these runs are turns of, newest last written first.

    Read from what each run recorded rather than from the store, so a conversation whose file
    has moved still lists. ``read`` is whether any run of it carried earlier messages into a
    node: a conversation nothing reads is one the pipeline is not taking part in.
    """
    held: dict[str, dict[str, Any]] = {}
    for handle in handles:
        record = handle.manifest.get("conversation") or {}
        name = record.get("id") or record.get("thread")
        if not name:
            continue
        one = held.setdefault(
            str(name),
            {
                "id": str(name),
                "runs": 0,
                "turns": 0,
                "carried": 0,
                "last": "",
                "run_ids": [],
            },
        )
        one["runs"] += 1
        one["turns"] = max(one["turns"], int(record.get("turn") or 0))
        one["carried"] += int(record.get("carried_in") or 0)
        one["run_ids"].append(handle.run_id)
        started = str(handle.manifest.get("started_at") or "")
        if started > one["last"]:
            one["last"] = started
    for one in held.values():
        one["read"] = one["carried"] > 0
    return sorted(held.values(), key=lambda one: one["last"], reverse=True)


def _history(handles: list[Any], root: Path) -> tuple[list[dict[str, Any]], str | None]:
    """One entry a day: how the day's runs ended, what they cost, and any throttle."""
    days: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"finished": 0, "failed": 0, "stopped": 0, "spend": 0.0, "throttled": 0, "runs": 0}
    )
    currency: str | None = None
    for index, handle in enumerate(handles):
        day = _day(handle.manifest.get("started_at"))
        if not day:
            continue
        held = days[day]
        held["runs"] += 1
        held[_ended(handle.manifest)] += 1
        value, unit = _cost_of(handle.manifest)
        held["spend"] += value
        currency = currency or unit
        if index < MOST_TRAJECTORIES and _throttled(handle.path / "trajectory.jsonl"):
            held["throttled"] += 1
    return (
        [{"day": day, **days[day]} for day in sorted(days)],
        currency,
    )


def _changes(handles: list[Any]) -> list[dict[str, Any]]:
    """Every day one pipeline's behaviour moved, oldest first.

    Kept within one graph, because two pipelines have two behaviours and reading a switch
    between them as a change would report one on every day a project runs both. The
    fingerprint covers the shape, the prompts, the sampling, the tools, the declared model and
    the budgets, so a day it moves within one graph is a day that agent started doing
    something else.

    A confirmation records the stage it was made at rather than a date, so nothing dates one
    and the marks here are behaviour alone.
    """
    by_graph: dict[str, list[Any]] = defaultdict(list)
    for handle in handles:
        by_graph[str(handle.manifest.get("graph_fingerprint") or "")].append(handle)
    found: list[dict[str, Any]] = []
    for graph, held in by_graph.items():
        last: str | None = None
        for handle in sorted(held, key=lambda one: str(one.manifest.get("started_at") or "")):
            stamp = str(handle.manifest.get("behaviour_fingerprint") or "")
            day = _day(handle.manifest.get("started_at"))
            if not stamp or not day:
                continue
            if last is not None and stamp != last:
                found.append(
                    {
                        "day": day,
                        "graph": graph,
                        "fingerprint": stamp,
                        "words": "The behaviour changed",
                    }
                )
            last = stamp
    return sorted(found, key=lambda one: one["day"])


def _by_role(directory: Path) -> list[dict[str, Any]]:
    """Every run under the project, counted by what it was for.

    A development run, a customer-facing one and an evaluation's rollout answer different
    questions, and one figure over all three describes none of them. `runs()` leaves rollouts
    out, so they are counted from the evaluation directories they are filed under.
    """
    from ..envelope import runs

    held: dict[str, dict[str, Any]] = {}

    def count(role: str, handles: list[Any]) -> None:
        if not handles:
            return
        one = held.setdefault(
            role, {"role": role, "runs": 0, "spend": 0.0, "currency": None, "last": ""}
        )
        for handle in handles:
            one["runs"] += 1
            value, unit = _cost_of(handle.manifest)
            one["spend"] += value
            one["currency"] = one["currency"] or unit
            started = str(handle.manifest.get("started_at") or "")
            if started > one["last"]:
                one["last"] = started

    # A census of what ran, so a run whose model answered from a script is one of them: the
    # page says what this project has done, rather than reporting a figure about the agent.
    every = runs(directory, nested=True, scripted=None)
    count("live", [one for one in every if one.manifest.get("live")])
    count("evaluation", [one for one in every if one.manifest.get("evaluation")])
    count(
        "development",
        [
            one
            for one in every
            if not one.manifest.get("live") and not one.manifest.get("evaluation")
        ],
    )
    return [held[role] for role in ("live", "development", "evaluation") if role in held]


def read_operating(root: str | Path) -> dict[str, Any] | None:
    """Everything the operate page draws, or ``None`` where nothing has run for real."""
    from ..envelope import runs

    root = Path(root).expanduser()
    directory = root / "runs"
    if not directory.is_dir():
        return None
    handles = runs(directory, live=True, scripted=None)
    if not handles:
        return None

    now = datetime.now(timezone.utc)
    stuck = _stuck(root, now)
    shelved = _shelved(root, now)
    history, currency = _history(handles, root)
    today = now.strftime("%Y-%m-%d")
    spent_today = next((day["spend"] for day in history if day["day"] == today), 0.0)
    unfinished = [one for one in handles if one.outcome is None]
    return {
        "now": {
            "running": sum(1 for one in unfinished if one.liveness == "running"),
            "abandoned": sum(1 for one in unfinished if one.liveness == "abandoned"),
            "unknown": sum(1 for one in unfinished if one.liveness == "unknown"),
            "waiting": len(stuck),
            "shelved": len(shelved),
            "spend": spent_today,
            "currency": currency,
            "day": today,
        },
        "runs": len(handles),
        "roles": _by_role(directory),
        "history": history,
        "changes": _changes(handles),
        "stuck": stuck
        + [
            {
                "run": one.run_id,
                "waiting_for": "",
                "since": one.manifest.get("started_at"),
                "waited": _how_long(one.manifest.get("started_at"), now),
                "on": "nothing",
                "abandoned": True,
                "node_id": "",
                "options": [],
                "until": None,
                "ready": False,
            }
            for one in unfinished
            if one.liveness == "abandoned"
        ],
        "shelf": shelved,
        "conversations": _conversations(handles),
    }
