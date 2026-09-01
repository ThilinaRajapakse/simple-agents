"""What one rollout produced, and everything known about the example it ran on.

One object reaches every scoring seam: ``matches``, ``node_matches``, a criterion's check, and
a ``ProjectMetric``'s ``score``. A rule that needs the question, what the end user knows, or
what the run did reads it off the same place, and a rule that needs only the answer ignores the
rest.

This module also holds the fold: an answer key says how many comparisons there are and how
their results combine, and ``matches`` says whether one pair matches. The two are separate on
purpose, so a project writes the comparison between two values once and the shape of the key
decides what is done with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Callable, Mapping

from ..errors import ConfigurationError
from ..schema import Unknown
from .answer_key import AnyOf, Contains, Criteria, WithinTolerance
from .examples import Example
from .judgements import Judged, JudgementMissing

if TYPE_CHECKING:  # pragma: no cover
    from .outcomes import Outcome

__all__ = ["Scoring", "Verdict", "verdict_of"]


@dataclass(frozen=True, slots=True)
class Scoring:
    """One answer, the key it is scored against, and where it came from.

    ``answer`` is what the rollout produced, read off the pipeline's output by
    ``EvalSuite(answer=...)``. ``expected`` is the value **this call** is about: with a plain
    label it is the label, with an answer key that has parts it is one of them, and inside a
    criterion's check it is that criterion's text, since a condition has no value to compare
    against. ``example.expected`` is always the whole key::

        matches=lambda s: s.answer.strip().lower() == s.expected.strip().lower()

    ``example`` is what the rollout ran on, so a rule that depends on the question, on what
    the end user knows, or on anything the project put in ``metadata`` reads it here::

        matches=lambda s: s.answer.cost_centre == s.example.metadata["cost_centre"]

    ``trajectory`` is the path to what the run recorded, for a rule about what the agent did
    rather than what it answered. Reading it opens a file per rollout::

        criteria={"asked_before_acting": lambda s: _consulted_first(s.trajectory)}

    ``outcome`` is ``None`` inside ``matches``, ``node_matches`` and a criterion's check,
    because those are what decide a verdict. It carries the outcome inside a ``ProjectMetric``,
    which is scored after the rollout has been sorted, and ``verdict`` beside it, which is how
    a figure reads what each condition of a decomposed key decided::

        met = lambda s, axis: [v for k, v in s.verdict.parts.items() if k.startswith(axis)]
        accuracy = ProjectMetric(name="accuracy_axis", definition="...",
                                 score=lambda s: _share(met(s, "accuracy.")))

    ``node_id`` names the node being scored where the figure is per node, and is ``None`` end
    to end. ``criterion_id`` names the condition being decided inside a criterion's check, and
    is ``None`` everywhere else. One function registered under two ids tells them apart::

        criteria={"vendor": field_matches, "total": field_matches}
        # inside field_matches, s.criterion_id is 'vendor' or 'total'

    :meth:`judgement` reads a decision a model or a person made about this rollout, for a rule
    code cannot write.
    """

    answer: Any
    expected: Any
    example: Example
    rollout: int
    seed: int
    run_id: str | None = None
    trajectory: str | None = None
    outcome: "Outcome | None" = None
    verdict: "Verdict | None" = None
    node_id: str | None = None
    criterion_id: str | None = None
    judgements: Any = None

    @property
    def expects_absence(self) -> bool:
        """Whether the correct answer to this example is that the information is not there."""
        return self.example.expects_absence

    @property
    def answered_absence(self) -> bool:
        """Whether the agent reported that the information is not there."""
        return isinstance(self.answer, Unknown)

    def about(self, expected: Any, *, criterion_id: str | None = None) -> Scoring:
        """The same scoring, about one part of the answer key."""
        return replace(self, expected=expected, criterion_id=criterion_id)

    def judgement(self, question: str, *, over: Any) -> Any:
        """What a model or a person decided about ``over``, when asked ``question``.

        For a rule code cannot write: whether a reply promised a refund, whether a summary is
        faithful to what it summarised, whether the passages a step retrieved were relevant::

            node_matches={"retrieve": lambda s: s.judgement(
                "are these passages relevant to the question?", over=s.answer)}

        The judgement is read out of ``evals/judgements.jsonl``. **Nothing here calls a model**:
        the decision was made earlier, by a judging pass or by a person, and this reads it.
        A condition on the answer key needs none of this and registers
        :class:`~simple_agents.evaluation.Judged` instead.

        ``over`` is what was judged, and the judgement is filed under a digest of it, so the
        same material judged again is not judged twice and material that changed has no
        judgement rather than an old one.

        An answer nothing has judged yet leaves this rule undecided for that rollout and is
        collected, so one pass names every judgement outstanding. ``EvalSuite.run`` refuses
        after the rollouts rather than reporting a number, and ``suite.judge(...)`` is what
        answers them.
        """
        from .judgements import JudgementRequest, judgement_key

        if self.judgements is None:
            raise ConfigurationError(
                f"A scoring rule asked for a judgement of {question!r} and this Scoring "
                f"carries no judgements to read, so nothing could answer it.\n"
                f"Judgements are read by an evaluation: suite.run(...), suite.rescore(...) "
                f"and suite.judge(...) all supply them. A Scoring built by hand, such as in a "
                f"test, has none unless one is passed: Scoring(..., judgements=Judgements())."
            )
        return self.judgements.resolve(
            JudgementRequest(
                key=judgement_key(self.example.id, question, over),
                question=question,
                material=over,
                example_id=self.example.id,
                rollout=self.rollout,
                criterion_id=self.criterion_id,
                node_id=self.node_id,
            )
        )


@dataclass(frozen=True, slots=True)
class Verdict:
    """What comparing one answer with one answer key produced.

    ``grade`` runs from 0.0 to 1.0. It is 1.0 or 0.0 for a key with nothing to meet
    separately, and the share of the weight met for one that has parts.

    ``met`` and ``total`` are counts rather than weights, so a report can print "met 2 of 3"
    beside a grade that the weights moved. ``parts`` holds each criterion's verdict, keyed by
    id, and is empty for every key but :class:`~simple_agents.evaluation.Criteria`. A part is
    ``True`` where the condition was met, ``False`` where the answer asserted something and it
    was wrong, and ``None`` where the answer asserted nothing about that condition::

        verdict.parts       # {'vendor': True, 'total': False, 'po_number': None}
        verdict.wrong       # ('total',)
        verdict.absent      # ('po_number',)

    An absent part counts toward neither the grade nor ``met``, and its weight stays in the
    denominator, so an answer that leaves a condition alone does not raise its own grade.

    ``unmet_required`` names the criteria declared ``required`` that the answer did not meet,
    by either route. An answer with any of them is not partly right, whatever the grade.

    ``asserted`` is whether the answer put any value forward, and it decides which rollouts a
    rate counting assertions is over. A record naming a vendor and leaving a required PO number
    alone asserted something. A condition declaring ``expects_absence`` is met by silence, so a
    record silent throughout can meet part of its key and still be ``False`` here::

        verdict.parts       # {'vendor': True, 'po_number': None}
        verdict.asserted    # True
    """

    grade: float
    met: int
    total: int
    parts: dict[str, bool | None] = field(default_factory=dict)
    unmet_required: tuple[str, ...] = ()
    asserted: bool = True

    @property
    def complete(self) -> bool:
        """Whether the answer met the whole key."""
        return not self.unmet_required and self.grade >= 1.0

    @property
    def empty(self) -> bool:
        """Whether the answer met none of the key."""
        return self.grade <= 0.0

    @property
    def wrong(self) -> tuple[str, ...]:
        """The criteria the answer asserted something about and got wrong."""
        return tuple(name for name, part in self.parts.items() if part is False)

    @property
    def absent(self) -> tuple[str, ...]:
        """The criteria the answer asserted nothing about."""
        return tuple(name for name, part in self.parts.items() if part is None)

    @property
    def asserted_wrong(self) -> bool:
        """Whether any part the answer did assert was wrong.

        This is what separates a confident wrong answer from one that left a condition alone.
        A key with no parts is one comparison, so anything short of meeting it was asserted
        and wrong.
        """
        if not self.parts:
            return self.grade < 1.0
        return any(part is False for part in self.parts.values())

    def to_record(self) -> dict[str, Any]:
        """What a results file stores about one rollout's verdict."""
        return {
            "grade": self.grade,
            "met": self.met,
            "total": self.total,
            "parts": dict(self.parts),
            "unmet_required": list(self.unmet_required),
            "asserted": self.asserted,
        }

    @classmethod
    def from_record(cls, raw: Mapping[str, Any]) -> Verdict:
        """Rebuild one verdict from a results file."""
        return cls(
            grade=float(raw.get("grade", 0.0)),
            met=int(raw.get("met", 0)),
            total=int(raw.get("total", 0)),
            parts={
                str(k): (None if v is None else bool(v))
                for k, v in (raw.get("parts") or {}).items()
            },
            unmet_required=tuple(str(i) for i in (raw.get("unmet_required") or ())),
            asserted=bool(raw.get("asserted", True)),
        )


def verdict_of(
    scoring: Scoring,
    *,
    matches: Callable[[Scoring], bool],
    criteria: Mapping[str, Callable[[Scoring], Any]] | None = None,
) -> Verdict:
    """Compare one asserted answer with its answer key.

    Called only where the answer as a whole is an asserted value, so no branch here handles an
    answer that reported absence end to end. A criterion's check may still report that this
    answer asserted nothing about its own condition.

    The key decides how many comparisons there are. A plain value is one call to ``matches``.
    :class:`~simple_agents.evaluation.AnyOf` is one call per admissible value, right where any
    of them matches. :class:`~simple_agents.evaluation.Contains` is one call per value the
    answer has to hold, and grades on how many were found.
    :class:`~simple_agents.evaluation.WithinTolerance` calls nothing and reads the bounds off
    the key. :class:`~simple_agents.evaluation.Criteria` calls each criterion's registered
    check.
    """
    key = scoring.expected

    if isinstance(key, Criteria):
        return _criteria_verdict(scoring, key, criteria or {})
    if isinstance(key, WithinTolerance):
        return _binary(key.admits(scoring.answer))
    if isinstance(key, AnyOf):
        found = any(_call(matches, scoring.about(value)) for value in key.values)
        return _binary(found)
    if isinstance(key, Contains):
        held = [bool(_call(matches, scoring.about(value))) for value in key.values]
        return _shared(held)
    return _binary(bool(_call(matches, scoring.about(key))))


def _binary(right: bool) -> Verdict:
    return Verdict(grade=1.0 if right else 0.0, met=1 if right else 0, total=1)


def _shared(held: list[bool]) -> Verdict:
    met = sum(1 for one in held if one)
    return Verdict(grade=met / len(held), met=met, total=len(held))


def _criteria_verdict(
    scoring: Scoring,
    key: Criteria,
    checks: Mapping[str, Callable[[Scoring], Any]],
) -> Verdict:
    parts: dict[str, bool | None] = {}
    unmet_required: list[str] = []
    asserted = False
    weight_met = 0.0
    weight_declared = 0.0
    for criterion in key.criteria:
        check = checks.get(criterion.id)
        if isinstance(check, Judged):
            # The condition's text is the question and the answer is the material, so a
            # judged condition declares nothing a coded one does not.
            check = _reading_a_judgement(criterion.text)
        if check is None:
            raise ConfigurationError(
                f"Example {scoring.example.id!r} names criterion {criterion.id!r} and the "
                f"suite registers no check for it, so nothing decides whether the answer met "
                f"it. Every rollout would fail on this before anything is scored.\n"
                f"Register it: EvalSuite(..., criteria={{{criterion.id!r}: "
                f"lambda s: ...}}). It is given the Scoring, so the answer is s.answer and "
                f"the example is s.example."
            )
        met = _call(
            check,
            scoring.about(criterion.text, criterion_id=criterion.id),
            what=f"criterion {criterion.id!r}",
            may_report_absence=True,
        )
        # Read before the fold below, which turns silence on an absent condition into a met
        # one and so cannot be asked afterwards whether anything was put forward.
        asserted = asserted or met is not None
        if criterion.expects_absence:
            # Absence on both sides, one level down. The right answer here is that the value is
            # not there, so reporting it is the only way to meet the condition and any asserted
            # value is wrong whatever the check made of it. `classify` decides the same two
            # cells for a whole answer without calling `matches` at all.
            met = met is None
        parts[criterion.id] = met
        weight_declared += criterion.weight
        if met:
            weight_met += criterion.weight
        elif criterion.required:
            unmet_required.append(criterion.id)
    return Verdict(
        grade=weight_met / weight_declared if weight_declared else 0.0,
        met=sum(1 for one in parts.values() if one),
        total=len(parts),
        parts=parts,
        unmet_required=tuple(unmet_required),
        asserted=asserted,
    )


def _reading_a_judgement(question: str) -> Callable[[Scoring], Any]:
    """The check behind a ``Judged()`` condition: read the judgement, decide nothing."""

    def read(scoring: Scoring) -> Any:
        return scoring.judgement(question, over=scoring.answer)

    return read


def _call(
    decide: Callable[[Scoring], Any],
    scoring: Scoring,
    *,
    what: str = "matches",
    may_report_absence: bool = False,
) -> bool | None:
    """Call one scoring rule, and refuse a return that is not a verdict.

    A criterion's check may also return ``Unknown``, meaning the answer asserted nothing about
    that condition, and ``None`` is what that becomes in the verdict.

    A rule that asked for a judgement nothing has made leaves this condition undecided and the
    request collected, so one pass over the rollouts names every judgement outstanding rather
    than stopping at the first.
    """
    try:
        value = decide(scoring)
    except JudgementMissing:
        return None
    except Exception as exc:
        raise ConfigurationError(
            f"{what} raised {type(exc).__name__} scoring rollout {scoring.rollout} of example "
            f"{scoring.example.id!r}: {exc}\n"
            f"It is called once per comparison for every rollout, so it has to return a "
            f"verdict for all of them. It takes one argument: the answer is s.answer, the "
            f"value being compared against is s.expected, and the example is s.example."
        ) from exc
    if may_report_absence and isinstance(value, Unknown):
        return None
    if not isinstance(value, bool):
        raise ConfigurationError(
            f"{what} returned {value!r} scoring rollout {scoring.rollout} of example "
            f"{scoring.example.id!r}. A comparison is yes or no, and the outcome of the "
            f"rollout is decided by it.\n"
            + (
                "Return a bool, or Unknown() where the answer asserted nothing about this "
                "condition, which is scored as unmet and reported apart from a wrong value.\n"
                if may_report_absence
                else "Return a bool.\n"
            )
            + "A figure that is a number belongs in a ProjectMetric, and an "
            "answer that can be partly right is an answer key with parts: Criteria([...]) "
            "for a list of conditions, Contains([...]) for values the answer has to hold."
        )
    return value


def criteria_in(examples: Any) -> dict[str, str]:
    """Every criterion an example's ``expected`` names, mapped to its text, in declaration order.

    Two examples naming one id share its check and its figure, and the text is taken from the
    first of them.

    ``expected_by_node`` is not read. A node's label reaches ``node_matches`` as it is written
    and is never folded, so a criterion named there would be registered, never called, and
    reported as a figure with no denominator.
    """
    found: dict[str, str] = {}
    for example in examples:
        if isinstance(example.expected, Criteria):
            for criterion in example.expected.criteria:
                found.setdefault(criterion.id, criterion.text)
    return found
