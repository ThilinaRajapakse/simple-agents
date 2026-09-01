"""The labelled data the project is measured on, read from ``evals/examples.jsonl``.

The set is the other half of what an evaluation says: a figure over nine examples and a figure
over nine hundred are read differently, and so is one where nothing is absent
(`docs/evaluation.md` §1.1).

**Only an inspectable split contributes a worked example.** Held-out splits contribute counts
and proportions but no rendered example, preserving their use in evaluation (FT-02).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["read_examples", "DEFAULT_EXAMPLES"]

DEFAULT_EXAMPLES = Path("evals") / "examples.jsonl"

MAX_VALUE_CHARS = 400
"""How much of one field of a worked example the page carries."""

_INSPECTABLE = ("dev", "train", "development")
"""Split names the viewer may inspect; every other split is held out."""


def _clip(value: Any) -> str:
    if isinstance(value, str):
        written = value
    else:
        try:
            written = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            written = str(value)
    written = " ".join(written.split())
    return written[:MAX_VALUE_CHARS]


def _rows(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        return [{"key": str(key), "value": _clip(inner)} for key, inner in value.items()]
    return [{"key": "", "value": _clip(value)}]


def _absent(entry: dict[str, Any]) -> bool:
    """Whether this example's right answer is that the value is not there."""
    expected = entry.get("expected")
    if expected is None:
        return True
    return isinstance(expected, dict) and expected.get("type") == "unknown"


def _worked(entry: dict[str, Any]) -> dict[str, Any]:
    """One example as the page shows it: what goes in, and what the right answer is."""
    return {
        "id": entry.get("id"),
        "split": entry.get("split"),
        "source": entry.get("source"),
        "inputs": _rows(entry.get("inputs")),
        "expected": _rows(entry.get("expected")),
        "expects_absence": _absent(entry),
        "labelled_steps": sorted((entry.get("expected_by_node") or {}).keys()),
        "metadata": sorted((entry.get("metadata") or {}).keys()),
    }


def _entries(target: Path) -> tuple[list[dict[str, Any]], int]:
    """Every row of the file that reads as an object, and how many did not."""
    entries: list[dict[str, Any]] = []
    unreadable = 0
    with target.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                held = json.loads(line)
            except ValueError:
                unreadable += 1
                continue
            if isinstance(held, dict):
                entries.append(held)
    return entries, unreadable


def _counted(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Splits, the absent answers inside each, the sources, and the steps a label reaches."""
    splits: dict[str, int] = {}
    absent: dict[str, int] = {}
    sources: set[str] = set()
    labelled: set[str] = set()
    for entry in entries:
        name = str(entry.get("split") or "unnamed")
        splits[name] = splits.get(name, 0) + 1
        if _absent(entry):
            absent[name] = absent.get(name, 0) + 1
        if entry.get("source"):
            sources.add(str(entry["source"]))
        labelled.update((entry.get("expected_by_node") or {}).keys())
    return {
        "splits": dict(sorted(splits.items())),
        "absent": absent,
        "sources": len(sources),
        "labelled_steps": sorted(labelled),
    }


def read_examples(root: str | Path) -> dict[str, Any] | None:
    """What the project has to measure itself against, or ``None`` where it has none.

    ::

        held = read_examples(".")
        held["splits"]          # {'dev': 22, 'held_out': 9}
        held["worked"]          # one example, never from a held-out split

    Every count is over the whole file. ``worked`` is one example from a split a project may
    look at, and is ``None`` where every example is held out.
    """
    target = Path(root).expanduser() / DEFAULT_EXAMPLES
    if not target.exists():
        return None
    entries, unreadable = _entries(target)
    if not entries and not unreadable:
        return None

    inspectable = [e for e in entries if str(e.get("split") or "") in _INSPECTABLE]
    return {
        "path": str(DEFAULT_EXAMPLES),
        "total": len(entries),
        **_counted(entries),
        "fields": sorted(
            {key for e in entries if isinstance(e.get("inputs"), dict) for key in e["inputs"]}
        ),
        "worked": _worked(inspectable[0]) if inspectable else None,
        "unreadable": unreadable,
    }
