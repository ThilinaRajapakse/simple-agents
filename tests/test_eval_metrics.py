"""Outcome classification, the eight rates, and per-node metrics.

Every fixture here is handcrafted so the right answer is known before the code runs. The rates
in particular can only be checked that way: over real rollouts the assertion would be that the
arithmetic agrees with itself.
"""

from __future__ import annotations

from typing import Any

import pytest

from simple_agents import ComputeBasis, Cost, PriceBasis, Unknown, decode_answer
from simple_agents.evaluation.metrics import METRIC_DEFINITIONS, aggregate
from simple_agents.evaluation.results import totals_of
from simple_agents.evaluation.outcomes import (
    NodeObservation,
    Outcome,
    RolloutOutcome,
    classify,
)
from simple_agents.evaluation.examples import Example
from simple_agents.evaluation.scoring import Scoring
from simple_agents.evaluation.per_node import (
    NodeMetrics,
    holds_absence,
    node_rates,
    per_node,
)

EXACT = lambda s: s.answer == s.expected


def rollout(
    example_id: str, outcome: Outcome, index: int = 0, left_out: tuple[str, ...] = ()
) -> RolloutOutcome:
    return RolloutOutcome(
        example_id=example_id,
        rollout=index,
        seed=100 + index,
        outcome=outcome,
        left_out=left_out,
    )


class TestSpendThatBoughtNothingAtTheOtherLevels:
    """The rest of `P3-22` §1's class: a call, a subtask and a tool.

    Each reports and none gates. An execution that produced nothing is the level that gates,
    and it is covered above.
    """

    def test_a_call_with_no_content_and_no_tool_call_is_counted(self) -> None:
        records = [
            model_call("m1", "n1", outputs={"content": "an answer", "tool_calls": []}),
            model_call("m2", "n1", outputs={"content": "", "tool_calls": []}),
            model_call("m3", "n1", outputs={"content": None, "tool_calls": []}),
            node("n1", "hunt", "agent"),
        ]

        found = per_node([records])

        assert found["hunt"].model_calls == 3
        assert found["hunt"].empty_responses == 2

    def test_a_chain_of_thought_with_no_answer_is_one_of_them(self) -> None:
        """The reasoning-model failure: the whole ceiling spent before it wrote anything."""
        records = [
            model_call(
                "m1",
                "n1",
                outputs={
                    "content": "",
                    "tool_calls": [],
                    "reasoning": {"text": "thinking at length"},
                },
                finish_reason="length",
            ),
            node("n1", "hunt", "agent"),
        ]

        assert per_node([records])["hunt"].empty_responses == 1

    def test_a_call_that_asked_for_a_tool_is_not(self) -> None:
        records = [
            model_call("m1", "n1", outputs={"content": "", "tool_calls": [{"name": "look"}]}),
            node("n1", "hunt", "agent"),
        ]

        assert per_node([records])["hunt"].empty_responses == 0

    def test_a_dropped_payload_is_not_counted_as_empty(self) -> None:
        records = [
            model_call("m1", "n1", outputs={"type": "not_recorded", "reason": "sampling"}),
            node("n1", "hunt", "agent"),
        ]

        assert per_node([records])["hunt"].empty_responses == 0

    def test_an_embedding_is_not_an_empty_response(self) -> None:
        """It records what came back in its own shape and has no content to be missing."""
        records = [
            model_call(
                "m1",
                "n1",
                params={"call_kind": "embedding"},
                outputs={"dimensions": 16, "vectors": 2},
            ),
            model_call(
                "m2",
                "n1",
                params={"call_kind": "rerank"},
                outputs={"order": [1, 0], "scores": [0.9, 0.1]},
            ),
            node("n1", "look", "deterministic"),
        ]

        found = per_node([records])

        assert found["look"].model_calls == 2
        assert found["look"].empty_responses == 0

    def test_a_subtask_that_ran_the_delegate_out_of_budget_is_counted(self) -> None:
        records = [
            delegation("d1", "n1", termination="completed"),
            delegation("d2", "n1", termination="budget"),
            delegation("d3", "n1", termination="rejected"),
            node("n1", "orchestrate", "agent"),
        ]

        found = per_node([records])

        assert found["orchestrate"].delegations == 3
        assert found["orchestrate"].delegations_out_of_budget == 1

    def test_a_subtask_that_stopped_and_resumed_is_one_subtask(self) -> None:
        """`docs/trajectory-format.md` §4.4: count the records where `resumed_from` is null.

        A consultation already followed that rule and a delegation did not, so a resumed run
        reported twice the subtasks it sent. Found at `P3-22`'s reverification pass.
        """
        records = [
            delegation("d1", "n1", termination="suspended"),
            delegation("d2", "n1", termination="budget", resumed_from="d1"),
            node("n1", "orchestrate", "agent"),
        ]

        found = per_node([records])

        assert found["orchestrate"].delegations == 1
        # `budget` only ever lands on the record that ended the subtask, so it counts once.
        assert found["orchestrate"].delegations_out_of_budget == 1

    def test_a_tool_that_never_answered_is_named_with_its_call_count(self) -> None:
        records = [
            tool_call("t1", "n1", tool_name="search", error={"message": "no"}),
            tool_call("t2", "n1", tool_name="search", error={"message": "no"}),
            tool_call("t3", "n1", tool_name="fetch"),
            node("n1", "hunt", "agent"),
        ]

        assert per_node([records])["hunt"].tools_that_never_succeeded == {"search": 2}

    def test_a_tool_that_failed_and_then_worked_is_not_named(self) -> None:
        records = [
            tool_call("t1", "n1", tool_name="search", error={"message": "no"}),
            tool_call("t2", "n1", tool_name="search"),
            node("n1", "hunt", "agent"),
        ]

        assert per_node([records])["hunt"].tools_that_never_succeeded == {}

    def test_two_nodes_calling_one_tool_are_counted_apart(self) -> None:
        records = [
            tool_call("t1", "n1", tool_name="search", error={"message": "no"}),
            node("n1", "hunt", "agent"),
            tool_call("t2", "n2", tool_name="search"),
            node("n2", "verify", "agent"),
        ]

        found = per_node([records])

        assert found["hunt"].tools_that_never_succeeded == {"search": 1}
        assert found["verify"].tools_that_never_succeeded == {}

    def test_the_three_survive_a_results_file(self) -> None:
        records = [
            model_call("m1", "n1", outputs={"content": "", "tool_calls": []}),
            tool_call("t1", "n1", tool_name="search", error={"message": "no"}),
            delegation("d1", "n1", termination="budget"),
            node("n1", "hunt", "agent"),
        ]

        found = per_node([records])["hunt"]
        read = NodeMetrics.from_record(found.to_record())

        assert read.empty_responses == 1
        assert read.delegations_out_of_budget == 1
        assert read.tools_that_never_succeeded == {"search": 1}


class TestBothFiguresAreReported:
    """A denominator that shrank is reported beside the figure it shrank for.

    `P3-22` stage 2. A rollout is inside a rate when what it returned is attributable to the
    agent, so a question that went unanswered takes it out. Reporting only the narrower figure
    would let a systematically silent answerer read as a better agent, so the same figure with
    those rollouts counted is printed under it.
    """

    def _four(self, left_out: tuple[str, ...]) -> list[RolloutOutcome]:
        return [
            rollout("q1", Outcome.CORRECT),
            rollout("q2", Outcome.CORRECT),
            rollout("q3", Outcome.CORRECT),
            rollout("q4", Outcome.MISSED, left_out=left_out),
        ]

    def test_the_headline_is_over_the_rollouts_that_measured_the_agent(self) -> None:
        found = aggregate(
            self._four(("unanswered_consultation",)), {f"q{i}": False for i in range(1, 5)}
        )

        assert found["accuracy"].interval.n == 3
        assert found["accuracy"].value == 1.0
        assert found["accuracy"].left_out == {"unanswered_consultation": 1}

    def test_the_same_figure_with_them_counted_is_beside_it(self) -> None:
        found = aggregate(
            self._four(("unanswered_consultation",)), {f"q{i}": False for i in range(1, 5)}
        )

        wider = found["accuracy"].including_left_out
        assert wider is not None
        assert wider.n == 4
        assert wider.point == 0.75

    def test_a_figure_whose_whole_denominator_was_left_out_still_reports_the_wider_one(
        self,
    ) -> None:
        """Undefined is where the wider figure is the only number there is."""
        rollouts = [
            rollout("q1", Outcome.CORRECT, left_out=("unanswered_consultation",)),
            rollout("q2", Outcome.MISSED, left_out=("unanswered_consultation",)),
        ]

        found = aggregate(rollouts, {"q1": False, "q2": False})

        assert found["accuracy"].interval is None
        assert "whose question went unanswered" in found["accuracy"].reason
        assert found["accuracy"].including_left_out.n == 2
        assert found["accuracy"].including_left_out.point == 0.5

    def test_a_rollout_the_backend_never_answered_has_no_second_figure(self) -> None:
        """There is no answer to count either way, which is what `no_response` means."""
        found = aggregate(
            [
                rollout("q1", Outcome.CORRECT),
                rollout("q2", Outcome.CORRECT),
                rollout("q3", Outcome.NO_RESPONSE),
            ],
            {"q1": False, "q2": False, "q3": False},
        )

        assert found["accuracy"].interval.n == 2
        assert found["accuracy"].left_out == {"no_response": 1}
        assert found["accuracy"].including_left_out is None

    def test_the_report_prints_both_lines(self) -> None:
        from simple_agents.evaluation.results import EvalResults

        rollouts = self._four(("unanswered_consultation",))
        absence = {f"q{i}": False for i in range(1, 5)}
        results = EvalResults(
            eval_id="eval_1",
            created_at="2026-08-19T00:00:00.000Z",
            config={"split": "held_out", "seed": 41, "k": 1},
            metrics=aggregate(rollouts, absence, seed=41),
            nodes={},
            rollouts=tuple(rollouts),
        )

        printed = results.report()

        assert "n=3 over all rollouts, less 1 whose question went unanswered" in printed
        assert "n=4, with the 1 left out above counted as scored" in printed

    def test_nothing_left_out_means_nothing_to_report_beside_it(self) -> None:
        found = aggregate(self._four(()), {f"q{i}": False for i in range(1, 5)})

        assert found["accuracy"].interval.n == 4
        assert found["accuracy"].left_out == {}
        assert found["accuracy"].including_left_out is None


def scoring(answer: Any, expected: Any, **rest: Any) -> Scoring:
    """One rollout's scoring context, for the classification tests below."""
    return Scoring(
        answer=answer,
        expected=expected,
        example=Example(id="q1", inputs={"question": "?"}, expected=expected, split="dev"),
        rollout=0,
        seed=41,
        **rest,
    )


# -- classification -----------------------------------------------------------------------


def test_a_matching_asserted_answer_is_correct() -> None:
    outcome, verdict = classify(scoring("Kirkwall", "Kirkwall"), matches=EXACT)

    assert outcome is Outcome.CORRECT
    assert verdict.grade == 1.0
    assert (verdict.met, verdict.total) == (1, 1)


def test_a_wrong_asserted_answer_is_false_confidence() -> None:
    outcome, verdict = classify(scoring("Northgate", "Kirkwall"), matches=EXACT)

    assert outcome is Outcome.FALSE_CONFIDENCE
    assert verdict.grade == 0.0


def test_asserting_anything_where_the_answer_is_absent_is_false_confidence() -> None:
    """There was nothing to be right about, so no comparison is made at all."""
    called: list[Any] = []

    outcome, verdict = classify(
        scoring("Dongguan", Unknown(reason="the collection names no city")),
        matches=lambda s: called.append((s.answer, s.expected)) or True,
    )

    assert outcome is Outcome.FALSE_CONFIDENCE
    assert called == []
    assert verdict is None


def test_reporting_absence_where_a_value_exists_is_a_miss_not_a_failure() -> None:
    outcome, verdict = classify(scoring(Unknown(reason="not found"), "Kirkwall"), matches=EXACT)

    assert outcome is Outcome.MISSED
    assert outcome.asserted is False
    assert outcome.succeeded is False
    assert verdict is None


def test_reporting_absence_where_the_answer_is_absent_is_correct() -> None:
    outcome, _ = classify(
        scoring(Unknown(reason="not found"), Unknown(reason="no date given")),
        matches=EXACT,
    )

    assert outcome is Outcome.CORRECT_ABSTENTION
    assert outcome.succeeded is True


def test_a_rollout_that_produced_nothing_is_failed_and_is_never_compared() -> None:
    def explode(s: Scoring) -> bool:
        raise AssertionError("a failed rollout has no answer to compare")

    assert classify(scoring(None, "Kirkwall"), matches=explode)[0] is Outcome.FAILED
    assert (
        classify(scoring("Kirkwall", "Kirkwall"), matches=explode, failed=True)[0] is Outcome.FAILED
    )


def test_the_record_writes_absence_as_the_tagged_object() -> None:
    record = RolloutOutcome(
        example_id="q1",
        rollout=0,
        seed=7,
        outcome=Outcome.CORRECT_ABSTENTION,
        answer=Unknown(reason="no date given"),
        run_id="run_1",
    ).to_record()

    assert record["answer"] == {"type": "unknown", "reason": "no date given"}
    assert record["outcome"] == "correct_abstention"
    assert record["run_id"] == "run_1"


# -- the eight rates ------------------------------------------------------------------------


def test_false_confidence_and_recall_are_different_numbers_over_different_denominators() -> None:
    """Four examples, two of which have no answer. One wrong assertion and one miss.

    Accuracy is 2 of 4. False confidence is 1 of 4, over everything. Recall is 1 of 2, over
    only the examples where a value exists. A single accuracy number reports none of that.
    """
    outcomes = [
        rollout("has-value-1", Outcome.CORRECT),
        rollout("has-value-2", Outcome.MISSED),
        rollout("absent-1", Outcome.CORRECT_ABSTENTION),
        rollout("absent-2", Outcome.FALSE_CONFIDENCE),
    ]
    absence = {
        "has-value-1": False,
        "has-value-2": False,
        "absent-1": True,
        "absent-2": True,
    }

    metrics = aggregate(outcomes, absence, resamples=200, seed=41)

    assert metrics["accuracy"].value == pytest.approx(0.5)
    assert metrics["false_confidence_rate"].value == pytest.approx(0.25)
    assert metrics["recall"].value == pytest.approx(0.5)
    assert metrics["recall"].interval.n == 2
    assert metrics["accuracy"].interval.n == 4


def test_precision_when_asserting_is_over_the_rollouts_that_asserted() -> None:
    outcomes = [
        rollout("q1", Outcome.CORRECT),
        rollout("q2", Outcome.CORRECT),
        rollout("q3", Outcome.FALSE_CONFIDENCE),
        rollout("q4", Outcome.MISSED),
        rollout("q5", Outcome.MISSED),
    ]
    absence = dict.fromkeys(["q1", "q2", "q3", "q4", "q5"], False)

    metrics = aggregate(outcomes, absence, resamples=200, seed=41)

    assert metrics["precision_when_asserting"].value == pytest.approx(2 / 3)
    assert metrics["precision_when_asserting"].interval.n == 3
    assert metrics["abstention_rate"].value == pytest.approx(0.4)


def test_a_rate_with_no_denominator_is_undefined_rather_than_zero() -> None:
    """Recall over a split where every answer is absent is not the agent finding nothing."""
    outcomes = [
        rollout("absent-1", Outcome.CORRECT_ABSTENTION),
        rollout("absent-2", Outcome.CORRECT_ABSTENTION),
    ]

    metrics = aggregate(outcomes, {"absent-1": True, "absent-2": True}, resamples=200)

    assert metrics["recall"].value is None
    assert metrics["recall"].interval is None
    assert "no denominator" in metrics["recall"].reason


def test_a_failed_rollout_counts_against_accuracy_and_is_reported_on_its_own() -> None:
    outcomes = [
        rollout("q1", Outcome.CORRECT),
        rollout("q2", Outcome.FAILED),
        rollout("q3", Outcome.CORRECT),
        rollout("q4", Outcome.CORRECT),
    ]
    absence = dict.fromkeys(["q1", "q2", "q3", "q4"], False)

    metrics = aggregate(outcomes, absence, resamples=200, seed=41)

    assert metrics["accuracy"].value == pytest.approx(0.75)
    assert metrics["failure_rate"].value == pytest.approx(0.25)
    assert metrics["precision_when_asserting"].value == pytest.approx(1.0)


def test_rollouts_of_one_example_are_grouped_before_the_interval_is_taken() -> None:
    """Five rollouts of two examples is n=2 for the interval, not n=10."""
    outcomes = [rollout("q1", Outcome.CORRECT, i) for i in range(5)] + [
        rollout("q2", Outcome.MISSED, i) for i in range(5)
    ]

    metrics = aggregate(outcomes, {"q1": False, "q2": False}, resamples=200, seed=41)

    assert metrics["accuracy"].interval.n == 2
    assert metrics["accuracy"].interval.k == 5
    assert metrics["accuracy"].rollouts == 10


def test_every_metric_carries_what_its_population_is() -> None:
    outcomes = [rollout("q1", Outcome.CORRECT), rollout("q2", Outcome.FALSE_CONFIDENCE)]

    metrics = aggregate(outcomes, {"q1": False, "q2": False}, resamples=200)

    assert set(metrics) == set(METRIC_DEFINITIONS)
    for name, metric in metrics.items():
        assert metric.population
        assert metric.to_record()["definition"] == METRIC_DEFINITIONS[name]


# -- per-node metrics ---------------------------------------------------------------------


def node(record_id: str, node_id: str, kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "record_type": "node_execution",
        "record_id": record_id,
        "parent_id": None,
        "node_id": node_id,
        "node_kind": kind,
        "started_at": "2026-07-29T09:00:00.000Z",
        "ended_at": "2026-07-29T09:00:02.000Z",
        "outputs": None,
        "error": None,
        "termination": None,
        **extra,
    }


def model_call(record_id: str, parent_id: str, output: Any = 20, **extra: Any) -> dict[str, Any]:
    return {
        "record_type": "model_call",
        "record_id": record_id,
        "parent_id": parent_id,
        "started_at": "2026-07-29T09:00:00.000Z",
        "ended_at": "2026-07-29T09:00:01.000Z",
        "tokens": {
            "input_uncached": 100,
            "input_cache_read": 0,
            "input_cache_write": 0,
            "cache_ttl": None,
            "output": output,
        },
        "concurrent_requests": None,
        "replayed": False,
        **extra,
    }


def tool_call(record_id: str, parent_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "record_type": "tool_call",
        "record_id": record_id,
        "parent_id": parent_id,
        "started_at": "2026-07-29T09:00:00.000Z",
        "ended_at": "2026-07-29T09:00:01.000Z",
        "tool_name": "document_search",
        "item_index": None,
        "error": None,
        **extra,
    }


def delegation(record_id: str, parent_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "record_type": "delegation",
        "record_id": record_id,
        "parent_id": parent_id,
        "started_at": "2026-07-29T09:00:00.000Z",
        "ended_at": "2026-07-29T09:00:01.000Z",
        "node_id": "orchestrate.research",
        "termination": "completed",
        "resumed_from": None,
        **extra,
    }


class TestWorkThatEndedWithoutProducingAnything:
    """An AgentNode's output comes from a `finish` call, so a budget stop produced nothing.

    Every fixture states its own right answer: the counts below are read off the records
    above them rather than off the code.
    """

    def test_a_budget_stop_is_counted_and_a_finish_is_not(self) -> None:
        records = [
            model_call("m1", "n1"),
            tool_call("t1", "n1"),
            node("n1", "hunt", "agent", termination="finish"),
            model_call("m2", "n2"),
            model_call("m3", "n2"),
            tool_call("t2", "n2"),
            node("n2", "hunt", "agent", termination="max_steps"),
        ]

        found = per_node([records])

        assert found["hunt"].unfinished_executions == 1
        assert found["hunt"].unfinished_model_calls == 2
        # It acted, so what stopped it was the cap rather than a loop that never started.
        assert found["hunt"].unfinished_without_tool_calls == 0

    def test_an_execution_that_never_acted_is_counted_apart(self) -> None:
        records = [
            model_call("m1", "n1"),
            model_call("m2", "n1"),
            model_call("m3", "n1"),
            node("n1", "look_closer", "agent", termination="max_steps"),
        ]

        found = per_node([records])

        assert found["look_closer"].unfinished_executions == 1
        assert found["look_closer"].unfinished_without_tool_calls == 1
        assert found["look_closer"].unfinished_model_calls == 3

    @pytest.mark.parametrize(
        "termination, counted",
        [
            ("max_steps", True),
            ("max_tokens", True),
            ("max_cost", True),
            ("max_wall_clock", True),
            ("finish_rejected", True),
            ("finish", False),
            # Counted by `errors`; never ran; continues in another process; a cycle running
            # out around a node that completed.
            ("error", False),
            ("skipped", False),
            ("suspended", False),
            ("max_iterations", False),
        ],
    )
    def test_which_terminations_produced_no_output(self, termination, counted) -> None:
        records = [
            model_call("m1", "n1"),
            node("n1", "hunt", "agent", termination=termination),
        ]

        found = per_node([records])

        assert found["hunt"].unfinished_executions == (1 if counted else 0)

    def test_a_fan_out_item_is_its_own_unit_of_work(self) -> None:
        """The node completed. Its items are where the work stopped."""
        records = [
            model_call("m1", "n1", item_index=0),
            tool_call("t1", "n1", item_index=0),
            model_call("m2", "n1", item_index=1),
            model_call("m3", "n1", item_index=1),
            node(
                "n1",
                "judge",
                "agent",
                termination=None,
                outputs={
                    "items": [
                        {"index": 0, "value": None, "termination": "max_steps"},
                        {"index": 1, "value": None, "termination": "max_steps"},
                        {"index": 2, "value": {"answer": "yes"}, "termination": "finish"},
                    ]
                },
                format_version="0.26",
            ),
        ]

        found = per_node([records])

        # Nothing at the execution level: a fan-out whose items spun completes normally.
        assert found["judge"].unfinished_executions == 0
        assert found["judge"].terminations == {}
        assert found["judge"].unfinished_items == 2
        assert found["judge"].unfinished_model_calls == 3
        # Item 0 called a tool and item 1 did not.
        assert found["judge"].unfinished_without_tool_calls == 1

    def test_an_older_record_cannot_say_which_item_called_a_tool(self) -> None:
        """`tool_call.item_index` arrived in trajectory format 0.26.

        Reading the item as inert would report a project that acted as one that did not, so
        the figure leaves those items out rather than guessing.
        """
        records = [
            model_call("m1", "n1", item_index=0),
            tool_call("t1", "n1"),
            node(
                "n1",
                "judge",
                "agent",
                outputs={"items": [{"index": 0, "value": None, "termination": "max_steps"}]},
                format_version="0.25",
            ),
        ]

        found = per_node([records])

        assert found["judge"].unfinished_items == 1
        assert found["judge"].unfinished_without_tool_calls == 0

    def test_a_dropped_payload_reports_no_items_rather_than_none_spun(self) -> None:
        records = [
            model_call("m1", "n1", item_index=0),
            node(
                "n1",
                "judge",
                "agent",
                outputs={"type": "not_recorded", "reason": "sampling"},
                format_version="0.26",
            ),
        ]

        found = per_node([records])

        assert found["judge"].unfinished_items == 0

    def test_the_figures_survive_a_results_file(self) -> None:
        records = [
            model_call("m1", "n1"),
            node("n1", "hunt", "agent", termination="max_steps"),
        ]

        found = per_node([records])["hunt"]
        read = NodeMetrics.from_record(found.to_record())

        assert read.unfinished_executions == 1
        assert read.unfinished_without_tool_calls == 1
        assert read.unfinished_model_calls == 1
        assert read.unfinished_items == 0


def test_calls_are_attributed_to_the_node_that_made_them() -> None:
    records = [
        model_call("m1", "n1"),
        tool_call("t1", "n1"),
        node("n1", "hunt", "agent", termination="finish"),
        model_call("m2", "n2"),
        node("n2", "verify", "llm"),
    ]

    found = per_node([records])

    assert found["hunt"].model_calls == 1
    assert found["hunt"].tool_calls == 1
    assert found["hunt"].terminations == {"finish": 1}
    assert found["verify"].model_calls == 1
    assert found["verify"].tool_calls == 0
    assert found["verify"].node_kind == "llm"


def test_a_model_call_made_inside_a_tool_lands_on_the_node_whose_tool_spent_it() -> None:
    """Its parent is the tool call, so the walk takes two steps to reach the node."""
    records = [
        model_call("m1", "t1"),
        tool_call("t1", "n1"),
        node("n1", "hunt", "agent"),
    ]

    found = per_node([records])

    assert found["hunt"].model_calls == 1
    assert found["hunt"].tokens["output"] == 20


def test_metrics_accumulate_across_rollouts() -> None:
    runs = [
        [model_call("m1", "n1"), node("n1", "hunt", "agent", termination="finish")],
        [model_call("m2", "n1"), node("n1", "hunt", "agent", termination="max_steps")],
        [model_call("m3", "n1"), node("n1", "hunt", "agent", termination="finish")],
    ]

    found = per_node(runs)

    assert found["hunt"].executions == 3
    assert found["hunt"].model_calls == 3
    assert found["hunt"].tokens["input_uncached"] == 300
    assert found["hunt"].terminations == {"finish": 2, "max_steps": 1}
    assert found["hunt"].wall_clock_ms == 6000


def test_an_unmeasured_token_class_stays_unmeasured_rather_than_summing_to_zero() -> None:
    unmeasured = {"type": "unknown", "reason": "server reports no prompt_tokens_details"}
    records = [
        model_call("m1", "n1"),
        model_call(
            "m2",
            "n1",
            tokens={
                "input_uncached": 50,
                "input_cache_read": unmeasured,
                "input_cache_write": 0,
                "cache_ttl": None,
                "output": 5,
            },
        ),
        node("n1", "hunt", "agent"),
    ]

    found = per_node([records])

    assert found["hunt"].tokens["input_uncached"] == 150
    assert found["hunt"].tokens["input_cache_read"] == unmeasured


def test_cost_is_derived_per_node_against_the_basis() -> None:
    records = [
        model_call("m1", "n1", backend="hosted_api"),
        node("n1", "hunt", "agent"),
    ]
    basis = PriceBasis(currency="USD", input_uncached_per_mtok=1.0, output_per_mtok=2.0)

    found = per_node([records], cost_basis=basis)

    assert found["hunt"].cost.value == pytest.approx(100 / 1e6 + 20 * 2 / 1e6)
    assert found["hunt"].cost.currency == "USD"


def test_a_compute_basis_with_no_concurrency_reports_an_upper_bound() -> None:
    records = [model_call("m1", "n1", backend="self_hosted"), node("n1", "hunt", "agent")]
    basis = ComputeBasis(currency="USD", device="RTX-3090", device_count=1, hourly_rate=0.22)

    found = per_node([records], cost_basis=basis)

    assert found["hunt"].cost.is_upper_bound is True
    assert found["hunt"].to_record()["cost"]["is_upper_bound"] is True


def test_an_output_reporting_absence_is_counted() -> None:
    records = [
        node("n1", "hunt", "agent", outputs={"answer": {"type": "unknown", "reason": "x"}}),
        node("n2", "verify", "llm", outputs={"answer": "Kirkwall"}),
    ]

    found = per_node([records])

    assert found["hunt"].absent_outputs == 1
    assert found["verify"].absent_outputs == 0


def test_an_absence_is_seen_in_both_shapes_one_output_can_be_in() -> None:
    """The two shapes must agree, and nothing else says so.

    An output is counted straight off the record, and scored after being decoded. If only one
    of those sees an absence, a node that reported "not published" is counted as having
    asserted a value, and the number moves with nothing raising.
    """
    recorded = {
        "source": {"type": "unknown", "reason": "no size chart"},
        "rows": [{"chest_cm": {"type": "unknown", "reason": "not listed"}}],
    }

    assert holds_absence(recorded) is True
    assert holds_absence(decode_answer(recorded)) is True


def test_an_errored_node_is_counted_and_reported_in_the_record() -> None:
    records = [
        node(
            "n1",
            "hunt",
            "agent",
            termination="error",
            error={"class": "caller_facing", "type": "CassetteMiss", "message": "..."},
        )
    ]

    record = per_node([records])["hunt"].to_record()

    assert record["errors"] == 1
    assert record["terminations"] == {"error": 1}
    assert record["executions"] == 1


# -- reach and per-node accuracy ------------------------------------------------------------


def test_a_skipped_node_is_recorded_but_is_not_an_execution() -> None:
    records = [
        node("n1", "hunt", "agent", termination="finish"),
        node("n2", "verify", "llm", termination="skipped"),
    ]

    found = per_node([records])

    assert found["hunt"].executions == 1
    assert found["verify"].executions == 0
    assert found["verify"].terminations == {"skipped": 1}


def test_reach_counts_the_rollouts_a_node_ran_in() -> None:
    ran = [node("n1", "hunt", "agent"), node("n2", "verify", "llm")]
    skipped = [node("n1", "hunt", "agent"), node("n2", "verify", "llm", termination="skipped")]

    found = per_node([ran, skipped, skipped])

    assert found["hunt"].runs == 3
    assert found["hunt"].reached == 3
    assert found["verify"].runs == 3
    assert found["verify"].reached == 1


def test_a_node_in_a_cycle_is_reached_once_and_executes_many_times() -> None:
    records = [
        node("n1", "draft", "llm"),
        node("n2", "critique", "llm"),
        node("n3", "draft", "llm"),
        node("n4", "critique", "llm", termination="max_iterations"),
    ]

    found = per_node([records])

    assert found["draft"].executions == 2
    assert found["draft"].reached == 1
    assert found["critique"].terminations == {"max_iterations": 1}


def observed(example_id: str, index: int, **nodes: Any) -> RolloutOutcome:
    return RolloutOutcome(
        example_id=example_id,
        rollout=index,
        seed=index,
        outcome=Outcome.CORRECT,
        nodes={
            node_id: NodeObservation(reached=reached, matched=matched)
            for node_id, (reached, matched) in nodes.items()
        },
    )


def test_reach_carries_an_interval_over_examples() -> None:
    metrics = {"verify": NodeMetrics(node_id="verify", node_kind="llm")}
    rollouts = [
        observed("q1", 0, verify=(True, None)),
        observed("q1", 1, verify=(True, None)),
        observed("q2", 0, verify=(False, None)),
        observed("q2", 1, verify=(False, None)),
    ]

    node_rates(metrics, rollouts, resamples=200, seed=1)

    reach = metrics["verify"].reach
    assert reach.interval.point == pytest.approx(0.5)
    assert reach.interval.low <= 0.5 <= reach.interval.high
    assert reach.rollouts == 4
    assert reach.examples == 2


def test_a_node_no_example_labels_reports_no_accuracy() -> None:
    metrics = {"verify": NodeMetrics(node_id="verify", node_kind="llm")}

    node_rates(metrics, [observed("q1", 0, verify=(True, None))], resamples=200)

    assert metrics["verify"].accuracy is None


def test_accuracy_is_over_the_rollouts_that_reached_the_node_and_carry_a_label() -> None:
    """A rollout the node never ran on is absent from the denominator, not a zero in it."""
    metrics = {"verify": NodeMetrics(node_id="verify", node_kind="llm")}
    rollouts = [
        observed("q1", 0, verify=(True, True)),
        observed("q1", 1, verify=(True, False)),
        observed("q2", 0, verify=(False, None)),
        observed("q3", 0, verify=(True, True)),
    ]

    node_rates(metrics, rollouts, resamples=200, seed=1)

    accuracy = metrics["verify"].accuracy
    assert accuracy.rollouts == 3
    assert accuracy.examples == 2
    assert accuracy.interval.point == pytest.approx(0.75)


def test_a_node_nothing_reached_reports_a_reason_rather_than_zero() -> None:
    metrics = {"verify": NodeMetrics(node_id="verify", node_kind="llm")}

    node_rates(metrics, [], resamples=200)

    assert metrics["verify"].reach.interval is None
    assert "no denominator" in metrics["verify"].reach.reason


class TestWhatAnEvaluationSpentWhenPartOfItCouldNotBeMeasured:
    """An unmeasured call makes the total unknown, and the rest of the bill is still a fact.

    Dogfood #3's Mistral evaluation ran out of credit at rollout 9. Its results file reported
    `cost.value: null` while its own eight completed rollouts carried $1.5627 between them, so
    the evaluation whose bill most needed reading reported nothing (`dev-docs/runs/dogfood-3/findings.md`
    DF3-D4).
    """

    def _nodes(self, *costs: Cost | None) -> dict[str, NodeMetrics]:
        return {
            f"node_{index}": NodeMetrics(node_id=f"node_{index}", node_kind="llm", cost=cost)
            for index, cost in enumerate(costs)
        }

    def test_the_measured_part_is_reported_beside_the_unknown(self):
        nodes = self._nodes(
            Cost(value=1.5, currency="USD", basis="price"),
            Cost(value=None, currency="USD", basis="price", reason="the call raised"),
            Cost(value=0.0627, currency="USD", basis="price"),
        )

        cost = totals_of(nodes)["cost"]

        assert cost["value"] is None
        assert cost["measured"] == pytest.approx(1.5627)
        assert cost["unpriced_nodes"] == ["node_1"]
        assert cost["reason"] == "the call raised"

    def test_a_fully_measured_evaluation_agrees_with_itself(self):
        nodes = self._nodes(
            Cost(value=1.5, currency="USD", basis="price"),
            Cost(value=0.0627, currency="USD", basis="price"),
        )

        cost = totals_of(nodes)["cost"]

        assert cost["value"] == pytest.approx(1.5627)
        assert cost["measured"] == pytest.approx(1.5627)
        assert cost["unpriced_nodes"] == []

    def test_nothing_measured_is_none_rather_than_zero(self):
        """A total of zero would read as free, which is the failure the unknown exists for."""
        nodes = self._nodes(Cost(value=None, currency="USD", basis="price", reason="no answer"))

        cost = totals_of(nodes)["cost"]

        assert cost["value"] is None
        assert cost["measured"] is None
        assert cost["unpriced_nodes"] == ["node_0"]

    def test_the_keys_are_always_present(self):
        """A reader never has to test for the field before reading it."""
        cost = totals_of(self._nodes())["cost"]

        assert set(cost) == {
            "value",
            "currency",
            "basis",
            "is_upper_bound",
            "reason",
            "measured",
            "priced_calls",
            "unpriced_calls",
            "unpriced_nodes",
        }


class TestHowAConsultationEnded:
    """Counting a question is not the same as knowing whether it was answered.

    Dogfood #3 ran 33 rollouts with `channel=lambda question, options, about=None: None`, so all 152
    consultations resolved `declined`. `per_node.consultations` counted them and the word
    `declined` appeared in no results file, so an evaluation measured against a live end user
    and one measured against silence produced identical numbers (`dev-docs/runs/dogfood-3/findings.md`
    DF3-D7).
    """

    def _trajectory(self, *resolutions: str, answers: str | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = [
            {
                "record_type": "node_execution",
                "record_id": "r1",
                "node_id": "hunt",
                "node_kind": "agent",
                "parent_id": None,
                "termination": "finish",
            }
        ]
        for index, resolution in enumerate(resolutions):
            records.append(
                {
                    "record_type": "consultation",
                    "record_id": f"c{index}",
                    "parent_id": "r1",
                    "resolution": resolution,
                    "answers": answers,
                }
            )
        return records

    def test_the_resolutions_are_counted_beside_the_questions(self):
        nodes = per_node([self._trajectory("declined", "answered", "declined")])

        assert nodes["hunt"].consultations == 3
        assert nodes["hunt"].consultation_resolutions == {"answered": 1, "declined": 2}

    def test_an_evaluation_answering_nothing_is_visible(self):
        """The dogfood #3 shape: every question asked, every one refused."""
        nodes = per_node([self._trajectory(*(["declined"] * 28))])

        assert nodes["hunt"].consultation_resolutions == {"declined": 28}

    def test_the_answering_half_of_a_resumed_question_is_not_a_second_question(self):
        """A question answered in a later process is two records describing one question."""
        records = self._trajectory("pending")
        records.append(
            {
                "record_type": "consultation",
                "record_id": "c_later",
                "parent_id": "r1",
                "resolution": "answered",
                "answers": "c0",
            }
        )

        nodes = per_node([records])

        assert nodes["hunt"].consultations == 1
        assert nodes["hunt"].consultation_resolutions == {"pending": 1, "answered": 1}

    def test_it_survives_a_round_trip_through_a_results_file(self):
        node = per_node([self._trajectory("declined")])["hunt"]

        assert NodeMetrics.from_record(node.to_record()).consultation_resolutions == {"declined": 1}

    def test_a_node_that_never_asked_carries_nothing(self):
        assert per_node([self._trajectory()])["hunt"].consultation_resolutions == {}
