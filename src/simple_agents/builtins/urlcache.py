"""A store of what was fetched, on disk, in front of the network.

The cassette records every call a run made and replays that run without a network. A second
run asking for something the first did not ask for fetches it again, including pages an earlier
run already read. This is the other half: a page read once is not read again until it is stale,
across runs, whatever else changed.

Scope, stated so it is not mistaken for more: **a cache for the two shipped network tools**, not
a general memoisation layer. Entries expire on age and on nothing else. There is no eviction,
no size accounting, and no locking beyond one atomic write per entry, so two processes writing
one entry leave whichever finished last.

Where a tool is served from here, the cassette still records what the tool returned, so replay
is unaffected.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ConfigurationError

__all__ = ["UrlCache", "CachedValue"]


@dataclass(frozen=True, slots=True)
class CachedValue:
    """A stored entry, and how old it is."""

    key: str
    value: str
    stored_at: float

    @property
    def age_days(self) -> float:
        """How long ago this was stored, in days."""
        return (time.time() - self.stored_at) / 86400.0


@dataclass(slots=True)
class UrlCache:
    """What a run has already fetched, kept on disk and reused by later runs::

        cache = UrlCache("cache/pages", max_age_days=7)
        registry.add(read_page(cache=cache, allow_hosts=["docs.example.com"]))

    ``directory`` is the project's to choose, and nothing here picks one. ``max_age_days``
    is how long a stored entry is served before the address is read again; the right number
    depends on how fast the pages move, so the project sets it.

    A tool served from here reports the entry's age in what it returns, so the model knows it
    is reading something stored rather than something just fetched.
    """

    directory: Path
    max_age_days: float = 7.0

    def __init__(self, directory: str | os.PathLike[str], *, max_age_days: float = 7.0) -> None:
        if max_age_days <= 0:
            raise ConfigurationError(
                f"UrlCache(max_age_days={max_age_days}) stores nothing that can be served, "
                f"since every entry is stale as soon as it is written. Pass the number of days "
                f"an entry stays good, or leave the cache out."
            )
        self.directory = Path(directory)
        self.max_age_days = float(max_age_days)

    def get(self, key: str) -> CachedValue | None:
        """The stored value for ``key``, or ``None`` where there is none or it is stale."""
        path = self._path(key)
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        stored_at = float(stored.get("stored_at", 0.0))
        if (time.time() - stored_at) / 86400.0 > self.max_age_days:
            return None
        return CachedValue(key=key, value=str(stored.get("value", "")), stored_at=stored_at)

    def put(self, key: str, value: str) -> CachedValue:
        """Store a value against ``key``, replacing anything already there.

        Written to a scratch file and renamed, so a reader never sees half an entry. The
        scratch name carries the writer, so two fetches of one URL cannot share a file and
        leave a partial one behind.
        """
        stored_at = time.time()
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        scratch = path.with_suffix(f".writing-{os.getpid()}-{threading.get_ident()}")
        scratch.write_text(
            json.dumps({"key": key, "stored_at": stored_at, "value": value}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(scratch, path)
        return CachedValue(key=key, value=value, stored_at=stored_at)

    def stored(self) -> int:
        """How many entries the directory holds, whether or not they are stale."""
        return len(list(self.directory.glob("*.json"))) if self.directory.is_dir() else 0

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        return self.directory / f"{digest}.json"


def request_key(*parts: Any) -> str:
    """A cache key over everything that identifies a request::

        request_key("search", query, count, sorted(domains or ()))

    Two requests differing in any part get different keys, which is what stops a scoped search
    being served a whole-web result recorded under the same query.
    """
    return json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
