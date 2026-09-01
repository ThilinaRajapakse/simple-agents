"""What overlaps, what a stop does to work in flight, and what stays the same either way.

Three units overlap: the arms of a branch, the items of a fan-out, and the tool calls inside
one turn. Each is declared, each is bounded by the run's ceiling, and none of them changes what
a run spends or which cassette entry answers a call.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import warnings
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import BaseModel

from simple_agents import (
    Cassette,
    AgentNode,
    Budget,
    Deterministic,
    LLMNode,
    Maybe,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    tool,
)
from simple_agents.budget import BudgetExceeded
from simple_agents.builtins import consult
from simple_agents.errors import ConfigurationError, RunSuspended, Suspend
from simple_agents.graph import Loop
from simple_agents.models import (
    FakeModelClient,
    ModelRequest,
    ToolCallRequest,
    fake_response,
)

from conftest import run_path

RUN_ID = "run_concurrency"
UNBOUNDED = Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


class Answer(BaseModel):
    text: Maybe[str]


def _slow(name: str, seconds: float = 0.2):
    def fn(inputs, ctx):
        time.sleep(seconds)
        return f"{name} done"

    fn.__name__ = name
    return fn


def _arms(groups):
    return Pipeline(
        [
            Deterministic(
                lambda i, c: i,
                node_id="plan",
                successors=["left", "right"],
                route=lambda o, c: ["left", "right"],
            ),
            Deterministic(_slow("left"), node_id="left", successors=["join"]),
            Deterministic(_slow("right"), node_id="right", successors=["join"]),
            Deterministic(lambda i, c: sorted(i.fired), node_id="join", successors=[]),
        ],
        budget=UNBOUNDED,
        concurrent_nodes=groups,
    )


class TestIndependentArms:
    """Two arms of a branch, listed in a group, run at the same time."""

    def test_arms_in_one_group_overlap(self, tmp_path) -> None:
        started = time.monotonic()
        result = _arms([["left", "right"]]).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=4
        )
        elapsed = time.monotonic() - started

        assert result.output == ["left", "right"]
        # Two 0.2s arms. Sequentially this is 0.4s; the margin is wide enough that a slow
        # machine cannot make an overlapping run look sequential.
        assert elapsed < 0.35

    def test_arms_not_in_a_group_run_one_after_another(self, tmp_path) -> None:
        started = time.monotonic()
        result = _arms(None).run({}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=4)

        assert result.output == ["left", "right"]
        assert time.monotonic() - started >= 0.4

    def test_a_ceiling_of_one_overlaps_nothing(self, tmp_path) -> None:
        """The declaration says what may overlap; the ceiling says how much does."""
        started = time.monotonic()
        _arms([["left", "right"]]).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=1
        )

        assert time.monotonic() - started >= 0.4

    def test_a_group_naming_an_unknown_node_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as caught:
            Pipeline(
                [Deterministic(lambda i, c: i, node_id="only", successors=[])],
                budget=UNBOUNDED,
                concurrent_nodes=[["only", "missing"]],
            )

        assert "'missing'" in str(caught.value)
        assert "'only'" in str(caught.value)

    def test_a_group_of_one_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as caught:
            Pipeline(
                [Deterministic(lambda i, c: i, node_id="only", successors=[])],
                budget=UNBOUNDED,
                concurrent_nodes=[["only"]],
            )

        assert "says nothing" in str(caught.value)

    def test_two_nodes_overlap_only_where_a_group_lists_both(self) -> None:
        graph = Pipeline(
            [
                Deterministic(
                    lambda i, c: i,
                    node_id="a",
                    successors=["b", "c", "d"],
                    route=lambda o, c: ["b", "c", "d"],
                ),
                Deterministic(lambda i, c: i, node_id="b", successors=["e"]),
                Deterministic(lambda i, c: i, node_id="c", successors=["e"]),
                Deterministic(lambda i, c: i, node_id="d", successors=["e"]),
                Deterministic(lambda i, c: i, node_id="e", successors=[]),
            ],
            budget=UNBOUNDED,
            concurrent_nodes=[["b", "c"], ["c", "d"]],
        ).graph

        assert graph.may_overlap("b", "c")
        assert graph.may_overlap("c", "d")
        assert not graph.may_overlap("b", "d")


class TestTwoArmsStoppingAtOnce:
    """Draining lets the arm beside a stop finish, and it can stop too."""

    def _pipeline(self):
        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        return Pipeline(
            [
                Deterministic(
                    lambda i, c: i,
                    node_id="plan",
                    successors=["left", "right"],
                    route=lambda o, c: ["left", "right"],
                ),
                AgentNode(
                    lambda i, c: "ask about fit",
                    output_schema=Answer,
                    tools=[
                        consult(unavailable, description="Ask about fit.", answered_by="end_user")
                    ],
                    budget=UNBOUNDED,
                    node_id="left",
                    successors=["join"],
                ),
                AgentNode(
                    lambda i, c: "ask about size",
                    output_schema=Answer,
                    tools=[
                        consult(unavailable, description="Ask about size.", answered_by="end_user")
                    ],
                    budget=UNBOUNDED,
                    node_id="right",
                    successors=["join"],
                ),
                Deterministic(lambda i, c: "joined", node_id="join", successors=[]),
            ],
            budget=UNBOUNDED,
            concurrent_nodes=[["left", "right"]],
        )

    def _asking(self):
        return FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c1", name="consult", arguments={"question": "which fit?"}
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c2", name="consult", arguments={"question": "which size?"}
                        )
                    ]
                ),
            ]
        )

    def test_both_stops_are_carried(self, tmp_path) -> None:
        with pytest.raises(RunSuspended) as caught:
            self._pipeline().run(
                {},
                envelope=RunEnvelope(run_dir=tmp_path),
                model=self._asking(),
                run_id=RUN_ID,
                seed=41,
                concurrency=4,
            )

        assert sorted(stop["node_id"] for stop in caught.value.stops) == ["left", "right"]
        state = json.loads(run_path(tmp_path, RUN_ID, "suspension.json").read_text())
        assert sorted(state["frames"][0]["in_progress"]) == ["left", "right"]
        # Each keeps what it was holding, so neither is re-run from the beginning.
        assert sorted(state["frames"][0]["node_state"]) == ["left", "right"]

    def test_one_answer_for_two_stops_is_refused(self, tmp_path) -> None:
        pipeline = self._pipeline()
        with pytest.raises(RunSuspended):
            pipeline.run(
                {},
                envelope=RunEnvelope(run_dir=tmp_path),
                model=self._asking(),
                run_id=RUN_ID,
                seed=41,
                concurrency=4,
            )

        with pytest.raises(Exception) as caught:
            pipeline.resume(
                RUN_ID,
                envelope=RunEnvelope(run_dir=tmp_path),
                model=self._asking(),
                answer="slim",
            )

        assert "answers=" in str(caught.value)
        assert "'left'" in str(caught.value)

    def test_answers_keyed_by_node_continue_both(self, tmp_path) -> None:
        pipeline = self._pipeline()
        with pytest.raises(RunSuspended):
            pipeline.run(
                {},
                envelope=RunEnvelope(run_dir=tmp_path),
                model=self._asking(),
                run_id=RUN_ID,
                seed=41,
                concurrency=4,
            )

        finishing = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="f1", name="finish", arguments={"text": "done"})]
                )
            ]
            * 2
        )
        result = pipeline.resume(
            RUN_ID,
            envelope=RunEnvelope(run_dir=tmp_path),
            model=finishing,
            answers={"left": "slim", "right": "medium"},
            concurrency=4,
        )

        assert result.output == "joined"

    def test_an_answer_for_a_node_that_did_not_stop_is_refused(self, tmp_path) -> None:
        pipeline = self._pipeline()
        with pytest.raises(RunSuspended):
            pipeline.run(
                {},
                envelope=RunEnvelope(run_dir=tmp_path),
                model=self._asking(),
                run_id=RUN_ID,
                seed=41,
                concurrency=4,
            )

        with pytest.raises(Exception) as caught:
            pipeline.resume(
                RUN_ID,
                envelope=RunEnvelope(run_dir=tmp_path),
                model=self._asking(),
                answers={"join": "slim"},
            )

        assert "'join'" in str(caught.value)


class TestAFanOutThatOverlaps:
    """Items run together, and are called with the seeds they would have had in order."""

    def _pipeline(self, concurrent_items):
        return Pipeline(
            [
                LLMNode(
                    lambda inputs, ctx: f"summarise {inputs['docs']}",
                    output_schema=Answer,
                    node_id="read",
                    over="docs",
                    concurrent_items=concurrent_items,
                    successors=[],
                )
            ],
            budget=UNBOUNDED,
        )

    def _client(self, count):
        # A function of the request rather than a queue: items that overlap take their
        # responses in whatever order they arrive, and a queue hands out whichever is next.
        return FakeModelClient(
            answer=lambda request: fake_response(
                content=json.dumps({"text": str(request.messages[-1]["content"])})
            )
        )

    def test_an_item_is_seeded_by_its_index_not_by_its_turn(self, tmp_path) -> None:
        """The same seeds either way, so a cassette recorded from one serves the other."""
        seeds = {}
        for label, width in (("ordered", None), ("overlapping", 4)):
            root = tmp_path / label
            result = self._pipeline(width).run(
                {"docs": ["a", "b", "c", "d"]},
                envelope=RunEnvelope(run_dir=root),
                model=self._client(4),
                seed=41,
                concurrency=4,
            )
            records = [
                json.loads(line)
                for line in Path(result.paths.trajectory).read_text().splitlines()
                if line.strip()
            ]
            seeds[label] = sorted(r["seed"] for r in records if r["record_type"] == "model_call")

        assert seeds["ordered"] == seeds["overlapping"]

    def test_the_outcomes_come_back_in_the_order_the_items_were_given(self, tmp_path) -> None:
        result = self._pipeline(4).run(
            {"docs": ["a", "b", "c", "d"]},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=self._client(4),
            seed=41,
            concurrency=4,
        )

        assert [outcome.index for outcome in result.output.outcomes] == [0, 1, 2, 3]
        assert [outcome.item for outcome in result.output.outcomes] == ["a", "b", "c", "d"]

    def test_concurrent_items_without_over_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as caught:
            LLMNode(
                lambda inputs, ctx: "one call",
                output_schema=Answer,
                node_id="read",
                concurrent_items=4,
            )

        assert "concurrent_items" in str(caught.value)
        assert "over=" in str(caught.value)

    def test_fewer_than_one_at_a_time_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as caught:
            LLMNode(
                lambda inputs, ctx: "one call",
                output_schema=Answer,
                node_id="read",
                over="docs",
                concurrent_items=0,
            )

        assert "concurrent_items=0" in str(caught.value)


class TestOverlappingToolCalls:
    """The tools a node named overlap within one turn; the rest of the turn does not."""

    def _tool(self, seconds=0.2):
        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="look_up")
        def look_up(q: str) -> str:
            """Wait, then answer."""
            time.sleep(seconds)
            return f"found {q}"

        return look_up

    def _writes(self):
        @tool(side_effect_class=SideEffectClass.WRITES, name="write_note")
        def write_note(text: str) -> str:
            """Write a note into the workspace."""
            return "written"

        return write_note

    def _client(self):
        return FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c1", name="look_up", arguments={"q": "one"}),
                        ToolCallRequest(id="c2", name="look_up", arguments={"q": "two"}),
                        ToolCallRequest(id="c3", name="look_up", arguments={"q": "three"}),
                    ]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="c4", name="finish", arguments={"text": "done"})]
                ),
            ]
        )

    def _pipeline(self, named):
        look_up = self._tool()
        return Pipeline(
            [
                AgentNode(
                    lambda i, c: "go",
                    tools=[look_up],
                    output_schema=Answer,
                    budget=UNBOUNDED,
                    node_id="hunt",
                    concurrent_tools=[look_up] if named else None,
                    successors=[],
                )
            ],
            budget=UNBOUNDED,
        )

    def test_named_tools_overlap_within_a_turn(self, tmp_path) -> None:
        started = time.monotonic()
        self._pipeline(named=True).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=self._client(),
            seed=41,
            concurrency=4,
        )

        assert time.monotonic() - started < 0.4

    def test_tools_not_named_run_one_after_another(self, tmp_path) -> None:
        started = time.monotonic()
        self._pipeline(named=False).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=self._client(),
            seed=41,
            concurrency=4,
        )

        assert time.monotonic() - started >= 0.6

    def test_identical_calls_keep_the_numbers_their_positions_give_them(self, tmp_path) -> None:
        """Two identical calls in one turn record two entries, whichever finished first."""
        look_up = self._tool(seconds=0.0)
        cassette = tmp_path / "turn.jsonl"
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda i, c: "go",
                    tools=[look_up],
                    output_schema=Answer,
                    budget=UNBOUNDED,
                    node_id="hunt",
                    concurrent_tools=[look_up],
                    successors=[],
                )
            ],
            budget=UNBOUNDED,
        )
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c1", name="look_up", arguments={"q": "same"}),
                        ToolCallRequest(id="c2", name="look_up", arguments={"q": "same"}),
                    ]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="c3", name="finish", arguments={"text": "done"})]
                ),
            ]
        )
        pipeline.run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette)),
            model=client,
            seed=41,
            concurrency=4,
        )

        entries = [json.loads(line) for line in cassette.read_text().splitlines() if line.strip()]
        occurrences = sorted(
            entry["request"]["occurrence"] for entry in entries if entry["kind"] == "tool_call"
        )
        assert occurrences == [0, 1]

    def test_a_writing_tool_cannot_be_named(self) -> None:
        writes = self._writes()
        with pytest.raises(ConfigurationError) as caught:
            AgentNode(
                lambda i, c: "go",
                tools=[writes],
                output_schema=Answer,
                budget=UNBOUNDED,
                node_id="hunt",
                concurrent_tools=[writes],
            )

        assert "WRITES" in str(caught.value)
        assert "one workspace directory" in str(caught.value)

    def test_a_tool_that_can_stop_the_run_cannot_be_named(self) -> None:
        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        asking = consult(unavailable, description="Ask.", answered_by="end_user")
        with pytest.raises(ConfigurationError) as caught:
            AgentNode(
                lambda i, c: "go",
                tools=[asking],
                output_schema=Answer,
                budget=UNBOUNDED,
                node_id="hunt",
                concurrent_tools=[asking],
            )

        assert "turn boundary" in str(caught.value)

    def test_a_tool_the_node_does_not_have_cannot_be_named(self) -> None:
        look_up = self._tool()
        other = self._writes()
        with pytest.raises(ConfigurationError) as caught:
            AgentNode(
                lambda i, c: "go",
                tools=[look_up],
                output_schema=Answer,
                budget=UNBOUNDED,
                node_id="hunt",
                concurrent_tools=[other],
            )

        assert "'write_note'" in str(caught.value)
        assert "'look_up'" in str(caught.value)


class TestAScriptedFakeUnderOverlap:
    """A queue of responses leaves the call each belongs to unknown, and says so."""

    def test_a_second_call_arriving_while_one_is_in_flight_is_refused(self) -> None:
        """The guard, checked directly: a queue cannot say which call a response belongs to."""
        client = FakeModelClient(responses=[fake_response(content="a")] * 4)
        request = ModelRequest(messages=[{"role": "user", "content": "hi"}], seed=1)
        client._in_flight = 1

        with pytest.raises(Exception) as caught:
            client.complete(request)

        assert "answer=" in str(caught.value)
        assert "which arrived first" in str(caught.value)

    def test_a_function_of_the_request_answers_each_call_with_its_own(self) -> None:
        client = FakeModelClient(
            answer=lambda request: fake_response(content=request.messages[-1]["content"])
        )
        one = client.complete(ModelRequest(messages=[{"role": "user", "content": "fit?"}], seed=1))
        two = client.complete(ModelRequest(messages=[{"role": "user", "content": "size?"}], seed=2))

        assert (one.content, two.content) == ("fit?", "size?")


class TestDraining:
    """A stop lets what is running finish, and does not start what has not begun."""

    def test_a_budget_stops_the_items_that_had_not_started(self, tmp_path) -> None:
        pipeline = Pipeline(
            [
                LLMNode(
                    lambda inputs, ctx: f"read {inputs['docs']}",
                    output_schema=Answer,
                    node_id="read",
                    over="docs",
                    concurrent_items=2,
                    successors=[],
                )
            ],
            budget=Budget(max_steps=2, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        client = FakeModelClient(
            responses=[fake_response(content=json.dumps({"text": f"n{i}"})) for i in range(8)]
        )

        with pytest.raises(BudgetExceeded) as caught:
            pipeline.run(
                {"docs": ["a", "b", "c", "d", "e", "f"]},
                envelope=RunEnvelope(run_dir=tmp_path),
                model=client,
                seed=41,
                concurrency=2,
            )

        assert caught.value.axis == "max_steps"
        records = [
            json.loads(line)
            for line in (Path(tmp_path).glob("**/trajectory.jsonl").__next__())
            .read_text()
            .splitlines()
            if line.strip()
        ]
        calls = [r for r in records if r["record_type"] == "model_call"]
        # One step is one call, and a call does not start unless a step remains, so the
        # ceiling is exact on this axis rather than overshooting by what was in flight.
        assert len(calls) == 2


class TestWhatDoesNotChange:
    """The wall clock is elapsed, and the counted axes read the same either way."""

    def test_a_run_that_overlaps_is_charged_the_time_that_passed(self, tmp_path) -> None:
        pipeline = _arms([["left", "right"]])
        pipeline.budget = Budget(
            max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=300
        )

        # Two 0.2s arms overlapping is 0.2s of wall clock, inside a 0.3s ceiling. Summing what
        # each arm took would be 0.4s and would stop the run.
        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=4)

        assert result.output == ["left", "right"]

    def test_the_same_run_in_order_exceeds_that_ceiling(self, tmp_path) -> None:
        pipeline = _arms(None)
        pipeline.budget = Budget(
            max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=300
        )

        with pytest.raises(BudgetExceeded) as caught:
            pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), seed=41)

        assert caught.value.axis == "max_wall_clock"


class Watcher:
    """A client that takes real time and records the most calls it ever had at once.

    A ceiling is then checked against what happened rather than against a stopwatch, which is
    what makes these assertions exact instead of timing-dependent.
    """

    def __init__(self, answer=None) -> None:
        self._answer = answer
        self._lock = threading.Lock()
        self.in_flight = 0
        self.peak = 0
        self.calls = 0

    def identity(self):
        from simple_agents.models import ModelIdentity

        return ModelIdentity(
            backend="self_hosted", request_model="test/model", model_revision="0" * 40
        )

    def complete(self, request):
        with self._lock:
            self.in_flight += 1
            self.calls += 1
            self.peak = max(self.peak, self.in_flight)
        try:
            time.sleep(0.02)
            return (
                self._answer(request)
                if self._answer is not None
                else fake_response(content=json.dumps({"text": "ok"}))
            )
        finally:
            with self._lock:
                self.in_flight -= 1


def _reading(request):
    return fake_response(content=json.dumps({"text": "ok"}))


def _fan_out_node(node_id, width, model=None):
    return LLMNode(
        lambda i, c: "x",
        output_schema=Answer,
        node_id=node_id,
        over="docs",
        concurrent_items=width,
        model=model,
        successors=["j"],
    )


class TestTheCeilingBinds:
    """`concurrency=N` is the most calls in flight, whatever declared it may overlap."""

    def test_a_fan_out_is_clamped_by_the_ceiling(self, tmp_path) -> None:
        client = Watcher(_reading)
        Pipeline(
            [
                LLMNode(
                    lambda i, c: "x",
                    output_schema=Answer,
                    node_id="read",
                    over="docs",
                    concurrent_items=8,
                    successors=[],
                )
            ],
            budget=UNBOUNDED,
        ).run(
            {"docs": list("abcdefgh")},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=client,
            seed=41,
            concurrency=2,
        )

        assert client.calls == 8
        assert client.peak == 2

    def test_one_ceiling_covers_two_concurrent_regions(self, tmp_path) -> None:
        """Each region bounding only itself would put six calls in flight, not three."""
        client = Watcher(_reading)
        Pipeline(
            [
                Deterministic(
                    lambda i, c: {"docs": list("abcd")},
                    node_id="plan",
                    successors=["l", "r"],
                    route=lambda o, c: ["l", "r"],
                ),
                _fan_out_node("l", 3),
                _fan_out_node("r", 3),
                Deterministic(lambda i, c: "done", node_id="j", successors=[]),
            ],
            budget=UNBOUNDED,
            concurrent_nodes=[["l", "r"]],
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client, seed=41, concurrency=3)

        assert client.calls == 8
        assert client.peak == 3

    def test_a_node_with_its_own_model_is_bounded_by_its_own_count(self, tmp_path) -> None:
        cheap, dear = Watcher(_reading), Watcher(_reading)
        Pipeline(
            [
                Deterministic(
                    lambda i, c: {"docs": list("abcdef")},
                    node_id="plan",
                    successors=["bulk", "hard"],
                    route=lambda o, c: ["bulk", "hard"],
                ),
                _fan_out_node("bulk", 6, model=cheap),
                LLMNode(
                    lambda i, c: "x",
                    output_schema=Answer,
                    node_id="hard",
                    model=dear,
                    successors=["j"],
                ),
                Deterministic(lambda i, c: "done", node_id="j", successors=[]),
            ],
            budget=UNBOUNDED,
            concurrent_nodes=[["bulk", "hard"]],
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=8)

        assert (cheap.calls, dear.calls) == (6, 1)
        assert dear.peak == 1


class TestOverlapNestedInsideOverlap:
    """A concurrent region inside another must not wait on itself."""

    def test_two_arms_each_a_fan_out(self, tmp_path) -> None:
        client = Watcher(_reading)
        Pipeline(
            [
                Deterministic(
                    lambda i, c: {"docs": list("abcd")},
                    node_id="plan",
                    successors=["l", "r"],
                    route=lambda o, c: ["l", "r"],
                ),
                _fan_out_node("l", 4),
                _fan_out_node("r", 4),
                Deterministic(lambda i, c: "done", node_id="j", successors=[]),
            ],
            budget=UNBOUNDED,
            concurrent_nodes=[["l", "r"]],
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client, seed=41, concurrency=6)

        assert client.calls == 8
        assert client.peak <= 6

    def test_a_nested_pipeline_carries_its_own_groups(self, tmp_path) -> None:
        client = Watcher(_reading)
        inner = Pipeline(
            [
                Deterministic(
                    lambda i, c: i,
                    node_id="split",
                    successors=["a", "b"],
                    route=lambda o, c: ["a", "b"],
                ),
                LLMNode(lambda i, c: "x", output_schema=Answer, node_id="a", successors=["m"]),
                LLMNode(lambda i, c: "x", output_schema=Answer, node_id="b", successors=["m"]),
                Deterministic(lambda i, c: "inner", node_id="m", successors=[]),
            ],
            budget=UNBOUNDED,
            node_id="inner",
            concurrent_nodes=[["a", "b"]],
            successors=[],
        )
        Pipeline(
            [Deterministic(lambda i, c: i, node_id="start", successors=["inner"]), inner],
            budget=UNBOUNDED,
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client, seed=41, concurrency=4)

        assert client.peak == 2


class TestGraphFeaturesUnderOverlap:
    """Routes, joins, skips, cycles and error edges keep working when arms overlap."""

    def _arms(self, left, right, route, groups=None, **kinds):
        return Pipeline(
            [
                Deterministic(lambda i, c: i, node_id="plan", successors=["l", "r"], route=route),
                Deterministic(left, node_id="l", successors=["j"], **kinds),
                Deterministic(right, node_id="r", successors=["j"]),
                Deterministic(lambda i, c: sorted(i.fired), node_id="j", successors=[]),
            ],
            budget=UNBOUNDED,
            concurrent_nodes=groups,
        )

    def test_a_join_reads_both_overlapping_arms(self, tmp_path) -> None:
        result = self._arms(
            lambda i, c: "L", lambda i, c: "R", lambda o, c: ["l", "r"], [["l", "r"]]
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=4)

        assert result.output == ["l", "r"]

    def test_an_arm_nothing_reached_is_still_skipped(self, tmp_path) -> None:
        result = self._arms(
            lambda i, c: "L", lambda i, c: "R", lambda o, c: ["l"], [["l", "r"]]
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=4)

        assert result.output == ["l"]

    def test_an_error_edge_inside_an_arm(self, tmp_path) -> None:
        def boom(inputs, ctx):
            raise ValueError("nope")

        result = Pipeline(
            [
                Deterministic(
                    lambda i, c: i,
                    node_id="plan",
                    successors=["bad", "good"],
                    route=lambda o, c: ["bad", "good"],
                ),
                Deterministic(boom, node_id="bad", successors=["j"], on_error="rescue"),
                Deterministic(lambda i, c: "G", node_id="good", successors=["j"]),
                Deterministic(lambda i, c: "rescued", node_id="rescue", successors=["j"]),
                Deterministic(lambda i, c: sorted(i.fired), node_id="j", successors=[]),
            ],
            budget=UNBOUNDED,
            concurrent_nodes=[["bad", "good"]],
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=4)

        assert result.output == ["good", "rescue"]

    def test_an_unhandled_raise_in_one_arm_ends_the_run(self, tmp_path) -> None:
        def boom(inputs, ctx):
            raise ValueError("nope")

        with pytest.raises(ValueError, match="nope"):
            self._arms(boom, lambda i, c: "R", lambda o, c: ["l", "r"], [["l", "r"]]).run(
                {}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=4
            )

    def test_a_cycle_inside_an_overlapping_arm(self, tmp_path) -> None:
        seen = {"n": 0}

        def again(inputs, ctx):
            seen["n"] += 1
            return seen["n"]

        Pipeline(
            [
                Deterministic(
                    lambda i, c: i,
                    node_id="plan",
                    successors=["loop", "other"],
                    route=lambda o, c: ["loop", "other"],
                ),
                Deterministic(again, node_id="loop", successors=["gate"]),
                Deterministic(
                    lambda i, c: i,
                    node_id="gate",
                    successors=["loop", "j"],
                    route=lambda o, c: "loop" if o < 3 else "j",
                    loop=Loop(then="j", max_iterations=5),
                ),
                Deterministic(lambda i, c: "O", node_id="other", successors=["j"]),
                Deterministic(lambda i, c: sorted(i.fired), node_id="j", successors=[]),
            ],
            budget=UNBOUNDED,
            concurrent_nodes=[["loop", "other"]],
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=4)

        assert seen["n"] == 3


class TestWhatTheTrajectoryStillSays:
    """Overlap changes the interleaving and nothing about how a record is read."""

    def test_every_call_resolves_to_its_node_and_parents_come_after(self, tmp_path) -> None:
        client = Watcher(_reading)
        result = Pipeline(
            [
                Deterministic(
                    lambda i, c: {"docs": list("abcd")},
                    node_id="plan",
                    successors=["l", "r"],
                    route=lambda o, c: ["l", "r"],
                ),
                _fan_out_node("l", 4),
                _fan_out_node("r", 4),
                Deterministic(lambda i, c: "done", node_id="j", successors=[]),
            ],
            budget=UNBOUNDED,
            concurrent_nodes=[["l", "r"]],
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client, seed=41, concurrency=8)

        records = [
            json.loads(line)
            for line in Path(result.paths.trajectory).read_text().splitlines()
            if line.strip()
        ]
        by_id = {r["record_id"]: r for r in records}
        nodes = {r["record_id"] for r in records if r["record_type"] == "node_execution"}
        calls = [r for r in records if r["record_type"] == "model_call"]

        assert len(calls) == 8
        # Every call belongs to a node record, and the node was written after it.
        assert all(r["parent_id"] in nodes for r in calls)
        assert all(by_id[r["parent_id"]]["sequence"] > r["sequence"] for r in calls)
        # `sequence` is still monotonic in the order records were written.
        assert [r["sequence"] for r in records] == sorted(r["sequence"] for r in records)


class TestAnEvaluationOfAConcurrentPipeline:
    """Rollouts and the runs inside them compose, and both numbers are recorded."""

    def test_rollouts_and_runs_multiply(self, tmp_path) -> None:
        from simple_agents.evaluation import EvalSuite, Example, ExampleSet

        client = Watcher(_reading)
        suite = EvalSuite(
            pipeline=Pipeline(
                [
                    LLMNode(
                        lambda i, c: "x",
                        output_schema=Answer,
                        node_id="read",
                        over="docs",
                        concurrent_items=4,
                        successors=[],
                    )
                ],
                budget=UNBOUNDED,
            ),
            examples=ExampleSet(
                [
                    Example(
                        id=f"e{i}", inputs={"docs": list("abcd")}, expected="ok", split="held_out"
                    )
                    for i in range(3)
                ]
            ),
            answer=lambda output: "ok",
            matches=lambda s: s.answer == s.expected,
        )
        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=client,
            split="held_out",
            k=2,
            seed=41,
            concurrency=2,
            run_concurrency=4,
            record=False,
        )

        assert client.calls == 24
        assert results.config["concurrency"] == 2
        assert results.config["run_concurrency"] == 4


class TestSharedStateUnderOverlap:
    """What several threads write into, checked with the interpreter preempting constantly.

    ``sys.setswitchinterval`` is turned down so a read-modify-write is interrupted rather than
    happening to complete. Both of these passed at the default interval while being unsafe, so
    the interval is what makes them tests rather than coincidences.
    """

    @contextmanager
    def _preempting(self):
        was = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            yield
        finally:
            sys.setswitchinterval(was)

    def _fan_out_run(self, tmp_path, items, width):
        client = Watcher(_reading)
        result = Pipeline(
            [
                LLMNode(
                    lambda i, c: "x",
                    output_schema=Answer,
                    node_id="read",
                    over="docs",
                    concurrent_items=width,
                    successors=[],
                )
            ],
            budget=UNBOUNDED,
        ).run(
            {"docs": [str(i) for i in range(items)]},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=client,
            seed=41,
            concurrency=width,
        )
        records = [
            json.loads(line)
            for line in Path(result.paths.trajectory).read_text().splitlines()
            if line.strip()
        ]
        return result, records

    def test_the_manifest_loses_no_count(self) -> None:
        """Every counter is read and written back, and an unguarded one loses updates.

        Hammered directly rather than through a run: a run makes too few calls to lose one
        reliably, and a test that passes whether or not the lock is there proves nothing.
        """
        from simple_agents.records.manifest import Manifest

        manifest = Manifest(
            run_id="r",
            started_at="t",
            seed=1,
            budget={},
            library_version="0",
            trajectory_path="t",
            workspace_path="w",
        )
        threads, each = 8, 20_000

        def hammer() -> None:
            for _ in range(each):
                manifest.count_record("model_call")
                manifest.count_cassette(hits=1)
                manifest.observe_tokens(
                    {
                        "input_uncached": 1,
                        "input_cache_read": 0,
                        "input_cache_write": 0,
                        "cache_ttl": None,
                        "output": 1,
                    }
                )
                manifest.observe_held_back(1)

        with self._preempting():
            running = [threading.Thread(target=hammer) for _ in range(threads)]
            for thread in running:
                thread.start()
            for thread in running:
                thread.join()

        written = manifest.to_json()
        expected = threads * each
        assert written["counts"]["model_call"] == expected
        assert written["cassette"]["hits"] == expected
        assert written["totals"]["tokens"]["output"] == expected
        assert written["totals"]["held_back_ms"] == expected

    def test_the_manifest_agrees_with_the_trajectory(self, tmp_path) -> None:
        """What the manifest says the run wrote is what the trajectory holds."""
        with self._preempting():
            result, records = self._fan_out_run(tmp_path, items=60, width=12)

        calls = [r for r in records if r["record_type"] == "model_call"]
        assert len(calls) == 60
        assert result.manifest["counts"]["model_call"] == 60
        assert result.manifest["totals"]["tokens"]["output"] == sum(
            r["tokens"]["output"] for r in calls
        )

    def test_a_record_is_numbered_inside_the_write(self, tmp_path) -> None:
        """Numbering and writing are one step, so the file is in the order of the numbers.

        Deterministic rather than probabilistic: the first writer is held inside its call while
        the second tries to write. If the two were separate steps the second could take its
        number and reach the file first, which is the defect this holds shut.
        """
        from simple_agents.records.trajectory import PENDING_SEQUENCE, TrajectoryWriter

        writer = TrajectoryWriter(tmp_path / "trajectory.jsonl")
        holding = threading.Event()
        second_arrived = threading.Event()
        given: list[int] = []

        def numbering(value: int, block: bool):
            def number() -> int:
                if block:
                    holding.set()
                    # Long enough that the other thread has certainly tried and blocked.
                    second_arrived.wait(0.5)
                given.append(value)
                return value

            return number

        def record(name: str):
            return {"record_type": "node_execution", "node_id": name, "sequence": PENDING_SEQUENCE}

        first = threading.Thread(
            target=lambda: writer.write(record("first"), number=numbering(1, block=True))
        )
        first.start()
        assert holding.wait(1.0)

        def second() -> None:
            second_arrived.set()
            writer.write(record("second"), number=numbering(2, block=False))

        later = threading.Thread(target=second)
        later.start()
        first.join(2.0)
        later.join(2.0)
        writer.close()

        written = [
            json.loads(line)
            for line in (tmp_path / "trajectory.jsonl").read_text().splitlines()
            if line.strip()
        ]
        # The blocked writer numbered first and reached the file first: the second could not
        # take a number while the first held the lock.
        assert given == [1, 2]
        assert [r["node_id"] for r in written] == ["first", "second"]
        assert [r["sequence"] for r in written] == [1, 2]

    def test_a_run_writes_its_records_in_sequence_order(self, tmp_path) -> None:
        with self._preempting():
            _, records = self._fan_out_run(tmp_path, items=200, width=16)

        sequences = [r["sequence"] for r in records]
        assert sequences == sorted(sequences)
        assert len(set(sequences)) == len(sequences)


class TestAblationKeepsTheGroups:
    """An arm has to differ from the baseline in the ablated node and in nothing else."""

    def _pipeline(self):
        return Pipeline(
            [
                # The route reads what this node still declares, so an arm that had a
                # successor ablated away does not name it.
                Deterministic(
                    lambda i, c: i,
                    node_id="plan",
                    successors=["l", "r", "extra"],
                    route=lambda o, c: [s for s in c.successors if s != "j"] or ["j"],
                ),
                Deterministic(lambda i, c: "L", node_id="l", successors=["j"]),
                Deterministic(lambda i, c: "R", node_id="r", successors=["j"]),
                Deterministic(lambda i, c: "X", node_id="extra", successors=["j"]),
                Deterministic(lambda i, c: "done", node_id="j", successors=[]),
            ],
            budget=UNBOUNDED,
            concurrent_nodes=[["l", "r"]],
        )

    def test_an_arm_keeps_a_group_neither_of_whose_nodes_it_removed(self) -> None:
        """Otherwise the arm runs sequentially what the baseline overlapped, and the
        comparison holds two differences rather than one."""
        from simple_agents.evaluation.variants import ablate

        arms = ablate(self._pipeline())

        assert arms["extra removed"].concurrent_nodes == (("l", "r"),)

    def test_a_group_left_with_one_node_is_dropped(self) -> None:
        """A group of one says nothing, and would be refused at construction."""
        from simple_agents.evaluation.variants import ablate

        arms = ablate(self._pipeline())

        assert arms["l removed"].concurrent_nodes == ()
        assert arms["r removed"].concurrent_nodes == ()

    def test_every_arm_still_builds_and_runs(self, tmp_path) -> None:
        from simple_agents.evaluation.variants import ablate

        for name, arm in ablate(self._pipeline()).items():
            result = arm.run(
                {},
                envelope=RunEnvelope(run_dir=tmp_path / name.replace(" ", "-")),
                seed=41,
                concurrency=4,
            )
            assert result.output == "done"


class TestTheWallClockIsElapsed:
    """`max_wall_clock_ms` counts the time that passed, not the sum of what calls took."""

    class _HeldBack:
        """A client that waits before answering and reports the wait as `held_back_ms`.

        What a `PacedClient` in front of a quota does, and what an adapter's retry backoff
        does. The wait is real time, so a run is charged for it.
        """

        def __init__(self, wait_s: float) -> None:
            self.wait_s = wait_s

        def identity(self):
            from simple_agents.models import ModelIdentity

            return ModelIdentity(
                backend="self_hosted", request_model="test/model", model_revision="0" * 40
            )

        def complete(self, request):
            time.sleep(self.wait_s)
            answer = fake_response(content=json.dumps({"text": "ok"}))
            return replace(answer, held_back_ms=int(self.wait_s * 1000))

    def _pipeline(self, ceiling_ms):
        return Pipeline(
            [
                LLMNode(lambda i, c: "x", output_schema=Answer, node_id="a", successors=["b"]),
                LLMNode(lambda i, c: "x", output_schema=Answer, node_id="b", successors=[]),
            ],
            budget=Budget(
                max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=ceiling_ms
            ),
        )

    def test_time_spent_waiting_to_be_allowed_to_call_is_charged(self, tmp_path) -> None:
        """It used to be subtracted, so a run held behind a quota was charged nothing for it."""
        with pytest.raises(BudgetExceeded) as caught:
            self._pipeline(150).run(
                {},
                envelope=RunEnvelope(run_dir=tmp_path),
                model=self._HeldBack(wait_s=0.2),
                seed=41,
            )

        assert caught.value.axis == "max_wall_clock"

    def test_a_run_inside_the_ceiling_still_finishes(self, tmp_path) -> None:
        result = self._pipeline(5_000).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=self._HeldBack(wait_s=0.02),
            seed=41,
        )

        assert result.output.text == "ok"

    def test_the_wall_clock_is_elapsed_and_not_the_sum_of_the_calls(self, tmp_path) -> None:
        """Two 0.2s arms overlapping is 0.2s of wall clock. Summed it would be 0.4s and would
        stop the run, which is what the axis used to do."""
        pipeline = Pipeline(
            [
                Deterministic(
                    lambda i, c: i,
                    node_id="plan",
                    successors=["l", "r"],
                    route=lambda o, c: ["l", "r"],
                ),
                LLMNode(
                    lambda i, c: "x",
                    output_schema=Answer,
                    node_id="l",
                    model=self._HeldBack(0.2),
                    successors=["j"],
                ),
                LLMNode(
                    lambda i, c: "x",
                    output_schema=Answer,
                    node_id="r",
                    model=self._HeldBack(0.2),
                    successors=["j"],
                ),
                Deterministic(lambda i, c: "done", node_id="j", successors=[]),
            ],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=320),
            concurrent_nodes=[["l", "r"]],
        )

        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), seed=41, concurrency=4)

        assert result.output == "done"


class TestTheVectorStoreUnderOverlap:
    """Identifiers and vectors are one table in two lists, and must stay paired."""

    def test_two_writers_never_file_a_vector_under_another_id(self) -> None:
        """A mispairing is silent: the scores are right and the documents named are not."""
        from simple_agents.builtins.ranking import VectorScan

        store = VectorScan()
        threads, each = 8, 300

        def add(tag: int) -> None:
            for index in range(each):
                store.add([f"{tag}-{index}"], [[float(tag), float(index)]])

        was = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            running = [threading.Thread(target=add, args=(tag,)) for tag in range(threads)]
            for thread in running:
                thread.start()
            for thread in running:
                thread.join()
        finally:
            sys.setswitchinterval(was)

        ids = store.ids()
        assert len(ids) == threads * each
        # Each vector holds the tag and index its own identifier names.
        mispaired = [
            name
            for name, vector in zip(ids, store._vectors)
            if name != f"{int(vector[0])}-{int(vector[1])}"
        ]
        assert mispaired == []

    def test_a_search_beside_a_write_reads_one_consistent_table(self) -> None:
        from simple_agents.builtins.ranking import VectorScan

        store = VectorScan()
        store.add(["seed"], [[1.0, 0.0]])
        stop = threading.Event()
        failures: list[BaseException] = []

        # Both sides are bounded: the store stays small, so a search stays cheap and the two
        # threads interleave rather than one outrunning the other into a quadratic scan.
        def writing() -> None:
            for index in range(400):
                if stop.is_set():
                    return
                store.add([f"w{index}"], [[1.0, float(index)]])

        def searching() -> None:
            try:
                for _ in range(400):
                    store.search([1.0, 0.0], top_k=3)
            except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
                failures.append(exc)

        writer = threading.Thread(target=writing, daemon=True)
        writer.start()
        reader = threading.Thread(target=searching)
        reader.start()
        reader.join(10)
        stop.set()
        writer.join(2)

        assert failures == []


class TestOverlappingRunsUnderDifferentScopes:
    """One `Pipeline` and one `RunEnvelope` serving many people at once.

    `P3-44`'s reason for existing: the scope was on the envelope, so a request handler
    rebuilt the envelope per request. Nothing per-run may live on either object now.
    """

    def test_no_run_reads_or_writes_another_person_s_memory(self, tmp_path) -> None:
        from simple_agents import MemoryStore
        from simple_agents.builtins import recall, remember

        people = [f"user-{i}" for i in range(24)]
        env = RunEnvelope(run_dir=tmp_path / "runs", memory=MemoryStore(tmp_path / "memory"))

        def work(inputs, ctx):
            ctx.call_tool("remember", key="mine", value=inputs["who"])
            return ctx.call_tool("recall", key="mine")

        pipeline = Pipeline(
            [Deterministic(work, node_id="w", tools=[remember(), recall()])],
            budget=Budget(max_steps=8, max_tokens=9_999, max_cost=None, max_wall_clock_ms=30_000),
        )
        answers: dict[str, str] = {}
        failures: list[str] = []

        def one(who: str) -> None:
            try:
                result = pipeline.run(
                    {"who": who}, envelope=env, run_id=f"r-{who}", memory_scope=who
                )
                answers[who] = result.output["value"]
            except Exception as error:  # noqa: BLE001
                failures.append(f"{who}: {error}")

        threads = [threading.Thread(target=one, args=(who,)) for who in people]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        store = MemoryStore(tmp_path / "memory")
        assert failures == []
        assert answers == {who: who for who in people}
        assert {who: store.scoped(who).get("mine").value for who in people} == {
            who: who for who in people
        }
        assert len(list((tmp_path / "memory").iterdir())) == len(people)
        digests = [
            json.loads(path.read_text())["memory"]["scope_digest"]
            for path in (tmp_path / "runs").rglob("manifest.json")
        ]
        assert sorted(digests) == sorted({store.scoped(who).scope_digest for who in people})


class TestADeclarationTheRunCuts:
    """Dogfood #5 ran a fan-out serially at five seconds a call with `concurrent_items=8`
    declared, twice, and read it as the model being slow (`DF5-D26`)."""

    def _pipeline(self):
        return Pipeline(
            [
                LLMNode(
                    lambda inputs, ctx: f"summarise {inputs['docs']}",
                    output_schema=Answer,
                    node_id="read",
                    over="docs",
                    concurrent_items=8,
                    successors=[],
                )
            ],
            budget=UNBOUNDED,
        )

    def _client(self):
        return FakeModelClient(
            answer=lambda request: fake_response(content=json.dumps({"text": "x"}))
        )

    def _warnings(self, tmp_path, cassette=None, **kwargs):
        envelope = RunEnvelope(run_dir=tmp_path, **({"cassette": cassette} if cassette else {}))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self._pipeline().run(
                {"docs": ["a", "b"]}, envelope=envelope, model=self._client(), **kwargs
            )
        return [str(w.message) for w in caught if "in flight" in str(w.message)]

    def test_the_run_says_which_node_it_cut_and_by_how_much(self, tmp_path):
        said = self._warnings(tmp_path)

        assert len(said) == 1
        assert "permits 1 call(s) in flight and read declares 8" in said[0]
        assert "Pipeline.run(concurrency=8)" in said[0]

    def test_a_run_with_room_for_the_declaration_says_nothing(self, tmp_path):
        assert self._warnings(tmp_path, concurrency=8) == []

    def test_a_run_permitting_more_than_the_node_asked_for_says_nothing(self, tmp_path):
        assert self._warnings(tmp_path, concurrency=16) == []

    def test_a_replay_is_silent_because_nothing_waits_on_a_backend(self, tmp_path):
        self._pipeline().run(
            {"docs": ["a", "b"]},
            envelope=RunEnvelope(
                run_dir=tmp_path / "rec", cassette=Cassette.record(tmp_path / "c.jsonl")
            ),
            model=self._client(),
        )

        assert (
            self._warnings(tmp_path / "rep", cassette=Cassette.replay(tmp_path / "c.jsonl")) == []
        )
