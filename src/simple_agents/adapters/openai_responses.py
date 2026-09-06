"""The fourth hosted-API adapter: OpenAI's Responses API, which returns the reasoning.

Backend ``hosted_api``. Cost derives under a :class:`~simple_agents.PriceBasis`. The same
provider's Chat Completions API is ``OpenAIClient``; this one exists for what only Responses
returns, the chain of thought as a summary and an encrypted item the next turn sends back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Mapping

import httpx
from pydantic import SecretStr

from ..models import Backend, ModelIdentity, ModelRequest, ModelResponse
from ._http import HTTPBackend, Retry
from ._openai_wire import unmeasured_tokens, usage_missing_error
from ._responses_wire import (
    StreamAssembler,
    content_from,
    finish_reason_from,
    input_from,
    reasoning_from,
    text_format_for,
    tokens_from,
    tool_calls_from,
    tools_from,
)
from .openai import DEFAULT_BASE_URL, passthrough, rate_limit_from, read_key

__all__ = ["OpenAIResponsesClient"]

# What the request asks for when reasoning is left on: the summary returned, and nothing kept
# on the provider's side, which is also what makes the encrypted item come back. And what it
# sets to turn reasoning off; a model without that level says which levels it has.
WITH_REASONING = {"summary": "auto"}
NO_REASONING = {"effort": "none"}


@dataclass(slots=True)
class OpenAIResponsesClient:
    """Calls a model over OpenAI's Responses API, recording the reasoning it returns.

    ``model`` is the identifier sent with every request, and the one the manifest pins::

        from simple_agents import OpenAIResponsesClient

        client = OpenAIResponsesClient(model="gpt-5.6-luna")
        result = pipeline.run({"question": "..."}, model=client)

    ``api_key`` defaults to the ``OPENAI_API_KEY`` environment variable and is held as a
    ``SecretStr``. **This API takes no seed**: the adapter declares ``seeded = False``, drops
    the run's seed, and the manifest lists the model under ``unseeded_models``.

    Reasoning comes back as a summary on ``outputs.reasoning.text`` and as an encrypted item
    on ``outputs.reasoning.blocks``, which the next turn of an ``AgentNode`` sends back. Every
    request sets ``store: false``. ``reasoning=False`` sends ``reasoning: {"effort": "none"}``,
    a ``reasoning`` in ``extra`` merges over the computed one, and ``extra={"reasoning":
    None}`` leaves it off for a model that does not reason::

        LLMNode(build_prompt, output_schema=Answer, extra={"reasoning": {"effort": "low"}})

    ``docs/model-clients/openai.md`` has the rates and the two APIs side by side.
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
    http_client: httpx.Client | None = None
    _backend: HTTPBackend = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.api_key = read_key(self.api_key, adapter=type(self).__name__)
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
        """What the manifest pins and the cassette key includes, without making a call."""
        return ModelIdentity(
            backend=self.backend, request_model=self.model, model_revision=self.model_revision
        )

    @property
    def backend(self) -> Backend:
        return "hosted_api"

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        """The request body, shared by ``complete`` and ``stream`` so the two cannot drift.

        ``request.seed`` is not sent: the API refuses the parameter.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "input": input_from(request.messages),
            "store": False,
            "reasoning": dict(WITH_REASONING if self.reasoning else NO_REASONING),
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_output_tokens"] = request.max_output_tokens
        if request.tools:
            payload["tools"] = tools_from(request.tools)
            payload["tool_choice"] = "auto"
        text_format = text_format_for(request.output_schema)
        if text_format is not None:
            payload["text"] = {"format": text_format}

        for name, value in request.extra.items():
            if name == "reasoning" and value is None:
                payload.pop("reasoning", None)
            elif name == "reasoning" and isinstance(value, Mapping):
                payload["reasoning"] = {**payload.get("reasoning", {}), **value}
            else:
                payload[name] = value
        return payload

    def _response(
        self,
        body: Mapping[str, Any],
        output: list[Mapping[str, Any]],
        usage: Mapping[str, Any] | None,
        headers: Mapping[str, str],
        held_back_ms: int,
        *,
        finish_reason: str | None,
    ) -> ModelResponse:
        return ModelResponse(
            content=content_from(output),
            tool_calls=tool_calls_from(output),
            finish_reason=finish_reason,
            backend=self.backend,
            request_model=self.model,
            response_model=body.get("model"),
            model_revision=self.model_revision,
            tokens=tokens_from(usage) if usage is not None else unmeasured_tokens(),
            concurrent_requests=None,
            rate_limit=rate_limit_from(headers),
            provider=passthrough(headers),
            reasoning=reasoning_from(output),
            held_back_ms=held_back_ms,
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Make one call and return what the backend reported."""
        result = self._backend.post_json("/responses", self._payload(request))
        body = result.body
        usage = body.get("usage")
        return self._response(
            body,
            list(body.get("output") or []),
            dict(usage) if isinstance(usage, dict) else None,
            result.headers,
            result.held_back_ms,
            finish_reason=finish_reason_from(body),
        )

    def stream(
        self,
        request: ModelRequest,
        on_chunk: Callable[[str], None],
        *,
        on_reasoning: Callable[[str], None] | None = None,
    ) -> ModelResponse:
        """The same call, delivering content to ``on_chunk`` as it arrives.

        Returns what ``complete`` returns: the stream's last event carries the whole
        response, and everything but the pieces is read off that. The reasoning summary goes
        to ``on_reasoning`` where the caller supplied one.

        Raises ``CallerFacingError`` where the stream ended without a usage block, unless the
        client was built with ``stream_without_usage=True``.
        """
        payload = self._payload(request)
        payload["stream"] = True

        assembler = StreamAssembler(on_content=on_chunk, on_reasoning=on_reasoning)
        result = self._backend.post_stream("/responses", payload, assembler.feed)

        if assembler.usage is None and not self.stream_without_usage:
            raise usage_missing_error(model=self.model, adapter=type(self).__name__)

        body = assembler.response or {}
        return self._response(
            body,
            assembler.output_items(),
            assembler.usage,
            result.headers,
            result.held_back_ms,
            finish_reason=finish_reason_from(body),
        )
