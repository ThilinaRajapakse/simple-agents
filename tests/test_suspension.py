"""Stopping a run and starting it again.

The checkpoint tests come first: the walk's state survives being written down and read back,
and a walk re-entered from a restored frame runs the nodes that had not run and none of the
ones that had. Nothing in this file makes a model call.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from simple_agents import (
    Prompt,
    Budget,
    CallerFacingError,
    Deterministic,
    Join,
    LLMNode,
    Maybe,
    NodeFailure,
    Pipeline,
    AgentNode,
    Cassette,
    FakeModelClient,
    RunEnvelope,
    RunSuspended,
    runs,
    SideEffectClass,
    Suspend,
    ToolCallRequest,
    ToolRegistry,
    Unknown,
    fake_response,
    tool,
)
from simple_agents.builtins import consult
from simple_agents.budget import Spend
from simple_agents.context import RunContext
from simple_agents.records.manifest import Manifest
from simple_agents.nodes import FanOutResult, ItemOutcome
from simple_agents.pipeline.edges import _EdgeState, _Frame
from simple_agents.records.suspension import ValueCodec
from simple_agents.records.trajectory import TrajectoryWriter, utc_now

from pydantic import BaseModel, Field

from conftest import run_path, RUN_ID


def _nodes(trajectory: Path) -> list[dict]:
    records = [json.loads(line) for line in trajectory.read_text().splitlines() if line.strip()]
    return [r for r in records if r["record_type"] == "node_execution"]


def _budget() -> Budget:
    return Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def _tag(name: str, **edges) -> Deterministic:
    """A node that appends its own name to a list, so the path taken is the output."""

    def run(inputs, ctx):
        seen = inputs if isinstance(inputs, list) else []
        return [*seen, name]

    return Deterministic(run, node_id=name, **edges)


def _run_context(tmp_path: Path, budget: Budget) -> RunContext:
    """A run context outside `Pipeline.run`, for driving the walk directly."""
    root = tmp_path / "second_process"
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(
        run_id=RUN_ID,
        started_at=utc_now(),
        seed=41,
        budget=budget.to_record(),
        library_version="test",
        trajectory_path=str(root / "trajectory.jsonl"),
        workspace_path=str(workspace),
    )
    return RunContext(
        run_id=RUN_ID,
        writer=TrajectoryWriter(root / "trajectory.jsonl"),
        budget=budget,
        workspace=workspace,
        seed=41,
        manifest=manifest,
    )


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def look_up(query: str) -> str:
    """Search the notes. Returns what was found."""
    return "a result"


class Notes(BaseModel):
    text: str
    # `Maybe[int] | None` is a union around a union, and the outer one drops the description
    # `Maybe` carries, so the absence encoding is spelled out here instead.
    found: Maybe[int] | None = Field(
        default=None,
        description='How many were found, or {"type": "unknown", "reason": "..."} where the '
        "notes do not say.",
    )


class TestValueCodec:
    """A value crossing a suspend point is rebuilt from the schema its node declared."""

    def _codec(self, schemas: dict[str, object], edges: dict | None = None) -> ValueCodec:
        edges = edges or {}
        return ValueCodec(
            schema_of=lambda node_id: schemas.get(node_id),
            in_edges=lambda node_id: tuple(edges.get(node_id, ())),
        )

    def test_a_model_comes_back_as_the_model_and_not_a_dict(self):
        codec = self._codec({"hunt": Notes})
        payload = codec.encode(Notes(text="Leeds", found=3), source="hunt")
        back = codec.decode(payload, source="hunt")
        assert isinstance(back, Notes)
        assert back.text == "Leeds"
        assert back.found == 3

    def test_the_type_is_not_written_to_the_file(self):
        """A rename of the class has to be invisible, so the payload names no type."""
        codec = self._codec({"hunt": Notes})
        payload = codec.encode(Notes(text="Leeds"), source="hunt")
        assert "Notes" not in json.dumps(payload)

    def test_a_reported_absence_stays_an_unknown(self):
        codec = self._codec({"hunt": Notes})
        back = codec.decode(
            codec.encode(Unknown(reason="not stated"), source="hunt"), source="hunt"
        )
        assert isinstance(back, Unknown)
        assert back.reason == "not stated"

    def test_an_unknown_inside_a_model_survives(self):
        codec = self._codec({"hunt": Notes})
        back = codec.decode(
            codec.encode(Notes(text="x", found=Unknown(reason="absent")), source="hunt"),
            source="hunt",
        )
        assert isinstance(back.found, Unknown)
        assert back.found.reason == "absent"

    def test_plain_data_needs_no_schema(self):
        codec = self._codec({})
        payload = codec.encode({"a": [1, 2.5, True, None, "x"]}, source="load")
        assert codec.decode(payload, source="load") == {"a": [1, 2.5, True, None, "x"]}

    def test_a_join_rebuilds_each_edge_against_its_own_source(self):
        codec = self._codec({"hunt": Notes, "verify": None})
        value = Join(
            {"hunt": Notes(text="Leeds"), "verify": Unknown(reason="skipped")},
            node_id="report",
            absent=frozenset({"verify"}),
        )
        back = codec.decode(codec.encode(value, source="report"), source="report")
        assert isinstance(back, Join)
        assert isinstance(back["hunt"], Notes)
        assert back.absent.keys() == {"verify"}
        assert back.fired == ("hunt",)

    def test_a_node_failure_rebuilds_the_inputs_the_failed_node_had(self):
        codec = self._codec({"load": Notes}, edges={"hunt": ("load",)})
        value = NodeFailure(
            node_id="hunt",
            inputs=Notes(text="corpus"),
            error={
                "class": "caller_facing",
                "type": "ValueError",
                "message": "boom",
                "retryable": False,
            },
            attempts=2,
        )
        back = codec.decode(codec.encode(value, source="hunt"), source="hunt")
        assert isinstance(back, NodeFailure)
        assert isinstance(back.inputs, Notes)
        assert back.attempts == 2

    def test_a_fan_out_keeps_its_failures_beside_its_values(self):
        codec = self._codec({"summarise": Notes})
        value = FanOutResult(
            outcomes=(
                ItemOutcome(index=0, item="a", value=Notes(text="one")),
                ItemOutcome(index=1, item="b", error={"message": "no"}),
            )
        )
        back = codec.decode(codec.encode(value, source="summarise"), source="summarise")
        assert len(back) == 2
        assert isinstance(back.outcomes[0].value, Notes)
        assert back.outcomes[1].error == {"message": "no"}
        assert [o.item for o in back] == ["a", "b"]

    def test_it_refuses_a_value_no_schema_describes(self):
        class Bespoke:
            pass

        codec = self._codec({})
        with pytest.raises(CallerFacingError) as caught:
            codec.encode(Bespoke(), source="load")
        assert "'load'" in str(caught.value)
        assert "Bespoke" in str(caught.value)
        assert "output_schema=" in str(caught.value)

    def test_it_refuses_a_value_the_declared_schema_does_not_describe(self):
        class Other(BaseModel):
            n: int

        codec = self._codec({"hunt": Notes})
        with pytest.raises(CallerFacingError) as caught:
            codec.encode(Other(n=1), source="hunt")
        assert "'hunt'" in str(caught.value)
        assert "Notes" in str(caught.value)

    def test_it_refuses_a_payload_tagged_by_a_version_it_cannot_read(self):
        codec = self._codec({})
        with pytest.raises(CallerFacingError) as caught:
            codec.decode({"kind": "sealed"}, source=None)
        assert "different version" in str(caught.value)


class TestDeterministicOutputSchema:
    def test_it_validates_what_the_function_returned(self, envelope):
        pipeline = Pipeline(
            [Deterministic(lambda i, c: {"text": "Leeds"}, node_id="load", output_schema=Notes)],
            budget=_budget(),
        )
        result = pipeline.run(None, envelope=envelope, run_id=RUN_ID)
        assert isinstance(result.output, Notes)

    def test_it_refuses_where_the_function_returned_something_else(self, envelope):
        pipeline = Pipeline(
            [Deterministic(lambda i, c: {"nope": 1}, node_id="load", output_schema=Notes)],
            budget=_budget(),
        )
        with pytest.raises(CallerFacingError) as caught:
            pipeline.run(None, envelope=envelope, run_id=RUN_ID)
        assert "'load'" in str(caught.value)
        assert "Notes" in str(caught.value)


class TestNodeBoundarySuspension:
    """A run stops before a node, writes its state, and continues in a fresh call."""

    def _pipeline(self, **on_b) -> Pipeline:
        return Pipeline(
            [_tag("a"), Deterministic(lambda i, c: [*i, "b"], node_id="b", **on_b), _tag("c")],
            budget=_budget(),
        )

    def test_a_declared_stop_raises_rather_than_returning_a_result(self, envelope):
        with pytest.raises(RunSuspended) as caught:
            self._pipeline(suspend_before=True).run([], envelope=envelope, run_id=RUN_ID)
        assert caught.value.run_id == RUN_ID
        assert caught.value.node_id == "b"
        assert "'b'" in caught.value.waiting_for

    def test_it_writes_its_state_beside_the_manifest(self, envelope, tmp_path):
        with pytest.raises(RunSuspended):
            self._pipeline(suspend_before=True).run([], envelope=envelope, run_id=RUN_ID)
        state = json.loads(run_path(tmp_path, RUN_ID, "suspension.json").read_text())
        assert state["format_version"] == "0.5"
        assert [stop["node_id"] for stop in state["stops"]] == ["b"]
        assert state["frames"][0]["in_progress"] == ["b"]

    def test_the_manifest_says_the_run_suspended(self, envelope, manifest_path):
        with pytest.raises(RunSuspended):
            self._pipeline(suspend_before=True).run([], envelope=envelope, run_id=RUN_ID)
        manifest = json.loads(manifest_path.read_text())
        assert manifest["outcome"] == "suspended"
        assert manifest["suspensions"][0]["node_id"] == "b"
        assert manifest["suspensions"][0]["resumed_at"] is None

    def test_only_the_nodes_before_the_stop_have_run(self, envelope, trajectory):
        with pytest.raises(RunSuspended):
            self._pipeline(suspend_before=True).run([], envelope=envelope, run_id=RUN_ID)
        assert [r["node_id"] for r in _nodes(trajectory)] == ["a"]

    def test_a_resume_finishes_the_run(self, envelope):
        pipeline = self._pipeline(suspend_before=True)
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        result = pipeline.resume(RUN_ID, envelope=envelope)
        assert result.output == ["a", "b", "c"]
        assert result.outcome == "completed"

    def test_a_resumed_run_is_still_the_kind_of_run_it_was(self, envelope, tmp_path):
        """A labelling pass that stopped for a person is a labelling pass when it continues.

        `Manifest.restore` rebuilt the manifest without `role`, so it took the dataclass
        default and every suspended labelling run came back as the agent's, which is the one
        thing the role exists to prevent.
        """
        pipeline = self._pipeline(suspend_before=True)
        labelling = envelope.with_role("labelling")
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=labelling, run_id=RUN_ID)
        assert (
            json.loads(run_path(tmp_path, RUN_ID, "manifest.json").read_text())["role"]
            == "labelling"
        )

        pipeline.resume(RUN_ID, envelope=labelling)

        assert (
            json.loads(run_path(tmp_path, RUN_ID, "manifest.json").read_text())["role"]
            == "labelling"
        )
        assert [r.run_id for r in runs(envelope.run_dir, role="labelling")] == [RUN_ID]
        assert runs(envelope.run_dir, role="agent") == []

    def test_the_run_keeps_its_own_role_when_the_resume_envelope_disagrees(
        self, envelope, tmp_path
    ):
        """The manifest is the run's record, and a resume continues one run rather than
        starting a second, so one envelope can resume whatever it finds."""
        pipeline = self._pipeline(suspend_before=True)
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope.with_role("labelling"), run_id=RUN_ID)

        pipeline.resume(RUN_ID, envelope=envelope)

        assert (
            json.loads(run_path(tmp_path, RUN_ID, "manifest.json").read_text())["role"]
            == "labelling"
        )

    def test_a_manifest_written_before_the_role_existed_resumes_as_the_agent(
        self, envelope, manifest_path
    ):
        pipeline = self._pipeline(suspend_before=True)
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        aged = json.loads(manifest_path.read_text())
        del aged["role"]
        manifest_path.write_text(json.dumps(aged))

        pipeline.resume(RUN_ID, envelope=envelope)

        assert json.loads(manifest_path.read_text())["role"] == "agent"

    def test_the_resumed_run_keeps_one_trajectory_and_one_manifest(
        self, envelope, trajectory, manifest_path
    ):
        pipeline = self._pipeline(suspend_before=True)
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        pipeline.resume(RUN_ID, envelope=envelope)

        assert [r["node_id"] for r in _nodes(trajectory)] == ["a", "b", "c"]
        manifest = json.loads(manifest_path.read_text())
        assert manifest["outcome"] == "completed"
        assert manifest["counts"]["node_execution"] == 3
        assert manifest["suspensions"][0]["resumed_at"] is not None

    def test_the_state_file_is_gone_once_the_run_has_moved_past_it(self, envelope, tmp_path):
        pipeline = self._pipeline(suspend_before=True)
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        pipeline.resume(RUN_ID, envelope=envelope)
        assert not run_path(tmp_path, RUN_ID, "suspension.json").exists()
        assert not (tmp_path / RUN_ID / "suspension.claimed.json").exists()

    def test_a_caller_stop_parks_the_run_at_the_next_node(self, envelope):
        pipeline = self._pipeline()
        stop = {"now": False}

        def watch(event):
            if event.phase == "completed" and event.node_id == "a":
                stop["now"] = True

        with pytest.raises(RunSuspended) as caught:
            pipeline.run(
                [],
                envelope=envelope,
                run_id=RUN_ID,
                on_progress=watch,
                stop_when=lambda: stop["now"],
            )
        assert caught.value.node_id == "b"
        assert pipeline.resume(RUN_ID, envelope=envelope).output == ["a", "b", "c"]

    def test_a_value_in_flight_comes_back_as_its_own_type(self, envelope):
        """The failure this whole design exists to prevent: a dict where an Answer was."""
        seen: list[object] = []
        pipeline = Pipeline(
            [
                Deterministic(lambda i, c: {"text": "Leeds"}, node_id="load", output_schema=Notes),
                Deterministic(
                    lambda i, c: seen.append(i) or "done", node_id="use", suspend_before=True
                ),
            ],
            budget=_budget(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run(None, envelope=envelope, run_id=RUN_ID)
        pipeline.resume(RUN_ID, envelope=envelope)
        assert isinstance(seen[0], Notes)
        assert seen[0].text == "Leeds"

    def test_it_refuses_a_resume_of_a_run_that_is_not_suspended(self, envelope):
        pipeline = self._pipeline()
        pipeline.run([], envelope=envelope, run_id=RUN_ID)
        with pytest.raises(CallerFacingError) as caught:
            pipeline.resume(RUN_ID, envelope=envelope)
        assert "no suspended run" in str(caught.value)

    def test_it_refuses_a_second_worker_taking_a_claimed_run(self, envelope):
        pipeline = self._pipeline(suspend_before=True)
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        pipeline.resume(RUN_ID, envelope=envelope)
        with pytest.raises(CallerFacingError):
            pipeline.resume(RUN_ID, envelope=envelope)

    def test_it_refuses_a_state_file_written_by_another_format(self, envelope, tmp_path):
        pipeline = self._pipeline(suspend_before=True)
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        path = run_path(tmp_path, RUN_ID, "suspension.json")
        state = json.loads(path.read_text())
        state["format_version"] = "9.9"
        path.write_text(json.dumps(state))
        with pytest.raises(CallerFacingError) as caught:
            pipeline.resume(RUN_ID, envelope=envelope)
        assert "9.9" in str(caught.value)


class TestSuspensionInsideANestedPipeline:
    def _outer(self) -> Pipeline:
        inner = Pipeline(
            [
                _tag("hunt"),
                Deterministic(lambda i, c: [*i, "verify"], node_id="verify", suspend_before=True),
            ],
            budget=_budget(),
            node_id="research",
        )
        return Pipeline([inner, _tag("write")], budget=_budget())

    def test_it_carries_a_frame_for_each_level(self, envelope, tmp_path):
        with pytest.raises(RunSuspended):
            self._outer().run([], envelope=envelope, run_id=RUN_ID)
        state = json.loads(run_path(tmp_path, RUN_ID, "suspension.json").read_text())
        # One frame per level, and the level below hangs off the node that stopped inside it,
        # so a level where two arms stopped branches into two rather than flattening.
        outer = state["frames"][0]
        assert list(outer["in_progress"]) == ["research"]
        assert len(outer["below"]["research"]) == 1
        assert outer["below"]["research"][0]["in_progress"] == ["verify"]

    def test_a_resume_continues_inside_the_nested_pipeline(self, envelope, trajectory):
        outer = self._outer()
        with pytest.raises(RunSuspended):
            outer.run([], envelope=envelope, run_id=RUN_ID)
        result = outer.resume(RUN_ID, envelope=envelope)
        assert result.output == ["hunt", "verify", "write"]
        assert [r["node_id"] for r in _nodes(trajectory)] == [
            "research.hunt",
            "research.verify",
            "write",
        ]


class TestStateSurvivesBeingWrittenDown:
    """The checkpoint: the walk's state round-trips before anything can suspend."""

    def test_an_edge_state_rebuilds_to_what_it_was(self, envelope):
        pipeline = Pipeline([_tag("a"), _tag("b"), _tag("c")], budget=_budget())
        taken: list[_Frame] = []
        original = Pipeline._new_frame

        def spy(self, run, prefix, parent_id=None):
            frame = original(self, run, prefix, parent_id)
            taken.append(frame)
            return frame

        Pipeline._new_frame = spy
        try:
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        finally:
            Pipeline._new_frame = original

        before = taken[0].edges
        after = _EdgeState.restored(
            pipeline.graph, before.snapshot(pipeline._codec()), pipeline._codec()
        )
        assert after.resolved == before.resolved
        assert after.visits == before.visits
        assert after.done == before.done

    def test_a_frame_rebuilds_to_what_it_was(self, envelope):
        pipeline = Pipeline([_tag("a"), _tag("b")], budget=_budget())
        taken: list[_Frame] = []
        original = Pipeline._new_frame

        def spy(self, run, prefix, parent_id=None):
            frame = original(self, run, prefix, parent_id)
            taken.append(frame)
            return frame

        Pipeline._new_frame = spy
        try:
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        finally:
            Pipeline._new_frame = original

        after = _Frame.restored(
            pipeline.graph, taken[0].snapshot(pipeline._codec()), pipeline._codec()
        )
        assert after.produced == taken[0].produced
        assert after.opened == taken[0].opened
        assert after.prefix == taken[0].prefix
        assert after.in_progress == []

    def test_the_run_counters_rebuild_to_what_they_were(self, tmp_path):
        run = _run_context(tmp_path, _budget())
        run.next_sequence()
        run.next_sequence()
        run.next_model_call("hunt")
        run.next_tool_call("hunt")
        run.note_input_size("hunt", tokens=900, chars=3600, call_index=0)
        state = run.counters()

        fresh = _run_context(tmp_path, _budget())
        fresh.restore_counters(state)
        assert fresh.next_sequence() == 3
        assert fresh.next_model_call("hunt") == 1
        assert fresh.next_tool_call("hunt") == 1
        assert fresh.counters()["last_input"]["hunt"]["tokens"] == 900


class TestReEntry:
    """A walk handed a restored frame continues rather than starting again."""

    def _stopped_at(self, envelope, pipeline: Pipeline, node_id: str) -> dict:
        """Run until `node_id` starts, and return the frame as it was at that moment."""
        taken: list[_Frame] = []
        snapshots: list[dict] = []
        original = Pipeline._new_frame

        def spy(self, run, prefix, parent_id=None):
            frame = original(self, run, prefix, parent_id)
            taken.append(frame)
            return frame

        def watch(event):
            if event.phase == "started" and event.node_id == node_id:
                snapshot = taken[0].snapshot(pipeline._codec())
                snapshot["in_progress"] = node_id
                snapshots.append(snapshot)

        Pipeline._new_frame = spy
        try:
            pipeline.run([], envelope=envelope, run_id=RUN_ID, on_progress=watch)
        finally:
            Pipeline._new_frame = original
        return snapshots[0]

    def test_it_runs_the_node_it_stopped_at_and_the_ones_after(self, envelope, tmp_path):
        pipeline = Pipeline([_tag("a"), _tag("b"), _tag("c")], budget=_budget())
        snapshot = self._stopped_at(envelope, pipeline, "c")

        run = _run_context(tmp_path, _budget())
        ran: list[str] = []
        output = pipeline._walk(
            [],
            run,
            None,
            frame=_Frame.restored(pipeline.graph, snapshot, pipeline._codec()),
            on_progress=lambda event: (
                ran.append(event.node_id) if event.phase == "completed" else None
            ),
        )
        assert ran == ["c"]
        assert output == ["a", "b", "c"]

    def test_it_does_not_count_the_resumed_node_as_a_second_iteration(self, envelope, tmp_path):
        pipeline = Pipeline([_tag("a"), _tag("b")], budget=_budget())
        snapshot = self._stopped_at(envelope, pipeline, "b")
        assert snapshot["edges"]["visits"]["b"] == 1

        run = _run_context(tmp_path, _budget())
        frame = _Frame.restored(pipeline.graph, snapshot, pipeline._codec())
        pipeline._walk([], run, None, frame=frame)
        assert frame.edges.visits["b"] == 1

    def test_a_restored_frame_does_not_charge_the_resumed_node_again(self, envelope, tmp_path):
        pipeline = Pipeline([_tag("a"), _tag("b")], budget=_budget())
        snapshot = self._stopped_at(envelope, pipeline, "b")

        # One step left, and the resumed node must not spend it before running.
        run = _run_context(
            tmp_path, Budget(max_steps=0, max_tokens=None, max_cost=None, max_wall_clock_ms=None)
        )
        run.spend = Spend(steps=0)
        output = pipeline._walk(
            [], run, None, frame=_Frame.restored(pipeline.graph, snapshot, pipeline._codec())
        )
        assert output == ["a", "b"]


class TestSuspensionInsideAnAgentLoop:
    """The case consultation actually has: a stop four turns into a search."""

    def _pipeline(self, ask, budget=None) -> Pipeline:
        registry = ToolRegistry()
        registry.add(look_up)
        registry.add(consult(ask, answered_by="end_user"))
        return Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: Prompt.user(
                        "Find it. Tools: {describe_tools}", describe_tools=ctx.describe_tools()
                    ),
                    tools=registry,
                    output_schema=Notes,
                    budget=budget
                    or Budget(max_steps=8, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
                    node_id="hunt",
                )
            ],
            budget=_budget(),
        )

    def _client(self) -> FakeModelClient:
        """Three turns: a search, a consultation, then the answer."""
        return FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c1", name="look_up", arguments={"query": "trousers"})
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c2", name="consult", arguments={"question": "slim or straight?"}
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c3", name="finish", arguments={"text": "slim, 32in"})
                    ]
                ),
            ]
        )

    def test_it_stops_where_the_channel_could_not_answer(self, envelope):
        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question, options=options)

        with pytest.raises(RunSuspended) as caught:
            self._pipeline(unavailable).run(
                {}, envelope=envelope, model=self._client(), run_id=RUN_ID
            )
        assert caught.value.node_id == "hunt"
        assert caught.value.waiting_for == "slim or straight?"

    def test_it_captures_the_conversation_so_far(self, envelope, tmp_path):
        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        with pytest.raises(RunSuspended):
            self._pipeline(unavailable).run(
                {}, envelope=envelope, model=self._client(), run_id=RUN_ID
            )
        # The state lives on the frame of the pipeline the node sits in, keyed by node.
        state = json.loads(run_path(tmp_path, RUN_ID, "suspension.json").read_text())
        held = state["frames"][-1]["node_state"]
        node = held[next(iter(held))]
        assert node["step"] == 2
        assert node["calls"] == 2
        assert node["pending"]["name"] == "consult"
        assert [c["name"] for c in node["made"]] == ["look_up"]
        assert any(m.get("role") == "tool" for m in node["messages"])

    def test_a_resume_answers_the_question_and_finishes(self, envelope):
        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        pipeline = self._pipeline(unavailable)
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, model=self._client(), run_id=RUN_ID)

        # The resumed process makes only the calls that had not been made.
        rest = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c3", name="finish", arguments={"text": "slim, 32in"})
                    ]
                ),
            ]
        )
        result = pipeline.resume(RUN_ID, envelope=envelope, model=rest, answer="slim")
        assert isinstance(result.output, Notes)
        assert result.output.text == "slim, 32in"

    def test_the_resumed_loop_sees_the_answer_and_what_it_read_before(self, envelope):
        seen: dict = {}

        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        def remembers(answer, ctx):
            seen["calls"] = [(c.name, c.result) for c in ctx.tool_calls]
            return None

        registry = ToolRegistry()
        registry.add(look_up)
        registry.add(consult(unavailable, answered_by="end_user"))
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: Prompt.user("Find it."),
                    tools=registry,
                    output_schema=Notes,
                    node_id="hunt",
                    finish_check=remembers,
                    budget=Budget(
                        max_steps=8, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=_budget(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, model=self._client(), run_id=RUN_ID)
        rest = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c3", name="finish", arguments={"text": "slim"})]
                ),
            ]
        )
        pipeline.resume(RUN_ID, envelope=envelope, model=rest, answer="slim")
        assert seen["calls"] == [("look_up", "a result"), ("consult", "slim")]

    def test_the_suspended_execution_is_recorded_before_the_process_ends(
        self, envelope, trajectory
    ):
        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        with pytest.raises(RunSuspended):
            self._pipeline(unavailable).run(
                {}, envelope=envelope, model=self._client(), run_id=RUN_ID
            )
        records = _nodes(trajectory)
        assert [r["termination"] for r in records] == ["suspended"]
        assert records[0]["outputs"] is None

    def test_no_model_call_is_left_without_the_node_record_it_hangs_from(
        self, envelope, trajectory
    ):
        """A run that is never resumed still has to leave a readable tree."""

        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        with pytest.raises(RunSuspended):
            self._pipeline(unavailable).run(
                {}, envelope=envelope, model=self._client(), run_id=RUN_ID
            )
        records = [json.loads(line) for line in trajectory.read_text().splitlines() if line.strip()]
        written = {r["record_id"] for r in records}
        parents = {r["parent_id"] for r in records if r["parent_id"] is not None}
        assert parents <= written

    def test_the_wait_is_charged_to_nothing(self, envelope):
        """A node with a wall-clock bound must not trip because a person took their time."""

        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        pipeline = self._pipeline(
            unavailable,
            budget=Budget(max_steps=8, max_tokens=None, max_cost=None, max_wall_clock_ms=60_000),
        )
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, model=self._client(), run_id=RUN_ID)

        import time as _time

        _time.sleep(0.05)
        rest = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c3", name="finish", arguments={"text": "slim"})]
                ),
            ]
        )
        result = pipeline.resume(RUN_ID, envelope=envelope, model=rest, answer="slim")
        assert result.outcome == "completed"

    def test_it_refuses_to_suspend_where_a_tool_result_cannot_cross(self, envelope):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def bespoke(query: str) -> object:
            """Returns something no schema describes."""
            return object()

        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        registry = ToolRegistry()
        registry.add(bespoke)
        registry.add(consult(unavailable, answered_by="end_user"))
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: Prompt.user("Find it."),
                    tools=registry,
                    output_schema=Notes,
                    node_id="hunt",
                    budget=Budget(
                        max_steps=8, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=_budget(),
        )
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c1", name="bespoke", arguments={"query": "x"})]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c2", name="consult", arguments={"question": "which?"})
                    ]
                ),
            ]
        )
        with pytest.raises(CallerFacingError) as caught:
            pipeline.run({}, envelope=envelope, model=client, run_id=RUN_ID)
        assert "'bespoke'" in str(caught.value)
        assert "plain data" in str(caught.value)


class TestConsultationAcrossProcesses:
    """A question asked in one process and answered in another is two records."""

    def _pipeline(self, ask) -> Pipeline:
        registry = ToolRegistry()
        registry.add(consult(ask, answered_by="end_user"))
        return Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: Prompt.user("Ask if unsure."),
                    tools=registry,
                    output_schema=Notes,
                    node_id="hunt",
                    budget=Budget(
                        max_steps=8, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=_budget(),
        )

    def _client(self) -> FakeModelClient:
        return FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c1", name="consult", arguments={"question": "slim or straight?"}
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments={"text": "slim"})]
                ),
            ]
        )

    def _consultations(self, trajectory: Path) -> list[dict]:
        records = [json.loads(line) for line in trajectory.read_text().splitlines() if line.strip()]
        return [r for r in records if r["record_type"] == "consultation"]

    def test_a_run_never_resumed_still_says_what_was_asked(self, envelope, trajectory):
        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        with pytest.raises(RunSuspended):
            self._pipeline(unavailable).run(
                {}, envelope=envelope, model=self._client(), run_id=RUN_ID
            )
        asked = self._consultations(trajectory)
        assert len(asked) == 1
        assert asked[0]["resolution"] == "pending"
        assert asked[0]["blocking"] is False
        assert asked[0]["response"] is None
        assert asked[0]["ended_at"] is None
        assert asked[0]["prompt"] == "slim or straight?"

    def test_the_answer_is_a_second_record_naming_the_first(self, envelope, trajectory):
        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        pipeline = self._pipeline(unavailable)
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, model=self._client(), run_id=RUN_ID)
        rest = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments={"text": "slim"})]
                ),
            ]
        )
        pipeline.resume(RUN_ID, envelope=envelope, model=rest, answer="slim")

        asked, answered = self._consultations(trajectory)
        assert answered["answers"] == asked["record_id"]
        assert answered["resolution"] == "answered"
        assert answered["response"] == "slim"
        assert answered["ended_at"] is not None
        # Counting consultations is counting the records that answer nothing.
        assert len([r for r in (asked, answered) if r["answers"] is None]) == 1

    def test_the_resumed_execution_names_the_one_it_continues(self, envelope, trajectory):
        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        pipeline = self._pipeline(unavailable)
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, model=self._client(), run_id=RUN_ID)
        rest = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments={"text": "slim"})]
                ),
            ]
        )
        pipeline.resume(RUN_ID, envelope=envelope, model=rest, answer="slim")

        stopped, continued = _nodes(trajectory)
        assert stopped["termination"] == "suspended"
        assert stopped["resumed_from"] is None
        assert continued["termination"] == "finish"
        assert continued["resumed_from"] == stopped["record_id"]

    def test_a_replay_of_a_suspended_run_never_suspends(self, tmp_path):
        """What keeps an evaluation over a consulting agent possible."""
        asked: list[str] = []

        def unavailable(question, options, about=None):
            asked.append(question)
            raise Suspend(waiting_for=question)

        cassette_path = tmp_path / "consult.jsonl"
        recording = RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path))
        pipeline = self._pipeline(unavailable)
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=recording, model=self._client(), run_id=RUN_ID, seed=41)
        rest = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments={"text": "slim"})]
                ),
            ]
        )
        pipeline.resume(RUN_ID, envelope=recording, model=rest, answer="slim")
        assert asked == ["slim or straight?"]

        # The same pipeline, replayed. The channel is never reached, so nothing suspends, and
        # `asked` stays at one entry. A second pipeline would be a second tool: what a channel
        # closed over is in its version, and `asked` has grown since the first was built.
        replaying = RunEnvelope(run_dir=tmp_path / "play", cassette=Cassette.replay(cassette_path))
        result = pipeline.run(
            {},
            envelope=replaying,
            model=FakeModelClient(responses=[]),
            run_id=RUN_ID,
            seed=41,
        )
        assert result.output.text == "slim"
        assert asked == ["slim or straight?"]

    def test_the_filed_answer_is_keyed_under_the_node_and_not_the_tool(self, tmp_path):
        """`Cassette.nearest` diagnoses a miss by node_id, so the entry names the node."""

        def unavailable(question, options, about=None):
            raise Suspend(waiting_for=question)

        cassette_path = tmp_path / "consult.jsonl"
        recording = RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path))
        pipeline = self._pipeline(unavailable)
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=recording, model=self._client(), run_id=RUN_ID, seed=41)
        rest = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments={"text": "slim"})]
                ),
            ]
        )
        pipeline.resume(RUN_ID, envelope=recording, model=rest, answer="slim")

        entries = [json.loads(line) for line in cassette_path.read_text().splitlines() if line]
        consults = [
            e
            for e in entries
            if e["kind"] == "tool_call" and e["request"].get("tool_name") == "consult"
        ]
        assert consults and all(e["node_id"] == "hunt" for e in consults)


class TestVerifyingTheGraphOnResume:
    """A resumed run checks the pipeline it is handed against what the run recorded."""

    def _suspended(self, envelope):
        pipeline = Pipeline([_tag("a"), _tag("b", suspend_before=True)], budget=_budget())
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        return pipeline

    def test_the_same_pipeline_resumes(self, envelope):
        self._suspended(envelope)
        same = Pipeline([_tag("a"), _tag("b", suspend_before=True)], budget=_budget())
        assert same.resume(RUN_ID, envelope=envelope).output == ["a", "b"]

    def test_it_refuses_a_pipeline_with_a_different_node(self, envelope):
        self._suspended(envelope)
        different = Pipeline([_tag("a"), _tag("elsewhere")], budget=_budget())
        with pytest.raises(CallerFacingError) as caught:
            different.resume(RUN_ID, envelope=envelope)
        assert "different shape" in str(caught.value)
        assert "elsewhere" in str(caught.value)

    def test_it_refuses_a_pipeline_whose_edges_moved(self, envelope):
        """The same nodes, wired differently. The node ids match, so only the edges say so."""
        pipeline = Pipeline(
            [
                _tag("a", successors=["b", "d"], route=lambda o, c: "b"),
                _tag("b", successors=["c"], suspend_before=True),
                _tag("c", successors=[]),
                _tag("d", successors=["c"]),
            ],
            budget=_budget(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)

        rewired = Pipeline(
            [
                _tag("a", successors=["b", "d"], route=lambda o, c: "b"),
                _tag("b", successors=["d"], suspend_before=True),
                _tag("c", successors=[]),
                _tag("d", successors=["c"]),
            ],
            budget=_budget(),
        )
        with pytest.raises(CallerFacingError) as caught:
            rewired.resume(RUN_ID, envelope=envelope)
        assert "different shape" in str(caught.value)
        assert "'b' differs in: successors" in str(caught.value)

    def test_it_refuses_a_pipeline_whose_sub_pipeline_was_rewired(self, envelope):
        """A container's edges are on no leaf entry, so the fingerprint used to miss them.

        The stored state is keyed on node ids, and a sub-pipeline that gained an error edge is
        a different graph however unchanged its children are.
        """

        def build(**inner_edges):
            inner = Pipeline(
                [_tag("hunt", successors=[])],
                budget=_budget(),
                node_id="research",
                **inner_edges,
            )
            return Pipeline(
                [
                    inner,
                    _tag("write", successors=["rescue"], suspend_before=True),
                    _tag("rescue", successors=[]),
                ],
                budget=_budget(),
            )

        with pytest.raises(RunSuspended):
            build().run([], envelope=envelope, run_id=RUN_ID)

        with pytest.raises(CallerFacingError) as caught:
            build(on_error="rescue").resume(RUN_ID, envelope=envelope)

        assert "different shape" in str(caught.value)
        assert "'research' differs in: on_error" in str(caught.value)

    def test_a_shape_change_cannot_be_waived(self, envelope):
        self._suspended(envelope)
        different = Pipeline([_tag("a"), _tag("elsewhere")], budget=_budget())
        with pytest.raises(CallerFacingError) as caught:
            different.resume(
                RUN_ID, envelope=envelope, accept_changed=["prompts.b", "model", "everything"]
            )
        assert "cannot be waived" in str(caught.value)

    def test_it_refuses_a_changed_output_schema(self, envelope):
        class Other(BaseModel):
            n: int

        pipeline = Pipeline(
            [
                Deterministic(lambda i, c: {"text": "x"}, node_id="load", output_schema=Notes),
                _tag("use", suspend_before=True),
            ],
            budget=_budget(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run(None, envelope=envelope, run_id=RUN_ID)
        changed = Pipeline(
            [
                Deterministic(lambda i, c: {"n": 1}, node_id="load", output_schema=Other),
                _tag("use", suspend_before=True),
            ],
            budget=_budget(),
        )
        with pytest.raises(CallerFacingError) as caught:
            changed.resume(RUN_ID, envelope=envelope)
        assert "'load'" in str(caught.value)
        assert "schema" in str(caught.value)

    def test_it_refuses_a_changed_prompt_and_names_the_waiver(self, envelope):
        first = Pipeline(
            [
                LLMNode(
                    lambda i, c: Prompt.user("ask one way"), output_schema=Notes, node_id="draft"
                ),
                _tag("use", suspend_before=True),
            ],
            budget=_budget(),
        )
        client = FakeModelClient(responses=[fake_response(content='{"text": "x"}')])
        with pytest.raises(RunSuspended):
            first.run(None, envelope=envelope, model=client, run_id=RUN_ID, seed=41)

        edited = Pipeline(
            [
                LLMNode(
                    lambda i, c: Prompt.user("ask another way"),
                    output_schema=Notes,
                    node_id="draft",
                ),
                _tag("use", suspend_before=True),
            ],
            budget=_budget(),
        )
        with pytest.raises(CallerFacingError) as caught:
            edited.resume(RUN_ID, envelope=envelope, model=client)
        assert "prompts.draft" in str(caught.value)
        assert "accept_changed" in str(caught.value)

    def test_a_named_waiver_lets_it_through_and_is_recorded(self, envelope, manifest_path):
        first = Pipeline(
            [
                LLMNode(
                    lambda i, c: Prompt.user("ask one way"), output_schema=Notes, node_id="draft"
                ),
                _tag("use", suspend_before=True),
            ],
            budget=_budget(),
        )
        client = FakeModelClient(responses=[fake_response(content='{"text": "x"}')])
        with pytest.raises(RunSuspended):
            first.run(None, envelope=envelope, model=client, run_id=RUN_ID, seed=41)

        edited = Pipeline(
            [
                LLMNode(
                    lambda i, c: Prompt.user("ask another way"),
                    output_schema=Notes,
                    node_id="draft",
                ),
                _tag("use", suspend_before=True),
            ],
            budget=_budget(),
        )
        edited.resume(RUN_ID, envelope=envelope, model=client, accept_changed=["prompts.draft"])
        assert json.loads(manifest_path.read_text())["resume_waivers"] == ["prompts.draft"]

    def test_a_prompt_edited_under_a_held_declaration_is_not_refused(self, envelope):
        """P3-20: the declaration is what identity reads, so the hash beside it cannot refuse."""

        def build(node) -> Pipeline:
            return Pipeline(
                [
                    LLMNode(node, output_schema=Notes, node_id="draft", prompt_version="v1"),
                    _tag("use", suspend_before=True),
                ],
                budget=_budget(),
            )

        client = FakeModelClient(responses=[fake_response(content='{"text": "x"}')])
        with pytest.raises(RunSuspended):
            build(lambda i, c: Prompt.user("ask one way")).run(
                None, envelope=envelope, model=client, run_id=RUN_ID, seed=41
            )

        resumed = build(lambda i, c: Prompt.user("ask another way")).resume(
            RUN_ID, envelope=envelope, model=client
        )

        assert resumed.output is not None

    def test_it_refuses_an_edited_deterministic_body_and_names_the_waiver(self, envelope):
        """Half a resumed run's trajectory came from the body the other half never ran."""

        def build(fn) -> Pipeline:
            return Pipeline(
                [Deterministic(fn, node_id="read"), _tag("use", suspend_before=True)],
                budget=_budget(),
            )

        with pytest.raises(RunSuspended):
            build(lambda i, c: ["early"]).run(None, envelope=envelope, run_id=RUN_ID, seed=41)

        with pytest.raises(CallerFacingError) as caught:
            build(lambda i, c: ["rebuilt", "store"]).resume(RUN_ID, envelope=envelope)

        assert "fn.read" in str(caught.value)
        assert "accept_changed" in str(caught.value)

    def test_a_deterministic_body_under_a_held_declaration_is_not_refused(self, envelope):
        def build(fn) -> Pipeline:
            return Pipeline(
                [Deterministic(fn, node_id="read", version="v1"), _tag("use", suspend_before=True)],
                budget=_budget(),
            )

        with pytest.raises(RunSuspended):
            build(lambda i, c: ["early"]).run(None, envelope=envelope, run_id=RUN_ID, seed=41)

        assert build(lambda i, c: ["rebuilt"]).resume(RUN_ID, envelope=envelope) is not None

    def test_it_refuses_a_changed_model_pin(self, envelope):
        pipeline = Pipeline(
            [
                LLMNode(lambda i, c: Prompt.user("ask"), output_schema=Notes, node_id="draft"),
                _tag("use", suspend_before=True),
            ],
            budget=_budget(),
        )
        first = FakeModelClient(responses=[fake_response(content='{"text": "x"}')])
        with pytest.raises(RunSuspended):
            pipeline.run(None, envelope=envelope, model=first, run_id=RUN_ID, seed=41)

        second = FakeModelClient(responses=[])
        second.model_identity = replace(second.model_identity, request_model="other/model")
        with pytest.raises(CallerFacingError) as caught:
            pipeline.resume(RUN_ID, envelope=envelope, model=second)
        assert "model" in str(caught.value)

    def test_a_refused_resume_leaves_the_run_resumable(self, envelope):
        """A refusal must not consume the suspension: the fix is to correct the pipeline."""
        self._suspended(envelope)
        different = Pipeline([_tag("a"), _tag("elsewhere")], budget=_budget())
        with pytest.raises(CallerFacingError):
            different.resume(RUN_ID, envelope=envelope)
        same = Pipeline([_tag("a"), _tag("b", suspend_before=True)], budget=_budget())
        assert same.resume(RUN_ID, envelope=envelope).output == ["a", "b"]


class TestWaitingOnAClock:
    """A run waiting for a quota to reset carries a time. The library runs no timer."""

    def _pipeline(self, when: str | None) -> Pipeline:
        parked = {"already": False}

        def park(inputs, ctx):
            """Stops once. A node that raised every time would suspend again on resume."""
            if not parked["already"]:
                parked["already"] = True
                raise Suspend(waiting_for="monthly token quota", resume_not_before=when)
            return [*inputs, "b"]

        return Pipeline([_tag("a"), Deterministic(park, node_id="b"), _tag("c")], budget=_budget())

    def _in(self, seconds: float) -> str:
        return (
            (datetime.now(timezone.utc) + timedelta(seconds=seconds))
            .isoformat()
            .replace("+00:00", "Z")
        )

    def test_the_time_travels_with_the_suspension(self, envelope, tmp_path):
        when = self._in(3600)
        with pytest.raises(RunSuspended) as caught:
            self._pipeline(when).run([], envelope=envelope, run_id=RUN_ID)
        assert caught.value.resume_not_before == when
        state = json.loads(run_path(tmp_path, RUN_ID, "suspension.json").read_text())
        assert state["stops"][0]["resume_not_before"] == when

    def test_it_refuses_a_resume_before_the_time_and_says_how_long(self, envelope):
        pipeline = self._pipeline(self._in(3600))
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        with pytest.raises(CallerFacingError) as caught:
            pipeline.resume(RUN_ID, envelope=envelope)
        assert "cannot be resumed before" in str(caught.value)
        assert "wait=True" in str(caught.value)

    def test_a_refusal_on_time_leaves_the_run_resumable(self, envelope):
        pipeline = self._pipeline(self._in(3600))
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        with pytest.raises(CallerFacingError):
            pipeline.resume(RUN_ID, envelope=envelope)
        # Still waiting, still listed, still claimable once its time comes.
        assert [s.run_id for s in Pipeline.suspensions(envelope.run_dir)] == [RUN_ID]

    def test_a_time_that_has_passed_resumes(self, envelope):
        pipeline = self._pipeline(self._in(-10))
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        assert pipeline.resume(RUN_ID, envelope=envelope).output == ["a", "b", "c"]

    def test_wait_blocks_rather_than_refusing(self, envelope):
        pipeline = self._pipeline(self._in(0.05))
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        assert pipeline.resume(RUN_ID, envelope=envelope, wait=True).output == ["a", "b", "c"]

    def test_a_run_waiting_on_a_person_carries_no_time(self, envelope):
        pipeline = self._pipeline(None)
        with pytest.raises(RunSuspended):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        state = Pipeline.suspensions(envelope.run_dir)[0]
        assert state.resume_not_before is None
        assert state.ready is True


class TestListingWhatIsWaiting:
    """What a project's own worker reads. The library runs no worker."""

    def test_it_reports_each_waiting_run_and_whether_it_is_ready(self, tmp_path):
        env = RunEnvelope(run_dir=tmp_path)

        def park(inputs, ctx):
            raise Suspend(waiting_for="a person")

        def later(inputs, ctx):
            raise Suspend(
                waiting_for="a quota",
                resume_not_before=(datetime.now(timezone.utc) + timedelta(hours=1))
                .isoformat()
                .replace("+00:00", "Z"),
            )

        for run_id, stop in (("run_now", park), ("run_later", later)):
            with pytest.raises(RunSuspended):
                Pipeline([Deterministic(stop, node_id="b")], budget=_budget()).run(
                    [], envelope=env, run_id=run_id
                )

        found = {s.run_id: s for s in Pipeline.suspensions(tmp_path)}
        assert set(found) == {"run_now", "run_later"}
        assert found["run_now"].ready is True
        assert found["run_now"].waiting_for == "a person"
        assert found["run_later"].ready is False
        assert 0 < found["run_later"].wait_seconds() <= 3600

    def test_a_directory_with_no_suspended_runs_lists_nothing(self, tmp_path):
        assert Pipeline.suspensions(tmp_path) == []


class TestSuspensionInsideAFanOut:
    """An `LLMNode` with `over=` is not atomic: a ModelClient can stop it part-way."""

    class _StopsAfter:
        """A client that answers `n` calls and then stops the run, as a quota wrapper would."""

        def __init__(self, n: int, answers: list[str]) -> None:
            self.n, self.answers, self.made = n, answers, 0

        def identity(self):
            return FakeModelClient().identity()

        def complete(self, request):
            if self.made >= self.n:
                raise Suspend(waiting_for="monthly token quota")
            self.made += 1
            return fake_response(content=self.answers.pop(0))

    def _pipeline(self) -> Pipeline:
        return Pipeline(
            [
                LLMNode(
                    lambda inputs, ctx: Prompt.user(
                        "summarise {documents}", documents=inputs["documents"]
                    ),
                    output_schema=Notes,
                    over="documents",
                    node_id="summarise",
                )
            ],
            budget=_budget(),
        )

    def _answers(self) -> list[str]:
        return [json.dumps({"text": t}) for t in ("one", "two", "three", "four")]

    def test_it_keeps_the_items_it_finished(self, envelope, tmp_path):
        stops = self._StopsAfter(2, self._answers())
        with pytest.raises(RunSuspended):
            self._pipeline().run(
                {"documents": ["a", "b", "c", "d"]},
                envelope=envelope,
                model=stops,
                run_id=RUN_ID,
                seed=41,
            )
        # The state lives on the frame of the pipeline the node sits in, keyed by node.
        state = json.loads(run_path(tmp_path, RUN_ID, "suspension.json").read_text())
        held = state["frames"][-1]["node_state"]
        node = held[next(iter(held))]
        assert node["kind"] == "fan_out"
        # The items that finished are named by index rather than by a prefix, so a fan-out
        # whose items overlapped resumes the ones that are left rather than the ones after a
        # boundary that does not exist.
        assert [done["index"] for done in node["done"]] == [0, 1]
        assert [d["index"] for d in node["done"]] == [0, 1]
        assert [d["value"]["text"] for d in node["done"]] == ["one", "two"]

    def test_a_resume_continues_at_the_next_item_and_pays_for_no_others(self, envelope):
        pipeline = self._pipeline()
        stops = self._StopsAfter(2, self._answers())
        with pytest.raises(RunSuspended):
            pipeline.run(
                {"documents": ["a", "b", "c", "d"]},
                envelope=envelope,
                model=stops,
                run_id=RUN_ID,
                seed=41,
            )
        rest = self._StopsAfter(9, [json.dumps({"text": t}) for t in ("three", "four")])
        result = pipeline.resume(RUN_ID, envelope=envelope, model=rest)
        assert rest.made == 2, "the first two items were paid for again"
        assert [o.value.text for o in result.output] == ["one", "two", "three", "four"]
        assert [o.index for o in result.output] == [0, 1, 2, 3]

    def test_a_failed_item_survives_the_stop_as_a_failure(self, envelope):
        pipeline = self._pipeline()
        stops = self._StopsAfter(2, ["not json at all", json.dumps({"text": "two"})])
        with pytest.raises(RunSuspended):
            pipeline.run(
                {"documents": ["a", "b", "c"]},
                envelope=envelope,
                model=stops,
                run_id=RUN_ID,
                seed=41,
            )
        rest = self._StopsAfter(9, [json.dumps({"text": "three"})])
        fanned = pipeline.resume(RUN_ID, envelope=envelope, model=rest).output
        assert len(fanned) == 3
        assert [o.ok for o in fanned] == [False, True, True]
        assert fanned.failures[0].index == 0

    def test_what_the_fan_out_kept_survives_a_stop_at_a_later_node(self, envelope):
        """`kept` is on the edge like any other value, so it crosses the same way."""
        pipeline = Pipeline(
            [
                Deterministic(
                    lambda inputs, ctx: {"documents": ["a", "b"], "question": inputs["q"]},
                    node_id="load",
                ),
                LLMNode(
                    lambda inputs, ctx: Prompt.user(
                        "summarise {documents}", documents=inputs["documents"]
                    ),
                    output_schema=Notes,
                    over="documents",
                    keep=["question"],
                    node_id="summarise",
                ),
                Deterministic(
                    lambda fanned, ctx: fanned.kept["question"],
                    node_id="report",
                    suspend_before=True,
                    successors=[],
                ),
            ],
            budget=_budget(),
        )
        answers = [json.dumps({"text": t}) for t in ("one", "two")]
        with pytest.raises(RunSuspended):
            pipeline.run(
                {"q": "how wide?"},
                envelope=envelope,
                model=self._StopsAfter(9, answers),
                run_id=RUN_ID,
                seed=41,
            )
        result = pipeline.resume(RUN_ID, envelope=envelope, model=FakeModelClient())
        assert result.output == "how wide?"

    def test_it_refuses_to_suspend_where_an_item_cannot_cross(self, envelope):
        class Bespoke:
            def __repr__(self):
                return "<bespoke>"

        stops = self._StopsAfter(1, self._answers())
        with pytest.raises(CallerFacingError) as caught:
            self._pipeline().run(
                {"documents": [Bespoke(), Bespoke()]},
                envelope=envelope,
                model=stops,
                run_id=RUN_ID,
                seed=41,
            )
        assert "'summarise'" in str(caught.value)
        assert "Bespoke" in str(caught.value)
        assert "plain data" in str(caught.value)


class TestAFanOutStoppedPartWayThrough:
    """What each item was holding survives the stop, so a resume finishes it.

    An item that runs again from the start re-makes every tool call it had made, which is
    what the per-item state exists to prevent. One suspension asks one question, so where
    several items stop together the rest keep their place and ask on the next pass.
    """

    @staticmethod
    def _pipeline(calls, concurrent_items=None):
        """A fan-out whose items each call a tool that suspends the first time it is asked."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def weigh(subject: str) -> str:
            """Weigh a subject. Returns its weight."""
            calls.append(subject)
            if subject not in _answered:
                raise Suspend(waiting_for=f"weight of {subject}")
            return _answered[subject]

        def load(inputs, ctx):
            return {"subjects": list(inputs["subjects"])}

        def weigh_one(inputs, ctx):
            return {
                "subject": inputs["subjects"],
                "weight": ctx.call_tool("weigh", subject=inputs["subjects"]),
            }

        return Pipeline(
            [
                Deterministic(load, node_id="load"),
                Deterministic(
                    weigh_one,
                    tools=[weigh],
                    over="subjects",
                    node_id="weigh_each",
                    concurrent_items=concurrent_items,
                ),
            ],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

    def test_the_items_already_done_are_not_run_again(self, envelope):
        global _answered
        _answered = {"a": "1kg"}
        calls: list[str] = []
        pipeline = self._pipeline(calls)

        with pytest.raises(RunSuspended):
            pipeline.run({"subjects": ["a", "b"]}, envelope=envelope, run_id=RUN_ID)

        assert calls == ["a", "b"]  # 'a' answered, 'b' suspended
        result = pipeline.resume(RUN_ID, envelope=envelope, answer="2kg")

        # 'a' finished before the stop and is not run again, and 'b' is served the answer at
        # the call it stopped on rather than calling the tool a second time.
        assert calls == ["a", "b"]
        assert [o.value["weight"] for o in result.output] == ["1kg", "2kg"]

    def test_the_state_records_which_item_was_asked(self, envelope, tmp_path):
        global _answered
        _answered = {"a": "1kg"}
        pipeline = self._pipeline([])

        with pytest.raises(RunSuspended):
            pipeline.run({"subjects": ["a", "b", "c"]}, envelope=envelope, run_id=RUN_ID)

        state = json.loads(run_path(tmp_path, RUN_ID, "suspension.json").read_text())
        held = state["frames"][0]["node_state"]["weigh_each"]
        assert held["kind"] == "fan_out"
        # One item finished, and the question on this suspension is the next one's.
        assert [record["index"] for record in held["done"]] == [0]
        assert held["asked"] == 1

    def test_items_that_stopped_together_each_keep_their_place(self, envelope, tmp_path):
        global _answered
        _answered = {}
        pipeline = self._pipeline([], concurrent_items=3)

        with pytest.raises(RunSuspended):
            pipeline.run({"subjects": ["a", "b", "c"]}, envelope=envelope, run_id=RUN_ID)

        state = json.loads(run_path(tmp_path, RUN_ID, "suspension.json").read_text())
        held = state["frames"][0]["node_state"]["weigh_each"]
        # The lowest item that stopped is the one asked, and what it was holding is kept. An
        # item that had not started when the stop arrived holds nothing, because it spent
        # nothing: the pool refuses to begin a unit once one of them has stopped the rest.
        assert held["asked"] == 0
        assert "0" in held["in_flight"]
        assert held["done"] == []

    def test_a_resume_answers_one_item_and_the_rest_ask_again(self, envelope):
        global _answered
        _answered = {}
        calls: list[str] = []
        pipeline = self._pipeline(calls)

        with pytest.raises(RunSuspended):
            pipeline.run({"subjects": ["a", "b"]}, envelope=envelope, run_id=RUN_ID)
        assert calls == ["a"]

        _answered["a"] = "1kg"
        with pytest.raises(RunSuspended):
            pipeline.resume(RUN_ID, envelope=envelope, answer="1kg")

        _answered["b"] = "2kg"
        result = pipeline.resume(RUN_ID, envelope=envelope, answer="2kg")
        assert [o.value["weight"] for o in result.output] == ["1kg", "2kg"]


_answered: dict[str, str] = {}


class TestWhatAResumedManifestKeeps:
    """A field `Manifest.restore` leaves out is one the resumed run's manifest drops.

    Found 2026-08-27 while building the memory scope. `role` was the first of these and is
    tested above; these are the three that were still missing.
    """

    def test_the_schema_blocks_its_records_reference_survive(self, tmp_path) -> None:
        """A `model_call` names a block by digest and the manifest is where the block lives."""

        class Answer(BaseModel):
            answer: str

        client = FakeModelClient(
            responses=[fake_response(content='{"answer": "a"}') for _ in range(4)]
        )
        envelope = RunEnvelope(run_dir=tmp_path / "runs")
        pipeline = Pipeline(
            [
                LLMNode(
                    lambda i, c: Prompt.user("hi"),
                    output_schema=Answer,
                    allow_unknown=False,
                    node_id="ask",
                ),
                Deterministic(lambda i, c: i, node_id="second", suspend_before=True),
            ],
            budget=_budget(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run(None, envelope=envelope, model=client, run_id=RUN_ID)
        trajectory = next((tmp_path / "runs").rglob("trajectory.jsonl"))
        referenced = {
            (json.loads(line).get("params") or {}).get("output_schema_ref")
            for line in trajectory.read_text().splitlines()
        } - {None}
        assert referenced

        pipeline.resume(RUN_ID, envelope=envelope, model=client)

        manifest = json.loads(next((tmp_path / "runs").rglob("manifest.json")).read_text())
        assert referenced <= set(manifest["schemas"])

    def test_the_servers_and_the_memory_it_recorded_survive(self) -> None:
        """Nothing writes either again after a stop, so restore is what carries them."""
        raw = {
            "run_id": RUN_ID,
            "started_at": "2026-08-27T00:00:00Z",
            "seed": 1,
            "budget": {},
            "library_version": "0",
            "paths": {"trajectory": "t", "workspace": "w"},
            "mcp": [{"server": "everything", "drift": []}],
            "memory": {"directory": "memory/", "scope_digest": "abc123", "entries": 4},
        }

        restored = Manifest.restore(raw).to_json()

        assert restored["mcp"] == raw["mcp"]
        assert restored["memory"] == raw["memory"]
