"""How a search ranks: lexically, by vector, or by combining the two, and what reorders it.

A :class:`~simple_agents.builtins.DocumentIndex` is given one ``ranking`` and at most one
``rerank``. The ranking decides which documents come back and in what order; the reranker
reorders the ones it returned::

    index = DocumentIndex.from_texts(corpus)                        # Lexical(), the only choice
    index = DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Hybrid(fuse=RRF()))
    index = DocumentIndex.from_texts(
        corpus,
        embeddings=embedder,
        ranking=Semantic(),
        rerank=CrossEncoderRerank(reranker, top_n=20),
    )

**No ranking is best on every corpus.** A lexical match finds an identifier a vector search
misses, a vector search finds a paraphrase sharing no words with the document, and which
matters depends on what is in the corpus and how end users ask. An index given ``embeddings``
and no ``ranking`` is refused for that reason, naming the three choices. The figures inside
each of them were chosen by measuring three corpora against two embedding models, and a
project that measures its own corpus should set them from that instead.
"""

from __future__ import annotations

import heapq
import threading
import math
import operator
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from ..embeddings import normalise
from ..errors import ConfigurationError

__all__ = [
    "Fusion",
    "RRF",
    "Interleave",
    "WeightedScore",
    "Ranking",
    "Lexical",
    "Semantic",
    "Hybrid",
    "VectorStore",
    "VectorScan",
    "normalise",
    "refuse_no_ranking",
]

DEFAULT_DEPTH = 50
"""How many results each retriever contributes to a fusion before it combines them."""

DEFAULT_RRF_K = 5
"""The rank discount in :class:`RRF`. See its docstring for where the figure comes from."""


# -- fusion ------------------------------------------------------------------------------


class Fusion(Protocol):
    """How two ranked lists become one.

    ``combine`` is given the lexical results and the semantic results, each as ``(doc_id,
    score)`` best first, and returns the document identifiers in their combined order::

        class MyFusion:
            def combine(self, lexical, semantic, top_k):
                ...
                return [doc_id, ...]

    The two score scales are not comparable: a BM25 score is unbounded and a cosine is in
    ``[-1, 1]``. A fusion that compares them numerically has to normalise first, which
    :class:`WeightedScore` does and :class:`RRF` avoids by using rank alone.
    """

    def combine(
        self,
        lexical: Sequence[tuple[str, float]],
        semantic: Sequence[tuple[str, float]],
        top_k: int,
    ) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class RRF:
    """Reciprocal rank fusion: each list votes by rank, and the votes add up.

    A document at rank ``r`` in a list contributes ``1 / (k + r)``, counting from 1::

        Hybrid(fuse=RRF(k=5))

    **``k`` sets how fast the vote decays with rank, and that decides which of two shapes
    wins**: a document ranked first by one retriever and missing from the other, against one
    ranked mid-list by both. A large ``k`` flattens the discount, so two mid-list votes
    outweigh one first place; a small ``k`` keeps the single first place ahead::

        lexical  = [decisive, ..., mediocre]      # decisive 1st, mediocre 11th
        semantic = [...,           mediocre]      # decisive absent, mediocre 11th

        RRF(k=5).combine(lexical, semantic, 1)     # ['decisive']
        RRF(k=60).combine(lexical, semantic, 1)    # ['mediocre']

    The default of 5 was measured against MS MARCO passage, Natural Questions and a corpus of
    near-identical part numbers, over two embedding models, where it matched or beat ``k=60``
    in every run. The published default for fusing many retrieval systems is 60, and a project
    fusing more than two should expect to raise it.

    Rank alone is used, so no score is normalised and nothing is comparable across the two
    lists. **Documents at the same rank in one list and absent from the other score exactly
    equal**, and that tie is broken by identifier, so a corpus of near-identical documents can
    have its order settled by their names.
    """

    k: int = DEFAULT_RRF_K

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ConfigurationError(
                f"RRF(k={self.k}) needs k of at least 1. k is added to a document's rank "
                f"before the reciprocal is taken, so a k below 1 divides by zero or negates "
                f"the vote.\n"
                f"Pass RRF(k=5) for two retrievers, or RRF(k=60) to match the published "
                f"default for fusing many."
            )

    def combine(
        self,
        lexical: Sequence[tuple[str, float]],
        semantic: Sequence[tuple[str, float]],
        top_k: int,
    ) -> list[str]:
        votes: dict[str, float] = {}
        for ranked in (lexical, semantic):
            for position, (doc_id, _) in enumerate(ranked):
                votes[doc_id] = votes.get(doc_id, 0.0) + 1.0 / (self.k + position + 1)
        order = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
        return [doc_id for doc_id, _ in order[:top_k]]


@dataclass(frozen=True, slots=True)
class Interleave:
    """Take each list's best in turn, skipping anything already taken.

    Nothing is compared across the two lists, so each retriever is guaranteed its top result::

        Hybrid(fuse=Interleave())

    **This trades the rank of the answer for the chance of finding it.** Reserving every second
    slot for the other retriever puts its best guess second whether or not it is any good,
    which lowers where the answer lands on average. Measured against MS MARCO passage and
    Natural Questions it returned the answer in the top five about as often as
    :class:`RRF` and ranked it lower every time. It is the fusion to reach for where one
    retriever is decisive on some queries and useless on others, such as a corpus of part
    numbers searched by both number and description.
    """

    def combine(
        self,
        lexical: Sequence[tuple[str, float]],
        semantic: Sequence[tuple[str, float]],
        top_k: int,
    ) -> list[str]:
        taken: list[str] = []
        seen: set[str] = set()
        for position in range(max(len(lexical), len(semantic))):
            for ranked in (lexical, semantic):
                if len(taken) >= top_k:
                    return taken
                if position < len(ranked) and ranked[position][0] not in seen:
                    seen.add(ranked[position][0])
                    taken.append(ranked[position][0])
        return taken


@dataclass(frozen=True, slots=True)
class WeightedScore:
    """Scale each list's scores to ``[0, 1]`` by its own best, then add them with weights.

    ``lexical`` is the weight on the lexical score and the semantic weight is ``1 - lexical``::

        Hybrid(fuse=WeightedScore(lexical=0.3))

    The scaling happens per query, so the top hit in each list scores 1.0 whether it matched
    the query closely or barely at all. A weight sets how much a list's ordering counts, and
    carries no information about how strong that list's matches were.
    """

    lexical: float = 0.5

    def __post_init__(self) -> None:
        if not 0.0 <= self.lexical <= 1.0:
            raise ConfigurationError(
                f"WeightedScore(lexical={self.lexical}) takes a weight between 0 and 1. The "
                f"semantic weight is 1 - lexical, so a value outside that range makes one of "
                f"the two negative.\n"
                f"Pass WeightedScore(lexical=0.5) to weight them equally, or use Lexical() or "
                f"Semantic() to use one alone."
            )

    def combine(
        self,
        lexical: Sequence[tuple[str, float]],
        semantic: Sequence[tuple[str, float]],
        top_k: int,
    ) -> list[str]:
        totals: dict[str, float] = {}
        for ranked, weight in ((lexical, self.lexical), (semantic, 1.0 - self.lexical)):
            if not ranked:
                continue
            best = max(abs(score) for _, score in ranked) or 1.0
            for doc_id, score in ranked:
                totals[doc_id] = totals.get(doc_id, 0.0) + weight * (score / best)
        order = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        return [doc_id for doc_id, _ in order[:top_k]]


# -- ranking -----------------------------------------------------------------------------


class Ranking(Protocol):
    """Which retrievers a search runs, and how their results are combined.

    Implemented by :class:`Lexical`, :class:`Semantic` and :class:`Hybrid`. A project does not
    implement this: a new way of combining two lists is a :class:`Fusion`, which is the smaller
    surface.
    """

    @property
    def needs_vectors(self) -> bool: ...

    @property
    def needs_lexical(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class Lexical:
    """Match on the words themselves, with BM25. The default, and what needs no model.

    A query sharing no words with a document does not find it::

        DocumentIndex.from_texts(corpus)                       # Lexical() by default
        DocumentIndex.from_texts(corpus, ranking=Lexical())    # the same, said out loud
    """

    @property
    def needs_vectors(self) -> bool:
        return False

    @property
    def needs_lexical(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class Semantic:
    """Match on meaning, by comparing the query's vector against each document's.

    Requires an embedding client on the index::

        DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic())

    An exact identifier is what this misses: a part number is split into pieces the model has
    no meaning for, so a corpus holding identifiers is usually searched with :class:`Hybrid`.
    """

    @property
    def needs_vectors(self) -> bool:
        return True

    @property
    def needs_lexical(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Hybrid:
    """Run both retrievers and combine them. The default once an index has embeddings.

    ``depth`` is how many results each retriever contributes before ``fuse`` combines them; it
    is not how many come back, which is the search's ``top_k``::

        DocumentIndex.from_texts(corpus, embeddings=embedder)   # Hybrid(fuse=RRF(k=5))
        DocumentIndex.from_texts(corpus, embeddings=embedder,
                                 ranking=Hybrid(fuse=Interleave(), depth=100))

    **Hybrid is not always better than one of its parts.** Where the embedding model suits the
    corpus, fusing a weaker lexical list into it can rank the answer lower than the vector
    search alone did. Measured on MS MARCO passage with a strong embedding model, semantic
    alone returned the answer in the top five 95.5% of the time against 91.0% for the same
    search fused with BM25. This is worth measuring on the project's own corpus rather than
    assumed either way.
    """

    fuse: Fusion = RRF()
    depth: int = DEFAULT_DEPTH

    def __post_init__(self) -> None:
        if self.depth < 1:
            raise ConfigurationError(
                f"Hybrid(depth={self.depth}) needs a depth of at least 1. depth is how many "
                f"results each retriever contributes to the fusion, so nothing is combined "
                f"below 1.\n"
                f"Pass Hybrid(depth=50), or raise it where the answer is being missed by both "
                f"lists before they are combined."
            )

    @property
    def needs_vectors(self) -> bool:
        return True

    @property
    def needs_lexical(self) -> bool:
        return True


# -- vectors -----------------------------------------------------------------------------


class VectorStore(Protocol):
    """Where an index keeps its vectors and how it finds the nearest.

    The library ships :class:`VectorScan`, which holds them in memory and compares against
    every one. A project with a corpus too large for that points ``vectors=`` at its own store
    over whatever it already runs::

        class MyStore:
            def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
                ...

            def search(self, vector: Sequence[float], top_k: int) -> list[tuple[str, float]]:
                ...

            def __len__(self) -> int:
                ...

    ``search`` returns ``(doc_id, score)`` best first, where a higher score is more similar.
    Vectors reaching ``add`` are already normalised to unit length, so a dot product is the
    cosine. A store that returns approximate neighbours returns fewer true matches than
    :class:`VectorScan` for the same ``top_k``, and the project owns that trade.
    """

    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None: ...

    def search(self, vector: Sequence[float], top_k: int) -> list[tuple[str, float]]: ...

    def __len__(self) -> int: ...


class VectorScan:
    """Vectors in memory, compared against every one. The default, and it needs no dependency.

    Results are exact: there is no approximation and no parameter trading recall for speed::

        store = VectorScan()
        store.add(["a1"], [[0.1, -0.3, 0.2]])
        store.search([0.1, -0.3, 0.2], top_k=1)     # [('a1', 1.0)]

    **What it costs, measured on one CPU core**: a corpus of 10,000 documents at 768 dimensions
    holds 31 MB and answers a query in about 64 ms on Python 3.12, or 146 ms on 3.11, where the
    faster arithmetic is unavailable. 100,000 documents holds 307 MB and takes about 620 ms.
    A project past that supplies its own :class:`VectorStore`.
    """

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._vectors: list[list[float]] = []
        # The identifiers and the vectors are one table kept in two lists, so a writer holds
        # both while it appends and a reader holds both while it scores. Without it two adds
        # at once file a vector under another document's identifier, which is the same fault
        # the length check below refuses.
        self._lock = threading.Lock()

    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        """Add vectors under their identifiers. Both sequences are paired by position."""
        if len(ids) != len(vectors):
            raise ConfigurationError(
                f"VectorScan.add was given {len(ids)} identifier(s) and {len(vectors)} "
                f"vector(s). They are paired by position, so a mismatch would file a vector "
                f"under another document's identifier."
            )
        added = [[float(x) for x in vector] for vector in vectors]
        with self._lock:
            self._ids.extend(ids)
            self._vectors.extend(added)

    def search(self, vector: Sequence[float], top_k: int) -> list[tuple[str, float]]:
        """The nearest vectors by dot product, best first. Empty where nothing was added."""
        if top_k < 1:
            return []
        query = list(vector)
        with self._lock:
            ids = list(self._ids)
            candidates = list(self._vectors)
        if not candidates:
            return []
        scores = [_dot(candidate, query) for candidate in candidates]
        best = heapq.nlargest(
            min(top_k, len(scores)), range(len(scores)), key=lambda i: (scores[i], ids[i])
        )
        return [(ids[i], scores[i]) for i in best]

    def ids(self) -> list[str]:
        """Every identifier held, in the order it was added."""
        return list(self._ids)

    def all_vectors(self) -> list[list[float]]:
        """Every vector held, in the order it was added."""
        return [list(v) for v in self._vectors]

    @property
    def dimensions(self) -> int | None:
        """How wide the vectors are, or ``None`` where none was added."""
        return len(self._vectors[0]) if self._vectors else None

    def __len__(self) -> int:
        return len(self._ids)


if hasattr(math, "sumprod"):  # Python 3.12 and later.

    def _dot(left: Sequence[float], right: Sequence[float]) -> float:
        return math.sumprod(left, right)

else:  # pragma: no cover - exercised on Python 3.11 only.

    def _dot(left: Sequence[float], right: Sequence[float]) -> float:
        return sum(map(operator.mul, left, right))


def ranking_to_record(ranking: Ranking, rerank: Any | None) -> dict[str, Any]:
    """How the manifest records what an index was searched with.

    Names the ranking, the fusion where there is one, and the reranker's model where one is
    declared, so a result that cannot be reproduced can be read back to what produced it.
    """
    record: dict[str, Any] = {"ranking": type(ranking).__name__}
    fuse = getattr(ranking, "fuse", None)
    if fuse is not None:
        record["fusion"] = type(fuse).__name__
        record["fusion_settings"] = {
            name: getattr(fuse, name)
            for name in getattr(fuse, "__slots__", ())
            if not name.startswith("_")
        }
        record["depth"] = getattr(ranking, "depth", None)
    record["rerank"] = None if rerank is None else type(rerank).__name__
    return record


def refuse_no_ranking(what: str) -> str:
    """The refusal for an index given an embedding client and no ranking.

    ``what`` names the thing being built, so the message points at the call to edit::

        raise ConfigurationError(refuse_no_ranking("DocumentIndex"))
    """
    return (
        f"{what} was given embeddings= and no ranking=. An index that can embed can rank three "
        f"ways, and which one is right depends on the queries:\n"
        f"    ranking=Lexical()                                  word overlap only\n"
        f"    ranking=Semantic()                                 meaning only\n"
        f"    ranking=Hybrid(fuse=RRF(k=5))                      both, combined by rank position\n"
        f"    ranking=Hybrid(fuse=WeightedScore(lexical=0.3))    both, combined by score"
    )
