"""`simple-agents report`, the note under the checks, and FT-35.

`P3-22` stages 3 and 4. Stage 1 put the figures in the trajectory and the manifest; nothing
printed them without writing code, and nothing gated on the one member with no benign reading.

**FT-35 reads every run the pipeline as it now stands has made**, by the
`behaviour_fingerprint` each run records. One run does not show this: 8.8% of dogfood #4's
3,293 runs held an execution that produced nothing, so a check reading the newest run alone
would have passed nine times in ten. Reading every run ever would leave a project that fixed
the node failed for as long as it keeps its runs, and the cheapest way out of that is to delete
them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    ComputeBasis,
    Deterministic,
    FakeModelClient,
    PriceBasis,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    basis_from_manifest,
    runs,
    tool,
)
from simple_agents.cli import main
from simple_agents.conformance import (
    Outcome,
    Scope,
    UnfinishedAcross,
    run_checks,
    unfinished_across,
)
from simple_agents.cost import basis_to_manifest
from simple_agents.models import ToolCallRequest, fake_response
from simple_agents.cli.reporting import report_over_runs

from schemas import Answer

SPINS = Budget(max_steps=3, max_tokens=None, max_cost=None, max_wall_clock_ms=None)
# The evaluation the conformance fixtures replay, which is the results file this points at.
RESULTS = Path(__file__).parent / "fixtures/projects/conforming/evals/results/held-out.json"
PRICES = PriceBasis(currency="USD", input_uncached_per_mtok=1.0, output_per_mtok=2.0)


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def look_up(name: str) -> str:
    """Look one name up."""
    return f"nothing on {name}"


def _prompt(inputs, ctx):
    return Prompt.user("answer the question")


def _after(inputs, ctx):
    return {"saw": inputs}


def _talks(request):
    """A model that never calls a tool and never finishes, which is dogfood #4's case."""
    return fake_response(content="I think I should keep thinking about this.")


def _calls_a_tool(request):
    return fake_response(
        tool_calls=[ToolCallRequest(id="c", name="look_up", arguments={"name": "N"})]
    )


def _finishes(request):
    return fake_response(
        tool_calls=[ToolCallRequest(id="f", name="finish", arguments={"answer": "32 inches"})]
    )


def pipeline(*, prompt=_prompt, allow_unfinished: bool = False) -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                prompt,
                tools=[look_up],
                output_schema=Answer,
                allow_unknown=False,
                allow_unfinished=allow_unfinished,
                node_id="hunt",
                budget=SPINS,
                successors=["after"],
            ),
            Deterministic(_after, node_id="after"),
        ],
        budget=Budget.unbounded(),
    )


def newest(run_dir: Path) -> Path:
    """The run directory written last, which is how a test names the run it just made.

    Run ids carry a timestamp to the second and a random suffix, so sorting the directory
    names is not the order the runs were made in.
    """
    return runs(run_dir, nested=True)[0].path


def spin(
    run_dir: Path,
    *,
    times: int = 1,
    answer=_talks,
    built: Pipeline | None = None,
    basis=PRICES,
    role: str = "agent",
    live: bool = False,
    trigger: str | None = None,
) -> None:
    """Runs of one pipeline, under one directory, written the way a project writes them."""
    for _ in range(times):
        (built or pipeline()).run(
            {},
            envelope=RunEnvelope(run_dir=run_dir, cost_basis=basis, role=role, live=live),
            trigger=trigger,
            model=FakeModelClient(answer=answer, scripted=False),
        )


class TestTheBasisARunRecorded:
    """Cost per node over a directory of runs needs the basis the runs were priced against."""

    @pytest.mark.parametrize(
        "basis",
        [
            PriceBasis(
                currency="USD",
                input_uncached_per_mtok=3.0,
                output_per_mtok=15.0,
                input_cache_read_per_mtok=0.3,
                cache_write_per_mtok_by_ttl={"5m": 3.75},
            ),
            ComputeBasis(currency="USD", device="H100-80GB", device_count=2, hourly_rate=2.69),
        ],
    )
    def test_it_reads_back_what_the_manifest_recorded(self, basis) -> None:
        assert basis_from_manifest(basis_to_manifest(basis)) == basis

    def test_one_basis_per_model_reads_back_as_the_mapping_it_was(self) -> None:
        declared = {
            "a": PRICES,
            "b": ComputeBasis(currency="USD", device="RTX3090", device_count=1, hourly_rate=0.22),
        }

        assert basis_from_manifest(basis_to_manifest(declared)) == declared

    def test_a_kind_this_version_does_not_write_reports_no_basis(self) -> None:
        """A manifest from a later library names a basis this one cannot price against."""
        assert basis_from_manifest({"kind": "per_seat", "currency": "USD"}) is None
        assert basis_from_manifest(None) is None

    @pytest.mark.parametrize(
        "block",
        [
            {"kind": "price", "currency": "USD", "output_per_mtok": 15.0},
            {"kind": "price", "input_uncached_per_mtok": 3.0, "output_per_mtok": 15.0},
            {"kind": "compute", "currency": "USD", "device": "H100"},
        ],
    )
    def test_a_basis_missing_a_rate_prices_nothing(self, block) -> None:
        """A rate that is not there is not a rate of zero, so nothing is derived from it."""
        assert basis_from_manifest(block) is None


class TestWhatTheReportSays:
    def test_it_names_how_many_runs_it_read(self, tmp_path) -> None:
        spin(tmp_path, times=3)

        report = report_over_runs(tmp_path)

        assert report.read == 3
        assert report.found == 3
        assert "3 run(s)" in report.text()

    def test_a_scoped_report_names_what_it_left_out(self, tmp_path) -> None:
        """A silent cap reads as coverage, so both numbers are on the line."""
        spin(tmp_path, times=3)

        report = report_over_runs(tmp_path, last=2)

        assert (report.read, report.found) == (2, 3)
        assert "2 of 3 run(s)" in report.text()
        assert "last 2" in report.text()

    def test_a_report_over_one_jobs_runs_names_the_trigger(self, tmp_path) -> None:
        """What a timer spent, apart from what people asked for."""
        spin(tmp_path, times=2, trigger="nightly digest")
        spin(tmp_path, times=1)

        report = report_over_runs(tmp_path, trigger="nightly digest")

        assert (report.read, report.found) == (2, 3)
        assert "trigger nightly digest" in report.text()

    def test_the_node_that_produced_nothing_carries_what_it_spent(self, tmp_path) -> None:
        spin(tmp_path, times=2)

        text = report_over_runs(tmp_path).text()

        # Two executions of three steps each, and every call bought nothing.
        assert "2 (100%)" in text
        assert "produced nothing: 2 unit(s) of work, spending 6 of 6 model call(s)" in text
        assert (
            "2 of those 2 made no tool call, consultation or delegation, spending 6 "
            "model call(s) (FT-35)"
        ) in text

    def test_a_node_that_finished_carries_no_such_line(self, tmp_path) -> None:
        spin(tmp_path, answer=_finishes)

        text = report_over_runs(tmp_path).text()

        assert "made no tool call" not in text
        assert "hunt" in text

    def test_cost_per_node_is_derived_against_the_basis_the_runs_recorded(self, tmp_path) -> None:
        spin(tmp_path, times=2)

        report = report_over_runs(tmp_path)

        assert report.nodes["hunt"].cost is not None
        assert report.nodes["hunt"].cost.value > 0
        assert report.basis_reason is None
        assert "USD" in report.text()

    def test_runs_priced_two_ways_report_no_figure_per_node_and_say_why(self, tmp_path) -> None:
        spin(tmp_path, basis=PRICES)
        spin(
            tmp_path,
            basis=ComputeBasis(currency="USD", device="RTX3090", device_count=1, hourly_rate=0.22),
        )

        report = report_over_runs(tmp_path)

        assert "written against 2 different cost bases" in report.text()
        # Each run still recorded what it cost, so the total is what the runs said.
        assert report.spend["USD"] > 0

    def test_a_basis_it_cannot_price_against_is_not_reported_as_no_basis(self, tmp_path) -> None:
        """Three things make a basis unusable, and telling a project to declare one it already
        declared is advice about the wrong one."""
        spin(tmp_path, times=2)
        for path in tmp_path.glob("**/manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["cost_basis"] = {"kind": "per_seat", "currency": "USD"}
            path.write_text(json.dumps(manifest), encoding="utf-8")

        text = report_over_runs(tmp_path).text()

        assert "cannot price against, of kind 'per_seat'" in text
        assert "recorded no cost basis" not in text

    def test_runs_with_no_basis_at_all_say_what_declares_one(self, tmp_path) -> None:
        spin(tmp_path, basis=None, times=2)

        assert "recorded no cost basis" in report_over_runs(tmp_path).text()

    def test_the_roles_are_named_where_more_than_one_was_read(self, tmp_path) -> None:
        spin(tmp_path, times=2)
        spin(tmp_path, role="labelling")

        text = report_over_runs(tmp_path).text()

        assert "roles: agent 2, labelling 1" in text
        assert report_over_runs(tmp_path, role="agent").read == 2

    def test_runs_made_by_a_slice_are_named(self, tmp_path) -> None:
        """A rung runs under the same role and keeps its node ids, so `roles` cannot show it.

        Its `reach` and every count over it are figures with the agent's names over a smaller
        graph, and a reader of this table has nothing else to tell them apart.
        """
        whole = pipeline()
        spin(tmp_path, times=2)
        spin(tmp_path, built=whole.slice(start=whole.graph.terminal))

        text = report_over_runs(tmp_path).text()

        assert "1 of them made by a slice of a pipeline" in text
        assert report_over_runs(tmp_path).sliced == 1

    def test_a_directory_of_whole_runs_says_nothing_about_slices(self, tmp_path) -> None:
        spin(tmp_path, times=2)

        assert report_over_runs(tmp_path).sliced == 0
        assert "slice of a pipeline" not in report_over_runs(tmp_path).text()

    def test_live_runs_are_separable(self, tmp_path) -> None:
        spin(tmp_path, times=2)
        spin(tmp_path, live=True)

        assert report_over_runs(tmp_path, live=True).read == 1
        assert report_over_runs(tmp_path, live=False).read == 2
        assert "1 of them made by an end user" in report_over_runs(tmp_path).text()

    def test_a_run_whose_trajectory_cannot_be_read_is_named_rather_than_counted(
        self, tmp_path
    ) -> None:
        spin(tmp_path, times=2)
        next(tmp_path.glob("**/trajectory.jsonl")).write_text("{not json\n", encoding="utf-8")

        report = report_over_runs(tmp_path)

        assert report.read == 1
        assert len(report.unread) == 1
        assert "recorded no trajectory this could read" in report.text()


class TestWhatEachToolWasEverCalledFrom:
    """A capability that was built and then stopped being reached.

    Dogfood #4 built four candidate sources behind one tool at the builder's prompting, and
    `uncommon_books` appears in 2 of the run directory's 3,293 manifests and is called in 1.
    A per-node count says how many calls a node made, never to what, so nothing said this.
    """

    def test_a_tool_registered_and_never_called_shows_both_numbers(self, tmp_path) -> None:
        spin(tmp_path, times=2)

        report = report_over_runs(tmp_path)

        assert report.tools["look_up"] == (2, 0)
        assert "look_up" in report.text()

    def test_a_tool_that_was_called_counts_the_runs_rather_than_the_calls(self, tmp_path) -> None:
        """A node calling one tool three times in a run is one run that reached it."""
        spin(tmp_path, times=2, answer=_calls_a_tool)

        assert report_over_runs(tmp_path).tools["look_up"] == (2, 2)

    def test_the_record_carries_both(self, tmp_path) -> None:
        spin(tmp_path, times=1)

        assert report_over_runs(tmp_path).to_record()["tools"]["look_up"] == {
            "registered_in": 1,
            "called_in": 0,
        }

    def test_a_directory_with_no_tools_prints_no_block(self, tmp_path) -> None:
        spin(
            tmp_path,
            times=1,
            built=Pipeline([Deterministic(_after, node_id="after")], budget=Budget.unbounded()),
        )

        assert "registered in" not in report_over_runs(tmp_path).text()


class TestTheCommand:
    def test_it_reads_a_directory_of_runs(self, tmp_path, capsys) -> None:
        spin(tmp_path, times=2)

        assert main(["report", str(tmp_path)]) == 0
        assert "hunt" in capsys.readouterr().out

    def test_it_reads_one_run(self, tmp_path, capsys) -> None:
        spin(tmp_path)
        one = next(tmp_path.glob("**/manifest.json")).parent

        assert main(["report", str(one)]) == 0
        assert "1 run(s)" in capsys.readouterr().out

    def test_it_reads_a_project_root_by_looking_under_runs(self, tmp_path, capsys) -> None:
        spin(tmp_path / "runs", times=2)

        assert main(["report", str(tmp_path)]) == 0
        assert "2 run(s)" in capsys.readouterr().out

    def test_it_reads_a_results_file(self, capsys) -> None:
        results = RESULTS

        assert main(["report", str(results)]) == 0
        printed = capsys.readouterr().out
        assert "rollout(s) on split" in printed
        assert "accuracy" in printed

    def test_a_results_file_as_json_carries_the_figures_and_not_the_rollouts(self, capsys) -> None:
        main(["report", str(RESULTS), "--json"])
        record = json.loads(capsys.readouterr().out)

        assert record["metrics"]
        assert "rollouts" not in record
        assert record["nodes"]["hunt"]["node_kind"] == "agent"

    def test_runs_as_json_carry_what_was_read(self, tmp_path, capsys) -> None:
        spin(tmp_path, times=2)

        main(["report", str(tmp_path), "--json"])
        record = json.loads(capsys.readouterr().out)

        assert record["runs"]["read"] == 2
        assert record["nodes"]["hunt"]["unfinished_executions"] == 2
        assert record["totals"]["model_calls"] == 6

    def test_a_path_holding_neither_exits_two_and_says_what_it_reads(
        self, tmp_path, capsys
    ) -> None:
        assert main(["report", str(tmp_path)]) == 2
        assert "reads a run directory" in capsys.readouterr().err

    @pytest.mark.parametrize("name", ["trajectory.jsonl", "manifest.json"])
    def test_a_run_s_own_file_names_the_directory_that_holds_it(
        self, tmp_path, capsys, name
    ) -> None:
        """The file most often pointed at here. Both used to raise rather than report."""
        spin(tmp_path)
        one = next(tmp_path.glob(f"**/{name}"))

        assert main(["report", str(one)]) == 2
        printed = capsys.readouterr().err
        assert "is not a results file" in printed
        assert str(one.parent) in printed


class TestWhichRunsTheGateReads:
    """The decision of 2026-08-19: the runs this pipeline made, rather than every run ever."""

    def test_it_reads_the_runs_of_the_pipeline_as_it_stands(self, tmp_path) -> None:
        spin(tmp_path, times=2)
        spin(tmp_path, built=pipeline(prompt=_other_prompt), answer=_finishes)

        found = unfinished_across(tmp_path)

        assert found.scoped == 3
        assert found.read == 1
        assert found.other_pipeline == 2
        assert not found.spinning()

    def test_a_project_that_fixed_the_node_is_measured_on_the_runs_since(self, tmp_path) -> None:
        """The old runs are still on disk. Nothing has to be deleted to pass."""
        spin(tmp_path, times=3)
        assert unfinished_across(tmp_path).spinning()

        spin(tmp_path, built=pipeline(prompt=_other_prompt), answer=_calls_a_tool)

        assert not unfinished_across(tmp_path).spinning()
        assert len(runs(tmp_path, nested=True)) == 4

    def test_what_it_read_is_named(self, tmp_path) -> None:
        spin(tmp_path / "runs", times=2)

        assert unfinished_across(tmp_path / "runs").covered() == "2 run(s) under runs/"

    def test_a_scope_narrows_it_and_says_so(self, tmp_path) -> None:
        spin(tmp_path, times=3)

        found = unfinished_across(tmp_path, Scope(last=2))

        assert found.read == 2
        assert "2 of the 3 run(s)" in found.covered()
        assert "narrowed by last 2" in found.covered()

    def test_a_run_older_than_the_counts_is_unread_rather_than_clean(self, tmp_path) -> None:
        spin(tmp_path, times=2)
        for path in tmp_path.glob("**/manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["format_version"] = "0.29"
            manifest.pop("unfinished")
            path.write_text(json.dumps(manifest), encoding="utf-8")

        found = unfinished_across(tmp_path)

        assert (found.read, found.without_counts) == (0, 2)
        assert not found.spinning()

    def test_every_run_it_did_not_read_is_accounted_for(self, tmp_path) -> None:
        """A denominator that does not close is what this whole item exists to prevent, so the
        counts under the figure have to add up to the runs on disk."""
        spin(tmp_path)
        broken = newest(tmp_path) / "manifest.json"
        spin(tmp_path)
        in_flight = newest(tmp_path) / "manifest.json"
        spin(tmp_path, role="labelling")
        spin(tmp_path, built=pipeline(prompt=_other_prompt), answer=_finishes)

        broken.write_text("{not json", encoding="utf-8")
        manifest = json.loads(in_flight.read_text(encoding="utf-8"))
        manifest["outcome"] = None
        in_flight.write_text(json.dumps(manifest), encoding="utf-8")

        found = unfinished_across(tmp_path)

        accounted = (
            found.read
            + found.other_role
            + found.unreadable
            + found.still_running
            + found.other_pipeline
            + found.without_counts
        )
        assert accounted == found.found == 4
        assert "under another role" in found.covered()
        assert "whose manifest nothing could read" in found.covered()

    def test_a_labelling_run_is_not_read_as_the_agents(self, tmp_path) -> None:
        spin(tmp_path, role="labelling")

        assert unfinished_across(tmp_path).read == 0
        assert unfinished_across(tmp_path, Scope(role="labelling")).read == 1


def _other_prompt(inputs, ctx):
    """A prompt whose source differs, which is what a project changes to fix this."""
    return Prompt.user("answer the question, and call look_up first")


class TestTheGate:
    def _project(self, tmp_path: Path, **kwargs) -> Path:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\n', encoding="utf-8")
        spin(tmp_path / "runs", **kwargs)
        return tmp_path

    def _check(self, root: Path, scope: Scope | None = None):
        report = run_checks(root, scope=scope)
        return [c for c in report.checks if c.entry_id == "FT-35"][0]

    def test_it_fires_on_a_node_that_spent_a_whole_allowance_without_acting(self, tmp_path) -> None:
        found = self._check(self._project(tmp_path, times=2))

        assert found.outcome is Outcome.FAILED
        [finding] = found.findings
        assert "`hunt` produced no output in `2` unit(s)" in finding.message
        assert "`6` model call(s)" in finding.message
        assert "2 run(s) under runs/" in finding.message

    def test_a_node_that_acted_and_ran_out_does_not_fire_it(self, tmp_path) -> None:
        found = self._check(self._project(tmp_path, answer=_calls_a_tool))

        assert found.outcome is Outcome.PASSED
        assert "No node spent an allowance without acting" in (found.detail or "")

    def test_the_waiver_turns_it_off_for_that_node(self, tmp_path) -> None:
        found = self._check(self._project(tmp_path, built=pipeline(allow_unfinished=True), times=2))

        assert found.outcome is Outcome.PASSED
        assert "hunt" in (found.detail or "")

    def test_the_waiver_is_recorded_in_the_manifest(self, tmp_path) -> None:
        spin(tmp_path, built=pipeline(allow_unfinished=True))

        manifest = json.loads(next(tmp_path.glob("**/manifest.json")).read_text(encoding="utf-8"))
        entries = {entry["node_id"]: entry for entry in manifest["nodes"]}
        assert entries["hunt"]["allow_unfinished"] is True
        # Only an `AgentNode` can end a unit of work without producing an output.
        assert "allow_unfinished" not in entries["after"]

    def test_a_project_with_no_run_is_blocked_rather_than_failed(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\n', encoding="utf-8")

        found = self._check(tmp_path)

        assert found.outcome is Outcome.BLOCKED
        assert "FT-13" in (found.detail or "")

    def test_runs_older_than_the_counts_say_so_rather_than_passing(self, tmp_path) -> None:
        """A manifest that predates the figures is unread. Reading it as clean would say the
        project produced something it never counted."""
        root = self._project(tmp_path, times=2)
        for path in (root / "runs").glob("**/manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["format_version"] = "0.30"
            path.write_text(json.dumps(manifest), encoding="utf-8")

        found = self._check(root)

        assert found.outcome is Outcome.BLOCKED
        assert "written before the manifest carried these counts" in (found.detail or "")

    def test_runs_that_are_not_the_agents_say_so(self, tmp_path) -> None:
        """Every check reads the agent's runs, and a project whose runs are all a labelling
        pass has runs. Saying it has none would be false."""
        root = self._project(tmp_path, role="labelling", times=2)

        found = self._check(root)

        assert found.outcome is Outcome.BLOCKED
        assert "none declaring role='agent'" in (found.detail or "")

    def test_a_manifest_nothing_can_read_says_so(self, tmp_path) -> None:
        """It is the agent's run, and saying it is not would send the reader to the envelope."""
        root = self._project(tmp_path, times=2)
        for path in (root / "runs").glob("**/manifest.json"):
            path.write_text("{not json", encoding="utf-8")

        found = self._check(root)

        assert found.outcome is Outcome.BLOCKED
        assert "carry a manifest nothing could read" in (found.detail or "")

    def test_a_scope_reaches_it_and_no_other_check(self, tmp_path) -> None:
        root = self._project(tmp_path, times=2)

        assert self._check(root, Scope(since="2099-01-01")).outcome is Outcome.BLOCKED
        assert self._check(root, Scope(since="2000-01-01")).outcome is Outcome.FAILED

    def test_the_command_takes_the_same_filters(self, tmp_path, capsys) -> None:
        """`--since` reaches FT-35, and the report says what it left the check with."""
        root = self._project(tmp_path, times=2)

        main(["check", str(root), "--since", "2099-01-01"])
        printed = capsys.readouterr().out

        assert "blocked  FT-35" in printed
        assert "none left to read after since 2099-01-01" in printed


class TestTheNoteUnderTheChecks:
    def test_it_reports_what_the_gate_does_not(self, tmp_path) -> None:
        """A cap that binds after real work is the cap doing its job, so it reports."""
        (tmp_path / "brief.toml").write_text('tier = "prototype"\n', encoding="utf-8")
        spin(tmp_path / "runs", answer=_calls_a_tool, times=2)

        notes = " ".join(run_checks(tmp_path).notes)

        assert "hunt 2 execution(s), spending 6 model call(s)" in notes
        assert "simple-agents report runs/" in notes

    def test_it_stays_quiet_where_the_gate_has_already_said_it(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\n', encoding="utf-8")
        spin(tmp_path / "runs", times=2)

        notes = " ".join(run_checks(tmp_path).notes)

        assert "produced no output and spent to do it" not in notes

    def test_a_run_where_everything_finished_prints_no_note(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\n', encoding="utf-8")
        spin(tmp_path / "runs", answer=_finishes, times=2)

        notes = " ".join(run_checks(tmp_path).notes)

        assert "produced no output" not in notes


class TestAFanOutWhoseItemsProducedNothing:
    """An item is a unit of work, and a fan-out whose items spin records no termination.

    The node completes, `FanOutResult.ok` is true and `failures` is empty, so before this item
    every figure the library reported said the node was fine. Dogfood #4's judging pass is a
    fan-out.
    """

    def _fan_out(self, tmp_path: Path, *, waived: bool = False) -> None:
        def judge_one(inputs, ctx):
            return Prompt.user("judge {book}", book=inputs["book"])

        built = Pipeline(
            [
                AgentNode(
                    judge_one,
                    tools=[look_up],
                    output_schema=Answer,
                    allow_unknown=False,
                    allow_unfinished=waived,
                    node_id="judge",
                    over="book",
                    budget=Budget(
                        max_steps=30, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                    ),
                    budget_per_item=SPINS,
                )
            ],
            budget=Budget.unbounded(),
        )
        built.run(
            {"book": ["Ubik", "Solaris"]},
            envelope=RunEnvelope(run_dir=tmp_path / "runs", cost_basis=PRICES),
            model=FakeModelClient(answer=_talks, scripted=False),
        )

    def test_the_node_itself_records_no_termination(self, tmp_path) -> None:
        self._fan_out(tmp_path)

        manifest = json.loads(
            next((tmp_path / "runs").glob("**/manifest.json")).read_text(encoding="utf-8")
        )
        assert manifest["unfinished"]["judge"] == {
            "executions": 0,
            "items": 2,
            "without_tool_calls": 2,
            "model_calls": 6,
            "model_calls_without_tool_calls": 6,
        }

    def test_the_gate_fires_on_the_items(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\n', encoding="utf-8")
        self._fan_out(tmp_path)

        [found] = [c for c in run_checks(tmp_path).checks if c.entry_id == "FT-35"]

        assert found.outcome is Outcome.FAILED
        assert "`judge` produced no output in `2` unit(s)" in found.findings[0].message

    def test_the_waiver_reaches_the_items(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\n', encoding="utf-8")
        self._fan_out(tmp_path, waived=True)

        [found] = [c for c in run_checks(tmp_path).checks if c.entry_id == "FT-35"]

        assert found.outcome is Outcome.PASSED

    def test_the_report_names_the_items_on_their_own_line(self, tmp_path) -> None:
        self._fan_out(tmp_path)

        text = report_over_runs(tmp_path / "runs").text()

        # The node's own row shows no unfinished execution, since it recorded none, so the
        # line under it has to say what the items were rather than referring to the row.
        assert "2 unit(s) of work, 2 of them fan-out item(s)" in text
        assert "2 of those 2 made no tool call" in text


class TestARunThatHasNotFinished:
    """A run writes what it produced when it ends, so one in flight is not a clean run."""

    def _in_flight(self, tmp_path: Path) -> None:
        for path in (tmp_path / "runs").glob("**/manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["outcome"] = None
            manifest["unfinished"] = {}
            path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_it_is_not_counted_as_a_run_that_produced_something(self, tmp_path) -> None:
        spin(tmp_path / "runs", times=2)
        self._in_flight(tmp_path)

        found = unfinished_across(tmp_path / "runs")

        assert (found.read, found.still_running) == (0, 2)
        assert not found.spinning()

    def test_the_check_says_so_rather_than_passing(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\n', encoding="utf-8")
        spin(tmp_path / "runs", times=2)
        self._in_flight(tmp_path)

        [found] = [c for c in run_checks(tmp_path).checks if c.entry_id == "FT-35"]

        assert found.outcome is Outcome.BLOCKED
        assert "have not finished" in (found.detail or "")

    def test_a_finished_run_beside_it_is_still_read(self, tmp_path) -> None:
        spin(tmp_path / "runs", times=2)
        self._in_flight(tmp_path)
        spin(tmp_path / "runs")

        found = unfinished_across(tmp_path / "runs")

        assert (found.read, found.still_running) == (1, 2)
        assert found.spinning()
        assert "2 that had not finished" in found.covered()


class TestTheDocumentedTableIsWhatIsPrinted:
    """`docs/run-envelope.md` §8.4 shows a report, and nothing ran it until this test.

    The figures in it are one project's and cannot be reproduced here. What is pinned is the
    part that moves when a column is added or renamed: the header, and the shape of the lines
    printed under a node.
    """

    def documented(self) -> list[str]:
        from simple_agents import docs_path

        text = (Path(docs_path()) / "run-envelope.md").read_text(encoding="utf-8")
        section = text[text.index("### 8.4 What every run did") :]
        [block] = [fenced for fenced in section.split("```") if "simple-agents report:" in fenced]
        return block.strip("\n").splitlines()

    def test_the_column_header_matches(self, tmp_path) -> None:
        spin(tmp_path, times=2)

        [documented] = [line for line in self.documented() if line.strip().startswith("node ")]
        [printed] = [
            line
            for line in report_over_runs(tmp_path).text().splitlines()
            if line.strip().startswith("node ")
        ]

        # The node column is as wide as the widest id, so the columns after it are compared
        # rather than the leading spaces.
        assert documented.split()[1:] == printed.split()[1:]

    def test_every_line_under_a_node_is_one_the_code_prints(self, tmp_path) -> None:
        """The documented lines are the ones `unfinished_lines` renders, word for word."""
        from simple_agents.evaluation.per_node import NodeMetrics, unfinished_lines

        look_closer = NodeMetrics(
            node_id="look_closer",
            node_kind="agent",
            executions=3063,
            model_calls=15610,
            unfinished_executions=257,
            unfinished_without_tool_calls=188,
            unfinished_model_calls=4626,
            unfinished_model_calls_without_tool_calls=3384,
        )
        hunt = NodeMetrics(
            node_id="hunt",
            node_kind="agent",
            executions=104,
            model_calls=1411,
            unfinished_executions=28,
            unfinished_without_tool_calls=1,
            unfinished_model_calls=772,
            unfinished_model_calls_without_tool_calls=23,
            tools_that_never_succeeded={"consult": 1},
        )
        printed = unfinished_lines(look_closer) + unfinished_lines(hunt)
        indented = [
            line.strip()
            for line in self.documented()
            if line.startswith("     ") and not line.strip().startswith("node ")
        ]

        assert indented == printed


class TestTheDocumentedGateLinesAreWhatIsPrinted:
    """`docs/conformance.md` §3.7 shows what a passing FT-35 says, and nothing ran it.

    The numbers are one project's; the sentence around them is the code's. It drifted twice in
    one session, both times because a message was reworded and the sample was not.
    """

    def documented(self) -> str:
        from simple_agents import docs_path

        text = (Path(docs_path()) / "conformance.md").read_text(encoding="utf-8")
        section = text[text.index("### 3.7 FT-35 and which runs it reads") :]
        # The fenced block, which is the one between the first pair of fences after the
        # heading rather than any prose above it that names the entry.
        [block] = [
            fenced
            for fenced in section.split("```")[1::2]
            if fenced.strip().startswith("pass  FT-35")
        ]
        return " ".join(block.split())

    def test_the_pass_line_is_what_the_check_renders(self) -> None:
        from simple_agents.conformance.checks import _what_was_read

        # The figures the block shows, which is what its own numbers have to be over.
        found = UnfinishedAcross(
            where="runs",
            found=3293,
            scoped=3261,
            read=195,
            other_role=32,
            other_pipeline=3066,
        )

        assert " ".join(_what_was_read(found).split()) in self.documented()
