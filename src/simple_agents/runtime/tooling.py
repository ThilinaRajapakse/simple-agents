"""Executing one tool call, wherever the call is made from."""

from __future__ import annotations

from typing import Any, Callable, Sequence
from ..records.conversation import Conversation
from ..context import RunContext, error_object
from ..errors import CallerFacingError, ConfigurationError, ModelFacingError, Suspend
from ..models import ToolCallRequest
from ..tools import ConsultTool, HostPolicy, Memory, NodeInput, Retrieval, Tool, Workspace
from ..records.trajectory import PENDING_SEQUENCE, ResourceAccessRecord, ToolCallRecord, utc_now
from .calls import _CallResult
from .consultation import (
    _InFlight,
    _delivered_answer,
    _make_the_call,
    _no_one_answered,
    _outcome_of,
    _record_a_consultation,
    _record_a_pending_consultation,
)
from .handles import _deterministic_handle, _node_input
from .metering import _Metered, _ToolOutcome, _cost_record
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..nodes import Execution


class _FixedPointCaller:
    """What backs ``ctx.call_tool`` for a node that declared tools.

    The call goes through the same path an ``AgentNode``'s calls take, so it is keyed,
    recorded and replayed identically. What differs is the failure: no model is choosing this
    call, so a ``ModelFacingError`` is re-raised rather than returned as an observation.

    Calls are numbered in the order the node function makes them. A node that stopped writes
    that number down, and the resumed node hands the answer to the call at the same number
    rather than making it again. ``delivered`` says whether that happened, so a function that
    took a different path on the way back is reported rather than losing the answer.
    """

    def __init__(
        self,
        *,
        run: RunContext,
        node_id: str,
        parent_id: str,
        tools: Sequence[Tool],
        inputs: Any,
        waiting: dict[str, Any] | None = None,
        answer: Any = None,
        item_index: int | None = None,
    ) -> None:
        self.run = run
        self.node_id = node_id
        self.parent_id = parent_id
        self.item_index = item_index
        self.inputs = inputs
        self.by_name = {t.name: t for t in tools}
        self.waiting = waiting
        self.answer = answer
        self.delivered = waiting is None
        self.number = 0

    def __call__(self, name: str, arguments: dict[str, Any]) -> Any:
        run, node_id = self.run, self.node_id
        number, self.number = self.number, self.number + 1
        tool = self.by_name.get(name)
        if tool is None:
            raise ConfigurationError(
                f"Node {node_id!r} called tool {name!r}, which it did not declare. It "
                f"declared {', '.join(sorted(self.by_name)) or '(none)'}.\n"
                f"Add it: Deterministic(fn, tools=[..., {name}])."
            )
        waiting = self.waiting
        if waiting is not None and waiting["call_number"] == number:
            if waiting["tool"] != name:
                raise CallerFacingError(
                    f"Node {node_id!r} stopped on call {number} to "
                    f"{waiting['tool']!r}, and on the way back call {number} went to "
                    f"{name!r}. A resumed node runs again from the beginning, so its calls "
                    f"have to come in the same order for the answer to reach the one that "
                    f"is waiting for it.\n"
                    f"Make the function up to that call depend only on the node's inputs, "
                    f"or hold the work that varies in an AgentNode, which is resumed from "
                    f"the conversation it had rather than by running again."
                )
            self.delivered = True
            return _delivered_answer(
                run=run,
                parent_id=self.parent_id,
                node_id=node_id,
                name=name,
                arguments=dict(arguments),
                answer=self.answer,
                tool=tool,
                asked_at=waiting["asked_at"],
                asked_record_id=waiting["asked_record_id"],
                occurrence=waiting["occurrence"],
                item_index=self.item_index,
            )

        # Built against the tool call's own record id rather than the node's, so an embedding
        # or a rerank made inside a search is parented to the search that made it.
        def handles(chosen: Tool, record_id: str, _sink: list[_CallResult]) -> dict[str, Any]:
            return {
                param: (
                    _node_input(chosen, param, self.inputs, node_id)
                    if issubclass(kind, NodeInput)
                    else _deterministic_handle(
                        run, chosen, kind, node_id, record_id, self.item_index
                    )
                )
                for param, kind in chosen.handles.items()
                if issubclass(
                    kind, (Workspace, Memory, Conversation, Retrieval, HostPolicy, NodeInput)
                )
            }

        asked_at = utc_now()
        try:
            outcome = _run_tool(
                run=run,
                parent_id=self.parent_id,
                node_id=node_id,
                tool=tool,
                call=ToolCallRequest(id=name, name=name, arguments=arguments),
                make_handles=handles,
                item_index=self.item_index,
            )
        except Suspend as suspending:
            # What the resumed node needs in order to hand this call its answer instead of
            # making it again. The node itself holds nothing else: it runs from the beginning.
            suspending.node_state = {
                "kind": "deterministic",
                "call_number": number,
                "tool": name,
                "asked_at": asked_at,
                "asked_record_id": suspending.asked_record_id,
                "occurrence": suspending.tool_occurrence,
            }
            raise
        if outcome.error is not None:
            # The failure itself where there is one, so a node body catching a kind of tool
            # failure catches what the tool raised rather than a flattened copy of it.
            raise outcome.raised or ModelFacingError(outcome.error)
        return outcome.value


def _run_tool(
    *,
    run: RunContext,
    parent_id: str,
    node_id: str,
    tool: Tool,
    call: Any,
    validate: Callable[[dict[str, Any]], Any] | None = None,
    make_handles: Callable[[Tool, str, list[_CallResult]], dict[str, Any]] | None = None,
    occurrence: int | None = None,
    item_index: int | None = None,
    by_model: bool = False,
) -> _ToolOutcome:
    """Execute one tool call and record it.

    A :class:`ModelFacingError` comes back as ``error``, for the loop to hand to the model as
    an observation. A :class:`CallerFacingError` propagates and ends the run.

    The time the tool takes binds ``max_wall_clock_ms``, which is elapsed time while the run
    is executing, and nothing here charges it.

    ``occurrence`` is the number this call records under, reserved by the caller where a turn's
    calls were dispatched together. ``item_index`` is the fan-out item this call was made for,
    and nothing else attributes a call to an item.

    The record's ``sequence`` is taken when it is written rather than when the call starts, so a
    model call made inside the tool is ordered before the record that contains it, which is how
    a ``node`` record already relates to its children. A consultation tool is bound to whoever
    answers this run before it is called, and ``by_model`` says whether the model chose the
    call, which is what decides whether the run's ``no_one_to_ask`` memo may answer it.
    """
    if isinstance(tool, ConsultTool):
        # The memo is an instruction to stop asking, and only a model can read one. A node
        # body's loop cannot, so silencing it discards the questions the code was written to
        # ask: one project asked 109 distinct questions and 5 reached the channel.
        already = run.no_one_to_ask(tool.name) if by_model else None
        if already is not None:
            return _no_one_answered(
                run=run,
                parent_id=parent_id,
                tool=tool,
                call=call,
                reason=already,
                item_index=item_index,
            )
        tool = tool.for_one_call(run.end_user)

    flight = _InFlight(
        run=run,
        tool=tool,
        call=call,
        parent_id=parent_id,
        node_id=node_id,
        item_index=item_index,
        record_id=run.new_record_id(),
        call_index=run.next_tool_call(node_id),
        started_at=utc_now(),
        metered=_Metered(tool, run),
    )

    try:
        _make_the_call(flight, validate=validate, make_handles=make_handles, occurrence=occurrence)
    except ModelFacingError as exc:
        flight.message = str(exc)
        flight.raised = exc
        flight.error = error_object(exc, model_facing=True, retryable=exc.retryable)
    except Suspend as exc:
        # The tool did not fail, and it has not answered either. The question is recorded
        # `pending`; the answering record names this one when it arrives.
        run.note_suspension_left(exc.waiting_for)
        if isinstance(tool, ConsultTool):
            exc.asked_record_id = flight.record_id
            _record_a_pending_consultation(flight)
        raise
    except CallerFacingError:
        raise
    except Exception as exc:
        # An undeclared exception is treated as caller-facing. Passing it to the model would
        # produce an answer built on a failed dependency, with no record that it had failed.
        _record_a_tool_call(flight, raised=exc)
        raise CallerFacingError(
            f"Tool {tool.name!r} raised {type(exc).__name__}: {exc}. The failure was not "
            f"declared as model-facing, so the run is treated as invalid rather than the "
            f"error being passed to the model as data. For failures the model can recover "
            f"from, such as an empty result set or a 404, raise ModelFacingError from within "
            f"the tool."
        ) from exc

    if isinstance(tool, ConsultTool):
        _record_a_consultation(flight)
        if flight.unread is not None:
            raise flight.unread
    else:
        _record_a_tool_call(flight)
    return _outcome_of(flight)


def _record_a_tool_call(flight: _InFlight, *, raised: BaseException | None = None) -> None:
    """What the tool was given and what it returned, or the failure that ended the run."""
    tool = flight.tool
    failed = raised is not None
    flight.run.emit(
        ToolCallRecord(
            record_id=flight.record_id,
            run_id=flight.run.run_id,
            parent_id=flight.parent_id,
            sequence=PENDING_SEQUENCE,
            started_at=flight.started_at,
            ended_at=utc_now(),
            tool_name=tool.name,
            tool_version=tool.version,
            side_effect_class=tool.side_effect_class.value,
            inputs=flight.call.arguments,
            outputs=None if failed or flight.message is not None else flight.result,
            replayed=False if failed else flight.replayed,
            re_executed=tool.re_executed,
            cassette_key=None if failed else flight.cassette_key,
            declared_cost=_cost_record(tool),
            spent=(
                flight.metered.report(replayed=False, failed=True) if failed else flight.spent()
            ),
            error=(error_object(raised, model_facing=False) if failed else flight.error),
            item_index=flight.item_index,
        )
    )


def _access_recorder(run: RunContext, execution: Execution, node: Any) -> Any:
    """What ``ctx.record_access`` writes: one record per access, under this execution.

    The node's ``touches=`` is captured here, so an access naming a resource the node never
    declared is refused where the declaration is in scope rather than at read time.
    """
    declared = frozenset(getattr(node, "touches", ()) or ())
    node_id = execution.node_id
    parent_id = execution.record_id

    def record(
        resource: str, direction: str, inputs: Any, outputs: Any, item_index: int | None
    ) -> None:
        if resource not in declared:
            named = ", ".join(sorted(declared)) if declared else "nothing"
            raise ConfigurationError(
                f"Node {node_id!r} recorded an access to {resource!r} and declares "
                f"{named}. A resource is named the same way wherever it is touched, so the "
                f"page that draws what flows between pipelines can join the two.\n"
                f"Declare it on the node: {type(node).__name__}(fn, "
                f"touches={resource!r})."
            )
        at = utc_now()
        run.emit(
            ResourceAccessRecord(
                record_id=run.new_record_id(),
                run_id=run.run_id,
                parent_id=parent_id,
                sequence=PENDING_SEQUENCE,
                started_at=at,
                ended_at=at,
                node_id=node_id,
                resource=resource,
                direction=direction,  # type: ignore[arg-type]
                inputs=inputs,
                outputs=outputs,
                item_index=item_index,
            )
        )

    return record
