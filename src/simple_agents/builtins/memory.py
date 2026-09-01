"""Tools over the run's memory store: write one fact, read one back, search what is there.

Each is a factory, because the name is the project's to choose and two agents sharing a process
should not be forced to share one. The store itself is not passed here: it comes from the
envelope, through the ``Memory`` handle the library fills in.

    from simple_agents import MemoryStore, RunEnvelope
    from simple_agents.builtins import memory_search, recall, remember

    env = RunEnvelope(run_dir="runs/", memory=MemoryStore("memory/"))
    registry = ToolRegistry([remember(), recall(), memory_search()])
    pipeline.run(question, envelope=env, model=client, memory_scope=f"user-{user_id}")

A run that reaches no memory is refused before it starts, naming what to declare.
Search is lexical, the same BM25 ``document_search`` uses, so a query sharing no words with a
stored value does not find it.
"""

from __future__ import annotations

from typing import Any

from ..embeddings import normalise
from ..errors import ConfigurationError
from ..memory import Memory
from ..tools import Retrieval, SideEffectClass, Tool, tool
from .ranking import Ranking, VectorScan, refuse_no_ranking
from .search import DocumentIndex

__all__ = ["remember", "recall", "memory_search"]

DEFAULT_TOP_K = 5

# Keys listed back when a search matches nothing and the store is not empty. Enough for the
# model to see what it has; a store larger than this reports the count alongside them.
MAX_KEYS_ON_EMPTY = 50


def remember(*, name: str = "remember", version: str | None = None) -> Tool:
    """A tool that stores one fact for later runs to read.

    Declared ``WRITES``. An evaluation gives each rollout its own store, so writing k×n times
    during one does not act on the world k×n times::

        registry.add(remember())

    **Storing under a key that already holds something replaces it.** The tool is re-run during
    a replay rather than served from the cassette, so writing twice has to leave the state
    writing once leaves. A fact with no natural key goes under one describing it, such as
    ``preferred_length``.
    """

    @tool(side_effect_class=SideEffectClass.WRITES, name=name, version=version)
    def write(memory: Memory, key: str, value: str) -> dict[str, Any]:
        """Store one fact so that a later conversation can read it back.

        `key` is a short name for what is being stored, such as `preferred_length` or
        `delivery_address`. Storing under a key that already holds something replaces it, so
        reuse the key when updating a fact and pick a new one when adding a different fact.

        `value` is the fact itself, written so it makes sense on its own months later.

        Store what will still be true next time. Do not store the current question, a
        step of the current task, or anything the end user asked to be kept private.

        Returns the key it was stored under and whether something was replaced.
        """
        existed = memory.recall(key) is not None
        entry = memory.remember(key, value)
        return {"key": entry.key, "replaced": existed, "stored_at": entry.stored_at}

    return write


def recall(*, name: str = "recall", version: str | None = None) -> Tool:
    """A tool that reads back one stored fact by its key.

    Declared ``READ_ONLY``, and re-run during a replay because it reads a store the replay
    rebuilds::

        registry.add(recall())

    Returns `found: false` rather than failing where nothing is stored, since finding nothing
    is something the model acts on by asking or by searching for something else.
    """

    @tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version=version)
    def read(memory: Memory, key: str) -> dict[str, Any]:
        """Read back one fact stored under a key, from earlier conversations.

        Returns `found`, and `value` and `stored_at` where something is stored. `found: false`
        means nothing is stored under that key: it does not mean the fact is untrue, only that
        it was never written down. The search tool finds a key that is not already known.
        """
        entry = memory.recall(key)
        if entry is None:
            return {"found": False, "key": key}
        return {
            "found": True,
            "key": entry.key,
            "value": entry.value,
            "stored_at": entry.stored_at,
        }

    return read


def memory_search(
    *,
    name: str = "memory_search",
    top_k: int = DEFAULT_TOP_K,
    embeddings: Any = None,
    ranking: Ranking | None = None,
    version: str | None = None,
) -> Tool:
    """A tool that searches stored facts by the words in them, and by what they mean.

    Declared ``READ_ONLY``, and re-run during a replay for the same reason ``recall`` is::

        registry.add(memory_search(top_k=3))

    Without ``embeddings``, matching is lexical over the key and the value together, so a query
    sharing no words with a stored fact does not find it.

    ``embeddings`` adds semantic recall, so a fact stored as "prefers short books" is found by
    a search for "length preference". ``ranking`` is required alongside it, and takes the
    values it takes on a :class:`~simple_agents.builtins.DocumentIndex`::

        registry.add(memory_search(embeddings=SentenceTransformerEmbeddings(),
                                   ranking=Hybrid(fuse=RRF(k=5))))

    **Each fact is embedded once and the vector is stored beside it.** A fact written before
    the store had embeddings, or written under a different model, is embedded the first time a
    search reads it and the vector is written back.

    Returns `results` in rank order, each carrying `key`, `value`, `stored_at` and `score`,
    plus `retriever` where ``embeddings`` is given; and `stored`, the number of facts held. A
    search that matched nothing over a store that holds something also returns `keys`, the
    first :data:`MAX_KEYS_ON_EMPTY` of them in alphabetical order. `docs/memory.md` §2.5
    prints the whole reply.
    """
    if embeddings is not None and ranking is None:
        raise ConfigurationError(refuse_no_ranking("memory_search"))
    default_k = top_k

    if embeddings is None:

        @tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version=version)
        def search(memory: Memory, query: str, top_k: int = default_k) -> dict[str, Any]:
            """Search facts stored in earlier conversations, by the words in them.

            Matching is lexical, on the words themselves, so use words that would appear in the
            stored fact rather than the phrasing of a question.

            Returns `results`, the best matches in rank order, each with its `key`, `value`,
            `stored_at` and `score`, and `stored`, how many facts are stored in total.

            When nothing matches and something is stored, the reply carries `keys`, the
            first 50 keys in alphabetical order, and `stored` says how many there are in total.
            Reading one with the recall tool is how a fact phrased differently from the question
            is found.

            Finding nothing means these words did not reach a stored fact. It does not establish
            that nothing was ever stored about the subject.
            """
            entries = {entry.key: entry for entry in memory.entries()}
            if not entries:
                return {"results": [], "stored": 0}
            index = DocumentIndex.from_texts(
                {key: f"{key} {entry.value}" for key, entry in entries.items()}
            )
            found = [
                {
                    "key": hit.doc_id,
                    "value": entries[hit.doc_id].value,
                    "stored_at": entries[hit.doc_id].stored_at,
                    "score": round(hit.score, 4),
                }
                for hit in index.search(query, top_k=top_k)
            ]
            reply: dict[str, Any] = {"results": found, "stored": len(entries)}
            if not found:
                reply["keys"] = sorted(entries)[:MAX_KEYS_ON_EMPTY]
            return reply

        return search

    chosen = ranking

    @tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version=version)
    def search_semantic(
        memory: Memory, retrieval: Retrieval, query: str, top_k: int = default_k
    ) -> dict[str, Any]:
        """Search facts stored in earlier conversations, by meaning and by the words in them.

        A fact phrased differently from the question is still found, so ask in whatever words
        the question uses rather than guessing how the fact was written down.

        Returns `results`, the best matches in rank order, each with its `key`, `value`,
        `stored_at`, `score` and `retriever` naming what found it, and `stored`, how many facts
        are stored in total. Scores from different retrievers are not comparable.

        When nothing matches and something is stored, the reply carries `keys`, the first 50
        keys in alphabetical order, and `stored` says how many there are in total. Reading one
        with the recall tool is the way to see what is held.

        Finding nothing means the query did not reach a stored fact. It does not establish that
        nothing was ever stored about the subject.
        """
        entries = {entry.key: entry for entry in memory.entries()}
        if not entries:
            return {"results": [], "stored": 0}
        texts = {key: f"{key} {entry.value}" for key, entry in entries.items()}
        store = _vectors_for(memory, entries, texts, embeddings, retrieval)
        index = DocumentIndex.from_texts(
            texts, embeddings=embeddings, ranking=chosen, vectors=store
        )
        index.embedded_by = embeddings.identity()
        found = [
            {
                "key": hit.doc_id,
                "value": entries[hit.doc_id].value,
                "stored_at": entries[hit.doc_id].stored_at,
                "score": round(hit.score, 4),
                "retriever": hit.retriever,
            }
            for hit in index.search(query, top_k=top_k, retrieval=retrieval)
        ]
        reply: dict[str, Any] = {"results": found, "stored": len(entries)}
        if not found:
            reply["keys"] = sorted(entries)[:MAX_KEYS_ON_EMPTY]
        return reply

    return search_semantic


def _vectors_for(
    memory: Memory,
    entries: dict[str, Any],
    texts: dict[str, str],
    embeddings: Any,
    retrieval: Retrieval,
) -> VectorScan:
    """The store's vectors, embedding and writing back only what is missing or stale.

    An entry already embedded by this model is read off disk. Anything else is embedded in one
    call and written back, so the cost falls on the first search after a fact is written rather
    than on every search.
    """
    identity = embeddings.identity().to_manifest()
    missing = [key for key, entry in entries.items() if not entry.embedded_under(identity)]
    fresh: dict[str, list[float]] = {}
    if missing:
        vectors = retrieval.embed(embeddings, [texts[key] for key in missing])
        for key, vector in zip(missing, vectors):
            fresh[key] = vector
            memory.store_vector(key, vector, identity)
    store = VectorScan()
    keys = list(entries)
    store.add(
        keys,
        [fresh.get(key) or normalise(entries[key].vector) for key in keys],
    )
    return store
