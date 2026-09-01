"""A condition a model or a person decides, and the file it is read out of.

The behaviour under test is `docs/evaluation.md` §12. No model is called anywhere here, which
is the point of the design: a judgement is made first and written to a file, and scoring reads
the file. The judge in these tests is a plain function, which is what a project's judging pass
is from the library's side.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simple_agents import Budget, Deterministic, Pipeline, RunEnvelope, Unknown
from simple_agents.errors import ConfigurationError
from simple_agents.evaluation import (
    Criteria,
    Criterion,
    EvalSuite,
    Example,
    ExampleSet,
    Judged,
    Label,
    Outcome,
    ProjectMetric,
    Scoring,
    UnjudgedAnswers,
    compare,
    judgement_key,
    read_labels,
    write_labels,
)

REPLIES = {
    "q0": "we will get that refunded today",
    "q1": "the order shipped on Tuesday",
    "q2": "the policy covers this and no refund is due",
}


def _pipeline() -> Pipeline:
    def reply(inputs, ctx):
        return {"answer": REPLIES[inputs["id"]]}

    return Pipeline(
        [Deterministic(reply, node_id="reply")],
        budget=Budget(max_steps=20, max_tokens=100, max_cost=0.0, max_wall_clock_ms=60_000),
    )


def _examples(ids=tuple(REPLIES)) -> ExampleSet:
    return ExampleSet(
        [
            Example(
                id=one,
                inputs={"id": one},
                expected=Criteria([Criterion(id="no_refund", text="does not promise a refund")]),
                split="held_out",
            )
            for one in ids
        ]
    )


def _suite(tmp_path: Path, **kwargs) -> EvalSuite:
    return EvalSuite(
        _pipeline(),
        kwargs.pop("examples", None) or _examples(),
        answer="answer",
        matches=lambda s: True,
        criteria=kwargs.pop("criteria", {"no_refund": Judged()}),
        judgements=tmp_path / "evals/judgements.jsonl",
        **kwargs,
    )


def _judge(ws):
    """A judge that reads the text. A project's would call a model; the seam is the same."""
    return [
        w.label(
            "refunded" not in str(w.material),
            decided_by="fixture-judge",
            reason="looked for a promise of a refund",
            run_id="run_fixture",
        )
        for w in ws
    ]


def _run_dir(tmp_path: Path) -> Path:
    return next((tmp_path / "runs" / "eval").glob("eval_*"))


class TestDeclaringACondition:
    def test_a_judged_condition_needs_no_check_to_construct(self, tmp_path):
        """The chicken and egg: a judgement is about an answer that does not exist yet.

        Refusing construction is what made a seeding run need a placeholder check, whose wrong
        numbers were then written to a results file.
        """
        suite = _suite(tmp_path)

        assert suite.judged == {"no_refund"}

    def test_a_condition_with_neither_a_check_nor_a_declaration_is_still_refused(self, tmp_path):
        with pytest.raises(ConfigurationError) as caught:
            EvalSuite(
                _pipeline(),
                _examples(),
                answer="answer",
                matches=lambda s: True,
                judgements=tmp_path / "evals/judgements.jsonl",
            )

        assert "no_refund" in str(caught.value)

    def test_scoring_built_by_hand_says_what_is_missing(self):
        """A rule asking for a judgement outside an evaluation has nothing to read it from."""
        example = Example(id="q0", inputs={}, expected="x", split="held_out")
        scoring = Scoring(answer="a", expected="x", example=example, rollout=0, seed=1)

        with pytest.raises(ConfigurationError) as caught:
            scoring.judgement("is it right?", over="a")

        assert "judgements=Judgements()" in str(caught.value)


class TestTheGate:
    def test_running_with_nothing_judged_refuses_after_the_rollouts(self, tmp_path):
        suite = _suite(tmp_path)

        with pytest.raises(ConfigurationError) as caught:
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=2,
                seed=7,
                concurrency=1,
            )

        message = str(caught.value)
        assert "3 answer(s) have no judgement" in message
        assert "suite.judge(" in message
        assert "suite.rescore(" in message

    def test_the_rollouts_survive_the_refusal(self, tmp_path):
        """Nothing that was paid for is lost: the gate is after the runs, not during them."""
        suite = _suite(tmp_path)
        with pytest.raises(ConfigurationError):
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=2,
                seed=7,
                concurrency=1,
            )

        assert len(list(_run_dir(tmp_path).glob("q*-*"))) == 6

    def test_an_unjudged_answer_is_not_scored_as_an_absence(self, tmp_path):
        """Silence from the agent and silence from the judge are different facts.

        Stage 3 shipped `Unknown` from a check meaning the answer asserted nothing about the
        condition. A judge may return exactly that, and it is reported as an absence. Nothing
        having judged is a different state and reports no number at all, so the two cannot be
        confused in a results file.
        """
        judged_absent = _suite(tmp_path / "a", examples=_examples(("q0",)))
        results = judged_absent.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "a/runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=lambda ws: [
                w.label(Unknown(reason="says nothing"), decided_by="fixture-judge") for w in ws
            ],
        )
        assert results.criteria["no_refund"].absent == 1

        nothing_judged = _suite(tmp_path / "b", examples=_examples(("q0",)))
        with pytest.raises(ConfigurationError) as caught:
            nothing_judged.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "b/runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
            )
        assert "have no judgement" in str(caught.value)


class TestWhereItMeetsPerFieldAbsence:
    """`expects_absence` turns an absent part into a met one, and a missing judgement is absent.

    The two features cross: a criterion declaring that silence is the right answer reads an
    undecided part as met, and a rule that asked for a judgement nothing made leaves its part
    undecided. The request is recorded before the rule is left undecided, so the gate still
    fires and no number is reported off the coincidence.
    """

    @staticmethod
    def _suite_declaring_absence(tmp_path):
        examples = ExampleSet(
            [
                Example(
                    id="q0",
                    inputs={"id": "q0"},
                    expected=Criteria(
                        [
                            Criterion(
                                id="no_refund",
                                text="mentions no refund",
                                expects_absence=True,
                            )
                        ]
                    ),
                    split="held_out",
                )
            ]
        )
        return _suite(tmp_path, examples=examples)

    def test_a_missing_judgement_still_refuses(self, tmp_path):
        suite = self._suite_declaring_absence(tmp_path)

        with pytest.raises(ConfigurationError) as caught:
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
            )

        assert "have no judgement" in str(caught.value)

    def test_a_judge_reporting_absence_meets_the_condition(self, tmp_path):
        suite = self._suite_declaring_absence(tmp_path)

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=lambda ws: [
                w.label(Unknown(reason="says nothing about refunds"), decided_by="fixture")
                for w in ws
            ],
        )

        assert results.criteria["no_refund"].interval.point == 1.0
        assert results.rollouts[0].outcome is Outcome.CORRECT


class TestJudgingAndScoring:
    def test_judge_then_rescore(self, tmp_path):
        suite = _suite(tmp_path)
        with pytest.raises(ConfigurationError):
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=2,
                seed=7,
                concurrency=1,
            )
        run_dir = _run_dir(tmp_path)

        made = suite.judge(run_dir=run_dir, split="held_out", using=_judge)
        results = suite.rescore(run_dir=run_dir, split="held_out")

        assert len(made) == 3
        assert results.criteria["no_refund"].interval.point == pytest.approx(2 / 3)

    def test_run_with_a_judge_does_all_of_it(self, tmp_path):
        seen = []
        suite = _suite(tmp_path)

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=2,
            seed=7,
            concurrency=1,
            judge=lambda ws: seen.append(len(ws)) or _judge(ws),
        )

        assert seen == [3], "one pass, given every judgement at once"
        assert results.criteria["no_refund"].interval.point == pytest.approx(2 / 3)

    def test_the_whole_worklist_is_passed_at_once(self, tmp_path):
        """A pass may batch, put them to a panel, or escalate only the hard ones.

        Calling the project once per judgement would fix the granularity at one model call per
        answer and make each of those either impossible or wasteful.
        """
        batches = []
        suite = _suite(tmp_path)

        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=3,
            seed=7,
            concurrency=1,
            judge=lambda ws: batches.append([w.example_id for w in ws]) or _judge(ws),
        )

        assert batches == [["q0", "q1", "q2"]]

    def test_a_pass_that_answers_nothing_stops_rather_than_asking_again(self, tmp_path):
        """Found on the live vLLM run, which spent eight judging passes to reach one refusal.

        A 1.7B judge failed schema validation on some items and the harness dropped them, so
        each round re-asked for the same ones, the model failed again, and the refusal blamed
        the missing judgement rather than the pass that had been asked and had not answered.
        """
        rounds = []
        suite = _suite(tmp_path)

        with pytest.raises(UnjudgedAnswers) as caught:
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
                judge=lambda ws: rounds.append(len(ws)) or [],
            )

        assert rounds == [3], "asked once, and not seven more times"
        assert "returned none of them" in str(caught.value)

    def test_a_pass_that_answers_some_is_asked_again_for_the_rest(self, tmp_path):
        """A pass making progress still rounds, which is what a second judgement needs.

        Only a round that answers none of what it was asked ends it.
        """
        rounds = []

        def only_q0(ws):
            rounds.append(len(ws))
            return [w.label(True, decided_by="fixture-judge") for w in ws if w.example_id == "q0"]

        suite = _suite(tmp_path)

        with pytest.raises(UnjudgedAnswers):
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
                judge=only_q0,
            )

        assert rounds == [3, 2], "asked again after progress, stopped when a round stalled"

    def test_a_judge_answering_something_nobody_asked_is_refused(self, tmp_path):
        suite = _suite(tmp_path)

        with pytest.raises(ConfigurationError) as caught:
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
                judge=lambda ws: [Label(id="made-up", verdict=True, decided_by="fixture-judge")],
            )

        assert "nothing asked about" in str(caught.value)

    def test_a_judge_returning_something_other_than_a_label_is_refused(self, tmp_path):
        suite = _suite(tmp_path)

        with pytest.raises(ConfigurationError) as caught:
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
                judge=lambda ws: [True for _ in ws],
            )

        assert "where a Label belongs" in str(caught.value)


class TestWhatAJudgementIsKeyedOn:
    def test_rollouts_that_produced_the_same_answer_are_judged_once(self, tmp_path):
        """Three rollouts of one example, one judgement, because the answer is the same."""
        batches = []
        suite = _suite(tmp_path, examples=_examples(("q0",)))

        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=3,
            seed=7,
            concurrency=1,
            judge=lambda ws: batches.append(len(ws)) or _judge(ws),
        )

        assert batches == [1]

    def test_a_judgement_made_against_another_answer_is_not_found(self, tmp_path):
        """The silent failure the key exists to prevent.

        A verdict made in March against March's answer must not be applied to an April answer
        that differs. Keyed on the answer, it simply is not found.
        """
        earlier = judgement_key("q0", "does not promise a refund", "an older answer")
        now = judgement_key("q0", "does not promise a refund", REPLIES["q0"])

        assert earlier != now

    def test_rewording_the_condition_leaves_the_judgements_unfindable(self, tmp_path):
        """The text is the question the judge was asked, so it is inside the key.

        This is why `compare()` need not compare the text separately: a reworded condition
        cannot be scored from the old judgements at all.
        """
        was = judgement_key("q0", "does not promise a refund", REPLIES["q0"])
        now = judgement_key("q0", "does not promise or imply a refund", REPLIES["q0"])

        assert was != now

    def test_a_stale_slot_is_named_in_the_refusal(self, tmp_path):
        """Without this the refusal reads as though the condition was never judged."""
        store = tmp_path / "evals/judgements.jsonl"
        store.parent.mkdir(parents=True, exist_ok=True)
        write_labels(
            store,
            [
                Label(
                    id=judgement_key("q0", "does not promise a refund", "an older answer"),
                    verdict=True,
                    decided_by="someone",
                    decided_at="2026-03-12T09:00:00.000Z",
                    about={"example": "q0", "criterion": "no_refund"},
                )
            ],
        )
        suite = _suite(tmp_path, examples=_examples(("q0",)))

        with pytest.raises(ConfigurationError) as caught:
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
            )

        message = str(caught.value)
        assert "was judged on 2026-03-12 by someone" in message
        assert "an answer that is not this one" in message


class TestTheTwoFiles:
    def test_the_store_keeps_an_overridden_verdict_and_the_override(self, tmp_path):
        suite = _suite(tmp_path, examples=_examples(("q0",)))
        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=_judge,
        )
        store = tmp_path / "evals/judgements.jsonl"
        key = next(iter(read_labels(store)))

        write_labels(
            store,
            [Label(id=key, verdict=True, decided_by="human", reason="disagree")],
            append=True,
        )

        assert len(store.read_text().splitlines()) == 2, "both lines survive"
        assert read_labels(store)[key].decided_by == "human", "the later line wins"

    def test_a_correction_does_not_move_what_an_earlier_run_reported(self, tmp_path):
        """The run directory's copy is what pins a reported number.

        Without it, re-scoring an evaluation from March would use whatever the store says
        today, and March's results file would claim a number nothing can reproduce.
        """
        suite = _suite(tmp_path, examples=_examples(("q0",)))
        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=_judge,
        )
        run_dir = _run_dir(tmp_path)
        store = tmp_path / "evals/judgements.jsonl"
        key = next(iter(read_labels(store)))
        before = suite.rescore(run_dir=run_dir, split="held_out")

        write_labels(
            store,
            [Label(id=key, verdict=True, decided_by="human", reason="disagree")],
            append=True,
        )
        after = suite.rescore(run_dir=run_dir, split="held_out")

        assert before.criteria["no_refund"].interval.point == 0.0
        assert after.criteria["no_refund"].interval.point == 0.0

    def test_a_new_evaluation_reads_the_correction(self, tmp_path):
        suite = _suite(tmp_path, examples=_examples(("q0",)))
        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=_judge,
        )
        store = tmp_path / "evals/judgements.jsonl"
        key = next(iter(read_labels(store)))
        write_labels(
            store,
            [Label(id=key, verdict=True, decided_by="human", reason="disagree")],
            append=True,
        )

        fresh = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs-b")),
            model=None,
            split="held_out",
            k=1,
            seed=99,
            concurrency=1,
        )

        assert fresh.criteria["no_refund"].interval.point == 1.0
        assert fresh.config["criteria"]["no_refund"]["decided_by"] == {"human": 1}

    def test_the_copy_holds_only_what_this_evaluation_used(self, tmp_path):
        suite = _suite(tmp_path, examples=_examples(("q0",)))
        store = tmp_path / "evals/judgements.jsonl"
        store.parent.mkdir(parents=True, exist_ok=True)
        write_labels(
            store,
            [Label(id="from-another-project", verdict=True, decided_by="human")],
        )

        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=_judge,
        )

        copied = read_labels(_run_dir(tmp_path) / "judgements.jsonl")
        assert len(copied) == 1
        assert "from-another-project" not in copied


class TestWhatTheResultsFileRecords:
    def test_a_judged_condition_records_its_deciders_and_a_digest(self, tmp_path):
        suite = _suite(tmp_path)

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=2,
            seed=7,
            concurrency=1,
            judge=_judge,
        )

        entry = results.config["criteria"]["no_refund"]
        assert entry["decided"] == "judged"
        assert entry["decided_by"] == {"fixture-judge": 3}
        assert entry["run_ids"] == ["run_fixture"]
        assert entry["judgements"].startswith("sha256:")

    def test_each_condition_records_its_own_judgements(self, tmp_path):
        """Found live: both judged conditions reported the whole evaluation's judgements.

        Two conditions over three examples recorded `n: 6` each and one shared digest, so a
        per-condition figure said it rested on judgements that were another condition's, and
        `comparison.criteria` could not tell which of them had been re-judged.
        """
        examples = ExampleSet(
            [
                Example(
                    id=one,
                    inputs={"id": one},
                    expected=Criteria(
                        [
                            Criterion(id="no_refund", text="does not promise a refund"),
                            Criterion(id="is_short", text="is one sentence"),
                        ]
                    ),
                    split="held_out",
                )
                for one in ("q0", "q1", "q2")
            ]
        )
        suite = _suite(
            tmp_path,
            examples=examples,
            criteria={"no_refund": Judged(), "is_short": Judged()},
        )

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=2,
            seed=7,
            concurrency=1,
            judge=lambda ws: [w.label(True, decided_by="fixture-judge") for w in ws],
        )

        no_refund = results.config["criteria"]["no_refund"]
        is_short = results.config["criteria"]["is_short"]
        assert no_refund["n"] == 3, "its own three examples, not all six judgements"
        assert is_short["n"] == 3
        assert no_refund["judgements"] != is_short["judgements"]
        assert results.config["judgements"]["n"] == 6, "every one, recorded once"

    def test_a_judged_figure_that_is_not_a_condition_is_still_covered(self, tmp_path):
        """Found live: a judged project metric had no entry, so nothing compared it.

        `_rules` compares each criterion's entry and each metric's source version. A metric
        whose figure comes from a judgement has an unchanged source version, so re-judging it
        moved the number with nothing recording that the rule had moved.
        """
        judged_well = ProjectMetric(
            name="reads_well",
            definition="how well the reply reads, judged",
            score=lambda s: float(s.judgement("how well does this read?", over=s.answer)),
        )

        def _one(tmp, verdict):
            suite = EvalSuite(
                _pipeline(),
                _examples(("q0",)),
                answer="answer",
                matches=lambda s: True,
                criteria={"no_refund": lambda s: True},
                metrics=[judged_well],
                judgements=tmp / "evals/judgements.jsonl",
            )
            return suite.run(
                envelope=RunEnvelope(run_dir=str(tmp / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
                judge=lambda ws: [w.label(verdict, decided_by="fixture-judge") for w in ws],
            )

        before = _one(tmp_path / "a", 0.2)
        after = _one(tmp_path / "b", 0.9)

        change = compare(before, after).metrics["accuracy"]
        assert change.moved is None, "the judgements moved, so no verdict is offered"
        assert change.rule_moved is not None

    def test_a_coded_condition_still_records_its_version(self, tmp_path):
        suite = _suite(tmp_path, criteria={"no_refund": lambda s: "refunded" not in s.answer})

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
        )

        entry = results.config["criteria"]["no_refund"]
        assert entry["decided"] == "code"
        assert entry["version"].startswith("sha256:")

    def test_a_comparison_withholds_its_verdict_when_the_judgements_moved(self, tmp_path):
        """The failure this exists for: re-judging moves every rate and looks like the agent."""
        suite = _suite(tmp_path, examples=_examples(("q0", "q1")))
        before = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=2,
            seed=7,
            concurrency=1,
            judge=_judge,
        )
        store = tmp_path / "evals/judgements.jsonl"
        for key in read_labels(store):
            write_labels(
                store,
                [Label(id=key, verdict=True, decided_by="human", reason="re-read them")],
                append=True,
            )
        after = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs-b")),
            model=None,
            split="held_out",
            k=2,
            seed=99,
            concurrency=1,
        )

        change = compare(before, after).metrics["accuracy"]
        assert change.moved is None
        assert change.rule_moved is not None
        assert change.rule_moved[0] != change.rule_moved[1]

    def test_the_report_names_who_decided(self, tmp_path):
        suite = _suite(tmp_path)

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=_judge,
        )

        assert "judged: fixture-judge 3" in results.report()

    def test_a_coded_condition_gets_no_judged_line(self, tmp_path):
        suite = _suite(tmp_path, criteria={"no_refund": lambda s: "refunded" not in s.answer})

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
        )

        assert "judged:" not in results.report()


class TestAJudgementFromAnywhereElse:
    def test_a_project_metric_can_read_one(self, tmp_path):
        """A judgement is not only a condition on the answer key.

        Every scoring seam is handed one `Scoring`, so a figure over the trajectory, a label on
        one node's output and a comparison against a baseline all reach the same seam.
        """
        judged_well = ProjectMetric(
            name="reads_well",
            definition="how well the reply reads, judged",
            score=lambda s: float(s.judgement("how well does this read?", over=s.answer)),
        )
        suite = EvalSuite(
            _pipeline(),
            _examples(("q0",)),
            answer="answer",
            matches=lambda s: True,
            criteria={"no_refund": lambda s: True},
            metrics=[judged_well],
            judgements=tmp_path / "evals/judgements.jsonl",
        )

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=lambda ws: [
                w.label(0.8, decided_by="fixture-judge", run_id="run_fixture") for w in ws
            ],
        )

        assert results.metrics["reads_well"].interval.point == pytest.approx(0.8)

    def test_a_judgement_may_report_absence(self, tmp_path):
        """A judge that finds the answer said nothing about the condition records that."""
        suite = _suite(tmp_path, examples=_examples(("q0",)))

        results = suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=lambda ws: [
                w.label(Unknown(reason="says nothing about refunds"), decided_by="fixture-judge")
                for w in ws
            ],
        )

        assert results.rollouts[0].outcome is Outcome.MISSED
        assert results.criteria["no_refund"].absent == 1


class TestTheRestOfTheSurface:
    """Seams a judgement reaches that the design did not walk through."""

    def test_a_node_judgement_survives_a_rollout_that_failed(self, tmp_path):
        """Found at verification: two failure paths built a Scoring carrying no judgements.

        A rollout that raised still reached the nodes before the one that stopped it, so
        `node_matches` runs on it. Without the judgements it raised "this Scoring carries no
        judgements" instead of collecting the request, which turns one agent failure into an
        evaluation failure.
        """

        def ok(inputs, ctx):
            return {"v": "the retrieved passages"}

        def boom(inputs, ctx):
            raise RuntimeError("the second node fails")

        pipeline = Pipeline(
            [
                Deterministic(ok, node_id="retrieve", successors=["fail"]),
                Deterministic(boom, node_id="fail"),
            ],
            budget=Budget(max_steps=20, max_tokens=100, max_cost=0.0, max_wall_clock_ms=60_000),
        )
        examples = ExampleSet(
            [
                Example(
                    id="q0",
                    inputs={},
                    expected="x",
                    split="held_out",
                    expected_by_node={"retrieve": "anything"},
                )
            ]
        )
        suite = EvalSuite(
            pipeline,
            examples,
            answer="v",
            matches=lambda s: True,
            node_matches={
                "retrieve": lambda s: bool(
                    s.judgement("were the passages relevant?", over=s.answer)
                )
            },
            judgements=tmp_path / "evals/judgements.jsonl",
        )

        with pytest.raises(UnjudgedAnswers) as caught:
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
            )

        assert "have no judgement" in str(caught.value)

    def test_a_rescore_does_not_overwrite_what_pinned_an_earlier_number(self, tmp_path):
        """Found at verification: a rescore reading fewer conditions shrank the frozen copy.

        The first results file then named judgements its own run directory no longer held,
        which is the pinning this copy exists for, undone.
        """
        both = ExampleSet(
            [
                Example(
                    id="q0",
                    inputs={"id": "q0"},
                    split="held_out",
                    expected=Criteria(
                        [
                            Criterion(id="a", text="condition a"),
                            Criterion(id="b", text="condition b"),
                        ]
                    ),
                )
            ]
        )
        wide = _suite(tmp_path, examples=both, criteria={"a": Judged(), "b": Judged()})
        wide.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=lambda ws: [w.label(True, decided_by="fixture") for w in ws],
        )
        run_dir = _run_dir(tmp_path)
        assert len(read_labels(run_dir / "judgements.jsonl")) == 2

        narrow_examples = ExampleSet(
            [
                Example(
                    id="q0",
                    inputs={"id": "q0"},
                    split="held_out",
                    expected=Criteria([Criterion(id="a", text="condition a")]),
                )
            ]
        )
        narrow = _suite(tmp_path, examples=narrow_examples, criteria={"a": Judged()})
        narrow.rescore(run_dir=run_dir, split="held_out")

        assert len(read_labels(run_dir / "judgements.jsonl")) == 2

    def test_a_sweep_passes_its_judge_to_every_arm(self, monkeypatch, tmp_path):
        """Every arm produces its own answers, so none can be judged before the sweep runs.

        Without this a project with a judged condition cannot sweep at all: each arm reaches
        the gate and refuses.
        """
        from simple_agents.evaluation import variants

        seen = []

        def spy(self, **kwargs):
            seen.append(kwargs.get("judge"))
            raise RuntimeError("stop here")

        monkeypatch.setattr(EvalSuite, "run", spy)
        suite = _suite(tmp_path, examples=_examples(("q0",)))
        marker = object()

        wider = Pipeline(
            [
                Deterministic(lambda i, c: {"answer": "a"}, node_id="reply", successors=["x"]),
                Deterministic(lambda i, c: i, node_id="x"),
            ],
            budget=Budget(max_steps=20, max_tokens=100, max_cost=0.0, max_wall_clock_ms=60_000),
        )

        with pytest.raises(RuntimeError):
            variants.compare_variants(
                suite,
                {"other": wider},
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=1,
                judge=marker,
            )

        assert seen == [marker]


class TestTheDocumentedFlow:
    """`docs/evaluation.md` §12.2's by-hand flow, run as written.

    An example that parses and resolves can still be wrong: the first draft of this one read
    `made.run_dir` off a `Recording`, which has no such field, and pointed at a directory
    `record` writes for filling a cassette rather than one holding scoreable rollouts.
    """

    def test_catching_the_refusal_gives_the_worklist_and_the_directory(self, tmp_path):
        suite = _suite(tmp_path, examples=_examples(("q0",)))
        env = RunEnvelope(run_dir=str(tmp_path / "runs"))

        try:
            results = suite.run(
                envelope=env, model=None, split="held_out", k=3, seed=41, concurrency=1
            )
        except UnjudgedAnswers as waiting:
            for want in waiting.wanted:
                write_labels(
                    tmp_path / "evals/judgements.jsonl",
                    [want.label(True, decided_by="human")],
                    append=True,
                )
            results = suite.rescore(run_dir=waiting.run_dir, split="held_out")

        assert results.criteria["no_refund"].interval.point == 1.0

    def test_the_refusal_carries_what_the_message_names(self, tmp_path):
        suite = _suite(tmp_path, examples=_examples(("q0", "q1")))

        with pytest.raises(UnjudgedAnswers) as caught:
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=2,
                seed=41,
                concurrency=1,
            )

        assert len(caught.value.wanted) == 2
        assert Path(caught.value.run_dir).name.startswith("eval_")
        assert str(caught.value.run_dir) in str(caught.value)


class TestTheWorklist:
    def test_a_request_says_what_it_is_about(self, tmp_path):
        suite = _suite(tmp_path, examples=_examples(("q0",)))
        with pytest.raises(ConfigurationError):
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
            )

        want = suite.unjudged(run_dir=_run_dir(tmp_path), split="held_out")[0]

        assert want.question == "does not promise a refund"
        assert want.material == REPLIES["q0"]
        assert want.example_id == "q0"
        assert "criterion 'no_refund'" in want.describe()

    def test_a_label_built_from_a_request_carries_the_join(self, tmp_path):
        suite = _suite(tmp_path, examples=_examples(("q0",)))
        with pytest.raises(ConfigurationError):
            suite.run(
                envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
                model=None,
                split="held_out",
                k=1,
                seed=7,
                concurrency=1,
            )
        want = suite.unjudged(run_dir=_run_dir(tmp_path), split="held_out")[0]

        label = want.label(False, decided_by="human", reason="promises one")

        assert label.id == want.key
        assert label.about["example"] == "q0"
        assert label.about["criterion"] == "no_refund"
        assert label.about["question"] == "does not promise a refund"

    def test_the_join_survives_a_round_trip_through_the_file(self, tmp_path):
        path = tmp_path / "judgements.jsonl"
        original = Label(
            id="sha256:abc",
            verdict=False,
            decided_by="human",
            about={"example": "q0", "criterion": "no_refund", "rollout": 1},
        )

        write_labels(path, [original])

        assert read_labels(path)["sha256:abc"].about == original.about

    def test_nothing_is_wanted_once_everything_is_judged(self, tmp_path):
        suite = _suite(tmp_path)
        suite.run(
            envelope=RunEnvelope(run_dir=str(tmp_path / "runs")),
            model=None,
            split="held_out",
            k=1,
            seed=7,
            concurrency=1,
            judge=_judge,
        )

        assert suite.unjudged(run_dir=_run_dir(tmp_path), split="held_out") == ()


class TestSeveralAnnotatorsOnOneThing:
    """Shape H1: the annotators disagreed and the disagreement is the signal.

    The survey recorded `read_labels` as collapsing repeats, which reads as the material being
    lost. The file keeps every line; collapsing is the reader's choice.
    """

    def _file(self, tmp_path):
        from simple_agents.evaluation.labels import Label, write_labels

        path = tmp_path / "labels.jsonl"
        write_labels(
            path,
            [
                Label(id="q1", verdict="spam", decided_by="ann_a"),
                Label(id="q1", verdict="spam", decided_by="ann_b"),
                Label(id="q1", verdict="not_spam", decided_by="ann_c"),
            ],
        )
        return path

    def test_read_labels_keeps_the_last_one(self, tmp_path) -> None:
        """A correction replacing an earlier judgement, which is what that reader is for."""
        from simple_agents.evaluation.labels import read_labels

        assert read_labels(self._file(tmp_path))["q1"].decided_by == "ann_c"

    def test_read_every_label_keeps_them_all(self, tmp_path) -> None:
        from simple_agents.evaluation.labels import read_every_label

        every = read_every_label(self._file(tmp_path))["q1"]

        assert [label.verdict for label in every] == ["spam", "spam", "not_spam"]
        assert [label.decided_by for label in every] == ["ann_a", "ann_b", "ann_c"]

    def test_the_spread_is_then_a_number_a_figure_can_score_against(self, tmp_path) -> None:
        from simple_agents.evaluation.labels import read_every_label

        every = read_every_label(self._file(tmp_path))["q1"]
        assert sum(1 for label in every if label.verdict == "spam") / len(every) == 2 / 3

    def test_a_file_that_does_not_exist_reads_as_empty(self, tmp_path) -> None:
        from simple_agents.evaluation.labels import read_every_label

        assert read_every_label(tmp_path / "nothing.jsonl") == {}
