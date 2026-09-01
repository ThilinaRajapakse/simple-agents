"""The decisions a coding agent makes, and the kinds of decision that go to the builder.

Every elicitation question asks the builder about their own world. None asks the coding agent
to put its own decision in front of them, so a decision the library never thought to ask about
is unseen until it is in the code.

The kinds here are what generalises. Which catalogue a project depends on cannot be a shipped
question, because the next project has no catalogue; that it rests on **something** external,
and that the builder should have picked it, generalises to every project there is.

::

    from simple_agents.conformance import DECISION_KINDS, kind

    [k.name for k in DECISION_KINDS]        # the six
    kind("dependency").ask                  # what to put to the builder

`docs/procedure.md`, under "What to settle first, and what to keep doing", is how a
coding agent uses these, and FT-30 is the gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from datetime import datetime

from ..errors import ConfigurationError

__all__ = [
    "DecisionKind",
    "DECISION_KINDS",
    "Decision",
    "PRODUCING_KINDS",
    "STATUSES",
    "kind",
    "kind_names",
]

# `proposed` is the coding agent's choice, not yet seen by the builder. `agreed` is the builder
# saying yes to it. `changed` is the builder saying something else, and the entry then records
# what they said rather than what was proposed. `not_applicable` is a kind this project has
# nothing of, which is recorded rather than left absent so that nothing-to-decide and
# nobody-thought-about-it are different states.
STATUSES = ("proposed", "agreed", "changed", "not_applicable")


@dataclass(frozen=True, slots=True)
class DecisionKind:
    """One class of decision that belongs to the builder rather than to the coding agent.

    ``ask`` is the question in the words the builder reads. ``covers`` says what falls under
    the kind, for a coding agent deciding whether something it just did belongs here.
    """

    name: str
    ask: str
    covers: str
    example: str
    produces: str | None = None
    """What this kind's ``produces`` names, in the run record, or ``None`` for a kind that
    carries no ``produces``. A decision of a kind that names one records what it became, and
    FT-42 joins that against what the project's runs recorded."""


DECISION_KINDS: tuple[DecisionKind, ...] = (
    DecisionKind(
        name="dependency",
        ask=(
            "This project needs something outside itself for data. Here is what is available "
            "and what each one costs. Which should it rest on?"
        ),
        covers=(
            "Any external service, API, dataset or file the agent's answers rest on. The one "
            "the project would have to be rebuilt around if it went away."
        ),
        example=(
            "Open Library, Google Books or a web search for book descriptions. A source "
            "needing an API key is not ruled out by needing one: ask before dropping it."
        ),
        produces="The tools it became, by the name each is registered under.",
    ),
    DecisionKind(
        name="shape",
        ask=(
            "Here are the steps the agent will take, which of them decide things for "
            "themselves, and which model runs each. Is this the shape the builder pictured?"
        ),
        covers=(
            "The nodes, their order, which are agentic, and which model each uses. The "
            "structure an ablation would later vary."
        ),
        example=(
            "Ten nodes, one of them agentic, on a local 30B. The builder may want the hunt "
            "cheaper, or a step they expected that is not there."
        ),
        produces="The nodes it became, by `node_id`.",
    ),
    DecisionKind(
        name="constant",
        ask=(
            "This number changes what the agent does and was guessed. Here is what raising "
            "and lowering it costs. What should it be?"
        ),
        covers=(
            "A literal written into the code that changes behaviour rather than performance: "
            "how many items are looked at, how many are returned, a threshold, a target share."
        ),
        example=(
            "How many of a 346-book library to read before judging taste. Twelve was chosen "
            "alone and turned out to be defending nothing."
        ),
        produces="The module-level numbers it settled, by the name each is written under.",
    ),
    DecisionKind(
        name="prompt_rule",
        ask=("The prompts tell the model these rules. Are they the builder's, and are they right?"),
        covers=(
            "Any instruction in a prompt that constrains the answer. A rule the coding agent "
            "invented while testing is the one to watch for, because it reads as the "
            "builder's own once it is in the file."
        ),
        example=(
            "'Not another ten-book series' was a coding agent's test prompt, written into the "
            "code as a builder constraint and then quoted back to them as a requirement."
        ),
        produces="The nodes whose prompts carry the rule, by `node_id`.",
    ),
    DecisionKind(
        name="presentation",
        ask=(
            "Here is how a result reaches the builder, and who else sees it. Is that the "
            "right shape?"
        ),
        covers=(
            "What the output looks like to a person: the fields, the ordering, what is shown "
            "and what is kept back, and whether it lands somewhere other than a terminal."
        ),
        example=(
            "A page rather than a printout changed the output schema, because a record per "
            "book with its own argument is what a page can render."
        ),
    ),
    DecisionKind(
        name="measurement",
        ask=(
            "Here is what the evaluation scores, and what an agent that did nothing would "
            "score on it. Is that worth measuring?"
        ),
        covers=(
            "What counts as correct, what the example set is, and what the number would read "
            "if the agent were replaced by chance."
        ),
        example=(
            "Naming one held-out author out of a million-work universe scores about 0.5% by "
            "luck, so a measured 0% separates a broken agent from an excellent one not at all."
        ),
    ),
)

_BY_NAME = {entry.name: entry for entry in DECISION_KINDS}


@dataclass(frozen=True, slots=True)
class Decision:
    """One decision the coding agent made, and what the builder said about it.

    ``chose`` is what the coding agent went with, ``considered`` the alternatives it weighed,
    and ``because`` why. ``status`` is one of :data:`STATUSES`; a ``changed`` decision records
    what the builder wanted rather than what was proposed.

    ``rests_on`` names the brief entries the decision was derived from, written as ``from`` in
    the brief and read back here::

        decision.rests_on          # ('not_building', 'one_real_input')

    ``produces`` names what the decision became in the code, read back the same way::

        decision.produces          # ('uncommon_books', 'explore_tag')

    Four kinds carry it and :attr:`DecisionKind.produces` says what each one names. FT-42 joins
    it against what the project's runs recorded, and the report prints the complement: what the
    runs hold that no decision names.

    The report prints the answers about what the builder wants that **no** decision names, so
    an answer nobody read is a line in the report rather than something to notice
    (`docs/conformance.md` §4.4).

    ``stage`` names which of the six this was decided at and ``recorded_at`` when, off the
    coding agent's system clock. ``recorded_at`` is required::

        [decisions.pool_size]
        kind = "constant"
        status = "agreed"
        stage = "build"
        recorded_at = "2026-08-27T09:14:02Z"
    """

    name: str
    kind: str
    status: str
    chose: str | None = None
    considered: tuple[str, ...] = ()
    because: str | None = None
    stage: str | None = None
    rests_on: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    recorded_at: str | None = None

    @property
    def seen_by_the_builder(self) -> bool:
        """Whether this is settled, either by agreement or by the builder overriding it."""
        return self.status in ("agreed", "changed", "not_applicable")


def kind(name: str) -> DecisionKind:
    """The decision kind recorded under ``name``.

    Raises :class:`~simple_agents.errors.ConfigurationError` naming the six where there is no
    such kind.
    """
    try:
        return _BY_NAME[name]
    except KeyError:
        raise ConfigurationError(
            f"There is no decision kind {name!r}. The six are {', '.join(_BY_NAME)}.\n"
            f"A decision that fits none of them is one the library has no opinion about, and "
            f"belongs in the brief as an ordinary entry rather than here."
        ) from None


def kind_names() -> tuple[str, ...]:
    """The six kinds, in the order a project meets them."""
    return tuple(_BY_NAME)


AN_EXAMPLE_STAMP = "2026-08-27T09:14:02Z"


def recorded_at(value: Any, *, required: bool, where: str, fix: str) -> str | None:
    """When what a brief entry or a decision now says was written down.

    Read off the coding agent's system clock and taken as given. What is checked is that it is
    a timestamp carrying a zone: two written on different machines cannot be put in order
    otherwise, which is the whole of what the field is for.

    ``where`` names the thing in the message and ``fix`` is the line to write.
    """
    text = str(value or "").strip()
    if not text:
        if not required:
            return None
        raise ConfigurationError(
            f"{where} records no recorded_at, so nothing says when it was written down and a "
            f"question of whether the code has moved since has nothing to anchor against.\n"
            f"{fix}"
        )
    try:
        stamped = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ConfigurationError(
            f"{where} records recorded_at = {text!r}, which is not a timestamp. Write what the "
            f"system clock says, in ISO 8601: {AN_EXAMPLE_STAMP}."
        ) from None
    if stamped.tzinfo is None:
        raise ConfigurationError(
            f"{where} records recorded_at = {text!r}, which names no time zone, so it cannot "
            f"be put in order against one written elsewhere. Write it in UTC: "
            f"{AN_EXAMPLE_STAMP}."
        )
    return text


def _kind_of(name: str, value: dict[str, Any], path: Any) -> str:
    """Which of the six kinds a decision declares, or a refusal naming all of them."""
    entry_kind = str(value.get("kind", "")).strip()
    if entry_kind not in _BY_NAME:
        raise ConfigurationError(
            f"{path} records decision {name!r} with kind "
            f"{entry_kind or 'none'!r}, and the six are {', '.join(_BY_NAME)}.\n"
            f'Write kind = "dependency" for what the project rests on, "shape" for the '
            f'nodes and models, "constant" for a number in the code, "prompt_rule" for a '
            f'rule in a prompt, "presentation" for how a result is shown, or "measurement" '
            f"for what the evaluation scores."
        )
    return entry_kind


def _status_of(name: str, value: dict[str, Any], path: Any) -> str:
    """What the builder has said about a decision, or a refusal naming the four."""
    status = str(value.get("status", "")).strip()
    if status not in STATUSES:
        raise ConfigurationError(
            f"{path} records decision {name!r} with status {status or 'none'!r}, and the "
            f"four are {', '.join(STATUSES)}.\n"
            f'Write status = "proposed" for a decision the builder has not seen, '
            f'"agreed" once they have, "changed" where they wanted something else, and '
            f'"not_applicable" for a kind this project has nothing of.'
        )
    return status


def decisions_from(raw: Any, path: Any) -> tuple[Decision, ...]:
    """Parse the ``[decisions]`` table of a brief.

    Refuses an entry with no kind, an unknown kind, or a status outside :data:`STATUSES`,
    because a gate reads all three and an entry it cannot read is one it cannot hold anything
    to.
    """
    out: list[Decision] = []
    for name, value in (raw or {}).items():
        if not isinstance(value, dict):
            raise ConfigurationError(
                f"{path} records decision {name!r} as {type(value).__name__}, and a decision "
                f"is a table: [decisions.{name}] with kind, status, chose and considered."
            )
        entry_kind = _kind_of(name, value, path)
        status = _status_of(name, value, path)
        considered = value.get("considered") or ()
        rests_on = _a_list_of_names(
            value.get("from"),
            "from",
            name,
            path,
            "It names the answers this decision was derived from.",
        )
        produces = _produces_from(value.get("produces"), name, entry_kind, path)
        out.append(
            Decision(
                name=str(name),
                kind=entry_kind,
                status=status,
                chose=value.get("chose"),
                considered=tuple(str(item) for item in considered),
                because=value.get("because"),
                stage=value.get("stage"),
                rests_on=rests_on,
                produces=produces,
                recorded_at=recorded_at(
                    value.get("recorded_at"),
                    required=True,
                    where=f"{path} records decision {name!r}, which",
                    fix=f'Add recorded_at = "{AN_EXAMPLE_STAMP}" under [decisions.{name}].',
                ),
            )
        )
    return tuple(out)


# The kinds that carry `produces`, in the order a project meets them. `presentation` and
# `measurement` are outside it: what a result looks like to a person and what an evaluation
# scores leave nothing in a run record to join against.
PRODUCING_KINDS = tuple(entry.name for entry in DECISION_KINDS if entry.produces)


def _a_list_of_names(raw: Any, field: str, name: str, path: Any, what: str) -> tuple[str, ...]:
    """One decision's ``from`` or ``produces``, refusing anything that is not a list of names.

    A single name written without its brackets is the common slip and is what the message
    corrects. Anything else says what the field takes, since a value nothing can read as names
    would otherwise reach a check as a name per character or raise where it is used.
    """
    if raw is None:
        return ()
    if isinstance(raw, str):
        raise ConfigurationError(
            f"{path} records decision {name!r} with {field} = {raw!r}, and `{field}` is a "
            f'list of names: {field} = ["{raw}"]. {what}'
        )
    if not isinstance(raw, (list, tuple)):
        raise ConfigurationError(
            f"{path} records decision {name!r} with {field} as {type(raw).__name__}, and "
            f'`{field}` is a list of names: {field} = ["first", "second"]. {what}'
        )
    return tuple(str(item) for item in raw)


def _produces_from(raw: Any, name: str, entry_kind: str, path: Any) -> tuple[str, ...]:
    """Parse one decision's ``produces``, refusing the wrong kind as well as the wrong shape."""
    named = _a_list_of_names(
        raw, "produces", name, path, "It names what this decision became in the code."
    )
    # The key being there is what is refused, empty or not: a kind that leaves nothing in a
    # run record has no answer to what it became, and `produces = []` reads as one.
    if raw is not None and entry_kind not in PRODUCING_KINDS:
        raise ConfigurationError(
            f"{path} records decision {name!r} with kind {entry_kind!r} and a `produces`, and "
            f"the kinds that carry one are {', '.join(PRODUCING_KINDS)}.\n"
            f"A {entry_kind} decision leaves nothing in a run record to join a name against: "
            f"{_BY_NAME[entry_kind].covers}\n"
            f"Remove `produces`, or record this under the kind whose artifact it names."
        )
    return named
