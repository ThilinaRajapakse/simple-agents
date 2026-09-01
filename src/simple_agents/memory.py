"""A store the agent reads and writes across runs, and the handle a tool reaches it through.

Memory is reached through a recorded tool call and nowhere else. A node calls a tool, the value
it returns is written to a ``tool_call`` record, and it travels on to the next node on a
declared edge like any other value. There is no ``ctx.memory``: a value read from a store that
no record names cannot be explained from the trajectory, and per-node numbers would be computed
over inputs that are not the real inputs.

Where the store lives and whose memory a run reads have different lifetimes. The directory is
project configuration, so :class:`MemoryStore` is declared once on the envelope. The scope is
per request, so it is an argument to the run and :class:`ScopedMemory` is what the two together
make.

The store outlives the run that wrote it. Three things follow, and each is handled here rather
than left to the project:

1. **Writes are redacted.** A value goes through the run's :class:`~simple_agents.Redaction`
   before it lands, and the entry records which rules were applied. Rules change between runs,
   so a store is a mixture, and a rule added later does not reach what is already stored.
2. **An evaluation gives each rollout its own store**, seeded from the example. Rollouts run
   concurrently, so a shared store would let one rollout answer out of another's write and the
   same measurement would produce a different number each time.
3. **A write is an idempotent put, not an append.** A tool taking a :class:`Memory` is re-run
   during a replay, so writing the same key twice has to leave the same state.

``docs/memory.md`` is this module's document.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .errors import CallerFacingError, ConfigurationError, ModelFacingError
from .records.trajectory import utc_now

__all__ = [
    "MemoryStore",
    "ScopedMemory",
    "MemoryEntry",
    "Memory",
    "ROLLOUT_SCOPE",
    "scope_digest_of",
    "refuse_unreachable",
    "refuse_another_scope",
]

MAX_KEY_LENGTH = 200

ROLLOUT_SCOPE = "rollout"
"""The memory scope every rollout of an evaluation uses.

Each rollout has its own store, so one name serves them all and a scoring rule reading a
rollout's memory back does not have to know which example it came from.
"""


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """One thing an agent stored, and what was known about it when it was stored.

    Returned by :meth:`ScopedMemory.get` and :meth:`ScopedMemory.entries`::

        entry.key           # 'preferred_length'
        entry.value         # 'prefers books under 300 pages'
        entry.stored_at     # '2026-08-10T09:14:02Z'
        entry.redactions    # ('value',) where a rule replaced something, else ()

    ``rules`` is what the run that wrote it redacted with. An entry written before a rule
    existed was not scanned by it, which is why the rules travel with the entry rather than
    being read off the current run.

    ``vector`` is the entry embedded for semantic recall, and ``embedded_by`` names the model
    that produced it. Both are empty on an entry written by a run that did not embed, and an
    entry embedded by another model is re-embedded rather than compared against, since vectors
    from two models occupy different spaces. **A store is therefore a mixture**, in the same
    way it is a mixture of redaction rules.
    """

    key: str
    value: str
    stored_at: str
    redactions: tuple[str, ...] = ()
    rules: Mapping[str, Any] = field(default_factory=dict)
    vector: tuple[float, ...] = ()
    embedded_by: Mapping[str, Any] | None = None

    def embedded_under(self, identity: Mapping[str, Any]) -> bool:
        """Whether this entry's vector was made by the model ``identity`` names."""
        if not self.vector or not self.embedded_by:
            return False
        return all(
            self.embedded_by.get(field) == identity.get(field)
            for field in ("backend", "request_model", "model_revision")
        )

    def to_json(self) -> dict[str, Any]:
        """The entry as the file holds it."""
        return {
            "key": self.key,
            "value": self.value,
            "stored_at": self.stored_at,
            "redactions": list(self.redactions),
            "rules": dict(self.rules),
            "vector": list(self.vector),
            "embedded_by": dict(self.embedded_by) if self.embedded_by else None,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> MemoryEntry:
        """An entry read back off disk."""
        stored = raw.get("embedded_by")
        return cls(
            key=str(raw.get("key", "")),
            value=str(raw.get("value", "")),
            stored_at=str(raw.get("stored_at", "")),
            redactions=tuple(raw.get("redactions") or ()),
            rules=dict(raw.get("rules") or {}),
            vector=tuple(float(x) for x in raw.get("vector") or ()),
            embedded_by=dict(stored) if stored else None,
        )


@dataclass(slots=True)
class MemoryStore:
    """Where a project's memories live.

    Declared once on the envelope; whose memory a run reads is an argument to the run, since
    that changes per request and the directory does not::

        env = RunEnvelope(run_dir="runs/", memory=MemoryStore("memory/"))
        result = pipeline.run(question, envelope=env.with_live(), model=client,
                              memory_scope=f"user-{user_id}")

    ``directory`` is the project's to choose and nothing here picks one. A scope separates one
    end user's memory from another's: two runs over one directory under different scopes share
    no entry. Every run that reaches memory names one, so there is no default.

    :meth:`scoped` is how one scope's memory is reached outside a run::

        MemoryStore("memory/").scoped(f"user-{user_id}").keys()

    An evaluation does not use the store it is handed. Each rollout gets its own, seeded from
    ``Example.memory``, so one rollout cannot answer out of another's write.
    """

    directory: Path

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)

    def scoped(self, scope: str) -> "ScopedMemory":
        """One end user's memory in this store, whether or not anything is stored in it."""
        return ScopedMemory(self.directory, scope)

    def rebound(
        self,
        directory: str | os.PathLike[str],
        *,
        seed: Mapping[str, str] | None = None,
    ) -> MemoryStore:
        """A store somewhere else, holding ``seed`` under :data:`ROLLOUT_SCOPE` and nothing more.

        What an evaluation gives each rollout: a directory inside that rollout's own run, and
        the example's ``memory`` as its starting contents. Rollouts run concurrently, so a
        store they shared would let one answer out of another's write.
        """
        moved = MemoryStore(directory)
        mine = moved.scoped(ROLLOUT_SCOPE)
        for key, value in (seed or {}).items():
            mine.put(str(key), str(value))
        return moved


@dataclass(slots=True)
class ScopedMemory:
    """One end user's memory, on disk.

    Produced by :meth:`MemoryStore.scoped`. A run reaches it through a tool taking a
    :class:`Memory`, and a project reads it outside a run directly::

        mine = MemoryStore("memory/").scoped(f"user-{user_id}")

        len(mine)                      # how many facts are stored
        mine.keys()                    # every key, sorted
        mine.get("preferred_length")   # one entry, or None

    ``scope`` names whose memory this is, such as the end user's identifier. The manifest
    records it as a digest rather than as the value, since it usually identifies a person.
    """

    directory: Path
    scope: str

    def __init__(self, directory: str | os.PathLike[str], scope: str) -> None:
        if not isinstance(scope, str) or not scope.strip():
            raise ConfigurationError(
                "A memory scope names whose memory a run reads and writes, such as the end "
                "user's identifier, and it has to be a non-empty string. There is no default, "
                "because one scope for every end user is one memory for every end user.\n"
                "Pass it to the run: pipeline.run(inputs, envelope=env, model=client, "
                "memory_scope=f'user-{user_id}')."
            )
        self.directory = Path(directory)
        self.scope = scope

    # -- identity -------------------------------------------------------------------------

    @property
    def scope_digest(self) -> str:
        """The scope as the manifest and the directory name record it.

        Twelve hex characters of the scope's SHA-256. Two runs over one memory record the same
        digest, and the identifier itself is not written to an artifact.
        """
        return scope_digest_of(self.scope)

    @property
    def root(self) -> Path:
        """Where this scope's entries live, whether or not the directory exists."""
        return self.directory / self.scope_digest

    # -- reading --------------------------------------------------------------------------

    def get(self, key: str) -> MemoryEntry | None:
        """The entry stored under ``key``, or ``None`` where there is none."""
        path = self._path(key)
        try:
            return MemoryEntry.from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None

    def entries(self) -> list[MemoryEntry]:
        """Everything in this scope, oldest first, then by key."""
        found = []
        if self.root.is_dir():
            for path in self.root.glob("*.json"):
                try:
                    found.append(
                        MemoryEntry.from_json(json.loads(path.read_text(encoding="utf-8")))
                    )
                except (OSError, ValueError):
                    continue
        return sorted(found, key=lambda entry: (entry.stored_at, entry.key))

    def keys(self) -> list[str]:
        """Every key in this scope, sorted."""
        return sorted(entry.key for entry in self.entries())

    def __len__(self) -> int:
        return len(self.entries())

    def __iter__(self) -> Iterator[MemoryEntry]:
        return iter(self.entries())

    # -- writing --------------------------------------------------------------------------

    def put(
        self,
        key: str,
        value: str,
        *,
        redaction: Any = None,
        vector: Sequence[float] = (),
        embedded_by: Mapping[str, Any] | None = None,
    ) -> MemoryEntry:
        """Store ``value`` under ``key``, replacing whatever was there.

        ``redaction`` is the run's rules, applied before the value lands. The entry records
        what they replaced and what they were, because the store outlives the run and a rule
        added later does not reach an entry already written.

        ``vector`` is the redacted value embedded, and ``embedded_by`` names the model that
        did it. Both are stored so a later semantic recall reads them rather than embedding
        the whole store on every search.

        Written to a scratch file and renamed, so a reader never sees half an entry.
        """
        key = _checked_key(key)
        stored, paths, rules = _redact(value, redaction)
        entry = MemoryEntry(
            key=key,
            value=stored,
            stored_at=utc_now(),
            redactions=tuple(paths),
            rules=rules,
            vector=tuple(float(x) for x in vector),
            embedded_by=dict(embedded_by) if embedded_by else None,
        )
        self.write(entry)
        return entry

    def write(self, entry: MemoryEntry) -> MemoryEntry:
        """Write an entry as it stands, replacing whatever is under its key.

        Used to add a vector to an entry already stored, which is what a semantic recall does
        for an entry written before the store was embedded. Nothing here redacts, because the
        entry's value has already been through the rules it records.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(entry.key)
        # The scratch name carries the writer, so two writers of one key cannot share a file
        # and leave a partial one behind. The rename is atomic, so a reader sees the old entry
        # or the new one and never half of either.
        scratch = path.with_suffix(f".writing-{os.getpid()}-{threading.get_ident()}")
        scratch.write_text(json.dumps(entry.to_json(), ensure_ascii=False), encoding="utf-8")
        os.replace(scratch, path)
        return entry

    def forget(self, key: str) -> bool:
        """Remove what is stored under ``key``. True where there was something to remove."""
        path = self._path(key)
        try:
            path.unlink()
        except OSError:
            return False
        return True

    # -- the manifest ---------------------------------------------------------------------

    def to_manifest(self) -> dict[str, Any]:
        """What the run manifest records: where the store is and how much it held.

        The scope is a digest, never the value. ``entries`` is the count at the moment this is
        called, which the run writes at its end.
        """
        return {
            "directory": str(self.directory),
            "scope_digest": self.scope_digest,
            "entries": len(self.entries()),
        }

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.root / f"{digest}.json"


@dataclass(frozen=True, slots=True)
class Memory:
    """What an agent remembers, as a tool sees it.

    A parameter annotated with this is filled by the library and is left out of the schema the
    model sees. A tool holding one is re-run during a replay rather than served from the
    cassette, so a replayed run rebuilds the store by making the same writes::

        @tool(side_effect_class=SideEffectClass.WRITES)
        def remember(memory: Memory, key: str, value: str) -> str:
            \"\"\"Store one fact for later runs to read. Returns the key it was stored under.\"\"\"
            memory.remember(key, value)
            return key

    A write is a put rather than an append: re-running has to leave the same state, so storing
    twice under one key stores once. A fact with no natural key goes under one derived from
    what it says.

    The built-in tools over this are ``simple_agents.builtins.remember``, ``recall`` and
    ``memory_search``. A tool holding one may not declare ``spends_money`` or ``irreversible``.
    """

    _store: ScopedMemory = field(repr=False)
    _redaction: Any = field(default=None, repr=False)

    @property
    def scope(self) -> str:
        """Whose memory this is, as the project declared it."""
        return self._store.scope

    def remember(self, key: str, value: str) -> MemoryEntry:
        """Store one fact, replacing anything under the same key.

        The value goes through the run's redaction rules first. Raises
        :class:`~simple_agents.errors.ModelFacingError` on an empty key or one longer than 200
        characters, so the model is told to pass a shorter one rather than the run ending.
        """
        return self._store.put(key, value, redaction=self._redaction)

    def recall(self, key: str) -> MemoryEntry | None:
        """What is stored under ``key``, or ``None`` where nothing is."""
        return self._store.get(key)

    def entries(self) -> list[MemoryEntry]:
        """Everything in this scope, oldest first."""
        return self._store.entries()

    def keys(self) -> list[str]:
        """Every key in this scope, sorted."""
        return self._store.keys()

    def forget(self, key: str) -> bool:
        """Remove what is stored under ``key``. True where there was something to remove."""
        return self._store.forget(key)

    def store_vector(
        self, key: str, vector: Sequence[float], embedded_by: Mapping[str, Any]
    ) -> MemoryEntry | None:
        """Attach an embedding to a fact already stored, without changing what it says.

        Called by the search tool for a fact written before the store had embeddings, so the
        next search reads the vector rather than making it again. Returns ``None`` where
        nothing is stored under ``key``.
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        return self._store.write(
            replace(entry, vector=tuple(float(x) for x in vector), embedded_by=dict(embedded_by))
        )


def scope_digest_of(scope: str) -> str:
    """A memory scope as every artifact records it: twelve hex characters of its SHA-256.

    What compares two scopes without either of them being written down::

        scope_digest_of(f"user-{user_id}") == manifest.memory["scope_digest"]
    """
    return hashlib.sha256(scope.encode("utf-8")).hexdigest()[:12]


def refuse_unreachable(
    store: MemoryStore | None,
    scope: str | None,
    *,
    wanting: Sequence[str],
    called: str,
) -> None:
    """Refuse memory tools with nothing to reach, naming which half is missing.

    Two things have to be present and either can be absent on its own: the envelope declares
    where memories live, and the call names whose memory this run reads. ``wanting`` is the
    tools that take a :class:`Memory`, and ``called`` is the method to name in the message.
    """
    named = ", ".join(repr(name) for name in wanting)
    spent = "the run would stop at the first one having spent whatever the nodes before it spent"
    if store is None:
        raise ConfigurationError(
            f"Tool(s) {named} take a Memory and this envelope declares no store, so {spent}. "
            f"Memory outlives the run, so the library will not invent a location for it.\n"
            f"Declare it: RunEnvelope(run_dir='runs/', memory=MemoryStore('memory/')), and "
            f"name whose memory the run reads: {called}(..., memory_scope=f'user-{{user_id}}')."
        )
    if scope is None:
        raise ConfigurationError(
            f"Tool(s) {named} take a Memory and this run names no memory scope, so {spent}. "
            f"The store holds one end user's memory per scope and the library will not decide "
            f"whose memory this run reads.\n"
            f"Name it: {called}(..., memory_scope=f'user-{{user_id}}')."
        )


def refuse_another_scope(scope: str | None, recorded: str | None) -> None:
    """Refuse continuing a run under a different end user's memory than it started under.

    ``recorded`` is the manifest's ``scope_digest``, so the two are compared as digests and
    neither is written down. Continuing under the wrong scope would write what the run learned
    into another end user's memory and answer out of it, with nothing downstream reporting it.
    """
    if scope is None or not recorded:
        return
    offered = scope_digest_of(scope)
    if offered == recorded:
        return
    raise CallerFacingError(
        f"This run read the memory scope recorded as {recorded} and memory_scope= names one "
        f"recorded as {offered}, so continuing it would write what the run learned into "
        f"another end user's memory.\n"
        f"Pass the scope this run started under, or start a new run for this one."
    )


def _checked_key(key: Any) -> str:
    """A usable key, or a failure the model can correct."""
    text = str(key).strip()
    if not text:
        raise ModelFacingError(
            "A memory key cannot be empty. Pass a short name for what is being stored, such "
            "as 'preferred_length' or 'shipping_address'.",
            retryable=False,
        )
    if len(text) > MAX_KEY_LENGTH:
        raise ModelFacingError(
            f"The memory key is {len(text)} characters and the limit is {MAX_KEY_LENGTH}. A "
            f"key names what is stored so it can be found again; the fact itself goes in the "
            f"value. Pass a shorter key.",
            retryable=False,
        )
    return text


def _redact(value: Any, redaction: Any) -> tuple[str, list[str], dict[str, Any]]:
    """``value`` with the run's rules applied, the paths they changed, and the rules."""
    text = value if isinstance(value, str) else str(value)
    if redaction is None:
        return text, [], {}
    cleaned, paths = redaction.redact(text, path="value")
    rules = redaction.to_manifest()
    return (
        cleaned if isinstance(cleaned, str) else text,
        paths,
        {
            "enabled": rules["enabled"],
            "builtin": rules["builtin"],
            "declared_rules": rules["declared_rules"],
            "secret_env": rules["secret_env"],
        },
    )
