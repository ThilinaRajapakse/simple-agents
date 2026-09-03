"""A consultation's answer: delivery, reading, and the records of both."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from ..context import RunContext, error_object
from ..errors import CallerFacingError, ConfigurationError, ModelFacingError
from ..models import ModelRequest, ModelResponse
from ..records.shelf import ShelvedQuestion
from ..tools import ConsultTool, Reading, Tool
from ..records.trajectory import (
    PENDING_SEQUENCE,
    ConsultationRecord,
    ModelCallRecord,
    ToolCallRecord,
    utc_now,
)
from .calls import _CallResult, _emit_failed_call_record, _inputs, _prompt_of
from .metering import (
    _Metered,
    _ToolOutcome,
    _cost_record,
    _refuse_bounded_cost,
    _refuse_unaffordable_call,
)


def _delivered_answer(
    *,
    run: RunContext,
    parent_id: str,
    node_id: str,
    name: str,
    arguments: dict[str, Any],
    answer: Any,
    tool: Tool | None,
    asked_at: str,
    asked_record_id: str | None,
    occurrence: int | None,
    item_index: int | None = None,
) -> Any:
    """Record the answer a suspended call was waiting for, and return what that call produces.

    The call is not made again. The answer is filed in the cassette under the key that call
    would have had, so a replay of this run serves it and never suspends.

    The consultation tool is bound to whoever answers this run, as the question was, so the
    record carrying the answer names the same person as the record carrying the question.
    """
    # Taken before the answer is read, because the reading's model call is parented to this
    # record and the reading happens here: an answer that arrives in a later process is read
    # for the first time in that process.
    record_id = run.new_record_id()
    read_by: str | None = None
    unread: CallerFacingError | None = None
    if isinstance(tool, ConsultTool):
        tool = tool.for_one_call(run.end_user)
    if isinstance(tool, ConsultTool) and tool.read_answer is not None:
        answer = tool.read_answer(answer, arguments.get("options"))
        try:
            answer, read_by = _read_the_answer(
                run=run,
                tool=tool,
                answer=answer,
                options=arguments.get("options"),
                node_id=node_id,
                parent_id=record_id,
                item_index=item_index,
            )
        except CallerFacingError as exc:
            unread = exc
    cassette_key = None
    if tool is not None and occurrence is not None:
        cassette_key = run.file_answer(
            tool=tool,
            arguments=arguments,
            occurrence=occurrence,
            answer=answer,
            node_id=node_id,
            call_index=0,
            item_index=item_index,
        )

    if isinstance(tool, ConsultTool):
        run.emit(
            ConsultationRecord(
                record_id=record_id,
                run_id=run.run_id,
                parent_id=parent_id,
                sequence=PENDING_SEQUENCE,
                started_at=asked_at,
                ended_at=utc_now(),
                prompt=str(arguments.get("question", "")),
                options=arguments.get("options"),
                about=arguments.get("about"),
                answered_at=getattr(answer, "answered_at", None),
                response=answer,
                chose=getattr(answer, "chose", None),
                declared_choice=getattr(answer, "declared_choice", None),
                read_by=read_by,
                reaches=tool.reaches,
                resolution=(
                    "answered" if unread is not None else tool.resolve(answer, failed=False)
                ),
                blocking=False,
                answered_by=tool.answered_by,
                answers=asked_record_id,
                error=None if unread is None else error_object(unread, model_facing=False),
                item_index=item_index,
            )
        )
        if unread is not None:
            raise unread
    else:
        run.emit(
            ToolCallRecord(
                record_id=record_id,
                run_id=run.run_id,
                parent_id=parent_id,
                sequence=PENDING_SEQUENCE,
                started_at=asked_at,
                ended_at=utc_now(),
                tool_name=name,
                tool_version=getattr(tool, "version", None),
                side_effect_class=(
                    tool.side_effect_class.value if tool is not None else "read_only"
                ),
                inputs=arguments,
                outputs=answer,
                replayed=False,
                re_executed=bool(getattr(tool, "re_executed", False)),
                cassette_key=cassette_key,
                declared_cost=_cost_record(tool) if tool is not None else None,
                # The call was made before the run suspended, so this process bought nothing
                # and the earlier one's record holds whatever it spent.
                spent=None,
                item_index=item_index,
            )
        )
    return answer


def _no_one_answered(
    *,
    run: RunContext,
    parent_id: str,
    tool: ConsultTool,
    call: Any,
    reason: str,
    item_index: int | None = None,
) -> _ToolOutcome:
    """Answer a consultation from what an earlier one in this run established.

    The channel reported that there is nobody to ask, so it is not asked again. The question is
    recorded anyway, and counted like any other, because how many times an agent tried to reach
    a person who was not there is what a project reads to decide whether the design holds
    without them.
    """
    from ..builtins.consult import Unavailable

    unavailable = Unavailable(reason=reason)
    now = utc_now()
    run.emit(
        ConsultationRecord(
            record_id=run.new_record_id(),
            run_id=run.run_id,
            parent_id=parent_id,
            sequence=PENDING_SEQUENCE,
            started_at=now,
            ended_at=now,
            prompt=str(call.arguments.get("question", "")),
            options=call.arguments.get("options"),
            about=call.arguments.get("about"),
            asked=False,
            response=None,
            resolution="unavailable",
            blocking=True,
            answered_by=tool.answered_by,
            reaches=tool.reaches,
            reason=reason,
            item_index=item_index,
        )
    )
    return _ToolOutcome(value=unavailable)


def _answering_model(run: RunContext, tool: ConsultTool) -> dict[str, Any] | None:
    """What the channel reported about the model that wrote this answer, priced.

    ``None`` where a person answered, and where a replay served the answer, since a replayed
    consultation bought nothing. The figure is kept off the node's own model calls: the model
    that plays an end user is not the model being measured.
    """
    reported = tool.provenance or {}
    identity = reported.get("model")
    if identity is None:
        return None
    tokens = reported.get("tokens")
    cost = reported.get("cost")
    return {
        **(identity.to_manifest() if hasattr(identity, "to_manifest") else dict(identity)),
        "tokens": tokens.to_record() if hasattr(tokens, "to_record") else tokens,
        "cost": _cost_entry(cost),
    }


def _cost_entry(cost: Any) -> dict[str, Any] | None:
    """A derived cost in the shape every other record writes it.

    ``Cost`` carries no serialiser of its own and holds slots rather than a dict, so a record
    given the object itself stores the string its ``repr`` produces.
    """
    if cost is None or isinstance(cost, Mapping):
        return dict(cost) if cost is not None else None
    return {
        "value": getattr(cost, "value", None),
        "currency": getattr(cost, "currency", None),
        "basis": getattr(cost, "basis", None),
        "is_upper_bound": bool(getattr(cost, "is_upper_bound", False)),
        "reason": getattr(cost, "reason", None),
    }


@dataclass
class _InFlight:
    """One tool call while it is running: what it is, what came back, what it spent.

    Held together rather than passed apart because a record is written from most of it, and
    from four places: the call succeeded, the tool failed, the tool suspended, and the model
    was handed an observation.
    """

    run: RunContext
    tool: Tool
    call: Any
    parent_id: str
    node_id: str
    item_index: int | None
    record_id: str
    call_index: int
    started_at: str
    metered: _Metered
    nested: list[_CallResult] = field(default_factory=list)
    result: Any = None
    message: str | None = None
    """What the model is handed as an observation, where the tool raised a model-facing
    failure. ``None`` on a call that did not fail that way."""
    error: dict[str, Any] | None = None
    raised: ModelFacingError | None = None
    """The failure itself, beside the text of it in ``message``. What ``ctx.call_tool``
    re-raises, so a node body catches the kind of failure the tool raised."""
    cassette_key: str | None = None
    replayed: bool = False
    read_by: str | None = None
    unread: CallerFacingError | None = None
    """The end user answered and the reading of their answer failed. The consultation is still
    recorded, carrying the answer and this."""

    @property
    def question(self) -> str:
        """What was asked, for a consultation."""
        return str(self.call.arguments.get("question", ""))

    @property
    def options(self) -> Any:
        """The options that were offered, or ``None``."""
        return self.call.arguments.get("options")

    @property
    def about(self) -> str | None:
        """The stable name the caller gave what the question is about, or ``None``."""
        return self.call.arguments.get("about")

    def spent(self) -> Any:
        """What this call cost, for the record."""
        return self.metered.report(replayed=self.replayed, failed=self.message is not None)


def _make_the_call(
    flight: _InFlight,
    *,
    validate: Callable[[dict[str, Any]], Any] | None,
    make_handles: Callable[[Tool, str, list[_CallResult]], dict[str, Any]] | None,
    occurrence: int | None,
) -> None:
    """Run the tool and put what came back on ``flight``.

    ``validate`` is `finish`, which is schema validation inside the library rather than a call
    on anything external, so it does not go through the cassette.
    """
    if validate is not None:
        flight.result = validate(flight.call.arguments)
        return
    tool, run = flight.tool, flight.run
    _refuse_unaffordable_call(run, tool)
    handles = (
        make_handles(tool, flight.record_id, flight.nested)
        if make_handles is not None and tool.handles
        else None
    )
    outcome = run.call_tool(
        tool,
        flight.call.arguments,
        node_id=flight.node_id,
        call_index=flight.call_index,
        handles=flight.metered.fill(handles),
        occurrence=occurrence,
        item_index=flight.item_index,
    )
    flight.result = outcome.value
    flight.cassette_key = outcome.cassette_key
    flight.replayed = outcome.replayed
    if isinstance(tool, ConsultTool) and tool.read_answer is not None:
        _read_what_they_said(flight)


def _read_what_they_said(flight: _InFlight) -> None:
    """Turn a consultation's raw answer into the option it meant.

    Done here rather than in the tool because a replayed answer arrives as bare text: a replay
    that skipped this would record ``answered`` where the live run recorded ``unmatched``.
    """
    tool = flight.tool
    flight.result = tool.read_answer(flight.result, flight.options)
    try:
        flight.result, flight.read_by = _read_the_answer(
            run=flight.run,
            tool=tool,
            answer=flight.result,
            options=flight.options,
            node_id=flight.node_id,
            parent_id=flight.record_id,
            item_index=flight.item_index,
        )
    except CallerFacingError as exc:
        # The person answered and the answer is on file; what failed is the reading of it. The
        # consultation is recorded carrying the answer and this error, so the run that ends
        # here still says what was said.
        flight.unread = exc


def _record_a_pending_consultation(flight: _InFlight) -> None:
    """The question a suspended run stopped on, so a run never resumed still says what it asked."""
    flight.run.emit(
        ConsultationRecord(
            record_id=flight.record_id,
            run_id=flight.run.run_id,
            parent_id=flight.parent_id,
            sequence=PENDING_SEQUENCE,
            started_at=flight.started_at,
            ended_at=None,
            prompt=flight.question,
            options=flight.options,
            about=flight.about,
            response=None,
            resolution="pending",
            blocking=False,
            answered_by=flight.tool.answered_by,
            reaches=flight.tool.reaches,
            item_index=flight.item_index,
        )
    )


def _record_a_consultation(flight: _InFlight) -> None:
    """How the question ended, and what was said."""
    tool, result = flight.tool, flight.result
    # A reading that failed leaves `chose` unset, and `unmatched` would report that as the end
    # user having said something off the list. They answered; what is unknown is which option
    # it was, and the error on the record is what says so.
    resolution = (
        "answered"
        if flight.unread is not None
        else tool.resolve(result, failed=flight.message is not None)
    )
    # A shelved question sets no memo. The once-per-run rule answers a channel that reported
    # nobody to ask, and a channel that shelves has reached somebody.
    if resolution == "unavailable":
        flight.run.note_no_one_to_ask(tool.name, result.reason)
    answered = flight.message is None and resolution not in ("unavailable", "shelved")
    if resolution == "shelved":
        _note_it_is_outstanding(flight, reason=getattr(result, "reason", None))
    flight.run.emit(
        ConsultationRecord(
            record_id=flight.record_id,
            run_id=flight.run.run_id,
            parent_id=flight.parent_id,
            sequence=PENDING_SEQUENCE,
            started_at=flight.started_at,
            ended_at=utc_now(),
            prompt=flight.question,
            options=flight.options,
            about=flight.about,
            asked=True,
            answered_at=getattr(result, "answered_at", None) if answered else None,
            response=result if answered else None,
            chose=getattr(result, "chose", None) if answered else None,
            declared_choice=getattr(result, "declared_choice", None) if answered else None,
            read_by=flight.read_by,
            reaches=tool.reaches,
            resolution=resolution,
            blocking=True,
            answered_by=tool.answered_by,
            reason=getattr(result, "reason", None) if not answered else None,
            answered_by_model=_answering_model(flight.run, tool),
            error=(
                flight.error
                if flight.unread is None
                else error_object(flight.unread, model_facing=False)
            ),
            item_index=flight.item_index,
        )
    )


def _note_it_is_outstanding(flight: _InFlight, *, reason: str | None) -> None:
    """Put a shelved question on the run's shelf, for whoever answers it later."""
    flight.run.note_shelved(
        ShelvedQuestion(
            run_id=flight.run.run_id,
            record_id=flight.record_id,
            node_id=flight.node_id,
            prompt=flight.question,
            asked_at=flight.started_at,
            about=flight.about,
            options=list(flight.options) if flight.options else None,
            reason=reason,
            item_index=flight.item_index,
        )
    )


def _read_the_answer(
    *,
    run: RunContext,
    tool: ConsultTool,
    answer: Any,
    options: Any,
    node_id: str,
    parent_id: str,
    item_index: int | None = None,
) -> tuple[Any, str | None]:
    """Read an end user's answer into the option it meant, and say what read it.

    Returns the answer and what decided ``chose``: ``"model"`` where the project registered a
    ``read=`` reader, ``"rule"`` where the tool's own matching decided it, and ``None`` where
    nothing did, which is an open question and an unanswered consultation.

    The reader runs wherever an answer arrives, and every call it makes goes through the
    cassette, so a replay reads again at the price of a cassette hit and an edited prompt is a
    miss on that call rather than the old verdict standing.
    """
    from ..builtins.consult import Reply

    if not isinstance(answer, Reply) or not options:
        return answer, None
    if tool.reader is None:
        return answer, "rule"
    try:
        chosen = tool.reader(
            _reading_handle(run, node_id, parent_id, item_index),
            str(answer),
            list(options),
        )
    except CallerFacingError:
        raise
    except Exception as exc:
        # Raised as caller-facing so the consultation is still recorded with the answer on it.
        # Left alone, it reaches the handler that reports an undeclared failure of the tool,
        # which writes a `tool_call` record for an event that was a consultation and names the
        # channel rather than the reader.
        raise CallerFacingError(
            f"The reader registered on {tool.name!r} raised {type(exc).__name__}: {exc}. It is "
            f"called with a Reading, the end user's answer and the offered options, and has to "
            f"return one of those options or None.\n"
            f"The answer it was reading was {str(answer)[:200]!r}. Reach the model through the "
            f"Reading it was given, so the call is recorded and replayed, and let a failure "
            f"that should end the run be a CallerFacingError."
        ) from exc
    if chosen is not None and chosen not in options:
        raise ConfigurationError(
            f"The reader registered on {tool.name!r} returned {chosen!r}, which is not one of "
            f"the options it was given ({', '.join(repr(o) for o in options)}). It decides "
            f"which branch the run takes, so a value that is not an option routes nowhere.\n"
            f"Return one of them, or None where the answer meant none."
        )
    return (
        Reply(
            str(answer),
            chose=chosen,
            options=answer.options,
            declared_choice=answer.declared_choice,
        ),
        "model",
    )


def _reading_handle(
    run: RunContext, node_id: str, parent_id: str, item_index: int | None = None
) -> Reading:
    """The recorded path a consultation's reader makes its model call through.

    ``item_index`` is the fan-out item whose loop asked the question. Without it two items'
    readings share one call counter, so the seed each is sent depends on which item asked
    first, and that seed is in the cassette key.
    """

    def complete(
        client: Any,
        prompt: Any,
        *,
        output_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> ModelResponse:
        asked = _prompt_of(prompt, where=f"The reader of a consultation in node {node_id!r}")
        return _call_reading_model(
            run=run,
            client=client,
            node_id=node_id,
            parent_id=parent_id,
            messages=asked[0],
            assembly=asked[1],
            output_schema=output_schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            item_index=item_index,
        )

    return Reading(_complete=complete)


def _call_reading_model(
    *,
    run: RunContext,
    client: Any,
    node_id: str,
    parent_id: str,
    messages: list[dict[str, Any]],
    output_schema: dict[str, Any] | None,
    temperature: float | None,
    max_output_tokens: int | None,
    item_index: int | None = None,
    assembly: dict[str, Any] | None = None,
) -> ModelResponse:
    """One reading call: recorded, counted and charged like any other model call.

    The record is parented to the consultation rather than to the node, so the tokens spent
    reading an answer are attributable to the question that needed reading. The cost is the
    agent's: a reader ships with it, and in production something has to read what a person
    typed.
    """
    # A reading is a model call, so it takes its step before dispatching rather than charging
    # one afterwards. The reservation is held until the charge lands, which is what stops two
    # consultations that overlap from both claiming the last step.
    with run.one_step(run.budget):
        call_index = run.next_model_call(node_id, item_index)
        request = ModelRequest(
            messages=messages,
            seed=run.seed_for(node_id, call_index, item_index),
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            output_schema=output_schema,
        )
        identity = client.identity()
        context_record = {"context_builder": None, "dropped": [], "estimate": None}
        started_at = utc_now()
        try:
            outcome = run.call_model(
                request,
                client,
                node_id=node_id,
                call_index=call_index,
                item_index=item_index,
            )
        except Exception as exc:
            _emit_failed_call_record(
                run=run,
                request=request,
                identity=identity,
                parent_id=parent_id,
                started_at=started_at,
                exc=exc,
                context=context_record,
                item_index=item_index,
            )
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
            item_index=item_index,
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
        run.manifest.observe_held_back(response.held_back_ms)
        _refuse_bounded_cost(run, cost)
        run.charge(steps=1, tokens=response.tokens.total, cost=cost.value)
        return response


def _outcome_of(flight: _InFlight) -> _ToolOutcome:
    """What the caller gets back, with what the call and anything inside it spent.

    The tool's own charge is applied to the run here rather than in the tool, so a tool that
    reports a figure and a tool priced by declaration deplete ``max_cost`` through one path.
    """
    priced = [c.cost.value for c in flight.nested if c.cost.value is not None]
    inside = sum(priced) if priced else None
    charged = flight.metered.amount
    if charged is not None:
        flight.run.charge(cost=charged)
    return _ToolOutcome(
        value=flight.result,
        error=flight.message,
        raised=flight.raised,
        calls=len(flight.nested),
        tokens=sum(c.response.tokens.total for c in flight.nested),
        cost=inside if charged is None else (inside or 0.0) + charged,
    )
