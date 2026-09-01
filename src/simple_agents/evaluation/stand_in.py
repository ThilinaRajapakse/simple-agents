"""The end user an evaluation answers with, played by a model.

An agent that consults is measured against whoever answers it. A channel that answers nothing
measures an agent whose questions all failed, and a channel returning a fixed string measures
one whose questions were all answered the same way. Neither is the agent the brief describes.

The questions cannot be written in advance: the model writes them during the run, out of what
that run happened to find. So the example describes the person instead, and a model reads that
description and answers as them.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any, Sequence

from ..builtins.consult import ConsultChannel, ModelAnswer
from ..context import derive_seed
from ..cost import CostBasis, cost_of
from ..errors import CallerFacingError, ConfigurationError
from ..models import ModelClient, ModelRequest
from ..records.trajectory import utc_now
from .end_user import EndUser

__all__ = ["SimulatedEndUser", "DEFAULT_INSTRUCTIONS"]

REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reply": {
            "type": ["string", "null"],
            "description": (
                "What this person says, in their own words, or null if they would not "
                "answer at all."
            ),
        }
    },
    "required": ["reply"],
    "additionalProperties": False,
}

CHOOSING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reply": REPLY_SCHEMA["properties"]["reply"],
        "chose": {
            "type": ["string", "null"],
            "description": (
                "Which offered answer the reply is, copied exactly, or null where it is none "
                "of them, including where it answers with a condition or a question."
            ),
        },
    },
    "required": ["reply", "chose"],
    "additionalProperties": False,
}

DEFAULT_INSTRUCTIONS = (
    "Reply as one specific person, described below. An agent is doing a task for that person "
    "and has stopped to ask them something.\n\n"
    "The person:\n{end_user}\n\n"
    "Write what they would say, in one or two sentences, in their own voice. Keep it what they "
    "would say even where that is unhelpful, brief, or a complaint about the question. Invent "
    "no facts about them that the description does not support, and do not write as an "
    "assistant would."
)
"""The prompt a stand-in uses where the project passes none.

``{end_user}`` is filled in with the example's description and whichever of its facts this
person would state. What the library appends to it is the reply format, and the rule about
what they have already said; a project replacing this keeps both.
"""

VOLUNTEERED = "They will say these without being asked:"
ON_ASK = "They know these, and will say one only when the agent asks about that thing:"

RECORD_RULE = (
    "\n\nWhat this person has already said in this conversation is below, and it is the whole "
    "record of it. Answer consistently with it, and where the agent says they chose or told it "
    "something that is not there, say so rather than agreeing."
)

FORMAT = (
    '\n\nReply with JSON: {{"reply": "<what they say>"}}, or {{"reply": null}} where this '
    "person would not answer at all."
)
CHOOSING_FORMAT = (
    '\n\nReply with JSON: {{"reply": "<what they say>", "chose": "<the offered answer this is, '
    'copied exactly, or null>"}}. Set "chose" to null where what they say is none of the '
    "offered answers, including where they answer with a condition or a question. Say what "
    "they would say either way: `chose` records which answer that was and does not replace it."
)

QUESTION = "The agent asks: {question}"
CHOICES = "It offers these answers: {options}. This person may pick one or say something else."


@dataclass(frozen=True, slots=True)
class SimulatedEndUser:
    """An end user played by a model, for evaluating an agent that consults.

    ``model`` is the client that plays them, and is not the one being measured::

        suite = EvalSuite(pipeline, examples, answer="answer", matches=exact)
        results = suite.run(envelope=env, model=client, split="held_out", k=3,
                            end_user=SimulatedEndUser(model=cheap))

    Each rollout gets its own, reading that example's ``end_user``. Every consultation records
    ``answered_by`` ``simulated`` with the model that wrote it and what it cost, so a figure is
    never read as one measured against real people.

    ``instructions`` is the prompt, and ``{end_user}`` in it is filled with the example's
    description and whichever facts that person would state. Replace it for a non-person::

        SimulatedEndUser(model=cheap, instructions=(
            "Reply as the system described below, which an agent has queried.\\n\\n"
            "The system:\\n{end_user}\\n\\n"
            "Answer with a value or an error, in the fewest words that carry it."))

    The reply format and the rule about what this person has already said are appended by the
    library, so replacing the prompt keeps both. Each question is answered with what this
    person already answered in that rollout in front of it, and without that a stand-in asked
    to approve a title they never picked agrees.

    Its calls are seeded from the rollout's seed and the question and stored in the cassette,
    so a replay gets the same answers. It spends against ``model`` rather than the agent's
    budget, and its tokens stay out of the node's counts. An example that says nothing about
    who the agent is answering is refused before the first rollout: a model with nobody to
    play invents an agreeable reader, which is what makes a consulting agent look better than
    it is.
    """

    model: ModelClient
    """The client that writes the answers. A cheap one is normally right; it is playing a
    person rather than doing the task."""

    temperature: float | None = None
    """Passed to that client. ``None`` leaves it to the client's own default."""

    max_output_tokens: int | None = 300
    """The ceiling on one call. An end user's reply is short, and a model that reasons spends
    this on its chain of thought as well, so one of those needs more than the default."""

    instructions: str = DEFAULT_INSTRUCTIONS
    """The prompt this plays the person with. ``{end_user}`` is filled in per example."""

    may_suspend = False
    """This channel answers in the process that asked, so its calls may overlap. A channel that
    stops the run to reach somebody leaves this unset (``docs/tools.md`` §4.6.3)."""

    def __post_init__(self) -> None:
        if not hasattr(self.model, "complete") or not hasattr(self.model, "identity"):
            raise ConfigurationError(
                f"SimulatedEndUser(model={self.model!r}) is not a ModelClient. It takes the "
                f"client that plays the end user, which is normally a cheaper one than the "
                f"agent is measured on: SimulatedEndUser(model=VLLMClient(...))."
            )
        if "{end_user}" not in self.instructions:
            raise ConfigurationError(
                "SimulatedEndUser(instructions=...) has no {end_user} in it, so the example's "
                "description of the person reaches the model nowhere and every rollout is "
                "answered by whoever the prompt alone describes.\n"
                "Put it where the description belongs: instructions='Reply as the system "
                "described below...\\n\\nThe system:\\n{end_user}\\n\\n...'."
            )

    def identity(self) -> dict[str, Any]:
        """What this stand-in is, for the evaluation's own identity.

        Two evaluations differing only in which model plays the end user, or in the prompt it
        plays them with, measured different things, so they resolve to different run
        directories rather than one refusing the other's.
        """
        return {
            "kind": "simulated",
            "model": self.model.identity().to_manifest(),
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "instructions": _digest(self.instructions),
        }

    def playing(
        self,
        end_user: EndUser | str,
        *,
        seed: int,
        cost_basis: CostBasis | None = None,
        name: str = "",
    ) -> ConsultChannel:
        """This stand-in bound to one rollout: one person, one seed, one conversation.

        ``end_user`` is the example's description of them. ``name`` is the answerer this plays
        where a run has more than one, which the seed and the record both carry. The library
        calls this; a project passes the :class:`SimulatedEndUser` itself to ``EvalSuite.run``.
        """
        person = (
            end_user
            if isinstance(end_user, EndUser)
            else EndUser(str(end_user))
            if str(end_user or "").strip()
            else None
        )
        said: list[tuple[str, str]] = []
        lock = threading.Lock()

        def answer(
            question: str,
            options: Sequence[str] | None = None,
            about: str | None = None,
        ) -> ModelAnswer:
            if person is None:
                raise ConfigurationError(
                    f"This rollout asked {question.strip()[:80]!r}, and the example it ran on "
                    f"says nothing about who the agent is answering, so there is nobody for "
                    f"the model to play. Answering anyway measures the agent against whoever "
                    f"the prompt alone describes, which is more agreeable than any real "
                    f"reader (FT-24).\n"
                    f"Describe them: Example(..., end_user='Reads a lot of grimdark, wants "
                    f"something under 400 pages, and finds questions about difficulty useless "
                    f"and says so')."
                )
            with lock:
                history = tuple(said)
            reply = self._answer(
                question,
                options,
                seed=derive_seed(seed, f"end_user:{name}", _asked_about(question, options)),
                cost_basis=cost_basis,
                end_user=person,
                history=history,
            )
            if reply.text is not None:
                with lock:
                    said.append((question, reply.text))
            return reply

        answer.answered_by = "simulated"  # type: ignore[attr-defined]
        answer.may_suspend = False  # type: ignore[attr-defined]
        return answer

    def _answer(
        self,
        question: str,
        options: Sequence[str] | None,
        *,
        seed: int,
        cost_basis: CostBasis | None,
        end_user: EndUser,
        history: Sequence[tuple[str, str]] = (),
    ) -> ModelAnswer:
        """One question, answered as this person, priced against the run's basis."""
        system = self.instructions.format(end_user=_describing(end_user))
        if history:
            system += RECORD_RULE
        system += (CHOOSING_FORMAT if options else FORMAT).replace("{{", "{").replace("}}", "}")

        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for asked, said in history:
            messages.append({"role": "user", "content": QUESTION.format(question=asked)})
            messages.append({"role": "assistant", "content": json.dumps({"reply": said})})
        messages.append({"role": "user", "content": QUESTION.format(question=question)})
        if options:
            messages.append({"role": "user", "content": CHOICES.format(options=", ".join(options))})

        started_at = utc_now()
        response = self.model.complete(
            ModelRequest(
                messages=messages,
                seed=seed,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                output_schema=CHOOSING_SCHEMA if options else REPLY_SCHEMA,
            )
        )
        reply, declared = _reply_in(
            response.content, self.model, options, finish_reason=response.finish_reason
        )
        return ModelAnswer(
            reply,
            model=response_identity(response),
            tokens=response.tokens,
            declared_choice=declared,
            cost=cost_of(
                {
                    "record_type": "model_call",
                    "request_model": response.request_model,
                    "response_model": response.response_model,
                    "tokens": response.tokens.to_record(),
                    "concurrent_requests": response.concurrent_requests,
                    "recorded_duration_ms": None,
                    "started_at": started_at,
                    "ended_at": utc_now(),
                },
                cost_basis,
            ),
        )


def _describing(end_user: EndUser) -> str:
    """The block that fills ``{end_user}``: who they are, and what they would say.

    A ``hidden`` fact is left out. The model is what would state it, so the only way it cannot
    is for it never to be given it; an answer key reads it off the example instead.
    """
    block = [end_user.description.strip()]
    for heading, disclose in ((VOLUNTEERED, "volunteer"), (ON_ASK, "on_ask")):
        facts = end_user.disclosed(disclose=disclose)
        if facts:
            block.append(heading)
            block.extend(f"- {fact.text}" for fact in facts.values())
    return "\n".join(block)


def _asked_about(question: str, options: Sequence[str] | None) -> int:
    """A stable number for one question, for the seed its answer is drawn at.

    Derived from what was asked rather than from how many questions came before it, so two
    live runs at one seed answer the same question the same way whatever order the questions
    arrived in.
    """
    material = json.dumps([question, list(options or ())], sort_keys=True, default=str)
    return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:4], "big")


def _digest(text: str) -> str:
    """A short identifier for a prompt, for an evaluation's identity to carry."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def response_identity(response: Any) -> dict[str, Any]:
    """Which model actually wrote an answer, read off the response rather than the client."""
    return {
        "backend": response.backend,
        "request_model": response.request_model,
        "model_revision": response.model_revision,
    }


def _reply_in(
    content: str | None,
    model: ModelClient,
    options: Sequence[str] | None,
    *,
    finish_reason: str | None = None,
) -> tuple[str | None, str | None]:
    """What the person said and which offered answer they say it was.

    A refusal to answer is ``null``, which reaches the run as a declined consultation. Anything
    that does not parse ends the run rather than being recorded as an answer: an invented
    answer that a person never gave is what evaluating against a stand-in exists to avoid.

    The declared choice is dropped where it is not one of the offered answers. It never routes
    the run, which stays on the project's own rule, so a stand-in naming an answer that was not
    offered costs a comparison rather than a branch.
    """
    try:
        parsed = json.loads(content or "")
        reply = parsed["reply"]
    except Exception as exc:
        if finish_reason == "length":
            raise CallerFacingError(
                f"The model playing the end user, {model.identity().request_model}, reached "
                f"its output ceiling before finishing the answer, so what the person said "
                f"cannot be read out of {(content or '')[:120]!r}. A reasoning model spends "
                f"this ceiling on its chain of thought as well as on the reply, and the "
                f"prompt grows through a rollout as the questions it has already answered are "
                f"added to it.\n"
                f"Raise it: SimulatedEndUser(model=..., max_output_tokens=2000)."
            ) from exc
        raise CallerFacingError(
            f"The model playing the end user, {model.identity().request_model}, answered with "
            f"{(content or '')[:200]!r}, which is not the "
            f'{{"reply": "..."}} it was asked for, so what the person said cannot be read out '
            f"of it. Recording it as the answer would put words in their mouth.\n"
            f"Pass a model that honours output_schema to "
            f"SimulatedEndUser(model=...), or answer the evaluation's consultations with a "
            f"channel of the project's own."
        ) from exc
    declared = parsed.get("chose") if isinstance(parsed, dict) else None
    if declared is not None and declared not in (options or ()):
        declared = None
    return (None if reply is None else str(reply)), declared
