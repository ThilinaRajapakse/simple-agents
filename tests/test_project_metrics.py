"""A metric the library does not ship: declaring it, what it is over, and what a comparison does.

Every fixture is handcrafted, so what each metric should report is fixed before the code runs.
The end-to-end tests run a real pipeline against a scripted client, because what `over` decides
is which rollouts the runner calls the score function on, which a hand-built results object
cannot show.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Budget,
    Cassette,
    ConfigurationError,
    FakeModelClient,
    LLMNode,
    Pipeline,
    RunEnvelope,
    Unknown,
)
from simple_agents.evaluation import (
    Example,
    ExampleSet,
    Outcome,
    Over,
    ProjectMetric,
    ProjectRatio,
    RolloutOutcome,
    Scoring,
    bootstrap_ci,
    compare,
)
from simple_agents.evaluation.metrics import (
    METRIC_DEFINITIONS,
    RATE,
    aggregate,
    score_of,
    scores_this_rollout,
)
from simple_agents.evaluation.ratios import ratio_of
from simple_agents.evaluation.results import EvalResults
from simple_agents.evaluation.runner import EvalSuite
from simple_agents.models import fake_response

from schemas import Answer

BUDGET = Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None)
EXACT = lambda s: s.answer == s.expected


def build_prompt(inputs, ctx):
    return f"Answer the question: {inputs['question']}"


ANSWERS = {
    "Which retailer ships from Leeds?": '{"answer": "Kirkwall depot", "source": "doc"}',
    "Who founded Northgate?": '{"answer": {"type": "unknown", "reason": "no founder named"}}',
    "When did Kirkwall open?": '{"answer": {"type": "unknown", "reason": "no date"}}',
}


class ScriptedClient:
    """Answers from a mapping of question to payload, so a rollout is deterministic."""

    def identity(self):
        return FakeModelClient().model_identity

    def complete(self, request):
        asked = request.messages[-1]["content"]
        for question, payload in ANSWERS.items():
            if question in asked:
                return fake_response(content=payload)
        raise AssertionError(f"nothing scripted for {asked!r}")


def three_examples() -> ExampleSet:
    """One asserted and right-ish, one that abstains where a value exists, one absent label."""
    return ExampleSet(
        [
            Example(
                id="q1",
                inputs={"question": "Which retailer ships from Leeds?"},
                expected="Kirkwall",
                split="held_out",
                expected_by_node={"extract": "Kirkwall"},
            ),
            Example(
                id="q2",
                inputs={"question": "Who founded Northgate?"},
                expected="Alan Blair",
                split="held_out",
                expected_by_node={"extract": "Alan Blair"},
            ),
            Example(
                id="q3",
                inputs={"question": "When did Kirkwall open?"},
                expected=Unknown(reason="the collection gives no date"),
                split="held_out",
                expected_by_node={"extract": Unknown(reason="no date")},
            ),
        ]
    )


def token_overlap(predicted, expected) -> float:
    """Fraction of the label's words that appear in the answer. 'Kirkwall depot' scores 1.0."""
    words = str(expected).lower().split()
    seen = set(str(predicted).lower().split())
    return sum(1.0 for word in words if word in seen) / len(words)


def overlap_metric(**kwargs) -> ProjectMetric:
    return ProjectMetric(
        name="overlap",
        definition="the label's words that appear in the answer",
        score=lambda s: token_overlap(s.answer, s.expected),
        **kwargs,
    )


def run(tmp_path: Path, **kwargs) -> EvalResults:
    suite = EvalSuite(
        Pipeline([LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET),
        three_examples(),
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


# -- what is reported ------------------------------------------------------------------------


def test_a_project_metric_is_reported_beside_the_six(tmp_path: Path) -> None:
    results = run(tmp_path, metrics=[overlap_metric()])

    assert set(results.metrics) == {*METRIC_DEFINITIONS, "overlap"}
    assert results.metrics["overlap"].interval is not None
    assert results.metrics["overlap"].definition == "the label's words that appear in the answer"


def test_its_interval_resamples_examples_like_every_other(tmp_path: Path) -> None:
    results = run(tmp_path, metrics=[overlap_metric()])
    interval = results.metrics["overlap"].interval

    # q1 and q2 have a value to find; q3's label is absence and is outside the denominator.
    assert (interval.n, interval.k) == (2, 2)
    assert interval.method == results.metrics["accuracy"].interval.method


# -- what `over` decides ---------------------------------------------------------------------


def test_by_default_a_rollout_that_reported_absence_scores_zero(tmp_path: Path) -> None:
    """q1 asserted and scores 1.0; q2 abstained where a value existed and scores 0.0."""
    results = run(tmp_path, metrics=[overlap_metric()])

    scores = {r.example_id: r.scores["overlap"] for r in results.rollouts if r.scores}

    assert scores == {"q1": 1.0, "q2": 0.0}
    assert results.metrics["overlap"].value == pytest.approx(0.5)


def test_the_score_function_is_never_handed_an_absence_by_default(tmp_path: Path) -> None:
    seen: list[tuple] = []
    metric = ProjectMetric(
        name="overlap",
        definition="what it was handed",
        score=lambda s: seen.append((s.answer, s.expected)) or 1.0,
    )

    run(tmp_path, metrics=[metric])

    assert seen, "the score function was never called at all"
    assert not any(isinstance(value, Unknown) for pair in seen for value in pair)


def test_over_asserted_leaves_out_the_rollouts_that_put_no_value_forward(tmp_path: Path) -> None:
    results = run(tmp_path, metrics=[overlap_metric(over=Over.ASSERTED)])

    carried = {r.example_id for r in results.rollouts if "overlap" in r.scores}

    assert carried == {"q1"}
    assert results.metrics["overlap"].value == 1.0
    assert results.metrics["overlap"].interval.n == 1


def test_over_all_reaches_every_rollout_including_the_absent_label(tmp_path: Path) -> None:
    seen: list[tuple] = []
    metric = ProjectMetric(
        name="anything",
        definition="what it was handed",
        score=lambda s: seen.append((s.answer, s.expected)) or 1.0,
        over=Over.ALL,
    )

    results = run(tmp_path, metrics=[metric])

    assert len(seen) == 6
    assert any(isinstance(predicted, Unknown) for predicted, _ in seen)
    assert any(isinstance(expected, Unknown) for _, expected in seen)
    assert results.metrics["anything"].interval.n == 3


def test_an_absence_labelled_example_is_outside_the_two_narrower_denominators(
    tmp_path: Path,
) -> None:
    for over in (Over.VALUE_EXISTS, Over.ASSERTED):
        results = run(tmp_path / over.value, metrics=[overlap_metric(over=over)])

        assert not any(r.scores for r in results.rollouts if r.example_id == "q3"), (
            f"q3's label is absence and {over} scored it anyway"
        )


def test_the_denominator_sentence_comes_from_over() -> None:
    assert overlap_metric().population == "rollouts of examples where a value exists"
    assert overlap_metric(over=Over.ALL).population == "all rollouts"


# -- what is refused -------------------------------------------------------------------------


def test_a_name_one_of_the_six_already_has_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        ProjectMetric(name="recall", definition="mine", score=lambda s: 1.0)

    assert "recall" in str(raised.value)
    assert "false_confidence_rate" in str(raised.value)


def test_two_metrics_of_one_name_in_one_place_are_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        EvalSuite(
            Pipeline(
                [LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET
            ),
            three_examples(),
            answer="answer",
            matches=EXACT,
            metrics=[overlap_metric(), overlap_metric()],
        )

    assert "overlap" in str(raised.value)


def test_the_same_metric_end_to_end_and_on_a_node_is_not_a_repeat(tmp_path: Path) -> None:
    results = run(
        tmp_path, metrics=[overlap_metric()], node_metrics={"extract": [overlap_metric()]}
    )

    assert results.metrics["overlap"].interval is not None
    assert results.nodes["extract"].metrics["overlap"].interval is not None


def test_node_metrics_naming_a_node_the_pipeline_does_not_hold_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        EvalSuite(
            Pipeline(
                [LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET
            ),
            three_examples(),
            answer="answer",
            matches=EXACT,
            node_metrics={"hunt": [overlap_metric()]},
        )

    assert "node_metrics" in str(raised.value)
    assert "'extract'" in str(raised.value)


def test_a_score_returning_a_boolean_is_refused_and_names_matches(tmp_path: Path) -> None:
    metric = ProjectMetric(name="right", definition="mine", score=lambda s: True)

    with pytest.raises(ConfigurationError) as raised:
        run(tmp_path, metrics=[metric])

    assert "matches=" in str(raised.value)


def test_a_score_that_raises_names_the_metric_and_the_rollout(tmp_path: Path) -> None:
    def explode(s):
        raise ValueError("no")

    with pytest.raises(ConfigurationError) as raised:
        run(tmp_path, metrics=[ProjectMetric(name="boom", definition="mine", score=explode)])

    message = str(raised.value)
    assert "'boom'" in message and "ValueError" in message
    assert "Over.ASSERTED" in message


def test_an_empty_denominator_reports_a_reason_rather_than_zero() -> None:
    rollouts = [
        RolloutOutcome(example_id="q1", rollout=0, seed=1, outcome=Outcome.CORRECT_ABSTENTION)
    ]

    metrics = aggregate(rollouts, {"q1": True}, project=[overlap_metric()], resamples=200, seed=41)

    assert metrics["overlap"].value is None
    assert "no denominator" in metrics["overlap"].reason


# -- units -------------------------------------------------------------------------------------


def test_a_rate_prints_as_a_percentage_and_anything_else_prints_its_unit(tmp_path: Path) -> None:
    results = run(
        tmp_path,
        metrics=[
            overlap_metric(),
            ProjectMetric(
                name="spend",
                definition="what one rollout cost",
                score=lambda s: 0.000153,
                over=Over.ALL,
                unit="USD",
            ),
        ],
    )

    report = results.report()

    assert "overlap" in report and "50.0%" in report
    assert "0.000153 USD" in report
    assert "0.0153%" not in report


def test_the_six_are_rates_and_say_so(tmp_path: Path) -> None:
    results = run(tmp_path)

    assert {m.unit for m in results.metrics.values()} == {RATE}


# -- the results file --------------------------------------------------------------------------


def test_the_score_is_written_on_the_rollout_that_produced_it(tmp_path: Path) -> None:
    results = run(tmp_path, metrics=[overlap_metric()])
    path = results.write(tmp_path / "results.json")

    raw = json.loads(path.read_text())
    scored = {r["example_id"]: r["scores"] for r in raw["rollouts"]}

    assert scored["q1"] == {"overlap": 1.0}
    assert scored["q3"] == {}


def test_the_declaration_and_its_version_are_in_the_config(tmp_path: Path) -> None:
    results = run(
        tmp_path, metrics=[overlap_metric()], node_metrics={"extract": [overlap_metric()]}
    )

    declared = results.config["metrics"][0]

    assert declared["name"] == "overlap"
    assert declared["over"] == "value_exists"
    assert declared["version"].startswith("sha256:")
    assert results.config["node_metrics"]["extract"][0]["name"] == "overlap"


def test_it_round_trips_through_the_file(tmp_path: Path) -> None:
    results = run(
        tmp_path, metrics=[overlap_metric()], node_metrics={"extract": [overlap_metric()]}
    )
    path = results.write(tmp_path / "results.json")

    back = EvalResults.read(path)

    assert back.metrics["overlap"].value == results.metrics["overlap"].value
    assert back.metrics["overlap"].unit == RATE
    assert back.nodes["extract"].metrics["overlap"].value is not None
    assert back.rollouts[0].scores == results.rollouts[0].scores


def test_ft_06_reads_a_project_metric_like_any_other(tmp_path: Path) -> None:
    from simple_agents.conformance.checks import _reported_metrics

    results = run(
        tmp_path, metrics=[overlap_metric()], node_metrics={"extract": [overlap_metric()]}
    )
    raw = json.loads(results.write(tmp_path / "results.json").read_text())

    named = [name for name, _ in _reported_metrics(raw)]

    assert "overlap" in named
    assert "extract.overlap" in named


# -- per node ------------------------------------------------------------------------------------


def test_a_node_reports_the_metrics_declared_for_it(tmp_path: Path) -> None:
    results = run(tmp_path, node_metrics={"extract": [overlap_metric()]})

    metric = results.nodes["extract"].metrics["overlap"]

    assert metric.interval is not None
    assert "reached this node" in metric.population


def test_a_node_output_holding_an_absence_scores_zero_rather_than_being_handed_over(
    tmp_path: Path,
) -> None:
    """q2's node output is `{"answer": {"type": "unknown", ...}}`, not the whole tagged object."""
    seen: list = []
    metric = ProjectMetric(
        name="overlap",
        definition="what it was handed",
        score=lambda s: seen.append(s.answer) or 1.0,
    )

    results = run(tmp_path, node_metrics={"extract": [metric]})

    scored = {r.example_id: r.nodes["extract"].scores.get("overlap") for r in results.rollouts}
    assert scored["q1"] == 1.0
    assert scored["q2"] == 0.0
    assert scored["q3"] is None
    assert all(not isinstance(value, Unknown) for value in seen)


def test_a_node_metric_is_given_the_recorded_output_rather_than_the_answer(
    tmp_path: Path,
) -> None:
    seen: list = []
    metric = ProjectMetric(
        name="shape",
        definition="what it was handed",
        score=lambda s: seen.append(s.answer) or 1.0,
    )

    run(tmp_path, node_metrics={"extract": [metric]})

    assert seen and all(isinstance(value, dict) for value in seen)
    assert all("answer" in value for value in seen)


def test_a_node_no_example_labels_reports_no_project_metric(tmp_path: Path) -> None:
    examples = ExampleSet(
        [
            Example(
                id="q1",
                inputs={"question": "Which retailer ships from Leeds?"},
                expected="Kirkwall",
                split="held_out",
            )
        ]
    )
    suite = EvalSuite(
        Pipeline([LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET),
        examples,
        answer="answer",
        matches=EXACT,
        node_metrics={"extract": [overlap_metric()]},
    )

    results = suite.run(
        envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
        model=ScriptedClient(),
        split="held_out",
        k=2,
        seed=41,
        concurrency=1,
    )

    assert results.nodes["extract"].metrics["overlap"].interval is None
    assert results.nodes["extract"].metrics["overlap"].reason


# -- comparing two evaluations ---------------------------------------------------------------


def compared(tmp_path: Path, **kwargs):
    before = run(tmp_path / "before", **kwargs)
    after = run(tmp_path / "after", **kwargs)
    return before, after


def test_a_comparison_pairs_on_a_project_metric(tmp_path: Path) -> None:
    before, after = compared(tmp_path, metrics=[overlap_metric()])

    comparison = compare(before, after, resamples=200)

    assert "overlap" in comparison.metrics
    assert comparison.metrics["overlap"].delta == 0.0
    assert comparison.metrics["overlap"].definition == overlap_metric().definition


def test_it_pairs_on_the_recorded_scores_rather_than_on_the_labels(tmp_path: Path) -> None:
    """The label is not in the results file, so a recomputation could not happen here."""
    before, after = compared(tmp_path, metrics=[overlap_metric()])
    path = after.write(tmp_path / "after.json")

    comparison = compare(before, EvalResults.read(path), resamples=200)

    assert comparison.metrics["overlap"].delta == 0.0
    assert "expected" not in json.dumps(json.loads(path.read_text())["examples"])


def test_a_metric_only_one_side_reports_is_left_out(tmp_path: Path) -> None:
    """Both directions. The walk is over the earlier file, so only one of them reaches the
    clause that asks whether the later one carries it too."""
    without = run(tmp_path / "without")
    with_it = run(tmp_path / "with", metrics=[overlap_metric()])

    added = compare(without, with_it, resamples=200)
    dropped = compare(with_it, without, resamples=200)

    assert set(added.metrics) == set(METRIC_DEFINITIONS)
    assert set(dropped.metrics) == set(METRIC_DEFINITIONS)


def test_a_node_project_metric_is_compared_too(tmp_path: Path) -> None:
    before, after = compared(tmp_path, node_metrics={"extract": [overlap_metric()]})

    comparison = compare(before, after, resamples=200)

    assert comparison.nodes["extract"].metrics["overlap"].delta == 0.0


# -- a scoring rule that moved ----------------------------------------------------------------


def test_a_changed_project_metric_withholds_the_verdict(tmp_path: Path) -> None:
    before = run(tmp_path / "before", metrics=[overlap_metric()])
    after = run(
        tmp_path / "after",
        metrics=[
            ProjectMetric(
                name="overlap",
                definition="the label's words that appear in the answer",
                score=lambda s: token_overlap(s.answer, s.expected) / 2,
            )
        ],
    )

    change = compare(before, after, resamples=200).metrics["overlap"]

    assert change.moved is None
    assert change.rule_moved == [
        before.config["metrics"][0]["version"],
        after.config["metrics"][0]["version"],
    ]
    assert "scored" in change.verdict_reason
    assert change.delta == pytest.approx(-0.25)


def test_a_changed_matches_withholds_the_verdict_on_all_eight(tmp_path: Path) -> None:
    before = enough_examples(tmp_path / "before", lambda s: True)
    after = enough_examples(tmp_path / "after", lambda s: False)

    comparison = compare(before, after, resamples=200)

    assert comparison.moved == []
    assert set(comparison.undecided) == set(METRIC_DEFINITIONS)
    assert comparison.metrics["accuracy"].delta == pytest.approx(-1.0)
    assert comparison.metrics["accuracy"].rule_moved is not None


def test_an_unchanged_matches_still_carries_its_verdict(tmp_path: Path) -> None:
    """The guard fires on a changed rule, not on every comparison."""
    always = lambda s: True
    before = enough_examples(tmp_path / "before", always)
    after = enough_examples(tmp_path / "after", always)

    comparison = compare(before, after, resamples=200)

    assert comparison.metrics["accuracy"].rule_moved is None
    assert comparison.metrics["accuracy"].moved is False


def enough_examples(tmp_path: Path, matches) -> EvalResults:
    """21 examples, so the 20-example verdict floor is not what withholds the verdict."""
    examples = ExampleSet(
        [
            Example(
                id=f"q{i}",
                inputs={"question": "Which retailer ships from Leeds?"},
                expected="Kirkwall",
                split="held_out",
            )
            for i in range(21)
        ]
    )
    suite = EvalSuite(
        Pipeline([LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET),
        examples,
        answer="answer",
        matches=matches,
    )
    return suite.run(
        envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
        model=ScriptedClient(),
        split="held_out",
        k=1,
        seed=41,
        concurrency=1,
    )


# -- the interval a project metric is handed ----------------------------------------------------


def test_bootstrap_ci_refuses_a_flat_list_and_says_how_to_group_it() -> None:
    with pytest.raises(ConfigurationError) as raised:
        bootstrap_ci([0.71, 0.33, 0.90], seed=41)

    message = str(raised.value)
    assert "flat sequence" in message
    assert "[[0.5], [0.3]]" in message


def test_bootstrap_ci_takes_one_score_per_example() -> None:
    interval = bootstrap_ci([[0.71], [0.33], [0.90]], resamples=200, seed=41)

    assert interval.n == 3
    assert interval.point == pytest.approx((0.71 + 0.33 + 0.90) / 3)


def test_bootstrap_ci_refuses_a_score_that_is_not_a_number() -> None:
    with pytest.raises(ConfigurationError) as raised:
        bootstrap_ci([["high"], ["low"]], seed=41)

    assert "not a number" in str(raised.value)


def test_a_project_metric_takes_the_same_interval_as_a_shipped_rate() -> None:
    """The seam changes what is scored, not how the interval over it is computed."""
    grouped = [[0.6, 0.8], [0.2, 0.4]]
    rollouts = [
        RolloutOutcome(
            example_id=example_id,
            rollout=index,
            seed=index,
            outcome=Outcome.CORRECT,
            scores={"overlap": score},
        )
        for example_id, scores in zip(("q1", "q2"), grouped)
        for index, score in enumerate(scores)
    ]

    metrics = aggregate(
        rollouts, {"q1": False, "q2": False}, project=[overlap_metric()], resamples=200, seed=41
    )

    assert metrics["overlap"].interval.point == pytest.approx(
        bootstrap_ci(grouped, resamples=200, seed=41).point
    )


class TestWhichRolloutsTheScoreFunctionSees:
    """`score_of` and `scores_this_rollout` read one rule, so they cannot drift apart.

    The second exists so a floor built entirely out of rollouts the function never saw can say
    so. If it answered differently from the branch `score_of` actually takes, the report would
    name the wrong figures.
    """

    @staticmethod
    def _scoring(answer: object, expected: object) -> Scoring:
        return Scoring(
            answer=answer,
            expected=expected,
            example=Example(id="q1", inputs={}, expected=expected, split="held_out"),
            rollout=0,
            seed=0,
        )

    @pytest.mark.parametrize("over", list(Over))
    @pytest.mark.parametrize("expected", ["a", Unknown(reason="absent")])
    @pytest.mark.parametrize("asserted", [True, False])
    def test_the_predicate_agrees_with_the_branch_the_scorer_takes(
        self, over: Over, expected: object, asserted: bool
    ) -> None:
        seen: list[Scoring] = []
        metric = ProjectMetric(
            name="probe",
            definition="records whether it was called",
            score=lambda s: seen.append(s) or 1.0,
            over=over,
        )
        scoring = self._scoring("a" if asserted else Unknown(reason="none"), expected)
        score_of(metric, scoring, asserted=asserted)
        assert bool(seen) == scores_this_rollout(metric, scoring, asserted=asserted)

    @pytest.mark.parametrize("over", list(Over))
    @pytest.mark.parametrize("expected", ["a", Unknown(reason="absent")])
    @pytest.mark.parametrize("asserted", [True, False])
    def test_a_ratio_takes_the_same_branch(
        self, over: Over, expected: object, asserted: bool
    ) -> None:
        seen: list[Scoring] = []
        ratio = ProjectRatio(
            name="probe",
            definition="records whether it was called",
            numerator=lambda s: seen.append(s) or 1.0,
            denominator=lambda s: 1.0,
            over=over,
        )
        scoring = self._scoring("a" if asserted else Unknown(reason="none"), expected)
        ratio_of(ratio, scoring, asserted=asserted)
        assert bool(seen) == scores_this_rollout(ratio, scoring, asserted=asserted)
