"""The node that owns a loop: the model decides the next action, the library owns dispatch and stopping."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any, Callable, Mapping, Sequence
from ..budget import Budget, BudgetExceeded
from ..records.conversation import (
    Conversation,
    ThreadWriter as _ThreadWriter,
    thread_view as _thread_view,
)
from ..context import (
    AgentContext,
    FinishAttempt,
    NodeContext,
    RunContext,
    ToolCallSummary,
    error_object,
)
from ..context_builder import AppendAll, ContextBuilder
from ..errors import ConfigurationError, ModelFacingError, Suspend
from ..graph import Loop, RetryPolicy
from ..records.manifest import source_version
from ..models import ModelClient, ModelResponse, ToolCallRequest
from ..schema import (
    require_a_schema_a_model_can_fill,
    require_unknown_branch,
    warn_literal_absence_union,
)
from ..tools import (
    FINISH_TOOL_NAME,
    ConsultTool,
    FinishTool,
    HostPolicy,
    Memory,
    ModelHandle,
    NodeInput,
    Retrieval,
    SideEffectClass,
    Tool,
    ToolRegistry,
    Workspace,
    normalized_touches,
)
from ..records.trajectory import PENDING_SEQUENCE, DelegationRecord, utc_now
from ..runtime.budgets import (
    _budget_tripped,
    _declare_agent_budgets,
    _refuse_over_budget,
    _spent_since,
)
from ..runtime.calls import _CallResult, _as_messages, _assistant_turn, _call_model, _observation
from ..runtime.consultation import _delivered_answer
from ..runtime.handles import (
    _conversation_handle,
    _fetch_policy_for,
    _memory_handle,
    _node_input,
    _retrieval_handle,
)
from ..runtime.metering import _ToolOutcome
from ..runtime.suspending import _Suspending, _captured
from ..runtime.tooling import _access_recorder, _run_tool
from .base import (
    Execution,
    NodeOutcome,
    _declare_edges,
    _declare_planned,
    _not_built_entry,
    _not_built_message,
    model_for,
)
from .delegation import Delegation
from .fanout import _declare_fan_out, _fan_out


# How many times one `finish` payload may be refused before the loop stops asking. A check
# that refuses the same answer repeatedly is not going to accept it on the next turn, and the
# alternative is a run that spends its whole step budget and returns nothing.
MAX_IDENTICAL_FINISH_REJECTIONS = 3


def _declare_dispatch_names(node: "AgentNode", tools: Any, delegates: Sequence[Any]) -> None:
    """Set the node's tools and delegations, refusing any ambiguity in the model's namespace.

    A delegation reaches the model as one more tool, so tools, delegations and `finish`
    share one namespace, and any duplicate makes dispatch ambiguous.
    """
    node.tools = list(tools)
    names = [t.name for t in node.tools]
    if FINISH_TOOL_NAME in names:
        raise ConfigurationError(
            f"AgentNode {node.node_id!r} was given a tool named {FINISH_TOOL_NAME!r}. "
            f"The name is reserved. The library supplies `finish` itself, validated "
            f"against this node's output_schema, so that termination is an explicit "
            f"schema-checked call. Rename the tool."
        )
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ConfigurationError(
            f"AgentNode {node.node_id!r} has more than one tool named "
            f"{', '.join(sorted(duplicates))}. The model selects tools by name, so a "
            f"duplicate makes dispatch ambiguous. Give each tool a distinct name."
        )

    node.delegates = list(delegates)
    for delegate in node.delegates:
        if not isinstance(delegate, Delegation):
            raise ConfigurationError(
                f"AgentNode {node.node_id!r} was given delegates="
                f"[{type(delegate).__name__}]. Each entry is a Delegation naming the "
                f"pipeline and how the model is told to use it: "
                f"delegates=[Delegation(research, description='...')]."
            )
    delegate_names = [d.name for d in node.delegates]
    clashing = sorted(set(delegate_names) & (set(names) | {FINISH_TOOL_NAME}))
    if clashing:
        raise ConfigurationError(
            f"AgentNode {node.node_id!r} offers {', '.join(repr(c) for c in clashing)} as "
            f"both a delegation and a tool. The model selects by name, so a duplicate "
            f"makes dispatch ambiguous and the trajectory cannot say which ran.\n"
            f"Rename the tool, or give the delegated pipeline a different node_id: "
            f"Pipeline([...], budget=..., node_id='research_worker')."
        )
    repeated = sorted({n for n in delegate_names if delegate_names.count(n) > 1})
    if repeated:
        raise ConfigurationError(
            f"AgentNode {node.node_id!r} has more than one delegation named "
            f"{', '.join(repeated)}. A delegation is offered under its pipeline's node_id, "
            f"and its nodes record under ids prefixed by it, so two would collide in the "
            f"trajectory as well as in dispatch.\n"
            f"Give each delegated pipeline a distinct node_id."
        )


class AgentNode:
    """The model decides what happens next: which tool, whether to loop, when to stop. It is
    the only node kind whose number of model calls is not known in advance, so a budget is
    required at construction, and any axis of it may be ``None``.

    ``over`` runs the loop once per item of an input key holding a sequence. ``budget`` then
    bounds every item together and ``budget_per_item`` bounds one, and declaring one warns::

        node = AgentNode(read_one, tools=[look_up], output_schema=Reading, over="documents",
                         budget_per_item=Budget(max_steps=8, max_tokens=20_000,
                                                max_cost=None, max_wall_clock_ms=60_000),
                         budget=Budget(max_steps=200, max_tokens=400_000,
                                       max_cost=None, max_wall_clock_ms=600_000))

    Trajectories from a working ``AgentNode`` show which decisions it makes identically every
    time. Those can be frozen into an ``LLMNode`` or a ``Deterministic`` node::

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def look_up(query: str) -> str:
            \"\"\"Search the document set. Returns matching passages.\"\"\"
            return index.search(query)

        def build_prompt(inputs: dict, ctx: AgentContext) -> str:
            return f"{inputs['question']} Available tools: {ctx.describe_tools()}"

        node = AgentNode(
            build_prompt,
            tools=[look_up],
            output_schema=Answer,
            budget=Budget(max_steps=8, max_tokens=50_000,
                          max_cost=None, max_wall_clock_ms=120_000),
        )

    The library supplies ``finish``, so ``tools`` holds the node's own tools alone, as a list
    or a ``ToolRegistry``; ``concurrent_tools`` names the ones whose calls overlap in a turn::

        node = AgentNode(build_prompt, tools=[search, fetch, write_note],
                         output_schema=Answer, budget=Budget(...),
                         concurrent_tools=[search, fetch])

    ``delegates`` holds the pipelines the model may hand a subtask to, as
    :class:`Delegation` objects, each offered as one more tool and spending this node's budget,
    and ``model`` is the client its calls go to, the loop's and any a tool makes alike::

        node = AgentNode(plan_the_work, tools=[read_page], output_schema=Report,
                         budget=Budget(...), model=strong,
                         delegates=[Delegation(research, description="Research one question.")])

    ``finish_check`` runs after the answer validates and rejects answers the schema cannot
    describe. A string is sent to the model as a failed ``finish``; ``None`` accepts it::

        def cited_what_it_read(answer: Answer, ctx: AgentContext) -> str | None:
            opened = {c.result for c in ctx.tool_calls if c.name == "read" and c.ok}
            missing = sorted(set(answer.sources) - opened)
            if missing and not ctx.finish_attempts:
                return f"Sources {missing} were cited but never read."
            return None

    ``ctx.tool_calls`` carries every call the node has made and what each returned. Refusing an
    answer it believes it has already given loops until ``termination: "finish_rejected"``, so
    read ``ctx.finish_attempts`` first (``docs/tools.md`` §5).
    ``allow_unfinished=True`` declares that spending the whole budget without calling a tool,
    consulting or delegating is expected here, which is what FT-35 fails a project for::

        node = AgentNode(watch_for_it, tools=[poll], output_schema=Answer,
                         budget=Budget(...), allow_unfinished=True)
    """

    node_kind = "agent"

    def __init__(
        self,
        prompt: Callable[[Any, AgentContext], Any],
        *,
        tools: Sequence[Tool] | ToolRegistry,
        output_schema: Any,
        touches: str | Sequence[str] | None = None,
        budget: Budget | None = None,
        budget_per_item: Budget | None = None,
        delegates: Sequence[Delegation] = (),
        concurrent_tools: Sequence[Tool] | None = None,
        over: str | None = None,
        keep: Sequence[str] | None = None,
        max_failures: int | None = None,
        concurrent_items: int | None = None,
        node_id: str | None = None,
        prompt_version: str | None = None,
        allow_unknown: bool = True,
        allow_unfinished: bool = False,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
        stream: bool = False,
        model: ModelClient | None = None,
        context: ContextBuilder | None = None,
        finish_check: Callable[[Any, AgentContext], str | None] | None = None,
        successors: Sequence[str] | None = None,
        route: Callable[[Any, Any], Any] | None = None,
        loop: Loop | None = None,
        on_error: str | None = None,
        retry: RetryPolicy | None = None,
        suspend_before: bool = False,
    ) -> None:
        self.prompt = prompt
        self.planned = _declare_planned(self, prompt, node_id, "AgentNode")
        self.output_schema = output_schema
        self.node_id = node_id if self.planned else (node_id or prompt.__name__)
        self.prompt_version = prompt_version
        self.prompt_entry = (
            _not_built_entry(prompt) if self.planned else source_version(prompt, prompt_version)
        )
        self.touches = normalized_touches(touches, where=f"AgentNode {self.node_id!r}")
        self.model = model
        self.context = context if context is not None else AppendAll()
        _declare_edges(
            self,
            successors=successors,
            route=route,
            loop=loop,
            on_error=on_error,
            retry=retry,
            suspend_before=suspend_before,
        )
        self.allow_unknown = allow_unknown
        self.allow_unfinished = allow_unfinished
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.extra = extra or {}
        self.stream = stream
        self.finish_check = finish_check
        self.finish_check_entry = source_version(finish_check) if finish_check is not None else None

        _declare_fan_out(
            self,
            over=over,
            keep=keep,
            max_failures=max_failures,
            concurrent_items=concurrent_items,
            retry=retry,
        )
        _declare_agent_budgets(self, budget=budget, budget_per_item=budget_per_item)

        _declare_dispatch_names(self, tools, delegates)
        self.concurrent_tools = self._accept_concurrent(concurrent_tools)

        # A planned node may leave the schema unsettled; the view shows the absence. A schema
        # that is declared is checked whether the node is planned or not.
        if self.planned and output_schema is None:
            self._finish = None
        else:
            require_a_schema_a_model_can_fill(
                output_schema, where=f"Node {self.node_id!r}", argument="output_schema"
            )
            require_unknown_branch(
                output_schema, node_name=self.node_id, allow_unknown=allow_unknown
            )
            warn_literal_absence_union(output_schema, node_name=self.node_id)
            self._finish = FinishTool(output_schema)

    def execute(
        self,
        inputs: Any,
        run: RunContext,
        model: ModelClient | None = None,
        execution: Execution | None = None,
        resume_state: dict[str, Any] | None = None,
        answer: Any = None,
        frames: list[dict[str, Any]] | None = None,
    ) -> NodeOutcome:
        """Run the loop until the model finishes, a budget binds, or something suspends.

        ``model`` is the run's client, used where this node declares none of its own.

        Under ``over=`` the loop runs once per item and the node returns a
        :class:`FanOutResult`, each outcome carrying how that item terminated.

        ``resume_state`` is what this node held when a run stopped inside it, ``answer`` is
        what the call that suspended returns, and ``frames`` is where a delegated pipeline had
        got to. All three come from the pipeline; a caller supplies none of them.
        """
        if self.planned:
            raise ConfigurationError(_not_built_message(self))
        model = model_for(self, model)
        if model is None:
            # A ConfigurationError rather than a bare CallerFacingError: it fails
            # identically on every rollout, so an evaluation stops on the first
            # rather than recording k x n agent failures.
            raise ConfigurationError(
                f"Node {self.node_id!r} is an AgentNode but the pipeline was run without a "
                f"model client and the node declares none.\n"
                f"Pass one to Pipeline.run(model=...), or to this node as "
                f"AgentNode(..., model=client)."
            )
        execution = execution if execution is not None else Execution.for_node(self, run)
        if self.over is None:
            outputs, termination = self._one(
                inputs,
                run,
                model,
                execution,
                resume_state=resume_state,
                answer=answer,
                frames=frames,
            )
            return NodeOutcome(outputs=outputs, termination=termination)

        seed_ctx = NodeContext(
            run_id=run.run_id,
            node_id=execution.node_id,
            workspace=run.workspace,
            seed=run.seed,
            budget=execution.budget,
            fetch_policy=run.node_fetch_policy(),
            _access_recorder=_access_recorder(run, execution, self),
        )
        with run.scoped_budget(execution.record_id, self.budget):
            return NodeOutcome(
                outputs=_fan_out(
                    self,
                    inputs=inputs,
                    run=run,
                    ctx=seed_ctx,
                    execution=execution,
                    one=lambda item_inputs, item_ctx, index, held, given: self._one(
                        item_inputs,
                        run,
                        model,
                        execution,
                        item_index=index,
                        resume_state=held,
                        answer=given,
                    ),
                    resume_state=resume_state,
                    answer=answer,
                )
            )

    def _one(
        self,
        inputs: Any,
        run: RunContext,
        model: ModelClient,
        execution: Execution,
        *,
        resume_state: dict[str, Any] | None = None,
        answer: Any = None,
        frames: list[dict[str, Any]] | None = None,
        item_index: int | None = None,
    ) -> tuple[Any, str | None]:
        """One run of the loop: the whole node, or one item of a fan-out.

        Returns what the loop produced and how it stopped. ``item_index`` is the fan-out item
        this is, and ``None`` outside one; an item is bounded by ``budget_per_item`` narrowing
        what the node was already narrowed to.
        """
        record_id = execution.record_id
        node_id = execution.node_id

        # The budget in force is the per-axis minimum of what remains of the run and this
        # node's own cap. A node may narrow what the run allows; it may not widen it. One item
        # of a fan-out narrows that again by what the item was given, so a runaway item stops
        # on its own allowance rather than on the node's.
        effective = execution.budget
        if item_index is not None:
            effective = effective.narrowed_by(self.budget_per_item)

        finish_tool = self._finish.as_tool()
        by_name = {t.name: t for t in self.tools}
        delegates = {d.name: d for d in self.delegates}
        # A delegation reaches the backend as one more tool declaration: there is no second
        # mechanism on the wire, and the model chooses among them by name either way.
        wire_tools = (
            [t.to_wire() for t in self.tools]
            + [d.to_wire() for d in self.delegates]
            + [finish_tool.to_wire()]
        )
        # How many subtasks each delegation has been sent in this execution, which is what
        # `max_calls` bounds and what the record's `invocation` counts.
        sent: dict[str, int] = dict.fromkeys(delegates, 0)

        node_started = time.monotonic()
        node_tokens = 0
        node_cost: float | None = None
        # One step is one model call, under every node kind and wherever the call was made
        # from. A model call inside a tool counts, so a node budget bounds what its tools spend.
        node_calls = 0
        step = 0
        outputs: Any = None
        termination = "error"
        made: list[ToolCallSummary] = []
        finish_attempts: list[FinishAttempt] = []
        # Time spent suspended is charged to nothing: this node's clock counts the stretches
        # it was executing, and a person taking a day to answer is not the node running for a
        # day. Waiting the node did itself, for a tool or a quota, is inside those stretches.
        already_ms = 0
        pending: list[Any] = []

        # A model call made inside a tool or a delegate is charged to the run where it was
        # made; the node's own totals have to pick it up too, or a node budget would not bind
        # what its tools spend.
        def fold_spend(outcome: _ToolOutcome) -> None:
            nonlocal node_calls, node_tokens, node_cost
            node_calls += outcome.calls
            node_tokens += outcome.tokens
            if outcome.cost is not None:
                node_cost = (node_cost or 0.0) + outcome.cost
            run.charge_scope(
                record_id,
                steps=outcome.calls,
                tokens=outcome.tokens,
                cost=outcome.cost,
            )

        # What this node holds at the moment a call under it suspends, read live from the
        # loop's own state. Only the suspended call itself differs between the two raises.
        def captured_here(
            *,
            pending_call: Any,
            remaining: list[Any],
            asked_at: str,
            asked_record_id: Any,
            occurrence: Any,
        ) -> dict[str, Any]:
            return _captured(
                messages=messages,
                made=made,
                finish_attempts=finish_attempts,
                calls=node_calls,
                tokens=node_tokens,
                cost=node_cost,
                step=step,
                elapsed_ms=already_ms + int((time.monotonic() - node_started) * 1000),
                pending=pending_call,
                remaining=remaining,
                asked_at=asked_at,
                asked_record_id=asked_record_id,
                occurrence=occurrence,
                node_id=node_id,
                sent=dict(sent),
            )

        ctx = AgentContext(
            run_id=run.run_id,
            node_id=node_id,
            workspace=run.workspace,
            seed=run.seed,
            budget=effective,
            tool_names=(*by_name, *delegates),
            step=0,
            item_index=item_index,
            conversation=_thread_view(run),
            _access_recorder=_access_recorder(run, execution, self),
        )

        writer = _ThreadWriter(ctx.conversation, run, node_id, item_index)
        if resume_state is None:
            messages = _as_messages(self.prompt(inputs, ctx))
            writer.opened(messages)
        else:  # noqa: PLR5501 - the resumed branch reads its state before it can open a turn
            messages = list(resume_state["messages"])
            made = [ToolCallSummary(**summary) for summary in resume_state["made"]]
            finish_attempts = [
                FinishAttempt(**attempt) for attempt in resume_state["finish_attempts"]
            ]
            node_calls = resume_state["calls"]
            node_tokens = resume_state["tokens"]
            node_cost = resume_state["cost"]
            step = resume_state["step"]
            already_ms = resume_state["elapsed_ms"]
            sent.update(resume_state.get("sent") or {})
            # The turn this run stopped inside is adopted here rather than at the prompt,
            # which a resumed execution does not run again.
            writer.resumed(messages)
            waiting = ToolCallRequest.from_record(resume_state["pending"])
            if waiting.name in delegates:
                # The run stopped inside the pipeline this subtask went to. It is finished
                # here, from the frames it stopped in, rather than being handed an answer:
                # nobody outside the delegate knows what it was going to return.
                outcome = self._delegate(
                    delegate=delegates[waiting.name],
                    call=waiting,
                    run=run,
                    model=model,
                    parent_id=record_id,
                    node_id=node_id,
                    invocation=sent[waiting.name],
                    made=made,
                    messages=messages,
                    started_at=resume_state["asked_at"],
                    resumed_from=resume_state["asked_record_id"],
                    frames=frames,
                    answer=answer,
                    item_index=item_index,
                )
                fold_spend(outcome)
            else:
                self._deliver(
                    run=run,
                    parent_id=record_id,
                    node_id=node_id,
                    call=waiting,
                    answer=answer,
                    tool=by_name.get(waiting.name),
                    made=made,
                    messages=messages,
                    asked_at=resume_state["asked_at"],
                    asked_record_id=resume_state["asked_record_id"],
                    occurrence=resume_state["occurrence"],
                    item_index=item_index,
                )
            # The calls the model asked for after the one that suspended have not run.
            # Dropping them would leave the assistant turn holding `tool_calls` with no
            # matching replies, which a backend refuses.
            pending = [ToolCallRequest.from_record(c) for c in resume_state["remaining"]]

        while True:
            if pending:
                # A turn the run stopped part-way through. Its calls are finished before the
                # model is asked anything else, or the conversation would carry an assistant
                # turn whose `tool_calls` have no matching replies.
                ordered, pending = pending, []
            else:
                tripped = _budget_tripped(
                    effective,
                    steps=node_calls,
                    tokens=node_tokens,
                    cost=node_cost,
                    wall_clock_ms=already_ms + int((time.monotonic() - node_started) * 1000),
                )
                if tripped is not None:
                    termination = tripped
                    break

                step += 1
                call = _call_model(
                    run=run,
                    model=model,
                    node_id=node_id,
                    parent_id=record_id,
                    # The full conversation, every turn. The context builder decides what of
                    # it is sent, and the loop keeps all of it either way, so a message left
                    # out of one call is still there for the next.
                    messages=list(messages),
                    context=self.context,
                    ctx=replace(ctx, step=step),
                    temperature=self.temperature,
                    max_output_tokens=self.max_output_tokens,
                    tools=wire_tools,
                    extra=self.extra,
                    stream=self.stream,
                    node_kind=self.node_kind,
                    item_index=item_index,
                )
                response = call.response
                node_calls += 1
                node_tokens += response.tokens.total
                if call.cost.value is not None:
                    node_cost = (node_cost or 0.0) + call.cost.value

                if not response.tool_calls:
                    # No tool call and no finish. The loop never infers an answer from
                    # prose, so this goes back to the model as a correction.
                    messages.append(_assistant_turn(response.content or "", response.reasoning))
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "That response contained no tool call. Call "
                                f"`{FINISH_TOOL_NAME}` with the final answer once it is "
                                "known, or call one of the other available tools."
                            ),
                        }
                    )
                    continue

                messages.append(
                    _assistant_turn(
                        response.content or "",
                        response.reasoning,
                        tool_calls=[c.to_record() for c in response.tool_calls],
                    )
                )

                # Every other tool runs before `finish`, whatever order the model asked in. A
                # turn may carry several calls, and a finish check asking "what did this run
                # read" has to see the reads made in the turn it is judging. A tool that can
                # suspend goes last too, so a stop lands on a turn boundary where it can, and
                # a delegation is there because anything inside the pipeline may suspend.
                ordered = sorted(
                    response.tool_calls,
                    key=lambda c: (
                        c.name == FINISH_TOOL_NAME,
                        c.name in delegates or self._may_suspend(by_name.get(c.name)),
                    ),
                )

            finished = False
            # The calls this node said may overlap run together, before the rest of the turn.
            # Each is answered as though it were made alone: they see the same `ctx.tool_calls`
            # and none sees another's result, which is what running at the same time means.
            done_early = self._overlap(
                ordered,
                run=run,
                node_id=node_id,
                record_id=record_id,
                by_name=by_name,
                ctx=replace(
                    ctx,
                    step=step,
                    tool_calls=tuple(made),
                    finish_attempts=tuple(finish_attempts),
                ),
                model=model,
                item_index=item_index,
                inputs=inputs,
            )
            for position, call in enumerate(ordered):
                at_step = replace(
                    ctx,
                    step=step,
                    tool_calls=tuple(made),
                    finish_attempts=tuple(finish_attempts),
                )
                if call.name == FINISH_TOOL_NAME:
                    outcome = _run_tool(
                        run=run,
                        parent_id=record_id,
                        node_id=node_id,
                        tool=finish_tool,
                        call=call,
                        validate=lambda args, c=at_step: self._accept(args, c),
                        item_index=item_index,
                        by_model=True,
                    )
                    if outcome.error is None:
                        outputs = outcome.value
                        termination = "finish"
                        finished = True
                        break
                    finish_attempts.append(
                        FinishAttempt(arguments=dict(call.arguments), rejection=str(outcome.error))
                    )
                    # A check refusing the same answer over and over teaches the model
                    # nothing it can act on, and the run ends with no result at all rather
                    # than the answer it refused. Stop, and say why.
                    repeats = sum(1 for a in finish_attempts if a.arguments == call.arguments)
                    if repeats >= MAX_IDENTICAL_FINISH_REJECTIONS:
                        termination = "finish_rejected"
                        finished = True
                        break
                    messages.append(_observation(call, outcome.error))
                    continue

                delegate = delegates.get(call.name)
                if delegate is not None:
                    if delegate.max_calls is not None and sent[call.name] >= delegate.max_calls:
                        messages.append(
                            _observation(
                                call,
                                f"{call.name!r} has already been sent "
                                f"{delegate.max_calls} subtasks, which is its limit. Do not "
                                f"send it another. Answer with what has already been found, "
                                f"and say what is still unknown.",
                            )
                        )
                        continue
                    sent[call.name] += 1
                    asked_at = utc_now()
                    try:
                        outcome = self._delegate(
                            delegate=delegate,
                            call=call,
                            run=run,
                            model=model,
                            parent_id=record_id,
                            node_id=node_id,
                            invocation=sent[call.name],
                            made=made,
                            messages=messages,
                            started_at=asked_at,
                            item_index=item_index,
                        )
                    except _Suspending as suspending:
                        # The subtask stopped inside the delegate. What this node holds goes
                        # on the exception so the frame above it can store it, and the
                        # subtask itself is what the resumed run finishes first.
                        suspending.node_state = captured_here(
                            pending_call=call,
                            remaining=ordered[position + 1 :],
                            asked_at=asked_at,
                            asked_record_id=suspending.delegation_record_id,
                            occurrence=None,
                        )
                        raise
                    fold_spend(outcome)
                    continue

                tool_obj = by_name.get(call.name)
                if tool_obj is None:
                    messages.append(
                        _observation(
                            call,
                            f"No tool named {call.name!r}. Available: "
                            f"{', '.join([*by_name, *delegates, FINISH_TOOL_NAME])}.",
                        )
                    )
                    continue

                asked_at = utc_now()
                try:
                    outcome = done_early.pop(id(call), None) or _run_tool(
                        run=run,
                        parent_id=record_id,
                        node_id=node_id,
                        tool=tool_obj,
                        call=call,
                        make_handles=self._handles_for(run, model, at_step, inputs),
                        item_index=item_index,
                        by_model=True,
                    )
                except Suspend as suspending:
                    suspending.node_state = captured_here(
                        pending_call=call,
                        remaining=ordered[position + 1 :],
                        asked_at=asked_at,
                        asked_record_id=suspending.asked_record_id,
                        occurrence=suspending.tool_occurrence,
                    )
                    raise
                fold_spend(outcome)
                made.append(
                    ToolCallSummary(
                        name=call.name,
                        arguments=dict(call.arguments),
                        ok=outcome.error is None,
                        result=outcome.value if outcome.error is None else outcome.error,
                    )
                )
                messages.append(
                    _observation(
                        call,
                        outcome.error if outcome.error is not None else outcome.value,
                    )
                )

            # As the node produces them: everything this iteration appended goes on the
            # thread before the next one starts, so a run killed mid-loop keeps what it did.
            writer.flush(messages)

            if finished:
                break

        writer.close(messages, outcome=termination or "completed", answered=outputs)
        return outputs, termination

    def _overlap(
        self,
        ordered: Sequence[Any],
        *,
        run: RunContext,
        node_id: str,
        record_id: str,
        by_name: dict[str, Tool],
        ctx: Any,
        model: ModelClient | None,
        inputs: Any,
        item_index: int | None = None,
    ) -> dict[int, Any]:
        """Run this turn's overlapping calls together, keyed by the call they answer.

        The calls named in ``concurrent_tools`` and asked for in this turn, up to the run's
        ceiling. Each records under the occurrence its position in the turn gives it, taken
        before any of them runs, so two identical calls keep the numbers they would have had
        in order and a replay serves each its own answer.

        Returns nothing where fewer than two of them were asked for, and the turn runs as it
        otherwise would.
        """
        chosen = [
            call
            for call in ordered
            if call.name in self.concurrent_tools
            and call.name in by_name
            and self._answers_in_process(by_name[call.name], run)
        ]
        if len(chosen) < 2:
            return {}

        occurrences = run.reserve_tool_occurrences(
            [(by_name[call.name], dict(call.arguments)) for call in chosen],
            node_id,
            item_index,
        )
        handles = self._handles_for(run, model, ctx, inputs)

        def unit(call: Any, occurrence: int) -> Any:
            return _run_tool(
                run=run,
                parent_id=record_id,
                node_id=node_id,
                tool=by_name[call.name],
                call=call,
                make_handles=handles,
                occurrence=occurrence,
                item_index=item_index,
                by_model=True,
            )

        outcomes = run.pool.map(
            [
                lambda call=call, occurrence=occurrence: unit(call, occurrence)
                for call, occurrence in zip(chosen, occurrences)
            ],
            limit=len(chosen),
            stops_on=lambda exc: True,
        )
        done: dict[int, Any] = {}
        for call, outcome in zip(chosen, outcomes):
            if outcome.error is not None:
                raise outcome.error
            if outcome.started:
                done[id(call)] = outcome.value
        return done

    def _accept_concurrent(self, named: Sequence[Tool] | None) -> tuple[str, ...]:
        """The tool names whose calls may overlap inside one turn, checked against this node.

        Refused where a name is not one of this node's tools, and where the tool writes: a run
        has one workspace directory and every node is handed the same one, so two writes at
        once can land on one path. A tool that can stop the run is refused too, because a stop
        has to land on a turn boundary.
        """
        if named is None:
            return ()
        by_name = {tool.name: tool for tool in self.tools}
        accepted: list[str] = []
        for tool in named:
            name = getattr(tool, "name", tool)
            mine = by_name.get(name)
            if mine is None:
                raise ConfigurationError(
                    f"AgentNode {self.node_id!r} lists {name!r} in concurrent_tools, and it "
                    f"is not one of this node's tools. This node offers "
                    f"{', '.join(repr(n) for n in by_name) or 'no tools'}.\n"
                    f"Name a tool this node was given, or add it to tools=."
                )
            if mine.side_effect_class is SideEffectClass.WRITES:
                raise ConfigurationError(
                    f"AgentNode {self.node_id!r} lists {name!r} in concurrent_tools, and "
                    f"{name!r} declares side_effect_class=WRITES. A run has one workspace "
                    f"directory and every node is handed the same one, so two of these calls "
                    f"running at the same time can write the same path, with no error at the "
                    f"time and a corrupt file afterwards.\n"
                    f"Drop {name!r} from concurrent_tools, and it runs after the calls that "
                    f"overlap. Where the writes go to separate paths and overlapping them is "
                    f"worth having, return the content from the tool and write it in a later "
                    f"node."
                )
            if self._may_suspend(mine) and getattr(mine.ask, "may_suspend", True) is not False:
                raise ConfigurationError(
                    f"AgentNode {self.node_id!r} lists {name!r} in concurrent_tools, and the "
                    f"channel it asks does not say whether it can stop the run to reach "
                    f"somebody. A run stops on a turn boundary, so a call that can stop it "
                    f"cannot overlap another.\n"
                    f"Where the channel answers in the process that asked, say so beside it: "
                    f"`ask.may_suspend = False`. SimulatedEndUser and unattended() declare it "
                    f"themselves. Where it can raise Suspend, drop {name!r} from "
                    f"concurrent_tools and the tools beside it still overlap."
                )
            accepted.append(name)
        return tuple(accepted)

    @staticmethod
    def _may_suspend(tool: Tool | None) -> bool:
        """Whether calling this tool can stop the run.

        True of a consultation whatever channel answers it, because the ordering this decides
        is fixed when the node is built and the channel is not. Sorting such a call to the end
        of its turn puts the stop on a turn boundary wherever the model asked for other work
        alongside it.
        """
        return isinstance(tool, ConsultTool)

    @staticmethod
    def _answers_in_process(tool: Tool | None, run: Any) -> bool:
        """Whether the channel answering this call can be overlapped with the calls beside it.

        A consultation overlaps only where the channel that will answer it says it never stops
        the run. The channel is the run's where a run supplied one, so a node built around a
        stand-in falls back to running its consultations one at a time when the same pipeline
        is run in front of a person.
        """
        if not isinstance(tool, ConsultTool):
            return True
        channel = getattr(run, "end_user", None)
        if isinstance(channel, Mapping):
            channel = channel.get(tool.reaches) if tool.reaches is not None else None
        return getattr(channel if channel is not None else tool.ask, "may_suspend", True) is False

    def _deliver(
        self,
        *,
        run: RunContext,
        parent_id: str,
        node_id: str,
        call: Any,
        answer: Any,
        tool: Tool | None,
        made: list[ToolCallSummary],
        messages: list[dict[str, Any]],
        asked_at: str,
        asked_record_id: str | None,
        occurrence: int | None,
        item_index: int | None = None,
    ) -> None:
        """Hand a resumed run the answer the call that suspended was waiting for.

        The call is not made again. What the answer is worth to the loop is what the tool
        would have returned, so it reaches the conversation and ``ctx.tool_calls`` the same
        way.
        """
        arguments = dict(call.arguments)
        answer = _delivered_answer(
            run=run,
            parent_id=parent_id,
            node_id=node_id,
            name=call.name,
            arguments=arguments,
            answer=answer,
            tool=tool,
            asked_at=asked_at,
            asked_record_id=asked_record_id,
            occurrence=occurrence,
            item_index=item_index,
        )
        made.append(ToolCallSummary(name=call.name, arguments=arguments, ok=True, result=answer))
        messages.append(_observation(call, answer))

    def _delegate(
        self,
        *,
        delegate: Delegation,
        call: Any,
        run: RunContext,
        model: ModelClient,
        parent_id: str,
        node_id: str,
        invocation: int,
        made: list[ToolCallSummary],
        messages: list[dict[str, Any]],
        started_at: str,
        resumed_from: str | None = None,
        frames: list[dict[str, Any]] | None = None,
        answer: Any = None,
        item_index: int | None = None,
    ) -> _ToolOutcome:
        """Run one subtask the model handed to a delegated pipeline.

        What the sub-pipeline spends is measured against the run's spend before and after, and
        comes back on the outcome so the calling node's budget bounds it. That is the same rule
        a model call inside a tool follows: one step is one model call, wherever it was made.

        The delegate's own budget running out is model-facing, since the model chose this
        subtask and can send a smaller one or answer with what it has. The run's budget running
        out is not, and propagates.
        """

        record_id = run.new_record_id()
        opened = run.spend
        sub_id = f"{node_id}.{delegate.name}"
        outputs: Any = None
        message: str | None = None
        error: dict[str, Any] | None = None
        termination = "completed"

        def close(kind: str) -> None:
            run.emit(
                DelegationRecord(
                    record_id=record_id,
                    run_id=run.run_id,
                    parent_id=parent_id,
                    sequence=PENDING_SEQUENCE,
                    started_at=started_at,
                    ended_at=None if kind == "suspended" else utc_now(),
                    node_id=sub_id,
                    invocation=invocation,
                    graph_fingerprint=delegate.pipeline.graph_fingerprint(),
                    inputs=call.arguments,
                    outputs=outputs,
                    termination=kind,
                    error=error,
                    resumed_from=resumed_from,
                    item_index=item_index,
                )
            )

        try:
            subtask = delegate.build_inputs(call.arguments)
        except ModelFacingError as exc:
            message = str(exc)
            error = error_object(exc, model_facing=True, retryable=exc.retryable)
            close("rejected")
            made.append(
                ToolCallSummary(
                    name=call.name, arguments=dict(call.arguments), ok=False, result=message
                )
            )
            messages.append(_observation(call, message))
            return _ToolOutcome(error=message)

        execution = Execution(
            node_id=sub_id,
            record_id=record_id,
            started_at=started_at,
            budget=run.remaining_budget(),
            seed=run.seed,
        )
        try:
            outputs = delegate.pipeline.execute(
                subtask,
                run,
                model,
                execution,
                frames=frames,
                answer=answer,
                parent_id=record_id,
            ).outputs
        except _Suspending as exc:
            # The record says the subtask stopped. The resumed run writes its own, naming this
            # one, so a reader can tell one subtask split in two from two subtasks.
            exc.delegation_record_id = record_id
            close("suspended")
            raise
        except BudgetExceeded as exc:
            # Whichever budget bound it, the run's is checked first: if that is the one that is
            # spent, this raises again and the run ends rather than the model being told to
            # carry on with nothing left to spend.
            _refuse_over_budget(run.budget, run.spend)
            termination = "budget"
            message = (
                f"The subtask sent to {delegate.name!r} stopped: its {exc.axis} budget is "
                f"spent. Send a smaller subtask, or answer with what has already been found "
                f"and say what is still unknown."
            )
            error = error_object(exc, model_facing=True)

        close(termination)
        spent = _spent_since(opened, run.spend)
        made.append(
            ToolCallSummary(
                name=call.name,
                arguments=dict(call.arguments),
                ok=message is None,
                result=message if message is not None else outputs,
            )
        )
        messages.append(_observation(call, message if message is not None else outputs))
        return _ToolOutcome(
            value=outputs,
            error=message,
            calls=spent.steps,
            tokens=spent.tokens,
            cost=spent.cost,
        )

    def _accept(self, arguments: dict[str, Any], ctx: AgentContext) -> Any:
        """Validate a finish payload, then put it to this node's finish check.

        A rejection is a :class:`ModelFacingError`, so it is recorded on the `finish` tool call
        and handed back to the model, which then has another turn to correct the answer.
        """
        value = self._finish.validate(arguments)
        if self.finish_check is None:
            return value
        rejection = self.finish_check(value, ctx)
        if rejection:
            raise ModelFacingError(str(rejection))
        return value

    def _handles_for(
        self, run: RunContext, model: ModelClient, ctx: AgentContext, inputs: Any
    ) -> Callable[[Tool, str, list[_CallResult]], dict[str, Any]]:
        """Build the handle arguments a tool's signature asks for.

        A ``ModelHandle`` makes its calls through the same path every model call goes through,
        parented to the tool call rather than to the node, so the tokens are attributable to
        the tool that spent them. A ``Workspace`` is the run's own directory. A ``NodeInput``
        is ``inputs``, which under ``over=`` is the item this execution is running.
        """

        def build(tool: Tool, record_id: str, sink: list[_CallResult]) -> dict[str, Any]:
            filled: dict[str, Any] = {}
            for param, kind in tool.handles.items():
                if issubclass(kind, Workspace):
                    filled[param] = Workspace(root=run.workspace)
                elif issubclass(kind, Memory):
                    filled[param] = _memory_handle(run, tool)
                elif issubclass(kind, Conversation):
                    filled[param] = _conversation_handle(run, tool)
                elif issubclass(kind, Retrieval):
                    filled[param] = _retrieval_handle(run, ctx.node_id, record_id, ctx.item_index)
                elif issubclass(kind, HostPolicy):
                    filled[param] = _fetch_policy_for(run, tool)
                elif issubclass(kind, NodeInput):
                    filled[param] = _node_input(tool, param, inputs, ctx.node_id)
                else:
                    filled[param] = ModelHandle(
                        _complete=self._nested_call(run, model, ctx, record_id, sink)
                    )
            return filled

        return build

    def _nested_call(
        self,
        run: RunContext,
        model: ModelClient,
        ctx: AgentContext,
        parent_id: str,
        sink: list[_CallResult],
    ) -> Callable[..., ModelResponse]:
        def complete(
            prompt: Any,
            *,
            output_schema: dict[str, Any] | None = None,
            temperature: float | None = None,
            max_output_tokens: int | None = None,
        ) -> ModelResponse:
            result = _call_model(
                run=run,
                model=model,
                node_id=ctx.node_id,
                parent_id=parent_id,
                messages=_as_messages(prompt),
                context=self.context,
                ctx=ctx,
                # The item whose loop called the tool. Without it two items' nested calls
                # share one counter, so the seed each is sent depends on which item reached
                # the tool first, and the call is attributable to no item afterwards.
                item_index=ctx.item_index,
                temperature=temperature if temperature is not None else self.temperature,
                max_output_tokens=(
                    max_output_tokens if max_output_tokens is not None else self.max_output_tokens
                ),
                output_schema=output_schema,
                extra=self.extra,
            )
            sink.append(result)
            return result.response

        return complete
