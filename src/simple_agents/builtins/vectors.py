"""Where an index keeps its vectors, and how it finds the nearest to a query.

Three stores ship. :class:`NumpyVectors` is what a
:class:`~simple_agents.builtins.DocumentIndex` builds when numpy is installed,
:class:`VectorScan` is what it builds otherwise, and :class:`FaissVectors` is behind the
``ann`` extra for a corpus past what an exact scan answers quickly::

    index = DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic())
    # NumpyVectors, since the index named no store and numpy is installed.
    index = DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic(),
                                     vectors=FaissVectors(kind="approximate"))

All three take vectors that are already unit length, so a dot product is the cosine, and all
three return ``(doc_id, score)`` best first. :class:`NumpyVectors` and :class:`VectorScan`
return the same documents in the same order; an approximate :class:`FaissVectors` returns
fewer true neighbours for the same ``top_k``, which is why a run records which store answered
it.
"""

from __future__ import annotations

import heapq
import math
import operator
import threading
import warnings
from typing import Any, Protocol, Sequence

from ..errors import ConfigurationError, SimpleAgentsWarning

__all__ = [
    "VectorStore",
    "VectorScan",
    "NumpyVectors",
    "FaissVectors",
    "default_store",
]


class VectorStore(Protocol):
    """Where an index keeps its vectors and how it finds the nearest.

    Three methods are required. A project with a corpus in a store it already runs points
    ``vectors=`` at its own::

        class MyStore:
            def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
                ...

            def search(self, vector: Sequence[float], top_k: int) -> list[tuple[str, float]]:
                ...

            def __len__(self) -> int:
                ...

        DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic(),
                                 vectors=MyStore())

    ``search`` returns ``(doc_id, score)`` best first, where a higher score is more similar.
    Vectors reaching ``add`` are already normalised to unit length, so a dot product is the
    cosine. A store that returns approximate neighbours returns fewer true matches than
    :class:`VectorScan` for the same ``top_k``, and the project owns that trade.

    **Three more methods are optional, and each one enables something on the index that holds
    the store**: ``ids()`` returns every identifier held, in the order ``all_vectors()``
    returns them; ``all_vectors()`` returns every vector; ``remove(ids)`` drops the ones
    named. Without ``ids`` and ``all_vectors``, :meth:`~simple_agents.builtins.DocumentIndex.save` refuses rather than
    writing a file with no vectors in it. Without ``remove``,
    :meth:`~simple_agents.builtins.DocumentIndex.remove` refuses. Every store the library ships has all three.
    """

    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None: ...

    def search(self, vector: Sequence[float], top_k: int) -> list[tuple[str, float]]: ...

    def __len__(self) -> int: ...


def _check_pairing(what: str, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
    if len(ids) != len(vectors):
        raise ConfigurationError(
            f"{what}.add was given {len(ids)} identifier(s) and {len(vectors)} vector(s). "
            f"They are paired by position, so a mismatch would file a vector under another "
            f"document's identifier."
        )


class VectorScan:
    """Vectors in memory as Python lists, compared against every one. Needs no dependency.

    Results are exact: there is no approximation and no parameter trading recall for speed::

        store = VectorScan()
        store.add(["a1"], [[0.1, -0.3, 0.2]])
        store.search([0.1, -0.3, 0.2], top_k=1)     # [('a1', 1.0)]

    **What it costs, measured on one CPU core at 768 dimensions**: 10,000 documents hold
    307 MB and answer a query in about 60 ms on Python 3.12, or 146 ms on 3.11, where the
    faster arithmetic is unavailable. 100,000 documents hold 3.0 GB and take about 590 ms.
    A Python float is an object, which is where the memory goes: :class:`NumpyVectors` holds
    the same two corpora in 39 MB and 306 MB and answers them in 3.5 ms and 7.1 ms, and is
    what an index builds where numpy is installed.
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
        _check_pairing("VectorScan", ids, vectors)
        added = [[float(x) for x in vector] for vector in vectors]
        with self._lock:
            self._ids.extend(ids)
            self._vectors.extend(added)

    def remove(self, ids: Sequence[str]) -> None:
        """Drop the vectors held under these identifiers. One not held is ignored."""
        dropping = set(ids)
        with self._lock:
            kept = [i for i, doc_id in enumerate(self._ids) if doc_id not in dropping]
            self._ids = [self._ids[i] for i in kept]
            self._vectors = [self._vectors[i] for i in kept]

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
        with self._lock:
            return list(self._ids)

    def all_vectors(self) -> list[list[float]]:
        """Every vector held, in the order :meth:`ids` returns them."""
        with self._lock:
            return [list(v) for v in self._vectors]

    @property
    def dimensions(self) -> int | None:
        """How wide the vectors are, or ``None`` where none was added."""
        return len(self._vectors[0]) if self._vectors else None

    def __len__(self) -> int:
        return len(self._ids)


class NumpyVectors:
    """Vectors in one numpy matrix, compared against every one. Exact, and the default.

    The same results as :class:`VectorScan` in the same order, an order of magnitude faster
    and in half the memory, because the comparison is one matrix product rather than a Python
    loop::

        store = NumpyVectors()
        store.add(["a1"], [[0.1, -0.3, 0.2]])
        store.search([0.1, -0.3, 0.2], top_k=1)     # [('a1', 1.0)]

    **What it costs, measured on one CPU core at 768 dimensions**: 10,000 documents hold 39 MB
    and answer a query in about 3.5 ms, and 100,000 hold 306 MB and take about 7.1 ms. A
    million documents hold 3 GB and are where :class:`FaissVectors` starts to pay for itself.

    Vectors are held as ``float32``, which is what an index file holds, so a
    score can differ from :class:`VectorScan`'s in the seventh decimal place. Results are
    recorded to four.
    """

    def __init__(self) -> None:
        self._numpy = _require_numpy("NumpyVectors")
        self._ids: list[str] = []
        self._matrix: Any = None
        # The identifiers and the rows of the matrix are one table, the same as in
        # `VectorScan`, and a reader that took the ids of one add and the matrix of the next
        # would report a vector under another document's identifier.
        self._lock = threading.Lock()

    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        """Add vectors under their identifiers. Both sequences are paired by position."""
        _check_pairing("NumpyVectors", ids, vectors)
        if not ids:
            return
        np = self._numpy
        added = np.asarray(vectors, dtype="float32")
        if added is vectors:
            # `asarray` hands back a matrix of the right dtype unchanged, so a caller that
            # kept a reference to it would be able to change what the store holds. A list of
            # floats, which is what an index passes, is converted and already a copy.
            added = added.copy()
        if added.ndim != 2:
            raise ConfigurationError(
                f"NumpyVectors.add was given vectors of {added.ndim} dimension(s). It takes "
                f"one list of floats per identifier, all of one width."
            )
        with self._lock:
            if self._matrix is None:
                self._matrix = added
            elif added.shape[1] != self._matrix.shape[1]:
                raise ConfigurationError(
                    f"NumpyVectors holds vectors of {self._matrix.shape[1]} dimension(s) and "
                    f"was given {added.shape[1]}. Vectors are compared against one another, "
                    f"which requires one width.\n"
                    f"Embed the new documents with the model that embedded the rest."
                )
            else:
                self._matrix = np.vstack((self._matrix, added))
            self._ids.extend(ids)

    def remove(self, ids: Sequence[str]) -> None:
        """Drop the vectors held under these identifiers. One not held is ignored."""
        dropping = set(ids)
        with self._lock:
            if self._matrix is None:
                return
            kept = [i for i, doc_id in enumerate(self._ids) if doc_id not in dropping]
            self._ids = [self._ids[i] for i in kept]
            self._matrix = self._matrix[kept] if kept else None

    def search(self, vector: Sequence[float], top_k: int) -> list[tuple[str, float]]:
        """The nearest vectors by dot product, best first. Empty where nothing was added."""
        if top_k < 1:
            return []
        np = self._numpy
        with self._lock:
            matrix = self._matrix
            ids = list(self._ids)
        if matrix is None or not len(ids):
            return []
        scores = matrix @ np.asarray(vector, dtype="float32")
        take = min(top_k, len(ids))
        # The threshold picks the candidates worth ordering, so the tie-break runs over a
        # handful of rows rather than the whole corpus. Ties are broken by identifier, the
        # same way `VectorScan` breaks them, so the two stores return one order.
        cut = float(np.partition(scores, len(ids) - take)[len(ids) - take])
        candidates = [int(i) for i in np.flatnonzero(scores >= cut)]
        best = heapq.nlargest(take, candidates, key=lambda i: (float(scores[i]), ids[i]))
        return [(ids[i], float(scores[i])) for i in best]

    def ids(self) -> list[str]:
        """Every identifier held, in the order it was added."""
        with self._lock:
            return list(self._ids)

    def all_vectors(self) -> Any:
        """Every vector held as one ``float32`` matrix, in the order :meth:`ids` returns them.

        The matrix itself, so a corpus of a million vectors is written to a file without a
        copy of it in Python lists. Adding to the store replaces the matrix rather than
        writing into this one.
        """
        with self._lock:
            if self._matrix is None:
                return self._numpy.zeros((0, 0), "float32")
            return self._matrix

    @property
    def dimensions(self) -> int | None:
        """How wide the vectors are, or ``None`` where none was added."""
        return int(self._matrix.shape[1]) if self._matrix is not None else None

    def __len__(self) -> int:
        return len(self._ids)


HNSW_NEIGHBOURS = 32
"""Edges per node in an approximate :class:`FaissVectors`. FAISS's own default is 32."""


class FaissVectors:
    """Vectors in a FAISS index, on the CPU or on a GPU. Needs the ``ann`` extra.

    ``kind`` decides what a search returns. ``exact`` compares against every vector, the same
    result as :class:`NumpyVectors` in less time. ``approximate`` walks a graph and returns
    most of the true neighbours for a fraction of the work::

        FaissVectors()                                    # exact, on the CPU
        FaissVectors(kind="approximate")                  # a graph, on the CPU
        FaissVectors(device="cuda")                       # exact, on the GPU

    ``device`` of ``cuda`` needs a FAISS built with GPU support, which is a different
    distribution from the one the ``ann`` extra installs. ``docs/retrieval.md`` §4.3 has the
    install. ``approximate`` on ``cuda`` is refused, because FAISS's GPU indexes do not
    include the graph.

    **An approximate index cannot delete.** FAISS builds the graph as vectors arrive and
    offers no way to take one out of it, so :meth:`remove` here marks the document and filters
    it out of every later search. That is correct and it grows more wasteful the more is
    removed, so a warning names :meth:`rebuild`, which builds the graph again from what is
    left. An exact index deletes outright and needs neither.

    **Searches of one store run one at a time.** FAISS is not safe to search while it is being
    written to, so the index is held for the search. :class:`NumpyVectors` takes a reference to
    its matrix and scores outside its lock, so its searches overlap.
    """

    def __init__(
        self,
        *,
        kind: str = "exact",
        device: str = "cpu",
        neighbours: int = HNSW_NEIGHBOURS,
    ) -> None:
        if kind not in ("exact", "approximate"):
            raise ConfigurationError(
                f"FaissVectors(kind={kind!r}) takes 'exact' or 'approximate'. 'exact' compares "
                f"against every vector and 'approximate' walks a graph, returning most of the "
                f"true neighbours for a fraction of the work."
            )
        if device not in ("cpu", "cuda"):
            raise ConfigurationError(f"FaissVectors(device={device!r}) takes 'cpu' or 'cuda'.")
        if kind == "approximate" and device == "cuda":
            raise ConfigurationError(
                "FaissVectors(kind='approximate', device='cuda') has no index behind it: "
                "FAISS's GPU indexes do not include the graph the approximate kind uses.\n"
                "Use FaissVectors(device='cuda') for an exact scan on the GPU, which compares "
                "a million vectors in single-digit milliseconds, or "
                "FaissVectors(kind='approximate') to walk the graph on the CPU."
            )
        self.kind = kind
        self.device = device
        self.neighbours = neighbours
        self._faiss = _require_faiss()
        self._numpy = _require_numpy("FaissVectors")
        self._index: Any = None
        self._gpu_resources: Any = None
        self._ids: list[str] = []
        self._positions: dict[str, int] = {}
        self._removed: set[int] = set()
        self._lock = threading.Lock()

    # -- building ---------------------------------------------------------------------

    def _new_index(self, dimensions: int) -> Any:
        faiss = self._faiss
        if self.device == "cuda":
            if faiss.get_num_gpus() < 1:
                raise ConfigurationError(
                    "FaissVectors(device='cuda') found no GPU. The FAISS installed here is "
                    "the CPU build, or the machine has no visible card.\n"
                    "Install a FAISS with GPU support (`pip uninstall -y faiss-cpu && pip "
                    "install faiss-gpu-cu12`, or conda's `faiss-gpu`), or pass device='cpu'."
                )
            self._gpu_resources = faiss.StandardGpuResources()
            return faiss.GpuIndexFlatIP(self._gpu_resources, dimensions)
        if self.kind == "approximate":
            return faiss.IndexHNSWFlat(dimensions, self.neighbours, faiss.METRIC_INNER_PRODUCT)
        return faiss.IndexFlatIP(dimensions)

    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None:
        """Add vectors under their identifiers. Both sequences are paired by position."""
        _check_pairing("FaissVectors", ids, vectors)
        if not ids:
            return
        added = self._numpy.asarray(vectors, dtype="float32")
        with self._lock:
            if self._index is None:
                self._index = self._new_index(int(added.shape[1]))
            elif int(added.shape[1]) != self._index.d:
                raise ConfigurationError(
                    f"FaissVectors holds vectors of {self._index.d} dimension(s) and was given "
                    f"{int(added.shape[1])}. Vectors are compared against one another, which "
                    f"requires one width.\n"
                    f"Embed the new documents with the model that embedded the rest."
                )
            self._index.add(added)
            for doc_id in ids:
                self._positions[doc_id] = len(self._ids)
                self._ids.append(doc_id)

    def remove(self, ids: Sequence[str]) -> None:
        """Drop the vectors held under these identifiers. One not held is ignored.

        An exact index deletes them. An approximate one marks them, warns, and filters them
        out of every later search until :meth:`rebuild` is called.
        """
        with self._lock:
            positions = sorted(self._positions[i] for i in ids if i in self._positions)
            if not positions:
                return
            if self.kind == "approximate":
                self._removed.update(positions)
                for doc_id in list(ids):
                    self._positions.pop(doc_id, None)
                warnings.warn(
                    f"{len(self._removed)} document(s) removed from an approximate "
                    f"FaissVectors are filtered out of each search rather than deleted, "
                    f"because FAISS builds the graph as vectors arrive and offers no way to "
                    f"take one out of it. Each search asks for that many extra candidates. "
                    f"Call store.rebuild() to build the graph again from what is left.",
                    SimpleAgentsWarning,
                    stacklevel=3,
                )
                return
            if self.device == "cpu":
                # A flat index compacts in place and keeps the order of what is left, so the
                # identifiers are the ones that were there with the removed positions taken
                # out. Measured against faiss-cpu 1.15.0.
                self._index.remove_ids(self._numpy.asarray(positions, dtype="int64"))
                kept = [doc_id for i, doc_id in enumerate(self._ids) if i not in set(positions)]
                self._ids = kept
                self._positions = {doc_id: i for i, doc_id in enumerate(kept)}
                return
            # A GPU index implements no removal, and an exact store that quietly kept
            # returning a deleted document would be worse than the cost of rebuilding it.
            self._rebuild(drop=set(positions))

    def rebuild(self) -> None:
        """Build the index again from the vectors still held, dropping what was removed.

        What an approximate index's :meth:`remove` warns about: the graph is built from what
        is left, so the removed vectors stop occupying a place in every search::

            store.remove(["s4121"])
            store.rebuild()
        """
        with self._lock:
            self._rebuild(drop=set())

    def _rebuild(self, *, drop: set[int]) -> None:
        """A fresh index over the vectors still held. The lock is already taken."""
        if self._index is None:
            return
        gone = self._removed | drop
        live = [i for i in range(len(self._ids)) if i not in gone]
        held = self._index.reconstruct_n(0, self._index.ntotal) if live else None
        ids = [self._ids[i] for i in live]
        # Built before the old one is dropped, so a rebuild that fails leaves the store
        # holding what it held.
        fresh = self._new_index(int(self._index.d))
        if held is not None:
            fresh.add(held[live])
        self._index = fresh
        self._removed = set()
        self._ids = ids
        self._positions = {doc_id: i for i, doc_id in enumerate(ids)}

    # -- searching --------------------------------------------------------------------

    def search(self, vector: Sequence[float], top_k: int) -> list[tuple[str, float]]:
        """The nearest vectors by inner product, best first. Empty where nothing was added."""
        if top_k < 1:
            return []
        query = self._numpy.asarray([vector], dtype="float32")
        with self._lock:
            if self._index is None or not self._ids:
                return []
            # Removed documents still occupy a row in an approximate index, so the search asks
            # for enough to fill `top_k` after they are filtered out.
            wanted = min(top_k + len(self._removed), self._index.ntotal)
            self._widen_the_search(wanted)
            scores, positions = self._index.search(query, wanted)
            found = [
                (self._ids[int(p)], float(s))
                for s, p in zip(scores[0], positions[0])
                if int(p) >= 0 and int(p) not in self._removed
            ]
        return found[:top_k]

    def _widen_the_search(self, wanted: int) -> None:
        """Let the graph walk at least as wide as the number of results asked for.

        FAISS explores ``efSearch`` candidates and returns the best ``k`` of them, and its
        default of 16 is below most of the depths a search asks for. Measured on 7,308
        documents at 1,024 dimensions against the exact answer: asking for 100 with the
        default returned 0.77 of the true neighbours in 0.18 ms, and 0.98 of them in 0.33 ms
        once the walk was this wide.
        """
        graph = getattr(self._index, "hnsw", None)
        if graph is not None and graph.efSearch < wanted:
            graph.efSearch = wanted

    def ids(self) -> list[str]:
        """Every identifier held, in the order it was added."""
        with self._lock:
            return [doc_id for i, doc_id in enumerate(self._ids) if i not in self._removed]

    def all_vectors(self) -> Any:
        """Every vector held as one ``float32`` matrix, in the order :meth:`ids` returns them.

        Read back out of the FAISS index, which is the only copy of them.
        """
        with self._lock:
            live = [i for i in range(len(self._ids)) if i not in self._removed]
            if self._index is None or not live:
                return self._numpy.zeros((0, 0), "float32")
            return self._index.reconstruct_n(0, self._index.ntotal)[live]

    @property
    def dimensions(self) -> int | None:
        """How wide the vectors are, or ``None`` where none was added."""
        return int(self._index.d) if self._index is not None else None

    def __len__(self) -> int:
        return len(self._ids) - len(self._removed)


def default_store() -> Any:
    """The store an index builds where the project names none.

    :class:`NumpyVectors` where numpy imports, :class:`VectorScan` otherwise::

        DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic())
        # vectors=default_store()

    Both are exact and return one order, so which one answered changes the time a search takes
    and not what comes back. A run records which one it was.
    """
    try:
        import numpy  # noqa: F401
    except ImportError:
        return VectorScan()
    return NumpyVectors()


def store_to_record(store: Any) -> dict[str, Any]:
    """How a run records the store that answered its searches.

    Names the class and whether its results are exact, so two figures measured on different
    stores are told apart rather than compared. Both keys are always present, and both are
    ``null`` for an index that holds no vectors::

        store_to_record(FaissVectors(kind="approximate"))
        # {'store': 'FaissVectors', 'exact': False}
    """
    if store is None:
        return {"store": None, "exact": None}
    approximate = getattr(store, "kind", "exact") == "approximate"
    return {"store": type(store).__name__, "exact": not approximate}


def _require_numpy(what: str) -> Any:
    try:
        import numpy

        return numpy
    except ImportError as exc:
        raise ConfigurationError(
            f"{what} needs numpy, which is not installed.\n"
            f"Install it with `pip install numpy`, or pass vectors=VectorScan(), which holds "
            f"the vectors as Python lists and needs no dependency."
        ) from exc


def _require_faiss() -> Any:
    try:
        import faiss

        return faiss
    except ImportError as exc:
        raise ConfigurationError(
            "FaissVectors needs the `ann` extra, which is not installed.\n"
            "Install it with `pip install 'simple-agents[ann]'` for the CPU build, or "
            "`pip install faiss-gpu-cu12` for one with GPU support. Use vectors=NumpyVectors()"
            " for an exact scan, which needs no extra and answers a corpus of a hundred "
            "thousand documents in under ten milliseconds."
        ) from exc


if hasattr(math, "sumprod"):  # Python 3.12 and later.

    def _dot(left: Sequence[float], right: Sequence[float]) -> float:
        return math.sumprod(left, right)

else:  # pragma: no cover - exercised on Python 3.11 only.

    def _dot(left: Sequence[float], right: Sequence[float]) -> float:
        return sum(map(operator.mul, left, right))
