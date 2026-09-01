"""The hosted-API adapter: Mistral's chat completions.

Backend ``hosted_api``. Cost derives under a :class:`~simple_agents.PriceBasis`, since the
provider bills per token and reports no serving concurrency.
"""

from __future__ import annotations

import os
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

__all__ = ["MistralClient"]

DEFAULT_BASE_URL = "https://api.mistral.ai/v1"
API_KEY_ENV = "MISTRAL_API_KEY"

NO_REASONING_CONTROL = (
    "MistralClient(reasoning=False) has nothing to set. The provider's switch for it, "
    "prompt_mode, is refused with `Reasoning prompt mode is not enabled for this model` on "
    "every model this API serves, so the request would go out unchanged and the setting would "
    "read as though it had been applied.\n"
    "Leave reasoning at its default. A model that reports a chain of thought separately is "
    "recorded on `model_call.outputs.reasoning`, and one that does not reports nothing there."
)


@dataclass(slots=True)
class MistralClient:
    """Calls a Mistral model over the hosted API.

    ``model`` is the identifier sent with every request, and the one the manifest pins::

        from simple_agents import MistralClient

        client = MistralClient(model="mistral-small-2603")
        result = pipeline.run({"question": "..."}, model=client)

    A dated snapshot is the pinned form. ``mistral-small-latest`` is an alias that resolves to
    different weights over time, and a response echoes back the identifier that was sent, so a
    run made against an alias cannot be attributed afterwards (FT-14). The adapter records
    what it is given and refuses nothing. ``api_key`` defaults to the ``MISTRAL_API_KEY``
    environment variable and is held as a ``SecretStr``, so it does not render.

    Prompt caching is opt-in. Without a ``prompt_cache_key`` in ``extra``, an identical prompt
    is charged in full and ``input_cache_read`` is a true ``0``::

        LLMNode(build_prompt, output_schema=Answer,
                extra={"prompt_cache_key": "catalogue-v1"})

    Cost derives under a ``PriceBasis`` the project declares. ``docs/model-clients/mistral.md``
    has the rates and what this backend leaves unavailable.

    ``reasoning=False`` is refused: the provider offers no setting this adapter can apply, so
    accepting it would leave a control that reads as applied and changes nothing.
    """

    model: str
    api_key: str | SecretStr | None = None
    base_url: str = DEFAULT_BASE_URL
    timeout_s: float = 120.0
    retry: Retry = Retry()
    stream_without_usage: bool = False
    reasoning: bool = True
    http_client: httpx.Client | None = None
    _backend: HTTPBackend = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.reasoning:
            raise ConfigurationError(NO_REASONING_CONTROL)
        key = self.api_key if self.api_key is not None else os.environ.get(API_KEY_ENV)
        if not key:
            raise ConfigurationError(
                f"MistralClient has no API key. Set the {API_KEY_ENV} environment variable, "
                f"or pass api_key= explicitly. Declare {API_KEY_ENV} in the envelope's "
                f"Redaction(secret_env=[...]) as well, so the value is stripped from anything "
                f"the run records."
            )
        self.api_key = key if isinstance(key, SecretStr) else SecretStr(key)
        self._backend = HTTPBackend(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key.get_secret_value()}",
                "Content-Type": "application/json",
            },
            timeout_s=self.timeout_s,
            retry=self.retry,
            client=self.http_client,
        )

    def identity(self) -> ModelIdentity:
        """What the manifest pins and the cassette key includes, without making a call.

        ``model_revision`` is ``None``: the provider exposes no revision for a hosted model.
        """
        return ModelIdentity(backend=self.backend, request_model=self.model, model_revision=None)

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
            payload["random_seed"] = request.seed
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.tools:
            payload["tools"] = tools_to_wire(request.tools)
            payload["tool_choice"] = "auto"
        response_format = response_format_for(request.output_schema)
        if response_format is not None:
            payload["response_format"] = response_format
        payload.update(request.extra)
        return payload

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Make one chat completion call and return what the backend reported."""
        result = self._backend.post_json("/chat/completions", self._payload(request))
        body = result.body
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}

        return ModelResponse(
            content=message.get("content"),
            tool_calls=tool_calls_from(message, backend="Mistral"),
            finish_reason=choice.get("finish_reason"),
            backend=self.backend,
            request_model=self.model,
            response_model=body.get("model"),
            model_revision=None,
            tokens=_tokens_from(body.get("usage") or {}),
            concurrent_requests=None,
            rate_limit=_rate_limit_from(result.headers),
            provider=_passthrough(result.headers),
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
            tool_calls=tool_calls_from(message, backend="Mistral"),
            finish_reason=assembler.finish_reason,
            backend=self.backend,
            request_model=self.model,
            response_model=assembler.model,
            model_revision=None,
            tokens=_tokens_from(assembler.usage)
            if assembler.usage is not None
            else unmeasured_tokens(),
            concurrent_requests=None,
            rate_limit=_rate_limit_from(result.headers),
            provider=_passthrough(result.headers),
            reasoning=assembler.reasoning(),
            held_back_ms=result.held_back_ms,
        )


RATE_LIMIT_HEADERS = (
    "x-ratelimit-remaining-req-minute",
    "x-ratelimit-remaining-tokens-minute",
)


def _rate_limit_from(headers: Mapping[str, str]) -> RateLimit | None:
    """What the response said is left of the per-minute window.

    Mistral publishes the allowance on every response, as a remaining request count and a
    remaining token count. A batch paced against it meets fewer 429s than one that retries
    into them. ``None`` when the response carried neither figure.
    """
    requests = _int_or_none(headers.get(RATE_LIMIT_HEADERS[0]))
    tokens = _int_or_none(headers.get(RATE_LIMIT_HEADERS[1]))
    if requests is None and tokens is None:
        return None
    return RateLimit(remaining_requests=requests, remaining_tokens=tokens)


def _passthrough(headers: Mapping[str, str]) -> dict[str, str]:
    """Every response header except the two whose values are already on ``rate_limit``.

    A record that carried both would store the same two numbers twice on every call.
    """
    return {name: value for name, value in headers.items() if name not in RATE_LIMIT_HEADERS}


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _tokens_from(usage: dict[str, Any]) -> TokenUsage:
    """Map Mistral's usage block onto the recorded breakdown.

    ``prompt_tokens`` includes the cached tokens, so the uncached count is the difference.
    The provider reports no cache-write count and bills no cache-write class, so that count is
    ``0`` rather than unknown. It reports no cache TTL.
    """
    prompt = usage.get("prompt_tokens")
    details = usage.get("prompt_tokens_details")
    output = usage.get("completion_tokens")

    if not isinstance(prompt, int):
        return TokenUsage(
            input_uncached=Unknown(reason="the response reported no prompt_tokens"),
            input_cache_read=Unknown(reason="the response reported no prompt_tokens"),
            input_cache_write=Unknown(reason="the response reported no prompt_tokens"),
            cache_ttl=None,
            output=output if isinstance(output, int) else Unknown(reason="not reported"),
        )

    if not isinstance(details, dict) or not isinstance(details.get("cached_tokens"), int):
        return TokenUsage(
            input_uncached=prompt,
            input_cache_read=Unknown(
                reason="the response carried no prompt_tokens_details.cached_tokens, so the "
                "cached share of the prompt is unmeasured"
            ),
            input_cache_write=Unknown(reason="the backend reports no cache-write count"),
            cache_ttl=None,
            output=output if isinstance(output, int) else Unknown(reason="not reported"),
        )

    cached = details["cached_tokens"]
    return TokenUsage(
        input_uncached=prompt - cached,
        input_cache_read=cached,
        input_cache_write=0,
        cache_ttl=None,
        output=output if isinstance(output, int) else Unknown(reason="not reported"),
    )
