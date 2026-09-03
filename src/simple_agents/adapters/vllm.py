"""The self-hosted adapter: open weights served by vLLM.

Backend ``self_hosted``. Cost derives under a :class:`~simple_agents.ComputeBasis`, since
nothing is billed per token and the device is what the run occupies.
"""

from __future__ import annotations

import threading
import time
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
from pydantic import SecretStr

from ..errors import SimpleAgentsWarning
from ..models import Backend, ModelIdentity, ModelRequest, ModelResponse, TokenUsage
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

__all__ = ["VLLMClient"]

DEFAULT_BASE_URL = "http://localhost:8000/v1"

# How long after sending a request the concurrency reading is taken. Long enough that requests
# issued together are all in flight by then, short enough to land inside a generation.
CONCURRENCY_SAMPLE_DELAY_S = 0.05

NO_TOKEN_DETAILS = (
    "This vLLM server reports no prompt_tokens_details, so the cached share of every prompt "
    "is recorded as unknown rather than as a number. Restart it with "
    "--enable-prompt-tokens-details to record the split. Prefix caching still works without "
    "the flag; only the reporting of it is missing, and an unmeasured count is never written "
    "as 0."
)

NO_REASONING_PARSER = (
    "This vLLM server returned a response whose content opens with a <think> block and whose "
    "reasoning field is empty, which is what a reasoning model served without a reasoning "
    "parser produces. The chain of thought is being recorded as part of the answer, so an "
    "output schema is validated against it and it goes back to the model as though it were "
    "the answer. Restart the server with --reasoning-parser matching the model, such as "
    "--reasoning-parser qwen3, and the two are recorded separately. Pass reasoning=False on "
    "the client instead to stop the model producing a chain of thought at all."
)

# What this backend calls the chain of thought on a request. vLLM accepts the older
# `reasoning_content` and renames it, so the current name is what is sent.
REASONING_FIELD = "reasoning"


@dataclass(slots=True)
class VLLMClient:
    """Calls a model served by vLLM's OpenAI-compatible server.

    ``model`` is the identifier the server serves under, which is the hub repo ID unless
    ``--served-model-name`` changed it. ``model_revision`` is the commit the weights came
    from::

        from simple_agents import VLLMClient

        client = VLLMClient(
            model="Qwen/Qwen3-8B",
            model_revision="6ee0d4a3a5a0a4e8b0f2c1d9e7b3a5c8d2f4e6a1",
            base_url="http://localhost:8000/v1",
        )

    A repo ID on its own is an alias, and resolves to different weights as the repo moves
    (FT-14). Serve a fixed revision, and start the server with both reporting flags::

        vllm serve Qwen/Qwen3-8B --revision <sha> \\
            --enable-prompt-tokens-details \\
            --enable-auto-tool-choice --tool-call-parser hermes

    Those flags decide what a run can record. Without ``--enable-prompt-tokens-details`` the
    adapter warns once and records the two cache counts as unknown. Without the tool-call
    flags the server rejects any request offering tools, and the error names them.

    Cost derives under a ``ComputeBasis``. ``report_concurrency`` reads the server's
    in-flight request count, at one local request per call, and is on by default because a
    figure derived without it is an upper bound. Pass ``report_concurrency=False`` for a server
    whose metrics endpoint is not reachable. ``docs/model-clients/vllm.md`` §5 has the rest.

    ``reasoning=False`` stops a reasoning model producing a chain of thought, by setting
    ``enable_thinking`` in the chat template::

        VLLMClient(model="Qwen/Qwen3-8B", model_revision="<sha>", reasoning=False)

    The default keeps whatever the model produces, since those tokens are charged either way.
    A template with no such switch ignores the setting, and the server accepts the request.
    """

    model: str
    model_revision: str | None = None
    base_url: str = DEFAULT_BASE_URL
    api_key: str | SecretStr | None = None
    timeout_s: float = 120.0
    retry: Retry = Retry()
    report_concurrency: bool = True
    stream_without_usage: bool = False
    reasoning: bool = True
    http_client: httpx.Client | None = None
    _backend: HTTPBackend = field(init=False, repr=False)
    _warned: bool = field(init=False, default=False, repr=False)
    _warned_parser: bool = field(init=False, default=False, repr=False)

    def __post_init__(self) -> None:
        headers = {"Content-Type": "application/json"}
        if self.api_key is not None:
            if not isinstance(self.api_key, SecretStr):
                self.api_key = SecretStr(self.api_key)
            headers["Authorization"] = f"Bearer {self.api_key.get_secret_value()}"
        self._backend = HTTPBackend(
            base_url=self.base_url,
            headers=headers,
            timeout_s=self.timeout_s,
            retry=self.retry,
            client=self.http_client,
            # A served model publishes no allowance: the ceiling is the server's own
            # concurrency, which `docs/model-clients/vllm.md` covers.
            publishes_allowance=False,
        )

    def identity(self) -> ModelIdentity:
        """What the manifest pins and the cassette key includes, without making a call.

        The server reports no revision, so ``model_revision`` is whatever the constructor was
        given, and ``None`` when it was given nothing.
        """
        return ModelIdentity(
            backend=self.backend, request_model=self.model, model_revision=self.model_revision
        )

    @property
    def backend(self) -> Backend:
        return "self_hosted"

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        """The request body, shared by ``complete`` and ``stream`` so the two cannot drift."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages_to_wire(request.messages, reasoning_field=REASONING_FIELD),
        }
        if not self.reasoning:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if request.seed is not None:
            payload["seed"] = request.seed
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

        A server started with a reasoning parser reports the chain of thought separately from
        the answer. ``on_chunk`` takes the answer, and ``on_reasoning`` takes the chain of
        thought where the caller supplied one. Started without a parser the chain of thought is
        inside the content and streams with it, which the adapter warns about once.
        """
        payload = self._payload(request)
        payload["stream"] = True
        payload.setdefault("stream_options", {"include_usage": True})

        assembler = StreamAssembler(on_content=on_chunk, on_reasoning=on_reasoning)
        sampler = self._start_concurrency_sample()
        result = self._backend.post_stream("/chat/completions", payload, assembler.feed)
        message = assembler.message()
        reasoning = assembler.reasoning()

        if assembler.usage is None:
            if not self.stream_without_usage:
                raise usage_missing_error(model=self.model, adapter=type(self).__name__)
        elif not isinstance(assembler.usage.get("prompt_tokens_details"), dict):
            self._warn_once()

        self._check_reasoning_parser(message["content"], reasoning)

        return ModelResponse(
            content=message["content"],
            tool_calls=tool_calls_from(message, backend="vLLM"),
            finish_reason=assembler.finish_reason,
            backend=self.backend,
            request_model=self.model,
            response_model=assembler.model,
            model_revision=self.model_revision,
            tokens=(
                _tokens_from(assembler.usage)
                if assembler.usage is not None
                else unmeasured_tokens()
            ),
            concurrent_requests=_finish_sample(sampler),
            rate_limit=None,
            provider=result.headers,
            reasoning=reasoning,
            held_back_ms=result.held_back_ms,
        )

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Make one chat completion call and return what the server reported."""
        payload = self._payload(request)

        sampler = self._start_concurrency_sample()
        result = self._backend.post_json("/chat/completions", payload)
        body = result.body
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = body.get("usage") or {}

        if not isinstance(usage.get("prompt_tokens_details"), dict):
            self._warn_once()

        reasoning = reasoning_from(message)
        self._check_reasoning_parser(message.get("content"), reasoning)

        return ModelResponse(
            content=message.get("content"),
            tool_calls=tool_calls_from(message, backend="vLLM"),
            finish_reason=choice.get("finish_reason"),
            backend=self.backend,
            request_model=self.model,
            response_model=body.get("model"),
            model_revision=self.model_revision,
            tokens=_tokens_from(usage),
            concurrent_requests=_finish_sample(sampler),
            # The server publishes no rate-limit headers, so there is no allowance to report.
            rate_limit=None,
            provider=result.headers,
            reasoning=reasoning,
            held_back_ms=result.held_back_ms,
        )

    def _warn_once(self) -> None:
        """Say once per client that the server is not reporting the prompt-token split."""
        if self._warned:
            return
        self._warned = True
        warnings.warn(NO_TOKEN_DETAILS, SimpleAgentsWarning, stacklevel=3)

    def _check_reasoning_parser(self, content: str | None, reasoning: Any) -> None:
        """Say once per client that a chain of thought is arriving inside the answer.

        The server reports nothing about which parsers it was started with, so the response is
        the only place this shows. Every condition is required: a model that produces no
        reasoning correctly reports none, and warning on that alone would fire on every server
        serving a model that does not think.
        """
        if self._warned_parser or not self.reasoning or reasoning is not None:
            return
        if not _carries_a_chain_of_thought(content):
            return
        self._warned_parser = True
        warnings.warn(NO_REASONING_PARSER, SimpleAgentsWarning, stacklevel=3)

    def _start_concurrency_sample(self) -> _Sample | None:
        """Begin reading how many requests the server has running, while this one runs.

        The reading is taken a moment **after** the request is sent, not before it. Sampled
        before, a batch of calls issued together each see a server with nothing running and
        every one of them records 1, which under a compute basis charges each the whole device
        and reports several times the real cost.

        ``None`` where ``report_concurrency`` is off, which leaves every compute-basis
        figure an upper bound. It is a sample at one instant rather than an average over the
        call, which ``docs/model-clients/vllm.md`` §5 states is what the field is.
        """
        if not self.report_concurrency:
            return None
        sample = _Sample()
        url = self.base_url.rstrip("/").removesuffix("/v1") + "/metrics"

        def read() -> None:
            time.sleep(CONCURRENCY_SAMPLE_DELAY_S)
            sample.value = self._backend.scrape_metric(url, "vllm:num_requests_running")
            sample.taken = True

        sample.thread = threading.Thread(target=read, daemon=True)
        sample.thread.start()
        return sample


def _carries_a_chain_of_thought(content: str | None) -> bool:
    """Whether a response's content holds a chain of thought that was left unparsed.

    An unparsed chain of thought opens the answer, so the tag has to be the first thing in the
    content. A response that mentions the tag in the middle of its prose is not one.

    An **empty** block is not one either. A model told not to think is given
    ``<think>\\n\\n</think>`` at the start of its answer by its own chat template, so a server
    with no reasoning parser returns content carrying those tags and nothing between them. That
    is a correct configuration, and warning about it would fire on every call a project makes
    with reasoning turned off.

    A response cut off by ``max_tokens`` part-way through thinking has an opening tag and no
    closing one, and is a chain of thought like any other.
    """
    if not content or not content.lstrip().startswith("<think>"):
        return False
    thought, _, _ = content.lstrip().removeprefix("<think>").partition("</think>")
    return bool(thought.strip())


def _tokens_from(usage: dict[str, Any]) -> TokenUsage:
    """Map vLLM's usage block onto the recorded breakdown.

    With ``--enable-prompt-tokens-details`` the server reports ``cached_tokens`` and
    ``created_cache_tokens``, which are disjoint and together with the uncached remainder sum
    to ``prompt_tokens``. Without the flag it reports the prompt size alone, and the whole
    prompt is recorded as uncached with the two cache counts unknown.

    There is no cache TTL under self-hosted serving.
    """
    prompt = usage.get("prompt_tokens")
    output = usage.get("completion_tokens")
    generated = output if isinstance(output, int) else Unknown(reason="not reported")
    details = usage.get("prompt_tokens_details")

    if not isinstance(prompt, int):
        return TokenUsage(
            input_uncached=Unknown(reason="the response reported no prompt_tokens"),
            input_cache_read=Unknown(reason="the response reported no prompt_tokens"),
            input_cache_write=Unknown(reason="the response reported no prompt_tokens"),
            cache_ttl=None,
            output=generated,
        )

    if not isinstance(details, dict):
        unmeasured = (
            "the server reports no prompt_tokens_details, so the cached share of the prompt "
            "is unmeasured. Restart it with --enable-prompt-tokens-details"
        )
        return TokenUsage(
            input_uncached=prompt,
            input_cache_read=Unknown(reason=unmeasured),
            input_cache_write=Unknown(reason=unmeasured),
            cache_ttl=None,
            output=generated,
        )

    cached = details.get("cached_tokens") or 0
    created = details.get("created_cache_tokens") or 0
    return TokenUsage(
        input_uncached=prompt - cached - created,
        input_cache_read=cached,
        input_cache_write=created,
        cache_ttl=None,
        output=generated,
    )


@dataclass(slots=True)
class _Sample:
    """A concurrency reading taken while a request was in flight."""

    value: float | None = None
    taken: bool = False
    thread: threading.Thread | None = None


def _finish_sample(sample: _Sample | None) -> int | None:
    """The reading, once it has landed. ``None`` when it was never taken or could not be read.

    A call that returned before the reading was due waits for it, which is why the delay is
    small. An unread metric leaves the field ``None`` rather than a guess.
    """
    if sample is None:
        return None
    if sample.thread is not None:
        sample.thread.join(timeout=CONCURRENCY_SAMPLE_DELAY_S + 5.0)
    if not sample.taken or sample.value is None:
        return None
    return max(int(sample.value), 1)
