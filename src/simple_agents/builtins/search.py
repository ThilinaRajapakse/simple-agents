"""Search over a document collection the project supplies.

The library ships the retrieval; the project holds the documents. No dataset ships with
Simple Agents, and what counts as the corpus is a builder decision.

An index built without ``embeddings=`` scores BM25 over whitespace-and-punctuation tokens, in
pure Python, so no dependency is added for it. It is a lexical match: a query sharing no words
with a relevant document does not find it.

An index built with ``embeddings=`` also holds a vector per document, and ``ranking=`` says how
the two are searched::

    index = DocumentIndex.from_texts(corpus, embeddings=SentenceTransformerEmbeddings(),
                                     ranking=Hybrid(fuse=RRF(k=5)))

``ranking`` is required there and ``rerank`` decides what reorders the result;
``simple_agents.builtins.ranking`` documents the choices and where their figures come from.

An index grows: ``add`` embeds the new documents alone, ``replace`` re-embeds the ones whose
text changed, and ``remove`` drops them. ``simple_agents.builtins.vectors`` holds the stores
they write through.
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..embeddings import normalise
from ..errors import ConfigurationError, ModelFacingError
from ..models import ModelIdentity
from ..tools import ModelHandle, Retrieval, SideEffectClass, Tool, tool
from .index_file import (
    ANALYZER,
    INDEX_FORMAT_VERSION,
    VECTOR_FILE_SUFFIX,
    has_method,
    read_index,
    refuse_mismatch,
    write_index,
)
from .ranking import (
    Lexical,
    Ranking,
    ranking_to_record,
    refuse_no_ranking,
)
from .vectors import VectorStore, default_store, store_to_record
from .rerank import CrossEncoderRerank, ModelRerank, Reranker

__all__ = [
    "ANALYZER",
    "DocumentIndex",
    "ENGLISH_STOPWORDS",
    "Hit",
    "INDEX_FORMAT_VERSION",
    "VECTOR_FILE_SUFFIX",
    "document_search",
    "tokens",
]

K1 = 1.5
B = 0.75

ENGLISH_STOPWORDS: frozenset[str] = frozenset(
    (
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any",
        "anyone", "anything", "are", "as", "at", "be", "because", "been", "before", "being",
        "below", "between", "both", "but", "by", "can", "cannot", "could", "did", "do",
        "does", "doing", "done", "down", "during", "each", "either", "else", "ever", "every",
        "everyone", "everything", "few", "for", "from", "further", "get", "got", "had",
        "has", "have", "having", "he", "her", "here", "hers", "herself", "him", "himself",
        "his", "how", "however", "i", "if", "in", "into", "is", "it", "its", "itself",
        "just", "let", "like", "many", "me", "might", "mine", "more", "most", "much",
        "must", "my", "myself", "need", "of", "off", "on", "once", "one", "only", "onto",
        "or", "other", "others", "ought", "our", "ours", "ourselves", "out", "over", "own",
        "please", "put", "rather", "same", "shall", "she", "should", "since", "so", "some",
        "someone", "something", "still", "such", "take", "than", "that", "the", "their",
        "theirs", "them", "themselves", "then", "there", "therefore", "these", "they",
        "thing", "things", "this", "those", "though", "through", "thus", "to", "too",
        "under", "until", "up", "upon", "us", "use", "used", "very", "was", "way", "we",
        "well", "were", "what", "whatever", "when", "whenever", "where", "wherever",
        "whether", "which", "while", "who", "whom", "whose", "why", "will", "with",
        "within", "without", "would", "yet",
        # prose-ok: a stopword list is data, and the second-person rule is about prose.
        "you", "your", "yours", "yourself", "yourselves",
    )
)  # fmt: skip
"""The words :class:`DocumentIndex` drops from a query unless ``stopwords`` says otherwise.

English function words and question words, which a question carries and a passage answering it
does not. Negations are not in it: a corpus of policies distinguishes "is refused" from "is not
refused", and dropping ``not`` from a query loses that.

Pass ``stopwords=`` to replace the list, and ``stopwords=()`` to search every word::

    DocumentIndex.from_texts(texts, stopwords=ENGLISH_STOPWORDS | {"depot"})
    DocumentIndex.from_texts(texts, stopwords=())
"""

_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    """The words the index matches on: lowercased, split on anything that is not a letter or digit.

    A project computing anything that has to line up with search results tokenises with this,
    rather than reimplementing the rule and drifting from it::

        tokens("Ashford's 34-inch inseam")   # ['ashford', 's', '34', 'inch', 'inseam']
    """
    return _WORD.findall(text.lower())


@dataclass(frozen=True, slots=True)
class Hit:
    """One search result: which document, how well it matched, and its text.

    ``retriever`` names what found it: ``lexical``, ``semantic`` or ``rerank``. ``score`` is
    that retriever's own, and **two retrievers' scores are not comparable**: a BM25 score is
    unbounded, a cosine is in ``[-1, 1]``, and a cross-encoder's is an unbounded logit. Compare
    a score only against another with the same ``retriever``.

    ``rank`` is the position this document held in the retriever's own list, counting from 1.
    """

    doc_id: str
    score: float
    text: str
    retriever: str = "lexical"
    rank: int = 1

    def to_record(self, *, attributed: bool = False) -> dict[str, Any]:
        """What a search result carries.

        ``attributed`` adds ``retriever`` and ``rank``. They are left out where one retriever
        produced every hit, since a field with one value on every row tells the reader nothing
        and costs the model context on each call.
        """
        record = {"doc_id": self.doc_id, "score": round(self.score, 4), "text": self.text}
        if attributed:
            record["retriever"] = self.retriever
            record["rank"] = self.rank
        return record


@dataclass
class DocumentIndex:
    """A collection of documents, searchable by the words in them and by what they mean.

    Built from a mapping of identifier to text, or from a directory of files whose names
    become the identifiers::

        index = DocumentIndex.from_texts({"a1": "Corveth raised a seed round.",
                                          "a2": "Corveth's seed round closed in March."})
        index = DocumentIndex.from_directory("corpus/", glob="*.md")

    The identifier is what a search result names and what an answer cites. A title is indexed
    by writing it into the text. ``stopwords`` are dropped from a query before searching and
    default to :data:`ENGLISH_STOPWORDS`; they reach the query and not the documents::

        DocumentIndex.from_texts({d["doc_id"]: f"{d['title']} {d['text']}" for d in docs})
        DocumentIndex.from_texts(texts, stopwords={"part", "order", "the"})
        DocumentIndex.from_texts(texts, stopwords=())     # every word the query holds

    **``embeddings`` embeds every document once, when the index is built**, so an index used
    more than once is saved and loaded rather than rebuilt. **``ranking`` is required
    alongside it**: an index that can embed can rank three ways and which one is right depends
    on the queries::

        index = DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic())
        index.save("corpus.index")
        index = DocumentIndex.load("corpus.index", embeddings=embedder, ranking=Semantic())

    An index built without ``embeddings`` ranks
    :class:`~simple_agents.builtins.ranking.Lexical`. ``rerank`` defaults to nothing, and
    ``vectors`` defaults to :func:`~simple_agents.builtins.vectors.default_store`.

    **The corpus grows without being rebuilt**, through :meth:`add`, :meth:`replace` and
    :meth:`remove`::

        index.add({"a3": "Corveth opened a second depot."}, retrieval=handle)
        index.save("corpus.index")
    """

    documents: dict[str, str]
    stopwords: frozenset[str] | None = None
    embeddings: Any = None
    ranking: Ranking | None = None
    rerank: Reranker | None = None
    vectors: VectorStore | None = None
    embedded_by: ModelIdentity | None = None
    _postings: dict[str, dict[str, int]] = field(default_factory=dict, init=False, repr=False)
    _lengths: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _average_length: float = field(default=0.0, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    """Guards the documents, the postings and the lengths together.

    A corpus that grows is read while it is written: a search scoring BM25 over the postings
    runs on one thread while `add` writes into them on another, and a dict being resized under
    an iterator raises. **Neither side holds it across a model call**: a search embeds its
    query before taking it, and `add` embeds the new documents before taking it, so what
    either one waits for is the other's bookkeeping.
    """

    def __post_init__(self) -> None:
        self.stopwords = (
            ENGLISH_STOPWORDS
            if self.stopwords is None
            else frozenset(word for entry in self.stopwords for word in tokens(str(entry)))
        )
        if not self.documents:
            raise ConfigurationError(
                "DocumentIndex was built with no documents, so every search returns nothing "
                "and the agent has no way to tell that from a corpus that does not contain "
                "the answer.\n"
                "Pass the documents: DocumentIndex.from_texts({'a1': '...'}) or "
                "DocumentIndex.from_directory('corpus/')."
            )
        if self.ranking is None:
            if self.embeddings is not None:
                raise ConfigurationError(refuse_no_ranking("DocumentIndex"))
            self.ranking = Lexical()
        self._check_ranking()
        for doc_id, text in self.documents.items():
            self._index_words(doc_id, text)
        self._set_average_length()
        if self.ranking.needs_vectors:
            if self.vectors is None:
                self.vectors = default_store()
            self._build_vectors()

    def _index_words(self, doc_id: str, text: str) -> None:
        """Put one document's words into the postings. The caller holds the lock."""
        counts = Counter(tokens(text))
        self._lengths[doc_id] = sum(counts.values())
        for term, count in counts.items():
            self._postings.setdefault(term, {})[doc_id] = count

    def _unindex_words(self, doc_id: str) -> None:
        """Take one document's words back out of the postings. The caller holds the lock."""
        for term in set(tokens(self.documents.get(doc_id, ""))):
            postings = self._postings.get(term)
            if postings is not None:
                postings.pop(doc_id, None)
                if not postings:
                    del self._postings[term]
        self._lengths.pop(doc_id, None)

    def _set_average_length(self) -> None:
        total = sum(self._lengths.values())
        self._average_length = total / len(self._lengths) if self._lengths else 0.0

    def _check_ranking(self) -> None:
        assert self.ranking is not None
        if self.ranking.needs_vectors and self.embeddings is None and self.vectors is None:
            raise ConfigurationError(
                f"DocumentIndex was given ranking={type(self.ranking).__name__}(), which "
                f"compares vectors, and no embedding client to produce them.\n"
                f"Pass embeddings=: DocumentIndex.from_texts(texts, "
                f"embeddings=SentenceTransformerEmbeddings()), which needs the `semantic` "
                f"extra, or embeddings=OpenAIEmbeddings(base_url=..., model=...) against an "
                f"endpoint. Use ranking=Lexical() to search the words alone."
            )
        if self.rerank is not None and not isinstance(
            self.rerank, (CrossEncoderRerank, ModelRerank)
        ):
            if not hasattr(self.rerank, "top_n"):
                raise ConfigurationError(
                    f"DocumentIndex was given rerank={self.rerank!r}, which declares no "
                    f"top_n, and how many candidates reach it is undeclared.\n"
                    f"Pass rerank=CrossEncoderRerank(LocalCrossEncoder(), top_n=20) or "
                    f"rerank=ModelRerank(top_n=10)."
                )

    def _build_vectors(self) -> None:
        """Embed the documents the store does not already hold, at construction.

        A store handed in already full is used as it is, which is what a loaded index and the
        agent's own memory pass. An empty one is filled from the corpus. A partly filled one
        has the rest embedded, so a store carried over from a smaller corpus is completed
        rather than searched with holes in it.
        """
        missing = self._not_in_the_store(self.documents)
        if missing and self.embeddings is None:
            raise ConfigurationError(
                f"DocumentIndex was given a vector ranking and a store holding "
                f"{len(self.vectors or ())} of its {len(self.documents)} document(s), and no "
                f"embedding client to make the rest.\n"
                f"Pass embeddings= alongside the store, or hand in a store already holding a "
                f"vector for every document."
            )
        if not missing:
            # What made these vectors is unknown here: the store arrived full. A loaded
            # index takes the model its file recorded, and one built with a client records
            # that client when it embeds.
            return
        self._embed_into_store({doc_id: self.documents[doc_id] for doc_id in missing}, None)

    def _not_in_the_store(self, texts: Mapping[str, str]) -> list[str]:
        """Which of these documents the store holds no vector for."""
        store = self.vectors
        if store is None:
            return list(texts)
        held = store.ids() if has_method(store, "ids") else None
        if held is None:
            return [] if len(store) else list(texts)
        known = set(held)
        return [doc_id for doc_id in texts if doc_id not in known]

    def _embed(self, texts: Mapping[str, str], retrieval: Retrieval | None) -> list[list[float]]:
        """One unit-length vector per text, in the order given. Writes nothing.

        ``retrieval`` is the handle, where there is one. Without it the call is made on the
        client directly, which is what construction does and what a build script does. Inside
        a running pipeline the handle is what makes the call recorded and replayable.
        """
        self._check_query_model(embedding="documents")
        wanted = list(texts.values())
        if retrieval is not None:
            # The handle normalises what the backend returned, the same as the branch below.
            return retrieval.embed(self.embeddings, wanted)
        response = self.embeddings.embed(wanted)
        response.check_against(wanted)
        return [normalise(v) for v in response.vectors]

    def _embed_into_store(self, texts: Mapping[str, str], retrieval: Retrieval | None) -> None:
        """Embed these documents and write them to the store."""
        assert self.vectors is not None
        self.vectors.add(list(texts), self._embed(texts, retrieval))
        if self.embedded_by is None:
            self.embedded_by = self.embeddings.identity()

    # -- growing ----------------------------------------------------------------------

    def add(self, texts: Mapping[str, str], *, retrieval: Retrieval | None = None) -> DocumentIndex:
        """Add documents to the corpus. Only these are embedded. Returns the index.

        The words go into the postings and the vectors into the store, so a corpus that gains
        a document a day is never rebuilt::

            index.add({"a3": "The Ashford depot closes at 4pm."})
            index.add(new_documents, retrieval=handle)     # inside a running pipeline

        ``retrieval`` is the handle a tool asks the library for. **An add made inside a run
        without it embeds outside every instrument**: the call is charged to no budget,
        recorded in no trajectory, and made again on every replay. An add made from a build
        script, before any run, needs none.

        An identifier the index already holds is refused, because two documents under one name
        would leave the postings holding both. Use :meth:`replace` to change one.
        """
        self._grow(dict(texts), retrieval, replacing=False)
        return self

    def replace(
        self, texts: Mapping[str, str], *, retrieval: Retrieval | None = None
    ) -> DocumentIndex:
        """Change what documents say. Only these are re-embedded. Returns the index.

        The old words come out of the postings and the old vectors out of the store::

            index.replace({"a3": "The Ashford depot closes at 5pm."})

        ``retrieval`` is the handle, and means here what it means on :meth:`add`. An
        identifier the index does not hold is refused, naming :meth:`add`.
        """
        self._grow(dict(texts), retrieval, replacing=True)
        return self

    def remove(self, doc_ids: Iterable[str]) -> DocumentIndex:
        """Drop documents from the corpus. Returns the index.

        The words leave the postings and the vectors leave the store::

            index.remove(["a3"])

        An identifier the index does not hold is refused, and so is removing every document,
        because an index with nothing in it answers every search the same way a corpus that
        does not contain the answer does. A store that declares no ``remove`` is refused too.

        An approximate :class:`~simple_agents.builtins.FaissVectors` cannot delete, so it
        warns here and filters the document out of every later search until its ``rebuild()``
        is called.
        """
        with self._lock:
            wanted = list(dict.fromkeys(doc_ids))
            unknown = sorted(doc_id for doc_id in wanted if doc_id not in self.documents)
            if unknown:
                raise ConfigurationError(
                    f"DocumentIndex.remove was given {len(unknown)} identifier(s) the index "
                    f"does not hold: {', '.join(unknown[:5])}"
                    f"{f' and {len(unknown) - 5} more' if len(unknown) > 5 else ''}."
                )
            if len(wanted) == len(self.documents):
                raise ConfigurationError(
                    "DocumentIndex.remove was given every document the index holds. An index "
                    "with no documents returns nothing to every search, and the agent has no "
                    "way to tell that from a corpus that does not contain the answer.\n"
                    "Keep at least one document, or build a new index when the corpus is "
                    "next filled."
                )
            if self.vectors is not None and len(self.vectors):
                self._require_removable_store()
                self.vectors.remove(wanted)  # type: ignore[attr-defined]
            for doc_id in wanted:
                self._unindex_words(doc_id)
                del self.documents[doc_id]
            self._set_average_length()
        return self

    def _grow(
        self, texts: Mapping[str, str], retrieval: Retrieval | None, *, replacing: bool
    ) -> None:
        """Embed these documents, then write them in. What :meth:`add` and :meth:`replace` do.

        **The embedding call is made with the lock released**, so a search on another thread
        waits for the bookkeeping and not for the model. The refusal is checked on both sides
        of the call, because another thread can write the same identifier while it is in
        flight.
        """
        if not texts:
            return
        with self._lock:
            self._refuse_a_conflict(texts, replacing=replacing)
        vectors = self._vectors_for(texts, retrieval, replacing=replacing)
        with self._lock:
            self._refuse_a_conflict(texts, replacing=replacing)
            self._write(texts, vectors, replacing=replacing)

    def _refuse_a_conflict(self, texts: Mapping[str, str], *, replacing: bool) -> None:
        """Refuse an add over an identifier held, or a replace of one that is not."""
        if replacing:
            unknown = sorted(doc_id for doc_id in texts if doc_id not in self.documents)
            if unknown:
                raise ConfigurationError(
                    f"DocumentIndex.replace was given {len(unknown)} identifier(s) the index "
                    f"does not hold: {', '.join(unknown[:5])}"
                    f"{f' and {len(unknown) - 5} more' if len(unknown) > 5 else ''}.\n"
                    f"Use index.add({{...}}) for a document the corpus does not have yet."
                )
            return
        held = sorted(doc_id for doc_id in texts if doc_id in self.documents)
        if held:
            raise ConfigurationError(
                f"DocumentIndex.add was given {len(held)} identifier(s) the index already "
                f"holds: {', '.join(held[:5])}"
                f"{f' and {len(held) - 5} more' if len(held) > 5 else ''}.\n"
                f"Use index.replace({{...}}) to change what a document says, or add them "
                f"under identifiers the index does not hold."
            )

    def _write(
        self,
        texts: Mapping[str, str],
        vectors: list[list[float]] | None,
        *,
        replacing: bool,
    ) -> None:
        """Put these documents into the postings and their vectors into the store."""
        if replacing:
            if self.vectors is not None and len(self.vectors):
                # Checked again here as well as before the embedding call: the store can have
                # been filled by another thread while that call was in flight.
                self._require_removable_store()
                self.vectors.remove(list(texts))  # type: ignore[attr-defined]
            for doc_id in texts:
                self._unindex_words(doc_id)
        for doc_id, text in texts.items():
            self.documents[doc_id] = text
            self._index_words(doc_id, text)
        self._set_average_length()
        if vectors is not None:
            assert self.vectors is not None
            self.vectors.add(list(texts), vectors)
            if self.embedded_by is None:
                self.embedded_by = self.embeddings.identity()

    def _vectors_for(
        self, texts: Mapping[str, str], retrieval: Retrieval | None, *, replacing: bool
    ) -> list[list[float]] | None:
        """The vectors a write needs, or ``None`` where the index searches words alone.

        **Everything that can fail on something outside this process happens here**, before
        the corpus is touched: the embedding call, and the two refusals that depend on the
        store. A call that failed after the words were written would leave the corpus holding
        documents no vector search can reach.
        """
        assert self.ranking is not None
        holding = self.vectors is not None and len(self.vectors)
        if replacing and holding:
            self._require_removable_store()
        if not self.ranking.needs_vectors:
            return None
        if self.embeddings is None:
            raise ConfigurationError(
                "This index searches by vector and holds no embedding client, so a "
                "document added to it cannot be embedded.\n"
                "Pass embeddings= when building or loading it: DocumentIndex.load("
                "'corpus.index', embeddings=embedder, ranking=Semantic())."
            )
        return self._embed(texts, retrieval)

    def _require_removable_store(self) -> None:
        if not has_method(self.vectors, "remove"):
            raise ConfigurationError(
                f"The vector store on this index, {type(self.vectors).__name__}, declares no "
                f"remove(ids), so a document cannot be taken out of it and one left behind "
                f"would keep being returned by searches.\n"
                f"Add `def remove(self, ids: Sequence[str]) -> None` to it, or use "
                f"vectors=NumpyVectors(), VectorScan() or FaissVectors(), which all have one."
            )

    @classmethod
    def from_texts(
        cls,
        texts: Mapping[str, str],
        *,
        stopwords: Iterable[str] | None = None,
        embeddings: Any = None,
        ranking: Ranking | None = None,
        rerank: Reranker | None = None,
        vectors: VectorStore | None = None,
    ) -> DocumentIndex:
        """An index over documents already in memory, keyed by identifier."""
        return cls(
            documents=dict(texts),
            stopwords=None if stopwords is None else frozenset(stopwords),
            embeddings=embeddings,
            ranking=ranking,
            rerank=rerank,
            vectors=vectors,
        )

    @classmethod
    def from_directory(
        cls,
        path: str | Path,
        *,
        glob: str = "*.txt",
        stopwords: Iterable[str] | None = None,
        embeddings: Any = None,
        ranking: Ranking | None = None,
        rerank: Reranker | None = None,
        vectors: VectorStore | None = None,
    ) -> DocumentIndex:
        """An index over files in a directory. The file name is the document identifier."""
        root = Path(path)
        if not root.is_dir():
            raise ConfigurationError(
                f"No directory at {root}. DocumentIndex.from_directory reads the corpus from "
                f"disk, so the path has to exist before the pipeline runs. Pass the directory "
                f"holding the documents, or DocumentIndex.from_texts({{...}}) to supply them "
                f"in memory."
            )
        found = sorted(root.glob(glob))
        if not found:
            raise ConfigurationError(
                f"No files matching {glob!r} in {root}. Pass the glob the corpus uses, such "
                f"as glob='*.md'."
            )
        return cls(
            documents={p.name: p.read_text(encoding="utf-8") for p in found},
            stopwords=None if stopwords is None else frozenset(stopwords),
            embeddings=embeddings,
            ranking=ranking,
            rerank=rerank,
            vectors=vectors,
        )

    # -- persistence ------------------------------------------------------------------

    def save(self, path: str | Path) -> Path:
        """Write the documents and their vectors. Returns the path of the JSON file.

        Embedding a corpus is the expensive part of building an index, so a corpus is embedded
        once and loaded thereafter::

            index = DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic())
            index.save("corpus.index")

        **Two files are written**: ``corpus.index`` holds the documents and what they were
        embedded with, and ``corpus.index.vec`` holds the vectors as raw ``float32``. A
        million 768-dimension vectors are 3 GB, which does not fit in a JSON string.
        :meth:`load` reads the pair, and moving an index means moving both.

        The file records which model produced the vectors and how the text was cut into words.
        Loading it under a different one of either is refused rather than answered.
        """
        # Held for the write. The identifiers and the vectors are read from the store as two
        # calls, so an `add` landing between them would write a file whose counts disagree.
        with self._lock:
            return write_index(self, path)

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        embeddings: Any = None,
        ranking: Ranking | None = None,
        rerank: Reranker | None = None,
        vectors: VectorStore | None = None,
    ) -> DocumentIndex:
        """Read back an index written by :meth:`save`.

        ``embeddings`` is the client the queries will be embedded with. It is checked against
        the model that embedded the file and a mismatch is refused. ``ranking`` is required
        alongside it, the same as when the index was built::

            index = DocumentIndex.load("corpus.index", embeddings=embedder,
                                       ranking=Hybrid(fuse=RRF(k=5)))

        ``vectors`` is which store the vectors are read into, and defaults to the same one a
        new index builds. A corpus large enough to want a different one says so here::

            DocumentIndex.load("corpus.index", embeddings=embedder, ranking=Semantic(),
                               vectors=FaissVectors(device="cuda"))

        The stopword list the file was saved with is restored with it. Files written by
        version ``1.0``, which packed the vectors into the JSON, are read as well.
        """
        parts = read_index(path, embeddings=embeddings)
        store = vectors
        if parts["vectors"] is not None:
            order, held = parts["vectors"]
            if store is None:
                store = default_store()
            store.add(order, held)
        index = cls(
            documents=parts["documents"],
            stopwords=parts["stopwords"],
            embeddings=embeddings,
            ranking=ranking,
            rerank=rerank,
            vectors=store,
        )
        # After construction, which is where a store handed in empty is filled: an index whose
        # file carried no vectors embeds its corpus there and records what embedded it, and
        # setting the file's `null` over that would leave the two-models refusal switched off.
        if parts["embedded_by"] is not None:
            index.embedded_by = parts["embedded_by"]
        return index

    # -- searching --------------------------------------------------------------------

    def query_terms(self, query: str) -> list[str]:
        """The words a query is searched on: its tokens, less any stopword.

        All of them where every word is a stopword::

            index.query_terms("What is the inseam?")   # ['inseam'], with those three declared
        """
        terms = tokens(query)
        kept = [term for term in terms if term not in self.stopwords]
        return kept or terms

    def documents_containing(self, query: str) -> dict[str, int]:
        """How many documents hold each word the query is searched on, keyed by the word.

        A count of zero means the index cannot match that word. It says nothing about whether
        the collection covers the subject, which may be there under another word::

            index.documents_containing("Ashford inseam")   # {"ashford": 3, "inseam": 0}
        """
        with self._lock:
            return {term: len(self._postings.get(term, {})) for term in self.query_terms(query)}

    def lexical_scores(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """The best BM25 matches as ``(doc_id, score)``, highest first."""
        terms = self.query_terms(query)
        if not terms:
            return []
        scores: dict[str, float] = {}
        # Held for the scoring, which reads the postings, the lengths and the mean together.
        # A document added on another thread lands either wholly inside this pass or wholly
        # after it, so no query is scored against a length the postings do not match.
        with self._lock:
            total_docs = len(self.documents)
            for term in terms:
                postings = self._postings.get(term)
                if not postings:
                    continue
                idf = math.log(1 + (total_docs - len(postings) + 0.5) / (len(postings) + 0.5))
                for doc_id, count in postings.items():
                    length = self._lengths[doc_id]
                    norm = K1 * (1 - B + B * length / self._average_length)
                    scores[doc_id] = scores.get(doc_id, 0.0) + idf * count * (K1 + 1) / (
                        count + norm
                    )
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ranked[:top_k]

    def semantic_scores(self, query_vector: Sequence[float], top_k: int) -> list[tuple[str, float]]:
        """The nearest documents to a query vector as ``(doc_id, score)``, highest first."""
        if self.vectors is None:
            return []
        return self.vectors.search(list(query_vector), top_k)

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        retrieval: Retrieval | None = None,
        model: Any = None,
    ) -> list[Hit]:
        """The best-matching documents, highest score first. Empty when nothing matches.

        ``retrieval`` is the handle the library fills on a tool that asks for one, and is what
        makes the embedding and reranking calls recorded and replayable. An index whose ranking
        needs vectors and is searched without one is refused, since the call would be made
        outside every instrument::

            index.search("length preference", top_k=3, retrieval=handle)

        ``model`` is a :class:`~simple_agents.ModelHandle`, needed only where the index
        reranks with :class:`~simple_agents.builtins.ModelRerank`. A purely lexical index needs
        neither and is searched with the query alone.
        """
        assert self.ranking is not None
        depth = max(top_k, getattr(self.ranking, "depth", top_k))
        if self.rerank is not None:
            depth = max(depth, self.rerank.top_n)
        lexical: list[tuple[str, float]] = []
        semantic: list[tuple[str, float]] = []
        if self.ranking.needs_lexical:
            lexical = self.lexical_scores(query, depth)
        if self.ranking.needs_vectors:
            vector = self._embed_query(query, retrieval)
            semantic = self.semantic_scores(vector, depth)

        if self.rerank is None:
            candidates = self._merge(lexical, semantic, top_k)
        else:
            pool = self._merge(lexical, semantic, self.rerank.top_n)
            candidates = self._reranked(query, pool, top_k, retrieval, model)
        with self._lock:
            return [
                Hit(
                    doc_id=doc_id,
                    score=score,
                    text=self.documents.get(doc_id, ""),
                    retriever=retriever,
                    rank=position + 1,
                )
                for position, (doc_id, score, retriever) in enumerate(candidates)
            ]

    def _embed_query(self, query: str, retrieval: Retrieval | None) -> list[float]:
        if self.embeddings is None:
            raise ConfigurationError(
                "This index searches by vector and holds no embedding client, so the query "
                "cannot be embedded.\n"
                "Pass embeddings= when building or loading it: DocumentIndex.load("
                "'corpus.index', embeddings=embedder)."
            )
        if retrieval is None:
            raise ConfigurationError(
                "DocumentIndex.search was called without a Retrieval handle on an index that "
                "searches by vector. Embedding the query is a model call, and one made outside "
                "the handle is charged to no budget, recorded in no trajectory, and made again "
                "on every replay and every rollout of an evaluation.\n"
                "Reach this index through document_search(index), which the library fills the "
                "handle for. A tool written by hand asks for it in its signature: "
                "`def find(retrieval: Retrieval, query: str)`."
            )
        self._check_query_model()
        return retrieval.embed(self.embeddings, [query])[0]

    def _check_query_model(self, *, embedding: str = "query") -> None:
        """Refuse where this index's vectors and this client's are from two models."""
        if self.embedded_by is None:
            return
        refuse_mismatch(
            self.embedded_by, self.embeddings.identity(), "this index", embedding=embedding
        )

    def _merge(
        self,
        lexical: Sequence[tuple[str, float]],
        semantic: Sequence[tuple[str, float]],
        top_k: int,
    ) -> list[tuple[str, float, str]]:
        """The fused order, each document carrying the score of whichever list ranked it best.

        A document both lists returned is attributed to the one that placed it higher, because
        that is the retriever whose judgement put it here. The score is that retriever's own.
        """
        assert self.ranking is not None
        if not self.ranking.needs_vectors:
            return [(doc_id, score, "lexical") for doc_id, score in lexical[:top_k]]
        if not self.ranking.needs_lexical:
            return [(doc_id, score, "semantic") for doc_id, score in semantic[:top_k]]
        lex = {doc_id: (rank, score) for rank, (doc_id, score) in enumerate(lexical)}
        sem = {doc_id: (rank, score) for rank, (doc_id, score) in enumerate(semantic)}
        merged = []
        for doc_id in self.ranking.fuse.combine(lexical, semantic, top_k):
            in_lex, in_sem = lex.get(doc_id), sem.get(doc_id)
            if in_lex is not None and (in_sem is None or in_lex[0] <= in_sem[0]):
                merged.append((doc_id, in_lex[1], "lexical"))
            elif in_sem is not None:
                merged.append((doc_id, in_sem[1], "semantic"))
        return merged

    def _reranked(
        self,
        query: str,
        pool: Sequence[tuple[str, float, str]],
        top_k: int,
        retrieval: Retrieval | None,
        model: Any,
    ) -> list[tuple[str, float, str]]:
        """The candidates reordered by the reranker, carrying its scores."""
        assert self.rerank is not None
        if not pool:
            return []
        ids = [doc_id for doc_id, _, _ in pool]
        with self._lock:
            texts = [self.documents.get(doc_id, "") for doc_id in ids]
        if isinstance(self.rerank, ModelRerank):
            if model is None:
                raise ConfigurationError(
                    "This index reranks with ModelRerank, which asks the run's chat model, and "
                    "no ModelHandle reached the search. The call would be charged to no budget "
                    "and recorded in no trajectory.\n"
                    "Reach this index through document_search(index), which the library fills "
                    "both handles for."
                )
            reply = model.complete(self.rerank.prompt_for(query, texts), max_output_tokens=256)
            order = self.rerank.order_from(reply.content or "", len(texts))
            return [
                (ids[i], float(len(order) - position), "rerank")
                for position, i in enumerate(order[:top_k])
            ]
        if retrieval is None:
            raise ConfigurationError(
                "DocumentIndex.search was called without a Retrieval handle on an index that "
                "reranks. A rerank is a model call, and one made outside the handle is charged "
                "to no budget and recorded in no trajectory.\n"
                "Reach this index through document_search(index), or ask for the handle in a "
                "hand-written tool's signature."
            )
        scored = retrieval.rerank(self.rerank.client, query, texts)
        return [(ids[s.index], s.score, "rerank") for s in scored[:top_k]]

    def to_record(self) -> dict[str, Any]:
        """What a run records about how this index searches.

        The ranking, the fusion and its settings, the reranker, the store the vectors are in
        and whether it is exact, the analyzer, and the model that embedded the corpus::

            index.to_record()["store"]     # 'NumpyVectors'

        This reaches the manifest and the results file on the entry for the tool that searches
        the index, so a figure measured against an approximate store is told apart from one
        measured against an exact scan rather than compared with it.

        **How many documents the index holds is not part of it.** The tool entry is part of
        `Pipeline.behaviour_fingerprint`, which a project writes beside every stored result to
        tell a current one from a stale one, and a corpus that gains a document has not
        changed how the pipeline behaves. The count is recorded on the manifest itself, under
        `retrieval`.
        """
        assert self.ranking is not None
        record = ranking_to_record(self.ranking, self.rerank)
        record.update(store_to_record(self.vectors))
        record["analyzer"] = ANALYZER
        record["embedded_by"] = self.embedded_by.to_manifest() if self.embedded_by else None
        return record

    def to_manifest(self) -> dict[str, Any]:
        """What the manifest records about the corpus itself, counted when the run ends.

        How many documents the index holds and which store they are in::

            index.to_manifest()['documents']     # 7308

        Separate from :meth:`to_record` because a run that adds to the corpus changes this and
        changes nothing about how the pipeline behaves.
        """
        # Two counts read together, the same as everywhere else they are read together: a
        # run that is still adding on another thread would otherwise record a corpus size and
        # a vector count from either side of one write.
        with self._lock:
            return {
                "documents": len(self.documents),
                **store_to_record(self.vectors),
                "vectors": len(self.vectors) if self.vectors is not None else 0,
                "embedded_by": self.embedded_by.to_manifest() if self.embedded_by else None,
            }

    def __len__(self) -> int:
        return len(self.documents)


def document_search(
    index: DocumentIndex,
    *,
    name: str = "document_search",
    top_k: int = 5,
    max_chars: int | None = None,
    version: str | None = None,
) -> Tool:
    """A tool that searches ``index`` and returns the matching documents.

    ``top_k`` is the default number of results; the model may ask for fewer. ``max_chars``
    truncates each document, for a corpus whose documents do not fit in a prompt::

        registry.add(document_search(DocumentIndex.from_directory("corpus/")))
        registry.add(document_search(index, top_k=3, max_chars=2_000))

    A query matching nothing returns an empty list rather than raising. Finding nothing is a
    result the model can act on by searching for something else, and recording it as an error
    would put a successful lookup in the record's error field.

    **An index that searches by vector or reranks makes model calls**, so the tool this returns
    asks the library for a handle and is re-run during replay rather than served from the
    cassette. Its embedding and reranking calls are served instead, and appear in the
    trajectory as ``model_call`` records under the tool call. An index that is purely lexical
    takes no handle and is stored as one entry, which is what it has always been.
    """
    default_k = top_k
    limit = max_chars
    assert index.ranking is not None
    needs_retrieval = index.ranking.needs_vectors or isinstance(index.rerank, CrossEncoderRerank)
    needs_chat_model = isinstance(index.rerank, ModelRerank)

    if needs_retrieval or needs_chat_model:
        return _searching_with_a_model(
            index, name, version, default_k, limit, needs_retrieval, needs_chat_model
        )

    @tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version=version)
    def search(query: str, top_k: int = default_k) -> dict[str, Any]:
        """Search the document collection for passages matching a query.

        Matching is lexical, on the words themselves, so use words that would appear in the
        passage rather than the phrasing of a question.

        Returns `results`, the best matches in rank order, each with `doc_id`, `score` and
        `text`, and `documents_containing`, how many documents hold each word of the query.

        Finding nothing means these words did not reach a passage. It does not establish that
        the collection lacks the fact.
        """
        hits = index.search(query, top_k=top_k)
        return {
            "results": [
                {**hit.to_record(), "text": hit.text[:limit] if limit else hit.text} for hit in hits
            ],
            "documents_containing": index.documents_containing(query),
        }

    search.searches = index
    return search


def _searching_with_a_model(
    index: DocumentIndex,
    name: str,
    version: str | None,
    default_k: int,
    limit: int | None,
    needs_retrieval: bool,
    needs_chat_model: bool,
) -> Tool:
    """The ``document_search`` variant for an index whose search makes model calls.

    Separate from the lexical one so that function's source, and therefore the version in every
    existing cassette key, does not move when this one changes.
    ``tests/test_search.py`` pins it.
    """
    described = """Search the document collection for passages matching a query.

        Matching is on meaning as well as on the words, so a question phrased differently from
        the passage still finds it. An exact identifier, such as a part number, is matched on
        the words, so quote it as it is written.

        Returns `results`, the best matches in rank order, each with `doc_id`, `score`,
        `retriever` naming what found it, and `text`; and `documents_containing`, how many
        documents hold each word of the query.

        Scores from different retrievers are not comparable. Finding nothing means the query
        did not reach a passage. It does not establish that the collection lacks the fact.
        """

    if needs_retrieval and needs_chat_model:

        def body(
            retrieval: Retrieval, model: ModelHandle, query: str, top_k: int = default_k
        ) -> dict[str, Any]:
            return _reply(index, query, top_k, limit, retrieval, model)

    elif needs_retrieval:

        def body(  # type: ignore[misc]
            retrieval: Retrieval, query: str, top_k: int = default_k
        ) -> dict[str, Any]:
            return _reply(index, query, top_k, limit, retrieval, None)

    else:

        def body(  # type: ignore[misc]
            model: ModelHandle, query: str, top_k: int = default_k
        ) -> dict[str, Any]:
            return _reply(index, query, top_k, limit, None, model)

    body.__doc__ = described
    body.__name__ = "search"
    built = tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version=version)(body)
    built.searches = index
    return built


def _reply(
    index: DocumentIndex,
    query: str,
    top_k: int,
    limit: int | None,
    retrieval: Retrieval | None,
    model: Any,
) -> dict[str, Any]:
    """One search over an index with more than one retriever, in the shape the model reads back."""
    if not query.strip():
        raise ModelFacingError(
            "The search query is empty. Pass the words or the question to search for.",
            retryable=True,
        )
    hits = index.search(query, top_k=top_k, retrieval=retrieval, model=model)
    return {
        "results": [
            {
                **hit.to_record(attributed=True),
                "text": hit.text[:limit] if limit else hit.text,
            }
            for hit in hits
        ],
        "documents_containing": index.documents_containing(query),
    }
