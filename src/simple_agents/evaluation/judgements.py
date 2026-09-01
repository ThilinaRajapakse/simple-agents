"""A judgement the scoring code did not compute, and the file it is read out of.

Some conditions on an answer cannot be decided by code. Whether a reply promised a refund,
whether a summary is faithful to its source, whether a recommendation honoured what the reader
asked for: a model or a person decides those, and a scoring rule reads the decision.

**A scoring rule never calls a model.** The judgement is made by a run, or by a person, and
written to ``evals/judgements.jsonl``; scoring reads the file. Scoring runs again on every
``EvalSuite.rescore`` and in continuous integration, so a model call inside it would need
credentials on a machine that has none, spend money every time a number is recomputed, and give
a different answer on each pass.

``docs/evaluation.md`` §12 is the surface of record.

A judgement is keyed on **what was judged** rather than on where it sat: the example, the
question, and the material. So the same answer produced again reuses the judgement, and an
answer that changed has none, which is what stops a verdict made against an older answer being
applied to a newer one.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..errors import ConfigurationError
from ..schema import encode_answer
from .labels import Label

__all__ = [
    "Judged",
    "UnjudgedAnswers",
    "JudgementRequest",
    "Judgements",
    "judgement_key",
]


# Rollouts are scored on several threads. What a judgement was read for is a dict write per
# rollout, and a lost one is a count and a digest that no re-run reproduces.
_WRITING = threading.Lock()


class JudgementMissing(Exception):
    """Raised inside a scoring rule that asked for a judgement nothing has made yet.

    Caught by whichever seam called the rule, so the rest of the rules still run and one pass
    collects everything that needs judging. It never reaches a project.
    """

    def __init__(self, request: "JudgementRequest") -> None:
        super().__init__(request.key)
        self.request = request


@dataclass(frozen=True, slots=True)
class Judged:
    """Registered in place of a check, for a condition code cannot decide::

        suite = EvalSuite(
            pipeline, examples, answer="answer", matches=exact,
            criteria={"cites_policy": names_a_section, "no_refund_promise": Judged()},
        )

    The condition's text is the question and the answer is the material, so nothing else is
    declared. A judgement that reads more than the answer, or a figure that is not a condition
    on the answer key, calls :meth:`~simple_agents.evaluation.Scoring.judgement` instead.

    Construction is satisfied by this, so an evaluation can run before anything is judged.
    What refuses is scoring: ``EvalSuite.run`` gates between the rollouts and the numbers, and
    names every answer still waiting on a judgement.
    """


@dataclass(frozen=True, slots=True)
class JudgementRequest:
    """One thing waiting to be judged, as handed to a judging pass.

    ``question`` is what the judge is asked and ``material`` is what it reads. The rest says
    where the request came from, so a person reading the worklist knows what they are looking
    at and a refusal can name it::

        for want in suite.unjudged(run_dir="runs/eval/eval_a1226bc495df", split="held_out"):
            want.question     # 'does not promise a refund'
            want.material     # the answer the rollout produced
            want.example_id   # 'q29'

    ``key`` is what the judgement is filed under, and is a digest of the example, the question
    and the material. Two rollouts that produced the same answer share one request.
    """

    key: str
    question: str
    material: Any
    example_id: str
    rollout: int | None = None
    criterion_id: str | None = None
    node_id: str | None = None

    @property
    def site(self) -> str | None:
        """Which figure read this judgement, so a results file records one per figure."""
        return self.criterion_id or self.node_id

    def about(self) -> dict[str, Any]:
        """What the judgement records about where it came from."""
        found: dict[str, Any] = {"example": self.example_id, "question": self.question}
        if self.rollout is not None:
            found["rollout"] = self.rollout
        if self.criterion_id is not None:
            found["criterion"] = self.criterion_id
        if self.node_id is not None:
            found["node"] = self.node_id
        found["material"] = encode_answer(self.material)
        return found

    def label(
        self, verdict: Any, *, decided_by: str, reason: str = "", run_id: str | None = None
    ) -> Label:
        """This request answered, as the record a judgements file holds::

        want.label(True, decided_by="human", reason="no refund is offered")
        """
        return Label(
            id=self.key,
            verdict=verdict,
            decided_by=decided_by,
            reason=reason,
            run_id=run_id,
            about=self.about(),
        )

    def describe(self) -> str:
        """One line naming what this is about, for a refusal or a worklist listing."""
        where = f"example {self.example_id!r}"
        if self.rollout is not None:
            where += f" rollout {self.rollout}"
        if self.criterion_id is not None:
            where += f", criterion {self.criterion_id!r}"
        elif self.node_id is not None:
            where += f", node {self.node_id!r}"
        return f"{where}: {self.question}"


def judgement_key(example_id: str, question: str, material: Any) -> str:
    """What a judgement about this material is filed under.

    A digest of the example, the question and the material, so a judgement is found again by
    the answer it was made about. The rollout index is not in it: the k rollouts of one example
    that produced the same answer share one judgement and are judged once.
    """
    rendered = _stable_json(encode_answer(material))
    material_text = f"{example_id}\x00{question}\x00{rendered}"
    return f"sha256:{hashlib.sha256(material_text.encode('utf-8')).hexdigest()[:16]}"


def _stable_json(value: Any) -> str:
    """A value rendered so that equal values give equal text in every process."""
    import json

    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


@dataclass
class Judgements:
    """What a scoring rule reads a judgement out of, for one evaluation.

    ``found`` is what the judgements file holds, keyed as :func:`judgement_key` keys it.
    ``wanted`` fills with every request nothing has answered, and ``used`` with every judgement
    a number actually rested on, which is what the run directory's copy holds.

    Built by the runner. A project never constructs one.
    """

    found: Mapping[str, Label] = field(default_factory=dict)
    wanted: dict[str, JudgementRequest] = field(default_factory=dict)
    used: dict[str, Label] = field(default_factory=dict)
    used_at: dict[str | None, dict[str, Label]] = field(default_factory=dict)

    def resolve(self, request: JudgementRequest) -> Any:
        """The verdict for this request, or record it as wanted and raise.

        The raise is caught by the seam that called the rule, so one pass over the rollouts
        collects every missing judgement rather than stopping at the first.

        Rollouts are scored concurrently, so the two records are written under a lock. Both are
        dictionaries keyed by the judgement, and a lost write would be a count and a digest
        that no re-run reproduces.
        """
        label = self.found.get(request.key)
        if label is None:
            with _WRITING:
                self.wanted.setdefault(request.key, request)
            raise JudgementMissing(request)
        with _WRITING:
            self.used[request.key] = label
            self.used_at.setdefault(request.site, {})[request.key] = label
        return label.verdict

    @property
    def missing(self) -> tuple[JudgementRequest, ...]:
        """Every request nothing has answered, in the order they were asked for."""
        return tuple(self.wanted.values())

    def at(self, site: str | None = None) -> dict[str, Label]:
        """The judgements one figure rested on, or every one this evaluation used."""
        if site is None:
            return dict(self.used)
        return dict(self.used_at.get(site, {}))

    def content_hash(self, site: str | None = None) -> str:
        """A digest of the judgements a figure rested on.

        Recorded in the results file so a comparison between two evaluations can tell a change
        in the agent from a change in what judged it. Re-judging, correcting a verdict by hand
        and swapping the judge all move this.
        """
        lines = [_stable_json(label.to_json()) for _, label in sorted(self.at(site).items())]
        joined = "\n".join(lines)
        return f"sha256:{hashlib.sha256(joined.encode('utf-8')).hexdigest()[:16]}"

    def deciders(self, site: str | None = None) -> dict[str, int]:
        """How many of the judgements each decider made, by ``decided_by``."""
        counts: dict[str, int] = {}
        for label in self.at(site).values():
            counts[label.decided_by] = counts.get(label.decided_by, 0) + 1
        return dict(sorted(counts.items()))

    def run_ids(self, site: str | None = None) -> list[str]:
        """The distinct runs that made these judgements, so the pass is recoverable."""
        return sorted({label.run_id for label in self.at(site).values() if label.run_id})

    def to_record(self, site: str | None = None) -> dict[str, Any]:
        """What a results file stores about the judgements one figure rested on.

        ``site`` is a criterion id or a node id. Without one this is every judgement the
        evaluation used, which is what the file records once so that a judged figure with no
        entry of its own still cannot move without a comparison seeing it.
        """
        return {
            "n": len(self.at(site)),
            "decided_by": self.deciders(site),
            "run_ids": self.run_ids(site),
            "judgements": self.content_hash(site),
        }


class UnjudgedAnswers(ConfigurationError):
    """An evaluation reached its numbers with unjudged answers.

    ``run_dir`` is the directory holding the rollouts, which finished and were recorded before
    this was raised, and ``wanted`` is what is waiting. Both are on the exception so a project
    can judge without parsing the message or repeating the path::

        try:
            results = suite.run(envelope=env, model=client, split="held_out", k=3, seed=41)
        except UnjudgedAnswers as waiting:
            write_labels("evals/judgements.jsonl",
                         [decide(want) for want in waiting.wanted], append=True)
            results = suite.rescore(run_dir=waiting.run_dir, split="held_out")
    """

    def __init__(self, message: str, *, run_dir: Any, wanted: Sequence["JudgementRequest"]) -> None:
        super().__init__(message)
        self.run_dir = run_dir
        self.wanted = tuple(wanted)


def refuse_unjudged(
    missing: Sequence[JudgementRequest],
    *,
    run_dir: Any,
    found: Mapping[str, Label],
    verb: str = "run",
    unanswered: Sequence[JudgementRequest] = (),
) -> None:
    """Refuse to score with judgements outstanding, naming what is waiting and what to call.

    Raised after every rollout has finished and been recorded, so nothing that was paid for is
    lost: the run directory holds them and ``rescore`` scores them once the judgements exist.

    ``unanswered`` is what a judging pass was asked for and returned nothing about, which is a
    different fault from nothing having been asked: the pass ran, cost what it cost, and left
    these behind. Naming it is what separates a judge that failed on some items from one that
    was never called.
    """
    if not missing:
        return
    shown = "\n".join(f"  {request.describe()}" for request in missing[:5])
    more = f"\n  ... and {len(missing) - 5} more" if len(missing) > 5 else ""
    stale = _stale(missing, found)
    if unanswered:
        raise UnjudgedAnswers(
            f"The judging pass was asked for {len(unanswered)} judgement(s) and returned "
            f"none of them, so scoring would report a number resting on judgements that were "
            f"never made.\n"
            f"{shown}{more}\n"
            f"Asking again is not going to answer them, so this stopped rather than paying "
            f"for the pass a second time. A pass that drops an item it could not decide leaves "
            f"exactly this. Return a Label for every request it is given, and raise where it "
            f"could not decide one, so the failure is visible. An Unknown verdict is not that: "
            f"it says the answer asserted nothing about the condition, which is a claim about "
            f"the answer rather than about the judge.\n"
            f"The rollouts are recorded in {run_dir} and none has to run again.",
            run_dir=run_dir,
            wanted=missing,
        )
    raise UnjudgedAnswers(
        f"{len(missing)} answer(s) have no judgement, so nothing decides whether they met the "
        f"condition and no number can be reported.\n"
        f"{shown}{more}\n"
        f"{stale}"
        f"The rollouts finished and are recorded in {run_dir}, so none of them has to run "
        f"again. Judge them and then score what is on disk:\n"
        f"  suite.judge(run_dir={str(run_dir)!r}, using=judging_pipeline, model=judge, "
        f"envelope=env)\n"
        f"  results = suite.rescore(run_dir={str(run_dir)!r}, split=...)\n"
        f"To judge as part of the {verb}, pass judge= to it. To judge by hand, catch "
        f"UnjudgedAnswers: its .wanted is this list and its .run_dir is that directory.",
        run_dir=run_dir,
        wanted=missing,
    )


def _stale(missing: Sequence[JudgementRequest], found: Mapping[str, Label]) -> str:
    """A line naming a slot that was judged before, against different material.

    A judgement is keyed on what was judged, so an answer that changed has none. Without this
    the refusal reads as though the condition was never judged at all, when what happened is
    that the agent's answer moved out from under a judgement that is still in the file.
    """
    by_slot = {
        (
            str(label.about.get("example")),
            label.about.get("criterion"),
            label.about.get("node"),
        ): label
        for label in found.values()
        if label.about
    }
    for request in missing:
        slot = (request.example_id, request.criterion_id, request.node_id)
        earlier = by_slot.get(slot)
        if earlier is not None:
            when = str(earlier.decided_at)[:10]
            return (
                f"{request.describe()} was judged on {when} by {earlier.decided_by}, against "
                f"an answer that is not this one. A judgement is keyed on what was judged, so "
                f"an answer that changed needs judging again.\n"
            )
    return ""


def judged_copy(used: Iterable[Label]) -> list[Label]:
    """The judgements one evaluation used, ordered so the file it is written to is stable."""
    return sorted(used, key=lambda label: label.id)
