"""Work that ended without producing anything, read back over a directory of runs.

`P3-22` stage 1. An `AgentNode` produces its output from a `finish` call, so an execution that
stops on a budget axis returns `None` to the node after it and the run completes with no error.
Dogfood #4 spent 24.4% of its model calls that way across 3,293 runs, and 15.2% on executions
that never called a tool at all. Every figure was in the trajectories and nothing aggregated
them: `per_node` computed most of it and was not exported, so the numbers existed only inside an
evaluation.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


from simple_agents import (
    AgentNode,
    Budget,
    Deterministic,
    FakeModelClient,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    node_metrics,
    read_trajectory,
    tool,
)
from simple_agents.errors import ModelFacingError
from simple_agents.models import ToolCallRequest, fake_response
from simple_agents.tools import ModelHandle

from schemas import Answer

SPINS = Budget(max_steps=3, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def look_up(name: str) -> str:
    """Look one name up."""
    return f"nothing on {name}"


def _prompt(inputs, ctx):
    return "answer the question"


def _after(inputs, ctx):
    return {"saw": inputs}


def _talks(request):
    """A model that never calls a tool and never finishes, which is dogfood #4's case."""
    return fake_response(content="I think I should keep thinking about this.")


def _calls_a_tool(request):
    return fake_response(
        tool_calls=[ToolCallRequest(id="c", name="look_up", arguments={"name": "N"})]
    )


def pipeline() -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                _prompt,
                tools=[look_up],
                output_schema=Answer,
                allow_unknown=False,
                node_id="hunt",
                budget=SPINS,
                successors=["after"],
            ),
            Deterministic(_after, node_id="after"),
        ],
        budget=Budget.unbounded(),
    )


class TestWhatASpunNodeProduced:
    def test_it_produces_nothing_and_the_run_completes(self, tmp_path) -> None:
        result = pipeline().run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=FakeModelClient(answer=_talks)
        )

        # The node after it was handed `None`, and nothing raised.
        assert result.output == {"saw": None}

    def test_the_figures_name_the_node_and_what_it_spent(self, tmp_path) -> None:
        for _ in range(2):
            pipeline().run(
                {},
                envelope=RunEnvelope(run_dir=tmp_path),
                model=FakeModelClient(answer=_talks),
            )

        found = node_metrics(tmp_path)

        assert found["hunt"].runs == 2
        assert found["hunt"].unfinished_executions == 2
        assert found["hunt"].unfinished_without_tool_calls == 2
        # Three steps each, and every one of them bought nothing.
        assert found["hunt"].unfinished_model_calls == 6
        assert found["hunt"].model_calls == 6
        assert found["after"].unfinished_executions == 0

    def test_a_node_that_acted_is_separated_from_one_that_did_not(self, tmp_path) -> None:
        pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(answer=_calls_a_tool),
        )

        found = node_metrics(tmp_path)

        # The cap cut off work that was under way, which is a different failure from a loop
        # that never started, and the two are reported apart.
        assert found["hunt"].unfinished_executions == 1
        assert found["hunt"].unfinished_without_tool_calls == 0
        assert found["hunt"].tool_calls == 3


class TestTheManifestSaysTheSameThing:
    """The manifest is what a gate over many runs reads, so it has to agree with the file."""

    def test_it_carries_what_the_trajectory_says(self, tmp_path) -> None:
        pipeline().run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=FakeModelClient(answer=_talks)
        )

        manifest = json.loads(next(tmp_path.glob("**/manifest.json")).read_text(encoding="utf-8"))
        from simple_agents.evaluation.per_node import unfinished_work

        trajectory = next(tmp_path.glob("**/trajectory.jsonl"))
        assert manifest["unfinished"] == unfinished_work(read_trajectory(trajectory))
        assert manifest["unfinished"] == {
            "hunt": {
                "executions": 1,
                "items": 0,
                "without_tool_calls": 1,
                "model_calls": 3,
                "model_calls_without_tool_calls": 3,
            }
        }

    def test_a_run_where_everything_produced_something_reports_nothing(self, tmp_path) -> None:
        def finishes(request):
            return fake_response(
                tool_calls=[
                    ToolCallRequest(id="f", name="finish", arguments={"answer": "32 inches"})
                ]
            )

        pipeline().run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=FakeModelClient(answer=finishes)
        )

        manifest = json.loads(next(tmp_path.glob("**/manifest.json")).read_text(encoding="utf-8"))
        assert manifest["unfinished"] == {}


class TestACallMadeInsideATool:
    """A `ModelHandle` call belongs to the item whose loop called the tool.

    Without that, two items' nested calls share one counter: the seed each is sent depends on
    which item reached the tool first, and the item that spent the call is then unknown.
    Measured 2026-08-19 at `P3-23`'s verification pass, with two items and `concurrency=2`.
    """

    def _run(self, tmp_path: Path, hold_back: str) -> dict[str, int]:
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def summarise(text: str, model: ModelHandle) -> str:
            """Summarise one passage, with a model of its own."""
            if hold_back in text:
                time.sleep(0.2)
            return str(model.complete(text).content)

        def judge_one(inputs, ctx):
            return f"judge {inputs['book']}"

        def answer(request):
            said = str(request.messages[-1].get("content", ""))
            if said.startswith("judge"):
                return fake_response(
                    tool_calls=[ToolCallRequest(id="c", name="summarise", arguments={"text": said})]
                )
            return fake_response(content="a summary")

        node = AgentNode(
            judge_one,
            tools=[summarise],
            output_schema=Answer,
            allow_unknown=False,
            node_id="judge",
            over="book",
            concurrent_items=2,
            budget=Budget(max_steps=30, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
            budget_per_item=SPINS,
        )
        Pipeline([node], budget=Budget.unbounded()).run(
            {"book": ["Ubik", "Solaris"]},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(answer=answer),
            seed=41,
            concurrency=2,
        )
        records = list(read_trajectory(next(tmp_path.glob("**/trajectory.jsonl"))))
        calls = {r["record_id"]: r for r in records if r["record_type"] == "tool_call"}
        return {
            calls[r["parent_id"]]["inputs"]["text"].split()[-1]: r["seed"]
            for r in records
            if r["record_type"] == "model_call" and r.get("parent_id") in calls
        }

    def test_its_seed_does_not_depend_on_which_item_got_there_first(self, tmp_path) -> None:
        first = self._run(tmp_path / "a", hold_back="Ubik")
        second = self._run(tmp_path / "b", hold_back="Solaris")

        assert first == second

    def test_what_it_spent_is_charged_to_its_own_item(self, tmp_path) -> None:
        self._run(tmp_path, hold_back="Ubik")

        found = node_metrics(tmp_path)["judge"]

        # Two items, three model calls each: two in the loop and one inside the tool.
        assert found.unfinished_items == 2
        assert found.unfinished_model_calls == 6


class TestWhichRunsAreRead:
    def _three_runs(self, tmp_path: Path) -> None:
        for _ in range(3):
            pipeline().run(
                {},
                envelope=RunEnvelope(run_dir=tmp_path),
                model=FakeModelClient(answer=_talks),
            )

    def test_every_run_under_the_directory_by_default(self, tmp_path) -> None:
        self._three_runs(tmp_path)

        assert node_metrics(tmp_path)["hunt"].runs == 3

    def test_last_keeps_the_newest_that_many(self, tmp_path) -> None:
        self._three_runs(tmp_path)

        found = node_metrics(tmp_path, last=2)

        assert found["hunt"].runs == 2
        assert found["hunt"].unfinished_executions == 2

    def test_since_leaves_out_what_started_earlier(self, tmp_path) -> None:
        self._three_runs(tmp_path)

        assert node_metrics(tmp_path, since="2099-01-01") == {}
        assert node_metrics(tmp_path, since="2000-01-01")["hunt"].runs == 3

    def test_a_role_the_project_declared_is_read_on_its_own(self, tmp_path) -> None:
        self._three_runs(tmp_path)
        pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, role="labelling"),
            model=FakeModelClient(answer=_talks),
        )

        assert node_metrics(tmp_path)["hunt"].runs == 4
        assert node_metrics(tmp_path, role="agent")["hunt"].runs == 3
        assert node_metrics(tmp_path, role="labelling")["hunt"].runs == 1

    def test_a_directory_with_no_runs_reports_nothing(self, tmp_path) -> None:
        assert node_metrics(tmp_path / "nothing-here") == {}


class TestAToolThatNeverAnswered:
    """`tools_that_never_succeeded` is over every run read, rather than over each one.

    Found 2026-08-19 reading the figure back over dogfood #4's 3,293 runs: the count was
    written per run rather than added, so a tool that failed once and worked afterwards was
    still named, with whichever run was read last deciding the number beside it.
    """

    def _run(self, tmp_path: Path, *, fails: bool) -> None:
        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="look_up")
        def looks_up(name: str) -> str:
            """Look one name up."""
            if fails:
                raise ModelFacingError("no match for that name")
            return f"something on {name}"

        Pipeline(
            [
                AgentNode(
                    _prompt,
                    tools=[looks_up],
                    output_schema=Answer,
                    allow_unknown=False,
                    node_id="hunt",
                    budget=SPINS,
                )
            ],
            budget=Budget.unbounded(),
        ).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(answer=_calls_a_tool),
        )

    def test_a_tool_that_failed_every_time_is_named_with_every_call(self, tmp_path) -> None:
        self._run(tmp_path, fails=True)
        self._run(tmp_path, fails=True)

        found = node_metrics(tmp_path)["hunt"]

        assert found.tools_that_never_succeeded == {"look_up": 6}

    def test_a_tool_that_worked_in_another_run_is_not_named(self, tmp_path) -> None:
        """The working run is the older one, since runs are read newest first."""
        self._run(tmp_path, fails=False)
        self._run(tmp_path, fails=True)

        assert node_metrics(tmp_path)["hunt"].tools_that_never_succeeded == {}
