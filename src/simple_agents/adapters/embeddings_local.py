"""Embedding and reranking from a model running in this process, with no endpoint.

Needs the optional extra::

    pip install 'simple-agents[semantic]'

Then semantic search works with nothing to configure and no server to start::

    from simple_agents.adapters import SentenceTransformerEmbeddings, LocalCrossEncoder

    index = DocumentIndex.from_texts(corpus, embeddings=SentenceTransformerEmbeddings())

The model is downloaded on first use and cached by ``sentence-transformers`` thereafter. A
project that already has an embedding endpoint should use
:class:`~simple_agents.adapters.OpenAIEmbeddings` instead, which needs no extra.

**These run on the machine the agent runs on.** A first call loads weights into memory, and a
large corpus embedded here competes with whatever else that machine is doing.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..embeddings import EmbeddingResponse, RerankResponse, RerankScore
from ..errors import ConfigurationError
from ..models import ModelIdentity, TokenUsage

__all__ = [
    "SentenceTransformerEmbeddings",
    "LocalCrossEncoder",
    "DEFAULT_EMBEDDING_MODEL",
    "DEFAULT_RERANK_MODEL",
]

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"
"""768 dimensions. Chosen for retrieval quality over speed; ``all-MiniLM-L6-v2`` is smaller."""

DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
"""22M parameters. Scores about twenty candidates in single-digit milliseconds on a GPU."""

_MISSING = (
    "{what} needs the `semantic` extra, which is not installed. It runs an embedding model in "
    "this process, so it depends on sentence-transformers and torch.\n"
    "Install it with `pip install 'simple-agents[semantic]'`, or use OpenAIEmbeddings "
    "(base_url=..., model=...) against an endpoint that serves /v1/embeddings, which needs no "
    "extra."
)


def _require(module: str, what: str) -> Any:
    try:
        import importlib

        return importlib.import_module(module)
    except ImportError as exc:
        raise ConfigurationError(_MISSING.format(what=what)) from exc


def _tokens(counted: int) -> TokenUsage:
    return TokenUsage(
        input_uncached=counted,
        input_cache_read=0,
        input_cache_write=0,
        cache_ttl=None,
        output=0,
    )


@dataclass
class SentenceTransformerEmbeddings:
    """An embedding model loaded into this process by ``sentence-transformers``.

    Needs no endpoint and no key::

        embedder = SentenceTransformerEmbeddings()
        embedder = SentenceTransformerEmbeddings(model="sentence-transformers/all-MiniLM-L6-v2",
                                                 device="cuda")

    ``model_revision`` pins the weights and is what FT-14 reads. Left unset, the library reads
    the commit ``sentence-transformers`` resolved and records that, so a run against a model
    downloaded today can be told apart from the same name downloaded later.

    ``device`` is passed through: ``None`` lets the library choose, ``"cpu"`` and ``"cuda"``
    force it. ``batch_size`` bounds how many texts are encoded at once.
    """

    model: str = DEFAULT_EMBEDDING_MODEL
    model_revision: str | None = None
    device: str | None = None
    batch_size: int = 32
    normalise: bool = True
    _encoder: Any = field(default=None, init=False, repr=False)
    _resolved: str | None = field(default=None, init=False, repr=False)
    _loading: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def _load(self) -> Any:
        # One loader at a time. Two nodes embedding at once on their first call would each
        # build the model, and two copies of one model on one device is how a load that fits
        # runs out of memory.
        with self._loading:
            if self._encoder is None:
                module = _require("sentence_transformers", "SentenceTransformerEmbeddings")
                self._encoder = module.SentenceTransformer(
                    self.model, device=self.device, revision=self.model_revision
                )
                self._resolved = self.model_revision or _commit_of(self._encoder)
        return self._encoder

    def identity(self) -> ModelIdentity:
        """The model and the commit its weights came from. Loads the model if it is not loaded."""
        self._load()
        return ModelIdentity(
            backend="self_hosted",
            request_model=self.model,
            model_revision=self._resolved,
        )

    def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        """One vector per text, encoded in this process."""
        if not texts:
            raise ConfigurationError(
                "SentenceTransformerEmbeddings.embed was given no texts, so there is nothing "
                "to attach a vector to.\n"
                "Pass the texts to embed, or skip the call where the caller has none."
            )
        encoder = self._load()
        encoded = encoder.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=self.normalise,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        vectors = [[float(x) for x in row] for row in encoded]
        counted = _count_tokens(encoder, texts)
        response = EmbeddingResponse(
            vectors=vectors,
            backend="self_hosted",
            request_model=self.model,
            response_model=self.model,
            model_revision=self._resolved,
            tokens=_tokens(counted),
        )
        response.check_against(texts)
        return response


@dataclass
class LocalCrossEncoder:
    """A cross-encoder reranker loaded into this process by ``sentence-transformers``.

    Scores a query against each candidate together, rather than comparing precomputed
    vectors::

        reranker = LocalCrossEncoder()
        index = DocumentIndex.from_texts(
            corpus, embeddings=embedder, rerank=CrossEncoderRerank(reranker, top_n=20)
        )

    ``model_revision`` pins the weights and is read by FT-14. Left unset, the resolved commit
    is recorded.
    """

    model: str = DEFAULT_RERANK_MODEL
    model_revision: str | None = None
    device: str | None = None
    batch_size: int = 32
    _encoder: Any = field(default=None, init=False, repr=False)
    _resolved: str | None = field(default=None, init=False, repr=False)
    _loading: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def _load(self) -> Any:
        # One loader at a time, for the reason the embedding model has one.
        with self._loading:
            if self._encoder is None:
                module = _require("sentence_transformers", "LocalCrossEncoder")
                self._encoder = module.CrossEncoder(
                    self.model, device=self.device, revision=self.model_revision
                )
                self._resolved = self.model_revision or _commit_of(self._encoder)
        return self._encoder

    def identity(self) -> ModelIdentity:
        """The model and the commit its weights came from. Loads the model if it is not loaded."""
        self._load()
        return ModelIdentity(
            backend="self_hosted",
            request_model=self.model,
            model_revision=self._resolved,
        )

    def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        """A relevance score for every document, against the query."""
        if not documents:
            raise ConfigurationError(
                "LocalCrossEncoder.rerank was given no documents, so there is nothing to "
                "score.\n"
                "Skip the rerank where the first pass returned nothing."
            )
        encoder = self._load()
        raw = encoder.predict(
            [(query, doc) for doc in documents],
            batch_size=self.batch_size,
            show_progress_bar=False,
        )
        scores = [RerankScore(index=i, score=float(s)) for i, s in enumerate(raw)]
        response = RerankResponse(
            scores=scores,
            backend="self_hosted",
            request_model=self.model,
            response_model=self.model,
            model_revision=self._resolved,
            tokens=_tokens(_count_tokens(encoder, [query, *documents])),
        )
        response.check_against(documents)
        return response


def _commit_of(encoder: Any) -> str | None:
    """The commit the loaded weights came from, where the library recorded one."""
    for holder in (encoder, getattr(encoder, "model", None)):
        config = getattr(holder, "config", None)
        commit = getattr(config, "_commit_hash", None)
        if isinstance(commit, str) and commit:
            return commit
    return None


def _count_tokens(encoder: Any, texts: Sequence[str]) -> int:
    """How many tokens the model was given, from its own tokeniser.

    Falls back to a whitespace count where the tokeniser cannot be reached, so a budget is
    charged an approximation rather than nothing.
    """
    tokeniser = getattr(encoder, "tokenizer", None) or getattr(
        getattr(encoder, "model", None), "tokenizer", None
    )
    if tokeniser is None:
        return sum(len(text.split()) for text in texts)
    try:
        return sum(len(ids) for ids in tokeniser(list(texts))["input_ids"])
    except Exception:
        return sum(len(text.split()) for text in texts)
