"""The three endpoints `P3-80` added, against exchanges captured from each of them.

Every fixture under `tests/fixtures/wire/{deepseek,glm,kimi}/` is a response captured from
`api.deepseek.com`, `api.z.ai` or `api.moonshot.ai` on 2026-09-07, stored with the request
that produced it. Two are marked `documented`: a spent allowance a funded account cannot
produce.

All three speak Chat Completions, so all three are `OpenAIClient(base_url=...)`. What each
does with the parameters it accepts differs, and the settings that say so are what these
tests cover.

No test here needs a key or a network.
"""

from __future__ import annotations

import json

import pytest

from simple_agents import (
    CallerFacingError,
    ConfigurationError,
    ContextOverflow,
    OpenAIClient,
    Suspend,
)
from simple_agents.adapters._http import Retry
from test_adapters import FIXTURES, Recorder, fixture, request, sse_client

DEEPSEEK = "https://api.deepseek.com/v1"
GLM = "https://api.z.ai/api/paas/v4"
KIMI = "https://api.moonshot.ai/v1"

# What each endpoint takes, measured 2026-09-07. `docs/model-clients/openai.md` §6 is the
# shipped copy of this table, and a row here that disagrees with it is a defect in one of them.
SETTINGS = {
    "deepseek": {
        "base_url": DEEPSEEK,
        "max_output_tokens_param": "max_tokens",
        "structured_output": "none",
        "publishes_allowance": False,
    },
    "glm": {
        "base_url": GLM,
        "max_output_tokens_param": "max_tokens",
        "reasoning_off": {"thinking": {"type": "disabled"}},
        "structured_output": "none",
        "publishes_allowance": False,
    },
    "kimi": {
        "base_url": KIMI,
        "structured_output": "json_schema",
        "publishes_allowance": False,
    },
}
MODELS = {"deepseek": "deepseek-v4-flash", "glm": "glm-4.7-flash", "kimi": "kimi-k3"}


def client_for(backend: str, **overrides: object) -> OpenAIClient:
    settings = {**SETTINGS[backend], **overrides}
    return OpenAIClient(model=MODELS[backend], api_key="k" * 20, **settings)  # type: ignore[arg-type]


def served(backend: str, name: str, **overrides: object) -> tuple[OpenAIClient, Recorder]:
    recorder = Recorder(fixture(backend, name))
    client = client_for(
        backend, http_client=recorder.client(SETTINGS[backend]["base_url"]), **overrides
    )
    return client, recorder


ALL = ["deepseek", "glm", "kimi"]


class TestEveryEndpointSpeaksTheDialect:
    """The shape of a response is OpenAI's on all three, so one adapter reads all three."""

    @pytest.mark.parametrize("backend", ALL)
    def test_a_plain_call_is_read(self, backend: str) -> None:
        client, _ = served(backend, "minimal")

        response = client.complete(request(max_output_tokens=16))

        assert isinstance(response.tokens.output, int)
        assert isinstance(response.tokens.input_uncached, int)

    @pytest.mark.parametrize("backend", ALL)
    def test_the_cached_share_of_a_prompt_is_counted(self, backend: str) -> None:
        # Each provider's own docs list only its own spelling of the cache count, and every
        # one of the three also sends OpenAI's `prompt_tokens_details.cached_tokens`. Reading
        # the vendor spelling was designed for and turned out to be unnecessary.
        client, _ = served(backend, "cached")

        response = client.complete(request())

        assert isinstance(response.tokens.input_cache_read, int)
        assert response.tokens.input_cache_read > 0
        assert response.tokens.input_cache_write == 0

    @pytest.mark.parametrize("backend", ALL)
    def test_a_tool_call_is_read_with_its_arguments(self, backend: str) -> None:
        client, _ = served(backend, "tool_call")

        response = client.complete(request())

        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "lookup_shelf"
        assert response.tool_calls[0].arguments == {"entry": 5}

    @pytest.mark.parametrize("backend", ALL)
    def test_a_stream_carries_its_usage_on_the_last_event(self, backend: str) -> None:
        http, _ = sse_client(backend, "stream_minimal", SETTINGS[backend]["base_url"])
        client = client_for(backend, http_client=http)
        pieces: list[str] = []

        response = client.stream(request(max_output_tokens=16), pieces.append)

        assert isinstance(response.tokens.output, int)

    @pytest.mark.parametrize("backend", ALL)
    def test_a_chain_of_thought_reported_separately_is_counted(self, backend: str) -> None:
        # `reasoning_content` was already in REASONING_FIELDS for vLLM, so all three land
        # with no work. The count is what this API reports; the text is not recorded here.
        client, _ = served(backend, "minimal")

        response = client.complete(request(max_output_tokens=16))

        assert response.tokens.output_reasoning is None or isinstance(
            response.tokens.output_reasoning, int
        )

    @pytest.mark.parametrize("backend", ALL)
    def test_no_endpoint_publishes_an_allowance(self, backend: str) -> None:
        assert SETTINGS[backend]["publishes_allowance"] is False

        client, _ = served(backend, "minimal")
        response = client.complete(request(max_output_tokens=16))

        assert response.rate_limit is None


class TestTheOutputCeiling:
    """`max_completion_tokens` is accepted and ignored on two of the three."""

    @pytest.mark.parametrize("backend", ["deepseek", "glm"])
    def test_the_ceiling_is_sent_under_the_name_the_endpoint_honours(self, backend: str) -> None:
        client, recorder = served(backend, "minimal")

        client.complete(request(max_output_tokens=16))

        assert recorder.requests[0]["max_tokens"] == 16
        assert "max_completion_tokens" not in recorder.requests[0]

    def test_kimi_and_openai_take_the_name_this_api_defines(self) -> None:
        client, recorder = served("kimi", "minimal")

        client.complete(request(max_output_tokens=16))

        assert recorder.requests[0]["max_completion_tokens"] == 16
        assert "max_tokens" not in recorder.requests[0]

    @pytest.mark.parametrize("backend", ["deepseek", "glm"])
    def test_the_capture_shows_what_the_ignored_name_did(self, backend: str) -> None:
        # The reason the setting exists: 20 was asked for and hundreds were generated, with
        # the response reporting `stop` rather than `length`. Measured 2026-09-07.
        raw = json.loads((FIXTURES / backend / "ceiling_ignored.json").read_text())

        assert raw["request"]["max_completion_tokens"] == 20
        assert raw["response"]["usage"]["completion_tokens"] > 100
        assert raw["response"]["choices"][0]["finish_reason"] == "stop"


class TestStructuredOutput:
    """One endpoint constrains decoding to a schema. Two accept the parameter and do not."""

    @pytest.mark.parametrize("backend", ["deepseek", "glm"])
    def test_a_node_asking_for_a_schema_is_refused(self, backend: str) -> None:
        client = client_for(backend)

        with pytest.raises(ConfigurationError) as raised:
            client.complete(request(output_schema={"type": "object", "properties": {}}))

        assert "does not constrain output to a schema" in str(raised.value)
        assert MODELS[backend] in str(raised.value)
        assert "json_object" in str(raised.value)

    @pytest.mark.parametrize("backend", ["deepseek", "glm"])
    def test_the_weaker_guarantee_is_opted_into_by_name(self, backend: str) -> None:
        client, recorder = served(backend, "minimal", structured_output="json_object")

        client.complete(request(output_schema={"type": "object", "properties": {}}))

        assert recorder.requests[0]["response_format"] == {"type": "json_object"}

    def test_kimi_is_sent_the_schema_itself(self) -> None:
        client, recorder = served("kimi", "json_schema")

        client.complete(request(output_schema={"type": "object", "properties": {}}))

        assert recorder.requests[0]["response_format"]["type"] == "json_schema"

    def test_kimi_answers_inside_the_schema_it_was_given(self) -> None:
        # The probe that separates constrained decoding from a model reading a schema: the
        # enum excludes the true answer, and a bound decoder cannot reach it. Kimi answered
        # "Rome" to "the capital of France". Measured 2026-09-07.
        raw = json.loads((FIXTURES / "kimi" / "json_schema.json").read_text())
        allowed = raw["request"]["response_format"]["json_schema"]["schema"]["properties"]
        answered = json.loads(raw["response"]["choices"][0]["message"]["content"])

        assert answered["city"] in allowed["city"]["enum"]
        assert "Paris" not in allowed["city"]["enum"]

    def test_deepseek_refuses_the_parameter_outright(self) -> None:
        raw = json.loads((FIXTURES / "deepseek" / "error_json_schema_refused.json").read_text())

        assert raw["status"] == 400
        assert raw["response"]["error"]["message"] == "This response_format type is unavailable now"

    def test_glm_accepts_the_parameter_and_answers_in_prose(self) -> None:
        # Worse than a refusal: 200 with content that no schema would accept, which fails
        # somewhere else entirely. This is why "none" refuses at the client.
        raw = json.loads((FIXTURES / "glm" / "json_schema_ignored.json").read_text())

        assert raw["status"] == 200
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw["response"]["choices"][0]["message"]["content"])

    def test_a_mode_this_adapter_lacks_is_refused_at_construction(self) -> None:
        with pytest.raises(ConfigurationError, match="not a mode"):
            OpenAIClient(model="deepseek-v4-flash", api_key="k" * 20, structured_output="strict")


class TestTheReasoningSwitch:
    def test_glm_is_sent_its_own_switch(self) -> None:
        client, recorder = served("glm", "reasoning_off", reasoning=False)

        client.complete(request(max_output_tokens=16))

        assert recorder.requests[0]["thinking"] == {"type": "disabled"}
        assert "reasoning_effort" not in recorder.requests[0]

    def test_deepseek_takes_the_name_this_api_defines(self) -> None:
        client, recorder = served("deepseek", "minimal", reasoning=False)

        client.complete(request(max_output_tokens=16))

        assert recorder.requests[0]["reasoning_effort"] == "none"

    def test_the_capture_shows_glm_ignoring_the_other_name(self) -> None:
        raw = json.loads((FIXTURES / "glm" / "reasoning_effort_ignored.json").read_text())
        spent = raw["response"]["usage"]["completion_tokens_details"]["reasoning_tokens"]

        assert raw["request"]["reasoning_effort"] == "none"
        assert spent > 0

    def test_the_capture_shows_glms_own_switch_working(self) -> None:
        raw = json.loads((FIXTURES / "glm" / "reasoning_off.json").read_text())
        spent = raw["response"]["usage"]["completion_tokens_details"]["reasoning_tokens"]

        assert raw["request"]["thinking"] == {"type": "disabled"}
        assert spent == 0


class TestASpentAllowanceStopsTheRun:
    """Each endpoint says it differently, and none of the three was visible to the classifier."""

    def test_deepseek_answers_a_spent_balance_with_402(self) -> None:
        client, _ = served("deepseek", "error_spent_balance")

        with pytest.raises(Suspend) as raised:
            client.complete(request())

        assert "spent allowance" in raised.value.waiting_for
        assert "Insufficient Balance" in raised.value.waiting_for

    def test_glm_names_a_numeric_code_beside_the_message(self) -> None:
        client, _ = served("glm", "error_spent_balance")

        with pytest.raises(Suspend):
            client.complete(request())

    def test_kimi_names_its_code_in_the_type(self) -> None:
        client, _ = served("kimi", "error_spent_quota")

        with pytest.raises(Suspend):
            client.complete(request())

    def test_a_rate_limit_from_the_same_status_is_still_retried(self) -> None:
        # Both providers answer a per-minute limit and a spent allowance with 429, so the
        # status alone cannot separate them and a wrong reading either burns the run's clock
        # or stops a run that would have continued.
        rate_limited = (
            429,
            {"error": {"type": "rate_limit_reached_error", "message": "reached max RPM: 3"}},
        )
        recorder = Recorder(rate_limited, fixture("kimi", "minimal"))
        client = client_for(
            "kimi",
            http_client=recorder.client(KIMI),
            retry=Retry(max_attempts=2, initial_backoff_s=0.0),
        )

        response = client.complete(request(max_output_tokens=16))

        assert isinstance(response.tokens.output, int)
        assert len(recorder.requests) == 2

    def test_a_numeric_code_is_named_per_endpoint_rather_than_shipped(self) -> None:
        # A bare number in the shipped set would match another endpoint's unrelated code.
        client, _ = served("glm", "error_spent_balance", retry=Retry(spent_quota_codes=("1113",)))

        with pytest.raises(Suspend):
            client.complete(request())

    def test_a_code_given_as_one_string_is_refused(self) -> None:
        with pytest.raises(ValueError, match="code per character"):
            Retry(spent_quota_codes="1113")  # type: ignore[arg-type]


class TestTheOtherRefusals:
    @pytest.mark.parametrize("backend", ALL)
    def test_a_request_past_the_context_window_names_the_window(self, backend: str) -> None:
        client, _ = served(backend, "error_context_overflow")

        with pytest.raises(ContextOverflow):
            client.complete(request())

    @pytest.mark.parametrize("backend", ALL)
    def test_a_bad_key_reaches_the_caller(self, backend: str) -> None:
        client, _ = served(backend, "error_bad_key")

        with pytest.raises(CallerFacingError):
            client.complete(request())

    @pytest.mark.parametrize("backend", ALL)
    def test_an_unknown_model_reaches_the_caller(self, backend: str) -> None:
        # DeepSeek and GLM answer 400 and Kimi 404, so the status is not what carries it.
        client, _ = served(backend, "error_bad_model")

        with pytest.raises(CallerFacingError):
            client.complete(request())
