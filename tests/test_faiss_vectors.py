"""The FAISS store, behind the `ann` extra. Skipped where FAISS is not installed.

An exact index answers what the numpy store answers. An approximate one trades recall for
time, so what is asserted here is the plumbing: that it holds what it was given, that removal
behaves the way each kind can, and that an index built on one store loads onto another.
"""

from __future__ import annotations

import pytest

from simple_agents import FakeEmbeddingClient
from simple_agents.builtins import DocumentIndex, NumpyVectors, Semantic
from simple_agents.embeddings import normalise
from simple_agents.errors import ConfigurationError, SimpleAgentsWarning

faiss = pytest.importorskip("faiss", reason="needs the `ann` extra")

from simple_agents.builtins import FaissVectors  # noqa: E402

CORPUS = {f"d{i}": f"document {i} about depots, bearings and seed rounds" for i in range(40)}


def vectors_for(texts, dimensions: int = 32) -> list[list[float]]:
    embedder = FakeEmbeddingClient(dimensions=dimensions)
    return [normalise(v) for v in embedder.embed(list(texts)).vectors]


class TestTheExactIndex:
    def test_it_returns_what_the_numpy_store_returns(self) -> None:
        ids = list(CORPUS)
        vectors = vectors_for(CORPUS.values())
        exact, reference = FaissVectors(), NumpyVectors()
        exact.add(ids, vectors)
        reference.add(ids, vectors)

        for query in vectors[:5]:
            found = exact.search(query, top_k=5)
            expected = reference.search(query, top_k=5)
            assert [doc_id for doc_id, _ in found] == [doc_id for doc_id, _ in expected]
            for (_, one), (_, two) in zip(found, expected):
                assert one == pytest.approx(two, abs=1e-5)

    def test_it_grows_one_document_at_a_time(self) -> None:
        store = FaissVectors()
        store.add(["a"], vectors_for(["one"]))
        store.add(["b"], vectors_for(["two"]))

        assert len(store) == 2
        assert store.ids() == ["a", "b"]

    def test_removing_deletes_and_leaves_the_rest_paired(self) -> None:
        ids = list(CORPUS)
        vectors = vectors_for(CORPUS.values())
        store = FaissVectors()
        store.add(ids, vectors)

        store.remove(["d0", "d5", "d9"])

        assert len(store) == 37
        assert store.ids() == [i for i in ids if i not in ("d0", "d5", "d9")]
        # Each surviving identifier still finds its own vector.
        for doc_id, vector in zip(ids, vectors):
            if doc_id in ("d0", "d5", "d9"):
                continue
            assert store.search(vector, top_k=1)[0][0] == doc_id

    def test_a_removed_document_stops_coming_back(self) -> None:
        ids = list(CORPUS)
        vectors = vectors_for(CORPUS.values())
        store = FaissVectors()
        store.add(ids, vectors)

        store.remove(["d3"])

        assert [doc_id for doc_id, _ in store.search(vectors[3], top_k=5)].count("d3") == 0

    def test_it_refuses_a_second_width(self) -> None:
        store = FaissVectors()
        store.add(["a"], [[1.0, 0.0]])

        with pytest.raises(ConfigurationError) as caught:
            store.add(["b"], [[1.0, 0.0, 0.0]])

        assert "requires one width" in str(caught.value)


class TestTheApproximateIndex:
    def test_it_holds_what_it_was_given(self) -> None:
        store = FaissVectors(kind="approximate")
        store.add(list(CORPUS), vectors_for(CORPUS.values()))

        assert len(store) == 40
        assert store.search(vectors_for(CORPUS.values())[0], top_k=3)[0][0] == "d0"

    def test_removing_warns_and_names_rebuild(self) -> None:
        store = FaissVectors(kind="approximate")
        store.add(list(CORPUS), vectors_for(CORPUS.values()))

        with pytest.warns(SimpleAgentsWarning) as caught:
            store.remove(["d7"])

        assert "store.rebuild()" in str(caught[0].message)
        assert len(store) == 39

    def test_a_removed_document_is_filtered_out_of_a_search(self) -> None:
        vectors = vectors_for(CORPUS.values())
        store = FaissVectors(kind="approximate")
        store.add(list(CORPUS), vectors)

        with pytest.warns(SimpleAgentsWarning):
            store.remove(["d7"])

        assert "d7" not in [doc_id for doc_id, _ in store.search(vectors[7], top_k=10)]
        assert "d7" not in store.ids()

    def test_the_walk_is_at_least_as_wide_as_the_results_asked_for(self) -> None:
        """FAISS explores `efSearch` candidates, and its default of 16 is below most depths."""
        store = FaissVectors(kind="approximate")
        store.add(list(CORPUS), vectors_for(CORPUS.values()))
        assert store._index.hnsw.efSearch == 16

        store.search(vectors_for(["anything"])[0], top_k=40)

        assert store._index.hnsw.efSearch >= 40

    def test_a_shallow_search_leaves_the_default_alone(self) -> None:
        store = FaissVectors(kind="approximate")
        store.add(list(CORPUS), vectors_for(CORPUS.values()))

        store.search(vectors_for(["anything"])[0], top_k=5)

        assert store._index.hnsw.efSearch == 16

    def test_an_exact_index_has_no_walk_to_widen(self) -> None:
        store = FaissVectors()
        store.add(list(CORPUS), vectors_for(CORPUS.values()))

        assert len(store.search(vectors_for(["anything"])[0], top_k=40)) == 40

    def test_rebuilding_drops_what_was_removed(self) -> None:
        vectors = vectors_for(CORPUS.values())
        store = FaissVectors(kind="approximate")
        store.add(list(CORPUS), vectors)
        with pytest.warns(SimpleAgentsWarning):
            store.remove(["d7", "d8"])

        store.rebuild()

        assert len(store) == 38
        assert store._index.ntotal == 38
        assert store.search(vectors[9], top_k=1)[0][0] == "d9"


class TestWhatIsRefused:
    def test_an_unknown_kind(self) -> None:
        with pytest.raises(ConfigurationError) as caught:
            FaissVectors(kind="fuzzy")

        assert "'exact' or 'approximate'" in str(caught.value)

    def test_an_approximate_index_on_the_gpu(self) -> None:
        with pytest.raises(ConfigurationError) as caught:
            FaissVectors(kind="approximate", device="cuda")

        assert "GPU indexes do not include the graph" in str(caught.value)

    def test_the_gpu_on_a_cpu_build_names_the_install(self) -> None:
        if faiss.get_num_gpus() > 0:
            pytest.skip("this FAISS has GPU support")
        store = FaissVectors(device="cuda")

        with pytest.raises(ConfigurationError) as caught:
            store.add(["a"], [[1.0, 0.0]])

        assert "faiss-gpu-cu12" in str(caught.value)


class TestAnIndexOverFaiss:
    def test_it_searches_and_grows(self) -> None:
        index = DocumentIndex.from_texts(
            dict(CORPUS),
            embeddings=FakeEmbeddingClient(),
            ranking=Semantic(),
            vectors=FaissVectors(),
        )

        index.add({"d99": "a newly announced show about a wharf"})

        assert len(index.vectors) == 41
        assert index.to_record()["store"] == "FaissVectors"
        assert index.to_record()["exact"] is True

    def test_an_approximate_index_records_that_it_is_not_exact(self) -> None:
        index = DocumentIndex.from_texts(
            dict(CORPUS),
            embeddings=FakeEmbeddingClient(),
            ranking=Semantic(),
            vectors=FaissVectors(kind="approximate"),
        )

        assert index.to_record()["exact"] is False

    def test_it_saves_and_loads_back_onto_the_default_store(self, tmp_path) -> None:
        index = DocumentIndex.from_texts(
            dict(CORPUS),
            embeddings=FakeEmbeddingClient(),
            ranking=Semantic(),
            vectors=FaissVectors(),
        )
        index.save(tmp_path / "corpus.index")

        back = DocumentIndex.load(
            tmp_path / "corpus.index", embeddings=FakeEmbeddingClient(), ranking=Semantic()
        )

        assert type(back.vectors).__name__ == "NumpyVectors"
        assert back.vectors.ids() == index.vectors.ids()

    def test_an_index_saved_from_numpy_loads_onto_faiss(self, tmp_path) -> None:
        DocumentIndex.from_texts(
            dict(CORPUS), embeddings=FakeEmbeddingClient(), ranking=Semantic()
        ).save(tmp_path / "corpus.index")

        back = DocumentIndex.load(
            tmp_path / "corpus.index",
            embeddings=FakeEmbeddingClient(),
            ranking=Semantic(),
            vectors=FaissVectors(),
        )

        assert len(back.vectors) == 40
        assert back.to_record()["store"] == "FaissVectors"
