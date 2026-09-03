"""A step that is ordinary code: no model, full recording."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Sequence
from ..records.conversation import thread_view as _thread_view
from ..context import NodeContext, RunContext
from ..errors import CallerFacingError, ConfigurationError
from ..graph import Loop, RetryPolicy
from ..records.manifest import source_version
from ..models import ModelClient
from ..tools import Tool, ToolRegistry, normalized_touches
from ..runtime.calls import _validated_output
from ..runtime.tooling import _FixedPointCaller, _access_recorder
from .base import (
    Execution,
    NodeOutcome,
    NotBuilt,
    _declare_edges,
    _declare_planned,
    _declared_tools,
    _not_built_entry,
    _not_built_message,
)
from .fanout import _declare_fan_out, _fan_out


class Deterministic:
    """Plain code. The function makes no model call, and is handed nothing that can make one.

    The function is handed a :class:`~simple_agents.context.NodeContext` with no model client.
    The cheapest node kind, and most of a pipeline: parsing, filtering, arithmetic, I/O::

        def load_docs(inputs: dict, ctx: NodeContext) -> str:
            return Path(inputs["corpus"]).read_text()

        node = Deterministic(load_docs)

    ``tools`` are the tools this node may call, reached through ``ctx.call_tool`` and recorded
    like any other call. A tool reached any other way is not. A call the model chooses to make
    is an ``AgentNode``, and a tool taking a ``ModelHandle`` is refused here::

        def fetch_the_page(inputs: dict, ctx: NodeContext) -> str:
            return ctx.call_tool("http_fetch", url=inputs["url"])

        node = Deterministic(fetch_the_page, tools=[http_fetch()])

    ``ctx.workspace`` is a fresh directory per run. Read a corpus from wherever it lives;
    write derived files there, beside the trajectory that records what the run did with them.

    ``output_schema`` says what the function returns. It is optional, and what needs it is a run
    that suspends: a resumed run rebuilds each value in flight from the schema its node
    declared, so a node with none has to return plain data to cross a suspend point::

        node = Deterministic(load_notes, output_schema=Notes)

    The value is validated against it on the way out, so a function returning something else
    fails where it was produced rather than in the node that receives it.

    ``over`` calls the function once per item of an input key holding a sequence, and a
    failed item is collected rather than ending the run::

        node = Deterministic(parse_one, over="pages", max_failures=2)

    ``version`` defaults to a hash of the function's source, so an edit names another evaluation
    directory. Declare one where the function reads data that changes underneath it::

        node = Deterministic(read_library, version="characterised-2026-08")
    """

    node_kind = "deterministic"

    def __init__(
        self,
        fn: Callable[[Any, NodeContext], Any] | NotBuilt,
        *,
        node_id: str | None = None,
        version: str | None = None,
        output_schema: Any = None,
        tools: Sequence[Tool] | ToolRegistry = (),
        touches: str | Sequence[str] | None = None,
        over: str | None = None,
        keep: Sequence[str] | None = None,
        max_failures: int | None = None,
        concurrent_items: int | None = None,
        successors: Sequence[str] | None = None,
        route: Callable[[Any, Any], Any] | None = None,
        loop: Loop | None = None,
        on_error: str | None = None,
        retry: RetryPolicy | None = None,
        suspend_before: bool = False,
    ):
        self.fn = fn
        self.version = version
        self.planned = _declare_planned(self, fn, node_id, "Deterministic")
        self.fn_entry = _not_built_entry(fn) if self.planned else source_version(fn, version)
        self.output_schema = output_schema
        self.node_id = node_id if self.planned else (node_id or fn.__name__)
        self.touches = normalized_touches(touches, where=f"Deterministic node {self.node_id!r}")
        self.tools = _declared_tools(self, tools)
        _declare_edges(
            self,
            successors=successors,
            route=route,
            loop=loop,
            on_error=on_error,
            retry=retry,
            suspend_before=suspend_before,
        )
        _declare_fan_out(
            self,
            over=over,
            keep=keep,
            max_failures=max_failures,
            concurrent_items=concurrent_items,
            retry=retry,
        )

    def execute(
        self,
        inputs: Any,
        run: RunContext,
        model: ModelClient | None = None,
        execution: Execution | None = None,
        resume_state: dict[str, Any] | None = None,
        answer: Any = None,
    ) -> NodeOutcome:
        """Run the function, and on a resumed run hand the call that stopped its answer.

        ``resume_state`` and ``answer`` come from the pipeline; a caller supplies neither.
        The function runs again from the beginning, so the tool calls it made before the one
        that stopped are made again.
        """
        if self.planned:
            raise ConfigurationError(_not_built_message(self))
        execution = execution if execution is not None else Execution.for_node(self, run)
        if self.over is None:
            return NodeOutcome(
                outputs=self._validated(
                    self._called(inputs, None, run, execution, resume_state, answer)
                )
            )
        seed_ctx = NodeContext(
            run_id=run.run_id,
            node_id=execution.node_id,
            workspace=run.workspace,
            run_inputs=run.run_inputs,
            # deterministic nodes do not sample; `docs/trajectory-format.md` §3 requires null
            seed=None,
            budget=execution.budget,
            conversation=_thread_view(run),
            fetch_policy=run.node_fetch_policy(),
            _access_recorder=_access_recorder(run, execution, self),
        )
        return NodeOutcome(
            outputs=_fan_out(
                self,
                inputs=inputs,
                run=run,
                ctx=seed_ctx,
                execution=execution,
                one=lambda item_inputs, item_ctx, index, held, given: (
                    self._validated(
                        self._called(item_inputs, item_ctx, run, execution, held, given)
                    ),
                    None,
                ),
                resume_state=resume_state,
                answer=answer,
            )
        )

    def _called(
        self,
        inputs: Any,
        ctx: NodeContext | None,
        run: RunContext,
        execution: Execution,
        resume_state: dict[str, Any] | None,
        answer: Any,
    ) -> Any:
        """One call of the function: the whole node, or one item of a fan-out.

        Each gets its own tool caller, so an item resumed with an answer reaches the call it
        stopped on and no other item is handed it.
        """
        caller = (
            _FixedPointCaller(
                run=run,
                node_id=execution.node_id,
                parent_id=execution.record_id,
                tools=self.tools,
                waiting=resume_state,
                answer=answer,
                # One item of a fan-out is handed a context naming which item it is, and
                # `ctx` is None on a node that does not fan out.
                item_index=getattr(ctx, "item_index", None),
                inputs=inputs,
            )
            if self.tools
            else None
        )
        base = (
            ctx
            if ctx is not None
            else NodeContext(
                run_id=run.run_id,
                node_id=execution.node_id,
                workspace=run.workspace,
                run_inputs=run.run_inputs,
                # deterministic nodes do not sample; `docs/trajectory-format.md` §3 requires null
                seed=None,
                budget=execution.budget,
                conversation=_thread_view(run),
                fetch_policy=run.node_fetch_policy(),
                _access_recorder=_access_recorder(run, execution, self),
            )
        )
        outputs = self.fn(inputs, replace(base, _tool_caller=caller))
        if caller is not None and not caller.delivered:
            waiting = resume_state or {}
            raise CallerFacingError(
                f"Node {self.node_id!r} was resumed with an answer for its call to "
                f"{waiting.get('tool')!r}, and the function returned without making that "
                f"call. A resumed node runs again from the beginning, so the answer reaches "
                f"the call at the position the run stopped on, and this run made "
                f"{caller.number} call(s) before returning.\n"
                f"Make the function reach the same call from the same inputs, or hold the "
                f"work that varies in an AgentNode, which is resumed from the conversation "
                f"it had rather than by running again."
            )
        return outputs

    def _validated(self, outputs: Any) -> Any:
        """The function's return, checked against ``output_schema`` where one is declared."""
        if self.output_schema is None:
            return outputs
        return _validated_output(outputs, self.output_schema, self.node_id)
