"""The two shipped adapters, against recorded exchanges from the real backends.

Every fixture under `tests/fixtures/wire/` is a response captured from Mistral or from a local
vLLM server, stored with the request that produced it. Replaying them through an
`httpx.MockTransport` tests the part a model cassette cannot: a cassette stores a decoded
`ModelResponse`, so replaying one never re-enters the adapter and proves nothing about how the
wire format was read.

No test here needs a key or a network.
"""

from __future__ import annotations

import json
import time
import warnings
from copy import deepcopy
from email.utils import formatdate
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from simple_agents import (
    Prompt,
    Budget,
    CallerFacingError,
    ConfigurationError,
    GeminiClient,
    LLMNode,
    MistralClient,
    ModelRequest,
    Pipeline,
    Retry,
    RunEnvelope,
    SimpleAgentsWarning,
    StreamUsageMissing,
    VLLMClient,
    read_trajectory,
)
from simple_agents.adapters._http import HTTPBackend, retry_after_seconds
from simple_agents.adapters.embeddings_openai import OpenAIEmbeddings
from simple_agents.models import held_back_ms_of
from simple_agents.adapters._openai_wire import messages_to_wire, strict_schema
from simple_agents.schema import Unknown

from schemas import Answer

FIXTURES = Path(__file__).parent / "fixtures" / "wire"


def fixture(backend: str, name: str) -> tuple[int, dict[str, Any]]:
    """A captured exchange: the status the backend returned, and the body."""
    raw = json.loads((FIXTURES / backend / f"{name}.json").read_text())
    return raw["status"], raw["response"]


class Recorder:
    """Serves fixtures in order and keeps the requests that asked for them."""

    def __init__(
        self,
        *exchanges: tuple[int, dict[str, Any]],
        headers: dict[str, str] | None = None,
    ) -> None:
        self.queued = list(exchanges)
        self.requests: list[dict[str, Any]] = []
        self.headers = headers or {}

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(json.loads(request.content))
            status, body = self.queued.pop(0)
            return httpx.Response(status, json=body, headers=self.headers)

        return httpx.MockTransport(handle)

    def client(self, base_url: str) -> httpx.Client:
        return httpx.Client(transport=self.transport(), base_url=base_url)


def request(**overrides: Any) -> ModelRequest:
    base: dict[str, Any] = {"messages": [{"role": "user", "content": "Reply with the word OK."}]}
    base.update(overrides)
    return ModelRequest(**base)


class TestMistralIdentity:
    def test_identity_needs_no_call(self) -> None:
        # The cassette key includes the identity and is computed before the call, so a client
        # that had to ask the backend could not be keyed on.
        client = MistralClient(model="mistral-small-2603", api_key="k" * 20)

        identity = client.identity()

        assert identity.backend == "hosted_api"
        assert identity.request_model == "mistral-small-2603"
        assert identity.model_revision is None

    def test_missing_key_is_refused_at_construction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

        with pytest.raises(ConfigurationError, match="MISTRAL_API_KEY"):
            MistralClient(model="mistral-small-2603")

    def test_key_is_read_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MISTRAL_API_KEY", "k" * 20)

        assert MistralClient(model="mistral-small-2603").identity().backend == "hosted_api"

    def test_key_does_not_render(self) -> None:
        client = MistralClient(model="mistral-small-2603", api_key="sk-live-do-not-print")

        assert "do-not-print" not in repr(client)
        assert isinstance(client.api_key, SecretStr)


class TestMistralResponses:
    def test_minimal_completion(self) -> None:
        recorder = Recorder(fixture("mistral", "minimal"))
        client = MistralClient(
            model="mistral-small-latest",
            api_key="k" * 20,
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )

        response = client.complete(request())

        assert response.content == "OK"
        assert response.finish_reason == "stop"
        assert response.backend == "hosted_api"
        assert response.request_model == "mistral-small-latest"
        assert response.tokens.input_uncached == 21
        assert response.tokens.input_cache_read == 0
        assert response.tokens.output == 2
        assert response.concurrent_requests is None

    def test_response_model_echoes_the_alias_that_was_sent(self) -> None:
        # Mistral returns the identifier the request carried rather than the snapshot it
        # resolved to, so a run made against an alias cannot be attributed after the fact.
        recorder = Recorder(fixture("mistral", "minimal"))
        client = MistralClient(
            model="mistral-small-latest",
            api_key="k" * 20,
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )

        assert client.complete(request()).response_model == "mistral-small-latest"

    def test_cached_prompt_splits_the_input_count(self) -> None:
        # prompt_tokens includes the cached tokens, so recording it as the uncached count
        # would price the whole prompt at the uncached rate.
        recorder = Recorder(fixture("mistral", "cached"))
        client = MistralClient(
            model="mistral-small-latest",
            api_key="k" * 20,
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )

        tokens = client.complete(request()).tokens

        assert tokens.input_cache_read == 3200
        assert tokens.input_uncached == 24
        assert tokens.input_cache_write == 0
        assert tokens.cache_ttl is None
        assert tokens.total_input == 3224

    def test_tool_call_arguments_are_parsed(self) -> None:
        recorder = Recorder(fixture("mistral", "tool_call"))
        client = MistralClient(
            model="mistral-small-latest",
            api_key="k" * 20,
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )

        response = client.complete(request())

        assert [c.name for c in response.tool_calls] == ["lookup_inseam"]
        assert response.tool_calls[0].arguments == {"product_code": "ABC-123"}
        assert response.finish_reason == "tool_calls"


class TestMistralRequests:
    def _send(self, recorder: Recorder, model_request: ModelRequest) -> dict[str, Any]:
        client = MistralClient(
            model="mistral-small-2603",
            api_key="k" * 20,
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )
        client.complete(model_request)
        return recorder.requests[0]

    def test_seed_is_sent_as_random_seed(self) -> None:
        sent = self._send(Recorder(fixture("mistral", "minimal")), request(seed=41))

        assert sent["random_seed"] == 41
        assert "seed" not in sent

    def test_sampling_and_limits_are_sent(self) -> None:
        sent = self._send(
            Recorder(fixture("mistral", "minimal")),
            request(temperature=0.0, max_output_tokens=128),
        )

        assert sent["temperature"] == 0.0
        assert sent["max_tokens"] == 128

    def test_tools_are_translated_to_function_declarations(self) -> None:
        sent = self._send(
            Recorder(fixture("mistral", "tool_call")),
            request(
                tools=[
                    {
                        "name": "lookup_inseam",
                        "description": "Return the inseam.",
                        "input_schema": {"type": "object", "properties": {}},
                    }
                ]
            ),
        )

        assert sent["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "lookup_inseam",
                    "description": "Return the inseam.",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        assert sent["tool_choice"] == "auto"

    def test_output_schema_becomes_a_json_schema_response_format(self) -> None:
        schema = {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }
        sent = self._send(
            Recorder(fixture("mistral", "json_schema")), request(output_schema=schema)
        )

        assert sent["response_format"]["type"] == "json_schema"
        assert sent["response_format"]["json_schema"]["schema"] == schema
        assert sent["response_format"]["json_schema"]["strict"] is True

    def test_a_schema_with_an_optional_field_is_sent_in_the_form_strict_requires(self) -> None:
        """Measured against the live backend: without this it answers with `"source_doc "`."""
        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "source_doc": {
                    "anyOf": [{"type": "string"}, {"type": "null"}],
                    "default": None,
                },
            },
            "required": ["answer"],
        }
        sent = self._send(
            Recorder(fixture("mistral", "json_schema")), request(output_schema=schema)
        )

        on_the_wire = sent["response_format"]["json_schema"]["schema"]
        assert on_the_wire["required"] == ["answer", "source_doc"]
        assert on_the_wire["additionalProperties"] is False
        assert "default" not in on_the_wire["properties"]["source_doc"]
        assert schema["required"] == ["answer"], "the caller's schema is left alone"

    def test_extra_reaches_the_backend_untouched(self) -> None:
        # Prompt caching is opt-in on this backend, and the key that turns it on is a
        # per-call parameter the library does not interpret.
        sent = self._send(
            Recorder(fixture("mistral", "cached")),
            request(extra={"prompt_cache_key": "catalogue-v1"}),
        )

        assert sent["prompt_cache_key"] == "catalogue-v1"


class TestWhatTheBackendReportsAlongside:
    """The allowance the backend publishes, and everything else it sent.

    Both item 7 checkpoint sessions wrote a pacer and both estimated the remaining allowance,
    because the library read these headers for `Retry-After` and discarded the rest.
    """

    def _respond(self, headers: dict[str, str]):
        recorder = Recorder(fixture("mistral", "minimal"), headers=headers)
        client = MistralClient(
            model="mistral-small-2603",
            api_key="k" * 20,
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )
        return client.complete(request())

    def test_the_remaining_allowance_is_reported(self) -> None:
        response = self._respond(
            {
                "x-ratelimit-remaining-req-minute": "46",
                "x-ratelimit-remaining-tokens-minute": "43466",
            }
        )

        assert response.rate_limit.remaining_requests == 46
        assert response.rate_limit.remaining_tokens == 43466

    def test_a_response_carrying_neither_figure_reports_no_allowance(self) -> None:
        """`None` rather than a record of nulls, so a caller can tell absent from zero."""
        assert self._respond({}).rate_limit is None

    def test_a_figure_that_is_not_a_number_is_left_out(self) -> None:
        response = self._respond({"x-ratelimit-remaining-req-minute": "unlimited"})

        assert response.rate_limit is None

    def test_everything_else_is_passed_through(self) -> None:
        """What the library does not read itself is still the builder's to use."""
        response = self._respond({"x-request-id": "req_9f2c", "x-served-by": "eu-west"})

        assert response.provider["x-request-id"] == "req_9f2c"
        assert response.provider["x-served-by"] == "eu-west"

    def test_the_allowance_reaches_the_trajectory(self, tmp_path) -> None:
        recorder = Recorder(
            fixture("mistral", "json_schema"),
            headers={"x-ratelimit-remaining-tokens-minute": "43466"},
        )
        client = MistralClient(
            model="mistral-small-2603",
            api_key="k" * 20,
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )
        pipeline = Pipeline(
            [LLMNode(lambda inputs, ctx: Prompt.user("go"), output_schema=Answer, node_id="ask")],
            budget=Budget.unbounded(),
        )
        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client)

        [call] = [
            r for r in read_trajectory(result.paths.trajectory) if r["record_type"] == "model_call"
        ]
        assert call["rate_limit"]["remaining_tokens"] == 43466
        assert call["rate_limit"]["remaining_requests"] is None

    def test_a_credential_in_the_passthrough_is_redacted(self, tmp_path) -> None:
        """Headers are recorded, and a trajectory gets committed and attached to bug reports."""
        recorder = Recorder(
            fixture("mistral", "json_schema"),
            headers={"set-cookie": "session=super-secret-value", "x-request-id": "req_9f2c"},
        )
        client = MistralClient(
            model="mistral-small-2603",
            api_key="k" * 20,
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )
        pipeline = Pipeline(
            [LLMNode(lambda inputs, ctx: Prompt.user("go"), output_schema=Answer, node_id="ask")],
            budget=Budget.unbounded(),
        )
        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client)

        [call] = [
            r for r in read_trajectory(result.paths.trajectory) if r["record_type"] == "model_call"
        ]
        assert "super-secret-value" not in json.dumps(call)
        assert call["provider"]["x-request-id"] == "req_9f2c"


class TestMistralErrors:
    def test_rejected_credentials_name_the_fix(self) -> None:
        recorder = Recorder(fixture("mistral", "error_bad_key"))
        client = MistralClient(
            model="mistral-small-2603",
            api_key="k" * 20,
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )

        with pytest.raises(CallerFacingError, match="rejected the credentials"):
            client.complete(request())

    def test_unknown_model_reports_the_backend_message(self) -> None:
        recorder = Recorder(fixture("mistral", "error_bad_model"))
        client = MistralClient(
            model="definitely-not-a-model-2020-01",
            api_key="k" * 20,
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )

        with pytest.raises(CallerFacingError, match="Invalid model"):
            client.complete(request())


class TestVLLM:
    def _client(self, recorder: Recorder, **kwargs: Any) -> VLLMClient:
        return VLLMClient(
            model="Qwen/Qwen3-1.7B",
            http_client=recorder.client("http://localhost:8001/v1"),
            **kwargs,
        )

    def test_identity_carries_the_revision_it_was_given(self) -> None:
        client = VLLMClient(model="Qwen/Qwen3-8B", model_revision="a" * 40)

        identity = client.identity()

        assert identity.backend == "self_hosted"
        assert identity.model_revision == "a" * 40

    def test_an_unpinned_repo_id_is_recorded_rather_than_refused(self) -> None:
        # What counts as a pin is FT-14's judgement, in one check, rather than each adapter's.
        assert VLLMClient(model="Qwen/Qwen3-8B").identity().model_revision is None

    def test_seed_is_sent_as_seed(self) -> None:
        recorder = Recorder(fixture("vllm", "minimal"))
        self._client(recorder).complete(request(seed=41))

        assert recorder.requests[0]["seed"] == 41

    def test_cache_counts_are_disjoint_and_sum_to_the_prompt(self) -> None:
        # Measured against a server started with --enable-prompt-tokens-details: a call that
        # both reads a cached prefix and extends it reports the two counts separately.
        recorder = Recorder(fixture("vllm", "cache_partial_overlap"))

        tokens = self._client(recorder).complete(request()).tokens

        assert tokens.input_cache_read == 3200
        assert tokens.input_cache_write == 624
        assert tokens.input_uncached == 0
        assert tokens.total_input == 3824

    def test_missing_token_details_warn_once_and_record_unknown(self) -> None:
        recorder = Recorder(
            fixture("vllm", "no_token_details"), fixture("vllm", "no_token_details")
        )
        client = self._client(recorder)

        with pytest.warns(SimpleAgentsWarning, match="--enable-prompt-tokens-details"):
            tokens = client.complete(request()).tokens

        assert tokens.input_uncached == 3224
        assert isinstance(tokens.input_cache_read, Unknown)
        assert isinstance(tokens.input_cache_write, Unknown)
        assert "unmeasured" in str(tokens.input_cache_read.reason)
        # The total is still recoverable; only the cached share is not.
        assert tokens.total_input == 3224

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            client.complete(request())

    def test_tool_call_arguments_are_parsed(self) -> None:
        recorder = Recorder(fixture("vllm", "tool_call"))

        response = self._client(recorder).complete(request())

        assert response.tool_calls[0].name == "lookup_inseam"
        assert response.tool_calls[0].arguments == {"product_code": "ABC-123"}

    def test_unknown_model_is_caller_facing(self) -> None:
        recorder = Recorder(fixture("vllm", "error_bad_model"))

        with pytest.raises(CallerFacingError, match="does not exist"):
            self._client(recorder).complete(request())


class TestVLLMConcurrency:
    """Reading the divisor compute-basis cost needs, from the server's own metrics.

    Measured against a live server before this shipped: `vllm:num_requests_running` tracked
    what was issued exactly, at 1, 2, 4 and 8, with nothing queued.
    """

    def transport(
        self, metrics: str | None, status: int = 200
    ) -> tuple[httpx.MockTransport, list[str]]:
        seen: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            if request.url.path.endswith("/metrics"):
                if metrics is None:
                    return httpx.Response(status, text="")
                return httpx.Response(status, text=metrics)
            return httpx.Response(200, json=fixture("vllm", "minimal")[1])

        return httpx.MockTransport(handle), seen

    def client(self, metrics: str | None, status: int = 200, **kwargs: Any) -> VLLMClient:
        transport, self.seen = self.transport(metrics, status)
        return VLLMClient(
            model="Qwen/Qwen3-1.7B",
            base_url="http://localhost:8001/v1",
            http_client=httpx.Client(transport=transport, base_url="http://localhost:8001/v1"),
            **kwargs,
        )

    def test_the_server_is_asked_by_default(self) -> None:
        """A figure derived without it is an upper bound, and max_cost then refuses."""
        client = self.client("vllm:num_requests_running 4.0\n")

        response = client.complete(request())

        assert response.concurrent_requests == 4
        assert any("metrics" in url for url in self.seen)

    def test_turning_the_flag_off_leaves_the_field_null(self) -> None:
        """For a server whose metrics endpoint cannot be reached."""
        client = self.client("vllm:num_requests_running 4.0\n", report_concurrency=False)

        response = client.complete(request())

        assert response.concurrent_requests is None
        assert not any("metrics" in url for url in self.seen)

    def test_the_flag_records_what_the_server_had_running(self) -> None:
        client = self.client(
            "# HELP vllm:num_requests_running x\nvllm:num_requests_running 8.0\n",
            report_concurrency=True,
        )

        assert client.complete(request()).concurrent_requests == 8

    def test_a_labelled_gauge_is_read(self) -> None:
        client = self.client(
            'vllm:num_requests_running{model_name="Qwen/Qwen3-1.7B"} 3.0\n',
            report_concurrency=True,
        )

        assert client.complete(request()).concurrent_requests == 3

    def test_an_idle_reading_never_reports_fewer_than_this_call(self) -> None:
        """The call is in flight while the reading is taken, so zero is not a possible answer."""
        client = self.client("vllm:num_requests_running 0.0\n", report_concurrency=True)

        assert client.complete(request()).concurrent_requests == 1

    def test_a_metric_the_server_does_not_publish_leaves_it_null(self) -> None:
        client = self.client("vllm:num_requests_waiting 0.0\n", report_concurrency=True)

        assert client.complete(request()).concurrent_requests is None

    def test_an_unreadable_endpoint_leaves_it_null_rather_than_failing_the_call(self) -> None:
        """A cost figure is better absent than invented, and the call itself is unaffected."""
        client = self.client(None, status=404, report_concurrency=True)

        response = client.complete(request())

        assert response.concurrent_requests is None
        assert response.content is not None

    def test_the_metrics_endpoint_sits_beside_the_api_root(self) -> None:
        client = self.client("vllm:num_requests_running 1.0\n", report_concurrency=True)
        client.complete(request())

        assert "http://localhost:8001/metrics" in self.seen


class TestHTTPBackend:
    def _backend(self, *statuses: int, retry: Retry | None = None) -> tuple[HTTPBackend, list]:
        slept: list[float] = []
        queue = list(statuses)

        def handle(request: httpx.Request) -> httpx.Response:
            status = queue.pop(0)
            headers = {"retry-after": "7"} if status == 429 else {}
            return httpx.Response(status, json={"message": "why"}, headers=headers)

        backend = HTTPBackend(
            base_url="https://x/v1",
            client=httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x/v1"),
            retry=retry or Retry(max_attempts=3, initial_backoff_s=0.5),
            sleep=slept.append,
        )
        return backend, slept

    def test_a_retryable_status_is_retried_then_succeeds(self) -> None:
        slept: list[float] = []
        queue = [503, 200]

        def handle(request: httpx.Request) -> httpx.Response:
            status = queue.pop(0)
            return httpx.Response(status, json={"ok": True} if status == 200 else {})

        backend = HTTPBackend(
            base_url="https://x/v1",
            client=httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x/v1"),
            sleep=slept.append,
        )

        assert backend.post_json("/chat/completions", {}).body == {"ok": True}
        assert slept == [1.0]

    def test_the_default_backoff_sequence_is_what_the_documents_quote(self) -> None:
        """`docs/model-clients.md` §4 and `Retry`'s docstring both name these figures.

        Asserted rather than trusted: the defaults went unexamined for four items while three
        documents described what they did.
        """
        backend, slept = self._backend(503, 503, 503, 503, 503, 503, retry=Retry())

        with pytest.raises(CallerFacingError, match="returned 503"):
            backend.post_json("/chat/completions", {})

        assert slept == [1.0, 2.0, 4.0, 8.0, 16.0]
        assert sum(slept) == 31.0

    def test_the_backoff_stops_doubling_at_the_cap(self) -> None:
        backend, slept = self._backend(*[503] * 9, retry=Retry(max_attempts=9))

        with pytest.raises(CallerFacingError, match="returned 503"):
            backend.post_json("/chat/completions", {})

        assert slept == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]

    def test_the_rate_limit_message_says_how_long_the_attempts_waited(self) -> None:
        backend, slept = self._backend(429, 429, 429)

        with pytest.raises(CallerFacingError, match=r"waited 14s in total"):
            backend.post_json("/chat/completions", {})

        assert sum(slept) == 14.0

    def test_retry_after_overrides_the_backoff(self) -> None:
        backend, slept = self._backend(429, 429, 429)

        with pytest.raises(CallerFacingError, match="rate-limited"):
            backend.post_json("/chat/completions", {})

        assert slept == [7.0, 7.0]

    def test_a_shorter_retry_after_is_waited_rather_than_the_backoff(self) -> None:
        """The backend states when its window reopens; the backoff is a guess made without one.

        Taking the longer of the two charged max_wall_clock_ms for time the provider never
        asked for.
        """
        slept: list[float] = []
        queue = [429, 429, 200]

        def handle(request: httpx.Request) -> httpx.Response:
            status = queue.pop(0)
            return httpx.Response(
                status,
                json={"ok": True} if status == 200 else {"message": "slow down"},
                headers={"retry-after": "0.5"} if status == 429 else {},
            )

        backend = HTTPBackend(
            base_url="https://x/v1",
            client=httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x/v1"),
            retry=Retry(max_attempts=4, initial_backoff_s=8.0),
            sleep=slept.append,
        )

        assert backend.post_json("/chat/completions", {}).body == {"ok": True}
        assert slept == [0.5, 0.5]

    def test_an_http_date_retry_after_is_read_as_a_wait(self) -> None:
        slept: list[float] = []
        queue = [429, 200]
        when = formatdate(time.time() + 12.0, usegmt=True)

        def handle(request: httpx.Request) -> httpx.Response:
            status = queue.pop(0)
            return httpx.Response(
                status,
                json={"ok": True} if status == 200 else {"message": "slow down"},
                headers={"retry-after": when} if status == 429 else {},
            )

        backend = HTTPBackend(
            base_url="https://x/v1",
            client=httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x/v1"),
            retry=Retry(max_attempts=3, initial_backoff_s=1.0),
            sleep=slept.append,
        )

        assert backend.post_json("/chat/completions", {}).body == {"ok": True}
        assert len(slept) == 1 and 10.0 < slept[0] <= 12.0

    def test_a_call_that_gave_up_carries_what_it_waited(self) -> None:
        """The call produced no response, so the wait travels on the exception instead.

        The run was charged max_wall_clock_ms for it either way, and a total that dropped it
        reports a throttled run as a slow one.
        """
        backend, slept = self._backend(429, 429, 429)

        with pytest.raises(CallerFacingError) as raised:
            backend.post_json("/chat/completions", {})

        assert sum(slept) == 14.0
        assert held_back_ms_of(raised.value) == 14_000

    def test_a_backend_that_never_opened_carries_what_it_waited(self) -> None:
        slept: list[float] = []

        def handle(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        backend = HTTPBackend(
            base_url="http://localhost:9/v1",
            client=httpx.Client(
                transport=httpx.MockTransport(handle), base_url="http://localhost:9/v1"
            ),
            retry=Retry(max_attempts=3, initial_backoff_s=2.0),
            sleep=slept.append,
        )

        with pytest.raises(CallerFacingError) as raised:
            backend.post_json("/chat/completions", {})

        assert slept == [2.0, 4.0]
        assert held_back_ms_of(raised.value) == 6_000

    def test_a_call_that_answered_carries_nothing_on_an_exception(self) -> None:
        assert held_back_ms_of(CallerFacingError("nothing waited")) == 0

    def test_a_non_retryable_status_is_not_retried(self) -> None:
        backend, slept = self._backend(400)

        with pytest.raises(CallerFacingError, match="refused the request"):
            backend.post_json("/chat/completions", {})

        assert slept == []

    def test_a_body_that_is_not_json_is_caller_facing(self) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>gateway</html>")

        backend = HTTPBackend(
            base_url="https://x/v1",
            client=httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x/v1"),
        )

        with pytest.raises(CallerFacingError, match="not JSON"):
            backend.post_json("/chat/completions", {})

    def test_an_unreachable_backend_says_nothing_was_recorded(self) -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        backend = HTTPBackend(
            base_url="http://localhost:9/v1",
            client=httpx.Client(
                transport=httpx.MockTransport(handle), base_url="http://localhost:9/v1"
            ),
            retry=Retry(max_attempts=1),
        )

        with pytest.raises(CallerFacingError, match="Could not reach"):
            backend.post_json("/chat/completions", {})

    def test_zero_attempts_is_refused(self) -> None:
        with pytest.raises(ValueError, match="makes no request at all"):
            Retry(max_attempts=0)


class TestRetryAfterHeader:
    """Both forms RFC 9110 allows, and what an unreadable one does."""

    def test_delta_seconds(self) -> None:
        assert retry_after_seconds("30") == 30.0
        assert retry_after_seconds(" 1.5 ") == 1.5

    def test_a_negative_delta_is_no_wait(self) -> None:
        assert retry_after_seconds("-5") == 0.0

    def test_an_http_date_is_the_seconds_until_it(self) -> None:
        assert retry_after_seconds("Wed, 13 Aug 2026 07:28:00 GMT", now=1786605960.0) == 120.0

    def test_a_date_already_past_is_no_wait(self) -> None:
        assert retry_after_seconds("Wed, 13 Aug 2026 07:28:00 GMT", now=1786606200.0) == 0.0

    def test_a_header_in_neither_form_is_no_reading(self) -> None:
        assert retry_after_seconds("soon") is None
        assert retry_after_seconds("") is None
        assert retry_after_seconds(None) is None


class TestEmbeddingTokenCounts:
    """What an embeddings endpoint reports, and what the adapter does where it reports less."""

    def _embedder(self, *bodies: dict[str, Any]) -> OpenAIEmbeddings:
        queue = list(bodies)

        def handle(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=queue.pop(0))

        return OpenAIEmbeddings(
            base_url="http://localhost:8001/v1",
            model="sentence-transformers/all-mpnet-base-v2",
            model_revision="e8c3b32",
            client=httpx.Client(
                transport=httpx.MockTransport(handle), base_url="http://localhost:8001/v1"
            ),
        )

    def _body(self, vectors: int, usage: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": "sentence-transformers/all-mpnet-base-v2",
            "data": [{"index": i, "embedding": [0.1, 0.2]} for i in range(vectors)],
            "usage": usage,
        }

    def test_a_response_with_no_prompt_split_leaves_the_cache_counts_unmeasured(self) -> None:
        """A zero there would say the provider served none of the prompt from a cache."""
        embedder = self._embedder(self._body(2, {"prompt_tokens": 40}))

        tokens = embedder.embed(["one", "two"]).tokens

        assert tokens.input_uncached == 40
        assert isinstance(tokens.input_cache_read, Unknown)
        assert isinstance(tokens.input_cache_write, Unknown)
        assert "prompt_tokens_details" in str(tokens.input_cache_read.reason)
        assert tokens.output == 0
        assert tokens.total == 40

    def test_a_reported_split_is_recorded_as_counted(self) -> None:
        embedder = self._embedder(
            self._body(1, {"prompt_tokens": 40, "prompt_tokens_details": {"cached_tokens": 30}})
        )

        tokens = embedder.embed(["one"]).tokens

        assert tokens.input_uncached == 10
        assert tokens.input_cache_read == 30
        assert tokens.input_cache_write == 0
        assert tokens.total_input == 40

    def test_a_class_unmeasured_by_one_batch_is_unmeasured_for_the_call(self) -> None:
        """The call went out as two requests, and the total cannot be completed without it."""
        embedder = self._embedder(
            self._body(1, {"prompt_tokens": 40, "prompt_tokens_details": {"cached_tokens": 30}}),
            self._body(1, {"prompt_tokens": 12}),
        )
        embedder.batch_size = 1

        tokens = embedder.embed(["one", "two"]).tokens

        assert tokens.input_uncached == 22
        assert isinstance(tokens.input_cache_read, Unknown)

    def test_an_endpoint_reporting_no_usage_is_refused(self) -> None:
        embedder = self._embedder(self._body(1, {}))

        with pytest.raises(ConfigurationError, match="usage.prompt_tokens"):
            embedder.embed(["one"])


def sse_fixture(backend: str, name: str) -> tuple[int, str, dict[str, str]]:
    """A captured server-sent event stream: the status, the raw body, and the headers.

    Stored whole rather than as parsed events, so a test reads what the backend actually put
    on the wire including its framing.
    """
    raw = json.loads((FIXTURES / backend / f"{name}.json").read_text())
    return raw["status"], raw["sse"], raw.get("headers", {})


def sse_client(backend: str, name: str, base_url: str) -> tuple[httpx.Client, list[dict]]:
    """A client serving one captured stream, and the list the request lands in."""
    status, body, headers = sse_fixture(backend, name)
    sent: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(status, text=body, headers=headers)

    return httpx.Client(transport=httpx.MockTransport(handle), base_url=base_url), sent


class TestStreamingOverTheWire:
    """What each backend puts on a streamed response, captured from it on 2026-08-04."""

    def test_mistral_delivers_content_and_reports_usage(self) -> None:
        client, sent = sse_client("mistral", "stream_minimal", "https://api.mistral.ai/v1")
        adapter = MistralClient(model="mistral-small-2603", api_key="k", http_client=client)

        pieces: list[str] = []
        response = adapter.stream(request(temperature=0.0, seed=41), pieces.append)

        assert sent[0]["stream"] is True
        assert "".join(pieces) == response.content
        assert response.finish_reason == "stop"
        assert isinstance(response.tokens.output, int) and response.tokens.output > 0
        assert isinstance(response.tokens.input_uncached, int)

    def test_mistral_publishes_no_allowance_on_a_streamed_response(self) -> None:
        """Measured 2026-08-04: five `x-ratelimit-*` headers on a call, none on a stream."""
        client, _ = sse_client("mistral", "stream_minimal", "https://api.mistral.ai/v1")
        adapter = MistralClient(model="mistral-small-2603", api_key="k", http_client=client)

        response = adapter.stream(request(), lambda piece: None)

        assert response.rate_limit is None, (
            "a streamed Mistral response carries no allowance, so PacedClient has nothing to "
            "pace it against"
        )

    def test_vllm_keeps_the_prompt_token_split_on_a_stream(self) -> None:
        client, _ = sse_client("vllm", "stream_minimal", "http://localhost:8001/v1")
        adapter = VLLMClient(model="Qwen/Qwen3-1.7B", model_revision="a" * 40, http_client=client)

        with warnings.catch_warnings():
            warnings.simplefilter("error", SimpleAgentsWarning)
            response = adapter.stream(request(), lambda piece: None)

        assert isinstance(response.tokens.input_cache_read, int)
        assert isinstance(response.tokens.input_cache_write, int)

    def test_vllm_assembles_tool_call_fragments_by_index(self) -> None:
        """Two parallel calls, ids on the first fragment of each, arguments in pieces."""
        client, _ = sse_client("vllm", "stream_tool_call", "http://localhost:8001/v1")
        adapter = VLLMClient(model="Qwen/Qwen3-1.7B", model_revision="a" * 40, http_client=client)

        response = adapter.stream(request(), lambda piece: None)

        assert [call.name for call in response.tool_calls] == ["search", "search"]
        assert [call.arguments["query"] for call in response.tool_calls] == [
            "belmont",
            "kirkwall",
        ]
        assert len({call.id for call in response.tool_calls}) == 2

    def test_a_response_with_no_usage_is_refused_by_default(self) -> None:
        body = (
            'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\ndata: [DONE]'
        )

        def handle(request_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=body)

        client = httpx.Client(
            transport=httpx.MockTransport(handle), base_url="https://api.mistral.ai/v1"
        )
        adapter = MistralClient(model="mistral-small-2603", api_key="k", http_client=client)

        with pytest.raises(StreamUsageMissing) as refusal:
            adapter.stream(request(), lambda piece: None)
        assert "stream_without_usage=True" in str(refusal.value)
        assert refusal.value.model == "mistral-small-2603"

    def test_the_waiver_records_unknown_counts_rather_than_zeros(self) -> None:
        body = (
            'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\ndata: [DONE]'
        )

        def handle(request_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=body)

        client = httpx.Client(
            transport=httpx.MockTransport(handle), base_url="https://api.mistral.ai/v1"
        )
        adapter = MistralClient(
            model="mistral-small-2603",
            api_key="k",
            http_client=client,
            stream_without_usage=True,
        )

        response = adapter.stream(request(), lambda piece: None)

        assert isinstance(response.tokens.output, Unknown)
        assert response.tokens.total == 0, "an unmeasured count contributes nothing to a sum"

    def test_a_stream_that_breaks_after_a_chunk_is_not_retried(self) -> None:
        attempts = []

        def handle(request_: httpx.Request) -> httpx.Response:
            attempts.append(1)
            return httpx.Response(
                200,
                stream=_BreakingStream(b'data: {"choices":[{"delta":{"content":"Par"}}]}\n\n'),
            )

        client = httpx.Client(
            transport=httpx.MockTransport(handle), base_url="https://api.mistral.ai/v1"
        )
        adapter = MistralClient(model="mistral-small-2603", api_key="k", http_client=client)

        with pytest.raises(CallerFacingError, match="broke after"):
            adapter.stream(request(), lambda piece: None)
        assert len(attempts) == 1, "retrying would re-deliver text the end user has seen"


class _BreakingStream(httpx.SyncByteStream):
    """Delivers one frame and then drops the connection."""

    def __init__(self, first: bytes) -> None:
        self.first = first

    def __iter__(self):
        yield self.first
        raise httpx.ReadError("connection reset")


class TestReasoningOverTheWire:
    """What each backend puts on a response's chain of thought, captured 2026-08-05."""

    def test_vllm_reads_the_reasoning_field_off_a_message(self) -> None:
        """`reasoning`, not `reasoning_content`: vLLM 0.26 renamed it and deprecated the old."""
        recorder = Recorder(fixture("vllm", "reasoning"))
        adapter = VLLMClient(
            model="Qwen/Qwen3-1.7B",
            model_revision="a" * 40,
            http_client=recorder.client("http://localhost:8001/v1"),
        )

        response = adapter.complete(request())

        assert response.reasoning is not None
        assert response.reasoning.text.startswith("\nOkay")
        assert response.reasoning.blocks == ()
        assert "</think>" not in (response.content or "")

    def test_the_reasoning_explains_the_output_token_count(self) -> None:
        """492 characters of content against 745 output tokens, before this was recorded."""
        recorder = Recorder(fixture("vllm", "reasoning"))
        adapter = VLLMClient(
            model="Qwen/Qwen3-1.7B",
            model_revision="a" * 40,
            http_client=recorder.client("http://localhost:8001/v1"),
        )

        response = adapter.complete(request())

        assert len(response.reasoning.text) > len(response.content or "")

    def test_vllm_streams_reasoning_on_its_own_channel(self) -> None:
        client, _ = sse_client("vllm", "stream_reasoning", "http://localhost:8001/v1")
        adapter = VLLMClient(model="Qwen/Qwen3-1.7B", model_revision="a" * 40, http_client=client)

        content: list[str] = []
        thoughts: list[str] = []
        response = adapter.stream(request(), content.append, on_reasoning=thoughts.append)

        assert len(thoughts) > len(content), (
            "this model sends its whole chain of thought before its first word of answer"
        )
        assert "".join(thoughts) == response.reasoning.text
        assert "".join(content) == response.content
        assert not any("</think>" in piece for piece in content)

    def test_a_stream_with_no_reasoning_sink_still_records_it(self) -> None:
        client, _ = sse_client("vllm", "stream_reasoning", "http://localhost:8001/v1")
        adapter = VLLMClient(model="Qwen/Qwen3-1.7B", model_revision="a" * 40, http_client=client)

        response = adapter.stream(request(), lambda piece: None)

        assert response.reasoning is not None and response.reasoning.text

    def test_mistral_reports_no_reasoning_on_any_model_it_serves(self) -> None:
        """Measured 2026-08-05 across all twelve models flagged `reasoning: true`."""
        recorder = Recorder(fixture("mistral", "minimal"))
        adapter = MistralClient(
            model="mistral-small-2603",
            api_key="k",
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )

        assert adapter.complete(request()).reasoning is None


class TestTheUnparsedChainOfThoughtWarning:
    """A reasoning model served without a reasoning parser leaves the chain in the answer."""

    def test_it_warns_once_when_the_chain_arrives_inside_the_content(self) -> None:
        recorder = Recorder(fixture("vllm", "minimal"), fixture("vllm", "minimal"))
        adapter = VLLMClient(
            model="Qwen/Qwen3-1.7B",
            model_revision="a" * 40,
            http_client=recorder.client("http://localhost:8001/v1"),
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", SimpleAgentsWarning)
            adapter.complete(request())
            adapter.complete(request())

        parser = [w for w in caught if "--reasoning-parser" in str(w.message)]
        assert len(parser) == 1, "once per client, not once per call"

    def test_an_empty_think_block_is_not_a_missing_parser(self) -> None:
        """`enable_thinking=false` puts `<think></think>` in the answer, correctly."""
        recorder = Recorder(fixture("vllm", "minimal"))
        adapter = VLLMClient(
            model="Qwen/Qwen3-1.7B",
            model_revision="a" * 40,
            http_client=recorder.client("http://localhost:8001/v1"),
        )
        recorder.queued[0][1]["choices"][0]["message"]["content"] = "<think>\n\n</think>\n\nOK."

        with warnings.catch_warnings():
            warnings.simplefilter("error", SimpleAgentsWarning)
            adapter.complete(request())

    def test_a_parsed_response_does_not_warn(self) -> None:
        recorder = Recorder(fixture("vllm", "reasoning"))
        adapter = VLLMClient(
            model="Qwen/Qwen3-1.7B",
            model_revision="a" * 40,
            http_client=recorder.client("http://localhost:8001/v1"),
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error", SimpleAgentsWarning)
            adapter.complete(request())

    def test_reasoning_false_sets_the_chat_template_switch(self) -> None:
        recorder = Recorder(fixture("vllm", "minimal"))
        adapter = VLLMClient(
            model="Qwen/Qwen3-1.7B",
            model_revision="a" * 40,
            reasoning=False,
            http_client=recorder.client("http://localhost:8001/v1"),
        )

        adapter.complete(request())

        assert recorder.requests[0]["chat_template_kwargs"] == {"enable_thinking": False}

    def test_a_node_setting_it_through_extra_wins(self) -> None:
        recorder = Recorder(fixture("vllm", "minimal"))
        adapter = VLLMClient(
            model="Qwen/Qwen3-1.7B",
            model_revision="a" * 40,
            reasoning=False,
            http_client=recorder.client("http://localhost:8001/v1"),
        )

        adapter.complete(request(extra={"chat_template_kwargs": {"enable_thinking": True}}))

        assert recorder.requests[0]["chat_template_kwargs"] == {"enable_thinking": True}


class TestReasoningOnTheRequest:
    def test_vllm_sends_an_assistant_turn_s_reasoning_back(self) -> None:
        """Measured: within a turn, Qwen3's template renders it, 100 prompt tokens against 58."""
        recorder = Recorder(fixture("vllm", "minimal"))
        adapter = VLLMClient(
            model="Qwen/Qwen3-1.7B",
            model_revision="a" * 40,
            http_client=recorder.client("http://localhost:8001/v1"),
        )

        adapter.complete(
            request(
                messages=[
                    {"role": "user", "content": "how wide?"},
                    {
                        "role": "assistant",
                        "content": "",
                        "reasoning": "I should look it up.",
                        "tool_calls": [{"id": "c1", "name": "look", "arguments": {}}],
                    },
                ]
            )
        )

        assert recorder.requests[0]["messages"][1]["reasoning"] == "I should look it up."

    def test_mistral_drops_it_because_it_has_no_field_for_it(self) -> None:
        recorder = Recorder(fixture("mistral", "minimal"))
        adapter = MistralClient(
            model="mistral-small-2603",
            api_key="k",
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )

        adapter.complete(
            request(
                messages=[
                    {"role": "user", "content": "how wide?"},
                    {"role": "assistant", "content": "22 inches", "reasoning": "32 minus 10."},
                ]
            )
        )

        sent = recorder.requests[0]["messages"][1]
        assert "reasoning" not in sent and "reasoning_content" not in sent


class TestBackendStateOnAToolCall:
    """`ToolCallRequest.provider` is state the backend requires back, and this dialect has no
    field for it. Dropping it makes the following turn unanswerable, and the loss is invisible
    until the backend refuses: the failure dogfood #4 measured as 102 of 102 node executions.
    """

    def test_a_call_carrying_provider_state_is_refused(self) -> None:
        with pytest.raises(CallerFacingError) as raised:
            messages_to_wire(
                [
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "name": "search",
                                "arguments": {"query": "x"},
                                "provider": {"thought_signature": "EjQKMgERTTIP"},
                            }
                        ],
                    },
                ]
            )

        message = str(raised.value)
        assert "thought_signature" in message and "'c1'" in message and "'search'" in message
        assert "docs/model-clients.md" in message

    def test_a_call_with_no_provider_state_is_translated(self) -> None:
        wire = messages_to_wire(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "c1", "name": "search", "arguments": {"query": "x"}}],
                },
            ]
        )

        assert wire[0]["tool_calls"][0]["function"]["arguments"] == '{"query": "x"}'

    def test_an_empty_provider_is_not_state(self) -> None:
        """`ToolCallRequest.provider` defaults to `{}`, and `to_record` omits it. A conversation
        rebuilt from a record written before the field existed must still translate."""
        wire = messages_to_wire(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"id": "c1", "name": "search", "arguments": {}, "provider": {}}],
                },
            ]
        )

        assert wire[0]["tool_calls"][0]["id"] == "c1"

    def test_the_shipped_openai_dialect_adapters_never_trip_it(self) -> None:
        """Neither backend sends state with a tool call, so neither can fill `provider`."""
        recorder = Recorder(fixture("mistral", "minimal"))
        adapter = MistralClient(
            model="mistral-small-2603",
            api_key="k",
            http_client=recorder.client("https://api.mistral.ai/v1"),
        )

        adapter.complete(
            request(
                messages=[
                    {"role": "user", "content": "how wide?"},
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"id": "c1", "name": "look", "arguments": {}}],
                    },
                    {"role": "tool", "tool_call_id": "c1", "content": "22 inches"},
                ]
            )
        )

        assert recorder.requests[0]["messages"][1]["tool_calls"][0]["id"] == "c1"


class TestStrictSchema:
    """`strict: true` names a contract, and a schema Pydantic produced does not meet it.

    Measured against `mistral-small-2603` on 2026-08-07 over ten real prompts: the schema as
    Pydantic writes it came back with a mangled field name such as `"source_doc "` on 10 of 10
    calls, and the same schema through `strict_schema` on 0 of 10.
    """

    def test_every_property_is_required_and_extra_keys_are_forbidden(self) -> None:
        out = strict_schema(
            {
                "type": "object",
                "properties": {"a": {"type": "string"}, "b": {"type": "integer", "default": 0}},
                "required": ["a"],
            }
        )

        assert out["required"] == ["a", "b"]
        assert out["additionalProperties"] is False
        assert "default" not in out["properties"]["b"]

    def test_it_reaches_defs_and_every_nested_subschema(self) -> None:
        out = strict_schema(
            {
                "$defs": {
                    "Unknown": {
                        "type": "object",
                        "properties": {"reason": {"type": "string", "default": None}},
                    }
                },
                "type": "object",
                "properties": {
                    "answer": {"anyOf": [{"type": "string"}, {"$ref": "#/$defs/Unknown"}]},
                    "notes": {
                        "type": "array",
                        "items": {"type": "object", "properties": {"text": {"type": "string"}}},
                    },
                },
            }
        )

        assert out["$defs"]["Unknown"]["required"] == ["reason"]
        assert out["$defs"]["Unknown"]["additionalProperties"] is False
        assert "default" not in out["$defs"]["Unknown"]["properties"]["reason"]
        assert out["properties"]["notes"]["items"]["additionalProperties"] is False
        assert out["properties"]["notes"]["items"]["required"] == ["text"]

    def test_the_caller_s_schema_is_not_touched(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "string", "default": "x"}}}
        before = deepcopy(schema)

        strict_schema(schema)

        assert schema == before

    def test_a_maybe_field_reaches_the_wire_required_and_still_a_union(self) -> None:
        out = strict_schema(Answer.model_json_schema())

        assert out["required"] == ["answer", "source"]
        assert out["properties"]["answer"]["anyOf"][1]["$ref"] == "#/$defs/Unknown"


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class TestGeminiIdentity:
    def test_identity_needs_no_call(self) -> None:
        client = GeminiClient(model="gemini-3.1-flash-lite", api_key="k" * 20)

        identity = client.identity()

        assert identity.backend == "hosted_api"
        assert identity.request_model == "gemini-3.1-flash-lite"

    def test_identity_carries_the_build_string_it_was_given(self) -> None:
        # No response repeats it, so the pin is what the constructor was told.
        client = GeminiClient(
            model="gemini-3.1-flash-lite",
            api_key="k" * 20,
            model_revision="3.1-flash-lite-05-2026",
        )

        assert client.identity().model_revision == "3.1-flash-lite-05-2026"

    def test_a_missing_key_names_the_variable_and_the_redaction(self, monkeypatch) -> None:
        """The variable is cleared, as the Mistral sibling above does.

        Without it this passed on a machine with no key exported and failed on one with, since
        `api_key=None` falls back to the environment and there was then nothing to refuse.
        """
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
            GeminiClient(model="gemini-3.1-flash-lite", api_key=None)

    def test_the_key_travels_in_a_header_rather_than_the_url(self) -> None:
        # A key in the query string reaches every URL a refusal quotes back.
        recorder = HeaderRecorder(fixture("gemini", "minimal"))
        client = GeminiClient(
            model="gemini-3.1-flash-lite",
            api_key="k" * 20,
            http_client=recorder.client(GEMINI_BASE),
        )

        client.complete(request())

        assert recorder.sent_headers[0]["x-goog-api-key"] == "k" * 20
        assert "k" * 20 not in str(recorder.urls[0])


class HeaderRecorder(Recorder):
    """A recorder that also keeps the headers and the URL each request went out with."""

    def __init__(self, *exchanges: tuple[int, dict[str, Any]]) -> None:
        super().__init__(*exchanges)
        self.sent_headers: list[dict[str, str]] = []
        self.urls: list[str] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(json.loads(request.content))
            self.sent_headers.append({k.lower(): v for k, v in request.headers.items()})
            self.urls.append(str(request.url))
            status, body = self.queued.pop(0)
            return httpx.Response(status, json=body, headers=self.headers)

        return httpx.MockTransport(handle)


class TestGeminiRequests:
    def _client(self, recorder: Recorder, **kwargs: Any) -> GeminiClient:
        return GeminiClient(
            model="gemini-3.1-flash-lite",
            api_key="k" * 20,
            http_client=recorder.client(GEMINI_BASE),
            **kwargs,
        )

    def test_the_seed_reaches_the_generation_config(self) -> None:
        # The OpenAI-compatible endpoint refuses this field, which is why the adapter does not
        # use it: `tests/fixtures/wire/gemini/openai_seed_refused.json` is that refusal.
        recorder = Recorder(fixture("gemini", "minimal"))

        self._client(recorder).complete(request(seed=41, temperature=0.0))

        assert recorder.requests[0]["generationConfig"]["seed"] == 41
        assert recorder.requests[0]["generationConfig"]["temperature"] == 0.0

    def test_a_conversation_becomes_contents_and_a_system_instruction(self) -> None:
        recorder = Recorder(fixture("gemini", "minimal"))
        messages = [
            {"role": "system", "content": "Answer briefly."},
            {"role": "user", "content": "Which retailer?"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "search",
                        "arguments": {"query": "belmont"},
                        "provider": {"thought_signature": "EjQK"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "search", "content": "Kirkwall."},
        ]

        self._client(recorder).complete(request(messages=messages))

        sent = recorder.requests[0]
        assert sent["systemInstruction"]["parts"][0]["text"] == "Answer briefly."
        assert [turn["role"] for turn in sent["contents"]] == ["user", "model", "user"]
        call_part = sent["contents"][1]["parts"][0]
        assert call_part["functionCall"]["args"] == {"query": "belmont"}
        assert sent["contents"][2]["parts"][0]["functionResponse"]["response"] == {
            "result": "Kirkwall."
        }

    def test_a_tool_call_goes_back_with_the_signature_it_arrived_with(self) -> None:
        # Without it the backend answers 400: the captured refusal is
        # `tests/fixtures/wire/gemini/error_missing_signature.json`.
        recorder = Recorder(fixture("gemini", "minimal"))
        messages = [
            {"role": "user", "content": "Which retailer?"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "search",
                        "arguments": {"query": "belmont"},
                        "provider": {"thought_signature": "EjQKMgERTTIP"},
                    }
                ],
            },
        ]

        self._client(recorder).complete(request(messages=messages))

        part = recorder.requests[0]["contents"][1]["parts"][0]
        assert part["thoughtSignature"] == "EjQKMgERTTIP"

    def test_a_nested_tool_schema_goes_in_parameters_json_schema(self) -> None:
        # The older `parameters` field is an OpenAPI subset and refuses `$defs` and `$ref`,
        # which every schema derived from a model carries.
        recorder = Recorder(fixture("gemini", "tool_call"))
        tools = [
            {
                "name": "search",
                "description": "Search the catalogue.",
                "input_schema": {
                    "type": "object",
                    "properties": {"filter": {"$ref": "#/$defs/F"}},
                    "$defs": {"F": {"type": "object", "properties": {"kind": {"type": "string"}}}},
                },
            }
        ]

        self._client(recorder).complete(request(tools=tools))

        declared = recorder.requests[0]["tools"][0]["functionDeclarations"][0]
        assert "parameters" not in declared
        assert declared["parametersJsonSchema"]["$defs"]["F"]["type"] == "object"

    def test_an_output_schema_goes_in_response_json_schema(self) -> None:
        recorder = Recorder(fixture("gemini", "json_schema"))

        self._client(recorder).complete(request(output_schema=Answer.model_json_schema()))

        config = recorder.requests[0]["generationConfig"]
        assert config["responseMimeType"] == "application/json"
        assert config["responseJsonSchema"]["$defs"]["Unknown"]["type"] == "object"

    def test_reasoning_is_asked_for_by_default_and_turned_off_on_request(self) -> None:
        # A model that thinks bills those tokens as output whether or not it returns them.
        recorder = Recorder(fixture("gemini", "minimal"), fixture("gemini", "minimal"))
        client = self._client(recorder)
        client.complete(request())

        quiet = GeminiClient(
            model="gemini-3.1-flash-lite",
            api_key="k" * 20,
            reasoning=False,
            http_client=recorder.client(GEMINI_BASE),
        )
        quiet.complete(request())

        assert recorder.requests[0]["generationConfig"]["thinkingConfig"] == {
            "includeThoughts": True
        }
        assert recorder.requests[1]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}

    def test_extra_merges_into_the_generation_config_rather_than_replacing_it(self) -> None:
        # Replacing it would drop the seed the cassette is keyed by and the output schema the
        # response is validated against.
        recorder = Recorder(fixture("gemini", "minimal"))

        self._client(recorder).complete(
            request(seed=41, extra={"generationConfig": {"topK": 5}, "safetySettings": []})
        )

        config = recorder.requests[0]["generationConfig"]
        assert config["seed"] == 41
        assert config["topK"] == 5
        assert recorder.requests[0]["safetySettings"] == []


class TestGeminiResponses:
    def _client(self, recorder: Recorder, **kwargs: Any) -> GeminiClient:
        return GeminiClient(
            model="gemini-3.1-flash-lite",
            api_key="k" * 20,
            http_client=recorder.client(GEMINI_BASE),
            **kwargs,
        )

    def test_a_plain_answer_comes_back_with_its_counts(self) -> None:
        recorder = Recorder(fixture("gemini", "minimal"))

        response = self._client(recorder).complete(request())

        assert response.content == "OK"
        assert response.backend == "hosted_api"
        assert response.response_model == "gemini-3.1-flash-lite"
        assert isinstance(response.tokens.input_uncached, int)
        assert isinstance(response.tokens.output, int)

    def test_a_tool_call_carries_its_arguments_and_its_signature(self) -> None:
        recorder = Recorder(fixture("gemini", "tool_call"))

        response = self._client(recorder).complete(request())

        call = response.tool_calls[0]
        assert call.name == "search"
        assert call.arguments == {"query": "trouser 34 inch inseam"}
        assert call.provider["thought_signature"].startswith("EjQK")

    def test_a_cached_prefix_is_read_out_of_the_prompt_count(self) -> None:
        # Captured on 2026-08-12: 6,129 prompt tokens of which 4,076 were served from cache,
        # with no key sent and nothing configured.
        recorder = Recorder(fixture("gemini", "cached"))

        tokens = self._client(recorder).complete(request()).tokens

        assert tokens.input_cache_read == 4076
        assert tokens.input_uncached == 6129 - 4076
        assert tokens.total_input == 6129

    def test_the_cache_write_count_is_unknown_rather_than_zero(self) -> None:
        recorder = Recorder(fixture("gemini", "cached"))

        tokens = self._client(recorder).complete(request()).tokens

        assert isinstance(tokens.input_cache_write, Unknown)
        assert "cache storage" in str(tokens.input_cache_write.reason)
        assert tokens.cache_ttl is None

    def test_thinking_tokens_are_counted_as_output_and_recorded_as_reasoning(self) -> None:
        # They are billed at the output rate, so a count that left them out would underprice
        # the call. The OpenAI-compatible endpoint reports them in neither count.
        status, body = fixture("gemini", "thinking")
        recorder = Recorder((status, body))

        response = self._client(recorder).complete(request())

        usage = body["usageMetadata"]
        assert usage["thoughtsTokenCount"] > 0
        assert response.tokens.output == usage["candidatesTokenCount"] + usage["thoughtsTokenCount"]
        assert response.reasoning is not None
        assert response.reasoning.text
        assert response.reasoning.text not in (response.content or "")

    def test_the_answer_excludes_the_thinking_part(self) -> None:
        recorder = Recorder(fixture("gemini", "thinking"))

        response = self._client(recorder).complete(request())

        assert response.content is not None
        assert not response.content.startswith("**Sheep")


class TestGeminiErrors:
    def _client(self, recorder: Recorder) -> GeminiClient:
        return GeminiClient(
            model="gemini-3.1-flash-lite",
            api_key="k" * 20,
            http_client=recorder.client(GEMINI_BASE),
        )

    def test_a_bad_key_is_reported_as_credentials_despite_the_400(self) -> None:
        # This backend answers a bad key with 400 rather than 401, so the status alone would
        # send the reader to check the parameters of a request that was fine.
        recorder = Recorder(fixture("gemini", "error_bad_key"))

        with pytest.raises(CallerFacingError, match="rejected the credentials"):
            self._client(recorder).complete(request())

    def test_an_unavailable_model_reports_the_backend_message(self) -> None:
        recorder = Recorder(fixture("gemini", "error_bad_model"))

        with pytest.raises(CallerFacingError, match="no such model or endpoint"):
            self._client(recorder).complete(request())

    def test_an_over_length_request_is_a_context_overflow(self) -> None:
        from simple_agents import ContextOverflow

        recorder = Recorder(fixture("gemini", "error_context_overflow"))

        with pytest.raises(ContextOverflow, match="context window"):
            self._client(recorder).complete(request())

    def test_the_openai_endpoint_refuses_the_seed_every_run_is_keyed_by(self) -> None:
        # Captured from that endpoint rather than asserted. It is why this adapter translates
        # the provider's own dialect instead of reusing `_openai_wire`.
        status, body = fixture("gemini", "openai_seed_refused")

        assert status == 400
        assert "seed" in json.dumps(body)


class TestGeminiStreaming:
    def test_it_delivers_content_and_reports_usage(self) -> None:
        client, sent = sse_client("gemini", "stream_minimal", GEMINI_BASE)
        adapter = GeminiClient(model="gemini-3.1-flash-lite", api_key="k" * 20, http_client=client)

        pieces: list[str] = []
        response = adapter.stream(request(temperature=0.0, seed=41), pieces.append)

        assert "".join(pieces) == response.content
        assert isinstance(response.tokens.output, int) and response.tokens.output > 0
        assert response.rate_limit is None

    def test_a_stream_with_no_usage_is_refused_by_default(self) -> None:
        body = (
            'data: {"candidates":[{"content":{"parts":[{"text":"OK"}]},"finishReason":"STOP"}]}\n\n'
        )

        def handle(request_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=body)

        client = httpx.Client(transport=httpx.MockTransport(handle), base_url=GEMINI_BASE)
        adapter = GeminiClient(model="gemini-3.1-flash-lite", api_key="k" * 20, http_client=client)

        with pytest.raises(StreamUsageMissing) as refusal:
            adapter.stream(request(), lambda piece: None)
        assert "stream_without_usage=True" in str(refusal.value)
