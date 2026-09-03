"""The second hosted-API adapter: Google's Gemini, over its own API.

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
from ..models import Backend, ModelIdentity, ModelRequest, ModelResponse
from ._gemini_wire import (
    StreamAssembler,
    content_from,
    contents_from,
    declarations_from,
    generation_config_for,
    reasoning_from,
    tokens_from,
    tool_calls_from,
)
from ._http import HTTPBackend, Retry
from ._openai_wire import unmeasured_tokens, usage_missing_error

__all__ = ["GeminiClient"]

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
API_KEY_ENV = "GEMINI_API_KEY"

# What the request asks for when reasoning is left on, and what it sets to turn it off. A
# model that does not think is unaffected by either.
INCLUDE_THOUGHTS = {"includeThoughts": True}
NO_THINKING = {"thinkingBudget": 0}


@dataclass(slots=True)
class GeminiClient:
    """Calls a Gemini model over Google's own API.

    ``model`` is the identifier sent with every request, and the one the manifest pins::

        from simple_agents import GeminiClient

        client = GeminiClient(model="gemini-3.1-flash-lite")
        result = pipeline.run({"question": "..."}, model=client)

    ``gemini-flash-lite-latest`` and its siblings are aliases that resolve to different weights
    over time, so a run made against one cannot be attributed afterwards (FT-14). A versioned
    identifier such as ``gemini-3.1-flash-lite`` is the pin. ``model_revision`` records the
    build string ``GET /v1beta/models`` publishes for it, which no response repeats::

        GeminiClient(model="gemini-3.1-flash-lite", model_revision="3.1-flash-lite-05-2026")

    ``api_key`` defaults to the ``GEMINI_API_KEY`` environment variable and is held as a
    ``SecretStr``, so it does not render.

    ``reasoning=False`` stops the model producing a chain of thought::

        GeminiClient(model="gemini-3.1-flash-lite", reasoning=False)

    The default keeps whatever the model produces and asks for it to be returned, since those
    tokens are charged as output either way.

    Cost derives under a ``PriceBasis`` the project declares, and that basis needs
    ``input_cache_write_per_mtok=0.0``: this backend reports no cache-write count, and an
    unmeasured count with no rate leaves every call unpriced.
    ``docs/model-clients/gemini.md`` has the rates, the caching, and what this backend leaves
    unavailable.
    """

    model: str
    api_key: str | SecretStr | None = None
    model_revision: str | None = None
    base_url: str = DEFAULT_BASE_URL
    timeout_s: float = 120.0
    retry: Retry = Retry()
    stream_without_usage: bool = False
    reasoning: bool = True
    http_client: httpx.Client | None = None
    _backend: HTTPBackend = field(init=False, repr=False)

    def __post_init__(self) -> None:
        key = self.api_key if self.api_key is not None else os.environ.get(API_KEY_ENV)
        if not key:
            raise ConfigurationError(
                f"GeminiClient has no API key. Set the {API_KEY_ENV} environment variable, "
                f"or pass api_key= explicitly. Declare {API_KEY_ENV} in the envelope's "
                f"Redaction(secret_env=[...]) as well, so the value is stripped from anything "
                f"the run records."
            )
        self.api_key = key if isinstance(key, SecretStr) else SecretStr(key)
        self._backend = HTTPBackend(
            base_url=self.base_url,
            headers={
                "x-goog-api-key": self.api_key.get_secret_value(),
                "Content-Type": "application/json",
            },
            timeout_s=self.timeout_s,
            retry=self.retry,
            client=self.http_client,
            # No Gemini response carries a rate-limit header, so `rate_limit` is None on every
            # call and a PacedClient in front of this adapter is a passthrough.
            publishes_allowance=False,
        )

    def identity(self) -> ModelIdentity:
        """What the manifest pins and the cassette key includes, without making a call.

        ``model_revision`` is whatever the constructor was given, and ``None`` when it was
        given nothing: no response carries the build a hosted model was served from.
        """
        return ModelIdentity(
            backend=self.backend, request_model=self.model, model_revision=self.model_revision
        )

    @property
    def backend(self) -> Backend:
        return "hosted_api"

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        """The request body, shared by ``complete`` and ``stream`` so the two cannot drift."""
        contents, system = contents_from(request.messages)
        payload: dict[str, Any] = {"contents": contents}
        if system is not None:
            payload["systemInstruction"] = system
        if request.tools:
            payload["tools"] = [{"functionDeclarations": declarations_from(request.tools)}]
        config = generation_config_for(
            seed=request.seed,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            output_schema=request.output_schema,
            thinking=INCLUDE_THOUGHTS if self.reasoning else NO_THINKING,
        )
        if config:
            payload["generationConfig"] = config

        # `extra` reaches the body unchanged, except that a `generationConfig` in it is merged
        # over the computed one rather than replacing it. Replacing it would drop the seed and
        # the output schema, which every cassette key and every validated output rest on.
        for name, value in request.extra.items():
            if name == "generationConfig" and isinstance(value, Mapping):
                payload["generationConfig"] = {**payload.get("generationConfig", {}), **value}
            else:
                payload[name] = value
        return payload

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Make one call and return what the backend reported."""
        result = self._backend.post_json(
            f"/models/{self.model}:generateContent", self._payload(request)
        )
        body = result.body
        candidate = (body.get("candidates") or [{}])[0] or {}
        parts = (candidate.get("content") or {}).get("parts") or []

        return ModelResponse(
            content=content_from(parts),
            tool_calls=tool_calls_from(parts),
            finish_reason=candidate.get("finishReason"),
            backend=self.backend,
            request_model=self.model,
            response_model=body.get("modelVersion"),
            model_revision=self.model_revision,
            tokens=tokens_from(body.get("usageMetadata") or {}),
            concurrent_requests=None,
            # The provider publishes no allowance on a response, so there is nothing to pace
            # against. `docs/model-clients/gemini.md` §5 says what that costs an evaluation.
            rate_limit=None,
            provider=result.headers,
            reasoning=reasoning_from(parts),
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

        Returns what ``complete`` returns, assembled from the chunks, so everything downstream
        reads one shape whichever way the call was made.

        Raises ``CallerFacingError`` where the response carries no usage block, unless the
        client was built with ``stream_without_usage=True``. Without counts a call charges
        nothing against a token budget and derives no cost, so the choice is the project's to
        make rather than the adapter's to make silently.

        A chain of thought arrives before the answer and goes to ``on_reasoning`` where the
        caller supplied one. ``on_chunk`` takes the answer alone.
        """
        assembler = StreamAssembler(on_content=on_chunk, on_reasoning=on_reasoning)
        result = self._backend.post_stream(
            f"/models/{self.model}:streamGenerateContent?alt=sse",
            self._payload(request),
            assembler.feed,
        )
        parts = assembler.parts()

        if assembler.usage is None and not self.stream_without_usage:
            raise usage_missing_error(model=self.model, adapter=type(self).__name__)

        return ModelResponse(
            content=content_from(parts),
            tool_calls=tool_calls_from(parts),
            finish_reason=assembler.finish_reason,
            backend=self.backend,
            request_model=self.model,
            response_model=assembler.model,
            model_revision=self.model_revision,
            tokens=(
                tokens_from(assembler.usage) if assembler.usage is not None else unmeasured_tokens()
            ),
            concurrent_requests=None,
            rate_limit=None,
            provider=result.headers,
            reasoning=reasoning_from(parts),
            held_back_ms=result.held_back_ms,
        )
