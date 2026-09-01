"""What an agent that did nothing would have scored, computed rather than written down.

Dogfood #4 did the right thing and put its floor where the figure could not be quoted without
it: inside the metric's own definition string. Then the splits were rebalanced and the sentence
was not, so thirty results files named a split of 20/14/2 at 0.56 after it had become 22/6/1 at
0.76, and fifteen of those were runs of the other split entirely. The reported figure was
0.82 [0.68, 0.94], whose interval contains the true floor and clears the stale one by 26 points.

A floor the library computes over the split that ran cannot go stale, and cannot be for the
wrong split.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

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
    against_baseline,
)
from simple_agents.evaluation import (
    EvalResults,
    Example,
    ExampleSet,
    ProjectMetric,
    ProjectRatio,
)
from simple_agents.evaluation.metrics import Over
from simple_agents.evaluation.runner import EvalSuite
from simple_agents.models import fake_response

from schemas import Answer

BUDGET = Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None)

# Thirty examples, twenty-one of them `shelve`. Always answering `shelve` scores 0.7 here, and
# it moves with the mix rather than staying at whatever a comment once said. Thirty rather than
# ten because a verdict on the difference needs `MINIMUM_EXAMPLES_FOR_A_VERDICT`.
LABELS = {f"s{i}": "shelve" for i in range(21)} | {f"k{i}": "skip" for i in range(9)}


def a_set(labels: dict[str, str] = LABELS) -> ExampleSet:
    return ExampleSet(
        [
            Example(id=name, inputs={"question": name}, expected=label, split="held_out")
            for name, label in labels.items()
        ]
    )


class AlwaysShelves:
    """An agent no better than the baseline: it answers the majority class every time."""

    def identity(self) -> Any:
        return FakeModelClient().model_identity

    def complete(self, request: Any) -> Any:
        return fake_response(content='{"answer": "shelve", "source": "doc"}')


class GetsThemRight:
    def identity(self) -> Any:
        return FakeModelClient().model_identity

    def complete(self, request: Any) -> Any:
        asked = request.messages[-1]["content"]
        name = asked.rsplit(": ", 1)[-1].strip()
        return fake_response(content=f'{{"answer": "{LABELS[name]}", "source": "doc"}}')


def evaluate(tmp_path: Path, client: Any, *, baseline: Any, labels: dict[str, str] = LABELS):
    suite = EvalSuite(
        Pipeline(
            [
                LLMNode(
                    lambda i, c: f"Answer: {i['question']}", output_schema=Answer, node_id="extract"
                )
            ],
            budget=BUDGET,
        ),
        a_set(labels),
        answer="answer",
        matches=lambda s: s.answer == s.expected,
        baseline=baseline,
    )
    return suite.run(
        envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
        model=client,
        split="held_out",
        k=1,
        seed=41,
        concurrency=1,
    )


MAJORITY = lambda example: "shelve"


class TestTheFloorIsComputedOverTheSplitThatRan:
    def test_it_scores_the_constant_answer_by_the_suite_s_own_rules(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, GetsThemRight(), baseline=MAJORITY)

        assert results.baseline_metrics()["accuracy"].interval.point == pytest.approx(0.7)

    def test_it_follows_the_mix_rather_than_a_sentence(self, tmp_path: Path) -> None:
        """The failure this exists for: a split is rebalanced and the floor moves with it."""
        rebalanced = {f"s{i}": "shelve" for i in range(27)} | {f"k{i}": "skip" for i in range(3)}
        results = evaluate(tmp_path / "b", GetsThemRight(), baseline=MAJORITY, labels=rebalanced)

        assert results.baseline_metrics()["accuracy"].interval.point == pytest.approx(0.9)

    def test_no_baseline_means_no_figures_rather_than_zero(self, tmp_path: Path) -> None:
        suite = EvalSuite(
            Pipeline(
                [LLMNode(lambda i, c: "x", output_schema=Answer, node_id="extract")], budget=BUDGET
            ),
            a_set(),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
        )
        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
            model=GetsThemRight(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        assert results.baseline == ()
        assert results.baseline_metrics() == {}
        assert against_baseline(results) == {}

    def test_a_ratio_reads_the_same_rule_and_says_why_it_has_no_floor(self, tmp_path: Path) -> None:
        """A ratio of two zero totals is undefined, so there is no floor line to append to.

        The reason is printed where the floor would be. Without it the figure reads the same as
        one whose suite declared no baseline at all.
        """
        ratio = ProjectRatio(
            name="avoided_ratio",
            definition="labels stayed away from, over labels",
            numerator=lambda s: 0.0 if s.answer == s.expected else 1.0,
            denominator=lambda s: 1.0,
            over=Over.VALUE_EXISTS,
        )
        suite = EvalSuite(
            Pipeline(
                [
                    LLMNode(
                        lambda i, c: f"Answer: {i['question']}",
                        output_schema=Answer,
                        node_id="extract",
                    )
                ],
                budget=BUDGET,
            ),
            a_set(),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
            metrics=[ratio],
            baseline=NOTHING,
        )
        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
            model=GetsThemRight(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )
        assert results.baseline_unscored == ("avoided_ratio",)
        assert results.baseline_metrics()["avoided_ratio"].interval is None
        report = results.report()
        assert "the baseline asserted nothing, so avoided_ratio was not called for it." in report
        assert "doing nothing, over 30 example(s)" not in report.split("avoided_ratio")[-1]

    def test_rescore_reaches_the_same_two_answers(self, tmp_path: Path) -> None:
        """Scoring runs already on disk goes through the same preflight and the same floor.

        `rescore` is the path a project takes after fixing a metric, so a baseline fixed at the
        same time has to be refused and reported there as well as on a live run.
        """
        results = evaluate_with(tmp_path, over=Over.VALUE_EXISTS, baseline=NOTHING)
        run_dir = next((tmp_path / "eval").iterdir())

        again = _suite_with(Over.VALUE_EXISTS, NOTHING).rescore(run_dir=run_dir, split="held_out")
        assert again.baseline_unscored == results.baseline_unscored == ("avoided_share",)

        under_all = _suite_with(Over.ALL, NOTHING).rescore(run_dir=run_dir, split="held_out")
        assert under_all.baseline_unscored == ()

        with pytest.raises(ConfigurationError) as raised:
            _suite_with(Over.VALUE_EXISTS, lambda example: None).rescore(
                run_dir=run_dir, split="held_out"
            )
        assert "baseline answered None on example 's0'" in str(raised.value)

    def test_a_part_scored_evaluation_puts_the_floor_over_what_ran(self, tmp_path: Path) -> None:
        """The report says every figure is over what ran, and the floor is one of those.

        Over the whole split instead, a rescore of 4 rollouts of a 30-example split reported a
        floor at n=30 under a figure at n=4: two populations, two interval widths, and
        `against_baseline` pairing examples the agent never answered.
        """
        evaluate_with(tmp_path, over=Over.ALL, baseline=NOTHING)
        run_dir = next((tmp_path / "eval").iterdir())
        kept = 0
        for child in sorted(run_dir.iterdir()):
            if child.is_dir():
                kept += 1
                if kept > 4:
                    shutil.rmtree(child)

        again = _suite_with(Over.ALL, NOTHING).rescore(run_dir=run_dir, split="held_out")
        assert again.config["incomplete"]["examples_scored"] == 4
        assert again.metrics["accuracy"].interval.n == 4
        assert again.baseline_metrics()["accuracy"].interval.n == 4
        assert {r.example_id for r in again.baseline} == {r.example_id for r in again.rollouts}
        assert "doing nothing, over 4 example(s)" in again.report()

    def test_it_survives_the_results_file(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, GetsThemRight(), baseline=MAJORITY)
        path = tmp_path / "results.json"
        results.write(path)

        read = EvalResults.read(path)

        assert len(read.baseline) == 30
        assert read.baseline_metrics()["accuracy"].interval.point == pytest.approx(0.7)

    def test_what_answered_it_is_versioned_beside_matches(self, tmp_path: Path) -> None:
        """An edit to what doing nothing answers moves the floor, so it is recorded."""
        results = evaluate(tmp_path, GetsThemRight(), baseline=MAJORITY)

        assert results.config["baseline"] is not None

    def test_something_that_is_not_a_function_is_refused_by_name(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            EvalSuite(
                Pipeline(
                    [LLMNode(lambda i, c: "x", output_schema=Answer, node_id="e")], budget=BUDGET
                ),
                a_set(),
                answer="answer",
                matches=lambda s: True,
                baseline="shelve",
            )

        assert "baseline='shelve'" in str(raised.value)
        assert "taking an Example" in str(raised.value)


class TestWhetherTheAgentBeatIt:
    def test_an_agent_no_better_than_the_floor_does_not_clear_it(self, tmp_path: Path) -> None:
        """`AlwaysShelves` is the baseline wearing a pipeline, so the difference is zero."""
        results = evaluate(tmp_path, AlwaysShelves(), baseline=MAJORITY)
        change = against_baseline(results)["accuracy"]

        assert results.metrics["accuracy"].interval.point == pytest.approx(0.7)
        assert change.delta == pytest.approx(0.0)
        assert change.moved is False

    def test_an_agent_that_beats_it_says_so(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path, GetsThemRight(), baseline=MAJORITY)
        change = against_baseline(results)["accuracy"]

        assert change.before == pytest.approx(0.7), "the floor"
        assert change.after == pytest.approx(1.0), "the agent"
        assert change.delta == pytest.approx(0.3)

    def test_a_floor_that_never_answers_is_a_floor_too(self, tmp_path: Path) -> None:
        """An agent that abstains everywhere scores nothing on recall and all of abstention."""
        results = evaluate(
            tmp_path, GetsThemRight(), baseline=lambda example: Unknown(reason="did nothing")
        )
        floor = results.baseline_metrics()

        assert floor["accuracy"].interval.point == pytest.approx(0.0)
        assert floor["abstention_rate"].interval.point == pytest.approx(1.0)

    def test_the_report_prints_the_floor_under_the_figure(self, tmp_path: Path) -> None:
        printed = evaluate(tmp_path, AlwaysShelves(), baseline=MAJORITY).report()

        assert "doing nothing, over 30 example(s)" in printed

    def test_the_report_says_where_the_figure_does_not_separate_them(self, tmp_path: Path) -> None:
        """The dogfood's case: 0.82 [0.68, 0.94] against 0.76, quoted as if it cleared it."""
        printed = evaluate(tmp_path, AlwaysShelves(), baseline=MAJORITY).report()

        assert "not separated from it" in printed


class TestABaselineThatAnswersNothing:
    """`None` is what a rollout produces when the pipeline returned nothing.

    Dogfood #5 wrote `baseline=lambda example: None` for an agent that recommends nothing, and
    the floor came out as a failure on every example: `failure_rate` read 100% for an agent that
    cannot fail, and `avoided_share` read 0.0 where the project's own function returns 1.0.
    """

    def test_none_is_refused_and_the_message_names_the_answer_to_give(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            evaluate(tmp_path, GetsThemRight(), baseline=lambda example: None)
        message = str(raised.value)
        assert "baseline answered None on example 's0'" in message
        assert "Unknown(reason='did nothing')" in message

    def test_it_is_refused_before_a_single_rollout_runs(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError):
            evaluate(tmp_path, GetsThemRight(), baseline=lambda example: None)
        assert list(tmp_path.rglob("trajectory.jsonl")) == []

    def test_a_raising_baseline_is_refused_before_a_single_rollout_runs(
        self, tmp_path: Path
    ) -> None:
        def raises(example: Any) -> Any:
            raise KeyError("label")

        with pytest.raises(ConfigurationError) as raised:
            evaluate(tmp_path, GetsThemRight(), baseline=raises)
        assert "baseline raised KeyError on example 's0'" in str(raised.value)
        assert "costs no rollouts" in str(raised.value)
        assert list(tmp_path.rglob("trajectory.jsonl")) == []

    def test_an_absent_answer_is_how_an_agent_that_never_answers_says_so(
        self, tmp_path: Path
    ) -> None:
        results = evaluate(
            tmp_path,
            GetsThemRight(),
            baseline=lambda example: Unknown(reason="did nothing"),
        )
        assert {r.outcome.value for r in results.baseline} == {"missed"}
        assert results.baseline_metrics()["failure_rate"].interval.point == 0.0


def _suite_with(over: Any, baseline: Any) -> EvalSuite:
    """The same suite carrying one project metric, whose `over` is the thing under test."""
    return EvalSuite(
        Pipeline(
            [
                LLMNode(
                    lambda i, c: f"Answer: {i['question']}", output_schema=Answer, node_id="extract"
                )
            ],
            budget=BUDGET,
        ),
        a_set(),
        answer="answer",
        matches=lambda s: s.answer == s.expected,
        metrics=[
            ProjectMetric(
                name="avoided_share",
                definition="the share of the labels the answer stayed away from",
                score=lambda s: 1.0 if s.answer != s.expected else 0.0,
                over=over,
            )
        ],
        baseline=baseline,
    )


def evaluate_with(tmp_path: Path, *, over: Any, baseline: Any):
    return _suite_with(over, baseline).run(
        envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
        model=GetsThemRight(),
        split="held_out",
        k=1,
        seed=41,
        concurrency=1,
    )


NOTHING = lambda example: Unknown(reason="did nothing")


class TestAFloorTheScoreFunctionNeverSaw:
    """A figure about what the agent refrained from, under a baseline that refrains.

    Under `Over.VALUE_EXISTS` a rollout that asserted nothing scores 0.0 and `score` is not
    called, so the floor describes the declaration rather than the answers. Dogfood #5 met this
    and declared `Over.ALL` on one of its two suites and the default on the other.
    """

    def test_the_default_reports_a_floor_its_score_function_never_saw(self, tmp_path: Path) -> None:
        results = evaluate_with(tmp_path, over=Over.VALUE_EXISTS, baseline=NOTHING)
        assert results.baseline_unscored == ("avoided_share",)
        assert results.baseline_metrics()["avoided_share"].interval.point == 0.0

    def test_over_all_hands_the_absence_to_the_project_s_own_function(self, tmp_path: Path) -> None:
        results = evaluate_with(tmp_path, over=Over.ALL, baseline=NOTHING)
        assert results.baseline_unscored == ()
        assert results.baseline_metrics()["avoided_share"].interval.point == 1.0

    def test_a_baseline_that_asserts_is_scored_and_is_not_named(self, tmp_path: Path) -> None:
        results = evaluate_with(tmp_path, over=Over.VALUE_EXISTS, baseline=MAJORITY)
        assert results.baseline_unscored == ()

    def test_the_report_says_so_under_the_floor_and_names_the_declaration(
        self, tmp_path: Path
    ) -> None:
        report = evaluate_with(tmp_path, over=Over.VALUE_EXISTS, baseline=NOTHING).report()
        assert "the baseline asserted nothing, so avoided_share was not called for it." in report
        assert "over=Over.ALL is what scores a figure about refraining." in report

    def test_the_report_is_silent_where_the_function_was_called(self, tmp_path: Path) -> None:
        report = evaluate_with(tmp_path, over=Over.ALL, baseline=NOTHING).report()
        assert "was not called for it" not in report

    def test_it_survives_the_results_file(self, tmp_path: Path) -> None:
        results = evaluate_with(tmp_path, over=Over.VALUE_EXISTS, baseline=NOTHING)
        written = tmp_path / "results.json"
        results.write(written)
        assert EvalResults.read(written).baseline_unscored == ("avoided_share",)

    def test_a_file_written_before_the_key_existed_reads_as_empty(self, tmp_path: Path) -> None:
        results = evaluate_with(tmp_path, over=Over.VALUE_EXISTS, baseline=NOTHING)
        written = tmp_path / "results.json"
        results.write(written)
        raw = json.loads(written.read_text())
        del raw["baseline_unscored"]
        written.write_text(json.dumps(raw))
        assert EvalResults.read(written).baseline_unscored == ()


def _answer_words(scoring: Any) -> float:
    """How many words the answer holds, as one half of a ratio."""
    return float(len(str(scoring.answer).split()))


def _one_answer(scoring: Any) -> float:
    return 1.0


class TestARatioAgainstTheFloor:
    """A ratio compared against the floor is paired on its recorded totals.

    Found by `P3-53`'s first reverification cycle in `compare()` and left here until `P3-52`
    landed, because the two were built in parallel. A ratio is summed rather than averaged, so
    its halves are in `rollouts[].ratios` and pairing it on scores finds none: every one
    reported "No shared example falls under the denominator on both sides" over a floor and an
    agent that both carried it.
    """

    def _evaluate(self, tmp_path: Path):
        from simple_agents.evaluation import ProjectRatio

        suite = EvalSuite(
            Pipeline(
                [
                    LLMNode(
                        lambda i, c: f"Answer: {i['question']}",
                        output_schema=Answer,
                        node_id="extract",
                    )
                ],
                budget=BUDGET,
            ),
            a_set(),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
            metrics=[
                ProjectRatio(
                    name="words",
                    definition="words in the answer, over answers",
                    numerator=_answer_words,
                    denominator=_one_answer,
                    over=Over.ALL,
                )
            ],
            baseline=lambda example: Unknown(reason="did nothing"),
        )
        return suite.run(
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
            model=GetsThemRight(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

    def test_it_is_paired_rather_than_reported_as_unpairable(self, tmp_path: Path) -> None:
        from simple_agents.evaluation.compare import against_baseline

        change = against_baseline(self._evaluate(tmp_path))["words"]

        assert change.examples > 0
        assert change.reason is None

    def test_the_two_sides_are_the_floor_and_the_agent(self, tmp_path: Path) -> None:
        from simple_agents.evaluation.compare import against_baseline

        results = self._evaluate(tmp_path)
        change = against_baseline(results)["words"]

        assert change.after == results.metrics["words"].value
        assert change.before != change.after

    def test_a_mean_against_the_floor_is_unaffected(self, tmp_path: Path) -> None:
        from simple_agents.evaluation.compare import against_baseline

        results = evaluate_with(
            tmp_path, over=Over.ALL, baseline=lambda example: Unknown(reason="did nothing")
        )
        change = against_baseline(results)["avoided_share"]

        assert change.examples > 0
