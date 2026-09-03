"""Answer keys, the fold over them, the third outcome, and the figure per criterion.

The distinction under test throughout: an answer key says what the right answer *is*, and
``matches`` says whether two values are the same. So a key changes how many comparisons are made
and what is done with their results, and never what a comparison means.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from simple_agents import (
    Prompt,
    Budget,
    Cassette,
    ConfigurationError,
    FakeModelClient,
    LLMNode,
    Pipeline,
    RunEnvelope,
    Unknown,
)
from simple_agents.evaluation import evaluation_dir
from simple_agents.evaluation import (
    AnyOf,
    Contains,
    Criteria,
    Criterion,
    Example,
    ExampleSet,
    Outcome,
    RolloutOutcome,
    WithinTolerance,
    compare,
)
from simple_agents.evaluation.results import EvalResults
from simple_agents.evaluation.runner import EvalSuite
from simple_agents.models import fake_response

from schemas import Answer
from simple_agents.evaluation.metrics import _SPECS, aggregate, criterion_metrics
from simple_agents.evaluation.outcomes import classify
from simple_agents.evaluation.scoring import Scoring, Verdict, criteria_in

EXACT = lambda s: s.answer == s.expected
CONTAINED = lambda s: s.expected in s.answer


def scoring(answer: Any, expected: Any, **rest: Any) -> Scoring:
    return Scoring(
        answer=answer,
        expected=expected,
        example=Example(id="q1", inputs={"q": "?"}, expected=expected, split="dev"),
        rollout=0,
        seed=41,
        **rest,
    )


def criteria_key() -> Criteria:
    """The three-condition key used throughout: one required, one weighted, one plain."""
    return Criteria(
        [
            Criterion(id="not_read", text="a book the reader has not read", required=True),
            Criterion(id="subject", text="shares a subject with the shelf", weight=2),
            Criterion(id="length", text="under 400 pages"),
        ]
    )


# -- what a key admits --------------------------------------------------------------------


class TestAnyOf:
    def test_any_admissible_value_is_right(self) -> None:
        key = AnyOf(["Kirkwall", "Kirkwall Retail Ltd"])

        assert classify(scoring("Kirkwall Retail Ltd", key), matches=EXACT)[0] is (Outcome.CORRECT)

    def test_a_value_outside_the_set_is_a_confident_wrong_answer(self) -> None:
        key = AnyOf(["Kirkwall", "Kirkwall Retail Ltd"])

        assert classify(scoring("Northgate", key), matches=EXACT)[0] is (Outcome.FALSE_CONFIDENCE)

    def test_matches_is_called_once_per_admissible_value(self) -> None:
        """The project writes a comparison between two single values. The key folds it."""
        seen: list[Any] = []

        classify(
            scoring("Northgate", AnyOf(["a", "b", "c"])),
            matches=lambda s: seen.append(s.expected) or False,
        )

        assert seen == ["a", "b", "c"]

    def test_the_whole_key_is_still_reachable_from_the_example(self) -> None:
        """`s.expected` narrows to one part; `s.example.expected` never does."""
        seen: list[Any] = []

        classify(
            scoring("x", AnyOf(["a", "b"])),
            matches=lambda s: seen.append(s.example.expected) or False,
        )

        assert all(isinstance(key, AnyOf) for key in seen)

    def test_it_never_grades(self) -> None:
        """One answer either came from the set or did not, so there is no part to meet."""
        _, verdict = classify(scoring("a", AnyOf(["a", "b", "c"])), matches=EXACT)

        assert (verdict.grade, verdict.met, verdict.total) == (1.0, 1, 1)

    def test_an_empty_set_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            AnyOf([])

        assert "no answer could ever be right" in str(raised.value)


class TestContains:
    def test_one_value_the_answer_holds_is_right(self) -> None:
        outcome, _ = classify(
            scoring(["Solaris", "The Left Hand of Darkness"], Contains("Solaris")),
            matches=CONTAINED,
        )

        assert outcome is Outcome.CORRECT

    def test_holding_some_of_several_is_partially_correct(self) -> None:
        outcome, verdict = classify(
            scoring(["Solaris", "Dune"], Contains(["Solaris", "Dune", "Ubik"])),
            matches=CONTAINED,
        )

        assert outcome is Outcome.PARTIALLY_CORRECT
        assert verdict.grade == pytest.approx(2 / 3)
        assert (verdict.met, verdict.total) == (2, 3)

    def test_holding_none_of_them_is_a_confident_wrong_answer(self) -> None:
        outcome, verdict = classify(
            scoring(["Ubik"], Contains(["Solaris", "Dune"])), matches=CONTAINED
        )

        assert outcome is Outcome.FALSE_CONFIDENCE
        assert verdict.grade == 0.0

    def test_a_bare_value_is_taken_as_one_value(self) -> None:
        assert Contains("Solaris").values == ["Solaris"]


class TestWithinTolerance:
    def test_a_value_inside_a_relative_bound_is_right(self) -> None:
        key = WithinTolerance(52.0, relative=0.02)

        assert key.admits(52.9) is True
        assert key.admits(53.5) is False

    def test_an_absolute_bound_is_a_fixed_margin(self) -> None:
        key = WithinTolerance(52.0, absolute=1.5)

        assert key.admits(53.4) is True
        assert key.admits(53.6) is False

    def test_both_bounds_must_hold(self) -> None:
        key = WithinTolerance(52.0, absolute=1.5, relative=0.01)

        assert key.admits(52.4) is True
        assert key.admits(53.0) is False

    def test_matches_is_never_called(self) -> None:
        """The tolerance is the whole comparison, and it lives in the key so it is versioned."""

        def explode(s: Scoring) -> bool:
            raise AssertionError("a tolerance is decided by the key")

        assert (
            classify(scoring(52.5, WithinTolerance(52.0, relative=0.02)), matches=explode)[0]
            is Outcome.CORRECT
        )

    def test_a_quantity_written_as_text_is_the_same_quantity(self) -> None:
        """Found live: an output schema types a field `str`, so the answer arrives as text."""
        key = WithinTolerance(5200.0, relative=0.02)

        assert key.admits("5200") is True
        assert key.admits(" 5200.0 ") is True
        assert key.admits("5400") is False

    def test_a_boolean_is_not_a_quantity(self) -> None:
        assert WithinTolerance(1.0, absolute=0.5).admits(True) is False

    def test_text_that_does_not_spell_a_number_is_wrong(self) -> None:
        key = WithinTolerance(5200.0, relative=0.02)

        assert key.admits("5200 sqm") is False
        assert key.admits("about five thousand") is False

    def test_prose_where_a_quantity_was_asked_for_is_wrong_rather_than_an_error(self) -> None:
        outcome, _ = classify(
            scoring("about fifty-two", WithinTolerance(52.0, relative=0.02)), matches=EXACT
        )

        assert outcome is Outcome.FALSE_CONFIDENCE

    def test_declaring_no_tolerance_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            WithinTolerance(52.0)

        assert "only an exact match would be right" in str(raised.value)

    def test_a_negative_tolerance_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            WithinTolerance(52.0, absolute=-1.0)

        assert "admits nothing" in str(raised.value)


# -- a key that is a list of conditions ----------------------------------------------------


class TestCriteria:
    def _checks(self, met: set[str]) -> dict[str, Any]:
        return {
            name: (lambda s, name=name: name in met) for name in ("not_read", "subject", "length")
        }

    def test_meeting_every_condition_is_correct(self) -> None:
        outcome, verdict = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=self._checks({"not_read", "subject", "length"}),
        )

        assert outcome is Outcome.CORRECT
        assert verdict.grade == 1.0

    def test_a_partly_met_key_grades_by_weight(self) -> None:
        """not_read and subject met, of a declared weight of 1 + 2 + 1."""
        outcome, verdict = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=self._checks({"not_read", "subject"}),
        )

        assert outcome is Outcome.PARTIALLY_CORRECT
        assert verdict.grade == pytest.approx(3 / 4)
        assert (verdict.met, verdict.total) == (2, 3)
        assert verdict.parts == {"not_read": True, "subject": True, "length": False}

    def test_missing_a_required_condition_is_a_confident_wrong_answer(self) -> None:
        """The recorded case: two of three met, and the one that mattered was not."""
        outcome, verdict = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=self._checks({"subject", "length"}),
        )

        assert outcome is Outcome.FALSE_CONFIDENCE
        assert verdict.unmet_required == ("not_read",)
        assert verdict.grade == pytest.approx(3 / 4), "the grade is recorded beside it"

    def test_meeting_nothing_is_a_confident_wrong_answer(self) -> None:
        outcome, _ = classify(
            scoring("x", criteria_key()), matches=EXACT, criteria=self._checks(set())
        )

        assert outcome is Outcome.FALSE_CONFIDENCE

    def test_a_check_is_given_the_example_so_one_check_serves_every_end_user(self) -> None:
        """The multi-user case: one registration, a verdict per person."""
        key = Criteria([Criterion(id="not_read", text="a book the reader has not read")])
        readers = [
            Example(
                id="r1", inputs={"q": "?"}, expected=key, split="dev", metadata={"read": ["Dune"]}
            ),
            Example(
                id="r2",
                inputs={"q": "?"},
                expected=key,
                split="dev",
                metadata={"read": ["Solaris"]},
            ),
        ]
        check = {"not_read": lambda s: s.answer not in s.example.metadata["read"]}

        outcomes = [
            classify(
                Scoring(answer="Dune", expected=key, example=reader, rollout=0, seed=1),
                matches=EXACT,
                criteria=check,
            )[0]
            for reader in readers
        ]

        assert outcomes == [Outcome.FALSE_CONFIDENCE, Outcome.CORRECT]

    def test_a_check_that_returns_a_number_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            classify(
                scoring("x", criteria_key()),
                matches=EXACT,
                criteria={name: (lambda s: 0.5) for name in ("not_read", "subject", "length")},
            )

        assert "criterion 'not_read' returned 0.5" in str(raised.value)
        assert "Criteria([...])" in str(raised.value)

    def test_a_repeated_id_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            Criteria([Criterion(id="a", text="one"), Criterion(id="a", text="two")])

        assert "counts that check twice in the grade" in str(raised.value)

    def test_a_weight_at_or_below_zero_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            Criterion(id="a", text="one", weight=0)

        assert "must NOT meet" in str(raised.value)

    def test_no_conditions_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            Criteria([])

        assert "nothing decides whether an answer is right" in str(raised.value)


# -- absence still comes first -------------------------------------------------------------


class TestAbsenceIsReadBeforeAnyKey:
    def test_reporting_absence_against_a_key_is_a_miss(self) -> None:
        outcome, verdict = classify(
            scoring(Unknown(reason="not found"), AnyOf(["a", "b"])), matches=EXACT
        )

        assert outcome is Outcome.MISSED
        assert verdict is None

    def test_a_failed_rollout_is_never_folded(self) -> None:
        def explode(s: Scoring) -> bool:
            raise AssertionError("a failed rollout has no answer to compare")

        assert classify(scoring(None, AnyOf(["a"])), matches=explode)[0] is Outcome.FAILED


# -- the file ------------------------------------------------------------------------------


class TestAnswerKeysRoundTrip:
    @pytest.mark.parametrize(
        "key",
        [
            AnyOf(["Kirkwall", "Kirkwall Retail Ltd"]),
            Contains(["Solaris", "Dune"]),
            WithinTolerance(52.0, relative=0.02),
            WithinTolerance(52.0, absolute=1.5),
            criteria_key(),
        ],
    )
    def test_a_key_survives_the_example_file(self, key: Any, tmp_path: Path) -> None:
        path = tmp_path / "examples.jsonl"
        ExampleSet([Example(id="q1", inputs={"q": "?"}, expected=key, split="dev")]).to_jsonl(path)

        [read] = list(ExampleSet.from_jsonl(path))

        assert read.expected == key

    def test_the_encoded_form_is_a_tagged_object(self, tmp_path: Path) -> None:
        path = tmp_path / "examples.jsonl"
        ExampleSet(
            [
                Example(
                    id="q1",
                    inputs={"q": "?"},
                    split="dev",
                    expected=AnyOf(["Kirkwall", "Kirkwall Retail Ltd"]),
                )
            ]
        ).to_jsonl(path)

        written = json.loads(path.read_text().strip())

        assert written["expected"] == {
            "type": "any_of",
            "values": ["Kirkwall", "Kirkwall Retail Ltd"],
        }

    def test_absence_still_decodes_as_absence(self, tmp_path: Path) -> None:
        """`decode_answer_key` falls through, so nothing about `Unknown` moved."""
        path = tmp_path / "examples.jsonl"
        ExampleSet(
            [
                Example(
                    id="q1",
                    inputs={"q": "?"},
                    split="dev",
                    expected=Unknown(reason="no date given"),
                )
            ]
        ).to_jsonl(path)

        [read] = list(ExampleSet.from_jsonl(path))

        assert isinstance(read.expected, Unknown)
        assert read.expects_absence is True

    def test_widening_an_admissible_set_changes_the_content_hash(self) -> None:
        """So `compare()` declines to attribute the resulting difference to the agent."""
        narrow = ExampleSet(
            [Example(id="q1", inputs={"q": "?"}, expected=AnyOf(["a"]), split="dev")]
        )
        wide = ExampleSet(
            [Example(id="q1", inputs={"q": "?"}, expected=AnyOf(["a", "b"]), split="dev")]
        )

        assert narrow.content_hash() != wide.content_hash()

    def test_a_criterion_s_weight_is_in_the_content_hash(self) -> None:
        def hashed(weight: float) -> str:
            key = Criteria([Criterion(id="a", text="one", weight=weight)])
            return ExampleSet(
                [Example(id="q1", inputs={"q": "?"}, expected=key, split="dev")]
            ).content_hash()

        assert hashed(1.0) != hashed(2.0)


def test_criteria_in_finds_every_id_an_example_set_names() -> None:
    """`expected` only. A node label reaches `node_matches` as written and is never folded, so
    a criterion named there would be registered, never called, and reported with no
    denominator."""
    examples = [
        Example(id="q1", inputs={"q": "?"}, expected=criteria_key(), split="dev"),
        Example(id="q2", inputs={"q": "?"}, expected="a plain value", split="dev"),
        Example(
            id="q3",
            inputs={"q": "?"},
            expected="v",
            split="dev",
            expected_by_node={"hunt": Criteria([Criterion(id="cited", text="cited a source")])},
        ),
    ]

    assert criteria_in(examples) == {
        "not_read": "a book the reader has not read",
        "subject": "shares a subject with the shelf",
        "length": "under 400 pages",
    }


# -- the rates -----------------------------------------------------------------------------


def graded(example_id: str, outcome: Outcome, grade: float, index: int = 0) -> RolloutOutcome:
    return RolloutOutcome(
        example_id=example_id,
        rollout=index,
        seed=index,
        outcome=outcome,
        verdict=Verdict(grade=grade, met=int(grade * 4), total=4),
    )


class TestTheTwoNewRates:
    def _rollouts(self) -> tuple[RolloutOutcome, ...]:
        """Four examples: right, partly right at 0.75, confidently wrong, right absence."""
        return (
            graded("q1", Outcome.CORRECT, 1.0),
            graded("q2", Outcome.PARTIALLY_CORRECT, 0.75),
            graded("q3", Outcome.FALSE_CONFIDENCE, 0.0),
            RolloutOutcome(example_id="q4", rollout=0, seed=0, outcome=Outcome.CORRECT_ABSTENTION),
        )

    def _metrics(self) -> dict[str, Any]:
        absence = {"q1": False, "q2": False, "q3": False, "q4": True}
        return aggregate(self._rollouts(), absence, seed=41)

    def test_a_partly_right_answer_is_out_of_the_false_confidence_rate(self) -> None:
        """The measured cost of the old shape: it was reported as a confident wrong value."""
        assert self._metrics()["false_confidence_rate"].value == pytest.approx(0.25)

    def test_it_is_in_the_partially_correct_rate(self) -> None:
        assert self._metrics()["partially_correct_rate"].value == pytest.approx(0.25)

    def test_accuracy_gives_it_nothing(self) -> None:
        assert self._metrics()["accuracy"].value == pytest.approx(0.5)

    def test_graded_accuracy_gives_it_its_grade(self) -> None:
        assert self._metrics()["graded_accuracy"].value == pytest.approx((1 + 0.75 + 0 + 1) / 4)

    def test_it_is_in_precision_when_asserting_s_denominator_and_not_its_numerator(self) -> None:
        """Three rollouts asserted; one was right. Leaving partials out would raise this."""
        precision = self._metrics()["precision_when_asserting"]

        assert precision.rollouts == 3
        assert precision.value == pytest.approx(1 / 3)

    def test_every_scored_outcome_is_in_some_numerator(self) -> None:
        """A rollout in no rate's numerator is invisible: this is why there is an eighth rate.

        Read off the specs rather than a list written here, so adding an outcome without a rate
        that counts it fails. A verdict is attached only where ``classify`` produces one, since
        which rollouts a rate is over is now read off the verdict rather than off the outcome
        alone.

        The outcomes a rate is not over are skipped by ``causes_of`` rather than by a list, so
        an outcome that is its own reason for being outside every rate, as ``no_response`` and
        ``left_the_slice`` are, says so once and is not restated here.
        """
        from simple_agents.evaluation.outcomes import causes_of

        carries_a_verdict = (
            Outcome.CORRECT,
            Outcome.PARTIALLY_CORRECT,
            Outcome.FALSE_CONFIDENCE,
        )
        for outcome in Outcome:
            grade = 0.75 if outcome is Outcome.PARTIALLY_CORRECT else 0.0
            rollout = (
                graded("q1", outcome, grade)
                if outcome in carries_a_verdict
                else RolloutOutcome(example_id="q1", rollout=0, seed=0, outcome=outcome)
            )
            if causes_of(rollout):
                continue
            absence = outcome is Outcome.CORRECT_ABSTENTION
            scored = [
                name
                for name, (_, included, score, _) in _SPECS.items()
                if included(rollout, absence) and score(rollout, absence) > 0.0
            ]

            assert scored, f"{outcome.value} is in no rate's numerator"

    def test_an_evaluation_with_no_partial_reports_accuracy_twice(self) -> None:
        rollouts = (graded("q1", Outcome.CORRECT, 1.0), graded("q2", Outcome.FALSE_CONFIDENCE, 0.0))
        metrics = aggregate(rollouts, {"q1": False, "q2": False}, seed=41)

        assert metrics["graded_accuracy"].value == metrics["accuracy"].value


class TestWhichDenominatorAnIncompleteAnswerFallsIn:
    """An answer given and an answer withheld, separated by what was put forward.

    The outcome does not separate them: `missed` covers a rollout that reported absence and one
    that filled some fields and left a `required` one alone. Reading the outcome alone put the
    second in `abstention_rate`, which is over rollouts that reported absence, and took it out of
    `precision_when_asserting`, where it scores 0.0 and was raising the figure by leaving.
    """

    def _rollout(self, met: set[str], absent: set[str]) -> RolloutOutcome:
        def decide(name: str) -> Any:
            if name in absent:
                return lambda s: Unknown(reason="the record leaves it empty")
            return lambda s, name=name: name in met

        outcome, verdict = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria={name: decide(name) for name in ("not_read", "subject", "length")},
        )
        return RolloutOutcome(
            example_id="q1", rollout=0, seed=41, outcome=outcome, answer="x", verdict=verdict
        )

    def _metrics(self, rollout: RolloutOutcome) -> dict[str, Any]:
        return aggregate([rollout], {"q1": False}, seed=41)

    def test_a_part_asserted_beside_a_required_silence_is_an_answer_given(self) -> None:
        """The case the shipped reading got wrong: it named a subject and declined the rest."""
        rollout = self._rollout({"subject"}, absent={"not_read", "length"})
        metrics = self._metrics(rollout)

        assert rollout.outcome is Outcome.MISSED, "a required condition is unmet"
        assert rollout.verdict.asserted is True
        assert metrics["precision_when_asserting"].rollouts == 1
        assert metrics["precision_when_asserting"].value == 0.0
        assert metrics["abstention_rate"].value == 0.0

    def test_saying_nothing_anywhere_is_an_answer_withheld(self) -> None:
        rollout = self._rollout(set(), absent={"not_read", "subject", "length"})
        metrics = self._metrics(rollout)

        assert rollout.verdict.asserted is False
        assert metrics["precision_when_asserting"].rollouts == 0
        assert metrics["abstention_rate"].value == 1.0

    def test_a_condition_met_by_silence_is_still_nothing_put_forward(self) -> None:
        """`expects_absence` folds silence into a met part, so `asserted` is read before it."""
        key = Criteria(
            [
                Criterion(id="vendor", text="the vendor"),
                Criterion(
                    id="po_number",
                    text="the PO number, or that none is stated",
                    expects_absence=True,
                ),
            ]
        )
        silent = lambda s: Unknown(reason="the record leaves it empty")
        outcome, verdict = classify(
            scoring("x", key),
            matches=EXACT,
            criteria={"vendor": silent, "po_number": silent},
        )
        rollout = RolloutOutcome(
            example_id="q1", rollout=0, seed=41, outcome=outcome, answer="x", verdict=verdict
        )

        assert verdict.parts == {"vendor": None, "po_number": True}
        assert verdict.asserted is False
        assert rollout.asserted is False
        assert self._metrics(rollout)["precision_when_asserting"].rollouts == 0

    def test_an_outcome_with_no_verdict_answers_on_its_own(self) -> None:
        """A rollout that reported absence end to end is compared against nothing."""
        rollout = RolloutOutcome(
            example_id="q1", rollout=0, seed=41, outcome=Outcome.CORRECT_ABSTENTION
        )

        assert rollout.verdict is None
        assert rollout.asserted is False

    def test_the_file_round_trips_what_was_put_forward(self) -> None:
        rollout = self._rollout({"subject"}, absent={"not_read", "length"})

        read = RolloutOutcome.from_record(json.loads(json.dumps(rollout.to_record())))

        assert read.verdict.asserted is True
        assert read.asserted is True

    def test_a_file_written_before_this_reads_as_an_answer_given(self) -> None:
        """`asserted` defaults to True, which is what every verdict written before it meant."""
        record = json.loads(json.dumps(self._rollout({"subject"}, absent={"length"}).to_record()))
        del record["verdict"]["asserted"]

        assert RolloutOutcome.from_record(record).verdict.asserted is True


# -- a figure per criterion ------------------------------------------------------------------


class TestCriterionFigures:
    def _rollouts(self) -> tuple[RolloutOutcome, ...]:
        def one(example_id: str, parts: dict[str, bool], index: int) -> RolloutOutcome:
            return RolloutOutcome(
                example_id=example_id,
                rollout=index,
                seed=index,
                outcome=Outcome.PARTIALLY_CORRECT,
                verdict=Verdict(grade=0.5, met=1, total=2, parts=parts),
            )

        return (
            one("q1", {"not_read": True, "length": False}, 0),
            one("q1", {"not_read": True, "length": True}, 1),
            one("q2", {"not_read": False, "length": True}, 0),
            one("q2", {"not_read": False, "length": True}, 1),
        )

    def _figures(self) -> dict[str, Any]:
        return criterion_metrics(
            self._rollouts(),
            {"not_read": "a book the reader has not read", "length": "under 400 pages"},
            {"q1": ("not_read", "length"), "q2": ("not_read", "length")},
            seed=41,
        )

    def test_one_figure_per_criterion_over_both_examples(self) -> None:
        figures = self._figures()

        assert set(figures) == {"not_read", "length"}
        assert figures["not_read"].value == pytest.approx(0.5)
        assert figures["length"].value == pytest.approx(0.75)

    def test_the_criterion_s_text_is_the_definition(self) -> None:
        assert self._figures()["length"].definition == "under 400 pages"

    def test_each_carries_its_own_n(self) -> None:
        assert self._figures()["length"].interval.n == 2

    def test_a_rollout_judged_against_nothing_is_outside_every_figure(self) -> None:
        """An abstention carries no verdict, so it is in no criterion's denominator."""
        rollouts = (
            *self._rollouts(),
            RolloutOutcome(example_id="q3", rollout=0, seed=0, outcome=Outcome.MISSED),
        )

        figures = criterion_metrics(
            rollouts,
            {"not_read": "a book the reader has not read"},
            {"q1": ("not_read",), "q2": ("not_read",), "q3": ("not_read",)},
            seed=41,
        )

        assert figures["not_read"].rollouts == 4

    def test_a_rollout_the_backend_never_answered_is_counted_beside_the_figure(self) -> None:
        rollouts = (
            *self._rollouts(),
            RolloutOutcome(example_id="q1", rollout=2, seed=2, outcome=Outcome.NO_RESPONSE),
        )

        figures = criterion_metrics(
            rollouts,
            {"not_read": "a book the reader has not read"},
            {"q1": ("not_read",), "q2": ("not_read",)},
            seed=41,
        )

        assert figures["not_read"].left_out == {"no_response": 1}


# -- end to end ------------------------------------------------------------------------------


BUDGET = Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None)

ANSWERS = {
    "Which retailer ships from Leeds?": '{"answer": "Kirkwall depot", "source": "doc"}',
    "Who founded Northgate?": '{"answer": "Alan Blair", "source": "doc"}',
}


def build_prompt(inputs, ctx):
    return Prompt.user("Answer the question: {question}", question=inputs["question"])


class ScriptedClient:
    def identity(self):
        return FakeModelClient().model_identity

    def complete(self, request):
        asked = request.messages[-1]["content"]
        for question, payload in ANSWERS.items():
            if question in asked:
                return fake_response(content=payload)
        raise AssertionError(f"nothing scripted for {asked!r}")


def two_examples(key: Any) -> ExampleSet:
    return ExampleSet(
        [
            Example(
                id="q1",
                inputs={"question": "Which retailer ships from Leeds?"},
                expected=key,
                split="held_out",
            ),
            Example(
                id="q2",
                inputs={"question": "Who founded Northgate?"},
                expected=key,
                split="held_out",
            ),
        ]
    )


def evaluate(tmp_path: Path, key: Any, **kwargs) -> Any:
    suite = EvalSuite(
        Pipeline([LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET),
        two_examples(key),
        answer="answer",
        matches=EXACT,
        **kwargs,
    )
    return suite.run(
        envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
        model=ScriptedClient(),
        split="held_out",
        k=2,
        seed=41,
        concurrency=1,
    )


LONG = Criteria(
    [
        Criterion(id="says_depot", text="the answer names a depot", weight=2),
        Criterion(id="says_year", text="the answer names a year"),
    ]
)
CHECKS = {
    "says_depot": lambda s: "depot" in str(s.answer),
    "says_year": lambda s: any(ch.isdigit() for ch in str(s.answer)),
}


class TestAnEvaluationOverCriteria:
    def test_a_partly_met_key_lands_in_the_new_outcome_and_the_new_rate(
        self, tmp_path: Path
    ) -> None:
        results = evaluate(tmp_path, LONG, criteria=CHECKS)

        outcomes = {r.outcome for r in results.rollouts}
        assert Outcome.PARTIALLY_CORRECT in outcomes
        assert results.metrics["partially_correct_rate"].value > 0.0

    def test_the_verdict_travels_into_the_results_file(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, LONG, criteria=CHECKS)
        written = results.write(tmp_path / "results.json")

        read = EvalResults.read(written)
        partial = [r for r in read.rollouts if r.outcome is Outcome.PARTIALLY_CORRECT][0]

        assert partial.verdict.parts == {"says_depot": True, "says_year": False}
        assert partial.verdict.grade == pytest.approx(2 / 3)

    def test_a_figure_per_criterion_is_reported(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, LONG, criteria=CHECKS)

        assert set(results.criteria) == {"says_depot", "says_year"}
        assert results.criteria["says_depot"].value == pytest.approx(0.5)
        assert results.criteria["says_year"].value == 0.0
        assert results.criteria["says_depot"].definition == "the answer names a depot"

    def test_the_figures_survive_the_file(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, LONG, criteria=CHECKS)
        read = EvalResults.read(results.write(tmp_path / "results.json"))

        assert read.criteria["says_depot"].value == pytest.approx(0.5)

    def test_the_report_prints_each_criterion_with_its_text(self, tmp_path: Path) -> None:
        printed = evaluate(tmp_path, LONG, criteria=CHECKS).report()

        assert "criteria met" in printed
        assert "the answer names a depot" in printed

    def test_each_check_s_version_is_recorded_beside_matches(self, tmp_path: Path) -> None:
        """Editing a check moves every rate, so a comparison has to be able to see it."""
        results = evaluate(tmp_path, LONG, criteria=CHECKS)

        recorded = results.config["criteria"]
        assert set(recorded) == {"says_depot", "says_year"}
        assert recorded["says_depot"]["text"] == "the answer names a depot"
        assert recorded["says_depot"]["version"].startswith("sha256:")

    def test_a_criterion_with_no_check_is_refused_at_construction(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            evaluate(tmp_path, LONG, criteria={"says_depot": CHECKS["says_depot"]})

        assert "'says_year'" in str(raised.value)
        assert "registers no check" in str(raised.value)

    def test_a_check_no_example_names_is_refused_at_construction(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            evaluate(tmp_path, LONG, criteria={**CHECKS, "spare": lambda s: True})

        assert "'spare'" in str(raised.value)
        assert "would never be called" in str(raised.value)


class TestComparingTwoEvaluationsOverCriteria:
    def test_each_criterion_is_paired(self, tmp_path: Path) -> None:
        before = evaluate(tmp_path / "before", LONG, criteria=CHECKS)
        after = evaluate(tmp_path / "after", LONG, criteria=CHECKS)

        comparison = compare(before, after)

        assert set(comparison.criteria) == {"says_depot", "says_year"}
        assert comparison.criteria["says_depot"].definition == "the answer names a depot"

    def test_a_moved_check_withholds_the_verdict_on_every_rate(self, tmp_path: Path) -> None:
        """A criterion decides an outcome exactly as `matches` does (FT-15)."""
        before = evaluate(tmp_path / "before", LONG, criteria=CHECKS)
        after = evaluate(
            tmp_path / "after",
            LONG,
            criteria={**CHECKS, "says_depot": lambda s: "DEPOT" in str(s.answer).upper()},
        )

        comparison = compare(before, after)

        assert comparison.metrics["accuracy"].rule_moved is not None
        assert comparison.criteria["says_depot"].rule_moved is not None
        assert comparison.criteria["says_year"].rule_moved is None

    def test_an_unchanged_check_leaves_the_verdict_alone(self, tmp_path: Path) -> None:
        before = evaluate(tmp_path / "before", LONG, criteria=CHECKS)
        after = evaluate(tmp_path / "after", LONG, criteria=CHECKS)

        comparison = compare(before, after)

        assert comparison.metrics["accuracy"].rule_moved is None
        assert comparison.criteria["says_depot"].rule_moved is None


# -- a condition the answer said nothing about ----------------------------------------------


ABSENT = lambda s: Unknown()


class TestACriterionMayReportAbsence:
    """The third return value, and what separates it from a wrong value.

    `False` is the answer asserting something and getting it wrong, which is the failure FT-10
    is named for. `Unknown()` is the answer asserting nothing there, which is the recoverable
    one. Before this they were one value.
    """

    def _checks(self, met: set[str], absent: set[str] = frozenset()) -> dict[str, Any]:
        def decide(name: str) -> Any:
            if name in absent:
                return ABSENT
            return lambda s, name=name: name in met

        return {name: decide(name) for name in ("not_read", "subject", "length")}

    def test_an_absent_condition_is_recorded_apart_from_a_wrong_one(self) -> None:
        _, verdict = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=self._checks({"not_read"}, absent={"length"}),
        )

        assert verdict.parts == {"not_read": True, "subject": False, "length": None}
        assert verdict.wrong == ("subject",)
        assert verdict.absent == ("length",)

    def test_an_absent_condition_earns_no_credit_and_keeps_its_weight(self) -> None:
        """Leaving a condition alone must not raise the grade it is scored against."""
        _, verdict = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=self._checks({"not_read"}, absent={"subject", "length"}),
        )

        assert verdict.grade == pytest.approx(1 / 4), "1 met of a declared weight of 1 + 2 + 1"
        assert (verdict.met, verdict.total) == (1, 3)

    def test_saying_nothing_anywhere_is_a_miss_rather_than_a_confident_wrong_answer(
        self,
    ) -> None:
        """An answer that invented nothing is the recoverable failure, not the dangerous one."""
        outcome, verdict = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=self._checks(set(), absent={"not_read", "subject", "length"}),
        )

        assert outcome is Outcome.MISSED
        assert verdict.absent == ("not_read", "subject", "length")
        assert verdict.asserted_wrong is False

    def test_one_wrong_value_among_absences_is_a_confident_wrong_answer(self) -> None:
        outcome, verdict = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=self._checks(set(), absent={"not_read", "length"}),
        )

        assert outcome is Outcome.FALSE_CONFIDENCE
        assert verdict.wrong == ("subject",)

    def test_some_met_and_some_absent_is_partly_right(self) -> None:
        outcome, verdict = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=self._checks({"not_read", "subject"}, absent={"length"}),
        )

        assert outcome is Outcome.PARTIALLY_CORRECT
        assert verdict.grade == pytest.approx(3 / 4)

    def test_a_required_condition_left_alone_is_a_miss_not_a_confident_wrong_answer(
        self,
    ) -> None:
        """`required` decides that the answer is not partly right; it does not decide which
        failure it was. The agent met two conditions and invented nothing."""
        outcome, verdict = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=self._checks({"subject", "length"}, absent={"not_read"}),
        )

        assert outcome is Outcome.MISSED
        assert verdict.unmet_required == ("not_read",)
        assert verdict.grade == pytest.approx(3 / 4), "the grade is recorded beside it"

    def test_a_required_condition_answered_wrongly_is_unchanged(self) -> None:
        outcome, _ = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=self._checks({"subject", "length"}),
        )

        assert outcome is Outcome.FALSE_CONFIDENCE

    def test_a_criterion_check_may_still_not_return_anything_else(self) -> None:
        with pytest.raises(ConfigurationError, match="Unknown"):
            classify(
                scoring("x", criteria_key()),
                matches=EXACT,
                criteria={**self._checks(set()), "length": lambda s: 0.5},
            )

    def test_matches_may_not_report_absence(self) -> None:
        """Only a condition can say the answer was silent about it. A whole answer that is
        absent is read before any key
        (`docs/evaluation.md` §2)."""
        with pytest.raises(ConfigurationError, match="A comparison is yes or no"):
            classify(scoring("x", AnyOf(["a"])), matches=ABSENT)

    def test_a_check_is_told_which_condition_it_is_deciding(self) -> None:
        """One function registered under two ids has nothing else to tell them apart."""
        seen: list[str | None] = []

        def note(s: Scoring) -> bool:
            seen.append(s.criterion_id)
            return True

        classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria=dict.fromkeys(("not_read", "subject", "length"), note),
        )

        assert seen == ["not_read", "subject", "length"]

    def test_a_node_comparison_may_not_report_absence_either(self, tmp_path: Path) -> None:
        """`node_matches` coerced its return with bool(), and `Unknown` is falsy, so a check
        written for `criteria=` and reused there recorded the node as answered wrongly."""
        examples = ExampleSet(
            [
                Example(
                    id="q1",
                    inputs={"question": "Which retailer ships from Leeds?"},
                    expected="Kirkwall depot",
                    split="held_out",
                    expected_by_node={"extract": "Kirkwall depot"},
                ),
            ]
        )
        suite = EvalSuite(
            Pipeline(
                [LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET
            ),
            examples,
            answer="answer",
            matches=EXACT,
            node_matches={"extract": ABSENT},
        )

        with pytest.raises(ConfigurationError, match="A comparison is yes or no"):
            suite.run(
                envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
                model=ScriptedClient(),
                split="held_out",
                k=1,
                seed=41,
                concurrency=1,
            )

    def test_matches_is_told_no_criterion(self) -> None:
        seen: list[str | None] = []

        def note(s: Scoring) -> bool:
            seen.append(s.criterion_id)
            return True

        classify(scoring("x", AnyOf(["a"])), matches=note)

        assert seen == [None]


class TestNothingMovesWhereNoCheckReportsAbsence:
    """The compatibility this change had to keep: with no absence reported, every key sorts a
    miss exactly where it sorted one before."""

    @pytest.mark.parametrize(
        "key,answer",
        [
            ("Kirkwall", "Northgate"),
            (AnyOf(["Kirkwall", "Kirkwall Ltd"]), "Northgate"),
            (Contains(["Leeds", "Kirkwall", "Perth"]), "nothing here"),
            (WithinTolerance(52.0, relative=0.02), 91.0),
        ],
    )
    def test_a_miss_is_still_a_confident_wrong_answer(self, key: Any, answer: Any) -> None:
        outcome, verdict = classify(scoring(answer, key), matches=CONTAINED)

        assert outcome is Outcome.FALSE_CONFIDENCE
        assert verdict.asserted_wrong is True

    def test_a_partly_held_collection_is_still_partly_right(self) -> None:
        outcome, verdict = classify(
            scoring("Leeds and Perth", Contains(["Leeds", "Kirkwall", "Perth"])),
            matches=CONTAINED,
        )

        assert outcome is Outcome.PARTIALLY_CORRECT
        assert verdict.asserted_wrong is True, "a value the answer had to hold and did not"

    def test_every_condition_wrong_is_still_a_confident_wrong_answer(self) -> None:
        outcome, _ = classify(
            scoring("x", criteria_key()),
            matches=EXACT,
            criteria={name: (lambda s: False) for name in criteria_key().ids},
        )

        assert outcome is Outcome.FALSE_CONFIDENCE


class TestDeclaringThatAConditionExpectsAbsence:
    """`expects_absence` puts the key's side of absence on the condition, and FT-04 reads it."""

    def _key(self) -> Criteria:
        return Criteria(
            [
                Criterion(id="vendor", text="names the vendor"),
                Criterion(
                    id="po_number", text="reports that no PO number is stated", expects_absence=True
                ),
            ]
        )

    def test_the_example_names_the_conditions_whose_answer_is_absence(self) -> None:
        example = Example(id="i1", inputs={"doc": "..."}, expected=self._key(), split="held_out")

        assert example.absent_parts == ("po_number",)

    def test_the_whole_answer_is_still_not_read_as_absent(self) -> None:
        """`Example.expects_absence` decides rate denominators, and a record with one empty
        field still holds values."""
        example = Example(id="i1", inputs={"doc": "..."}, expected=self._key(), split="held_out")

        assert example.expects_absence is False

    def test_a_plain_key_names_no_conditions(self) -> None:
        example = Example(id="q1", inputs={"q": "?"}, expected="Kirkwall", split="dev")

        assert example.absent_parts == ()

    def test_reporting_absence_where_the_condition_expects_it_meets_it(self) -> None:
        """Absence on both sides, one level down. The check says the answer gave nothing and
        the key says nothing was there, so the condition is met."""
        outcome, verdict = classify(
            scoring("x", self._key()),
            matches=EXACT,
            criteria={"vendor": lambda s: True, "po_number": ABSENT},
        )

        assert outcome is Outcome.CORRECT
        assert verdict.parts == {"vendor": True, "po_number": True}
        assert verdict.absent == ()

    def test_asserting_a_value_where_the_condition_expects_absence_is_wrong(self) -> None:
        """Inventing a PO number for an invoice that states none is the dangerous failure, and
        the answer is partly right because it did give the vendor."""
        outcome, verdict = classify(
            scoring("x", self._key()),
            matches=EXACT,
            criteria={"vendor": lambda s: True, "po_number": lambda s: False},
        )

        assert outcome is Outcome.PARTIALLY_CORRECT
        assert verdict.wrong == ("po_number",)
        assert verdict.absent == ()

    def test_an_invented_value_is_wrong_whatever_the_check_made_of_it(self) -> None:
        """The right answer here is that the value is not there, so reporting it is the only
        way to meet the condition. Crediting an asserted value here would score an invented
        one as right, which is the failure FT-10 is named for."""
        outcome, verdict = classify(
            scoring("x", self._key()),
            matches=EXACT,
            criteria={"vendor": lambda s: True, "po_number": lambda s: True},
        )

        assert outcome is Outcome.PARTIALLY_CORRECT
        assert verdict.parts == {"vendor": True, "po_number": False}
        assert verdict.wrong == ("po_number",)

    def test_inventing_a_value_and_meeting_nothing_else_is_a_confident_wrong_answer(
        self,
    ) -> None:
        outcome, verdict = classify(
            scoring("x", self._key()),
            matches=EXACT,
            criteria={"vendor": lambda s: False, "po_number": lambda s: False},
        )

        assert outcome is Outcome.FALSE_CONFIDENCE
        assert verdict.asserted_wrong is True

    def test_a_key_that_expects_absence_throughout_is_met_by_saying_nothing(self) -> None:
        """Every condition's right answer is that the value is not there, and the answer gave
        exactly that, so the key was met in full."""
        key = Criteria(
            [
                Criterion(
                    id="vendor", text="the vendor, or that none is named", expects_absence=True
                ),
                Criterion(
                    id="po_number",
                    text="the PO number, or that none is stated",
                    expects_absence=True,
                ),
            ]
        )
        outcome, verdict = classify(
            scoring("x", key),
            matches=EXACT,
            criteria={"vendor": ABSENT, "po_number": ABSENT},
        )

        assert outcome is Outcome.CORRECT
        assert verdict.grade == 1.0
        assert verdict.absent == ()

    def test_meeting_one_condition_by_silence_is_partly_right_not_a_miss(self) -> None:
        """An answer is `missed` where it met *none* of its key. Meeting one condition by
        correctly reporting absence is credit, so the rollout is partly right even though it
        asserted nothing anywhere."""
        outcome, verdict = classify(
            scoring("x", self._key()),
            matches=EXACT,
            criteria={"vendor": ABSENT, "po_number": ABSENT},
        )

        assert outcome is Outcome.PARTIALLY_CORRECT
        assert verdict.grade == pytest.approx(0.5)
        assert verdict.parts == {"vendor": None, "po_number": True}

    def test_a_condition_expecting_a_value_still_reads_silence_as_unmet(self) -> None:
        """The same check, the same silence, and the other declaration."""
        key = Criteria([Criterion(id="po_number", text="gives the PO number")])
        outcome, verdict = classify(
            scoring("x", key), matches=EXACT, criteria={"po_number": ABSENT}
        )

        assert outcome is Outcome.MISSED
        assert verdict.absent == ("po_number",)

    def test_it_survives_the_file(self) -> None:
        example = Example(id="i1", inputs={"doc": "..."}, expected=self._key(), split="held_out")

        read = Example.from_json(json.loads(json.dumps(example.to_json())))

        assert read.absent_parts == ("po_number",)

    def test_a_key_written_before_the_field_existed_still_reads(self) -> None:
        raw = {
            "id": "q4",
            "split": "held_out",
            "inputs": {"q": "?"},
            "expected": {
                "type": "criteria",
                "criteria": [
                    {"id": "length", "text": "under 400 pages", "weight": 1.0, "required": False},
                ],
            },
        }

        read = Example.from_json(raw)

        assert read.expected.criteria[0].expects_absence is False
        assert read.absent_parts == ()


class TestTheFigurePerCriterionSaysHowMuchOfTheShortfallIsSilence:
    def _rollouts(self) -> tuple[RolloutOutcome, ...]:
        def one(example_id: str, parts: dict[str, Any], index: int) -> RolloutOutcome:
            return RolloutOutcome(
                example_id=example_id,
                rollout=index,
                seed=index,
                outcome=Outcome.PARTIALLY_CORRECT,
                verdict=Verdict(grade=0.5, met=1, total=2, parts=parts),
            )

        return (
            one("q1", {"vendor": True, "po_number": None}, 0),
            one("q1", {"vendor": True, "po_number": None}, 1),
            one("q2", {"vendor": False, "po_number": True}, 0),
            one("q2", {"vendor": True, "po_number": False}, 1),
        )

    def _figures(self) -> dict[str, Any]:
        return criterion_metrics(
            self._rollouts(),
            {"vendor": "names the vendor", "po_number": "gives the PO number"},
            {"q1": ("vendor", "po_number"), "q2": ("vendor", "po_number")},
            seed=41,
        )

    def test_an_absent_verdict_is_unmet(self) -> None:
        assert self._figures()["po_number"].value == pytest.approx(0.25)

    def test_it_stays_inside_the_denominator(self) -> None:
        """It measured the agent: the agent chose to say nothing there."""
        assert self._figures()["po_number"].interval.n == 2
        assert self._figures()["po_number"].rollouts == 4

    def test_the_count_of_silences_is_reported_beside_it(self) -> None:
        figures = self._figures()

        assert figures["po_number"].absent == 2
        assert figures["vendor"].absent == 0

    def test_a_rollout_that_reported_absence_per_condition_is_inside_the_figure(self) -> None:
        """It was judged. Only a rollout that reported absence end to end, failed, or got no
        answer carries no verdict and falls outside."""
        figures = self._figures()

        assert figures["po_number"].rollouts == 4
        assert figures["po_number"].interval.n == 2

    def test_the_count_survives_the_file(self) -> None:
        figure = self._figures()["po_number"]

        assert type(figure).from_record(figure.to_record()).absent == 2


SILENT = Criteria(
    [
        Criterion(id="says_depot", text="the answer names a depot", weight=2),
        Criterion(id="says_year", text="the answer gives the year"),
    ]
)
DECLARED = Criteria(
    [
        Criterion(id="says_depot", text="the answer names a depot", weight=2),
        Criterion(id="says_year", text="the year, or that none is recorded", expects_absence=True),
    ]
)
SILENT_CHECKS = {
    "says_depot": lambda s: "depot" in str(s.answer),
    "says_year": lambda s: Unknown(),
}


class TestAnEvaluationWhereAConditionWasLeftAlone:
    def test_the_rollouts_carry_the_absent_part(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, SILENT, criteria=SILENT_CHECKS)

        q1 = [r for r in results.rollouts if r.example_id == "q1"]
        assert all(r.verdict.parts["says_year"] is None for r in q1)
        assert all(r.outcome is Outcome.PARTIALLY_CORRECT for r in q1)

    def test_an_answer_that_invented_nothing_is_not_a_confident_wrong_answer(
        self, tmp_path: Path
    ) -> None:
        """An answer that invented nothing is the recoverable failure, not the dangerous one."""
        results = evaluate(
            tmp_path,
            SILENT,
            criteria={**SILENT_CHECKS, "says_depot": lambda s: Unknown()},
        )

        assert {r.outcome for r in results.rollouts} == {Outcome.MISSED}
        assert results.metrics["false_confidence_rate"].value == 0.0
        assert results.metrics["abstention_rate"].value == 1.0

    def test_the_figure_per_condition_carries_the_silences(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, SILENT, criteria=SILENT_CHECKS)

        assert results.criteria["says_year"].absent == 4
        assert results.criteria["says_year"].value == 0.0

    def test_the_file_round_trips_an_absent_part(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, SILENT, criteria=SILENT_CHECKS)
        path = tmp_path / "results.json"
        results.write(path)

        read = EvalResults.read(path)

        assert read.rollouts[0].verdict.parts["says_year"] is None
        assert read.criteria["says_year"].absent == 4

    def test_the_report_says_how_many_asserted_nothing(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, SILENT, criteria=SILENT_CHECKS)

        assert "4 asserted nothing" in results.report()


class TestAnEvaluationWhereSayingNothingWasRight:
    """The same answers and the same checks, against a key that declares the absent case.

    Found by running the first arm of this against `gemini-3.1-flash-lite`: the model read a
    record stating no manager, reported absence, and was scored partly right.
    """

    def test_reporting_absence_where_the_key_expects_it_is_met(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, DECLARED, criteria=SILENT_CHECKS)

        q1 = [r for r in results.rollouts if r.example_id == "q1"]
        assert all(r.verdict.parts["says_year"] is True for r in q1)
        assert all(r.outcome is Outcome.CORRECT for r in q1)

    def test_it_is_not_counted_as_a_silence(self, tmp_path: Path) -> None:
        """`absent` says how much of the shortfall was silence, and this was not a shortfall."""
        results = evaluate(tmp_path, DECLARED, criteria=SILENT_CHECKS)

        assert results.criteria["says_year"].absent == 0
        assert results.criteria["says_year"].value == 1.0

    def test_the_example_set_declares_the_absent_case(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, DECLARED, criteria=SILENT_CHECKS)

        assert results.examples["q1"]["absent_parts"] == ["says_year"]


# -- absences travelling through the surfaces beside a run ---------------------------------


class TestAbsencesThroughTheSurfacesBesideARun:
    """`compare()`, `rescore` and a variant sweep each read a verdict back rather than
    computing it, so each is a place a tri-state part could be lost."""

    def test_comparing_two_evaluations_where_one_carries_absences(self, tmp_path: Path) -> None:
        before = evaluate(tmp_path / "before", SILENT, criteria=SILENT_CHECKS)
        after = evaluate(
            tmp_path / "after",
            SILENT,
            criteria={**SILENT_CHECKS, "says_year": lambda s: True},
        )

        comparison = compare(before, after)

        assert before.criteria["says_year"].absent == 4
        assert after.criteria["says_year"].absent == 0
        assert set(comparison.criteria) == {"says_depot", "says_year"}

    def test_a_moved_check_still_withholds_the_verdict_where_absences_are_involved(
        self, tmp_path: Path
    ) -> None:
        """The silence is the check's decision, so changing it changes every rate."""
        before = evaluate(tmp_path / "before", SILENT, criteria=SILENT_CHECKS)
        after = evaluate(
            tmp_path / "after",
            SILENT,
            criteria={**SILENT_CHECKS, "says_year": lambda s: True},
        )

        comparison = compare(before, after)

        assert comparison.criteria["says_year"].rule_moved is not None
        assert comparison.metrics["accuracy"].moved is None

    def test_rescoring_from_disk_reproduces_every_absent_part(self, tmp_path: Path) -> None:
        suite = EvalSuite(
            Pipeline(
                [LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET
            ),
            two_examples(SILENT),
            answer="answer",
            matches=EXACT,
            criteria=SILENT_CHECKS,
        )
        live = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
            model=ScriptedClient(),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

        rescored = suite.rescore(run_dir=evaluation_dir(tmp_path, live.eval_id), split="held_out")

        assert [r.verdict.parts for r in rescored.rollouts] == [
            r.verdict.parts for r in live.rollouts
        ]
        assert [r.outcome for r in rescored.rollouts] == [r.outcome for r in live.rollouts]
        assert rescored.criteria["says_year"].absent == live.criteria["says_year"].absent

    def test_a_variant_sweep_over_a_key_that_declares_an_absent_case(self, tmp_path: Path) -> None:
        from simple_agents.evaluation.variants import compare_variants

        def asked_differently(inputs, ctx):
            return Prompt.user(
                "Please answer this question: {question}", question=inputs["question"]
            )

        base = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET
        )
        reworded = Pipeline(
            [LLMNode(asked_differently, output_schema=Answer, node_id="extract")], budget=BUDGET
        )
        suite = EvalSuite(
            base,
            two_examples(DECLARED),
            answer="answer",
            matches=EXACT,
            criteria=SILENT_CHECKS,
        )

        comparison = compare_variants(
            suite,
            {"reworded prompt": reworded},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
            model=ScriptedClient(),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

        assert comparison.baseline.criteria["says_year"].value == 1.0
        assert comparison.baseline.criteria["says_year"].absent == 0
        assert all(r.verdict.parts["says_year"] is True for r in comparison.baseline.rollouts)


# -- the documented rules, against every case they cover -----------------------------------


class TestEveryCaseAgreesWithTheDocumentedRules:
    """The rules as `docs/evaluation.md` §1.6 and §2 state them, implemented here and compared
    against the library over every combination.

    Four verification passes over this feature each found a statement that had drifted from the
    behaviour, because the prose and the code were written from the design rather than from each
    other. This is the pair that cannot drift: `_by_the_documented_rules` is written from the
    documents and the library is written from the design, and they are compared on 72 cases.

    The rules, in the documents' own words:

    - A condition declaring `expects_absence` has absence as its right answer, so reporting it
      meets the condition and an asserted value is wrong whatever the check returned.
    - Otherwise a check's `True` is met, `False` is wrong, and `Unknown` is absent and unmet.
    - The grade is the weight met over the weight declared, an absent weight staying in the
      denominator.
    - An answer is not partly right where it met none of the key or missed a `required`
      condition. It is then `false_confidence` if any part was asserted and wrong, and `missed`
      otherwise.
    """

    RETURNS = {"met": True, "wrong": False, "silent": None}

    def _by_the_documented_rules(self, conditions: list[dict[str, Any]]) -> tuple[Any, ...]:
        parts: dict[str, Any] = {}
        weight_met = weight_all = 0.0
        unmet_required: list[str] = []
        for c in conditions:
            returned = self.RETURNS[c["returns"]]
            if c["declares"]:
                part = returned is None
            else:
                part = None if returned is None else returned
            parts[c["id"]] = part
            weight_all += c["weight"]
            if part is True:
                weight_met += c["weight"]
            elif c["required"]:
                unmet_required.append(c["id"])
        grade = weight_met / weight_all if weight_all else 0.0
        asserted_wrong = any(p is False for p in parts.values())
        if unmet_required or grade <= 0.0:
            outcome = Outcome.FALSE_CONFIDENCE if asserted_wrong else Outcome.MISSED
        elif grade >= 1.0:
            outcome = Outcome.CORRECT
        else:
            outcome = Outcome.PARTIALLY_CORRECT
        return outcome, pytest.approx(grade), parts, tuple(unmet_required)

    def _conditions(self, a_ret, b_ret, a_dec, b_dec, a_req) -> list[dict[str, Any]]:
        return [
            {"id": "a", "returns": a_ret, "declares": a_dec, "weight": 2.0, "required": a_req},
            {"id": "b", "returns": b_ret, "declares": b_dec, "weight": 1.0, "required": False},
        ]

    @pytest.mark.parametrize("a_ret", ["met", "wrong", "silent"])
    @pytest.mark.parametrize("b_ret", ["met", "wrong", "silent"])
    @pytest.mark.parametrize("a_dec", [False, True])
    @pytest.mark.parametrize("b_dec", [False, True])
    @pytest.mark.parametrize("a_req", [False, True])
    def test_one_case(self, a_ret, b_ret, a_dec, b_dec, a_req) -> None:
        conditions = self._conditions(a_ret, b_ret, a_dec, b_dec, a_req)
        returns = {"met": True, "wrong": False, "silent": Unknown()}
        key = Criteria(
            [
                Criterion(
                    id=c["id"],
                    text=f"condition {c['id']}",
                    weight=c["weight"],
                    required=c["required"],
                    expects_absence=c["declares"],
                )
                for c in conditions
            ]
        )

        outcome, verdict = classify(
            scoring("an answer", key),
            matches=EXACT,
            criteria={c["id"]: (lambda s, r=c["returns"]: returns[r]) for c in conditions},
        )

        assert (outcome, verdict.grade, verdict.parts, verdict.unmet_required) == (
            self._by_the_documented_rules(conditions)
        )
        assert verdict.absent == tuple(n for n, p in verdict.parts.items() if p is None)
        assert verdict.wrong == tuple(n for n, p in verdict.parts.items() if p is False)
        assert verdict.met == sum(1 for p in verdict.parts.values() if p is True)
        assert verdict.total == len(verdict.parts)


class TestThePairsTheBuilderIsShown:
    """`too_similar` asks a builder to judge pairs, so something has to produce them.

    Dogfood #4's set was clean at 0.8, 0.6 and 0.4, so `contamination` returned nothing at
    every threshold the coding agent tried, and what reached the builder was the sweep. He
    reported being asked about "contamination or something going from 0.8 to 0.4 or whatever.
    No context given, no defining the terms."
    """

    def _set(self):
        from simple_agents.evaluation import Example, ExampleSet

        return ExampleSet(
            [
                Example(
                    id="d1",
                    inputs={"q": "grimdark fantasy, morally grey"},
                    expected="A",
                    split="dev",
                    source="bookA",
                ),
                Example(
                    id="d2",
                    inputs={"q": "a cosy village mystery"},
                    expected="B",
                    split="dev",
                    source="bookB",
                ),
                Example(
                    id="h1",
                    inputs={"q": "gritty fantasy, ambiguous heroes"},
                    expected="C",
                    split="held_out",
                    source="bookC",
                ),
                Example(
                    id="h2",
                    inputs={"q": "hard science fiction, first contact"},
                    expected="D",
                    split="held_out",
                    source="bookD",
                ),
            ]
        )

    def test_a_clean_set_still_has_pairs_to_show(self) -> None:
        examples = self._set()

        assert examples.contamination(threshold=0.4).clean
        assert examples.nearest_cross_split(n=2)

    def test_a_pair_carries_both_texts(self) -> None:
        """The builder judges the wording, so ids and a percentage are not enough."""
        closest = self._set().nearest_cross_split(n=1)[0]

        assert closest.left_text == "grimdark fantasy, morally grey"
        assert closest.right_text == "gritty fantasy, ambiguous heroes"
        assert closest.left_split == "dev"
        assert closest.right_split == "held_out"

    def test_the_closest_pair_comes_first(self) -> None:
        found = self._set().nearest_cross_split(n=4)

        assert [pair.similarity for pair in found] == sorted(
            (pair.similarity for pair in found), reverse=True
        )

    def test_a_shared_source_is_named(self) -> None:
        from simple_agents.evaluation import Example, ExampleSet

        examples = ExampleSet(
            [
                Example(id="d1", inputs={"q": "one"}, expected="A", split="dev", source="doc"),
                Example(id="h1", inputs={"q": "two"}, expected="B", split="held_out", source="doc"),
            ]
        )

        assert examples.nearest_cross_split(n=1)[0].shared_source == "doc"

    def test_examples_inside_one_split_are_not_compared(self) -> None:
        from simple_agents.evaluation import Example, ExampleSet

        examples = ExampleSet(
            [
                Example(id="d1", inputs={"q": "same"}, expected="A", split="dev"),
                Example(id="d2", inputs={"q": "same"}, expected="B", split="dev"),
            ]
        )

        assert examples.nearest_cross_split(n=5) == ()

    def test_n_below_one_is_refused_by_name(self) -> None:
        import pytest

        from simple_agents.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="n is at least 1"):
            self._set().nearest_cross_split(n=0)
