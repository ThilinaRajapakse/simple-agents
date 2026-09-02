"""Writing an answer or a decision into the brief, stamped by the clock.

``recorded_at`` says when what an entry says was written down, and a stamp a coding agent
composes is a guess about the time: the first project on the public package wrote twenty of
thirty-three in local time with a UTC suffix. These two functions write the entry and read the
clock themselves, so the stamp is a reading rather than a composition. ``simple-agents record``
is the same two from the command line (`docs/conformance.md` §2.3)::

    from simple_agents.conformance import record_answer, record_decision

    record_answer("brief.toml", "used_through",
                  answer="A phone app over an HTTP API on the builder's machine.")
    record_decision("brief.toml", "pool_size", kind="constant", status="agreed",
                    chose="200", considered=["60, the first guess"],
                    produces=["CANDIDATES_RETRIEVED"], rests_on=["presentation"],
                    because="the audit measured recall at 200")

A table already in the file is replaced whole, keeping any key the call did not name; the
rest of the file is left byte for byte. The file is re-read as a brief before it is written,
so a value ``Brief.read`` would refuse is refused here and nothing changes on disk.

Both raise :class:`~simple_agents.errors.ConfigurationError` for a name that is not a
question, a status or stage outside the known ones, an answered entry with no answer, and a
brief the result would not parse as.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..errors import ConfigurationError
from .brief import SOURCES, Brief
from .brief import STATUSES as ENTRY_STATUSES
from .decisions import STATUSES as DECISION_STATUSES
from .decisions import kind as decision_kind
from .elicitation import names as question_names
from .elicitation import question
from .stages import STAGES, is_stage

__all__ = [
    "Recorded",
    "TOP_LEVEL_KEYS",
    "CONFIRMED_DOCUMENTS",
    "clock_stamp",
    "newest_run_fingerprints",
    "record_answer",
    "record_decision",
    "record_key",
    "record_shape",
]

# A name a decision may be recorded under: what a TOML bare key holds.
_A_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_A_HEADER = re.compile(r"^\[[A-Za-z_]")
_A_KEY_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")

# The keys above the first table, each a scalar the checks read.
TOP_LEVEL_KEYS = (
    "tier",
    "stage",
    "results",
    "comments_block_gates",
    "understanding_confirmed_at",
    "research_confirmed_at",
    "design_confirmed_at",
    "confirmed_against",
)
# The document each `*_confirmed_at` key dates, by the name a person calls it.
CONFIRMED_DOCUMENTS = {
    "idea": "understanding_confirmed_at",
    "research": "research_confirmed_at",
    "design": "design_confirmed_at",
}


@dataclass(frozen=True, slots=True)
class Recorded:
    """What one call wrote: the file, the table or key, the stamp, and whether it replaced one.

    ``recorded_at`` is empty for a top-level key or a shape, which carry no stamp.
    """

    path: Path
    table: str
    recorded_at: str
    replaced: bool


def clock_stamp() -> str:
    """The clock, now, as ``recorded_at`` writes it: ISO 8601 in UTC to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def record_answer(
    path: str | os.PathLike[str],
    name: str,
    *,
    answer: str | None = None,
    status: str = "answered",
    source: str | None = None,
    asked_at: str | None = None,
    deferred_to: str | None = None,
) -> Recorded:
    """Write ``[entries.<name>]`` with the clock's stamp.

    ``name`` is a question's key. ``answer`` may be left out on an entry that already holds
    one, or on a ``deferred`` or ``unanswered`` entry. A question every gate puts again needs
    ``asked_at``, the stage this answer was given at::

        record_answer("brief.toml", "anything_else", asked_at="build",
                      answer="brainstorm: nothing. build: the export is stale after Tuesdays.")
        record_answer("brief.toml", "budget", status="deferred", deferred_to="measure")
    """
    target = Path(path)
    text, raw = _read(target)
    _check_answer(name, status, source, asked_at, deferred_to)
    fields = _answer_fields(
        (raw.get("entries") or {}).get(name) or {},
        name,
        answer=answer,
        status=status,
        source=source,
        asked_at=asked_at,
        deferred_to=deferred_to,
    )
    stamp = clock_stamp()
    fields["recorded_at"] = stamp
    block = _block(f"entries.{name}", fields, _ENTRY_ORDER, ("answer",))
    return _splice(target, text, f"entries.{name}", block, stamp)


def record_decision(
    path: str | os.PathLike[str],
    name: str,
    *,
    kind: str,
    status: str = "proposed",
    chose: str | None = None,
    considered: Iterable[str] = (),
    because: str | None = None,
    rests_on: Iterable[str] = (),
    produces: Iterable[str] = (),
    stage: str | None = None,
) -> Recorded:
    """Write ``[decisions.<name>]`` with the clock's stamp.

    ``kind`` is one of the six decision kinds and ``status`` one of the four. ``rests_on`` is
    written as ``from`` and names question keys; ``produces`` names what the decision became
    in the code, on the four kinds that carry it::

        record_decision("brief.toml", "show_catalogue", kind="dependency", status="agreed",
                        chose="TVmaze, caching every payload whole",
                        considered=["TMDB, rejected on licence"],
                        produces=["catalogue_search", "catalogue_episodes"],
                        rests_on=["approaches"], because="no key, two calls a second")
    """
    target = Path(path)
    text, raw = _read(target)
    _check_decision(name, kind, status, rests_on, stage)
    fields = _decision_fields(
        (raw.get("decisions") or {}).get(name) or {},
        kind=kind,
        status=status,
        chose=chose,
        considered=considered,
        because=because,
        rests_on=rests_on,
        produces=produces,
        stage=stage,
    )
    stamp = clock_stamp()
    fields["recorded_at"] = stamp
    block = _block(f"decisions.{name}", fields, _DECISION_ORDER, ("because",))
    return _splice(target, text, f"decisions.{name}", block, stamp)


def record_key(path: str | os.PathLike[str], key: str, value: str | bool) -> Recorded:
    """Write one of the brief's top-level keys, above the first table.

    ``key`` is one of :data:`TOP_LEVEL_KEYS`. ``comments_block_gates`` takes a bool and the
    rest a string; ``results`` names a file under the project, ``confirmed_against`` a
    ``sha256:`` stamp, and a stage the tier never reaches is refused as the brief refuses it::

        record_key("brief.toml", "stage", "build")
        record_key("brief.toml", "design_confirmed_at", "shape")
        record_key("brief.toml", "confirmed_against", newest_run_fingerprints(".")[0])
    """
    target = Path(path)
    text, _raw = _read(target)
    _check_key(target, key, value)
    line = f"{key} = {_value(value, key, 'the brief')}\n"
    lines = text.splitlines(keepends=True)
    region = _top_level_end(lines)
    for index in range(region):
        found = _A_KEY_LINE.match(lines[index])
        if found and found.group(1) == key:
            new_text = "".join(lines[:index]) + line + "".join(lines[index + 1 :])
            return _write(target, new_text, key, replaced=True)
    last_key = max((i for i in range(region) if _A_KEY_LINE.match(lines[i])), default=None)
    at = last_key + 1 if last_key is not None else 0
    new_text = "".join(lines[:at]) + line + "".join(lines[at:])
    return _write(target, new_text, key, replaced=False)


def record_shape(path: str | os.PathLike[str], pipeline: str, fingerprint: str) -> Recorded:
    """Write one pipeline's entry under ``[shape_confirmed]``, keeping the others.

    ``fingerprint`` is ``Pipeline.graph_fingerprint()`` of the picture the builder agreed to::

        record_shape("brief.toml", "recommend", pipeline.graph_fingerprint())
    """
    target = Path(path)
    text, raw = _read(target)
    if not _A_NAME.match(pipeline):
        raise ConfigurationError(
            f"{pipeline!r} cannot name a pipeline. A name is letters, digits, `_` and `-`, the "
            f"name its factory registers."
        )
    _check_stamp(fingerprint, f"shape_confirmed.{pipeline}")
    fields = dict(raw.get("shape_confirmed") or {})
    fields[pipeline] = fingerprint
    block = _block("shape_confirmed", fields, (), ())
    return _splice(target, text, "shape_confirmed", block, "")


def newest_run_fingerprints(root: str | os.PathLike[str]) -> tuple[str, str, Path]:
    """The newest agent run's ``behaviour_fingerprint`` and ``graph_fingerprint``, and its path.

    What FT-38 compares ``confirmed_against`` to, read the way the checks read it::

        stamp, shape, run = newest_run_fingerprints(".")

    Raises :class:`~simple_agents.errors.ConfigurationError` where no agent run is on disk
    or the newest carries no stamp.
    """
    from .artifacts import Artifacts, read_json

    found = Artifacts.discover(Path(root))
    if found.run_dir is None:
        raise ConfigurationError(
            f"No run of the project's agent under {Path(root) / 'runs'}, so nothing records "
            f"what the code is. Run the pipeline once, and the stamp is on its manifest."
        )
    manifest, reason = read_json(found.run_dir / "manifest.json")
    stamp = (manifest or {}).get("behaviour_fingerprint") if isinstance(manifest, dict) else None
    shape = (manifest or {}).get("graph_fingerprint") if isinstance(manifest, dict) else None
    if reason is not None or not isinstance(stamp, str) or not isinstance(shape, str):
        raise ConfigurationError(
            f"The newest run, {found.run_dir}, carries no readable behaviour_fingerprint, so "
            f"it was written before the field existed. Run the pipeline once more."
        )
    return stamp, shape, found.run_dir


def _check_key(target: Path, key: str, value: Any) -> None:
    if key not in TOP_LEVEL_KEYS:
        raise ConfigurationError(
            f"{key!r} is not a key the brief carries above its tables. The keys are "
            f"{', '.join(TOP_LEVEL_KEYS)}; an answer goes under [entries.<name>] through "
            f"record_answer, and a decision under [decisions.<name>] through record_decision."
        )
    if key == "comments_block_gates":
        if not isinstance(value, bool):
            raise ConfigurationError(
                "comments_block_gates is true or false: whether an open comment fails a gate."
            )
        return
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{key} takes a string, and was given {value!r}.")
    if key == "results" and not (target.parent / value).is_file():
        raise ConfigurationError(
            f"results = {value!r} names no file under {target.parent}. It names the results "
            f"file this project reports, relative to the brief: evals/results/<name>.json."
        )
    if key == "confirmed_against":
        _check_stamp(value, key)


def _check_stamp(value: str, key: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ConfigurationError(
            f"{key} = {value!r} is not a fingerprint. It holds what the library stamps, "
            f"sha256:<digest>: Pipeline.behaviour_fingerprint(model=client) for "
            f"confirmed_against, Pipeline.graph_fingerprint() for shape_confirmed, or the value "
            f"a run's manifest records."
        )


def _top_level_end(lines: list[str]) -> int:
    """The index of the first table header, which ends the region the top-level keys live in."""
    for index, line in enumerate(lines):
        if _A_HEADER.match(line):
            return index
    return len(lines)


def _write(target: Path, new_text: str, what: str, *, replaced: bool) -> Recorded:
    """Validate ``new_text`` as a brief and replace the file atomically."""
    try:
        Brief.from_data(tomllib.loads(new_text), path=target)
    except (ConfigurationError, tomllib.TOMLDecodeError) as exc:
        raise ConfigurationError(
            f"Recording {what} would leave {target} unreadable as a brief, so nothing was "
            f"written: {exc}"
        ) from exc
    scratch = target.with_name(target.name + ".writing")
    scratch.write_text(new_text, encoding="utf-8")
    os.replace(scratch, target)
    return Recorded(path=target, table=what, recorded_at="", replaced=replaced)


# -- what a call may say ------------------------------------------------------------------


def _check_answer(
    name: str, status: str, source: str | None, asked_at: str | None, deferred_to: str | None
) -> None:
    """Refuse a name, status, source or stage the brief would not read."""
    if name not in question_names():
        raise ConfigurationError(
            f"{name!r} is not a question, so no gate reads an entry under it. The keys are "
            f"{', '.join(question_names())}; `simple-agents questions --stage ship` prints "
            f"each with its question."
        )
    if status not in ENTRY_STATUSES:
        raise ConfigurationError(
            f"status={status!r} is not one of {', '.join(ENTRY_STATUSES)}. An entry put to the "
            f'builder and answered is "answered", one put off to a later stage is "deferred" '
            f'naming that stage, and one not yet asked is "unanswered".'
        )
    if source is not None and source not in SOURCES:
        raise ConfigurationError(
            f"source={source!r} is not one of {', '.join(SOURCES)}. Leave it out for an answer "
            f'the builder gave; "coding_agent" marks one they have not seen.'
        )
    for label, stage in (("asked_at", asked_at), ("deferred_to", deferred_to)):
        if stage is not None and not is_stage(stage):
            raise ConfigurationError(
                f"{label}={stage!r} is not a stage. The six are {', '.join(STAGES)}."
            )


def _answer_fields(
    existing: dict[str, Any],
    name: str,
    *,
    answer: str | None,
    status: str,
    source: str | None,
    asked_at: str | None,
    deferred_to: str | None,
) -> dict[str, Any]:
    """The entry's keys after this call: what was there, overwritten by what was named."""
    fields = dict(existing)
    fields["status"] = status
    if answer is not None:
        fields["answer"] = answer.rstrip("\n")
    if status == "answered" and not str(fields.get("answer") or "").strip():
        raise ConfigurationError(
            f"entries.{name} would be recorded answered with no answer. Pass answer=, or "
            f'status="deferred" with the stage it moves to.'
        )
    for key, value in (("source", source), ("asked_at", asked_at), ("deferred_to", deferred_to)):
        if value is not None:
            fields[key] = value
    if status != "deferred":
        fields.pop("deferred_to", None)
    if question(name).re_asked_each_stage and not fields.get("asked_at"):
        raise ConfigurationError(
            f"entries.{name} is put again at every stage, so the entry says which stage this "
            f'answer was given at. Pass asked_at="build", or the stage it was asked at.'
        )
    return fields


def _check_decision(
    name: str, kind: str, status: str, rests_on: Iterable[str], stage: str | None
) -> None:
    """Refuse a name, kind, status, `from` or stage the brief would not read."""
    if not _A_NAME.match(name):
        raise ConfigurationError(
            f"{name!r} cannot name a decision. A name is letters, digits, `_` and `-`, and "
            f"heads the table [decisions.{name}]."
        )
    decision_kind(kind)
    if status not in DECISION_STATUSES:
        raise ConfigurationError(
            f"status={status!r} is not one of {', '.join(DECISION_STATUSES)}. A decision the "
            f'builder has not seen is "proposed", one they agreed is "agreed", one they changed '
            f'is "changed", and a kind this project has nothing of is "not_applicable".'
        )
    unknown = [n for n in rests_on if n not in question_names()]
    if unknown:
        raise ConfigurationError(
            f"rests_on names {', '.join(repr(n) for n in unknown)}, which "
            f"{'is' if len(unknown) == 1 else 'are'} not a question. `from` names the answers "
            f"a decision was derived from, by their keys: {', '.join(question_names())}."
        )
    if stage is not None and not is_stage(stage):
        raise ConfigurationError(
            f"stage={stage!r} is not a stage. The six are {', '.join(STAGES)}."
        )


def _decision_fields(
    existing: dict[str, Any],
    *,
    kind: str,
    status: str,
    chose: str | None,
    considered: Iterable[str],
    because: str | None,
    rests_on: Iterable[str],
    produces: Iterable[str],
    stage: str | None,
) -> dict[str, Any]:
    """The decision's keys after this call: what was there, overwritten by what was named."""
    fields = dict(existing)
    fields["kind"] = kind
    fields["status"] = status
    for key, text in (("chose", chose), ("because", because), ("stage", stage)):
        if text is not None:
            fields[key] = text.rstrip("\n")
    for key, names in (("considered", considered), ("from", rests_on), ("produces", produces)):
        listed = list(names)
        if listed:
            fields[key] = listed
    return fields


# -- the file ----------------------------------------------------------------------------


def _read(target: Path) -> tuple[str, dict[str, Any]]:
    """The brief's text and its parse, refusing a file that is missing or will not parse."""
    if not target.exists():
        raise ConfigurationError(
            f"No brief at {target}. The brief starts with the tier the project claims, and "
            f'an entry is written into it: write tier = "prototype" to {target} first.'
        )
    text = target.read_text(encoding="utf-8")
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(
            f"{target} is not readable as TOML: {exc}. Nothing is written into a brief that "
            f"does not parse, since the entry could not be read back either."
        ) from exc
    if not isinstance(raw, dict):  # pragma: no cover - tomllib returns a dict
        raise ConfigurationError(f"{target} did not parse to a table.")
    return text, raw


def _splice(target: Path, text: str, header: str, block: str, stamp: str) -> Recorded:
    """Replace the table under ``header`` with ``block``, or append it, and write atomically."""
    lines = text.splitlines(keepends=True)
    start = _header_line(lines, header)
    if start is None:
        body = text.rstrip("\n")
        new_text = (body + "\n\n" if body else "") + block + "\n"
        replaced = False
    else:
        end = _end_of_table(lines, start)
        rest = "".join(lines[end:])
        new_text = "".join(lines[:start]) + block + ("\n\n" + rest if rest else "\n")
        replaced = True
    written = _write(target, new_text, f"[{header}]", replaced=replaced)
    return Recorded(path=target, table=header, recorded_at=stamp, replaced=written.replaced)


def _header_line(lines: list[str], header: str) -> int | None:
    wanted = re.compile(rf"^\[{re.escape(header)}\]\s*(#.*)?$")
    for index, line in enumerate(lines):
        if wanted.match(line):
            return index
    return None


def _end_of_table(lines: list[str], start: int) -> int:
    """The index of the line the next table starts on, or the end of the file.

    A line opening with ``[`` inside a multi-line string is not a header, so a candidate is
    taken only where the text from the header up to it parses on its own.
    """
    for index in range(start + 1, len(lines)):
        if _A_HEADER.match(lines[index]):
            try:
                tomllib.loads("".join(lines[start:index]))
            except tomllib.TOMLDecodeError:
                continue
            return index
    return len(lines)


# -- rendering ---------------------------------------------------------------------------

_ENTRY_ORDER = ("status", "source", "asked_at", "deferred_to", "recorded_at")
_DECISION_ORDER = (
    "kind",
    "status",
    "stage",
    "recorded_at",
    "from",
    "produces",
    "chose",
    "considered",
)


def _block(
    header: str, fields: dict[str, Any], first: tuple[str, ...], last: tuple[str, ...]
) -> str:
    lines = [f"[{header}]"]
    for key in first:
        if key in fields:
            lines.append(_pair(key, fields[key], header))
    for key in fields:
        if key not in first and key not in last:
            lines.append(_pair(key, fields[key], header))
    for key in last:
        if key in fields:
            lines.append(_pair(key, fields[key], header))
    return "\n".join(lines)


def _pair(key: str, value: Any, header: str) -> str:
    return f"{key} = {_value(value, key, header)}"


def _value(value: Any, key: str, header: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        items = [_value(item, key, header) for item in value]
        if any("\n" in item for item in items) or sum(len(item) for item in items) > 80:
            return "[\n" + "".join(f"  {item},\n" for item in items) + "]"
        return "[" + ", ".join(items) + "]"
    raise ConfigurationError(
        f"[{header}] holds {key} = {value!r}, which this writer cannot render. It writes "
        f"strings, numbers, booleans and lists of them; move anything else out of the table "
        f"before recording into it."
    )


def _string(value: str) -> str:
    """A TOML basic string: one line through the JSON escapes, several as a multi-line string."""
    if "\n" not in value:
        return json.dumps(value, ensure_ascii=False)
    body = value.replace("\\", "\\\\").replace('"""', '""\\"')
    return '"""\n' + body + '"""'
