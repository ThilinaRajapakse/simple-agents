"""What every run a project ever made says, per step and per edge.

`runs_overlay` reads every manifest and the two newest trajectories of each shape, which is
what one run looks like. This is the other question: over the whole record, what does each step
cost, how often is each edge taken, and what has each step done to the stores it declares.

**Cost is never summed across two bases.** A project that ran against a hosted price and
against a device holds figures in dollars and figures in device-seconds, and adding them
produces a number in no unit. Every figure here is keyed by its basis, the way a run group's
totals already are.

**A node execution is read without parsing its payload.** One can be megabytes and six of its
fields matter here, so they are lifted out of the line and the record is parsed whole only when
that misses. A model call is parsed, because what it cost is derived from it and a cost taken
off a reconstruction is an unverifiable cost.

Measured 2026-08-28 over the largest project on record: 2,393 runs, 2.54 GB, 12,421 node
executions and 49,767 model calls, in **4.3 seconds**.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..cost import basis_from_manifest, cost_of
from ..envelope import manifest_paths

__all__ = ["read_record"]

_NODE_MARKS = ('"record_type": "node_execution"', '"record_type":"node_execution"')
_MODEL_MARKS = ('"record_type": "model_call"', '"record_type":"model_call"')
_TOOL_MARKS = ('"record_type": "tool_call"', '"record_type":"tool_call"')
_ACCESS_MARKS = ('"record_type": "resource_access"', '"record_type":"resource_access"')

_RECORD_ID = re.compile(r'"record_id"\s*:\s*"([^"]*)"')
_NODE_ID = re.compile(r'"node_id"\s*:\s*"([^"]*)"')
_ROUTE = re.compile(r'"route"\s*:\s*\[([^\]]*)\]')
_TERMINATION = re.compile(r'"termination"\s*:\s*(?:"([^"]*)"|null)')
_QUOTED = re.compile(r'"([^"]*)"')
_STARTED = re.compile(r'"started_at"\s*:\s*"([^"]*)"')
_ENDED = re.compile(r'"ended_at"\s*:\s*(?:"([^"]*)"|null)')

HEAD = 4_000
"""How much of a line the head fields are looked for in before the record is parsed whole."""

TAIL = 1_200
"""How much of a node execution's end its route and termination are looked for in.

They are written after the payloads, so the tail is where they are. A record whose tail does
not hold them is parsed whole rather than guessed at.
"""


def _last(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    """The final match, which is the record's own field rather than one inside a payload."""
    found = None
    for match in pattern.finditer(text):
        found = match
    return found


def _node_facts(line: str) -> dict[str, Any] | None:
    """A node execution's id, node, route and termination, without parsing its payload.

    ``None`` where the line does not yield all six, which sends the caller to ``json.loads``.

    **The payload is never searched.** Every field read here is written before ``inputs`` or
    after ``outputs`` (`docs/trajectory-format.md` §3), so the head stops at the first payload
    and the tail takes each field's last match. A payload holding the word ``route`` would
    otherwise be read as the route the run took.
    """
    payload = line.find('"inputs"')
    head = line[: HEAD if payload < 0 else min(HEAD, payload)]
    tail = line[-TAIL:]
    record_id = _RECORD_ID.search(head)
    node_id = _NODE_ID.search(head)
    route = _last(_ROUTE, tail)
    termination = _last(_TERMINATION, tail)
    started = _STARTED.search(head)
    ended = _ENDED.search(head)
    if not (record_id and node_id and route and termination and started and ended):
        return None
    return {
        "record_id": record_id.group(1),
        "node_id": node_id.group(1),
        "route": _QUOTED.findall(route.group(1)),
        "termination": termination.group(1),
        "started_at": started.group(1),
        "ended_at": ended.group(1),
        "item_index": None,
    }


def _parsed_node(line: str) -> dict[str, Any] | None:
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return {
        "record_id": record.get("record_id"),
        "node_id": record.get("node_id", "?"),
        "route": list(record.get("route") or []),
        "termination": record.get("termination"),
        "started_at": record.get("started_at"),
        "ended_at": record.get("ended_at"),
        "item_index": record.get("item_index"),
    }


def _blank_node() -> dict[str, Any]:
    return {
        "executions": 0,
        "skipped": 0,
        "model_calls": 0,
        "tool_calls": 0,
        "cost_by_basis": defaultdict(float),
        "cost_unknown": 0,
        "ms": 0.0,
        "spend_by_currency": defaultdict(float),
        "items": set(),
        "reads": defaultdict(int),
        "writes": defaultdict(int),
    }


def _blank_group(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "fingerprint": manifest.get("graph_fingerprint"),
        "runs": 0,
        "unreadable": 0,
        "nodes": defaultdict(_blank_node),
        "edges": defaultdict(int),
        "accesses": defaultdict(list),
        "tool_calls": defaultdict(list),
        "tool_call_counts": defaultdict(int),
        "bases": set(),
    }


def _basis_key(manifest: dict[str, Any]) -> str:
    """One run's cost basis as a word a reader recognises, and the key figures sum under."""
    basis = manifest.get("cost_basis") or {}
    kind = basis.get("kind")
    if kind == "device":
        return f"device-seconds on {basis.get('device') or 'a device'}"
    currency = basis.get("currency")
    return str(currency) if currency else "an undeclared basis"


def _own_the_call(
    record: dict[str, Any], owner: dict[str, str], parents: dict[str, str]
) -> str | None:
    """Which node a model or tool call belongs to, walking up to the first node execution."""
    at = record.get("parent_id")
    for _step in range(6):
        if at is None:
            return None
        if at in owner:
            return owner[at]
        at = parents.get(at)
    return None


def _absorb_line(
    line: str,
    group: dict[str, Any],
    owner: dict[str, str],
    parents: dict[str, str],
    deferred: list[dict[str, Any]],
) -> None:
    """One line: a node execution folded in now, anything else kept for the second pass.

    A call is attributed to the node it was made inside, and a node execution is written
    after the calls beneath it, so the calls wait until every owner is known.
    """
    head = line[:220]
    if any(mark in head for mark in _NODE_MARKS):
        facts = _node_facts(line) or _parsed_node(line)
        if facts is not None:
            _absorb_node(facts, group, owner)
        return
    if not any(
        mark in head for marks in (_MODEL_MARKS, _TOOL_MARKS, _ACCESS_MARKS) for mark in marks
    ):
        return
    record = _load(line)
    if record is None:
        return
    deferred.append(record)
    _note_parent(record, parents)


def _one_run(path: Path, manifest: dict[str, Any], group: dict[str, Any]) -> None:
    """Fold one run's trajectory into its shape's totals."""
    basis = basis_from_manifest(manifest.get("cost_basis"))
    key = _basis_key(manifest)
    group["bases"].add(key)
    owner: dict[str, str] = {}
    parents: dict[str, str] = {}
    deferred: list[dict[str, Any]] = []

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            _absorb_line(line, group, owner, parents, deferred)

    for record in deferred:
        _absorb_call(record, group, owner, parents, basis, key, path.parent.name)


def _load(line: str) -> dict[str, Any] | None:
    try:
        held = json.loads(line)
    except ValueError:
        return None
    return held if isinstance(held, dict) else None


def _note_parent(record: dict[str, Any], parents: dict[str, str]) -> None:
    """A model call made inside a tool call reaches its node through the tool call."""
    if record.get("record_id") and record.get("parent_id"):
        parents[record["record_id"]] = record["parent_id"]


def _elapsed_ms(started: str | None, ended: str | None) -> float:
    """How long one execution took, and zero where either end is missing."""
    if not started or not ended:
        return 0.0
    try:
        first = datetime.fromisoformat(started.replace("Z", "+00:00"))
        last = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return (last - first).total_seconds() * 1000.0


def _absorb_node(facts: dict[str, Any], group: dict[str, Any], owner: dict[str, str]) -> None:
    node_id = facts["node_id"]
    if facts["record_id"]:
        owner[facts["record_id"]] = node_id
    held = group["nodes"][node_id]
    if facts["termination"] == "skipped":
        held["skipped"] += 1
        return
    held["executions"] += 1
    held["ms"] += _elapsed_ms(facts.get("started_at"), facts.get("ended_at"))
    for target in facts["route"]:
        group["edges"][f"{node_id}→{target}"] += 1


def _absorb_model(record: dict[str, Any], held: dict[str, Any], basis: Any, key: str) -> None:
    """One model call priced against the basis its own run declared."""
    held["model_calls"] += 1
    priced = cost_of(record, basis)
    if priced.value is None:
        held["cost_unknown"] += 1
    else:
        held["cost_by_basis"][key] += float(priced.value)


def _absorb_tool(
    record: dict[str, Any], group: dict[str, Any], held: dict[str, Any], node_id: str, run: str
) -> None:
    """One tool call: what it spent, and the call itself for the store it names."""
    held["tool_calls"] += 1
    spent = record.get("spent") or {}
    if isinstance(spent.get("amount"), (int, float)):
        held["spend_by_currency"][str(spent.get("currency") or "?")] += float(spent["amount"])
    name = str(record.get("tool_name") or "?")
    group["tool_call_counts"][name] += 1
    group["tool_calls"][name].append(
        {
            "node_id": node_id,
            "run": run,
            "tool": name,
            "effect": record.get("side_effect_class"),
            "inputs": record.get("inputs"),
            "outputs": record.get("outputs"),
            "omitted": sorted(record.get("omissions") or []),
        }
    )


def _absorb_access(
    record: dict[str, Any], group: dict[str, Any], held: dict[str, Any], node_id: str, run: str
) -> None:
    """One access a step's own code recorded, counted and kept for the store's card."""
    resource = str(record.get("resource") or "?")
    held["writes" if record.get("direction") == "write" else "reads"][resource] += 1
    group["accesses"][resource].append(
        {
            "node_id": node_id,
            "run": run,
            "direction": record.get("direction"),
            "inputs": record.get("inputs"),
            "outputs": record.get("outputs"),
            "omitted": sorted(record.get("omissions") or []),
        }
    )


def _absorb_call(
    record: dict[str, Any],
    group: dict[str, Any],
    owner: dict[str, str],
    parents: dict[str, str],
    basis: Any,
    key: str,
    run: str,
) -> None:
    """One call, folded onto the node it was made inside."""
    kind = record.get("record_type")
    node_id = (
        record.get("node_id")
        if kind == "resource_access"
        else _own_the_call(record, owner, parents)
    )
    if node_id is None:
        return
    held = group["nodes"][node_id]
    if record.get("item_index") is not None:
        # Counted as a set of (run, index): one item makes several calls, and two runs of one
        # fan-out repeat the same indices. The highest index seen is not how many there were.
        held["items"].add((run, int(record["item_index"])))
    if kind == "model_call":
        _absorb_model(record, held, basis, key)
    elif kind == "tool_call":
        _absorb_tool(record, group, held, node_id, run)
    elif kind == "resource_access":
        _absorb_access(record, group, held, node_id, run)


MAX_ACCESSES = 40
"""Accesses kept per resource, newest run first. The counts are over every run."""


def _settled(group: dict[str, Any]) -> dict[str, Any]:
    """One shape's totals as plain data, with the defaultdicts closed."""
    nodes = {}
    for node_id, held in group["nodes"].items():
        nodes[node_id] = {
            **{
                k: v
                for k, v in held.items()
                if k not in ("cost_by_basis", "spend_by_currency", "reads", "writes", "items")
            },
            "items": len(held["items"]),
            "cost_by_basis": dict(held["cost_by_basis"]),
            "spend_by_currency": dict(held["spend_by_currency"]),
            "reads": dict(held["reads"]),
            "writes": dict(held["writes"]),
        }
    edges = [
        {"from": name.split("→")[0], "to": name.split("→")[1], "runs": count}
        for name, count in sorted(group["edges"].items(), key=lambda pair: -pair[1])
    ]
    return {
        "fingerprint": group["fingerprint"],
        "runs": group["runs"],
        "unreadable": group["unreadable"],
        "nodes": nodes,
        "edges": edges,
        "bases": sorted(group["bases"]),
        "accesses": {name: found[-MAX_ACCESSES:] for name, found in group["accesses"].items()},
        "access_counts": {name: len(found) for name, found in group["accesses"].items()},
        "tool_calls": {name: found[-MAX_ACCESSES:] for name, found in group["tool_calls"].items()},
        "tool_call_counts": dict(group["tool_call_counts"]),
    }


def _signature(manifest: dict[str, Any]) -> str:
    return " → ".join(n.get("node_id", "?") for n in manifest.get("nodes") or [])


def _over(paths: list[Path]) -> dict[str, dict[str, Any]]:
    """One group per shape over the runs given, each read whole."""
    groups: dict[str, dict[str, Any]] = {}
    for manifest_path in paths:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not (manifest.get("nodes") or []):
            continue
        key = manifest.get("graph_fingerprint") or f"signature:{_signature(manifest)}"
        group = groups.setdefault(key, _blank_group(manifest))
        group["runs"] += 1
        trajectory = manifest_path.parent / "trajectory.jsonl"
        if not trajectory.exists():
            group["unreadable"] += 1
            continue
        try:
            _one_run(trajectory, manifest, group)
        except OSError:
            group["unreadable"] += 1
    return {key: _settled(group) for key, group in groups.items()}


def read_record(root: str | Path) -> dict[str, dict[str, dict[str, Any]]]:
    """Every run a project has made, read for what each step cost and each edge carried.

    ::

        held = read_record(".")
        one = held["runs"]["sha256:5cd1c1f4a52c0f1a"]
        one["nodes"]["judge"]["cost_by_basis"]      # {'USD': 0.41}
        one["edges"][0]                             # {'from': ..., 'to': ..., 'runs': 2423}
        one["accesses"]["catalogue"][-1]["outputs"] # what the newest read came back with
        held["rollouts"]["sha256:5cd1c1f4a52c0f1a"] # the same over an evaluation's rollouts

    **The project's own runs and an evaluation's rollouts are counted apart.** They answer
    different questions, and one population's figures added to the other's describe nothing.
    Both are keyed the way `read_runs` groups: the manifest's ``graph_fingerprint`` where it
    has one, the node-id chain where it does not.

    Every trajectory is read. On the largest project on record that is 2.54 GB and takes a few
    seconds; a project at the `shape` gate has no run record to read.
    """
    runs_dir = Path(root).expanduser() / "runs"
    return {
        "runs": _over(manifest_paths(runs_dir)),
        "rollouts": _over(manifest_paths(runs_dir, rollouts=True)),
    }
