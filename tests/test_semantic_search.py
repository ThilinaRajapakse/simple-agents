"""Semantic and hybrid retrieval: the ranking, the recorded calls, and what refuses.

The retrieval quality of any particular model is measured rather than tested here. These tests
hold the plumbing: which handles a tool asks for, what reaches the cassette, what the manifest
records, and which mistakes are refused rather than answered.
"""

from __future__ import annotations


import pytest

from simple_agents import (
    FakeEmbeddingClient,
    FakeRerankClient,
    ModelIdentity,
    Retrieval,
)
from simple_agents.builtins import (
    CrossEncoderRerank,
    DocumentIndex,
    Hybrid,
    Interleave,
    Lexical,
    ModelRerank,
    RRF,
    Semantic,
    VectorScan,
    WeightedScore,
    document_search,
)
from simple_agents.embeddings import normalise
from simple_agents.errors import ConfigurationError
from simple_agents.tools import derived_version

CORPUS = {
    "a1": "Corveth raised a seed round in March.",
    "a2": "The seed round closed quickly and quietly.",
    "a3": "Part AX-7719-B is the replacement bearing.",
    "a4": "Delivery to the depot is refused after 4pm.",
}


def handle(record: list[tuple[str, int]] | None = None) -> Retrieval:
    """A Retrieval that calls the client directly, standing in for the recorded path."""

    def embed(client, texts):
        if record is not None:
            record.append(("embed", len(texts)))
        return [normalise(v) for v in client.embed(texts).vectors]

    def rerank(client, query, documents):
        if record is not None:
            record.append(("rerank", len(documents)))
        return client.rerank(query, documents).ordered()

    return Retrieval(_embed=embed, _rerank=rerank)


class TestTheLexicalPathIsUntouched:
    """A project that does not turn semantic search on sees no change at all."""

    def test_the_derived_version_of_the_lexical_tool_is_pinned(self) -> None:
        """Every committed cassette keys `document_search` on this hash.

        `derived_version` hashes the function's source and what it closed over, and the source
        of a nested function includes the indentation it is written at. Moving that closure
        inside a branch, or changing the index it is built over, changes the hash, and every
        recorded `document_search` call in every project misses.

        **It moved once, on 2026-08-19**, when a tool's version came to cover what its function
        closed over. Every cassette here was re-recorded against vLLM and Gemini, and the
        Mistral tool arm retired rather than being regenerated against a backend out of credits.
        A move needs the same: re-record every arm, or do not make it.
        """
        assert (
            derived_version(document_search(DocumentIndex.from_texts(CORPUS)).fn)
            == "sha256:62a117a5c471"
        )

    def test_it_asks_for_no_handle_and_is_served_from_the_cassette(self) -> None:
        tool = document_search(DocumentIndex.from_texts(CORPUS))

        assert tool.handles == {}
        assert tool.re_executed is False

    def test_its_results_carry_the_three_fields_they_always_carried(self) -> None:
        tool = document_search(DocumentIndex.from_texts(CORPUS))

        first = tool.call({"query": "seed round"})["results"][0]

        assert sorted(first) == ["doc_id", "score", "text"]


class TestWhatTheIndexDefaultsTo:
    def test_no_embeddings_means_lexical(self) -> None:
        assert isinstance(DocumentIndex.from_texts(CORPUS).ranking, Lexical)

    def test_embeddings_with_no_ranking_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            DocumentIndex.from_texts(CORPUS, embeddings=FakeEmbeddingClient())

        assert "embeddings= and no ranking=" in str(raised.value)

    def test_the_refusal_names_every_ranking_it_could_have_been_given(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            DocumentIndex.from_texts(CORPUS, embeddings=FakeEmbeddingClient())

        message = str(raised.value)
        assert "ranking=Lexical()" in message
        assert "ranking=Semantic()" in message
        assert "ranking=Hybrid(fuse=RRF(k=5))" in message
        assert "ranking=Hybrid(fuse=WeightedScore(lexical=0.3))" in message

    def test_loading_an_index_with_embeddings_and_no_ranking_is_refused(self, tmp_path) -> None:
        client = FakeEmbeddingClient()
        DocumentIndex.from_texts(CORPUS, embeddings=client, ranking=Semantic()).save(
            tmp_path / "c.index"
        )

        with pytest.raises(ConfigurationError) as raised:
            DocumentIndex.load(tmp_path / "c.index", embeddings=client)

        assert "embeddings= and no ranking=" in str(raised.value)

    def test_the_corpus_is_embedded_once_when_the_index_is_built(self) -> None:
        client = FakeEmbeddingClient()

        DocumentIndex.from_texts(CORPUS, embeddings=client, ranking=Semantic())

        assert client.texts == list(CORPUS.values())

    def test_it_records_the_model_that_embedded_it(self) -> None:
        index = DocumentIndex.from_texts(
            CORPUS, embeddings=FakeEmbeddingClient(), ranking=Semantic()
        )

        assert index.embedded_by == FakeEmbeddingClient().identity()


class TestEveryRankingRuns:
    @pytest.mark.parametrize(
        "ranking",
        [
            Lexical(),
            Semantic(),
            Hybrid(fuse=RRF()),
            Hybrid(fuse=RRF(k=60)),
            Hybrid(fuse=Interleave()),
            Hybrid(fuse=WeightedScore(lexical=0.3)),
        ],
    )
    def test_it_returns_results_attributed_to_what_found_them(self, ranking) -> None:
        index = DocumentIndex.from_texts(CORPUS, embeddings=FakeEmbeddingClient(), ranking=ranking)

        hits = index.search("seed round", top_k=3, retrieval=handle())

        assert hits
        assert all(hit.retriever in ("lexical", "semantic") for hit in hits)
        assert [hit.rank for hit in hits] == list(range(1, len(hits) + 1))

    def test_a_purely_lexical_ranking_never_embeds(self) -> None:
        client = FakeEmbeddingClient()
        index = DocumentIndex.from_texts(CORPUS, embeddings=client, ranking=Lexical())
        client.texts.clear()

        index.search("seed round", top_k=2, retrieval=handle())

        assert client.texts == []


class TestFusionArithmetic:
    """Held here because the fusion is a decision, and a silent change to it moves results."""

    LEXICAL = [("a", 8.31), ("b", 2.70), ("c", 2.70)]
    SEMANTIC = [("d", 0.916), ("a", 0.915), ("e", 0.914)]

    def test_reciprocal_rank_fusion_adds_one_over_k_plus_rank(self) -> None:
        combined = RRF(k=5).combine(self.LEXICAL, self.SEMANTIC, top_k=2)

        # 'a' is first in one list and second in the other: 1/6 + 1/7 beats 'd' at 1/6.
        assert combined == ["a", "d"]

    def test_a_larger_k_prefers_two_mediocre_votes_to_one_decisive_one(self) -> None:
        """The failure mode the default of 5 was chosen against.

        A flat discount makes two mid-list votes outweigh one first place, so a document
        neither retriever thought much of displaces the one a retriever was decisive about.
        """
        lexical = [("decisive", 9.0)] + [(f"l{i}", 1.0) for i in range(9)] + [("mediocre", 0.9)]
        semantic = [(f"s{i}", 0.9) for i in range(10)] + [("mediocre", 0.5)]

        assert RRF(k=5).combine(lexical, semantic, top_k=1) == ["decisive"]
        assert RRF(k=60).combine(lexical, semantic, top_k=1) == ["mediocre"]

    def test_equal_ranks_in_one_list_tie_and_are_broken_by_identifier(self) -> None:
        """Stated because a corpus of near-identical documents is settled by their names."""
        combined = RRF().combine([("zeta", 9.0)], [("alpha", 0.9)], top_k=2)

        assert combined == ["alpha", "zeta"]

    def test_interleaving_guarantees_each_retriever_its_best(self) -> None:
        combined = Interleave().combine(self.LEXICAL, self.SEMANTIC, top_k=2)

        assert combined == ["a", "d"]

    def test_interleaving_skips_a_document_already_taken(self) -> None:
        combined = Interleave().combine([("a", 1.0)], [("a", 1.0), ("b", 0.5)], top_k=2)

        assert combined == ["a", "b"]

    def test_weighted_score_normalises_each_list_by_its_own_best(self) -> None:
        combined = WeightedScore(lexical=1.0).combine(self.LEXICAL, self.SEMANTIC, top_k=1)

        assert combined == ["a"]

    def test_a_fusion_setting_outside_its_range_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="at least 1"):
            RRF(k=0)
        with pytest.raises(ConfigurationError, match="between 0 and 1"):
            WeightedScore(lexical=1.5)
        with pytest.raises(ConfigurationError, match="at least 1"):
            Hybrid(depth=0)


class TestTheVectorScan:
    def test_it_finds_the_nearest_and_reports_the_dot_product(self) -> None:
        store = VectorScan()
        store.add(["a", "b"], [normalise([1, 0, 0]), normalise([0, 1, 0])])

        found = store.search(normalise([0.9, 0.1, 0.0]), top_k=2)

        assert [doc_id for doc_id, _ in found] == ["a", "b"]
        assert found[0][1] == pytest.approx(0.9938, abs=1e-3)

    def test_it_refuses_identifiers_and_vectors_of_different_lengths(self) -> None:
        with pytest.raises(ConfigurationError, match="paired by position"):
            VectorScan().add(["a", "b"], [[1.0]])

    def test_an_empty_store_returns_nothing_rather_than_failing(self) -> None:
        assert VectorScan().search([1.0], top_k=3) == []

    def test_a_project_may_supply_its_own(self) -> None:
        """The escape hatch: `vectors=` takes anything with add, search and a length."""

        class Reversed:
            def __init__(self) -> None:
                self.ids: list[str] = []

            def add(self, ids, vectors):
                self.ids.extend(ids)

            def search(self, vector, top_k):
                return [(doc_id, 1.0) for doc_id in reversed(self.ids)][:top_k]

            def __len__(self):
                return len(self.ids)

        store = Reversed()
        store.add(list(CORPUS), [[0.0]] * len(CORPUS))
        index = DocumentIndex.from_texts(
            CORPUS, embeddings=FakeEmbeddingClient(), ranking=Semantic(), vectors=store
        )

        hits = index.search("anything", top_k=1, retrieval=handle())

        assert hits[0].doc_id == "a4"


class TestReranking:
    def test_a_cross_encoder_reorders_and_reports_its_own_score(self) -> None:
        index = DocumentIndex.from_texts(
            CORPUS,
            embeddings=FakeEmbeddingClient(),
            ranking=Hybrid(fuse=RRF()),
            rerank=CrossEncoderRerank(FakeRerankClient(), top_n=4),
        )

        hits = index.search("seed round", top_k=2, retrieval=handle())

        assert [hit.retriever for hit in hits] == ["rerank", "rerank"]

    def test_only_top_n_candidates_reach_it(self) -> None:
        seen: list[tuple[str, int]] = []
        index = DocumentIndex.from_texts(
            CORPUS,
            embeddings=FakeEmbeddingClient(),
            ranking=Hybrid(fuse=RRF()),
            rerank=CrossEncoderRerank(FakeRerankClient(), top_n=2),
        )

        index.search("seed round", top_k=2, retrieval=handle(seen))

        assert ("rerank", 2) in seen

    def test_a_model_rerank_asks_for_the_chat_model_as_well(self) -> None:
        index = DocumentIndex.from_texts(
            CORPUS,
            embeddings=FakeEmbeddingClient(),
            ranking=Hybrid(fuse=RRF()),
            rerank=ModelRerank(top_n=3),
        )

        assert set(document_search(index).handles) == {"retrieval", "model"}

    def test_a_reply_naming_nothing_leaves_the_order_alone(self) -> None:
        assert ModelRerank().order_from("no numbers here", 3) == [0, 1, 2]

    def test_a_reply_naming_some_puts_the_rest_behind_them(self) -> None:
        assert ModelRerank().order_from("3, 1", 4) == [2, 0, 1, 3]

    def test_a_reply_naming_a_number_out_of_range_drops_it(self) -> None:
        assert ModelRerank().order_from("9, 2", 2) == [1, 0]

    def test_a_reranker_with_no_candidates_is_refused_at_construction(self) -> None:
        with pytest.raises(ConfigurationError, match="at least 1 candidate"):
            CrossEncoderRerank(FakeRerankClient(), top_n=0)

    def test_top_n_caps_top_k(self) -> None:
        """A search returns at most `top_n`, however many the model asked for."""
        index = DocumentIndex.from_texts(
            CORPUS,
            embeddings=FakeEmbeddingClient(),
            ranking=Hybrid(fuse=RRF()),
            rerank=CrossEncoderRerank(FakeRerankClient(), top_n=2),
        )

        hits = index.search("seed round", top_k=4, retrieval=handle())

        assert len(hits) == 2

    def test_a_top_n_at_the_corpus_size_hands_the_whole_corpus_over(self) -> None:
        """The first pass then decides nothing about what comes back."""
        seen: list[tuple[str, int]] = []
        index = DocumentIndex.from_texts(
            CORPUS,
            embeddings=FakeEmbeddingClient(),
            ranking=Hybrid(fuse=RRF()),
            rerank=CrossEncoderRerank(FakeRerankClient(), top_n=len(CORPUS) + 10),
        )

        index.search("seed round", top_k=2, retrieval=handle(seen))

        assert ("rerank", len(CORPUS)) in seen


class TestSavingAndLoading:
    def test_it_round_trips_the_documents_and_the_vectors(self, tmp_path) -> None:
        client = FakeEmbeddingClient()
        index = DocumentIndex.from_texts(CORPUS, embeddings=client, ranking=Semantic())
        index.save(tmp_path / "corpus.index")

        back = DocumentIndex.load(tmp_path / "corpus.index", embeddings=client, ranking=Semantic())

        assert back.documents == CORPUS
        assert [hit.doc_id for hit in back.search("seed round", top_k=3, retrieval=handle())] == [
            hit.doc_id for hit in index.search("seed round", top_k=3, retrieval=handle())
        ]

    def test_loading_does_not_re_embed(self, tmp_path) -> None:
        client = FakeEmbeddingClient()
        DocumentIndex.from_texts(CORPUS, embeddings=client, ranking=Semantic()).save(
            tmp_path / "c.index"
        )
        client.texts.clear()

        DocumentIndex.load(tmp_path / "c.index", embeddings=client, ranking=Semantic())

        assert client.texts == []

    def test_loading_under_another_model_is_refused(self, tmp_path) -> None:
        DocumentIndex.from_texts(CORPUS, embeddings=FakeEmbeddingClient(), ranking=Semantic()).save(
            tmp_path / "c.index"
        )
        other = FakeEmbeddingClient(
            model_identity=ModelIdentity(
                backend="self_hosted", request_model="other/embed", model_revision="1" * 40
            )
        )

        with pytest.raises(ConfigurationError, match="different"):
            DocumentIndex.load(tmp_path / "c.index", embeddings=other, ranking=Semantic())

    def test_the_refusal_names_both_models_and_how_to_fix_it(self, tmp_path) -> None:
        DocumentIndex.from_texts(CORPUS, embeddings=FakeEmbeddingClient(), ranking=Semantic()).save(
            tmp_path / "c.index"
        )
        other = FakeEmbeddingClient(
            model_identity=ModelIdentity(
                backend="self_hosted", request_model="other/embed", model_revision="1" * 40
            )
        )

        with pytest.raises(ConfigurationError) as caught:
            DocumentIndex.load(tmp_path / "c.index", embeddings=other, ranking=Semantic())

        assert "test/embed" in str(caught.value)
        assert "other/embed" in str(caught.value)
        assert "re-embed" in str(caught.value)

    def test_an_unreadable_file_says_how_to_rebuild_it(self, tmp_path) -> None:
        (tmp_path / "broken.index").write_text("not json", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="Rebuild it"):
            DocumentIndex.load(tmp_path / "broken.index")


class TestWhatIsRefused:
    def test_a_vector_ranking_with_no_embedding_client(self) -> None:
        with pytest.raises(ConfigurationError, match="no embedding client"):
            DocumentIndex.from_texts(CORPUS, ranking=Semantic())

    def test_searching_by_vector_with_no_handle(self) -> None:
        index = DocumentIndex.from_texts(
            CORPUS, embeddings=FakeEmbeddingClient(), ranking=Semantic()
        )

        with pytest.raises(ConfigurationError, match="charged to no budget"):
            index.search("seed round", top_k=2)

    def test_reranking_with_no_handle(self) -> None:
        index = DocumentIndex.from_texts(
            CORPUS, rerank=CrossEncoderRerank(FakeRerankClient(), top_n=2)
        )

        with pytest.raises(ConfigurationError, match="charged to no budget"):
            index.search("seed round", top_k=2)

    def test_a_model_rerank_with_no_chat_handle(self) -> None:
        index = DocumentIndex.from_texts(
            CORPUS,
            embeddings=FakeEmbeddingClient(),
            ranking=Hybrid(fuse=RRF()),
            rerank=ModelRerank(top_n=2),
        )

        with pytest.raises(ConfigurationError, match="ModelHandle"):
            index.search("seed round", top_k=2, retrieval=handle())

    def test_an_embedding_backend_returning_the_wrong_count(self) -> None:
        class Short(FakeEmbeddingClient):
            def embed(self, texts):
                response = super().embed(texts)
                response.vectors = response.vectors[:-1]
                return response

        with pytest.raises(ConfigurationError, match="paired with inputs by position"):
            DocumentIndex.from_texts(CORPUS, embeddings=Short(), ranking=Semantic())


class TestTheToolAsksForWhatItNeeds:
    @pytest.mark.parametrize(
        "kwargs,expected",
        [
            ({}, set()),
            ({"embeddings": FakeEmbeddingClient(), "ranking": Semantic()}, {"retrieval"}),
            (
                {"rerank": CrossEncoderRerank(FakeRerankClient(), top_n=2)},
                {"retrieval"},
            ),
            (
                {
                    "embeddings": FakeEmbeddingClient(),
                    "ranking": Hybrid(fuse=RRF()),
                    "rerank": ModelRerank(top_n=2),
                },
                {"retrieval", "model"},
            ),
        ],
    )
    def test_the_handles_match_the_calls_the_search_will_make(self, kwargs, expected) -> None:
        index = DocumentIndex.from_texts(CORPUS, **kwargs)

        assert set(document_search(index).handles) == expected

    def test_the_handle_is_never_offered_to_the_model(self) -> None:
        index = DocumentIndex.from_texts(
            CORPUS, embeddings=FakeEmbeddingClient(), ranking=Semantic()
        )

        offered = document_search(index).to_wire()["input_schema"]["properties"]

        assert sorted(offered) == ["query", "top_k"]

    def test_a_semantic_search_is_re_executed_rather_than_stored(self) -> None:
        index = DocumentIndex.from_texts(
            CORPUS, embeddings=FakeEmbeddingClient(), ranking=Semantic()
        )

        assert document_search(index).re_executed is True
