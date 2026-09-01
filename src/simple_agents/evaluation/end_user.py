"""Who an example's agent is answering, and what that person knows.

``Example.end_user`` takes prose where the answerer is only a manner of speaking, and an
:class:`EndUser` where they hold something the agent has to obtain. A model plays them during an
evaluation, and the facts decide both what it may say and what a scoring rule compares against.

An evaluation whose agent consults is measured against whoever answers it, so what an example
carries about that person is part of the label rather than decoration. ``docs/evaluation.md``
§5.4 is the schema of record for the encoded form.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping

from pydantic import BaseModel, ConfigDict

from ..errors import ConfigurationError

__all__ = ["Fact", "EndUser", "DISCLOSURE", "decode_end_user", "encode_end_user"]

DISCLOSURE = ("volunteer", "on_ask", "hidden")
"""When the end user says a fact they know.

``volunteer`` is stated without being asked, ``on_ask`` only when the agent asks about that
thing, and ``hidden`` never. ``docs/evaluation.md`` §5.4 says what each does to a run.
"""


class Fact(BaseModel):
    """One thing the end user knows, and when they say it.

    ``text`` is what they know, in words, and is what the model playing them is told.
    ``value`` is the same thing as data, for a scoring rule to compare an answer against::

        Fact("the cost centre for this project is CC-4471", value="CC-4471")
        Fact("anything over 5,000 pounds needs her director", value=5000, disclose="hidden")

    Both in one place is what keeps them from disagreeing: a fact written into the description
    and repeated in ``metadata`` is two values nothing compares.

    ``disclose`` is one of :data:`DISCLOSURE`. ``volunteer`` is in the prompt and stated
    unasked; ``on_ask`` is in the prompt with the instruction to state it only when asked about
    that thing, so the model is instructed rather than prevented; ``hidden`` is never given to
    the model, and reaches a run only through the answer key::

        criteria={"under_cap":
                  lambda s: s.answer.total <= s.example.end_user.knows["cap"].value}

    An agent cannot obtain a ``hidden`` fact by asking, so an example carrying one asks whether
    the answer respects something the agent was never told.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    value: Any = None
    disclose: Literal["volunteer", "on_ask", "hidden"] = "on_ask"

    def __init__(self, text: Any = None, **data: Any) -> None:
        if text is not None:
            data["text"] = text
        super().__init__(**data)
        if not str(self.text).strip():
            raise ConfigurationError(
                "A Fact was given no text. The text is what the model playing the end user is "
                "told, and what a report prints, so a fact with none is one the person cannot "
                "state.\n"
                "Pass Fact('the cost centre for this project is CC-4471', value='CC-4471')."
            )

    def to_json(self) -> dict[str, Any]:
        """What one line of an example file stores for this fact."""
        record: dict[str, Any] = {"text": self.text, "disclose": self.disclose}
        if self.value is not None:
            record["value"] = self.value
        return record


class EndUser(BaseModel):
    """The person or system an agent consults on one example, for a model to play.

    The description is what they are and how they answer, and it is written in the same place
    whether the other end is a person, an approver applying a policy, or an upstream system::

        EndUser("An operations manager. Brusque, and has no patience for questions she "
                "thinks the agent should answer itself.")

        EndUser("A billing API. Answers with a value or an error, and never explains.")

    ``knows`` is what they hold that the agent may have to obtain, keyed by a name a scoring
    rule can use::

        EndUser(
            "An operations manager. Brusque, no patience for questions she thinks the agent "
            "should answer itself.",
            knows={
                "deadline": Fact("this has to be filed today", disclose="volunteer"),
                "cost_centre": Fact("the cost centre is CC-4471", value="CC-4471"),
                "cap": Fact("anything over 5,000 needs her director", value=5000,
                            disclose="hidden"),
            },
        )

    A description alone is the common case and is written as a plain string:
    ``end_user="An operations manager..."`` means ``EndUser("An operations manager...")``.

    Write what would change an answer, including what the person will not put up with. What
    the description does not carry, the model will not invent: a stand-in asked for a cost
    centre no description mentions deflects rather than making one up, which is what makes an
    example's expected answer unreachable in every rollout.

    An example whose agent consults more than one person carries one of these per answerer,
    keyed by the name the ``consult`` tool declares in ``reaches``
    (``docs/evaluation.md`` §5.4).
    """

    model_config = ConfigDict(frozen=True)

    description: str
    knows: dict[str, Fact] = {}

    def __init__(self, description: Any = None, **data: Any) -> None:
        if description is not None:
            data["description"] = description
        data["knows"] = {
            str(name): _fact_in(fact) for name, fact in (data.get("knows") or {}).items()
        }
        super().__init__(**data)
        if not str(self.description).strip():
            raise ConfigurationError(
                "An EndUser was given no description. A model with nobody to play answers as "
                "an assistant would, which is more agreeable and more articulate than any "
                "real reader, and every rate computed over that is a rate against an "
                "invention (FT-24).\n"
                "Pass EndUser('Reads a lot of grimdark, wants something under 400 pages, and "
                "finds questions about difficulty useless and says so')."
            )

    def disclosed(self, *, disclose: str) -> dict[str, Fact]:
        """The facts carrying one disclosure, keyed as they were declared."""
        return {name: f for name, f in self.knows.items() if f.disclose == disclose}

    @property
    def hidden(self) -> dict[str, Fact]:
        """What this person never states, and an answer key may still read."""
        return self.disclosed(disclose="hidden")

    def to_json(self) -> Any:
        """What one line of an example file stores for this answerer.

        An answerer who knows nothing beyond their description stores as that description, so
        an example set written before ``knows`` existed hashes to what it always did.
        """
        if not self.knows:
            return self.description
        return {
            "type": "end_user",
            "description": self.description,
            "knows": {name: f.to_json() for name, f in self.knows.items()},
        }


def encode_end_user(value: Any) -> Any:
    """What an example file stores under ``end_user``, for any of the three forms."""
    if value is None:
        return None
    if isinstance(value, EndUser):
        return value.to_json()
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {str(name): encode_end_user(one) for name, one in value.items()}
    raise ConfigurationError(
        f"Example(end_user={value!r}) is a {type(value).__name__}. It takes the description of "
        f"the person the agent is answering, an EndUser carrying what they know, or one of "
        f"those per answerer keyed by the name a consult tool declares in reaches=.\n"
        f"Pass end_user='An operations manager, brusque and short of time', or "
        f"end_user=EndUser('...', knows={{'cost_centre': Fact('...', value='CC-4471')}})."
    )


def decode_end_user(raw: Any) -> Any:
    """Rebuild what an example file stored under ``end_user``.

    A string is a description. An object tagged ``end_user`` is one answerer. Anything else
    mapping-shaped is one per answerer.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        return EndUser(raw) if raw.strip() else None
    if isinstance(raw, EndUser):
        return raw
    if isinstance(raw, Mapping):
        if raw.get("type") == "end_user":
            return EndUser(
                str(raw.get("description") or ""),
                knows={
                    str(name): _fact_in(fact) for name, fact in (raw.get("knows") or {}).items()
                },
            )
        return {str(name): decode_end_user(one) for name, one in raw.items()}
    raise ConfigurationError(
        f"An example's end_user is {type(raw).__name__}, which is none of the three forms it "
        f'takes: a description, an object tagged {{"type": "end_user"}}, or one of those per '
        f"answerer."
    )


def _fact_in(raw: Any) -> Fact:
    """One fact, from a :class:`Fact`, from bare text, or from what a file stored.

    Bare text is a fact with the default disclosure and no value, which is right for something
    the end user says and no scoring rule reads.
    """
    if isinstance(raw, Fact):
        return raw
    if isinstance(raw, str):
        return Fact(raw)
    if isinstance(raw, Mapping):
        return Fact(
            str(raw.get("text") or ""),
            value=raw.get("value"),
            disclose=str(raw.get("disclose") or "on_ask"),
        )
    raise ConfigurationError(
        f"EndUser(knows=...) was given a {type(raw).__name__} where a fact was expected. Each "
        f"entry says what the person knows, when they say it, and what a scoring rule compares "
        f"against.\n"
        f"Pass Fact('the cost centre is CC-4471', value='CC-4471', disclose='on_ask'), or the "
        f"text alone for a fact nothing scores against."
    )


def answerers_in(end_user: Any) -> dict[str, EndUser]:
    """The answerers an example declares, keyed by name.

    A single answerer is keyed by the empty string, which is the name a consult tool that
    declares no ``reaches`` matches.
    """
    if end_user is None:
        return {}
    if isinstance(end_user, EndUser):
        return {"": end_user}
    if isinstance(end_user, str):
        return {"": EndUser(end_user)} if end_user.strip() else {}
    if isinstance(end_user, Mapping):
        found: dict[str, EndUser] = {}
        for name, one in end_user.items():
            decoded = decode_end_user(one)
            if isinstance(decoded, EndUser):
                found[str(name)] = decoded
        return found
    return {}


def described(end_user: Any, names: Iterable[str]) -> list[str]:
    """The names among ``names`` this example describes nobody for.

    A single description does not stand in for a named answerer. A run that asks two people and
    an example that describes one is the shape this exists to separate: both would be played
    from the same description, both consultations would record ``simulated``, and nothing in
    the results would say the two answerers were one.
    """
    answerers = answerers_in(end_user)
    return [name for name in names if name not in answerers]
