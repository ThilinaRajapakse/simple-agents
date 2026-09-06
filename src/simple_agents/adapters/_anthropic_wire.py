"""The parts of Anthropic's Messages API the adapter translates to and from.

Nothing here is shared with ``_openai_wire``: the two dialects agree on no field. A message
is a list of typed content blocks, a tool call is a ``tool_use`` block and its result a
``tool_result`` block inside a ``user`` turn, the system prompt is a top-level field, the
chain of thought is a signed ``thinking`` block the next request returns verbatim, and the
usage block splits a cache write by the TTL it was written at.

Measured against ``api.anthropic.com`` on 2026-09-06, and read against the provider's
documentation the same day.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from ..errors import CallerFacingError, ConfigurationError
from ..models import RateLimit, Reasoning, TokenUsage, ToolCallRequest
from ..schema import Unknown
from ._openai_wire import strict_schema

__all__ = [
    "ANTHROPIC_VERSION",
    "CACHE_MARK",
    "messages_from",
    "tools_from",
    "output_config_for",
    "content_from",
    "tool_calls_from",
    "reasoning_from",
    "tokens_from",
    "rate_limit_from",
    "RATE_LIMIT_HEADERS",
    "StreamAssembler",
]

ANTHROPIC_VERSION = "2023-06-01"

# The key a prompt sets with `Prompt.marked(cache_control=...)`. It sits on the message in
# the library's shape and on a content block in this backend's, so the adapter moves it.
CACHE_MARK = "cache_control"

_REASONING_BLOCKS = ("thinking", "redacted_thinking")


def messages_from(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Translate the conversation the loop built into ``messages``, and the system blocks.

    A ``system`` message becomes a text block in the top-level ``system`` list. A ``user``
    message becomes a turn of one text block, or of the blocks it already carries where the
    prompt was built with ``Prompt.blocks``. An assistant turn carries its reasoning blocks
    back exactly as they arrived, then its text, then one ``tool_use`` block per call.
    Consecutive tool results become one ``user`` turn of ``tool_result`` blocks, which is
    how this backend takes the results of parallel calls::

        turns, system = messages_from([
            {"role": "system", "content": "Answer briefly.",
             "cache_control": {"type": "ephemeral"}},
            {"role": "user", "content": "Which retailer is in Kirkwall?"},
            {"role": "assistant", "content": "",
             "reasoning_blocks": [{"type": "thinking", "thinking": "...",
                                   "signature": "Ep0C..."}],
             "tool_calls": [{"id": "toolu_1", "name": "lookup",
                             "arguments": {"town": "Kirkwall"}}]},
            {"role": "tool", "tool_call_id": "toolu_1", "content": "Kirkwall Hardware"},
        ])

    **A cache mark moves from the message onto its last block**, since that is where this
    backend reads it. Every mark in one request has to name one TTL: the record holds one
    ``cache_ttl`` per call, so a request that wrote at both is refused with a
    ``ConfigurationError`` rather than recorded as a sum no basis can price.

    **Reasoning blocks are sent back unchanged.** This backend rejects a turn whose thinking
    blocks were edited, reordered or partly dropped, and a signature it cannot verify with
    them. A ``reasoning`` string carried from another backend has no block to travel in and
    is left out.
    """
    marks = _Marks()
    turns: list[dict[str, Any]] = []
    system: list[dict[str, Any]] = []

    for message in messages:
        role = message.get("role")
        if role == "system":
            system.append(
                marks.attach({"type": "text", "text": str(message.get("content") or "")}, message)
            )
        elif role == "tool":
            _append_tool_result(turns, marks.attach(_tool_result_block(message), message))
        else:
            blocks = _assistant_blocks(message) if role == "assistant" else _user_blocks(message)
            if not blocks:
                # A turn that said nothing and called nothing has no block this backend
                # accepts, and an empty text block is refused. The turn after it still
                # reads correctly without it.
                continue
            blocks[-1] = marks.attach(blocks[-1], message)
            turns.append(
                {"role": "assistant" if role == "assistant" else "user", "content": blocks}
            )

    marks.refuse_if_mixed()
    for turn in turns:
        turn.pop("_results", None)
    return turns, (system or None)


class _Marks:
    """Moves each message's cache mark onto a block, and remembers which TTLs it saw."""

    def __init__(self) -> None:
        self.ttls: set[str] = set()

    def attach(self, block: dict[str, Any], message: Mapping[str, Any]) -> dict[str, Any]:
        mark = message.get(CACHE_MARK)
        if not isinstance(mark, Mapping):
            return block
        self.ttls.add(str(mark.get("ttl") or "5m"))
        return {**block, CACHE_MARK: dict(mark)}

    def refuse_if_mixed(self) -> None:
        if len(self.ttls) > 1:
            raise ConfigurationError(
                f"The prompt marks its messages for caching at more than one TTL "
                f"({', '.join(sorted(self.ttls))}). A call's record holds one cache_ttl, "
                f"priced by the rate declared for it, and a write split across two TTLs "
                f"cannot be priced. Mark every message in the prompt with the same ttl."
            )


def _tool_result_block(message: Mapping[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    return {
        "type": "tool_result",
        "tool_use_id": message.get("tool_call_id"),
        "content": str(content if content is not None else ""),
    }


def _append_tool_result(turns: list[dict[str, Any]], block: dict[str, Any]) -> None:
    """Add a result to the open turn of results, or open one."""
    if turns and turns[-1].get("_results"):
        turns[-1]["content"].append(block)
    else:
        turns.append({"role": "user", "content": [block], "_results": True})


def _assistant_blocks(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    blocks = [dict(block) for block in message.get("reasoning_blocks") or []]
    content = message.get("content")
    if isinstance(content, str) and content:
        blocks.append({"type": "text", "text": content})
    elif isinstance(content, list):
        blocks.extend(dict(one) for one in content)
    for call in message.get("tool_calls") or []:
        blocks.append(
            {
                "type": "tool_use",
                "id": call["id"],
                "name": call["name"],
                "input": _arguments(call.get("arguments")),
            }
        )
    return blocks


def _user_blocks(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    content = message.get("content")
    if isinstance(content, list):
        return [dict(one) for one in content]
    return [{"type": "text", "text": str(content or "")}]


def _arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return dict(value or {})


def tools_from(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate the library's tool declarations into this backend's, which take the same
    three fields under the same names::

        tools_from([{"name": "search", "description": "...", "input_schema": {...}}])
    """
    return [
        {
            "name": tool["name"],
            "description": tool.get("description") or "",
            "input_schema": tool.get("input_schema") or {"type": "object", "properties": {}},
        }
        for tool in tools
    ]


def output_config_for(output_schema: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The ``output_config`` that constrains a response to ``output_schema``, or ``None``.

    The schema is sent in the form ``strict_schema`` produces: every property required,
    ``additionalProperties`` false, no defaults. That is the form this backend's structured
    output was measured to accept.
    """
    if not output_schema:
        return None
    return {"format": {"type": "json_schema", "schema": strict_schema(output_schema)}}


def content_from(blocks: Iterable[Mapping[str, Any]]) -> str | None:
    """The answer text across the response's text blocks, or ``None`` where there is none."""
    text = "".join(str(block.get("text") or "") for block in blocks if block.get("type") == "text")
    return text or None


def tool_calls_from(blocks: Iterable[Mapping[str, Any]]) -> list[ToolCallRequest]:
    """The ``tool_use`` blocks in a response.

    Arguments arrive as an object under ``input``, so nothing is parsed. Anything other than
    an object raises: the library has no channel for correcting a malformed tool call.
    """
    calls: list[ToolCallRequest] = []
    for index, block in enumerate(blocks):
        if block.get("type") != "tool_use":
            continue
        arguments = block.get("input")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise CallerFacingError(
                f"Anthropic returned tool call {index} for {block.get('name')!r} whose "
                f"arguments are {type(arguments).__name__}, not an object: "
                f"{str(arguments)[:200]!r}"
            )
        calls.append(
            ToolCallRequest(
                id=str(block.get("id") or f"call_{index}"),
                name=str(block.get("name") or ""),
                arguments=arguments,
            )
        )
    return calls


def reasoning_from(blocks: Iterable[Mapping[str, Any]]) -> Reasoning | None:
    """The thinking blocks, as text and as the blocks to send back.

    ``text`` is the ``thinking`` field joined across the blocks: a summary under
    ``display: "summarized"``, empty under the default ``"omitted"`` and so ``None`` here. A
    ``redacted_thinking`` block has no text at all. ``blocks`` holds each block as it
    arrived, signature included, which is what the next turn sends back. ``None`` where the
    response carried no thinking block.
    """
    found = [dict(block) for block in blocks if block.get("type") in _REASONING_BLOCKS]
    if not found:
        return None
    text = "".join(str(block.get("thinking") or "") for block in found)
    return Reasoning(text=text or None, blocks=tuple(found))


def tokens_from(usage: Mapping[str, Any]) -> TokenUsage:
    """Map the usage block onto the recorded breakdown.

    ``input_tokens`` is already the uncached count: the provider reports the cache read and
    the cache write beside it rather than inside it. The write is split by TTL under
    ``cache_creation``, and ``cache_ttl`` is the one it was written at.
    ``output_tokens_details.thinking_tokens`` is the reasoning share of ``output_tokens``.
    """
    prompt = usage.get("input_tokens")
    output = usage.get("output_tokens")
    details = usage.get("output_tokens_details")
    thought = details.get("thinking_tokens") if isinstance(details, Mapping) else None
    generated: int | Unknown = output if isinstance(output, int) else Unknown(reason="not reported")
    reasoning = thought if isinstance(thought, int) else None

    if not isinstance(prompt, int):
        unmeasured = Unknown(reason="the response reported no input_tokens")
        return TokenUsage(
            input_uncached=unmeasured,
            input_cache_read=unmeasured,
            input_cache_write=unmeasured,
            cache_ttl=None,
            output=generated,
            output_reasoning=reasoning,
        )

    read = usage.get("cache_read_input_tokens")
    write, ttl = _cache_write(usage)
    return TokenUsage(
        input_uncached=prompt,
        input_cache_read=read
        if isinstance(read, int)
        else Unknown(reason="the response reported no cache_read_input_tokens"),
        input_cache_write=write,
        cache_ttl=ttl,
        output=generated,
        output_reasoning=reasoning,
    )


def _cache_write(usage: Mapping[str, Any]) -> tuple[int | Unknown, str | None]:
    """The cache-write count and the TTL it was written at."""
    written = usage.get("cache_creation_input_tokens")
    if not isinstance(written, int):
        return Unknown(reason="the response reported no cache_creation_input_tokens"), None
    split = usage.get("cache_creation")
    if not written or not isinstance(split, Mapping):
        return written, None
    at = [
        name
        for name, count in (
            ("5m", split.get("ephemeral_5m_input_tokens")),
            ("1h", split.get("ephemeral_1h_input_tokens")),
        )
        if isinstance(count, int) and count
    ]
    if len(at) > 1:
        return (
            Unknown(
                reason="the response reported a cache write split across two TTLs, which one "
                "cache_ttl cannot carry"
            ),
            None,
        )
    return written, (at[0] if at else None)


RATE_LIMIT_HEADERS = (
    "anthropic-ratelimit-requests-remaining",
    "anthropic-ratelimit-tokens-remaining",
    "anthropic-ratelimit-requests-reset",
    "anthropic-ratelimit-tokens-reset",
)


def rate_limit_from(headers: Mapping[str, str], now: float | None = None) -> RateLimit | None:
    """What the response said is left of the window.

    Published on every response as remaining requests and remaining tokens, the latter for
    the most restrictive token limit in force, and a reset instant for each in RFC 3339.
    ``resets_in_s`` is the later of the two, measured from ``now``. ``None`` where the
    response carried none of them.
    """
    requests = _int_or_none(headers.get("anthropic-ratelimit-requests-remaining"))
    tokens = _int_or_none(headers.get("anthropic-ratelimit-tokens-remaining"))
    resets = [
        seconds
        for seconds in (
            _seconds_until(headers.get("anthropic-ratelimit-requests-reset"), now),
            _seconds_until(headers.get("anthropic-ratelimit-tokens-reset"), now),
        )
        if seconds is not None
    ]
    if requests is None and tokens is None and not resets:
        return None
    return RateLimit(
        remaining_requests=requests,
        remaining_tokens=tokens,
        resets_in_s=max(resets) if resets else None,
    )


def _seconds_until(value: str | None, now: float | None) -> float | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    current = datetime.now(timezone.utc).timestamp() if now is None else now
    return max(0.0, moment.timestamp() - current)


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


class StreamAssembler:
    """Builds one response out of the events a streamed call arrives in.

    A ``message_start`` carries the model and the input counts, each content block opens,
    delivers deltas and closes under its index, and a ``message_delta`` carries the stop
    reason and the cumulative output counts. A thinking block streams its text as
    ``thinking_delta`` events and its signature as one ``signature_delta``; a ``tool_use``
    block streams its arguments as ``input_json_delta`` fragments::

        assembler = StreamAssembler(on_content=on_chunk, on_reasoning=on_thought)
        backend.post_stream("/messages", {**payload, "stream": True}, assembler.feed)
        assembler.content_blocks()   # the blocks, in the shape a plain response carries
        assembler.usage        # the input and output counts, merged

    ``on_content`` is called with each piece of the answer and with nothing else, since a
    recording's chunk boundaries are offsets into ``content``. An ``error`` event raises,
    since the stream then carries no response.
    """

    def __init__(self, on_content: Any, on_reasoning: Any = None) -> None:
        self.on_content = on_content
        self.on_reasoning = on_reasoning
        self.model: str | None = None
        self.stop_reason: str | None = None
        self.usage: dict[str, Any] | None = None
        self._blocks: dict[int, dict[str, Any]] = {}

    def feed(self, event: Mapping[str, Any]) -> None:
        """Take one server-sent event. Events of a kind this does not read are skipped."""
        handler = getattr(self, f"_on_{event.get('type')}", None)
        if handler is not None:
            handler(event)

    def _on_message_start(self, event: Mapping[str, Any]) -> None:
        message = event.get("message") or {}
        if message.get("model"):
            self.model = str(message["model"])
        self._merge_usage(message.get("usage"))

    def _on_content_block_start(self, event: Mapping[str, Any]) -> None:
        index = int(event.get("index", len(self._blocks)))
        block = dict(event.get("content_block") or {})
        if block.get("type") == "tool_use":
            block["_partial"] = ""
        self._blocks[index] = block

    def _on_content_block_delta(self, event: Mapping[str, Any]) -> None:
        block = self._blocks.setdefault(int(event.get("index", 0)), {"type": "text", "text": ""})
        delta = event.get("delta") or {}
        take = getattr(self, f"_take_{delta.get('type')}", None)
        if take is not None:
            take(block, delta)

    def _on_message_delta(self, event: Mapping[str, Any]) -> None:
        delta = event.get("delta") or {}
        if delta.get("stop_reason"):
            self.stop_reason = str(delta["stop_reason"])
        self._merge_usage(event.get("usage"))

    def _on_error(self, event: Mapping[str, Any]) -> None:
        error = event.get("error") or {}
        raise CallerFacingError(
            f"Anthropic sent an error inside the stream ({error.get('type')}): "
            f"{error.get('message') or json.dumps(dict(event))}"
        )

    def _merge_usage(self, usage: Any) -> None:
        if isinstance(usage, dict):
            self.usage = {**(self.usage or {}), **usage}

    def _take_text_delta(self, block: dict[str, Any], delta: Mapping[str, Any]) -> None:
        piece = delta.get("text")
        if isinstance(piece, str) and piece:
            block["text"] = str(block.get("text") or "") + piece
            self.on_content(piece)

    def _take_thinking_delta(self, block: dict[str, Any], delta: Mapping[str, Any]) -> None:
        piece = delta.get("thinking")
        if isinstance(piece, str) and piece:
            block["thinking"] = str(block.get("thinking") or "") + piece
            if self.on_reasoning is not None:
                self.on_reasoning(piece)

    def _take_signature_delta(self, block: dict[str, Any], delta: Mapping[str, Any]) -> None:
        block["signature"] = str(block.get("signature") or "") + str(delta.get("signature") or "")

    def _take_input_json_delta(self, block: dict[str, Any], delta: Mapping[str, Any]) -> None:
        block["_partial"] = str(block.get("_partial") or "") + str(delta.get("partial_json") or "")

    def content_blocks(self) -> list[Mapping[str, Any]]:
        """The assembled content blocks, in the shape a non-streamed response carries."""
        assembled: list[Mapping[str, Any]] = []
        for index in sorted(self._blocks):
            block = dict(self._blocks[index])
            partial = block.pop("_partial", None)
            if block.get("type") == "tool_use":
                block["input"] = _arguments(partial) if partial else dict(block.get("input") or {})
            assembled.append(block)
        return assembled
