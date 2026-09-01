"""The k-rollout runner: what turns a pipeline and a labeled set into a measured number.

One rollout is one `Pipeline.run`, with its own run directory, its own trajectory and its own
seed derived from the evaluation's. Running each example k times is what separates a real
change from run-to-run variance, which on agent tasks is routinely larger than the effect being
measured (FT-05).

**A tool whose effects reach outside the run is refused before any rollout starts** (FT-20).
An ``irreversible`` tool is refused outright. A ``spends_money`` tool is refused unless the
evaluation declares ``max_spend``, the most the whole evaluation may cost.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from pydantic import TypeAdapter

from ..records.cassette import Cassette
from ..context import derive_seed, error_object
from ..cost import basis_to_manifest
from ..records.conversation import ROLLOUT_CONVERSATION
from ..memory import ROLLOUT_SCOPE
from ..envelope import EVAL_BUCKET, EvaluationRef, RunEnvelope, rollouts_under
from ..errors import (
    ConfigurationError,
    RunSuspended,
    SimpleAgentsWarning,
    StreamUsageMissing,
)
from ..records.manifest import source_version
from ..models import ModelClient
from ..pacing import PacedClient
from ..pipeline import Pipeline
from ..pipeline.recording import _without_derived
from ..schema import Unknown, decode_answer
from ..tools import ConsultTool, SideEffectClass, Tool
from ..records.trajectory import read_trajectory, utc_now
from .progress import RolloutProgress, _Progress
from .declared import (
    config_differences,
    _declarations_in,
    _declarations_of,
    _held_declarations,
    _measured_configuration,
    _measured_configuration_of,
)
from .end_user import answerers_in, described
from .examples import Example, ExampleSet
from .intervals import DEFAULT_CONFIDENCE, DEFAULT_RESAMPLES
from .answer_key import Criteria
from .baseline import answers_for as baseline_answers_for
from .baseline import rollouts_for as baseline_rollouts_for
from .metrics import ProjectMetric, aggregate, criterion_metrics
from .ratios import ProjectRatio
from .ratios import figures_for
from .outcomes import (
    NodeObservation,
    Outcome,
    RolloutOutcome,
    _ended_on_an_unanswered_call,
    _left_out_of,
    _outcome_for,
    _unanswered_in,
    _unreached_items_in,
    classify,
)
from .judgements import (
    Judged,
    JudgementRequest,
    Judgements,
    judged_copy,
    refuse_unjudged,
)
from .labels import Label, read_labels, write_labels
from .scoring import Scoring, _call, criteria_in
from .per_node import holds_absence, node_rates, per_node, reached_in
from .results import EvalResults, totals_of

__all__ = [
    "EvalSuite",
    "Recording",
    "UsedRunDirectory",
    "DEFAULT_CONCURRENCY",
    "DEFAULT_JUDGEMENTS",
    "output_of",
    "terminal_node_id",
]

# Rollouts are independent runs, and a backend serves several at once. A hosted API with a
# per-minute quota needs a paced client in front of the adapter whatever this is set to.
DEFAULT_CONCURRENCY = 4

# Where judgements are kept. Appended to and never rewritten, so a verdict corrected by hand
# is a later line and the one it replaced stays in the file (`docs/evaluation.md` §12).
DEFAULT_JUDGEMENTS = "evals/judgements.jsonl"

# What one evaluation used, beside the rollouts it scored, so a rescore reproduces its numbers
# after the store has moved on.
JUDGEMENTS_NAME = "judgements.jsonl"

# A scoring rule reaches its second judgement only once the first is answered, so a pass that
# discovers more rounds rather than refusing. One round is what a condition on the answer key
# takes; the bound is a backstop against a rule that asks for a new judgement every time.
JUDGE_ROUNDS = 8


class UsedRunDirectory(ConfigurationError):
    """An evaluation was told to write rollouts into a directory that already holds some.

    ``run_dir`` is the directory. A sweep catches this to say which of its arms resolved
    there, since ``compare_variants`` runs several evaluations and the directory name alone
    does not say which one stopped.
    """

    def __init__(self, message: str, *, run_dir: Path) -> None:
        super().__init__(message)
        self.run_dir = run_dir


_UNSAFE_FOR_ROLLOUTS = (
    "An evaluation runs k rollouts over n examples, so every action a tool takes happens k×n times."
)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class Recording:
    """What :meth:`EvalSuite.record` produced, and what it cost.

    ``seed`` is the one to pass to :meth:`EvalSuite.run`, because a rollout's seed derives from
    it and a recording serves only the seeds it was made at::

        made = suite.record(envelope=env, model=client, split="held_out", k=5, max_spend=0.50)
        results = suite.run(
            envelope=env.with_cassette(Cassette.replay(made.cassette)),
            model=client, split="held_out", k=5, seed=made.seed,
        )

    ``paid_calls`` counts the **tool** calls that were charged for, and ``spend`` is what the
    whole recording was charged, model calls and paid tool calls together. ``currency`` is the
    unit ``spend`` is in, and is ``None`` only where nothing could be priced.
    All three are measured rather than declared, so a call a tool answered from its own cache
    counts in none of them, and the count of model calls is on each run's manifest rather than
    here.

    ``failed`` names the runs that ended in an error. A recording with any is incomplete, and
    the rollouts replaying those examples will miss. A run that stopped to ask a person is not
    one of them: ``RunSuspended`` reaches the caller (§7.4 of ``docs/evaluation.md``).
    """

    cassette: str
    seed: int
    examples: int
    k: int
    runs: int
    paid_calls: int
    spend: float | None
    currency: str | None
    entries: int
    failed: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        """The recording as plain data. All keys always present."""
        return {
            "cassette": self.cassette,
            "seed": self.seed,
            "examples": self.examples,
            "k": self.k,
            "runs": self.runs,
            "paid_calls": self.paid_calls,
            "spend": self.spend,
            "currency": self.currency,
            "entries": self.entries,
            "failed": list(self.failed),
        }


class EvalSuite:
    """A pipeline, a labeled set, and how an answer is compared to its label.

    ``answer`` names the field of the pipeline's output holding the answer, or a function that
    takes the output and returns it. ``matches`` compares two asserted answers and has no
    default: what counts as a correct answer is a decision about the task::

        suite = EvalSuite(
            pipeline,
            ExampleSet.from_jsonl("evals/examples.jsonl"),
            answer="answer",
            matches=lambda s: s.answer.strip() == s.expected.strip(),
        )
        results = suite.run(envelope=env, model=client, split="held_out", k=5, seed=41)
        results.write("evals/results/held-out-v3.json")

    Every scoring rule takes one :class:`~simple_agents.evaluation.Scoring`, so a comparison
    that depends on the question or on what the end user knows is written once for everyone::

        matches=lambda s: s.answer.cost_centre == s.example.metadata["cost_centre"]

    ``matches`` is called only on two asserted values, and once per part of an answer key.

    ``criteria`` registers the check behind each ``Criterion`` an example names, keyed by id.
    One check serves every example naming it, and its version is recorded beside ``matches``::

        suite = EvalSuite(
            pipeline, examples, answer="answer", matches=exact,
            criteria={"under_400_pages": lambda s: s.answer.pages < 400},
        )
        results.criteria["under_400_pages"].interval.point

    Construction is refused for a criterion nothing registers, and for a check nothing names.

    ``baseline`` is what an agent that did nothing would answer, so every figure has a floor.
    Asked once per example before the first rollout, and it may not answer ``None``::

        suite = EvalSuite(pipeline, examples, answer="answer", matches=agreement,
                          baseline=lambda example: "shelve")
        results.baseline_metrics()["accuracy"].interval.point

    ``node_matches`` reports accuracy per node, for the nodes an example set labels through
    ``Example.expected_by_node``. Its ``s.answer`` is the node's **recorded** output, plain data
    rather than the object the node returned, and ``s.expected`` that node's label as written::

        suite = EvalSuite(
            pipeline, examples, answer="answer", matches=exact,
            node_matches={"hunt": lambda s: s.answer["answer"] == s.expected},
        )

    ``metrics`` and ``node_metrics`` report figures the library does not ship, beside the eight
    rates and beside per-node accuracy. Each is a ``ProjectMetric``::

        span_f1 = ProjectMetric(
            name="span_f1",
            definition="token overlap between the asserted answer and the label",
            score=lambda s: token_f1(s.answer, s.expected),
        )
        suite = EvalSuite(
            pipeline, examples, answer="answer", matches=exact,
            metrics=[span_f1], node_metrics={"hunt": [span_f1]},
        )
        results.metrics["span_f1"].interval.point
        results.nodes["hunt"].metrics["span_f1"].interval.point
    """

    def __init__(
        self,
        pipeline: Pipeline,
        examples: ExampleSet,
        *,
        answer: str | Callable[[Any], Any],
        matches: Callable[[Scoring], bool],
        contamination_threshold: float | None = None,
        node_matches: Mapping[str, Callable[[Scoring], bool]] | None = None,
        criteria: Mapping[str, Callable[[Scoring], bool] | Judged] | None = None,
        metrics: Sequence[ProjectMetric | ProjectRatio] = (),
        node_metrics: Mapping[str, Sequence[ProjectMetric]] | None = None,
        baseline: Callable[[Example], Any] | None = None,
        judgements: str | os.PathLike[str] = DEFAULT_JUDGEMENTS,
    ) -> None:
        if not isinstance(pipeline, Pipeline):
            raise ConfigurationError(
                f"EvalSuite was given {type(pipeline).__name__}, not a Pipeline. Pass the "
                f"pipeline the evaluation runs: EvalSuite(pipeline, examples, answer='answer', "
                f"matches=...)."
            )
        if not isinstance(examples, ExampleSet):
            raise ConfigurationError(
                f"EvalSuite was given {type(examples).__name__} where an ExampleSet belongs. "
                f"Build one with ExampleSet([Example(...), ...]) or "
                f"ExampleSet.from_jsonl('evals/examples.jsonl')."
            )
        self._refuse_an_uncallable_matches(matches)
        declared = {node_id for node_id, _ in pipeline.declared_nodes()}
        self._refuse_unknown_nodes("node_matches", node_matches, declared)
        self._refuse_unknown_nodes("node_metrics", node_metrics, declared)
        self._refuse_repeated_names(metrics, node_metrics)
        self.criterion_texts = criteria_in(examples)
        self._refuse_unregistered_criteria(criteria, self.criterion_texts)
        self.pipeline = pipeline
        self.examples = examples
        self.answer = answer
        self.matches = matches
        self.criteria = dict(criteria or {})
        self.judged = frozenset(
            name for name, check in self.criteria.items() if isinstance(check, Judged)
        )
        self.judgements_path = Path(judgements)
        self.contamination_threshold = contamination_threshold
        self.node_matches = dict(node_matches or {})
        self.metrics = tuple(metrics)
        self.node_metrics = {
            node_id: tuple(declared_metrics)
            for node_id, declared_metrics in (node_metrics or {}).items()
        }
        self._refuse_an_uncallable_baseline(baseline)
        self.baseline = baseline

    @staticmethod
    def _refuse_an_uncallable_matches(matches: Any) -> None:
        if callable(matches):
            return
        raise ConfigurationError(
            "EvalSuite needs matches=, a function comparing an asserted answer with the "
            "expected one. There is no default, because what counts as a correct answer "
            "is a decision about the task: whether case matters, whether a longer span "
            "containing the answer counts, whether a date may be written either way.\n"
            "Pass matches=lambda s: s.answer.strip() == s.expected.strip() to start, then "
            "decide what it should really be. It is given a Scoring: the answer is "
            "s.answer, the value being compared against is s.expected, and the example is "
            "s.example."
        )

    @staticmethod
    def _refuse_an_uncallable_baseline(baseline: Any) -> None:
        if baseline is None or callable(baseline):
            return
        raise ConfigurationError(
            f"EvalSuite was given baseline={baseline!r}, and it has to be a function "
            f"taking an Example and returning the answer an agent that did nothing would "
            f"give.\n"
            f"Pass baseline=lambda example: 'shelve' for the majority class, or "
            f"baseline=lambda example: Unknown(reason='did nothing') for one that never "
            f"answers. It is scored by this suite's own matches and criteria, over the "
            f"examples that ran."
        )

    @staticmethod
    def _refuse_unknown_nodes(
        argument: str, given: Mapping[str, Any] | None, declared: set[str]
    ) -> None:
        unknown = sorted(set(given or ()) - declared)
        if not unknown:
            return
        raise ConfigurationError(
            f"{argument} names {', '.join(repr(u) for u in unknown)}, and this pipeline has no "
            f"node with that id, so the figure it asks for would never be computed and the "
            f"results would report none without saying why.\n"
            f"This pipeline holds {', '.join(repr(d) for d in sorted(declared))}. Correct the "
            f"key, or drop it."
        )

    @staticmethod
    def _refuse_unregistered_criteria(
        given: Mapping[str, Any] | None, named: Mapping[str, str]
    ) -> None:
        """Refuse a criterion with no check, and a check no example asks for.

        Both fail the whole evaluation rather than one rollout: a criterion with no check has
        nothing to decide it on every rollout of every example that names it, and a check
        nothing names is a scoring rule that was written and never applied, which reads from
        the results as though it had been.
        """
        registered = set(given or ())
        missing = sorted(set(named) - registered)
        if missing:
            raise ConfigurationError(
                f"The example set names {', '.join(repr(m) for m in missing)} as criteria and "
                f"the suite registers no check for them, so nothing would decide whether an "
                f"answer met them.\n"
                f"Register one per id: EvalSuite(..., criteria={{{missing[0]!r}: "
                f"lambda s: ...}}). Each is given a Scoring, so the answer is s.answer and the "
                f"example is s.example."
            )
        spare = sorted(registered - set(named))
        if spare:
            raise ConfigurationError(
                f"criteria names {', '.join(repr(s) for s in spare)}, and no example in this "
                f"set carries a criterion with that id, so the check would never be called and "
                f"the results would report no figure for it without saying why.\n"
                f"This set names {', '.join(repr(n) for n in sorted(named)) or '(none)'}. "
                f"Correct the key, or drop it."
            )

    @staticmethod
    def _refuse_repeated_names(
        metrics: Sequence[ProjectMetric | ProjectRatio],
        node_metrics: Mapping[str, Sequence[ProjectMetric]] | None,
    ) -> None:
        """Refuse two metrics sharing a name in one place, which would report one of them.

        The same metric declared end to end and again on a node is not a repeat: the two are
        different figures over different denominators and are recorded in different places.
        """
        groups = [("metrics", metrics)] + [
            (f"node_metrics[{node_id!r}]", declared)
            for node_id, declared in (node_metrics or {}).items()
        ]
        for where, declared in groups:
            seen: set[str] = set()
            for metric in declared:
                if metric.name in seen:
                    raise ConfigurationError(
                        f"{where} declares two metrics named {metric.name!r}, and the results "
                        f"file holds one entry per name, so one of them would be reported and "
                        f"the other silently dropped.\n"
                        f"Give them names saying what each is over."
                    )
                seen.add(metric.name)

    def run(
        self,
        *,
        envelope: RunEnvelope,
        model: ModelClient | None = None,
        split: str,
        k: int,
        seed: int | None = None,
        max_spend: float | None = None,
        record: bool = True,
        concurrency: int = DEFAULT_CONCURRENCY,
        run_concurrency: int = 1,
        resamples: int = DEFAULT_RESAMPLES,
        confidence: float = DEFAULT_CONFIDENCE,
        allow_mixed_cassette: bool = False,
        allow_contaminated_split: bool = False,
        resume_from: str | os.PathLike[str] | None = None,
        on_rollout: Callable[[RolloutProgress], None] | None = None,
        end_user: Any = None,
        judge: Callable[[Sequence[JudgementRequest]], Any] | None = None,
    ) -> EvalResults:
        """Run every example in ``split`` ``k`` times and report what happened.

        Each rollout writes its own run directory under ``<run_dir>/eval/<eval_id>/``, so a
        surprising result in the report has a trajectory to open::

            results = suite.run(envelope=env, model=client, split="held_out", k=5, seed=41)

        ``seed`` governs every rollout: each derives from it, the example's id and the rollout
        index, so one integer reconstructs the evaluation (FT-07). Unset, one is generated.
        ``max_spend`` is the most this evaluation may cost and is what lets a ``spends_money``
        tool run in rollouts at all::

            suite.run(envelope=env, model=client, split="held_out", k=5, seed=41,
                      max_spend=0.50)

        **An evaluation records its rollouts**, into ``<run_dir>/eval/<eval_id>/cassette.jsonl``
        unless the envelope names one, so a metric that raised is applied again with
        :meth:`rescore` rather than paid for again. ``record=False`` turns it off.
        ``concurrency`` runs that many at once; a hosted backend with a per-minute quota needs
        a ``PacedClient`` in front of the adapter.
        ``resume_from`` names this evaluation's own directory, where it stopped part way:
        rollouts that finished are scored from disk, the missing ones are run, and one that
        never finished is run again. ``on_rollout`` is called as each finishes::

            suite.run(envelope=env, model=client, split="held_out", k=3, seed=41,
                      resume_from="runs/eval/eval_a1226bc495df",
                      on_rollout=lambda progress: print(progress.describe()))

        ``end_user`` answers consultations in place of the channel (`docs/evaluation.md` §5.4)::

            suite.run(envelope=env, model=client, split="held_out", k=3, seed=41,
                      end_user=SimulatedEndUser(model=cheap))

        ``allow_mixed_cassette`` runs a cassette in ``update`` mode and
        ``allow_contaminated_split`` a split sharing material with this one, both otherwise
        refused. ``docs/evaluation.md`` §5.4, §6 and §7 cover the rest.
        """
        chosen = self.examples.in_split(split)
        self._refuse_bad_k(k)
        if not allow_mixed_cassette:
            self._refuse_mixed_cassette(envelope)
        if not allow_contaminated_split:
            self._refuse_contaminated_split(split=split, examples=len(chosen), k=k)
        self._refuse_unsafe_tools(
            envelope, examples=len(chosen), k=k, max_spend=max_spend, verb="run"
        )
        self._refuse_a_live_consultation(envelope, end_user, len(chosen), k, verb="run")
        self._refuse_an_unaffordable_ceiling(
            envelope, examples=len(chosen), k=k, max_spend=max_spend, verb="run"
        )
        self._refuse_an_ambiguous_recording(envelope)
        self._refuse_sampled_trajectory(envelope)
        self._refuse_an_undescribed_end_user(end_user, chosen)
        # Before the rollouts, so a refusal costs none of them (`baseline.answers_for`).
        baseline_answers = baseline_answers_for(self.baseline, chosen)
        # A rollout of a pipeline whose own work overlaps issues that many calls at once, so
        # the callers sharing a client are the product rather than the rollout count.
        callers = concurrency * max(1, run_concurrency)
        for client in _clients_of(self.pipeline, model):
            _pace_for(client, callers, replaying=envelope.cassette.is_replaying)
        run_ids = self._run_ids(chosen, k)
        judgements = self._judgements()

        eval_seed = seed if seed is not None else random.SystemRandom().randrange(2**31)
        self._refuse_an_unservable_recording(
            envelope, chosen=chosen, k=k, eval_seed=eval_seed, given_seed=seed
        )
        eval_id = self._eval_id(eval_seed, split, k, model, end_user)
        scoped = envelope.with_run_dir(Path(envelope.run_dir) / EVAL_BUCKET / eval_id)
        resumed = self._resumed(resume_from, Path(scoped.run_dir), chosen, k, run_ids, judgements)
        if not resumed:
            self._refuse_a_used_directory(Path(scoped.run_dir))
        scoped = _recording_by_default(scoped, record=record, resuming=resume_from is not None)

        rollouts = self._run_rollouts(
            chosen,
            k,
            resumed,
            scoped,
            model=model,
            eval_seed=eval_seed,
            run_ids=run_ids,
            concurrency=concurrency,
            run_concurrency=run_concurrency,
            end_user=end_user,
            judgements=judgements,
            on_rollout=on_rollout,
            eval_id=eval_id,
        )
        # Before the gate, so a judged condition asked about the baseline's constant answer is
        # collected in the same pass as the agent's and judged with it rather than after. Only
        # where a condition is judged at all; otherwise the scoring below is the only one.
        # The floor is read against the agent's own figure, so it is over the examples the
        # rollouts cover rather than over the split. The two differ where an evaluation scored
        # part of one, and the report says every figure is over what ran.
        floor_over = _examples_scored(chosen, rollouts)
        if self.judged:
            baseline_rollouts_for(self, floor_over, judgements, baseline_answers)
        rollouts, judgements = self._through_judging(
            rollouts, chosen, judgements, using=judge, run_dir=Path(scoped.run_dir)
        )
        baseline, baseline_unscored = baseline_rollouts_for(
            self, floor_over, judgements, baseline_answers
        )

        nodes, metrics, criteria = self._figures(
            rollouts,
            chosen,
            cost_basis=envelope.cost_basis,
            confidence=confidence,
            resamples=resamples,
            seed=eval_seed,
        )

        return EvalResults(
            eval_id=eval_id,
            created_at=utc_now(),
            config=self._config(
                split=split,
                chosen=chosen,
                k=k,
                seed=eval_seed,
                # The scoped envelope rather than the one passed in: it carries the cassette
                # the rollouts actually ran under, which is not the caller's where the
                # evaluation recorded one of its own.
                envelope=scoped,
                model=model,
                concurrency=concurrency,
                run_concurrency=run_concurrency,
                resamples=resamples,
                confidence=confidence,
                rollouts=rollouts,
                max_spend=max_spend,
                judgements=judgements,
            ),
            metrics=metrics,
            criteria=criteria,
            nodes=nodes,
            rollouts=tuple(rollouts),
            examples={e.id: e.results_entry() for e in chosen},
            baseline=baseline,
            baseline_unscored=baseline_unscored,
            totals=totals_of(nodes),
            contamination=self._contamination(),
        )

    def _run_rollouts(
        self,
        chosen: Sequence[Example],
        k: int,
        resumed: Mapping[tuple[str, int], RolloutOutcome],
        scoped: RunEnvelope,
        *,
        model: ModelClient | None,
        eval_seed: int,
        run_ids: dict[tuple[str, int], str],
        concurrency: int,
        run_concurrency: int,
        end_user: Any,
        judgements: Judgements | None,
        on_rollout: Callable[[RolloutProgress], None] | None,
        eval_id: str,
    ) -> list[RolloutOutcome]:
        """Every rollout not already on disk, run and scored, with the resumed ones beside.

        Sorted by example and index, so the order the results file reports is the split's
        rather than the order the pool finished in.
        """
        jobs = [
            (example, index)
            for example in chosen
            for index in range(k)
            if (example.id, index) not in resumed
        ]
        watch = _Progress(
            total=len(chosen) * k,
            resumed=len(resumed),
            report=on_rollout,
            eval_id=eval_id,
            write_to=Path(scoped.run_dir),
        )
        for done in resumed.values():
            watch.saw(done, replayed=True)
        if concurrency > 1 and len(jobs) > 1:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                pending = [
                    pool.submit(
                        self._rollout,
                        example,
                        index,
                        scoped,
                        model,
                        eval_seed,
                        run_ids,
                        run_concurrency,
                        end_user,
                        judgements,
                    )
                    for example, index in jobs
                ]
                rollouts = list(resumed.values())
                try:
                    for future in pending:
                        rollouts.append(watch.saw(future.result()))
                except BaseException:
                    # A rollout raises only for something that fails every rollout the same
                    # way, such as a scoring function that cannot read the answer. The ones
                    # not yet started are not worth paying for. Those already running finish,
                    # so at most `concurrency` are lost.
                    for unstarted in pending:
                        unstarted.cancel()
                    raise
        else:
            rollouts = list(resumed.values()) + [
                watch.saw(
                    self._rollout(
                        example,
                        index,
                        scoped,
                        model,
                        eval_seed,
                        run_ids,
                        run_concurrency,
                        end_user,
                        judgements,
                    )
                )
                for example, index in jobs
            ]
        rollouts.sort(key=lambda outcome: (outcome.example_id, outcome.rollout))
        return rollouts

    # -- the recording an evaluation replays ------------------------------------------------

    def record(
        self,
        *,
        envelope: RunEnvelope,
        model: ModelClient | None = None,
        split: str,
        k: int,
        seed: int | None = None,
        max_spend: float | None = None,
        end_user: Any = None,
    ) -> Recording:
        """Make the live runs an evaluation's rollouts will replay, and say what they cost.

        One live run per rollout, each at the seed that rollout will use, all into one
        cassette. :meth:`run` then replays them with no network and no spend::

            made = suite.record(
                envelope=env, model=client, split="held_out", k=5, max_spend=0.50
            )
            results = suite.run(
                envelope=env.with_cassette(Cassette.replay(made.cassette)),
                model=client, split="held_out", k=5, seed=made.seed,
            )

        The envelope's cassette names the file and is ``Cassette.record(path)`` for a new one
        or ``Cassette.update(path)`` to fill in what an earlier recording does not hold. A call
        already on file is served rather than made again, which is why this costs less than the
        same rollouts run live: the k rollouts of one example that make the same tool call buy
        one answer between them.

        ``max_spend`` is required wherever a ``spends_money`` tool is reachable, and means the
        same as it does on :meth:`run`. ``split``, ``k`` and ``seed`` have to match the
        evaluation this recording is for, because the seeds derive from them; ``seed`` comes
        back on the result for that reason.

        ``end_user`` is who answers a consultation during these runs, and has to be the one
        :meth:`run` is given, since the answers go into the cassette.

        A run that fails is recorded as far as it got and named in ``failed`` rather than
        raising, so one bad example does not discard the calls the others paid for.
        """
        chosen = self.examples.in_split(split)
        self._refuse_bad_k(k)
        self._refuse_a_recording_that_replays(envelope)
        self._refuse_unsafe_tools(
            envelope, examples=len(chosen), k=k, max_spend=max_spend, verb="record"
        )
        self._refuse_a_live_consultation(envelope, end_user, len(chosen), k, verb="record")
        self._refuse_an_unaffordable_ceiling(
            envelope, examples=len(chosen), k=k, max_spend=max_spend, verb="record"
        )
        self._refuse_an_undescribed_end_user(end_user, chosen)
        eval_seed = seed if seed is not None else random.SystemRandom().randrange(2**31)
        eval_id = self._eval_id(eval_seed, split, k, model, end_user)
        root = Path(envelope.run_dir) / EVAL_BUCKET / f"{eval_id}-recording"
        path = Path(str(envelope.cassette.path))
        run_ids = self._run_ids(chosen, k)

        # One cassette, filling up as the runs go. Every run after the first serves what the
        # ones before it recorded, so a repeated call is not bought twice.
        filling = envelope.with_cassette(Cassette.update(path))
        failed: list[str] = []
        for example in chosen:
            for index in range(k):
                run_id = run_ids[(example.id, index)]
                scoped = _scoped_for_rollout(
                    filling.with_run_dir(root),
                    example,
                    root / run_id,
                    end_user=end_user,
                    seed=derive_seed(eval_seed, example.id, index),
                    eval_id=eval_id,
                    rollout=index,
                )
                try:
                    self.pipeline.run(
                        example.inputs,
                        envelope=scoped,
                        model=model,
                        seed=derive_seed(eval_seed, example.id, index),
                        run_id=run_id,
                    )
                except RunSuspended:
                    # The run stopped to ask a person. Naming it in `failed` would report a
                    # recording that is short of one run rather than one waiting on a person,
                    # and the state to continue it is already on disk.
                    raise
                except Exception:  # noqa: BLE001, one failed run does not end the recording
                    failed.append(run_id)
        spent = _spend_of(root, run_ids.values())
        return Recording(
            cassette=str(path),
            seed=eval_seed,
            examples=len(chosen),
            k=k,
            runs=len(chosen) * k,
            paid_calls=spent["paid_calls"],
            spend=spent["spend"],
            currency=spent["currency"],
            entries=len(Cassette.replay(path).variants()) if path.exists() else 0,
            failed=tuple(failed),
        )

    @staticmethod
    def _refuse_a_recording_that_replays(envelope: RunEnvelope) -> None:
        """Refuse an envelope whose cassette would record nothing, or record it per run."""
        if envelope.cassette.awaiting_path:
            raise ConfigurationError(
                "suite.record was given an envelope with the default cassette, which records "
                "each run into its own directory. The rollouts an evaluation replays have to "
                "be in one file, so that the k rollouts of an example share the calls they "
                "make in common.\n"
                "Pass envelope.with_cassette(Cassette.record("
                "'evals/cassettes/held-out.jsonl')) for a new recording, or "
                "Cassette.update(path) to fill in the calls an earlier one does not hold."
            )
        if envelope.cassette.is_recording:
            return
        raise ConfigurationError(
            f"suite.record was given an envelope whose cassette is "
            f"{envelope.cassette.mode.value!r}, and this makes the live runs an evaluation "
            f"replays, so it has to have a file to write them to.\n"
            f"Pass envelope.with_cassette(Cassette.record('evals/cassettes/held-out.jsonl')) "
            f"for a new recording, or Cassette.update(path) to fill in the calls an earlier "
            f"one does not hold."
        )

    # -- scoring rollouts that already ran --------------------------------------------------

    def rescore(
        self,
        *,
        run_dir: str | os.PathLike[str],
        split: str,
        cost_basis: Any = None,
        resamples: int = DEFAULT_RESAMPLES,
        confidence: float = DEFAULT_CONFIDENCE,
    ) -> EvalResults:
        """Score rollouts that already ran, without running anything.

        ``run_dir`` is the evaluation's own directory, the one holding a directory per
        rollout::

            results = suite.rescore(run_dir="runs/eval/eval_a1226bc495df", split="held_out")
            results.write("evals/results/held-out-v3.json")

        Nothing here executes a pipeline, calls a model or spends anything. Each rollout's
        answer is read back from its trajectory and compared with ``matches`` as it was live,
        so this is how a metric that raised, a ``matches`` that was wrong, or a metric added
        afterwards is applied to rollouts already paid for.

        Raises :class:`~simple_agents.errors.ConfigurationError` when the rollouts were
        produced by a different pipeline, because a number scored from them would describe code
        that never ran (FT-15); when the directory holds no rollouts; or when a rollout names an
        example this split does not contain.

        ``k`` and ``seed`` come from what is on disk. ``concurrency`` and ``max_spend`` describe
        running an evaluation and are recorded as ``null``, since nothing ran here. Pass the
        ``cost_basis`` the rollouts ran under for per-node cost figures; without one those are
        ``null``, because a basis is not recoverable from a run directory and inventing one
        would price the run under rates it never paid.
        """
        chosen = self.examples.in_split(split)
        baseline_answers = baseline_answers_for(self.baseline, chosen)
        found = self._rollouts_on_disk(Path(run_dir), chosen)
        eval_seed = self._recorded_seed(found)
        judgements = self._judgements(run_dir=Path(run_dir))
        rollouts = [
            self._rescored(handle, example, index, judgements) for handle, example, index in found
        ]
        # Asked before the refusal, so a judged condition on the baseline's constant answer is
        # named alongside the agent's rather than after a second pass.
        floor_over = _examples_scored(chosen, rollouts)
        if self.judged:
            baseline_rollouts_for(self, floor_over, judgements, baseline_answers)
        refuse_unjudged(
            judgements.missing,
            run_dir=run_dir,
            found=judgements.found,
            verb="rescore",
        )
        baseline, baseline_unscored = baseline_rollouts_for(
            self, floor_over, judgements, baseline_answers
        )
        self._keep_judgements(Path(run_dir), judgements)

        nodes, metrics, criteria = self._figures(
            rollouts,
            chosen,
            cost_basis=cost_basis,
            confidence=confidence,
            resamples=resamples,
            seed=eval_seed,
        )
        k = 1 + max((r.rollout for r in rollouts), default=0)
        return EvalResults(
            eval_id=Path(run_dir).name,
            created_at=utc_now(),
            config=self._rescored_config(
                split=split,
                chosen=chosen,
                k=k,
                seed=eval_seed,
                found=found,
                rollouts=rollouts,
                resamples=resamples,
                confidence=confidence,
                judgements=judgements,
            ),
            metrics=metrics,
            criteria=criteria,
            nodes=nodes,
            rollouts=tuple(rollouts),
            examples={e.id: e.results_entry() for e in chosen},
            baseline=baseline,
            baseline_unscored=baseline_unscored,
            totals=totals_of(nodes),
            contamination=self._contamination(),
        )

    def _figures(
        self,
        rollouts: Sequence[RolloutOutcome],
        chosen: Sequence[Example],
        *,
        cost_basis: Any,
        confidence: float,
        resamples: int,
        seed: int,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """The per-node, end-to-end and per-criterion figures over these rollouts.

        ``run`` and ``rescore`` report the same figures; what differs between them is where
        the rollouts came from and what ``config`` says about it.
        """
        nodes = per_node(
            (
                read_trajectory(r.trajectory)
                for r in rollouts
                if r.trajectory and Path(r.trajectory).exists()
            ),
            cost_basis=cost_basis,
        )
        node_rates(
            nodes,
            rollouts,
            project=self.node_metrics,
            confidence=confidence,
            resamples=resamples,
            seed=seed,
        )
        metrics = aggregate(
            rollouts,
            {e.id: e.expects_absence for e in chosen},
            project=self.metrics,
            confidence=confidence,
            resamples=resamples,
            seed=seed,
        )
        criteria = criterion_metrics(
            rollouts,
            self.criterion_texts,
            _criteria_named_by(chosen),
            confidence=confidence,
            resamples=resamples,
            seed=seed,
        )
        return nodes, metrics, criteria

    def _contamination(self) -> Any:
        """The suite's contamination report, or ``None`` where no threshold declares one."""
        if self.contamination_threshold is None:
            return None
        return self.examples.contamination(threshold=self.contamination_threshold)

    def _rollouts_on_disk(
        self, run_dir: Path, chosen: Sequence[Example]
    ) -> list[tuple[Any, Example, int]]:
        """Each rollout directory under ``run_dir``, with the example and index it ran for.

        A rollout directory is named ``<example>-<index>``, which is what ``_run_ids`` wrote.
        The example is matched by that name rather than by the id, since an id holding a
        character a path cannot carry was rewritten when the directory was made.
        """
        handles = rollouts_under(run_dir)
        if not handles:
            raise ConfigurationError(
                f"Nothing to score: {str(run_dir)!r} holds no run directory with a manifest. "
                f"rescore reads an evaluation's own directory, the one holding a directory per "
                f"rollout.\n"
                f"Pass the path an evaluation wrote to, which is <run_dir>/eval/<eval_id>, not the "
                f"run_dir the envelope declared."
            )
        by_name = {
            _SAFE_NAME.sub("_", example.id).strip("_") or "example": example for example in chosen
        }
        self._refuse_a_moved_pipeline(handles, run_dir)
        by_id = {example.id: example for example in chosen}
        found: list[tuple[Any, Example, int]] = []
        latest: dict[tuple[str, int], tuple[int, Any, Example]] = {}
        for handle in handles:
            # A run says which rollout of which evaluation it is, so a rollout that ran as
            # several turns is read from what it recorded rather than from its directory's
            # name. A manifest written before format `0.35` says nothing, and the name is
            # what identified a rollout before the field existed.
            recorded = handle.evaluation
            if recorded is not None and recorded.example in by_id:
                key = (recorded.example, recorded.rollout)
                held = latest.get(key)
                if held is None or recorded.turn >= held[0]:
                    latest[key] = (recorded.turn, handle, by_id[recorded.example])
                continue
            name, _, index = str(handle.run_id).rpartition("-")
            example = by_name.get(name)
            if example is None or not index.isdigit():
                raise ConfigurationError(
                    f"Rollout directory {str(handle.run_id)!r} under {str(run_dir)!r} does not "
                    f"name an example in split {chosen[0].split!r} if this run holds one. A "
                    f"rollout directory is <example>-<index>, and its example has to be in the "
                    f"split being scored, or the number would be over a different set than the "
                    f"one that produced it.\n"
                    f"Pass the split these rollouts were run for, or the example set they were "
                    f"run against."
                )
            found.append((handle, example, int(index)))
        found.extend(
            (handle, example, rollout) for (_, rollout), (_, handle, example) in latest.items()
        )
        return sorted(found, key=lambda entry: (entry[1].id, entry[2]))

    def _refuse_a_moved_pipeline(self, handles: Sequence[Any], run_dir: Path) -> None:
        """Refuse to score rollouts a different pipeline or configuration produced (FT-15).

        Each run records the shape of the graph it walked and the configuration it walked it
        under. Scoring rollouts from one under a suite holding another reports a number for
        something that never ran, and nothing in the results file would say so.
        """
        mine = self.pipeline.graph_fingerprint()
        theirs = {
            str(handle.manifest.get("graph_fingerprint"))
            for handle in handles
            if handle.manifest.get("graph_fingerprint")
        }
        moved = sorted(theirs - {mine})
        if moved:
            raise ConfigurationError(
                f"The rollouts in {str(run_dir)!r} were produced by a different pipeline: they "
                f"record graph_fingerprint {', '.join(moved)}, and this suite's pipeline is "
                f"{mine}. A number scored from them would describe a shape that never ran, and "
                f"the results file would not say so (FT-15).\n"
                f"Score them with the pipeline that produced them, or run the evaluation again "
                f"under the current one."
            )
        self._refuse_a_moved_configuration(handles, run_dir)
        self._warn_a_moved_declaration(handles, run_dir)

    def _refuse_a_moved_configuration(self, handles: Sequence[Any], run_dir: Path) -> None:
        """Refuse rollouts run at other sampling parameters, tools, budgets or `allow_unknown`.

        The shape is the same, so `graph_fingerprint` cannot tell these apart. What the run
        recorded is compared with what this suite declares, field by field, and the refusal
        names the fields rather than two digests.
        """
        now = _measured_configuration(self.pipeline)
        for handle in handles:
            was = _measured_configuration_of(handle.manifest)
            if not any(was.values()):
                continue
            differences = config_differences(was, now)
            if not differences:
                continue
            shown = "\n".join(
                f"  {path}: {before!r} -> {after!r}"
                for path, (before, after) in sorted(differences.items())[:5]
            )
            more = len(differences) - 5
            raise ConfigurationError(
                f"The rollouts in {str(run_dir)!r} ran under a different configuration. The "
                f"graph is the same shape, and {len(differences)} field(s) that decide what "
                f"was measured are not. A number scored from them would describe a "
                f"configuration that never ran, and the results file would carry this suite's "
                f"rather than theirs (FT-15).\n"
                f"{shown}" + (f"\n  and {more} more" if more > 0 else "") + "\n"
                "Score them with the configuration that produced them, or run the evaluation "
                "again under the current one, which writes its own directory."
            )

    def _warn_a_moved_declaration(self, handles: Sequence[Any], run_dir: Path) -> None:
        """Report a declared version that stayed put while the source under it moved (FT-15).

        A declared version is what decides identity, so an edit made under one is not a
        different evaluation and is not refused. It is also the one change nothing else traces:
        the directory name, the fingerprint and the field-by-field comparison all read the
        declaration. This reads the hash recorded beside it.
        """
        now = _declarations_of(self.pipeline)
        moved: dict[str, tuple[str, str, Any]] = {}
        for handle in handles:
            moved.update(_held_declarations(_declarations_in(handle.manifest), now))
        if not moved:
            return
        shown = "\n".join(
            f"  {where}: version {version!r} held, source {was} -> {then}"
            for where, (was, then, version) in sorted(moved.items())[:5]
        )
        more = len(moved) - 5
        warnings.warn(
            f"{len(moved)} declaration(s) in {str(run_dir)!r} name a version that has not "
            f"moved while the source under it has. The rollouts being read ran the earlier "
            f"source, so a figure that changes is attributable to nothing (FT-15).\n"
            f"{shown}" + (f"\n  and {more} more" if more > 0 else "") + "\n"
            "Bump the declared version so the change is traceable, or leave it as it is if "
            "the edit changed no behaviour.",
            SimpleAgentsWarning,
            stacklevel=4,
        )

    @staticmethod
    def _recorded_seed(found: Sequence[tuple[Any, Example, int]]) -> int:
        """The evaluation seed these rollouts ran under, from a rollout's own recorded seed.

        A rollout's seed is derived from the evaluation's, and the derivation does not invert,
        so what is recovered is a seed that reproduces the same intervals rather than the
        integer the evaluation was given. It is recorded as `seed_source: "rollout"` so a
        reader does not take it for the one that would re-run this evaluation.
        """
        for handle, _, _ in found:
            seed = handle.manifest.get("seed")
            if isinstance(seed, int):
                return seed
        return 0

    def _rescored(
        self,
        handle: Any,
        example: Example,
        index: int,
        judgements: Judgements | None = None,
    ) -> RolloutOutcome:
        """One rollout, scored from what its run directory holds.

        A rollout that stopped on a model call the backend never answered is ``no_response``
        here as it was live, so a re-score reproduces the numbers the run reported.
        """
        trajectory = str(handle.trajectory_path)
        failed = not handle.finished
        unanswered = failed and _ended_on_an_unanswered_call(trajectory)
        answer = None if failed else self._answer_of(output_of(self.pipeline, trajectory))
        seed = int(handle.manifest.get("seed") or 0)
        scoring = self._scoring(
            example=example,
            answer=answer,
            rollout=index,
            seed=seed,
            run_id=str(handle.run_id),
            trajectory=trajectory,
            judgements=judgements,
        )
        outcome, verdict = classify(
            scoring, matches=self.matches, criteria=self.criteria, failed=failed
        )
        if unanswered:
            outcome, verdict = Outcome.NO_RESPONSE, None
        observed, unanswered_questions, lost_items, causes = self._observed(
            scoring, Path(trajectory)
        )
        # Read off the trajectory rather than off an exception, so a rescore of a rung sorts
        # the rollout the way the run that made it was sorted.
        if "left_the_slice" in causes:
            outcome, verdict = Outcome.LEFT_THE_SLICE, None
        return self._score(
            RolloutOutcome(
                example_id=example.id,
                rollout=index,
                seed=seed,
                outcome=outcome,
                answer=answer,
                run_id=str(handle.run_id),
                trajectory=trajectory,
                error=None if not failed else {"type": "run", "message": str(handle.outcome)},
                nodes=observed,
                unanswered_consultations=unanswered_questions,
                unreached_items=lost_items,
                left_out=causes,
                verdict=verdict,
            ),
            example,
            judgements,
        )

    # -- one rollout ----------------------------------------------------------------------

    def _slice_record(self) -> dict[str, Any] | None:
        """What the evaluated pipeline is a slice of, or ``None`` where it is a whole one."""
        sliced = getattr(self.pipeline, "slice_of", None)
        return sliced.to_record() if sliced is not None else None

    def _eval_id(
        self,
        eval_seed: int,
        split: str,
        k: int,
        model: ModelClient | None,
        end_user: Any = None,
    ) -> str:
        """A name for this evaluation's directory, derived from what decides what is measured.

        The examples and their labels, the seed, the split, k, the model, who answered the
        consultations, and everything the manifest records about the pipeline: its shape, the
        version of every prompt in it, the sampling parameters and tools of every node,
        `allow_unknown`, and the budgets of the pipeline and of every pipeline used as a node.

        The stand-in end user is in here because it is part of what was measured. Two
        evaluations differing only in which model played the end user would otherwise resolve
        to one directory, and the second would be refused after the first had been paid for.

        Re-running one evaluation writes into one directory. Changing any of those names a
        different directory, so two evaluations that measured different things cannot write
        into one, and `resume_from` and `rescore` refuse rollouts a different configuration
        produced.

        Wider than :meth:`Pipeline.graph_fingerprint`, which is a digest of shape alone and
        answers a different question: whether stored state can still be walked.
        """
        prompts = self.pipeline.manifest_prompts()
        identity = model.identity().to_manifest() if model is not None else None
        material = json.dumps(
            [
                self.examples.content_hash(),
                eval_seed,
                split,
                k,
                self.pipeline.graph_fingerprint(),
                {node: entry.get("version") for node, entry in sorted(prompts.items())},
                identity,
                _measured_configuration(self.pipeline),
                _end_user_identity(end_user),
            ],
            sort_keys=True,
            default=str,
        )
        return f"eval_{hashlib.sha256(material.encode()).hexdigest()[:12]}"

    def _resumed(
        self,
        resume_from: str | os.PathLike[str] | None,
        run_dir: Path,
        chosen: Sequence[Example],
        k: int,
        run_ids: dict[tuple[str, int], str],
        judgements: Judgements | None = None,
    ) -> dict[tuple[str, int], RolloutOutcome]:
        """The rollouts already on disk, scored, keyed by the example and index they ran for.

        Empty where nothing is being resumed. A rollout that never finished is left out and
        its directory removed, because a rollout appends to the trajectory it finds and
        resuming into a half-written one would produce a file holding two runs.
        """
        if resume_from is None:
            return {}
        given = Path(resume_from)
        if given.name != run_dir.name:
            raise ConfigurationError(
                f"resume_from={str(given)!r} is not this evaluation's directory. These "
                f"arguments produce {run_dir.name!r}, and a rollout's seed derives from the "
                f"evaluation's, so rollouts from another one answer different questions under "
                f"different seeds.\n"
                f"Pass the directory this evaluation wrote, or score the other one with "
                f"suite.rescore(run_dir=...) instead."
            )
        if not given.exists():
            raise ConfigurationError(
                f"resume_from={str(given)!r} does not exist, so there is nothing to resume. "
                f"Run the evaluation without resume_from."
            )
        wanted = {run_ids[(example.id, index)] for example in chosen for index in range(k)}
        handles = [h for h in rollouts_under(given) if str(h.run_id) in wanted]
        self._refuse_a_moved_pipeline(handles, given)
        by_name = {run_ids[(e.id, i)]: (e, i) for e in chosen for i in range(k)}
        done: dict[tuple[str, int], RolloutOutcome] = {}
        for handle in handles:
            example, index = by_name[str(handle.run_id)]
            if handle.manifest.get("ended_at") is None:
                shutil.rmtree(Path(handle.trajectory_path).parent, ignore_errors=True)
                continue
            done[(example.id, index)] = self._rescored(handle, example, index, judgements)
        return done

    @staticmethod
    def _refuse_a_used_directory(run_dir: Path) -> None:
        """Refuse to write rollouts beside an earlier evaluation's (FT-15).

        A rollout appends to the trajectory it finds, so a second evaluation writing into the
        same directory produces one file holding two runs: every per-node count doubles, and
        calls from the earlier run are read into this one's cost.
        """
        if not run_dir.exists() or not any(run_dir.iterdir()):
            return
        raise UsedRunDirectory(
            f"{str(run_dir)!r} already holds an evaluation's rollouts. A rollout appends to "
            f"the trajectory it finds, so running into this directory again would produce "
            f"trajectories holding two runs: every per-node count doubles, and the earlier "
            f"run's model calls are read into this one's totals.\n"
            f"Delete the directory to measure again, or pass an envelope with a different "
            f"run_dir so each evaluation keeps its own rollouts. The directory name is "
            f"derived from what decides what is measured, so a changed prompt, split, k, "
            f"seed, model, sampling parameter, tool, budget or allow_unknown already writes "
            f"elsewhere.",
            run_dir=run_dir,
        )

    def _through_the_turns(
        self,
        example: Example,
        *,
        envelope: RunEnvelope,
        model: ModelClient | None,
        seed: int,
        run_id: str,
        concurrency: int,
    ) -> Any:
        """Run one rollout, which is one run unless the example carries a conversation.

        An example naming ``turns`` is a conversation the rollout goes through in order, one
        run per turn, sharing one thread. What the example expects is what the last turn
        answered, so that run's result is what is scored and the earlier turns are what put
        the agent in the state it answered from.

        The turns run in sequence whatever ``concurrency`` says, since turn 3 is answered
        against what turn 2 left behind.
        """
        conversation_id = ROLLOUT_CONVERSATION if envelope.conversations is not None else None
        scope = ROLLOUT_SCOPE if envelope.memory is not None else None
        result = self.pipeline.run(
            example.inputs,
            envelope=_at_turn(envelope, 1),
            model=model,
            seed=seed,
            run_id=run_id if not example.turns else f"{run_id}-t1",
            conversation_id=conversation_id,
            memory_scope=scope,
            concurrency=concurrency,
        )
        for number, said in enumerate(example.turns, start=2):
            result = self.pipeline.run(
                said
                if isinstance(said, dict)
                else {**_as_inputs(example.inputs), **_said(said, example)},
                envelope=_at_turn(envelope, number),
                model=model,
                seed=derive_seed(seed, "turn", number),
                run_id=f"{run_id}-t{number}",
                conversation_id=conversation_id,
                memory_scope=scope,
                concurrency=concurrency,
            )
        return result

    def _rollout(
        self,
        example: Example,
        index: int,
        envelope: RunEnvelope,
        model: ModelClient | None,
        eval_seed: int,
        run_ids: dict[tuple[str, int], str],
        run_concurrency: int = 1,
        end_user: Any = None,
        judgements: Judgements | None = None,
    ) -> RolloutOutcome:
        seed = derive_seed(eval_seed, example.id, index)
        run_id = run_ids[(example.id, index)]
        root = Path(envelope.run_dir) / run_id
        trajectory = str(root / "trajectory.jsonl")
        # The evaluation scoped `run_dir` to its own directory, so its id is that name.
        scoped = _scoped_for_rollout(
            envelope,
            example,
            root,
            end_user=end_user,
            seed=seed,
            eval_id=Path(envelope.run_dir).name,
            rollout=index,
        )

        try:
            result = self._through_the_turns(
                example,
                envelope=scoped,
                model=model,
                seed=seed,
                run_id=run_id,
                concurrency=run_concurrency,
            )
        except RunSuspended:
            # The run stopped to ask a person and its state is on disk. Scoring it would
            # report a failure over a rollout that is waiting rather than finished, so it
            # reaches the caller, which `docs/evaluation.md` §7.4 states.
            raise
        except ConfigurationError:
            # The project is wired up wrongly, which fails identically on every rollout, so
            # one is enough to know and the other k×n are not paid for.
            raise
        except StreamUsageMissing:
            # The client reports no token counts on a streamed call, on every call it makes.
            raise
        except Exception as exc:
            return self._failed_rollout(
                example,
                index,
                seed=seed,
                run_id=run_id,
                trajectory=trajectory,
                outcome=_outcome_for(exc, trajectory),
                exc=exc,
                judgements=judgements,
            )

        try:
            answer = self._answer_of(result.output)
        except ConfigurationError:
            # The same mismatch fails every rollout, so it ends the evaluation rather than
            # being recorded as k×n agent failures.
            raise
        except Exception as exc:
            return self._failed_rollout(
                example,
                index,
                seed=seed,
                run_id=result.run_id,
                trajectory=str(result.trajectory_path),
                outcome=Outcome.FAILED,
                exc=exc,
                judgements=judgements,
            )

        scoring = self._scoring(
            example=example,
            answer=answer,
            rollout=index,
            seed=seed,
            run_id=result.run_id,
            trajectory=str(result.trajectory_path),
            judgements=judgements,
        )
        outcome, verdict = classify(scoring, matches=self.matches, criteria=self.criteria)
        observed, unanswered_questions, lost_items, causes = self._observed(
            scoring, result.trajectory_path
        )
        return self._score(
            RolloutOutcome(
                example_id=example.id,
                rollout=index,
                seed=seed,
                outcome=outcome,
                answer=answer,
                run_id=result.run_id,
                trajectory=str(result.trajectory_path),
                nodes=observed,
                unanswered_consultations=unanswered_questions,
                unreached_items=lost_items,
                left_out=causes,
                verdict=verdict,
            ),
            example,
            judgements,
        )

    def _failed_rollout(
        self,
        example: Example,
        index: int,
        *,
        seed: int,
        run_id: str,
        trajectory: str,
        outcome: Outcome,
        exc: Exception,
        judgements: Judgements | None,
    ) -> RolloutOutcome:
        """One rollout whose run raised, scored from whatever it left on disk."""
        observed, unanswered_questions, lost_items, causes = self._observed(
            self._scoring(
                example=example,
                answer=None,
                rollout=index,
                seed=seed,
                run_id=run_id,
                trajectory=trajectory,
                judgements=judgements,
            ),
            Path(trajectory),
        )
        return self._score(
            RolloutOutcome(
                example_id=example.id,
                rollout=index,
                seed=seed,
                outcome=outcome,
                run_id=run_id,
                trajectory=trajectory,
                error=error_object(exc, model_facing=False),
                nodes=observed,
                unanswered_consultations=unanswered_questions,
                unreached_items=lost_items,
                left_out=causes,
            ),
            example,
            judgements,
        )

    def _criteria_record(self, judgements: Judgements | None = None) -> dict[str, Any]:
        """Each criterion the example set names, its text, and what decided it.

        A coded condition records the version of its check. A judged one has no check to
        version, and what its figure rests on is the judgements themselves, so it records the
        deciders, the judging runs and a digest of the judgements this evaluation used. Either
        way `compare()` withholds its verdict when what decided the condition moved.

        A judged condition also records its text for comparison, because the text is the
        question the judge was asked: rewording it asks something else. A coded condition's
        text is documentation and its check is the rule, so the text is recorded and not
        compared, and a typo fix does not withhold a verdict.
        """
        found: dict[str, Any] = {}
        for criterion_id, text in sorted(self.criterion_texts.items()):
            check = self.criteria.get(criterion_id)
            if isinstance(check, Judged):
                found[criterion_id] = {
                    "text": text,
                    "decided": "judged",
                    **(judgements.to_record(criterion_id) if judgements is not None else {}),
                }
            else:
                found[criterion_id] = {
                    "text": text,
                    "decided": "code",
                    **source_version(check),
                }
        return found

    # -- judgements ---------------------------------------------------------------------------

    def _judgements(self, *, run_dir: Path | None = None) -> Judgements:
        """What this evaluation reads its judgements out of.

        A run directory holding its own copy is read from that copy, so a rescore reproduces
        the numbers that evaluation reported however the store has moved since. Anything else
        reads the store.
        """
        if run_dir is not None:
            copied = run_dir / JUDGEMENTS_NAME
            if copied.exists():
                return Judgements(found=read_labels(copied))
        return Judgements(found=read_labels(self.judgements_path))

    def unjudged(
        self, *, run_dir: str | os.PathLike[str], split: str
    ) -> tuple[JudgementRequest, ...]:
        """Every answer in this run directory waiting on a judgement.

        The worklist, for judging by hand or in a process of the project's own::

            for want in suite.unjudged(run_dir="runs/eval/eval_a1226bc495df", split="held_out"):
                print(want.describe())
                verdict = input("met? ")
                write_labels("evals/judgements.jsonl",
                             [want.label(verdict == "y", decided_by="human")], append=True)

        Empty where everything is judged. Two rollouts that produced the same answer are one
        entry, since a judgement is about what was judged rather than about where it sat.
        """
        chosen = self.examples.in_split(split)
        found = self._rollouts_on_disk(Path(run_dir), chosen)
        judgements = self._judgements()
        for handle, example, index in found:
            self._rescored(handle, example, index, judgements)
        return judgements.missing

    def judge(
        self,
        *,
        run_dir: str | os.PathLike[str],
        split: str,
        using: Callable[[Sequence[JudgementRequest]], Any],
    ) -> list[Label]:
        """Answer every judgement this run directory is waiting on, and keep them.

        ``using`` is given the **whole worklist** and returns a :class:`Label` per judgement.
        What it does in between is the project's: one model call per answer, one call judging
        twenty, a panel of three voting, or a cheap rule that resolves the clear cases and
        escalates the rest::

            def judge_them(wants):
                result = judging_pipeline.run(
                    {"wants": [{"question": w.question, "answer": w.material} for w in wants]},
                    model=judge, envelope=env.with_role("labelling"),
                )
                return [
                    want.label(verdict.met, decided_by=judge.identity().request_model,
                               reason=verdict.reason, run_id=result.run_id)
                    for want, verdict in zip(wants, result.output.verdicts)
                ]

            suite.judge(run_dir="runs/eval/eval_a1226bc495df", split="held_out", using=judge_them)

        Running the pass as a ``Pipeline`` under an envelope is what makes it recoverable:
        ``run_id`` on each judgement names the run holding the model, the prompt and the cost.

        Judgements are appended to the file ``EvalSuite(judgements=...)`` names, so an earlier
        verdict stays in it and a correction is a later line. Returns what this pass decided.

        Raises :class:`~simple_agents.errors.ConfigurationError` where ``using`` returns
        anything but labels, or a label for something nothing asked about.
        """
        wanted = self.unjudged(run_dir=run_dir, split=split)
        if not wanted:
            return []
        made = self._judged_by(using, wanted)
        write_labels(self.judgements_path, made, append=True)
        return made

    @staticmethod
    def _judged_by(
        using: Callable[[Sequence[JudgementRequest]], Any],
        wanted: Sequence[JudgementRequest],
    ) -> list[Label]:
        """What one judging pass decided, refused unless it answers what was asked."""
        if not callable(using):
            raise ConfigurationError(
                f"judge(using=...) takes a function of one argument, the list of judgements "
                f"waiting, returning a Label for each. It was given "
                f"{type(using).__name__}.\n"
                f"The whole list is passed at once so a pass may batch them, put them to a "
                f"panel, or resolve the clear ones cheaply and escalate the rest."
            )
        produced = list(using(wanted))
        asked = {request.key: request for request in wanted}
        for label in produced:
            if not isinstance(label, Label):
                raise ConfigurationError(
                    f"A judging pass returned {type(label).__name__} where a Label belongs. "
                    f"Build one from the request so it is filed against what was judged: "
                    f"want.label(True, decided_by='human', reason='...')."
                )
            if label.id not in asked:
                raise ConfigurationError(
                    f"A judging pass returned a judgement keyed {label.id!r}, which nothing "
                    f"asked about, so nothing would ever read it. A judgement is keyed on "
                    f"what was judged.\n"
                    f"Build it from the request rather than by hand: "
                    f"want.label(verdict, decided_by=...)."
                )
        return produced

    def _through_judging(
        self,
        rollouts: list[RolloutOutcome],
        chosen: Sequence[Example],
        judgements: Judgements,
        *,
        using: Callable[[Sequence[JudgementRequest]], Any] | None,
        run_dir: Path,
    ) -> tuple[list[RolloutOutcome], Judgements]:
        """Judge whatever the rollouts left waiting, then score them against it.

        The gate sits here, between the rollouts and the numbers, because a judgement is about
        an answer and no answer exists until its rollout has run. Every rollout is finished and
        recorded by this point, so a refusal costs the run and nothing that was paid for: the
        directory holds them and ``rescore`` scores them once the judgements exist.

        A rule that reads a second judgement only reaches it once the first is answered, so
        this rounds until nothing new is asked for. A round that answers none of what it was
        asked ends it: the pass is not going to answer them by being asked again, and asking
        seven more times spends seven more times as much to reach the same refusal.
        """
        unanswered: tuple[JudgementRequest, ...] = ()
        for _ in range(JUDGE_ROUNDS):
            if not judgements.missing or using is None:
                break
            asked = {request.key for request in judgements.missing}
            write_labels(
                self.judgements_path,
                self._judged_by(using, judgements.missing),
                append=True,
            )
            judgements = self._judgements()
            rollouts = [
                self._rescored(handle, example, index, judgements)
                for handle, example, index in self._rollouts_on_disk(run_dir, chosen)
            ]
            rollouts.sort(key=lambda outcome: (outcome.example_id, outcome.rollout))
            still = {request.key for request in judgements.missing}
            if asked - still:
                # The pass answered some of them, so the rest may be a rule reaching its
                # second judgement. Ask again.
                continue
            unanswered = tuple(request for request in judgements.missing if request.key in asked)
            if unanswered:
                break
        refuse_unjudged(
            judgements.missing,
            run_dir=run_dir,
            found=judgements.found,
            unanswered=unanswered,
        )
        self._keep_judgements(run_dir, judgements)
        return rollouts, judgements

    def _keep_judgements(self, run_dir: Path, judgements: Judgements) -> None:
        """Write the judgements this evaluation used beside the rollouts it scored.

        The store keeps growing and a verdict in it can be corrected later. This copy is what
        pins a reported number to what decided it, so `rescore` on this directory gives back
        what the evaluation reported rather than what the store says today.

        **Written once and never replaced.** A later scoring of the same rollouts may read
        fewer conditions, and overwriting would leave the first results file naming judgements
        its own run directory no longer holds. A directory with no copy gets one, which is how
        rollouts recorded before this existed become pinned.
        """
        copied = run_dir / JUDGEMENTS_NAME
        if not judgements.used or copied.exists():
            return
        write_labels(copied, judged_copy(judgements.used.values()))

    def _scoring(
        self,
        *,
        example: Example,
        answer: Any,
        rollout: int,
        seed: int,
        run_id: str | None = None,
        trajectory: str | None = None,
        outcome: Outcome | None = None,
        judgements: Judgements | None = None,
        verdict: Any = None,
    ) -> Scoring:
        """The context every scoring rule is given, for one rollout of one example."""
        return Scoring(
            answer=answer,
            expected=example.expected,
            example=example,
            rollout=rollout,
            seed=seed,
            run_id=run_id,
            trajectory=trajectory,
            outcome=outcome,
            judgements=judgements,
            verdict=verdict,
        )

    # -- project metrics ------------------------------------------------------------------

    def _score(
        self,
        rollout: RolloutOutcome,
        example: Example,
        judgements: Judgements | None = None,
    ) -> RolloutOutcome:
        """Every project metric's score for one rollout, written onto it.

        Scored as the rollout finishes rather than after the whole evaluation, so a scoring
        function that cannot read what the agent produced fails while there are still rollouts
        left to not pay for. It fails the same way on every rollout, so failing on the first is
        the whole of the information.

        Scored here rather than at aggregation time for a second reason: the number travels in
        the results file, so a comparison between two evaluations needs neither the labels nor
        the functions that produced it.
        """
        if not self.metrics and not self.node_metrics:
            return rollout
        scoring = self._scoring_for(rollout, example, judgements)
        scores, ratios = figures_for(self.metrics, scoring, asserted=rollout.asserted)
        return replace(
            rollout,
            scores={**rollout.scores, **scores},
            ratios={**rollout.ratios, **ratios},
            nodes=self._node_scores(rollout, example, judgements),
        )

    def _scoring_for(
        self,
        rollout: RolloutOutcome,
        example: Example,
        judgements: Judgements | None = None,
    ) -> Scoring:
        """The context this rollout's figures are scored against, built once for all of them."""
        return self._scoring(
            example=example,
            answer=rollout.answer,
            rollout=rollout.rollout,
            seed=rollout.seed,
            run_id=rollout.run_id,
            trajectory=rollout.trajectory,
            outcome=rollout.outcome,
            judgements=judgements,
        )

    def _node_scores(
        self,
        rollout: RolloutOutcome,
        example: Example,
        judgements: Judgements | None = None,
    ) -> dict[str, NodeObservation]:
        """Per-node scores, over the rollouts that reached the node and carry a label for it.

        A node put a value forward when its recorded output holds no absence anywhere in it,
        read by the same walk that counts ``absent_outputs``. A node's output is a schema
        object, so an absence sits in a field rather than being the whole value.
        """
        observed = dict(rollout.nodes)
        if not self.node_metrics:
            return observed
        outputs = self._node_outputs(rollout)
        for node_id, declared in self.node_metrics.items():
            seen = observed.get(node_id)
            if seen is None or not seen.reached or node_id not in example.expected_by_node:
                continue
            output = outputs.get(node_id)
            scoring = replace(
                self._scoring_for(rollout, example, judgements),
                answer=output,
                expected=example.expected_by_node[node_id],
                node_id=node_id,
            )
            scores, ratios = figures_for(
                declared,
                scoring,
                asserted=output is not None and not holds_absence(output),
            )
            observed[node_id] = replace(
                seen,
                scores={**seen.scores, **scores},
                ratios={**seen.ratios, **ratios},
            )
        return observed

    def _node_outputs(self, rollout: RolloutOutcome) -> dict[str, Any]:
        """Every node's recorded output on this rollout, read back from its trajectory."""
        if not rollout.trajectory or not Path(rollout.trajectory).exists():
            return {}
        return {
            str(record.get("node_id")): decode_answer(record.get("outputs"))
            for record in read_trajectory(rollout.trajectory)
            if record.get("record_type") == "node_execution"
            and record.get("termination") != "skipped"
        }

    def _observed(
        self, scoring: Scoring, trajectory: Path
    ) -> tuple[dict[str, NodeObservation], int, int, tuple[str, ...]]:
        """What each node did on this rollout: whether it ran, and whether it was right.

        The output compared is the one written to the trajectory rather than the object the
        node returned, so the same comparison can be made again from a results file and a run
        directory long after the process that produced them has gone.

        A rollout that failed is read the same way. A run that stopped partway still reached
        the nodes before the one that stopped it, and `reach` is over all rollouts, so reading
        nothing for them would report every node as reached exactly as often as the rollout
        succeeded. An empty mapping comes back only where no trajectory was written.
        """
        if not Path(trajectory).exists():
            return {}, 0, 0, ()
        example = scoring.example
        records = list(read_trajectory(trajectory))
        reached = reached_in(records)
        outputs = {
            str(r.get("node_id")): decode_answer(r.get("outputs"))
            for r in records
            if r.get("record_type") == "node_execution" and r.get("termination") != "skipped"
        }
        found: dict[str, NodeObservation] = {}
        for node_id, _ in self.pipeline.declared_nodes():
            matched: bool | None = None
            compare = self.node_matches.get(node_id)
            if compare is not None and node_id in example.expected_by_node and node_id in reached:
                matched = _call(
                    compare,
                    replace(
                        scoring,
                        answer=outputs.get(node_id),
                        expected=example.expected_by_node[node_id],
                        node_id=node_id,
                        outcome=None,
                    ),
                    what=f"node_matches[{node_id!r}]",
                )
            found[node_id] = NodeObservation(reached=node_id in reached, matched=matched)
        return (
            found,
            _unanswered_in(records),
            _unreached_items_in(records),
            _left_out_of(records),
        )

    def _answer_of(self, output: Any) -> Any:
        """The asserted answer, read off the pipeline's output by name or by the function.

        A named answer that the output does not carry raises ``ConfigurationError`` rather
        than failing the rollout: the same mismatch would fail every rollout, so the
        evaluation stops before the rest are paid for.
        """
        if callable(self.answer):
            return self.answer(output)
        if output is None:
            return None
        if isinstance(output, Unknown):
            # The whole output is a reported absence, so it is the answer: the rollout
            # classifies as an abstention rather than as a failure to produce one.
            return output
        name = str(self.answer)
        if isinstance(output, Mapping):
            if name in output:
                return output[name]
            raise ConfigurationError(
                f"EvalSuite(answer={name!r}) names a key the pipeline's output does not "
                f"carry. The output is a {type(output).__name__} with keys: "
                f"{', '.join(sorted(str(k) for k in output)) or '(none)'}. Every rollout "
                f"would fail on this before anything is scored.\n"
                f"Pass answer= one of those keys, or a function over the output: "
                f"answer=lambda output: output['...']."
            )
        if hasattr(output, name):
            return getattr(output, name)
        raise ConfigurationError(
            f"EvalSuite(answer={name!r}) names a field the pipeline's output does not "
            f"carry. The output is {type(output).__name__}, whose fields are: "
            f"{', '.join(sorted(vars(output))) if hasattr(output, '__dict__') else '(none readable)'}. "
            f"Every rollout would fail on this before anything is scored.\n"
            f"Pass answer= one of those fields, or a function over the output: "
            f"answer=lambda output: output.value."
        )

    # -- refusals -------------------------------------------------------------------------

    def _refuse_an_undescribed_end_user(self, end_user: Any, chosen: Sequence[Example]) -> None:
        """Refuse a stand-in end user with an example that does not say who they are.

        The stand-in answers as the person the example describes. Given no description it
        writes what an assistant would say, which is agreeable, articulate and nothing like
        the people the agent is for, and every rate computed over it is a rate against that
        (FT-24).

        Checked before the first rollout rather than at the consultation, so the k×n runs are
        not paid for first, and only where the pipeline can consult at all. A run answering
        more than one person needs a description for each name its consult tools reach.
        """
        playing = [
            one
            for one in (end_user.values() if isinstance(end_user, Mapping) else [end_user])
            if getattr(one, "playing", None) is not None
        ]
        if not playing:
            return
        consulting = [t for t in _tools_of(self.pipeline) if isinstance(t, ConsultTool)]
        if not consulting:
            return

        if isinstance(end_user, Mapping):
            # The same refusal `for_one_call` makes, made before the rollouts are paid for.
            for tool in consulting:
                tool._channel_in(end_user)
            wanted = sorted({str(name) for name in end_user})
            missing = [
                f"{example.id} ({', '.join(described(example.end_user, wanted))})"
                for example in chosen
                if described(example.end_user, wanted)
            ]
            correction = (
                f"Describe each: Example(..., end_user={{"
                f"{', '.join(f'{name!r}: EndUser(...)' for name in wanted[:2])}"
                f"{', ...' if len(wanted) > 2 else ''}}}). The names are the ones the consult "
                f"tools declare in reaches=."
            )
        else:
            named = [e.id for e in chosen if isinstance(e.end_user, Mapping)]
            if named:
                raise ConfigurationError(
                    f"{len(named)} of {len(chosen)} examples describe an answerer by name, and "
                    f"this evaluation was given one channel for all of them. Which of those "
                    f"people it plays is undeclared: {', '.join(named[:5])}"
                    f"{' and others' if len(named) > 5 else ''}.\n"
                    f"Pass one per name: suite.run(..., end_user={{'requester': "
                    f"SimulatedEndUser(model=cheap), 'approver': "
                    f"SimulatedEndUser(model=cheap)}}). The names are the ones the consult "
                    f"tools declare in reaches=."
                )
            missing = [
                example.id
                for example in chosen
                if not str(getattr(example.end_user, "description", "") or "").strip()
            ]
            correction = (
                "Describe them: Example(..., end_user='Reads a lot of grimdark, wants "
                "something under 400 pages, and finds questions about difficulty useless and "
                "says so')."
            )
        if not missing:
            return
        named = ", ".join(missing[:5]) + (" and others" if len(missing) > 5 else "")
        raise ConfigurationError(
            f"{len(missing)} of {len(chosen)} examples do not say who the agent is answering, "
            f"and this evaluation answers its consultations with a model playing that person: "
            f"{named}. With nothing to play, the model answers as an assistant would, and the "
            f"agent is measured against a reader more agreeable than any it will meet.\n"
            f"{correction} To measure the agent against the project's own channel instead, "
            f"drop end_user= from this call."
        )

    def _refuse_bad_k(self, k: int) -> None:
        if isinstance(k, int) and k >= 1:
            return
        raise ConfigurationError(
            f"EvalSuite.run(k={k!r}) needs a whole number of rollouts per example, at least 1. "
            f"Start at k=5: agents are stochastic, and run-to-run variance is routinely larger "
            f"than the effect being measured, so a single rollout cannot tell a real "
            f"improvement from noise (FT-05)."
        )

    def _refuse_sampled_trajectory(self, envelope: RunEnvelope) -> None:
        if not envelope.trajectory.samples:
            return
        raise ConfigurationError(
            f"This evaluation runs through an envelope with "
            f"Trajectory.sampled({envelope.trajectory.rate}), which drops the payload fields "
            f"on most rollouts. Per-node accuracy and `absent_outputs` are read back out of "
            f"each rollout's trajectory, so a sampled evaluation reports numbers computed "
            f"from records that no longer hold what the nodes produced.\n"
            f"Pass an envelope with Trajectory.full() here, and keep the sampled one for "
            f"production runs: envelope.with_trajectory(Trajectory.full())."
        )

    def _refuse_contaminated_split(self, *, split: str, examples: int, k: int) -> None:
        """Refuse a split whose two sides overlap, before the rollouts are paid for (FT-03).

        The report is written into the results file either way, so without this the project
        learns that its number was measured over a contaminated split from a file it produced
        by running the whole evaluation.

        Only pairs with one side in ``split`` are refused. An overlap between two other splits
        cannot reach this number, and refusing the run for it costs the project an evaluation
        over material it is not measuring. The results file still records the whole report.
        """
        if self.contamination_threshold is None:
            return
        report = self.examples.contamination(threshold=self.contamination_threshold)
        reaching = [pair for pair in report.pairs if split in (pair.left_split, pair.right_split)]
        if not reaching:
            return
        shown = "\n".join(f"  {pair.detail}" for pair in reaching[:5])
        more = len(reaching) - 5
        raise ConfigurationError(
            f"{len(reaching)} pair(s) of examples fall on both sides of this split at "
            f"threshold {self.contamination_threshold}, so a number measured over it reports "
            f"memorisation of material the dev side may be tuned against (FT-03). This "
            f"evaluation would be {examples * k} rollout(s) producing that number.\n"
            f"{shown}" + (f"\n  and {more} more" if more > 0 else "") + "\n"
            "A `shared_source` pair is two examples drawn from one `source`, so assign whole "
            "sources to a split rather than drawing examples independently. A "
            "`near_duplicate` pair is the same content under two ids, so drop one side.\n"
            "Pass allow_contaminated_split=True to measure over it anyway, or "
            "contamination_threshold=None to the suite to decide what counts as too similar "
            "some other way."
        )

    def _refuse_mixed_cassette(self, envelope: RunEnvelope) -> None:
        if envelope.cassette.mode.value != "update":
            return
        raise ConfigurationError(
            "This evaluation runs with Cassette.update, which serves the calls already on file "
            "and makes live calls for the rest. A reported number would then come partly from "
            "responses recorded earlier and partly from responses produced now, with no way to "
            "say which rollouts were which.\n"
            "Use Cassette.record(path) to measure against the live backend, or "
            "Cassette.replay(path) to measure against a recording. Cassette.update is for "
            "iterating on a pipeline between evaluations.\n"
            "Pass allow_mixed_cassette=True to run it anyway, which is what a sweep does when "
            "its arms share one file and the number compares the arms rather than the backend."
        )

    @staticmethod
    def _refuse_an_ambiguous_recording(envelope: RunEnvelope) -> None:
        """Refuse a replay whose file answers one tool call two ways.

        A tool call is keyed on its name, its version, its arguments and how many times that
        same call has been made in this run. Two rollouts making the identical call therefore
        share a key, which is what lets one recorded answer serve all k of them (FT-20). Where
        the recording holds more than one response under that key, the tool answered the same
        request differently, so the key does not identify the answer and replay would serve the
        first rollout's value to every rollout with nothing saying it had.

        Model calls are not read here. A hosted backend answering one request two ways is
        ordinary, and the manifest's `diverged` count is what reports it.
        """
        if not envelope.cassette.is_replaying:
            return
        ambiguous = sorted(
            {
                group[0].request.get("tool_name", group[0].node_id)
                for group in envelope.cassette.variants().values()
                if group and group[0].kind == "tool_call" and len(group) > 1
            }
        )
        if not ambiguous:
            return
        raise ConfigurationError(
            f"Evaluation refused to run: the recording answers one call to "
            f"{', '.join(repr(name) for name in ambiguous)} in more than one way, under a "
            f"single key. A tool call is keyed on its arguments and not on which rollout made "
            f"it, so replay would serve the first recorded answer to every rollout and report "
            f"a number built on one rollout's value.\n"
            f"A tool whose answer depends on anything but its arguments has to take a handle, "
            f"which makes it run again rather than be served: ModelHandle for a model call, "
            f"Workspace for the run's files, Memory for what the agent remembers, and "
            f"Annotated[<type>, NodeInput()] for the node's own input, which is what differs "
            f"between one rollout and the next (docs/tools.md §3.2). Record the cassette "
            f"again once it does."
        )

    ANSWERS_WITHOUT_A_PERSON = ("simulated", "canned", "nobody")
    """The channels a rollout may run through. Each answers without anybody being asked."""

    def _refuse_a_live_consultation(
        self, envelope: RunEnvelope, end_user: Any, examples: int, k: int, *, verb: str
    ) -> None:
        """Refuse a rollout that would put k×n real questions to a person.

        A consultation reaches outside the run the way a paid tool does: one rollout asks, and
        an evaluation of n examples at k rollouts asks n×k times. ``consult`` is declared
        ``read_only`` because this is checked here, and the declaration a channel already
        carries is what it reads.

        Passing ``end_user=`` is the waiver, whether that is a stand-in or the registered
        channel handed back. Replay never reaches a channel at all.
        """
        if envelope.cassette.is_replaying or end_user is not None:
            return
        reaching = [
            tool
            for tool in _tools_of(self.pipeline)
            if isinstance(tool, ConsultTool)
            and tool.answered_by not in self.ANSWERS_WITHOUT_A_PERSON
        ]
        if not reaching:
            return
        named = ", ".join(f"{tool.name!r} (answered_by {tool.answered_by!r})" for tool in reaching)
        raise ConfigurationError(
            f"Evaluation refused to {verb}: {named} asks a person, and this evaluation is "
            f"{examples * k} rollout(s) ({examples} examples × {k}), each of which may ask "
            f"more than once. Every question would be put for real, and the answers would "
            f"decide what the rollouts measured.\n"
            f"Answer them with a stand-in: suite.{verb}(..., "
            f"end_user=SimulatedEndUser(model=cheap)), which answers as the person each "
            f"example describes and is recorded as `simulated` (`docs/evaluation.md` §5.4). "
            f"Where nobody should be asked at all, unattended() answers `Unavailable`. Where "
            f"the questions are meant to reach a person, pass that channel here with its own "
            f"declaration on it: ask_in_chat.answered_by = 'end_user', then "
            f"suite.{verb}(..., end_user=ask_in_chat)."
        )

    def _refuse_unsafe_tools(
        self,
        envelope: RunEnvelope,
        *,
        examples: int,
        k: int,
        max_spend: float | None,
        verb: str,
    ) -> None:
        """Refuse a rollout over a tool whose effects reach outside the run (FT-20).

        Replay never executes such a tool, since the call is served from the file. Every other
        mode would perform it in every rollout, so the two classes are separated by what a
        builder can do about it: an ``irreversible`` tool is refused outright, and a
        ``spends_money`` tool runs under a declared ``max_spend``.
        """
        if envelope.cassette.is_replaying:
            return
        paid: list[Tool] = []
        for tool in _tools_of(self.pipeline):
            if tool.side_effect_class is SideEffectClass.IRREVERSIBLE:
                raise ConfigurationError(
                    f"Evaluation refused to {verb}: tool {tool.name!r} is declared "
                    f"irreversible and this evaluation is {examples * k} rollout(s) "
                    f"({examples} examples × {k}), each of which may call it more than once. "
                    f"{_UNSAFE_FOR_ROLLOUTS} There is no ceiling for this class, because an "
                    f"action that cannot be undone cannot be bounded by declaring how many of "
                    f"them are acceptable.\n"
                    f"Record the calls once with suite.record(...) and evaluate against the "
                    f"recording with Cassette.replay(path), where the tool is served from the "
                    f"file and its body never runs. If the tool's effects are confined to the "
                    f"run, declare READ_ONLY, or WRITES for one that only writes inside the "
                    f"run's workspace."
                )
            if tool.side_effect_class is SideEffectClass.SPENDS_MONEY:
                paid.append(tool)
        if not paid or max_spend is not None:
            return
        prices = ", ".join(
            f"{tool.name!r} at up to {tool.declared_cost.ceiling} "
            f"{tool.declared_cost.currency} a call"
            for tool in paid
            if tool.declared_cost is not None and tool.declared_cost.ceiling is not None
        )
        raise ConfigurationError(
            f"Evaluation refused to {verb}: {_named(paid)} declared spends_money, and this "
            f"evaluation is {examples * k} rollout(s) ({examples} examples × {k}), each of "
            f"which may call it more than once. {_UNSAFE_FOR_ROLLOUTS} The acceptable spend "
            f"is undeclared, so the run would spend an amount decided by how often the agent "
            f"reaches for the tool: {prices}.\n"
            f"Say how much: suite.{verb}(..., max_spend=0.50) is the most this evaluation may "
            f"cost, model calls and paid calls together, and it is checked before the first "
            f"rollout. The cheaper path is to buy each distinct call once: "
            f"suite.record(...) makes the live runs and suite.run(..., "
            f"Cassette.replay(path)) replays them, and a repeated call is served from the file "
            f"rather than bought again."
        )

    def _refuse_an_unaffordable_ceiling(
        self,
        envelope: RunEnvelope,
        *,
        examples: int,
        k: int,
        max_spend: float | None,
        verb: str,
    ) -> None:
        """Refuse a ceiling the pipeline's budget cannot be shown to hold to.

        One rollout is bounded by the pipeline's ``max_cost``, which depletes on what a tool
        meters and on what a model call costs, inside a delegate as well as outside one. So
        ``examples × k × max_cost`` bounds the whole evaluation and is checked here, before
        anything runs. Nothing is checked during the evaluation, and nothing binds part-way
        through it.

        A replay is not checked, because a served call makes no request and spends nothing.
        """
        if max_spend is None or envelope.cassette.is_replaying:
            return
        currency = _currency_of(envelope, self.pipeline)
        unit = f" {currency}" if currency else ""
        max_cost = self.pipeline.budget.max_cost
        if max_cost is None:
            raise ConfigurationError(
                f"Evaluation refused to {verb}: max_spend={max_spend}{unit} is the most this "
                f"evaluation may cost, and the pipeline's budget sets max_cost=None, so one "
                f"rollout is unbounded and {examples * k} of them cannot be bounded either.\n"
                f"Set the per-rollout limit the ceiling is built from: "
                f"Budget(max_steps=..., max_tokens=..., "
                f"max_cost={max_spend / max(1, examples * k):.6f}, max_wall_clock_ms=...) on "
                f"the pipeline gives {examples} examples × {k} rollouts a total of "
                f"{max_spend}{unit}."
            )
        bound = examples * k * max_cost
        if bound <= max_spend:
            return
        raise ConfigurationError(
            f"Evaluation refused to {verb}: {examples} examples × {k} rollouts at "
            f"max_cost={max_cost}{unit} each can cost {bound:.6f}{unit}, and max_spend is "
            f"{max_spend}{unit}. The ceiling is checked here rather than during the "
            f"evaluation, so an evaluation that starts is one whose spend is already "
            f"bounded.\n"
            f"Raise max_spend to {bound:.6f}{unit}, lower the pipeline's max_cost to "
            f"{max_spend / (examples * k):.6f}{unit}, or run fewer rollouts. A rollout can "
            f"still pass max_cost by one model call, whose cost is known only after it "
            f"returns, and by whatever a tool meters above its own declared_cost."
        )

    def _refuse_an_unservable_recording(
        self,
        envelope: RunEnvelope,
        *,
        chosen: Sequence[Example],
        k: int,
        eval_seed: int,
        given_seed: int | None,
    ) -> None:
        """Refuse a replay whose recording was not made at the seeds these rollouts will use.

        A model call's cassette key carries the seed the request was sent with, and a rollout's
        seed derives from the evaluation's seed, the example's id and the rollout index. A
        recording made at other seeds therefore misses on every model call, and a missed
        rollout is a failed rollout rather than an error: without this the evaluation completes
        and reports a rate over rollouts that all failed.

        Only a pipeline that can call a model is checked. A tool call's key carries no seed, so
        a recording of tool calls alone serves whatever seed the rollouts run at.
        """
        if not envelope.cassette.is_replaying:
            return
        if not any(
            node.node_kind in ("llm", "agent") for _, node in self.pipeline.declared_nodes()
        ):
            return
        recorded = envelope.cassette.recorded_seeds()
        if not recorded:
            # A file recorded before seeds were stored names none. Nothing can be concluded
            # from that, and refusing it would refuse a recording that may serve perfectly.
            return
        wanted = {
            derive_seed(eval_seed, example.id, index) for example in chosen for index in range(k)
        }
        missing = wanted - recorded
        if not missing:
            return
        seeded = (
            f"This evaluation runs at seed={eval_seed}"
            if given_seed is not None
            else f"This evaluation was given no seed and generated {eval_seed}"
        )
        raise ConfigurationError(
            f"Evaluation refused to run: the recording at "
            f"{str(envelope.cassette.path)!r} cannot serve {len(missing)} of "
            f"{len(wanted)} rollout(s). {seeded}, and each rollout's seed derives from it, "
            f"the example's id and the rollout index; a model call is recorded under the seed "
            f"it was sent with. Those rollouts would miss on their first model call, fail, and "
            f"be scored as failures rather than raising, so the evaluation would report a rate "
            f"measured over runs that never happened.\n"
            f"Make the recording with suite.record(envelope=..., model=..., split=..., k={k}), "
            f"which runs each rollout live at the seed it will replay at and returns the seed "
            f"to pass here. Where the recording already exists, pass the seed it was made at."
        )

    def _run_ids(self, chosen: Sequence[Example], k: int) -> dict[tuple[str, int], str]:
        """A readable directory name per rollout, refusing two that would collide.

        The example's id names the directory, so a result in the report is found by looking
        for it. Two ids differing only in a character a path cannot hold would land in one
        directory and overwrite each other.
        """
        taken: dict[str, str] = {}
        ids: dict[tuple[str, int], str] = {}
        for example in chosen:
            safe = _SAFE_NAME.sub("_", example.id).strip("_") or "example"
            clash = taken.get(safe)
            if clash is not None and clash != example.id:
                raise ConfigurationError(
                    f"Examples {clash!r} and {example.id!r} both name the run directory "
                    f"{safe!r}, so their rollouts would overwrite each other. Rename one so "
                    f"the two differ in letters, digits, dots, dashes or underscores."
                )
            taken[safe] = example.id
            for index in range(k):
                ids[(example.id, index)] = f"{safe}-{index}"
        return ids

    # -- what was measured ----------------------------------------------------------------

    def _declared_config(
        self,
        *,
        split: str,
        judgements: Judgements | None,
        resamples: int,
        confidence: float,
        seed: int,
    ) -> dict[str, Any]:
        """What the suite declares, identical however the rollouts were produced.

        One record shared by :meth:`_config` and :meth:`_rescored_config`, so a key added to
        what an evaluation declares appears in both results files. What differs between the
        two, which is where the rollouts came from and what ran, stays in each method.
        """
        return {
            "example_set": {
                "content_hash": self.examples.content_hash(),
                "splits": self.examples.splits(),
                # Which split may not be inspected, so a reader of the file knows what the
                # reported number was measured over without knowing the project's naming
                # (FT-02).
                "held_out": self.examples.held_out,
                "absent_proportion": self.examples.absent_proportion(split),
            },
            # A change to what counts as a correct answer moves every rate, and versioning it
            # the way a prompt is versioned is what puts it in compare()'s `changed` (FT-15).
            # It is also what makes a comparison withhold its verdict when the rule moved
            # between the two evaluations rather than the agent.
            "matches": source_version(self.matches),
            # The floor is scored by the same rules as the agent, so an edit to what doing
            # nothing answers moves it the way an edit to `matches` moves every rate.
            "baseline": (source_version(self.baseline) if self.baseline is not None else None),
            # Each criterion's text and the version of the check that decided it. A criterion
            # is data in the example file and its check is code here, so an edit to a check
            # moves every rate with nothing recording that the rule changed unless the version
            # travels beside it (FT-15).
            "criteria": self._criteria_record(judgements),
            # Every judgement any figure rested on, so one that has no entry of its own
            # cannot move without `compare()` seeing it.
            "judgements": (
                judgements.to_record() if judgements is not None and judgements.used else None
            ),
            # Each project metric's declaration and the version of the function that scored
            # it, for the same reason.
            "metrics": [m.to_record() for m in self.metrics],
            "node_metrics": {
                node_id: [m.to_record() for m in declared]
                for node_id, declared in sorted(self.node_metrics.items())
            },
            "bootstrap": {"resamples": resamples, "confidence": confidence, "seed": seed},
            # A nested pipeline is expanded into its own nodes, so these are the ids the
            # per-node figures are keyed on. The same entries the manifest records, because a
            # difference `compare()` cannot see is a moved number with no candidate cause
            # (FT-15), and two shapes for one thing is how they came to differ.
            # `_without_derived`: the hash beside a declared version says an edit happened and
            # not that a different thing was measured, and where nothing was declared it equals
            # `version`, so `compare()` would name every prompt edit twice. `prompt_differences`
            # and the resume warning are what read it.
            # What the evaluated pipeline is a slice of, and `null` where it is whole. Two
            # rungs of one pipeline are joined on `of`, which is what puts a ladder of them in
            # order rather than leaving four unrelated evaluations.
            "slice": self._slice_record(),
            "nodes": _without_derived(self.pipeline.manifest_nodes()),
            # What each pipeline used as a node declares, which is on no entry in `nodes`: its
            # budget, and its edges in the graph that holds it. Without it a sub-pipeline that
            # was rewired or rebudgeted between two evaluations is a moved number with nothing
            # to trace it to.
            "containers": self.pipeline.manifest_containers(),
            # The digest of the shape these numbers were measured over. A reader with the
            # results file alone can then ask whether the pipeline changed since, without
            # opening a run directory (FT-12).
            "graph_fingerprint": self.pipeline.graph_fingerprint(),
            "tools": [
                {
                    "name": t.name,
                    "version": t.version,
                    "side_effect_class": t.side_effect_class.value,
                }
                for t in _tools_of(self.pipeline)
            ],
            "budget": self.pipeline.budget.to_record(),
        }

    def _config(
        self,
        *,
        split: str,
        chosen: Sequence[Example],
        k: int,
        seed: int,
        envelope: RunEnvelope,
        model: ModelClient | None,
        concurrency: int,
        run_concurrency: int,
        resamples: int,
        confidence: float,
        rollouts: Sequence[RolloutOutcome],
        max_spend: float | None,
        judgements: Judgements | None = None,
    ) -> dict[str, Any]:
        return {
            "split": split,
            "k": k,
            "n": len(chosen),
            "seed": seed,
            "concurrency": concurrency,
            "run_concurrency": run_concurrency,
            **self._declared_config(
                split=split,
                judgements=judgements,
                resamples=resamples,
                confidence=confidence,
                seed=seed,
            ),
            # What produced these numbers, at the width a manifest records it. The declared
            # shape is identical across an edited prompt, a changed temperature and a swapped
            # model, so it cannot say that the pipeline the file describes is gone (FT-37).
            "behaviour_fingerprint": self._behaviour_fingerprint(model),
            "prompts": _without_derived(_prompts_of(rollouts)),
            "model": model.identity().to_manifest() if model is not None else None,
            "cost_basis": basis_to_manifest(envelope.cost_basis),
            "cassette": {
                **envelope.cassette.to_manifest(),
                **_cassette_counts(rollouts),
            },
            # The ceiling this number was measured under, and `null` where none was declared.
            # A rate measured with a paid tool running live was bounded by something, and a
            # reader of the file cannot tell what from the budget alone (FT-27).
            "max_spend": max_spend,
            "scored_from": "rollouts",
            "seed_source": "evaluation",
        }

    def _behaviour_fingerprint(self, model: ModelClient | None) -> str | None:
        """The stamp of what produced these numbers, or ``None`` where it cannot be taken.

        :meth:`Pipeline.behaviour_fingerprint` refuses where a node takes the run's model and
        none was given, rather than returning a stamp that would not move when the model
        changed. A results file recording ``null`` says the stamp could not be taken, and
        FT-37 reports that as blocked rather than as a match.
        """
        try:
            return self.pipeline.behaviour_fingerprint(model)
        except ConfigurationError:
            return None

    def _rescored_config(
        self,
        *,
        split: str,
        chosen: Sequence[Example],
        k: int,
        seed: int,
        found: Sequence[tuple[Any, Example, int]],
        rollouts: Sequence[RolloutOutcome],
        resamples: int,
        confidence: float,
        judgements: Judgements | None = None,
    ) -> dict[str, Any]:
        """The config of a results file scored from run directories rather than from a run.

        What the rollouts recorded is read off their manifests. What describes running an
        evaluation, rather than the rollouts themselves, is `null`: nothing ran here, so
        `concurrency` and `max_spend` would be inventions. `scored_from` says which this is,
        so a reader of the file does not have to infer it.
        """
        first = found[0][0].manifest if found else {}
        scored = {rollout.example_id for rollout in rollouts}
        expected = len(chosen) * k
        return {
            "split": split,
            "k": k,
            # The examples the number is over, which is not the whole split when the
            # evaluation stopped before running all of them. `incomplete` below says so.
            "n": len(scored),
            "seed": seed,
            "concurrency": None,
            "run_concurrency": None,
            "incomplete": (
                None
                if len(scored) == len(chosen) and len(rollouts) == expected
                else {
                    "examples_in_split": len(chosen),
                    "examples_scored": len(scored),
                    "rollouts_expected": expected,
                    "rollouts_scored": len(rollouts),
                }
            ),
            **self._declared_config(
                split=split,
                judgements=judgements,
                resamples=resamples,
                confidence=confidence,
                seed=seed,
            ),
            # The rollouts' own, not this pipeline's: re-scoring runs nothing, so what produced
            # these numbers is what the manifests beside them record (FT-37).
            "behaviour_fingerprint": first.get("behaviour_fingerprint"),
            "prompts": _without_derived(dict(first.get("prompts") or {})),
            "model": (first.get("models") or [None])[0]
            if isinstance(first.get("models"), list)
            else first.get("models"),
            "cost_basis": first.get("cost_basis"),
            "cassette": dict(first.get("cassette") or {}),
            "max_spend": None,
            # These rollouts were not produced by this call, and the seed is one rollout's
            # rather than the evaluation's, which does not invert from it.
            "scored_from": "run_directory",
            "seed_source": "rollout",
        }


def _at_turn(envelope: RunEnvelope, turn: int) -> RunEnvelope:
    """The rollout's envelope, saying which turn of its conversation this run is."""
    if envelope.evaluation is None:
        return envelope
    return replace(envelope, evaluation=replace(envelope.evaluation, turn=turn))


def _as_inputs(inputs: Any) -> dict[str, Any]:
    """The example's inputs as a dict, for a later turn built from them."""
    return dict(inputs) if isinstance(inputs, Mapping) else {}


def _said(said: Any, example: Example) -> dict[str, Any]:
    """A later turn's inputs: the example's, with the one key that carries what was said.

    The key is whichever of the example's own inputs holds a string, so a pipeline taking
    ``question`` and one taking ``message`` both work without the example naming the key.
    """
    if not isinstance(example.inputs, Mapping):
        return {}
    for key, value in example.inputs.items():
        if isinstance(value, str):
            return {key: said}
    return {}


def _scoped_for_rollout(
    envelope: RunEnvelope,
    example: Example,
    root: Path,
    *,
    end_user: Any = None,
    seed: int = 0,
    eval_id: str | None = None,
    rollout: int = 0,
    turn: int = 1,
) -> RunEnvelope:
    """The envelope for one rollout: its own memory, its own end user, nothing shared.

    Rollouts run concurrently over one pipeline, so a store they shared would let one answer
    out of another's write, and the same measurement would report a different number each time.
    The store holds what the example declares and what this rollout writes into it.

    The conversation is rebound the same way, so a rollout starts from what its example says
    was already said rather than from what another rollout left behind.

    A stand-in end user is bound here for the same reason, to this example's description of the
    person and to this rollout's seed, so two rollouts of one example ask their own questions
    and get their own answers.

    ``eval_id`` and ``rollout`` are what the rollout's manifest records of where it came
    from, so a rollout says it is one rather than being identified by how deep it sits.

    A rollout is never live, whatever the envelope it came from says. It runs a seeded example
    rather than something an end user asked for, so a project whose envelope is the one it
    ships with does not write its evaluation into the runs a person made.
    """
    scoped = envelope if not envelope.live else replace(envelope, live=False)
    if eval_id is not None:
        scoped = replace(
            scoped,
            evaluation=EvaluationRef(
                eval_id=eval_id, example=example.id, rollout=rollout, turn=turn
            ),
        )
    if envelope.memory is not None:
        scoped = replace(
            scoped, memory=envelope.memory.rebound(root / "memory", seed=example.memory)
        )
    if envelope.conversations is not None:
        scoped = replace(
            scoped,
            conversations=envelope.conversations.rebound(
                root / "conversation", seed=example.conversation
            ),
        )
    if end_user is not None:
        scoped = replace(scoped, end_user=_playing(end_user, example, seed, envelope))
    return scoped


def _end_user_identity(end_user: Any) -> Any:
    """What an evaluation's identity records about who answered its consultations.

    A stand-in reports what it is. A channel the project wrote reports the fact that one was
    given, since the library cannot read what it does. A run answering more than one person
    reports each by name, so two evaluations differing in one of them are two evaluations.
    """
    if end_user is None:
        return None
    if isinstance(end_user, Mapping):
        return {str(name): _end_user_identity(one) for name, one in sorted(end_user.items())}
    identity = getattr(end_user, "identity", None)
    return identity() if callable(identity) else "project_channel"


def _playing(end_user: Any, example: Example, seed: int, envelope: RunEnvelope) -> Any:
    """The channel one rollout consults, from whatever ``end_user=`` was given.

    A :class:`SimulatedEndUser` is bound to this example and seed. Anything else is a channel
    the project wrote and is passed through, since the library knows nothing about what it
    needs. One channel per answerer is bound the same way, each to the person this example
    describes under that name.
    """
    if isinstance(end_user, Mapping):
        return {
            str(name): _one_playing(one, example, seed, envelope, str(name))
            for name, one in end_user.items()
        }
    return _one_playing(end_user, example, seed, envelope, "")


def _one_playing(
    end_user: Any, example: Example, seed: int, envelope: RunEnvelope, name: str
) -> Any:
    """One stand-in bound to the person this example describes under ``name``."""
    playing = getattr(end_user, "playing", None)
    if playing is None:
        return end_user
    answerers = answerers_in(example.end_user)
    person = answerers.get(name) or answerers.get("")
    return playing(person or "", seed=seed, cost_basis=envelope.cost_basis, name=name)


def _recording_by_default(
    envelope: RunEnvelope, *, record: bool, resuming: bool = False
) -> RunEnvelope:
    """The envelope an evaluation's rollouts run under, recording unless told otherwise.

    An envelope that names a cassette is left alone: a replay stays a replay, ``Cassette.off()``
    stays off, and a path the project chose is where the recording goes. The default recording
    is replaced with one naming the evaluation's own directory, so the rollouts write **one**
    file between them rather than one each, and a later replay serves one recorded answer to
    the k rollouts of an example (FT-20). While this mode records, every call runs live;
    ``resuming``'s update mode and ``EvalSuite.record`` serve what the file already holds.

    ``resuming`` continues the file the interrupted evaluation left there, so the rollouts that
    already ran keep what they bought and the ones being run now are recorded beside them. The
    same file recorded again would be refused.

    ``record=False`` turns the default off explicitly. Returning the envelope untouched would
    leave each rollout resolving a recording of its own.
    """
    if not record:
        return envelope.with_cassette(Cassette.off())
    if not envelope.cassette.awaiting_path:
        return envelope
    path = Path(envelope.run_dir) / "cassette.jsonl"
    if resuming and path.exists() and path.stat().st_size > 0:
        return envelope.with_cassette(Cassette.update(path))
    return envelope.with_cassette(Cassette.record(path))


def terminal_node_id(pipeline: Pipeline) -> str:
    """The id of the node whose output is the run's, as a trajectory records it.

    A pipeline with two nodes that have no successor is refused at construction, so exactly one
    node produces the run's output. A pipeline used as a node records nothing under its own id,
    so a container terminal resolves to the leaf its own graph ends at::

        terminal_node_id(pipeline)   # 'orchestrate.report'
    """
    node_id = pipeline.graph.terminal
    holder = pipeline
    while True:
        below = next(
            (n for n in holder.nodes if getattr(n, "node_id", None) == holder.graph.terminal),
            None,
        )
        if not isinstance(below, Pipeline):
            return node_id
        node_id = f"{node_id}.{below.graph.terminal}"
        holder = below


def _examples_scored(
    chosen: Sequence[Example], rollouts: Sequence[RolloutOutcome]
) -> list[Example]:
    """The chosen examples at least one scored rollout covers, in the split's own order.

    An evaluation that scored part of a split reports every figure over what ran, and the floor
    is one of those figures. Over the whole split instead it would be a different population
    from the figure it sits under, computed at a different n, and the paired comparison
    ``against_baseline`` makes would pair examples the agent never answered.
    """
    scored = {rollout.example_id for rollout in rollouts}
    return [example for example in chosen if example.id in scored]


def output_of(pipeline: Pipeline, trajectory: str | Path) -> Any:
    """What a recorded run returned, read back from its trajectory.

    The value is decoded, so an absence is an ``Unknown`` rather than the tagged object the
    file holds, and rebuilt through the terminal node's ``output_schema``, so a caller reading
    a field off it gets what the live run produced rather than a plain dict::

        answer = output_of(pipeline, "runs/eval/eval_a12/q7-0/trajectory.jsonl")

    ``None`` where the terminal node has no execution on file, which is a run that stopped or
    failed before reaching it.
    """
    path = Path(trajectory)
    if not path.exists():
        return None
    node_id = terminal_node_id(pipeline)
    ran = [
        record
        for record in read_trajectory(path)
        if record.get("record_type") == "node_execution"
        and str(record.get("node_id")) == node_id
        and record.get("termination") != "skipped"
    ]
    if not ran:
        return None
    decoded = decode_answer(max(ran, key=lambda r: r["sequence"]).get("outputs"))
    declared = dict(pipeline.declared_nodes()).get(node_id)
    schema = getattr(declared, "output_schema", None)
    if schema is None or decoded is None or isinstance(decoded, Unknown):
        return decoded
    try:
        return TypeAdapter(schema).validate_python(decoded)
    except Exception:  # noqa: BLE001
        # A record written under an older schema still answers as plain data, which is what a
        # named `answer` reads. Refusing here would make a re-score fail on the one run it is
        # most wanted for.
        return decoded


def _named(tools: Sequence[Tool]) -> str:
    """``"tool 'a'"`` or ``"tools 'a', 'b' and 'c'"``, for a message naming what it found."""
    names = [repr(tool.name) for tool in tools]
    if len(names) == 1:
        return f"tool {names[0]}"
    return f"tools {', '.join(names[:-1])} and {names[-1]}"


def _currency_of(envelope: RunEnvelope, pipeline: Pipeline) -> str | None:
    """The currency a spend ceiling is in, where anything declares one.

    A run uses one currency, checked before it starts, so the cost basis and every paid tool
    agree wherever both exist. Either may be absent: a pipeline of `Deterministic` nodes needs
    no basis, and an evaluation with no paid tool has no declared_cost to read.
    """
    basis = envelope.cost_basis
    if basis is not None and getattr(basis, "currency", None):
        return str(basis.currency)
    for tool in _tools_of(pipeline):
        if tool.declared_cost is not None and tool.declared_cost.currency:
            return tool.declared_cost.currency
    return None


def _spend_of(root: Path, run_ids: Any) -> dict[str, Any]:
    """What a recording's runs were charged, summed over the manifests they wrote.

    ``charged_cost`` is money the run was charged, model calls and paid tool calls together;
    ``tool_spend`` is the paid tool half of it and carries the call count. A run whose
    manifest is missing contributes nothing, which is the run that failed before writing one.
    """
    spend: float | None = None
    currency: str | None = None
    paid_calls = 0
    for run_id in run_ids:
        manifest = root / run_id / "manifest.json"
        if not manifest.exists():
            continue
        totals = json.loads(manifest.read_text(encoding="utf-8")).get("totals") or {}
        charged = totals.get("charged_cost")
        if charged is not None:
            spend = charged if spend is None else spend + charged
        tool_spend = totals.get("tool_spend") or {}
        paid_calls += int(tool_spend.get("calls") or 0)
        # `spend` is the model calls and the paid tool calls together, so a recording that
        # made no paid tool call still has a unit: the one the run's cost was priced in.
        currency = (
            currency or tool_spend.get("currency") or (totals.get("cost") or {}).get("currency")
        )
    return {"spend": spend, "currency": currency, "paid_calls": paid_calls}


def _criteria_named_by(examples: Sequence[Example]) -> dict[str, tuple[str, ...]]:
    """Which criteria each example's answer key names, keyed by example id.

    What a per-criterion figure counts as unanswered is read off this: a rollout that got no
    answer out of the backend was judged against nothing, and the figures it fell out of are
    the ones its own example named.
    """
    found: dict[str, tuple[str, ...]] = {}
    for example in examples:
        named: list[str] = []
        for key in (example.expected, *example.expected_by_node.values()):
            if isinstance(key, Criteria):
                named.extend(key.ids)
        if named:
            found[example.id] = tuple(named)
    return found


def _tools_of(pipeline: Pipeline) -> list[Tool]:
    """Every tool the pipeline can call, once each, in node order.

    Every node kind that carries tools is read, including ``Deterministic``, which calls one
    at a fixed point through ``ctx.call_tool``. A tool reachable that way runs once per
    rollout the same as one the model chose, so it is here for the same reasons.

    A tool declared in a registry that no node uses is not here: it cannot run during a
    rollout, and refusing on it would refuse a project for a tool this evaluation never
    reaches.
    """
    found: dict[str, Tool] = {}
    for _, node in pipeline.declared_nodes():
        for tool in getattr(node, "tools", None) or ():
            found.setdefault(tool.name, tool)
    return list(found.values())


def _clients_of(pipeline: Pipeline, model: ModelClient | None) -> list[ModelClient]:
    """Every distinct client this evaluation can call, once each.

    A node may declare its own, and each is paced separately because each holds its own view
    of what the backend said is left of the window.
    """
    found: list[ModelClient] = []
    for _, node in pipeline.declared_nodes():
        if node.node_kind not in ("llm", "agent"):
            continue
        client = getattr(node, "model", None) or model
        if client is not None and not any(client is seen for seen in found):
            found.append(client)
    return found


def _pace_for(model: ModelClient | None, concurrency: int, *, replaying: bool) -> None:
    """Pace the client for the rollouts about to share it, or say it is not paced.

    A `PacedClient` given no `min_remaining_requests` takes this evaluation's concurrency as
    its floor. A client that is not paced, running more than one rollout at a time against a
    hosted backend, warns: a per-minute quota is what rate limits an evaluation, a rate-limited
    call records no token counts, and one of those makes the whole evaluation's cost unknown.
    """
    if model is None or replaying or concurrency <= 1:
        return
    if isinstance(model, PacedClient):
        model.expect_callers(concurrency)
        return
    if getattr(model.identity(), "backend", None) != "hosted_api":
        return
    warnings.warn(
        f"This evaluation runs {concurrency} rollouts at once against a hosted backend "
        f"through a client that does not pace. A per-minute quota answers the calls that "
        f"overrun it with a rate-limit error, retries do not clear a quota, and a "
        f"rate-limited call reports no token counts, so one of them leaves the whole "
        f"evaluation's cost unknown.\n"
        f"Wrap the adapter: "
        f"model=PacedClient({type(model).__name__}"
        f"(model={model.identity().request_model!r})). It reads the allowance off each "
        f"response and holds the next call back, and this runner sets its floor from "
        f"concurrency. A backend that publishes no allowance leaves the wrapper a "
        f"passthrough, and concurrency=1 is what bounds the rate there.",
        SimpleAgentsWarning,
        stacklevel=3,
    )


def _cassette_counts(rollouts: Sequence[RolloutOutcome]) -> dict[str, int]:
    """This evaluation's cassette outcomes, summed over the manifests the rollouts wrote.

    ``diverged`` is the one to read: it counts requests already on file whose response came
    back different, so a non-zero count on a recording means the file holds two answers to one
    request and replay will serve the earlier. Each rollout counts its own, and nothing else
    adds them up.
    """
    totals = {"hits": 0, "misses": 0, "recorded": 0, "diverged": 0}
    for rollout in rollouts:
        if not rollout.trajectory:
            continue
        manifest = Path(rollout.trajectory).parent / "manifest.json"
        if not manifest.exists():
            continue
        counts = json.loads(manifest.read_text(encoding="utf-8")).get("cassette") or {}
        for name in totals:
            totals[name] += int(counts.get(name) or 0)
    return totals


def _prompts_of(rollouts: Sequence[RolloutOutcome]) -> dict[str, Any]:
    """The prompt versions the runs recorded, from the first manifest that has any.

    A regression between two evaluations is traced to a prompt edit through these (FT-15).
    """
    for rollout in rollouts:
        if not rollout.trajectory:
            continue
        manifest = Path(rollout.trajectory).parent / "manifest.json"
        if not manifest.exists():
            continue
        recorded = json.loads(manifest.read_text(encoding="utf-8")).get("prompts")
        if recorded:
            return dict(recorded)
    return {}
