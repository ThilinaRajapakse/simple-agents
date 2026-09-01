"""The handles a node's tools reach the library through."""

from __future__ import annotations

from typing import Any, Callable, Mapping
from ..records.conversation import Conversation
from ..context import RunContext
from ..embeddings import normalise
from ..errors import ConfigurationError
from ..tools import HostPolicy, Memory, Retrieval, Tool, Workspace
from ..records.trajectory import PENDING_SEQUENCE, ModelCallRecord, utc_now
from .metering import _refuse_bounded_cost


def _node_input(tool: Tool, param: str, inputs: Any, node_id: str) -> Any:
    """What a tool's ``NodeInput`` parameter is filled with: the node's input, or one key of it.

    The key is declared where the tool is, so a key the input does not carry is a
    ``ConfigurationError`` rather than a caller-facing failure: it fails the same way on every
    rollout, and an evaluation stops on the first rather than recording k×n agent failures.
    """
    key = tool.node_inputs.get(param)
    if key is None:
        return inputs
    if not isinstance(inputs, Mapping):
        raise ConfigurationError(
            f"Tool {tool.name!r} asks for NodeInput({key!r}) and node {node_id!r} was handed "
            f"a {type(inputs).__name__}, which has no keys.\n"
            f"Read the whole input with Annotated[<type>, NodeInput] and take what the tool "
            f"needs in its body, or carry a mapping on the edge into this node."
        )
    if key not in inputs:
        held = ", ".join(repr(name) for name in inputs) or "nothing"
        raise ConfigurationError(
            f"Tool {tool.name!r} asks for NodeInput({key!r}) and node {node_id!r} was handed "
            f"an input carrying {held}.\n"
            f"Name a key the node receives, or read the whole input with "
            f"Annotated[<type>, NodeInput] where the value is there on some runs and not "
            f"others."
        )
    return inputs[key]


def _deterministic_handle(
    run: RunContext,
    tool: Tool,
    kind: type,
    node_id: str,
    parent_id: str,
    item_index: int | None = None,
) -> Any:
    """The handle a tool called from a deterministic node is given."""
    if issubclass(kind, Workspace):
        return Workspace(root=run.workspace)
    if issubclass(kind, Retrieval):
        return _retrieval_handle(run, node_id, parent_id, item_index)
    if issubclass(kind, HostPolicy):
        return _fetch_policy_for(run, tool)
    if issubclass(kind, Conversation):
        return _conversation_handle(run, tool)
    return _memory_handle(run, tool)


def _fetch_policy_for(run: RunContext, tool: Tool) -> Any:
    """The run's copy of the policy this tool counts against.

    The tool's own declaration wins; a tool declaring none takes the pipeline's. Neither
    being declared is refused at ``Pipeline`` construction, so reaching this with neither is
    a tool called outside any pipeline that declares one.
    """
    declaration = (
        tool.fetch_policy if tool.fetch_policy is not None else run.fetch_policy_declaration
    )
    if declaration is None:
        raise ConfigurationError(
            f"Tool {tool.name!r} takes a HostPolicy parameter and neither the tool nor the "
            f"pipeline declares one. Pass policy= where the tool is built, or declare "
            f"Pipeline(fetch_policy=...)."
        )
    return run.bound_fetch_policy(declaration)


def _retrieval_handle(
    run: RunContext, node_id: str, parent_id: str, item_index: int | None = None
) -> Retrieval:
    """The recorded path a search tool's embedding and reranking calls take.

    Each call goes through the cassette, emits a ``model_call`` record parented to the tool
    call, and is charged to the run's budget, so the tokens a search spends are attributable to
    the search that spent them.
    """

    def embed(client: Any, texts: list[str]) -> list[list[float]]:
        response = _call_retrieval_model(
            run=run,
            client=client,
            node_id=node_id,
            parent_id=parent_id,
            kind="embedding",
            item_index=item_index,
            inputs={"texts": list(texts)},
            invoke=lambda index: run.call_embedding(
                client, texts, node_id=node_id, call_index=index
            ),
            outputs=lambda r: {"dimensions": r.dimensions, "vectors": len(r.vectors)},
        )
        return [normalise(v) for v in response.vectors]

    def rerank(client: Any, query: str, documents: list[str]) -> list[Any]:
        response = _call_retrieval_model(
            run=run,
            client=client,
            node_id=node_id,
            parent_id=parent_id,
            kind="rerank",
            item_index=item_index,
            inputs={"query": query, "documents": len(documents)},
            invoke=lambda index: run.call_rerank(
                client, query, documents, node_id=node_id, call_index=index
            ),
            outputs=lambda r: {
                "order": [s.index for s in r.ordered()],
                "scores": [round(s.score, 6) for s in r.ordered()],
            },
        )
        return response.ordered()

    return Retrieval(_embed=embed, _rerank=rerank)


def _call_retrieval_model(
    *,
    run: RunContext,
    client: Any,
    node_id: str,
    parent_id: str,
    kind: str,
    inputs: dict[str, Any],
    invoke: Callable[[int], Any],
    outputs: Callable[[Any], dict[str, Any]],
    item_index: int | None = None,
) -> Any:
    """One embedding or reranking call: recorded, counted and charged like any model call.

    ``inputs`` records what was asked rather than the vectors that came back: a 768-dimension
    vector is 17 kB as JSON, and a trajectory holding one per search is mostly numbers no
    reader uses. The dimension and the count are recorded instead.
    """
    # An embedding or a rerank is a model call, so it takes its step before dispatching
    # rather than charging one afterwards. The reservation is held until the charge lands,
    # so a search whose calls overlap stops exactly on `max_steps`.
    with run.one_step(run.budget):
        call_index = run.next_model_call(node_id, item_index)
        started_at = utc_now()
        outcome = invoke(call_index)
        response = outcome.value
        held_back_ms = getattr(response, "held_back_ms", 0)

        record = ModelCallRecord(
            record_id=run.new_record_id(),
            run_id=run.run_id,
            parent_id=parent_id,
            sequence=PENDING_SEQUENCE,
            started_at=started_at,
            ended_at=utc_now(),
            backend=response.backend,
            request_model=response.request_model,
            model_revision=response.model_revision,
            response_model=response.response_model,
            params={"call_kind": kind},
            seed=None,
            item_index=item_index,
            inputs=inputs,
            outputs=outputs(response),
            finish_reason=None,
            tokens=response.tokens.to_record(),
            concurrent_requests=None,
            replayed=outcome.replayed,
            cassette_key=outcome.cassette_key,
            context={"context_builder": None, "dropped": [], "estimate": None},
            recorded_duration_ms=outcome.recorded_duration_ms,
            held_back_ms=held_back_ms,
            provider=dict(getattr(response, "provider", {})),
        )
        run.emit(record)
        cost = run.cost_of_call(record)
        run.manifest.observe_model(
            backend=response.backend,
            request_model=response.request_model,
            response_model=response.response_model,
            model_revision=response.model_revision,
        )
        run.manifest.observe_tokens(response.tokens.to_record())
        run.manifest.observe_held_back(held_back_ms)
        _refuse_bounded_cost(run, cost)
        run.charge(steps=1, tokens=response.tokens.total, cost=cost.value)
        return response


def _memory_handle(run: RunContext, tool: Tool) -> Memory:
    """The memory this run's memory tools reach, or a refusal naming what to declare."""
    if run.memory is None:
        raise ConfigurationError(
            f"Tool {tool.name!r} takes a Memory and this run reaches none, so there is nothing "
            f"for it to read or write. Memory outlives the run, so the library will not invent "
            f"a location for it or decide whose memory it is.\n"
            f"Declare where memories live and name whose this run reads: "
            f"RunEnvelope(run_dir='runs/', memory=MemoryStore('memory/')) and "
            f"pipeline.run(inputs, envelope=env, memory_scope=f'user-{{user_id}}')."
        )
    return Memory(_store=run.memory, _redaction=run.redaction)


def _conversation_handle(run: RunContext, tool: Tool) -> Conversation:
    """The conversation this run's tools reach, or a refusal naming what to declare."""
    thread = getattr(run, "conversation", None)
    if thread is None:
        raise ConfigurationError(
            f"Tool {tool.name!r} takes a Conversation and this run is not a turn of one, so "
            f"there is nothing for it to read or write. A conversation outlives the run, so "
            f"the library will not invent one.\n"
            f"Declare the store on the envelope and name the conversation on the run: "
            f"RunEnvelope(run_dir='runs/', conversations=ConversationStore('conversations/')) "
            f"and pipeline.run(inputs, envelope=env, model=client, "
            f"conversation_id=f'chat-{{chat_id}}')."
        )
    recorded = getattr(run.manifest, "conversation", None)
    turn = int((recorded or {}).get("turn") or thread.turn_count or 1)
    return Conversation(_thread=thread, _turn=turn)
