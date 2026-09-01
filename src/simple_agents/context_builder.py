"""What the model is sent on each call, as an object a project can replace.

Every model call is assembled by a context builder, under every node kind: an ``LLMNode``
builds once, a fan-out once per item, an ``AgentNode`` once per turn over the conversation so
far, and a tool holding a ``ModelHandle`` once over that call's own prompt.

``AppendAll`` is the default and sends everything it is given, dropping no message and
shortening none. ``DropOldestTurns`` sends the most recent turns and records the rest as
dropped. A project needing something else writes its own, declares the policy in the brief,
and reports each drop on the record, which is what FT-17 asks of it.

See ``docs/context.md`` for what overflow means, where a context window is published, and how
to write a context builder.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from typing import Any, Protocol

from .context import NodeContext
from .errors import CallerFacingError, SimpleAgentsWarning
from .schema import Unknown

__all__ = [
    "ContextBuilder",
    "ContextResult",
    "Dropped",
    "Estimate",
    "AppendAll",
    "DropOldestTurns",
    "ContextOverflow",
    "message_chars",
]


class ContextOverflow(CallerFacingError):
    """The request does not fit, so the run stops rather than sending less than was built.

    Raised in two places: by a context builder whose declared limit was passed, and by an
    adapter whose backend refused the request as longer than the model's context window.
    """


@dataclass(frozen=True, slots=True)
class Dropped:
    """One message a context builder left out, and why.

    Recorded verbatim on the ``model_call`` record. ``index`` is the position in the list the
    builder was handed::

        Dropped(index=3, role="tool", reason="oldest observation, over max_input_tokens")
    """

    index: int
    role: str
    reason: str

    def to_record(self) -> dict[str, Any]:
        return {"index": self.index, "role": self.role, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class Estimate:
    """A token count derived from characters, and the measurement it was derived from.

    Never a count. ``chars_per_token`` is what the previous call in this node actually
    exhibited, so the ratio is measured and the extrapolation from it is not. Inside a fan-out
    that call belongs to some item, which is not always the item being estimated: the ratio is
    a property of the node and the backend, and any of the node's calls measures it.
    """

    input_tokens: int
    limit: int
    chars_per_token: float
    measured_on_call: int
    measured_on_item: int | None = None
    """The fan-out item the measured call belonged to, and ``None`` outside one.
    ``measured_on_call`` counts within that item, so the pair names one call."""

    def to_record(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "limit": self.limit,
            "chars_per_token": round(self.chars_per_token, 3),
            "measured_on_call": self.measured_on_call,
            "measured_on_item": self.measured_on_item,
        }


@dataclass(frozen=True, slots=True)
class ContextResult:
    """What a builder produces: the messages to send, and anything it left out.

    ``messages`` goes on the wire and into the cassette key. ``dropped`` is empty when
    everything was sent, which is what makes a record say so rather than stay silent::

        return ContextResult(messages=list(messages))
    """

    messages: list[dict[str, Any]]
    dropped: tuple[Dropped, ...] = ()
    estimate: Estimate | None = None


class ContextBuilder(Protocol):
    """Decides what goes on the wire for one model call.

    ``messages`` is the conversation so far, in order, and ``ctx`` is the node's own view of
    the run. The return value is what gets sent; the loop keeps the full conversation either
    way, so leaving a message out of one call does not remove it from the next::

        class DropOldestTools:
            def build(self, messages, ctx: NodeContext) -> ContextResult:
                keep = [m for i, m in enumerate(messages) if i == 0 or m["role"] != "tool"]
                dropped = tuple(
                    Dropped(index=i, role=m["role"], reason="older tool observation")
                    for i, m in enumerate(messages) if m not in keep
                )
                return ContextResult(messages=keep, dropped=dropped)

    An implementation must hold no state between calls. One instance is shared across every
    call, every fan-out item, every node given the same instance, and every run of the
    pipeline, so a value stored on it leaks into all four. Everything a decision needs arrives
    in the arguments.

    ``to_manifest`` is optional and reports the settings the run was configured with.
    """

    def build(self, messages: list[dict[str, Any]], ctx: NodeContext) -> ContextResult: ...


@dataclass(frozen=True, slots=True)
class AppendAll:
    """Sends the whole conversation. The default, and it never shortens anything.

    ``max_input_tokens`` is an optional ceiling, checked before the call against an estimate::

        AppendAll()                          # the backend decides what does not fit
        AppendAll(max_input_tokens=200_000)  # stop before reaching the backend

    Read the number from the backend rather than guessing it: Mistral publishes
    ``max_context_length`` and vLLM publishes ``max_model_len``, both on ``GET /v1/models``.
    Leave headroom for the output, which the same window has to hold.

    **The check is an estimate, and it binds from the second call of a node onward.** Only a
    completed call reports a token count, so the ratio comes from the previous call in this
    node within this run. An ``AgentNode`` is checked from turn 2 and a fan-out from item 2. A
    node making one call per run is never checked, and the backend's refusal bounds it. A
    backend that reports no prompt size leaves the ceiling with nothing to check against, and
    the run warns once for that node.

    Passing the ceiling raises :class:`ContextOverflow`. A fan-out collects that item and
    carries on; anywhere else the run stops. Sending less instead means a context builder that
    drops, such as :class:`DropOldestTurns` (FT-17).
    """

    max_input_tokens: int | None = None

    def build(self, messages: list[dict[str, Any]], ctx: NodeContext) -> ContextResult:
        sent = list(messages)
        estimate = self._estimate(sent, ctx)
        if estimate is not None and estimate.input_tokens > estimate.limit:
            raise ContextOverflow(_over_limit_message(estimate, ctx))
        return ContextResult(messages=sent, estimate=estimate)

    def to_manifest(self) -> dict[str, Any]:
        return {"max_input_tokens": self.max_input_tokens}

    def _estimate(self, messages: list[dict[str, Any]], ctx: NodeContext) -> Estimate | None:
        """Extrapolate this list's token count from what the previous call in this node cost.

        ``None`` when no ceiling is set, when no call has completed yet, or when the backend
        left the prompt size unmeasured. An unmeasured quantity produces no estimate rather
        than a default ratio, and warns, because a ceiling that cannot be evaluated does not
        bind.
        """
        if self.max_input_tokens is None:
            return None
        tokens, chars = ctx.last_input_tokens, ctx.last_input_chars
        if isinstance(tokens, Unknown):
            # One warning per node: the text carries the node id, so Python's own registry
            # holds each node's warning down to its first occurrence.
            warnings.warn(
                _inert_ceiling_message(self.max_input_tokens, ctx.node_id),
                SimpleAgentsWarning,
                stacklevel=3,
            )
            return None
        if tokens is None or chars is None or tokens <= 0:
            return None
        ratio = chars / tokens
        return Estimate(
            input_tokens=int(message_chars(messages) / ratio),
            limit=self.max_input_tokens,
            chars_per_token=ratio,
            measured_on_call=ctx.last_call_index if ctx.last_call_index is not None else 0,
            measured_on_item=ctx.last_item_index,
        )


@dataclass(frozen=True, slots=True)
class DropOldestTurns:
    """Sends the first message and the most recent turns, and records what it left out.

    For a node whose conversation outgrows the window::

        node = AgentNode(prompt, tools=[search], output_schema=Answer, budget=budget,
                         context=DropOldestTurns(keep_turns=6))

    A turn is one assistant message and the tool observations answering it. Dropping stops at
    a turn boundary, so a tool observation is never sent without the assistant message that
    asked for it: a backend refuses that request rather than answering it. The first message
    is kept whatever ``keep_turns`` is, since it carries the prompt.

    Every message left out is a :class:`Dropped` entry on the ``model_call`` record, which is
    what FT-17 reads. Declare the policy in the brief: which observations a task can spare is
    a decision about the task.
    """

    keep_turns: int = 6

    def build(self, messages: list[dict[str, Any]], ctx: NodeContext) -> ContextResult:
        starts = [i for i, m in enumerate(messages) if i > 0 and m.get("role") != "tool"]
        if len(starts) <= self.keep_turns:
            return ContextResult(messages=list(messages))
        cut = starts[-self.keep_turns]
        return ContextResult(
            messages=[messages[0], *messages[cut:]],
            dropped=tuple(
                Dropped(index=i, role=str(messages[i].get("role")), reason="older than keep_turns")
                for i in range(1, cut)
            ),
        )

    def to_manifest(self) -> dict[str, Any]:
        return {"keep_turns": self.keep_turns}


def message_chars(messages: list[dict[str, Any]]) -> int:
    """Characters a message list serializes to, which is what an estimate is derived from.

    Counts the whole encoded request rather than the ``content`` fields alone, so tool calls
    and their arguments are included.
    """
    return len(json.dumps(messages, default=str))


def _inert_ceiling_message(limit: int, node_id: str) -> str:
    return (
        f"AppendAll(max_input_tokens={limit}) on node {node_id!r} has nothing to check "
        f"against: the backend reported no prompt size for the previous call in this node, "
        f"so there is no measured ratio to extrapolate from. The ceiling does not bind for "
        f"this node.\n"
        f"\n"
        f"A vLLM server reports the prompt size when it is started with "
        f"--enable-prompt-tokens-details (docs/model-clients/vllm.md §2). The backend's own "
        f"refusal still bounds every call."
    )


def _over_limit_message(estimate: Estimate, ctx: NodeContext) -> str:
    return (
        f"the message list is an estimated {estimate.input_tokens} prompt tokens, above "
        f"max_input_tokens={estimate.limit}. Nothing was sent.\n"
        f"\n"
        f"The estimate is characters divided by {estimate.chars_per_token:.1f} characters per "
        f"token, which is what {_measured_on(estimate)} of this node measured. It is "
        f"an estimate; an exact count is available only after a call.\n"
        f"\n"
        f"AppendAll drops nothing, so there is no shorter request to fall back to. What "
        f"should happen instead is a build-time decision: give the node less, fan out over it "
        f"with over='documents', raise max_input_tokens, or pass context= a "
        f"builder that drops what it can spare and reports each drop on the record (FT-17)."
    )


def _measured_on(estimate: Estimate) -> str:
    """Which call the ratio came from, naming its fan-out item where it had one.

    Inside a fan-out a call is numbered within its item, so the number alone names a call in
    every item rather than one call.
    """
    if estimate.measured_on_item is None:
        return f"call {estimate.measured_on_call}"
    return f"call {estimate.measured_on_call} of item {estimate.measured_on_item}"


def locate_overflow(exc: ContextOverflow, ctx: NodeContext, call_index: int) -> ContextOverflow:
    """The same refusal, saying which call it was and what became of the run.

    Both overflow paths pass through here, the builder's own ceiling and a backend refusing
    the request, so one message shape covers both. A fan-out collects the item and carries on;
    anywhere else the exception ends the run.
    """
    if ctx.item_index is not None:
        where = f"Node {ctx.node_id!r}, item {ctx.item_index}"
        outcome = (
            "\n\nThis item produced no output. It is recorded in the node's `failures` with "
            "its input, and the remaining items still run."
        )
    else:
        where = f"Node {ctx.node_id!r}, call {call_index}"
        outcome = "\n\nThe run stops here."
    return ContextOverflow(f"{where}: {exc}{outcome}")
