"""The progress display, over both callbacks that report what is running.

`on_rollout=` shipped a one-line `describe()`, `on_progress=` and `progress_of` shipped data
and nothing rendered either, and dogfood #4's project rebuilt the third by hand, wrongly twice.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest

from simple_agents import ProgressBar
from simple_agents.evaluation.progress import RolloutProgress
from simple_agents.pipeline import NodeEvent

FIXTURES = Path(__file__).parent / "fixtures" / "projects"


class Terminal(io.StringIO):
    """A stream that says it is a terminal, which is what tqdm reads to decide."""

    def isatty(self) -> bool:
        return True


def rollout(**kwargs) -> RolloutProgress:
    fields = {
        "eval_id": "eval_a1226bc495df",
        "finished": 4,
        "total": 9,
        "resumed": 0,
        "outcomes": {"completed": 3, "error": 1},
        "cost": 0.0412,
        "currency": "USD",
        "elapsed_s": 10.0,
        "remaining_s": 12.0,
        "latest": None,
    }
    fields.update(kwargs)
    return RolloutProgress(**fields)


def node(phase: str, **kwargs) -> NodeEvent:
    return NodeEvent(phase=phase, node_id=kwargs.pop("node_id", "hunt"), node_kind="llm", **kwargs)


class TestWhatItWritesWhereTheStreamIsATerminal:
    def test_an_evaluation_gets_a_proportion_and_the_outcomes(self) -> None:
        out = Terminal()
        with ProgressBar(file=out) as bar:
            bar(rollout())

        written = out.getvalue()
        assert "4/9" in written
        assert "3 completed, 1 error" in written
        assert "0.0412 USD" in written

    def test_a_resumed_evaluation_starts_where_it_left_off(self) -> None:
        """`finished` counts what was read back from disk, so the bar is set and not stepped."""
        out = Terminal()
        with ProgressBar(file=out) as bar:
            bar(rollout(finished=7, resumed=6))

        assert "7/9" in out.getvalue()

    def test_a_fan_out_gets_a_bar_because_the_node_says_how_many(self) -> None:
        out = Terminal()
        with ProgressBar(file=out) as bar:
            bar(node("started"))
            bar(node("item", item_index=0, item_total=40))
            bar(node("item", item_index=1, item_total=40))

        assert "2/40" in out.getvalue()

    def test_a_resumed_fan_out_reaches_its_total(self) -> None:
        """`item_already_done` is what the resumed pass announces nothing for. Without it the
        bar ends short by whatever the earlier pass finished."""
        out = Terminal()
        with ProgressBar(file=out) as bar:
            bar(node("item", item_index=30, item_total=40, item_already_done=30))
            for index in range(31, 40):
                bar(node("item", item_index=index, item_total=40, item_already_done=30))

        assert "40/40" in out.getvalue()

    def test_a_failed_item_is_counted_and_said(self) -> None:
        """Dogfood #5 watched a bar reach its total over 37 failures (`DF5-D25`)."""
        out = Terminal()
        with ProgressBar(file=out) as bar:
            bar(node("item", item_index=0, item_total=3))
            bar(node("item", item_index=1, item_total=3, error={"message": "no"}))
            bar(node("item", item_index=2, item_total=3, error={"message": "no"}))

        written = out.getvalue()
        assert "3/3" in written
        assert "2 failed" in written

    def test_a_fan_out_with_nothing_wrong_says_nothing_about_failures(self) -> None:
        out = Terminal()
        with ProgressBar(file=out) as bar:
            bar(node("item", item_index=0, item_total=2))
            bar(node("item", item_index=1, item_total=2))

        assert "failed" not in out.getvalue()

    def test_two_fan_outs_count_their_failures_apart(self) -> None:
        out = Terminal()
        with ProgressBar(file=out) as bar:
            bar(node("item", node_id="a", item_index=0, item_total=2, error={"message": "no"}))
            bar(node("item", node_id="b", item_index=0, item_total=2))
            bar(node("item", node_id="b", item_index=1, item_total=2))

        assert "1 failed" in out.getvalue()
        assert "2 failed" not in out.getvalue()

    def test_a_run_gets_a_counter_because_nothing_knows_the_total(self) -> None:
        """Loops and routes decide how many nodes run while the run is running."""
        out = Terminal()
        with ProgressBar(file=out) as bar:
            bar(node("started"))
            bar(node("completed"))
            bar(node("started", node_id="verify"))
            bar(node("completed", node_id="verify"))

        written = out.getvalue()
        assert "2 nodes" in written
        assert "%" not in written

    def test_two_fan_outs_keep_their_own_counts(self) -> None:
        out = Terminal()
        with ProgressBar(file=out) as bar:
            bar(node("item", node_id="hunt", item_index=0, item_total=40))
            bar(node("item", node_id="score", item_index=0, item_total=7))
            bar(node("item", node_id="hunt", item_index=1, item_total=40))

        written = out.getvalue()
        assert "2/40" in written
        assert "1/7" in written


class TestWhatItWritesWhereTheStreamIsNot:
    """A run under CI or piped to a file is unchanged."""

    def test_an_evaluation_writes_nothing(self) -> None:
        out = io.StringIO()
        with ProgressBar(file=out) as bar:
            bar(rollout())

        assert out.getvalue() == ""

    def test_a_fan_out_writes_nothing(self) -> None:
        out = io.StringIO()
        with ProgressBar(file=out) as bar:
            bar(node("item", item_index=0, item_total=40))

        assert out.getvalue() == ""


class TestTheWatchCommand:
    """`simple-agents watch` reads a directory, so it needs nothing of the process running it."""

    def test_it_reports_a_finished_evaluation_and_returns(self, tmp_path, capsys) -> None:
        from simple_agents.cli import main

        source = FIXTURES / "conforming" / "runs"
        evaluation = next(source.iterdir())
        shutil.copytree(evaluation, tmp_path / evaluation.name)

        assert main(["watch", str(tmp_path / evaluation.name), "--expected", "9", "--once"]) == 0

    def test_without_a_total_it_counts_rather_than_claiming_to_be_finished(self, tmp_path) -> None:
        """A directory holding 12 rollouts cannot say whether that is all of them."""
        from simple_agents import progress_of
        from simple_agents.cli.main import _as_rollout_progress

        source = FIXTURES / "conforming" / "runs"
        evaluation = next(source.iterdir())
        shutil.copytree(evaluation, tmp_path / evaluation.name)

        out = Terminal()
        with ProgressBar(file=out) as bar:
            bar(_as_rollout_progress(progress_of(tmp_path / evaluation.name)))

        written = out.getvalue()
        assert "rollouts" in written
        assert "100%" not in written

    def test_it_reads_the_same_figures_progress_of_does(self, tmp_path) -> None:
        from simple_agents.cli.main import _as_rollout_progress
        from simple_agents import progress_of

        source = FIXTURES / "conforming" / "runs"
        evaluation = next(source.iterdir())
        shutil.copytree(evaluation, tmp_path / evaluation.name)

        state = progress_of(tmp_path / evaluation.name, expected=9)
        shown = _as_rollout_progress(state)

        assert shown.finished == state["finished"]
        assert shown.total == state["expected"]
        assert shown.outcomes == state["outcomes"]
        assert shown.cost == state["cost"]


class TestTheDisplayOutlivesNothing:
    def test_closing_twice_is_harmless(self) -> None:
        bar = ProgressBar(file=Terminal())
        bar(rollout())
        bar.close()
        bar.close()

    def test_the_block_closes_it_however_it_ends(self) -> None:
        out = Terminal()
        with pytest.raises(ValueError):
            with ProgressBar(file=out) as bar:
                bar(rollout())
                raise ValueError("the run failed")

        assert "4/9" in out.getvalue()
