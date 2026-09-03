"""What survives a refused resume, and which node kinds are handed the answer.

A resume claimed its suspension and then discarded the claim before the checks that can refuse
had run, so a typo in `answers=` deleted the run it named. And the answer reached an
`AgentNode` and nothing else, so a `Deterministic` node holding a consultation asked again and
stopped again, which is the configuration `docs/tools.md` §4.6.1 shows.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from simple_agents import (
    Budget,
    Deterministic,
    Pipeline,
    RunSuspended,
    Suspend,
)
from simple_agents.builtins import consult
from simple_agents.errors import CallerFacingError

from conftest import run_path

RUN_ID = "run_resume_recovery"


def _asks(question: str, options: list[str], about: str | None = None):
    """A node whose consultation channel is never there to answer."""

    def channel(asked, offered=None, about=None):
        raise Suspend(waiting_for=asked, options=offered)

    def fn(inputs, ctx):
        return ctx.call_tool("consult", question=question, options=options)

    return fn, consult(channel, answered_by="end_user")


def _one_stop() -> Pipeline:
    fn, tool = _asks("Which fit?", ["slim", "regular"])
    return Pipeline([Deterministic(fn, tools=[tool], node_id="ask")], budget=Budget.unbounded())


def _two_stops() -> Pipeline:
    """Two arms that stop together, held at a barrier so neither drains the other."""
    gate = threading.Barrier(2, timeout=10)

    def channel(asked, offered=None, about=None):
        try:
            gate.wait()
        except threading.BrokenBarrierError:
            pass
        raise Suspend(waiting_for=asked, options=offered)

    def left(inputs, ctx):
        return ctx.call_tool("consult", question="Which fit?", options=["slim"])

    def right(inputs, ctx):
        return ctx.call_tool("consult", question="Which colour?", options=["red"])

    return Pipeline(
        [
            Deterministic(
                lambda i, c: i,
                node_id="plan",
                successors=["left", "right"],
                route=lambda o, c: ["left", "right"],
            ),
            Deterministic(
                left,
                tools=[consult(channel, answered_by="end_user")],
                node_id="left",
                successors=["end"],
            ),
            Deterministic(
                right,
                tools=[consult(channel, answered_by="end_user")],
                node_id="right",
                successors=["end"],
            ),
            Deterministic(lambda i, c: "closed", node_id="end", successors=[]),
        ],
        budget=Budget.unbounded(),
        concurrent_nodes=[["left", "right"]],
    )


class TestARefusedResumeKeepsTheRun:
    """The state file was unlinked, and the two things that can still refuse were evaluated
    afterwards as arguments to the call. Every refusal therefore destroyed the run it named."""

    def test_a_typo_in_answers_leaves_the_suspension_in_place(self, envelope, tmp_path):
        pipeline = _one_stop()
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        with pytest.raises(CallerFacingError) as refusal:
            pipeline.resume(RUN_ID, envelope=envelope, answers={"ask_typo": "slim"})

        assert "'ask_typo'" in str(refusal.value)
        assert run_path(tmp_path, RUN_ID, "suspension.json").exists()
        assert [state.run_id for state in Pipeline.suspensions(tmp_path)] == [RUN_ID]
        # The correction the refusal asked for now works.
        assert pipeline.resume(RUN_ID, envelope=envelope, answers={"ask": "slim"}).output == "slim"

    def test_one_answer_for_two_stops_leaves_the_suspension_in_place(self, envelope, tmp_path):
        pipeline = _two_stops()
        with pytest.raises(RunSuspended) as stop:
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41, concurrency=4)
        assert sorted(s["node_id"] for s in stop.value.stops) == ["left", "right"]

        with pytest.raises(CallerFacingError):
            pipeline.resume(RUN_ID, envelope=envelope, answer="slim")

        assert run_path(tmp_path, RUN_ID, "suspension.json").exists()
        result = pipeline.resume(
            RUN_ID,
            envelope=envelope,
            answers={"left": "slim", "right": "red"},
            concurrency=4,
        )
        assert result.output == "closed"

    def test_a_state_this_version_cannot_read_stays_findable(self, envelope, tmp_path):
        """`claim_state` renames before it parses, so the refusal left the file claimed."""
        pipeline = _one_stop()
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        path = run_path(tmp_path, RUN_ID, "suspension.json")
        body = json.loads(path.read_text())
        body["format_version"] = "0.3"
        path.write_text(json.dumps(body))

        with pytest.raises(CallerFacingError) as refusal:
            pipeline.resume(RUN_ID, envelope=envelope, answer="slim")

        assert "0.3" in str(refusal.value)
        assert path.exists()
        assert not run_path(tmp_path, RUN_ID, "suspension.claimed.json").exists()


class TestAResumeThatFailedPartWay:
    """The claim was discarded before the run was driven, so a failure inside a resumed run
    left no suspension to claim and the run had to be started over.

    Dogfood #6 carried it as an operational fact. What goes back is the state the resume
    found, so the nodes the failed attempt completed run again.
    """

    def _falls_over_after_answering(self, fails: dict) -> Pipeline:
        fn, tool = _asks("Which fit?", ["slim", "regular"])

        def store(inputs, ctx):
            if fails["still"]:
                raise RuntimeError("the store was down")
            return f"stored {inputs}"

        return Pipeline(
            [
                Deterministic(fn, tools=[tool], node_id="ask", successors=["store"]),
                Deterministic(store, node_id="store", successors=[]),
            ],
            budget=Budget.unbounded(),
        )

    def test_the_suspension_is_where_it_was_found_and_the_run_resumes_again(
        self, envelope, tmp_path
    ):
        fails = {"still": True}
        pipeline = self._falls_over_after_answering(fails)
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        with pytest.raises(RuntimeError):
            pipeline.resume(RUN_ID, envelope=envelope, answer="slim")

        assert run_path(tmp_path, RUN_ID, "suspension.json").exists()
        assert not run_path(tmp_path, RUN_ID, "suspension.claimed.json").exists()
        assert [state.run_id for state in Pipeline.suspensions(tmp_path)] == [RUN_ID]

        fails["still"] = False
        assert pipeline.resume(RUN_ID, envelope=envelope, answer="slim").output == "stored slim"

    def test_a_resume_that_stops_again_keeps_its_own_state_rather_than_the_older_one(
        self, envelope, tmp_path
    ):
        """The state written by the second stop is later than the one the resume claimed."""
        fn, tool = _asks("Which fit?", ["slim", "regular"])
        second, second_tool = _asks("Which colour?", ["red", "blue"])
        pipeline = Pipeline(
            [
                Deterministic(fn, tools=[tool], node_id="ask", successors=["confirm"]),
                Deterministic(second, tools=[second_tool], node_id="confirm", successors=[]),
            ],
            budget=Budget.unbounded(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)
        with pytest.raises(RunSuspended) as again:
            pipeline.resume(RUN_ID, envelope=envelope, answer="slim")

        assert [s["node_id"] for s in again.value.stops] == ["confirm"]
        state = json.loads(run_path(tmp_path, RUN_ID, "suspension.json").read_text())
        assert [s["node_id"] for s in state["stops"]] == ["confirm"]
        assert not run_path(tmp_path, RUN_ID, "suspension.claimed.json").exists()
        assert pipeline.resume(RUN_ID, envelope=envelope, answer="red").output == "red"

    def test_the_second_attempt_runs_the_completed_nodes_again(self, envelope, tmp_path):
        """What putting the found state back costs: those nodes write their records twice."""
        fails = {"still": True}
        ran: list = []
        fn, tool = _asks("Which fit?", ["slim", "regular"])

        def middle(inputs, ctx):
            ran.append(inputs)
            return inputs

        def store(inputs, ctx):
            if fails["still"]:
                raise RuntimeError("the store was down")
            return f"stored {inputs}"

        pipeline = Pipeline(
            [
                Deterministic(fn, tools=[tool], node_id="ask", successors=["middle"]),
                Deterministic(middle, node_id="middle", successors=["store"]),
                Deterministic(store, node_id="store", successors=[]),
            ],
            budget=Budget.unbounded(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)
        with pytest.raises(RuntimeError):
            pipeline.resume(RUN_ID, envelope=envelope, answer="slim")
        fails["still"] = False
        pipeline.resume(RUN_ID, envelope=envelope, answer="slim")

        assert ran == ["slim", "slim"]
        records = [
            json.loads(line)
            for line in run_path(tmp_path, RUN_ID, "trajectory.jsonl").read_text().splitlines()
        ]
        middles = [
            r
            for r in records
            if r.get("record_type") == "node_execution" and r["node_id"] == "middle"
        ]
        assert len(middles) == 2


class TestAResumedRunStillReadsWhatItWasGiven:
    def test_run_inputs_are_restored_from_the_suspension(self, envelope, tmp_path):
        """They are rebuilt through the codec, so they are set after the context is built."""
        seen: list = []
        fn, tool = _asks("Which fit?", ["slim", "regular"])

        def store(inputs, ctx):
            seen.append(ctx.run_inputs)
            return ctx.run_inputs["database"]

        pipeline = Pipeline(
            [
                Deterministic(fn, tools=[tool], node_id="ask", successors=["store"]),
                Deterministic(store, node_id="store", successors=[]),
            ],
            budget=Budget.unbounded(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run({"database": "shows.db"}, envelope=envelope, run_id=RUN_ID, seed=41)

        assert pipeline.resume(RUN_ID, envelope=envelope, answer="slim").output == "shows.db"
        assert seen == [{"database": "shows.db"}]


class TestTheManifestRecordsEveryStop:
    def test_two_arms_stopping_at_once_are_both_recorded(self, envelope, tmp_path):
        pipeline = _two_stops()
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41, concurrency=4)

        manifest = json.loads(run_path(tmp_path, RUN_ID, "manifest.json").read_text())
        entries = manifest["suspensions"]
        assert [entry["node_id"] for entry in entries] == ["left", "right"]
        assert {entry["waiting_for"] for entry in entries} == {
            "Which fit?",
            "Which colour?",
        }
        assert all(entry["resumed_at"] is None for entry in entries)

        pipeline.resume(
            RUN_ID,
            envelope=envelope,
            answers={"left": "slim", "right": "red"},
            concurrency=4,
        )
        manifest = json.loads(run_path(tmp_path, RUN_ID, "manifest.json").read_text())
        assert all(entry["resumed_at"] for entry in manifest["suspensions"])


class TestADeterministicNodeIsHandedItsAnswer:
    """The node runs again from the beginning, and the call that stopped is not made a second
    time: it is handed the answer instead."""

    def test_the_answer_reaches_the_call_that_suspended(self, envelope, tmp_path):
        pipeline = _one_stop()
        with pytest.raises(RunSuspended) as stop:
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)
        assert stop.value.node_id == "ask"

        result = pipeline.resume(RUN_ID, envelope=envelope, answer="slim")

        assert result.output == "slim"
        assert result.outcome == "completed"

    def test_the_two_consultation_records_name_each_other(self, envelope, tmp_path):
        pipeline = _one_stop()
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)
        pipeline.resume(RUN_ID, envelope=envelope, answer="slim")

        records = [
            json.loads(line)
            for line in run_path(tmp_path, RUN_ID, "trajectory.jsonl").read_text().splitlines()
        ]
        asked, answered = [r for r in records if r["record_type"] == "consultation"]
        assert asked["resolution"] == "pending"
        assert answered["answers"] == asked["record_id"]
        assert answered["response"] == "slim"

    def test_a_node_waiting_on_a_clock_continues(self, envelope):
        when = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()

        def channel(asked, offered=None, about=None):
            raise Suspend(
                waiting_for="monthly token quota",
                resume_not_before=when.replace("+00:00", "Z"),
            )

        def gate(inputs, ctx):
            return ctx.call_tool("consult", question="ready?")

        pipeline = Pipeline(
            [Deterministic(gate, node_id="gate", tools=[consult(channel, answered_by="end_user")])],
            budget=Budget.unbounded(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        result = pipeline.resume(RUN_ID, envelope=envelope, answer="go", wait=True)
        assert result.output == "go"

    def test_the_calls_before_the_one_that_stopped_are_made_again(self, envelope, tmp_path):
        """A `Deterministic` node holds nothing, so its earlier calls run a second time."""
        seen: list[str] = []

        def note(what: str) -> str:
            """Write one word down. Takes the word to write."""
            seen.append(what)
            return what

        def channel(asked, offered=None, about=None):
            raise Suspend(waiting_for=asked, options=offered)

        def fn(inputs, ctx):
            ctx.call_tool("note", what="first")
            return ctx.call_tool("consult", question="Which fit?", options=["slim"])

        from simple_agents import SideEffectClass, tool

        noted = tool(side_effect_class=SideEffectClass.READ_ONLY)(note)
        pipeline = Pipeline(
            [
                Deterministic(
                    fn, tools=[noted, consult(channel, answered_by="end_user")], node_id="ask"
                )
            ],
            budget=Budget.unbounded(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)
        assert seen == ["first"]

        assert pipeline.resume(RUN_ID, envelope=envelope, answer="slim").output == "slim"
        assert seen == ["first", "first"]

    def test_the_answer_reaches_a_node_inside_a_pipeline_used_as_a_node(self, envelope, tmp_path):
        """`_attempt` dispatched a container without `answer=`, and the outer walk looked the
        answer up under the container's id.

        The stop names `research.ask_inner`, the id the trajectory and the manifest use, so
        two nested pipelines each holding an `ask_inner` are distinguishable (H-6).
        """
        fn, tool = _asks("Which fit?", ["slim", "regular"])
        inner = Pipeline(
            [Deterministic(fn, tools=[tool], node_id="ask_inner")],
            budget=Budget.unbounded(),
            node_id="research",
        )
        outer = Pipeline(
            [
                Deterministic(lambda i, c: i, node_id="open", successors=["research"]),
                inner,
                Deterministic(lambda i, c: f"closed on {i}", node_id="close"),
            ],
            budget=Budget.unbounded(),
        )

        with pytest.raises(RunSuspended) as stop:
            outer.run({}, envelope=envelope, run_id=RUN_ID, seed=41)
        assert [s["node_id"] for s in stop.value.stops] == ["research.ask_inner"]

        assert outer.resume(
            RUN_ID, envelope=envelope, answers={"research.ask_inner": "slim"}
        ).output == ("closed on slim")
        records = [
            json.loads(line)
            for line in run_path(tmp_path, RUN_ID, "trajectory.jsonl").read_text().splitlines()
        ]
        asked, answered = [r for r in records if r["record_type"] == "consultation"]
        assert answered["resolution"] == "answered"
        assert answered["response"] == "slim"

    def test_a_function_that_does_not_reach_the_call_again_is_refused(self, envelope, tmp_path):
        """A dropped answer is reported rather than being lost inside a completed run."""
        state = {"asked": False}

        def channel(asked, offered=None, about=None):
            raise Suspend(waiting_for=asked, options=offered)

        def fn(inputs, ctx):
            if state["asked"]:
                return "went another way"
            state["asked"] = True
            return ctx.call_tool("consult", question="Which fit?", options=["slim"])

        pipeline = Pipeline(
            [Deterministic(fn, tools=[consult(channel, answered_by="end_user")], node_id="ask")],
            budget=Budget.unbounded(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        with pytest.raises(CallerFacingError) as refusal:
            pipeline.resume(RUN_ID, envelope=envelope, answer="slim")
        assert "'ask'" in str(refusal.value)
        assert "AgentNode" in str(refusal.value)


def test_two_nested_pipelines_with_one_leaf_name_produce_distinguishable_stops(envelope, tmp_path):
    """The bare leaf id named both. Every other surface qualifies it, and now so does the stop."""
    first_fn, first_tool = _asks("Which fit?", ["slim", "regular"])
    second_fn, second_tool = _asks("Which colour?", ["navy", "olive"])
    fit = Pipeline(
        [Deterministic(first_fn, tools=[first_tool], node_id="ask")],
        budget=Budget.unbounded(),
        node_id="fit",
    )
    colour = Pipeline(
        [Deterministic(second_fn, tools=[second_tool], node_id="ask")],
        budget=Budget.unbounded(),
        node_id="colour",
    )
    outer = Pipeline(
        [
            Deterministic(lambda i, c: i, node_id="open", successors=["fit"]),
            fit,
            colour,
        ],
        budget=Budget.unbounded(),
    )

    with pytest.raises(RunSuspended) as first:
        outer.run({}, envelope=envelope, run_id=RUN_ID, seed=41)
    assert [s["node_id"] for s in first.value.stops] == ["fit.ask"]

    with pytest.raises(RunSuspended) as second:
        outer.resume(RUN_ID, envelope=envelope, answers={"fit.ask": "slim"})

    assert [s["node_id"] for s in second.value.stops] == ["colour.ask"]
    assert second.value.waiting_for == "Which colour?"

    resumed = outer.resume(RUN_ID, envelope=envelope, answers={"colour.ask": "navy"})

    assert resumed.output == "navy"
