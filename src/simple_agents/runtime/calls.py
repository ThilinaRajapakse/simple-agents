"""One model call: making it, validating what came back, recording what it cost."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from pydantic import TypeAdapter, ValidationError
from ..budget import Budget
from ..context import ChunkRecorder, NodeContext, RunContext, TokenEvent, error_object
from ..context_builder import ContextBuilder, ContextOverflow, locate_overflow, message_chars
from ..cost import Cost
from ..errors import CallerFacingError, ConfigurationError, StreamUsageMissing
from ..pacing import warn_unpaced_wait
from ..prompting import Prompt
from ..models import (
    ModelClient,
    ModelIdentity,
    ModelRequest,
    ModelResponse,
    TokenUsage,
    held_back_ms_of,
)
from ..schema import Unknown, json_schema_for_model
from ..records.trajectory import PENDING_SEQUENCE, ModelCallRecord, utc_now
from .metering import _refuse_bounded_cost


@dataclass(frozen=True, slots=True)
class _CallResult:
    """One model call's response and what it cost."""

    response: ModelResponse
    cost: Cost


def _call_model(
    *,
    run: RunContext,
    model: ModelClient,
    node_id: str,
    parent_id: str,
    messages: list[dict[str, Any]],
    context: ContextBuilder,
    ctx: NodeContext,
    temperature: float | None,
    max_output_tokens: int | None,
    output_schema: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
    stream: bool = False,
    node_kind: str = "",
    call_index: int | None = None,
    item_index: int | None = None,
    assembly: dict[str, Any] | None = None,
) -> _CallResult:
    """Make one model call, record it, and charge the run for it.

    The context builder decides what of ``messages`` goes on the wire, once per call under
    every node kind. Its output is what the cassette is keyed on, so a context builder that
    varies with run state produces a miss rather than a response recorded against a
    different request.

    The seed sent to the backend is derived from the run seed, this node, and how many calls
    this node has already made, so every call in a run reconstructs from the one seed the
    manifest records. That makes the request identical on a re-run; whether the response is
    identical is the backend's to say (``docs/run-envelope.md`` §5).

    ``item_index`` is the fan-out item this call belongs to, and ``call_index`` counts within
    that item. Numbering an item's calls by their position in that item's own work rather than
    by how the items interleaved is what makes two runs of one fan-out send the same seed for
    the same item whether or not the items overlapped.
    """
    # One step is one model call, and the step is taken here rather than after the
    # response returns, so a call does not start unless one remains. The reservation is
    # held until the charge below lands, which is what stops two calls that overlap from
    # both claiming the last step.
    with run.one_step(run.budget, scope=parent_id):
        if call_index is None:
            call_index = run.next_model_call(node_id, item_index)
        else:
            run.saw_model_call(node_id, call_index, item_index)
        view = run.context_view(ctx, node_id)
        try:
            built = context.build(list(messages), view)
        except ContextOverflow as exc:
            # Nothing was sent, so there is no call to record. The node record carries the error.
            raise locate_overflow(exc, view, call_index) from exc
        context_record = {
            "context_builder": type(context).__name__,
            "dropped": [d.to_record() for d in built.dropped],
            "estimate": built.estimate.to_record() if built.estimate is not None else None,
        }
        request = ModelRequest(
            messages=built.messages,
            seed=run.seed_for(node_id, call_index, item_index),
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            tools=list(tools) if tools else [],
            output_schema=output_schema,
            extra=dict(extra) if extra else {},
        )

        # Read before the call, so a failure is recorded against the model that was asked for
        # rather than losing the identity along with the response.
        identity = model.identity()
        # A run that supplied only one of the two sinks still streams, so the chain of thought can
        # be shown without the answer or the other way round. The content recorder is built either
        # way, because the chunk boundaries it captures are what a replay re-emits.
        streaming = stream and (run.token_sink is not None or run.reasoning_sink is not None)
        recorder = (
            _token_sink(run, node_id=node_id, node_kind=node_kind, call_index=call_index, ctx=ctx)
            if streaming
            else None
        )
        reasoning_recorder = (
            _token_sink(
                run,
                node_id=node_id,
                node_kind=node_kind,
                call_index=call_index,
                ctx=ctx,
                kind="reasoning",
            )
            if streaming
            else None
        )
        started_at = utc_now()
        try:
            outcome = run.call_model(
                request,
                model,
                node_id=node_id,
                call_index=call_index,
                item_index=item_index,
                on_chunk=recorder,
                on_reasoning=reasoning_recorder,
            )
        # BaseException rather than Exception, because a `ModelClient` may raise `Suspend`
        # and that record says what the run had already streamed when it stopped.
        except BaseException as exc:
            _emit_failed_call_record(
                run=run,
                assembly=assembly,
                request=request,
                identity=identity,
                parent_id=parent_id,
                started_at=started_at,
                exc=exc,
                context=context_record,
                recorder=recorder,
                item_index=item_index,
            )
            if isinstance(exc, ContextOverflow):
                raise locate_overflow(exc, view, call_index) from exc
            if isinstance(exc, StreamUsageMissing):
                raise _locate_missing_usage(
                    exc,
                    run=run,
                    node_id=node_id,
                    node_kind=node_kind,
                    call_index=call_index,
                    node_budget=getattr(ctx, "budget", None),
                ) from exc
            raise
        response: ModelResponse = outcome.value

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
            params=request.params_for_record(run.manifest.register_schema),
            seed=request.seed,
            inputs=_inputs(request.messages, assembly),
            outputs={
                "content": response.content,
                "tool_calls": [c.to_record() for c in response.tool_calls],
                "reasoning": (
                    response.reasoning.to_record() if response.reasoning is not None else None
                ),
            },
            finish_reason=response.finish_reason,
            tokens=response.tokens.to_record(),
            concurrent_requests=response.concurrent_requests,
            replayed=outcome.replayed,
            cassette_key=outcome.cassette_key,
            context=context_record,
            recorded_duration_ms=outcome.recorded_duration_ms,
            held_back_ms=response.held_back_ms,
            rate_limit=response.rate_limit.to_record() if response.rate_limit else None,
            provider=dict(response.provider),
            stream=outcome.stream.to_record() if outcome.stream is not None else None,
            item_index=item_index,
        )
        if assembly is not None:
            run.manifest.observe_templates(node_id, assembly.get("templates") or [])
        run.emit(record)

        # What this call's prompt cost, for the next call's context builder to extrapolate from.
        run.note_input_size(
            node_id,
            tokens=response.tokens.measured_input,
            chars=message_chars(request.messages),
            call_index=call_index,
            item_index=item_index,
        )

        cost = run.cost_of_call(record)
        # The call happened, so the manifest records it before anything decides whether the run
        # continues. Refusing first left `counts.model_call` at 1 beside an empty `models.observed`
        # and zero tokens, for a run whose trajectory holds the call.
        run.manifest.observe_model(
            backend=response.backend,
            request_model=response.request_model,
            response_model=response.response_model,
            model_revision=response.model_revision,
        )
        run.manifest.observe_tokens(response.tokens.to_record())
        first_wait_of_the_run = not run.manifest.held_back_ms and response.held_back_ms
        run.manifest.observe_held_back(response.held_back_ms)
        if first_wait_of_the_run:
            warn_unpaced_wait(model, response)
        _refuse_bounded_cost(run, cost)
        # The step reserved above becomes spend here, under every node kind. Charging it here
        # rather than in the agent loop is what makes the axis bound a pipeline of LLMNodes.
        run.charge(steps=1, tokens=response.tokens.total, cost=cost.value, scope=parent_id)
        return _CallResult(response=response, cost=cost)


def _locate_missing_usage(
    exc: StreamUsageMissing,
    *,
    run: RunContext,
    node_id: str,
    node_kind: str,
    call_index: int,
    node_budget: Budget | None,
) -> StreamUsageMissing:
    """The same refusal, saying where it happened and what this run loses by it.

    Every consequence named is one the run actually has. A pipeline with no token limit, no
    cost basis and no step limit is told that instead, rather than three things that are not
    true of it.
    """
    kind = {"llm": "LLMNode", "agent": "AgentNode"}.get(node_kind, "the node")
    losses = []
    if run.budget.max_tokens is not None:
        losses.append(
            f"this pipeline sets max_tokens={run.budget.max_tokens}, which will charge 0 for "
            f"this call"
        )
    if run.cost_basis is not None:
        losses.append("no cost derives from it, so FT-27 has nothing to read")
    consequence = (
        " and ".join(losses).capitalize() + "."
        if losses
        else (
            "Nothing in this run reads a token count. The trajectory records `unknown` for it, "
            "and an evaluation over that trajectory later reads the same."
        )
    )

    bounded = (
        f" This node's max_steps={node_budget.max_steps} still binds, so the run stays bounded "
        f"by calls."
        if node_budget is not None and node_budget.max_steps is not None
        else ""
    )

    return StreamUsageMissing(
        f"Node {node_id!r}, call {call_index}: {exc.summary}\n"
        f"{consequence}\n"
        f"\n"
        f"There are two fixes:\n"
        f"  1. Keep streaming and accept the loss. Pass "
        f'{exc.adapter}(model="{exc.model}", stream_without_usage=True). Streamed calls then '
        f"record `unknown` counts naming this reason, and the waiver is recorded in the "
        f"manifest.{bounded}\n"
        f"  2. Drop streaming on this node. Remove stream=True from {kind}({node_id!r}) and "
        f"the call is made through complete(), fully counted.",
        model=exc.model,
        adapter=exc.adapter,
        summary=exc.summary,
    )


def _token_sink(
    run: RunContext,
    *,
    node_id: str,
    node_kind: str,
    call_index: int,
    ctx: Any,
    kind: str = "content",
) -> Any:
    """The recorder each piece of a streamed response passes through, or ``None``.

    A node declaring ``stream=True`` still makes an ordinary call where the run was given no
    ``on_token``, so an evaluation of a streaming pipeline makes the same calls a
    non-streaming one does. The two channels are independent, so a run may take the chain of
    thought without the answer or the other way round.
    """
    sink = run.reasoning_sink if kind == "reasoning" else run.token_sink
    if sink is None:
        # The content channel still records where the pieces fell, since a cassette entry
        # stores those boundaries and a replay re-emits them. The reasoning channel has
        # nothing to record for a run that did not ask for it.
        return None if kind == "reasoning" else ChunkRecorder(lambda text: None)
    item_index = getattr(ctx, "item_index", None)

    def deliver(text: str) -> None:
        sink(
            TokenEvent(
                node_id=node_id,
                node_kind=node_kind,
                call_index=call_index,
                text=text,
                item_index=item_index,
                kind=kind,
            )
        )

    return ChunkRecorder(deliver)


def _emit_failed_call_record(
    *,
    run: RunContext,
    request: ModelRequest,
    identity: ModelIdentity,
    parent_id: str,
    started_at: str,
    exc: BaseException,
    context: dict[str, Any],
    recorder: Any = None,
    item_index: int | None = None,
    assembly: dict[str, Any] | None = None,
) -> None:
    """Record a model call that raised before returning a response.

    ``ended_at`` is ``null``, which ``docs/trajectory-format.md`` §2 defines as an operation
    that never completed, and every token count is ``unknown`` rather than ``0``. A call that
    timed out after two minutes and one that was refused in a millisecond are both real
    outcomes, and neither is recoverable from a trajectory that omits the attempt.

    A streamed call that stopped part-way records the text that reached the end user and how
    far it got. Those pieces cannot be recalled, and a resumed run makes the call again from
    the start, so a reader needs to see what was already delivered.

    Time the call spent held back before it raised is on the exception, and is recorded and
    added to the run total. A run a rate limit ended waited, and the wait is what explains its
    wall clock.

    ``item_index`` names the fan-out item the call was for, as it does on a call that returned.
    A fan-out collects a failed item rather than raising, so this record is the only place the
    run says which item never reached the backend.
    """
    unmeasured = Unknown(reason="the call raised before the backend returned a response")
    partial = recorder.text if recorder is not None and recorder.parts else None
    held_back_ms = held_back_ms_of(exc)
    run.manifest.observe_held_back(held_back_ms)
    run.emit(
        ModelCallRecord(
            record_id=run.new_record_id(),
            run_id=run.run_id,
            parent_id=parent_id,
            sequence=PENDING_SEQUENCE,
            started_at=started_at,
            ended_at=None,
            backend=identity.backend,
            request_model=identity.request_model,
            model_revision=identity.model_revision,
            response_model=None,
            params=request.params_for_record(run.manifest.register_schema),
            seed=request.seed,
            inputs=_inputs(request.messages, assembly),
            outputs=(None if partial is None else {"content": partial, "tool_calls": []}),
            finish_reason=None,
            tokens=TokenUsage(
                input_uncached=unmeasured,
                input_cache_read=unmeasured,
                input_cache_write=unmeasured,
                cache_ttl=None,
                output=unmeasured,
            ).to_record(),
            concurrent_requests=None,
            replayed=False,
            cassette_key=None,
            context=context,
            held_back_ms=held_back_ms,
            stream=recorder.capture().to_record() if partial is not None else None,
            error=error_object(exc, model_facing=False),
            item_index=item_index,
        )
    )


def _assistant_turn(
    content: str, reasoning: Any, *, tool_calls: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """One turn of the loop's own conversation, in the library's shape.

    ``reasoning`` is carried where the backend reported one, so the model is given its own
    chain of thought back on the turn it is still working on. Each adapter decides whether its
    backend accepts the field; one with no field for it drops it in ``messages_to_wire``.

    The key is absent rather than null where there is nothing to carry, so a conversation from
    a backend that reports no reasoning is byte-identical to one built before this existed.
    """
    turn: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning is not None and reasoning.text:
        turn["reasoning"] = reasoning.text
    if tool_calls is not None:
        turn["tool_calls"] = tool_calls
    return turn


def _observation(call: Any, content: Any) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "name": call.name,
        "content": content if isinstance(content, str) else repr(content),
    }


def _inputs(messages: list[dict[str, Any]], assembly: dict[str, Any] | None) -> dict[str, Any]:
    """What the call was sent, and how the prompt behind it was built.

    ``assembly`` is absent on a call whose messages are a conversation rather than a prompt,
    which is every turn of an agent loop after the first.
    """
    held: dict[str, Any] = {"messages": messages}
    if assembly is not None:
        held["assembly"] = assembly
    return held


def _prompt_of(built: Any, *, where: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The messages one call sends, and the record of how they were built.

    A prompt is fixed text with named values, so what the model was told is recorded apart
    from the data that filled it. A string carries neither and is refused.
    """
    if isinstance(built, Prompt):
        if not built.messages:
            raise ConfigurationError(
                f"{where} returned a Prompt with no messages, so the call would send nothing. "
                f"Build at least one: Prompt.user('...')."
            )
        return built.to_messages(), built.to_record()
    if isinstance(built, str):
        raise ConfigurationError(
            f"{where} returned a string, and a prompt is built from fixed text with named "
            f"values:\n\n    return Prompt.user('Answer using {{notes}}.', notes=inputs['notes'])"
            f"\n\nThe text already assembled goes through unchanged as the fixed text: "
            f"Prompt.user(text). `docs/prompts.md` §1."
        )
    if isinstance(built, list):
        raise ConfigurationError(
            f"{where} returned a list of messages. Build them with Prompt, which records what "
            f"each one was written from:\n\n    return Prompt.system('...') + "
            f"Prompt.user('{{question}}', question=q)\n\nMessages a run already recorded are "
            f"carried with Prompt.turns(messages). `docs/prompts.md` §1."
        )
    raise ConfigurationError(
        f"{where} returned {type(built).__name__}, and a prompt function returns a Prompt: "
        f"Prompt.user('...{{name}}...', name=value). `docs/prompts.md` §1."
    )


def _validated_output(value: Any, output_schema: Any, node_id: str) -> Any:
    """A ``Deterministic`` node's return value, checked against what the node declared.

    Raises :class:`CallerFacingError` rather than reaching the next node, so the mismatch is
    reported where it was produced.
    """
    try:
        return TypeAdapter(output_schema).validate_python(value)
    except ValidationError as exc:
        raise CallerFacingError(
            f"Node {node_id!r} declares "
            f"output_schema={getattr(output_schema, '__name__', output_schema)!r} and returned "
            f"a {type(value).__name__} that does not validate against it:\n{exc}\n"
            f"Return what the schema describes, or drop output_schema= from the node."
        ) from exc


def _json_schema(output_schema: Any) -> dict[str, Any] | None:
    if getattr(output_schema, "model_json_schema", None) is None:
        return None
    return json_schema_for_model(output_schema)


def _validate(output_schema: Any, content: str | None) -> Any:
    """Validate an ``LLMNode`` response against its output schema.

    A schema violation is caller-facing: an ``LLMNode`` makes one call, so the model has no
    subsequent step in which to correct the response.
    """
    validator = getattr(output_schema, "model_validate_json", None)
    if validator is None or content is None:
        return content
    try:
        return validator(content)
    except Exception as exc:
        raise CallerFacingError(
            f"The model's response did not match the declared output schema "
            f"({getattr(output_schema, '__name__', output_schema)}): {exc}\n"
            f"Raw response: {content!r}\n"
            f"An LLMNode makes exactly one call, so there is no step in which the model can "
            f"correct this. Constrain decoding to the schema by passing it through `extra` to "
            f"a backend that supports guided decoding, tighten the prompt, or use an "
            f"AgentNode if the task requires more than one attempt."
        ) from exc


def _is_plain(value: Any) -> bool:
    """Whether a value is already what JSON holds, all the way down."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_plain(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_plain(v) for k, v in value.items())
    return False
