"""What a node accepts, what it produces, and the disagreements between the two.

A node declares what it produces as ``output_schema``. What it accepts is read off its
function's first parameter, the same way a tool's JSON schema is read off its annotations::

    def verify(inputs: Notes, ctx: NodeContext) -> str:
        return f"Check this: {inputs.notes}"

Nothing has to be annotated. What is written down is read; what is not is not guessed at. A
disagreement is refused only where both sides are declared and no value could satisfy both, so
a pipeline that annotates nothing is refused nothing.

``docs/pipeline.md`` §3 is this module's document.
"""

from __future__ import annotations

import inspect
import types
from typing import Any, Mapping, Sequence, Union, get_args, get_origin, get_type_hints

from .graph import Graph, Join, NodeFailure

__all__ = ["accepted_by", "produced_by", "refutation", "type_name"]


def accepted_by(node: Any) -> Any:
    """The type a node's function declares for its first parameter, or ``None``.

    ``None`` where the parameter carries no annotation, where the annotation names something
    that cannot be resolved, or where the function has no readable signature, which is what a
    lambda and most callable objects have. A pipeline used as a node accepts what its entry
    node accepts::

        accepted_by(LLMNode(verify, output_schema=Answer))   # <class 'Notes'>
    """
    graph = getattr(node, "graph", None)
    if graph is not None:
        return accepted_by(graph.by_id[graph.entry])
    return _first_parameter(_function_of(node))


def produced_by(node: Any) -> Any:
    """The type a node declares it produces, or ``None``.

    ``output_schema`` where the node declares one, which an ``LLMNode`` and an ``AgentNode``
    always do. A ``Deterministic`` node that declares none falls back to its function's return
    annotation, which is the only other place it says what it returns. A pipeline used as a
    node produces what its terminal node produces.
    """
    graph = getattr(node, "graph", None)
    if graph is not None:
        return produced_by(graph.by_id[graph.terminal])
    declared = getattr(node, "output_schema", None)
    if declared is not None:
        return declared
    if getattr(node, "node_kind", None) != "deterministic":
        return None
    return _return_annotation(_function_of(node))


def refutation(expected: Any, arriving: Any) -> str | None:
    """Why no value of ``arriving`` can be what ``expected`` describes, or ``None``.

    ``None`` means the two were not shown to disagree, which covers everything undeclared as
    well as everything compatible. A disagreement is returned only where both sides reduce to
    a class and no value of one is a value of the other::

        refutation(Notes, Count)    # "declares Count and this node reads Notes"
        refutation(dict, Join)      # None: a Join is a Mapping and reads by key
        refutation(None, Count)     # None: this node declares nothing
    """
    if expected is None or arriving is None:
        return None
    if any(_may_accept(member, arriving) for member in _members(expected)):
        return None
    return f"{type_name(arriving)} where {type_name(expected)} is what the node reads"


def type_name(annotation: Any) -> str:
    """What a refusal calls a type. The declared name, so it matches the source."""
    if annotation is None:
        return "nothing"
    if _is_union(annotation):
        return " | ".join(type_name(arg) for arg in get_args(annotation))
    return getattr(annotation, "__name__", None) or str(annotation)


def digest_of(annotation: Any) -> str | None:
    """What the manifest records for a declared type, or ``None`` where none was declared.

    A pydantic model digests as its JSON schema, so the record says whether it is the same
    shape rather than whether it kept its name. Anything else digests as its name.
    """
    if annotation is None:
        return None
    from .pipeline.recording import _digest, _schema_digest

    if getattr(annotation, "model_json_schema", None) is not None:
        return _schema_digest(annotation)
    return _digest(type_name(annotation))


# -- what the graph says arrives ---------------------------------------------------------


def arriving_at(graph: Graph, node_id: str) -> tuple[Any, ...]:
    """Every type that can reach this node, with ``None`` for one nothing declares.

    The shape follows the declared edges. A node with more than one in-edge receives a
    :class:`~simple_agents.graph.Join`, a node fed by a fan-out receives a ``FanOutResult``,
    and a node reached by an error edge receives a
    :class:`~simple_agents.graph.NodeFailure`. The entry node receives what was passed to
    ``run``, including where a cycle returns to it. Its type is unknown to the pipeline, so
    it is one entry of ``None``.
    """
    incoming = graph.in_edges(node_id)
    found: list[Any] = [None] if node_id == graph.entry else []
    if not incoming:
        return tuple(found)
    if len(incoming) > 1:
        return (*found, Join)

    source = incoming[0]
    if source not in graph.by_id:
        # A slice's cut in-edge, whose source is outside this pipeline. It never fires, so
        # what arrives cannot be named and the node is left unchecked.
        return (*found, None)
    if getattr(graph.by_id[source], "on_error", None) == node_id:
        found.append(NodeFailure)
    if node_id in graph.successors[source]:
        found.append(_produced_over_edge(graph.by_id[source]))
    return tuple(found)


def _produced_over_edge(source: Any) -> Any:
    """What travels along a normal edge out of this node."""
    if getattr(source, "over", None) is not None:
        from .nodes import FanOutResult

        return FanOutResult
    return produced_by(source)


# -- the refusals ------------------------------------------------------------------------


def refuse_disagreements(graph: Graph) -> None:
    """Refuse a node that reads a type nothing reaching it can be.

    Called once per pipeline, at construction. Every refusal names the node, what it reads,
    what reaches it, and the two ways to fix it.
    """
    from .errors import ConfigurationError

    for node in graph.nodes:
        _refuse_fan_out_over_a_shape_it_cannot_read(graph, node)
        expected = accepted_by(node)
        arriving = arriving_at(graph, node.node_id)
        if expected is None or not arriving:
            continue
        # Refused only where nothing that can arrive is what the node reads. One arriving
        # type the graph cannot name is enough to leave the question open.
        if any(refutation(expected, one) is None for one in arriving):
            continue
        sources = ", ".join(repr(s) for s in graph.in_edges(node.node_id))
        raise ConfigurationError(
            f"Node {node.node_id!r} reads its input as {type_name(expected)}, and what "
            f"reaches it from {sources} is {_join_names(arriving)}. Every run would call this "
            f"node with a value it does not describe.\n"
            f"Annotate the first parameter with what arrives, or change what the node before "
            f"it produces. A node receives what the node before it returned, and a node that "
            f"needs a value produced further back has to be handed it."
        )


def _refuse_fan_out_over_a_shape_it_cannot_read(graph: Graph, node: Any) -> None:
    """Refuse a fan-out node that cannot reach the key it fans out over.

    ``over=`` reads a key off the value the node received, so that value has to be a plain
    dict. A node with more than one in-edge receives a ``Join``, and a node whose predecessor
    declares an output schema receives a model. Neither is a dict, so the run would raise on
    every rollout.
    """
    from .errors import ConfigurationError

    over = getattr(node, "over", None)
    if over is None:
        return
    incoming = graph.in_edges(node.node_id)
    if len(incoming) > 1:
        raise ConfigurationError(
            f"Node {node.node_id!r} fans out over {over!r} and takes input from "
            f"{len(incoming)} nodes ({', '.join(repr(s) for s in incoming)}), so it receives a "
            f"Join rather than a dict. `over` reads its key off a plain dict, so every rollout "
            f"would fail there.\n"
            f"Put a node between them that reads the Join and returns a dict carrying "
            f"{over!r}, or give this node one in-edge."
        )
    arriving = arriving_at(graph, node.node_id)
    for one in arriving or ():
        if one is None or _may_accept(dict, one):
            continue
        raise ConfigurationError(
            f"Node {node.node_id!r} fans out over {over!r}, and node {incoming[0]!r} declares "
            f"it produces {type_name(one)}. `over` reads its key off a plain dict, so every "
            f"rollout would fail there.\n"
            f"Have {incoming[0]!r} return a dict carrying {over!r}, or drop over= and make one "
            f"call over the whole value."
        )


def refuse_value_arriving(node: Any, value: Any, source: str | None) -> None:
    """Refuse a value that is not what the node reads, at the point it is handed over.

    What a node accepts is checked against the value itself as well as against the graph,
    because the node before it may declare nothing while still producing something this node
    cannot read.
    """
    from .errors import CallerFacingError

    expected = accepted_by(node)
    if expected is None:
        return
    if refutation(expected, type(value)) is None:
        return
    came_from = f"from node {source!r}" if source else "as the run's inputs"
    raise CallerFacingError(
        f"Node {node.node_id!r} reads its input as {type_name(expected)}, and what arrived "
        f"{came_from} is {type_name(type(value))}.\n"
        f"Annotate the first parameter with what arrives, or change what produced it. A node "
        f"receives what the node before it returned, and a node that needs a value produced "
        f"further back has to be handed it."
    )


# -- reading a signature -------------------------------------------------------------------


def _function_of(node: Any) -> Any:
    """The function a node was built from: its own for a `Deterministic`, else its prompt."""
    return getattr(node, "fn", None) or getattr(node, "prompt", None)


def _first_parameter(fn: Any) -> Any:
    if fn is None:
        return None
    try:
        parameters = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return None
    if not parameters or parameters[0].annotation is inspect.Parameter.empty:
        return None
    return _hints(fn).get(parameters[0].name)


def _return_annotation(fn: Any) -> Any:
    if fn is None:
        return None
    try:
        if inspect.signature(fn).return_annotation is inspect.Signature.empty:
            return None
    except (TypeError, ValueError):
        return None
    return _hints(fn).get("return")


def _hints(fn: Any) -> Mapping[str, Any]:
    """Resolved annotations, or nothing where a name in one does not resolve.

    ``from __future__ import annotations`` makes every annotation a string, so they are
    resolved against the function's own module. One that names something unimportable is read
    as undeclared rather than raised on, since it is a fact about the caller's imports.
    """
    try:
        return get_type_hints(fn)
    except Exception:
        return {}


# -- what can be what ------------------------------------------------------------------------


def _is_union(annotation: Any) -> bool:
    """Whether this is a union, written either way. ``A | B`` and ``Union[A, B]`` differ in
    what ``get_origin`` reports."""
    return get_origin(annotation) in (Union, types.UnionType)


def _members(annotation: Any) -> tuple[Any, ...]:
    """A union's members, or the annotation itself."""
    if _is_union(annotation):
        return get_args(annotation)
    return (annotation,)


def _may_accept(expected: Any, arriving: Any) -> bool:
    """Whether a value of ``arriving`` could be what ``expected`` describes.

    True wherever the two were not shown to disagree, so anything this cannot reduce to a pair
    of classes passes.
    """
    if expected is Any or arriving is Any or expected is object:
        return True
    if expected is None or arriving is None:
        return True
    # A union on the arriving side holds values this node could read, so it is not refuted.
    members = _members(arriving)
    if len(members) > 1:
        return any(_may_accept(expected, member) for member in members)
    expected_class = _as_class(expected)
    arriving_class = _as_class(arriving)
    if expected_class is None or arriving_class is None:
        return True
    if issubclass(arriving_class, expected_class):
        return True
    # A Join reads by key like the dict a node would otherwise have received, so a node
    # annotated `dict` at a join is reading it the way the class supports.
    return expected_class is dict and issubclass(arriving_class, Mapping)


def _as_class(annotation: Any) -> type | None:
    """The class an annotation reduces to, or ``None`` where it reduces to none."""
    if _is_union(annotation):
        return None
    origin = get_origin(annotation)
    if origin is not None:
        return origin if isinstance(origin, type) else None
    return annotation if isinstance(annotation, type) else None


def _join_names(arriving: Sequence[Any]) -> str:
    return " or ".join(type_name(one) for one in arriving)
