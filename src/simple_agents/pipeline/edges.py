"""The executor's working state: frames, edges, and what each in-edge resolved to."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence
from ..budget import Spend
from ..errors import LeftTheSlice
from ..graph import Graph, Join, NodeFailure
from ..nodes import Execution
from ..schema import Unknown
from ..records.suspension import ValueCodec


@dataclass(frozen=True, slots=True)
class _Attempted:
    """One execution of a node that returned, and the record it will be written under."""

    execution: Execution
    outputs: Any
    termination: str | None


@dataclass(frozen=True, slots=True)
class _Edge:
    """One in-edge's resolution: it carried a value, or it did not fire and this is why."""

    fired: bool
    value: Any = None
    reason: str | None = None


@dataclass(slots=True)
class _Frame:
    """One pipeline's place in the walk, and everything needed to re-enter it.

    ``in_progress`` names the nodes that were executing when the run stopped: the walk runs
    those again rather than choosing which is ready, so a resumed node is not counted as a
    second entry to its loop. There is more than one where arms that were overlapping stopped
    together.

    ``node_state`` is what each of them held, keyed by node, and ``below`` is the stack of
    frames each stopped inside, for a node that had delegated. A suspended run is therefore a
    tree rather than a stack: one frame per pipeline level, and a level where two arms stopped
    branches into two.
    """

    prefix: str
    edges: _EdgeState
    produced: dict[str, Any]
    opened: Spend
    in_progress: list[str] = field(default_factory=list)
    # The record every node in this walk is written inside, which is the `delegation` for a
    # delegated pipeline and `None` for one the run reached along an edge.
    parent_id: str | None = None
    node_state: dict[str, dict[str, Any]] = field(default_factory=dict)
    below: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def snapshot(self, codec: ValueCodec) -> dict[str, Any]:
        return {
            "prefix": self.prefix,
            "edges": self.edges.snapshot(codec),
            "produced": {
                node_id: codec.encode(value, source=node_id)
                for node_id, value in self.produced.items()
            },
            "opened": self.opened.to_record(),
            "in_progress": list(self.in_progress),
            "node_state": self.node_state,
            "below": self.below,
        }

    @classmethod
    def restored(cls, graph: Graph, snapshot: dict[str, Any], codec: ValueCodec) -> _Frame:
        return cls(
            prefix=snapshot["prefix"],
            edges=_EdgeState.restored(graph, snapshot["edges"], codec),
            produced={
                node_id: codec.decode(value, source=node_id)
                for node_id, value in snapshot["produced"].items()
            },
            opened=Spend.from_record(snapshot["opened"]),
            in_progress=list(snapshot["in_progress"]),
            node_state=dict(snapshot.get("node_state") or {}),
            below={k: list(v) for k, v in (snapshot.get("below") or {}).items()},
        )


class _EdgeState:
    """What each edge has resolved to, which nodes have run, and where a cycle has got to.

    Held for one run. A node returning ``Unknown`` is a node that answered, so whether an edge
    fired is tracked apart from what it carried; testing the value would read a reported
    absence as an edge that never ran.
    """

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.resolved: dict[tuple[str, str], _Edge] = {}
        self.visits: dict[str, int] = {}
        self.done: set[str] = set()
        self.left_the_slice: LeftTheSlice | None = None
        """The boundary this run reached, where it reached one. Only a slice has any."""
        # A slice's cut in-edge resolves before anything runs. It never fires, so the node it
        # arrives at is ready as soon as the edges the slice does hold have resolved, and the
        # `Join` it receives carries the arm as absent with this as the reason.
        for target, sources in graph.cut_in.items():
            for source in sources:
                self.resolved[(source, target)] = _Edge(
                    fired=False,
                    reason=f"{source!r} is outside this slice of the pipeline",
                )

    # -- crossing a suspend point ---------------------------------------------------------

    def snapshot(self, codec: ValueCodec) -> dict[str, Any]:
        """What this state is, as plain data a resumed run rebuilds it from.

        An edge is one entry naming its source and target rather than a joined key, since a
        node id may contain any character a delimiter could use. Each value is encoded against
        the schema its source node declared.
        """
        return {
            "resolved": [
                {
                    "source": source,
                    "target": target,
                    "fired": edge.fired,
                    "value": codec.encode(edge.value, source=source) if edge.fired else None,
                    "reason": edge.reason,
                }
                for (source, target), edge in self.resolved.items()
            ],
            "visits": dict(self.visits),
            "done": sorted(self.done),
        }

    @classmethod
    def restored(cls, graph: Graph, snapshot: dict[str, Any], codec: ValueCodec) -> _EdgeState:
        """A state rebuilt from :meth:`snapshot`, against the graph it was taken from."""
        state = cls(graph)
        state.resolved = {
            (edge["source"], edge["target"]): _Edge(
                fired=edge["fired"],
                value=codec.decode(edge["value"], source=edge["source"]) if edge["fired"] else None,
                reason=edge["reason"],
            )
            for edge in snapshot["resolved"]
        }
        state.visits = dict(snapshot["visits"])
        state.done = set(snapshot["done"])
        return state

    # -- what the walk asks ---------------------------------------------------------------

    def ready(self, node_id: str) -> bool:
        """Whether every edge into this node has resolved.

        An edge that closes a cycle is left out. Counting it would deadlock the first entry to
        the cycle, since it cannot resolve until the cycle has been round once.
        """
        return all(
            (source, node_id) in self.resolved
            for source in self.graph.in_edges(node_id)
            if not self.graph.is_back_edge(source, node_id)
        )

    def all_absent(self, node_id: str) -> bool:
        """Whether nothing reached this node.

        The first node receives the run's own inputs and always runs, including where it is
        also the node a cycle returns to and so has an in-edge that has not fired yet.
        """
        if node_id == self.graph.entry:
            return False
        incoming = self.graph.in_edges(node_id)
        return bool(incoming) and not any(self.edge(s, node_id).fired for s in incoming)

    def source_of(self, node_id: str) -> str | None:
        """Which node's output this one is about to receive, where exactly one carried it.

        ``None`` for the entry node reading the run's inputs, and for a node receiving a
        :class:`Join`, whose value names its own sources.
        """
        fired = [s for s in self.graph.in_edges(node_id) if self.edge(s, node_id).fired]
        return fired[0] if len(fired) == 1 else None

    def edge(self, source: str, target: str) -> _Edge:
        return self.resolved.get(
            (source, target),
            _Edge(fired=False, reason=f"{source!r} did not run"),
        )

    def inputs_for(self, node_id: str, run_inputs: Any) -> Any:
        """What this node receives.

        The shape follows the declared graph and never what ran: a node with one in-edge gets
        that value, and a node with more than one always gets a :class:`Join` carrying a key
        per declared in-edge.

        The entry node receives what was passed to ``run``. Where a cycle returns to it, every
        edge into it closes that cycle, so it receives the run's inputs on its first execution
        and what the cycle carried on the ones after.
        """
        incoming = self.graph.in_edges(node_id)
        if not incoming:
            return run_inputs
        if node_id == self.graph.entry and not any(
            self.edge(source, node_id).fired for source in incoming
        ):
            return run_inputs
        if len(incoming) == 1:
            edge = self.edge(incoming[0], node_id)
            return edge.value if edge.fired else Unknown(reason=edge.reason)
        return Join(
            {
                source: (
                    self.edge(source, node_id).value
                    if self.edge(source, node_id).fired
                    else Unknown(reason=self.edge(source, node_id).reason)
                )
                for source in incoming
            },
            node_id=node_id,
            absent=frozenset(s for s in incoming if not self.edge(s, node_id).fired),
        )

    def loop_record(self, node_id: str) -> dict[str, Any] | None:
        """The ``loop`` object for this node's record, or ``None`` for a node in no cycle."""
        cycle = self.graph.cycle_around(node_id)
        if cycle is None:
            return None
        closing = self.graph.loop_at(node_id)
        return {
            "node_id": cycle.node_id,
            "iteration": self.visits.get(node_id, 0),
            "max_iterations": cycle.loop.max_iterations,
            "exhausted": bool(
                closing is not None and self.visits.get(node_id, 0) >= closing.loop.max_iterations
            ),
        }

    # -- what the walk records ------------------------------------------------------------

    def enter(self, node_id: str) -> int:
        """Note that this node is about to run, and return which iteration it is."""
        self.visits[node_id] = self.visits.get(node_id, 0) + 1
        self.done.add(node_id)
        return self.visits[node_id]

    def unenter(self, node_id: str) -> None:
        """Take back an entry for a node that was drained before it began.

        Nothing it would have done was done, so the walk chooses it again and its loop count
        is what it would have been had the batch never held it.
        """
        left = self.visits.get(node_id, 1) - 1
        if left <= 0:
            self.visits.pop(node_id, None)
            self.done.discard(node_id)
        else:
            self.visits[node_id] = left

    def advance(self, node_id: str, value: Any, chosen: tuple[str, ...]) -> None:
        """Resolve every edge out of this node, and reopen a cycle its route went back into."""
        taken = ", ".join(repr(c) for c in chosen)
        for target in self.graph.successors[node_id]:
            self.resolved[(node_id, target)] = (
                _Edge(fired=True, value=value)
                if target in chosen
                else _Edge(fired=False, reason=f"{node_id!r} routed to {taken}")
            )
        handler = getattr(self.graph.by_id[node_id], "on_error", None)
        if handler and handler not in self.graph.successors[node_id]:
            self.resolved[(node_id, handler)] = _Edge(
                fired=False, reason=f"{node_id!r} did not fail"
            )
        self._note_entries(node_id, chosen)

    def note_the_boundary(
        self, node_id: str, chosen: Sequence[str], *, kind: str = "successor"
    ) -> bool:
        """Whether this node's output went to an edge the slice does not hold, and note it.

        A slice keeps such an edge declared, so a route selects it exactly as it would in the
        pipeline the slice came from. Nothing runs on the other side, so the walk ends and the
        run says it reached the boundary rather than reporting no path to its final node.
        """
        for target in chosen:
            if not self.graph.is_cut(node_id, target):
                continue
            if self.left_the_slice is None:
                self.left_the_slice = LeftTheSlice(node_id=node_id, target=target, kind=kind)
            return True
        return False

    def divert(self, node_id: str, handler: str, failure: NodeFailure) -> None:
        """Send a failed node's output along its error edge, and nowhere else."""
        for target in self.graph.successors[node_id]:
            self.resolved[(node_id, target)] = _Edge(
                fired=False, reason=f"{node_id!r} failed after {failure.attempts} attempt(s)"
            )
        self.resolved[(node_id, handler)] = _Edge(fired=True, value=failure)

    def resolve_all_absent(self, node_id: str, reason: str) -> None:
        """Resolve every edge out of a node that did not run."""
        for target in self.graph.edges[node_id]:
            self.resolved[(node_id, target)] = _Edge(fired=False, reason=reason)

    def _note_entries(self, node_id: str, chosen: tuple[str, ...]) -> None:
        for target in chosen:
            cycle = self.graph.cycle_around(target)
            if cycle is not None and node_id not in cycle.body:
                # The cycle was entered from outside it, so its count starts again. This is
                # what makes a loop bounded at 3 inside one bounded at 10 get three each time.
                for member in cycle.body:
                    self.visits[member] = 0
            if self.graph.is_back_edge(node_id, target):
                self._reopen(node_id, target)

    def _reopen(self, node_id: str, target: str) -> None:
        """Clear the cycle so its nodes run again, keeping the edge that sent the run back."""
        cycle = self.graph.loop_at(node_id)
        if cycle is None:
            return
        self.done -= cycle.body
        for edge in list(self.resolved):
            if edge[0] in cycle.body and edge != (node_id, target):
                del self.resolved[edge]
