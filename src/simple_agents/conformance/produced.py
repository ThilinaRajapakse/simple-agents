"""What the project's runs recorded producing, read across every run under ``runs/``.

A decision names what it became under ``produces`` and this is the other side of that join.
It reads every manifest rather than the newest one: a project with more than one pipeline runs
whichever it was asked for, so the newest run describes one of them and a decision about any
other would read as naming something no run produced.

**Every run is read, whatever its role and whatever answered its model.** A decision the
builder agreed to can be about a pipeline that is not the agent: one project's `dependency`
decision about its catalogue named the nodes and the constants of a `role="corpus"` pipeline,
and reading the agent's runs alone reported ten built names as never recorded. What separates
the agent's runs from a labelling pass, and a paid run from a scripted one, is a question for
the checks that measure the agent. This is a lookup, and a name is a name wherever it ran.

Each name carries the day of the newest run that recorded it, which is what separates a step
the project still has from one it removed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..envelope import runs
from ..records.manifest import DEFAULT_ROLE

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
    seen before the project last ran. ``roles`` says which roles recorded each name, so a
    report can say where a name came from rather than only that it exists.
    """

    nodes: dict[str, str] = field(default_factory=dict)
    tools: dict[str, str] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)
    roles: dict[str, set[str]] = field(default_factory=dict)
    """Every role that recorded each name. ``{"summarise": {"corpus"}}`` says the name is a
    node of a pipeline the project runs for itself rather than of the agent."""

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

    def where_from(self, name: str) -> str:
        """Which runs recorded ``name``, in the words a report prints.

        Empty where a run of the agent recorded it, which is what a reader assumes, and empty
        where no run recorded it at all. A name two roles recorded is the agent's::

            produced.where_from("summarise")     # 'recorded by corpus runs'
            produced.where_from("hunt")          # ''
        """
        held = self.roles.get(name, set())
        if not held or DEFAULT_ROLE in held:
            return ""
        return f"recorded by {', '.join(sorted(held))} runs"


def produced_across(run_dir: Path) -> Produced:
    """Read every manifest under ``run_dir`` for what the runs recorded producing.

    Every role is read, and each name records which of them carried it. A run made by a
    scripted client is read too: the names it recorded are the project's own node ids, tools
    and numbers, which is what this is a lookup over, and what its model answered has no
    bearing on them.
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
    roles: dict[str, set[str]] = {}
    for handle in runs(run_dir, nested=True, scripted=None):
        # A manifest nothing could parse is not a run this read, and FT-13 is what reports it.
        # Counting it would make `runs_read` a count of directories.
        if handle.unreadable is not None:
            continue
        manifest = handle.manifest
        read += 1
        day = str(manifest.get("started_at") or "")[:10]
        newest = max(newest, day)
        _note_each(nodes, manifest.get("nodes"), "node_id", day, roles, handle.role)
        _note_each(tools, manifest.get("tools"), "name", day, roles, handle.role)
        sliced = manifest.get("slice")
        if isinstance(sliced, dict) and isinstance(sliced.get("of"), str):
            found_slices.add(str(sliced["of"]))
        held = manifest.get("constants")
        if isinstance(held, list):
            saw_constants = True
            _note_each(constants, held, "name", day, roles, handle.role)
    return Produced(
        nodes=nodes,
        tools=tools,
        constants=constants,
        roles=roles,
        runs_read=read,
        newest_day=newest,
        constants_recorded=saw_constants,
        sliced_from=found_slices,
    )


def _note_each(
    held: dict[str, str],
    entries: object,
    key: str,
    day: str,
    roles: dict[str, set[str]],
    role: str,
) -> None:
    """Record every ``key`` in ``entries`` as seen on ``day``, by a run of ``role``.

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
            roles.setdefault(name, set()).add(role)
