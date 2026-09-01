"""Token streaming through the model client seam.

Two layers, on the precedent `docs/model-clients.md` sets for the adapters. Here the client is
a fake that delivers scripted pieces, which tests what the library does with a stream. What a
backend actually puts on the wire is `test_adapters.py` over captured fixtures, and
`test_adapter_integration.py` over recordings taken from the live backends.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from simple_agents import (
    AgentNode,
    Budget,
    Cassette,
    ConfigurationError,
    FakeModelClient,
    LLMNode,
    PacedClient,
    Pipeline,
    RunEnvelope,
    TokenEvent,
    fake_response,
)

from conftest import run_path, RUN_ID
from schemas import Answer

BUDGET = Budget(max_steps=8, max_tokens=100_000, max_cost=None, max_wall_clock_ms=120_000)

ANSWER = json.dumps({"answer": "32 inches", "source": "spec"})


def pieces_of(text: str, size: int = 5) -> list[str]:
    """`text` cut into fixed-width pieces, standing in for what a backend delivers."""
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


class StreamingFake:
    """A fake client that delivers scripted content in pieces before returning it whole.

    `chunks` scripts what each call delivers. Left unset, each response's content is cut into
    five-character pieces, which is enough for a test that cares that boundaries survive.
    """

    def __init__(self, responses: list, chunks: list[list[str]] | None = None) -> None:
        self.responses = list(responses)
        self.chunks = chunks
        self.requests: list = []
        self.streamed = 0
        self.completed = 0

    def identity(self):
        return FakeModelClient().identity()

    def complete(self, request):
        self.requests.append(request)
        self.completed += 1
        return self.responses.pop(0)

    def stream(self, request, on_chunk):
        self.requests.append(request)
        index = self.streamed
        self.streamed += 1
        response = self.responses.pop(0)
        scripted = self.chunks[index] if self.chunks else pieces_of(response.content or "")
        for piece in scripted:
            on_chunk(piece)
        return response


def answering(*contents: str, chunks: list[list[str]] | None = None) -> StreamingFake:
    return StreamingFake([fake_response(content=c) for c in contents], chunks=chunks)


def one_node(*, stream: bool = True, node_id: str = "answer") -> Pipeline:
    return Pipeline(
        [
            LLMNode(
                lambda inputs, ctx: "what size?",
                output_schema=Answer,
                node_id=node_id,
                stream=stream,
            )
        ],
        budget=BUDGET,
    )


class TestTheSinkDecidesWhetherAnythingStreams:
    """`stream=True` says a node may stream; `on_token=` is what makes it."""

    def test_a_declaring_node_streams_when_a_sink_is_given(self, envelope):
        seen: list[TokenEvent] = []
        client = answering(ANSWER)
        one_node().run({}, envelope=envelope, model=client, on_token=seen.append, seed=41)

        assert client.streamed == 1 and client.completed == 0
        assert "".join(event.text for event in seen) == ANSWER

    def test_a_declaring_node_makes_an_ordinary_call_with_no_sink(self, envelope):
        client = answering(ANSWER)
        one_node().run({}, envelope=envelope, model=client, seed=41)

        assert client.completed == 1 and client.streamed == 0

    def test_a_node_that_does_not_declare_it_never_streams(self, envelope):
        seen: list[TokenEvent] = []
        client = answering(ANSWER, ANSWER)
        Pipeline(
            [
                LLMNode(lambda i, c: "a", output_schema=Answer, node_id="quiet"),
                LLMNode(lambda i, c: "b", output_schema=Answer, node_id="loud", stream=True),
            ],
            budget=BUDGET,
        ).run({}, envelope=envelope, model=client, on_token=seen.append, seed=41)

        assert client.completed == 1 and client.streamed == 1
        assert {event.node_id for event in seen} == {"loud"}


class TestWhatATokenEventCarries:
    def test_it_names_the_node_that_produced_it(self, envelope):
        seen: list[TokenEvent] = []
        one_node(node_id="reply").run(
            {}, envelope=envelope, model=answering(ANSWER), on_token=seen.append, seed=41
        )

        assert {(e.node_id, e.node_kind, e.call_index) for e in seen} == {("reply", "llm", 0)}
        assert all(event.item_index is None for event in seen)

    def test_call_index_counts_the_turns_of_an_agent_loop(self, envelope, tmp_path):
        from simple_agents import SideEffectClass, tool

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def look_up(query: str) -> str:
            """Search the specification. Returns matching text."""
            return "32 inches"

        client = StreamingFake(
            [
                fake_response(
                    content=None,
                    tool_calls=[_call("look_up", {"query": "size"})],
                    finish_reason="tool_calls",
                ),
                fake_response(
                    content=None,
                    tool_calls=[_call("finish", {"answer": "32 inches", "source": "spec"})],
                    finish_reason="tool_calls",
                ),
            ],
            chunks=[[], []],
        )
        seen: list[TokenEvent] = []
        Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: "find the size",
                    tools=[look_up],
                    output_schema=Answer,
                    budget=BUDGET,
                    node_id="hunt",
                    stream=True,
                )
            ],
            budget=BUDGET,
        ).run({}, envelope=envelope, model=client, on_token=seen.append, seed=41)

        assert client.streamed == 2, "every turn of the loop goes through the same seam"

    def test_item_index_is_filled_inside_a_fan_out(self, envelope):
        seen: list[TokenEvent] = []
        Pipeline(
            [
                LLMNode(
                    lambda inputs, ctx: f"summarise {inputs['documents']}",
                    output_schema=Answer,
                    over="documents",
                    node_id="each",
                    stream=True,
                )
            ],
            budget=BUDGET,
        ).run(
            {"documents": ["a", "b"]},
            envelope=envelope,
            model=answering(ANSWER, ANSWER),
            on_token=seen.append,
            seed=41,
        )

        assert {event.item_index for event in seen} == {0, 1}


class TestWhatTheRecordSays:
    def test_a_streamed_call_records_its_chunks(self, envelope, trajectory):
        one_node().run(
            {},
            envelope=envelope,
            model=answering(ANSWER),
            on_token=lambda e: None,
            run_id=RUN_ID,
            seed=41,
        )
        call = _model_calls(trajectory)[0]

        assert call["stream"]["chunks"] == len(pieces_of(ANSWER))
        assert call["stream"]["first_chunk_ms"] is not None

    def test_a_call_that_did_not_stream_records_null(self, envelope, trajectory):
        one_node(stream=False).run(
            {}, envelope=envelope, model=answering(ANSWER), run_id=RUN_ID, seed=41
        )

        assert _model_calls(trajectory)[0]["stream"] is None


class TestReplay:
    """A replay hands the sink the pieces the recording delivered."""

    def test_it_re_emits_the_recorded_boundaries(self, tmp_path):
        path = tmp_path / "qa.jsonl"
        recorded = pieces_of(ANSWER, size=7)
        self._record(tmp_path, path, chunks=[recorded])

        seen: list[str] = []
        one_node().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.replay(path)),
            model=answering(ANSWER),
            on_token=lambda e: seen.append(e.text),
            run_id="replayed",
            seed=41,
        )
        assert seen == recorded

    def test_an_entry_recorded_without_streaming_replays_as_one_piece(self, tmp_path):
        path = tmp_path / "qa.jsonl"
        one_node(stream=False).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(path)),
            model=answering(ANSWER),
            run_id="recorded",
            seed=41,
        )

        seen: list[str] = []
        one_node().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.replay(path)),
            model=answering(ANSWER),
            on_token=lambda e: seen.append(e.text),
            run_id="replayed",
            seed=41,
        )
        assert seen == [ANSWER], "nothing is invented where no boundaries were recorded"

    def test_the_record_of_such_a_replay_says_it_did_not_stream(self, tmp_path):
        path = tmp_path / "qa.jsonl"
        one_node(stream=False).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(path)),
            model=answering(ANSWER),
            run_id="recorded",
            seed=41,
        )
        one_node().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.replay(path)),
            model=answering(ANSWER),
            on_token=lambda e: None,
            run_id="replayed",
            seed=41,
        )
        call = _model_calls(run_path(tmp_path, "replayed", "trajectory.jsonl"))[0]
        assert call["stream"] is None and call["replayed"] is True

    def test_streaming_is_not_in_the_key(self, tmp_path):
        """A recording made while streaming is served to a run that does not stream."""
        path = tmp_path / "qa.jsonl"
        self._record(tmp_path, path)

        result = one_node(stream=False).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.replay(path)),
            model=FakeModelClient(responses=[]),
            run_id="unstreamed",
            seed=41,
        )
        assert result.output.answer == "32 inches"

    def _record(self, tmp_path: Path, path: Path, chunks=None) -> None:
        one_node().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(path)),
            model=answering(ANSWER, chunks=chunks),
            on_token=lambda e: None,
            run_id="recorded",
            seed=41,
        )


class TestRefusals:
    def test_a_sink_no_node_can_reach_is_refused(self, envelope):
        with pytest.raises(ConfigurationError) as refusal:
            one_node(stream=False).run(
                {}, envelope=envelope, model=answering(ANSWER), on_token=lambda e: None
            )

        assert "no node in this pipeline declares stream=True" in str(refusal.value)
        assert "'answer'" in str(refusal.value), "it names where to declare it"

    def test_a_client_that_cannot_stream_is_refused(self, envelope):
        with pytest.raises(ConfigurationError) as refusal:
            one_node().run(
                {},
                envelope=envelope,
                model=FakeModelClient(responses=[fake_response(content=ANSWER)]),
                on_token=lambda e: None,
            )

        assert "has no stream() method" in str(refusal.value)
        assert "FakeModelClient" in str(refusal.value)

    def test_an_adapter_whose_pieces_do_not_rebuild_its_content_is_refused(self, envelope):
        from simple_agents import CallerFacingError

        class Lies(StreamingFake):
            def stream(self, request, on_chunk):
                on_chunk("something else entirely")
                return self.responses.pop(0)

        with pytest.raises(CallerFacingError) as refusal:
            one_node().run(
                {},
                envelope=envelope,
                model=Lies([fake_response(content=ANSWER)]),
                on_token=lambda e: None,
            )

        assert "reconstruct ModelResponse.content" in str(refusal.value)

    def test_a_stream_with_no_usage_names_what_this_run_loses(self, envelope):
        """The message is built from the run: only consequences it actually has appear."""
        from simple_agents import StreamUsageMissing

        with pytest.raises(StreamUsageMissing) as refusal:
            one_node().run(
                {}, envelope=envelope, model=_NoUsage(), on_token=lambda e: None, seed=41
            )

        said = str(refusal.value)
        assert "Node 'answer', call 0" in said
        assert f"max_tokens={BUDGET.max_tokens}" in said
        assert "no cost derives" not in said, "this envelope declares no cost basis"
        assert 'FakeBackend(model="test/model", stream_without_usage=True)' in said
        assert "Remove stream=True from LLMNode('answer')" in said

    def test_a_run_with_no_limits_is_told_what_is_true_of_it(self, envelope):
        from simple_agents import StreamUsageMissing

        unbounded = Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None)
        pipeline = Pipeline(
            [LLMNode(lambda i, c: "x", output_schema=Answer, node_id="answer", stream=True)],
            budget=unbounded,
        )
        with pytest.raises(StreamUsageMissing) as refusal:
            pipeline.run({}, envelope=envelope, model=_NoUsage(), on_token=lambda e: None, seed=41)

        said = str(refusal.value)
        assert "Nothing in this run reads a token count" in said
        assert "max_tokens=" not in said and "max_steps=" not in said


class TestSuspensionMidStream:
    """A `Suspend` from a model client is not a failure, and what streamed is not unsaid."""

    class _StopsMidStream(StreamingFake):
        def stream(self, request, on_chunk):
            from simple_agents import Suspend

            on_chunk(ANSWER[:8])
            raise Suspend(waiting_for="monthly token quota")

    def test_the_record_is_not_a_caller_facing_failure(self, envelope, trajectory):
        from simple_agents import RunSuspended

        with pytest.raises(RunSuspended):
            one_node().run(
                {},
                envelope=envelope,
                model=self._StopsMidStream([]),
                on_token=lambda e: None,
                run_id=RUN_ID,
                seed=41,
            )

        call = _model_calls(trajectory)[0]
        assert call["error"]["class"] == "suspended", (
            "the node did not fail, so counting caller_facing failures must not count this"
        )
        assert call["error"]["type"] == "Suspend"

    def test_it_records_what_reached_the_end_user(self, envelope, trajectory):
        from simple_agents import RunSuspended

        with pytest.raises(RunSuspended):
            one_node().run(
                {},
                envelope=envelope,
                model=self._StopsMidStream([]),
                on_token=lambda e: None,
                run_id=RUN_ID,
                seed=41,
            )

        call = _model_calls(trajectory)[0]
        assert call["outputs"]["content"] == ANSWER[:8]
        assert call["stream"]["chunks"] == 1
        assert call["ended_at"] is None, "the call never completed"


class TestPacedClient:
    def test_it_delegates_stream_where_the_wrapped_client_has_one(self, envelope):
        inner = answering(ANSWER)
        paced = PacedClient(inner)

        seen: list[str] = []
        one_node().run(
            {}, envelope=envelope, model=paced, on_token=lambda e: seen.append(e.text), seed=41
        )
        assert inner.streamed == 1
        assert "".join(seen) == ANSWER

    def test_wrapping_a_client_that_cannot_stream_leaves_it_unable_to(self):
        paced = PacedClient(FakeModelClient(responses=[]))

        assert not hasattr(paced, "stream"), (
            "a class-level stream() would turn the refusal before the run into an "
            "AttributeError during it"
        )

    def test_it_says_so_when_the_allowance_it_paces_against_stops_arriving(self):
        """Measured against Mistral: a streamed response carries no x-ratelimit headers."""
        from simple_agents import RateLimit, SimpleAgentsWarning

        paced = PacedClient(
            StreamingFake(
                [
                    fake_response(content=ANSWER),
                    fake_response(content=ANSWER),
                ]
            )
        )
        paced.inner.responses[0].rate_limit = RateLimit(
            remaining_requests=40, remaining_tokens=40_000
        )
        req = __import__("simple_agents").ModelRequest(messages=[])

        paced.complete(req)
        with pytest.warns(SimpleAgentsWarning, match="published a rate-limit allowance"):
            paced.stream(req, lambda piece: None)

    def test_a_backend_that_never_publishes_one_says_nothing(self):
        from simple_agents import SimpleAgentsWarning

        paced = PacedClient(StreamingFake([fake_response(content=ANSWER)]))
        req = __import__("simple_agents").ModelRequest(messages=[])

        with warnings.catch_warnings():
            warnings.simplefilter("error", SimpleAgentsWarning)
            paced.complete(req)


class _NoUsage(StreamingFake):
    """A client whose backend reports no token counts on a stream, as the refusal describes."""

    def __init__(self) -> None:
        super().__init__([fake_response(content=ANSWER)])

    def stream(self, request, on_chunk):
        from simple_agents.adapters._openai_wire import usage_missing_error

        on_chunk(ANSWER)
        raise usage_missing_error(model="test/model", adapter="FakeBackend")


def _call(name: str, arguments: dict):
    from simple_agents import ToolCallRequest

    return ToolCallRequest(id=f"call_{name}", name=name, arguments=arguments)


def _model_calls(trajectory: Path) -> list[dict]:
    return [
        record
        for record in (json.loads(line) for line in trajectory.read_text().splitlines())
        if record["record_type"] == "model_call"
    ]
