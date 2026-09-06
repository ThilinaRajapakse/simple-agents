"""The fifth hosted-API adapter: Anthropic's Messages API.

Backend ``hosted_api``. Cost derives under a :class:`~simple_agents.PriceBasis`, since the
provider bills per token and reports no serving concurrency. This is the backend that bills
a cache write at a rate per TTL and returns a signed thinking block, so it is the first to
fill ``cache_write_per_mtok_by_ttl`` and ``Reasoning.blocks``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Mapping

import httpx
from pydantic import SecretStr

from ..errors import ConfigurationError
from ..models import Backend, ModelIdentity, ModelRequest, ModelResponse
from ._anthropic_wire import (
    ANTHROPIC_VERSION,
    RATE_LIMIT_HEADERS,
    StreamAssembler,
    content_from,
    messages_from,
    output_config_for,
    rate_limit_from,
    reasoning_from,
    tokens_from,
    tool_calls_from,
    tools_from,
)
from ._http import HTTPBackend, Retry
from ._openai_wire import unmeasured_tokens, usage_missing_error

__all__ = ["AnthropicClient"]

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
API_KEY_ENV = "ANTHROPIC_API_KEY"

# What the request asks for when reasoning is left on, and what it sets to turn it off. The
# summary is asked for because the tokens are billed whether or not the text comes back, and
# the default on current models returns none of it. A model that refuses either form says so.
WITH_REASONING = {"type": "adaptive", "display": "summarized"}
NO_REASONING = {"type": "disabled"}


@dataclass(slots=True)
class AnthropicClient:
    """Calls a Claude model over Anthropic's Messages API.

    ``model`` is the identifier sent with every request, and the one the manifest pins::

        from simple_agents import AnthropicClient

        client = AnthropicClient(model="claude-sonnet-5")
        result = pipeline.run({"question": "..."}, model=client)

    ``api_key`` defaults to the ``ANTHROPIC_API_KEY`` environment variable and is held as a
    ``SecretStr``. ``model_revision`` is recorded as given. **This API takes no seed**: the
    adapter declares ``seeded = False``, drops the run's seed, and the manifest lists the model
    under ``unseeded_models``. **Every request needs an output ceiling**, so a node that sets
    none is sent ``max_output_tokens`` from here.

    Reasoning is asked for by default, recorded as text and as the signed block the next turn
    of an ``AgentNode`` sends back unchanged. ``reasoning=False`` sends
    ``thinking: {"type": "disabled"}``, and a ``thinking`` in ``extra`` replaces the computed
    one, which is how a model taking the older ``budget_tokens`` form is called::

        LLMNode(build_prompt, output_schema=Answer,
                extra={"thinking": {"type": "enabled", "budget_tokens": 2048}})

    A prompt asks for caching with ``Prompt.marked(cache_control={"type": "ephemeral"})``.
    ``docs/model-clients/anthropic.md`` has the rates per cache TTL and what this backend
    leaves unavailable.
    """

    seeded: ClassVar[bool] = False

    model: str
    api_key: str | SecretStr | None = None
    model_revision: str | None = None
    base_url: str = DEFAULT_BASE_URL
    timeout_s: float = 120.0
    retry: Retry = Retry()
    stream_without_usage: bool = False
    reasoning: bool = True
    max_output_tokens: int = 16_000
    http_client: httpx.Client | None = None
    _backend: HTTPBackend = field(init=False, repr=False)

    def __post_init__(self) -> None:
        key = self.api_key if self.api_key is not None else os.environ.get(API_KEY_ENV)
        if not key:
            raise ConfigurationError(
                f"AnthropicClient has no API key. Set the {API_KEY_ENV} environment variable, "
                f"or pass api_key= explicitly. Declare {API_KEY_ENV} in the envelope's "
                f"Redaction(secret_env=[...]) as well, so the value is stripped from anything "
                f"the run records."
            )
        self.api_key = key if isinstance(key, SecretStr) else SecretStr(key)
        if self.max_output_tokens < 1:
            raise ConfigurationError(
                f"AnthropicClient(max_output_tokens={self.max_output_tokens}) leaves no room "
                f"for an answer. The API requires a ceiling of at least 1 on every request."
            )
        self._backend = HTTPBackend(
            base_url=self.base_url,
            headers={
                "x-api-key": self.api_key.get_secret_value(),
                "anthropic-version": ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            },
            timeout_s=self.timeout_s,
            retry=self.retry,
            client=self.http_client,
        )

    def identity(self) -> ModelIdentity:
        """What the manifest pins and the cassette key includes, without making a call."""
        return ModelIdentity(
            backend=self.backend, request_model=self.model, model_revision=self.model_revision
        )

    @property
    def backend(self) -> Backend:
        return "hosted_api"

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        """The request body, shared by ``complete`` and ``stream`` so the two cannot drift.

        ``request.seed`` is not sent: the API has no such parameter.
        """
        turns, system = messages_from(request.messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": (
                request.max_output_tokens
                if request.max_output_tokens is not None
                else self.max_output_tokens
            ),
            "messages": turns,
            "thinking": dict(WITH_REASONING if self.reasoning else NO_REASONING),
        }
        if system is not None:
            payload["system"] = system
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.tools:
            payload["tools"] = tools_from(request.tools)
        output_config = output_config_for(request.output_schema)
        if output_config is not None:
            payload["output_config"] = output_config
        for name, value in request.extra.items():
            if name == "thinking" and value is None:
                payload.pop("thinking", None)
            elif name == "output_config" and isinstance(value, Mapping):
                payload["output_config"] = {**payload.get("output_config", {}), **value}
            else:
                payload[name] = value
        return payload

    def _response(
        self,
        *,
        blocks: list[Mapping[str, Any]],
        usage: Mapping[str, Any] | None,
        headers: Mapping[str, str],
        held_back_ms: int,
        finish_reason: str | None,
        response_model: str | None,
    ) -> ModelResponse:
        return ModelResponse(
            content=content_from(blocks),
            tool_calls=tool_calls_from(blocks),
            finish_reason=finish_reason,
            backend=self.backend,
            request_model=self.model,
            response_model=response_model,
            model_revision=self.model_revision,
            tokens=tokens_from(usage) if usage is not None else unmeasured_tokens(),
            concurrent_requests=None,
            rate_limit=rate_limit_from(headers),
            provider={k: v for k, v in headers.items() if k not in RATE_LIMIT_HEADERS},
            reasoning=reasoning_from(blocks),
            held_back_ms=held_back_ms,
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Make one call and return what the backend reported."""
        result = self._backend.post_json("/messages", self._payload(request))
        body = result.body
        usage = body.get("usage")
        return self._response(
            blocks=list(body.get("content") or []),
            usage=dict(usage) if isinstance(usage, dict) else None,
            headers=result.headers,
            held_back_ms=result.held_back_ms,
            finish_reason=body.get("stop_reason"),
            response_model=body.get("model"),
        )

    def stream(
        self,
        request: ModelRequest,
        on_chunk: Callable[[str], None],
        *,
        on_reasoning: Callable[[str], None] | None = None,
    ) -> ModelResponse:
        """The same call, delivering content to ``on_chunk`` as it arrives.

        Returns what ``complete`` returns, assembled from the events, so everything downstream
        reads one shape whichever way the call was made. The thinking text goes to
        ``on_reasoning`` where the caller supplied one; under the default display it is
        empty and only the signature arrives.

        Raises ``CallerFacingError`` where the stream ended without a usage block, unless the
        client was built with ``stream_without_usage=True``.
        """
        payload = self._payload(request)
        payload["stream"] = True

        assembler = StreamAssembler(on_content=on_chunk, on_reasoning=on_reasoning)
        result = self._backend.post_stream("/messages", payload, assembler.feed)

        if assembler.usage is None and not self.stream_without_usage:
            raise usage_missing_error(model=self.model, adapter=type(self).__name__)

        return self._response(
            blocks=assembler.content_blocks(),
            usage=assembler.usage,
            headers=result.headers,
            held_back_ms=result.held_back_ms,
            finish_reason=assembler.stop_reason,
            response_model=assembler.model,
        )
