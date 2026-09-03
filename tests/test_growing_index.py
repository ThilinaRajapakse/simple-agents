"""An index that grows: add, replace, remove, the stores under them, and what a run records.

The retrieval quality of any store is measured rather than tested here. These hold the
plumbing: that only the new documents are embedded, that the words and the vectors move
together, that the exact stores agree, that a saved index round-trips through two files, and
that what a run records separates how a search ranks from how large the corpus got.
"""

from __future__ import annotations

import json
import threading

import pytest

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    FakeEmbeddingClient,
    FakeModelClient,
    ModelIdentity,
    Pipeline,
    Retrieval,
)
from simple_agents.builtins import (
    DocumentIndex,
    Hybrid,
    Lexical,
    NumpyVectors,
    RRF,
    Semantic,
    VectorScan,
    default_store,
    document_search,
)
from simple_agents.builtins.search import ANALYZER, INDEX_FORMAT_VERSION, VECTOR_FILE_SUFFIX
from simple_agents.embeddings import normalise
from simple_agents.errors import ConfigurationError
from simple_agents.models import ToolCallRequest, fake_response

from conftest import RUN_ID
from schemas import Answer

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


def semantic_index(**kwargs) -> tuple[DocumentIndex, FakeEmbeddingClient]:
    embedder = FakeEmbeddingClient()
    index = DocumentIndex.from_texts(
        dict(CORPUS), embeddings=embedder, ranking=Semantic(), **kwargs
    )
    return index, embedder


class TestAddingToTheCorpus:
    """`add` puts the words in the postings and the vectors in the store."""

    def test_a_lexical_index_finds_what_was_added(self) -> None:
        index = DocumentIndex.from_texts(dict(CORPUS))

        index.add({"a5": "The Ashford warehouse holds the spare bearings."})

        assert [hit.doc_id for hit in index.search("ashford", top_k=2)] == ["a5"]
        assert len(index) == 5

    def test_only_the_new_documents_are_embedded(self) -> None:
        index, embedder = semantic_index()
        embedder.texts.clear()

        index.add({"a5": "A new depot opened in Ashford."})

        assert embedder.texts == ["A new depot opened in Ashford."]
        assert len(index.vectors) == 5

    def test_the_added_document_is_reachable_by_vector(self) -> None:
        index, embedder = semantic_index()
        index.add({"a5": "A new depot opened in Ashford."})

        found = index.search("A new depot opened in Ashford.", top_k=1, retrieval=handle())

        assert found[0].doc_id == "a5"

    def test_an_identifier_already_held_is_refused_and_names_replace(self) -> None:
        index = DocumentIndex.from_texts(dict(CORPUS))

        with pytest.raises(ConfigurationError) as caught:
            index.add({"a1": "Something else entirely."})

        assert "already holds" in str(caught.value)
        assert "index.replace" in str(caught.value)
        assert index.documents["a1"] == CORPUS["a1"]

    def test_the_refusal_names_the_first_few_and_counts_the_rest(self) -> None:
        index = DocumentIndex.from_texts({f"d{i}": f"document {i}" for i in range(10)})

        with pytest.raises(ConfigurationError) as caught:
            index.add({f"d{i}": "again" for i in range(8)})

        assert "d0, d1, d2, d3, d4 and 3 more" in str(caught.value)

    def test_the_lexical_statistics_move_with_the_corpus(self) -> None:
        index = DocumentIndex.from_texts({"a1": "seed round"})
        before = index._average_length

        index.add({"a2": "a much longer document about seed rounds and depots and bearings"})

        assert index._average_length > before
        assert index.documents_containing("seed") == {"seed": 2}

    def test_adding_through_the_handle_records_the_call(self) -> None:
        index, _ = semantic_index()
        calls: list[tuple[str, int]] = []

        index.add({"a5": "A new depot opened in Ashford."}, retrieval=handle(calls))

        assert calls == [("embed", 1)]

    def test_a_vector_index_with_no_embedding_client_refuses_an_add(self) -> None:
        index, embedder = semantic_index()
        index.embeddings = None

        with pytest.raises(ConfigurationError) as caught:
            index.add({"a5": "A new depot."})

        assert "cannot be embedded" in str(caught.value)

    def test_adding_under_a_different_model_is_refused(self) -> None:
        index, _ = semantic_index()
        index.embeddings = FakeEmbeddingClient(
            model_identity=ModelIdentity(backend="self_hosted", request_model="other/embed")
        )

        with pytest.raises(ConfigurationError) as caught:
            index.add({"a5": "A new depot."})

        assert "occupy different spaces" in str(caught.value)
        # An add embeds documents; naming a query would send the reader to the search.
        assert "the documents would be embedded by 'other/embed'" in str(caught.value)


class TestGrowingMatchesBuildingWhole:
    """The promise of the three verbs: the index is what a rebuild would have produced."""

    LONGER = {
        **CORPUS,
        "a5": "The Ashford depot refused a delivery of bearings after 4pm in March.",
        "a6": "Corveth's second seed round closed in March, quietly.",
        "a7": "Part AX-7720-C replaced the bearing in the Ashford depot.",
        "a8": "A delivery quoted the part number and was refused all the same.",
    }
    QUERY = "ashford depot bearing refused march"

    def test_an_index_grown_one_at_a_time_scores_like_one_built_whole(self) -> None:
        grown = DocumentIndex.from_texts(dict(CORPUS))
        for doc_id in ("a5", "a6", "a7", "a8"):
            grown.add({doc_id: self.LONGER[doc_id]})
        whole = DocumentIndex.from_texts(dict(self.LONGER))

        one = grown.lexical_scores(self.QUERY, 8)
        two = whole.lexical_scores(self.QUERY, 8)

        assert [doc_id for doc_id, _ in one] == [doc_id for doc_id, _ in two]
        assert all(a == pytest.approx(b, abs=1e-9) for (_, a), (_, b) in zip(one, two))

    def test_a_shrunk_index_scores_like_one_built_without_it(self) -> None:
        shrunk = DocumentIndex.from_texts(dict(self.LONGER))
        shrunk.remove(["a7", "a8"])
        without = DocumentIndex.from_texts(
            {k: v for k, v in self.LONGER.items() if k not in ("a7", "a8")}
        )

        one = shrunk.lexical_scores(self.QUERY, 8)
        two = without.lexical_scores(self.QUERY, 8)

        assert [doc_id for doc_id, _ in one] == [doc_id for doc_id, _ in two]
        assert all(a == pytest.approx(b, abs=1e-9) for (_, a), (_, b) in zip(one, two))

    def test_replacing_a_document_with_its_own_text_moves_no_score(self) -> None:
        index = DocumentIndex.from_texts(dict(self.LONGER))
        before = index.lexical_scores(self.QUERY, 8)

        index.replace({"a5": self.LONGER["a5"]})

        assert index.lexical_scores(self.QUERY, 8) == before

    def test_the_vectors_of_a_grown_index_are_the_vectors_of_a_whole_one(self) -> None:
        embedder = FakeEmbeddingClient()
        grown = DocumentIndex.from_texts(dict(CORPUS), embeddings=embedder, ranking=Semantic())
        for doc_id in ("a5", "a6", "a7", "a8"):
            grown.add({doc_id: self.LONGER[doc_id]})
        whole = DocumentIndex.from_texts(
            dict(self.LONGER), embeddings=FakeEmbeddingClient(), ranking=Semantic()
        )
        query = normalise(FakeEmbeddingClient().embed([self.QUERY]).vectors[0])

        one = grown.semantic_scores(query, 8)
        two = whole.semantic_scores(query, 8)

        assert [doc_id for doc_id, _ in one] == [doc_id for doc_id, _ in two]
        assert all(a == pytest.approx(b, abs=1e-6) for (_, a), (_, b) in zip(one, two))


class TestAnEmbeddingCallThatFails:
    """The one step of a write that can fail on something outside the process."""

    class Refusing:
        model_identity = ModelIdentity(
            backend="self_hosted", request_model="test/embed", model_revision="0" * 40
        )

        def identity(self):
            return self.model_identity

        def embed(self, texts):
            raise RuntimeError("the embedding endpoint is down")

    def test_an_add_that_cannot_embed_leaves_the_corpus_as_it_was(self) -> None:
        index, _ = semantic_index()
        index.embeddings = self.Refusing()

        with pytest.raises(RuntimeError):
            index.add({"a5": "A new depot opened in Ashford."})

        assert "a5" not in index.documents
        assert index.documents_containing("ashford") == {"ashford": 0}
        assert len(index) == len(index.vectors) == 4

    def test_a_replace_that_cannot_embed_keeps_the_old_document(self) -> None:
        index, _ = semantic_index()
        index.embeddings = self.Refusing()

        with pytest.raises(RuntimeError):
            index.replace({"a4": "Collection from the wharf is refused after 4pm."})

        assert index.documents["a4"] == CORPUS["a4"]
        assert [doc_id for doc_id, _ in index.lexical_scores("depot", 1)] == ["a4"]
        assert len(index.vectors) == 4

    def test_a_replace_on_a_store_that_cannot_remove_refuses_before_it_embeds(self) -> None:
        """The refusal names the store rather than leaving the old vector behind the new."""

        class AddOnly:
            def __init__(self) -> None:
                self._scan = VectorScan()

            def add(self, ids, vectors):
                self._scan.add(ids, vectors)

            def search(self, vector, top_k):
                return self._scan.search(vector, top_k)

            def __len__(self):
                return len(self._scan)

        embedder = FakeEmbeddingClient()
        index = DocumentIndex.from_texts(
            dict(CORPUS), embeddings=embedder, ranking=Semantic(), vectors=AddOnly()
        )
        embedder.texts.clear()

        with pytest.raises(ConfigurationError) as caught:
            index.replace({"a4": "Collection from the wharf is refused after 4pm."})

        assert "declares no remove(ids)" in str(caught.value)
        assert embedder.texts == []
        assert index.documents["a4"] == CORPUS["a4"]


class TestReplacingAndRemoving:
    def test_replacing_changes_what_the_words_find(self) -> None:
        index = DocumentIndex.from_texts(dict(CORPUS))

        index.replace({"a4": "Collection from the wharf is refused after 4pm."})

        assert index.search("depot", top_k=3) == []
        assert [hit.doc_id for hit in index.search("wharf", top_k=1)] == ["a4"]

    def test_replacing_re_embeds_only_that_document(self) -> None:
        index, embedder = semantic_index()
        embedder.texts.clear()

        index.replace({"a4": "Collection from the wharf is refused after 4pm."})

        assert embedder.texts == ["Collection from the wharf is refused after 4pm."]
        assert len(index.vectors) == 4

    def test_the_old_vector_is_gone_after_a_replace(self) -> None:
        index, _ = semantic_index()

        index.replace({"a4": "Collection from the wharf is refused after 4pm."})
        found = index.search(CORPUS["a4"], top_k=4, retrieval=handle())

        assert [hit.doc_id for hit in found][0] != "a4"

    def test_an_identifier_not_held_is_refused_and_names_add(self) -> None:
        index = DocumentIndex.from_texts(dict(CORPUS))

        with pytest.raises(ConfigurationError) as caught:
            index.replace({"a9": "Nothing here."})

        assert "does not hold" in str(caught.value)
        assert "index.add" in str(caught.value)

    def test_removing_takes_the_words_and_the_vectors(self) -> None:
        index, _ = semantic_index()

        index.remove(["a4"])

        assert "a4" not in index.documents
        assert len(index.vectors) == 3
        assert index.documents_containing("depot") == {"depot": 0}

    def test_removing_something_not_held_is_refused(self) -> None:
        index = DocumentIndex.from_texts(dict(CORPUS))

        with pytest.raises(ConfigurationError) as caught:
            index.remove(["a9"])

        assert "does not hold" in str(caught.value)

    def test_removing_everything_is_refused_the_way_an_empty_index_is(self) -> None:
        index = DocumentIndex.from_texts(dict(CORPUS))

        with pytest.raises(ConfigurationError) as caught:
            index.remove(list(CORPUS))

        assert "returns nothing to every search" in str(caught.value)
        assert len(index) == 4

    def test_a_store_with_no_remove_is_refused_rather_than_left_holding_it(self) -> None:
        class AddOnly:
            def __init__(self) -> None:
                self._scan = VectorScan()

            def add(self, ids, vectors):
                self._scan.add(ids, vectors)

            def search(self, vector, top_k):
                return self._scan.search(vector, top_k)

            def __len__(self):
                return len(self._scan)

        index = DocumentIndex.from_texts(
            dict(CORPUS), embeddings=FakeEmbeddingClient(), ranking=Semantic(), vectors=AddOnly()
        )

        with pytest.raises(ConfigurationError) as caught:
            index.remove(["a4"])

        assert "declares no remove(ids)" in str(caught.value)
        assert "a4" in index.documents


class TestTheStoreAnIndexBuilds:
    def test_a_store_passed_in_empty_is_filled(self) -> None:
        """The documented escape hatch: `vectors=MyStore()` gets the corpus embedded into it."""
        store = VectorScan()

        index = DocumentIndex.from_texts(
            dict(CORPUS), embeddings=FakeEmbeddingClient(), ranking=Semantic(), vectors=store
        )

        assert len(store) == 4
        assert index.search(CORPUS["a3"], top_k=1, retrieval=handle())[0].doc_id == "a3"

    def test_a_store_passed_in_full_is_used_as_it_is(self) -> None:
        embedder = FakeEmbeddingClient()
        store = VectorScan()
        store.add(
            list(CORPUS), [normalise(v) for v in embedder.embed(list(CORPUS.values())).vectors]
        )
        embedder.texts.clear()

        DocumentIndex.from_texts(
            dict(CORPUS), embeddings=embedder, ranking=Semantic(), vectors=store
        )

        assert embedder.texts == []

    def test_a_partly_filled_store_has_the_rest_embedded(self) -> None:
        embedder = FakeEmbeddingClient()
        store = VectorScan()
        store.add(["a1"], [normalise(embedder.embed([CORPUS["a1"]]).vectors[0])])
        embedder.texts.clear()

        DocumentIndex.from_texts(
            dict(CORPUS), embeddings=embedder, ranking=Semantic(), vectors=store
        )

        assert len(embedder.texts) == 3
        assert len(store) == 4

    def test_a_store_passed_in_full_leaves_the_embedding_model_unknown(self) -> None:
        """Nothing here embedded anything, so what made those vectors is the caller's to say."""
        embedder = FakeEmbeddingClient()
        store = VectorScan()
        store.add(
            list(CORPUS), [normalise(v) for v in embedder.embed(list(CORPUS.values())).vectors]
        )

        index = DocumentIndex.from_texts(
            dict(CORPUS), embeddings=embedder, ranking=Semantic(), vectors=store
        )

        assert index.embedded_by is None

    def test_a_saved_index_that_names_no_model_does_not_take_the_reader_s(self, tmp_path) -> None:
        """Adopting one would put a model on the record that never saw the corpus."""
        embedder = FakeEmbeddingClient()
        store = VectorScan()
        store.add(
            list(CORPUS), [normalise(v) for v in embedder.embed(list(CORPUS.values())).vectors]
        )
        written = DocumentIndex.from_texts(
            dict(CORPUS), embeddings=embedder, ranking=Semantic(), vectors=store
        ).save(tmp_path / "corpus.index")
        assert json.loads(written.read_text())["embedded_by"] is None

        back = DocumentIndex.load(
            written,
            embeddings=FakeEmbeddingClient(
                model_identity=ModelIdentity(backend="hosted_api", request_model="someone/else")
            ),
            ranking=Semantic(),
        )

        assert back.embedded_by is None
        assert back.to_record()["embedded_by"] is None

    def test_an_empty_store_with_no_client_is_refused_by_name(self) -> None:
        """The store cannot be filled and the index would search a corpus it has no vectors for."""
        with pytest.raises(ConfigurationError) as caught:
            DocumentIndex.from_texts(dict(CORPUS), ranking=Semantic(), vectors=NumpyVectors())

        assert "holding 0 of its 4 document(s)" in str(caught.value)
        assert "Pass embeddings=" in str(caught.value)

    def test_a_full_store_with_no_client_is_allowed(self) -> None:
        """Nothing needs embedding, so nothing needs a client to embed it."""
        embedder = FakeEmbeddingClient()
        store = VectorScan()
        store.add(
            list(CORPUS), [normalise(v) for v in embedder.embed(list(CORPUS.values())).vectors]
        )

        index = DocumentIndex.from_texts(dict(CORPUS), ranking=Semantic(), vectors=store)

        assert len(index.vectors) == 4
        assert index.semantic_scores(store.all_vectors()[0], 1)[0][0] == "a1"

    def test_the_default_is_numpy_where_it_imports(self) -> None:
        index, _ = semantic_index()

        assert type(index.vectors) is type(default_store())
        assert type(index.vectors).__name__ == "NumpyVectors"


class TestTheExactStoresAgree:
    """`NumpyVectors` is the default and `VectorScan` is the fallback, so they answer alike."""

    @pytest.fixture
    def vectors(self) -> list[list[float]]:
        embedder = FakeEmbeddingClient(dimensions=32)
        return [normalise(v) for v in embedder.embed(list(CORPUS.values())).vectors]

    def test_they_return_one_order(self, vectors) -> None:
        scan, numpy_store = VectorScan(), NumpyVectors()
        scan.add(list(CORPUS), vectors)
        numpy_store.add(list(CORPUS), vectors)

        for query in vectors:
            scanned = scan.search(query, top_k=4)
            fast = numpy_store.search(query, top_k=4)
            assert [doc_id for doc_id, _ in scanned] == [doc_id for doc_id, _ in fast]
            for (_, one), (_, two) in zip(scanned, fast):
                assert one == pytest.approx(two, abs=1e-5)

    def test_they_break_a_tie_the_same_way(self) -> None:
        """Identical vectors score equal, and the identifier settles the order."""
        same = [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]
        scan, numpy_store = VectorScan(), NumpyVectors()
        scan.add(["b", "a", "c"], same)
        numpy_store.add(["b", "a", "c"], same)

        assert [doc_id for doc_id, _ in scan.search([1.0, 0.0], top_k=2)] == [
            doc_id for doc_id, _ in numpy_store.search([1.0, 0.0], top_k=2)
        ]

    def test_both_are_empty_before_anything_is_added(self) -> None:
        assert VectorScan().search([1.0, 0.0], top_k=3) == []
        assert NumpyVectors().search([1.0, 0.0], top_k=3) == []

    def test_both_refuse_identifiers_and_vectors_of_different_lengths(self) -> None:
        for store in (VectorScan(), NumpyVectors()):
            with pytest.raises(ConfigurationError) as caught:
                store.add(["a", "b"], [[1.0, 0.0]])
            assert "paired by position" in str(caught.value)

    def test_numpy_refuses_a_second_width(self) -> None:
        store = NumpyVectors()
        store.add(["a"], [[1.0, 0.0]])

        with pytest.raises(ConfigurationError) as caught:
            store.add(["b"], [[1.0, 0.0, 0.0]])

        assert "requires one width" in str(caught.value)

    def test_removing_from_numpy_leaves_the_rest_paired(self) -> None:
        store = NumpyVectors()
        store.add(["a", "b", "c"], [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]])

        store.remove(["b"])

        assert store.ids() == ["a", "c"]
        assert store.search([0.0, 1.0], top_k=1)[0][0] == "c"

    def test_removing_everything_from_numpy_leaves_an_empty_store(self) -> None:
        store = NumpyVectors()
        store.add(["a"], [[1.0, 0.0]])

        store.remove(["a"])

        assert len(store) == 0
        assert store.search([1.0, 0.0], top_k=1) == []
        assert store.dimensions is None


class TestTwoWritersAndAReader:
    """A corpus that grows is read while it is written."""

    def test_an_add_beside_a_search_leaves_one_consistent_index(self) -> None:
        index = DocumentIndex.from_texts({"seed": "the seed document about depots"})
        failures: list[BaseException] = []
        stop = threading.Event()

        def adding() -> None:
            try:
                for i in range(200):
                    index.add({f"w{i}": f"document {i} about depots and bearings"})
            except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
                failures.append(exc)
            finally:
                stop.set()

        def searching() -> None:
            try:
                while not stop.is_set():
                    index.search("depots", top_k=3)
                    index.documents_containing("depots bearings")
            except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
                failures.append(exc)

        writer = threading.Thread(target=adding)
        reader = threading.Thread(target=searching)
        writer.start()
        reader.start()
        writer.join()
        reader.join()

        assert failures == []
        assert len(index) == 201

    def test_an_add_cannot_land_inside_a_save(self, tmp_path) -> None:
        """`save` reads the identifiers and the vectors from the store as two calls.

        An add landing between the two writes a file naming one number of documents and
        holding another. The add is made from another thread inside that window, so it waits
        for the save rather than landing in the middle of it.
        """
        index, _ = semantic_index()
        store = index.vectors
        started: list[threading.Thread] = []
        landed: list[BaseException | None] = []

        def adding() -> None:
            try:
                index.add({"a5": "A new depot opened in Ashford."})
                landed.append(None)
            except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
                landed.append(exc)

        class AddsWhileRead:
            """A store that runs an add while `save` is between its two reads."""

            def ids(self):
                held = store.ids()
                # After the snapshot and before `save` asks for the vectors, which is the
                # window an add has to land in for the two to disagree.
                thread = threading.Thread(target=adding)
                started.append(thread)
                thread.start()
                thread.join(timeout=0.2)
                return held

            def __getattr__(self, name):
                return getattr(store, name)

            def __len__(self):
                return len(store)

        index.vectors = AddsWhileRead()

        written = index.save(tmp_path / "corpus.index")

        assert landed == [], "the add ran inside the save rather than waiting for it"
        started[0].join(timeout=2)
        assert landed == [None]
        back = DocumentIndex.load(written, embeddings=FakeEmbeddingClient(), ranking=Semantic())
        assert len(back) == 4
        assert len(back.vectors) == 4
        assert len(index) == 5

    def test_a_search_runs_while_an_add_is_embedding(self) -> None:
        """A bulk add embeds for as long as its backend takes, and searches carry on."""
        index, _ = semantic_index()
        searched = threading.Event()
        embedding = threading.Event()

        class Slow:
            model_identity = FakeEmbeddingClient().model_identity

            def identity(self):
                return self.model_identity

            def embed(self, texts):
                embedding.set()
                # The search has to get through while this call is in flight.
                if not searched.wait(timeout=2):
                    raise AssertionError("the search waited for the embedding call")
                return FakeEmbeddingClient().embed(texts)

        index.embeddings = Slow()

        def searching() -> None:
            # The paths that take the index's lock, and no model call of their own: the
            # query's embedding would go through the same client and wait on it.
            embedding.wait(timeout=2)
            index.lexical_scores("depot", 1)
            index.documents_containing("depot")
            searched.set()

        reader = threading.Thread(target=searching)
        reader.start()
        index.add({"a5": "A new depot opened in Ashford."})
        reader.join(timeout=3)

        assert searched.is_set()
        assert len(index) == 5

    def test_two_adders_never_lose_a_document(self) -> None:
        index = DocumentIndex.from_texts({"seed": "the seed document"})

        def adding(tag: int) -> None:
            for i in range(100):
                index.add({f"{tag}-{i}": f"document {i} from writer {tag}"})

        threads = [threading.Thread(target=adding, args=(tag,)) for tag in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(index) == 401
        assert len(index._lengths) == 401


class TestSavingAndLoading:
    def test_it_writes_the_json_and_the_vectors_beside_it(self, tmp_path) -> None:
        index, _ = semantic_index()

        written = index.save(tmp_path / "corpus.index")
        raw = json.loads(written.read_text())

        assert raw["format_version"] == INDEX_FORMAT_VERSION
        assert raw["analyzer"] == ANALYZER
        assert raw["store"] == "NumpyVectors"
        assert raw["vectors"] == "corpus.index" + VECTOR_FILE_SUFFIX
        sidecar = tmp_path / ("corpus.index" + VECTOR_FILE_SUFFIX)
        assert sidecar.stat().st_size == 4 * 4 * 16

    def test_it_round_trips_the_documents_and_the_vectors(self, tmp_path) -> None:
        index, _ = semantic_index()
        before = index.search(CORPUS["a3"], top_k=4, retrieval=handle())

        index.save(tmp_path / "corpus.index")
        back = DocumentIndex.load(
            tmp_path / "corpus.index", embeddings=FakeEmbeddingClient(), ranking=Semantic()
        )

        assert back.documents == CORPUS
        after = back.search(CORPUS["a3"], top_k=4, retrieval=handle())
        assert [hit.doc_id for hit in after] == [hit.doc_id for hit in before]
        for one, two in zip(before, after):
            assert one.score == pytest.approx(two.score, abs=1e-5)

    def test_loading_does_not_re_embed(self, tmp_path) -> None:
        index, _ = semantic_index()
        index.save(tmp_path / "corpus.index")
        embedder = FakeEmbeddingClient()

        DocumentIndex.load(tmp_path / "corpus.index", embeddings=embedder, ranking=Semantic())

        assert embedder.texts == []

    def test_an_index_added_to_and_saved_carries_the_new_documents(self, tmp_path) -> None:
        index, _ = semantic_index()
        index.add({"a5": "A new depot opened in Ashford."})
        index.save(tmp_path / "corpus.index")

        back = DocumentIndex.load(
            tmp_path / "corpus.index", embeddings=FakeEmbeddingClient(), ranking=Semantic()
        )

        assert len(back) == 5
        assert (
            back.search("A new depot opened in Ashford.", top_k=1, retrieval=handle())[0].doc_id
            == "a5"
        )

    def test_a_removed_document_is_gone_from_the_saved_file(self, tmp_path) -> None:
        index, _ = semantic_index()
        index.remove(["a4"])
        index.save(tmp_path / "corpus.index")

        raw = json.loads((tmp_path / "corpus.index").read_text())

        assert "a4" not in raw["documents"]
        assert raw["order"] == ["a1", "a2", "a3"]
        assert (tmp_path / ("corpus.index" + VECTOR_FILE_SUFFIX)).stat().st_size == 3 * 4 * 16

    def test_it_loads_into_the_store_it_was_given(self, tmp_path) -> None:
        index, _ = semantic_index()
        index.save(tmp_path / "corpus.index")

        back = DocumentIndex.load(
            tmp_path / "corpus.index",
            embeddings=FakeEmbeddingClient(),
            ranking=Semantic(),
            vectors=VectorScan(),
        )

        assert isinstance(back.vectors, VectorScan)
        assert len(back.vectors) == 4

    def test_a_file_written_by_the_older_format_is_still_read(self, tmp_path) -> None:
        """`1.0` packed the vectors into the JSON as base64."""
        import base64
        from array import array

        embedder = FakeEmbeddingClient()
        vectors = [normalise(v) for v in embedder.embed(list(CORPUS.values())).vectors]
        (tmp_path / "old.index").write_text(
            json.dumps(
                {
                    "format_version": "1.0",
                    "documents": CORPUS,
                    "stopwords": [],
                    "embedded_by": embedder.identity().to_manifest(),
                    "order": list(CORPUS),
                    "dimensions": 16,
                    "vectors": base64.b64encode(
                        b"".join(array("f", v).tobytes() for v in vectors)
                    ).decode("ascii"),
                }
            )
        )

        back = DocumentIndex.load(
            tmp_path / "old.index", embeddings=FakeEmbeddingClient(), ranking=Semantic()
        )

        assert len(back.vectors) == 4
        assert back.search(CORPUS["a2"], top_k=1, retrieval=handle())[0].doc_id == "a2"

    def test_a_refused_save_leaves_the_index_that_was_there(self, tmp_path) -> None:
        """An index is two files that have to agree, and re-embedding a corpus is the cost."""

        class Racing:
            """A store that grew between `ids()` and `all_vectors()`."""

            def __init__(self, real) -> None:
                self._real = real

            def add(self, ids, vectors):
                self._real.add(ids, vectors)

            def search(self, vector, top_k):
                return self._real.search(vector, top_k)

            def ids(self):
                return self._real.ids()

            def all_vectors(self):
                rows = list(self._real.all_vectors())
                return rows + [list(rows[0])]

            def __len__(self):
                return len(self._real)

        index, _ = semantic_index()
        written = index.save(tmp_path / "corpus.index")
        held = (tmp_path / ("corpus.index" + VECTOR_FILE_SUFFIX)).read_bytes()
        index.vectors = Racing(index.vectors)

        with pytest.raises(ConfigurationError):
            index.save(tmp_path / "corpus.index")

        assert (tmp_path / ("corpus.index" + VECTOR_FILE_SUFFIX)).read_bytes() == held
        assert sorted(p.name for p in tmp_path.iterdir()) == [
            "corpus.index",
            "corpus.index" + VECTOR_FILE_SUFFIX,
        ]
        back = DocumentIndex.load(written, embeddings=FakeEmbeddingClient(), ranking=Semantic())
        assert len(back.vectors) == 4

    def test_the_vectors_are_read_as_a_matrix_where_numpy_is_installed(self, tmp_path) -> None:
        """A list of Python floats is about nine times the file, which a large corpus is not."""
        import numpy

        from simple_agents.builtins.index_file import _read_vectors

        index, _ = semantic_index()
        written = index.save(tmp_path / "corpus.index")

        read = _read_vectors(json.loads(written.read_text()), written)

        assert isinstance(read, numpy.ndarray)
        assert read.shape == (4, 16)
        assert read.dtype == numpy.dtype("float32")

    def test_a_missing_vector_file_says_both_files_move_together(self, tmp_path) -> None:
        index, _ = semantic_index()
        index.save(tmp_path / "corpus.index")
        (tmp_path / ("corpus.index" + VECTOR_FILE_SUFFIX)).unlink()

        with pytest.raises(ConfigurationError) as caught:
            DocumentIndex.load(
                tmp_path / "corpus.index", embeddings=FakeEmbeddingClient(), ranking=Semantic()
            )

        assert "both move together" in str(caught.value)

    def test_a_vector_file_of_the_wrong_size_is_refused(self, tmp_path) -> None:
        index, _ = semantic_index()
        index.save(tmp_path / "corpus.index")
        sidecar = tmp_path / ("corpus.index" + VECTOR_FILE_SUFFIX)
        sidecar.write_bytes(sidecar.read_bytes()[:-8])

        with pytest.raises(ConfigurationError) as caught:
            DocumentIndex.load(
                tmp_path / "corpus.index", embeddings=FakeEmbeddingClient(), ranking=Semantic()
            )

        assert "from different saves" in str(caught.value)

    def test_a_file_in_a_format_this_version_does_not_read_is_refused(self, tmp_path) -> None:
        index, _ = semantic_index()
        written = index.save(tmp_path / "corpus.index")
        raw = json.loads(written.read_text())
        raw["format_version"] = "3.0"
        written.write_text(json.dumps(raw))

        with pytest.raises(ConfigurationError) as caught:
            DocumentIndex.load(written, embeddings=FakeEmbeddingClient(), ranking=Semantic())

        assert "is format '3.0'" in str(caught.value)
        assert "reads 1.0 and 2.0" in str(caught.value)

    def test_a_file_with_no_format_version_is_refused(self, tmp_path) -> None:
        (tmp_path / "corpus.index").write_text(json.dumps({"documents": {"a": "one"}}))

        with pytest.raises(ConfigurationError) as caught:
            DocumentIndex.load(tmp_path / "corpus.index")

        assert "unstated" in str(caught.value)

    def test_a_file_written_by_another_analyzer_is_refused(self, tmp_path) -> None:
        index, _ = semantic_index()
        written = index.save(tmp_path / "corpus.index")
        raw = json.loads(written.read_text())
        raw["analyzer"] = "porter-stemmed"
        written.write_text(json.dumps(raw))

        with pytest.raises(ConfigurationError) as caught:
            DocumentIndex.load(
                tmp_path / "corpus.index", embeddings=FakeEmbeddingClient(), ranking=Semantic()
            )

        assert "decides what a word is" in str(caught.value)

    def test_a_store_that_cannot_hand_its_vectors_back_is_refused(self, tmp_path) -> None:
        class Opaque:
            def __init__(self) -> None:
                self._scan = VectorScan()

            def add(self, ids, vectors):
                self._scan.add(ids, vectors)

            def search(self, vector, top_k):
                return self._scan.search(vector, top_k)

            def __len__(self):
                return len(self._scan)

        index = DocumentIndex.from_texts(
            dict(CORPUS), embeddings=FakeEmbeddingClient(), ranking=Semantic(), vectors=Opaque()
        )

        with pytest.raises(ConfigurationError) as caught:
            index.save(tmp_path / "corpus.index")

        assert "re-embeds the whole corpus" in str(caught.value)

    def test_a_lexical_index_saves_and_loads_with_no_vector_file(self, tmp_path) -> None:
        DocumentIndex.from_texts(dict(CORPUS)).save(tmp_path / "corpus.index")

        back = DocumentIndex.load(tmp_path / "corpus.index")

        assert not (tmp_path / ("corpus.index" + VECTOR_FILE_SUFFIX)).exists()
        assert isinstance(back.ranking, Lexical)
        assert [hit.doc_id for hit in back.search("bearing", top_k=1)] == ["a3"]


class TestWhatARunRecords:
    def test_the_tool_entry_says_how_the_index_ranks_and_where_the_vectors_are(self) -> None:
        index, _ = semantic_index()

        record = index.to_record()

        assert record["ranking"] == "Semantic"
        assert record["store"] == "NumpyVectors"
        assert record["exact"] is True
        assert record["analyzer"] == ANALYZER
        assert record["embedded_by"]["request_model"] == "test/embed"

    def test_the_tool_entry_holds_no_count_of_the_documents(self) -> None:
        """It is part of `behaviour_fingerprint`, and a grown corpus is not a changed pipeline."""
        index, _ = semantic_index()

        before = index.to_record()
        index.add({"a5": "A new depot opened in Ashford."})

        assert index.to_record() == before
        assert "documents" not in before

    def test_the_manifest_entry_counts_the_corpus(self) -> None:
        index, _ = semantic_index()
        index.add({"a5": "A new depot opened in Ashford."})

        entry = index.to_manifest()

        assert entry["documents"] == 5
        assert entry["vectors"] == 5
        assert entry["store"] == "NumpyVectors"

    def test_a_lexical_index_records_a_ranking_and_no_store(self) -> None:
        record = DocumentIndex.from_texts(dict(CORPUS)).to_record()

        assert record["ranking"] == "Lexical"
        assert record["store"] is None
        assert record["exact"] is None
        assert record["embedded_by"] is None

    def test_a_hybrid_index_records_the_fusion_beside_the_store(self) -> None:
        index = DocumentIndex.from_texts(
            dict(CORPUS), embeddings=FakeEmbeddingClient(), ranking=Hybrid(fuse=RRF(k=9))
        )

        record = index.to_record()

        assert record["fusion"] == "RRF"
        assert record["fusion_settings"] == {"k": 9}
        assert record["store"] == "NumpyVectors"

    def test_the_tool_carries_the_index_it_searches(self) -> None:
        index, _ = semantic_index()

        assert document_search(index).searches is index
        assert document_search(DocumentIndex.from_texts(dict(CORPUS))).searches is not None


class TestWhatOneRunWrites:
    """The record reaches the manifest through the tool that searches the index."""

    def _pipeline(self, index):
        return Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: Prompt.user("find the depot"),
                    tools=[document_search(index)],
                    output_schema=Answer,
                    budget=Budget.unbounded(),
                )
            ],
            budget=Budget.unbounded(),
        )

    def _client(self):
        return FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c1", name="document_search", arguments={"query": "depot"}
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c2", name="finish", arguments={"answer": "a4", "citations": []}
                        )
                    ]
                ),
            ]
        )

    def test_the_tool_entry_carries_how_the_index_ranks(self, envelope, run_root) -> None:
        index, _ = semantic_index()

        self._pipeline(index).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        manifest = json.loads((run_root / "manifest.json").read_text())
        [entry] = [t for t in manifest["tools"] if t["name"] == "document_search"]
        assert entry["retrieval"]["ranking"] == "Semantic"
        assert entry["retrieval"]["store"] == "NumpyVectors"
        assert entry["retrieval"]["exact"] is True

    def test_the_manifest_counts_the_corpus_when_the_run_ends(self, envelope, run_root) -> None:
        index, _ = semantic_index()

        self._pipeline(index).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        manifest = json.loads((run_root / "manifest.json").read_text())
        assert manifest["retrieval"] == [
            {
                "tool": "document_search",
                "documents": 4,
                "store": "NumpyVectors",
                "exact": True,
                "vectors": 4,
                "embedded_by": index.embedded_by.to_manifest(),
            }
        ]

    def test_a_run_that_added_a_document_leaves_the_count_it_finished_with(
        self, envelope, run_root
    ) -> None:
        index, _ = semantic_index()
        pipeline = self._pipeline(index)
        index.add({"a5": "A new depot opened in Ashford."})

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client())

        manifest = json.loads((run_root / "manifest.json").read_text())
        assert manifest["retrieval"][0]["documents"] == 5

    def test_a_corpus_that_grew_does_not_move_the_behaviour_fingerprint(self) -> None:
        index, _ = semantic_index()
        pipeline = self._pipeline(index)
        before = pipeline.behaviour_fingerprint(model=self._client())

        index.add({"a5": "A new depot opened in Ashford."})

        assert pipeline.behaviour_fingerprint(model=self._client()) == before

    def test_a_changed_store_does_move_it(self) -> None:
        index, _ = semantic_index()
        pipeline = self._pipeline(index)
        before = pipeline.behaviour_fingerprint(model=self._client())

        index.vectors = VectorScan()

        assert pipeline.behaviour_fingerprint(model=self._client()) != before

    def test_a_lexical_index_is_counted_with_no_store(self, envelope, run_root) -> None:
        """The corpus size is worth recording whether or not anything embedded it."""
        index = DocumentIndex.from_texts(dict(CORPUS))

        self._pipeline(index).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        manifest = json.loads((run_root / "manifest.json").read_text())
        assert manifest["retrieval"] == [
            {
                "tool": "document_search",
                "documents": 4,
                "store": None,
                "exact": None,
                "vectors": 0,
                "embedded_by": None,
            }
        ]

    def test_a_pipeline_with_no_index_records_an_empty_array(self, envelope, run_root) -> None:
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: Prompt.user("answer"),
                    tools=[],
                    output_schema=Answer,
                    budget=Budget.unbounded(),
                )
            ],
            budget=Budget.unbounded(),
        )

        pipeline.run(
            {},
            envelope=envelope,
            run_id=RUN_ID,
            seed=41,
            model=FakeModelClient(
                responses=[
                    fake_response(
                        tool_calls=[
                            ToolCallRequest(
                                id="c1",
                                name="finish",
                                arguments={"answer": "x", "citations": []},
                            )
                        ]
                    )
                ]
            ),
        )

        manifest = json.loads((run_root / "manifest.json").read_text())
        assert manifest["retrieval"] == []
