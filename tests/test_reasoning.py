"""Reasoning output through the model client seam.

Two layers, on the precedent `test_streaming.py` sets. Here the client is a fake that reports a
chain of thought, which tests what the library does with one. What a backend actually puts on
the wire is `test_adapters.py` over captured fixtures, and `test_adapter_integration.py` over
recordings taken from the live backends.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    Cassette,
    ConfigurationError,
    FakeModelClient,
    LLMNode,
    MistralClient,
    PacedClient,
    Pipeline,
    Reasoning,
    RunEnvelope,
    SideEffectClass,
    TokenEvent,
    fake_response,
    tool,
)

from conftest import run_path, RUN_ID
from schemas import Answer

BUDGET = Budget(max_steps=8, max_tokens=100_000, max_cost=None, max_wall_clock_ms=120_000)

ANSWER = json.dumps({"answer": "32 inches", "source": "spec"})
THOUGHT = "The shelf is 32 inches and two books take 10, so 22 remain."


def thinking_response(content: str | None = ANSWER, text: str | None = THOUGHT, **kw):
    response = fake_response(content=content, **kw)
    response.reasoning = Reasoning(text=text) if text is not None else None
    return response


class ThinkingFake:
    """A client that reports a chain of thought separately, and streams it on its own sink."""

    def __init__(self, responses: list, reasoning_pieces: int = 4) -> None:
        self.responses = list(responses)
        self.requests: list = []
        self.reasoning_pieces = reasoning_pieces

    def identity(self):
        return FakeModelClient().identity()

    def complete(self, request):
        self.requests.append(request)
        return self.responses.pop(0)

    def stream(self, request, on_chunk, *, on_reasoning=None):
        self.requests.append(request)
        response = self.responses.pop(0)
        thought = response.reasoning.text if response.reasoning else ""
        if on_reasoning is not None and thought:
            size = max(1, len(thought) // self.reasoning_pieces)
            for i in range(0, len(thought), size):
                on_reasoning(thought[i : i + size])
        content = response.content or ""
        for i in range(0, len(content), 7):
            on_chunk(content[i : i + 7])
        return response


class BlindFake:
    """A client written before reasoning existed: two positional parameters, no keyword."""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)

    def identity(self):
        return FakeModelClient().identity()

    def complete(self, request):
        return self.responses.pop(0)

    def stream(self, request, on_chunk):
        response = self.responses.pop(0)
        for piece in (response.content or "",):
            on_chunk(piece)
        return response


def one_node(*, stream: bool = True) -> Pipeline:
    return Pipeline(
        [
            LLMNode(
                lambda inputs, ctx: Prompt.user("what size?"),
                output_schema=Answer,
                node_id="answer",
                stream=stream,
            )
        ],
        budget=BUDGET,
    )


def model_calls(trajectory: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in trajectory.read_text().splitlines()
        if json.loads(line)["record_type"] == "model_call"
    ]


class TestWhatTheRecordSays:
    def test_the_chain_of_thought_is_recorded_beside_the_answer(self, envelope):
        pipeline = one_node(stream=False)
        pipeline.run(
            {}, envelope=envelope, model=ThinkingFake([thinking_response()]), run_id=RUN_ID
        )

        outputs = model_calls(run_path(envelope.run_dir, RUN_ID, "trajectory.jsonl"))[0]["outputs"]
        assert outputs["reasoning"] == {"text": THOUGHT, "blocks": []}
        assert outputs["content"] == ANSWER

    def test_a_backend_reporting_none_records_null(self, envelope):
        pipeline = one_node(stream=False)
        pipeline.run(
            {},
            envelope=envelope,
            model=FakeModelClient([fake_response(ANSWER)]),
            run_id=RUN_ID,
        )

        outputs = model_calls(run_path(envelope.run_dir, RUN_ID, "trajectory.jsonl"))[0]["outputs"]
        assert outputs["reasoning"] is None

    def test_opaque_blocks_are_recorded_as_the_backend_sent_them(self, envelope):
        response = fake_response(content=ANSWER)
        response.reasoning = Reasoning(
            text=None,
            blocks=({"type": "redacted_thinking", "data": "Ej8BCkY..."},),
        )
        one_node(stream=False).run(
            {}, envelope=envelope, model=ThinkingFake([response]), run_id=RUN_ID
        )

        outputs = model_calls(run_path(envelope.run_dir, RUN_ID, "trajectory.jsonl"))[0]["outputs"]
        assert outputs["reasoning"] == {
            "text": None,
            "blocks": [{"type": "redacted_thinking", "data": "Ej8BCkY..."}],
        }


class TestTheAgentConversation:
    """The defect this item exists to fix: a turn the model is still working on."""

    def test_the_assistant_turn_carries_the_reasoning_back(self, envelope):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def look(query: str) -> str:
            """Look something up."""
            return "32 inches"

        client = ThinkingFake(
            [
                thinking_response(
                    content=None,
                    text="I should look this up rather than guess.",
                    tool_calls=[_call("look", {"query": "shelf"})],
                ),
                thinking_response(
                    content=None,
                    text="The lookup says 32 inches, so I can finish.",
                    tool_calls=[_call("finish", {"answer": "32 inches", "source": "spec"})],
                ),
            ]
        )
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: Prompt.user("how wide?"),
                    tools=[look],
                    output_schema=Answer,
                    budget=BUDGET,
                    node_id="hunt",
                )
            ],
            budget=BUDGET,
        )
        pipeline.run({}, envelope=envelope, model=client)

        second = client.requests[1].messages
        assistant = [m for m in second if m["role"] == "assistant"]
        assert assistant[0]["reasoning"] == "I should look this up rather than guess."

    def test_a_turn_with_no_reasoning_carries_no_key(self, envelope):
        client = ThinkingFake(
            [
                thinking_response(content="not a tool call", text=None),
                thinking_response(
                    content=None,
                    text=None,
                    tool_calls=[_call("finish", {"answer": "32 inches", "source": "spec"})],
                ),
            ]
        )
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: Prompt.user("how wide?"),
                    tools=[],
                    output_schema=Answer,
                    budget=BUDGET,
                    node_id="hunt",
                )
            ],
            budget=BUDGET,
        )
        pipeline.run({}, envelope=envelope, model=client)

        assistant = [m for m in client.requests[1].messages if m["role"] == "assistant"]
        assert "reasoning" not in assistant[0], (
            "A conversation from a backend reporting no reasoning has to stay byte-identical "
            "to one built before the field existed."
        )


class TestTheLiveSink:
    def test_reasoning_reaches_its_own_sink_as_it_arrives(self, envelope):
        thoughts: list[TokenEvent] = []
        content: list[TokenEvent] = []
        one_node().run(
            {},
            envelope=envelope,
            model=ThinkingFake([thinking_response()]),
            on_token=content.append,
            on_reasoning=thoughts.append,
        )

        assert "".join(e.text for e in thoughts) == THOUGHT
        assert "".join(e.text for e in content) == ANSWER
        assert {e.kind for e in thoughts} == {"reasoning"}
        assert {e.kind for e in content} == {"content"}

    def test_the_two_channels_are_independent(self, envelope):
        thoughts: list[TokenEvent] = []
        one_node().run(
            {},
            envelope=envelope,
            model=ThinkingFake([thinking_response()]),
            on_reasoning=thoughts.append,
            run_id=RUN_ID,
        )

        assert "".join(e.text for e in thoughts) == THOUGHT

    def test_the_record_counts_the_reasoning_pieces(self, envelope):
        one_node().run(
            {},
            envelope=envelope,
            model=ThinkingFake([thinking_response()], reasoning_pieces=4),
            on_token=lambda e: None,
            on_reasoning=lambda e: None,
            run_id=RUN_ID,
        )

        stream = model_calls(run_path(envelope.run_dir, RUN_ID, "trajectory.jsonl"))[0]["stream"]
        assert stream["reasoning_chunks"] >= 4
        assert stream["chunks"] >= 1

    def test_a_run_with_no_reasoning_sink_counts_no_reasoning_chunks(self, envelope):
        one_node().run(
            {},
            envelope=envelope,
            model=ThinkingFake([thinking_response()]),
            on_token=lambda e: None,
            run_id=RUN_ID,
        )

        stream = model_calls(run_path(envelope.run_dir, RUN_ID, "trajectory.jsonl"))[0]["stream"]
        assert stream["reasoning_chunks"] == 0


class TestRefusals:
    def test_a_client_that_takes_no_reasoning_sink_is_refused_by_name(self, envelope):
        with pytest.raises(ConfigurationError) as raised:
            one_node().run(
                {},
                envelope=envelope,
                model=BlindFake([thinking_response()]),
                on_reasoning=lambda e: None,
            )

        assert "BlindFake" in str(raised.value)
        assert "on_reasoning" in str(raised.value)

    def test_a_reasoning_sink_no_node_can_reach_is_refused(self, envelope):
        with pytest.raises(ConfigurationError) as raised:
            one_node(stream=False).run(
                {},
                envelope=envelope,
                model=ThinkingFake([thinking_response()]),
                on_reasoning=lambda e: None,
            )

        assert "stream=True" in str(raised.value)

    def test_an_adapter_whose_pieces_do_not_rebuild_its_reasoning_is_refused(self, envelope):
        class Lies(ThinkingFake):
            def stream(self, request, on_chunk, *, on_reasoning=None):
                response = self.responses.pop(0)
                if on_reasoning is not None:
                    on_reasoning("something else entirely")
                on_chunk(response.content or "")
                return response

        with pytest.raises(Exception) as raised:
            one_node().run(
                {},
                envelope=envelope,
                model=Lies([thinking_response()]),
                on_token=lambda e: None,
                on_reasoning=lambda e: None,
            )

        assert "reasoning" in str(raised.value)

    def test_mistral_refuses_a_control_it_cannot_apply(self):
        with pytest.raises(ConfigurationError) as raised:
            MistralClient(model="mistral-small-2603", api_key="x", reasoning=False)

        assert "prompt_mode" in str(raised.value)


class TestBlindAdapters:
    """An adapter written before this item keeps working, and is never handed the keyword."""

    def test_a_two_parameter_stream_is_never_called_with_a_third(self, envelope):
        content: list[TokenEvent] = []
        one_node().run(
            {},
            envelope=envelope,
            model=BlindFake([fake_response(content=ANSWER)]),
            on_token=content.append,
        )

        assert "".join(e.text for e in content) == ANSWER

    def test_paced_client_republishes_what_it_wraps(self):
        assert not hasattr(PacedClient(FakeModelClient()), "stream")

        blind = PacedClient(BlindFake([]))
        thinking = PacedClient(ThinkingFake([]))
        assert hasattr(blind, "stream") and hasattr(thinking, "stream")

        import inspect

        assert "on_reasoning" not in inspect.signature(blind.stream).parameters
        assert "on_reasoning" in inspect.signature(thinking.stream).parameters


class TestReplay:
    def test_a_replayed_call_reports_the_reasoning_the_recording_held(self, tmp_path):
        path = tmp_path / "reasoning.jsonl"
        recording = RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(path))
        one_node(stream=False).run(
            {},
            envelope=recording,
            model=ThinkingFake([thinking_response()]),
            run_id="rec",
            seed=41,
        )

        replaying = RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(path))
        one_node(stream=False).run(
            {}, envelope=replaying, model=ThinkingFake([]), run_id="rep", seed=41
        )

        replayed = model_calls(run_path(tmp_path / "rep", "rep", "trajectory.jsonl"))[0]
        assert replayed["outputs"]["reasoning"] == {"text": THOUGHT, "blocks": []}
        assert replayed["replayed"] is True

    def test_a_replay_re_emits_the_reasoning_pieces_the_recording_delivered(self, tmp_path):
        path = tmp_path / "reasoning.jsonl"
        recording = RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(path))
        live: list[TokenEvent] = []
        one_node().run(
            {},
            envelope=recording,
            model=ThinkingFake([thinking_response()]),
            run_id="rec",
            seed=41,
            on_token=lambda e: None,
            on_reasoning=live.append,
        )

        replaying = RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(path))
        replayed: list[TokenEvent] = []
        one_node().run(
            {},
            envelope=replaying,
            model=ThinkingFake([]),
            run_id="rep",
            seed=41,
            on_token=lambda e: None,
            on_reasoning=replayed.append,
        )

        assert [e.text for e in replayed] == [e.text for e in live]

    def test_an_entry_recorded_before_reasoning_replays_as_none(self, tmp_path):
        path = tmp_path / "old.jsonl"
        recording = RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(path))
        one_node(stream=False).run(
            {},
            envelope=recording,
            model=FakeModelClient([fake_response(ANSWER)]),
            run_id="rec",
            seed=41,
        )
        # Strip the field the way a file written before this item would have it.
        entries = [json.loads(line) for line in path.read_text().splitlines()]
        for entry in entries:
            entry["response"].pop("reasoning", None)
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        replaying = RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(path))
        one_node(stream=False).run(
            {}, envelope=replaying, model=FakeModelClient([]), run_id="rep", seed=41
        )

        replayed = model_calls(run_path(tmp_path / "rep", "rep", "trajectory.jsonl"))[0]
        assert replayed["outputs"]["reasoning"] is None


class TestRedaction:
    def test_a_credential_inside_a_chain_of_thought_is_scrubbed(self, tmp_path):
        envelope = RunEnvelope(run_dir=tmp_path)
        leaked = "I will call the API with sk-livekey01234567890abcdef and report back."
        one_node(stream=False).run(
            {},
            envelope=envelope,
            model=ThinkingFake([thinking_response(text=leaked)]),
            run_id=RUN_ID,
        )

        record = model_calls(run_path(tmp_path, RUN_ID, "trajectory.jsonl"))[0]
        assert "sk-livekey01234567890abcdef" not in json.dumps(record)
        assert "[redacted:sk_prefixed_key]" in record["outputs"]["reasoning"]["text"]
        assert "outputs.reasoning.text" in record["redactions"]


def _call(name: str, arguments: dict):
    from simple_agents import ToolCallRequest

    return ToolCallRequest(id=f"c_{name}", name=name, arguments=arguments)
