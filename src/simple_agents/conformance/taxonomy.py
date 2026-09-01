"""The failure taxonomy, read out of the shipped document rather than restated here.

``docs/failure-taxonomy.md`` is the specification the conformance suite derives from, and its
failure messages are the text a coding agent reads and acts on. Holding a second copy of that
text in Python would let the two drift, and a message that has drifted tells a reader to do
something the document does not ask for. So the runner parses the document.

Two conventions in that document are a contract rather than formatting. An entry opens with
``### FT-nn: Name`` followed by ``*Surface: … · Tier: …*``, which may carry a third field,
``· Stage: ship``, for a check that fires only once a project has reached that stage. Its
message is a ``**Failure message.**`` line followed by one blockquote, and every placeholder in
it is a plain name in backticks, such as ``` `<alias>` ```, with no expressions and no
alternations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ..errors import ConfigurationError
from .stages import STAGES, is_stage

__all__ = ["Entry", "Taxonomy", "Tier", "taxonomy"]

_ENTRY = re.compile(r"^### (FT-\d+): (.+?)\s*$", re.MULTILINE)
_SURFACE_TIER = re.compile(
    r"^\*Surface:\s*(.+?)\s*·\s*Tier:\s*(.+?)\s*(?:·\s*Stage:\s*(.+?)\s*)?\*$",
    re.MULTILINE,
)
_CHECK = re.compile(r"^\*\*Check\.\*\*\s*(.+?)$", re.MULTILINE)
_MESSAGE = re.compile(r"^\*\*Failure message\.\*\*\n((?:>.*\n)+)", re.MULTILINE)
_PLACEHOLDER = re.compile(r"`<([a-z_]+)>`")


class Tier(str):
    """One of the three tiers a project can claim, ordered so a gate can compare them.

    ``prototype`` applies to everything, ``evaluated`` adds everything about measurement, and
    ``trained`` adds the RL hazards. Tiers are cumulative::

        Tier("evaluated").covers(Tier("prototype"))    # True
        Tier("prototype").covers(Tier("evaluated"))    # False

    Constructing one from anything else raises ``ConfigurationError`` naming the three.
    """

    ORDER = ("prototype", "evaluated", "trained")

    def __new__(cls, value: str) -> Tier:
        if value not in cls.ORDER:
            raise ConfigurationError(
                f"{value!r} is not a tier. The three are prototype, evaluated and trained, "
                f"and they are cumulative: evaluated includes every prototype gate. Declare "
                f'one in the brief as tier = "prototype".'
            )
        return super().__new__(cls, value)

    def covers(self, other: Tier | str) -> bool:
        """Whether a project claiming this tier is held to the gates of ``other``."""
        return self.ORDER.index(self) >= self.ORDER.index(str(other))


@dataclass(frozen=True, slots=True)
class Entry:
    """One taxonomy entry, as the document states it.

    ``message`` is the failure text with its placeholders intact, and ``render`` fills them::

        entry = taxonomy()["FT-14"]
        entry.tier                     # 'prototype'
        entry.render(alias="gpt-4o")   # the message, with `<alias>` replaced

    ``render`` raises ``ConfigurationError`` when a placeholder is left unfilled or an
    unexpected name is passed, because a message reaching a reader with `<alias>` still in it
    names nothing to act on.
    """

    id: str
    name: str
    surface: str
    tier: Tier
    check: str
    message: str
    placeholders: tuple[str, ...]
    stage: str | None = None
    """The stage a project has to have reached for this check to fire, and ``None`` for an
    entry that fires whenever its tier applies. Read off the entry's `· Stage:` field."""

    def render(self, **values: object) -> str:
        """The failure message with every placeholder filled."""
        unexpected = sorted(set(values) - set(self.placeholders))
        if unexpected:
            raise ConfigurationError(
                f"{self.id}'s failure message has no placeholder called "
                f"{', '.join(unexpected)}. It takes "
                f"{', '.join(self.placeholders) or 'no placeholders'}, and the message in "
                f"docs/failure-taxonomy.md is what decides that."
            )
        missing = sorted(set(self.placeholders) - set(values))
        if missing:
            raise ConfigurationError(
                f"{self.id}'s failure message was rendered without "
                f"{', '.join(missing)}, so the text a reader gets would name nothing to act "
                f"on. Pass every placeholder: {', '.join(self.placeholders)}."
            )
        text = self.message
        for name, value in values.items():
            text = text.replace(f"`<{name}>`", f"`{value}`")
        return text


class Taxonomy:
    """Every entry in ``docs/failure-taxonomy.md``, keyed by id.

    ::

        entries = taxonomy()
        entries["FT-02"].name           # 'No held-out split'
        [e.id for e in entries.at_tier(Tier("prototype"))]

    Reading one that does not exist raises rather than returning nothing, because a check
    citing an id the document has retired should stop the suite rather than run without a
    message.
    """

    def __init__(self, entries: dict[str, Entry], source: Path) -> None:
        self._entries = entries
        self.source = source

    def __getitem__(self, entry_id: str) -> Entry:
        try:
            return self._entries[entry_id]
        except KeyError:
            raise ConfigurationError(
                f"{self.source} has no entry {entry_id!r}. It holds "
                f"{', '.join(sorted(self._entries))}."
            ) from None

    def __iter__(self) -> Iterator[Entry]:
        return iter(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)

    def at_tier(self, claimed: Tier) -> list[Entry]:
        """The entries whose gate fires for a project claiming this tier."""
        return [entry for entry in self if claimed.covers(entry.tier)]


def taxonomy(path: Path | None = None) -> Taxonomy:
    """Parse the shipped taxonomy, or one at ``path``.

    ::

        from simple_agents.conformance import taxonomy

        taxonomy()["FT-13"].message

    Raises ``ConfigurationError`` when the document is missing, when it holds no entries, or
    when an entry carries no failure message, since the runner has nothing to print without
    one.
    """
    from .. import docs_path

    target = Path(path) if path is not None else docs_path() / "failure-taxonomy.md"
    if not target.exists():
        raise ConfigurationError(
            f"No failure taxonomy at {target}. The conformance runner reads its failure "
            f"messages out of that document rather than holding a copy of them. It installs "
            f"beside the package; simple_agents.docs_path() returns the directory."
        )

    text = target.read_text(encoding="utf-8")
    marks = list(_ENTRY.finditer(text))
    if not marks:
        raise ConfigurationError(
            f"{target} holds no `### FT-nn: Name` entries. That heading shape is what the "
            f"runner reads entries from."
        )

    entries: dict[str, Entry] = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = text[mark.end() : end]
        entries[mark.group(1)] = _entry(mark.group(1), mark.group(2), body, target)
    return Taxonomy(entries, target)


def _entry(entry_id: str, name: str, body: str, source: Path) -> Entry:
    surface_tier = _SURFACE_TIER.search(body)
    if surface_tier is None:
        raise ConfigurationError(
            f"{source}: {entry_id} carries no `*Surface: … · Tier: …*` line. A check cannot "
            f"tell whether its gate fires without the tier."
        )
    message = _MESSAGE.search(body)
    if message is None:
        raise ConfigurationError(
            f"{source}: {entry_id} carries no `**Failure message.**` blockquote. The runner "
            f"prints that text when the check fires, and holds no copy of its own."
        )
    check = _CHECK.search(body)
    rendered = " ".join(line.lstrip("> ").rstrip() for line in message.group(1).splitlines())
    return Entry(
        id=entry_id,
        name=name,
        surface=surface_tier.group(1),
        tier=Tier(surface_tier.group(2)),
        check=check.group(1).strip() if check else "",
        message=rendered,
        placeholders=tuple(dict.fromkeys(_PLACEHOLDER.findall(rendered))),
        stage=_stage_of(surface_tier.group(3), entry_id, source),
    )


def _stage_of(declared: str | None, entry_id: str, source: Path) -> str | None:
    """The `· Stage:` field of an entry's surface line, checked against the six stages."""
    if declared is None:
        return None
    name = declared.strip().strip("`")
    if not is_stage(name):
        raise ConfigurationError(
            f"{source}: {entry_id} names stage {name!r}, and the six are "
            f"{', '.join(STAGES)}. A stage on an entry says the check fires only once the "
            f"project has reached it. Leave the field out for a check that fires whenever its "
            f"tier applies."
        )
    return name
