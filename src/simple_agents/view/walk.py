"""One run, step by step: what each step was handed, what it produced, and what it asked.

The page is about the system. This is the other question, and until now it had no surface at
all: `simple-agents report` gives a table over many runs and `simple-agents watch` follows one
in flight, and neither walks a run that has already finished.

**What travels with a static page is bounded**: the newest run of each shape, and the rollouts
whose examples came out wrong, which are the ones a builder opens. The served page reads any
run on demand, so the whole record is reachable without any of it being written into the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..envelope import manifest_paths
from .runs_overlay import (
    MAX_RECORD_CHARS,
    _clipped,
    _compact,
    _elapsed_ms,
    _rows,
    _volume,
)

__all__ = ["walk_run", "walkable_runs"]

MAX_STEPS = 200
"""Steps carried from one run. A run longer than this is reported by its length."""

MAX_CALLS_PER_STEP = 12
"""Model calls, tool calls and accesses listed under one step."""


def _tool_row(record: dict[str, Any]) -> dict[str, Any]:
    asked, _ = _compact(record.get("inputs"))
    got, full = _compact(record.get("outputs"))
    return {
        "kind": "tool",
        "name": record.get("tool_name"),
        "effect": record.get("side_effect_class"),
        "asked": asked,
        "got": got,
        "chars": full,
        "spent": (record.get("spent") or {}).get("amount"),
        "currency": (record.get("spent") or {}).get("currency"),
        "replayed": bool(record.get("replayed")),
        "failed": record.get("error") is not None,
    }


def _model_row(record: dict[str, Any]) -> dict[str, Any]:
    outputs = record.get("outputs") or {}
    said, full = _compact(outputs.get("content"))
    tools = [c.get("name") for c in (outputs.get("tool_calls") or [])]
    return {
        "kind": "model",
        "name": record.get("request_model"),
        "said": said,
        "chars": full,
        "asked_for": [t for t in tools if t],
        "finish_reason": record.get("finish_reason"),
        "tokens": record.get("tokens") or {},
        "replayed": bool(record.get("replayed")),
    }


def _access_row(record: dict[str, Any]) -> dict[str, Any]:
    asked, _ = _compact(record.get("inputs"))
    got, full = _compact(record.get("outputs"))
    return {
        "kind": "access",
        "name": record.get("resource"),
        "direction": record.get("direction"),
        "asked": asked,
        "got": got,
        "chars": full,
    }


def _consultation_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "asked",
        "name": record.get("about") or "a question",
        "prompt": _clipped(record.get("prompt")),
        "options": [str(o)[:60] for o in (record.get("options") or [])][:6],
        "answer": _clipped(record.get("response")),
        "chose": record.get("chose"),
        "resolution": record.get("resolution"),
        "answered_by": record.get("answered_by"),
    }


_ROWS = {
    "tool_call": _tool_row,
    "model_call": _model_row,
    "resource_access": _access_row,
    "consultation": _consultation_row,
}


def _step(record: dict[str, Any]) -> dict[str, Any]:
    """One node execution as a row of the walk."""
    return {
        "node_id": record.get("node_id", "?"),
        "kind": record.get("node_kind"),
        "sequence": record.get("sequence"),
        "record_id": record.get("record_id"),
        "started_at": record.get("started_at"),
        "ms": _elapsed_ms(record.get("started_at"), record.get("ended_at")),
        "took_in": _rows(record.get("inputs")),
        "handed_on": _rows(record.get("outputs")),
        "took_in_volume": _volume(record.get("inputs")),
        "handed_on_volume": _volume(record.get("outputs")),
        "termination": record.get("termination"),
        "route": list(record.get("route") or []),
        "loop": record.get("loop"),
        "error": (record.get("error") or {}).get("message") if record.get("error") else None,
        "item_index": record.get("item_index"),
        "did": [],
        "did_not_shown": 0,
    }


def walk_run(run_dir: str | Path) -> dict[str, Any] | None:
    """One run read whole, in the order it happened.

    ::

        walk = walk_run("runs/run_20260826T134059Z_f87d2f2d")
        walk["steps"][0]["node_id"]          # where it started
        walk["steps"][0]["did"]              # what that step called, in order
        walk["steps"][-1]["route"]           # where it went next, or nothing

    ``None`` where the directory holds no trajectory. A step that was skipped is in ``steps``
    carrying ``termination: "skipped"``, so the walk shows the branches the run did not take
    beside the ones it did.
    """
    directory = Path(run_dir).expanduser()
    trajectory = directory / "trajectory.jsonl"
    if not trajectory.exists():
        return None

    steps, order, children, parents, oversize = _read(trajectory)
    _hang_the_calls(children, steps, parents)
    order.sort(key=lambda held: held["sequence"] or 0)
    ran = [held for held in order if held["termination"] != "skipped"]
    manifest = _manifest(directory)
    return {
        "run": directory.name,
        "outcome": manifest.get("outcome"),
        "started_at": manifest.get("started_at"),
        "ended_at": manifest.get("ended_at"),
        "fingerprint": manifest.get("graph_fingerprint"),
        # A rollout is measurement, not the project running. The two are read on different
        # pages and one picker offering both mixes the questions.
        "rollout": bool(manifest.get("evaluation")),
        "cost": (manifest.get("totals") or {}).get("cost"),
        "steps": order[:MAX_STEPS],
        "left_out": max(0, len(order) - MAX_STEPS),
        "ran": len(ran),
        "skipped": len(order) - len(ran),
        "unreadable": oversize,
    }


def _manifest(directory: Path) -> dict[str, Any]:
    """One run's manifest, and an empty one where it cannot be read."""
    path = directory / "manifest.json"
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return held if isinstance(held, dict) else {}


def _read(
    trajectory: Path,
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, str],
    int,
]:
    """The steps, the calls under them, and how many records were too large to read."""
    steps: dict[str, dict[str, Any]] = {}
    order: list[dict[str, Any]] = []
    children: list[dict[str, Any]] = []
    parents: dict[str, str] = {}
    oversize = 0
    with trajectory.open(encoding="utf-8") as handle:
        for line in handle:
            if len(line) > MAX_RECORD_CHARS:
                oversize += 1
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            kind = record.get("record_type")
            if kind == "node_execution":
                held = _step(record)
                if record.get("record_id"):
                    steps[record["record_id"]] = held
                order.append(held)
            elif kind in _ROWS:
                children.append(record)
                if record.get("record_id") and record.get("parent_id"):
                    parents[record["record_id"]] = record["parent_id"]
    return steps, order, children, parents, oversize


def _hang_the_calls(
    children: list[dict[str, Any]], steps: dict[str, dict[str, Any]], parents: dict[str, str]
) -> None:
    """Put each call under the step it was made inside, walking up through any tool call."""
    for record in children:
        at = record.get("parent_id")
        for _up in range(6):
            if at is None or at in steps:
                break
            at = parents.get(at)
        if at not in steps:
            continue
        if len(steps[at]["did"]) >= MAX_CALLS_PER_STEP:
            # Counted rather than dropped: a step whose calls are cut off saying nothing
            # reads as a step that made twelve, which is the shape of a loop that ran away.
            steps[at]["did_not_shown"] += 1
            continue
        steps[at]["did"].append(
            {
                **_ROWS[str(record["record_type"])](record),
                "sequence": record.get("sequence"),
            }
        )


def walkable_runs(root: str | Path, wrong: list[str] | None = None) -> dict[str, Any]:
    """The runs a static page carries whole: the newest of each shape, and what came out wrong.

    ::

        walkable_runs(".", wrong=["runs/eval/eval_47/t-seat-count-0"])

    ``wrong`` names rollout directories relative to the project, which is what a results file
    records against each rollout that did not come out right. Every other run is reachable on
    the served page and named here only by id.
    """
    root = Path(root).expanduser()
    runs = root / "runs"
    if not runs.is_dir():
        return {"walks": {}, "others": []}

    wanted = _newest_of_each_shape(runs)
    for name in wrong or []:
        candidate = root / name
        if candidate.is_dir() and candidate not in wanted:
            wanted.append(candidate)

    walks = {}
    for directory in wanted:
        held = walk_run(directory)
        if held is not None:
            walks[directory.name] = held
    others = sorted(
        path.parent.name for path in manifest_paths(runs) if path.parent.name not in walks
    )
    return {"walks": walks, "others": others[:200], "more": max(0, len(others) - 200)}


def _newest_of_each_shape(runs: Path) -> list[Path]:
    """The most recently started run of each shape under a runs directory."""
    newest: dict[str, tuple[str, Path]] = {}
    for manifest_path in manifest_paths(runs):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        key = str(manifest.get("graph_fingerprint") or manifest_path.parent.name)
        started = str(manifest.get("started_at") or "")
        if key not in newest or started > newest[key][0]:
            newest[key] = (started, manifest_path.parent)
    return [directory for _started, directory in newest.values()]
