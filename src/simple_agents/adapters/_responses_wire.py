"""The parts of OpenAI's Responses API the adapter translates to and from.

OpenAI serves Chat Completions as well, and ``OpenAIClient`` speaks that through
``_openai_wire``. This module exists because Chat Completions returns no chain of thought:
a reasoning model reports how many tokens it spent thinking and nothing else. Responses
returns the reasoning as an output item carrying a summary and an encrypted payload, which
the adapter records and returns on the following turn. The shapes here are that API's:
``input`` items rather than messages, ``function_call`` and ``function_call_output`` items,
``text.format`` for a schema, and a stream of typed events ending in the whole response.

Measured against ``api.openai.com`` on 2026-09-06. ``seed`` is refused by this API, which is
why the adapter declares ``seeded = False``.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from ..errors import CallerFacingError
from ..models import Reasoning, TokenUsage, ToolCallRequest
from ._openai_wire import strict_schema
from .openai import tokens_from_response

__all__ = [
    "input_from",
    "tools_from",
    "text_format_for",
    "content_from",
    "tool_calls_from",
    "reasoning_from",
    "finish_reason_from",
    "tokens_from",
    "StreamAssembler",
]

_DROPPED = ("tool_calls", "reasoning", "reasoning_blocks")


def input_from(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate the conversation the loop built into ``input`` items.

    A ``user`` or ``system`` message passes through as a message item. An assistant turn
    becomes its reasoning items, sent back exactly as they arrived, then a message item where
    it said something, then one ``function_call`` item per tool call. A tool result is a
    ``function_call_output`` item::

        input_from([
            {"role": "user", "content": "Which retailer?"},
            {"role": "assistant", "content": "",
             "reasoning_blocks": [{"type": "reasoning", "id": "rs_1",
                                   "encrypted_content": "gAAA...", "summary": []}],
             "tool_calls": [{"id": "call_1", "name": "lookup",
                             "arguments": {"town": "Kirkwall"}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": "Kirkwall Hardware"},
        ])

    The reasoning items go first because that is the order the model produced them in, and
    the provider's guide asks for them back ahead of the call they led to. A turn without
    them is accepted, so a conversation recorded against another backend still runs here.
    """
    items: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id"),
                    "output": message.get("content", ""),
                }
            )
            continue
        if role != "assistant":
            items.append({k: v for k, v in message.items() if k not in _DROPPED})
            continue
        for block in message.get("reasoning_blocks") or []:
            items.append(dict(block))
        content = message.get("content")
        if content:
            items.append({"role": "assistant", "content": content})
        for call in message.get("tool_calls") or []:
            arguments = call.get("arguments")
            items.append(
                {
                    "type": "function_call",
                    "call_id": call["id"],
                    "name": call["name"],
                    "arguments": arguments
                    if isinstance(arguments, str)
                    else json.dumps(arguments or {}),
                }
            )
    return items


def tools_from(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate the library's tool declarations into this API's function tools.

    The function's fields sit on the tool itself rather than under ``function``::

        tools_from([{"name": "search", "description": "...", "input_schema": {...}}])
    """
    return [
        {
            "type": "function",
            "name": tool["name"],
            "description": tool.get("description") or "",
            "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
        }
        for tool in tools
    ]


def text_format_for(output_schema: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The ``text.format`` that constrains a response to ``output_schema``, or ``None``."""
    if not output_schema:
        return None
    return {
        "type": "json_schema",
        "name": "output",
        "schema": strict_schema(output_schema),
        "strict": True,
    }


def content_from(output: Iterable[Mapping[str, Any]]) -> str | None:
    """The answer text across the response's message items, or ``None`` where there is none."""
    pieces = [
        str(part.get("text") or "")
        for item in output
        if item.get("type") == "message"
        for part in item.get("content") or []
        if part.get("type") == "output_text"
    ]
    text = "".join(pieces)
    return text or None


def tool_calls_from(output: Iterable[Mapping[str, Any]]) -> list[ToolCallRequest]:
    """The ``function_call`` items, with their arguments parsed.

    Arguments arrive as a JSON string. One that does not parse raises ``CallerFacingError``:
    the library has no channel for correcting a malformed tool call.
    """
    calls: list[ToolCallRequest] = []
    for index, item in enumerate(output):
        if item.get("type") != "function_call":
            continue
        raw = item.get("arguments")
        try:
            arguments = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except (ValueError, TypeError) as exc:
            raise CallerFacingError(
                f"OpenAI returned function call {index} for {item.get('name')!r} with "
                f"arguments that are not JSON: {str(raw)[:200]!r}"
            ) from exc
        if not isinstance(arguments, dict):
            raise CallerFacingError(
                f"OpenAI returned function call {index} for {item.get('name')!r} whose "
                f"arguments are {type(arguments).__name__}, not an object: "
                f"{str(arguments)[:200]!r}"
            )
        calls.append(
            ToolCallRequest(
                id=str(item.get("call_id") or f"call_{index}"),
                name=str(item.get("name") or ""),
                arguments=arguments,
            )
        )
    return calls


def reasoning_from(output: Iterable[Mapping[str, Any]]) -> Reasoning | None:
    """The reasoning items, as text and as the items to send back.

    ``text`` is the summary the request asked for, joined across the items, and ``None``
    where the model wrote none. ``blocks`` holds every reasoning item as it arrived, with its
    ``id`` and ``encrypted_content``, which is what the next turn sends back. ``None`` where
    the response carried no reasoning item.
    """
    items = [dict(item) for item in output if item.get("type") == "reasoning"]
    if not items:
        return None
    summaries = [
        str(part.get("text") or "")
        for item in items
        for part in item.get("summary") or []
        if part.get("text")
    ]
    text = "\n\n".join(summaries)
    return Reasoning(text=text or None, blocks=tuple(items))


def finish_reason_from(body: Mapping[str, Any]) -> str | None:
    """Why the response ended: its ``status``, or the reason it is incomplete.

    ``completed`` on a turn that ended by itself, tool calls included. An incomplete response
    reports ``incomplete_details.reason``, such as ``max_output_tokens``.
    """
    status = body.get("status")
    if status == "incomplete":
        details = body.get("incomplete_details") or {}
        return str(details.get("reason") or status)
    return str(status) if status else None


def tokens_from(usage: Mapping[str, Any]) -> TokenUsage:
    """Map the usage block onto the recorded breakdown.

    ``input_tokens`` includes the cached tokens and the written ones, the same arithmetic
    Chat Completions uses under other names; ``tokens_from_response`` in ``openai`` does it.
    """
    return tokens_from_response(usage)


class StreamAssembler:
    """Builds one response out of the events a streamed call arrives in.

    The stream is typed events, and the last of them carries the whole response. Content and
    reasoning arrive as deltas, which go to their sinks as they come; everything else is read
    off the final response, so a streamed call records what a plain one would::

        assembler = StreamAssembler(on_content=on_chunk, on_reasoning=on_thought)
        backend.post_stream("/responses", {**payload, "stream": True}, assembler.feed)
        assembler.response     # the whole response, or None where the stream ended early
        assembler.usage        # its usage block, or None

    ``on_content`` is called with each piece of the answer and with nothing else, since a
    recording's chunk boundaries are offsets into ``content``.
    """

    def __init__(self, on_content: Any, on_reasoning: Any = None) -> None:
        self.on_content = on_content
        self.on_reasoning = on_reasoning
        self.content: list[str] = []
        self.reasoning_parts: list[str] = []
        self.response: dict[str, Any] | None = None
        self.usage: dict[str, Any] | None = None

    def feed(self, event: Mapping[str, Any]) -> None:
        """Take one server-sent event. Events of a kind this does not read are skipped."""
        handler = _HANDLERS.get(str(event.get("type")))
        if handler is not None:
            handler(self, event)

    def _content(self, event: Mapping[str, Any]) -> None:
        piece = event.get("delta")
        if isinstance(piece, str) and piece:
            self.content.append(piece)
            self.on_content(piece)

    def _reasoning(self, event: Mapping[str, Any]) -> None:
        piece = event.get("delta")
        if isinstance(piece, str) and piece:
            self.reasoning_parts.append(piece)
            if self.on_reasoning is not None:
                self.on_reasoning(piece)

    def _done(self, event: Mapping[str, Any]) -> None:
        if isinstance(event.get("response"), dict):
            self.response = dict(event["response"])
            usage = self.response.get("usage")
            self.usage = dict(usage) if isinstance(usage, dict) else None

    def _failed(self, event: Mapping[str, Any]) -> None:
        response = event.get("response") or {}
        error = response.get("error") or {}
        raise CallerFacingError(
            f"OpenAI reported the streamed response as failed: "
            f"{error.get('message') or json.dumps(error)}"
        )

    def _error(self, event: Mapping[str, Any]) -> None:
        raise CallerFacingError(
            f"OpenAI sent an error inside the stream: "
            f"{event.get('message') or json.dumps(dict(event))}"
        )

    def output_items(self) -> list[Mapping[str, Any]]:
        """The final response's output items, in the shape a plain response carries."""
        if self.response is None:
            return []
        return list(self.response.get("output") or [])


_HANDLERS = {
    "response.output_text.delta": StreamAssembler._content,
    "response.reasoning_summary_text.delta": StreamAssembler._reasoning,
    "response.completed": StreamAssembler._done,
    "response.incomplete": StreamAssembler._done,
    "response.failed": StreamAssembler._failed,
    "error": StreamAssembler._error,
}
