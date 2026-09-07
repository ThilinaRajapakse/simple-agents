"""The third hosted-API adapter: OpenAI's Chat Completions, and every endpoint that serves it.

Backend ``hosted_api``. Cost derives under a :class:`~simple_agents.PriceBasis`, since the
provider bills per token and reports no serving concurrency. ``base_url`` points the same
adapter at any other endpoint speaking this dialect; what that endpoint reports in its usage
block and its headers is its own, and a field it leaves out is recorded as unmeasured.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import httpx
from pydantic import SecretStr

from ..errors import ConfigurationError
from ..models import (
    Backend,
    ModelIdentity,
    ModelRequest,
    ModelResponse,
    RateLimit,
    TokenUsage,
)
from ..schema import Unknown
from ._http import HTTPBackend, Retry
from ._openai_wire import (
    StreamAssembler,
    messages_to_wire,
    reasoning_from,
    response_format_for,
    tool_calls_from,
    tools_to_wire,
    unmeasured_tokens,
    usage_missing_error,
)

__all__ = ["OpenAIClient", "API_KEY_ENV", "DEFAULT_BASE_URL"]

DEFAULT_BASE_URL = "https://api.openai.com/v1"
API_KEY_ENV = "OPENAI_API_KEY"

# What the request sets to stop a reasoning model thinking. A model without that level says
# which levels it has, and a model that does not reason ignores it.
NO_REASONING = {"reasoning_effort": "none"}

# The name OpenAI bounds output with. Its reasoning models refuse `max_tokens` even alongside
# this one, measured 2026-09-07, so the two names cannot both be sent and an endpoint that
# ignores this one names the other through `max_output_tokens_param`.
CEILING_PARAM = "max_completion_tokens"

# What `structured_output` may be set to. `json_schema` binds the decoder to the schema;
# `json_object` asks only for valid JSON, so the fields are whatever the model produced; and
# `none` is an endpoint that constrains nothing, where a node asking for a schema is refused
# rather than answered with prose. Measured per endpoint 2026-09-07, `openai.md` §6.
STRUCTURED_OUTPUT_MODES = ("json_schema", "json_object", "none")


@dataclass(slots=True)
class OpenAIClient:
    """Calls a model over OpenAI's Chat Completions API, at OpenAI or anywhere it is served.

    ``model`` is the identifier sent with every request, and the one the manifest pins::

        from simple_agents import OpenAIClient

        client = OpenAIClient(model="gpt-5.6-luna")
        result = pipeline.run({"question": "..."}, model=client)

    A response names the dated snapshot that served it, and ``response_model`` records it
    (FT-14). ``api_key`` defaults to ``OPENAI_API_KEY`` and is held as a ``SecretStr``.
    ``base_url`` points the adapter at any endpoint speaking this dialect::

        OpenAIClient(model="deepseek-v4-flash", base_url="https://api.deepseek.com/v1",
                     api_key=os.environ["DEEPSEEK_API_KEY"],
                     max_output_tokens_param="max_tokens", structured_output="none",
                     publishes_allowance=False)

    **Four settings say what an endpoint does with the parameters it accepts**, each
    defaulting to what ``api.openai.com`` takes, with a row per measured endpoint in
    ``docs/model-clients/openai.md`` §6. ``max_output_tokens_param`` is the name the ceiling
    is sent under, ``reasoning_off`` what ``reasoning=False`` sends, ``publishes_allowance``
    whether a response reports a rate-limit allowance, and ``structured_output`` how an
    ``output_schema`` is sent: ``"json_schema"`` binds the decoder, ``"json_object"`` asks
    for valid JSON and leaves the fields to the model, and ``"none"`` refuses a node that
    asks for a schema.

    At ``api.openai.com`` a reasoning model reports the count alone, recorded as
    ``tokens.output_reasoning``, and ``OpenAIResponsesClient`` records the chain of thought.
    Other endpoints serving this dialect return the text over it.
    ``docs/model-clients/openai.md`` has the rates, the cache-write class GPT-5.6 bills, and
    what this backend leaves unavailable.
    """

    model: str
    api_key: str | SecretStr | None = None
    model_revision: str | None = None
    base_url: str = DEFAULT_BASE_URL
    timeout_s: float = 120.0
    retry: Retry = Retry()
    stream_without_usage: bool = False
    reasoning: bool = True
    max_output_tokens_param: str = CEILING_PARAM
    reasoning_off: Mapping[str, Any] = field(default_factory=lambda: dict(NO_REASONING))
    structured_output: str = "json_schema"
    publishes_allowance: bool = True
    http_client: httpx.Client | None = None
    _backend: HTTPBackend = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.structured_output not in STRUCTURED_OUTPUT_MODES:
            raise ConfigurationError(
                f"OpenAIClient(structured_output={self.structured_output!r}) is not a mode "
                f"this adapter has. Pass one of {', '.join(STRUCTURED_OUTPUT_MODES)}.\n"
                f"`docs/model-clients/openai.md` §6 says which one each endpoint takes."
            )
        self.api_key = read_key(self.api_key, adapter=type(self).__name__)
        self._backend = HTTPBackend(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            timeout_s=self.timeout_s,
            retry=self.retry,
            publishes_allowance=self.publishes_allowance,
            client=self.http_client,
        )

    def identity(self) -> ModelIdentity:
        """What the manifest pins and the cassette key includes, without making a call.

        ``model_revision`` is whatever the constructor was given, and ``None`` when it was
        given nothing: the provider exposes no revision for a hosted model beyond its dated
        identifier.
        """
        return ModelIdentity(
            backend=self.backend, request_model=self.model, model_revision=self.model_revision
        )

    @property
    def backend(self) -> Backend:
        return "hosted_api"

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        """The request body, shared by ``complete`` and ``stream`` so the two cannot drift."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages_to_wire(request.messages),
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload[self.max_output_tokens_param] = request.max_output_tokens
        if request.tools:
            payload["tools"] = tools_to_wire(request.tools)
            payload["tool_choice"] = "auto"
        response_format = self._response_format(request.output_schema)
        if response_format is not None:
            payload["response_format"] = response_format
        if not self.reasoning:
            payload.update(self.reasoning_off)
        payload.update(request.extra)
        return payload

    def _response_format(self, output_schema: Mapping[str, Any] | None) -> dict[str, Any] | None:
        """The ``response_format`` for a schema, in whichever mode this endpoint constrains.

        An endpoint that constrains nothing refuses the request here rather than answering it
        with prose that fails to parse several steps later.
        """
        if not output_schema:
            return None
        if self.structured_output == "none":
            raise ConfigurationError(
                f"{self.base_url} does not constrain output to a schema, and this node asked "
                f"for one (model {self.model!r}).\n"
                f"Send the schema as a request for valid JSON with "
                f"OpenAIClient(structured_output='json_object'), which asks the model for "
                f"JSON and leaves the fields to it, and validate what comes back. Use a "
                f"model that constrains decoding to keep the guarantee; "
                f"`docs/model-clients/openai.md` §6 says which endpoints do."
            )
        if self.structured_output == "json_object":
            return {"type": "json_object"}
        return response_format_for(output_schema)

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Make one chat completion call and return what the backend reported."""
        result = self._backend.post_json("/chat/completions", self._payload(request))
        body = result.body
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}

        return ModelResponse(
            content=message.get("content"),
            tool_calls=tool_calls_from(message, backend="OpenAI"),
            finish_reason=choice.get("finish_reason"),
            backend=self.backend,
            request_model=self.model,
            response_model=body.get("model"),
            model_revision=self.model_revision,
            tokens=tokens_from_completion(body.get("usage") or {}),
            concurrent_requests=None,
            rate_limit=rate_limit_from(result.headers),
            provider=passthrough(result.headers),
            reasoning=reasoning_from(message),
            held_back_ms=result.held_back_ms,
        )

    def stream(
        self,
        request: ModelRequest,
        on_chunk: Callable[[str], None],
        *,
        on_reasoning: Callable[[str], None] | None = None,
    ) -> ModelResponse:
        """The same call, delivering content to ``on_chunk`` as it arrives.

        Returns what ``complete`` returns, assembled from the deltas, so everything downstream
        reads one shape whichever way the call was made.

        Raises ``CallerFacingError`` where the response carries no usage block, unless the
        client was built with ``stream_without_usage=True``. Without counts a call charges
        nothing against a token budget and derives no cost, so the choice is the project's to
        make rather than the adapter's to make silently.
        """
        payload = self._payload(request)
        payload["stream"] = True
        payload.setdefault("stream_options", {"include_usage": True})

        assembler = StreamAssembler(on_content=on_chunk, on_reasoning=on_reasoning)
        result = self._backend.post_stream("/chat/completions", payload, assembler.feed)
        message = assembler.message()

        if assembler.usage is None and not self.stream_without_usage:
            raise usage_missing_error(model=self.model, adapter=type(self).__name__)

        return ModelResponse(
            content=message["content"],
            tool_calls=tool_calls_from(message, backend="OpenAI"),
            finish_reason=assembler.finish_reason,
            backend=self.backend,
            request_model=self.model,
            response_model=assembler.model,
            model_revision=self.model_revision,
            tokens=tokens_from_completion(assembler.usage)
            if assembler.usage is not None
            else unmeasured_tokens(),
            concurrent_requests=None,
            rate_limit=rate_limit_from(result.headers),
            provider=passthrough(result.headers),
            reasoning=assembler.reasoning(),
            held_back_ms=result.held_back_ms,
        )


def read_key(given: str | SecretStr | None, *, adapter: str) -> SecretStr:
    """The API key to send, from the argument or the environment, refused where neither holds one."""
    key = given if given is not None else os.environ.get(API_KEY_ENV)
    if not key:
        raise ConfigurationError(
            f"{adapter} has no API key. Set the {API_KEY_ENV} environment variable, or pass "
            f"api_key= explicitly. Declare {API_KEY_ENV} in the envelope's "
            f"Redaction(secret_env=[...]) as well, so the value is stripped from anything the "
            f"run records."
        )
    return key if isinstance(key, SecretStr) else SecretStr(key)


RATE_LIMIT_HEADERS = (
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
    "x-ratelimit-limit-requests",
    "x-ratelimit-limit-tokens",
)

_DURATION = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def duration_seconds(value: str | None) -> float | None:
    """A reset header's duration in seconds, or ``None`` where it reads as none.

    The provider writes ``6ms``, ``0s``, ``1m2.5s`` and ``1h3m``, which its rate-limits guide
    documents in that form::

        duration_seconds("1m2.5s")   # 62.5
    """
    if not value:
        return None
    parts = _DURATION.findall(value.strip())
    if not parts or "".join(n + u for n, u in parts) != value.strip():
        return None
    return sum(float(number) * _UNIT_SECONDS[unit] for number, unit in parts)


def rate_limit_from(headers: Mapping[str, str]) -> RateLimit | None:
    """What the response said is left of the window.

    Published on every response, streamed or not, as a remaining request count, a remaining
    token count, and the time until each resets. ``resets_in_s`` is the longer of the two
    resets, since a batch paced against the window that reopens later meets fewer 429s.
    ``None`` when the response carried none of them.
    """
    requests = _int_or_none(headers.get("x-ratelimit-remaining-requests"))
    tokens = _int_or_none(headers.get("x-ratelimit-remaining-tokens"))
    resets = [
        seconds
        for seconds in (
            duration_seconds(headers.get("x-ratelimit-reset-requests")),
            duration_seconds(headers.get("x-ratelimit-reset-tokens")),
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


def passthrough(headers: Mapping[str, str]) -> dict[str, str]:
    """Every response header except the rate-limit ones: the four whose values are on
    ``rate_limit``, and the two limits those are measured against."""
    return {name: value for name, value in headers.items() if name not in RATE_LIMIT_HEADERS}


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def tokens_from_completion(usage: Mapping[str, Any]) -> TokenUsage:
    """Map a Chat Completions usage block onto the recorded breakdown.

    ``prompt_tokens`` includes the cached tokens and, on a model that bills a cache write, the
    written ones, so the uncached count is what is left after both. A usage block with no
    ``prompt_tokens_details`` leaves the split unmeasured, which is what an endpoint that
    reports one prompt figure said.
    """
    return _tokens(
        prompt=usage.get("prompt_tokens"),
        details=usage.get("prompt_tokens_details"),
        output=usage.get("completion_tokens"),
        output_details=usage.get("completion_tokens_details"),
    )


def tokens_from_response(usage: Mapping[str, Any]) -> TokenUsage:
    """Map a Responses usage block onto the recorded breakdown: the same counts, renamed."""
    return _tokens(
        prompt=usage.get("input_tokens"),
        details=usage.get("input_tokens_details"),
        output=usage.get("output_tokens"),
        output_details=usage.get("output_tokens_details"),
    )


def _tokens(
    *,
    prompt: Any,
    details: Any,
    output: Any,
    output_details: Any,
) -> TokenUsage:
    reasoning = (
        output_details.get("reasoning_tokens") if isinstance(output_details, Mapping) else None
    )
    generated: int | Unknown = output if isinstance(output, int) else Unknown(reason="not reported")
    thought = reasoning if isinstance(reasoning, int) else None

    if not isinstance(prompt, int):
        unmeasured = Unknown(reason="the response reported no prompt token count")
        return _unsplit(unmeasured, unmeasured, unmeasured, generated, thought)

    if not isinstance(details, Mapping) or not isinstance(details.get("cached_tokens"), int):
        return _unsplit(
            prompt,
            Unknown(
                reason="the response carried no cached-token count, so the cached share of "
                "the prompt is unmeasured"
            ),
            Unknown(
                reason="the response carried no cached-token count, so what was written to "
                "the cache is unmeasured"
            ),
            generated,
            thought,
        )

    cached = details["cached_tokens"]
    written = details.get("cache_write_tokens")
    # A model that bills no cache-write class reports no count for it, and the class it does
    # not bill is 0 rather than unknown. GPT-5.6 and later report and bill it. Measured
    # 2026-09-06.
    write: int = written if isinstance(written, int) else 0
    return TokenUsage(
        input_uncached=prompt - cached - write,
        input_cache_read=cached,
        input_cache_write=write,
        cache_ttl=None,
        output=generated,
        output_reasoning=thought,
    )


def _unsplit(
    uncached: int | Unknown,
    read: Unknown,
    write: Unknown,
    output: int | Unknown,
    reasoning: int | None,
) -> TokenUsage:
    """A breakdown for a usage block that did not say how the prompt divided."""
    return TokenUsage(
        input_uncached=uncached,
        input_cache_read=read,
        input_cache_write=write,
        cache_ttl=None,
        output=output,
        output_reasoning=reasoning,
    )
