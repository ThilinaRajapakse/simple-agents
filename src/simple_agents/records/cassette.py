"""Recording model and tool calls, and replaying them with no network.

A cassette stores every external call a run makes, keyed by the content of the request. In
``replay`` mode a matching request is served from the file and nothing leaves the process,
which is what lets an evaluation run in CI with no credentials and no spend (FT-21), and what
lets it repeat a tool call without repeating what the tool does (FT-20).

A model call's key covers the model identity, the messages, the sampling parameters, the tools
offered, and the seed. A tool call's covers its name, its version, its arguments, and how many
times that same call has already been made in this run, so a tool answering differently at two
moments replays as two answers rather than one. A request that differs in any of that has no
entry, and replay raises :class:`CassetteMiss` naming what changed. A recorded response answers
the request it was recorded against, so serving it for a different request would report a
result the current code never produced.

A tool taking a handle is re-run during replay instead of being stored; ``docs/tools.md``
covers why and what such a tool may do.

A model call's seed derives from the run's, so a replay has to run at the seed the recording
ran at. Every entry records it, and a run replaying with no seed of its own takes it from the
file.

Four modes, and the default is a recording into the run's own directory::

    Cassette.into_run()                     # live calls, recorded beside the trajectory
    Cassette.off()                          # live calls, nothing stored
    Cassette.record("cassettes/qa.jsonl")   # live calls, appended to the file
    Cassette.replay("cassettes/qa.jsonl")   # no live calls, served from the file
    Cassette.update("cassettes/qa.jsonl")   # served where there is an entry, live where not

Recording appends and never overwrites. An edited prompt hashes to a different key, so a
collision means the identical request was made again; if it came back different, both
responses are kept and the manifest counts the divergence. Replay serves the first response
recorded for a key, so a replay is reproducible and the earliest run stays replayable.
Deleting the file re-records from nothing.

``update`` is for iterating on a pipeline: editing one node's prompt leaves every earlier
node's calls on file and re-runs only what changed. It never serves a stale response, because
an edited request hashes to a key with no entry and is answered live. An evaluation refuses it,
so a reported number comes from a run that was all live or all replayed rather than a mixture.

A cassette is shared by every run made through one envelope, including runs on separate
threads, so its file and its index are guarded by a lock. The lock covers one process:
two processes recording into one file are not coordinated, and each reads the file once.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..embeddings import EmbeddingResponse, RerankResponse, RerankScore
from ..errors import CallerFacingError, ConfigurationError, ModelFacingError, Throttled
from ..models import ModelResponse, RateLimit, Reasoning, TokenUsage, ToolCallRequest
from ..schema import Unknown

__all__ = ["Cassette", "CassetteMode", "CassetteEntry", "CassetteMiss", "StoreOutcome"]

MAX_REPORTED_DIFFERENCES = 6

REDACTION_MARKER = re.compile(r"\[redacted:[^\]]*\]")
"""What every rule in ``simple_agents.redaction`` leaves behind, whatever it replaced."""

CASSETTE_NAME = "cassette.jsonl"
"""What the default recording is called inside a run's own directory."""


class CassetteMode(str, Enum):
    """Whether calls go to the backend, to the file, or to the file and then the backend."""

    OFF = "off"
    RECORD = "record"
    REPLAY = "replay"
    UPDATE = "update"


class CassetteMiss(CallerFacingError):
    """A replayed request has no recorded response.

    Raised rather than passed to the model: a run that cannot replay one of its calls is not
    the run that was recorded, and continuing would produce a trajectory describing neither.
    """


@dataclass(frozen=True, slots=True)
class CassetteEntry:
    """One recorded call.

    ``request`` is the keyed content after redaction. ``response`` is what the backend
    returned, in the shape the caller reconstructs from.
    """

    key: str
    kind: str
    node_id: str
    call_index: int
    recorded_at: str
    request: Mapping[str, Any]
    response: Mapping[str, Any]
    item_index: int | None = None
    """The fan-out item this call belongs to, and ``None`` outside one. ``call_index`` counts
    within the item where this is set, so the two together locate a call in a fan-out whose
    items overlapped."""
    run_id: str | None = None
    """The run that recorded this entry. ``None`` in a file written before it was recorded."""
    run_seed: int | None = None
    """The seed of the run that recorded this entry. A model call's seed derives from it and is
    part of the key, so this is what a replay of the entry has to run at. ``None`` in a file
    written before it was recorded."""
    duration_ms: int | None = None
    """How long the live call took, for a replay to price a compute basis on. ``None`` on a
    tool call, and in a file written before it was recorded."""
    stream: Mapping[str, Any] | None = None
    """Where the chunks fell on a call that streamed: ``cuts``, which are offsets into the
    response's content, and ``first_chunk_ms``. ``None`` on a call that did not stream, and in
    a file written before it was recorded, whose content replays as one piece."""

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "node_id": self.node_id,
            "call_index": self.call_index,
            "item_index": self.item_index,
            "recorded_at": self.recorded_at,
            "run_id": self.run_id,
            "run_seed": self.run_seed,
            "duration_ms": self.duration_ms,
            "stream": dict(self.stream) if self.stream is not None else None,
            "request": dict(self.request),
            "response": dict(self.response),
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> CassetteEntry:
        return cls(
            key=raw["key"],
            kind=raw["kind"],
            node_id=raw.get("node_id", ""),
            call_index=raw.get("call_index", 0),
            item_index=raw.get("item_index"),
            recorded_at=raw.get("recorded_at", ""),
            request=raw.get("request", {}),
            response=raw.get("response", {}),
            run_id=raw.get("run_id"),
            run_seed=raw.get("run_seed"),
            duration_ms=raw.get("duration_ms"),
            stream=raw.get("stream"),
        )


@dataclass(frozen=True, slots=True)
class StoreOutcome:
    """What happened to an entry offered to a cassette.

    ``written`` is false when this exact response was already on file. ``diverged`` is true
    when the key already held a different one, which means the backend answered the same
    request two ways and both are now kept. The run manifest counts both.
    """

    written: bool
    diverged: bool


@dataclass(slots=True)
class Cassette:
    """Where recorded calls are stored, and whether they are being written or read.

    Construct one with :meth:`off`, :meth:`record`, or :meth:`replay` and pass it to a
    ``RunEnvelope``. The same cassette serves every run made through that envelope, so an
    evaluation records once and replays for every rollout after::

        env = RunEnvelope(run_dir="runs/", cassette=Cassette.replay("cassettes/qa.jsonl"))
    """

    mode: CassetteMode = CassetteMode.OFF
    path: Path | None = None

    _variants: dict[str, list[CassetteEntry]] | None = field(
        default=None, init=False, repr=False, compare=False
    )
    _lock: threading.RLock = field(
        default_factory=threading.RLock, init=False, repr=False, compare=False
    )

    @classmethod
    def into_run(cls) -> Cassette:
        """Live calls, recorded into the run's own directory. The default.

        The path is ``<run_dir>/<run_id>/cassette.jsonl`` and is filled in when the run starts,
        since the run's id does not exist before then. Until then :attr:`path` is ``None``::

            RunEnvelope(run_dir="runs/")                            # this
            RunEnvelope(run_dir="runs/", cassette=Cassette.off())   # nothing recorded

        The recording is kept or dropped with the trajectory's payloads, on the one decision
        :meth:`Trajectory.keeps` makes for the run, so a sampled project's cassette does not
        outlive the payloads its trajectory dropped.
        """
        return cls(mode=CassetteMode.RECORD, path=None)

    @classmethod
    def off(cls) -> Cassette:
        """Live calls, nothing recorded.

        Every run records by default, so this is what states that a run's prompts and responses
        are not to be written. It leaves the trajectory alone, which carries them too;
        ``Trajectory.sampled(0.0)`` is what keeps payloads off disk entirely.
        """
        return cls(mode=CassetteMode.OFF, path=None)

    @classmethod
    def record(cls, path: str | os.PathLike[str]) -> Cassette:
        """Live calls, each appended to ``path``, which must not already hold a recording.

        Replay serves the first response recorded for a key, so a second recording into a file
        that already holds one is written and never read. Recording a changed run over an
        earlier one is therefore refused: pass a new path, or :meth:`update` to fill in the
        calls the file does not already have.
        """
        path = Path(path)
        if path.exists() and path.stat().st_size > 0:
            raise ConfigurationError(
                f"Cassette.record({str(path)!r}) was given a file that already holds a "
                f"recording. Replay serves the first response recorded for each request, so "
                f"the calls this run made would be written into the file and never read, and "
                f"a later replay would return the earlier run's answers under this run's "
                f"name.\n"
                f"Record to a new path, one per evaluation, so each recording replays the run "
                f"it was made from. Cassette.update({str(path)!r}) instead serves what the "
                f"file already holds and records only the calls it does not."
            )
        return cls(mode=CassetteMode.RECORD, path=path)

    @classmethod
    def replay(cls, path: str | os.PathLike[str]) -> Cassette:
        """Calls served from ``path``. A request with no entry raises :class:`CassetteMiss`."""
        return cls(mode=CassetteMode.REPLAY, path=Path(path))

    @classmethod
    def update(cls, path: str | os.PathLike[str]) -> Cassette:
        """Served from ``path`` where there is an entry, called live and recorded where not.

        For iterating on a pipeline. Editing one node's prompt leaves every earlier node's
        calls on file and re-runs only what changed, where re-recording would pay for the
        whole run again::

            env = RunEnvelope(run_dir="runs/", cassette=Cassette.update("cassettes/qa.jsonl"))

        A recorded response is never served for a request it was not recorded against: an
        edited request hashes to a key with no entry and is answered live. An evaluation
        refuses this mode, so a reported number comes from a run that was all live or all
        replayed rather than a mixture of the two.
        """
        return cls(mode=CassetteMode.UPDATE, path=Path(path))

    def for_run(self, root: str | os.PathLike[str]) -> Cassette:
        """This cassette with the default recording's path filled in, from the run's directory.

        Called once at run start, where ``root`` is the run's own directory::

            cassette = envelope.cassette.for_run(paths.root)

        A cassette that names a path is returned unchanged, so one file shared by every run
        made through an envelope stays one file. A default recording becomes a new cassette per
        run, since each run's directory is its own. Two runs written into one directory append,
        which is what the trajectory beside it does.
        """
        if not self.awaiting_path:
            return self
        return Cassette(mode=CassetteMode.RECORD, path=Path(root) / CASSETTE_NAME)

    @property
    def awaiting_path(self) -> bool:
        """Whether this is the default recording, waiting for the run to name its file.

        True between :meth:`into_run` and :meth:`for_run`, and false everywhere else. A caller
        reading ``path`` before the run starts reads ``None``, which is why an operation that
        needs a file of its own tests this and says what to pass.
        """
        return self.mode is CassetteMode.RECORD and self.path is None

    @property
    def is_replaying(self) -> bool:
        """Whether a request with no entry is a failure rather than a live call."""
        return self.mode is CassetteMode.REPLAY

    @property
    def is_recording(self) -> bool:
        """Whether a live call is written to the file."""
        return self.mode in (CassetteMode.RECORD, CassetteMode.UPDATE)

    @property
    def serves_hits(self) -> bool:
        """Whether a request already on file is answered from it rather than called."""
        return self.mode in (CassetteMode.REPLAY, CassetteMode.UPDATE)

    @property
    def enabled(self) -> bool:
        return self.mode is not CassetteMode.OFF

    # -- reading --------------------------------------------------------------------------

    def variants(self) -> dict[str, list[CassetteEntry]]:
        """Every entry in the file, grouped by key, in the order recorded. Read once and held.

        A key with more than one entry is a request the backend answered differently on
        different occasions. The count is the evidence for whether a backend reproduces its
        own sampling::

            {k: len(v) for k, v in cassette.variants().items() if len(v) > 1}
        """
        with self._lock:
            if self._variants is None:
                self._variants = _load(self.path) if self.path is not None else {}
            return self._variants

    def entries(self) -> dict[str, CassetteEntry]:
        """The entry replay serves for each key: the first one recorded."""
        with self._lock:
            return {key: group[0] for key, group in self.variants().items()}

    def recorded_seeds(self) -> set[int]:
        """Every run seed this file names. Empty for one recorded before seeds were stored."""
        return {
            entry.run_seed
            for group in self.variants().values()
            for entry in group
            if entry.run_seed is not None
        }

    @property
    def recorded_seed(self) -> int | None:
        """The seed a replay of this file runs at, where the file names one::

            Cassette.replay("cassettes/qa.jsonl").recorded_seed   # 1927391078

        ``None`` where the file names none, which is one recorded before seeds were stored, and
        where it names several, which is a file holding an evaluation's rollouts.
        """
        seeds = self.recorded_seeds()
        return next(iter(seeds)) if len(seeds) == 1 else None

    def lookup(self, key: str) -> CassetteEntry | None:
        """What replay serves for ``key``, or ``None``.

        The first response recorded, so a replay returns the same answer every time and a
        later recording into the same file cannot change what an earlier run replays.
        """
        with self._lock:
            group = self.variants().get(key)
            return group[0] if group else None

    def nearest(
        self, node_id: str, call_index: int, kind: str, item_index: int | None = None
    ) -> CassetteEntry | None:
        """The entry a missed request was most likely recorded as.

        Used to report what changed. Prefers the same call of the same fan-out item, then any
        call of that item, then any call of the same kind in that node. Comparing across items
        would point at a call built from different inputs, which is a worse diff than a call of
        the same item at a different position.
        """
        candidates = [e for e in self.entries().values() if e.node_id == node_id and e.kind == kind]
        if not candidates:
            return None
        same_item = [e for e in candidates if e.item_index == item_index]
        for entry in same_item:
            if entry.call_index == call_index:
                return entry
        pool = same_item or candidates
        return min(pool, key=lambda e: abs(e.call_index - call_index))

    # -- writing --------------------------------------------------------------------------

    def store(self, entry: CassetteEntry) -> StoreOutcome:
        """Append an entry, reporting what happened to it.

        Nothing is ever overwritten. An identical response already recorded for this key is
        not written again; a different one is appended alongside it, so the file keeps the
        evidence that the backend answered the same request two ways::

            outcome = cassette.store(entry)
            outcome.written     # False when this exact response was already on file
            outcome.diverged    # True when the key had a different response already

        The read, the append and the index update happen under one lock, and both facts are
        decided inside it, so rollouts running on separate threads through one envelope
        neither interleave nor miscount.

        Raises ``CallerFacingError`` on a recording that has no file yet, which is a default
        cassette given to a run without :meth:`for_run`. Storing nothing and reporting success
        would leave a run that recorded nothing looking like one that had.
        """
        if self.awaiting_path:
            raise CallerFacingError(
                "This cassette is the default recording and has no file yet, so there is "
                "nowhere to store the call. A run resolves it with "
                "cassette.for_run(paths.root) before its first call. Reaching here means a "
                "run was driven with an unresolved cassette."
            )
        if self.path is None:
            return StoreOutcome(written=False, diverged=False)
        with self._lock:
            recorded = self.variants().get(entry.key, [])
            if any(existing.response == entry.response for existing in recorded):
                return StoreOutcome(written=False, diverged=False)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry.to_json(), ensure_ascii=False, default=str) + "\n")
            self.variants().setdefault(entry.key, []).append(entry)
            return StoreOutcome(written=True, diverged=bool(recorded))

    def discard(self) -> bool:
        """Delete the recorded file, reporting whether there was one.

        What a run does at close to a default recording whose payloads the trajectory dropped,
        so the two copies of what was said go together. The in-memory index is cleared with it,
        so a cassette asked for its entries afterwards reports none rather than the entries of
        a file that is gone.
        """
        with self._lock:
            if self.path is None or not self.path.exists():
                return False
            self.path.unlink()
            self._variants = None
            return True

    def to_manifest(self) -> dict[str, Any]:
        """The cassette as the run manifest records it. Counts are added by the run.

        ``dropped`` is ``null`` while the file is there and names the reason where the run
        deleted it, so a manifest counting recorded calls says whether they are still on disk.
        """
        return {
            "mode": self.mode.value,
            "path": str(self.path) if self.path else None,
            "dropped": None,
        }


def model_call_key(
    *,
    backend: str,
    request_model: str,
    model_revision: str | None,
    messages: list[dict[str, Any]],
    params: Mapping[str, Any],
) -> str:
    """The key for one model call.

    Model identity is part of the key. Without it, switching models would replay the previous
    model's responses and report them as the new one's, which is the attribution failure FT-14
    exists to catch. ``params`` carries the sampling parameters, the offered tools and the
    output schema, so a changed tool description is a different request.
    """
    return _hash(
        {
            "kind": "model_call",
            "backend": backend,
            "request_model": request_model,
            "model_revision": model_revision,
            "messages": messages,
            "params": dict(params),
        }
    )


def embedding_key(
    *,
    backend: str,
    request_model: str,
    model_revision: str | None,
    texts: Sequence[str],
) -> str:
    """The key for one embedding call.

    Model identity is part of the key for the reason it is part of a model call's: vectors from
    two models are not comparable, so replaying one model's vectors under another's name would
    return confident nonsense. An embedding is a function of the model and the texts alone, so
    nothing else is keyed and no occurrence count is needed.
    """
    return _hash(
        {
            "kind": "embedding",
            "backend": backend,
            "request_model": request_model,
            "model_revision": model_revision,
            "texts": list(texts),
        }
    )


def rerank_key(
    *,
    backend: str,
    request_model: str,
    model_revision: str | None,
    query: str,
    documents: Sequence[str],
) -> str:
    """The key for one reranking call.

    A rerank reads the query and the documents together, so both are keyed, in the order they
    were given: a reranker returns a score per position and the caller pairs them by index.
    """
    return _hash(
        {
            "kind": "rerank",
            "backend": backend,
            "request_model": request_model,
            "model_revision": model_revision,
            "query": query,
            "documents": list(documents),
        }
    )


def _tokens_from_record(raw: Mapping[str, Any]) -> TokenUsage:
    """A token breakdown from what a cassette entry stored."""
    return TokenUsage(
        input_uncached=raw.get("input_uncached", 0),
        input_cache_read=raw.get("input_cache_read", 0),
        input_cache_write=raw.get("input_cache_write", 0),
        cache_ttl=raw.get("cache_ttl"),
        output=raw.get("output", 0),
        output_reasoning=raw.get("output_reasoning"),
    )


def encode_embedding_response(response: EmbeddingResponse) -> dict[str, Any]:
    """An embedding response in the shape a cassette entry stores."""
    return {
        "vectors": response.vectors,
        "backend": response.backend,
        "request_model": response.request_model,
        "response_model": response.response_model,
        "model_revision": response.model_revision,
        "tokens": response.tokens.to_record(),
        "provider": dict(response.provider),
    }


def decode_embedding_response(raw: Mapping[str, Any]) -> EmbeddingResponse:
    """Rebuild an embedding response from a cassette entry."""
    return EmbeddingResponse(
        vectors=[[float(x) for x in v] for v in raw.get("vectors") or []],
        backend=raw.get("backend") or "self_hosted",  # type: ignore[arg-type]
        request_model=str(raw.get("request_model") or ""),
        response_model=raw.get("response_model"),
        model_revision=raw.get("model_revision"),
        tokens=_tokens_from_record(raw.get("tokens") or {}),
        provider=dict(raw.get("provider") or {}),
    )


def encode_rerank_response(response: RerankResponse) -> dict[str, Any]:
    """A reranking response in the shape a cassette entry stores."""
    return {
        "scores": [{"index": s.index, "score": s.score} for s in response.scores],
        "backend": response.backend,
        "request_model": response.request_model,
        "response_model": response.response_model,
        "model_revision": response.model_revision,
        "tokens": response.tokens.to_record(),
        "provider": dict(response.provider),
    }


def decode_rerank_response(raw: Mapping[str, Any]) -> RerankResponse:
    """Rebuild a reranking response from a cassette entry."""
    return RerankResponse(
        scores=[
            RerankScore(index=int(s.get("index", 0)), score=float(s.get("score", 0.0)))
            for s in raw.get("scores") or []
        ],
        backend=raw.get("backend") or "self_hosted",  # type: ignore[arg-type]
        request_model=str(raw.get("request_model") or ""),
        response_model=raw.get("response_model"),
        model_revision=raw.get("model_revision"),
        tokens=_tokens_from_record(raw.get("tokens") or {}),
        provider=dict(raw.get("provider") or {}),
    )


def tool_call_key(
    *,
    node_id: str,
    tool_name: str,
    tool_version: str | None,
    arguments: Mapping[str, Any],
    occurrence: int,
    item_index: int | None = None,
) -> str:
    """The key for one tool call.

        ``occurrence`` counts how many times this same name, version and argument set has already
        been called in this node, so a tool that answers differently at two moments records two
        entries and replays each in turn. Without it a clock called twice would replay its first
        reading twice and a trajectory would describe a run that did not happen.

        ``node_id`` is in the key so that count belongs to one node. Counted across the run, a call
        added to one node renumbers another node's calls and every entry recorded for them stops
        resolving, and two nodes whose calls overlap take their numbers in whichever order they
        finished.

    ``item_index`` is in the key for the same reason ``node_id`` is: a fan-out's items overlap,
        so two of them making one call take their occurrences in whichever order they arrived, and a
        replay that interleaved differently would hand each item the other's answer. Absent from the
        key outside a fan-out, so a call recorded before this existed keeps the key it had.

        A model call carries the same distinction already: its seed is derived from the index of
        the call within the node and the item, and the seed is in the key.
    """
    material: dict[str, Any] = {
        "kind": "tool_call",
        "node_id": node_id,
        "tool_name": tool_name,
        "tool_version": tool_version,
        "arguments": dict(arguments),
        "occurrence": occurrence,
    }
    if item_index is not None:
        material["item_index"] = item_index
    return _hash(material)


def miss_error(
    *,
    cassette: Cassette,
    kind: str,
    node_id: str,
    call_index: int,
    request: Mapping[str, Any],
    item_index: int | None = None,
) -> CassetteMiss:
    """The error raised when a replayed request has no entry, naming what differs.

    The comparison is against the nearest recorded request in the same node, so the message
    points at the edit that invalidated the entry rather than only reporting the key.
    """
    nearest = cassette.nearest(node_id, call_index, kind, item_index)
    label = "call" if kind == "model_call" else "tool call"
    where = (
        f"node {node_id!r}" if item_index is None else (f"item {item_index} of node {node_id!r}")
    )
    header = f"No recorded response for {label} {call_index} of {where} in {cassette.path}."

    if nearest is None:
        detail = (
            "Nothing was recorded for this node at all. Either the cassette was recorded "
            "from a different pipeline, or this node is new."
        )
    else:
        differences = describe_differences(request, nearest.request)
        if differences:
            listed = "\n".join(f"  {line}" for line in differences)
            detail = f"The nearest recorded request for this node differs in:\n{listed}"
        else:
            detail = (
                "The nearest recorded request for this node matches on every compared field, "
                "which means the difference is in a value that was redacted before storage."
            )
        detail += _seed_note(nearest, differences)
        detail += _redaction_note(request, nearest.request)

    return CassetteMiss(
        f"{header}\n\n{detail}\n\n"
        f"A recorded response answers the request it was recorded against, so replaying it "
        f"here would report a result the current code does not produce. Re-record with "
        f"Cassette.record({str(cassette.path)!r}), or revert the change."
    )


def _seed_note(nearest: CassetteEntry, differences: list[str]) -> str:
    """What to pass, where the request differs in its seed.

    The seed on a request is derived from the run seed and is not the value a caller passes,
    so a message reporting only the difference names a number that cannot be used.
    """
    if nearest.run_seed is None or not any(d.startswith("params.seed") for d in differences):
        return ""
    return (
        f"\n\nThat entry was recorded at run seed {nearest.run_seed}. A call's seed derives "
        f"from the run's, so pass seed={nearest.run_seed}, or pass no seed and it is taken "
        f"from the cassette."
    )


def _redaction_note(current: Mapping[str, Any], recorded: Mapping[str, Any]) -> str:
    """What to do where a redacted value is what the two requests differ by.

    A tool result carrying a credential is stored redacted, so a replay serves the marker where
    the live run had the value. Every request built from that result afterwards differs from the
    one recorded, and without this the message reports a length change nothing explains.
    """
    if not _differs_by_redaction(current, recorded):
        return ""
    return (
        "\n\nOne of those differences is a redaction marker. A tool result carrying a "
        "credential is stored redacted, so the replay served the marker where the recorded run "
        "had the value, and every request built from that result afterwards is a different "
        "request. Have the tool take the credential as a SecretStr and return only what the "
        "model needs (`docs/tools.md` §1.6), so that what the run uses and what the file holds "
        "are the same."
    )


def _differs_by_redaction(current: Any, recorded: Any) -> bool:
    """Whether two keyed requests differ at a leaf where either side holds a marker."""
    if isinstance(current, Mapping) and isinstance(recorded, Mapping):
        return any(
            _differs_by_redaction(current.get(key), recorded.get(key))
            for key in dict.fromkeys([*recorded, *current])
        )
    if isinstance(current, list) and isinstance(recorded, list):
        return any(_differs_by_redaction(c, r) for c, r in zip(current, recorded))
    if current == recorded:
        return False
    return any(
        isinstance(side, str) and REDACTION_MARKER.search(side) for side in (current, recorded)
    )


def describe_differences(current: Mapping[str, Any], recorded: Mapping[str, Any]) -> list[str]:
    """Field paths where two keyed requests differ, most specific first.

    Long strings are reported by length rather than quoted, so a message about a prompt edit
    stays readable.
    """
    found: list[str] = []
    _diff(current, recorded, "", found)
    return found[:MAX_REPORTED_DIFFERENCES]


def _diff(current: Any, recorded: Any, path: str, found: list[str]) -> None:
    if len(found) >= MAX_REPORTED_DIFFERENCES:
        return
    if isinstance(current, Mapping) and isinstance(recorded, Mapping):
        for key in dict.fromkeys([*recorded, *current]):
            _diff(current.get(key), recorded.get(key), f"{path}.{key}" if path else str(key), found)
        return
    if isinstance(current, list) and isinstance(recorded, list):
        if len(current) != len(recorded):
            found.append(f"{path} (recorded {_items(recorded)}, now {_items(current)})")
            return
        for i, (c, r) in enumerate(zip(current, recorded)):
            _diff(c, r, f"{path}[{i}]", found)
        return
    if current != recorded:
        found.append(f"{path} ({_render(recorded, 'recorded')}, {_render(current, 'now')})")


def encode_model_response(response: ModelResponse) -> dict[str, Any]:
    """A model response in the shape a cassette entry stores."""
    return {
        "content": response.content,
        "tool_calls": [c.to_record() for c in response.tool_calls],
        "finish_reason": response.finish_reason,
        "backend": response.backend,
        "request_model": response.request_model,
        "response_model": response.response_model,
        "model_revision": response.model_revision,
        "tokens": response.tokens.to_record(),
        "concurrent_requests": response.concurrent_requests,
        "rate_limit": response.rate_limit.to_record() if response.rate_limit else None,
        "reasoning": response.reasoning.to_record() if response.reasoning else None,
    }


def _count(stored: Any) -> Any:
    """One token count, as the entry stored it.

    A count the backend did not report is stored as an ``Unknown`` rather than as a number, so
    it comes back as one. Decoded as the raw object it would be a mapping where the rest of
    the library holds an int or an ``Unknown``, and every sum over it would fail.
    """
    if isinstance(stored, Mapping) and stored.get("type") == "unknown":
        return Unknown(reason=stored.get("reason"))
    return stored


def decode_model_response(raw: Mapping[str, Any]) -> ModelResponse:
    """Rebuild a model response from a cassette entry.

    Token counts, concurrency and the rate-limit allowance come back as recorded, so a
    replayed run reports what the live run met. Duration is carried separately, on
    ``CassetteEntry.duration_ms``, and reaches the record as ``recorded_duration_ms``: a
    replayed call takes no device time of its own, so a compute-basis cost is derived from
    what the live call took. An entry written before that field existed carries no duration,
    and such a cost reports unknown.

    A field absent from an entry decodes as ``None``, which is what a backend reporting nothing
    produces, so a file written before a field was recorded still replays.
    """
    tokens = raw.get("tokens") or {}
    allowance = raw.get("rate_limit")
    return ModelResponse(
        content=raw.get("content"),
        tool_calls=[ToolCallRequest.from_record(c) for c in raw.get("tool_calls") or []],
        finish_reason=raw.get("finish_reason"),
        backend=raw.get("backend", "self_hosted"),
        request_model=raw.get("request_model", ""),
        response_model=raw.get("response_model"),
        model_revision=raw.get("model_revision"),
        tokens=TokenUsage(
            input_uncached=_count(tokens.get("input_uncached", 0)),
            input_cache_read=_count(tokens.get("input_cache_read", 0)),
            input_cache_write=_count(tokens.get("input_cache_write", 0)),
            cache_ttl=tokens.get("cache_ttl"),
            output=_count(tokens.get("output", 0)),
            output_reasoning=(
                None
                if tokens.get("output_reasoning") is None
                else _count(tokens.get("output_reasoning"))
            ),
        ),
        concurrent_requests=raw.get("concurrent_requests"),
        rate_limit=RateLimit(**allowance) if isinstance(allowance, dict) else None,
        reasoning=Reasoning.from_record(raw.get("reasoning")),
    )


def encode_tool_result(value: Any) -> dict[str, Any]:
    """A successful tool return in the shape a cassette entry stores."""
    return {"ok": True, "value": value}


def encode_tool_failure(exc: ModelFacingError) -> dict[str, Any]:
    """A model-facing tool failure, stored so that replay reproduces it.

    A recorded run in which a search returned nothing replays as a search that returns
    nothing, rather than as a call that succeeds.
    """
    error: dict[str, Any] = {
        "message": str(exc),
        "retryable": getattr(exc, "retryable", True),
    }
    if isinstance(exc, Throttled):
        # The class, so a replayed throttle is still a throttle to a node body that catches
        # one. `retry_after_s` travels with it because it is part of what the source said.
        error["throttled"] = True
        error["retry_after_s"] = exc.retry_after_s
    return {"ok": False, "error": error}


def decode_tool_response(raw: Mapping[str, Any]) -> Any:
    """Rebuild a tool result. A recorded failure is raised again."""
    if raw.get("ok"):
        return raw.get("value")
    error = raw.get("error") or {}
    message = error.get("message", "the recorded tool call failed")
    if error.get("throttled"):
        # A recording is made after the retries are spent, so this is the source still busy
        # rather than the first refusal, and it is raised rather than waited out again.
        raise Throttled(message, retry_after_s=error.get("retry_after_s"))
    raise ModelFacingError(message, retryable=bool(error.get("retryable", True)))


def _items(value: list[Any]) -> str:
    return f"{len(value)} item" if len(value) == 1 else f"{len(value)} items"


def _render(value: Any, label: str) -> str:
    if isinstance(value, str) and len(value) > 40:
        return f"{label} {len(value)} chars"
    return f"{label} {value!r}"


def _hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return "ck_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _load(path: Path) -> dict[str, list[CassetteEntry]]:
    if not path.exists():
        return {}
    entries: dict[str, list[CassetteEntry]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = CassetteEntry.from_json(json.loads(line))
            entries.setdefault(entry.key, []).append(entry)
        except (json.JSONDecodeError, KeyError) as exc:
            raise CallerFacingError(
                f"{path}:{number} is not a readable cassette entry: {exc}. A cassette is one "
                f"JSON object per line, each with a `key`. Delete the file and re-record with "
                f"Cassette.record({str(path)!r})."
            ) from exc
    return entries
