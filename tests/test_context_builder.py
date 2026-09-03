"""The context builder: what reaches the model, and what the record says about it.

One build per model call under every node kind. The default sends everything and records that
it dropped nothing, which is what makes FT-17 checkable from an artifact rather than inferable
from silence.
"""

from __future__ import annotations

import json
import warnings

import httpx
import pytest

from simple_agents import (
    Prompt,
    AgentNode,
    AppendAll,
    Budget,
    ContextOverflow,
    ContextResult,
    Deterministic,
    DropOldestTurns,
    Dropped,
    FakeModelClient,
    LLMNode,
    MistralClient,
    Retry,
    Pipeline,
    SideEffectClass,
    SimpleAgentsWarning,
    TokenUsage,
    Unknown,
    read_trajectory,
    tool,
)
from simple_agents.context import NodeContext
from simple_agents.models import ToolCallRequest, fake_response

from schemas import Answer, Finding
from conftest import run_path, RUN_ID

FOUND = json.dumps({"answer": "32 inches"})
DONE = json.dumps({"retailer": "Kirkwall", "returns_policy": "free within 30 days"})


def build_prompt(inputs, ctx):
    return Prompt.user("answer: {value}", value=inputs.get("question", ""))


def summarise(inputs, ctx):
    return Prompt.user("summarise: {documents}", documents=inputs["documents"])


def load(inputs, ctx):
    return {"documents": list(inputs["documents"])}


def hunt(inputs, ctx):
    return Prompt.user("find the trouser")


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def look_up(query: str) -> str:
    """Search the catalogue. Returns matching entries."""
    return f"entry for {query}"


def unbounded() -> Budget:
    return Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def one_llm(**kw) -> Pipeline:
    return Pipeline(
        [LLMNode(build_prompt, output_schema=Answer, node_id="answer", **kw)],
        budget=unbounded(),
    )


def fan_out(**kw) -> Pipeline:
    return Pipeline(
        [Deterministic(load), LLMNode(summarise, output_schema=Answer, over="documents", **kw)],
        budget=unbounded(),
    )


def agent(**kw) -> Pipeline:
    return Pipeline(
        [AgentNode(hunt, tools=[look_up], output_schema=Finding, budget=unbounded(), **kw)],
        budget=unbounded(),
    )


def model_calls(trajectory):
    return [r for r in read_trajectory(trajectory) if r["record_type"] == "model_call"]


def unmeasured() -> TokenUsage:
    """What a vLLM server started without `--enable-prompt-tokens-details` reports."""
    reason = Unknown(reason="server reports no prompt_tokens_details")
    return TokenUsage(
        input_uncached=100,
        input_cache_read=reason,
        input_cache_write=reason,
        cache_ttl=None,
        output=5,
    )


class Recorder:
    """A builder that sends everything and keeps what it was handed, for inspection.

    Stateful, which a real builder must not be. It exists to assert on the arguments, and
    nothing in it reaches the messages.
    """

    def __init__(self) -> None:
        self.seen: list[tuple[list[dict], NodeContext]] = []

    def build(self, messages, ctx):
        self.seen.append((list(messages), ctx))
        return ContextResult(messages=list(messages))


class DropAfterFirst:
    """Keeps the first message only, and reports every message it left out."""

    def build(self, messages, ctx):
        if len(messages) < 2:
            return ContextResult(messages=list(messages))
        return ContextResult(
            messages=[messages[0]],
            dropped=tuple(
                Dropped(index=i, role=m["role"], reason="kept the first message only")
                for i, m in enumerate(messages)
                if i > 0
            ),
        )


class TestTheDefault:
    def test_it_sends_what_it_was_given_under_every_node_kind(self, envelope, trajectory):
        client = FakeModelClient(responses=[fake_response(content=FOUND)])
        one_llm().run({}, envelope=envelope, run_id=RUN_ID, model=client)

        assert client.requests[0].messages == [{"role": "user", "content": "answer: "}]

    def test_every_model_call_record_says_nothing_was_dropped(self, envelope, trajectory):
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(3)])
        fan_out().run(
            {"documents": ["a", "b", "c"]}, envelope=envelope, run_id=RUN_ID, model=client
        )

        records = model_calls(trajectory)
        assert len(records) == 3
        # An empty `dropped` is a statement, not an absence. A record with no context field
        # could not distinguish a context builder that dropped nothing from one that said
        # nothing.
        for record in records:
            assert record["context"] == {
                "context_builder": "AppendAll",
                "dropped": [],
                "estimate": None,
            }

    def test_an_agent_loop_records_the_builder_on_every_turn(self, envelope, trajectory):
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c1", name="look_up", arguments={"query": "x"})]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments=json.loads(DONE))]
                ),
            ]
        )
        agent().run({}, envelope=envelope, run_id=RUN_ID, model=client)

        records = model_calls(trajectory)
        assert len(records) == 2
        assert all(r["context"]["context_builder"] == "AppendAll" for r in records)

    def test_the_manifest_names_the_builder_per_node(self, envelope, manifest_path):
        client = FakeModelClient(responses=[fake_response(content=FOUND)])
        one_llm(context=AppendAll(max_input_tokens=1000)).run(
            {}, envelope=envelope, run_id=RUN_ID, model=client
        )

        nodes = json.loads(manifest_path.read_text())["nodes"]
        assert nodes[0]["context_builder"] == {
            "name": "AppendAll",
            "config": {"max_input_tokens": 1000},
        }


class TestWhatTheBuilderIsHanded:
    def test_an_agent_loop_hands_over_the_growing_conversation(self, envelope):
        recorder = Recorder()
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c1", name="look_up", arguments={"query": "x"})]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments=json.loads(DONE))]
                ),
            ]
        )
        agent(context=recorder).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        first, second = (messages for messages, _ in recorder.seen)
        assert len(first) == 1
        # The tool call and its observation, appended by the loop between the two calls.
        assert len(second) == 3
        assert [m["role"] for m in second] == ["user", "assistant", "tool"]

    def test_step_counts_the_loop_iteration(self, envelope):
        recorder = Recorder()
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c1", name="look_up", arguments={"query": "x"})]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments=json.loads(DONE))]
                ),
            ]
        )
        agent(context=recorder).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        assert [ctx.step for _, ctx in recorder.seen] == [1, 2]

    def test_item_index_is_set_during_a_fan_out_and_null_otherwise(self, envelope):
        recorder = Recorder()
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(3)])
        fan_out(context=recorder).run(
            {"documents": ["a", "b", "c"]}, envelope=envelope, run_id=RUN_ID, model=client
        )
        assert [ctx.item_index for _, ctx in recorder.seen] == [0, 1, 2]

        single = Recorder()
        one_llm(context=single).run(
            {},
            envelope=envelope,
            run_id="other",
            model=FakeModelClient(responses=[fake_response(content=FOUND)]),
        )
        assert single.seen[0][1].item_index is None

    def test_each_fan_out_item_starts_from_its_own_prompt(self, envelope):
        recorder = Recorder()
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(3)])
        fan_out(context=recorder).run(
            {"documents": ["a", "b", "c"]}, envelope=envelope, run_id=RUN_ID, model=client
        )

        # Nothing accumulates across items, which is what keeps values[2] a function of
        # item 2 alone.
        assert all(len(messages) == 1 for messages, _ in recorder.seen)
        assert [m[0]["content"] for m, _ in recorder.seen] == [
            "summarise: a",
            "summarise: b",
            "summarise: c",
        ]

    def test_the_previous_call_is_what_the_ratio_is_measured_from(self, envelope):
        recorder = Recorder()
        usage = TokenUsage(
            input_uncached=40, input_cache_read=0, input_cache_write=0, cache_ttl=None, output=5
        )
        client = FakeModelClient(
            responses=[fake_response(content=FOUND, tokens=usage) for _ in range(2)]
        )
        fan_out(context=recorder).run(
            {"documents": ["a", "b"]}, envelope=envelope, run_id=RUN_ID, model=client
        )

        first, second = (ctx for _, ctx in recorder.seen)
        assert first.last_input_tokens is None
        assert first.last_input_chars is None
        assert second.last_input_tokens == 40
        assert second.last_input_chars > 0
        assert second.last_call_index == 0

    def test_an_unmeasured_prompt_size_arrives_as_unknown(self, envelope):
        recorder = Recorder()
        unreported = Unknown(reason="server reports no prompt_tokens_details")
        usage = TokenUsage(
            input_uncached=40,
            input_cache_read=unreported,
            input_cache_write=unreported,
            cache_ttl=None,
            output=5,
        )
        client = FakeModelClient(
            responses=[fake_response(content=FOUND, tokens=usage) for _ in range(2)]
        )
        fan_out(context=recorder).run(
            {"documents": ["a", "b"]}, envelope=envelope, run_id=RUN_ID, model=client
        )

        # Not 40. Summing the classes that were reported would understate the prompt, and a
        # builder extrapolating from that figure would under-count every call.
        assert isinstance(recorder.seen[1][1].last_input_tokens, Unknown)


class TestThePreFlightEstimate:
    def _client(self, count: int, chars_per_token: float = 4.0):
        # 100 prompt tokens against however many characters the request serializes to is set
        # by the response, so the ratio the node measures is fixed by the test.
        usage = TokenUsage(
            input_uncached=100, input_cache_read=0, input_cache_write=0, cache_ttl=None, output=5
        )
        return FakeModelClient(
            responses=[fake_response(content=FOUND, tokens=usage) for _ in range(count)]
        )

    def test_the_first_call_of_a_node_is_not_checked(self, envelope, trajectory):
        # Nothing has been measured, so there is no ratio and no estimate. The backend
        # refusing an over-long request is what bounds this call.
        client = self._client(1)
        one_llm(context=AppendAll(max_input_tokens=1)).run(
            {}, envelope=envelope, run_id=RUN_ID, model=client
        )

        assert model_calls(trajectory)[0]["context"]["estimate"] is None

    def test_the_limit_never_binds_a_single_call_node_even_across_runs(self, envelope):
        # The ratio is measured per run, so a node making one call per run never has a
        # previous call to measure. Nothing is wasted by that: a single call either fits or
        # is refused by the backend, with no earlier turns spent. Pinned here so the boundary
        # cannot move without a test saying so.
        pipeline = one_llm(context=AppendAll(max_input_tokens=1))
        client = self._client(2)

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client)
        pipeline.run({}, envelope=envelope, run_id="second", model=client)

        second = model_calls(run_path(envelope.run_dir, "second", "trajectory.jsonl"))
        assert second[0]["context"]["estimate"] is None

    def test_it_stops_an_agent_loop_on_the_turn_after_the_measurement(self, envelope, trajectory):
        usage = TokenUsage(
            input_uncached=100, input_cache_read=0, input_cache_write=0, cache_ttl=None, output=5
        )
        client = FakeModelClient(
            responses=[
                fake_response(
                    tokens=usage,
                    tool_calls=[ToolCallRequest(id="c1", name="look_up", arguments={"query": "x"})],
                ),
                fake_response(
                    tokens=usage,
                    tool_calls=[
                        ToolCallRequest(id="c2", name="finish", arguments=json.loads(DONE))
                    ],
                ),
            ]
        )
        with pytest.raises(ContextOverflow) as exc:
            agent(context=AppendAll(max_input_tokens=1)).run(
                {}, envelope=envelope, run_id=RUN_ID, model=client
            )

        message = str(exc.value)
        assert message.startswith("Node 'hunt', call 1")
        assert "The run stops here." in message
        assert "estimated" in message
        assert "max_input_tokens=1" in message
        assert "characters per token" in message
        # Turn 1 went through unchecked; turn 2 was refused before it was sent.
        assert len(model_calls(trajectory)) == 1

    def test_an_over_long_fan_out_item_is_collected_rather_than_fatal(self, envelope, trajectory):
        client = self._client(2)
        result = fan_out(context=AppendAll(max_input_tokens=1)).run(
            {"documents": ["a", "b"]}, envelope=envelope, run_id=RUN_ID, model=client
        )

        # One oversized item says nothing about the next, so it fails like any other item.
        assert [o.index for o in result.output.outcomes if o.ok] == [0]
        failure = result.output.failures[0]
        assert failure.index == 1
        assert failure.error["type"] == "ContextOverflow"
        assert "item 1" in failure.error["message"]
        assert "recorded in the node's `failures`" in failure.error["message"]
        assert "estimated" in failure.error["message"]
        assert "max_input_tokens=1" in failure.error["message"]
        # The second call was refused before it was sent.
        assert len(model_calls(trajectory)) == 1

    def test_a_call_under_the_limit_records_the_basis_of_its_estimate(self, envelope, trajectory):
        client = self._client(2)
        fan_out(context=AppendAll(max_input_tokens=1_000_000)).run(
            {"documents": ["a", "b"]}, envelope=envelope, run_id=RUN_ID, model=client
        )

        estimate = model_calls(trajectory)[1]["context"]["estimate"]
        assert estimate["limit"] == 1_000_000
        assert estimate["measured_on_call"] == 0
        assert estimate["chars_per_token"] > 0
        assert estimate["input_tokens"] > 0

    def test_an_unmeasured_prompt_size_produces_no_estimate(self, envelope, trajectory):
        client = FakeModelClient(
            responses=[fake_response(content=FOUND, tokens=unmeasured()) for _ in range(2)]
        )
        # No ratio can be measured, so nothing is estimated and no limit fires. Falling back
        # to a default ratio would put an unmeasured number into the record.
        with pytest.warns(SimpleAgentsWarning):
            fan_out(context=AppendAll(max_input_tokens=1)).run(
                {"documents": ["a", "b"]}, envelope=envelope, run_id=RUN_ID, model=client
            )

        assert [r["context"]["estimate"] for r in model_calls(trajectory)] == [None, None]

    def test_a_ceiling_that_cannot_bind_says_so(self, envelope):
        client = FakeModelClient(
            responses=[fake_response(content=FOUND, tokens=unmeasured()) for _ in range(2)]
        )
        # A configured limit that can never fire is the failure FT-27 refuses for max_cost.
        # Here it is only knowable once a response has come back unmeasured, so it warns.
        with pytest.warns(SimpleAgentsWarning) as caught:
            fan_out(context=AppendAll(max_input_tokens=200_000)).run(
                {"documents": ["a", "b"]}, envelope=envelope, run_id=RUN_ID, model=client
            )

        message = str(caught[0].message)
        assert "max_input_tokens=200000" in message
        assert "'summarise'" in message
        assert "--enable-prompt-tokens-details" in message

    def test_a_measured_prompt_size_warns_about_nothing(self, envelope):
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(2)])
        with warnings.catch_warnings():
            warnings.simplefilter("error", SimpleAgentsWarning)
            fan_out(context=AppendAll(max_input_tokens=1_000_000)).run(
                {"documents": ["a", "b"]}, envelope=envelope, run_id=RUN_ID, model=client
            )


class TestDropOldestTurns:
    """The shipped policy: keep the prompt and the most recent turns, report the rest."""

    def _pattern(self, tool_calls_per_turn):
        turns = [
            fake_response(
                tool_calls=[
                    ToolCallRequest(id=f"c{i}_{j}", name="look_up", arguments={"query": f"q{i}{j}"})
                    for j in range(n)
                ]
            )
            for i, n in enumerate(tool_calls_per_turn)
        ]
        finish = fake_response(
            tool_calls=[ToolCallRequest(id="done", name="finish", arguments=json.loads(DONE))]
        )
        return FakeModelClient(responses=[*turns, finish])

    def test_a_tool_observation_is_never_sent_without_the_call_that_asked_for_it(
        self, envelope, trajectory
    ):
        # Cutting at a fixed offset into the message list survives a conversation growing two
        # messages a turn and breaks on a turn carrying a different number of tool calls. A
        # backend refuses the result: Mistral answers 400 invalid_request_message_order.
        client = self._pattern([1, 2, 1, 1, 2, 1, 1, 1, 1, 3, 1])
        agent(context=DropOldestTurns(keep_turns=4)).run(
            {}, envelope=envelope, run_id=RUN_ID, model=client
        )

        for record in model_calls(trajectory):
            sent = record["inputs"]["messages"]
            asked = {
                call["id"]
                for message in sent
                if message["role"] == "assistant"
                for call in message.get("tool_calls", [])
            }
            unmatched = [
                m["tool_call_id"]
                for m in sent
                if m["role"] == "tool" and m["tool_call_id"] not in asked
            ]
            assert unmatched == []

    def test_it_keeps_the_prompt_and_reports_every_message_it_left_out(self, envelope, trajectory):
        client = self._pattern([1, 1, 1, 1, 1, 1])
        agent(context=DropOldestTurns(keep_turns=2)).run(
            {}, envelope=envelope, run_id=RUN_ID, model=client
        )

        # Six turns of one tool call each: the prompt, then twelve messages. Two turns kept.
        last = model_calls(trajectory)[-1]
        sent = last["inputs"]["messages"]
        assert [m["role"] for m in sent] == ["user", "assistant", "tool", "assistant", "tool"]
        assert [d["index"] for d in last["context"]["dropped"]] == list(range(1, 9))
        assert {d["reason"] for d in last["context"]["dropped"]} == {"older than keep_turns"}

    def test_a_conversation_within_keep_turns_is_sent_whole(self, envelope, trajectory):
        client = self._pattern([1, 1])
        agent(context=DropOldestTurns(keep_turns=6)).run(
            {}, envelope=envelope, run_id=RUN_ID, model=client
        )

        assert all(r["context"]["dropped"] == [] for r in model_calls(trajectory))

    def test_the_manifest_records_how_it_was_configured(self, envelope, manifest_path):
        client = self._pattern([1])
        agent(context=DropOldestTurns(keep_turns=3)).run(
            {}, envelope=envelope, run_id=RUN_ID, model=client
        )

        entry = json.loads(manifest_path.read_text())["nodes"][0]["context_builder"]
        assert entry == {"name": "DropOldestTurns", "config": {"keep_turns": 3}}


class TestABuilderThatDrops:
    def test_its_drops_reach_the_record(self, envelope, trajectory):
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c1", name="look_up", arguments={"query": "x"})]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments=json.loads(DONE))]
                ),
            ]
        )
        agent(context=DropAfterFirst()).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        second = model_calls(trajectory)[1]
        assert second["context"]["context_builder"] == "DropAfterFirst"
        assert second["context"]["dropped"] == [
            {"index": 1, "role": "assistant", "reason": "kept the first message only"},
            {"index": 2, "role": "tool", "reason": "kept the first message only"},
        ]
        assert len(second["inputs"]["messages"]) == 1

    def test_dropping_from_one_call_does_not_shorten_the_next(self, envelope):
        recorder = Recorder()

        class DropThenRecord:
            def build(self, messages, ctx):
                recorder.seen.append((list(messages), ctx))
                return ContextResult(messages=[messages[0]])

        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c1", name="look_up", arguments={"query": "x"})]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="look_up", arguments={"query": "y"})]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="c3", name="finish", arguments=json.loads(DONE))]
                ),
            ]
        )
        agent(context=DropThenRecord()).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        # The loop keeps the whole conversation whatever the builder returns, so a message
        # left out of turn 2 is still there on turn 3.
        assert [len(messages) for messages, _ in recorder.seen] == [1, 3, 5]


class TestTheBackendRefusal:
    def _client_answering(self, status: int, body: dict) -> MistralClient:
        transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
        return MistralClient(
            model="mistral-small-2603",
            api_key="k" * 20,
            http_client=httpx.Client(transport=transport, base_url="https://api.mistral.ai/v1"),
            retry=Retry(max_attempts=1),
        )

    def test_an_over_length_refusal_raises_context_overflow(self, envelope):
        # The body Mistral actually returned, from
        # tests/fixtures/wire/mistral/error_context_overflow.json.
        client = self._client_answering(
            400,
            {
                "object": "error",
                "message": "Prompt contains 314588 tokens and 0 draft tokens, too large for "
                "model with 262144 maximum context length",
                "type": "invalid_request_invalid_args",
                "code": "3051",
            },
        )
        with pytest.raises(ContextOverflow) as exc:
            one_llm().run({}, envelope=envelope, run_id=RUN_ID, model=client)

        message = str(exc.value)
        assert "longer than the model's context window" in message
        assert "over='documents'" in message

    def test_the_vllm_wording_is_matched_too(self, envelope):
        client = self._client_answering(
            400,
            {
                "error": {
                    "message": "This model's maximum context length is 40960 tokens. However, "
                    "the request contains at least 40945 input tokens.",
                    "type": "BadRequestError",
                    "param": "input_tokens",
                    "code": 400,
                }
            },
        )
        with pytest.raises(ContextOverflow):
            one_llm().run({}, envelope=envelope, run_id=RUN_ID, model=client)

    def test_another_bad_request_is_not_read_as_an_overflow(self, envelope):
        client = self._client_answering(
            400, {"object": "error", "message": "Invalid model: nope", "type": "invalid_model"}
        )
        with pytest.raises(Exception) as exc:
            one_llm().run({}, envelope=envelope, run_id=RUN_ID, model=client)
        assert not isinstance(exc.value, ContextOverflow)

    def test_the_failed_call_is_still_recorded_with_its_context(self, envelope, trajectory):
        client = self._client_answering(
            400,
            {
                "object": "error",
                "message": "too large for model with 262144 maximum context length",
                "type": "invalid_request_invalid_args",
            },
        )
        with pytest.raises(ContextOverflow):
            one_llm().run({}, envelope=envelope, run_id=RUN_ID, model=client)

        record = model_calls(trajectory)[0]
        assert record["ended_at"] is None
        assert record["context"]["context_builder"] == "AppendAll"
        assert record["error"]["class"] == "caller_facing"
