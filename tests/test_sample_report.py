"""The sample reports in `docs/evaluation.md` §8.1 are what `report()` actually prints.

Nothing executed those blocks until this file, and a documented example nothing runs goes stale
without anything failing. What is pinned is the per-node table, which is the part that moves
when a column is added: the header, both node rows including their spacing, and the lines
indented under a node. The second block, which shows what a rollout the backend never answered
does to a rate, is pinned line for line.

The reach interval is computed here rather than written down. The block said `[70%,100%]` for
nine months, which is `wilson_ci(9, 9)`; `reach` groups by example, so the figure the code emits
over three examples is `wilson_ci(3, 3)`. A hand-built interval let the document and the test
agree on a number the library never produced (F-01).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from simple_agents import docs_path
from simple_agents.cost import Cost
from simple_agents.evaluation.intervals import Interval, wilson_ci
from simple_agents.evaluation.metrics import Metric, aggregate
from simple_agents.evaluation.outcomes import Outcome, RolloutOutcome
from simple_agents.evaluation.per_node import NodeMetrics
from simple_agents.evaluation.results import EvalResults

NODE_TABLE = re.compile(r"^  node .*$", re.MULTILINE)


def _sample_blocks() -> list[list[str]]:
    """The fenced report outputs in `docs/evaluation.md` §8.1, in the order they appear."""
    document = (Path(docs_path()) / "evaluation.md").read_text(encoding="utf-8")
    section = document[document.index("### 8.1 Reading it without parsing it") :]
    section = section[: section.index("\n## ")]
    return [
        fenced.splitlines() for fenced in section.split("```") if "rollout(s) on split" in fenced
    ]


def _sample_block() -> list[str]:
    """The first one, which is the report of an evaluation where nothing went wrong."""
    return _sample_blocks()[0]


def _interval(point: float, low: float, high: float, n: int) -> Interval:
    return Interval(
        point=point,
        low=low,
        high=high,
        n=n,
        k=None,
        confidence=0.95,
        resamples=0,
        seed=0,
    )


def _reach() -> Metric:
    """Reach over the three examples the sample describes, as the code computes it."""
    return Metric(
        name="reach",
        definition="",
        population="rollouts",
        rollouts=9,
        examples=3,
        interval=wilson_ci(3, 3),
    )


def _sample_nodes() -> dict[str, NodeMetrics]:
    """The two nodes the sample report describes, with the figures it prints."""
    hunt = NodeMetrics(
        node_id="hunt",
        node_kind="agent",
        runs=9,
        reached=9,
        executions=9,
        model_calls=19,
        tool_calls=19,
        reach=_reach(),
        cost=Cost(value=0.001038, currency="USD", basis="price"),
        terminations={"finish": 9},
        metrics={
            "span_f1": Metric(
                name="span_f1",
                definition="",
                population="rollouts",
                rollouts=2,
                examples=2,
                interval=_interval(1.0, 0.342, 1.0, 2),
            )
        },
    )
    verify = NodeMetrics(
        node_id="verify",
        node_kind="llm",
        runs=9,
        reached=9,
        executions=9,
        model_calls=9,
        tool_calls=0,
        reach=_reach(),
        cost=Cost(value=0.000338, currency="USD", basis="price"),
    )
    return {"hunt": hunt, "verify": verify}


def _report() -> list[str]:
    results = EvalResults(
        eval_id="sample",
        created_at="2026-08-09T00:00:00Z",
        config={"split": "held-out", "k": 3, "n": 3, "seed": 41},
        metrics={},
        nodes=_sample_nodes(),
        rollouts=(),
    )
    return results.report().splitlines()


def _rollouts_with_a_dead_backend() -> tuple[RolloutOutcome, ...]:
    """Three examples at k=3, one of which the backend stopped answering for."""
    outcomes = {
        "q1": Outcome.CORRECT,
        "q2": Outcome.NO_RESPONSE,
        "q3": Outcome.CORRECT_ABSTENTION,
    }
    return tuple(
        RolloutOutcome(example_id=example_id, rollout=index, seed=index, outcome=outcome)
        for example_id, outcome in outcomes.items()
        for index in range(3)
    )


def _unanswered_report() -> list[str]:
    rollouts = _rollouts_with_a_dead_backend()
    absence = {"q1": False, "q2": False, "q3": True}
    results = EvalResults(
        eval_id="sample",
        created_at="2026-08-09T00:00:00Z",
        config={"split": "held_out", "k": 3, "n": 3, "seed": 41},
        metrics=aggregate(rollouts, absence, seed=41),
        nodes={},
        rollouts=rollouts,
    )
    return results.report().splitlines()


class TestTheSampleReportIsWhatIsPrinted:
    def test_the_document_holds_a_node_table(self) -> None:
        """Guards the extraction: a rename of §8 must not make this file pass vacuously."""
        assert [line for line in _sample_block() if NODE_TABLE.match(line)]

    def test_the_column_header_matches(self) -> None:
        [documented] = [line for line in _sample_block() if NODE_TABLE.match(line)]
        [printed] = [line for line in _report() if NODE_TABLE.match(line)]

        assert documented == printed

    @pytest.mark.parametrize("node_id", ["hunt", "verify"])
    def test_each_node_row_matches(self, node_id: str) -> None:
        """Column widths as well as figures: the row is compared whole, including spacing."""
        prefix = f"  {node_id:<11} "
        [documented] = [line for line in _sample_block() if line.startswith(prefix)]
        [printed] = [line for line in _report() if line.startswith(prefix)]

        assert documented == printed

    def test_the_lines_under_a_node_match(self) -> None:
        """A project metric and the terminations, which are indented under their node."""
        under = "              "
        documented = [
            line
            for line in _sample_block()
            if line.startswith(under) and ("span_f1" in line or "ended" in line)
        ]
        printed = [
            line
            for line in _report()
            if line.startswith(under) and ("span_f1" in line or "ended" in line)
        ]

        assert documented == printed
        assert len(documented) == 2


class TestTheUnansweredSampleIsWhatIsPrinted:
    """The second block of §8.1: what a rollout the backend never answered does to a rate."""

    def test_the_document_holds_a_second_block(self) -> None:
        assert len(_sample_blocks()) == 2

    @pytest.mark.parametrize(
        "name",
        [
            "accuracy",
            "false_confidence_rate",
            "recall",
            "abstention_rate",
            "failure_rate",
            "precision_when_asserting",
        ],
    )
    def test_each_rate_line_matches(self, name: str) -> None:
        prefix = f"  {name} "
        [documented] = [line for line in _sample_blocks()[1] if line.startswith(prefix)]
        [printed] = [line for line in _unanswered_report() if line.startswith(prefix)]

        assert documented == printed

    def test_the_outcome_summary_matches(self) -> None:
        [documented] = [line for line in _sample_blocks()[1] if "no_response 3" in line]
        [printed] = [line for line in _unanswered_report() if "no_response 3" in line]

        assert documented == printed

    def test_every_rate_names_what_it_left_out(self) -> None:
        """The count is beside every rate, not only in a corner of the results file."""
        rates = [line for line in _sample_blocks()[1] if line.startswith("  ") and "%" in line]

        assert len(rates) == 8
        assert all("less 3 that got no response" in line for line in rates)
