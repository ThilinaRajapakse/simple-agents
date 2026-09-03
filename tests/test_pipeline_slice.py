"""Part of a pipeline as a pipeline, and what its edges out of the slice do.

The graph under test is the shape the strategy is for: a linear spine with one routed arm that
rejoins at the end, so `present` takes a `Join` and a rung starting after the branch loses one
of its two in-edges. A slice that dropped that edge would hand `present` a bare value, and
nothing in the graph checks would catch it: `refuse_disagreements` skips a node whose single
predecessor declares no output type, so it builds and fails on the first rollout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Budget,
    ConfigurationError,
    Deterministic,
    Join,
    LeftTheSlice,
    Loop,
    Pipeline,
    RunEnvelope,
)


def pool(value, ctx) -> dict:
    return {"pool": ["a", "b"]}


def select(value, ctx) -> dict:
    return {"picked": (value.get("pool") or [None])[0]}


def judge(value, ctx) -> dict:
    return {"verdict": "ok", "picked": value["picked"]}


def apologise(value, ctx) -> dict:
    return {"sorry": True}


def present(value: Join, ctx) -> dict:
    return {"shown": value["judge"], "absent": sorted(value.absent)}


def recommender(route=lambda output, ctx: "judge") -> Pipeline:
    """build_pool -> select -> {judge, apologise} -> present."""
    return Pipeline(
        [
            Deterministic(pool, node_id="pool", successors=["select"]),
            Deterministic(select, node_id="select", successors=["judge", "apologise"], route=route),
            Deterministic(judge, node_id="judge", successors=["present"]),
            Deterministic(apologise, node_id="apologise", successors=["present"]),
            Deterministic(present, node_id="present", successors=[]),
        ],
        budget=Budget.unbounded(),
    )


def env(tmp_path: Path) -> RunEnvelope:
    return RunEnvelope(run_dir=tmp_path / "runs")


class TestWhichNodesASliceHolds:
    def test_a_tail_is_the_node_and_everything_it_reaches(self) -> None:
        rung = recommender().slice(start="judge")

        assert [n.node_id for n in rung.nodes] == ["judge", "present"]
        assert rung.graph.entry == "judge"
        assert rung.graph.terminal == "present"

    def test_a_prefix_is_everything_that_reaches_the_node(self) -> None:
        rung = recommender().slice(end="select")

        assert [n.node_id for n in rung.nodes] == ["pool", "select"]
        assert rung.graph.terminal == "select"

    def test_a_span_is_the_interval_between_the_two(self) -> None:
        rung = recommender().slice(start="select", end="judge")

        assert [n.node_id for n in rung.nodes] == ["select", "judge"]

    def test_one_node_alone(self) -> None:
        rung = recommender().slice(start="judge", end="judge")

        assert [n.node_id for n in rung.nodes] == ["judge"]

    def test_a_named_set_takes_the_arm_two_bounds_cannot_choose(self) -> None:
        """`select` routes two ways and only one arm is wanted, which no start/end says."""
        rung = recommender().slice(nodes=["select", "judge", "present"])

        assert [n.node_id for n in rung.nodes] == ["select", "judge", "present"]

    def test_the_pipeline_it_was_sliced_out_of_is_untouched(self) -> None:
        whole = recommender()
        whole.slice(start="judge")

        assert [n.node_id for n in whole.nodes] == [
            "pool",
            "select",
            "judge",
            "apologise",
            "present",
        ]
        assert whole.graph.successors["judge"] == ("present",)


class TestACutInEdge:
    """The arm a slice does not hold stays declared, so a joining node still joins."""

    def test_a_joining_node_keeps_both_in_edges(self) -> None:
        rung = recommender().slice(start="judge")

        assert rung.graph.in_edges("present") == ("judge", "apologise")

    def test_it_receives_a_join_with_the_cut_arm_absent(self, tmp_path: Path) -> None:
        rung = recommender().slice(start="judge")

        output = rung.run({"picked": "a"}, envelope=env(tmp_path)).output

        assert output == {"shown": {"verdict": "ok", "picked": "a"}, "absent": ["apologise"]}

    def test_the_rung_produces_what_the_whole_pipeline_produces(self, tmp_path: Path) -> None:
        """The point of keeping the edge: the rung measures the path, not an approximation."""
        whole = recommender().run({"q": 1}, envelope=env(tmp_path)).output
        rung = recommender().slice(start="judge")

        assert rung.run({"picked": "a"}, envelope=env(tmp_path)).output == whole

    def test_the_entry_takes_the_run_input_rather_than_a_cut_edge(self) -> None:
        """A cut in-edge into the first node is what running on ideal inputs means."""
        rung = recommender().slice(start="judge")

        assert rung.graph.in_edges("judge") == ()
        assert any(e.target == "judge" for e in rung.slice_of.cut_edges)


class TestACutOutEdge:
    def test_a_route_may_still_select_an_arm_the_slice_does_not_hold(self) -> None:
        rung = recommender().slice(nodes=["select", "judge", "present"])

        assert rung.graph.routable("select") == ("judge", "apologise")
        assert rung.graph.successors["select"] == ("judge",)

    def test_the_run_ends_there(self, tmp_path: Path) -> None:
        rung = recommender(route=lambda output, ctx: "apologise").slice(
            nodes=["select", "judge", "present"]
        )

        with pytest.raises(LeftTheSlice) as caught:
            rung.run({"pool": ["a"]}, envelope=env(tmp_path))

        assert caught.value.node_id == "select"
        assert caught.value.target == "apologise"

    def test_the_run_records_why_it_ended(self, tmp_path: Path) -> None:
        rung = recommender(route=lambda output, ctx: "apologise").slice(
            nodes=["select", "judge", "present"]
        )

        with pytest.raises(LeftTheSlice):
            rung.run({"pool": ["a"]}, envelope=env(tmp_path))

        run = next((tmp_path / "runs").rglob("manifest.json"))
        manifest = json.loads(run.read_text())
        assert manifest["outcome"] == "stopped_early"
        assert manifest["stopped_early"] == "left_the_slice"

        records = [
            json.loads(line) for line in (run.parent / "trajectory.jsonl").read_text().splitlines()
        ]
        ended = [
            r
            for r in records
            if r.get("record_type") == "node_execution" and r.get("termination") == "left_the_slice"
        ]
        assert [r["node_id"] for r in ended] == ["select"]


class TestTheSlicesLastNode:
    """A slice taken with `end=` cuts its last node's successor, and the run finishes there.

    Every run of this form raised `LeftTheSlice` until 2026-09-03. The mechanism ships in
    `docs/pipeline.md` §1.14 and `docs/evaluation.md` §5.6 as `pipeline.slice(end="select")`,
    and the example raised on itself: dogfood #6's first evaluation recorded 23 of 23 rollouts
    as `left_the_slice` and an accuracy with no denominator.
    """

    def test_a_prefix_runs_and_returns_its_last_node(self, tmp_path: Path) -> None:
        rung = recommender().slice(end="select")

        assert rung.run({}, envelope=env(tmp_path)).output == {"picked": "a"}

    def test_a_named_set_ending_short_of_the_terminal_runs_too(self, tmp_path: Path) -> None:
        rung = recommender().slice(nodes=["pool", "select"])

        assert rung.run({}, envelope=env(tmp_path)).output == {"picked": "a"}

    def test_the_run_completed_rather_than_stopping_early(self, tmp_path: Path) -> None:
        rung = recommender().slice(end="select")
        rung.run({}, envelope=env(tmp_path))

        manifest = json.loads(next((tmp_path / "runs").rglob("manifest.json")).read_text())
        assert manifest["outcome"] == "completed"
        assert manifest["stopped_early"] is None

    def test_the_last_node_records_the_cut_arm_it_routed_to_and_no_termination(
        self, tmp_path: Path
    ) -> None:
        rung = recommender().slice(end="select")
        rung.run({}, envelope=env(tmp_path))

        run = next((tmp_path / "runs").rglob("manifest.json")).parent
        records = [json.loads(line) for line in (run / "trajectory.jsonl").read_text().splitlines()]
        last = [
            r
            for r in records
            if r.get("record_type") == "node_execution" and r["node_id"] == "select"
        ]
        assert [r["termination"] for r in last] == [None]
        assert last[0]["route"] == ["judge"]

    def test_an_earlier_node_routing_out_of_the_slice_still_leaves(self, tmp_path: Path) -> None:
        """The rule is about the last node alone: `select` here is not it."""
        rung = recommender(route=lambda output, ctx: "apologise").slice(
            nodes=["select", "judge", "present"]
        )

        with pytest.raises(LeftTheSlice) as caught:
            rung.run({"pool": ["a"]}, envelope=env(tmp_path))

        assert (caught.value.node_id, caught.value.target) == ("select", "apologise")

    def test_the_last_node_failing_into_a_cut_handler_still_leaves(self, tmp_path: Path) -> None:
        """The node produced no output, so there is nothing for the run to return."""

        def boom(value, ctx) -> dict:
            raise RuntimeError("the tool was down")

        fragile = Pipeline(
            [
                Deterministic(pool, node_id="prep", successors=["work"]),
                Deterministic(boom, node_id="work", successors=["after"], on_error="rescue"),
                Deterministic(judge, node_id="rescue", successors=["after"]),
                Deterministic(pool, node_id="after", successors=[]),
            ],
            budget=Budget.unbounded(),
        )
        rung = fragile.slice(nodes=["prep", "work"])

        assert rung.graph.terminal == "work"
        with pytest.raises(LeftTheSlice) as caught:
            rung.run({}, envelope=env(tmp_path))

        assert (caught.value.node_id, caught.value.target) == ("work", "rescue")
        assert caught.value.kind == "on_error"


class TestWhatTheSliceRecords:
    def test_the_manifest_says_what_it_is_a_slice_of(self, tmp_path: Path) -> None:
        whole = recommender()
        rung = whole.slice(start="judge")

        result = rung.run({"picked": "a"}, envelope=env(tmp_path))

        recorded = json.loads((result.paths.root / "manifest.json").read_text())["slice"]
        assert recorded["of"] == whole.graph_fingerprint()
        assert recorded["nodes"] == ["judge", "present"]
        assert recorded["start"] == "judge" and recorded["end"] is None
        assert recorded["dropped"] == ["pool", "select", "apologise"]
        assert {"from": "apologise", "to": "present", "kind": "successor"} in (
            recorded["cut_edges"]
        )

    def test_a_whole_pipeline_records_null(self, tmp_path: Path) -> None:
        result = recommender().run({"q": 1}, envelope=env(tmp_path))

        assert json.loads((result.paths.root / "manifest.json").read_text())["slice"] is None

    def test_a_named_set_records_no_bounds(self) -> None:
        rung = recommender().slice(nodes=["judge", "present"])

        assert rung.slice_of.start is None and rung.slice_of.end is None

    def test_two_rungs_of_one_pipeline_share_the_fingerprint_they_are_of(self) -> None:
        whole = recommender()

        assert whole.slice(start="judge").slice_of.of == (whole.slice(start="select").slice_of.of)


class TestWhatASliceRefuses:
    def test_a_node_the_pipeline_does_not_hold(self) -> None:
        with pytest.raises(ConfigurationError, match="holds no node with that id"):
            recommender().slice(start="nope")

    def test_a_dotted_id_says_to_slice_the_inner_pipeline(self) -> None:
        inner = Pipeline(
            [Deterministic(judge, node_id="judge")],
            budget=Budget.unbounded(),
            node_id="research",
        )
        outer = Pipeline(
            [inner, Deterministic(apologise, node_id="report", successors=[])],
            budget=Budget.unbounded(),
        )

        with pytest.raises(ConfigurationError) as caught:
            outer.slice(start="research.judge")

        assert "slice 'research' itself" in str(caught.value)

    def test_no_bound_at_all(self) -> None:
        with pytest.raises(ConfigurationError, match="no bound"):
            recommender().slice()

    def test_both_ways_of_naming_the_set(self) -> None:
        with pytest.raises(ConfigurationError, match="two ways of saying the same thing"):
            recommender().slice(start="judge", nodes=["judge"])

    def test_an_empty_named_set(self) -> None:
        with pytest.raises(ConfigurationError, match="empty nodes="):
            recommender().slice(nodes=[])

    def test_a_disconnected_set(self) -> None:
        with pytest.raises(ConfigurationError, match="no path inside it reaches"):
            recommender().slice(nodes=["pool", "present"])

    def test_bounds_the_wrong_way_round(self) -> None:
        with pytest.raises(ConfigurationError, match="the slice would hold nothing"):
            recommender().slice(start="present", end="judge")

    def test_a_set_with_two_nodes_ending_it(self) -> None:
        with pytest.raises(ConfigurationError, match="nodes that end it"):
            recommender().slice(nodes=["select", "judge", "apologise"])


class TestACycleAtTheBoundary:
    """A cycle is entered from one node and left through the loop's `then`."""

    def _looping(self) -> Pipeline:
        return Pipeline(
            [
                Deterministic(pool, node_id="pool", successors=["hunt"]),
                Deterministic(judge, node_id="hunt", successors=["check"]),
                Deterministic(
                    select,
                    node_id="check",
                    successors=["hunt", "report"],
                    route=lambda output, ctx: "hunt",
                    loop=Loop(max_iterations=2, then="report"),
                ),
                Deterministic(apologise, node_id="report", successors=[]),
            ],
            budget=Budget.unbounded(),
        )

    def test_slicing_at_the_loop_head_keeps_the_whole_cycle(self) -> None:
        rung = self._looping().slice(start="hunt")

        assert [n.node_id for n in rung.nodes] == ["hunt", "check", "report"]
        assert rung.graph.loop_at("check") is not None

    def test_holding_a_cycle_without_its_exit_is_refused(self) -> None:
        """Every way out of `hunt` and `check` is the loop's `then`, which leaves the slice.

        Nothing would end such a rung: every run of it would reach the boundary and return
        nothing, so there is no figure to compute. The message names the node to hold.
        """
        with pytest.raises(ConfigurationError) as caught:
            self._looping().slice(nodes=["hunt", "check"])

        assert "none of them ends it" in str(caught.value)
        assert "'hunt', 'check', 'report'" in str(caught.value)

    def test_a_span_ending_at_the_loop_exit_holds_the_cycle_and_the_exit(self) -> None:
        rung = self._looping().slice(start="hunt", end="report")

        assert [n.node_id for n in rung.nodes] == ["hunt", "check", "report"]
        assert rung.graph.loop_at("check") is not None
        assert rung.graph.terminal == "report"


class TestPathsBesideTheGraph:
    """What a slice does to everything a pipeline carries that is not an edge.

    Each of these was found by reading rather than by a failure, so each is here to keep it
    that way.
    """

    def test_a_container_node_is_held_whole(self, tmp_path: Path) -> None:
        """A pipeline used as a node is one node here, and its children keep their dotted ids."""
        inner = Pipeline(
            [
                Deterministic(apologise, node_id="hunt"),
                Deterministic(apologise, node_id="verify"),
            ],
            budget=Budget.unbounded(),
            node_id="research",
        )
        outer = Pipeline(
            [
                Deterministic(pool, node_id="prep", successors=["research"]),
                inner,
                Deterministic(apologise, node_id="write", successors=[]),
            ],
            budget=Budget.unbounded(),
        )

        rung = outer.slice(start="research")

        assert [n.node_id for n in rung.nodes] == ["research", "write"]
        assert [i for i, _ in rung.declared_nodes()] == [
            "research.hunt",
            "research.verify",
            "write",
        ]
        assert rung.run({"x": 1}, envelope=env(tmp_path)).output is not None

    def test_a_concurrent_group_is_narrowed_to_the_nodes_the_slice_holds(self) -> None:
        both = Pipeline(
            [
                Deterministic(
                    pool,
                    node_id="start",
                    successors=["a", "b"],
                    route=lambda output, ctx: ["a", "b"],
                ),
                Deterministic(judge, node_id="a", successors=["merge"]),
                Deterministic(apologise, node_id="b", successors=["merge"]),
                Deterministic(present, node_id="merge", successors=[]),
            ],
            budget=Budget.unbounded(),
            concurrent_nodes=[["a", "b"]],
        )

        assert both.slice(start="start").concurrent_nodes == (("a", "b"),)
        assert both.slice(nodes=["a", "merge"]).concurrent_nodes == ()

    def test_a_cut_in_edge_survives_a_suspension(self, tmp_path: Path) -> None:
        """It is resolved when the edge state is built, and a resume restores that state."""
        from simple_agents import RunSuspended

        gathered = Pipeline(
            [
                Deterministic(
                    pool,
                    node_id="split",
                    successors=["judge", "apologise"],
                    route=lambda output, ctx: ["judge", "apologise"],
                ),
                Deterministic(judge, node_id="judge", successors=["present"]),
                Deterministic(apologise, node_id="apologise", successors=["present"]),
                Deterministic(present, node_id="present", suspend_before=True, successors=[]),
            ],
            budget=Budget.unbounded(),
        )
        rung = gathered.slice(start="judge")
        envelope = env(tmp_path)

        with pytest.raises(RunSuspended) as stop:
            rung.run({"picked": "a"}, envelope=envelope)
        resumed = rung.resume(stop.value.run_id, envelope=envelope, answers={"present": "go"})

        assert resumed.output == {
            "shown": {"verdict": "ok", "picked": "a"},
            "absent": ["apologise"],
        }

    def test_rerun_of_a_rung_is_still_a_rung(self, tmp_path: Path) -> None:
        rung = recommender().slice(start="judge")
        first = rung.run({"picked": "a"}, envelope=env(tmp_path))

        again = rung.rerun(first.paths.root, envelope=RunEnvelope(run_dir=tmp_path / "two"))

        recorded = json.loads((again.paths.root / "manifest.json").read_text())["slice"]
        assert recorded["nodes"] == ["judge", "present"]

    def test_a_slice_of_a_slice_names_the_one_it_came_from(self) -> None:
        """`of` is the immediate source, so a chain of them is followed one link at a time."""
        whole = recommender()
        once = whole.slice(start="judge")
        twice = once.slice(start="present")

        assert once.slice_of.of == whole.graph_fingerprint()
        assert twice.slice_of.of == once.graph_fingerprint()


class TestAnErrorEdgeAtTheBoundary:
    """An `on_error` handler is an edge like any other, and is not one a route chooses.

    Both halves of that were wrong at first. Counting a cut handler among the arms refused the
    slice, saying the node declared two successors and no route; and leaving it in the graph's
    edges made the handler a target with no node to invert an edge into.
    """

    def _fragile(self) -> Pipeline:
        def boom(value, ctx) -> dict:
            raise RuntimeError("the tool was down")

        def rescue(failure, ctx) -> dict:
            return {"recovered": failure.error["type"]}

        def after(value: Join, ctx) -> dict:
            return {"done": sorted(value.fired)}

        return Pipeline(
            [
                Deterministic(pool, node_id="prep", successors=["work"]),
                Deterministic(boom, node_id="work", successors=["after"], on_error="rescue"),
                Deterministic(rescue, node_id="rescue", successors=["after"]),
                Deterministic(after, node_id="after", successors=[]),
            ],
            budget=Budget.unbounded(),
        )

    def test_a_cut_handler_is_not_counted_as_a_route_arm(self) -> None:
        rung = self._fragile().slice(nodes=["work", "after"])

        assert rung.graph.routable("work") == ("after",)
        assert any(e.target == "rescue" and e.kind == "on_error" for e in rung.slice_of.cut_edges)

    def test_a_failure_whose_handler_is_outside_ends_at_the_boundary(self, tmp_path: Path) -> None:
        rung = self._fragile().slice(nodes=["work", "after"])

        with pytest.raises(LeftTheSlice) as caught:
            rung.run({}, envelope=env(tmp_path))

        assert (caught.value.node_id, caught.value.target) == ("work", "rescue")
        assert caught.value.kind == "on_error"

    def test_the_whole_pipeline_still_recovers(self, tmp_path: Path) -> None:
        output = self._fragile().run({}, envelope=env(tmp_path)).output

        assert output == {"done": ["rescue"]}

    def test_a_slice_holding_the_handler_recovers_too(self, tmp_path: Path) -> None:
        rung = self._fragile().slice(start="work")

        assert rung.run({}, envelope=env(tmp_path)).output == {"done": ["rescue"]}


class TestARefusalNamesTheFormItWasGiven:
    def test_two_ends_from_a_named_set_says_which_node_to_hold(self) -> None:
        with pytest.raises(ConfigurationError) as caught:
            recommender().slice(nodes=["select", "judge", "apologise"])

        assert "They meet at 'present'" in str(caught.value)
        assert "pipeline.slice(nodes=[" in str(caught.value)

    def test_two_ends_from_bounds_says_to_pass_end(self) -> None:
        wider = Pipeline(
            [
                Deterministic(
                    pool,
                    node_id="head",
                    successors=["one", "two"],
                    route=lambda output, ctx: "one",
                ),
                Deterministic(judge, node_id="one", successors=["tail"]),
                Deterministic(apologise, node_id="two", successors=["tail"]),
                Deterministic(present, node_id="tail", successors=[]),
            ],
            budget=Budget.unbounded(),
        )

        with pytest.raises(ConfigurationError) as caught:
            wider.slice(nodes=["head", "one", "two"])

        assert "They meet at 'tail'" in str(caught.value)
