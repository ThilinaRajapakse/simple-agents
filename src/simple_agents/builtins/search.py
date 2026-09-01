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
"""

from __future__ import annotations

import base64
import json
import math
import re
from array import array
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..embeddings import normalise
from ..errors import ConfigurationError, ModelFacingError
from ..models import ModelIdentity
from ..tools import ModelHandle, Retrieval, SideEffectClass, Tool, tool
from .ranking import (
    Lexical,
    Ranking,
    VectorScan,
    VectorStore,
    ranking_to_record,
    refuse_no_ranking,
)
from .rerank import CrossEncoderRerank, ModelRerank, Reranker

__all__ = ["DocumentIndex", "ENGLISH_STOPWORDS", "Hit", "document_search", "tokens"]

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

INDEX_FORMAT_VERSION = "1.0"
"""What :meth:`DocumentIndex.save` writes and :meth:`DocumentIndex.load` reads."""

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

    The identifier is what a search result names and what an answer cites. A title or heading
    is indexed by writing it into the text::

        DocumentIndex.from_texts({d["doc_id"]: f"{d['title']} {d['text']}" for d in docs})

    ``stopwords`` are dropped from a query before searching and default to
    :data:`ENGLISH_STOPWORDS`. They reach the query and not the documents, so a word listed
    here is still findable in a passage, and a query of nothing but stopwords is searched as
    written::

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
    :class:`~simple_agents.builtins.ranking.Lexical`, which is what it can do with the words
    alone. ``rerank`` defaults to nothing. ``vectors`` is where the vectors live and defaults
    to :class:`~simple_agents.builtins.ranking.VectorScan`.
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
            counts = Counter(tokens(text))
            self._lengths[doc_id] = sum(counts.values())
            for term, count in counts.items():
                self._postings.setdefault(term, {})[doc_id] = count
        total = sum(self._lengths.values())
        self._average_length = total / len(self._lengths) if self._lengths else 0.0
        if self.ranking.needs_vectors and self.vectors is None:
            self._build_vectors()

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
        """Embed every document once, at construction."""
        store = VectorScan()
        keys = list(self.documents)
        response = self.embeddings.embed([self.documents[k] for k in keys])
        response.check_against(keys)
        store.add(keys, [normalise(v) for v in response.vectors])
        self.vectors = store
        self.embedded_by = self.embeddings.identity()

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
        """Write the documents and their vectors to one file. Returns the path written.

        Embedding a corpus is the expensive part of building an index, so a corpus that does
        not change is embedded once and loaded thereafter::

            DocumentIndex.from_texts(corpus, embeddings=embedder).save("corpus.index")

        The file records which model produced the vectors. Loading it under a different one is
        refused rather than answered, because vectors from two models are not comparable.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        packed = None
        if self.vectors is not None and isinstance(self.vectors, VectorScan):
            packed = base64.b64encode(
                b"".join(array("f", v).tobytes() for v in self.vectors.all_vectors())
            ).decode("ascii")
        target.write_text(
            json.dumps(
                {
                    "format_version": INDEX_FORMAT_VERSION,
                    "documents": self.documents,
                    "stopwords": sorted(self.stopwords),
                    "embedded_by": (self.embedded_by.to_manifest() if self.embedded_by else None),
                    "order": self.vectors.ids() if isinstance(self.vectors, VectorScan) else [],
                    "dimensions": (
                        self.vectors.dimensions if isinstance(self.vectors, VectorScan) else None
                    ),
                    "vectors": packed,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return target

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        embeddings: Any = None,
        ranking: Ranking | None = None,
        rerank: Reranker | None = None,
    ) -> DocumentIndex:
        """Read back an index written by :meth:`save`.

        ``embeddings`` is the client the queries will be embedded with. It is checked against
        the model that embedded the file and a mismatch is refused. ``ranking`` is required
        alongside it, the same as when the index was built::

            index = DocumentIndex.load("corpus.index", embeddings=embedder,
                                       ranking=Hybrid(fuse=RRF(k=5)))

        The stopword list the file was saved with is restored with it.
        """
        source = Path(path)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConfigurationError(
                f"Could not read a saved index at {source}: {exc}.\n"
                f"Rebuild it with DocumentIndex.from_texts(corpus, embeddings=...).save("
                f"{str(source)!r})."
            ) from exc
        stored = raw.get("embedded_by")
        identity = ModelIdentity(**stored) if stored else None
        if identity is not None and embeddings is not None:
            _refuse_mismatch(identity, embeddings.identity(), str(source))
        store = None
        if raw.get("vectors") and raw.get("order"):
            store = VectorScan()
            width = int(raw["dimensions"])
            flat = array("f")
            flat.frombytes(base64.b64decode(raw["vectors"]))
            order = list(raw["order"])
            store.add(
                order,
                [list(flat[i * width : (i + 1) * width]) for i in range(len(order))],
            )
        index = cls(
            documents=dict(raw.get("documents") or {}),
            stopwords=frozenset(raw.get("stopwords") or ()),
            embeddings=embeddings,
            ranking=ranking,
            rerank=rerank,
            vectors=store,
        )
        index.embedded_by = identity
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
        return {term: len(self._postings.get(term, {})) for term in self.query_terms(query)}

    def lexical_scores(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """The best BM25 matches as ``(doc_id, score)``, highest first."""
        terms = self.query_terms(query)
        if not terms:
            return []
        total_docs = len(self.documents)
        scores: dict[str, float] = {}
        for term in terms:
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = math.log(1 + (total_docs - len(postings) + 0.5) / (len(postings) + 0.5))
            for doc_id, count in postings.items():
                length = self._lengths[doc_id]
                norm = K1 * (1 - B + B * length / self._average_length)
                scores[doc_id] = scores.get(doc_id, 0.0) + idf * count * (K1 + 1) / (count + norm)
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

    def _check_query_model(self) -> None:
        if self.embedded_by is None:
            return
        _refuse_mismatch(self.embedded_by, self.embeddings.identity(), "this index")

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
        """How the manifest records what this index searches with."""
        assert self.ranking is not None
        record = ranking_to_record(self.ranking, self.rerank)
        record["documents"] = len(self.documents)
        record["embedded_by"] = self.embedded_by.to_manifest() if self.embedded_by else None
        return record

    def __len__(self) -> int:
        return len(self.documents)


def _refuse_mismatch(stored: ModelIdentity, asked: ModelIdentity, where: str) -> None:
    """Refuse a query embedded by a different model than the corpus was."""
    if (stored.backend, stored.request_model) == (asked.backend, asked.request_model) and (
        stored.model_revision == asked.model_revision
        or stored.model_revision is None
        or asked.model_revision is None
    ):
        return
    raise ConfigurationError(
        f"The vectors in {where} were made by {stored.request_model!r}"
        f"{f'@{stored.model_revision}' if stored.model_revision else ''} and the query would "
        f"be embedded by {asked.request_model!r}"
        f"{f'@{asked.model_revision}' if asked.model_revision else ''}. Vectors from two "
        f"models occupy different spaces, so comparing them returns confident nonsense with "
        f"nothing raised.\n"
        f"Use the model the corpus was embedded with, or re-embed the corpus with the new one "
        f"and save it again: DocumentIndex.from_texts(corpus, embeddings=new).save(path)."
    )


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
    return tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version=version)(body)


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
