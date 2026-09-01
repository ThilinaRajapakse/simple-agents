"""Re-key a cassette's tool calls after the key gained the node and the occurrence became
the node's.

A tool call used to be keyed on the tool, its arguments and how many times that exact call had
been made anywhere in the run. It is now keyed on those and the node the call was made in, and
the occurrence counts within that node. Every entry already stores the node it ran in and the
whole of what the key is made from, so a recorded file is migrated by arithmetic and no backend
is called::

    uv run python scripts/rekey_tool_calls.py tests/cassettes/*.jsonl
    uv run python scripts/rekey_tool_calls.py --check tests/cassettes/*.jsonl

``--check`` reports what would change and writes nothing.

``--relabel=old=new`` corrects the node an entry names before it is keyed. A recording made
before a fix can name a node that never made the call, which cost nothing while the label was
only read by a miss message and is wrong once the label is in the key::

    uv run python scripts/rekey_tool_calls.py --relabel=consult=outfit suspend.jsonl

Entries are renumbered in the order they were recorded, which is the order the file holds them
in, so an occurrence taken across a run becomes the one that node would take on its own.

**What this declines.** An entry whose arguments were redacted before being stored: the key was
hashed from the arguments themselves and the file holds the marker, so the key cannot be
recomputed. Those are reported and the file is left alone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from simple_agents.records.cassette import tool_call_key  # noqa: E402
from simple_agents.records.trajectory import SECRET_MARKER  # noqa: E402


def _redacted(value: object) -> bool:
    """Whether a stored argument holds the marker rather than what was hashed."""
    if isinstance(value, str):
        return SECRET_MARKER in value
    if isinstance(value, dict):
        return any(_redacted(item) for item in value.values())
    if isinstance(value, list):
        return any(_redacted(item) for item in value)
    return False


def rekey(
    path: Path, *, write: bool, relabel: dict[str, str] | None = None
) -> tuple[int, int, list[str]]:
    """Rewrite one file's tool-call keys. Returns changed, unchanged, and what was declined."""
    relabel = relabel or {}
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    seen: dict[str, int] = {}
    declined: list[str] = []
    changed = unchanged = 0
    out: list[str] = []

    for line in lines:
        entry = json.loads(line)
        if entry.get("kind") != "tool_call":
            out.append(line)
            continue
        request = entry.get("request") or {}
        node_id = relabel.get(entry.get("node_id"), entry.get("node_id"))
        entry["node_id"] = node_id
        if node_id is None:
            declined.append(f"{entry.get('key')}: no node_id on the entry")
            out.append(line)
            continue
        arguments = request.get("arguments") or {}
        if _redacted(arguments):
            declined.append(f"{entry.get('key')}: arguments were redacted before storage")
            out.append(line)
            continue

        identity = json.dumps(
            {
                "node_id": node_id,
                "name": request.get("tool_name"),
                "version": request.get("tool_version"),
                "arguments": arguments,
            },
            sort_keys=True,
            default=str,
        )
        occurrence = seen.get(identity, 0)
        seen[identity] = occurrence + 1

        key = tool_call_key(
            node_id=node_id,
            tool_name=request.get("tool_name"),
            tool_version=request.get("tool_version"),
            arguments=arguments,
            occurrence=occurrence,
        )
        request["node_id"] = node_id
        request["occurrence"] = occurrence
        entry["request"] = request
        if key == entry.get("key"):
            unchanged += 1
        else:
            changed += 1
        entry["key"] = key
        out.append(json.dumps(entry, ensure_ascii=False))

    if write and changed:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed, unchanged, declined


def main(argv: list[str]) -> int:
    write = "--check" not in argv
    relabel = dict(
        arg.removeprefix("--relabel=").split("=", 1) for arg in argv if arg.startswith("--relabel=")
    )
    paths = [Path(arg) for arg in argv if not arg.startswith("--")]
    if not paths:
        print(__doc__)
        return 2

    problems = 0
    for path in paths:
        changed, unchanged, declined = rekey(path, write=write, relabel=relabel)
        verb = "rewrote" if write and changed else "would rewrite" if changed else "left"
        print(f"{path}: {verb} {changed} tool call(s), {unchanged} already current")
        for note in declined:
            problems += 1
            print(f"  declined {note}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
