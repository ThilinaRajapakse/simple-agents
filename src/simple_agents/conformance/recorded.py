"""The graph a run recorded, read one way.

A manifest and a results file's ``config`` block both carry the pipeline that ran as ``nodes``
and ``containers`` arrays. Every check that reads them builds on :class:`RecordedNodes`, so
what tolerates a missing section or a malformed entry is decided once: an absent array reads
as empty, and an entry that is not a mapping is skipped.
"""

from __future__ import annotations

from typing import Any, Mapping

NESTING_READ = 8
"""How far into pipelines used as nodes the answering-node walk descends.

A bound rather than a rule: a graph deeper than this is read as ending at that depth, and the
check then reads more nodes than it has to rather than fewer.
"""


def calls_a_model(entry: Any) -> bool:
    """Whether a node entry is one whose execution can make a model call."""
    return isinstance(entry, dict) and entry.get("node_kind") in ("llm", "agent")


class RecordedNodes:
    """The node entries one manifest or ``config`` block recorded.

    ::

        recorded = RecordedNodes(manifest)
        recorded.model_calling()   # entries whose execution can call a model
        recorded.planned()         # ids still declared NotBuilt
        recorded.last_units()      # what produces the run's output

    ``declared`` is whether the source held a ``nodes`` array at all, which is how a file a
    project wrote by hand reads differently from one holding an empty pipeline.
    """

    def __init__(self, config: Any) -> None:
        raw: Mapping[str, Any] = config if isinstance(config, Mapping) else {}
        nodes_raw = raw.get("nodes")
        self.declared = isinstance(nodes_raw, list)
        self.nodes: list[dict[str, Any]] = [
            entry for entry in (nodes_raw if self.declared else ()) if isinstance(entry, dict)
        ]
        self.containers: list[dict[str, Any]] = [
            entry for entry in raw.get("containers") or [] if isinstance(entry, dict)
        ]
        self.entries: dict[str, dict[str, Any]] = {
            entry["node_id"]: entry
            for entry in [*self.nodes, *self.containers]
            if entry.get("node_id")
        }
        self.children: dict[str, list[str]] = {
            entry["node_id"]: list(entry.get("nodes") or ())
            for entry in self.containers
            if entry.get("node_id")
        }

    def model_calling(self) -> list[dict[str, Any]]:
        """The node entries whose execution can make a model call."""
        return [entry for entry in self.nodes if calls_a_model(entry)]

    def planned(self) -> list[str]:
        """The ids of steps recorded as declared and never built."""
        return [str(entry.get("node_id")) for entry in self.nodes if entry.get("planned")]

    def top_level(self) -> list[str]:
        """The ids declared outside any container."""
        return [node_id for node_id in self.entries if "." not in node_id]

    def last_units(self) -> list[str]:
        """The units the run's output comes out of, innermost first.

        A pipeline used as a node is descended into, since what produces its output is a node
        inside it, bounded at :data:`NESTING_READ`. The last declared unit stands in where
        every one of them points somewhere, which a loop back to the start produces.
        """
        return self._last_units(self.top_level(), 0)

    def _last_units(self, among: list[str], depth: int) -> list[str]:
        last = [
            node_id for node_id in among if not self.entries.get(node_id, {}).get("successors")
        ] or among[-1:]
        found: list[str] = []
        for node_id in last:
            if node_id in self.children and depth < NESTING_READ:
                found.extend(self._last_units(self.children[node_id], depth + 1))
            else:
                found.append(node_id)
        return found

    def feeding(self, reached: list[str]) -> list[dict[str, Any]]:
        """The model-calling entries pointing at ``reached``.

        What decides an answer a ``Deterministic`` node assembled is whatever put the words in
        it, and that node has no declaration of its own to read.
        """
        return [
            entry
            for entry in self.entries.values()
            if calls_a_model(entry) and set(entry.get("successors") or ()) & set(reached)
        ]
