"""A conversation that outlives the run: what was said across many runs of one pipeline.

One turn is one run. A chat's second message is a second run of the same pipeline, with its own
trajectory, manifest and budget, and this is what carries the messages between them.

A node reads the thread in its prompt function and the library writes what the node produces,
as it produces it. Nothing here is a tool call: what a prompt function returns is on the
trajectory as ``inputs.messages``, so a conversation read this way is already on the record.

``docs/conversation.md`` is the whole surface.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from ..errors import ConfigurationError

__all__ = [
    "CONVERSATION_FORMAT_VERSION",
    "ROLLOUT_CONVERSATION",
    "Conversation",
    "ConversationStore",
    "Thread",
    "ThreadView",
    "ThreadWriter",
    "Turn",
]

CONVERSATION_FORMAT_VERSION = "0.2"

ROLLOUT_CONVERSATION = "rollout"
"""The conversation id every rollout of an evaluation uses.

Each rollout has its own store, so one name serves them all and a scoring rule reading a
rollout's conversation back does not have to know which example it came from.
"""

_PROVIDER_KEYS = ("provider", "reasoning", "reasoning_blocks")

_WRITE_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Turn:
    """One run's contribution to a conversation.

    ``said`` and ``answered`` are the turn in one line each, for a surface rendering the
    conversation and for :meth:`Thread.compact`. ``outcome`` is what ended the turn:
    ``completed``, ``error``, or what the node's own loop stopped on, such as ``finish``.
    ``None`` is a turn whose run has not finished::

        for turn in thread.turns():
            print(turn.number, turn.said, "->", turn.answered)
    """

    number: int
    run_id: str
    node_id: str
    at: str
    carried_in: int = 0
    said: Any = None
    answered: Any = None
    outcome: str | None = None
    messages: tuple[dict[str, Any], ...] = ()


class Thread:
    """One conversation, on disk.

    Produced by :meth:`ConversationStore.thread`. A prompt function reads it and splats it
    where the history belongs::

        def build_prompt(inputs, ctx):
            return [
                {"role": "system", "content": SYSTEM},
                *ctx.conversation,
                {"role": "user", "content": inputs["question"]},
            ]

    Iterating gives every message the conversation holds, oldest first, in the library's own
    message shape. The library appends what the node produces, so a prompt function reads and
    never writes.

    ``compact()`` gives the said/answered pairs instead of the full messages, which is what a
    later turn needs where the agent's own tool calls are not worth re-sending.
    ``without_provider_state()`` drops the fields one backend requires back verbatim, which is
    what a thread recorded against one backend and continued against another needs.
    """

    def __init__(self, path: Path, conversation_id: str, redaction: Any = None) -> None:
        self.path = path
        self.conversation_id = conversation_id
        self.redaction = redaction

    # -- reading ---------------------------------------------------------------------------

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.messages())

    def __len__(self) -> int:
        return len(self.messages())

    def __bool__(self) -> bool:
        return bool(self.messages())

    def messages(self) -> list[dict[str, Any]]:
        """Every message the conversation holds, oldest first.

        A message a compaction replaced is left out, and the summary it was replaced by is in
        its place. The dicts are the ones the library will compare against when it decides
        what a turn added, so pass them through rather than rebuilding them.
        """
        records = self._records()
        # The newest compaction is read from the whole file before anything is kept. A
        # compaction is written after the messages it replaced, so deciding as they are read
        # would keep every message written before the compaction that dropped it. Its summary
        # goes at the head, where what it summarises was.
        newest = max(
            (record for record in records if record.get("record") == "compaction"),
            key=lambda record: int(record.get("superseded_through") or 0),
            default=None,
        )
        through = int((newest or {}).get("superseded_through") or 0)
        kept: list[dict[str, Any]] = []
        if newest is not None and newest.get("summary"):
            kept.append({"role": "user", "content": str(newest["summary"])})
        kept.extend(
            _message_of(record)
            for position, record in enumerate(_written(records), start=1)
            if position > through
        )
        return kept

    def compact(self) -> list[dict[str, Any]]:
        """The conversation as said/answered pairs, leaving out the agent's own working.

        A turn that recorded neither is left out. What this drops is the tool calls and the
        observations a turn made, which a later turn does not always need::

            return [{"role": "system", "content": SYSTEM}, *ctx.conversation.compact(),
                    {"role": "user", "content": inputs["question"]}]
        """
        out: list[dict[str, Any]] = []
        for turn in self.turns():
            if turn.said is not None:
                out.append({"role": "user", "content": _as_text(turn.said)})
            if turn.answered is not None:
                out.append({"role": "assistant", "content": _as_text(turn.answered)})
        return out

    def without_provider_state(self) -> list[dict[str, Any]]:
        """Every message, with the fields one backend requires back verbatim removed.

        A tool call recorded against Gemini carries a ``thought_signature`` that backend
        expects on the next request, and an OpenAI-dialect adapter refuses to translate a call
        carrying it. A thread continued against a different backend reads this instead, and
        gives up the reasoning state rather than the conversation::

            *ctx.conversation.without_provider_state(),
        """
        return [_stripped(message) for message in self.messages()]

    def turns(self) -> list[Turn]:
        """Every turn, oldest first, with the messages each one added."""
        found: list[Turn] = []
        open_turn: dict[str, Any] | None = None
        collected: list[dict[str, Any]] = []
        for record in self._records():
            kind = record.get("record")
            if kind == "turn_opened":
                if open_turn is not None:
                    found.append(_turn_of(open_turn, collected))
                open_turn, collected = dict(record), []
            elif kind == "message" and open_turn is not None:
                collected.append(_message_of(record))
            elif kind == "turn_closed" and open_turn is not None:
                open_turn.update(
                    {k: record[k] for k in ("said", "answered", "outcome") if k in record}
                )
                found.append(_turn_of(open_turn, collected))
                open_turn, collected = None, []
        if open_turn is not None:
            found.append(_turn_of(open_turn, collected))
        return found

    @property
    def turn_count(self) -> int:
        """How many turns the conversation holds. The next run is this plus one."""
        return sum(1 for record in self._records() if record.get("record") == "turn_opened")

    def run_ids(self) -> list[str]:
        """The run that produced each turn, oldest first.

        What a spend figure over the conversation is summed from: read each run back with
        ``runs()`` and add up what its manifest recorded.
        """
        return [
            str(record.get("run_id") or "")
            for record in self._records()
            if record.get("record") == "turn_opened"
        ]

    # -- writing, which the library does ---------------------------------------------------

    def open_turn(self, *, run_id: str, node_id: str, carried_in: int, said: Any = None) -> int:
        """Record that a run has started a turn, and return its number.

        Written before the first model call, so a run killed mid-turn leaves the turn on the
        thread rather than leaving the conversation with no trace that anything was asked.
        """
        number = self.turn_count + 1
        self._append(
            {
                "record": "turn_opened",
                "turn": number,
                "run_id": run_id,
                "node_id": node_id,
                "carried_in": carried_in,
                "said": self._scrubbed(said),
                "at": _now(),
            }
        )
        return number

    def reopen(self, run_id: str) -> tuple[int, int] | None:
        """The turn this run left open, and how many messages it had already put on it.

        A run that stopped to ask somebody left its turn open. When it continues, what it
        answers belongs in the turn that asked, so the resumed execution adopts it rather than
        opening a second one and leaving the first open for good.

        ``None`` where this run has no open turn, which is every run that has not stopped.
        """
        open_turn: int | None = None
        held = 0
        for record in self._records():
            kind = record.get("record")
            if kind == "turn_opened":
                open_turn = (
                    int(record.get("turn") or 0)
                    if str(record.get("run_id") or "") == run_id
                    else None
                )
                held = 0
            elif kind == "turn_closed":
                if open_turn == int(record.get("turn") or 0):
                    open_turn = None
            elif kind == "message" and open_turn is not None:
                held += 1
        return None if open_turn is None else (open_turn, held)

    def add(self, messages: Sequence[Mapping[str, Any]], *, turn: int) -> None:
        """Append messages to the conversation, as the node produces them.

        Each message goes through the run's redaction rules on the way in, the same as a
        memory entry and a trajectory record. The conversation outlives every run, so a
        credential written into it is not removed by deleting a run directory.
        """
        for message in messages:
            body = {k: _plain(v) for k, v in dict(message).items()}
            redacted: list[str] = []
            if self.redaction is not None:
                body, redacted = self.redaction.redact(body)
            record = {"record": "message", "turn": turn, "at": _now(), **body}
            if redacted:
                record["redactions"] = list(redacted)
            self._append(record)

    def close_turn(
        self, *, turn: int, run_id: str, outcome: str | None, answered: Any = None
    ) -> None:
        """Record that the run finished, and what it answered."""
        self._append(
            {
                "record": "turn_closed",
                "turn": turn,
                "run_id": run_id,
                "outcome": outcome,
                "answered": self._scrubbed(answered),
                "at": _now(),
            }
        )

    def supersede(
        self, *, turn: int, run_id: str, summary: str, keep_last: int, model: str | None = None
    ) -> None:
        """Replace everything but the newest ``keep_last`` messages with one summary.

        What ``compact_conversation`` writes. The messages stay in the file and stop being
        read, so what a compaction dropped is still readable by anything reading the records.

        The watermark is a count of the message records in the file, computed here from the
        file itself, so nothing outside has to do arithmetic over positions it cannot see.
        """
        written = _written(self._records())
        through = max(0, len(written) - max(0, keep_last))
        self._append(
            {
                "record": "compaction",
                "turn": turn,
                "run_id": run_id,
                "superseded_through": through,
                "summary": summary,
                "model": model,
                "at": _now(),
            }
        )

    def _scrubbed(self, value: Any) -> Any:
        """A value the project supplied, through the run's redaction rules."""
        plain = _plain(value)
        if self.redaction is None:
            return plain
        scrubbed, _ = self.redaction.redact(plain)
        return scrubbed

    def written_count(self) -> int:
        """How many message records the file holds, superseded ones included."""
        return len(_written(self._records()))

    def forget(self) -> bool:
        """Delete the conversation. Returns whether there was one."""
        if not self.path.exists():
            return False
        self.path.unlink()
        return True

    # -- the file ---------------------------------------------------------------------------

    def _records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        found: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                found.append(record)
        return found

    def _append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK:
            first = not self.path.exists()
            with self.path.open("a", encoding="utf-8") as handle:
                if first:
                    handle.write(
                        json.dumps(
                            {
                                "record": "conversation",
                                "format_version": CONVERSATION_FORMAT_VERSION,
                                "conversation_id": self.conversation_id,
                                "started_at": _now(),
                            }
                        )
                        + "\n"
                    )
                handle.write(json.dumps(record) + "\n")


@dataclass(frozen=True, slots=True)
class Conversation:
    """A tool's handle on the conversation the run is a turn of.

    Filled in by the library and left out of the schema the model is shown, the same as a
    ``Memory`` or a ``Workspace`` (``docs/tools.md`` §3.2). A tool holding one is re-run during
    a replay rather than served from the cassette, since a later turn reads what it wrote::

        @tool(side_effect_class=SideEffectClass.WRITES)
        def note_the_topic(conversation: Conversation, topic: str) -> str:
            "Record what this conversation is about."
            return f"{conversation.id}: {topic}"
    """

    _thread: Thread
    _turn: int = 0

    @property
    def id(self) -> str:
        """The conversation's own id, as the project gave it."""
        return self._thread.conversation_id

    @property
    def turn(self) -> int:
        """Which turn of the conversation this run is."""
        return self._turn

    def messages(self) -> list[dict[str, Any]]:
        """Every message the conversation holds, oldest first."""
        return self._thread.messages()

    def turns(self) -> list[Turn]:
        """Every turn, oldest first."""
        return self._thread.turns()

    def supersede(self, summary: str, *, keep_last: int, model: str | None = None) -> None:
        """Replace everything but the newest ``keep_last`` messages with one summary."""
        self._thread.supersede(
            turn=self._turn,
            run_id="",
            summary=summary,
            keep_last=keep_last,
            model=model,
        )

    def _scrubbed(self, value: Any) -> Any:
        """A value the project supplied, through the run's redaction rules."""
        plain = _plain(value)
        if self.redaction is None:
            return plain
        scrubbed, _ = self.redaction.redact(plain)
        return scrubbed

    def last_sequence(self) -> int:
        """The sequence number of the newest message, or 0 where there are none."""
        return self._thread.last_sequence()


class ThreadView:
    """The conversation as one node sees it, and the record of whether that node read it.

    What ``ctx.conversation`` holds. Reading it is what enrols the node: the library writes
    the messages that node produces back to the thread, and a node that never reads it takes
    no part in the conversation. So a pipeline whose middle step summarises a document with a
    model call does not put that call into the chat.

    Every read returns the same message objects, which is what lets the library tell what a
    turn added from what the prompt carried in.

    **A run that names no conversation gets an empty one rather than nothing**, so the same
    prompt function serves a chat and a one-shot request without a branch around the splat.
    ``ctx.conversation.id`` is ``None`` there.
    """

    def __init__(self, thread: Thread | None) -> None:
        self.thread = thread
        self.was_read = False
        self._messages: list[dict[str, Any]] | None = None

    def _read(self) -> list[dict[str, Any]]:
        self.was_read = True
        if self._messages is None:
            self._messages = self.thread.messages() if self.thread is not None else []
        return self._messages

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._read())

    def __len__(self) -> int:
        return len(self._read())

    def __bool__(self) -> bool:
        return bool(self._read())

    def __getitem__(self, index: Any) -> Any:
        return self._read()[index]

    def messages(self) -> list[dict[str, Any]]:
        """Every message the conversation holds, oldest first."""
        return self._read()

    def compact(self) -> list[dict[str, Any]]:
        """The said/answered pairs, leaving out the agent's own working."""
        self._read()
        return self.thread.compact() if self.thread is not None else []

    def without_provider_state(self) -> list[dict[str, Any]]:
        """Every message, with the state one backend requires back verbatim removed."""
        return [_stripped(message) for message in self._read()]

    def turns(self) -> list[Turn]:
        """Every turn, oldest first."""
        self._read()
        return self.thread.turns() if self.thread is not None else []

    @property
    def turn_count(self) -> int:
        """How many turns the conversation held when this node started."""
        return self.thread.turn_count if self.thread is not None else 0

    @property
    def id(self) -> str | None:
        """The conversation's own id, as the project gave it.

        ``None`` on a run that names no conversation, which is what a pipeline serving both a
        chat and a one-shot request reads to tell them apart.
        """
        return self.thread.conversation_id if self.thread is not None else None


@dataclass
class ConversationStore:
    """Where a project's conversations live.

    Declared once on the envelope; which conversation a run is a turn of is an argument to
    ``Pipeline.run``, since that changes per request and the store does not::

        env = RunEnvelope(run_dir="runs/", conversations=ConversationStore("conversations/"))
        result = pipeline.run(question, envelope=env.with_live(), model=client,
                              conversation_id=f"chat-{chat_id}")

    ``directory`` is the project's to choose. A ``conversation_id`` names one conversation the
    project minted, such as a chat, a ticket or a channel. It is recorded on the manifest of
    every run of that conversation as it is given, so a project that puts a person's identifier
    there has put it in an artifact.

    The file a conversation is kept in is named by a digest of the id, which is what keeps an id
    holding a slash or five hundred characters from deciding a path.
    """

    directory: Path
    redaction: Any = None
    _threads: dict[str, Thread] = field(default_factory=dict, repr=False, compare=False)

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.directory = Path(directory)
        self.redaction = None
        self._threads = {}

    def under(self, redaction: Any) -> "ConversationStore":
        """This store with a run's redaction rules bound, which the run does when it starts."""
        self.redaction = redaction
        self._threads = {}
        return self

    def thread(self, conversation_id: str) -> Thread:
        """The conversation with this id, whether or not anything has been said in it."""
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ConfigurationError(
                "A conversation's id names one conversation, such as a chat, a ticket or a "
                "channel, and it has to be a non-empty string.\n"
                "Pass it to the run: pipeline.run(inputs, envelope=env, model=client, "
                "conversation_id=f'chat-{chat_id}')."
            )
        if conversation_id not in self._threads:
            self._threads[conversation_id] = Thread(
                self._path_for(conversation_id), conversation_id, redaction=self.redaction
            )
        return self._threads[conversation_id]

    def conversation_ids(self) -> list[str]:
        """Every conversation this store holds, by id, sorted.

        Read out of the files rather than from their names, which are digests.
        """
        found: list[str] = []
        if not self.directory.is_dir():
            return found
        for path in sorted(self.directory.glob("*.jsonl")):
            try:
                first = path.read_text(encoding="utf-8").splitlines()[0]
                found.append(str(json.loads(first)["conversation_id"]))
            except (OSError, ValueError, IndexError, KeyError):
                continue
        return sorted(found)

    def _path_for(self, conversation_id: str) -> Path:
        digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:16]
        return self.directory / f"{digest}.jsonl"

    def rebound(
        self,
        directory: str | os.PathLike[str],
        *,
        seed: Sequence[Mapping[str, Any]] = (),
    ) -> "ConversationStore":
        """A store somewhere else, holding ``seed`` as one conversation's opening turn.

        What an evaluation gives each rollout: a directory inside that rollout's own run, and
        the example's ``conversation`` as what has already been said. Rollouts run
        concurrently, so a store they shared would let one answer out of another's turn.
        """
        moved = ConversationStore(directory)
        if seed:
            conversation = moved.thread(ROLLOUT_CONVERSATION)
            turn = conversation.open_turn(run_id="", node_id="", carried_in=0, said=_said_of(seed))
            conversation.add(seed, turn=turn)
            conversation.close_turn(
                turn=turn, run_id="", outcome="completed", answered=_answered_of(seed)
            )
        return moved

    def to_manifest(self) -> dict[str, Any]:
        """What the manifest records of the store itself."""
        return {"directory": str(self.directory)}


def new_to_the_thread(
    produced: Sequence[Mapping[str, Any]], carried: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The messages of ``produced`` that the thread does not already hold.

    A prompt function splats the conversation into what it returns, so what a turn added is
    what is left after the conversation's own messages are taken out of it. The messages the
    thread handed over are matched first by identity and then, in order, by content, so a
    prompt that copies them rather than splatting them still records one turn's worth.

    A message that neither matches is new, which is what a prompt rebuilding the history
    rather than splatting it produces. `docs/conversation.md` §3 says to splat.

    **A system message is never part of the conversation.** It is the node's standing
    instruction, the prompt function supplies it on every turn, and a system prompt carrying
    today's date or the reader's current plan has to be able to change. Storing it would put
    turn 1's copy at the head of turn 40.
    """
    carried_ids = {id(message) for message in carried}
    remaining = list(carried)
    out: list[dict[str, Any]] = []
    for message in produced:
        if message.get("role") == "system":
            continue
        if id(message) in carried_ids:
            continue
        if remaining and _same(message, remaining[0]):
            remaining.pop(0)
            continue
        out.append(dict(message))
    return out


def _said_of(messages: Sequence[Mapping[str, Any]]) -> Any:
    """The last thing the end user said in a seeded conversation."""
    return said_in(messages)


def _answered_of(messages: Sequence[Mapping[str, Any]]) -> Any:
    """The last thing the agent answered in a seeded conversation."""
    for message in reversed(list(messages)):
        if message.get("role") == "assistant":
            return message.get("content")
    return None


def _same(one: Mapping[str, Any], other: Mapping[str, Any]) -> bool:
    return dict(one) == dict(other)


def _written(records: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Every message record in the file, in the order it was appended."""
    return [record for record in records if record.get("record") == "message"]


def _message_of(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in ("record", "turn", "at", "redactions")
    }


def _turn_of(opened: Mapping[str, Any], messages: Sequence[Mapping[str, Any]]) -> Turn:
    return Turn(
        number=int(opened.get("turn") or 0),
        run_id=str(opened.get("run_id") or ""),
        node_id=str(opened.get("node_id") or ""),
        at=str(opened.get("at") or ""),
        carried_in=int(opened.get("carried_in") or 0),
        said=opened.get("said"),
        answered=opened.get("answered"),
        outcome=opened.get("outcome"),
        messages=tuple(dict(message) for message in messages),
    )


def _stripped(message: Mapping[str, Any]) -> dict[str, Any]:
    out = {key: value for key, value in message.items() if key not in _PROVIDER_KEYS}
    calls = out.get("tool_calls")
    if isinstance(calls, list):
        out["tool_calls"] = [
            {k: v for k, v in dict(call).items() if k != "provider"} for call in calls
        ]
    return out


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(_plain(value))


def _plain(value: Any) -> Any:
    """What survives being written to the file, for a value the project supplied."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    dumped = getattr(value, "model_dump", None)
    if callable(dumped):
        return _plain(dumped())
    return str(value)


class ThreadWriter:
    """Writes one node's messages into the conversation the run is a turn of.

    Built for every node execution and doing nothing until the node's prompt function reads
    ``ctx.conversation``. Reading it is what enrols the node (`docs/conversation.md` §3).

    Messages go on as the node produces them rather than in one write at the end. A run killed
    mid-turn then leaves the turn on the thread, which is what the trajectory and the manifest
    already promise, and a run suspended for a consultation does not leave the conversation
    empty for as long as the answer takes.
    """

    def __init__(self, view: Any, run: Any, node_id: str, item_index: int | None) -> None:
        self.view = view
        self.run = run
        self.node_id = node_id
        self.item_index = item_index
        self.turn: int | None = None
        self.flushed = 0

    @property
    def engaged(self) -> bool:
        return self.view is not None and self.view.was_read and self.view.thread is not None

    def opened(self, messages: list[dict[str, Any]]) -> None:
        """Open the turn and record what the prompt added to the conversation."""
        # A fan-out item reads the conversation and adds nothing to it. A conversation is one
        # sequence of turns and a fan-out is many items at once, so there is no order for
        # them to go on in; reading is what an item wants and is unambiguous.
        if not self.engaged or self.turn is not None or self.item_index is not None:
            return
        carried = list(self.view.messages())
        if not _continues(messages, carried):
            return
        thread = self.view.thread
        continuing = thread.reopen(self.run.run_id)
        if continuing is not None:
            # This run stopped inside this turn and is continuing. What it answers belongs in
            # the turn that asked, and whatever it had already put on is not put on twice:
            # the conversation's own messages are taken back out of what the node now holds.
            self.turn, already = continuing
            thread.add(new_to_the_thread(messages, carried), turn=self.turn)
            self.flushed = len(messages)
            self._record_on_the_manifest(len(carried) - already)
            return
        self.turn = thread.open_turn(
            run_id=self.run.run_id,
            node_id=self.node_id,
            carried_in=len(carried),
            said=said_in(new_to_the_thread(messages, carried)),
        )
        thread.add(new_to_the_thread(messages, carried), turn=self.turn)
        self.flushed = len(messages)
        self._record_on_the_manifest(len(carried))

    def _record_on_the_manifest(self, carried_in: int) -> None:
        """Which turn this run is, and how many earlier messages the node was shown.

        ``carried_in`` of zero past the first turn is a conversation written and not read.
        """
        recorded = getattr(self.run.manifest, "conversation", None)
        if isinstance(recorded, dict):
            recorded["turn"] = self.turn
            recorded["carried_in"] = max(0, carried_in)
            recorded["node_id"] = self.node_id

    def resumed(self, messages: list[dict[str, Any]]) -> None:
        """Adopt the turn this run stopped inside, for an execution that continues one.

        A resumed execution does not run its prompt function again, so nothing reads the
        conversation and nothing enrols the node. What says it took part is that the
        conversation holds an open turn belonging to this run.
        """
        if self.view is None or self.view.thread is None or self.turn is not None:
            return
        continuing = self.view.thread.reopen(self.run.run_id)
        if continuing is None:
            return
        carried = list(self.view.messages())
        self.turn, already = continuing
        self.view.thread.add(new_to_the_thread(messages, carried), turn=self.turn)
        self.flushed = len(messages)
        self._record_on_the_manifest(len(carried) - already)

    def flush(self, messages: list[dict[str, Any]]) -> None:
        """Append whatever the node has produced since the last flush."""
        if self.turn is None or len(messages) <= self.flushed:
            return
        self.view.thread.add(messages[self.flushed :], turn=self.turn)
        self.flushed = len(messages)

    def close(self, messages: list[dict[str, Any]], outcome: str, answered: Any = None) -> None:
        """Record that the run finished this turn, and what it answered."""
        if self.turn is None:
            return
        self.flush(messages)
        self.view.thread.close_turn(
            turn=self.turn, run_id=self.run.run_id, outcome=outcome, answered=answered
        )
        self.turn = None


def _continues(produced: Sequence[Mapping[str, Any]], carried: Sequence[Mapping[str, Any]]) -> bool:
    """Whether a node's prompt continues the conversation rather than looking at it.

    A node takes part by putting the conversation into what it sends, so a prompt that carries
    none of it is doing something else with it. The node that summarises a conversation reads
    every message and renders them into one string, and its own prompt and answer are not a
    turn of the chat it just summarised.

    A conversation with nothing in it yet cannot be matched against, so the first turn goes on
    whenever the node read it at all.
    """
    if not carried:
        return True
    carried_ids = {id(message) for message in carried}
    return any(
        id(message) in carried_ids or any(_same(message, held) for held in carried)
        for message in produced
    )


def said_in(messages: Sequence[Mapping[str, Any]]) -> Any:
    """What the end user said this turn: the last user message the prompt added."""
    for message in reversed(list(messages)):
        if message.get("role") == "user":
            return message.get("content")
    return None


def thread_view(run: Any) -> "ThreadView":
    """This run's view of the conversation it is a turn of.

    A run that names no conversation gets an empty view rather than ``None``, so a prompt
    function splatting ``*ctx.conversation`` works whether or not this run is a turn of one.
    """
    return ThreadView(getattr(run, "conversation", None))
