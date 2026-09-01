"""The declared graph: edges on a node, and the checks over the whole shape.

A pipeline is a directed graph over the same three node kinds. Edges are declared on the node
as ``successors=``, and a node with more than one names a ``route=`` to choose between them. A
node that declares nothing hands its output to the next node in the list, which is what a
pipeline of one successor per node already means.

Everything here is static: the graph is known before the run starts, so an unreachable node, an
undeclared successor and an unbounded cycle are all refused at construction rather than found
part-way through a run.

``docs/pipeline.md`` §1 is this module's document.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Callable, Iterator, Mapping, Sequence

from .errors import CallerFacingError, ConfigurationError

__all__ = ["Loop", "RetryPolicy", "Join", "NodeFailure", "Graph", "CutEdge"]


@dataclass(frozen=True, slots=True)
class NodeFailure:
    """What travels along ``on_error`` when a node's last attempt has failed.

    The handler receives this in place of the output the failed node never produced, so it can
    answer with a fallback, record the failure, or raise something of its own::

        def fallback(failure: NodeFailure, ctx: NodeContext) -> Answer:
            return Answer(answer=Unknown(reason=f"{failure.node_id} failed: "
                                                f"{failure.error['message']}"))

    ``inputs`` is what the failed node received, so a handler can retry the work differently
    rather than re-deriving it. ``error`` is the object ``docs/trajectory-format.md`` §5.2
    defines, and ``attempts`` is how many executions were made before the failure was final.
    """

    node_id: str
    inputs: Any
    error: dict[str, Any]
    attempts: int

    def to_record(self) -> dict[str, Any]:
        """What the handler's ``node_execution`` record stores for its inputs."""
        return {
            "type": "node_failure",
            "node_id": self.node_id,
            "error": self.error,
            "attempts": self.attempts,
        }


@dataclass(frozen=True, slots=True)
class Loop:
    """The bound on a cycle, declared on the node that closes it.

    ``max_iterations`` counts executions of that node **per entry to the cycle**, so a counter
    reset when the cycle is entered from outside. ``then`` names the successor taken once the
    count is reached, and must be one of the node's successors from outside the cycle::

        critique = LLMNode(judge, output_schema=Verdict, successors=["draft", "publish"],
                           route=again_or_done, loop=Loop(max_iterations=3, then="publish"))

    A cycle with no ``Loop`` is refused at construction. No budget axis bounds one: ``max_steps``
    counts model calls and a cycle of ``Deterministic`` nodes makes none.
    """

    max_iterations: int
    then: str

    def __post_init__(self) -> None:
        if not isinstance(self.max_iterations, int) or self.max_iterations < 1:
            raise ConfigurationError(
                f"Loop(max_iterations={self.max_iterations!r}) needs a whole number of "
                f"iterations, at least 1. It counts executions of the node carrying it, per "
                f"entry to the cycle. Pass Loop(max_iterations=3, then='publish')."
            )
        if not str(self.then).strip():
            raise ConfigurationError(
                "Loop was constructed with no `then`. A bounded cycle needs somewhere to go "
                "once the count is reached, or reaching it would end the run with no result. "
                "Pass Loop(max_iterations=3, then='publish'), naming a successor of the node "
                "that carries this Loop and that lies outside the cycle."
            )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How many times a node is executed before its failure is final.

    ``attempts`` is the total number of executions, so ``attempts=1`` is the default behaviour
    of no retry. Every attempt emits its own ``node_execution`` record, and the failed ones
    carry ``termination: "error"``::

        node = LLMNode(build_prompt, output_schema=Answer,
                       retry=RetryPolicy(attempts=3, backoff_ms=200), on_error="fallback")

    Attempts share one node budget, so retrying does not multiply what a node may spend. A
    failure that survives the last attempt follows ``on_error=`` where the node declares one,
    and propagates where it does not.

    A cassette miss and an exhausted budget are never retried: neither is the node's failure.
    """

    attempts: int
    backoff_ms: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.attempts, int) or self.attempts < 1:
            raise ConfigurationError(
                f"RetryPolicy(attempts={self.attempts!r}) needs a whole number of executions, "
                f"at least 1. `attempts` counts every execution rather than the retries after "
                f"the first, so attempts=1 is no retry and attempts=3 is one execution plus "
                f"two more. Pass RetryPolicy(attempts=3)."
            )
        if not isinstance(self.backoff_ms, int) or self.backoff_ms < 0:
            raise ConfigurationError(
                f"RetryPolicy(backoff_ms={self.backoff_ms!r}) needs a whole number of "
                f"milliseconds to wait between attempts, or 0 to retry at once. Pass "
                f"RetryPolicy(attempts=3, backoff_ms=200)."
            )


class Join(Mapping[str, Any]):
    """What a node with more than one in-edge receives, keyed by the node each value came from.

    Every declared in-edge is a key, whether or not it fired, so the shape is a function of the
    graph and never of what ran. An edge that did not fire holds an :class:`Unknown` saying
    why::

        def report(inputs: Join, ctx: NodeContext) -> str:
            if "verify" in inputs.absent:
                return f"Unverified: {inputs['hunt']}"
            return f"Verified: {inputs['verify']}"

        inputs.fired      # ('hunt',)
        inputs.absent     # {'verify': Unknown(reason="'hunt' routed to 'report'")}

    ``absent`` is what says an edge did not fire. A node whose own answer was that the value is
    not there returns an ``Unknown`` and its edge fires, so testing the value with ``isinstance``
    reads that answer as a branch that never ran.

    A key that is not a declared in-edge raises rather than returning ``None``, because a
    misspelled node id would otherwise read as an edge that did not fire.
    """

    __slots__ = ("_edges", "_node_id", "_absent")

    def __init__(
        self,
        edges: Mapping[str, Any],
        *,
        node_id: str,
        absent: frozenset[str] = frozenset(),
    ) -> None:
        self._edges = dict(edges)
        self._node_id = node_id
        self._absent = frozenset(absent)

    def __getitem__(self, source: str) -> Any:
        try:
            return self._edges[source]
        except KeyError:
            raise CallerFacingError(
                f"Node {self._node_id!r} has no in-edge from {source!r}. Its declared in-edges "
                f"are {', '.join(repr(s) for s in self._edges)}. Read one of those, or declare "
                f"{source!r} as a predecessor by adding {self._node_id!r} to its successors."
            ) from None

    def __iter__(self) -> Iterator[str]:
        return iter(self._edges)

    def __len__(self) -> int:
        return len(self._edges)

    def __repr__(self) -> str:
        return f"Join({self._edges!r})"

    @property
    def node_id(self) -> str:
        """The node these edges arrive at."""
        return self._node_id

    @property
    def fired(self) -> tuple[str, ...]:
        """The in-edges that carried a value, in declaration order."""
        return tuple(k for k in self._edges if k not in self._absent)

    @property
    def absent(self) -> dict[str, Any]:
        """The in-edges that did not fire, each holding why."""
        return {k: v for k, v in self._edges.items() if k in self._absent}

    def to_record(self) -> dict[str, Any]:
        """What the ``node_execution`` record stores for a join's inputs.

        Tagged, so a reader tells a join from a node that returned a plain mapping. ``absent``
        names the edges that did not fire, which the values alone do not say.
        """
        return {
            "type": "join",
            "edges": dict(self._edges),
            "absent": sorted(self._absent),
        }


@dataclass(frozen=True, slots=True)
class CutEdge:
    """One declared edge whose other end is outside the pipeline holding it.

    Produced by :meth:`~simple_agents.pipeline.Pipeline.slice`, and by nothing else. A pipeline
    a builder writes has none.

    ``source`` and ``target`` are the ids the original graph declared, and ``kind`` is what
    declared it: ``successor``, ``on_error`` or ``loop_then``. Whichever end is outside, the
    edge stays declared, so a node that took a
    :class:`~simple_agents.graph.Join` still receives one and a route may still select an arm
    the slice does not hold.
    """

    source: str
    target: str
    kind: str = "successor"


@dataclass(frozen=True, slots=True)
class _Cycle:
    """One bounded cycle: the node that closes it, the edges back into it, and its members."""

    node_id: str
    loop: Loop
    back: tuple[str, ...]
    body: frozenset[str]


class Graph:
    """The declared edges of a pipeline, and what the shape has to satisfy.

    Built by :class:`~simple_agents.pipeline.Pipeline` from its nodes. Every refusal it raises
    names a node and the call that fixes it.
    """

    def __init__(
        self,
        nodes: Sequence[Any],
        concurrent_nodes: Sequence[Sequence[str]] | None = None,
        cut_edges: Sequence[CutEdge] = (),
    ) -> None:
        self.nodes = tuple(nodes)
        self.by_id = {node.node_id: node for node in self.nodes}
        self.order = {node.node_id: index for index, node in enumerate(self.nodes)}
        self.entry = self.nodes[0].node_id

        self.cut_edges = tuple(cut_edges)
        self.cut_in = _cut_by(self.cut_edges, lambda edge: edge.target, self.by_id, skip=self.entry)
        self.cut_out = _cut_by(self.cut_edges, lambda edge: edge.source, self.by_id)
        # An error edge is not one a route chooses between, in a slice as in a whole pipeline:
        # what selects it is a failure. Counting one here refused a slice whose kept node had
        # its handler outside, saying it declared two successors and no route.
        self._cut_routes = _cut_by(
            [edge for edge in self.cut_edges if edge.kind != "on_error"],
            lambda edge: edge.source,
            self.by_id,
        )

        self.successors = _successors_of(self.nodes)
        self._refuse_unknown_targets()
        self._refuse_undecided_routes()
        self.edges = _edges_of(self.nodes, self.successors, self.by_id)
        self.predecessors = _with_cut_sources(_invert(self.edges), self.cut_in)

        self.back_edges = self._back_edges()
        self.acyclic = {
            source: tuple(t for t in targets if (source, t) not in self.back_edges)
            for source, targets in self.edges.items()
        }
        # Reachability and the terminal node come before the Loop checks. A pipeline where
        # every node names a successor has no node to return from, and saying so is more use
        # than saying a `then` re-enters its cycle, which is the same fault seen from inside.
        self._refuse_unreachable()
        self.terminal = self._terminal()

        self.cycles = self._cycles()
        self._refuse_loop_closing_nothing()
        self._refuse_bad_then()
        # What each node reads, against what the edges into it carry. Last, because it is the
        # only check here that reads inside a node rather than at its edges.
        from .shapes import refuse_disagreements

        refuse_disagreements(self)

        self.concurrent_nodes = tuple(tuple(group) for group in (concurrent_nodes or ()))
        self._refuse_bad_groups()
        self._overlapping = {
            frozenset(pair)
            for group in self.concurrent_nodes
            for pair in combinations(sorted(set(group)), 2)
        }

    # -- what the scheduler reads ---------------------------------------------------------

    def may_overlap(self, one: str, other: str) -> bool:
        """Whether these two nodes may run at the same time.

        True when a ``concurrent_nodes`` group lists both. A node listed in several groups may
        overlap what each of them holds, and two nodes that never share a group never overlap.
        """
        return frozenset((one, other)) in self._overlapping

    def loop_at(self, node_id: str) -> _Cycle | None:
        """The cycle this node closes, or ``None`` where it closes none."""
        for cycle in self.cycles:
            if cycle.node_id == node_id:
                return cycle
        return None

    def cycle_around(self, node_id: str) -> _Cycle | None:
        """The innermost cycle this node is a member of, or ``None`` where it is in none.

        Innermost is the smallest body, which is what a nested loop's iteration counts.
        """
        holding = [cycle for cycle in self.cycles if node_id in cycle.body]
        if not holding:
            return None
        return min(holding, key=lambda cycle: (len(cycle.body), self.order[cycle.node_id]))

    def is_back_edge(self, source: str, target: str) -> bool:
        """Whether this edge closes a cycle rather than advancing through the graph."""
        return (source, target) in self.back_edges

    def joins(self, node_id: str) -> bool:
        """Whether this node takes input from more than one predecessor."""
        return len(self.predecessors.get(node_id, ())) > 1

    def in_edges(self, node_id: str) -> tuple[str, ...]:
        """The nodes whose output can reach this one, in declaration order.

        A slice's cut in-edge is here like any other, so a node that took a
        :class:`Join` in the pipeline it was sliced out of still receives one.
        """
        return self.predecessors.get(node_id, ())

    def routable(self, node_id: str) -> tuple[str, ...]:
        """The successors a route on this node may select, cut edges included.

        Wider than ``successors[node_id]``, which holds the ones inside this pipeline. A route
        that selects a cut edge ends the run there rather than being refused, because the route
        is the pipeline's own and a slice does not rewrite it.
        """
        return (*self.successors.get(node_id, ()), *self._cut_routes.get(node_id, ()))

    def is_cut(self, source: str, target: str) -> bool:
        """Whether this edge leads out of the pipeline, which only a slice produces."""
        return target in self.cut_out.get(source, ())

    def schema_of(self, node_id: str) -> Any:
        """What this node declared it produces, or ``None`` where it declared nothing.

        A resumed run rebuilds each value in flight from the schema of the node that produced
        it, so this is what makes a suspension carry no type names of its own.
        """
        return getattr(self.by_id.get(node_id), "output_schema", None)

    def to_mermaid(self) -> str:
        """The declared graph as a Mermaid flowchart.

        Renders wherever Markdown does, which is how the shape gets checked against what was
        meant::

            print(pipeline.to_mermaid())

        A routed edge is dashed, an error edge is labelled ``on error``, the edge that closes a
        cycle carries its iteration bound, and a node declaring ``suspend_before`` is labelled
        ``stops before``.
        """
        lines = ["flowchart TD"]
        for node in self.nodes:
            shape = _MERMAID_SHAPES.get(node.node_kind, ("[", "]"))
            stop = "<br/><i>stops before</i>" if getattr(node, "suspend_before", False) else ""
            lines.append(
                f"    {_safe(node.node_id)}{shape[0]}"
                f'"{node.node_id}<br/><i>{node.node_kind}</i>{stop}"{shape[1]}'
            )
        for node in self.nodes:
            source = node.node_id
            routed = len(self.successors[source]) > 1
            for target in self.successors[source]:
                label = ""
                cycle = self.loop_at(source)
                if cycle is not None and target in cycle.back:
                    label = f"|to {cycle.loop.max_iterations}x|"
                arrow = "-.->" if routed else "-->"
                lines.append(f"    {_safe(source)} {arrow}{label} {_safe(target)}")
            handler = getattr(node, "on_error", None)
            if handler:
                lines.append(f"    {_safe(source)} -.->|on error| {_safe(handler)}")
        return "\n".join(lines)

    # -- refusals -------------------------------------------------------------------------

    def _refuse_unknown_targets(self) -> None:
        for node in self.nodes:
            declared = getattr(node, "successors", None) or ()
            named = [(s, "successors") for s in declared]
            handler = getattr(node, "on_error", None)
            if handler:
                named.append((handler, "on_error"))
            loop = getattr(node, "loop", None)
            if loop is not None:
                named.append((loop.then, "loop's then"))
            for target, where in named:
                if target in self.by_id or target in self.cut_out.get(node.node_id, ()):
                    continue
                raise ConfigurationError(
                    f"Node {node.node_id!r} names {target!r} in its {where}, and this pipeline "
                    f"has no node with that id. Edges are declared by node_id, so a node has "
                    f"to be in the list before another can name it.\n"
                    f"This pipeline holds {', '.join(repr(i) for i in self.by_id)}. Add a node "
                    f"with node_id={target!r}, or correct the name."
                )

    def _refuse_bad_groups(self) -> None:
        for group in self.concurrent_nodes:
            unknown = [node_id for node_id in group if node_id not in self.by_id]
            if unknown:
                raise ConfigurationError(
                    f"concurrent_nodes names {', '.join(repr(u) for u in unknown)}, and this "
                    f"pipeline has no node with that id. A group says which of this "
                    f"pipeline's nodes may run at the same time.\n"
                    f"This pipeline holds {', '.join(repr(i) for i in self.by_id)}. Correct "
                    f"the name, or drop it from the group."
                )
            if len(set(group)) < 2:
                raise ConfigurationError(
                    f"concurrent_nodes holds a group of "
                    f"{len(set(group))} node{'' if len(set(group)) == 1 else 's'} "
                    f"({', '.join(repr(g) for g in group) or 'none'}), which says nothing: a "
                    f"group means the nodes in it may run at the same time as each other.\n"
                    f"List at least two, as concurrent_nodes=[['read_specs', "
                    f"'fetch_reviews']], or drop the group."
                )

    def _refuse_undecided_routes(self) -> None:
        for node in self.nodes:
            targets = self.routable(node.node_id)
            route = getattr(node, "route", None)
            if len(targets) > 1 and route is None:
                raise ConfigurationError(
                    f"Node {node.node_id!r} declares {len(targets)} successors "
                    f"({', '.join(repr(t) for t in targets)}) and no route, so nothing decides "
                    f"which of them its output goes to.\n"
                    f"Pass route=, a function taking the node's validated output and returning "
                    f"the id it goes to: route=lambda output, ctx: 'verify' if output.answer "
                    f"else 'report'. Returning a list of ids sends the output down every arm "
                    f"named, one after another; list those arms in the pipeline's "
                    f"concurrent_nodes to overlap them."
                )
            if route is not None and len(targets) < 2:
                raise ConfigurationError(
                    f"Node {node.node_id!r} declares a route and {len(targets)} successor"
                    f"{'' if len(targets) == 1 else 's'}, so the route has nothing to choose "
                    f"between and every output goes the same way.\n"
                    f"Declare the successors it chooses among with "
                    f"successors=['verify', 'report'], or drop route=."
                )

    def _refuse_loop_closing_nothing(self) -> None:
        for node in self.nodes:
            if getattr(node, "loop", None) is None:
                continue
            if any(source == node.node_id for source, _ in self.back_edges):
                continue
            raise ConfigurationError(
                f"Node {node.node_id!r} declares a Loop, and none of its successors leads back "
                f"to a node that has already run, so there is no cycle for the bound to apply "
                f"to.\n"
                f"A Loop belongs on the node that closes a cycle, which is the one whose "
                f"successors include an earlier node. Add that successor, or drop loop=."
            )

    def _refuse_bad_then(self) -> None:
        for cycle in self.cycles:
            then = cycle.loop.then
            targets = self.routable(cycle.node_id)
            if then not in targets:
                raise ConfigurationError(
                    f"Node {cycle.node_id!r} has loop=Loop(then={then!r}), and {then!r} is not "
                    f"one of its successors ({', '.join(repr(t) for t in targets)}). The run "
                    f"takes `then` once the iteration count is reached, so it has to be an "
                    f"edge this node declares.\n"
                    f"Add {then!r} to successors=, or name one of the successors it already "
                    f"has."
                )
            if then in cycle.body:
                raise ConfigurationError(
                    f"Node {cycle.node_id!r} has loop=Loop(then={then!r}), and {then!r} is "
                    f"inside the cycle it bounds ({', '.join(sorted(cycle.body))}). Taking it "
                    f"once the count is reached would re-enter the cycle the count exists to "
                    f"stop.\n"
                    f"Name a successor outside the cycle, which is where the run continues "
                    f"once the iterations are spent."
                )

    def _terminal(self) -> str:
        ends = [node.node_id for node in self.nodes if not self.edges[node.node_id]]
        if len(ends) == 1:
            return ends[0]
        if not ends:
            raise ConfigurationError(
                "Every node in this pipeline names a successor, so no node ends the run and "
                "there is nothing for run() to return. One node has to be the last one.\n"
                "Leave successors off the final node, which then takes the default of no "
                "successor, or pass successors=[] to say so explicitly."
            )
        raise ConfigurationError(
            f"This pipeline has {len(ends)} nodes with no successor "
            f"({', '.join(repr(e) for e in ends)}), so which of them produces the run's output "
            f"depends on which path ran. A run returns one value, from one node.\n"
            f"Give every branch a successor that leads to a single final node. A node that "
            f"takes input from more than one branch receives a Join, and an arm that did not "
            f"run is an Unknown on that key."
        )

    def _refuse_unreachable(self) -> None:
        reached = {self.entry} | _reachable(self.edges, self.entry)
        stranded = [node.node_id for node in self.nodes if node.node_id not in reached]
        if not stranded:
            return
        raise ConfigurationError(
            f"No path from {self.entry!r} reaches {', '.join(repr(s) for s in stranded)}, so "
            f"{'that node' if len(stranded) == 1 else 'those nodes'} can never run. Per-node "
            f"metrics would report it with a reach of zero on every evaluation.\n"
            f"Add it to the successors of a node that does run, or remove it from the "
            f"pipeline. Execution starts at {self.entry!r}, the first node in the list."
        )

    # -- cycles ---------------------------------------------------------------------------

    def _back_edges(self) -> frozenset[tuple[str, str]]:
        """The edges that close a cycle, and the refusal for a cycle nothing bounds.

        An edge is a back edge when it points at a node already on the path being walked, which
        is what makes it distinguishable from an edge that merely rejoins a later branch. A
        back edge leaving a node that declares no ``Loop`` is a cycle with no bound.
        """
        colour: dict[str, int] = {}
        path: list[str] = []
        found: set[tuple[str, str]] = set()

        def walk(source: str) -> None:
            colour[source] = 1
            path.append(source)
            for target in self.edges.get(source, ()):
                if colour.get(target, 0) == 1:
                    self._refuse_unbounded_cycle(source, target, path)
                    found.add((source, target))
                elif colour.get(target, 0) == 0:
                    walk(target)
            path.pop()
            colour[source] = 2

        walk(self.entry)
        return frozenset(found)

    def _refuse_unbounded_cycle(self, source: str, target: str, path: list[str]) -> None:
        if getattr(self.by_id[source], "loop", None) is not None:
            return
        members = path[path.index(target) :]
        raise ConfigurationError(
            f"This pipeline has a cycle with no bound on it: "
            f"{' -> '.join(members)} -> {target}. A run could go round it forever, and no "
            f"budget axis stops one: max_steps counts model calls and a cycle of Deterministic "
            f"nodes makes none, so a limit that looks set would stop nothing (FT-18).\n"
            f"Declare the bound on the node that closes the cycle. Pass "
            f"loop=Loop(max_iterations=3, then=...) to node {source!r}, where `then` names the "
            f"successor taken once the count is reached."
        )

    def _cycles(self) -> tuple[_Cycle, ...]:
        """One entry per node closing a cycle, with the members of the cycle it closes.

        A body is measured over the graph with every back edge removed, so an inner loop nested
        inside an outer one has the inner members and not the outer ones.
        """
        found: list[_Cycle] = []
        for node in self.nodes:
            loop = getattr(node, "loop", None)
            here = node.node_id
            back = tuple(t for s, t in sorted(self.back_edges) if s == here)
            if loop is None or not back:
                continue
            body = {here}
            for target in back:
                for member in {target} | _reachable(self.acyclic, target):
                    if here in _reachable(self.acyclic, member):
                        body.add(member)
            found.append(_Cycle(node_id=here, loop=loop, back=back, body=frozenset(body)))
        return tuple(found)


_MERMAID_SHAPES = {
    "deterministic": ("[", "]"),
    "llm": ("([", "])"),
    "agent": ("{{", "}}"),
}


def _safe(node_id: str) -> str:
    """A Mermaid node name, which may hold only word characters."""
    return "".join(c if c.isalnum() else "_" for c in node_id)


def _successors_of(nodes: Sequence[Any]) -> dict[str, tuple[str, ...]]:
    """Each node's routing successors, with the default of the next node in the list.

    ``successors=None`` is the default and means the following node, which is what a pipeline
    of one successor per node already means. ``successors=[]`` says the node ends the run.
    """
    resolved: dict[str, tuple[str, ...]] = {}
    for index, node in enumerate(nodes):
        declared = getattr(node, "successors", None)
        if declared is None:
            following = nodes[index + 1].node_id if index + 1 < len(nodes) else None
            resolved[node.node_id] = (following,) if following is not None else ()
        else:
            resolved[node.node_id] = tuple(dict.fromkeys(str(s) for s in declared))
    return resolved


def _edges_of(
    nodes: Sequence[Any],
    successors: Mapping[str, tuple[str, ...]],
    by_id: Mapping[str, Any],
) -> dict[str, tuple[str, ...]]:
    """Every declared edge inside this pipeline, including error edges.

    An ``on_error`` target is an edge like any other for reachability, cycle detection and the
    terminal check. It differs only in what selects it, which is a failure rather than a route.

    A handler outside the pipeline is left out: only a slice has one, it leads nowhere here,
    and the node it names has no entry to invert an edge into.
    """
    edges: dict[str, tuple[str, ...]] = {}
    for node in nodes:
        targets = list(successors[node.node_id])
        handler = getattr(node, "on_error", None)
        if handler and handler in by_id and handler not in targets:
            targets.append(handler)
        edges[node.node_id] = tuple(targets)
    return edges


def _cut_by(
    cut_edges: Sequence[CutEdge],
    end: Callable[[CutEdge], str],
    by_id: Mapping[str, Any],
    skip: str | None = None,
) -> dict[str, tuple[str, ...]]:
    """Cut edges grouped by whichever end is inside the pipeline, in declaration order.

    ``skip`` leaves out one node, which is how the entry keeps its in-edges cut without them
    reaching the graph: the entry receives what ``run`` was passed. They stay on the slice's
    own record, because what was cut is provenance whether or not it changes the shape.
    """
    found: dict[str, list[str]] = {}
    for edge in cut_edges:
        inside = end(edge)
        if inside not in by_id or inside == skip:
            continue
        other = edge.target if inside == edge.source else edge.source
        found.setdefault(inside, []).append(other)
    return {node_id: tuple(dict.fromkeys(others)) for node_id, others in found.items()}


def _with_cut_sources(
    predecessors: dict[str, tuple[str, ...]], cut_in: Mapping[str, tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    """Every in-edge each node declares, with a slice's cut ones after the ones it holds.

    A cut in-edge never fires, and its key is in the ``Join`` because the shape of a join
    follows the graph rather than what ran.
    """
    return {
        node_id: (*sources, *cut_in.get(node_id, ())) for node_id, sources in predecessors.items()
    }


def _invert(edges: Mapping[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    found: dict[str, list[str]] = {source: [] for source in edges}
    for source, targets in edges.items():
        for target in targets:
            found[target].append(source)
    return {node_id: tuple(sources) for node_id, sources in found.items()}


def _reachable(edges: Mapping[str, tuple[str, ...]], start: str) -> set[str]:
    """Every node reachable from ``start`` by one edge or more.

    ``start`` itself is in the result only when it lies on a cycle.
    """
    seen: set[str] = set()
    stack = list(edges.get(start, ()))
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        stack.extend(edges.get(node_id, ()))
    return seen


def reaching(edges: Mapping[str, tuple[str, ...]], target: str) -> set[str]:
    """Every node with a path to ``target`` by one edge or more.

    The mirror of :func:`_reachable`, and what a span's second bound is computed with:
    a span holds what its start reaches and what reaches its end.
    """
    backward: dict[str, list[str]] = {}
    for source, targets in edges.items():
        for one in targets:
            backward.setdefault(one, []).append(source)
    return _reachable({k: tuple(v) for k, v in backward.items()}, target)


def selected_by(
    route: Callable[[Any, Any], Any],
    output: Any,
    ctx: Any,
    *,
    node_id: str,
    declared: tuple[str, ...],
) -> tuple[str, ...]:
    """What a route chose, checked against what the node declared.

    A route returning an id the node does not declare, or returning nothing at all, is a
    caller-facing failure: the graph was checked at construction and this is the one edge
    decision that could not be.
    """
    chosen = route(output, ctx)
    if chosen is None:
        picked: tuple[str, ...] = ()
    elif isinstance(chosen, str):
        picked = (chosen,)
    else:
        picked = tuple(dict.fromkeys(str(c) for c in chosen))

    if not picked:
        raise CallerFacingError(
            f"The route on node {node_id!r} selected no successor, so its output goes nowhere "
            f"and the run has no path to its final node. A route returns at least one id.\n"
            f"Return one of {', '.join(repr(d) for d in declared)}. To end a branch early, "
            f"return the id of the node the run finishes at, rather than nothing."
        )
    unknown = [p for p in picked if p not in declared]
    if unknown:
        raise CallerFacingError(
            f"The route on node {node_id!r} selected {', '.join(repr(u) for u in unknown)}, "
            f"which {'is' if len(unknown) == 1 else 'are'} not among the successors it "
            f"declares ({', '.join(repr(d) for d in declared)}). A route chooses among the "
            f"declared edges; it does not add one.\n"
            f"Return one of the declared ids, or add the node to successors= on {node_id!r}."
        )
    return picked
