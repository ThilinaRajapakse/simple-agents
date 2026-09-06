"""The three adapters `P3-69` added, against exchanges captured from the real backends.

Every fixture under `tests/fixtures/wire/{openai,openai_responses,anthropic}/` is a response
captured from `api.openai.com` or `api.anthropic.com` on 2026-09-06, stored with the request
that produced it. Replaying them through an `httpx.MockTransport` tests what a model cassette
cannot: how the wire format was read.

No test here needs a key or a network.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from simple_agents import (
    AnthropicClient,
    CallerFacingError,
    ConfigurationError,
    ContextOverflow,
    OpenAIClient,
    OpenAIResponsesClient,
    Reasoning,
    StreamUsageMissing,
    Suspend,
    TokenUsage,
)
from simple_agents.adapters._anthropic_wire import messages_from
from simple_agents.adapters._anthropic_wire import rate_limit_from as anthropic_rate_limit
from simple_agents.adapters._http import HTTPBackend, Retry
from simple_agents.adapters._responses_wire import input_from
from simple_agents.adapters.openai import duration_seconds, rate_limit_from
from simple_agents.schema import Unknown
from test_adapters import Recorder, fixture, request, sse_client

OPENAI_BASE = "https://api.openai.com/v1"
ANTHROPIC_BASE = "https://api.anthropic.com/v1"


def headers_of(backend: str, name: str) -> dict[str, str]:
    from test_adapters import FIXTURES

    raw = json.loads((FIXTURES / backend / f"{name}.json").read_text())
    return dict(raw.get("headers") or {})


# ---------------------------------------------------------------------------------------------
# OpenAI, Chat Completions


class TestOpenAIIdentity:
    def test_identity_needs_no_call(self) -> None:
        client = OpenAIClient(model="gpt-5.6-luna", api_key="k" * 20)

        identity = client.identity()

        assert identity.backend == "hosted_api"
        assert identity.request_model == "gpt-5.6-luna"
        assert identity.model_revision is None

    def test_the_revision_is_a_passthrough(self) -> None:
        client = OpenAIClient(model="gpt-5-mini", api_key="k" * 20, model_revision="2025-08-07")

        assert client.identity().model_revision == "2025-08-07"

    def test_missing_key_is_refused_at_construction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
            OpenAIClient(model="gpt-5.6-luna")

    def test_key_does_not_render(self) -> None:
        client = OpenAIClient(model="gpt-5.6-luna", api_key="do-not-print-" + "k" * 20)

        assert "do-not-print" not in repr(client)
        assert isinstance(client.api_key, SecretStr)

    def test_it_takes_the_seed(self) -> None:
        # Chat Completions accepts a seed, so this adapter makes no declaration; the manifest's
        # `unseeded_models` stays empty for it.
        assert getattr(OpenAIClient, "seeded", True) is True


class TestOpenAIRequests:
    def _client(self, recorder: Recorder, **kwargs: Any) -> OpenAIClient:
        return OpenAIClient(
            model="gpt-5.6-luna",
            api_key="k" * 20,
            http_client=recorder.client(OPENAI_BASE),
            **kwargs,
        )

    def test_the_ceiling_is_sent_under_the_name_every_model_accepts(self) -> None:
        # `max_tokens` is refused by every reasoning model: `error_max_tokens` is that
        # refusal, and `max_completion_tokens` was accepted on gpt-4.1-mini as well.
        recorder = Recorder(fixture("openai", "minimal"))

        self._client(recorder).complete(request(max_output_tokens=300, seed=41))

        sent = recorder.requests[0]
        assert sent["max_completion_tokens"] == 300
        assert "max_tokens" not in sent
        assert sent["seed"] == 41

    def test_the_refusal_of_max_tokens_was_captured(self) -> None:
        status, body = fixture("openai", "error_max_tokens")

        assert status == 400
        assert body["error"]["param"] == "max_tokens"
        assert "max_completion_tokens" in body["error"]["message"]

    def test_reasoning_off_sets_the_effort_to_none(self) -> None:
        recorder = Recorder(fixture("openai", "minimal"), fixture("openai", "minimal"))
        client = self._client(recorder)

        client.complete(request())
        self._client(recorder, reasoning=False).complete(request())

        assert "reasoning_effort" not in recorder.requests[0]
        assert recorder.requests[1]["reasoning_effort"] == "none"

    def test_a_temperature_reaches_the_backend_and_its_refusal_comes_back(self) -> None:
        # The library sends what the node set; the model that refuses it says so.
        recorder = Recorder(fixture("openai", "error_temperature"))

        with pytest.raises(CallerFacingError, match="temperature"):
            self._client(recorder).complete(request(temperature=0.2))

    def test_reasoning_blocks_from_another_backend_are_left_out(self) -> None:
        recorder = Recorder(fixture("openai", "minimal"))
        messages = [
            {"role": "user", "content": "Which retailer?"},
            {
                "role": "assistant",
                "content": "Kirkwall.",
                "reasoning": "It is Kirkwall.",
                "reasoning_blocks": [{"type": "thinking", "thinking": "..", "signature": "x"}],
            },
        ]

        self._client(recorder).complete(request(messages=messages))

        sent = recorder.requests[0]["messages"][1]
        assert sent == {"role": "assistant", "content": "Kirkwall."}


class TestOpenAIResponses:
    def _client(self, recorder: Recorder, **kwargs: Any) -> OpenAIClient:
        return OpenAIClient(
            model="gpt-4.1-mini",
            api_key="k" * 20,
            http_client=recorder.client(OPENAI_BASE),
            **kwargs,
        )

    def test_an_alias_comes_back_as_its_dated_snapshot(self) -> None:
        # Unlike Mistral and Gemini, which echo what was sent. `response_model` is what
        # attributes the run.
        recorder = Recorder(fixture("openai", "minimal"))

        response = self._client(recorder).complete(request())

        assert response.content == "Paris"
        assert response.request_model == "gpt-4.1-mini"
        assert response.response_model == "gpt-4.1-mini-2025-04-14"
        assert response.finish_reason == "stop"
        assert response.reasoning is None

    def test_a_model_billing_no_cache_write_records_zero_for_it(self) -> None:
        recorder = Recorder(fixture("openai", "minimal"))

        tokens = self._client(recorder).complete(request()).tokens

        assert tokens == TokenUsage(
            input_uncached=14,
            input_cache_read=0,
            input_cache_write=0,
            cache_ttl=None,
            output=1,
            output_reasoning=0,
        )

    def test_a_cache_write_on_gpt_5_6_is_taken_out_of_the_prompt_count(self) -> None:
        # Captured 2026-09-06: 3,028 prompt tokens, 3,025 of them written to the cache. The
        # provider bills that class at 1.25x the uncached rate on this model.
        recorder = Recorder(fixture("openai", "cache_written"))

        tokens = self._client(recorder).complete(request()).tokens

        assert tokens.input_cache_write == 3025
        assert tokens.input_cache_read == 0
        assert tokens.input_uncached == 3028 - 3025
        assert tokens.total_input == 3028
        assert tokens.cache_ttl is None

    def test_the_second_call_reads_what_the_first_wrote(self) -> None:
        recorder = Recorder(fixture("openai", "cached"))

        tokens = self._client(recorder).complete(request()).tokens

        assert tokens.input_cache_read == 3025
        assert tokens.input_cache_write == 0
        assert tokens.input_uncached == 3

    def test_reasoning_tokens_are_counted_inside_output_and_recorded_apart(self) -> None:
        # Chat Completions returns no chain of thought. The count is the only explanation the
        # record has for an output figure larger than the answer.
        status, body = fixture("openai", "reasoning")
        recorder = Recorder((status, body))

        response = self._client(recorder).complete(request())

        assert response.content == "25"
        assert response.reasoning is None
        assert response.tokens.output == body["usage"]["completion_tokens"]
        assert response.tokens.output_reasoning == 64
        assert response.tokens.output_reasoning < response.tokens.output

    def test_a_tool_call_carries_its_parsed_arguments(self) -> None:
        recorder = Recorder(fixture("openai", "tool_call"))

        response = self._client(recorder).complete(request())

        call = response.tool_calls[0]
        assert call.name == "lookup"
        assert call.arguments == {"town": "Kirkwall"}
        assert call.provider == {}
        assert response.finish_reason == "tool_calls"

    def test_a_schema_constrained_answer_comes_back_as_json(self) -> None:
        recorder = Recorder(fixture("openai", "json_schema"))

        response = self._client(recorder).complete(request())

        assert json.loads(response.content or "")["answer"]

    def test_the_allowance_is_read_off_the_headers(self) -> None:
        recorder = Recorder(fixture("openai", "minimal"), headers=headers_of("openai", "minimal"))

        response = self._client(recorder).complete(request())

        assert response.rate_limit is not None
        assert response.rate_limit.remaining_requests == 9999
        assert response.rate_limit.remaining_tokens == 9999991
        assert response.rate_limit.resets_in_s == pytest.approx(0.006)
        assert "x-ratelimit-remaining-tokens" not in response.provider

    def test_an_endpoint_reporting_one_prompt_figure_leaves_the_split_unknown(self) -> None:
        status, body = fixture("openai", "minimal")
        body = json.loads(json.dumps(body))
        del body["usage"]["prompt_tokens_details"]
        recorder = Recorder((status, body))

        tokens = self._client(recorder).complete(request()).tokens

        assert tokens.input_uncached == 14
        assert isinstance(tokens.input_cache_read, Unknown)
        assert isinstance(tokens.input_cache_write, Unknown)


class TestOpenAIErrors:
    def _client(self, recorder: Recorder) -> OpenAIClient:
        return OpenAIClient(
            model="gpt-4.1-mini", api_key="k" * 20, http_client=recorder.client(OPENAI_BASE)
        )

    def test_a_bad_key_is_reported_as_credentials(self) -> None:
        recorder = Recorder(fixture("openai", "error_bad_key"))

        with pytest.raises(CallerFacingError, match="rejected the credentials"):
            self._client(recorder).complete(request())

    def test_an_unavailable_model_reports_the_backend_message(self) -> None:
        recorder = Recorder(fixture("openai", "error_bad_model"))

        with pytest.raises(CallerFacingError, match="does not exist"):
            self._client(recorder).complete(request())

    def test_an_over_length_request_is_a_context_overflow(self) -> None:
        recorder = Recorder(fixture("openai", "error_context_overflow"))

        with pytest.raises(ContextOverflow, match="context window"):
            self._client(recorder).complete(request())


class TestOpenAIStreaming:
    def test_it_delivers_content_and_reports_usage_and_the_allowance(self) -> None:
        # Measured 2026-09-06: the allowance headers are on a streamed response too, which is
        # what Mistral does not do.
        client, sent = sse_client("openai", "stream_minimal", OPENAI_BASE)
        adapter = OpenAIClient(model="gpt-4.1-mini", api_key="k" * 20, http_client=client)

        pieces: list[str] = []
        response = adapter.stream(request(seed=41), pieces.append)

        assert sent[0]["stream"] is True
        assert sent[0]["stream_options"] == {"include_usage": True}
        assert "".join(pieces) == response.content
        assert response.finish_reason == "stop"
        assert response.tokens.output == 5
        assert response.tokens.output_reasoning == 0
        assert response.rate_limit is not None
        assert response.rate_limit.remaining_requests == 9999

    def test_a_stream_with_no_usage_is_refused_by_default(self) -> None:
        body = 'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'

        def handle(request_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=body)

        client = httpx.Client(transport=httpx.MockTransport(handle), base_url=OPENAI_BASE)
        adapter = OpenAIClient(model="gpt-4.1-mini", api_key="k" * 20, http_client=client)

        with pytest.raises(StreamUsageMissing):
            adapter.stream(request(), lambda piece: None)


class TestOpenAIRateLimitHeaders:
    def test_a_reset_duration_is_read_in_the_forms_the_provider_writes(self) -> None:
        assert duration_seconds("6ms") == pytest.approx(0.006)
        assert duration_seconds("0s") == 0.0
        assert duration_seconds("1m2.5s") == 62.5
        assert duration_seconds("1h3m") == 3780.0
        assert duration_seconds("soon") is None
        assert duration_seconds(None) is None

    def test_the_later_reset_is_the_one_a_batch_paces_against(self) -> None:
        limit = rate_limit_from(
            {
                "x-ratelimit-remaining-requests": "12",
                "x-ratelimit-remaining-tokens": "4000",
                "x-ratelimit-reset-requests": "2s",
                "x-ratelimit-reset-tokens": "1m",
            }
        )

        assert limit is not None
        assert (limit.remaining_requests, limit.remaining_tokens) == (12, 4000)
        assert limit.resets_in_s == 60.0

    def test_no_headers_is_no_allowance(self) -> None:
        assert rate_limit_from({"content-type": "application/json"}) is None


# ---------------------------------------------------------------------------------------------
# OpenAI, Responses


class TestResponsesIdentity:
    def test_it_declares_that_the_seed_does_not_reach_the_backend(self) -> None:
        # `error_seed` is the refusal: "Unknown parameter: 'seed'". Every run has a seed, so
        # the adapter drops it and says so, and the manifest lists the model.
        status, body = fixture("openai_responses", "error_seed")

        assert status == 400 and body["error"]["param"] == "seed"
        assert OpenAIResponsesClient.seeded is False

    def test_missing_key_is_refused_at_construction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with pytest.raises(ConfigurationError, match="OPENAI_API_KEY"):
            OpenAIResponsesClient(model="gpt-5.6-luna")


class TestResponsesRequests:
    def _client(self, recorder: Recorder, **kwargs: Any) -> OpenAIResponsesClient:
        return OpenAIResponsesClient(
            model="gpt-5-mini",
            api_key="k" * 20,
            http_client=recorder.client(OPENAI_BASE),
            **kwargs,
        )

    def test_the_seed_is_dropped_and_nothing_is_stored(self) -> None:
        recorder = Recorder(fixture("openai_responses", "minimal"))

        self._client(recorder).complete(request(seed=41, max_output_tokens=200))

        sent = recorder.requests[0]
        assert "seed" not in sent
        assert sent["store"] is False
        assert sent["max_output_tokens"] == 200
        assert sent["reasoning"] == {"summary": "auto"}

    def test_reasoning_off_sets_the_effort_to_none(self) -> None:
        recorder = Recorder(fixture("openai_responses", "minimal"))

        self._client(recorder, reasoning=False).complete(request())

        assert recorder.requests[0]["reasoning"] == {"effort": "none"}

    def test_an_effort_in_extra_merges_over_the_summary(self) -> None:
        recorder = Recorder(fixture("openai_responses", "minimal"))

        self._client(recorder).complete(request(extra={"reasoning": {"effort": "low"}}))

        assert recorder.requests[0]["reasoning"] == {"summary": "auto", "effort": "low"}

    def test_a_none_in_extra_leaves_reasoning_off_the_request(self) -> None:
        recorder = Recorder(fixture("openai_responses", "minimal"))

        self._client(recorder).complete(request(extra={"reasoning": None}))

        assert "reasoning" not in recorder.requests[0]

    def test_the_conversation_becomes_input_items_with_the_reasoning_sent_back(self) -> None:
        items = input_from(
            [
                {"role": "system", "content": "Answer briefly."},
                {"role": "user", "content": "Which retailer?"},
                {
                    "role": "assistant",
                    "content": "",
                    "reasoning": "Planning the call.",
                    "reasoning_blocks": [
                        {
                            "type": "reasoning",
                            "id": "rs_1",
                            "summary": [{"type": "summary_text", "text": "Planning"}],
                            "encrypted_content": "gAAA",
                        }
                    ],
                    "tool_calls": [{"id": "call_1", "name": "lookup", "arguments": {"town": "K"}}],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "name": "lookup",
                    "content": "Kirkwall.",
                },
                {"role": "assistant", "content": "It is Kirkwall."},
            ]
        )

        assert items == [
            {"role": "system", "content": "Answer briefly."},
            {"role": "user", "content": "Which retailer?"},
            {
                "type": "reasoning",
                "id": "rs_1",
                "summary": [{"type": "summary_text", "text": "Planning"}],
                "encrypted_content": "gAAA",
            },
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "lookup",
                "arguments": '{"town": "K"}',
            },
            {"type": "function_call_output", "call_id": "call_1", "output": "Kirkwall."},
            {"role": "assistant", "content": "It is Kirkwall."},
        ]

    def test_tools_and_the_schema_take_this_apis_shape(self) -> None:
        recorder = Recorder(fixture("openai_responses", "minimal"))
        tools = [{"name": "lookup", "description": "Look up.", "input_schema": {"type": "object"}}]
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}

        self._client(recorder).complete(request(tools=tools, output_schema=schema))

        sent = recorder.requests[0]
        assert sent["tools"][0]["type"] == "function"
        assert sent["tools"][0]["name"] == "lookup"
        assert "function" not in sent["tools"][0]
        assert sent["text"]["format"]["type"] == "json_schema"
        assert sent["text"]["format"]["schema"]["additionalProperties"] is False


class TestResponsesResponses:
    def _client(self, recorder: Recorder, **kwargs: Any) -> OpenAIResponsesClient:
        return OpenAIResponsesClient(
            model="gpt-5-mini",
            api_key="k" * 20,
            http_client=recorder.client(OPENAI_BASE),
            **kwargs,
        )

    def test_the_reasoning_item_is_recorded_as_text_and_as_the_item_to_send_back(self) -> None:
        # Captured 2026-09-06 with `store: false`: a reasoning item carrying a summary and an
        # encrypted payload, then a function call.
        recorder = Recorder(fixture("openai_responses", "reasoning_tool_call"))

        response = self._client(recorder).complete(request())

        assert response.reasoning is not None
        assert response.reasoning.text and "tool" in response.reasoning.text.lower()
        assert len(response.reasoning.blocks) == 1
        block = response.reasoning.blocks[0]
        assert block["type"] == "reasoning"
        assert block["id"].startswith("rs_")
        assert block["encrypted_content"].startswith("gAAAA")
        assert response.tool_calls[0].name == "lookup"
        assert response.tool_calls[0].arguments == {"town": "Kirkwall"}
        assert response.tool_calls[0].id.startswith("call_")
        assert response.content is None
        assert response.finish_reason == "completed"
        assert response.response_model == "gpt-5-mini-2025-08-07"

    def test_reasoning_tokens_are_inside_output_and_recorded_apart(self) -> None:
        status, body = fixture("openai_responses", "reasoning_tool_call")
        recorder = Recorder((status, body))

        tokens = self._client(recorder).complete(request()).tokens

        assert tokens.output == body["usage"]["output_tokens"] == 122
        assert tokens.output_reasoning == 64
        assert tokens.input_uncached == 54

    def test_the_turn_after_a_tool_result_answers_in_text(self) -> None:
        recorder = Recorder(fixture("openai_responses", "turn_after_tool_result"))

        response = self._client(recorder).complete(request())

        assert response.content == "Kirkwall Hardware."
        assert response.tool_calls == []
        assert response.reasoning is None

    def test_a_cache_write_and_a_cache_read_come_out_of_the_input_count(self) -> None:
        written = Recorder(fixture("openai_responses", "cache_written"))
        read = Recorder(fixture("openai_responses", "cached"))

        first = self._client(written).complete(request()).tokens
        second = self._client(read).complete(request()).tokens

        assert (first.input_uncached, first.input_cache_read, first.input_cache_write) == (
            3,
            0,
            3025,
        )
        assert (second.input_uncached, second.input_cache_read, second.input_cache_write) == (
            3,
            3025,
            0,
        )

    def test_a_schema_constrained_answer_comes_back_as_json(self) -> None:
        recorder = Recorder(fixture("openai_responses", "json_schema"))

        response = self._client(recorder).complete(request())

        assert json.loads(response.content or "") == {"answer": "Paris."}

    def test_a_temperature_refusal_reaches_the_caller_with_the_backend_message(self) -> None:
        recorder = Recorder(fixture("openai_responses", "error_temperature"))

        with pytest.raises(CallerFacingError, match="temperature"):
            self._client(recorder).complete(request(temperature=0.2))


class TestResponsesStreaming:
    def test_the_last_event_carries_the_whole_response(self) -> None:
        # Captured 2026-09-06: 84 summary deltas, 7 argument deltas, and a `response.completed`
        # holding the output items and the usage. Nothing about the call is lost to streaming.
        client, sent = sse_client("openai_responses", "stream_reasoning_tool_call", OPENAI_BASE)
        adapter = OpenAIResponsesClient(model="gpt-5-mini", api_key="k" * 20, http_client=client)

        pieces: list[str] = []
        thoughts: list[str] = []
        response = adapter.stream(request(), pieces.append, on_reasoning=thoughts.append)

        assert sent[0]["stream"] is True
        assert pieces == []
        assert response.content is None
        assert response.reasoning is not None
        assert "".join(thoughts) == response.reasoning.text
        assert len(response.reasoning.blocks) == 1
        assert response.tool_calls[0].name == "lookup"
        assert response.tokens.output_reasoning == 64
        assert response.finish_reason == "completed"
        assert response.rate_limit is not None

    def test_a_stream_that_ends_without_the_response_is_refused(self) -> None:
        body = 'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"OK"}\n\n'

        def handle(request_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=body)

        client = httpx.Client(transport=httpx.MockTransport(handle), base_url=OPENAI_BASE)
        adapter = OpenAIResponsesClient(model="gpt-5-mini", api_key="k" * 20, http_client=client)

        with pytest.raises(StreamUsageMissing):
            adapter.stream(request(), lambda piece: None)


# ---------------------------------------------------------------------------------------------
# Anthropic


class TestAnthropicIdentity:
    def test_identity_needs_no_call_and_the_seed_does_not_reach_the_backend(self) -> None:
        client = AnthropicClient(model="claude-sonnet-5", api_key="k" * 20)

        identity = client.identity()

        assert identity.backend == "hosted_api"
        assert identity.request_model == "claude-sonnet-5"
        assert identity.model_revision is None
        assert AnthropicClient.seeded is False

    def test_missing_key_is_refused_at_construction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
            AnthropicClient(model="claude-sonnet-5")

    def test_key_does_not_render(self) -> None:
        client = AnthropicClient(model="claude-sonnet-5", api_key="do-not-print-" + "k" * 20)

        assert "do-not-print" not in repr(client)

    def test_a_ceiling_of_nothing_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="max_output_tokens=0"):
            AnthropicClient(model="claude-sonnet-5", api_key="k" * 20, max_output_tokens=0)


class TestAnthropicRequests:
    def _client(self, recorder: Recorder, **kwargs: Any) -> AnthropicClient:
        return AnthropicClient(
            model="claude-sonnet-5",
            api_key="k" * 20,
            http_client=recorder.client(ANTHROPIC_BASE),
            **kwargs,
        )

    def test_the_request_carries_the_version_header_the_key_and_a_ceiling(self) -> None:
        recorder = Recorder(fixture("anthropic", "minimal"))
        captured: list[httpx.Request] = []
        transport = recorder.transport()
        original = transport.handler

        def handle(request_: httpx.Request) -> httpx.Response:
            captured.append(request_)
            return original(request_)

        client = httpx.Client(transport=httpx.MockTransport(handle), base_url=ANTHROPIC_BASE)
        adapter = AnthropicClient(model="claude-sonnet-5", api_key="k" * 20, http_client=client)

        adapter.complete(request(seed=41))

        assert captured[0].headers["anthropic-version"] == "2023-06-01"
        assert captured[0].headers["x-api-key"] == "k" * 20
        sent = recorder.requests[0]
        assert sent["max_tokens"] == 16_000
        assert "seed" not in sent
        assert sent["thinking"] == {"type": "adaptive", "display": "summarized"}

    def test_the_nodes_ceiling_wins_over_the_clients(self) -> None:
        recorder = Recorder(fixture("anthropic", "minimal"))

        self._client(recorder, max_output_tokens=500).complete(request(max_output_tokens=2000))

        assert recorder.requests[0]["max_tokens"] == 2000

    def test_reasoning_off_disables_thinking_and_extra_replaces_it(self) -> None:
        recorder = Recorder(fixture("anthropic", "minimal"), fixture("anthropic", "minimal"))

        self._client(recorder, reasoning=False).complete(request())
        self._client(recorder).complete(
            request(extra={"thinking": {"type": "enabled", "budget_tokens": 2048}})
        )

        assert recorder.requests[0]["thinking"] == {"type": "disabled"}
        assert recorder.requests[1]["thinking"] == {"type": "enabled", "budget_tokens": 2048}

    def test_the_conversation_becomes_turns_of_blocks_and_a_system_list(self) -> None:
        turns, system = messages_from(
            [
                {"role": "system", "content": "Answer briefly."},
                {"role": "user", "content": "Which retailer?"},
                {
                    "role": "assistant",
                    "content": "",
                    "reasoning": "Looking it up.",
                    "reasoning_blocks": [
                        {"type": "thinking", "thinking": "Looking it up.", "signature": "Ep0C"}
                    ],
                    "tool_calls": [
                        {"id": "toolu_1", "name": "lookup", "arguments": {"town": "Kirkwall"}},
                        {"id": "toolu_2", "name": "lookup", "arguments": {"town": "Leeds"}},
                    ],
                },
                {"role": "tool", "tool_call_id": "toolu_1", "name": "lookup", "content": "K."},
                {"role": "tool", "tool_call_id": "toolu_2", "name": "lookup", "content": "L."},
                {"role": "assistant", "content": "Kirkwall and Leeds."},
            ]
        )

        assert system == [{"type": "text", "text": "Answer briefly."}]
        assert turns == [
            {"role": "user", "content": [{"type": "text", "text": "Which retailer?"}]},
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Looking it up.", "signature": "Ep0C"},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "lookup",
                        "input": {"town": "Kirkwall"},
                    },
                    {
                        "type": "tool_use",
                        "id": "toolu_2",
                        "name": "lookup",
                        "input": {"town": "Leeds"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "K."},
                    {"type": "tool_result", "tool_use_id": "toolu_2", "content": "L."},
                ],
            },
            {"role": "assistant", "content": [{"type": "text", "text": "Kirkwall and Leeds."}]},
        ]

    def test_a_cache_mark_moves_from_the_message_onto_its_block(self) -> None:
        turns, system = messages_from(
            [
                {
                    "role": "system",
                    "content": "A long prefix.",
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                },
                {
                    "role": "user",
                    "content": "Q",
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                },
            ]
        )

        assert system == [
            {
                "type": "text",
                "text": "A long prefix.",
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ]
        assert turns[0]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
        assert "cache_control" not in turns[0]

    def test_two_ttls_in_one_request_are_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="more than one TTL"):
            messages_from(
                [
                    {"role": "system", "content": "P", "cache_control": {"type": "ephemeral"}},
                    {
                        "role": "user",
                        "content": "Q",
                        "cache_control": {"type": "ephemeral", "ttl": "1h"},
                    },
                ]
            )

    def test_blocks_a_prompt_built_pass_through_unchanged(self) -> None:
        turns, _ = messages_from(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "data": "AAAA"}},
                        {"type": "text", "text": "Read the total."},
                    ],
                }
            ]
        )

        assert turns[0]["content"][0]["type"] == "image"
        assert turns[0]["content"][1] == {"type": "text", "text": "Read the total."}

    def test_tools_and_the_schema_take_this_apis_shape(self) -> None:
        recorder = Recorder(fixture("anthropic", "minimal"))
        tools = [{"name": "lookup", "description": "Look up.", "input_schema": {"type": "object"}}]
        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}

        self._client(recorder).complete(request(tools=tools, output_schema=schema))

        sent = recorder.requests[0]
        assert sent["tools"] == [
            {"name": "lookup", "description": "Look up.", "input_schema": {"type": "object"}}
        ]
        assert sent["output_config"]["format"]["type"] == "json_schema"
        assert sent["output_config"]["format"]["schema"]["additionalProperties"] is False


class TestAnthropicResponses:
    def _client(self, recorder: Recorder, **kwargs: Any) -> AnthropicClient:
        return AnthropicClient(
            model="claude-sonnet-5",
            api_key="k" * 20,
            http_client=recorder.client(ANTHROPIC_BASE),
            **kwargs,
        )

    def test_a_plain_answer_comes_back_with_its_counts(self) -> None:
        recorder = Recorder(fixture("anthropic", "minimal"))

        response = self._client(recorder).complete(request())

        assert response.content == "**Paris**"
        assert response.response_model == "claude-sonnet-5"
        assert response.finish_reason == "end_turn"
        assert response.reasoning is None
        assert response.tokens == TokenUsage(
            input_uncached=15,
            input_cache_read=0,
            input_cache_write=0,
            cache_ttl=None,
            output=7,
            output_reasoning=0,
        )

    def test_a_thinking_block_is_recorded_as_text_and_as_the_block_to_send_back(self) -> None:
        # Captured 2026-09-06 under `display: "summarized"`: a thinking block with its
        # signature, then a tool_use block.
        recorder = Recorder(fixture("anthropic", "thinking_tool_call"))

        response = self._client(recorder).complete(request())

        assert response.reasoning is not None
        assert response.reasoning.text and "Kirkwall" in response.reasoning.text
        block = response.reasoning.blocks[0]
        assert block["type"] == "thinking"
        assert block["signature"].startswith("Ep0C")
        assert response.tool_calls[0].name == "lookup"
        assert response.tool_calls[0].arguments == {"town": "Kirkwall"}
        assert response.tool_calls[0].id.startswith("toolu_")
        assert response.finish_reason == "tool_use"
        assert response.tokens.output_reasoning == 20
        assert response.tokens.output == 73

    def test_the_turn_after_a_tool_result_answers_in_text(self) -> None:
        recorder = Recorder(fixture("anthropic", "turn_after_tool_result"))

        response = self._client(recorder).complete(request())

        assert "Kirkwall Hardware" in (response.content or "")
        assert response.tool_calls == []

    def test_a_five_minute_write_is_recorded_with_its_ttl(self) -> None:
        # Captured 2026-09-06: 4,808 tokens written at the default TTL, 18 uncached beside
        # them. `input_tokens` excludes both cache counts on this backend.
        recorder = Recorder(fixture("anthropic", "cache_written_5m"))

        tokens = self._client(recorder).complete(request()).tokens

        assert tokens.input_cache_write == 4808
        assert tokens.cache_ttl == "5m"
        assert tokens.input_uncached == 18
        assert tokens.input_cache_read == 0
        assert tokens.total_input == 4826

    def test_an_hour_write_is_recorded_with_its_ttl(self) -> None:
        recorder = Recorder(fixture("anthropic", "cache_written_1h"))

        tokens = self._client(recorder).complete(request()).tokens

        assert tokens.input_cache_write == 4812
        assert tokens.cache_ttl == "1h"

    def test_the_second_call_reads_what_the_first_wrote(self) -> None:
        recorder = Recorder(fixture("anthropic", "cached"))

        tokens = self._client(recorder).complete(request()).tokens

        assert tokens.input_cache_read == 4808
        assert tokens.input_cache_write == 0
        assert tokens.cache_ttl is None

    def test_a_write_split_across_two_ttls_is_unmeasured_rather_than_summed(self) -> None:
        status, body = fixture("anthropic", "cache_written_5m")
        body = json.loads(json.dumps(body))
        body["usage"]["cache_creation"]["ephemeral_1h_input_tokens"] = 100
        recorder = Recorder((status, body))

        tokens = self._client(recorder).complete(request()).tokens

        assert isinstance(tokens.input_cache_write, Unknown)
        assert "two TTLs" in tokens.input_cache_write.reason

    def test_a_schema_constrained_answer_comes_back_as_json(self) -> None:
        recorder = Recorder(fixture("anthropic", "json_schema"))

        response = self._client(recorder).complete(request())

        assert json.loads(response.content or "") == {"answer": "Paris"}

    def test_the_allowance_is_read_off_the_headers(self) -> None:
        recorder = Recorder(
            fixture("anthropic", "thinking_tool_call"),
            headers=headers_of("anthropic", "thinking_tool_call"),
        )

        response = self._client(recorder).complete(request())

        assert response.rate_limit is not None
        assert response.rate_limit.remaining_requests == 9999
        assert response.rate_limit.remaining_tokens == 12000000
        assert response.rate_limit.resets_in_s == 0.0
        assert "anthropic-ratelimit-tokens-remaining" not in response.provider

    def test_a_reset_instant_is_measured_from_now(self) -> None:
        limit = anthropic_rate_limit(
            {
                "anthropic-ratelimit-requests-remaining": "5",
                "anthropic-ratelimit-tokens-reset": "2026-09-06T10:04:09Z",
            },
            now=1788688989.0,  # 2026-09-06T10:03:09Z
        )

        assert limit is not None
        assert limit.remaining_requests == 5
        assert limit.remaining_tokens is None
        assert limit.resets_in_s == 60.0


class TestAnthropicErrors:
    def _client(self, recorder: Recorder) -> AnthropicClient:
        return AnthropicClient(
            model="claude-sonnet-5", api_key="k" * 20, http_client=recorder.client(ANTHROPIC_BASE)
        )

    def test_a_bad_key_is_reported_as_credentials(self) -> None:
        recorder = Recorder(fixture("anthropic", "error_bad_key"))

        with pytest.raises(CallerFacingError, match="rejected the credentials"):
            self._client(recorder).complete(request())

    def test_an_unavailable_model_reports_the_backend_message(self) -> None:
        recorder = Recorder(fixture("anthropic", "error_bad_model"))

        with pytest.raises(CallerFacingError, match="claude-nope"):
            self._client(recorder).complete(request())

    def test_an_over_length_request_is_a_context_overflow(self) -> None:
        # "prompt is too long: 230024 tokens > 200000 maximum", a phrase neither of the
        # earlier backends uses.
        recorder = Recorder(fixture("anthropic", "error_context_overflow"))

        with pytest.raises(ContextOverflow, match="context window"):
            self._client(recorder).complete(request())

    def test_a_temperature_refusal_reaches_the_caller_with_the_backend_message(self) -> None:
        recorder = Recorder(fixture("anthropic", "error_temperature"))

        with pytest.raises(CallerFacingError, match="temperature"):
            self._client(recorder).complete(request(temperature=0.0))


class TestAnthropicStreaming:
    def test_a_tool_call_is_assembled_from_its_fragments(self) -> None:
        # Captured 2026-09-06: the model went straight to the tool, so the stream holds one
        # tool_use block in four input_json_delta fragments, and usage on message_start and
        # message_delta.
        client, sent = sse_client("anthropic", "stream_tool_call", ANTHROPIC_BASE)
        adapter = AnthropicClient(model="claude-sonnet-5", api_key="k" * 20, http_client=client)

        pieces: list[str] = []
        response = adapter.stream(request(), pieces.append)

        assert sent[0]["stream"] is True
        assert pieces == []
        assert response.content is None
        assert response.tool_calls[0].name == "lookup"
        assert response.tool_calls[0].arguments == {"town": "Kirkwall"}
        assert response.finish_reason == "tool_use"
        assert response.tokens.input_uncached == 461
        assert response.tokens.output == 52
        assert response.response_model == "claude-sonnet-5"
        assert response.rate_limit is not None

    def test_thinking_streams_as_deltas_and_one_signature(self) -> None:
        events = [
            {
                "type": "message_start",
                "message": {
                    "model": "claude-sonnet-5",
                    "usage": {
                        "input_tokens": 9,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "output_tokens": 1,
                    },
                },
            },
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking", "thinking": "", "signature": ""},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "Two "},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "words."},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "signature_delta", "signature": "Ep0C"},
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "text", "text": ""},
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "text_delta", "text": "Par"},
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "text_delta", "text": "is"},
            },
            {"type": "content_block_stop", "index": 1},
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 12, "output_tokens_details": {"thinking_tokens": 4}},
            },
            {"type": "message_stop"},
        ]
        body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)

        def handle(request_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=body)

        client = httpx.Client(transport=httpx.MockTransport(handle), base_url=ANTHROPIC_BASE)
        adapter = AnthropicClient(model="claude-sonnet-5", api_key="k" * 20, http_client=client)

        pieces: list[str] = []
        thoughts: list[str] = []
        response = adapter.stream(request(), pieces.append, on_reasoning=thoughts.append)

        assert "".join(pieces) == response.content == "Paris"
        assert response.reasoning == Reasoning(
            text="Two words.",
            blocks=({"type": "thinking", "thinking": "Two words.", "signature": "Ep0C"},),
        )
        assert "".join(thoughts) == "Two words."
        assert response.tokens.output == 12
        assert response.tokens.output_reasoning == 4
        assert response.tokens.input_uncached == 9

    def test_an_error_event_inside_the_stream_raises(self) -> None:
        body = 'event: error\ndata: {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}\n\n'

        def handle(request_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=body)

        client = httpx.Client(transport=httpx.MockTransport(handle), base_url=ANTHROPIC_BASE)
        adapter = AnthropicClient(model="claude-sonnet-5", api_key="k" * 20, http_client=client)

        with pytest.raises(CallerFacingError, match="Overloaded"):
            adapter.stream(request(), lambda piece: None)


# ---------------------------------------------------------------------------------------------
# A spent allowance, by code and by the two 400s


class TestSpentAllowanceByCode:
    def backend(self, status: int, body: dict[str, Any]) -> tuple[HTTPBackend, dict[str, int]]:
        calls = {"n": 0}

        def handle(request_: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(status, json=body)

        client = httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x")
        return HTTPBackend(
            base_url="https://x", client=client, retry=Retry(), sleep=lambda s: None
        ), calls

    def test_an_openai_code_stops_the_run_whatever_the_wording(self) -> None:
        backend, calls = self.backend(
            429,
            {"error": {"message": "Some new wording.", "code": "credit_balance_exhausted"}},
        )

        with pytest.raises(Suspend):
            backend.post_json("/chat", {})
        assert calls["n"] == 1

    def test_the_documented_openai_wording_stops_the_run(self) -> None:
        # The body is the provider's documented one, held as a fixture since a funded account
        # cannot produce it.
        status, body = fixture("openai", "error_insufficient_quota")
        backend, calls = self.backend(status, body)

        with pytest.raises(Suspend):
            backend.post_json("/chat", {})
        assert calls["n"] == 1

    def test_anthropics_spend_cap_is_read_off_its_nested_code(self) -> None:
        backend, calls = self.backend(
            429,
            {
                "type": "error",
                "error": {
                    "type": "rate_limit_error",
                    "message": "Some new wording.",
                    "details": {"error_code": "enforced_spend_limit_reached"},
                },
            },
        )

        with pytest.raises(Suspend):
            backend.post_json("/messages", {})
        assert calls["n"] == 1

    def test_anthropics_spent_balance_is_a_400_and_still_stops_the_run(self) -> None:
        status, body = fixture("anthropic", "error_credit_balance")
        backend, calls = self.backend(status, body)

        with pytest.raises(Suspend) as stop:
            backend.post_json("/messages", {})
        assert (status, calls["n"]) == (400, 1)
        assert "credit balance is too low" in stop.value.waiting_for

    def test_an_ordinary_400_is_still_a_bad_request(self) -> None:
        backend, _ = self.backend(
            400, {"error": {"message": "Unsupported parameter: 'temperature'."}}
        )

        with pytest.raises(CallerFacingError, match="refused the request"):
            backend.post_json("/messages", {})
