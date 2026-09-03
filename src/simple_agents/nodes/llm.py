"""A model call at a fixed point in fixed control flow."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Sequence
from ..records.conversation import ThreadWriter as _ThreadWriter, thread_view as _thread_view
from ..context import NodeContext, RunContext
from ..context_builder import AppendAll, ContextBuilder
from ..errors import ConfigurationError, Suspend
from ..graph import Loop, RetryPolicy
from ..prompting import text_shape
from ..records.manifest import source_version
from ..models import ModelClient
from ..schema import (
    require_a_schema_a_model_can_fill,
    require_unknown_branch,
    warn_literal_absence_union,
)
from ..tools import Tool, ToolRegistry, normalized_touches
from ..runtime.calls import _assistant_turn, _call_model, _json_schema, _prompt_of, _validate
from ..runtime.suspending import _Suspending
from ..runtime.tooling import _FixedPointCaller, _access_recorder
from .base import (
    Execution,
    NodeOutcome,
    _declare_edges,
    _declare_planned,
    _declared_tools,
    _not_built_entry,
    _not_built_message,
    model_for,
)
from .fanout import _declare_fan_out, _fan_out


class LLMNode:
    """A model call at a fixed point in fixed control flow. One call, one place, one shape.

    The caller supplies a function returning a `Prompt`, which is fixed text with named values
    (`docs/prompts.md`); the library makes the call and validates the response against
    ``output_schema``. A step whose next action depends on what the model returned is an
    ``AgentNode``::

        class Answer(BaseModel):
            answer: Maybe[str]

        def build_prompt(inputs: dict, ctx: NodeContext) -> Prompt:
            return Prompt.user("Answer using only these documents: {docs}", docs=inputs["docs"])

        node = LLMNode(build_prompt, output_schema=Answer)

    ``output_schema`` must admit ``unknown`` unless ``allow_unknown=False``. Backend-specific
    options such as guided decoding go in ``extra``. ``model`` is the client this node calls,
    overriding ``Pipeline.run(model=...)``::

        node = LLMNode(reduce_notes, output_schema=Notes, model=cheap)

    ``over`` names an input key holding a sequence and makes the same call once per item,
    returning a :class:`FanOutResult`::

        node = LLMNode(summarise, output_schema=Summary, over="documents")

    A fan-out returns the outcomes and nothing else. ``keep`` names input keys that travel on
    with them, reaching the next node as ``FanOutResult.kept``::

        node = LLMNode(summarise, output_schema=Summary, over="documents",
                       keep=["question", "unreadable"])

    ``concurrent_items`` runs that many items at once, up to the run's ``concurrency``::

        node = LLMNode(summarise, output_schema=Summary, over="documents",
                       concurrent_items=8)

    ``tools`` are what the prompt function may call through ``ctx.call_tool``::

        def build_prompt(inputs, ctx):
            page = ctx.call_tool("http_fetch", url=inputs["url"])
            return Prompt.user("Summarise this page: {page}", page=page)

        node = LLMNode(build_prompt, output_schema=Summary, tools=[http_fetch()])

    ``stream=True`` delivers this node's output as it is produced, to the callback
    ``Pipeline.run(on_token=...)`` was given. The response is validated when it is complete,
    the same way::

        node = LLMNode(reply, output_schema=Answer, stream=True)

    A run given no ``on_token`` makes an ordinary call whatever the node declares. With an
    ``output_schema`` set the pieces are fragments of JSON rather than prose.
    """

    node_kind = "llm"

    def __init__(
        self,
        prompt: Callable[[Any, NodeContext], Any],
        *,
        output_schema: Any,
        tools: Sequence[Tool] | ToolRegistry = (),
        touches: str | Sequence[str] | None = None,
        node_id: str | None = None,
        prompt_version: str | None = None,
        allow_unknown: bool = True,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
        over: str | None = None,
        keep: Sequence[str] | None = None,
        max_failures: int | None = None,
        concurrent_items: int | None = None,
        stream: bool = False,
        model: ModelClient | None = None,
        context: ContextBuilder | None = None,
        successors: Sequence[str] | None = None,
        route: Callable[[Any, Any], Any] | None = None,
        loop: Loop | None = None,
        on_error: str | None = None,
        retry: RetryPolicy | None = None,
        suspend_before: bool = False,
    ) -> None:
        self.prompt = prompt
        self.planned = _declare_planned(self, prompt, node_id, "LLMNode")
        self.output_schema = output_schema
        self.node_id = node_id if self.planned else (node_id or prompt.__name__)
        self.prompt_version = prompt_version
        self.prompt_entry = (
            _not_built_entry(prompt)
            if self.planned
            else {
                **source_version(prompt, prompt_version, text=True),
                "text": text_shape(prompt),
            }
        )
        self.touches = normalized_touches(touches, where=f"LLMNode {self.node_id!r}")
        self.tools = _declared_tools(self, tools)
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
        # Retained rather than only checked: the value is written to the run manifest, so
        # the waiver is visible to a reader of the results.
        self.allow_unknown = allow_unknown
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.extra = extra or {}
        self.stream = stream

        _declare_fan_out(
            self,
            over=over,
            keep=keep,
            max_failures=max_failures,
            concurrent_items=concurrent_items,
            retry=retry,
        )

        # A planned node may leave the schema unsettled; the view shows the absence. A schema
        # that is declared is checked whether the node is planned or not.
        if not (self.planned and output_schema is None):
            require_a_schema_a_model_can_fill(
                output_schema, where=f"Node {self.node_id!r}", argument="output_schema"
            )
            require_unknown_branch(
                output_schema, node_name=self.node_id, allow_unknown=allow_unknown
            )
            warn_literal_absence_union(output_schema, node_name=self.node_id)

    def execute(
        self,
        inputs: Any,
        run: RunContext,
        model: ModelClient | None = None,
        execution: Execution | None = None,
        resume_state: dict[str, Any] | None = None,
        answer: Any = None,
    ) -> NodeOutcome:
        """Make the call, or one call per item where the node fans out.

        ``model`` is the run's client, used where this node declares none of its own.

        ``resume_state`` is what a fan-out had finished when a run stopped part-way through
        it. A single call holds nothing worth keeping, so it is made again. Both come from the
        pipeline; a caller supplies neither.
        """
        if self.planned:
            raise ConfigurationError(_not_built_message(self))
        model = model_for(self, model)
        if model is None:
            # A ConfigurationError rather than a bare CallerFacingError: it fails
            # identically on every rollout, so an evaluation stops on the first
            # rather than recording k x n agent failures.
            raise ConfigurationError(
                f"Node {self.node_id!r} is an LLMNode but the pipeline was run without a "
                f"model client and the node declares none.\n"
                f"Pass one to Pipeline.run(model=...), or to this node as "
                f"LLMNode(..., model=client)."
            )
        execution = execution if execution is not None else Execution.for_node(self, run)
        ctx = NodeContext(
            run_id=run.run_id,
            node_id=execution.node_id,
            workspace=run.workspace,
            run_inputs=run.run_inputs,
            seed=run.seed,
            budget=execution.budget,
            conversation=_thread_view(run),
            fetch_policy=run.node_fetch_policy(),
            _access_recorder=_access_recorder(run, execution, self),
        )
        if self.over is not None:
            outputs: Any = _fan_out(
                self,
                inputs=inputs,
                run=run,
                ctx=ctx,
                execution=execution,
                one=lambda item_inputs, item_ctx, index, held, given: (
                    self._one(
                        item_inputs,
                        run,
                        model,
                        item_ctx,
                        execution,
                        item_index=index,
                        resume_state=held,
                        answer=given,
                    ),
                    None,
                ),
                resume_state=resume_state,
                answer=answer,
            )
        else:
            outputs = self._one(
                inputs, run, model, ctx, execution, resume_state=resume_state, answer=answer
            )
        return NodeOutcome(outputs=outputs)

    def _one(
        self,
        inputs: Any,
        run: RunContext,
        model: ModelClient,
        ctx: Any,
        execution: Execution,
        item_index: int | None = None,
        resume_state: dict[str, Any] | None = None,
        answer: Any = None,
    ) -> Any:
        # A caller per item, so an item resumed with an answer reaches the call it stopped on
        # and no other item is handed it.
        if self.tools:
            ctx = replace(
                ctx,
                _tool_caller=_FixedPointCaller(
                    run=run,
                    node_id=execution.node_id,
                    parent_id=execution.record_id,
                    tools=self.tools,
                    waiting=resume_state,
                    answer=answer,
                    item_index=item_index,
                    inputs=inputs,
                ),
            )
        messages, assembly = _prompt_of(
            self.prompt(inputs, ctx), where=f"The prompt function of node {execution.node_id!r}"
        )
        writer = _ThreadWriter(ctx.conversation, run, execution.node_id, item_index)
        writer.opened(messages)
        try:
            call = _call_model(
                run=run,
                model=model,
                node_id=execution.node_id,
                parent_id=execution.record_id,
                item_index=item_index,
                messages=messages,
                assembly=assembly,
                context=self.context,
                ctx=ctx,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                output_schema=_json_schema(self.output_schema),
                extra=self.extra,
                stream=self.stream,
                node_kind=self.node_kind,
            )
        except (Suspend, _Suspending):
            # The run stopped to ask somebody and will continue. Its turn stays open, so the
            # answer it eventually gives lands in the turn that asked the question.
            raise
        except BaseException:
            # The turn stays on the thread carrying what was asked, so the next turn is not
            # answering a person whose message the conversation never recorded.
            writer.close(messages, outcome="error")
            raise
        answer = _validate(self.output_schema, call.response.content)
        writer.close(
            [*messages, _assistant_turn(call.response.content or "", call.response.reasoning)],
            outcome="completed",
            answered=call.response.content,
        )
        return answer
