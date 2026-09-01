"""The recorded-call path `call_embedding` and `call_rerank` share.

One cassette walk serves both: off runs the client directly, record stores what came back,
replay serves the stored response, and a replay miss raises. The fakes here are deterministic,
so a served response can be compared with a live one field by field.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simple_agents import Budget
from simple_agents.context import RunContext
from simple_agents.embeddings import EmbeddingResponse, RerankResponse, RerankScore
from simple_agents.models import ModelIdentity, TokenUsage
from simple_agents.records.cassette import Cassette, CassetteMiss
from simple_agents.records.manifest import Manifest
from simple_agents.records.trajectory import TrajectoryWriter, utc_now


class _Embedder:
    calls = 0

    def identity(self) -> ModelIdentity:
        return ModelIdentity(backend="self_hosted", request_model="fake-embed", model_revision="r1")

    def embed(self, texts):
        type(self).calls += 1
        return EmbeddingResponse(
            vectors=[[float(len(t)), 1.0] for t in texts],
            backend="self_hosted",
            request_model="fake-embed",
            response_model="fake-embed",
            model_revision="r1",
            tokens=TokenUsage(
                input_uncached=7,
                input_cache_read=0,
                input_cache_write=0,
                cache_ttl=None,
                output=0,
            ),
        )


class _Reranker:
    calls = 0

    def identity(self) -> ModelIdentity:
        return ModelIdentity(
            backend="self_hosted", request_model="fake-rerank", model_revision="r1"
        )

    def rerank(self, query, documents):
        type(self).calls += 1
        return RerankResponse(
            scores=[RerankScore(index=i, score=float(-i)) for i in range(len(documents))],
            backend="self_hosted",
            request_model="fake-rerank",
            response_model=None,
            model_revision="r1",
            tokens=TokenUsage(
                input_uncached=9,
                input_cache_read=0,
                input_cache_write=0,
                cache_ttl=None,
                output=0,
            ),
        )


def _context(root: Path, cassette: Cassette) -> RunContext:
    budget = Budget.unbounded()
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(
        run_id="run_recorded_calls",
        started_at=utc_now(),
        seed=41,
        budget=budget.to_record(),
        library_version="test",
        trajectory_path=str(root / "trajectory.jsonl"),
        workspace_path=str(workspace),
    )
    return RunContext(
        run_id="run_recorded_calls",
        writer=TrajectoryWriter(root / "trajectory.jsonl"),
        budget=budget,
        workspace=workspace,
        seed=41,
        manifest=manifest,
        cassette=cassette,
    )


class TestTheRecordedCallPath:
    def test_off_calls_the_client_and_stores_nothing(self, tmp_path):
        run = _context(tmp_path, Cassette.off())
        outcome = run.call_embedding(_Embedder(), ["abc"], node_id="n", call_index=0)
        assert outcome.value.vectors == [[3.0, 1.0]]
        assert outcome.replayed is False
        assert outcome.cassette_key is None

    def test_a_recorded_embedding_replays_with_the_same_fields(self, tmp_path):
        path = tmp_path / "cassette.jsonl"
        recording = _context(tmp_path / "a", Cassette.record(path))
        live = recording.call_embedding(_Embedder(), ["ab", "cdef"], node_id="n", call_index=0)

        before = _Embedder.calls
        replaying = _context(tmp_path / "b", Cassette.replay(path))
        served = replaying.call_embedding(_Embedder(), ["ab", "cdef"], node_id="n", call_index=0)
        assert _Embedder.calls == before
        assert served.replayed is True
        assert served.cassette_key == live.cassette_key
        assert served.value.vectors == live.value.vectors
        assert served.value.tokens.to_record() == live.value.tokens.to_record()
        assert replaying.manifest._cassette_counts["hits"] == 1

    def test_a_recorded_rerank_replays_in_order(self, tmp_path):
        path = tmp_path / "cassette.jsonl"
        recording = _context(tmp_path / "a", Cassette.record(path))
        live = recording.call_rerank(
            _Reranker(), "q", ["d1", "d2", "d3"], node_id="n", call_index=0
        )

        replaying = _context(tmp_path / "b", Cassette.replay(path))
        served = replaying.call_rerank(
            _Reranker(), "q", ["d1", "d2", "d3"], node_id="n", call_index=0
        )
        assert served.replayed is True
        assert [(s.index, s.score) for s in served.value.ordered()] == [
            (s.index, s.score) for s in live.value.ordered()
        ]

    def test_a_replay_miss_raises_and_counts(self, tmp_path):
        path = tmp_path / "cassette.jsonl"
        recording = _context(tmp_path / "a", Cassette.record(path))
        recording.call_embedding(_Embedder(), ["recorded"], node_id="n", call_index=0)

        replaying = _context(tmp_path / "b", Cassette.replay(path))
        with pytest.raises(CassetteMiss):
            replaying.call_embedding(_Embedder(), ["something else"], node_id="n", call_index=0)
        assert replaying.manifest._cassette_counts["misses"] == 1

    def test_a_changed_model_identity_is_a_different_key(self, tmp_path):
        """The key carries the identity, so a swapped embedding model misses rather than
        serving vectors the new model would not have produced."""
        path = tmp_path / "cassette.jsonl"
        recording = _context(tmp_path / "a", Cassette.record(path))
        recording.call_embedding(_Embedder(), ["abc"], node_id="n", call_index=0)

        class _Other(_Embedder):
            def identity(self) -> ModelIdentity:
                return ModelIdentity(
                    backend="self_hosted", request_model="other-embed", model_revision="r1"
                )

        replaying = _context(tmp_path / "b", Cassette.replay(path))
        with pytest.raises(CassetteMiss):
            replaying.call_embedding(_Other(), ["abc"], node_id="n", call_index=0)
