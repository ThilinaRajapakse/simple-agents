"""What the project's runs recorded producing, read across every run under ``runs/``.

A decision names what it became under ``produces`` and this is the other side of that join.
It reads every manifest rather than the newest one: a project with more than one pipeline runs
whichever it was asked for, so the newest run describes one of them and a decision about any
other would read as naming something no run produced.

Each name carries the day of the newest run that recorded it, which is what separates a step
the project still has from one it removed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..envelope import runs

__all__ = ["Produced", "produced_across"]

# What a name can be, and what the message says to do about each.
NODES = "node id"
TOOLS = "tool name"
CONSTANTS = "constant"


@dataclass(frozen=True, slots=True)
class Produced:
    """Every node id, tool name and constant the project's runs recorded, by day last seen.

    Each mapping is a name against the ``started_at`` day of the newest run carrying it.
    ``newest_day`` is the day of the newest run read, so a name whose day is earlier was last
    seen before the project last ran.
    """

    nodes: dict[str, str] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)
    runs_read: int = 0
    newest_day: str = ""
    constants_recorded: bool = False
    """Whether any run read carried a ``constants`` array. Manifests hold one from format
    ``0.33``, so a project whose runs all predate it has none and is told that rather than
    being read as a project that defines no constant."""

    sliced_from: set[str] = field(default_factory=set)
    """Every pipeline any run was a slice of, by that pipeline's ``graph_fingerprint``.

    A run made by ``Pipeline.slice`` records what it is a slice of, so this is how the report
    tells a project that scored a step on its own from one whose figures are all end to end.
    Empty for a project that has taken no slice, and for one whose runs predate manifest
    format ``0.39``."""

    def by_kind(self) -> tuple[tuple[str, dict[str, str]], ...]:
        """The three mappings with the word for what each holds, in the order a report reads."""
        return ((NODES, self.nodes), (TOOLS, self.tools), (CONSTANTS, self.constants))

    def every_name(self) -> set[str]:
        """Every name any run recorded, across all three kinds."""
        return set(self.nodes) | set(self.tools) | set(self.constants)

    def what_it_is(self, name: str) -> str | None:
        """The word for what ``name`` was recorded as, or ``None`` where no run recorded it."""
        for word, held in self.by_kind():
            if name in held:
                return word
        return None


def produced_across(run_dir: Path) -> Produced:
    """Read every manifest under ``run_dir`` for what the runs recorded producing.

    Runs whose ``role`` is not ``agent`` are left out: a labelling pass or a judge is work the
    project does for itself, and its nodes are not the agent's (`docs/run-envelope.md` §2.1).
    """
    if not run_dir.is_dir():
        return Produced()
    nodes: dict[str, str] = {}
    tools: dict[str, str] = {}
    constants: dict[str, str] = {}
    read = 0
    newest = ""
    saw_constants = False
    found_slices: set[str] = set()
    for handle in runs(run_dir, nested=True, role="agent"):
        # A manifest nothing could parse is not a run this read, and FT-13 is what reports it.
        # Counting it would make `runs_read` a count of directories.
        if handle.unreadable is not None:
            continue
        manifest = handle.manifest
        read += 1
        day = str(manifest.get("started_at") or "")[:10]
        newest = max(newest, day)
        _note_each(nodes, manifest.get("nodes"), "node_id", day)
        _note_each(tools, manifest.get("tools"), "name", day)
        sliced = manifest.get("slice")
        if isinstance(sliced, dict) and isinstance(sliced.get("of"), str):
            found_slices.add(str(sliced["of"]))
        held = manifest.get("constants")
        if isinstance(held, list):
            saw_constants = True
            _note_each(constants, held, "name", day)
    return Produced(
        nodes=nodes,
        tools=tools,
        constants=constants,
        runs_read=read,
        newest_day=newest,
        constants_recorded=saw_constants,
        sliced_from=found_slices,
    )


def _note_each(held: dict[str, str], entries: object, key: str, day: str) -> None:
    """Record every ``key`` in ``entries`` as seen on ``day``.

    Every shape is read defensively. A manifest is a file on disk that anything may have
    written, and a report that raised on one malformed entry would tell a project nothing
    about anything else it checked.
    """
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get(key)
        if isinstance(name, str) and name:
            held[name] = max(held.get(name, ""), day)
