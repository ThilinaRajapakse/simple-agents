"""The conversation between the builder and the coding agent, held on parts of the system.

``comments.toml`` lives beside the brief. One ``[[comment]]`` per thread: someone points at
a part of the picture and says something, and replies accumulate under it until it is
addressed. The served view writes the builder's side; the coding agent reads the file, does
what a thread asks or takes it back to the builder, and writes its replies here too::

    version = "1"

    [[comment]]
    id = "c3"
    at = "recommend/judge_candidates"
    by = "builder"
    said = "Why does this rank the whole catalogue before truncating?"
    about = "judge_candidates, a model call in recommend"
    stage = "build"
    shape = "sha256:988e4b3bf95de3b8"
    when = "2026-08-27T06:12:03.412Z"
    status = "open"

    [[comment.replies]]
    by = "coding_agent"
    said = "It should not. Capping the pool before ranking; the change lands today."
    when = "2026-08-27T06:31:44.002Z"

``at`` is the address the view shows on every element: a pipeline (``"recommend"``), a step
(``"recommend/judge_candidates"``), an edge (``"recommend/judge_candidates->select"``), a
resource (``"resource:catalogue"``), a question (``"question:how_far"``), a decision
(``"decision:candidate_pool"``), or the project itself (``"project"``). ``about``, ``stage``
and ``shape`` are a snapshot of what the writer was looking at: what the address resolved to
in words, the stage the project was at, and the addressed pipeline's structural fingerprint.
An address rots when a step is renamed; the snapshot keeps the thread interpretable after
the thing it pointed at moved.

**A prompt has three addresses of its own**, for a whole prompt, one value in it, and words
selected in it (`docs/view.md` §6.10):

    prompt:recommend/judge_candidates                 the whole prompt
    prompt:recommend/judge_candidates#catalogue       the value called catalogue
    prompt:recommend/judge_candidates#words-3f9a1c2d5e70   words the builder selected

A selection is keyed by a digest of the words, so selecting the same words again lands in the
thread that is already there. Three more snapshot fields carry what a selection thread needs
once the text has been rewritten: ``quoted`` is the words verbatim, ``run`` is the run the
filled prompt came from, and ``instruction`` is the digest the prompt's fixed text had at the
time, which is what says the wording has moved since. ``quoted`` is cut at 2,000 characters
with ``quoted_chars`` giving the length before the cut.

``kind`` says what the thread is doing: a plain ``comment``, an ``answer`` to an open
question, or an ``amendment`` to something already answered or agreed. An ``answer`` or an
``amendment`` is not written into the brief by anything here: the coding agent reads it,
asks whatever follow-up the question's scaffold needs, and records the entry itself, so the
brief stays what passed between them.

A thread is ``open`` until what it asks for is done or decided, then ``addressed`` with
``addressed_by`` naming what answered it and ``addressed_when`` saying when; ``withdrawn``
is the writer taking it back. The gates report open threads at every stage, and
``comments_block_gates = true`` in the brief makes them refuse instead (FT-39).

``version`` is the file's own format, for reading old files after the shape grows.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

from ..errors import ConfigurationError

__all__ = [
    "Comment",
    "Comments",
    "Reply",
    "read_comments",
    "append_comment",
    "append_reply",
    "set_status",
    "DEFAULT_COMMENTS",
    "COMMENTS_FORMAT_VERSION",
    "prompt_address",
    "names_a_prompt",
    "names_a_thread",
]

DEFAULT_COMMENTS = "comments.toml"
COMMENTS_FORMAT_VERSION = "2"

_STATUSES = ("open", "addressed", "withdrawn")
_KINDS = ("comment", "answer", "amendment")
_SIDES = ("builder", "coding_agent")

_HEADER = (
    "# What was said about parts of the system, and what came back. Written by the served\n"
    "# `simple-agents view` and by the coding agent; read by both, and by the gates (FT-39).\n"
    "# docs/view.md#5 is the shape.\n"
    f'version = "{COMMENTS_FORMAT_VERSION}"\n'
)


def prompt_address(address: str) -> tuple[str, str, str] | None:
    """The pipeline, the step and the part one ``prompt:`` address names, or ``None``.

    ::

        prompt_address("prompt:trip/plan#notes")     # ('trip', 'plan', 'notes')
        prompt_address("trip/plan")                  # None

    The part is ``""`` for the whole prompt, a value's name, or ``words-`` and a digest of the
    words a builder selected (`docs/view.md` §5). ``None`` for any other address, and for a
    ``prompt:`` address naming no step, which the page never writes.
    """
    if not address.startswith("prompt:"):
        return None
    where, _, part = address.removeprefix("prompt:").partition("#")
    pipeline, _, node_id = where.partition("/")
    return (pipeline, node_id, part) if pipeline and node_id else None


def names_a_thread(address: str) -> str | None:
    """One ``prompt:`` address in words, named by the step alone, or ``None``.

    ::

        names_a_thread("prompt:trip/plan#notes")   # 'the notes value in the prompt for plan'

    What a page or a gate message shows beside a thread. A thread's own ``about`` names the
    step more fully, with the kind of step it is and the pipeline it is in, because the view
    had the drawing in hand when it wrote it.
    """
    held = prompt_address(address)
    return None if held is None else names_a_prompt(held[2], held[1])


def names_a_prompt(part: str, named: str) -> str:
    """What a thread at a prompt address is about, in words.

    ``named`` is the step, already named for whoever is reading::

        names_a_prompt("notes", "plan")   # 'the notes value in the prompt for plan'
    """
    if not part:
        return f"the prompt for {named}"
    if part.startswith("words-"):
        return f"words in the prompt for {named}"
    return f"the {part} value in the prompt for {named}"


def _now() -> str:
    from .trajectory import utc_now

    return utc_now()


@dataclass(frozen=True, slots=True)
class Reply:
    """One turn in a thread. ``by`` is ``"builder"`` or ``"coding_agent"``."""

    by: str
    said: str
    when: str | None = None


@dataclass(frozen=True, slots=True)
class Comment:
    """One thread: what was said at an address, its snapshot, and every reply under it.

    ``kind`` is ``"comment"``, ``"answer"`` or ``"amendment"``. ``about``, ``stage`` and
    ``shape`` snapshot what the writer was looking at, and ``quoted``, ``run`` and
    ``instruction`` snapshot the rest of it on a thread about words in a prompt: the words
    themselves, the run whose prompt they were read in, and the digest the fixed text had
    then. ``quoted_chars`` is the length before a long selection was cut. ``addressed_by``
    and ``addressed_when`` are only meaningful once ``status`` is ``"addressed"``.
    """

    at: str
    said: str
    id: str = ""
    by: str = "builder"
    kind: str = "comment"
    about: str | None = None
    stage: str | None = None
    shape: str | None = None
    quoted: str | None = None
    quoted_chars: int | None = None
    run: str | None = None
    instruction: str | None = None
    when: str | None = None
    status: str = "open"
    addressed_by: str | None = None
    addressed_when: str | None = None
    replies: tuple[Reply, ...] = ()

    @property
    def open(self) -> bool:
        return self.status == "open"


@dataclass(frozen=True, slots=True)
class Comments:
    """Every thread in the file, in file order. Empty where the file does not exist."""

    path: str | None
    all: tuple[Comment, ...] = ()
    version: str = COMMENTS_FORMAT_VERSION

    @property
    def open(self) -> tuple[Comment, ...]:
        return tuple(c for c in self.all if c.open)

    def at(self, address: str) -> tuple[Comment, ...]:
        """The threads addressed to one element, open first."""
        matched = [c for c in self.all if c.at == address]
        return tuple(sorted(matched, key=lambda c: not c.open))

    def thread(self, comment_id: str) -> Comment | None:
        for candidate in self.all:
            if candidate.id == comment_id:
                return candidate
        return None


def read_comments(path: str | Path) -> Comments:
    """Read ``comments.toml``, or an empty record where there is none.

    ::

        comments = read_comments(root / "comments.toml")
        comments.open                       # what still waits on an answer
        comments.at("recommend/select")     # the threads on one step

    A thread written before ids existed gets one from its position, and the next write
    makes it permanent. Raises :class:`~simple_agents.errors.ConfigurationError` on a file
    that cannot be parsed or an entry missing ``at`` or ``said``, naming the entry, because
    a comment that cannot be read is the builder's words being silently lost.
    """
    target = Path(path).expanduser()
    if not target.exists():
        return Comments(path=None)
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(
            f"{target} could not be parsed as TOML: {error}. Each thread is one "
            f"[[comment]] table with `at`, `said`, and optionally `id`, `by`, `kind`, "
            f"`about`, `stage`, `shape`, `quoted`, `quoted_chars`, `run`, `instruction`, "
            f"`when`, `status`, `addressed_by`, `addressed_when` and [[comment.replies]] "
            f"entries."
        ) from error

    entries = raw.get("comment")
    version = str(raw.get("version") or COMMENTS_FORMAT_VERSION)
    if entries is None:
        return Comments(path=str(target), version=version)
    if not isinstance(entries, list):
        raise ConfigurationError(
            f"{target} holds `comment` as a single table. Write each as its own "
            f"[[comment]] entry, double-bracketed, so more can be added without reshaping "
            f"the file."
        )

    comments = []
    for index, entry in enumerate(entries):
        comments.append(_one(target, index, entry))
    return Comments(path=str(target), all=tuple(comments), version=version)


def _text(entry: dict, key: str) -> str | None:
    value = entry.get(key)
    return str(value) if value not in (None, "") else None


def _a_count(value: object) -> int | None:
    """One recorded count, and ``None`` for anything that is not one."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _one(target: Path, index: int, entry: dict) -> Comment:
    at, said = entry.get("at"), entry.get("said")
    if not isinstance(at, str) or not at.strip() or not isinstance(said, str) or not said.strip():
        raise ConfigurationError(
            f"{target} entry {index + 1} is missing `at` or `said`. `at` is the address "
            f"the view shows on the element the thread is about, and `said` is the "
            f"writer's words, verbatim."
        )
    status = str(entry.get("status", "open"))
    if status not in _STATUSES:
        raise ConfigurationError(
            f"{target} entry {index + 1} has status={status!r}. A thread is 'open' until "
            f"the thing it asks for is done or decided, then 'addressed' with "
            f"addressed_by naming what answered it; 'withdrawn' is the writer taking "
            f"it back."
        )
    kind = str(entry.get("kind", "comment"))
    if kind not in _KINDS:
        raise ConfigurationError(
            f"{target} entry {index + 1} has kind={kind!r}, and the three are 'comment', "
            f"'answer' and 'amendment'."
        )
    by = str(entry.get("by", "builder"))
    if by not in _SIDES:
        raise ConfigurationError(
            f"{target} entry {index + 1} has by={by!r}, and a thread is by 'builder' or "
            f"'coding_agent'."
        )
    replies = []
    for spot, reply in enumerate(entry.get("replies") or []):
        reply_by = str(reply.get("by", ""))
        reply_said = reply.get("said")
        if reply_by not in _SIDES or not isinstance(reply_said, str) or not reply_said.strip():
            raise ConfigurationError(
                f"{target} entry {index + 1} reply {spot + 1} needs by= 'builder' or "
                f"'coding_agent' and non-empty said=."
            )
        replies.append(
            Reply(
                by=reply_by,
                said=reply_said.strip(),
                when=_text(reply, "when") or _text(reply, "date"),
            )
        )
    return Comment(
        at=at.strip(),
        said=said.strip(),
        id=str(entry.get("id") or f"c{index + 1}"),
        by=by,
        kind=kind,
        when=_text(entry, "when") or _text(entry, "date"),
        status=status,
        addressed_by=_text(entry, "addressed_by"),
        addressed_when=_text(entry, "addressed_when"),
        replies=tuple(replies),
        **_snapshot_in(entry),
    )


def _snapshot_in(entry: dict) -> dict:
    """What the writer was looking at, as the file recorded it.

    ``about``, ``stage`` and ``shape`` on any thread; ``quoted``, ``quoted_chars``, ``run``
    and ``instruction`` on one about words in a prompt.
    """
    return {
        "about": _text(entry, "about"),
        "stage": _text(entry, "stage"),
        "shape": _text(entry, "shape"),
        "quoted": _text(entry, "quoted"),
        "quoted_chars": _a_count(entry.get("quoted_chars")),
        "run": _text(entry, "run"),
        "instruction": _text(entry, "instruction"),
    }


# -- writing ----------------------------------------------------------------------------------


QUOTE_LIMIT = 2_000
"""How much of a selection a thread keeps. Longer than this and `quoted_chars` says so."""


def _cut(quoted: str | None) -> tuple[str | None, int | None]:
    """The words a thread keeps, and the length they had where they were cut."""
    if quoted is None:
        return None, None
    return (quoted[:QUOTE_LIMIT], len(quoted)) if len(quoted) > QUOTE_LIMIT else (quoted, None)


def append_comment(
    path: str | Path,
    *,
    at: str,
    said: str,
    by: str = "builder",
    kind: str = "comment",
    about: str | None = None,
    stage: str | None = None,
    shape: str | None = None,
    quoted: str | None = None,
    run: str | None = None,
    instruction: str | None = None,
    when: str | None = None,
) -> Comment:
    """Start a thread and return it, with the id the file now holds.

    ::

        append_comment("comments.toml", at="recommend/judge", said="Why the whole pool?",
                       about="judge, a model call in recommend", stage="build")

    A thread about words the builder selected in a prompt passes them as ``quoted``, with
    ``run`` naming the run the prompt was read in and ``instruction`` the digest of its
    fixed text::

        append_comment("comments.toml", at="trip/plan#words-3f9a1c2d5e70",
                       said="120 words is too short once there are four days.",
                       quoted="Answer in at most 120 words", run="run_20260903T140233Z_9c1f",
                       instruction="sha256:aa4d52b117e0")

    A selection longer than 2,000 characters is cut there and ``quoted_chars`` records the
    length it had. ``when`` defaults to now, UTC. The served view calls this when the builder
    submits; the coding agent may open threads the same way. Creates the file when there is
    none.
    """
    _refuse_a_bad_thread(kind, by, at, said)
    held = read_comments(path)
    taken = {c.id for c in held.all}
    number = len(held.all) + 1
    while f"c{number}" in taken:
        number += 1
    kept, full = _cut(quoted)
    thread = Comment(
        at=at.strip(),
        said=said.strip(),
        id=f"c{number}",
        by=by,
        kind=kind,
        about=about,
        stage=stage,
        shape=shape,
        quoted=kept,
        quoted_chars=full,
        run=run,
        instruction=instruction,
        when=when or _now(),
    )
    _write(path, (*held.all, thread))
    return thread


def _refuse_a_bad_thread(kind: str, by: str, at: str, said: str) -> None:
    """What `append_comment` will not write, and what to pass instead."""
    if kind not in _KINDS:
        raise ConfigurationError(
            f"append_comment was given kind={kind!r}, and the three are 'comment', "
            f"'answer' and 'amendment'."
        )
    if by not in _SIDES:
        raise ConfigurationError(
            f"append_comment was given by={by!r}, and a thread is by 'builder' or 'coding_agent'."
        )
    if not at.strip() or not said.strip():
        raise ConfigurationError(
            "append_comment needs both at= (the element's address) and said= (the words)."
        )


def append_reply(
    path: str | Path, comment_id: str, *, by: str, said: str, when: str | None = None
) -> Comment:
    """Add one turn to a thread and return the thread as it now stands.

    ::

        append_reply("comments.toml", "c3", by="coding_agent",
                     said="Capped the pool before ranking; the change lands today.")
    """
    if by not in _SIDES:
        raise ConfigurationError(
            f"append_reply was given by={by!r}, and a reply is by 'builder' or 'coding_agent'."
        )
    if not said.strip():
        raise ConfigurationError("append_reply was given empty said=.")
    held = read_comments(path)
    updated, found = [], None
    for thread in held.all:
        if thread.id == comment_id:
            found = replace(
                thread,
                replies=(*thread.replies, Reply(by=by, said=said.strip(), when=when or _now())),
            )
            updated.append(found)
        else:
            updated.append(thread)
    if found is None:
        raise ConfigurationError(
            f"{path} holds no thread {comment_id!r}. `read_comments(path).all` lists the "
            f"ids the file has."
        )
    _write(path, tuple(updated))
    return found


def set_status(
    path: str | Path,
    comment_id: str,
    status: str,
    *,
    addressed_by: str | None = None,
    when: str | None = None,
) -> Comment:
    """Move a thread to ``open``, ``addressed`` or ``withdrawn``, and return it.

    ::

        set_status("comments.toml", "c3", "addressed", addressed_by="decisions.pool_cap")
    """
    if status not in _STATUSES:
        raise ConfigurationError(
            f"set_status was given {status!r}, and the three are 'open', 'addressed' and "
            f"'withdrawn'."
        )
    held = read_comments(path)
    updated, found = [], None
    for thread in held.all:
        if thread.id == comment_id:
            found = replace(
                thread,
                status=status,
                addressed_by=addressed_by if status == "addressed" else None,
                addressed_when=(when or _now()) if status == "addressed" else None,
            )
            updated.append(found)
        else:
            updated.append(thread)
    if found is None:
        raise ConfigurationError(
            f"{path} holds no thread {comment_id!r}. `read_comments(path).all` lists the "
            f"ids the file has."
        )
    _write(path, tuple(updated))
    return found


def _write(path: str | Path, threads: tuple[Comment, ...]) -> None:
    """Serialise every thread and replace the file atomically.

    Strings are written as TOML basic strings through the JSON escapes, which TOML shares,
    so any words the writer types round-trip.
    """
    target = Path(path).expanduser()
    lines = [_HEADER]
    for thread in threads:
        lines.append("\n[[comment]]")
        lines.append(f"id = {json.dumps(thread.id)}")
        lines.append(f"at = {json.dumps(thread.at)}")
        if thread.by != "builder":
            lines.append(f"by = {json.dumps(thread.by)}")
        if thread.kind != "comment":
            lines.append(f"kind = {json.dumps(thread.kind)}")
        lines.append(f"said = {json.dumps(thread.said)}")
        for key in ("about", "stage", "shape", "quoted", "run", "instruction", "when"):
            value = getattr(thread, key)
            if value:
                lines.append(f"{key} = {json.dumps(value)}")
        if thread.quoted_chars:
            lines.append(f"quoted_chars = {thread.quoted_chars}")
        lines.append(f"status = {json.dumps(thread.status)}")
        if thread.addressed_by:
            lines.append(f"addressed_by = {json.dumps(thread.addressed_by)}")
        if thread.addressed_when:
            lines.append(f"addressed_when = {json.dumps(thread.addressed_when)}")
        for reply in thread.replies:
            lines.append("\n[[comment.replies]]")
            lines.append(f"by = {json.dumps(reply.by)}")
            lines.append(f"said = {json.dumps(reply.said)}")
            if reply.when:
                lines.append(f"when = {json.dumps(reply.when)}")
    body = "\n".join(lines) + "\n"
    scratch = target.with_suffix(".toml.writing")
    scratch.write_text(body, encoding="utf-8")
    os.replace(scratch, target)
