"""The parts of Gemini's own wire format the adapter translates to and from.

Google serves an OpenAI-compatible endpoint as well, and this module exists because that
endpoint drops three things the library records: it refuses ``seed``, it leaves thinking
tokens out of ``completion_tokens`` while billing them, and it returns no chain of thought.
The shapes here are the native API's: ``contents`` of ``parts`` rather than messages,
``functionDeclarations`` rather than function tools, and ``usageMetadata`` rather than a usage
block.

Nothing here is shared with ``_openai_wire``. The two dialects agree on no field.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..errors import CallerFacingError
from ..models import Reasoning, TokenUsage, ToolCallRequest
from ..schema import Unknown

__all__ = [
    "contents_from",
    "declarations_from",
    "generation_config_for",
    "tool_calls_from",
    "reasoning_from",
    "content_from",
    "tokens_from",
    "StreamAssembler",
    "THOUGHT_SIGNATURE",
]

# What this backend calls the state it sends with a tool call and requires back on the next
# request. It travels on `ToolCallRequest.provider` under this key.
THOUGHT_SIGNATURE = "thought_signature"


def contents_from(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Translate the conversation the loop built into ``contents``, and the system turn.

    The library's message list is OpenAI-shaped: roles ``user``, ``assistant`` and ``tool``,
    an assistant turn carrying ``tool_calls`` as ``{id, name, arguments}``. This backend wants
    ``user`` and ``model`` turns made of parts, and a tool result as a ``functionResponse``
    part in a ``user`` turn::

        contents, system = contents_from([
            {"role": "user", "content": "Which retailer?"},
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "c1", "name": "search", "arguments": {"query": "x"},
                             "provider": {"thought_signature": "EjQK..."}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "Kirkwall."},
        ])

    **A tool call is sent back with the signature it arrived with.** This backend refuses the
    following turn with a 400 naming ``thought_signature`` when a ``functionCall`` part carries
    none, so a call whose ``provider`` was dropped somewhere makes the next turn unanswerable.

    A ``system`` message is returned separately rather than as a turn, since the field it
    belongs in is ``systemInstruction``. ``None`` where the conversation has none.
    """
    contents: list[dict[str, Any]] = []
    system: dict[str, Any] | None = None

    for message in messages:
        role = message.get("role")
        if role == "system":
            system = {"parts": [{"text": str(message.get("content") or "")}]}
            continue
        if role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "id": message.get("tool_call_id"),
                                "name": message.get("name") or "",
                                "response": {"result": message.get("content", "")},
                            }
                        }
                    ],
                }
            )
            continue

        parts: list[dict[str, Any]] = []
        text = message.get("content")
        if isinstance(text, str) and text:
            parts.append({"text": text})
        for call in message.get("tool_calls") or []:
            part: dict[str, Any] = {
                "functionCall": {
                    "id": call["id"],
                    "name": call["name"],
                    "args": call.get("arguments") or {},
                }
            }
            signature = (call.get("provider") or {}).get(THOUGHT_SIGNATURE)
            if signature:
                part["thoughtSignature"] = signature
            parts.append(part)
        if not parts:
            parts.append({"text": ""})
        contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})

    return contents, system


def declarations_from(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate the library's tool declarations into ``functionDeclarations``.

    ``Tool.to_wire()`` produces ``{name, description, input_schema}``, and the schema comes
    from the annotations, so a parameter typed as a model arrives carrying ``$defs`` and
    ``$ref``::

        declarations_from([{"name": "search", "description": "...", "input_schema": {...}}])

    It goes in ``parametersJsonSchema``, which takes that dialect. The older ``parameters``
    field is an OpenAPI subset and refuses both keywords.
    """
    return [
        {
            "name": tool["name"],
            "description": tool.get("description") or "",
            "parametersJsonSchema": (
                tool.get("input_schema") or {"type": "object", "properties": {}}
            ),
        }
        for tool in tools
    ]


def generation_config_for(
    *,
    seed: int | None,
    temperature: float | None,
    max_output_tokens: int | None,
    output_schema: Mapping[str, Any] | None,
    thinking: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """The ``generationConfig`` for one request.

    An output schema goes in ``responseJsonSchema`` beside ``responseMimeType``, for the reason
    a tool's parameters go in ``parametersJsonSchema``: the schema comes from a model and
    carries ``$defs``.
    """
    config: dict[str, Any] = {}
    if seed is not None:
        config["seed"] = seed
    if temperature is not None:
        config["temperature"] = temperature
    if max_output_tokens is not None:
        config["maxOutputTokens"] = max_output_tokens
    if output_schema:
        config["responseMimeType"] = "application/json"
        config["responseJsonSchema"] = dict(output_schema)
    if thinking:
        config["thinkingConfig"] = dict(thinking)
    return config


def content_from(parts: Iterable[Mapping[str, Any]]) -> str | None:
    """The answer text in a response, with the thinking parts left out.

    ``None`` where the model returned no text, which is what a turn of tool calls alone
    produces.
    """
    answer = "".join(part["text"] for part in parts if part.get("text") and not part.get("thought"))
    return answer or None


def reasoning_from(parts: Iterable[Mapping[str, Any]]) -> Reasoning | None:
    """The chain of thought a response reported separately, or ``None``.

    A thinking part is a text part flagged ``thought``. It arrives only where the request asked
    for it; a request that did not ask still pays for the tokens, which is why the adapter asks
    by default.
    """
    thoughts = [str(part["text"]) for part in parts if part.get("thought") and part.get("text")]
    if not thoughts:
        return None
    return Reasoning(text="".join(thoughts))


def tool_calls_from(parts: Iterable[Mapping[str, Any]]) -> list[ToolCallRequest]:
    """The tool calls in a response, each carrying the signature it arrived with.

    Arguments arrive as an object rather than as a JSON string, so nothing is parsed and the
    malformed-arguments case both OpenAI-dialect backends have does not arise. Anything other
    than an object raises: the library has no channel for correcting a malformed tool call.
    """
    calls: list[ToolCallRequest] = []
    for index, part in enumerate(parts):
        function = part.get("functionCall")
        if not function:
            continue
        arguments = function.get("args")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise CallerFacingError(
                f"Gemini returned tool call {index} for {function.get('name')!r} whose "
                f"arguments are {type(arguments).__name__}, not an object: "
                f"{str(arguments)[:200]!r}"
            )
        signature = part.get("thoughtSignature")
        calls.append(
            ToolCallRequest(
                id=str(function.get("id") or f"call_{index}"),
                name=str(function.get("name") or ""),
                arguments=arguments,
                provider={THOUGHT_SIGNATURE: signature} if signature else {},
            )
        )
    return calls


def tokens_from(usage: Mapping[str, Any]) -> TokenUsage:
    """Map ``usageMetadata`` onto the recorded breakdown.

    ``promptTokenCount`` includes the cached tokens, so the uncached count is the difference.
    ``thoughtsTokenCount`` is billed at the output rate and is added to the output count, which
    is what makes a derived cost match the bill on a call that thought.

    The provider reports no cache-write count: it bills cache storage by the hour rather than
    by the token, and a request that populated the cache says nothing about having done so. So
    that count is ``unknown`` rather than ``0``, and there is no cache TTL on the response.
    """
    prompt = usage.get("promptTokenCount")
    generated = usage.get("candidatesTokenCount")
    thoughts = usage.get("thoughtsTokenCount")

    no_write = Unknown(
        reason="the backend reports no cache-write count. It bills cache storage per token "
        "per hour rather than per token written, and a response says nothing about what a "
        "request cached"
    )

    if not isinstance(prompt, int):
        unmeasured = Unknown(reason="the response reported no promptTokenCount")
        return TokenUsage(
            input_uncached=unmeasured,
            input_cache_read=unmeasured,
            input_cache_write=no_write,
            cache_ttl=None,
            output=(
                _output(generated, thoughts)
                if isinstance(generated, int)
                else Unknown(reason="not reported")
            ),
        )

    cached = usage.get("cachedContentTokenCount")
    read = cached if isinstance(cached, int) else 0
    return TokenUsage(
        input_uncached=prompt - read,
        input_cache_read=read,
        input_cache_write=no_write,
        cache_ttl=None,
        output=(
            _output(generated, thoughts)
            if isinstance(generated, int)
            else Unknown(reason="not reported")
        ),
    )


def _output(generated: int, thoughts: Any) -> int:
    """What the call is charged for as output: the answer and the thinking together."""
    return generated + (thoughts if isinstance(thoughts, int) else 0)


class StreamAssembler:
    """Builds one response out of the chunks a streamed call arrives in.

    Each chunk is a whole ``generateContent`` body carrying the parts produced since the last
    one, and every chunk repeats the usage totals so far, so the last one seen is the call's::

        assembler = StreamAssembler(on_content=on_chunk, on_reasoning=on_thought)
        backend.post_stream(path, payload, assembler.feed)
        assembler.parts()      # the assembled parts, in the shape a whole response carries
        assembler.usage        # the last usageMetadata seen

    ``on_content`` is called with each piece of the answer and with nothing else, since a
    recording's chunk boundaries are offsets into ``content``. ``on_reasoning`` is optional and
    takes the thinking pieces on their own channel; thinking is collected either way.
    """

    def __init__(self, on_content: Any, on_reasoning: Any = None) -> None:
        self.on_content = on_content
        self.on_reasoning = on_reasoning
        self.content: list[str] = []
        self.thoughts: list[str] = []
        self.finish_reason: str | None = None
        self.usage: dict[str, Any] | None = None
        self.model: str | None = None
        self._calls: list[Mapping[str, Any]] = []

    def feed(self, event: Mapping[str, Any]) -> None:
        """Take one chunk of the stream."""
        if isinstance(event.get("usageMetadata"), dict):
            self.usage = dict(event["usageMetadata"])
        if event.get("modelVersion"):
            self.model = str(event["modelVersion"])
        candidate = (event.get("candidates") or [{}])[0] or {}
        if candidate.get("finishReason"):
            self.finish_reason = str(candidate["finishReason"])
        for part in (candidate.get("content") or {}).get("parts") or []:
            if part.get("functionCall"):
                self._calls.append(part)
                continue
            piece = part.get("text")
            if not isinstance(piece, str) or not piece:
                continue
            if part.get("thought"):
                self.thoughts.append(piece)
                if self.on_reasoning is not None:
                    self.on_reasoning(piece)
            else:
                self.content.append(piece)
                self.on_content(piece)

    def parts(self) -> list[Mapping[str, Any]]:
        """The assembled parts, in the shape a non-streamed response carries."""
        assembled: list[Mapping[str, Any]] = []
        if self.thoughts:
            assembled.append({"text": "".join(self.thoughts), "thought": True})
        if self.content:
            assembled.append({"text": "".join(self.content)})
        return assembled + self._calls
