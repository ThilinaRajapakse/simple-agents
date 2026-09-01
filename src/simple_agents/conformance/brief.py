"""The brief: the file where a project records what it claims and what it was asked.

A gate fires only when the project claims the tier it belongs to, and the claim cannot be read
off the project's artifacts: the check for a missing evaluation fires exactly when a project
claims ``evaluated`` and has none, so inferring the claim from the presence of an evaluation
would make that check unable to fire.

The file is TOML, at ``brief.toml`` in the project root::

    tier = "evaluated"
    stage = "measure"
    results = "evals/results/held-out-v3.json"

    [entries.ground_truth]
    status = "answered"
    answer = "A retailer name, matched case-insensitively."

    [entries.budget]
    status = "deferred"
    deferred_to = "measure"

    [decisions.book_source]
    kind = "dependency"
    status = "agreed"
    chose = "Open Library, with Google Books where a key is configured"
    considered = ["Open Library alone", "a web search over publisher pages"]
    because = "the export carries no descriptions, so something has to supply them"

``tier`` decides which gates apply. ``stage`` says how far the project has got, and the
elicitation gate compares the entries against the questions required at that stage (FT-24).

``results`` names the evaluation the project reports, and the checks that read a results file
read that one. It is optional, and without it the most recent under ``evals/results/`` is
read. A project measuring a variant after its reported number is why it exists: the variant
is the more recent file.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ConfigurationError
from .decisions import AN_EXAMPLE_STAMP, Decision, decisions_from, kind_names, recorded_at
from .elicitation import QUESTIONS
from .stages import STAGES, is_stage, stages_for
from .taxonomy import Tier

__all__ = ["Brief", "BriefEntry", "SOURCES", "STATUSES"]

STATUSES = ("answered", "deferred", "unanswered")

# Where an answer came from. `builder` is the default and the only one a required question
# passes on alone: the other three each say somebody other than the builder produced it.
SOURCES = ("builder", "research", "document", "coding_agent")
DEFAULT_SOURCE = SOURCES[0]


@dataclass(frozen=True, slots=True)
class BriefEntry:
    """One question put to the builder, and what came back.

    ``status`` is ``answered``, ``deferred`` or ``unanswered``. A deferred entry names the
    stage it is deferred to, so a postponed decision is distinguishable from a forgotten one.
    The deferral holds until the project reaches that stage, where the answer becomes due and
    the gate asks for it (FT-24).

    ``source`` says where an answer came from, and defaults to ``builder``::

        [entries.too_similar]
        status = "answered"
        source = "coding_agent"
        answer = "0.8. The builder has not been asked; the number is the library's own starting point."

    ``builder`` is what they said, ``research`` a finding out of ``research.md`` put to them and
    agreed, ``document`` something read out of a file they supplied. **A required question whose
    source is ``coding_agent`` fails FT-24**: the coding agent filled it in unseen.

    ``asked_at`` is the stage the question was last put at and ``recorded_at`` is when what
    the entry now says was written down, off the coding agent's system clock::

        [entries.anything_else]
        status = "answered"
        asked_at = "shape"
        recorded_at = "2026-08-27T09:14:02Z"
        answer = "brainstorm: nothing. research: the export is stale after Tuesdays."

    A question a gate puts again at every stage fails FT-24 while ``asked_at`` is absent or
    names an earlier stage than the project is at, which is how a re-asked question differs
    from one settled once. Nothing reads it on any other entry.

    **``recorded_at`` is required on an ``answered`` entry**, and a re-asked question moves it
    with ``asked_at``, since what it dates is the writing.
    """

    name: str
    status: str
    answer: str | None = None
    deferred_to: str | None = None
    source: str = "builder"
    asked_at: str | None = None
    recorded_at: str | None = None


@dataclass(frozen=True, slots=True)
class Brief:
    """What a project declares about itself.

    ::

        brief = Brief.read("brief.toml")
        brief.tier                       # Tier('evaluated')
        brief.unanswered()               # ['budget']

    ``understanding_confirmed_at`` is the stage at which ``idea.md`` was last confirmed to
    still describe the project, and is ``None`` where the key is absent. ``design_confirmed_at``
    is the same for ``design.md`` and ``research_confirmed_at`` for ``research.md``. FT-29,
    FT-34 and FT-36 read them against the stage the project has reached::

        understanding_confirmed_at = "build"

    ``confirmed_against`` is the pipeline the entries were last read against, as
    ``Pipeline.behaviour_fingerprint(model=client)`` reports it, and ``None`` where the brief
    carries no such key. An entry goes stale when the code moves rather than when a gate is reached, so
    this is what dates the answers against the code::

        confirmed_against = "sha256:213998182146fc28"

    ``shape_confirmed`` dates the picture rather than the answers, holding the
    ``Pipeline.graph_fingerprint()`` of each pipeline the builder was last shown, keyed by
    the name its factory registers::

        [shape_confirmed]
        triage = "sha256:5cd1c1f4a52c0f1a"

    ``read`` raises ``ConfigurationError`` naming the file and the line to write when the
    file is missing, unparseable, or declares no tier.
    """

    path: Path
    tier: Tier
    stage: str | None = None
    entries: tuple[BriefEntry, ...] = ()
    decisions: tuple[Decision, ...] = ()
    understanding_confirmed_at: str | None = None
    design_confirmed_at: str | None = None
    research_confirmed_at: str | None = None
    confirmed_against: str | None = None
    shape_confirmed: tuple[tuple[str, str], ...] = ()
    """The shape of each pipeline the builder was last shown, by pipeline name."""
    comments_block_gates: bool = False
    """Whether an open comment in ``comments.toml`` fails a gate rather than being reported
    beside it (FT-39). The builder's toggle: ``comments_block_gates = true`` in the brief."""

    @classmethod
    def read(cls, path: str | Path) -> Brief:
        """Read a brief from disk."""
        target = Path(path)
        if not target.exists():
            raise ConfigurationError(_MISSING.format(path=target))
        try:
            raw = tomllib.loads(target.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(
                f"{target} is not readable as TOML: {exc}. The brief is what declares this "
                f"project's tier, so nothing can run until it parses. It starts with one "
                f'line: tier = "prototype".'
            ) from exc
        return cls.from_data(raw, path=target)

    @classmethod
    def from_data(cls, raw: dict[str, Any], *, path: Path) -> Brief:
        """Build one from parsed TOML, which is what ``read`` does with the file."""
        if "tier" not in raw:
            raise ConfigurationError(_MISSING.format(path=path))
        tier = Tier(str(raw["tier"]))
        stage = raw.get("stage")
        if stage is not None and not is_stage(str(stage).strip()):
            raise ConfigurationError(
                f"{path} declares stage {str(stage).strip() or 'none'!r}, and the six are "
                f"{', '.join(STAGES)}. A stage names where the project has got to, and the "
                f"elicitation gate reads it to decide which questions are required. Write "
                f'stage = "brainstorm" while the builder is still settling what to build, or '
                f"leave the key out and the gate reads it as `brainstorm`."
            )
        if stage is not None and str(stage).strip() not in stages_for(tier):
            raise ConfigurationError(_outside_the_tier(path, str(stage).strip(), tier))
        return cls(
            path=path,
            tier=tier,
            stage=str(stage) if stage is not None else None,
            entries=tuple(
                _entry(name, value, path, tier)
                for name, value in (raw.get("entries") or {}).items()
            ),
            decisions=decisions_from(raw.get("decisions"), path),
            understanding_confirmed_at=_confirmed_at(raw, path),
            design_confirmed_at=_confirmed_at(raw, path, key="design_confirmed_at"),
            research_confirmed_at=_confirmed_at(raw, path, key="research_confirmed_at"),
            confirmed_against=_text_or_none(raw.get("confirmed_against")),
            shape_confirmed=_shape_confirmed(raw.get("shape_confirmed"), path),
            comments_block_gates=bool(raw.get("comments_block_gates", False)),
        )

    def confirmed_shape(self, name: str) -> str | None:
        """The fingerprint the builder confirmed for one pipeline, or ``None``."""
        return dict(self.shape_confirmed).get(name)

    def unanswered(self) -> list[str]:
        """The entries recorded as ``unanswered``, in declaration order."""
        return [entry.name for entry in self.entries if entry.status == "unanswered"]

    def unseen_decisions(self) -> list[str]:
        """The decisions still recorded ``proposed``, which the builder has not settled."""
        return [d.name for d in self.decisions if not d.seen_by_the_builder]

    def kinds_with_no_decision(self) -> list[str]:
        """The decision kinds this brief records nothing for, in the taxonomy's order.

        A kind a project has nothing of is recorded ``not_applicable`` rather than left out,
        so nothing-to-decide and nobody-thought-about-it are different states.
        """
        recorded = {d.kind for d in self.decisions}
        return [name for name in kind_names() if name not in recorded]

    def entry(self, name: str) -> BriefEntry | None:
        """The entry recorded under ``name``, or ``None`` where the brief carries none.

        A question with no entry at all and one recorded ``unanswered`` are the same thing to
        a gate: the answer is missing. They read differently to a person, so both are kept.
        """
        for candidate in self.entries:
            if candidate.name == name:
                return candidate
        return None


def _text_or_none(value: Any) -> str | None:
    """A brief key read as text, and ``None`` where it is absent or blank."""
    text = str(value).strip() if value is not None else ""
    return text or None


def _shape_confirmed(value: Any, path: Path) -> tuple[tuple[str, str], ...]:
    """``[shape_confirmed]`` as pipeline name to fingerprint, refusing anything else."""
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ConfigurationError(
            f"{path} declares shape_confirmed as {type(value).__name__}, and it is a table "
            f"of one fingerprint per pipeline. It records the picture the builder was shown, "
            f"so what changed since is exact.\n"
            f'Write it as: [shape_confirmed]\ntriage = "sha256:5cd1c1f4a52c0f1a"'
        )
    found = []
    for name, fingerprint in value.items():
        text = _text_or_none(fingerprint)
        if text is None:
            raise ConfigurationError(
                f"{path} declares shape_confirmed.{name} with no fingerprint. The value is "
                f"what Pipeline.graph_fingerprint() returned when the builder agreed to the "
                f"shape, and an empty one dates nothing.\n"
                f'Write the fingerprint, or leave the pipeline out: {name} = "sha256:...".'
            )
        found.append((str(name), text))
    return tuple(sorted(found))


# Which file each confirmation key dates, and which check reports it missing.
_CONFIRMS = {
    "understanding_confirmed_at": ("idea.md", "FT-29", STAGES[0]),
    "design_confirmed_at": ("design.md", "FT-34", "shape"),
    "research_confirmed_at": ("research.md", "FT-36", "research"),
}


def _confirmed_at(
    raw: dict[str, Any], path: Path, key: str = "understanding_confirmed_at"
) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    name = str(value).strip()
    if not is_stage(name):
        document, check, first = _CONFIRMS[key]
        raise ConfigurationError(
            f"{path} declares {key} {name or 'none'!r}, and the "
            f"six stages are {', '.join(STAGES)}. It names the stage at which {document} was last "
            f"confirmed to still describe the project. Write {key} = "
            f'"{first}" after reading that file, or leave the key out and {check} reports '
            f"it as unconfirmed."
        )
    return name


def _outside_the_tier(path: Path, stage: str, tier: Tier) -> str:
    """Why a stage and a tier that exclude it cannot both be declared.

    The text names measuring, because ``measure`` is the only stage any tier leaves out. A tier
    that excludes another one needs this message rewritten alongside ``STAGES_BY_TIER``.
    """
    return (
        f"{path} declares stage {stage!r} and tier {str(tier)!r}, and a project at that tier "
        f"has the stages {', '.join(stages_for(tier))}. Stage {stage!r} is not one of them, so "
        f"the brief claims both to be measuring and to report no number.\n"
        f'Write tier = "evaluated" for a project that reports how often it is right, or '
        f'stage = "{_last_before(stage, tier)}" for one that stops before measuring.'
    )


def _last_before(stage: str, tier: Tier) -> str:
    """The latest stage this tier has that comes before ``stage``."""
    earlier = [name for name in stages_for(tier) if STAGES.index(name) < STAGES.index(stage)]
    return earlier[-1] if earlier else STAGES[0]


def _entry(name: str, value: Any, path: Path, tier: Tier) -> BriefEntry:
    if not isinstance(value, dict):
        raise ConfigurationError(
            f"{path}: entry {name!r} is {type(value).__name__}, and a brief entry is a table "
            f'carrying at least a status: [entries.{name}] then status = "answered".'
        )
    status = str(value.get("status", "")).strip()
    if status not in STATUSES:
        raise ConfigurationError(
            f"{path}: entry {name!r} has status {status or 'none'!r}. The three are "
            f"{', '.join(STATUSES)}. An entry not yet put to the builder is "
            f'"unanswered", and one put off to a later stage is "deferred" naming that stage.'
        )
    deferred_to = _deferred_to(name, value, path, status, tier)
    source = str(value.get("source") or DEFAULT_SOURCE).strip()
    if source not in SOURCES:
        raise ConfigurationError(
            f"{path}: entry {name!r} names source {source or 'none'!r}. The four are "
            f"{', '.join(SOURCES)}. Leave it out for an answer the builder gave; write "
            f'source = "coding_agent" for one they have not seen, which a required question '
            f"fails on (FT-24) until it is put to them."
        )
    return BriefEntry(
        name=name,
        status=status,
        answer=str(value["answer"]) if value.get("answer") is not None else None,
        deferred_to=deferred_to,
        source=source,
        asked_at=_asked_at(name, value, path, status),
        recorded_at=recorded_at(
            value.get("recorded_at"),
            required=status == "answered",
            where=f"{path}: entry {name!r} is answered and",
            fix=f'Add recorded_at = "{AN_EXAMPLE_STAMP}" under [entries.{name}].',
        ),
    )


def _deferred_to(
    name: str, value: dict[str, Any], path: Path, status: str, tier: Tier
) -> str | None:
    """The stage a deferred entry is put at instead, and what a deferral may not name.

    A deferral is legitimate and has to say where it goes, or a postponed decision reads the
    same as a forgotten one. A stage the project's tier never reaches is refused for the same
    reason: the answer would never come due.
    """
    deferred_to = str(value.get("deferred_to") or "").strip()
    if status == "deferred" and not deferred_to:
        raise ConfigurationError(
            f"{path}: entry {name!r} is deferred and names no stage. Deferral is legitimate "
            f"and has to say where it is deferred to, or a postponed decision reads the same "
            f'as a forgotten one. Add deferred_to = "measure".'
        )
    if not deferred_to:
        return None
    if not is_stage(deferred_to):
        raise ConfigurationError(
            f"{path}: entry {name!r} is deferred to {deferred_to!r}, and the six stages are "
            f"{', '.join(STAGES)}. A deferral names the stage the question is put at instead, "
            f'so the gate there can require it. Write deferred_to = "measure".'
        )
    if deferred_to not in stages_for(tier):
        raise ConfigurationError(
            f"{path}: entry {name!r} is deferred to {deferred_to!r}, and a project at tier "
            f"{str(tier)!r} has the stages {', '.join(stages_for(tier))}. It never reaches "
            f"{deferred_to!r}, so the answer would never come due and the deferral reads as a "
            f"question that never has to be asked.\n"
            f'Defer it to "{stages_for(tier)[-1]}", answer it now, or write tier = "evaluated" '
            f"for a project that measures."
        )
    return deferred_to


def _asked_at(name: str, value: dict[str, Any], path: Path, status: str) -> str | None:
    """The stage this entry was last put at, and what a re-asked question may not record.

    A question every gate puts again has no later stage to be deferred to, so a deferral on
    one is refused: it would silence the question at every stage after this one.
    """
    asked_at = str(value.get("asked_at") or "").strip()
    if asked_at and not is_stage(asked_at):
        raise ConfigurationError(
            f"{path}: entry {name!r} was asked at {asked_at!r}, and the six stages are "
            f"{', '.join(STAGES)}. It names the stage the question was last put to the "
            f'builder at. Write asked_at = "shape".'
        )
    re_asked = any(q.name == name and q.re_asked_each_stage for q in QUESTIONS)
    if status == "deferred" and re_asked:
        raise ConfigurationError(
            f"{path}: entry {name!r} is deferred, and it is a question every gate puts again "
            f"rather than one a single answer settles. There is no later stage to defer it "
            f"to: deferring it here would silence it at every stage after this one.\n"
            f'Ask it, and record what came back with asked_at naming this stage. "Nothing" '
            f"is an answer and is recorded as one."
        )
    return asked_at or None


_MISSING = (
    "No tier declared at {path}, so the conformance checks cannot tell which gates apply to "
    "this project. Write the file:\n"
    "\n"
    '    tier = "prototype"     # hygiene that costs nothing, and applies to everything\n'
    '    tier = "evaluated"     # the project reports a number about how well it works\n'
    "\n"
    "A tier is a claim about what this project is for, and the library cannot infer it: the "
    "check for a missing evaluation fires exactly when a project claims `evaluated` and has "
    "none, so reading the claim off the artifacts would stop that check firing at all."
)
