"""What one rollout produced, sorted into the six outcomes an evaluation distinguishes.

An agent that returns `unknown` when it does not know is usable. An agent that returns a
confident wrong value is worse than nothing, because whatever consumes it acts on it. Averaging
the two into one accuracy number hides the dangerous failure behind the harmless one, and
optimizing against the average trades the harmless one away (FT-10).

The library sorts a rollout by reading absence on both sides, so the project supplies only the
comparison between two asserted answers:

==========================  ==========================  ==========================
                            ``expected`` is a value     ``expected`` is ``Unknown``
==========================  ==========================  ==========================
asserted, met the key       ``correct``                 not reachable
asserted, met part          ``partially_correct``       not reachable
asserted, met none          ``false_confidence``        ``false_confidence``
met none of it, and
asserted nothing wrong      ``missed``                  not reachable
reported ``unknown``        ``missed``                  ``correct_abstention``
produced nothing            ``failed``                  ``failed``
never answered              ``no_response``             ``no_response``
==========================  ==========================  ==========================

``partially_correct`` is reachable only from an answer key whose parts can be met separately:
``Criteria``, and ``Contains`` with more than one value. A plain label, an ``AnyOf`` and a
``WithinTolerance`` each admit one answer or none, so a rollout scored against one of those is
``correct`` or ``false_confidence``.

The same separation runs inside the answer. A criterion's check reports that the answer
asserted nothing about its condition by returning ``Unknown``, and an answer that met none of
its key that way is ``missed`` rather than ``false_confidence``: it invented nothing, so it is
the recoverable failure and not the dangerous one. An answer that met part of its key and was
silent on the rest is still ``partially_correct``, and a criterion declaring ``expects_absence``
is **met** by silence rather than left unmet by it.

``no_response`` is the seventh state, and it is not a way the agent can be wrong: the backend
never answered, so the agent produced nothing to sort. It is outside every rate's denominator
and is counted beside them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..budget import BudgetExceeded
from ..context_builder import ContextOverflow
from ..errors import LeftTheSlice
from ..records.cassette import CassetteMiss
from ..records.trajectory import read_trajectory
from ..schema import Unknown, decode_answer, encode_answer
from .scoring import Scoring, Verdict, verdict_of

__all__ = [
    "Outcome",
    "causes_of",
    "NodeObservation",
    "RolloutOutcome",
    "classify",
]


class Outcome(str, Enum):
    """How one rollout ended, against what the example expected."""

    CORRECT = "correct"
    CORRECT_ABSTENTION = "correct_abstention"
    FALSE_CONFIDENCE = "false_confidence"
    MISSED = "missed"
    FAILED = "failed"

    PARTIALLY_CORRECT = "partially_correct"
    """The agent asserted an answer that met part of the answer key and not all of it.

    Reachable from an answer key whose parts can be met separately: ``Criteria``, and
    ``Contains`` with more than one value. The share met is on the rollout::

        results.rollouts[0].verdict.grade    # 0.75
        results.rollouts[0].verdict.parts    # {'not_read': True, 'length': False}

    An answer that missed a criterion declared ``required`` is not partly right whatever the
    grade, so a failure that matters is not reported as mostly right. It is
    ``false_confidence`` where it asserted something wrong and ``missed`` where it asserted
    nothing about the conditions it fell short of.
    """

    LEFT_THE_SLICE = "left_the_slice"
    """The run reached an edge whose other end is outside the slice it was run on.

    Only reachable on a pipeline produced by ``Pipeline.slice``. A route selected an arm the
    slice does not hold, or a node failed with its ``on_error`` handler outside it, so the run
    ended at the boundary rather than being sent somewhere it would not have gone. The rollout
    is outside every rate's denominator and its count is reported beside every rate::

        results.metrics["accuracy"].left_out    # {'left_the_slice': 7}

    The agent neither answered nor failed here, so this is separate from both.
    """

    NO_RESPONSE = "no_response"
    """The rollout never got an answer out of the backend, so nothing measured the agent.

    A model call that raised before returning a response, or a replay with no entry for a call
    the run made. A rollout in this state is outside every rate's denominator and its count is
    reported beside every rate::

        results.metrics["accuracy"].left_out       # {'no_response': 9}

    ``failed`` is the agent producing no answer from a backend that did answer: a tool raised, a
    response did not validate against the schema, the run passed its budget.
    """

    @property
    def asserted(self) -> bool:
        """Whether this outcome alone says the agent put an answer forward.

        ``missed`` covers an answer that reported absence and a record that filled some fields
        and left a ``required`` one alone, and the outcome does not separate them.
        :attr:`RolloutOutcome.asserted` reads the verdict as well and is what every rate is
        computed over; this is the answer where there is no verdict to read.
        """
        return self in (
            Outcome.CORRECT,
            Outcome.PARTIALLY_CORRECT,
            Outcome.FALSE_CONFIDENCE,
        )

    @property
    def succeeded(self) -> bool:
        """Whether the agent gave the right answer, including the right report of absence."""
        return self in (Outcome.CORRECT, Outcome.CORRECT_ABSTENTION)

    @property
    def measured(self) -> bool:
        """Whether the backend answered this rollout at all.

        False only for ``no_response``. It is one of three things that put a rollout outside
        a rate's denominator, and ``RolloutOutcome.left_out`` names whichever applied::

            [r for r in results.rollouts if not r.left_out]
        """
        return self is not Outcome.NO_RESPONSE


NO_RESPONSE_CAUSE = "no_response"


def causes_of(rollout: RolloutOutcome) -> tuple[str, ...]:
    """Every reason this rollout is outside a rate's denominator, or empty where it is inside.

    ``no_response`` and ``left_the_slice`` are outcomes as well as causes, so a rollout in
    either carries the cause whoever built it. The rest are on ``RolloutOutcome.left_out``::

        [r for r in results.rollouts if not causes_of(r)]   # the ones a rate is over
    """
    causes = list(rollout.left_out)
    for cause, outcome in (
        ("left_the_slice", Outcome.LEFT_THE_SLICE),
        (NO_RESPONSE_CAUSE, None),
    ):
        named = rollout.outcome is outcome if outcome else not rollout.outcome.measured
        if named and cause not in causes:
            causes.insert(0, cause)
    return tuple(causes)


def classify(
    scoring: Scoring,
    *,
    matches: Callable[[Scoring], bool],
    criteria: Mapping[str, Callable[[Scoring], bool]] | None = None,
    failed: bool = False,
) -> tuple[Outcome, Verdict | None]:
    """Sort one rollout into an outcome, and return the verdict that decided it.

    ``matches`` is called only when both sides are asserted values, so it never has to handle
    absence and never decides whether an answer was given. The verdict is ``None`` where no
    comparison happened, which is every branch absence or a failure decided::

        classify(scoring, matches=lambda s: s.answer == s.expected)
        # (Outcome.CORRECT, Verdict(grade=1.0, met=1, total=1))

    A rollout that raised, or that produced no output, is ``failed`` and is never compared. An
    asserted value where the correct answer is absence is ``false_confidence`` whatever it
    says, because there was nothing to be right about.

    An answer that met part of its key is ``partially_correct``, and one that missed a
    criterion declared ``required`` is not partly right whatever else it met.

    **An answer that is not partly right is sorted the way the whole answer is**: it is
    ``false_confidence`` where it asserted something wrong, and ``missed`` where every
    condition it did not meet is one it asserted nothing about. A record with every field left
    empty is ``missed`` where every condition asked for a value, and ``partially_correct``
    where one of them declared ``expects_absence`` and the silence met it.
    """
    answer, expected = scoring.answer, scoring.expected
    if failed or answer is None:
        return Outcome.FAILED, None
    if isinstance(answer, Unknown):
        return (
            Outcome.CORRECT_ABSTENTION if isinstance(expected, Unknown) else Outcome.MISSED
        ), None
    if isinstance(expected, Unknown):
        return Outcome.FALSE_CONFIDENCE, None

    verdict = verdict_of(scoring, matches=matches, criteria=criteria)
    if verdict.unmet_required or verdict.empty:
        if verdict.asserted_wrong:
            return Outcome.FALSE_CONFIDENCE, verdict
        return Outcome.MISSED, verdict
    if verdict.complete:
        return Outcome.CORRECT, verdict
    return Outcome.PARTIALLY_CORRECT, verdict


@dataclass(frozen=True, slots=True)
class NodeObservation:
    """What one node did on one rollout, for the rates that are per node.

    ``reached`` is whether the node ran at all, which a graph makes a question rather than a
    given. ``matched`` is whether its output matched the label for that node, and is ``None``
    where the example carries no label for it or the node did not run::

        results.rollouts[0].nodes["verify"].reached    # True
        results.rollouts[0].nodes["verify"].matched    # None, if nothing labels `verify`

    ``scores`` holds this node's project metrics for this rollout, keyed by metric name. A
    metric whose denominator this rollout falls outside has no key here rather than a zero::

        results.rollouts[0].nodes["hunt"].scores       # {'span_f1': 0.83}
    """

    reached: bool
    matched: bool | None = None
    scores: dict[str, float] = field(default_factory=dict)
    ratios: dict[str, tuple[float, float]] = field(default_factory=dict)
    """This node's contribution to each ratio figure declared for it, as
    ``(numerator, denominator)``.

    Apart from ``scores`` for the reason an end-to-end ratio is apart from an end-to-end
    score: a ratio is summed over the rollouts rather than averaged, so one number per rollout
    would not carry it::

        results.rollouts[0].nodes["hunt"].ratios    # {'unreadable_pages': (2.0, 11.0)}
    """

    def to_record(self) -> dict[str, Any]:
        return {
            "reached": self.reached,
            "matched": self.matched,
            "scores": dict(self.scores),
            "ratios": {name: list(pair) for name, pair in self.ratios.items()},
        }

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> NodeObservation:
        return cls(
            reached=bool(raw.get("reached")),
            matched=raw.get("matched"),
            scores={str(k): float(v) for k, v in (raw.get("scores") or {}).items()},
            ratios={
                str(k): (float(v[0]), float(v[1])) for k, v in (raw.get("ratios") or {}).items()
            },
        )


@dataclass(frozen=True)
class RolloutOutcome:
    """One rollout of one example: what it answered, how it was sorted, and where it is.

    ``run_id`` and ``trajectory`` are what make a surprising result in the report findable
    rather than gone. ``seed`` is what the rollout was run at, derived from the evaluation's
    own seed (FT-07)::

        worst = [r for r in results.rollouts if r.outcome is Outcome.FALSE_CONFIDENCE]
        worst[0].trajectory     # the run that produced it

    ``scores`` holds this rollout's project metrics, keyed by metric name. They are written
    when the evaluation runs and read back from the results file, so a comparison between two
    evaluations needs neither the labels nor the scoring functions::

        results.rollouts[0].scores      # {'span_f1': 0.83}

    ``verdict`` is what the comparison with the answer key produced, and is ``None`` where no
    comparison happened: a failure, and either side reporting absence end to end. It carries
    the share of the key that was met and each criterion's own verdict, which is ``None`` for a
    condition the answer asserted nothing about::

        results.rollouts[0].verdict.grade    # 0.75
        results.rollouts[0].verdict.parts    # {'not_read': True, 'length': False}
    """

    example_id: str
    rollout: int
    seed: int
    outcome: Outcome
    answer: Any = None
    run_id: str | None = None
    trajectory: str | None = None
    error: dict[str, Any] | None = None
    nodes: dict[str, NodeObservation] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    ratios: dict[str, tuple[float, float]] = field(default_factory=dict)
    """This rollout's contribution to each ratio figure, as ``(numerator, denominator)``.

    Kept apart from ``scores`` because a ratio is summed rather than averaged, so one number
    per rollout would not carry it: two rollouts contributing 1 of 10 and 1 of 2 make 2 of 12,
    which is not the mean of their two ratios::

        results.rollouts[0].ratios     # {'backlist_share': (1.0, 10.0)}

    Written when the evaluation runs and read back from the results file, so a comparison
    between two evaluations needs neither the labels nor the scoring functions.
    """

    verdict: Verdict | None = None
    left_out: tuple[str, ...] = ()
    """Why this rollout is outside a rate's denominator, beyond the backend not answering.

    A rollout measures the agent when what it returned is attributable to the agent.
    ``unanswered_consultation`` is a question that went to a channel meant to answer it and
    did not, and ``unreached_items`` a fan-out item that died on a call the backend never
    answered::

        [r for r in results.rollouts if "unanswered_consultation" in r.left_out]

    A question answered by a channel declaring ``nobody``, which :func:`~simple_agents.builtins.consult.unattended` does, is
    the designed path rather than an answer that failed to arrive, so it is not here. The
    backend never answering is ``no_response``, which is the outcome itself: :func:`causes_of`
    reads both together, and every figure carries the counts beside it.
    """

    unanswered_consultations: int = 0
    """How many of this rollout's questions the end user declined or was not there for.

    A rollout that had to ask and got nothing back was scored against an answer it had no way
    to reach, so a rate computed over it is partly a measurement of whoever was answering::

        [r for r in results.rollouts if r.unanswered_consultations]

    Zero for a rollout that asked nothing, and for one whose questions were all answered.
    """

    unreached_items: int = 0
    """How many of this rollout's fan-out items died on a call the backend never answered.

    A fan-out collects a failed item rather than raising, so a rollout whose items were
    rate-limited or refused completes and is scored on what the rest produced. Where the
    fan-out is what produces the answer, that reads as the agent declining::

        [r for r in results.rollouts if r.unreached_items]

    Zero for a rollout with no fan-out, and for one whose items all reached the backend. An
    item that failed on a reply it was given, such as one that did not validate, is not counted
    here: the agent produced no answer from an answer.
    """

    @property
    def score(self) -> float:
        """1.0 for a right answer, including a right report of absence. 0.0 otherwise."""
        return 1.0 if self.outcome.succeeded else 0.0

    @property
    def graded_score(self) -> float:
        """The same, with a partly-right answer scoring the share of its key it met.

        1.0 for a right answer and for a right report of absence, the grade for an answer that
        met part of its key, and 0.0 otherwise, which includes an answer that met part of its
        key and missed a ``required`` condition. ``graded_accuracy`` is the mean of this and
        ``accuracy`` the mean of :attr:`score`, so the two differ only where a rollout was
        sorted ``partially_correct``.
        """
        if self.outcome is Outcome.PARTIALLY_CORRECT and self.verdict is not None:
            return self.verdict.grade
        return self.score

    @property
    def asserted(self) -> bool:
        """Whether this rollout put an answer forward, right, wrong or partly right.

        Read off the verdict where there is one, so a record that named a vendor and left a
        ``required`` PO number alone counts as an answer given: it is inside
        ``precision_when_asserting``, where it scores 0.0, and outside ``abstention_rate``,
        which is over rollouts that reported absence::

            results.rollouts[0].verdict.parts   # {'vendor': True, 'po_number': None}
            results.rollouts[0].asserted        # True

        Where no comparison happened there is no verdict, and the outcome answers alone: a
        rollout that reported absence, failed, or never got an answer out of the backend
        asserted nothing.
        """
        if self.verdict is not None:
            return self.verdict.asserted
        return self.outcome.asserted

    def to_record(self) -> dict[str, Any]:
        """What a results file stores for this rollout."""
        return {
            "example_id": self.example_id,
            "rollout": self.rollout,
            "seed": self.seed,
            "outcome": self.outcome.value,
            "answer": encode_answer(self.answer),
            "run_id": self.run_id,
            "trajectory": self.trajectory,
            "error": self.error,
            "nodes": {node_id: n.to_record() for node_id, n in self.nodes.items()},
            "scores": dict(self.scores),
            "ratios": {name: list(pair) for name, pair in self.ratios.items()},
            "verdict": self.verdict.to_record() if self.verdict is not None else None,
            "left_out": list(self.left_out),
            "unanswered_consultations": self.unanswered_consultations,
            "unreached_items": self.unreached_items,
        }

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> RolloutOutcome:
        """Rebuild one rollout from a results file."""
        verdict = raw.get("verdict")
        return cls(
            example_id=str(raw["example_id"]),
            rollout=int(raw["rollout"]),
            seed=int(raw["seed"]),
            outcome=Outcome(raw["outcome"]),
            answer=decode_answer(raw.get("answer")),
            run_id=raw.get("run_id"),
            trajectory=raw.get("trajectory"),
            error=raw.get("error"),
            nodes={
                str(node_id): NodeObservation.from_record(entry)
                for node_id, entry in (raw.get("nodes") or {}).items()
            },
            scores={str(k): float(v) for k, v in (raw.get("scores") or {}).items()},
            ratios={
                str(k): (float(v[0]), float(v[1])) for k, v in (raw.get("ratios") or {}).items()
            },
            verdict=Verdict.from_record(verdict) if verdict else None,
            left_out=tuple(str(cause) for cause in (raw.get("left_out") or ())),
            unanswered_consultations=int(raw.get("unanswered_consultations", 0)),
            unreached_items=int(raw.get("unreached_items", 0)),
        )


def _unreached_items_in(records: Sequence[Mapping[str, Any]]) -> int:
    """How many fan-out items of this rollout failed on a call the backend never answered.

    A fan-out collects a failed item rather than raising, and at the default ``max_failures``
    it never raises at all, so a rollout whose items died on the backend completes and is
    scored on whatever the successful ones produced. Where the fan-out is what produces the
    answer, that reads as the agent declining rather than as a call that did not happen.

    Counted the way :func:`_outcome_for` classifies a whole run: an item whose last model call
    recorded an error and returned no content. An item that failed on something the backend did
    answer, such as a response that did not validate, is not one of these; it is the agent
    producing no answer from a reply it was given.
    """
    # A step's outputs are whatever it returned, and a fan-out's items are under a mapping;
    # a step that returned a string or a list has no items to read.
    failed = {
        (record.get("record_id"), item.get("index"))
        for record in records
        if record.get("record_type") == "node_execution"
        and isinstance(record.get("outputs"), Mapping)
        for item in (record["outputs"].get("items") or [])
        if isinstance(item, Mapping) and item.get("error") is not None
    }
    if not failed:
        return 0
    # Keyed on the node as well as the item: an index is a position within one fan-out, so two
    # fan-out nodes in one rollout both have an item 0 and reading them as one would let a
    # later node's success stand in for an earlier node's failure.
    last: dict[Any, Mapping[str, Any]] = {}
    for record in records:
        if record.get("record_type") != "model_call":
            continue
        key = (record.get("parent_id"), record.get("item_index"))
        if key in failed:
            last[key] = record
    return sum(
        1
        for record in last.values()
        if record.get("error") and not (record.get("outputs") or {}).get("content")
    )


def _unanswered_in(records: Sequence[Mapping[str, Any]]) -> int:
    """How many of a rollout's questions the end user declined or was not there for.

    Counted off the asking record, as every other consultation figure is, so a question
    answered in a later process is one question rather than two.
    """
    return sum(1 for _ in _unanswered_questions(records))


def _unanswered_questions(
    records: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """The asking records of the questions that got no answer."""
    return [
        record
        for record in records
        if record.get("record_type") == "consultation"
        and record.get("answers") is None
        and str(record.get("resolution")) in ("declined", "unavailable")
    ]


def _left_out_of(records: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Why this rollout does not measure the agent, beyond the backend not answering.

    A rollout is inside a rate's denominator when what it returned is attributable to the
    agent. A question that went to someone meant to answer it and did not is not, nor is an
    item that died on a call the backend never answered. The backend never answering at all is
    the outcome itself, which ``causes_of`` reads beside these.

    A channel declaring ``nobody``, which ``unattended()`` does, is the designed path rather
    than an answer that failed to arrive, so a question it declined leaves the rollout inside.
    """
    causes: list[str] = []
    if any(
        str(record.get("answered_by") or "") != "nobody"
        for record in _unanswered_questions(records)
    ):
        causes.append("unanswered_consultation")
    if _unreached_items_in(records):
        causes.append("unreached_items")
    if _left_the_slice(records):
        causes.append("left_the_slice")
    return tuple(causes)


def _left_the_slice(records: Sequence[Mapping[str, Any]]) -> bool:
    """Whether this run ended at the boundary of the slice it was run on.

    A route selected an arm the slice does not hold, so the run went no further. The agent
    neither answered nor failed, and the rollout is outside every figure.
    """
    return any(
        record.get("record_type") == "node_execution"
        and record.get("termination") == "left_the_slice"
        for record in records
    )


def _outcome_for(exc: BaseException, trajectory: str | os.PathLike[str]) -> Outcome:
    """How to sort a rollout whose run raised: as the agent failing, or as no answer at all.

    Two things are ``no_response``, and nothing the agent did was measured in either.
    :class:`~simple_agents.records.cassette.CassetteMiss`, where the recording holds no answer for a
    call the run made. And any other failure whose run stopped on a model call that recorded an
    error and returned no response: the backend was unreachable, rejected the request,
    rate-limited past its retries, or answered with a status the adapter could not use.

    ``failed`` for everything else, which is the agent producing no answer from a backend that
    did answer: a tool raised, a response did not validate against the declared schema, the run
    passed its budget, a request the node's own context built was refused as too long.

    ``left_the_slice`` is its own answer, reachable only on a pipeline produced by
    ``Pipeline.slice``: the run reached the slice's boundary, so the agent neither answered nor
    failed.

    The trajectory is read rather than the exception type, because a client the project wrote
    raises whatever it raises and the record the library writes for a call that never returned
    is the same either way.
    """
    if isinstance(exc, CassetteMiss):
        return Outcome.NO_RESPONSE
    if isinstance(exc, LeftTheSlice):
        return Outcome.LEFT_THE_SLICE
    if isinstance(exc, (BudgetExceeded, ContextOverflow)):
        return Outcome.FAILED
    return Outcome.NO_RESPONSE if _ended_on_an_unanswered_call(trajectory) else Outcome.FAILED


def _ended_on_an_unanswered_call(trajectory: str | os.PathLike[str]) -> bool:
    """Whether the last model call this run made recorded an error and no response."""
    if not Path(trajectory).exists():
        return False
    calls = [
        record
        for record in read_trajectory(trajectory)
        if record.get("record_type") == "model_call"
    ]
    if not calls:
        return False
    last = calls[-1]
    return bool(last.get("error")) and not (last.get("outputs") or {}).get("content")
