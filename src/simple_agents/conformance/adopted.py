"""The library facilities a research survey adopted, against what the runs reached.

`research.md`'s survey is where the design's options were gathered, and a row's ``Outcome``
says what became of each candidate. FT-36 reads that the cell says something. This reads what
it says: a row taken up that names something this library ships, against what the project's
runs recorded.

One project adopted five facilities and its build reached one. Fetching became ``urllib``
inside two ``Deterministic`` nodes, outside the host policy, the cassette and the record, and
nothing said so until the tree was read by hand afterwards.

::

    from simple_agents.conformance.adopted import unreached

    unreached(research_text, produced.facilities)
    # (('http_fetch', 'fetching a page'), ('memory_search', 'the taste model'))

The report prints this and no gate reads it: a candidate adopted at `research` and dropped at
`shape` is a design that changed, which the survey has no way to record.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .artifacts import IN_BACKTICKS, OUTCOME_COLUMN, SURVEY_SECTION, adopted_rows

__all__ = [
    "Facility",
    "FACILITIES",
    "facilities_among",
    "facilities_named",
    "facilities_in",
    "reached_by",
    "rows_read",
    "unreached",
]


@dataclass(frozen=True, slots=True)
class Facility:
    """One thing this library ships that a run records reaching.

    ``name`` is what a survey row writes and what the note prints. ``tool`` is a facility a
    run records under the name it is registered as; ``field`` is one a run records by filling
    a manifest field. ``also`` holds the other spellings a row might use.
    """

    name: str
    tool: bool = False
    field: str | None = None
    also: tuple[str, ...] = ()

    def spellings(self) -> tuple[str, ...]:
        return (self.name,) + self.also


# Thirteen of the fourteen built-in tools, by the name each registers under, and the facilities
# a manifest records by filling a field. `now` is the one left out: a survey row would have to
# write it in backticks to be read at all, and the cost of reading it wrongly is higher than
# the chance a project adopts a clock.
FACILITIES: tuple[Facility, ...] = (
    Facility("document_search", tool=True),
    Facility("http_fetch", tool=True),
    Facility("read_page", tool=True),
    Facility("web_search", tool=True),
    Facility("extract_to_schema", tool=True),
    Facility("consult", tool=True),
    Facility("remember", tool=True),
    Facility("recall", tool=True),
    Facility("memory_search", tool=True),
    Facility("compact_conversation", tool=True),
    Facility("workspace_read", tool=True),
    Facility("workspace_write", tool=True),
    Facility("workspace_list", tool=True),
    Facility("DocumentIndex", field="retrieval", also=("document index",)),
    Facility("MemoryStore", field="memory", also=("memory store", "ScopedMemory")),
    Facility("HostPolicy", field="fetch_policy", also=("host policy",)),
    Facility("Conversation", field="conversation", also=("ConversationStore",)),
    Facility("Suspend", field="suspensions", also=("RunSuspended", "Pipeline.resume")),
)


# A built-in can be registered under any name: `document_search(index, name="catalogue_search")`
# is documented and ordinary, and one fixture in this repository does exactly that. So a tool is
# recognised by its `version` as well as by its name. `@tool` derives that from the library's own
# function source, so it is the same value whatever the project called the tool and whatever it
# constructed it with, and it moves only when the library's own code for that tool moves. A run
# recorded against an older library carries the older value, which the name still catches.
def _built_in_versions() -> dict[str, str]:
    """Each built-in tool's derived version, against the facility name it belongs to.

    Built lazily and once: constructing them imports the search and consultation machinery,
    which a project reading a brief has no other reason to load.
    """
    from ..builtins import (
        DocumentIndex,
        compact_conversation,
        consult,
        document_search,
        extract_to_schema,
        http_fetch,
        memory_search,
        read_page,
        recall,
        remember,
        unattended,
        workspace_list,
        workspace_read,
        workspace_write,
    )

    made = {
        "document_search": lambda: document_search(DocumentIndex.from_texts({"a": "a"})),
        "http_fetch": http_fetch,
        "read_page": read_page,
        "extract_to_schema": lambda: extract_to_schema(_a_schema(), allow_unknown=False),
        "consult": lambda: consult(unattended()),
        "remember": remember,
        "recall": recall,
        "memory_search": memory_search,
        "compact_conversation": compact_conversation,
        "workspace_read": workspace_read,
        "workspace_write": workspace_write,
        "workspace_list": workspace_list,
    }
    found: dict[str, str] = {}
    for name, build in made.items():
        try:
            version = build().version
        except Exception:  # pragma: no cover - a built-in that will not construct bare
            continue
        if version:
            found[str(version)] = name
    return found


def _a_schema() -> Any:
    """The smallest schema `extract_to_schema` will take, for reading its version.

    It refuses anything but a pydantic model, since what it declares is shown to the model.
    """
    from pydantic import BaseModel

    class OneValue(BaseModel):
        value: str

    return OneValue


_VERSIONS: dict[str, str] | None = None


def _versions() -> dict[str, str]:
    global _VERSIONS
    if _VERSIONS is None:
        _VERSIONS = _built_in_versions()
    return _VERSIONS


_BY_SPELLING = {
    spelling.casefold(): entry.name for entry in FACILITIES for spelling in entry.spellings()
}

# A manifest field is reached when it holds something. `memory` and `conversation` are `null`
# on a run that used neither, and the three arrays are empty.
_FIELDS = tuple(sorted({entry.field for entry in FACILITIES if entry.field}))

_TRAILING_CALL = re.compile(r"\(.*\)\s*$")


def facilities_named(cell: str) -> tuple[str, ...]:
    """Every facility one cell names in backticks, in the order it names them.

    The one place a survey's words are matched against what this library ships, so the report
    and the research page read a row the same way::

        facilities_named("adopted: `http_fetch` and `read_page`")   # ('http_fetch', 'read_page')

    A name written in prose is not read: what a row means by "the library's page fetcher" is a
    judgement, and the callers say how many rows they could read instead of guessing.
    """
    return facilities_among(IN_BACKTICKS.findall(str(cell or "")))


def facilities_among(names: Iterable[str]) -> tuple[str, ...]:
    """The facilities among ``names``, each written as a survey row writes it.

    ``facilities_named`` reads the names out of a cell first; a caller holding them already
    (`artifacts.adopted_rows` returns them) comes here instead::

        facilities_among(["http_fetch", "pandas"])      # ('http_fetch',)

    A trailing call is ignored, so ``http_fetch(policy)`` is ``http_fetch``.
    """
    found: list[str] = []
    for raw in names:
        name = _BY_SPELLING.get(_TRAILING_CALL.sub("", str(raw)).strip().casefold())
        if name is not None and name not in found:
            found.append(name)
    return tuple(found)


def facilities_in(text: str) -> tuple[tuple[str, str], ...]:
    """Every facility an adopted survey row names, as ``(facility, the row that named it)``.

    Only names a row wrote in backticks are read (`artifacts.adopted_rows`), so a row calling
    something "the library's page fetcher" is not joined::

        facilities_in(research)     # (('http_fetch', 'fetching a page'), ...)
    """
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row, named in adopted_rows(text, SURVEY_SECTION, OUTCOME_COLUMN):
        for entry in facilities_among(named):
            if entry not in seen:
                seen.add(entry)
                found.append((entry, row))
    return tuple(found)


def rows_read(text: str) -> tuple[int, int]:
    """How many adopted rows the survey holds, and how many name something this library ships."""
    rows = adopted_rows(text, SURVEY_SECTION, OUTCOME_COLUMN)
    joined = sum(1 for _, named in rows if facilities_among(named))
    return len(rows), joined


def reached_by(manifest: Any, tools: set[str], into: set[str]) -> None:
    """Add every facility one manifest records reaching to ``into``.

    ``tools`` is the tool names that manifest recorded, which the caller already reads. A tool
    is matched by its recorded ``version`` as well, so a built-in registered under a name of
    the project's own is still read as reached.
    """
    into |= _tools_named(tools)
    if not isinstance(manifest, dict):
        return
    into |= _tools_versioned(manifest.get("tools"))
    into |= _fields_filled(manifest)


def _tools_named(tools: set[str]) -> set[str]:
    """The tool facilities a run recorded under the name this library registers them as."""
    return {entry.name for entry in FACILITIES if entry.tool and entry.name in tools}


def _tools_versioned(held: Any) -> set[str]:
    """The tool facilities a run recorded by version, whatever the project named them.

    `document_search(index, name="catalogue_search")` is documented and ordinary, so a name is
    not enough. ``@tool`` derives a version from the library's own function source, which is
    the same value whatever the tool was called and whatever it was constructed with.
    """
    if not isinstance(held, list):
        return set()
    known = _versions()
    found = set()
    for recorded in held:
        if isinstance(recorded, dict):
            name = known.get(str(recorded.get("version") or ""))
            if name is not None:
                found.add(name)
    return found


def _fields_filled(manifest: dict[str, Any]) -> set[str]:
    """The facilities a run records by filling a manifest field rather than by naming a tool.

    ``memory`` and ``conversation`` are ``null`` on a run that used neither, and the arrays
    are empty, so holding anything is what says the run reached it.
    """
    filled = {field for field in _FIELDS if manifest.get(field)}
    return {entry.name for entry in FACILITIES if entry.field in filled}


def unreached(text: str, reached: set[str]) -> tuple[tuple[str, str], ...]:
    """The facilities the survey adopted that no run recorded, with the row that named each."""
    return tuple((name, row) for name, row in facilities_in(text) if name not in reached)
