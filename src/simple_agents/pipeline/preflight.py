"""What a run refuses before it starts, and what it warns is being cut."""

from __future__ import annotations

import warnings
from typing import Any, Mapping, Sequence

from ..context import accepts_reasoning_sink
from ..cost import DeviceBasis, basis_for, currencies_in
from ..envelope import RunEnvelope
from ..errors import ConfigurationError, SimpleAgentsWarning
from ..graph import Join, _reachable
from ..memory import refuse_unreachable
from ..models import ModelClient
from ..tools import HostPolicy, Memory
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Pipeline


def _refuse_an_unknown_slice_node(value: str, where: str, held: list[str]) -> None:
    """Refuse a node id ``slice()`` was given that the pipeline does not hold.

    A dotted id names a node inside a pipeline used as a node here, which is a different
    graph, so the fix is to slice that one.
    """
    inner = value.split(".")[0]
    raise ConfigurationError(
        f"slice() was given {where}={value!r}, and this pipeline holds no node with that id. "
        f"It holds {', '.join(repr(i) for i in held)}.\n"
        + (
            f"{value!r} is a node inside {inner!r}, a pipeline used as a node here. A slice is "
            f"taken over one pipeline's own nodes, so slice {inner!r} itself and put the "
            f"result where it goes."
            if "." in value
            else "Correct the name, or pass one of the ids above."
        )
    )


def _refuse_delegation_cycle(pipeline: Pipeline, prefix: str, seen: tuple[int, ...]) -> None:
    """Refuse a pipeline that can reach itself, before the walk recurses into it forever.

    A pipeline used as a node cannot hold itself, since it does not exist when its nodes are
    constructed. A delegation can be attached to a node afterwards, so this is reachable.
    """
    if id(pipeline) not in seen:
        return
    raise ConfigurationError(
        f"The pipeline reached at {prefix.rstrip('.')!r} delegates, directly or through "
        f"another pipeline, to itself. Every node id is a path through the declared "
        f"structure, so a pipeline that contains itself has no finite set of node ids and "
        f"nothing could bound the run.\n"
        f"Break the cycle: a step that decides whether to go round again is a route or a "
        f"Loop inside one pipeline, and a subtask handed onward is a second pipeline."
    )


def _warn_declarations_the_run_cuts(
    pipeline: Pipeline, concurrency: int, *, replaying: bool
) -> None:
    """Say which nodes declared more overlap than the run permits.

    ``concurrent_items`` is what a node declares and ``Pipeline.run(concurrency=)`` is what
    the run permits, and the effective width is the smaller of the two. A node declaring more
    than the run allows is not an error and not a refusal: the run is correct, and slower than
    the node asked for, which reads as the model being slow.

    Silent while replaying, on the same reasoning ``_pace_clients`` is: a cassette serves the
    calls, so nothing is waiting on a backend.
    """
    if replaying:
        return
    cut = [
        (node_id, node.concurrent_items)
        for node_id, node in pipeline.declared_nodes()
        if (getattr(node, "concurrent_items", None) or 0) > concurrency
    ]
    if not cut:
        return
    named = ", ".join(f"{node_id} declares {items}" for node_id, items in cut)
    warnings.warn(
        f"This run permits {concurrency} call(s) in flight and {named}, so those items run "
        f"{concurrency} at a time. Pass Pipeline.run(concurrency={max(i for _, i in cut)}) "
        f"to give the declarations room, or lower them to what the run permits.",
        SimpleAgentsWarning,
        stacklevel=3,
    )


def _refuse_a_bad_slice(
    pipeline: "Pipeline",
    *,
    start: str | None,
    end: str | None,
    nodes: Sequence[str] | None,
    held: list[str],
) -> None:
    """What is wrong before any node set is computed: the arguments themselves."""
    if nodes is not None and (start is not None or end is not None):
        raise ConfigurationError(
            "slice() was given nodes= as well as start= or end=, and they are two ways of "
            "saying the same thing. start= and end= compute the set from the graph; "
            "nodes= names it.\n"
            "Pass one: pipeline.slice(start='judge'), or "
            "pipeline.slice(nodes=['select', 'judge'])."
        )
    if nodes is None and start is None and end is None:
        raise ConfigurationError(
            f"slice() was given no bound, so it would return this whole pipeline and say "
            f"nothing. A slice is part of a pipeline evaluated on its own.\n"
            f"Pass start= for the tail from a node, end= for the head up to one, both for "
            f"the span between them, or nodes= to name the set. This pipeline holds "
            f"{', '.join(repr(i) for i in held)}."
        )
    if nodes is not None and not list(nodes):
        raise ConfigurationError(
            f"slice() was given an empty nodes=, so the slice would hold nothing. A "
            f"pipeline needs at least one node to run.\n"
            f"Name the nodes the slice holds: "
            f"pipeline.slice(nodes=[{held[0]!r}]). This pipeline holds "
            f"{', '.join(repr(i) for i in held)}."
        )
    for value, where in (
        (start, "start"),
        (end, "end"),
        *((one, "nodes") for one in (nodes or ())),
    ):
        if value is not None and value not in held:
            _refuse_an_unknown_slice_node(str(value), where, held)


def _refuse_a_disconnected_slice(
    pipeline: "Pipeline", kept: list[str], *, start: str | None, end: str | None, named: bool
) -> None:
    """Refuse a set that is not one connected piece with one node ending it.

    Refused here rather than by :class:`~simple_agents.graph.Graph`, whose messages for
    these two shapes name the node to add, and the node to add is one the slice leaves out.
    """
    if not kept:
        bounds = ", ".join(
            f"{where}={value!r}"
            for where, value in (("start", start), ("end", end))
            if value is not None
        )
        raise ConfigurationError(
            f"No node of this pipeline is both reachable from and leads to {bounds}, so "
            f"the slice would hold nothing.\n"
            f"A span holds what start reaches and what reaches end, so end has to lie "
            f"downstream of start. Check the direction, or drop one of the two."
        )
    inside = set(kept)
    within = {
        node_id: tuple(t for t in pipeline.graph.edges[node_id] if t in inside) for node_id in kept
    }
    entry = kept[0]
    stranded = [n for n in kept[1:] if n not in _reachable(within, entry)]
    if stranded:
        raise ConfigurationError(
            f"This slice holds {', '.join(repr(n) for n in kept)}, and no path inside it "
            f"reaches {', '.join(repr(n) for n in stranded)} from {entry!r}, the first of "
            f"them. A pipeline runs from its first node, so a node nothing reaches can "
            f"never run.\n"
            + (
                "Name the nodes between them as well, or take one slice per piece."
                if named
                else "The bounds given select two pieces of the graph. Name the set "
                "instead: pipeline.slice(nodes=[...])."
            )
        )
    ends = [n for n in kept if not within[n]]
    if not ends:
        leaving = sorted({t for n in kept for t in pipeline.graph.edges[n] if t not in inside})
        raise ConfigurationError(
            f"Every node in this slice leads to another node in it, so none of them ends "
            f"it and a run would have nothing to return. Each way out of "
            f"{', '.join(repr(n) for n in kept)} goes to "
            f"{', '.join(repr(one) for one in leaving) or 'nothing'}, which the slice does "
            f"not hold.\n"
            f"Hold the node the run continues to as well: "
            f"pipeline.slice(nodes=[{', '.join(repr(n) for n in kept)}, "
            f"{leaving[0]!r}])."
            if leaving
            else "Every node in this slice leads to another node in it, so none of them ends "
            "it and a run would have nothing to return.\n"
            "End the slice at the node whose output the run returns, with end=."
        )
    if len(ends) > 1:
        meeting = sorted({t for n in ends for t in pipeline.graph.edges[n] if t not in inside})
        where = f" They meet at {', '.join(repr(m) for m in meeting)}." if meeting else ""
        raise ConfigurationError(
            f"This slice has {len(ends)} nodes that end it "
            f"({', '.join(repr(e) for e in ends)}), so which of them produces the run's "
            f"output depends on which path ran. A run returns one value, from one "
            f"node.{where}\n"
            + (
                f"Hold the node they meet at as well: pipeline.slice(nodes=["
                f"{', '.join(repr(n) for n in kept)}"
                + (f", {meeting[0]!r}" if meeting else "")
                + "])."
                if named
                else "End the slice where the branches meet: pass end= naming the node "
                "they lead to, or leave it out to take the tail to the end of the "
                "pipeline."
            )
        )


def _refuse_unauditable_cost(
    pipeline: "Pipeline", envelope: RunEnvelope, model: ModelClient | None
) -> None:
    """Refuse `max_cost` where nothing the run does can be priced.

    A pipeline whose only spend is a paid tool needs no basis: the tool reports what it
    was charged, or declares it. A model call is what needs one.

    A basis given per model has to name every model this run can call, since a call to a
    model it does not name has no cost and the limit would bound the rest of the run alone.
    """
    if pipeline.budget.max_cost is None:
        return
    calling = pipeline._calling_nodes(model)
    if not calling:
        return
    if envelope.cost_basis is None:
        raise ConfigurationError(
            f"The budget sets max_cost={pipeline.budget.max_cost} but the envelope declares "
            f"no cost basis, so no cost can be derived from this pipeline's model calls "
            f"and the limit would bound only what its tools report (FT-27).\n"
            f"A run on a device the project already owns has no rate to declare: set "
            f"max_cost=None, and bound it with max_wall_clock_ms on the budget instead. "
            f"Pass cost_basis=DeviceBasis(device='RTX-3090', device_count=1) to have that "
            f"run report the device-seconds it used. Where the hour is billed to someone, "
            f"pass cost_basis=PriceBasis(...) for a hosted API or "
            f"cost_basis=ComputeBasis(...) for self-hosted serving."
        )
    in_device_seconds = sorted(
        {
            client.identity().request_model
            for _, _, client in calling
            if client is not None
            and isinstance(
                basis_for(envelope.cost_basis, client.identity().request_model),
                DeviceBasis,
            )
        }
    )
    if in_device_seconds:
        named = ", ".join(repr(m) for m in in_device_seconds)
        raise ConfigurationError(
            f"The budget sets max_cost={pipeline.budget.max_cost} and the cost basis for "
            f"{named} is a DeviceBasis, which reports device-seconds. Device-seconds are "
            f"a measurement of what the run used rather than money, so a limit in money "
            f"has nothing to bind against.\n"
            f"Set max_cost=None and bound this run with max_wall_clock_ms on the budget. "
            f"Where the hour is billed to someone, declare ComputeBasis(currency=..., "
            f"device=..., device_count=..., hourly_rate=...) instead."
        )
    unpriced = sorted(
        {
            client.identity().request_model
            for _, _, client in calling
            if client is not None
            and basis_for(envelope.cost_basis, client.identity().request_model) is None
        }
    )
    if unpriced:
        named = ", ".join(repr(m) for m in unpriced)
        raise ConfigurationError(
            f"The budget sets max_cost={pipeline.budget.max_cost} and the cost basis names no "
            f"rate for {named}, which this pipeline calls, so those calls would have no "
            f"cost and the limit would bound the rest of the run alone (FT-27).\n"
            f"Add an entry for each: cost_basis={{{unpriced[0]!r}: PriceBasis(...)}}. "
            f"The key is the identifier the client reports as request_model."
        )


def _refuse_unpriceable(
    pipeline: "Pipeline", envelope: RunEnvelope, model: ModelClient | None
) -> None:
    """Refuse a single cost basis that cannot price every model this run calls.

    Per-token rates belong to one model and a device rate to one deployment, so one basis
    over two models prices one of them at the other's rates and reports a figure nothing
    says is wrong. Both cases are known before the first call.
    """
    basis = envelope.cost_basis
    if basis is None or isinstance(basis, Mapping):
        return
    identities = {
        client.identity() for _, _, client in pipeline._calling_nodes(model) if client is not None
    }
    backends = {identity.backend for identity in identities}
    models = sorted({identity.request_model for identity in identities})
    if len(backends) > 1:
        raise ConfigurationError(
            f"This run calls both a hosted and a self-hosted backend ({', '.join(models)}) "
            f"and declares one {type(basis).__name__}. A hosted call is priced on tokens "
            f"and a self-hosted one on device time, so one basis would price one of them "
            f"on the other's terms.\n"
            f"Pass one per model: cost_basis={{{models[0]!r}: PriceBasis(...), "
            f"{models[-1]!r}: ComputeBasis(...)}}. Both have to declare the same currency."
        )
    if getattr(basis, "kind", None) == "price" and len(models) > 1:
        raise ConfigurationError(
            f"This run calls {len(models)} models ({', '.join(models)}) and declares one "
            f"PriceBasis. Per-token rates are one model's, so the calls to the others "
            f"would be priced at this model's rates.\n"
            f"Pass one per model: cost_basis={{{models[0]!r}: PriceBasis(...), "
            f"{models[1]!r}: PriceBasis(...)}}. A ComputeBasis is a property of the "
            f"deployment rather than the model, so one of those covers several models "
            f"served by the same devices."
        )


def _refuse_mixed_currencies(pipeline: "Pipeline", envelope: RunEnvelope) -> None:
    """Refuse a run whose money figures are in more than one currency.

    `max_cost` bounds model spend and tool spend together, and two currencies cannot be
    added. Checked whenever a tool declares one, whether or not a limit is set, because
    the run's totals are summed either way.
    """
    declared: dict[str, list[str]] = {}
    for basis_currency in currencies_in(envelope.cost_basis):
        declared.setdefault(basis_currency, []).append("the cost basis")
    for tool in pipeline._declared_tools():
        currency = tool.declared_cost.currency if tool.declared_cost else None
        if currency:
            declared.setdefault(currency, []).append(f"tool {tool.name!r}")
    if len(declared) < 2:
        return
    listed = "; ".join(
        f"{currency}: {', '.join(sorted(where))}" for currency, where in sorted(declared.items())
    )
    raise ConfigurationError(
        f"This run declares money in more than one currency, and a total cannot add them "
        f"({listed}).\n"
        f"Declare every tool's DeclaredCost in the currency the cost basis uses, and "
        f"convert at the point the price is set rather than after the run."
    )


def _warn_bounded_cost_limit(pipeline: "Pipeline", envelope: RunEnvelope) -> None:
    """Say at the start that this limit may not be enforceable, rather than at the call.

    Under a compute basis a call whose backend reports no concurrency is priced as a
    bound, and the run ends on the first one rather than terminating against it
    (`docs/run-envelope.md` §4.4). The run has spent nothing yet when this is read.
    """
    basis = envelope.cost_basis
    if pipeline.budget.max_cost is None or getattr(basis, "kind", None) != "compute":
        return
    warnings.warn(
        f"This run sets max_cost={pipeline.budget.max_cost} under a compute basis. A call "
        f"whose backend reports no concurrent request count is priced as an upper bound, "
        f"and the run ends rather than enforcing the limit against one. "
        f"VLLMClient reports it by default; a client that cannot leaves every figure a "
        f"bound. max_wall_clock_ms bounds a self-hosted run exactly and needs no basis.",
        SimpleAgentsWarning,
        stacklevel=3,
    )


def _refuse_unserved(pipeline: "Pipeline", model: ModelClient | None) -> None:
    """Refuse a node that can call a model and has no client to call, before anything runs.

    The node raises this itself when it is reached, by which time the nodes before it have
    spent. Every input is known before the first one starts.
    """
    unserved = [node_id for node_id, _, client in pipeline._calling_nodes(model) if client is None]
    if not unserved:
        return
    raise ConfigurationError(
        f"Node(s) {', '.join(repr(n) for n in unserved)} can call a model, and neither "
        f"this run nor the node itself was given a client, so the run would stop there "
        f"having spent whatever the nodes before it spent.\n"
        f"Pass one to Pipeline.run(model=...) for every node that declares none, or "
        f"declare one on the node: LLMNode(..., model=client)."
    )


def _refuse_an_unstored_conversation(
    pipeline: "Pipeline", envelope: RunEnvelope, conversation_id: Any
) -> None:
    """Refuse a run that names a conversation with nowhere to keep it.

    The conversation outlives the run, so the library will not invent a location for it.
    """
    if conversation_id is None or envelope.conversations is not None:
        return
    raise ConfigurationError(
        f"Pipeline.run(conversation_id={conversation_id!r}) names a conversation and this "
        f"envelope declares nowhere to keep one, so what was said this turn would be gone "
        f"before the next one. A conversation outlives the run, so the library will not "
        f"invent a location for it.\n"
        f"Declare it: RunEnvelope(run_dir='runs/', "
        f"conversations=ConversationStore('conversations/'))."
    )


def _refuse_unreachable_memory(
    pipeline: "Pipeline", envelope: RunEnvelope, memory_scope: str | None, called: str
) -> None:
    """Refuse a memory tool with nothing to reach, before anything runs.

    Detectable from the declaration: a tool taking a ``Memory`` names it in its signature.
    ``simple_agents.memory`` holds what each way of being unreachable says.
    """
    if envelope.memory is not None and memory_scope is not None:
        return
    wanting = sorted(
        {
            tool.name
            for _, node in pipeline.declared_nodes()
            for tool in getattr(node, "tools", None) or ()
            if any(issubclass(held, Memory) for held in tool.handles.values())
        }
    )
    if wanting:
        refuse_unreachable(envelope.memory, memory_scope, wanting=wanting, called=called)


def _refuse_unstreamable(
    pipeline: "Pipeline", on_token: Any, model: ModelClient | None, on_reasoning: Any = None
) -> None:
    """Refuse a sink nothing can reach, before the run starts.

    Three ways it cannot be reached: no node asked to stream, the client cannot stream at
    all, or the client streams but takes no reasoning sink. All are detectable before any
    call, and none is worth discovering after a run has spent money delivering nothing.
    """
    if on_token is None and on_reasoning is None:
        return
    given = "on_token=" if on_token is not None else "on_reasoning="

    streaming = [
        node_id for node_id, node in pipeline.declared_nodes() if getattr(node, "stream", False)
    ]
    if not streaming:
        declared = ", ".join(
            f"{node_id!r}"
            for node_id, node in pipeline.declared_nodes()
            if node.node_kind in ("llm", "agent")
        )
        raise ConfigurationError(
            f"Pipeline.run was given {given} but no node in this pipeline declares "
            f"stream=True, so the callback would never be called.\n"
            f"Declare it on the node whose output is being rendered: "
            f"LLMNode(..., stream=True). The nodes that make model calls are "
            f"{declared or 'none'}. Drop {given} to run without streaming."
        )

    # Per node, since a node may declare its own client: the run's client streaming is no
    # use to a node whose own cannot, and which node it is names what to change.
    for node_id, node, client in pipeline._calling_nodes(model):
        if not getattr(node, "stream", False) or client is None:
            continue
        if not hasattr(client, "stream"):
            raise ConfigurationError(
                f"Node {node_id!r} declares stream=True and {given} was passed, but the "
                f"client its calls are made against, {type(client).__name__}, has no "
                f"stream() method, so nothing can deliver the tokens.\n"
                f"Use a client that implements it, add stream() to this one alongside "
                f"complete() and identity(), or drop {given} and the calls are made "
                f"unstreamed. A wrapper standing in front of an adapter has to delegate "
                f"stream() the way it delegates complete()."
            )
        if on_reasoning is not None and not accepts_reasoning_sink(client):
            raise ConfigurationError(
                f"Pipeline.run was given on_reasoning= but the client node {node_id!r} "
                f"calls, {type(client).__name__}, takes no on_reasoning keyword on "
                f"stream(), so the chain of thought cannot be delivered as it arrives.\n"
                f"Add it to that client: def stream(self, request, on_chunk, *, "
                f"on_reasoning=None). Drop on_reasoning= and the reasoning is still "
                f"recorded on model_call.outputs.reasoning once each call completes. A "
                f"wrapper standing in front of an adapter has to accept and forward the "
                f"keyword the way it forwards on_chunk."
            )


def _refuse_non_nodes(nodes: Sequence[Any]) -> None:
    """Refuse an empty node list, a Join in it, and anything in it that is not a node."""
    if not nodes:
        raise ConfigurationError(
            "Pipeline was constructed with no nodes. A pipeline needs at least one node "
            "to run. Pass the nodes in execution order: "
            "Pipeline([Deterministic(...), LLMNode(...)], budget=...)."
        )
    for position, listed in enumerate(nodes):
        if isinstance(listed, Join):
            raise ConfigurationError(
                f"Pipeline was given a Join at position {position} of its node list. A "
                f"Join is not a node and does not execute: it is the value a node with "
                f"more than one in-edge receives, keyed by the node each value came "
                f"from.\n"
                f"Take it out of the list, and declare the join with edges instead: the "
                f"nodes that feed it name it in successors=, and its own function reads "
                f"the Join it is handed.\n"
                f"    Pipeline([Deterministic(hunt, successors=['report']),\n"
                f"              Deterministic(verify, successors=['report']),\n"
                f"              Deterministic(report)], budget=...)"
            )
        if not hasattr(listed, "node_kind"):
            raise ConfigurationError(
                f"Pipeline was given a {type(listed).__name__} at position {position} of "
                f"its node list, and it is not a node. A pipeline holds Deterministic, "
                f"LLMNode and AgentNode, and a Pipeline given a node_id.\n"
                f"Wrap plain code in a node: Deterministic(fn, node_id='step')."
            )


def _refuse_a_nameless_nested_pipeline(nodes: Sequence[Any], *, kind: type) -> None:
    """Refuse a pipeline used as a node with no node_id to prefix its nodes with."""
    nameless = [n for n in nodes if isinstance(n, kind) and n.node_id is None]
    if not nameless:
        return
    raise ConfigurationError(
        f"This pipeline holds {len(nameless)} pipeline(s) with no node_id. Per-node "
        f"metrics, ablation and the trajectory all key on node_id, and a pipeline used "
        f"as a node prefixes its own nodes with it, so it has to have one.\n"
        f"Pass node_id= when constructing it: "
        f"Pipeline([...], budget=..., node_id='research')."
    )


def _refuse_unusable_ids(ids: Sequence[str]) -> None:
    """Refuse two nodes sharing an id, and an id holding a dot at the top level."""
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ConfigurationError(
            f"This pipeline has more than one node called {', '.join(duplicates)}. "
            f"Per-node metrics and ablation are keyed on node_id, so duplicates report as "
            f"one node, and two nodes sharing an id also share a model-call counter, "
            f"which makes the second node's seeds depend on how many calls the first "
            f"made.\n"
            f"Pass node_id= explicitly: LLMNode(build_prompt, output_schema=Answer, "
            f"node_id='draft'). It defaults to the function's name, so two nodes built "
            f"from one function collide, as do two lambdas."
        )
    dotted = sorted(i for i in ids if "." in i)
    if dotted:
        raise ConfigurationError(
            f"This pipeline holds {len(dotted)} node(s) whose node_id contains a dot "
            f"({', '.join(repr(i) for i in dotted)}). A pipeline used as a node prefixes "
            f"its own nodes with its id and a dot, so 'research.hunt' already means 'hunt' "
            f"inside 'research', and a dotted id at the top level is indistinguishable "
            f"from it. Per-node metrics, the trajectory, the manifest and ablation all key "
            f"on that id.\n"
            f"Use an id with no dot, such as {dotted[0].replace('.', '_')!r}. To get a "
            f"dotted id, put the node in a pipeline with that node_id: "
            f"Pipeline([...], budget=..., node_id={dotted[0].split('.')[0]!r})."
        )


def _refuse_a_model_pipeline_without_budget(
    nodes: Sequence[Any], budget: Any, *, kinds: tuple[type, ...]
) -> None:
    """Refuse a pipeline that can call a model and carries no budget decision (FT-18)."""
    model_nodes = [n for n in nodes if isinstance(n, kinds)]
    if not model_nodes or budget is not None:
        return
    names = ", ".join(n.node_id for n in model_nodes)
    raise ConfigurationError(
        f"This pipeline can call a model ({names}) but was constructed without a "
        f"budget. An unbounded run consumes tokens or money until an external "
        f"limit stops it, and is the most commonly omitted piece in hand-rolled "
        f"code and the one with the worst failure mode. This is a refusal rather "
        f"than a warning, because warnings get ignored (FT-18).\n"
        f"Pass budget=Budget(max_steps=..., max_tokens=..., max_cost=..., "
        f"max_wall_clock_ms=...). Any axis may be None to leave it unbounded; "
        f"what is refused is the absence of a decision. "
        f"Budget.unbounded() states that explicitly when every axis should be open."
    )


def _refuse_an_unfillable_policy(nodes: Sequence[Any], fetch_policy: Any) -> None:
    """Refuse a tool taking a HostPolicy that neither the tool nor the pipeline declares."""
    for node in nodes:
        for one in getattr(node, "tools", None) or []:
            takes_policy = any(issubclass(kind, HostPolicy) for kind in one.handles.values())
            if takes_policy and one.fetch_policy is None and fetch_policy is None:
                raise ConfigurationError(
                    f"Tool {one.name!r} on node {node.node_id!r} takes a HostPolicy "
                    f"parameter, and neither the tool nor this pipeline declares a "
                    f"policy, so the run has nothing to fill it with. Pass policy= "
                    f"where the tool is built, or declare Pipeline(fetch_policy=...)."
                )
