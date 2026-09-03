"""What a saved :class:`~simple_agents.builtins.DocumentIndex` is on disk, and how it is read.

Two files. ``corpus.index`` is JSON holding the documents, the stopwords, the analyzer that
cut them into words, what embedded them, and the identifiers of the vectors in order.
``corpus.index.vec`` holds those vectors as raw ``float32``, since a million 768-dimension
vectors are 3 GB and do not fit in a JSON string. Both move together.

``DocumentIndex.save`` and ``DocumentIndex.load`` are the surface a project uses; these are
what they call::

    written = write_index(index, "corpus.index")
    parts = read_index("corpus.index", embeddings=embedder)
"""

from __future__ import annotations

import base64
import json
import sys
from array import array
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..errors import ConfigurationError
from ..models import ModelIdentity

__all__ = [
    "ANALYZER",
    "INDEX_FORMAT_VERSION",
    "VECTOR_FILE_SUFFIX",
    "read_index",
    "refuse_mismatch",
    "write_index",
]

INDEX_FORMAT_VERSION = "2.0"
"""What :func:`write_index` writes. :func:`read_index` also reads ``1.0``.

``2.0`` writes the vectors to a binary file beside the JSON one. ``1.0`` packed them into the
JSON as base64, which a corpus of a million vectors does not fit into.
"""

ANALYZER = "whole-word"
"""How the index cuts text into words, recorded in every index file and in every run.

Lowercased, split on anything that is not a letter or a digit, with nothing stemmed. A file
written under one analyzer and searched under another matches on different words, so the name
is stored beside the vectors and a mismatch is refused.
"""

VECTOR_FILE_SUFFIX = ".vec"
"""What :func:`write_index` appends to the index path for the vector file."""

WRITING_SUFFIX = ".writing"
"""What a file being written is called until it is complete and moved into place."""


def write_index(index: Any, path: str | Path) -> Path:
    """Write one index to ``path`` and its vectors beside it. Returns the JSON file's path.

    **Both files are written beside the real ones and moved into place at the end.** An index
    is two files that have to agree, and a save that failed after writing one of them would
    leave the corpus that was already there unreadable. Embedding a corpus is the expensive
    thing this file exists to avoid repeating, so a failed save leaves it exactly as it was.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    sidecar = target.with_name(target.name + VECTOR_FILE_SUFFIX)
    store = index.vectors
    order: list[str] = []
    width: int | None = None
    pending = sidecar.with_name(sidecar.name + WRITING_SUFFIX)
    try:
        if store is not None and len(store):
            _require_a_readable_store(store)
            order = list(store.ids())
            width = _write_vectors(pending, store.all_vectors())
            _check_what_was_written(order, width, pending)
        written = target.with_name(target.name + WRITING_SUFFIX)
        written.write_text(
            json.dumps(
                {
                    "format_version": INDEX_FORMAT_VERSION,
                    "documents": index.documents,
                    "stopwords": sorted(index.stopwords),
                    "analyzer": ANALYZER,
                    "embedded_by": (index.embedded_by.to_manifest() if index.embedded_by else None),
                    "store": type(store).__name__ if store is not None else None,
                    "order": order,
                    "dimensions": width,
                    "byte_order": sys.byteorder,
                    "vectors": sidecar.name if order else None,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except BaseException:
        pending.unlink(missing_ok=True)
        raise
    if order:
        pending.replace(sidecar)
    else:
        # An index saved over one that had vectors leaves no stale file behind it.
        sidecar.unlink(missing_ok=True)
    written.replace(target)
    return target


def read_index(path: str | Path, *, embeddings: Any = None) -> dict[str, Any]:
    """The parts of a saved index: ``documents``, ``stopwords``, ``embedded_by``, ``vectors``.

    ``vectors`` is ``(ids, vectors)`` and ``None`` where the file carried none. ``embeddings``
    is the client the queries will be embedded with, checked against what embedded the file::

        parts = read_index("corpus.index", embeddings=embedder)
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
    _check_format(raw, source)
    _check_analyzer(raw, source)
    stored = raw.get("embedded_by")
    identity = ModelIdentity(**stored) if stored else None
    if identity is not None and embeddings is not None:
        refuse_mismatch(identity, embeddings.identity(), str(source))
    order = list(raw.get("order") or ())
    vectors = (order, _read_vectors(raw, source)) if raw.get("vectors") and order else None
    return {
        "documents": dict(raw.get("documents") or {}),
        "stopwords": frozenset(raw.get("stopwords") or ()),
        "embedded_by": identity,
        "vectors": vectors,
    }


def refuse_mismatch(
    stored: ModelIdentity, asked: ModelIdentity, where: str, *, embedding: str = "query"
) -> None:
    """Refuse text embedded by a different model than the corpus was.

    ``embedding`` names what was about to be embedded, so the message points at the call the
    reader made: a ``query`` on a search, and ``documents`` on an add or a replace.
    """
    if (stored.backend, stored.request_model) == (asked.backend, asked.request_model) and (
        stored.model_revision == asked.model_revision
        or stored.model_revision is None
        or asked.model_revision is None
    ):
        return
    raise ConfigurationError(
        f"The vectors in {where} were made by {stored.request_model!r}"
        f"{f'@{stored.model_revision}' if stored.model_revision else ''} and the "
        f"{embedding} would be embedded by {asked.request_model!r}"
        f"{f'@{asked.model_revision}' if asked.model_revision else ''}. Vectors from two "
        f"models occupy different spaces, so comparing them returns confident nonsense with "
        f"nothing raised.\n"
        f"Use the model the corpus was embedded with, or re-embed the corpus with the new one "
        f"and save it again: DocumentIndex.from_texts(corpus, embeddings=new).save(path)."
    )


def has_method(store: Any, name: str) -> bool:
    """Whether a vector store offers one of the optional methods, as a method.

    A store holding a list under the same name is not offering the method, and calling the
    list would raise from inside the library rather than at the store that named it.
    """
    return callable(getattr(store, name, None))


def _require_a_readable_store(store: Any) -> None:
    if not (has_method(store, "ids") and has_method(store, "all_vectors")):
        raise ConfigurationError(
            f"The vector store on this index, {type(store).__name__}, declares no ids() and "
            f"all_vectors(), so what it holds cannot be written to a file. Saving anyway "
            f"would write an index that re-embeds the whole corpus when it is loaded.\n"
            f"Add `def ids(self) -> list[str]` and `def all_vectors(self)` to it, or use "
            f"vectors=NumpyVectors(), VectorScan() or FaissVectors(), which all have both."
        )


def _write_vectors(target: Path, vectors: Any) -> int:
    """Write the vectors as raw ``float32``. Returns how wide they are.

    A numpy matrix is written whole, so a corpus of a million vectors reaches the file without
    a copy of it in Python lists first. Anything else is written a row at a time.
    """
    if hasattr(vectors, "dtype") and hasattr(vectors, "tobytes"):
        matrix = vectors.astype("float32", copy=False)
        target.write_bytes(matrix.tobytes())
        return int(matrix.shape[1])
    width = len(vectors[0])
    with target.open("wb") as handle:
        for vector in vectors:
            handle.write(array("f", vector).tobytes())
    return width


def _read_vectors(raw: Mapping[str, Any], source: Path) -> Any:
    """The vectors a saved index holds, from the file beside it or from the JSON itself.

    **A ``float32`` matrix where numpy is installed**, and a list of lists otherwise. The file
    is the size of the matrix, and a list of Python floats is about nine times that: 7,308
    vectors of 1,024 dimensions are 30 MB on disk and 269 MB as lists, measured. A corpus of a
    million, which is the size this format exists for, does not fit either way as lists.
    """
    width = int(raw["dimensions"])
    order = list(raw["order"])
    named = str(raw["vectors"])
    if raw.get("format_version") == "1.0":
        packed = base64.b64decode(named)
    else:
        sidecar = source.with_name(named)
        try:
            packed = sidecar.read_bytes()
        except OSError as exc:
            raise ConfigurationError(
                f"The index at {source} records its vectors in {sidecar.name}, which could "
                f"not be read: {exc}.\n"
                f"An index is two files and both move together. Copy {sidecar.name} beside "
                f"it, or rebuild the index with DocumentIndex.from_texts(corpus, "
                f"embeddings=...).save({str(source)!r})."
            ) from exc
    flat = array("f")
    flat.frombytes(packed)
    if raw.get("byte_order", sys.byteorder) != sys.byteorder:
        flat.byteswap()
    if len(flat) != len(order) * width:
        raise ConfigurationError(
            f"The index at {source} names {len(order)} document(s) at {width} dimension(s), "
            f"which is {len(order) * width} numbers, and its vectors hold {len(flat)}.\n"
            f"The two files are from different saves. Rebuild the index with "
            f"DocumentIndex.from_texts(corpus, embeddings=...).save({str(source)!r})."
        )
    try:
        import numpy
    except ImportError:
        return [list(flat[i * width : (i + 1) * width]) for i in range(len(order))]
    return numpy.frombuffer(flat, dtype="float32").reshape(len(order), width)


def _check_what_was_written(order: Sequence[str], width: int | None, sidecar: Path) -> None:
    """Refuse a store whose identifiers and vectors do not line up, before the file is used."""
    written = sidecar.stat().st_size // 4
    if width and written != len(order) * width:
        raise ConfigurationError(
            f"The vector store returned {len(order)} identifier(s) and {written // width} "
            f"vector(s) of {width} dimension(s). ids() and all_vectors() are paired by "
            f"position, so a mismatch would file a vector under another document's "
            f"identifier.\n"
            f"Fix the store to return them in one order."
        )


READABLE_FORMATS = ("1.0", "2.0")
"""The index file versions :func:`read_index` understands, oldest first."""


def _check_format(raw: Mapping[str, Any], source: Path) -> None:
    """Refuse a file written in a version this library does not read."""
    version = str(raw.get("format_version") or "")
    if version not in READABLE_FORMATS:
        raise ConfigurationError(
            f"The index at {source} is format {version or 'unstated'!r} and this version of "
            f"the library reads {' and '.join(READABLE_FORMATS)}. What the file holds and "
            f"where it holds it are what a version says.\n"
            f"Read it with the library version that wrote it, or rebuild the index: "
            f"DocumentIndex.from_texts(corpus, embeddings=...).save({str(source)!r})."
        )


def _check_analyzer(raw: Mapping[str, Any], source: Path) -> None:
    """Refuse an index file whose words were cut by an analyzer this version does not have."""
    stored = raw.get("analyzer", ANALYZER)
    if stored != ANALYZER:
        raise ConfigurationError(
            f"The index at {source} was written with the {stored!r} analyzer and this version "
            f"of the library has {ANALYZER!r}. An analyzer decides what a word is, so the "
            f"stored postings match on different words than a query would.\n"
            f"Rebuild the index with DocumentIndex.from_texts(corpus, embeddings=...).save("
            f"{str(source)!r})."
        )
