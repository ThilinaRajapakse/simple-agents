"""Reordering what a search returned, by reading the query and each document together.

A first pass ranks the whole corpus cheaply and a reranker reorders the few it returned::

    index = DocumentIndex.from_texts(
        corpus,
        embeddings=embedder,
        rerank=CrossEncoderRerank(LocalCrossEncoder(), top_n=20),
    )

**Reranking is the largest single change to what a search returns.** Measured over MS MARCO
passage and Natural Questions with two embedding models, a cross-encoder over the top twenty
raised how often the answer came back in the top five by 0.05 to 0.13, and moved it up the
list further than any choice of fusion did. It costs one model call per search over ``top_n``
documents, so it is charged to the run's budget like any other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from ..errors import ConfigurationError

__all__ = ["Reranker", "CrossEncoderRerank", "ModelRerank"]

DEFAULT_TOP_N = 20
"""Candidates reranked by default. Measured at about 7 ms on a local cross-encoder."""


class Reranker(Protocol):
    """How an index reorders the candidates a first pass returned.

    Implemented by :class:`CrossEncoderRerank` and :class:`ModelRerank`. ``top_n`` is how many
    candidates reach it; the search's own ``top_k`` decides how many come back after.
    """

    @property
    def top_n(self) -> int: ...


@dataclass(frozen=True, slots=True)
class CrossEncoderRerank:
    """Score each candidate against the query with a cross-encoder, then sort by the score.

    ``client`` is a :class:`~simple_agents.RerankClient`, either
    :class:`~simple_agents.adapters.LocalCrossEncoder` or
    :class:`~simple_agents.adapters.OpenAIReranker`::

        CrossEncoderRerank(LocalCrossEncoder(), top_n=20)

    ``top_n`` bounds the cost: a rerank reads every candidate alongside the query, so twice the
    candidates is roughly twice the tokens. Raising it past what the first pass ranks well is
    what recovers an answer the first pass buried, and 20 is the default because that is where
    the measured gain had mostly arrived.
    """

    client: Any
    top_n: int = DEFAULT_TOP_N

    def __post_init__(self) -> None:
        _check_top_n(self.top_n, "CrossEncoderRerank")
        if not hasattr(self.client, "rerank") or not hasattr(self.client, "identity"):
            raise ConfigurationError(
                f"CrossEncoderRerank was given {self.client!r}, which is not a RerankClient. "
                f"A RerankClient declares `rerank(query, documents)` and `identity()`.\n"
                f"Pass CrossEncoderRerank(LocalCrossEncoder()), or "
                f"CrossEncoderRerank(OpenAIReranker(base_url=..., model=...))."
            )


@dataclass(frozen=True, slots=True)
class ModelRerank:
    """Ask the run's chat model which candidates answer the query, and sort by what it says.

    Needs no second model and no extra, since it uses the model the agent already runs on::

        ModelRerank(top_n=10)

    **A chat model reranks worse than a cross-encoder trained for it, and costs more.** It
    reads every candidate into a prompt, so the tokens grow with ``top_n`` and with document
    length, and the ordering it returns is not a score. Reach for this where a second model is
    not available, and measure it against no reranking at all before keeping it.

    ``instruction`` replaces the wording the model is given, for a corpus where relevance
    means something specific.
    """

    top_n: int = 10
    instruction: str | None = None

    def __post_init__(self) -> None:
        _check_top_n(self.top_n, "ModelRerank")

    def prompt_for(self, query: str, documents: Sequence[str]) -> str:
        """The prompt sent to the chat model, listing the candidates by number."""
        task = self.instruction or (
            "Order the passages by how well each answers the question. "
            "Reply with the numbers alone, best first, separated by commas."
        )
        listed = "\n".join(f"{i + 1}. {doc}" for i, doc in enumerate(documents))
        return f"{task}\n\nQuestion: {query}\n\nPassages:\n{listed}"

    def order_from(self, reply: str, count: int) -> list[int]:
        """The positions the model named, as indices, with anything it left out appended.

        A reply naming a number twice keeps the first mention, and one naming a number outside
        the range drops it. Candidates the model did not mention keep their incoming order
        behind the ones it did, so a truncated reply reorders what it covered and loses
        nothing.
        """
        seen: list[int] = []
        for found in re.findall(r"\d+", reply or ""):
            index = int(found) - 1
            if 0 <= index < count and index not in seen:
                seen.append(index)
        return seen + [i for i in range(count) if i not in seen]


def _check_top_n(top_n: int, what: str) -> None:
    if top_n < 1:
        raise ConfigurationError(
            f"{what}(top_n={top_n}) needs at least 1 candidate to rerank. A reranker reorders "
            f"what the first pass returned, so there is nothing for it to do below 1.\n"
            f"Pass {what}(top_n=20), or leave rerank unset to return the first pass unchanged."
        )
