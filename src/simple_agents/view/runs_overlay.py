"""What the run record says about each pipeline, read from manifests without importing code.

Runs are grouped by the shape that made them: `graph_fingerprint` where the manifest carries
one, the node-id chain where it does not. A group whose fingerprint matches a declared
pipeline becomes that pipeline's history; one matching nothing declared is a shape the
project ran and no longer has, which the page shows rather than drops.

Trajectories are streamed and only the small records parsed: one payload record can be
megabytes, and there can be thousands of runs.

The same pass collects one real value per step, which is what the page shows beside a step's
declared schema. A record over ``MAX_RECORD_CHARS`` is left unparsed and reported by its size.

A step nothing reached emits a record too, carrying ``termination: "skipped"`` and no output.
Those are counted apart from executions, so a branch the run did not take is never reported as
a step that ran. It is the accounting an evaluation's per-node figures already use.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..envelope import manifest_paths
from .words import _clip

_NODE_EXECUTION_MARKS = ('"record_type": "node_execution"', '"record_type":"node_execution"')
_CONSULTATION_MARKS = ('"record_type": "consultation"', '"record_type":"consultation"')
_NODE_ID = re.compile(r'"node_id"\s*:\s*"([^"]*)"')

MAX_RECORD_CHARS = 40_000_000
"""The largest ``node_execution`` record this parses.

One payload can be megabytes and a trajectory can be tens of them, so the first prototype
read them line by line rather than as one object. Parsing the lines is what the ceiling is
about, and it is cheap: measured 2026-08-27 over an 11.3 MB trajectory whose largest record
is 2.7 MB, all eleven of its node executions parse in 0.06 seconds.
"""

MAX_VALUE_CHARS = 220
"""How much of one value the example rows carry. The whole length is reported beside it."""

MAX_KEYS = 8
"""Keys shown from a value that is a mapping."""

MAX_QUESTIONS = 6
"""Questions carried from one run, for the page to show what was actually asked."""

MAX_QUESTION_CHARS = 260
"""How much of one question and one answer the page carries."""

MAX_DEPTH = 3
"""How far into a value the shape goes before it stops describing."""


def _stream_node_executions(path: Path):
    """Every ``node_execution`` record small enough to parse, in file order."""
    for record, _oversize in _node_executions(path):
        if record is not None:
            yield record


def _node_executions(path: Path):
    """Every ``node_execution`` record, and for each one too large to parse, its size.

    Yields ``(record, None)`` or ``(None, {"node_id": ..., "chars": ...})``.
    """
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            head = line[:220]
            if not any(mark in head for mark in _NODE_EXECUTION_MARKS):
                continue
            if len(line) > MAX_RECORD_CHARS:
                found = _NODE_ID.search(line[:4000])
                yield None, {"node_id": found.group(1) if found else "?", "chars": len(line)}
                continue
            try:
                yield json.loads(line), None
            except Exception:  # noqa: BLE001 - a malformed line is skipped, never fatal
                continue


def _questions_in(path: Path, parents: dict[str, str]) -> list[dict[str, Any]]:
    """Every question this run put to a person, with what came back.

    ``parents`` maps a node execution's record id to its node, so a question is reported
    against the step that asked it. A consultation record is small: they are parsed whole.
    """
    if not path.exists():
        return []
    found = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not any(mark in line[:220] for mark in _CONSULTATION_MARKS):
                continue
            try:
                record = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            answer = record.get("response")
            found.append(
                {
                    "asked_by": parents.get(record.get("parent_id") or "", "?"),
                    "about": record.get("about"),
                    "prompt": _clipped(record.get("prompt")),
                    "options": [str(o)[:60] for o in (record.get("options") or [])][:6],
                    "answer": _clipped(answer) if answer is not None else None,
                    "resolution": record.get("resolution"),
                    "chose": record.get("chose"),
                    "declared_choice": record.get("declared_choice"),
                    "misread": bool(record.get("declared_choice"))
                    and record.get("chose") != record.get("declared_choice"),
                    "answered_by": record.get("answered_by"),
                    "reason": _clipped(record.get("reason")),
                    "blocking": bool(record.get("blocking")),
                    "asked": bool(record.get("asked", True)),
                }
            )
    return found[:MAX_QUESTIONS]


def _clipped(value: Any) -> str | None:
    if value is None:
        return None
    written = " ".join(str(value).split())
    return _clip(written, MAX_QUESTION_CHARS) or None


def _compact(value: Any) -> tuple[str, int]:
    """One value as a line of text, and the length it had before clipping."""
    if isinstance(value, str):
        written = value
    elif value is None or isinstance(value, (int, float, bool)):
        written = json.dumps(value)
    else:
        try:
            written = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            written = str(value)
    written = " ".join(written.split())
    return written[:MAX_VALUE_CHARS], len(written)


def _rows(value: Any) -> list[dict[str, Any]]:
    """One value as the rows a card shows: a row per key, or a single row."""
    if isinstance(value, dict):
        rows = []
        for key in list(value)[:MAX_KEYS]:
            shown, full = _compact(value[key])
            rows.append({"key": key, "value": shown, "chars": full})
        if len(value) > MAX_KEYS:
            rows.append(
                {"key": None, "value": f"and {len(value) - MAX_KEYS} more keys", "chars": 0}
            )
        return rows
    if isinstance(value, list):
        rows = [
            {
                "key": None,
                "value": f"{len(value):,} item" + ("" if len(value) == 1 else "s"),
                "chars": 0,
            }
        ]
        if value:
            shown, full = _compact(value[0])
            rows.append({"key": "first", "value": shown, "chars": full})
        return rows
    shown, full = _compact(value)
    return [{"key": None, "value": shown, "chars": full}]


def _rank(value: Any) -> tuple[int, int]:
    """How much a key is worth showing: a collection, then text, then a scalar."""
    if isinstance(value, (list, dict)):
        return (0, -len(value))
    if isinstance(value, str):
        return (1, -len(value))
    return (2, 0)


def _shape(value: Any, depth: int = MAX_DEPTH) -> dict[str, Any]:
    """What one value is, and how much of it there is.

    A list is its length and the shape of its first item; a mapping is its keys and each of
    their shapes; text is its length in characters. This is what a step moved, which a slice
    of the value written out is not: 40 candidates in and 8 recommendations out is a fact a
    builder reads at a glance, and the first 220 characters of the same record is not.
    """
    if isinstance(value, list):
        held = {"kind": "list", "count": len(value)}
        if value and depth > 0:
            held["of"] = _shape(value[0], depth - 1)
        return held
    if isinstance(value, dict):
        held = {"kind": "record", "count": len(value)}
        if depth > 0:
            # Keys holding a collection come first, then text, then scalars. A record of
            # nineteen fields where two of them are the 40 candidates and the 2,000 surveyed
            # is a record about those two, and truncating in declaration order hides them.
            keys = sorted(value, key=lambda k: _rank(value[k]))
            held["fields"] = {str(key): _shape(value[key], depth - 1) for key in keys[:MAX_KEYS]}
        return held
    if isinstance(value, str):
        return {"kind": "text", "count": len(value)}
    if value is None:
        return {"kind": "nothing", "count": 0}
    if isinstance(value, bool):
        return {"kind": "yes or no", "count": 1}
    if isinstance(value, (int, float)):
        return {"kind": "number", "count": 1}
    return {"kind": type(value).__name__, "count": 1}


def _amount(shape: dict[str, Any]) -> str:
    """One value's size, in the words a builder counts in."""
    count = shape.get("count", 0)
    kind = shape.get("kind")
    if kind == "list":
        return f"{count:,} item" + ("" if count == 1 else "s")
    if kind == "text":
        return f"{count:,} character" + ("" if count == 1 else "s")
    if kind == "record":
        return f"{count:,} field" + ("" if count == 1 else "s")
    if kind == "nothing":
        return "nothing"
    return kind or "a value"


def _absent(value: Any) -> bool:
    """Whether this is a recorded ``Unknown``: an edge that did not fire, or a stated absence."""
    return isinstance(value, dict) and value.get("type") == "unknown"


def _join_volume(value: dict[str, Any], limit: int) -> str:
    """A `Join`'s volume, edge by edge, because that is what a join is.

    A record of a join holds every declared in-edge whether or not it fired, so counting its
    fields would report the graph rather than the run.
    """
    edges = value.get("edges") or {}
    fired = [(name, inner) for name, inner in edges.items() if not _absent(inner)]
    if not fired:
        return f"nothing arrived on {len(edges)} edge" + ("" if len(edges) == 1 else "s")
    shown = " · ".join(f"{name} {_volume(inner, limit)}" for name, inner in fired[:limit])
    quiet = len(edges) - len(fired)
    return shown + (f" · {quiet} edge{'' if quiet == 1 else 's'} did not fire" if quiet else "")


def _counts_in(value: dict[str, Any]) -> list[tuple[str, int]]:
    """Each key holding a non-empty list, with how many it holds, biggest first."""
    counted = [
        (key, len(inner)) for key, inner in value.items() if isinstance(inner, list) and inner
    ]
    counted.sort(key=lambda pair: -pair[1])
    return counted


def _text_in(value: dict[str, Any]) -> list[tuple[str, int]]:
    """Each key holding non-empty text, with its length, longest first."""
    text = [(key, len(inner)) for key, inner in value.items() if isinstance(inner, str) and inner]
    text.sort(key=lambda pair: -pair[1])
    return text


def _numbers_in(value: dict[str, Any]) -> list[tuple[str, int]]:
    """Each key holding a whole number, biggest first.

    A step that counts what it moved rather than carrying it reports numbers, which is what
    ``ctx.record_access`` invites and what a step reading 67,353 rows and keeping 12 has to
    say. Reading that as "2 fields" reports the record's shape and not what moved.
    """
    counted = [
        (key, int(inner))
        for key, inner in value.items()
        if isinstance(inner, int) and not isinstance(inner, bool)
    ]
    counted.sort(key=lambda pair: -pair[1])
    return counted


def _volume(value: Any, limit: int = 4) -> str:
    """How much data a step received or produced, as one line.

    ::

        _volume({"pool": [1, 2], "survey": [3, 4, 5]})     # 'survey 3 · pool 2'
        _volume({"rows": 67_353, "kept": 12})              # 'rows 67,353 · kept 12'

    A record names the keys that hold a count, because those are what grew or shrank, and it
    names them from the whole record rather than from the keys the shape shows. A record whose
    counts are numbers rather than collections names those, one of text names its longest, and
    one holding none of the three is reported by its field count.
    """
    if _absent(value):
        return "nothing"
    if isinstance(value, dict) and value.get("type") == "join":
        return _join_volume(value, limit)
    if not isinstance(value, dict) or not value:
        return _amount(_shape(value, 0))
    counted = _counts_in(value)
    if counted:
        shown = " · ".join(f"{key} {size:,}" for key, size in counted[:limit])
        return shown + (f" · and {len(counted) - limit} more" if len(counted) > limit else "")
    return _scalars(value, limit)


def _scalars(value: dict[str, Any], limit: int) -> str:
    """A record holding no collection: its counts, else its longest text, else its size."""
    numbers, text = _numbers_in(value), _text_in(value)
    if numbers and len(numbers) >= len(text):
        return " · ".join(f"{key} {size:,}" for key, size in numbers[:limit])
    if not text:
        return _amount(_shape(value, 0))
    return " · ".join(
        f"{key} {size:,} character{'' if size == 1 else 's'}" for key, size in text[:2]
    )


def _skipped(record: dict[str, Any]) -> bool:
    return record.get("termination") == "skipped"


def _arrived(given: Any) -> dict[str, dict[str, Any]]:
    """What came in on each edge, where the step took a `Join`, keyed by the step that sent it.

    A step with several edges into it records a `Join` holding one entry per declared edge,
    carrying either the value that arrived or an `Unknown` saying why it did not. That is
    per-edge truth read from the receiving end, which is the only end that has it.
    """
    if not isinstance(given, dict) or given.get("type") != "join":
        return {}
    found = {}
    for source, value in (given.get("edges") or {}).items():
        shown, full = _compact(value)
        found[str(source)] = {
            "absent": _absent(value),
            "reason": value.get("reason") if _absent(value) else None,
            "value": shown,
            "chars": full,
            "volume": _volume(value),
        }
    return found


def _example(record: dict[str, Any], run: str) -> dict[str, Any]:
    """What one execution received and produced, clipped, with what was held back."""
    held_back = []
    if record.get("redactions"):
        held_back.append("redacted")
    if record.get("omissions"):
        held_back.append("held back")
    given, produced = record.get("inputs"), record.get("outputs")
    return {
        "run": run,
        "when": record.get("started_at"),
        "took_in": _rows(record.get("inputs")),
        "handed_on": _rows(record.get("outputs")),
        "took_in_shape": _shape(given),
        "handed_on_shape": _shape(produced),
        "took_in_volume": _volume(given),
        "handed_on_volume": _volume(produced),
        "arrived": _arrived(given),
        "error": (record.get("error") or {}).get("message") if record.get("error") else None,
        "held_back": held_back,
        "executions": 1,
    }


def _elapsed_ms(started: str | None, ended: str | None) -> float:
    if not started or not ended:
        return 0.0
    read = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
    try:
        return (read(ended) - read(started)).total_seconds() * 1000.0
    except ValueError:
        return 0.0


def _cost_of(manifest: dict[str, Any]) -> tuple[float, str, bool, bool]:
    """One run's cost, keyed ``basis:currency:label`` so two bases are never summed.

    A run whose total could not be derived contributes the floor it did measure, and the
    fourth field says it was one. Reading such a run as zero reported a rate-limited
    evaluation that cost real money as costing nothing.
    """
    cost = (manifest.get("totals") or {}).get("cost") or {}
    basis = manifest.get("cost_basis") or {}
    label = basis.get("device") if basis.get("kind") == "device" else cost.get("currency")
    value = cost.get("value")
    floor = False
    if not isinstance(value, (int, float)):
        value = cost.get("measured")
        floor = True
    if not isinstance(value, (int, float)):
        return 0.0, "", False, False
    return (
        float(value),
        f"{cost.get('basis') or 'unknown'}:{cost.get('currency') or '?'}:{label or '?'}",
        bool(cost.get("is_upper_bound")),
        floor,
    )


def _signature(manifest: dict[str, Any]) -> str:
    return " → ".join(n.get("node_id", "?") for n in manifest.get("nodes") or [])


def _newest_open_manifest(runs_dir: Path) -> tuple[str, Path, dict[str, Any]] | None:
    """The most recently started run whose manifest is not closed, or ``None``."""
    newest: tuple[str, Path, dict[str, Any]] | None = None
    for manifest_path in manifest_paths(runs_dir):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if manifest.get("ended_at"):
            continue
        started = manifest.get("started_at") or ""
        if newest is None or started > newest[0]:
            newest = (started, manifest_path, manifest)
    return newest


def _count_one(done: dict[str, dict[str, Any]], record: dict[str, Any], run: str) -> None:
    """Fold one finished record into what the moving run has done so far."""
    node_id = record.get("node_id", "?")
    one = done.setdefault(node_id, {"executions": 0, "ms": 0.0, "errors": 0, "skipped": 0})
    if _skipped(record):
        one["skipped"] += 1
        return
    one["executions"] += 1
    if "example" not in one:
        one["example"] = _example(record, run)
    if record.get("error"):
        one["errors"] += 1
    one["ms"] += _elapsed_ms(record.get("started_at"), record.get("ended_at"))


def _still_in_flight(head: str, finished_records: set[str]) -> bool:
    """Whether this model call belongs to a step whose own record has not been written."""
    start = head.find('"parent_id": "')
    if start < 0:
        return True
    return head[start + 14 : head.find('"', start + 14)] not in finished_records


def _follow(trajectory: Path, run: str) -> tuple[dict[str, dict[str, Any]], int]:
    """What the moving run has finished, and how many model calls are still out."""
    done: dict[str, dict[str, Any]] = {}
    finished_records: set[str] = set()
    pending = 0
    with trajectory.open(encoding="utf-8") as handle:
        for line in handle:
            head = line[:220]
            if any(mark in head for mark in _NODE_EXECUTION_MARKS):
                if len(line) > MAX_RECORD_CHARS:
                    continue
                try:
                    record = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                _count_one(done, record, run)
                if record.get("record_id"):
                    finished_records.add(record["record_id"])
            elif '"record_type": "model_call"' in head or '"record_type":"model_call"' in head:
                pending += int(_still_in_flight(head, finished_records))
    return done, pending


def live_run(root: str | Path) -> dict[str, Any] | None:
    """The run happening right now, or ``None``.

    ::

        moving = live_run(".")
        moving["done"]                # what each step has finished, by node id
        moving["calls_in_flight"]     # model calls whose step has not landed yet

    A run is live while its manifest has no ``ended_at`` and its trajectory moved in the
    last fifteen minutes, so a crashed run stops haunting the page on its own.
    """
    import time

    newest = _newest_open_manifest(Path(root).expanduser() / "runs")
    if newest is None:
        return None
    started, path, manifest = newest
    trajectory = path.parent / "trajectory.jsonl"
    if not trajectory.exists() or time.time() - trajectory.stat().st_mtime > 900:
        return None
    done, pending = _follow(trajectory, path.parent.name)
    return {
        "run": path.parent.name,
        "fingerprint": manifest.get("graph_fingerprint"),
        "signature": _signature(manifest),
        "started_at": started,
        "done": done,
        "calls_in_flight": pending,
        "evaluation": _evaluation_around(path.parent),
    }


def _evaluation_around(run_dir: Path) -> dict[str, Any] | None:
    """The evaluation a live rollout belongs to, and how far it has got.

    The runner keeps ``progress.json`` current beside the rollouts: the total it declared,
    the outcomes it has scored so far, what they cost, and its own estimate of the time
    left. Where that file is absent (an evaluation written by an older library) the count
    of finished rollouts is read off their manifests and carries no total, because the page
    does not invent a denominator.
    """
    holder = run_dir.parent
    if holder.parent.name != "eval" and not holder.name.startswith("eval_"):
        return None
    held = {
        "id": holder.name,
        "rollouts_done": 0,
        "total": None,
        "outcomes": {},
        "scored_right": None,
        "cost": None,
        "currency": None,
        "elapsed_s": None,
        "remaining_s": None,
        "updated_at": None,
    }
    progress = _progress_written(holder / "progress.json")
    if progress is not None:
        held.update(progress)
        return held
    finished = 0
    for sibling in holder.glob("*/manifest.json"):
        try:
            record = json.loads(sibling.read_text())
        except (OSError, ValueError):
            continue
        if record.get("ended_at"):
            finished += 1
    held["rollouts_done"] = finished
    return held


def _progress_written(path: Path) -> dict[str, Any] | None:
    """What the runner's ``progress.json`` says, or ``None`` where there is none to read."""
    from ..evaluation.outcomes import Outcome

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    outcomes = {str(k): int(v) for k, v in (record.get("outcomes") or {}).items()}
    right = 0
    for name, count in outcomes.items():
        try:
            right += count if Outcome(name).succeeded else 0
        except ValueError:
            continue
    return {
        "rollouts_done": int(record.get("finished") or 0),
        "total": record.get("total"),
        "outcomes": outcomes,
        "scored_right": right,
        "cost": record.get("cost"),
        "currency": record.get("currency"),
        "elapsed_s": record.get("elapsed_s"),
        "remaining_s": record.get("remaining_s"),
        "updated_at": record.get("updated_at"),
    }


def _new_group(key: str, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "fingerprint": manifest.get("graph_fingerprint"),
        "signature": _signature(manifest),
        "runs": 0,
        "first": None,
        "last": None,
        "cost_by_basis": defaultdict(float),
        "cost_upper_bound": set(),
        "cost_is_floor": set(),
        "consultations": 0,
        "outcomes": Counter(),
        "models": set(),
        "agent_node_dates": {},
    }


def _absorb_cost(entry: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Add one run's cost under its own basis, so two bases are never summed."""
    value, basis, upper, floor = _cost_of(manifest)
    if not basis:
        return
    entry["cost_by_basis"][basis] += value
    if upper:
        entry["cost_upper_bound"].add(basis)
    if floor:
        entry["cost_is_floor"].add(basis)


def _absorb_when(entry: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Move the group's first and last dates, and note when each agent step last ran."""
    started = manifest.get("started_at") or ""
    if not started:
        return
    entry["first"] = min(entry["first"] or started, started)
    entry["last"] = max(entry["last"] or started, started)
    for node in manifest.get("nodes") or []:
        if node.get("node_kind") == "agent":
            held = entry["agent_node_dates"].get(node["node_id"], "")
            entry["agent_node_dates"][node["node_id"]] = max(held, started[:10])


def _absorb(entry: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Fold one run's manifest into the group for the shape that made it."""
    entry["runs"] += 1
    _absorb_cost(entry, manifest)
    _absorb_when(entry, manifest)
    entry["consultations"] += int((manifest.get("counts") or {}).get("consultation") or 0)
    entry["outcomes"][manifest.get("outcome") or "unrecorded"] += 1
    configured = (manifest.get("models") or {}).get("configured") or {}
    if isinstance(configured, dict) and configured.get("request_model"):
        entry["models"].add(configured["request_model"])


def _blank() -> dict[str, Any]:
    return {"executions": 0, "ms": 0.0, "errors": 0, "skipped": 0, "ended": {}}


def _scan(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """One run read whole: what each step did, one value each, and what was asked of a person.

    ``ended`` counts a step's terminations, which is where a failure, an exhausted budget and
    a step nothing reached are told apart. A retried step has an execution per attempt, so
    ``executions`` above one on a single run is what a retry looks like.
    """
    stats: dict[str, dict[str, Any]] = defaultdict(_blank)
    run_name = path.parent.name
    examples: dict[str, dict[str, Any]] = {}
    parents: dict[str, str] = {}
    for record, oversize in _node_executions(path.parent / "trajectory.jsonl"):
        if record is None:
            held = examples.setdefault(
                oversize["node_id"],
                {
                    "run": run_name,
                    "too_large": oversize["chars"],
                    "took_in": [],
                    "handed_on": [],
                    "executions": 0,
                },
            )
            held["executions"] += 1
            continue
        node_id = record.get("node_id", "?")
        if record.get("record_id"):
            parents[record["record_id"]] = node_id
        one = stats[node_id]
        ending = record.get("termination")
        if ending:
            one["ended"][ending] = one["ended"].get(ending, 0) + 1
        if _skipped(record):
            one["skipped"] += 1
            continue
        one["executions"] += 1
        if record.get("error"):
            one["errors"] += 1
        one["ms"] += _elapsed_ms(record.get("started_at"), record.get("ended_at"))
        if node_id in examples:
            examples[node_id]["executions"] += 1
        else:
            examples[node_id] = _example(record, run_name)
    return {
        "run": run_name,
        "started_at": manifest.get("started_at"),
        "outcome": manifest.get("outcome"),
        "questions": _questions_in(path.parent / "trajectory.jsonl", parents),
        "nodes": {
            n["node_id"]: {
                "kind": n.get("node_kind"),
                "planned": bool(n.get("planned")),
                "example": examples.get(n["node_id"]),
                **stats.get(n["node_id"], _blank()),
            }
            for n in manifest.get("nodes") or []
        },
    }


def rollout_runs(root: str | Path) -> dict[str, Any]:
    """The runs an evaluation made, which sit a level below the project's own.

    ::

        rollout_runs(".")     # {"runs": 6, "evaluations": ["eval_fde20093d0ff"]}

    `read_runs` reads ``runs/*/`` and stops there, which is what ``runs("runs/")`` returns
    and what the project's own runs are. An evaluation writes a directory per rollout under
    one for the evaluation, so those are counted here and never mixed into a shape's history.
    """
    runs_dir = Path(root).expanduser() / "runs"
    found = manifest_paths(runs_dir, rollouts=True)
    return {
        "runs": len(found),
        "evaluations": sorted({path.parent.parent.name for path in found}),
    }


def _two_newest(
    paths: list[tuple[str, Path, dict[str, Any]]],
) -> list[tuple[str, Path, dict[str, Any]]]:
    """The two most recently started runs of one shape, newest first."""
    return sorted(paths, key=lambda held: held[0], reverse=True)[:2]


def read_runs(root: str | Path) -> list[dict[str, Any]]:
    """One entry per distinct pipeline shape found under ``runs/``, busiest first.

    ::

        [group["signature"] for group in read_runs(".")]
        read_runs(".")[0]["newest"]["nodes"]["judge"]["example"]
        read_runs(".")[0]["previous"]["run"]      # the run before it, or None

    The newest run of each shape is read whole, and the one before it too, so the page can say
    what moved between them. Every other run contributes its manifest alone.
    """
    runs_dir = Path(root).expanduser() / "runs"
    groups: dict[str, dict[str, Any]] = {}
    recent: dict[str, list[tuple[str, Path, dict[str, Any]]]] = defaultdict(list)

    for manifest_path in manifest_paths(runs_dir):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not (manifest.get("nodes") or []):
            continue
        key = manifest.get("graph_fingerprint") or f"signature:{_signature(manifest)}"
        _absorb(groups.setdefault(key, _new_group(key, manifest)), manifest)
        recent[key] = _two_newest(
            [*recent[key], (manifest.get("started_at") or "", manifest_path, manifest)]
        )

    for key, held in recent.items():
        read = [_scan(path, manifest) for _started, path, manifest in held]
        groups[key]["newest"] = read[0] if read else None
        groups[key]["previous"] = read[1] if len(read) > 1 else None

    ordered = sorted(groups.values(), key=lambda g: -g["runs"])
    for entry in ordered:
        entry["cost_by_basis"] = dict(entry["cost_by_basis"])
        entry["cost_upper_bound"] = sorted(entry["cost_upper_bound"])
        entry["cost_is_floor"] = sorted(entry["cost_is_floor"])
        entry["outcomes"] = dict(entry["outcomes"])
        entry["models"] = sorted(entry["models"])
        entry.setdefault("newest", None)
        entry.setdefault("previous", None)
    return ordered
