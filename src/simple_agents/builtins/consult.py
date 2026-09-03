"""Asking the end user something mid-run.

Consultation is designed behaviour, not a fault path. The builder anticipates that the agent
will need a preference, a disambiguation, or an authorisation it has no way to derive, and
registers this tool so it can ask instead of guessing. An agent that treats asking as failure
guesses, and a guess is indistinguishable from an answer in the trajectory (FT-25).

Not to be confused with elicitation, which happens at build time between the coding agent and
the builder and lands in the brief.

The channel is a function the project supplies, because the library owns no terminal, no
notebook and no chat window. It is served from the cassette like any other tool, so a replay
of a run serves the recorded answer rather than asking the person again.

A channel says who answers through it, and that declaration is recorded on every consultation
it carries. `docs/tools.md` §4.6.2 covers who to declare and what each value means.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ..prompting import Prompt, Section
from ..errors import CallerFacingError, ConfigurationError
from ..grounding import normalise_text
from ..tools import (
    ANSWERED_BY,
    ConsultTool,
    Reading,
    SideEffectClass,
    derived_version,
    tool,
)

__all__ = [
    "consult",
    "ConsultChannel",
    "Reply",
    "ModelAnswer",
    "Shelved",
    "ModelReader",
    "Unavailable",
    "unattended",
    "ask_on_stdin",
    "on_reply",
    "DEFAULT_READING_INSTRUCTIONS",
]

ConsultChannel = Callable[
    [str, "Sequence[str] | None", "str | None"],
    "str | ModelAnswer | Unavailable | Shelved | None",
]


class Reply(str):
    """What the end user said, and which offered option it was.

    A ``str``, so it reaches the model as the text they typed and compares equal to it. What it
    adds is ``chose``: the option the answer matched, or ``None`` where it matched none::

        reply = ctx.call_tool("consult", question="Ship it?", options=["yes", "no"])
        reply              # 'Yes.'
        reply.chose        # 'yes'
        reply.options      # ('yes', 'no')

    The rule compares the whole answer against the whole option and folds case and punctuation,
    so ``"Yes."`` matches and ``"Yes, go ahead"`` does not: that answer arrives with ``chose``
    of ``None``. Pass ``match=`` to :func:`consult` for a rule that reads more.

    ``declared_choice`` is the option the channel itself said this answer was, and is ``None``
    for a channel that cannot say. It never decides ``chose``, which is what routes the run,
    and the two differing is what ``per_node.consultation_misreadings`` counts.

    ``chose`` is ``None`` when the answer matched no option, which is the case a route must
    have a branch for, and when no options were offered.

    ``answered_at`` is when the person said it, for a channel serving an answer it stored
    earlier, and ``None`` where they answered during this call. It is what separates a count of
    people answering from a count of records::

        return Reply(stored.text, chose=None, answered_at=stored.at)

    A consultation the end user declined is ``None`` rather than a ``Reply``.
    """

    __slots__ = ("chose", "options", "declared_choice", "answered_at")

    chose: str | None
    options: tuple[str, ...]
    declared_choice: str | None
    answered_at: str | None

    def __new__(
        cls,
        text: str,
        *,
        chose: str | None,
        options: Sequence[str] = (),
        declared_choice: str | None = None,
        answered_at: str | None = None,
    ) -> Reply:
        reply = super().__new__(cls, text)
        object.__setattr__(reply, "chose", chose)
        object.__setattr__(reply, "options", tuple(options))
        object.__setattr__(reply, "declared_choice", declared_choice)
        object.__setattr__(reply, "answered_at", answered_at)
        return reply

    @staticmethod
    def stored_in(value: Any) -> bool:
        """Whether a value read back from a cassette is one of these with a declared choice."""
        return isinstance(value, Mapping) and "declared_choice" in value

    def to_json(self) -> dict[str, Any]:
        """The plain form a cassette stores where the channel declared which option it meant.

        ``chose`` is left out and derived again on the way back, as it is for an answer stored
        as bare text, so a rule changed between recording and replay is the rule that reads
        both.
        """
        return {
            "reply": str(self),
            "declared_choice": self.declared_choice,
            "answered_at": self.answered_at,
        }

    @property
    def matched(self) -> bool:
        """Whether the answer was one of the offered options."""
        return self.chose is not None


class Unavailable(str):
    """What a channel returns where there is nobody to ask.

    A run with no one at the other end is not a run whose end user declined. Declining is a
    choice and narrows what the agent should do next; nobody being there is the absence of a
    choice, and the agent proceeds on what it has and says what is missing::

        def ask_by_email(question, options, about):
            if not on_call():
                return Unavailable(reason="the desk is closed outside business hours")
            send_email(question, options)
            raise Suspend(waiting_for=question, options=options)

    A ``str``, so the model reads it as an instruction to stop asking. ``reason`` is the text
    the channel gave::

        reply.reason      # 'the desk is closed outside business hours'

    The consultation is recorded with ``resolution`` ``unavailable`` and the reason beside it.
    The rest of the run's calls to that tool return this without reaching the channel again,
    and each one is recorded, so a results file says how many questions the run had for
    somebody who was not there. :func:`on_reply` needs a branch for it.

    :func:`unattended` is the shipped channel that returns nothing else.
    """

    __slots__ = ("reason",)

    reason: str
    no_one_to_ask = True

    def __new__(cls, reason: str) -> Unavailable:
        if not str(reason).strip():
            raise ConfigurationError(
                "Unavailable() was given no reason. The reason is what a trajectory says "
                "about why a designed interaction did not happen, and it is the difference "
                "between a channel that is off and one that is broken.\n"
                "Pass Unavailable(reason='no one is at a terminal in an unattended run')."
            )
        text = (
            f"No one is available to answer questions in this run: {reason}. Do not ask "
            f"again. Continue with what is already available, and state in the answer what "
            f"could not be settled without them."
        )
        unavailable = super().__new__(cls, text)
        object.__setattr__(unavailable, "reason", str(reason))
        return unavailable

    def to_json(self) -> dict[str, Any]:
        """The plain form a cassette stores, so a replay is unavailable rather than answered."""
        return {"unavailable": {"reason": self.reason}}

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> Unavailable:
        """Rebuild one from :meth:`to_json`."""
        return cls(reason=str((raw.get("unavailable") or {}).get("reason") or "unrecorded"))

    @staticmethod
    def stored_in(value: Any) -> bool:
        """Whether a value read back from a cassette is one of these."""
        return isinstance(value, Mapping) and "unavailable" in value


class Shelved(str):
    """What a channel returns where the question is on record and an answer may come later.

    The third of the three ways a consultation ends. Engaged: the channel raises
    :class:`~simple_agents.errors.Suspend`, the run stops, and ``Pipeline.resume`` continues it
    once the answer arrives. Unavailable: there is nobody to ask, and the agent proceeds on what
    it has. Shelved: the question is put somewhere a person will see it, the run finishes now,
    and the answer reaches a later run::

        def ask_the_site(question, options, about):
            answered = questions.answer_to(about)
            if answered is not None:
                return Reply(answered, chose=None, answered_at=questions.answered_at(about))
            questions.put(about, question, options)
            return Shelved(reason="the site is unattended; the question is on the questions page")

    This is the mode a run fired by cron or by a store write needs, because such a run is
    unattended and cannot stop. ``reason`` is where the question went, and is
    recorded beside the consultation::

        reply.reason      # 'the site is unattended; the question is on the questions page'

    The consultation is recorded with ``resolution`` ``shelved``, which is asked-and-outstanding
    rather than unanswered. **A shelved answer never silences a later question**: the
    once-per-run rule is for a channel reporting that there is nobody to ask, and this one is
    reaching somebody. :func:`on_reply` needs a branch for it.

    A ``str``, so the model reads it as what happened. Where a run must wait for the answer
    instead, the channel raises ``Suspend`` (``docs/pipeline.md`` §1.8).
    """

    __slots__ = ("reason",)

    reason: str
    shelved = True

    def __new__(cls, reason: str) -> Shelved:
        if not str(reason).strip():
            raise ConfigurationError(
                "Shelved() was given no reason. The reason is where the question went, and it "
                "is what a person reading the trajectory needs in order to find the answer or "
                "to know why one never came.\n"
                "Pass Shelved(reason='the site is unattended; the question is on the questions page')."
            )
        text = (
            f"This question is on record and has no answer yet: {reason}. Continue with what "
            f"is already available, and state in the answer what could not be settled. The "
            f"answer may arrive after this run has finished."
        )
        it = super().__new__(cls, text)
        object.__setattr__(it, "reason", str(reason))
        return it

    def to_json(self) -> dict[str, Any]:
        """The plain form a cassette stores, so a replay is shelved rather than answered."""
        return {"shelved": {"reason": self.reason}}

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> Shelved:
        """Rebuild one from :meth:`to_json`."""
        return cls(reason=str((raw.get("shelved") or {}).get("reason") or "unrecorded"))

    @staticmethod
    def stored_in(value: Any) -> bool:
        """Whether a value read back from a cassette is one of these."""
        return isinstance(value, Mapping) and "shelved" in value


class ModelAnswer:
    """An answer with what produced it, for a channel that calls a model to write one.

    A channel returning a plain string says what the end user said and nothing about where it
    came from. One that runs a model returns this instead, so the model, what it spent and what
    it cost are recorded on the consultation and stay out of the node's own model-call counts::

        def ask_a_model(question, options, about) -> ModelAnswer:
            response = client.complete(ModelRequest(messages=[...]))
            return ModelAnswer(response.content, model=client.identity(),
                               tokens=response.tokens)

    ``text`` of ``None`` is a refusal to answer, the same as a channel returning ``None``.

    ``declared_choice`` is the offered option the channel says its answer was, for a channel
    that can say. It never routes the run, which stays on the rule ``match=`` names, so what it
    records is whether that rule read the answer the way the channel meant it::

        ModelAnswer(text, model=client.identity(), declared_choice="The Will of the Many")

    ``SimulatedEndUser`` is the shipped channel that returns these.
    """

    __slots__ = ("text", "model", "tokens", "cost", "declared_choice")

    def __init__(
        self,
        text: str | None,
        *,
        model: Any = None,
        tokens: Any = None,
        cost: Any = None,
        declared_choice: str | None = None,
    ) -> None:
        self.text = text
        self.model = model
        self.tokens = tokens
        self.cost = cost
        self.declared_choice = declared_choice


READING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chose": {
            "type": ["string", "null"],
            "description": (
                "Which offered option the answer meant, copied exactly, or null where it "
                "meant none of them."
            ),
        },
        "reason": {
            "type": "string",
            "description": "One sentence on what in the answer decided it.",
        },
    },
    "required": ["chose", "reason"],
    "additionalProperties": False,
}

DEFAULT_READING_INSTRUCTIONS = (
    "An agent asked a person a question and offered them a fixed set of options. Decide which "
    "option their answer meant.\n\n"
    "The options:\n{options}\n\n"
    "Their answer:\n{answer}\n\n"
    "Copy one option exactly, or use null where the answer meant none of them. Three kinds of "
    "answer mean none:\n"
    "  - one that attaches a condition, such as 'only if it is under 400 pages; otherwise, "
    "no', which states terms rather than choosing\n"
    "  - one that asks a question back, or amends what was asked\n"
    "  - one about something else entirely\n\n"
    "Read the whole answer rather than the words in it. An answer that rules something out "
    "means the opposite of what it names: 'anything but the second one' is not the second one. "
    "An option's word can appear without being the choice: 'I have no strong feeling either "
    "way, go ahead' agrees, and the 'no' in it chooses nothing."
)
"""The prompt a :class:`ModelReader` uses where the project passes none.

``{options}`` is filled with the offered options, one per line, and ``{answer}`` with what the
end user said. What the library appends to it is the reply format; a project replacing this
keeps that.
"""

READING_FORMAT = (
    '\n\nReply with JSON: {{"chose": "<the option, copied exactly, or null>", '
    '"reason": "<one sentence>"}}.'
)
"""Appended to the reading instructions. A brace is doubled because this is prompt text."""

RETRY_RULE = (
    "That reply could not be read: {problem}\n"
    'Reply again with JSON, and set "chose" to one of these copied exactly, or to null:\n'
    "{options}"
)


@dataclass(frozen=True)
class ModelReader:
    """Reads an end user's answer into the option it meant, with a model.

    Whole-answer equality reads no option out of prose, so a channel a person writes sentences
    into needs a rule that reads more. Registering one of these is that rule::

        registry.add(consult(ask_in_chat, answered_by="end_user",
                             read=ModelReader(model=cheap)))

    ``model`` is the client that reads answers, and is not the one the agent runs on. A cheap
    one is normally right: the question is which of a handful of options a sentence meant. One
    answer takes one call, or up to ``attempts`` of them, and the verdict reaches the run as
    ``Reply.chose``. Each call is charged to the run's budget and recorded as a ``model_call``
    parented to the consultation, and served from the cassette on a replay.

    ``instructions`` is the prompt. ``{options}`` and ``{answer}`` in it are filled per call,
    and both are required::

        ModelReader(model=cheap, instructions=(
            "A support agent offered these codes:\\n{options}\\n\\n"
            "The engineer replied:\\n{answer}\\n\\n"
            "Copy the code they meant, or null where they named none."))

    ``attempts`` counts every call, so ``attempts=1`` is no retry and the default of 2 is one
    call plus one more. A model naming something that is not an option is told what was wrong
    and given the list again. A reader that has used its attempts ends the run rather than
    returning a verdict nobody made, and the answer it could not read is in the message.

    An answer meaning none of the options is ``None``, which reaches the run as ``unmatched``
    and is what a route branches on. An end user answering with a condition is amending the
    question rather than choosing.
    """

    model: Any
    """The client that reads the answers."""

    instructions: str = DEFAULT_READING_INSTRUCTIONS
    """The prompt it reads them with. ``{options}`` and ``{answer}`` are filled per call."""

    temperature: float | None = 0.0
    """Passed to that client. Reading an answer is not a task variety helps."""

    max_output_tokens: int | None = 1500
    """The ceiling on one call. A verdict is a handful of tokens and a model that reasons
    spends the rest on its chain of thought: `Qwen/Qwen3-1.7B` spent 404 to 827 reading three
    answers over two options. Unreached tokens cost nothing, so this is high enough for one of
    those rather than tight around the verdict."""

    attempts: int = 2
    """Total calls for one answer, counting the first. ``1`` is no retry."""

    def __post_init__(self) -> None:
        if not hasattr(self.model, "complete") or not hasattr(self.model, "identity"):
            raise ConfigurationError(
                f"ModelReader(model={self.model!r}) is not a ModelClient. It takes the client "
                f"that reads what an end user answered, which is normally a cheaper one than "
                f"the agent runs on: ModelReader(model=VLLMClient(...))."
            )
        missing = [f for f in ("{options}", "{answer}") if f not in self.instructions]
        if missing:
            raise ConfigurationError(
                f"ModelReader(instructions=...) has no {' or '.join(missing)} in it, so "
                f"{'they reach' if len(missing) > 1 else 'it reaches'} the model nowhere and "
                f"every answer is read against the prompt alone.\n"
                f"Put {'them' if len(missing) > 1 else 'it'} where the text belongs: "
                f"instructions='...The options:\\n{{options}}\\n\\nTheir answer:\\n"
                f"{{answer}}\\n\\n...'."
            )
        try:
            Prompt.user(
                self.instructions + READING_FORMAT, options="- an option", answer="an answer"
            ).to_messages()
        except Exception as exc:
            raise ConfigurationError(
                f"ModelReader(instructions=...) cannot be filled in: {type(exc).__name__}: "
                f"{exc}. The prompt is formatted once per answer, so a brace that is not "
                f"{{options}} or {{answer}} raises after the end user has already been asked.\n"
                f'Double any other brace: a JSON example is written {{{{"chose": "yes"}}}}.'
            ) from exc
        if not isinstance(self.attempts, int) or self.attempts < 1:
            raise ConfigurationError(
                f"ModelReader(attempts={self.attempts!r}) needs a whole number of calls, at "
                f"least 1. `attempts` counts every call rather than the retries after the "
                f"first, so attempts=1 is no retry and attempts=2 is one call plus one more. "
                f"Pass ModelReader(model=..., attempts=2)."
            )

    def __call__(self, reading: Reading, answer: str, options: Sequence[str]) -> str | None:
        """Which option this answer meant, or ``None`` where it meant none of them."""
        listed = Section.joined(
            "options", [Section("option", "- {option}", option=option) for option in options]
        )
        asked = Prompt.user(self.instructions + READING_FORMAT, options=listed, answer=answer)
        problem = ""
        for _ in range(self.attempts):
            response = reading.complete(
                self.model,
                asked,
                output_schema=READING_SCHEMA,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
            )
            chosen, problem = _choice_in(response.content, options)
            if problem is None:
                return chosen
            if response.finish_reason == "length":
                raise CallerFacingError(
                    f"The model reading the end user's answer, "
                    f"{self.model.identity().request_model}, reached its output ceiling before "
                    f"finishing, so which option they meant cannot be read out of "
                    f"{(response.content or '')[:120]!r}. A reasoning model spends this "
                    f"ceiling on its chain of thought as well as on the verdict.\n"
                    f"Raise it: ModelReader(model=..., max_output_tokens=2000)."
                )
            asked = (
                asked
                + Prompt.assistant("{said}", said=response.content or "")
                + Prompt.user(RETRY_RULE, problem=problem, options=listed)
            )
        raise CallerFacingError(
            f"The model reading the end user's answer, "
            f"{self.model.identity().request_model}, did not name one of the options in "
            f"{self.attempts} call{'s' if self.attempts > 1 else ''}. Last: {problem}\n"
            f"The answer it was reading was {str(answer)[:200]!r}, offered "
            f"{', '.join(repr(o) for o in options)}. A run recording a cassette has that "
            f"answer filed in it, so a re-run against that cassette serves it rather than "
            f"asking again.\n"
            f"Raise ModelReader(attempts=...), pass a model that honours output_schema, or "
            f"read this channel's answers with consult(match=...) instead."
        )

    def identity(self) -> dict[str, Any]:
        """What this reader is, for the manifest entry of the tool it reads for.

        Two runs differing in which model read the answers, or in the prompt it read them
        with, routed on different verdicts, so the entry says which one this run used.
        """
        return {
            "kind": "model",
            "model": self.model.identity().to_manifest(),
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "attempts": self.attempts,
            "instructions": _digest(self.instructions),
        }


def _choice_in(content: str | None, options: Sequence[str]) -> tuple[str | None, str | None]:
    """The option a reading names, and what is wrong with it where nothing is named.

    ``(chosen, None)`` is a verdict, and ``chosen`` of ``None`` is the answer meaning none of
    the options. ``(None, problem)`` is a reply that could not be read, and ``problem`` is what
    the retry states back.
    """
    try:
        parsed = json.loads(content or "")
        chosen = parsed["chose"]
    except Exception:
        return None, (
            f"{(content or '')[:200]!r} is not the "
            f'{{"chose": ..., "reason": ...}} it was asked for.'
        )
    if chosen is None:
        return None, None
    if chosen in options:
        return str(chosen), None
    return None, (
        f"{str(chosen)[:120]!r} is not one of the options, and an option has to be copied exactly."
    )


def _digest(text: str) -> str:
    """A short digest of a prompt, for a record that says which one a run used."""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"


def unattended(
    reason: str = "this run is unattended, so no one can be asked",
) -> ConsultChannel:
    """A channel for a run with nobody to ask, which answers nothing and blocks nothing.

    Smoke runs, fake runs and sweeps reach a consultation with no person behind it. A channel
    that reads a terminal blocks such a run and one that returns a fixed string records an
    answer nobody gave, so this returns :class:`Unavailable` instead::

        registry.add(consult(unattended()))

        smoke = env.with_end_user(unattended())     # or, without touching the registration

    It declares ``answered_by`` of ``nobody``, so a project whose live runs still go through it
    is visible in the manifest rather than in its numbers.
    """
    channel: Any = lambda question, options, about=None: Unavailable(  # noqa: E731
        reason=reason
    )
    channel.answered_by = "nobody"
    channel.may_suspend = False
    return channel


def ask_on_stdin(
    question: str, options: Sequence[str] | None = None, about: str | None = None
) -> str | None:
    """A channel that prints the question and reads the answer from the terminal.

    For a run someone is sitting in front of. The options are shown, and an empty line is a
    refusal to answer::

        registry.add(consult(ask_on_stdin, answered_by="builder"))

    ``answered_by`` has to be declared beside it, because a terminal is the builder's while a
    project is being built and the end user's once it ships, and the answer to which one this
    is decides whether a number was measured against the people it claims.

    The run blocks until the line is typed. Where nobody may be there,
    :func:`unattended` answers nothing and :class:`~simple_agents.errors.Suspend` stops the run
    instead (``docs/pipeline.md`` §1.8).
    """
    prompt = f"{question} ({', '.join(options)}) " if options else f"{question} "
    return input(prompt).strip() or None


def _matched(answer: str, options: Sequence[str] | None, match: Any) -> str | None:
    """Which option the answer is, or ``None`` where it is none of them."""
    if not options:
        return None
    if match is not None:
        chosen = match(answer, list(options))
        if chosen is not None and chosen not in options:
            raise ConfigurationError(
                f"A consult(match=...) function returned {chosen!r}, which is not one of the "
                f"options it was given ({', '.join(repr(o) for o in options)}). Return one of "
                f"them, or None where the answer matched none."
            )
        return chosen
    folded = normalise_text(answer)
    for option in options:
        if normalise_text(option) == folded:
            return option
    return None


def consult(
    ask: ConsultChannel,
    *,
    answered_by: str | None = None,
    reaches: str | None = None,
    permission: str | None = None,
    name: str = "consult",
    description: str | None = None,
    version: str | None = None,
    match: Callable[[str, list[str]], "str | None"] | None = None,
    read: Callable[..., "str | None"] | None = None,
) -> ConsultTool:
    """A tool that asks the end user a question and returns their answer.

    ``ask`` takes the question, the offered options and the ``about`` the caller named, and
    returns the answer, ``None`` if the end user declined, :class:`Unavailable` if there was
    nobody to ask, or :class:`Shelved` if the question was put somewhere a person will see it
    later. What it does in between is the project's::

        registry.add(consult(ask_on_stdin, answered_by="builder"))

        def ask_in_chat(question, options, about):
            return chat.ask(question, buttons=options)

        registry.add(consult(ask_in_chat, answered_by="end_user"))

    ``answered_by`` says who the channel reaches, one of ``end_user``, ``builder``,
    ``coding_agent``, ``simulated``, ``canned`` or ``nobody``, and is required: a resolution of
    ``answered`` says a question was answered and not by whom. A shipped channel declares its
    own, and ``coding_agent`` needs ``permission`` beside it. ``reaches`` names which answerer,
    where a pipeline asks more than one: two tools reaching one person declare one name, and a
    pipeline asking one leaves it unset::

        registry.add(consult(ask_analyst, answered_by="end_user", reaches="requester",
                             name="ask_requester"))
        registry.add(consult(ask_director, answered_by="end_user", reaches="approver",
                             name="ask_approver"))

    The answer comes back as a :class:`Reply`, a string carrying which option it matched::

        reply = ctx.call_tool("consult", question="Ship it?", options=["yes", "no"])
        reply.chose      # 'yes', or None where the answer matched no option

    ``options`` decides how an answer is read and does not constrain what the end user may
    say: one matching none of them is kept, with ``chose`` set to ``None``. ``match=`` is a
    rule over the text and ``read=`` one made through a model, and a tool takes one::

        registry.add(consult(ask_in_chat, answered_by="end_user",
                             read=ModelReader(model=cheap)))

    The call is recorded as a ``consultation`` rather than a ``tool_call``, carrying what was
    asked, what came back, who answered and how it ended, and is declared ``READ_ONLY``. Set
    ``description`` to say what this agent should ask about; the default invites either too
    many questions or none.
    """
    _refuse_a_bad_registration(ask, match, read)
    answered_by = _declared_answerer(ask, answered_by)
    permission = _declared_permission(ask, answered_by, permission)

    @tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, description=description)
    def ask_the_user(
        question: str, options: list[str] | None = None, about: str | None = None
    ) -> Reply | None:
        """Ask the person using this agent a question, and wait for their answer.

        Use this for something only they can settle: a preference, which of two readings was
        meant, or permission to go ahead. Do not use it for anything findable with the other
        tools. Pass `options` to offer a choice rather than an open question. Pass `about` as a
        short stable name for the thing the question is about, the same name every time it
        comes up, so an answer arriving later can be matched to it. Returns their answer, or
        nothing if they declined to answer.
        """
        return _asked(ask, None)(question, options, about)

    def read_answer(answer: Any, options: Sequence[str] | None) -> Reply | None:
        if answer is None:
            return None
        if isinstance(answer, (Unavailable, Shelved)):
            return answer
        if Unavailable.stored_in(answer):
            return Unavailable.from_json(answer)
        if Shelved.stored_in(answer):
            return Shelved.from_json(answer)
        declared = answered_at = None
        if isinstance(answer, Reply):
            # A channel that builds its own carries what only it knows. `chose` is derived
            # again below, because the rule that reads it is the tool's and runs on a replay
            # too.
            declared, answered_at = answer.declared_choice, answer.answered_at
        elif Reply.stored_in(answer):
            declared = answer.get("declared_choice")
            answered_at = answer.get("answered_at")
            answer = answer.get("reply")
            if answer is None:
                return None
        text = str(answer)
        return Reply(
            text,
            chose=_matched(text, options, match),
            options=options or (),
            declared_choice=declared,
            answered_at=answered_at,
        )

    def _asked(channel: ConsultChannel, provenance: dict[str, Any] | None) -> Callable[..., Any]:
        """The body one call runs: ask ``channel``, and report what produced the answer."""

        def one_call(
            question: str, options: list[str] | None = None, about: str | None = None
        ) -> Any:
            answer = channel(question, options, about)
            if isinstance(answer, (Unavailable, Shelved)):
                # Stored as plain data rather than as itself, so a replay of this run ends the
                # way the live run did rather than being answered with the text.
                return answer.to_json()
            declared = None
            if isinstance(answer, ModelAnswer):
                if provenance is not None and answer.model is not None:
                    provenance.update(model=answer.model, tokens=answer.tokens, cost=answer.cost)
                declared = answer.declared_choice
                answer = answer.text
            reply = read_answer(answer, options)
            if reply is None or isinstance(reply, (Unavailable, Shelved)):
                return reply
            if declared is None and reply.answered_at is None:
                return reply
            # Stored as plain data rather than as text, so a replay of this run reads the same
            # declaration the live run did and reports the same misreading count, and says the
            # same thing about when the answer was given.
            return Reply(
                str(reply),
                chose=reply.chose,
                options=reply.options,
                declared_choice=declared if declared is not None else reply.declared_choice,
                answered_at=reply.answered_at,
            ).to_json()

        return one_call

    return ConsultTool(
        name=ask_the_user.name,
        description=ask_the_user.description,
        parameters=ask_the_user.parameters,
        side_effect_class=ask_the_user.side_effect_class,
        fn=ask_the_user.fn,
        version=version or _derived_version(ask, match),
        declared_cost=ask_the_user.declared_cost,
        handles=ask_the_user.handles,
        _validator=ask_the_user._validator,
        read_answer=read_answer,
        reader=read,
        answered_by=answered_by,
        reaches=_declared_answerer_name(ask, reaches),
        permission=permission,
        ask=ask,
        asking=_asked,
    )


def _refuse_a_bad_registration(ask: Any, match: Any, read: Any) -> None:
    """Refuse a :func:`consult` whose channel or reading rule cannot do the job asked of it."""
    if not callable(ask):
        raise ConfigurationError(
            "consult(ask=...) takes a function of (question, options, about) returning the end "
            "user's answer, None where they declined, or Unavailable(reason=...) where there "
            "was nobody to ask. The library never reads from a terminal itself, so the "
            "project supplies the channel: consult(ask_on_stdin, answered_by='builder')."
        )
    if match is not None and not callable(match):
        raise ConfigurationError(
            "consult(match=...) takes a function of (answer, options) returning the option "
            "the answer is, or None where it is none of them. Leave it unset for the default, "
            "which folds case and punctuation so 'Yes.' matches the option 'yes'."
        )
    if read is not None and not callable(read):
        raise ConfigurationError(
            "consult(read=...) takes the rule that reads an answer into the option it meant, "
            "made through a model. Pass the shipped one, consult(ask, answered_by='end_user', "
            "read=ModelReader(model=cheap)), or a function of (reading, answer, options) "
            "returning one of the options or None."
        )
    if read is not None and match is not None:
        raise ConfigurationError(
            "consult() was given both match= and read=, which are two rules for one job: "
            "which option an answer was. `match` runs on every replay and reads the text "
            "alone; `read` makes one recorded model call and its verdict is stored.\n"
            "Keep the one that reads this channel's answers. A channel whose answers are "
            "always one of the options needs neither."
        )


def _declared_answerer_name(ask: ConsultChannel, reaches: str | None) -> str | None:
    """Which answerer this channel reaches, from the argument or from the channel itself."""
    declared = reaches if reaches is not None else getattr(ask, "reaches", None)
    if declared is None:
        return None
    if not str(declared).strip():
        raise ConfigurationError(
            "consult(reaches='') was given an empty name. It names which answerer this tool "
            "asks, for a pipeline that asks more than one, and a run supplies a description "
            "per name.\n"
            "Pass consult(ask, answered_by='end_user', reaches='approver'), or leave it unset "
            "where the pipeline asks one person."
        )
    return str(declared)


def _declared_answerer(ask: ConsultChannel, answered_by: str | None) -> str:
    """Who this channel says answers, from the argument or from the channel itself."""
    declared = answered_by if answered_by is not None else getattr(ask, "answered_by", None)
    if declared is None:
        raise ConfigurationError(
            "consult() was given no answered_by, so a trajectory would record that its "
            "questions were answered without recording who by. A channel returning a fixed "
            "string and one reaching a person both record `answered`, which is how an agent "
            "measured unattended reads as one measured against its end users (FT-25).\n"
            "Declare it: consult(ask, answered_by='end_user') for a channel reaching the "
            "people the agent is for, 'builder' for a terminal answered while the project is "
            "built, 'coding_agent' with permission=..., 'canned' for a fixed answer, or "
            "consult(unattended()) for a run with nobody to ask."
        )
    if declared not in ANSWERED_BY:
        raise ConfigurationError(
            f"consult(answered_by={declared!r}) is not one of {', '.join(ANSWERED_BY)}. "
            f"Declare the closest one: 'end_user' for the people the agent is for, 'builder' "
            f"for the project's own author standing in for them, 'coding_agent' for an "
            f"unattended run the builder agreed to, 'simulated' for a model playing them, "
            f"'canned' for a fixed answer, 'nobody' for a channel that answers nothing."
        )
    return declared


def _declared_permission(
    ask: ConsultChannel, answered_by: str, permission: str | None
) -> str | None:
    """The builder's agreement to a coding agent answering, where one is needed."""
    given = permission if permission is not None else getattr(ask, "permission", None)
    if answered_by != "coding_agent":
        return str(given) if given else None
    if not (given and str(given).strip()):
        raise ConfigurationError(
            "consult(answered_by='coding_agent') was given no permission. A coding agent "
            "answering as the end user invents what a person would have said, and it knows "
            "what the pipeline it wrote needs to hear, so the builder agrees to it in "
            "advance and the run records that they did.\n"
            "Pass their words: consult(ask, answered_by='coding_agent', permission='agreed "
            "on 2026-08-15 that smoke runs may be answered without me'). Where they have not "
            "agreed, consult(unattended()) answers nothing instead."
        )
    return str(given)


_MISSING = object()


def _reply_in(output: Any, field: str | None) -> Any:
    """The reply a route is deciding on, read off the node's output.

    ``field`` is a key on a mapping and an attribute on anything else, so a node returning
    ``{"answer": reply}`` and one returning a model with an ``answer`` field both work. A
    field that is not there raises rather than reading as a refusal.
    """
    if field is None:
        return output
    found = (
        output.get(field, _MISSING)
        if isinstance(output, Mapping)
        else getattr(output, field, _MISSING)
    )
    if found is _MISSING:
        raise CallerFacingError(
            f"on_reply(field={field!r}) found no {field!r} on the "
            f"{type(output).__name__} this node returned, and a missing reply cannot be told "
            f"from a refusal, so this route would pick a branch on an answer it never read.\n"
            f"{_where_to_look(field)} What the node returned holds "
            f"{_names_on(output) or 'nothing'}."
        )
    return found


def _names_on(output: Any) -> str:
    """The keys or fields a route could have been pointed at, for a refusal to name."""
    if isinstance(output, Mapping):
        return ", ".join(repr(str(key)) for key in sorted(map(str, output)))
    if output is None:
        return ""
    fields = getattr(type(output), "model_fields", None)
    names = fields if fields is not None else getattr(output, "__dict__", {})
    return ", ".join(repr(name) for name in sorted(names))


def _where_to_look(field: str | None) -> str:
    """The correction both refusals end on."""
    if field is None:
        return (
            "Return the reply itself from the node, or name where it is: "
            "on_reply({...}, field='answer', ...)."
        )
    return (
        f"Return the reply under {field!r}, name the field it is really under, or drop field= "
        f"and return the reply itself. A field typed `str` keeps the text and drops `chose`, "
        f"so type it `Reply`."
    )


def _derived_version(*parts: Any) -> str | None:
    """A version over the project's channel and its matcher.

    ``@tool`` derives a version from one function's source, and a consult tool's behaviour is
    spread over two: two consult tools differing only in which channel they ask through record
    under different cassette keys.

    The library's own tool function is left out, unlike every other built-in. What a
    consultation stores is what the end user said, which no edit to this module changes, so
    covering it would make a library upgrade miss every recorded consultation and ask a person
    again for nothing.

    ``None`` where neither has readable source, such as a channel built by
    ``functools.partial``. Declare ``version=`` where that matters.

    ``read=`` is left out as well. What a consultation stores is what the end user said, and
    the rule that reads it into an option is applied afterwards, so covering it here would
    miss every recorded answer and ask a person again over an edited prompt. The reader is on
    the tool's manifest entry instead, and an edit to it is a miss on the reading's own model
    call.
    """
    sources = [derived_version(part) for part in parts if part is not None]
    if not any(sources):
        return None
    joined = "|".join(source or "" for source in sources)
    return f"sha256:{hashlib.sha256(joined.encode('utf-8')).hexdigest()[:12]}"


def on_reply(
    chose: Mapping[str, str],
    *,
    unmatched: str | None = None,
    declined: str | None = None,
    unavailable: str | None = None,
    shelved: str | None = None,
    field: str | None = None,
    exhaustive: bool = False,
) -> Callable[[Any, Any], str]:
    """A ``route=`` over what the end user answered, one successor per option.

    ``chose`` maps an offered option to the node it goes to; ``unmatched`` takes an answer
    that was none of them, ``declined`` a refusal, ``unavailable`` nobody to ask, and
    ``shelved`` a question put somewhere a person will answer later::

        Deterministic(
            ask,
            tools=[consult(channel, answered_by="end_user")],
            successors=["apply", "amend", "stop", "proceed"],
            route=on_reply({"yes": "apply", "no": "stop"}, unmatched="amend",
                           declined="stop", unavailable="proceed", shelved="proceed"),
        )

    Those three usually differ: declining is a choice, nobody being there is the absence of
    one, and a shelved question has reached somebody with the answer still coming.

    ``field`` names where the reply is on the node's output, for a node returning a model or a
    dict rather than the reply itself::

        route=on_reply({"yes": "apply"}, field="answer", unmatched="amend",
                       declined="stop", unavailable="proceed", shelved="proceed")

    A route that cannot find the reply refuses rather than picking a branch: a field that is
    not there and a value that is not a :class:`Reply` both end the run naming what came back.

    All four branches are required, since an end user can always say something that is not on
    the list, can always decline, can always turn out not to be there, and can always be
    somebody the question was left with who has not answered yet. Where the options really are
    the only outcomes, waive all four with ``exhaustive=True``::

        route=on_reply({"approve": "apply", "reject": "stop"}, exhaustive=True)

    The waiver is recorded in the run manifest, and a reply that arrives unmatched, declined,
    unavailable or shelved under it ends the run rather than picking a branch, naming what the
    end user said.
    """
    if not chose:
        raise ConfigurationError(
            "on_reply() needs at least one option mapped to a successor: "
            "on_reply({'yes': 'apply', 'no': 'stop'}, unmatched='amend', declined='stop', "
            "unavailable='proceed', shelved='proceed')."
        )
    branches = (
        ("unmatched", unmatched),
        ("declined", declined),
        ("unavailable", unavailable),
        ("shelved", shelved),
    )
    if exhaustive and any(value is not None for _, value in branches):
        named = next(name for name, value in branches if value is not None)
        raise ConfigurationError(
            f"on_reply() was given exhaustive=True and a branch for {named}, which contradict "
            f"each other: exhaustive=True says the options are the only outcomes, and the "
            f"branch says what happens when they are not. Drop exhaustive=True and name all "
            f"four branches, or drop the branch."
        )
    if not exhaustive and any(value is None for _, value in branches):
        missing = [name for name, value in branches if value is None]
        raise ConfigurationError(
            f"on_reply() has no branch for {' and '.join(missing)}. An end user can answer "
            f"something that is not on the list, can decline to answer, can turn out not to be "
            f"there at all, and can be somebody the question was left with who has not answered "
            f"yet, so a route without somewhere for those to go stops the run on an answer it "
            f"was given. Declining is a choice, being unavailable is the absence of one, and a "
            f"shelved question has reached somebody, so they rarely go to the same node.\n"
            f"Name them: on_reply({{...}}, unmatched='amend', declined='stop', "
            f"unavailable='proceed', shelved='proceed'). Where the options really are the only "
            f"outcomes, waive all four with on_reply({{...}}, exhaustive=True); the waiver is "
            f"recorded in the manifest."
        )

    def route(output: Any, ctx: Any) -> str:
        reply = _reply_in(output, field)
        if isinstance(reply, Shelved):
            if shelved is not None:
                return shelved
            raise CallerFacingError(
                f"This question was shelved for somebody to answer later ({reply.reason}), "
                f"and this route was built with exhaustive=True, which says the offered "
                f"options are the only outcomes. Give it a branch: on_reply({{...}}, "
                f"unmatched=..., declined=..., unavailable=..., shelved=...)."
            )
        if isinstance(reply, Unavailable):
            if unavailable is not None:
                return unavailable
            raise CallerFacingError(
                f"There was nobody to answer this consultation ({reply.reason}), and this "
                f"route was built with exhaustive=True, which says the offered options are "
                f"the only outcomes. Give it a branch: on_reply({{...}}, unmatched=..., "
                f"declined=..., unavailable=..., shelved=...)."
            )
        if reply is None:
            if declined is not None:
                return declined
            raise CallerFacingError(
                "The end user declined to answer, and this route was built with "
                "exhaustive=True, which says the offered options are the only outcomes. "
                "Give it a branch: on_reply({...}, unmatched=..., declined=..., "
                "unavailable=..., shelved=...)."
            )
        if not hasattr(reply, "chose"):
            raise CallerFacingError(
                f"on_reply() was given {type(reply).__name__} where the consultation's reply "
                f"was expected, and a value with no `chose` cannot be told from a refusal, so "
                f"this route would pick a branch on an answer it never read.\n"
                f"{_where_to_look(field)}"
            )
        chosen = reply.chose
        if chosen is None:
            if unmatched is not None:
                return unmatched
            raise CallerFacingError(
                f"The end user answered {str(reply)!r}, which is none of the offered options "
                f"({', '.join(repr(o) for o in getattr(reply, 'options', ()))}), and this "
                f"route was built with exhaustive=True, which says they are the only "
                f"outcomes. Give it a branch: on_reply({{...}}, unmatched=..., declined=..., "
                f"unavailable=..., shelved=...)."
            )
        if chosen not in chose:
            raise CallerFacingError(
                f"The end user chose {chosen!r} and this route maps "
                f"{', '.join(repr(o) for o in chose)}, so nothing says where it goes. Add it: "
                f"on_reply({{..., {chosen!r}: '<node id>'}}, ...)."
            )
        return chose[chosen]

    route.consultation_route = {  # type: ignore[attr-defined]
        "chose": dict(chose),
        "unmatched": unmatched,
        "declined": declined,
        "unavailable": unavailable,
        "shelved": shelved,
        "field": field,
        "exhaustive": exhaustive,
    }
    return route
