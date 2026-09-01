"""Embedding and reranking over an OpenAI-compatible HTTP endpoint.

One adapter serves every provider that speaks ``/v1/embeddings``, which is Mistral, OpenAI, a
vLLM server started for pooling, and most things that host either::

    from simple_agents.adapters import OpenAIEmbeddings, MistralEmbeddings

    embedder = MistralEmbeddings()                                  # reads MISTRAL_API_KEY
    embedder = OpenAIEmbeddings(base_url="http://localhost:8001/v1",
                                model="sentence-transformers/msmarco-bert-co-condensor",
                                model_revision=WEIGHTS_SHA)

**A chat server does not serve embeddings.** vLLM loads one model per server and decides at
startup whether it generates or pools, so a self-hosted project runs a second server for the
embedding model and points ``base_url`` at it. A hosted provider serves both from one endpoint
and one key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import httpx
from pydantic import SecretStr

from ..embeddings import EmbeddingResponse, RerankResponse, RerankScore
from ..errors import ConfigurationError
from ..models import Backend, ModelIdentity, TokenUsage
from ..schema import Unknown
from ._http import HTTPBackend, Retry

__all__ = ["OpenAIEmbeddings", "MistralEmbeddings", "OpenAIReranker"]

MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
MISTRAL_API_KEY_ENV = "MISTRAL_API_KEY"
MISTRAL_EMBED_MODEL = "mistral-embed"

DEFAULT_BATCH = 128
"""Texts per request. A provider with a lower limit takes ``batch_size`` in the constructor."""


NO_PROMPT_SPLIT = (
    "the endpoint reported no prompt_tokens_details.cached_tokens, so how much of the prompt "
    "was served from a cache is unmeasured"
)


def _tokens_from(usage: Mapping[str, Any] | None, texts: Sequence[str]) -> TokenUsage:
    """The token breakdown, from what the provider reported.

    An embedding produces no output, so ``output`` is ``0`` rather than unknown. The two cache
    counts come from ``prompt_tokens_details.cached_tokens`` where the endpoint reports it, and
    are ``Unknown`` where it does not: a response carrying one prompt figure does not say how
    that prompt divided, and a zero there would be a measurement. A provider reporting no usage
    at all is an error: a call whose size is unmeasured cannot be charged to a budget.
    """
    if not usage or usage.get("prompt_tokens") is None:
        raise ConfigurationError(
            "The embedding endpoint returned no `usage.prompt_tokens`. A model call whose size "
            "is unknown cannot be charged to the run's token budget or priced by the cost "
            "basis, and reporting zero would understate both.\n"
            "Use a provider that reports usage on /v1/embeddings, or write an adapter that "
            "counts the tokens it sent."
        )
    prompt = int(usage["prompt_tokens"])
    details = usage.get("prompt_tokens_details")
    cached = details.get("cached_tokens") if isinstance(details, Mapping) else None
    if isinstance(cached, int):
        return TokenUsage(
            input_uncached=prompt - cached,
            input_cache_read=cached,
            input_cache_write=0,
            cache_ttl=None,
            output=0,
        )
    return TokenUsage(
        input_uncached=prompt,
        input_cache_read=Unknown(reason=NO_PROMPT_SPLIT),
        input_cache_write=Unknown(reason=NO_PROMPT_SPLIT),
        cache_ttl=None,
        output=0,
    )


def _summed(parts: Sequence[TokenUsage]) -> TokenUsage:
    """One breakdown for a call that went out as several batched requests.

    A class left unmeasured by any batch is unmeasured for the call: the total cannot be
    completed without it.
    """
    if len(parts) == 1:
        return parts[0]

    def add(name: str) -> int | Unknown:
        counts = [getattr(part, name) for part in parts]
        for count in counts:
            if isinstance(count, Unknown):
                return count
        return sum(counts)

    return TokenUsage(
        input_uncached=add("input_uncached"),
        input_cache_read=add("input_cache_read"),
        input_cache_write=add("input_cache_write"),
        cache_ttl=None,
        output=0,
    )


@dataclass
class OpenAIEmbeddings:
    """Embeddings from any endpoint serving OpenAI's ``/v1/embeddings``.

    ``base_url`` is the API root and ``model`` the model to request::

        OpenAIEmbeddings(base_url="http://localhost:8001/v1",
                         model="sentence-transformers/msmarco-bert-co-condensor",
                         model_revision="4d3f2a1...")

    ``model_revision`` is the commit the weights came from and is what FT-14 reads on a
    self-hosted backend. Nothing in a response carries it, so an adapter built without one
    reports ``None`` and fails that check.

    ``api_key`` authenticates where the endpoint needs it, and is left unset for a local
    server. ``truncate`` asks the server to cut text longer than the model's window rather
    than refusing it, which vLLM requires before it will embed a long passage.
    """

    base_url: str
    model: str
    model_revision: str | None = None
    api_key: SecretStr | None = None
    backend: Backend = "self_hosted"
    batch_size: int = DEFAULT_BATCH
    truncate: bool = True
    timeout_s: float = 120.0
    retry: Retry = field(default_factory=Retry)
    client: httpx.Client | None = None

    def identity(self) -> ModelIdentity:
        return ModelIdentity(
            backend=self.backend,
            request_model=self.model,
            model_revision=self.model_revision,
        )

    def _backend(self) -> HTTPBackend:
        headers = {}
        if self.api_key is not None:
            headers["Authorization"] = f"Bearer {self.api_key.get_secret_value()}"
        return HTTPBackend(
            base_url=self.base_url,
            headers=headers,
            timeout_s=self.timeout_s,
            retry=self.retry,
            client=self.client,
        )

    def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        """One vector per text, batching where there are more than ``batch_size``."""
        if not texts:
            raise ConfigurationError(
                "OpenAIEmbeddings.embed was given no texts. An empty call still costs a "
                "request, and there is nothing to attach the result to.\n"
                "Pass the texts to embed, or skip the call where the caller has none."
            )
        http = self._backend()
        vectors: list[list[float]] = []
        batches: list[TokenUsage] = []
        served: str | None = None
        provider: dict[str, str] = {}
        for start in range(0, len(texts), self.batch_size):
            chunk = list(texts[start : start + self.batch_size])
            payload: dict[str, Any] = {"model": self.model, "input": chunk}
            if self.truncate:
                payload["truncate_prompt_tokens"] = -1
            result = http.post_json("/embeddings", payload)
            body = result.body if isinstance(result.body, dict) else {}
            data = body.get("data") or []
            for item in sorted(data, key=lambda d: d.get("index", 0)):
                vectors.append([float(x) for x in item.get("embedding") or []])
            batches.append(_tokens_from(body.get("usage"), chunk))
            served = body.get("model") or served
            if body.get("id"):
                provider["id"] = str(body["id"])
        response = EmbeddingResponse(
            vectors=vectors,
            backend=self.backend,
            request_model=self.model,
            response_model=served,
            model_revision=self.model_revision,
            tokens=_summed(batches),
            provider=provider,
        )
        response.check_against(texts)
        return response


def MistralEmbeddings(
    *,
    model: str = MISTRAL_EMBED_MODEL,
    api_key: SecretStr | str | None = None,
    **kwargs: Any,
) -> OpenAIEmbeddings:
    """Mistral's embedding model, over the same endpoint shape.

    The key is read from ``MISTRAL_API_KEY`` where none is passed::

        embedder = MistralEmbeddings()
        embedder = MistralEmbeddings(model="mistral-embed", api_key=SecretStr(key))

    Backend ``hosted_api``, so ``model_revision`` is ``None`` and FT-14 reads the model name
    for whether it floats. A dated model string is a provider's promise that it keeps
    resolving to the same weights, and a bare name is not.
    """
    if api_key is None:
        raw = os.environ.get(MISTRAL_API_KEY_ENV)
        if not raw:
            raise ConfigurationError(
                f"MistralEmbeddings found no API key. Set {MISTRAL_API_KEY_ENV} in the "
                f"environment, or pass MistralEmbeddings(api_key=SecretStr(key)).\n"
                f"Confirm the credential is available before the first run (FT-14)."
            )
        api_key = SecretStr(raw)
    elif isinstance(api_key, str):
        api_key = SecretStr(api_key)
    return OpenAIEmbeddings(
        base_url=kwargs.pop("base_url", MISTRAL_BASE_URL),
        model=model,
        api_key=api_key,
        backend="hosted_api",
        **kwargs,
    )


@dataclass
class OpenAIReranker:
    """Reranking over an endpoint serving ``/v1/rerank``, which vLLM and several hosts do.

    ``base_url`` is the API root and ``model`` the cross-encoder to request::

        OpenAIReranker(base_url="http://localhost:8004/v1",
                       model="cross-encoder/ms-marco-MiniLM-L-6-v2",
                       model_revision="c5ee24c...")

    Pass this to :class:`~simple_agents.builtins.CrossEncoderRerank` rather than to an index
    directly, since how many candidates to rerank is the index's setting.
    """

    base_url: str
    model: str
    model_revision: str | None = None
    api_key: SecretStr | None = None
    backend: Backend = "self_hosted"
    timeout_s: float = 120.0
    retry: Retry = field(default_factory=Retry)
    client: httpx.Client | None = None

    def identity(self) -> ModelIdentity:
        return ModelIdentity(
            backend=self.backend,
            request_model=self.model,
            model_revision=self.model_revision,
        )

    def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        """A relevance score for every document, against the query."""
        if not documents:
            raise ConfigurationError(
                "OpenAIReranker.rerank was given no documents. There is nothing to score, and "
                "the call still costs a request.\n"
                "Skip the rerank where the first pass returned nothing."
            )
        headers = {}
        if self.api_key is not None:
            headers["Authorization"] = f"Bearer {self.api_key.get_secret_value()}"
        http = HTTPBackend(
            base_url=self.base_url,
            headers=headers,
            timeout_s=self.timeout_s,
            retry=self.retry,
            client=self.client,
        )
        result = http.post_json(
            "/rerank",
            {"model": self.model, "query": query, "documents": list(documents)},
        )
        body = result.body if isinstance(result.body, dict) else {}
        scores = [
            RerankScore(index=int(item.get("index", 0)), score=float(item["relevance_score"]))
            for item in body.get("results") or []
        ]
        response = RerankResponse(
            scores=scores,
            backend=self.backend,
            request_model=self.model,
            response_model=body.get("model"),
            model_revision=self.model_revision,
            tokens=_tokens_from(body.get("usage"), documents),
        )
        response.check_against(documents)
        return response
