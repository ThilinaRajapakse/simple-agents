"""What the scheduler does: routes, skips, parallel arms, joins and bounded cycles.

Every pipeline here holds `Deterministic` nodes, so what is under test is the path and nothing
else, and no model client is involved. The same shapes run against live backends in
`test_graph_integration.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Budget,
    CallerFacingError,
    Deterministic,
    Join,
    Loop,
    NodeFailure,
    Pipeline,
    RetryPolicy,
    Unknown,
)

from conftest import RUN_ID


def _budget() -> Budget:
    return Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def _records(trajectory: Path) -> list[dict]:
    return [json.loads(line) for line in trajectory.read_text().splitlines() if line.strip()]


def _nodes(trajectory: Path) -> list[dict]:
    return [r for r in _records(trajectory) if r["record_type"] == "node_execution"]


def _by_id(trajectory: Path) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for record in _nodes(trajectory):
        found.setdefault(record["node_id"], []).append(record)
    return found


def _tag(name: str, **edges) -> Deterministic:
    """A node that appends its own name to a list, so the path taken is the output."""

    def run(inputs, ctx):
        seen = inputs if isinstance(inputs, list) else []
        return [*seen, name]

    return Deterministic(run, node_id=name, **edges)


class TestSequence:
    """A list of nodes with nothing declared runs as a chain, which is what it always did."""

    def test_each_node_receives_the_previous_output(self, envelope, trajectory):
        pipeline = Pipeline([_tag("a"), _tag("b"), _tag("c")], budget=_budget())
        result = pipeline.run([], envelope=envelope, run_id=RUN_ID)
        assert result.output == ["a", "b", "c"]
        assert [r["node_id"] for r in _nodes(trajectory)] == ["a", "b", "c"]

    def test_every_record_names_where_its_output_went(self, envelope, trajectory):
        Pipeline([_tag("a"), _tag("b")], budget=_budget()).run([], envelope=envelope, run_id=RUN_ID)
        records = _nodes(trajectory)
        assert records[0]["route"] == ["b"]
        assert records[1]["route"] == []

    def test_a_node_outside_a_cycle_carries_no_loop(self, envelope, trajectory):
        Pipeline([_tag("a"), _tag("b")], budget=_budget()).run([], envelope=envelope, run_id=RUN_ID)
        assert all(r["loop"] is None for r in _nodes(trajectory))


class TestRouting:
    def _pipeline(self, pick: str) -> Pipeline:
        return Pipeline(
            [
                _tag("classify", successors=["hunt", "absent"], route=lambda o, c: pick),
                _tag("hunt", successors=["report"]),
                _tag("absent", successors=["report"]),
                _tag("report", successors=[]),
            ],
            budget=_budget(),
        )

    def test_the_selected_arm_runs(self, envelope, trajectory):
        self._pipeline("hunt").run([], envelope=envelope, run_id=RUN_ID)
        ran = {r["node_id"] for r in _nodes(trajectory) if r["termination"] != "skipped"}
        assert ran == {"classify", "hunt", "report"}

    def test_the_arm_not_selected_is_skipped_and_still_recorded(self, envelope, trajectory):
        self._pipeline("hunt").run([], envelope=envelope, run_id=RUN_ID)
        skipped = _by_id(trajectory)["absent"][0]
        assert skipped["termination"] == "skipped"
        assert skipped["outputs"] is None
        assert skipped["route"] == []

    def test_a_skipped_node_records_why_nothing_reached_it(self, envelope, trajectory):
        self._pipeline("hunt").run([], envelope=envelope, run_id=RUN_ID)
        skipped = _by_id(trajectory)["absent"][0]
        assert skipped["inputs"]["type"] == "unknown"
        assert "routed to 'hunt'" in skipped["inputs"]["reason"]

    def test_the_route_is_recorded_on_the_node_that_chose(self, envelope, trajectory):
        self._pipeline("absent").run([], envelope=envelope, run_id=RUN_ID)
        assert _by_id(trajectory)["classify"][0]["route"] == ["absent"]

    def test_a_route_reads_the_validated_output(self, envelope, trajectory):
        seen: list = []

        def remember(output, ctx):
            seen.append((output, ctx.node_id, ctx.successors))
            return "hunt"

        Pipeline(
            [
                _tag("classify", successors=["hunt", "absent"], route=remember),
                _tag("hunt", successors=["report"]),
                _tag("absent", successors=["report"]),
                _tag("report", successors=[]),
            ],
            budget=_budget(),
        ).run([], envelope=envelope, run_id=RUN_ID)
        assert seen == [(["classify"], "classify", ("hunt", "absent"))]

    def test_a_route_selecting_an_undeclared_node_raises(self, envelope):
        pipeline = self._pipeline("report")
        with pytest.raises(CallerFacingError) as exc:
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        message = str(exc.value)
        assert "selected 'report'" in message
        assert "'hunt', 'absent'" in message

    def test_a_route_selecting_nothing_raises(self, envelope):
        pipeline = Pipeline(
            [
                _tag("classify", successors=["hunt", "absent"], route=lambda o, c: []),
                _tag("hunt", successors=["report"]),
                _tag("absent", successors=["report"]),
                _tag("report", successors=[]),
            ],
            budget=_budget(),
        )
        with pytest.raises(CallerFacingError) as exc:
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        message = str(exc.value)
        assert "selected no successor" in message
        assert "return the id of the node the run finishes at" in message


class TestJoin:
    def _pipeline(self, pick) -> Pipeline:
        def merge(inputs: Join, ctx):
            return {
                "fired": list(inputs.fired),
                "absent": sorted(inputs.absent),
                "hunt": inputs["hunt"],
            }

        return Pipeline(
            [
                _tag("classify", successors=["hunt", "absent"], route=pick),
                _tag("hunt", successors=["report"]),
                _tag("absent", successors=["report"]),
                Deterministic(merge, node_id="report", successors=[]),
            ],
            budget=_budget(),
        )

    def test_a_join_carries_a_key_for_every_declared_in_edge(self, envelope):
        result = self._pipeline(lambda o, c: "hunt").run([], envelope=envelope, run_id=RUN_ID)
        assert result.output["fired"] == ["hunt"]
        assert result.output["absent"] == ["absent"]

    def test_an_absent_edge_carries_an_unknown_saying_why(self, envelope):
        def read(inputs: Join, ctx):
            return inputs["absent"]

        pipeline = Pipeline(
            [
                _tag("classify", successors=["hunt", "absent"], route=lambda o, c: "hunt"),
                _tag("hunt", successors=["report"]),
                _tag("absent", successors=["report"]),
                Deterministic(read, node_id="report", successors=[]),
            ],
            budget=_budget(),
        )
        value = pipeline.run([], envelope=envelope, run_id=RUN_ID).output
        assert isinstance(value, Unknown)
        assert "was skipped" in str(value.reason)

    def test_both_arms_run_when_the_route_selects_both(self, envelope, trajectory):
        result = self._pipeline(lambda o, c: ["hunt", "absent"]).run(
            [], envelope=envelope, run_id=RUN_ID
        )
        assert result.output["fired"] == ["hunt", "absent"]
        assert result.output["absent"] == []
        assert {r["node_id"] for r in _nodes(trajectory)} == {
            "classify",
            "hunt",
            "absent",
            "report",
        }
        assert all(r["termination"] != "skipped" for r in _nodes(trajectory))

    def test_a_join_waits_for_every_arm_before_running(self, envelope, trajectory):
        self._pipeline(lambda o, c: ["hunt", "absent"]).run([], envelope=envelope, run_id=RUN_ID)
        order = [r["node_id"] for r in _nodes(trajectory)]
        assert order.index("report") > order.index("hunt")
        assert order.index("report") > order.index("absent")

    def test_the_join_is_tagged_on_the_record(self, envelope, trajectory):
        self._pipeline(lambda o, c: "hunt").run([], envelope=envelope, run_id=RUN_ID)
        recorded = _by_id(trajectory)["report"][0]["inputs"]
        assert recorded["type"] == "join"
        assert sorted(recorded["edges"]) == ["absent", "hunt"]
        assert recorded["absent"] == ["absent"]

    def test_reading_a_node_that_is_not_a_predecessor_raises(self, envelope):
        def wrong(inputs: Join, ctx):
            return inputs["classify"]

        pipeline = Pipeline(
            [
                _tag("classify", successors=["hunt", "absent"], route=lambda o, c: "hunt"),
                _tag("hunt", successors=["report"]),
                _tag("absent", successors=["report"]),
                Deterministic(wrong, node_id="report", successors=[]),
            ],
            budget=_budget(),
        )
        with pytest.raises(CallerFacingError) as exc:
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        message = str(exc.value)
        assert "has no in-edge from 'classify'" in message
        assert "'hunt', 'absent'" in message

    def test_a_node_that_answered_absence_still_fires_its_edge(self, envelope):
        """An `Unknown` output is an answer, so the edge carrying it fired."""

        def nothing_found(inputs, ctx):
            return Unknown(reason="the notes give no figure")

        def merge(inputs: Join, ctx):
            return {"absent": sorted(inputs.absent), "value": inputs["hunt"]}

        pipeline = Pipeline(
            [
                _tag("classify", successors=["hunt", "absent"], route=lambda o, c: "hunt"),
                Deterministic(nothing_found, node_id="hunt", successors=["report"]),
                _tag("absent", successors=["report"]),
                Deterministic(merge, node_id="report", successors=[]),
            ],
            budget=_budget(),
        )
        output = pipeline.run([], envelope=envelope, run_id=RUN_ID).output
        assert output["absent"] == ["absent"]
        assert isinstance(output["value"], Unknown)


class TestBoundedCycle:
    def _pipeline(self, accept_after: int) -> Pipeline:
        def draft(inputs, ctx):
            # The entry node, and the node the cycle returns to. The run's inputs arrive on
            # the first pass and the critique's output on the ones after.
            return inputs

        def critique(inputs, ctx):
            return inputs + 1

        def again(output, ctx):
            return "publish" if output >= accept_after else "draft"

        def publish(inputs, ctx):
            return f"published after {inputs}"

        return Pipeline(
            [
                Deterministic(draft, node_id="draft", successors=["critique"]),
                Deterministic(
                    critique,
                    node_id="critique",
                    successors=["draft", "publish"],
                    route=again,
                    loop=Loop(max_iterations=3, then="publish"),
                ),
                Deterministic(publish, node_id="publish", successors=[]),
            ],
            budget=_budget(),
        )

    def test_a_cycle_stops_when_the_route_says_so(self, envelope, trajectory):
        result = self._pipeline(accept_after=2).run(0, envelope=envelope, run_id=RUN_ID)
        assert result.output == "published after 2"
        assert len(_by_id(trajectory)["draft"]) == 2
        assert len(_by_id(trajectory)["critique"]) == 2

    def test_a_cycle_stops_at_max_iterations_and_says_so(self, envelope, trajectory):
        result = self._pipeline(accept_after=99).run(0, envelope=envelope, run_id=RUN_ID)
        assert result.output == "published after 3"
        assert len(_by_id(trajectory)["critique"]) == 3
        last = _by_id(trajectory)["critique"][-1]
        assert last["termination"] == "max_iterations"
        assert last["route"] == ["publish"]

    def test_every_iteration_is_numbered_on_the_record(self, envelope, trajectory):
        self._pipeline(accept_after=99).run(0, envelope=envelope, run_id=RUN_ID)
        loops = [r["loop"]["iteration"] for r in _by_id(trajectory)["critique"]]
        assert loops == [1, 2, 3]
        assert [r["loop"]["exhausted"] for r in _by_id(trajectory)["critique"]] == [
            False,
            False,
            True,
        ]

    def test_a_node_in_the_cycle_names_the_loop_it_belongs_to(self, envelope, trajectory):
        self._pipeline(accept_after=99).run(0, envelope=envelope, run_id=RUN_ID)
        first = _by_id(trajectory)["draft"][0]
        assert first["loop"]["node_id"] == "critique"
        assert first["loop"]["max_iterations"] == 3
        assert first["loop"]["exhausted"] is False

    def test_a_node_after_the_cycle_runs_once(self, envelope, trajectory):
        self._pipeline(accept_after=99).run(0, envelope=envelope, run_id=RUN_ID)
        assert len(_by_id(trajectory)["publish"]) == 1

    def test_the_body_sees_the_feedback_and_what_entered_the_cycle(self, envelope):
        """`draft` joins the run's input with the critique that sent it back."""
        seen: list = []

        def draft(inputs: Join, ctx):
            seen.append(sorted(inputs.absent))
            return 0 if "critique" in inputs.absent else inputs["critique"]

        pipeline = Pipeline(
            [
                _tag("start", successors=["draft"]),
                Deterministic(draft, node_id="draft", successors=["critique"]),
                Deterministic(
                    lambda i, c: i + 1,
                    node_id="critique",
                    successors=["draft", "publish"],
                    route=lambda o, c: "publish" if o >= 2 else "draft",
                    loop=Loop(max_iterations=5, then="publish"),
                ),
                Deterministic(lambda i, c: i, node_id="publish", successors=[]),
            ],
            budget=_budget(),
        )
        assert pipeline.run([], envelope=envelope, run_id=RUN_ID).output == 2
        assert seen == [["critique"], []]

    def test_the_edge_from_outside_keeps_the_value_that_entered(self, envelope):
        """Every iteration reads the same value on it, which `docs/pipeline.md` §1.4 states.

        A node folding each iteration's result into what arrived on that edge folds into the
        value from before the first iteration every time.
        """
        entered: list = []

        def head(inputs: Join, ctx):
            state = inputs["start"]
            entered.append(list(state["found"]))
            return {"found": [*state["found"], "one more"]}

        pipeline = Pipeline(
            [
                Deterministic(lambda i, c: {"found": []}, node_id="start", successors=["head"]),
                Deterministic(head, node_id="head", successors=["body"]),
                Deterministic(
                    lambda i, c: i,
                    node_id="body",
                    successors=["head", "done"],
                    route=lambda o, c: "head",
                    loop=Loop(max_iterations=3, then="done"),
                ),
                Deterministic(lambda i, c: i, node_id="done", successors=[]),
            ],
            budget=_budget(),
        )
        pipeline.run({}, envelope=envelope, run_id=RUN_ID)
        assert entered == [[], [], []], "the entry edge never carries what accumulated"

    def test_a_value_accumulates_on_the_edge_that_closes_the_cycle(self, envelope, trajectory):
        """The shape `docs/pipeline.md` §1.4 shows: fold before going back round."""

        def select(inputs: Join, ctx):
            state = inputs["seed"] if "fold" in inputs.absent else inputs["fold"]
            pending = list(state["pending"])
            return {**state, "pending": pending[1:], "current": pending[0] if pending else None}

        def fold(inputs: Join, ctx):
            state = inputs["select"]
            return {**state, "resolved": [*state["resolved"], inputs["work"]]}

        pipeline = Pipeline(
            [
                Deterministic(
                    lambda i, c: {"pending": ["a", "b", "c"], "resolved": []},
                    node_id="seed",
                    successors=["select"],
                ),
                Deterministic(
                    select,
                    node_id="select",
                    successors=["work", "fold", "finalise"],
                    route=lambda o, c: ["work", "fold"] if o["current"] else "finalise",
                ),
                Deterministic(
                    lambda i, c: f"did {i['current']}", node_id="work", successors=["fold"]
                ),
                Deterministic(
                    fold,
                    node_id="fold",
                    successors=["select", "finalise"],
                    route=lambda o, c: "select",
                    loop=Loop(max_iterations=8, then="finalise"),
                ),
                Deterministic(
                    lambda i, c: i["select"] if "fold" in i.absent else i["fold"],
                    node_id="finalise",
                    successors=[],
                ),
            ],
            budget=_budget(),
        )
        result = pipeline.run({}, envelope=envelope, run_id=RUN_ID)
        assert result.output["resolved"] == ["did a", "did b", "did c"]
        assert result.output["pending"] == []

        # Every iteration's working set is on a record, which is what the workspace is not.
        folds = [r for r in _by_id(trajectory)["fold"] if r["outputs"] is not None]
        assert [len(r["outputs"]["resolved"]) for r in folds] == [1, 2, 3]
        # The pass that left the cycle reached `finalise` without `fold`, which is why the
        # example reads whichever edge fired.
        skipped = [r for r in _by_id(trajectory)["fold"] if r["outputs"] is None]
        assert [r["termination"] for r in skipped] == ["skipped"]


class TestNestedCycle:
    def test_the_inner_count_starts_again_on_every_outer_pass(self, envelope, trajectory):
        """Per entry, not per run: an inner loop bounded at 2 gets 2 on each outer pass."""

        def inner_route(output, ctx):
            return "inner"

        pipeline = Pipeline(
            [
                _tag("start", successors=["inner"]),
                Deterministic(lambda i, c: i, node_id="inner", successors=["gate"]),
                Deterministic(
                    lambda i, c: i,
                    node_id="gate",
                    successors=["inner", "outer"],
                    route=inner_route,
                    loop=Loop(max_iterations=2, then="outer"),
                ),
                Deterministic(
                    lambda i, c: i,
                    node_id="outer",
                    successors=["inner", "end"],
                    route=lambda o, c: "inner",
                    loop=Loop(max_iterations=3, then="end"),
                ),
                _tag("end", successors=[]),
            ],
            budget=_budget(),
        )
        pipeline.run([], envelope=envelope, run_id=RUN_ID)
        counts = _by_id(trajectory)
        # The outer loop runs 3 times, and each of its passes gives the inner loop 2.
        assert len(counts["outer"]) == 3
        assert len(counts["gate"]) == 6
        assert [r["loop"]["iteration"] for r in counts["gate"]] == [1, 2, 1, 2, 1, 2]


class TestErrorEdgeAndRetry:
    def _pipeline(self, fail_times: int, **edges) -> tuple[Pipeline, list]:
        attempts: list[int] = []

        def flaky(inputs, ctx):
            attempts.append(len(attempts) + 1)
            if len(attempts) <= fail_times:
                raise RuntimeError(f"attempt {len(attempts)} failed")
            return "worked"

        def rescue(inputs: NodeFailure, ctx):
            return f"rescued {inputs.node_id} after {inputs.attempts}: {inputs.error['message']}"

        def end(inputs: Join, ctx):
            """Whichever arm fired. One of the two always did."""
            return inputs[inputs.fired[0]]

        pipeline = Pipeline(
            [
                Deterministic(flaky, node_id="work", successors=["end"], **edges),
                Deterministic(rescue, node_id="rescue", successors=["end"]),
                Deterministic(end, node_id="end", successors=[]),
            ],
            budget=_budget(),
        )
        return pipeline, attempts

    def _alone(self, **edges) -> Pipeline:
        """The same flaky node with no handler, so a final failure ends the run."""

        def always_fails(inputs, ctx):
            raise RuntimeError("no recovery declared")

        return Pipeline(
            [
                Deterministic(always_fails, node_id="work", successors=["end"], **edges),
                Deterministic(lambda i, c: i, node_id="end", successors=[]),
            ],
            budget=_budget(),
        )

    def test_a_node_with_no_retry_runs_once(self, envelope, trajectory):
        pipeline, attempts = self._pipeline(fail_times=0, on_error="rescue")
        pipeline.run([], envelope=envelope, run_id=RUN_ID)
        assert attempts == [1]

    def test_a_retry_runs_the_node_again(self, envelope, trajectory):
        pipeline, attempts = self._pipeline(
            fail_times=2, on_error="rescue", retry=RetryPolicy(attempts=3)
        )
        pipeline.run([], envelope=envelope, run_id=RUN_ID)
        assert attempts == [1, 2, 3]

    def test_every_attempt_writes_its_own_record(self, envelope, trajectory):
        pipeline, _ = self._pipeline(fail_times=2, on_error="rescue", retry=RetryPolicy(attempts=3))
        pipeline.run([], envelope=envelope, run_id=RUN_ID)
        records = _by_id(trajectory)["work"]
        assert [r["termination"] for r in records] == ["error", "error", None]
        assert records[0]["error"]["message"] == "attempt 1 failed"
        assert records[-1]["outputs"] == "worked"

    def test_a_node_that_recovers_does_not_take_the_error_edge(self, envelope, trajectory):
        pipeline, _ = self._pipeline(fail_times=1, on_error="rescue", retry=RetryPolicy(attempts=2))
        result = pipeline.run([], envelope=envelope, run_id=RUN_ID)
        assert result.output == "worked"
        assert _by_id(trajectory)["rescue"][0]["termination"] == "skipped"

    def test_an_exhausted_retry_takes_the_error_edge(self, envelope, trajectory):
        pipeline, _ = self._pipeline(
            fail_times=99, on_error="rescue", retry=RetryPolicy(attempts=2)
        )
        result = pipeline.run([], envelope=envelope, run_id=RUN_ID)
        assert result.output == "rescued work after 2: attempt 2 failed"

    def test_the_failing_record_names_where_the_failure_went(self, envelope, trajectory):
        pipeline, _ = self._pipeline(
            fail_times=99, on_error="rescue", retry=RetryPolicy(attempts=2)
        )
        pipeline.run([], envelope=envelope, run_id=RUN_ID)
        records = _by_id(trajectory)["work"]
        assert records[0]["route"] == []
        assert records[1]["route"] == ["rescue"]

    def test_the_handler_records_what_failed(self, envelope, trajectory):
        pipeline, _ = self._pipeline(fail_times=99, on_error="rescue")
        pipeline.run([], envelope=envelope, run_id=RUN_ID)
        recorded = _by_id(trajectory)["rescue"][0]["inputs"]
        assert recorded["type"] == "node_failure"
        assert recorded["node_id"] == "work"
        assert recorded["attempts"] == 1
        assert recorded["error"]["class"] == "caller_facing"

    def test_a_failure_with_no_error_edge_ends_the_run(self, envelope, trajectory):
        pipeline = self._alone(retry=RetryPolicy(attempts=2))
        with pytest.raises(RuntimeError):
            pipeline.run([], envelope=envelope, run_id=RUN_ID)
        assert [r["termination"] for r in _by_id(trajectory)["work"]] == ["error", "error"]
        assert "end" not in _by_id(trajectory)

    def test_a_run_that_failed_still_wrote_its_manifest(self, envelope, manifest_path):
        with pytest.raises(RuntimeError):
            self._alone().run([], envelope=envelope, run_id=RUN_ID)
        assert json.loads(manifest_path.read_text())["outcome"] == "error"


class TestComposition:
    """A pipeline used as a node inside another."""

    def _inner(self) -> Pipeline:
        return Pipeline(
            [_tag("hunt"), _tag("verify", successors=[])],
            budget=_budget(),
            node_id="research",
        )

    def _outer(self, **edges) -> Pipeline:
        return Pipeline([self._inner(), _tag("write", successors=[])], budget=_budget(), **edges)

    def test_the_inner_nodes_run_in_order(self, envelope, trajectory):
        result = self._outer().run([], envelope=envelope, run_id=RUN_ID)
        assert result.output == ["hunt", "verify", "write"]

    def test_inner_ids_are_namespaced_by_the_containing_node(self, envelope, trajectory):
        self._outer().run([], envelope=envelope, run_id=RUN_ID)
        assert [r["node_id"] for r in _nodes(trajectory)] == [
            "research.hunt",
            "research.verify",
            "write",
        ]

    def test_the_container_writes_no_record_of_its_own(self, envelope, trajectory):
        self._outer().run([], envelope=envelope, run_id=RUN_ID)
        assert all(r["node_kind"] != "pipeline" for r in _nodes(trajectory))

    def test_the_manifest_lists_the_namespaced_nodes_and_no_container(
        self, envelope, manifest_path
    ):
        self._outer().run([], envelope=envelope, run_id=RUN_ID)
        nodes = json.loads(manifest_path.read_text())["nodes"]
        assert [n["node_id"] for n in nodes] == ["research.hunt", "research.verify", "write"]
        assert nodes[0]["successors"] == ["research.verify"]
        assert all(n["node_kind"] in {"deterministic", "llm", "agent"} for n in nodes)

    def test_two_copies_of_one_pipeline_do_not_collide(self, envelope, trajectory):
        left = Pipeline([_tag("step", successors=[])], budget=_budget(), node_id="left")
        right = Pipeline([_tag("step", successors=[])], budget=_budget(), node_id="right")
        Pipeline([left, right, _tag("end", successors=[])], budget=_budget()).run(
            [], envelope=envelope, run_id=RUN_ID
        )
        assert [r["node_id"] for r in _nodes(trajectory)] == [
            "left.step",
            "right.step",
            "end",
        ]

    def test_a_container_can_be_routed_around(self, envelope, trajectory):
        pipeline = Pipeline(
            [
                _tag("classify", successors=["research", "write"], route=lambda o, c: "write"),
                Pipeline(
                    [_tag("hunt", successors=[])],
                    budget=_budget(),
                    node_id="research",
                    successors=["write"],
                ),
                _tag("write", successors=[]),
            ],
            budget=_budget(),
        )
        pipeline.run([], envelope=envelope, run_id=RUN_ID)
        assert "research.hunt" not in _by_id(trajectory)

    def test_declared_nodes_names_what_a_trajectory_will_hold(self):
        assert [node_id for node_id, _ in self._outer().declared_nodes()] == [
            "research.hunt",
            "research.verify",
            "write",
        ]
        assert self._outer().node_kinds == {"deterministic": 3}

    def test_a_nested_pipeline_with_no_node_id_refuses(self):
        with pytest.raises(Exception) as exc:
            Pipeline(
                [Pipeline([_tag("a", successors=[])], budget=_budget()), _tag("b")],
                budget=_budget(),
            )
        message = str(exc.value)
        assert "pipeline(s) with no node_id" in message
        assert "node_id='research'" in message


class TestWhatTheManifestSaysAboutAContainer:
    """`nodes` alone is not a graph: the edge out of a container is on no entry in it.

    Two entries read as ending the run, and an edge names an id the array does not hold, which
    is a shape `Graph` refuses to construct. `containers` is where the rest is.
    """

    def _outer(self, **inner_edges) -> Pipeline:
        inner = Pipeline(
            [_tag("hunt"), _tag("verify", successors=[])],
            budget=Budget(max_steps=6, max_tokens=20_000, max_cost=None, max_wall_clock_ms=None),
            node_id="research",
            **inner_edges,
        )
        return Pipeline([inner, _tag("write", successors=[])], budget=_budget())

    def test_the_container_carries_its_children_its_edges_and_its_budget(self):
        containers = self._outer().manifest_containers()

        assert containers == [
            {
                "node_id": "research",
                "node_kind": "pipeline",
                "nodes": ["research.hunt", "research.verify"],
                "successors": ["write"],
                "route": None,
                "loop": None,
                "on_error": None,
                "retry": None,
                "suspend_before": False,
                "budget": {
                    "max_steps": 6,
                    "max_tokens": 20_000,
                    "max_cost": None,
                    "max_wall_clock_ms": None,
                },
                "reached_by": None,
            }
        ]

    def test_a_pipeline_nesting_none_records_none(self):
        assert Pipeline([_tag("a", successors=[])], budget=_budget()).manifest_containers() == []

    def test_a_container_two_deep_is_recorded_under_both_prefixes(self):
        deep = Pipeline([_tag("find", successors=[])], budget=_budget(), node_id="sources")
        middle = Pipeline([deep], budget=_budget(), node_id="research")
        outer = Pipeline([middle, _tag("write", successors=[])], budget=_budget())

        assert [c["node_id"] for c in outer.manifest_containers()] == [
            "research",
            "research.sources",
        ]
        assert outer.manifest_containers()[1]["nodes"] == ["research.sources.find"]

    def test_an_edge_target_inside_a_container_is_written_under_the_id_it_records(self):
        """`successors` was prefixed and `on_error` and `loop.then` beside it were not."""
        inner = Pipeline(
            [
                _tag("hunt", successors=["verify"], on_error="rescue"),
                _tag("rescue", successors=["verify"]),
                _tag("verify", successors=[]),
            ],
            budget=_budget(),
            node_id="research",
        )
        entries = {
            entry["node_id"]: entry
            for entry in Pipeline(
                [inner, _tag("write", successors=[])], budget=_budget()
            ).manifest_nodes()
        }

        assert entries["research.hunt"]["on_error"] == "research.rescue"
        assert entries["research.hunt"]["successors"] == ["research.verify"]

    def test_the_manifest_written_by_a_run_holds_them(self, envelope, manifest_path):
        self._outer().run([], envelope=envelope, run_id=RUN_ID)

        written = json.loads(manifest_path.read_text())
        assert [c["node_id"] for c in written["containers"]] == ["research"]
        assert written["containers"][0]["successors"] == ["write"]


class TestTheFingerprintCoversAContainer:
    """A suspension's state is keyed on node ids, so a rewired sub-pipeline made it meaningless.

    `_STRUCTURAL` read leaf entries, and a container had none.
    """

    def _outer(self, *, budget=None, **inner_edges) -> Pipeline:
        inner = Pipeline(
            [_tag("hunt"), _tag("verify", successors=[])],
            budget=budget or _budget(),
            node_id="research",
            **inner_edges,
        )
        return Pipeline(
            [inner, _tag("write", successors=["rescue"]), _tag("rescue", successors=[])],
            budget=_budget(),
        )

    def test_a_container_gaining_an_error_edge_moves_it(self):
        assert (
            self._outer().graph_fingerprint() != self._outer(on_error="rescue").graph_fingerprint()
        )

    def test_a_container_gaining_a_retry_moves_it(self):
        assert (
            self._outer().graph_fingerprint()
            != self._outer(retry=RetryPolicy(attempts=3)).graph_fingerprint()
        )

    def test_a_container_budget_does_not_move_it(self):
        """Recorded, and not structural, the same as a leaf's `node_budget`. A budget that
        changed is a run that may stop somewhere else, not state that has stopped meaning
        anything."""
        tighter = Budget(max_steps=1, max_tokens=1, max_cost=None, max_wall_clock_ms=None)

        assert self._outer().graph_fingerprint() == self._outer(budget=tighter).graph_fingerprint()
        assert self._outer(budget=tighter).manifest_containers()[0]["budget"]["max_steps"] == 1


class TestProgressEvents:
    def _seen(self, pipeline, envelope) -> list:
        events: list = []
        pipeline.run([], envelope=envelope, run_id=RUN_ID, on_progress=events.append)
        return events

    def test_every_node_reports_starting_and_completing(self, envelope):
        events = self._seen(Pipeline([_tag("a"), _tag("b")], budget=_budget()), envelope)
        assert [(e.phase, e.node_id) for e in events] == [
            ("started", "a"),
            ("completed", "a"),
            ("started", "b"),
            ("completed", "b"),
        ]

    def test_a_completed_event_names_where_the_output_went(self, envelope):
        events = self._seen(Pipeline([_tag("a"), _tag("b")], budget=_budget()), envelope)
        assert events[1].route == ("b",)
        assert events[3].route == ()

    def test_a_skipped_node_reports_once(self, envelope):
        pipeline = Pipeline(
            [
                _tag("classify", successors=["hunt", "absent"], route=lambda o, c: "hunt"),
                _tag("hunt", successors=["report"]),
                _tag("absent", successors=["report"]),
                Deterministic(lambda i, c: i["hunt"], node_id="report", successors=[]),
            ],
            budget=_budget(),
        )
        phases = {(e.phase, e.node_id) for e in self._seen(pipeline, envelope)}
        assert ("skipped", "absent") in phases
        assert ("started", "absent") not in phases

    def test_each_iteration_of_a_cycle_is_numbered(self, envelope):
        pipeline = Pipeline(
            [
                # The entry node: the run's inputs on the first pass, the count after it.
                Deterministic(lambda i, c: 0 if not isinstance(i, int) else i, node_id="draft"),
                Deterministic(
                    lambda i, c: i + 1,
                    node_id="critique",
                    successors=["draft", "publish"],
                    route=lambda o, c: "draft",
                    loop=Loop(max_iterations=2, then="publish"),
                ),
                Deterministic(lambda i, c: i, node_id="publish", successors=[]),
            ],
            budget=_budget(),
        )
        iterations = [
            e.iteration
            for e in self._seen(pipeline, envelope)
            if e.node_id == "critique" and e.phase == "started"
        ]
        assert iterations == [1, 2]

    def test_a_retried_node_reports_each_failed_attempt(self, envelope):
        attempts: list[int] = []

        def flaky(inputs, ctx):
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("not yet")
            return "worked"

        pipeline = Pipeline(
            [
                Deterministic(flaky, node_id="work", retry=RetryPolicy(attempts=3)),
                _tag("end", successors=[]),
            ],
            budget=_budget(),
        )
        events = self._seen(pipeline, envelope)
        failed = [(e.phase, e.attempt) for e in events if e.node_id == "work"]
        assert failed == [
            ("started", 1),
            ("failed", 1),
            ("failed", 2),
            ("completed", 1),
        ]

    def test_a_nested_pipeline_reports_its_nodes_and_not_itself(self, envelope):
        inner = Pipeline([_tag("hunt", successors=[])], budget=_budget(), node_id="research")
        pipeline = Pipeline([inner, _tag("write", successors=[])], budget=_budget())
        assert [(e.phase, e.node_id) for e in self._seen(pipeline, envelope)] == [
            ("started", "research.hunt"),
            ("completed", "research.hunt"),
            ("started", "write"),
            ("completed", "write"),
        ]
