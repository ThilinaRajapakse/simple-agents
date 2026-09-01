"""The parts of the wire format the two OpenAI-dialect backends use unchanged.

Mistral's API and vLLM's server both accept OpenAI-shaped chat completions, so tool
declarations, tool calls in a response, and JSON-schema output take the same form on each.
What differs between them stays in the adapters: authentication, the seed parameter's name,
what the usage block reports, and the shape of an error body.

These are the pieces measured to be identical against both backends. Anything found to differ
belongs back in its adapter. Gemini speaks its own dialect and is translated in
``_gemini_wire``.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..errors import CallerFacingError, StreamUsageMissing
from ..models import Reasoning, TokenUsage, ToolCallRequest
from ..schema import Unknown

__all__ = [
    "messages_to_wire",
    "tools_to_wire",
    "response_format_for",
    "strict_schema",
    "tool_calls_from",
    "reasoning_from",
    "REASONING_FIELDS",
    "StreamAssembler",
    "usage_missing_error",
    "unmeasured_tokens",
]

# What a message or a delta calls the chain of thought, in the order they are read. vLLM 0.26
# answers with `reasoning` and accepts `reasoning_content` on a request as the older spelling;
# both are checked because a server predating the rename answers with the other one.
REASONING_FIELDS = ("reasoning", "reasoning_content")


def reasoning_from(message: Mapping[str, Any]) -> Reasoning | None:
    """The chain of thought a response message reported separately, or ``None``.

    ``None`` covers three cases that are one case to a caller: the backend has no such field,
    the field is present and null, and the model produced no reasoning on this call. A server
    started without a reasoning parser leaves the chain of thought inside ``content`` and is
    this case too, which ``docs/model-clients/vllm.md`` §2 covers.
    """
    for name in REASONING_FIELDS:
        value = message.get(name)
        if isinstance(value, str) and value:
            return Reasoning(text=value)
    return None


def unmeasured_tokens() -> TokenUsage:
    """Every count ``unknown``, for a streamed response that reported no usage.

    Reached only where the client was built with ``stream_without_usage=True``. The reason
    travels onto every affected record, so a trajectory read later says which calls were not
    counted rather than reporting them as zero.
    """
    reason = Unknown(
        reason="the backend reported no usage block on a streamed response, and the client "
        "was built with stream_without_usage=True"
    )
    return TokenUsage(
        input_uncached=reason,
        input_cache_read=reason,
        input_cache_write=reason,
        cache_ttl=None,
        output=reason,
    )


class StreamAssembler:
    """Builds one chat completion out of the deltas a streamed response arrives in.

    Both backends send the same shape: a ``choices[0].delta`` carrying ``content``, or
    ``tool_calls`` whose ``function.arguments`` arrive in fragments to be joined by ``index``.
    A delta may instead carry ``reasoning``, which arrives before any content on both shipped
    backends. A final event carries ``usage`` where the request asked for it::

        assembler = StreamAssembler(on_content=on_chunk, on_reasoning=on_thought)
        backend.post_stream(path, payload, assembler.feed)
        assembler.message()     # {"content": ..., "tool_calls": [...]}
        assembler.reasoning()   # Reasoning(text=...), or None

    ``on_content`` is called with each piece of content and with nothing else, since a
    recording's chunk boundaries are offsets into ``content``. ``on_reasoning`` is optional and
    takes the reasoning pieces on their own channel; reasoning is collected either way.
    """

    def __init__(self, on_content: Any, on_reasoning: Any = None) -> None:
        self.on_content = on_content
        self.on_reasoning = on_reasoning
        self.content: list[str] = []
        self.reasoning_parts: list[str] = []
        self.finish_reason: str | None = None
        self.usage: dict[str, Any] | None = None
        self.model: str | None = None
        self._tool_calls: dict[int, dict[str, Any]] = {}

    def feed(self, event: Mapping[str, Any]) -> None:
        """Take one server-sent event."""
        if isinstance(event.get("usage"), dict):
            self.usage = dict(event["usage"])
        if event.get("model"):
            self.model = str(event["model"])
        choices = event.get("choices") or []
        if not choices:
            return
        choice = choices[0] or {}
        if choice.get("finish_reason"):
            self.finish_reason = str(choice["finish_reason"])
        delta = choice.get("delta") or {}
        piece = delta.get("content")
        if isinstance(piece, str) and piece:
            self.content.append(piece)
            self.on_content(piece)
        for name in REASONING_FIELDS:
            thought = delta.get(name)
            if isinstance(thought, str) and thought:
                self.reasoning_parts.append(thought)
                if self.on_reasoning is not None:
                    self.on_reasoning(thought)
                break
        for fragment in delta.get("tool_calls") or []:
            self._take_tool_fragment(fragment)

    def reasoning(self) -> Reasoning | None:
        """The assembled chain of thought, or ``None`` where no delta carried one."""
        if not self.reasoning_parts:
            return None
        return Reasoning(text="".join(self.reasoning_parts))

    def _take_tool_fragment(self, fragment: Mapping[str, Any]) -> None:
        index = int(fragment.get("index", len(self._tool_calls)))
        call = self._tool_calls.setdefault(
            index, {"id": None, "type": "function", "function": {"name": "", "arguments": ""}}
        )
        if fragment.get("id"):
            call["id"] = fragment["id"]
        function = fragment.get("function") or {}
        if function.get("name"):
            call["function"]["name"] = function["name"]
        if function.get("arguments"):
            call["function"]["arguments"] += function["arguments"]

    def message(self) -> dict[str, Any]:
        """The assembled message, in the shape a non-streamed response carries."""
        return {
            "content": "".join(self.content) if self.content else None,
            "tool_calls": [self._tool_calls[i] for i in sorted(self._tool_calls)],
        }


def usage_missing_error(*, model: str, adapter: str) -> StreamUsageMissing:
    """The refusal for a streamed response that reported no token usage.

    Carries both fixes the adapter knows about. Raised inside a run, the node, the call index
    and which of this run's limits the missing counts affect are added to it.
    """
    summary = (
        f"{model} returned a streamed response with no usage block, so this call's token "
        f"counts cannot be recorded."
    )
    return StreamUsageMissing(
        f"{summary}\n"
        f"Either accept the loss, with "
        f'{adapter}(model="{model}", stream_without_usage=True), which records `unknown` '
        f"counts naming this reason, or stop streaming this call and it is made through "
        f"complete() and fully counted.",
        model=model,
        adapter=adapter,
        summary=summary,
    )


def messages_to_wire(
    messages: list[dict[str, Any]], *, reasoning_field: str | None = None
) -> list[dict[str, Any]]:
    """Translate the conversation the loop built into OpenAI-dialect messages.

    An ``AgentNode`` records what the model asked for as ``{id, name, arguments}`` with the
    arguments as a dict, which is the library's own shape. Both backends expect a tool call
    nested under ``function`` with its arguments serialised as a string, and reject anything
    else with a 422::

        messages_to_wire([{"role": "assistant", "content": "",
                           "tool_calls": [{"id": "c1", "name": "search",
                                           "arguments": {"query": "x"}}]}])

    An assistant turn also carries the ``reasoning`` the model produced on that turn, in the
    library's own shape. ``reasoning_field`` is what this backend calls it, and the adapter
    passes the name its backend accepts::

        messages_to_wire(messages, reasoning_field="reasoning")

    Left ``None``, the reasoning is dropped from the request, which is what a backend with no
    field for it needs. Sending it matters within a turn the model is still working on: a chat
    template that renders prior reasoning is given the model's own thinking back, and one that
    ignores the field is unaffected.

    A message with no tool calls and no reasoning passes through unchanged. A tool call
    carrying ``ToolCallRequest.provider`` is refused, since this dialect cannot express it;
    ``_refuse_provider_state`` says what an adapter for such a backend does instead.
    """
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": message.get("tool_call_id"),
                    "content": message.get("content", ""),
                }
            )
            continue
        wire = {k: v for k, v in message.items() if k not in ("tool_calls", "reasoning")}
        reasoning = message.get("reasoning")
        if reasoning_field is not None and isinstance(reasoning, str) and reasoning:
            wire[reasoning_field] = reasoning
        calls = message.get("tool_calls")
        if calls:
            for call in calls:
                _refuse_provider_state(call)
            wire["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": call["arguments"]
                        if isinstance(call["arguments"], str)
                        else json.dumps(call["arguments"]),
                    },
                }
                for call in calls
            ]
        out.append(wire)
    return out


def _refuse_provider_state(call: Mapping[str, Any]) -> None:
    """Refuse a tool call carrying state this dialect cannot express.

    ``ToolCallRequest.provider`` is what a backend sent alongside a tool call and requires back
    on the next request. The OpenAI dialect has no field for it, so translating the turn would
    drop it and the backend would answer the next request with an error rather than degrading.
    Refusing here puts the failure at the call that caused it.

    ``provider`` is filled only by an adapter that read it off its own backend's response, so a
    backend sending none never reaches this and neither shipped adapter can. An adapter for a
    backend that does send it translates the conversation itself rather than calling
    ``messages_to_wire``, the way ``_gemini_wire.contents_from`` returns a thought signature as
    ``thoughtSignature``. ``docs/model-clients.md`` §7 is the builder-facing version.
    """
    provider = call.get("provider")
    if not provider:
        return
    fields = ", ".join(sorted(str(key) for key in provider))
    raise CallerFacingError(
        f"Tool call {str(call.get('id'))!r} for {str(call.get('name'))!r} carries provider "
        f"state ({fields}) and the OpenAI dialect has no field for it. The backend that sent "
        f"it requires it back and refuses the next request without it, so the turn is refused "
        f"here rather than one request later. An adapter for such a backend translates the "
        f"conversation itself rather than calling messages_to_wire(): docs/model-clients.md "
        f"§7 says what that involves, and _gemini_wire.contents_from is the shipped one."
    )


def tools_to_wire(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate the library's tool declarations into OpenAI function declarations.

    ``Tool.to_wire()`` produces ``{name, description, input_schema}``. Both backends expect
    ``{"type": "function", "function": {name, description, parameters}}``::

        tools_to_wire([{"name": "search", "description": "...", "input_schema": {...}}])
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description") or "",
                "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
            },
        }
        for tool in tools
    ]


_STRICT_UNSUPPORTED = ("default",)
_SUBSCHEMA_LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")
_SUBSCHEMA_KEYS = ("items", "not", "if", "then", "else")


def strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """``schema`` in the form ``strict: true`` decoding requires, leaving the original alone.

    Every object lists all of its properties in ``required`` and sets
    ``additionalProperties: false``, and ``default`` is dropped, throughout ``$defs`` and every
    nested subschema.

    **A field with a default is sent as required.** Pydantic leaves such a field out of
    ``required``, and a schema-guided decoder is then free to omit it or to invent a key for it.
    An optional field is expressed as required and nullable instead, which is what the dialect
    supports: ``source_doc: str | None = None`` reaches the model as a field it must send,
    holding either a string or ``null``. A field whose type cannot hold ``null`` becomes one the
    model has to produce a value for rather than one it may leave to the default.
    """
    if not isinstance(schema, Mapping):
        return schema
    out = {k: v for k, v in schema.items() if k not in _STRICT_UNSUPPORTED}
    properties = out.get("properties")
    if isinstance(properties, Mapping):
        out["properties"] = {k: strict_schema(v) for k, v in properties.items()}
        out["required"] = list(out["properties"])
        out["additionalProperties"] = False
    for key in ("$defs", "definitions"):
        nested = out.get(key)
        if isinstance(nested, Mapping):
            out[key] = {k: strict_schema(v) for k, v in nested.items()}
    for key in _SUBSCHEMA_LISTS:
        members = out.get(key)
        if isinstance(members, list):
            out[key] = [strict_schema(m) for m in members]
    for key in _SUBSCHEMA_KEYS:
        member = out.get(key)
        if isinstance(member, Mapping):
            out[key] = strict_schema(member)
    return out


def response_format_for(output_schema: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The ``response_format`` that constrains a response to ``output_schema``.

    Returns ``None`` when no schema was requested, which leaves the parameter off the request.

    The schema is sent in the form ``strict: true`` requires, through ``strict_schema``. A
    backend given a schema that does not meet it is not obliged to reject the request, and
    Mistral does not: its decoder returns field names padded with punctuation, such as
    ``"source_doc "`` and ``"source_doc: "``, which validate as unknown fields and are dropped.
    """
    if not output_schema:
        return None
    return {
        "type": "json_schema",
        "json_schema": {"name": "output", "schema": strict_schema(output_schema), "strict": True},
    }


def tool_calls_from(message: Mapping[str, Any], *, backend: str) -> list[ToolCallRequest]:
    """The tool calls in a response message, with their arguments parsed.

    Both backends send ``arguments`` as a JSON string. A string that does not parse raises
    ``CallerFacingError``: the library has no channel for correcting a malformed tool call, and
    recording it as an empty argument set would describe a call the model did not make.
    """
    calls = message.get("tool_calls") or []
    out: list[ToolCallRequest] = []
    for index, call in enumerate(calls):
        function = call.get("function") or {}
        raw = function.get("arguments")
        try:
            arguments = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except (ValueError, TypeError) as exc:
            raise CallerFacingError(
                f"{backend} returned tool call {index} for {function.get('name')!r} with "
                f"arguments that are not JSON: {str(raw)[:200]!r}\n"
                f"Constrained decoding prevents this. Pass an output schema, or on a "
                f"self-hosted server start it with a tool call parser that matches the model."
            ) from exc
        if not isinstance(arguments, dict):
            raise CallerFacingError(
                f"{backend} returned tool call {index} for {function.get('name')!r} whose "
                f"arguments are {type(arguments).__name__}, not an object: "
                f"{str(arguments)[:200]!r}"
            )
        out.append(
            ToolCallRequest(
                id=str(call.get("id") or f"call_{index}"),
                name=str(function.get("name") or ""),
                arguments=arguments,
            )
        )
    return out
