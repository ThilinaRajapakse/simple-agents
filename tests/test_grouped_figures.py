"""A figure grouped by a property of the example, and what a pooled one hides.

Dogfood #4 reported a null result its own data did not support: a change improved one class of
example and damaged another, the split's 70/30 prevalence cancelled them in the headline, and
nothing reported the two apart. The pooled number is the mean over whatever mix the split
happens to hold, so it moves with the mix as well as with the agent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from simple_agents import (
    Prompt,
    Budget,
    Cassette,
    ConfigurationError,
    FakeModelClient,
    Group,
    LLMNode,
    Pipeline,
    RunEnvelope,
)
from simple_agents.evaluation import EvalResults, Example, ExampleSet, Outcome, compare
from simple_agents.evaluation.examples import METADATA_CEILING
from simple_agents.evaluation.outcomes import RolloutOutcome
from simple_agents.evaluation.runner import EvalSuite
from simple_agents.models import fake_response

from schemas import Answer

BUDGET = Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None)


# -- an evaluation that carries the properties ------------------------------------------------


def build_prompt(inputs: Any, ctx: Any) -> str:
    return Prompt.user("Answer the question: {question}", question=inputs["question"])


class ScriptedClient:
    def identity(self) -> Any:
        return FakeModelClient().model_identity

    def complete(self, request: Any) -> Any:
        return fake_response(content='{"answer": "shelve", "source": "doc"}')


def a_set() -> ExampleSet:
    return ExampleSet(
        [
            Example(
                id="q1",
                inputs={"question": "one"},
                expected="shelve",
                split="held_out",
                source="doc:a",
                metadata={"genre": "fantasy", "pages": 320},
            ),
            Example(
                id="q2",
                inputs={"question": "two"},
                expected="skip",
                split="held_out",
                source="doc:b",
                metadata={"genre": "history", "pages": 700},
            ),
        ]
    )


def evaluate(tmp_path: Path) -> EvalResults:
    suite = EvalSuite(
        Pipeline([LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET),
        a_set(),
        answer="answer",
        matches=lambda s: s.answer == s.expected,
    )
    return suite.run(
        envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
        model=ScriptedClient(),
        split="held_out",
        k=2,
        seed=41,
        concurrency=1,
    )


class TestWhatTheResultsFileCarriesAboutAnExample:
    def test_the_metadata_reaches_the_file(self, tmp_path: Path) -> None:
        """Without this a grouping needs the example set beside the results file."""
        results = evaluate(tmp_path)

        assert results.examples["q1"]["metadata"] == {"genre": "fantasy", "pages": 320}

    def test_a_single_valued_label_reaches_the_file(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path)

        assert results.examples["q1"]["label"] == "shelve"
        assert results.examples["q2"]["label"] == "skip"

    def test_it_survives_a_round_trip(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path)
        path = tmp_path / "results.json"
        results.write(path)

        read = EvalResults.read(path)

        assert read.examples["q1"]["metadata"]["genre"] == "fantasy"
        assert read.grouped("genre")["fantasy"].examples == 1

    def test_every_property_is_groupable(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path)

        assert results.groupable() == ("genre", "label", "pages", "source", "split")

    def test_a_key_nothing_carries_is_refused_by_name(self, tmp_path: Path) -> None:
        results = evaluate(tmp_path)

        with pytest.raises(ConfigurationError) as raised:
            results.grouped("reader")

        assert "'reader'" in str(raised.value)
        assert "genre" in str(raised.value), "the refusal names what is groupable instead"

    def test_a_key_whose_values_cannot_name_a_cell_says_that_rather_than_missing(
        self, tmp_path: Path
    ) -> None:
        """The examples do carry it, so "nothing carries it" would send the reader nowhere."""
        suite = EvalSuite(
            Pipeline(
                [LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET
            ),
            ExampleSet(
                [
                    Example(
                        id=f"q{i}",
                        inputs={"question": str(i)},
                        expected="shelve",
                        split="held_out",
                        metadata={"tags": ["a", "b"]},
                    )
                    for i in range(2)
                ]
            ),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
        )
        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
            model=ScriptedClient(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        with pytest.raises(ConfigurationError) as raised:
            results.grouped("tags")

        assert "2 example(s) carry 'tags'" in str(raised.value)
        assert "the values are list" in str(raised.value)

    def test_the_report_says_how_many_examples_carry_no_value(self, tmp_path: Path) -> None:
        """A grouping that silently drops examples is a denominator that shrank in silence."""
        suite = EvalSuite(
            Pipeline(
                [LLMNode(build_prompt, output_schema=Answer, node_id="extract")], budget=BUDGET
            ),
            ExampleSet(
                [
                    Example(
                        id="q1",
                        inputs={"question": "one"},
                        expected="shelve",
                        split="held_out",
                        metadata={"genre": "fantasy"},
                    ),
                    Example(
                        id="q2", inputs={"question": "two"}, expected="shelve", split="held_out"
                    ),
                ]
            ),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
        )
        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
            model=ScriptedClient(),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        assert "by genre, 1 example(s) carry no genre" in results.report(group_by="genre")

    def test_a_metadata_value_over_the_ceiling_is_named_rather_than_written(self) -> None:
        """A project may hold something large for a scoring rule without copying it per file."""
        example = Example(
            id="q1",
            inputs={},
            expected="shelve",
            split="dev",
            metadata={"genre": "fantasy", "document": "x" * (METADATA_CEILING + 1)},
        )

        entry = example.results_entry()

        assert entry["metadata"] == {"genre": "fantasy"}
        assert entry["metadata_omitted"] == ["document"]
        assert example.metadata["document"], "the example itself is unchanged"

    def test_a_key_with_parts_carries_no_label(self) -> None:
        from simple_agents.evaluation import Criteria, Criterion

        example = Example(
            id="q1",
            inputs={},
            split="dev",
            expected=Criteria([Criterion(id="a", text="a condition")]),
        )

        assert "label" not in example.results_entry()


# -- the case grouping exists for --------------------------------------------------------------


def results_of(scores: dict[str, list[float]], labels: dict[str, str]) -> EvalResults:
    """An evaluation over `labels`, where each example scored `scores[id]` on its rollouts."""
    rollouts = tuple(
        RolloutOutcome(
            example_id=example_id,
            rollout=index,
            seed=index,
            outcome=Outcome.CORRECT if score else Outcome.FALSE_CONFIDENCE,
            answer="x",
        )
        for example_id, per_rollout in scores.items()
        for index, score in enumerate(per_rollout)
    )
    return EvalResults(
        eval_id="eval_test",
        created_at="2026-01-01T00:00:00.000Z",
        config={"split": "held_out", "k": 1, "n": len(labels), "seed": 41},
        metrics={},
        nodes={},
        rollouts=rollouts,
        examples={
            example_id: {
                "split": "held_out",
                "expects_absence": False,
                "absent_parts": [],
                "source": None,
                "metadata": {},
                "label": label,
            }
            for example_id, label in labels.items()
        },
    )


# Seven `shelve` examples and three `skip`, which is dogfood #4's 70/30 prevalence. The change
# turns three `shelve` misses into hits and all three `skip` hits into misses.
LABELS = {f"s{i}": "shelve" for i in range(7)} | {f"k{i}": "skip" for i in range(3)}
BEFORE = {
    **{f"s{i}": [1.0] if i < 4 else [0.0] for i in range(7)},
    **{f"k{i}": [1.0] for i in range(3)},
}
AFTER = {**{f"s{i}": [1.0] for i in range(7)}, **{f"k{i}": [0.0] for i in range(3)}}


class TestAPooledFigureMovesWithTheMix:
    def test_the_headline_does_not_move_at_all(self) -> None:
        """Seven of ten before and seven of ten after, by two changes that cancel."""
        pooled = compare(results_of(BEFORE, LABELS), results_of(AFTER, LABELS))

        assert pooled.metrics["accuracy"].delta == pytest.approx(0.0)

    def test_grouping_separates_the_two_changes(self) -> None:
        grouped = compare(results_of(BEFORE, LABELS), results_of(AFTER, LABELS), group_by="label")

        assert grouped.groups["shelve"].metrics["accuracy"].delta == pytest.approx(3 / 7)
        assert grouped.groups["skip"].metrics["accuracy"].delta == pytest.approx(-1.0)

    def test_a_cell_too_small_for_a_verdict_reports_its_figure_and_withholds_one(self) -> None:
        """Three examples is under `MINIMUM_EXAMPLES_FOR_A_VERDICT`, and the cell says so."""
        grouped = compare(results_of(BEFORE, LABELS), results_of(AFTER, LABELS), group_by="label")
        cell = grouped.groups["skip"].metrics["accuracy"]

        assert cell.delta == pytest.approx(-1.0)
        assert cell.moved is None
        assert "3 example(s) carry this metric" in cell.verdict_reason

    def test_grouping_does_not_nest(self) -> None:
        grouped = compare(results_of(BEFORE, LABELS), results_of(AFTER, LABELS), group_by="label")

        assert grouped.groups["shelve"].groups == {}

    def test_each_cell_reports_its_own_n(self) -> None:
        cells = results_of(AFTER, LABELS).grouped("label")

        assert isinstance(cells["shelve"], Group)
        assert (cells["shelve"].examples, cells["skip"].examples) == (7, 3)
        assert cells["skip"].metrics["accuracy"].interval.n == 3

    def test_the_report_prints_the_cells_under_the_headline(self) -> None:
        printed = results_of(AFTER, LABELS).report(group_by="label")

        assert "by label" in printed
        assert "shelve (7 example(s))" in printed
        assert "skip (3 example(s))" in printed
