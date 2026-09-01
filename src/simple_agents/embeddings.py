"""The embedding and reranking seams.

Two protocols beside :class:`~simple_agents.ModelClient`, for the two kinds of model a search
uses that a chat model cannot serve. An adapter implements one of them and nothing else.

``ModelClient`` takes messages and returns content and tool calls. An embedding takes text and
returns a vector, and a rerank takes a query and a list of texts and returns a score for each,
so neither is that protocol with a field left unused.

    from simple_agents.adapters import SentenceTransformerEmbeddings

    embedder = SentenceTransformerEmbeddings()
    index = DocumentIndex.from_texts(corpus, embeddings=embedder)

``identity`` reports which model the adapter calls without making a call. An index records the
identity that embedded it, the manifest records every identity that served the run, and a
search whose query is embedded by a different model than the corpus is refused.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from .errors import ConfigurationError
from .models import Backend, ModelIdentity, TokenUsage

__all__ = [
    "EmbeddingResponse",
    "EmbeddingClient",
    "RerankScore",
    "RerankResponse",
    "RerankClient",
    "FakeEmbeddingClient",
    "FakeRerankClient",
    "normalise",
]


def normalise(vector: Sequence[float]) -> list[float]:
    """A vector scaled to unit length, so a dot product against another is the cosine.

    A vector of all zeros is returned unchanged, since it has no direction to preserve::

        normalise([3.0, 4.0])     # [0.6, 0.8]
    """
    values = [float(x) for x in vector]
    length = math.sqrt(sum(x * x for x in values))
    return [x / length for x in values] if length else values


@dataclass(slots=True)
class EmbeddingResponse:
    """What an embedding backend returns: one vector per text, in the order given.

    ``vectors`` holds one list of floats per input text. ``tokens`` is the same breakdown every
    model call records, with ``output`` of ``0``, since an embedding produces no output tokens::

        EmbeddingResponse(
            vectors=[[0.01, -0.22, ...]],
            backend="hosted_api",
            request_model="mistral-embed",
            response_model="mistral-embed",
            model_revision=None,
            tokens=TokenUsage(input_uncached=13, input_cache_read=0,
                              input_cache_write=0, cache_ttl=None, output=0),
        )

    An adapter returning a different number of vectors than it was given texts raises
    :class:`~simple_agents.errors.ConfigurationError`, because the caller pairs them by
    position.
    """

    vectors: list[list[float]]
    backend: Backend
    request_model: str
    response_model: str | None
    model_revision: str | None
    tokens: TokenUsage
    provider: dict[str, str] = field(default_factory=dict)
    held_back_ms: int = 0

    @property
    def dimensions(self) -> int | None:
        """The length of each vector, or ``None`` where no vector was returned."""
        return len(self.vectors[0]) if self.vectors else None

    def check_against(self, texts: Sequence[str]) -> None:
        """Raise where the backend returned a different number of vectors than texts given."""
        if len(self.vectors) != len(texts):
            raise ConfigurationError(
                f"The embedding backend was given {len(texts)} text(s) and returned "
                f"{len(self.vectors)} vector(s). Results are paired with inputs by position, "
                f"so a short reply would attach a vector to the wrong document.\n"
                f"Fix the adapter to return one vector per input text, in the order given."
            )
        widths = {len(v) for v in self.vectors}
        if len(widths) > 1:
            raise ConfigurationError(
                f"The embedding backend returned vectors of differing widths ({sorted(widths)})."
                f" Vectors are compared against one another, which requires one width.\n"
                f"Fix the adapter, or use a model that returns a fixed number of dimensions."
            )


class EmbeddingClient(Protocol):
    """The embedding seam. Two methods.

    ``embed`` takes texts and returns one vector each. ``identity`` reports which model does it,
    without making a call::

        class MyEmbeddings:
            def identity(self) -> ModelIdentity:
                return ModelIdentity(backend="hosted_api", request_model="my-embed-v2")

            def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
                ...

    A backend with a batch limit batches inside ``embed`` rather than asking the caller to.
    """

    def embed(self, texts: Sequence[str]) -> EmbeddingResponse: ...

    def identity(self) -> ModelIdentity: ...


@dataclass(frozen=True, slots=True)
class RerankScore:
    """One reranked document: which one, and how relevant the model found it.

    ``index`` is the position of the document in the list the reranker was given. Scores are
    the model's own and are comparable only against others from the same model.
    """

    index: int
    score: float


@dataclass(slots=True)
class RerankResponse:
    """What a reranking backend returns: a score for each document it was given.

    ``scores`` holds one :class:`RerankScore` per document, and the caller sorts by it. An
    adapter returns a score for every document rather than dropping the ones it scored low,
    because the caller decides how many to keep::

        RerankResponse(
            scores=[RerankScore(index=0, score=8.2), RerankScore(index=1, score=-4.1)],
            backend="self_hosted",
            request_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
            response_model=None,
            model_revision="a1b2c3d",
            tokens=TokenUsage(input_uncached=800, input_cache_read=0,
                              input_cache_write=0, cache_ttl=None, output=0),
        )
    """

    scores: list[RerankScore]
    backend: Backend
    request_model: str
    response_model: str | None
    model_revision: str | None
    tokens: TokenUsage
    provider: dict[str, str] = field(default_factory=dict)
    held_back_ms: int = 0

    def ordered(self) -> list[RerankScore]:
        """The scores, most relevant first."""
        return sorted(self.scores, key=lambda s: (-s.score, s.index))

    def check_against(self, documents: Sequence[str]) -> None:
        """Raise where the backend scored a different number of documents than it was given."""
        if len(self.scores) != len(documents):
            raise ConfigurationError(
                f"The reranking backend was given {len(documents)} document(s) and returned "
                f"{len(self.scores)} score(s). A score is matched to a document by its "
                f"``index``, so a short reply leaves documents unranked.\n"
                f"Fix the adapter to return one score per document, scoring rather than "
                f"filtering."
            )


class RerankClient(Protocol):
    """The reranking seam. Two methods.

    ``rerank`` scores every document against the query, and ``identity`` reports which model
    does it::

        class MyReranker:
            def identity(self) -> ModelIdentity:
                return ModelIdentity(backend="hosted_api", request_model="my-rerank-v1")

            def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
                ...

    A reranker reads the query and the document together, so it cannot be precomputed the way
    an embedding can. It runs over the candidates a first pass returned, which is what
    ``top_n`` on a reranker bounds.
    """

    def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse: ...

    def identity(self) -> ModelIdentity: ...


def _fake_tokens(count: int) -> TokenUsage:
    return TokenUsage(
        input_uncached=count,
        input_cache_read=0,
        input_cache_write=0,
        cache_ttl=None,
        output=0,
    )


@dataclass(slots=True)
class FakeEmbeddingClient:
    """A deterministic embedding client for tests. Makes no call and needs no server.

    Each text is hashed into a fixed-width vector, so the same text embeds to the same vector
    every time. Nothing about the vectors is meaningful: they are for testing the plumbing,
    not the retrieval::

        index = DocumentIndex.from_texts(corpus, embeddings=FakeEmbeddingClient())

    ``model_identity`` is what :meth:`identity` reports. Change it to test behaviour that
    depends on which model embedded a store, such as an index read back under another one.
    """

    dimensions: int = 16
    model_identity: ModelIdentity = ModelIdentity(
        backend="self_hosted", request_model="test/embed", model_revision="0" * 40
    )
    texts: list[str] = field(default_factory=list)

    def identity(self) -> ModelIdentity:
        return self.model_identity

    def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        vectors = []
        for text in texts:
            self.texts.append(text)
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw = [digest[i % len(digest)] / 255.0 - 0.5 for i in range(self.dimensions)]
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            vectors.append([x / norm for x in raw])
        return EmbeddingResponse(
            vectors=vectors,
            backend=self.model_identity.backend,
            request_model=self.model_identity.request_model,
            response_model=self.model_identity.request_model,
            model_revision=self.model_identity.model_revision,
            tokens=_fake_tokens(sum(len(t.split()) for t in texts)),
        )


@dataclass(slots=True)
class FakeRerankClient:
    """A deterministic reranker for tests. Scores by how many query words a document holds.

    Makes no call and needs no server. The score is the count of query tokens present in the
    document, so a test can predict the order. It goes inside ``CrossEncoderRerank`` the way
    any rerank client does::

        index = DocumentIndex.from_texts(
            corpus,
            embeddings=FakeEmbeddingClient(),
            rerank=CrossEncoderRerank(FakeRerankClient(), top_n=20),
        )
    """

    model_identity: ModelIdentity = ModelIdentity(
        backend="self_hosted", request_model="test/rerank", model_revision="0" * 40
    )
    queries: list[str] = field(default_factory=list)

    def identity(self) -> ModelIdentity:
        return self.model_identity

    def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        self.queries.append(query)
        wanted = set(query.lower().split())
        scores = [
            RerankScore(index=i, score=float(len(wanted & set(doc.lower().split()))))
            for i, doc in enumerate(documents)
        ]
        return RerankResponse(
            scores=scores,
            backend=self.model_identity.backend,
            request_model=self.model_identity.request_model,
            response_model=self.model_identity.request_model,
            model_revision=self.model_identity.model_revision,
            tokens=_fake_tokens(sum(len(d.split()) for d in documents)),
        )
