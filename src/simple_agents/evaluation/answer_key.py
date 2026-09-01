"""What the project holds about the right answer to one example.

``Example.expected`` takes a plain value where the answer is one thing. Where it is not, it
takes one of the types here, and the type says what the answer key **is**. It never says how
to compare two values: that stays in ``matches``, which the project writes.

Each of these encodes as a tagged object, the way ``Unknown`` does, so an answer key is
written into a JSONL example file and read back from it, and ``ExampleSet.content_hash``
covers it. Widening an admissible set is therefore a change a comparison between two
evaluations declines to attribute to the agent.

``docs/evaluation.md`` §1.6 is the schema of record for the encoded form.
"""

from __future__ import annotations

from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict

from ..errors import ConfigurationError
from ..schema import decode_answer

__all__ = [
    "AnswerKey",
    "AnyOf",
    "Contains",
    "WithinTolerance",
    "Criterion",
    "Criteria",
    "decode_answer_key",
]


class AnswerKey(BaseModel):
    """What the project holds about the right answer, where it is not one value.

    The four subclasses cover a set of admissible answers (:class:`AnyOf`), an answer that is
    itself a collection (:class:`Contains`), a quantity right when close enough
    (:class:`WithinTolerance`), and a list of conditions each judged yes or no
    (:class:`Criteria`).

    ``isinstance(example.expected, AnswerKey)`` distinguishes a key from a plain value.
    """

    model_config = ConfigDict(frozen=True)


class AnyOf(AnswerKey):
    """Several admissible answers, any one of which is right.

    The answer is one thing and the key is the set it has to come from::

        Example(id="q1", inputs={"question": "Which retailer ships from Leeds?"},
                expected=AnyOf(["Kirkwall", "Kirkwall Retail Ltd"]), split="dev")

    ``matches`` is called once per admissible value and the answer is right where any call
    returns true, so the project writes the comparison between two single values and nothing
    about the set.

    The answer is right or it is not: there is no partly-right state here, because one value
    either came from the set or did not. A key whose parts can be met separately is
    :class:`Contains` or :class:`Criteria`.
    """

    type: Literal["any_of"] = "any_of"
    values: list[Any]

    def __init__(self, values: Iterable[Any] | None = None, **data: Any) -> None:
        if values is not None:
            data["values"] = list(values)
        super().__init__(**data)
        if not self.values:
            raise ConfigurationError(
                "AnyOf was given no values, so no answer could ever be right and every "
                "rollout of this example would report the agent asserting a wrong value.\n"
                "Pass the admissible answers: AnyOf(['Kirkwall', 'Kirkwall Retail Ltd']). "
                "Where the correct answer is that the information is not there, pass "
                "expected=Unknown(reason='...') instead."
            )


class Contains(AnswerKey):
    """The answer is a collection, and each of these has to appear in it.

    The key is one value or several, and the answer is the collection they have to be found
    in::

        Example(id="q4", inputs={"question": "Find me something to read"},
                expected=Contains("The Left Hand of Darkness"), split="held_out")

        Example(id="q9", inputs={"question": "Which depots opened in 1974?"},
                expected=Contains(["Leeds", "Kirkwall"]), split="held_out")

    ``matches`` is called once per value, given the whole answer and that one value, so it
    answers "does this answer contain this", and the project decides what containment means.

    With more than one value the answer can be partly right: an answer holding two of three
    is ``partially_correct`` and carries a grade of 0.67.
    """

    type: Literal["contains"] = "contains"
    values: list[Any]

    def __init__(self, values: Any = None, **data: Any) -> None:
        if values is not None:
            data["values"] = list(values) if isinstance(values, (list, tuple, set)) else [values]
        super().__init__(**data)
        if not self.values:
            raise ConfigurationError(
                "Contains was given no values, so nothing has to appear in the answer and "
                "every answer would be right.\n"
                "Pass what the answer has to hold: Contains('The Left Hand of Darkness'), or "
                "Contains(['Leeds', 'Kirkwall'])."
            )


class WithinTolerance(AnswerKey):
    """A quantity, right where it is close enough.

    ``absolute`` and ``relative`` are both bounds on the difference, and either or both may be
    given. The answer is right where it is inside every bound declared::

        Example(id="s7", inputs={"garment": "..."},
                expected=WithinTolerance(52.0, relative=0.02), split="dev")

        Example(id="s8", inputs={"garment": "..."},
                expected=WithinTolerance(52.0, absolute=1.5), split="dev")

    ``matches`` is not called. The tolerance is the whole of what "close enough" means here,
    and it is declared in the key so that it travels into the example file and into
    ``content_hash``. A tolerance written into ``matches`` instead is not in the example file,
    so the set does not say what close enough means. Where it is a constant that function reads
    rather than a value it closes over, ``source_version`` does not see it either, and widening
    it from 2% to 5% moves every rate with nothing recording that the rule changed.

    A quantity the agent wrote as text is read as the number it spells, because an output
    schema types a field ``str`` more often than it types it ``float`` and the answer is the
    same quantity either way. Text that does not spell a number is wrong rather than an error:
    a model asked for a quantity that returned prose asserted something that is not close to
    anything. Where the answer needs stripping first, such as ``"5200 sqm"``, do it in
    ``EvalSuite(answer=...)``, which is what reads the answer off the output.
    """

    type: Literal["within_tolerance"] = "within_tolerance"
    value: float
    absolute: float | None = None
    relative: float | None = None

    def __init__(self, value: Any = None, **data: Any) -> None:
        if value is not None:
            data["value"] = value
        super().__init__(**data)
        if self.absolute is None and self.relative is None:
            raise ConfigurationError(
                f"WithinTolerance({self.value}) declares no tolerance, and how "
                f"close an answer has to be and only an exact match would be right.\n"
                f"Pass one or both: WithinTolerance({self.value}, relative=0.02) for 2%, "
                f"WithinTolerance({self.value}, absolute=1.5) for a fixed margin. A quantity "
                f"compared exactly is a plain value: expected={self.value}."
            )
        for name, bound in (("absolute", self.absolute), ("relative", self.relative)):
            if bound is not None and bound < 0:
                raise ConfigurationError(
                    f"WithinTolerance was given {name}={bound}, and a tolerance is a distance, "
                    f"so a negative one admits nothing and every answer would be wrong.\n"
                    f"Pass {name}={abs(bound)}."
                )

    def admits(self, answer: Any) -> bool:
        """Whether ``answer`` is inside every bound this key declares.

        ``52.5``, ``"52.5"`` and ``" 52.5 "`` are the same quantity. ``True`` is not a number
        here, and neither is text that does not spell one.
        """
        if isinstance(answer, bool):
            return False
        if isinstance(answer, str):
            try:
                answer = float(answer.strip())
            except ValueError:
                return False
        elif not isinstance(answer, (int, float)):
            return False
        difference = abs(float(answer) - self.value)
        if self.absolute is not None and difference > self.absolute:
            return False
        if self.relative is not None and difference > abs(self.value) * self.relative:
            return False
        return True


class Criterion(BaseModel):
    """One condition a correct answer has to meet, judged yes or no.

    ``id`` names the check that decides it, which the project registers on the suite. The
    criterion is data and the check is code, so the key stays storable and the check is
    versioned the way ``matches`` is::

        Criterion(id="not_already_read", text="a book the reader has not already read",
                  required=True)
        Criterion(id="under_400_pages", text="under 400 pages", weight=1)

        EvalSuite(pipeline, examples, answer="answer", matches=exact, criteria={
            "not_already_read": lambda s: s.answer.title not in s.example.metadata["read"],
            "under_400_pages": lambda s: s.answer.pages < 400,
        })

    One check serves every example naming it, and is given the whole
    :class:`~simple_agents.evaluation.Scoring`, so a condition that depends on the end user
    reads it off ``s.example``.

    A check returns ``True``, ``False``, or ``Unknown`` where the answer asserted nothing about
    this condition. Silence is reported apart from a wrong value, so a field the agent left
    empty is not counted as a field it got wrong::

        def po_number(s):
            if isinstance(s.answer.po_number, Unknown):
                return Unknown()
            return s.answer.po_number == s.example.metadata["po"]

    ``expects_absence`` declares that the right answer here is that the value is not there, as
    ``expected=Unknown(...)`` does for a whole answer, and silence meets it. The example whose
    document states no PO number declares it and the one whose document states a PO number does
    not, so the check above serves both, and FT-04 reads it::

        Criterion(id="po_number", text="the PO number, or that none is stated",
                  expects_absence=True)

    ``weight`` is how much this condition counts toward the grade, relative to the others in
    the same list. ``required`` makes an unmet condition wrong rather than partly right.
    ``text`` is what a report prints and what the per-criterion figure is defined as.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    text: str
    weight: float = 1.0
    required: bool = False
    expects_absence: bool = False

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not str(self.id).strip():
            raise ConfigurationError(
                "A Criterion was given an empty id. The id is what resolves the check that "
                "decides it and what the per-criterion figure is keyed on.\n"
                "Pass Criterion(id='under_400_pages', text='under 400 pages')."
            )
        if not str(self.text).strip():
            raise ConfigurationError(
                f"Criterion {self.id!r} was given no text. The text is what a report prints "
                f"and what the figure for this criterion is defined as, so a reader of the "
                f"results has nothing else saying what was measured.\n"
                f"Pass Criterion(id={self.id!r}, text='<the condition, in words>')."
            )
        if self.weight <= 0:
            raise ConfigurationError(
                f"Criterion {self.id!r} was given weight={self.weight}. A weight is how much "
                f"this condition counts toward the grade, and one at or below zero either "
                f"removes the condition or lets meeting it lower the grade.\n"
                f"Pass a positive weight, or drop the criterion. A condition the answer must "
                f"NOT meet is written as a criterion whose check returns True when the thing "
                f"is absent."
            )


class Criteria(AnswerKey):
    """A list of conditions, each judged yes or no, and the grade over them.

    The answer key for a task with no enumerable right answer. Nothing lists the correct
    answers; the conditions recognise one::

        Example(id="q4", inputs={"question": "Find me something to read"},
                split="held_out", expected=Criteria([
                    Criterion(id="not_read", text="a book the reader has not read",
                              required=True),
                    Criterion(id="subject", text="shares a subject with the to-read shelf",
                              weight=2),
                    Criterion(id="length", text="under 400 pages"),
                ]))

    The grade is the weight met over the weight declared, so meeting the subject and the
    length above grades 0.75. An answer meeting some conditions and not all is
    ``partially_correct``, which is its own outcome and its own rate.

    An unmet ``required`` condition makes the answer ``false_confidence`` whatever the grade,
    and the grade is recorded beside it.
    """

    type: Literal["criteria"] = "criteria"
    criteria: list[Criterion]

    def __init__(self, criteria: Iterable[Criterion] | None = None, **data: Any) -> None:
        if criteria is not None:
            data["criteria"] = list(criteria)
        super().__init__(**data)
        if not self.criteria:
            raise ConfigurationError(
                "Criteria was given no conditions, so nothing decides whether an answer is "
                "right and every answer would be graded over an empty list.\n"
                "Pass the conditions: Criteria([Criterion(id='under_400_pages', "
                "text='under 400 pages')])."
            )
        ids = [c.id for c in self.criteria]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        if repeated:
            raise ConfigurationError(
                f"This answer key names {', '.join(repeated)} more than once. One check "
                f"decides each id, so a repeat counts that check twice in the grade and "
                f"reports one figure for both.\n"
                f"Give each condition a distinct id, or drop the repeat and raise its weight."
            )

    @property
    def ids(self) -> tuple[str, ...]:
        """Every criterion id in this key, in the order declared."""
        return tuple(c.id for c in self.criteria)

    @property
    def absent_parts(self) -> tuple[str, ...]:
        """The criteria whose right answer is that the value is not there."""
        return tuple(c.id for c in self.criteria if c.expects_absence)


_TAGS: dict[str, type[AnswerKey]] = {
    "any_of": AnyOf,
    "contains": Contains,
    "within_tolerance": WithinTolerance,
    "criteria": Criteria,
}


def decode_answer_key(raw: Any) -> Any:
    """An answer key as a file stores it, back as the object.

    Read where a label is expected and nowhere else, so a tagged object arriving from a model
    as an answer stays the data it was::

        decode_answer_key({"type": "any_of", "values": ["Kirkwall", "Kirkwall Retail Ltd"]})
        # AnyOf(values=['Kirkwall', 'Kirkwall Retail Ltd'])

    Anything that is not one of the four tags goes through ``decode_answer``, so a plain value
    and an ``Unknown`` come back as they always did.
    """
    if isinstance(raw, dict):
        key = _TAGS.get(str(raw.get("type", "")))
        if key is not None:
            fields = {name: decode_answer(value) for name, value in raw.items() if name != "type"}
            try:
                if key is Criteria:
                    fields["criteria"] = [
                        Criterion(**entry) if isinstance(entry, dict) else entry
                        for entry in fields.get("criteria") or []
                    ]
                return key(**fields)
            except ConfigurationError:
                raise
            except Exception as exc:
                raise ConfigurationError(
                    f"An example carries an answer key tagged {raw.get('type')!r} that could "
                    f"not be read: {exc}\n"
                    f"The encoded forms are in docs/evaluation.md §1.6. An answer key written "
                    f"by hand is easier to get right by building it in code and writing the "
                    f"set out with ExampleSet.to_jsonl()."
                ) from exc
    return decode_answer(raw)
