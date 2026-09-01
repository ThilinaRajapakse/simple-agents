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
]

DEFAULT_COMMENTS = "comments.toml"
COMMENTS_FORMAT_VERSION = "1"

_STATUSES = ("open", "addressed", "withdrawn")
_KINDS = ("comment", "answer", "amendment")
_SIDES = ("builder", "coding_agent")

_HEADER = (
    "# What was said about parts of the system, and what came back. Written by the served\n"
    "# `simple-agents view` and by the coding agent; read by both, and by the gates (FT-39).\n"
    "# docs/view.md#5 is the shape.\n"
    f'version = "{COMMENTS_FORMAT_VERSION}"\n'
)


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
    ``shape`` snapshot what the writer was looking at. ``addressed_by`` and
    ``addressed_when`` are only meaningful once ``status`` is ``"addressed"``.
    """

    at: str
    said: str
    id: str = ""
    by: str = "builder"
    kind: str = "comment"
    about: str | None = None
    stage: str | None = None
    shape: str | None = None
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
            f"`about`, `stage`, `shape`, `when`, `status`, `addressed_by`, "
            f"`addressed_when` and [[comment.replies]] entries."
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
        about=_text(entry, "about"),
        stage=_text(entry, "stage"),
        shape=_text(entry, "shape"),
        when=_text(entry, "when") or _text(entry, "date"),
        status=status,
        addressed_by=_text(entry, "addressed_by"),
        addressed_when=_text(entry, "addressed_when"),
        replies=tuple(replies),
    )


# -- writing ----------------------------------------------------------------------------------


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
    when: str | None = None,
) -> Comment:
    """Start a thread and return it, with the id the file now holds.

    ::

        append_comment("comments.toml", at="recommend/judge", said="Why the whole pool?",
                       about="judge, a model call in recommend", stage="build")

    ``when`` defaults to now, UTC. The served view calls this when the builder submits;
    the coding agent may open threads the same way. Creates the file when there is none.
    """
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
    held = read_comments(path)
    taken = {c.id for c in held.all}
    number = len(held.all) + 1
    while f"c{number}" in taken:
        number += 1
    thread = Comment(
        at=at.strip(),
        said=said.strip(),
        id=f"c{number}",
        by=by,
        kind=kind,
        about=about,
        stage=stage,
        shape=shape,
        when=when or _now(),
    )
    _write(path, (*held.all, thread))
    return thread


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
        for key in ("about", "stage", "shape", "when"):
            value = getattr(thread, key)
            if value:
                lines.append(f"{key} = {json.dumps(value)}")
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
