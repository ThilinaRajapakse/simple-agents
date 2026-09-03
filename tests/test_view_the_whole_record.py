"""What the page says once it reads every run rather than the newest one.

`P3-40` read the two newest runs of each shape, which is what one run looks like. Three
questions need the whole record instead: what a step costs, how often each edge is taken, and
what has gone in and out of each store. All three are joined onto the drawing here.

The `branching` fixture is the one with every shape at once: a three-way route, a bounded
loop, a fan-out, a failure path, a nested pipeline, four stores reached three different ways,
two live runs and a live evaluation over six rollouts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents.view import assemble
from simple_agents.view.callables import read_callable, signature_line
from simple_agents.view.record import read_record
from simple_agents.view.walk import walk_run, walkable_runs
from simple_agents.envelope import manifest_paths

FIXTURES = Path(__file__).parent / "fixtures" / "view_projects"
BRANCHING = FIXTURES / "branching"


@pytest.fixture(scope="module")
def branching() -> dict:
    return assemble(BRANCHING)


def pipeline(data: dict, name: str) -> dict:
    return next(p for p in data["pipelines"] if p.get("name") == name)


def node(data: dict, pipe: str, node_id: str) -> dict:
    return next(n for n in pipeline(data, pipe)["nodes"] if n["id"] == node_id)


class TestWhatEachStepCost:
    def test_the_two_populations_are_counted_apart(self, branching) -> None:
        held = pipeline(branching, "triage")

        assert held["over_runs"]["runs"] == 2
        assert held["over_rollouts"]["runs"] == 16

    def test_a_step_carries_its_cost_in_the_basis_its_runs_declared(self, branching) -> None:
        draft = node(branching, "triage", "draft")

        assert list(draft["over_the_record"]["cost_by_basis"]) == ["USD"]
        assert draft["over_the_record"]["cost_by_basis"]["USD"] > 0

    def test_a_step_that_calls_no_model_reports_no_cost(self, branching) -> None:
        assert node(branching, "triage", "intake")["over_the_record"]["cost_by_basis"] == {}

    def test_the_per_node_costs_add_up_to_what_the_runs_recorded(self) -> None:
        """The join is exact, so the sum over steps is the sum the manifests already carry."""
        held = read_record(BRANCHING)["runs"]
        [group] = held.values()
        summed = sum(
            value for one in group["nodes"].values() for value in one["cost_by_basis"].values()
        )
        recorded = 0.0
        for path in manifest_paths(BRANCHING / "runs"):
            manifest = json.loads(path.read_text())
            recorded += float((manifest["totals"]["cost"] or {}).get("value") or 0.0)

        assert summed == pytest.approx(recorded, rel=1e-6)

    def test_a_paid_tool_is_kept_apart_from_the_model_calls(self, branching) -> None:
        """`answer_directly` is reached by the evaluation alone, and it buys something."""
        held = pipeline(branching, "triage")["over_rollouts"]["nodes"]["answer_directly"]

        assert held["spend_by_currency"] == {"USD": pytest.approx(0.012)}
        assert held["cost_by_basis"]["USD"] > 0

    def test_a_fan_out_reports_how_many_items_it_handled(self, branching) -> None:
        """Two runs of two items each is four, not the highest index either of them saw."""
        held = node(branching, "triage", "research.read_source")["over_the_record"]

        assert held["executions"] == 2
        assert held["items"] == 4

    def test_time_is_read_from_the_records_own_stamps(self, branching) -> None:
        assert node(branching, "triage", "classify")["over_the_record"]["ms"] > 0

    def test_a_step_the_runs_never_reached_is_counted_as_skipped(self, branching) -> None:
        held = node(branching, "triage", "apologise")["over_the_record"]

        assert held["executions"] == 0
        assert held["skipped"] > 0


class TestWhatTheEvaluationSaysItCost:
    """The results file has carried a per-node cost all along and the page did not read it."""

    def test_each_step_carries_what_its_model_calls_cost(self, branching) -> None:
        assert node(branching, "triage", "draft")["measured"]["cost"] > 0
        assert node(branching, "triage", "draft")["measured"]["cost_currency"] == "USD"

    def test_a_step_that_calls_no_model_says_why_it_has_no_figure(self, branching) -> None:
        held = node(branching, "triage", "intake")["measured"]

        assert held["cost"] is None

    def test_the_paid_tool_is_beside_the_model_cost_and_not_inside_it(self, branching):
        held = node(branching, "triage", "answer_directly")["measured"]

        assert held["tool_spend"] == pytest.approx(0.004)
        assert held["cost"] == pytest.approx(0.0004515)

    def test_the_accesses_a_step_recorded_reach_the_per_node_figures(self, branching):
        assert node(branching, "triage", "intake")["measured"]["resource_reads"] == {"inbox": 8}
        assert node(branching, "triage", "publish")["measured"]["resource_writes"] == {"outbox": 8}


class TestHowOftenEachEdgeIsTaken:
    def test_an_edge_carries_the_runs_that_took_it(self, branching) -> None:
        assert pipeline(branching, "triage")["over_runs"]["edges"]["intake->classify"] == 2

    def test_a_route_arm_no_run_took_is_absent_rather_than_zero(self, branching) -> None:
        """The drawing tells "counted and never taken" from "not counted" by absence."""
        edges = pipeline(branching, "triage")["over_runs"]["edges"]

        assert "classify->escalate" not in edges
        assert "classify->answer_directly" not in edges

    def test_the_evaluation_took_the_arms_the_runs_did_not(self, branching) -> None:
        edges = pipeline(branching, "triage")["over_rollouts"]["edges"]

        assert edges["classify->answer_directly"] == 3
        assert edges["classify->escalate"] == 5
        assert edges["classify->research.pick_sources"] == 8

    def test_an_edge_into_a_nested_pipeline_names_its_first_step(self, branching) -> None:
        """The record names the container and the drawing enters at its entry, so the two
        are joined rather than the edge being dropped."""
        edges = pipeline(branching, "triage")["over_rollouts"]["edges"]

        assert "classify->research.pick_sources" in edges
        assert "classify->research" not in edges

    def test_the_loop_back_has_never_fired_and_says_so(self, branching) -> None:
        edges = pipeline(branching, "triage")["over_rollouts"]["edges"]

        assert "critique->draft" not in edges
        assert edges["critique->publish"] == 8


class TestWhatWentInAndOutOfEachStore:
    def test_a_store_reached_through_a_tool_carries_its_calls(self, branching) -> None:
        handbook = next(r for r in branching["resources"] if r["name"] == "handbook")
        through = [a for a in handbook["accesses"] if a["how"] == "handbook_lookup"]

        assert through
        assert all(a["direction"] == "read" for a in through)
        assert "question" in through[0]["inputs"]

    def test_a_store_reached_in_a_steps_own_code_carries_its_accesses(self, branching):
        inbox = next(r for r in branching["resources"] if r["name"] == "inbox")

        assert inbox["access_count"] == 2
        assert all(a["how"] == "its own code" for a in inbox["accesses"])
        assert inbox["accesses"][0]["outputs"]["open_tickets"] == 128

    def test_a_write_recorded_in_code_says_which_way_it_went(self, branching) -> None:
        outbox = next(r for r in branching["resources"] if r["name"] == "outbox")

        assert [a["direction"] for a in outbox["accesses"]] == ["write", "write"]
        assert outbox["accesses"][0]["outputs"] == {"sent": True}

    def test_the_evaluations_reach_is_counted_apart(self, branching) -> None:
        """A rollout touches the real store, and counting it as work would overstate it."""
        web = next(r for r in branching["resources"] if r["name"] == "web")

        assert web["access_count"] == 0
        assert web["access_count_measuring"] == 3

    def test_a_step_reports_what_it_read_and_wrote_by_name(self, branching) -> None:
        assert node(branching, "triage", "intake")["over_the_record"]["reads"] == {"inbox": 2}
        assert node(branching, "triage", "publish")["over_the_record"]["writes"] == {"outbox": 2}


class TestHowMuchAStepMoved:
    """A step that counts what it moved reports numbers, and they are what moved."""

    def test_a_record_of_counts_names_them(self) -> None:
        from simple_agents.view.runs_overlay import _volume

        assert _volume({"rows": 67_353, "kept": 12}) == "rows 67,353 · kept 12"

    def test_a_collection_still_wins_over_a_number_beside_it(self) -> None:
        from simple_agents.view.runs_overlay import _volume

        assert _volume({"pool": [1, 2, 3], "tried": 40}) == "pool 3"

    def test_text_still_wins_where_there_is_more_of_it(self) -> None:
        from simple_agents.view.runs_overlay import _volume

        assert _volume({"body": "x" * 40, "why": "y" * 10}) == (
            "body 40 characters · why 10 characters"
        )

    def test_a_flag_is_not_a_count(self) -> None:
        from simple_agents.view.runs_overlay import _volume

        assert _volume({"sent": True}) == "1 field"


class TestWhatTheCodeSays:
    def test_a_tool_carries_its_signature_and_where_it_lives(self, branching) -> None:
        tools = node(branching, "triage", "research.pick_sources")["tools"]
        held = next(t for t in tools if t["name"] == "handbook_lookup")

        assert signature_line(held["code"]) == "handbook_lookup(question: str) -> list"
        assert held["code"]["where"]["at"] == "agent.py:50"
        assert held["code"]["where"]["library"] is False

    def test_a_step_carries_the_function_it_runs(self, branching) -> None:
        held = node(branching, "triage", "publish")["code"]

        assert held["name"] == "publish"
        assert "record_access" in held["source"]["text"]

    def test_a_library_tool_says_it_is_the_librarys(self, branching) -> None:
        tools = node(branching, "triage", "answer_directly")["tools"]
        held = next(t for t in tools if t["name"] == "consult")

        assert held["code"]["where"]["library"] is True

    def test_a_step_not_built_yet_has_no_code_to_show(self, branching) -> None:
        assert node(branching, "reindex", "dedupe")["code"] is None

    def test_a_return_naming_a_model_is_expanded_into_its_fields(self, branching) -> None:
        """`classify` hands on a `Ticket`, so what a row of it holds is readable from the
        code alone, before anything has run."""
        held = node(branching, "triage", "classify")["produces"]

        assert [f["name"] for f in held["fields"]] == [
            "topic",
            "needs_handbook",
            "questions",
        ]

    def test_a_credential_in_the_source_does_not_reach_the_page(self, branching) -> None:
        """`view.html` is a file a builder shares, so source goes through the run's rules."""
        from simple_agents.view.cards import _redactor

        scrub = _redactor()

        def leaky():
            token = "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # noqa: S105
            return token

        held = read_callable(leaky, lambda a: None, redact=scrub)

        assert "sk-ant-api03-AAAA" not in held["source"]["text"]

    def test_something_with_no_readable_source_is_left_out(self) -> None:
        assert read_callable(None, lambda a: None) is None
        assert read_callable(lambda x: x, lambda a: None)["name"] == "<lambda>"


class TestTheShapeTheBuilderAgreedTo:
    def test_a_matching_fingerprint_reads_as_unmoved(self, branching) -> None:
        assert pipeline(branching, "triage")["shape_moved"] is False

    def test_a_brief_naming_another_shape_reads_as_moved(self, tmp_path) -> None:
        import shutil

        target = tmp_path / "project"
        shutil.copytree(BRANCHING, target)
        brief = target / "brief.toml"
        brief.write_text(
            brief.read_text().replace(
                pipeline(assemble(BRANCHING), "triage")["fingerprint"], "sha256:0000"
            )
        )

        assert pipeline(assemble(target), "triage")["shape_moved"] is True

    def test_a_brief_naming_no_shape_says_nothing_either_way(self) -> None:
        assert pipeline(assemble(FIXTURES / "one-pipeline"), "summarise")["shape_moved"] is None

    def test_a_fingerprint_with_no_value_is_refused_naming_the_fix(self, tmp_path) -> None:
        from simple_agents.conformance.brief import Brief
        from simple_agents.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="graph_fingerprint"):
            Brief.from_data(
                {"tier": "prototype", "shape_confirmed": {"triage": "  "}},
                path=tmp_path / "brief.toml",
            )


class TestWalkingOneRun:
    def test_a_run_reads_in_the_order_it_happened(self) -> None:
        newest = sorted((BRANCHING / "runs").glob("dev/*/run_*"))[-1]
        held = walk_run(newest)

        assert [s["node_id"] for s in held["steps"]][:3] == [
            "intake",
            "classify",
            "research.pick_sources",
        ]
        assert held["outcome"] == "completed"

    def test_each_step_carries_what_it_did_inside_itself(self) -> None:
        newest = sorted((BRANCHING / "runs").glob("dev/*/run_*"))[-1]
        held = walk_run(newest)
        intake = next(s for s in held["steps"] if s["node_id"] == "intake")
        sources = next(s for s in held["steps"] if s["node_id"] == "research.pick_sources")

        assert [one["kind"] for one in intake["did"]] == ["access"]
        assert [one["name"] for one in sources["did"]] == [
            "handbook_lookup",
            "handbook_lookup",
        ]

    def test_a_step_the_run_never_reached_is_in_the_walk(self) -> None:
        newest = sorted((BRANCHING / "runs").glob("dev/*/run_*"))[-1]
        held = walk_run(newest)
        skipped = [s["node_id"] for s in held["steps"] if s["termination"] == "skipped"]

        assert "apologise" in skipped
        assert held["ran"] + held["skipped"] == len(held["steps"])

    def test_what_a_person_was_asked_is_in_the_walk(self) -> None:
        newest = sorted((BRANCHING / "runs").glob("dev/*/run_*"))[-1]
        held = walk_run(newest)
        publish = next(s for s in held["steps"] if s["node_id"] == "publish")

        assert any(one["kind"] == "asked" for one in publish["did"])

    def test_a_step_with_more_calls_than_fit_says_how_many(self, tmp_path) -> None:
        """A cap that says nothing reads as a step that made exactly twelve calls."""
        import json as _json

        from simple_agents.view.walk import MAX_CALLS_PER_STEP

        lines = [
            _json.dumps(
                {
                    "record_type": "node_execution",
                    "record_id": "n1",
                    "sequence": 99,
                    "node_id": "hunt",
                    "node_kind": "agent",
                    "inputs": None,
                    "outputs": None,
                    "termination": "finish",
                    "route": [],
                    "started_at": None,
                    "ended_at": None,
                }
            )
        ]
        for number in range(MAX_CALLS_PER_STEP + 5):
            lines.append(
                _json.dumps(
                    {
                        "record_type": "tool_call",
                        "record_id": f"t{number}",
                        "parent_id": "n1",
                        "sequence": number,
                        "tool_name": "search",
                        "inputs": {},
                        "outputs": "x",
                        "side_effect_class": "read_only",
                    }
                )
            )
        (tmp_path / "trajectory.jsonl").write_text("\n".join(lines))
        [step] = walk_run(tmp_path)["steps"]

        assert len(step["did"]) == MAX_CALLS_PER_STEP
        assert step["did_not_shown"] == 5

    def test_a_directory_with_no_trajectory_reads_as_nothing(self, tmp_path) -> None:
        assert walk_run(tmp_path) is None

    def test_the_page_carries_the_newest_run_and_what_came_out_wrong(self, branching) -> None:
        held = branching["walks"]
        wrong = {
            one["trajectory"].rsplit("/", 2)[-2] for one in branching["measured"]["went_wrong"]
        }

        assert any(name.startswith("run_") for name in held["walks"])
        assert wrong <= set(held["walks"])

    def test_every_other_run_is_named_and_not_carried(self, branching) -> None:
        held = branching["walks"]

        assert held["others"]
        assert not set(held["others"]) & set(held["walks"])

    def test_a_project_with_no_runs_carries_no_walk(self) -> None:
        assert walkable_runs(FIXTURES / "day-zero") == {"walks": {}, "others": []}


class TestWhatTheRunWrote:
    def test_the_newest_runs_workspace_is_read(self, branching) -> None:
        """A run that produces a file produces it there, and nothing on the page read it."""
        held = branching["workspace"]

        assert held["run"].startswith("run_")
        assert [f["name"] for f in held["files"]] == ["sent.txt"]
        assert held["bytes"] > 0

    def test_a_project_with_no_runs_has_no_workspace(self) -> None:
        assert assemble(FIXTURES / "day-zero")["workspace"] is None


class TestReadingIsCheapEnoughToDoAtEveryGate:
    def test_a_node_execution_is_read_without_parsing_its_payload(self) -> None:
        """One record can be megabytes and three of its fields matter, so the fast path is
        the one that runs and the parse is the fallback."""
        from simple_agents.view.record import _node_facts

        line = json.dumps(
            {
                "record_type": "node_execution",
                "record_id": "r1",
                "run_id": "x",
                "started_at": "2026-08-26T00:00:00.000Z",
                "ended_at": "2026-08-26T00:00:01.000Z",
                "node_id": "judge",
                "inputs": {"rows": ["x"] * 50},
                "outputs": None,
                "termination": None,
                "route": ["publish"],
                "loop": None,
                "resumed_from": None,
            }
        )
        held = _node_facts(line)

        assert held["node_id"] == "judge" and held["route"] == ["publish"]

    def test_a_payload_naming_the_same_fields_is_never_read_as_them(self) -> None:
        """The fast path reads the record's fields, and a payload can hold the same words."""
        from simple_agents.view.record import _node_facts, _parsed_node

        line = json.dumps(
            {
                "record_type": "node_execution",
                "record_id": "r1",
                "run_id": "x",
                "started_at": "2026-08-26T00:00:00.000Z",
                "ended_at": "2026-08-26T00:00:01.000Z",
                "node_id": "judge",
                "inputs": {"text": '"node_id": "impostor", "route": ["wrong"]'},
                "outputs": {"text": '"termination": "error"'},
                "termination": None,
                "route": ["publish"],
                "loop": None,
                "resumed_from": None,
            }
        )
        fast, parsed = _node_facts(line), _parsed_node(line)

        assert fast["node_id"] == parsed["node_id"] == "judge"
        assert fast["route"] == parsed["route"] == ["publish"]
        assert fast["termination"] == parsed["termination"] is None

    def test_a_line_the_fast_path_cannot_read_falls_back_to_parsing(self) -> None:
        from simple_agents.view.record import _node_facts, _parsed_node

        line = json.dumps(
            {
                "record_type": "node_execution",
                "record_id": "r1",
                "node_id": "judge",
                "route": ["publish"],
                "termination": None,
                "trailing": "x" * 4000,
            }
        )

        assert _node_facts(line) is None
        assert _parsed_node(line)["route"] == ["publish"]


class TestFollowingAnEvaluationLive:
    """What the live banner reads while an evaluation runs: the runner's own progress file."""

    def test_progress_the_runner_wrote_reaches_the_live_run(self, tmp_path) -> None:
        import json

        from simple_agents.view.runs_overlay import _evaluation_around

        holder = tmp_path / "runs" / "eval" / "eval_abc"
        rollout = holder / "t-x-0"
        rollout.mkdir(parents=True)
        (holder / "progress.json").write_text(
            json.dumps(
                {
                    "eval_id": "eval_abc",
                    "finished": 3,
                    "total": 8,
                    "resumed": 0,
                    "outcomes": {"correct": 2, "missed": 1},
                    "cost": 0.0004,
                    "currency": "USD",
                    "elapsed_s": 12.0,
                    "remaining_s": 20.0,
                    "updated_at": "2026-08-28T00:00:00Z",
                }
            )
        )
        held = _evaluation_around(rollout)
        assert held["total"] == 8 and held["rollouts_done"] == 3
        assert held["scored_right"] == 2
        assert held["remaining_s"] == 20.0 and held["currency"] == "USD"

    def test_an_evaluation_with_no_progress_file_carries_no_total(self, tmp_path) -> None:
        import json

        from simple_agents.view.runs_overlay import _evaluation_around

        holder = tmp_path / "runs" / "eval" / "eval_old"
        for name, ended in (("t-x-0", "2026-08-28T00:00:01Z"), ("t-x-1", None)):
            (holder / name).mkdir(parents=True)
            (holder / name / "manifest.json").write_text(json.dumps({"ended_at": ended}))
        held = _evaluation_around(holder / "t-x-1")
        assert held["total"] is None and held["rollouts_done"] == 1
        assert held["scored_right"] is None
