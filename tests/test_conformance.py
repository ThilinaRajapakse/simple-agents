"""The twenty-nine checks, against project fixtures produced by replaying a real evaluation.

`scripts/build_conformance_fixtures.py` writes them. `conforming/` passes them all, and every
other fixture is that one with a single mutation, so a test that fires a check names the one
thing it changed. A check that has only ever been shown to fire proves as little as one that
has only ever been shown to stay quiet, so every check here is exercised both ways.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from simple_agents.pipeline.recording import _node_entries
from simple_agents.conformance import (
    DECISION_KINDS,
    Outcome,
    Tier,
    kind_names,
    required_at,
    run_checks,
    taxonomy,
)
from simple_agents.conformance.artifacts import Artifacts, _latest_run, runs_by_pipeline
from simple_agents.conformance.brief import Brief
from simple_agents.conformance.decisions import PRODUCING_KINDS, decisions_from
from simple_agents.conformance.produced import produced_across
from simple_agents.conformance.run import _produced_by_no_decision
from simple_agents.conformance.checks import (
    CHECKS,
    COMMON_RECORD_FIELDS,
    Context,
    RECORD_TYPES,
    _absence_waived,
    _answering_nodes,
    _floats,
    _where_absence_is_declared,
)
from simple_agents.errors import ConfigurationError
from simple_agents import Budget, Deterministic, LLMNode, Maybe, Pipeline, Prompt
from pydantic import BaseModel

PROJECTS = Path(__file__).parent / "fixtures" / "projects"


def project(name: str) -> Path:
    path = PROJECTS / name
    if not path.exists():
        pytest.skip(f"no fixture {name}; run scripts/build_conformance_fixtures.py")
    return path


def _by_id(report, entry_id: str):
    """One check out of a report by the entry it reports on, so adding a check cannot move it."""
    return [c for c in report.checks if c.entry_id == entry_id][0]


def copied(name: str, tmp_path: Path) -> Path:
    """A fixture copied somewhere writable, for a test that has to change one of its files."""
    target = tmp_path / name
    shutil.copytree(project(name), target)
    return target


def outcomes(name: str) -> dict[str, Outcome]:
    report = run_checks(project(name))
    return {check.entry_id: check.outcome for check in report.checks}


class TestTheConformingProject:
    """The fixture every mutation is measured against."""

    def test_all_ten_pass(self) -> None:
        report = run_checks(project("conforming"))

        # FT-31, FT-37 and FT-38 fire at stage `ship` and this project is at `measure`;
        # FT-39 passes with no comments.toml on disk, FT-40 with no agent.py, since a
        # project that declares no pipeline in code has declared no step it has not built,
        # FT-42 because every name under `produces` was recorded by a run, and FT-45 because
        # the results file names the pipeline its factory registers.
        assert [c.outcome for c in report.checks].count(Outcome.PASSED) == 26
        assert [c.entry_id for c in report.checks if c.outcome is Outcome.NOT_APPLICABLE] == [
            "FT-31",
            "FT-37",
            "FT-38",
        ]
        assert report.ok

    def test_the_report_names_the_artifacts_it_read(self) -> None:
        """Which run and which results file, so a passing report is checkable by hand."""
        report = run_checks(project("conforming"))
        read = {c.entry_id: c.read for c in report.checks}

        # The evaluation directory is named for a fresh uuid, so the name is read off the
        # fixture rather than transcribed into the test.
        latest = sorted(project("conforming").glob("runs/**/e3-2/manifest.json"))[0]
        where = str(latest.relative_to(project("conforming")))
        assert read["FT-14"] == (where,)
        assert read["FT-02"] == ("evals/results/held-out.json",)
        assert len(read["FT-07"]) == 10  # the results file and nine rollout trajectories

    def test_a_metric_with_no_denominator_does_not_fire_ft_06(self, tmp_path) -> None:
        """`recall` over a split where every answer is absent reports no value and no interval.

        The library writes `interval: null` with a reason, which is correct output and is a
        metric-shaped object carrying no interval.
        """
        root = copied("conforming", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        results["metrics"]["recall"] = {
            "name": "recall",
            "interval": None,
            "reason": "No rollouts fall under rollouts of examples where a value exists.",
        }
        path.write_text(json.dumps(results))

        assert run_checks(root).ok

    def test_a_declared_census_does_not_fire_ft_06(self, tmp_path) -> None:
        """A count over one run has a value and no interval, and says so in its declaration.

        The alternative is the number living in a print statement, where FT-06, `compare()` and
        the fingerprint cannot see it at all.
        """
        root = copied("conforming", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        results["metrics"]["dropped"] = {
            "name": "dropped",
            "interval": None,
            "numerator": 47,
            "estimated": False,
            "reason": "a count over this run, not an estimate of a rate",
        }
        path.write_text(json.dumps(results))

        assert run_checks(root).ok

    def test_a_reported_value_with_a_bare_reason_still_fires_ft_06(self, tmp_path) -> None:
        """The reason is not a passphrase. A figure reporting a number declares why it has none.

        `reason` alone used to pass: any non-empty string did, so a bare percentage carrying
        `reason: "n/a"` met the check.
        """
        root = copied("conforming", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        results["metrics"]["dropped"] = {
            "name": "dropped",
            "interval": None,
            "numerator": 47,
            "estimated": True,
            "reason": "n/a",
        }
        path.write_text(json.dumps(results))

        report = run_checks(root)
        assert not report.ok
        assert any(f.entry_id == "FT-06" for c in report.checks for f in c.findings)

    def test_a_node_with_no_label_does_not_fire_ft_06(self) -> None:
        """`accuracy` is `null` on a node no example labels, which reports no rate at all.

        The conforming project labels `hunt` and not `verify`, so one node carries the rate
        and the other carries nothing, and FT-06 fires on neither.
        """
        results = json.loads((project("conforming") / "evals/results/held-out.json").read_text())
        assert results["nodes"]["verify"]["accuracy"] is None
        assert results["nodes"]["hunt"]["accuracy"] is not None

        report = run_checks(project("conforming"))

        assert report.ok

    def test_a_skipped_node_recording_no_seed_does_not_fire_ft_07(self, tmp_path) -> None:
        """A node the run routed around sampled nothing, and `termination` says so.

        Reading it as unseeded left a project two ways to pass, and the cheap one was to stop
        routing around the node: 1,584 model calls in one evaluation arm, buying nothing
        (`DF4-D6`).
        """
        root = copied("conforming", tmp_path)
        for trajectory in root.glob("runs/**/trajectory.jsonl"):
            records = [json.loads(line) for line in trajectory.read_text().splitlines()]
            for record in records:
                if record["record_type"] == "node_execution":
                    record["node_kind"] = "llm"
                    record["termination"] = "skipped"
                    record["seed"] = None
            trajectory.write_text("\n".join(json.dumps(r) for r in records) + "\n")

        report = run_checks(root)

        assert next(c for c in report.checks if c.entry_id == "FT-07").outcome is Outcome.PASSED

    def test_a_node_that_ran_and_recorded_no_seed_still_fires_ft_07(self, tmp_path) -> None:
        """The exemption is `skipped` rather than a null seed on any agentic node."""
        root = copied("conforming", tmp_path)
        for trajectory in root.glob("runs/**/trajectory.jsonl"):
            records = [json.loads(line) for line in trajectory.read_text().splitlines()]
            for record in records:
                if record["record_type"] == "node_execution":
                    record["node_kind"] = "llm"
                    record["termination"] = "finish"
                    record["seed"] = None
            trajectory.write_text("\n".join(json.dumps(r) for r in records) + "\n")

        report = run_checks(root)

        assert next(c for c in report.checks if c.entry_id == "FT-07").outcome is Outcome.FAILED

    def test_a_deterministic_node_recording_no_seed_does_not_fire_ft_07(self, tmp_path) -> None:
        """`seed` is `null` on a node that does not sample, and present so it says so."""
        root = copied("conforming", tmp_path)
        for trajectory in root.glob("runs/**/trajectory.jsonl"):
            records = [json.loads(line) for line in trajectory.read_text().splitlines()]
            for record in records:
                if record["record_type"] == "node_execution":
                    record["node_kind"] = "deterministic"
                    record["seed"] = None
            trajectory.write_text("\n".join(json.dumps(r) for r in records) + "\n")

        report = run_checks(root)

        assert next(c for c in report.checks if c.entry_id == "FT-07").outcome is Outcome.PASSED


class TestEachCheckFires:
    """One fixture per check, each a single mutation away from the conforming one."""

    @pytest.mark.parametrize(
        "fixture,entry",
        [
            ("no-trajectory", "FT-13"),
            ("unreadable-trajectory", "FT-13"),
            ("floating-model", "FT-14"),
            ("unversioned-prompt", "FT-15"),
            ("one-split", "FT-02"),
            ("contaminated-split", "FT-03"),
            ("no-absent-examples", "FT-04"),
            ("bare-metric", "FT-06"),
            ("no-rollout-seeds", "FT-07"),
            ("no-node-seed", "FT-07"),
        ],
    )
    def test_it_fails_and_nothing_else_does(self, fixture: str, entry: str) -> None:
        found = outcomes(fixture)

        assert found[entry] is Outcome.FAILED
        assert [e for e, o in found.items() if o is Outcome.FAILED] == [entry]

    def test_ft_03_names_how_many_pairs_and_the_threshold_applied(self) -> None:
        report = run_checks(project("contaminated-split"))
        message = report.failed[0].findings[0].message

        assert "`1` held-out examples" in message
        assert "`0.8`" in message

    def test_an_evaluation_that_declared_no_threshold_ran_no_check_and_says_so(
        self, tmp_path
    ) -> None:
        """The project decided what counts as too similar some other way, and said so.

        `n/a` and not `pass`: the example set is on disk and the property is computable, so
        the honest report is that no check was made. It printed `pass` until 2026-08-25, on a
        project whose 14 results files all carried `contamination: null`.
        """
        root = copied("conforming", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        results["contamination"] = None
        path.write_text(json.dumps(results))

        report = run_checks(root)
        result = next(c for c in report.checks if c.entry_id == "FT-03")

        assert result.outcome is Outcome.NOT_APPLICABLE
        assert "ran no contamination check and this check made none" in (result.detail or "")
        assert report.ok

    def test_a_pipeline_waiving_the_absence_branch_does_not_fire_ft_04(self, tmp_path) -> None:
        """`allow_unknown=False` says this output has no absent state, so no example has one."""
        root = copied("no-absent-examples", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        for node in results["config"]["nodes"]:
            if node["node_kind"] in ("llm", "agent"):
                node["allow_unknown"] = False
        path.write_text(json.dumps(results))

        report = run_checks(root)

        assert report.ok

    def test_only_the_answering_node_has_to_waive_it(self, tmp_path) -> None:
        """`P3-46`. A lookup on the way to the answer may find nothing and declares nothing.

        Dogfood #5's shipped pipeline had eight model-calling nodes, two of which genuinely
        could be absent, so the all-or-nothing waiver could not be made at all and twenty
        invented absence examples were written instead.
        """
        root = copied("no-absent-examples", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        by_id = {node["node_id"]: node for node in results["config"]["nodes"]}
        by_id["verify"]["allow_unknown"] = False
        by_id["hunt"]["allow_unknown"] = True
        path.write_text(json.dumps(results))

        report = run_checks(root)

        assert report.ok

    def test_waiving_the_lookup_alone_does_not_waive_the_answer(self, tmp_path) -> None:
        """The other direction: the gate is about the scored answer and nothing else."""
        root = copied("no-absent-examples", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        by_id = {node["node_id"]: node for node in results["config"]["nodes"]}
        by_id["hunt"]["allow_unknown"] = False
        path.write_text(json.dumps(results))

        report = run_checks(root)

        assert not report.ok
        assert any(c.entry_id == "FT-04" for c in report.failed)

    def test_the_failure_names_the_node_and_what_the_builder_said(self, tmp_path) -> None:
        """A coding agent that already asked is otherwise told the abstract version of it."""
        root = copied("no-absent-examples", tmp_path)

        report = run_checks(root)
        message = next(c for c in report.failed if c.entry_id == "FT-04").findings[0].message

        assert "`allow_unknown=False` on `verify`" in message
        assert "absence_vs_error" in message

    def test_the_failure_reads_naturally_where_the_brief_has_no_answer(self, tmp_path) -> None:
        """The quote slot is filled either way, and nothing else exercises the empty one."""
        root = copied("no-absent-examples", tmp_path)
        brief = root / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        start = text.index("[entries.absence_vs_error]")
        end = text.index("[entries.", start + 1)
        brief.write_text(text[:start] + text[end:], encoding="utf-8")

        report = run_checks(root)
        message = next(c for c in report.failed if c.entry_id == "FT-04").findings[0].message

        assert "`absence_vs_error`: `nothing yet" in message

    def test_an_answer_a_deterministic_node_assembles_names_what_fed_it(self, tmp_path) -> None:
        """That node has no `allow_unknown` of its own, so the declaration goes upstream."""
        root = copied("no-absent-examples", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        for node in results["config"]["nodes"]:
            node["successors"] = ["assemble"] if node["node_id"] == "verify" else node["successors"]
        results["config"]["nodes"].append(
            {"node_id": "assemble", "node_kind": "deterministic", "successors": []}
        )
        path.write_text(json.dumps(results))

        report = run_checks(root)
        message = next(c for c in report.failed if c.entry_id == "FT-04").findings[0].message

        assert "`allow_unknown=False` on `verify`" in message

    def test_an_absent_case_in_one_condition_of_the_key_satisfies_ft_04(self, tmp_path) -> None:
        """A project whose answer is a record holds its absent cases in single empty fields.
        Before this the gate could be satisfied only by an example whose whole answer was
        absent, so the cases it exists to require were the ones it could not see."""
        root = copied("no-absent-examples", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        held_out = next(e for e in results["examples"].values() if e["split"] == "held_out")
        held_out["absent_parts"] = ["po_number"]
        path.write_text(json.dumps(results))

        report = run_checks(root)

        assert report.ok

    def test_a_missing_trajectory_names_the_run_directory_it_looked_in(self) -> None:
        """Which run has none. Reading the file reports the same failure less usefully."""
        report = run_checks(project("no-trajectory"))

        assert "no trajectory.jsonl in runs/" in report.failed[0].findings[0].message

    def test_a_trajectory_of_readable_records_and_no_node_execution_fails(self, tmp_path) -> None:
        """Every line conforms, and nothing says a node ran, which is what FT-13 is about."""
        root = copied("conforming", tmp_path)
        for trajectory in root.glob("runs/**/trajectory.jsonl"):
            kept = [
                line
                for line in trajectory.read_text().splitlines()
                if json.loads(line)["record_type"] != "node_execution"
            ]
            trajectory.write_text("\n".join(kept) + "\n")

        report = run_checks(root)

        assert report.failed[0].entry_id == "FT-13"
        assert "holds no node_execution record" in report.failed[0].findings[0].message

    def test_a_results_file_holding_no_rollouts_fails_ft_01(self, tmp_path) -> None:
        """A file that exists and records nothing scored is not an evaluation."""
        root = copied("conforming", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        results["rollouts"] = []
        path.write_text(json.dumps(results))

        report = run_checks(root)

        assert [c.entry_id for c in report.failed] == ["FT-01"]

    def test_splits_that_do_not_include_the_named_held_out_one_fail(self, tmp_path) -> None:
        """Two splits, neither of them the one the set says may not be inspected."""
        root = copied("conforming", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        results["config"]["example_set"]["splits"] = {"train": 5, "test": 3}
        path.write_text(json.dumps(results))

        report = run_checks(root)

        assert [c.entry_id for c in report.failed] == ["FT-02"]
        assert "'held_out' as held out" in report.failed[0].findings[0].message

    def test_a_trajectory_that_exists_and_says_nothing_still_fails(self) -> None:
        """`touch trajectory.jsonl` is what an existence check would accept."""
        report = run_checks(project("unreadable-trajectory"))
        message = report.failed[0].findings[0].message

        assert "No usable trajectory log" in message
        assert "is missing ended_at" in message

    def test_the_alias_is_named_in_the_message(self) -> None:
        report = run_checks(project("floating-model"))

        assert "`mistral-small-latest`" in report.failed[0].findings[0].message

    def test_the_split_shape_is_named_in_the_message(self) -> None:
        report = run_checks(project("one-split"))

        assert "declares one split, 'held_out'" in report.failed[0].findings[0].message

    def test_ft_06_names_the_metric_and_reports_one_finding_per_metric(self) -> None:
        report = run_checks(project("bare-metric"))
        findings = report.failed[0].findings

        assert len(findings) == 1
        assert "Metric `accuracy`" in findings[0].message


class TestWhichResultsFileIsRead:
    """Dogfood #1 run 2 measured a variant last, and the gate certified the variant."""

    def _second_results_file(self, root: Path) -> Path:
        """A copy of the project's results file, created later and reporting nothing."""
        reported = sorted((root / "evals" / "results").glob("*.json"))[0]
        data = json.loads(reported.read_text())
        data["created_at"] = "2099-01-01T00:00:00.000Z"
        later = reported.parent / "a-variant.json"
        later.write_text(json.dumps(data))
        return later

    def test_the_most_recent_is_read_when_the_brief_names_none(self, tmp_path: Path) -> None:
        root = copied("conforming", tmp_path)
        later = self._second_results_file(root)

        report = run_checks(root)

        assert _by_id(report, "FT-01").read == (str(later.relative_to(root)),)

    def test_the_brief_names_which_one_the_project_reports(self, tmp_path: Path) -> None:
        root = copied("conforming", tmp_path)
        self._second_results_file(root)
        reported = root / "evals" / "results" / "held-out.json"
        brief = root / "brief.toml"
        brief.write_text(
            f'results = "{reported.relative_to(root)}"\n' + brief.read_text(), encoding="utf-8"
        )

        report = run_checks(root)

        assert report.ok
        assert _by_id(report, "FT-01").read == (str(reported.relative_to(root)),)


class TestTheProjectsAccountOfItself:
    """FT-29: `idea.md` carries its sections, and the brief confirms it at the current stage."""

    def test_a_project_with_no_idea_file_fails(self, tmp_path: Path) -> None:
        root = copied("conforming", tmp_path)
        (root / "idea.md").unlink()

        found = _by_id(run_checks(root), "FT-29")

        assert found.outcome is Outcome.FAILED
        assert "no idea.md" in found.findings[0].message

    def test_a_section_left_empty_fails_and_the_message_names_it(self, tmp_path: Path) -> None:
        root = copied("conforming", tmp_path)
        text = (root / "idea.md").read_text(encoding="utf-8")
        head, _, _ = text.partition("## What is still open")
        (root / "idea.md").write_text(head + "## What is still open\n", encoding="utf-8")

        found = _by_id(run_checks(root), "FT-29")

        assert found.outcome is Outcome.FAILED
        assert "What is still open" in found.findings[0].message

    def test_a_heading_carrying_punctuation_still_counts(self, tmp_path: Path) -> None:
        """A project writing `## What this is:` is not failed for the colon."""
        root = copied("conforming", tmp_path)
        text = (root / "idea.md").read_text(encoding="utf-8")
        (root / "idea.md").write_text(
            text.replace("## What this is", "### What this is:"), encoding="utf-8"
        )

        assert _by_id(run_checks(root), "FT-29").outcome is Outcome.PASSED

    @pytest.mark.parametrize(
        "heading",
        [
            "## Where this is going and where it is not",
            "## Where this is going, and where it is not",
            "## Where this is going and where it is not:",
        ],
    )
    def test_the_section_the_documents_name_counts_however_it_is_punctuated(
        self, tmp_path: Path, heading: str
    ) -> None:
        """The check took the comma form alone, and no document writes the comma.

        A project copying the heading out of `docs/procedure.md` or FT-29 wrote the form
        without it, and failed a check for a comma.
        """
        root = copied("conforming", tmp_path)
        idea = root / "idea.md"
        idea.write_text(
            idea.read_text(encoding="utf-8").replace(
                "## Where this is going, and where it is not", heading
            ),
            encoding="utf-8",
        )

        assert _by_id(run_checks(root), "FT-29").outcome is Outcome.PASSED

    def test_the_five_sections_are_spelled_the_way_the_documents_spell_them(self) -> None:
        """The name the failure message prints is what a project writes as its heading."""
        from simple_agents import docs_path
        from simple_agents.conformance.artifacts import IDEA_SECTIONS

        for document in ("procedure.md", "failure-taxonomy.md"):
            text = (docs_path() / document).read_text(encoding="utf-8").lower()
            for section in IDEA_SECTIONS:
                assert section.lower() in text, (document, section)

    def test_an_account_confirmed_at_an_earlier_stage_is_stale(self, tmp_path: Path) -> None:
        root = copied("conforming", tmp_path)
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                'understanding_confirmed_at = "measure"', 'understanding_confirmed_at = "shape"'
            ),
            encoding="utf-8",
        )

        found = _by_id(run_checks(root), "FT-29")

        assert found.outcome is Outcome.FAILED
        assert "'shape'" in found.findings[0].message
        assert "'measure'" in found.findings[0].message

    def test_a_brief_that_never_confirmed_it_fails(self, tmp_path: Path) -> None:
        root = copied("conforming", tmp_path)
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                'understanding_confirmed_at = "measure"\n', ""
            ),
            encoding="utf-8",
        )

        found = _by_id(run_checks(root), "FT-29")

        assert found.outcome is Outcome.FAILED
        assert "understanding_confirmed_at" in found.findings[0].message

    def test_a_stage_that_is_not_a_stage_is_refused_when_the_brief_is_read(
        self, tmp_path: Path
    ) -> None:
        root = copied("conforming", tmp_path)
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                'understanding_confirmed_at = "measure"', 'understanding_confirmed_at = "later"'
            ),
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="understanding_confirmed_at"):
            Brief.read(brief)

    def test_it_reads_the_file_it_reports_on(self, tmp_path: Path) -> None:
        report = run_checks(project("conforming"))

        assert "idea.md" in _by_id(report, "FT-29").read


class TestTheTierGate:
    def test_a_prototype_project_is_held_to_two_checks(self) -> None:
        found = outcomes("prototype")

        assert found["FT-13"] is Outcome.PASSED
        assert found["FT-14"] is Outcome.PASSED
        assert found["FT-24"] is Outcome.PASSED
        assert found["FT-29"] is Outcome.PASSED
        assert found["FT-34"] is Outcome.PASSED
        assert all(
            found[entry] is Outcome.NOT_APPLICABLE for entry in ("FT-01", "FT-02", "FT-06", "FT-07")
        )

    def test_an_inapplicable_check_is_reported_rather_than_dropped(self) -> None:
        report = run_checks(project("prototype"))

        assert len(report.checks) == 29
        assert "Fires at tier evaluated, and this project claims prototype." in report.text()

    def test_a_project_with_no_evaluation_fails_once_and_blocks_the_rest(self) -> None:
        """Four failures for one cause would bury the one thing to do about it."""
        found = outcomes("no-evaluation")

        assert found["FT-01"] is Outcome.FAILED
        assert [found[e] for e in ("FT-02", "FT-03", "FT-04", "FT-06", "FT-07")] == (
            [Outcome.BLOCKED] * 5
        )

    def test_a_blocked_check_names_the_one_that_reports_it(self) -> None:
        report = run_checks(project("no-evaluation"))
        blocked = next(c for c in report.checks if c.entry_id == "FT-02")

        assert "FT-01" in (blocked.detail or "")
        assert report.counts()["failed"] == 1


class TestWhatSectionTwoSaysAboutTheBriefsKeys:
    """The keys `Brief` reads, against the paragraph in `docs/conformance.md` §2 naming them.

    That paragraph said "three keys" and named two of them plus `confirmed_against`, which
    dates the entries against the code rather than against a stage. `research_confirmed_at`
    shipped at `P3-28` and never reached it.
    """

    SPELLED = {"two": 2, "three": 3, "four": 4, "five": 5}

    @property
    def text(self) -> str:
        from simple_agents import docs_path

        whole = (docs_path() / "conformance.md").read_text(encoding="utf-8")
        return whole.split("## 2. The brief")[1].split("### 2.1")[0]

    def _stage_keys(self) -> set:
        from simple_agents.conformance.brief import Brief

        return {name for name in Brief.__dataclass_fields__ if name.endswith("_confirmed_at")}

    def test_it_names_every_key_that_dates_an_account_against_a_stage(self) -> None:
        assert all(f"`{name}`" in self.text for name in self._stage_keys())

    def test_the_number_it_spells_is_the_number_there_are(self) -> None:
        found = re.search(r"\*\*(\w+) keys name the stage", self.text)

        assert found, "docs/conformance.md §2 no longer says how many such keys there are"
        assert self.SPELLED[found.group(1).lower()] == len(self._stage_keys())


STAMP = "2026-08-27T09:14:02Z"


class _Out(BaseModel):
    v: Maybe[str]


def _a_prompt(inputs, ctx):
    return Prompt.user("hi")


def _a_budget() -> Budget:
    return Budget(max_steps=8, max_tokens=9999, max_cost=None, max_wall_clock_ms=9999)


class TestTheBrief:
    def test_a_missing_brief_stops_the_suite_rather_than_defaulting(self, tmp_path) -> None:
        """A project could otherwise delete the file to silence four checks."""
        with pytest.raises(ConfigurationError) as exc:
            run_checks(tmp_path)

        assert 'tier = "prototype"' in str(exc.value)

    def test_a_brief_that_declares_no_tier_is_refused(self, tmp_path) -> None:
        """The file exists and says everything except the one thing a gate reads."""
        (tmp_path / "brief.toml").write_text('stage = "shape"\n')

        with pytest.raises(ConfigurationError, match="No tier declared"):
            run_checks(tmp_path)

    def test_a_tier_outside_the_three_is_refused_by_name(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "production"\n')

        with pytest.raises(ConfigurationError, match="prototype, evaluated and trained"):
            run_checks(tmp_path)

    def test_a_brief_that_is_not_toml_is_refused(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text("tier: prototype\n")

        with pytest.raises(ConfigurationError, match="not readable as TOML"):
            run_checks(tmp_path)

    def test_an_entry_with_no_status_is_refused(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text(
            'tier = "prototype"\n\n[entries.ground_truth]\nanswer = "a retailer name"\n'
        )

        with pytest.raises(ConfigurationError, match="answered, deferred, unanswered"):
            run_checks(tmp_path)

    def test_a_deferred_entry_naming_no_stage_is_refused(self, tmp_path) -> None:
        """Deferral has to say where to, or it reads the same as a forgotten question."""
        (tmp_path / "brief.toml").write_text(
            'tier = "prototype"\n\n[entries.budget]\nstatus = "deferred"\n'
        )

        with pytest.raises(ConfigurationError, match="names no stage"):
            run_checks(tmp_path)

    def test_it_reads_the_entries_a_project_recorded(self) -> None:
        brief = Brief.read(project("conforming") / "brief.toml")

        assert brief.tier == Tier("evaluated")
        assert brief.stage == "measure"
        # Every required question, plus one optional entry the fixture defers so all three
        # statuses appear in it.
        assert [e.name for e in brief.entries] == [
            *(q.name for q in required_at("measure")),
            "prices",
        ]
        assert brief.entry("budget").status == "answered"
        assert brief.unanswered() == []

    def test_a_deferral_settles_a_question_until_the_project_reaches_that_stage(
        self, tmp_path
    ) -> None:
        (tmp_path / "brief.toml").write_text(
            'tier = "prototype"\nstage = "shape"\n\n'
            + "".join(
                f'[entries.{q.name}]\nstatus = "answered"\n'
                + f'recorded_at = "{STAMP}"\n'
                + ('asked_at = "shape"\n' if q.re_asked_each_stage else "")
                + 'answer = "settled"\n\n'
                for q in required_at("shape")
                if q.name != "ground_truth"
            )
            + '[entries.ground_truth]\nstatus = "deferred"\ndeferred_to = "build"\n'
        )

        report = run_checks(tmp_path)

        assert next(c for c in report.checks if c.entry_id == "FT-24").outcome is Outcome.PASSED

    def test_a_deferral_to_the_stage_the_project_is_at_fails_with_the_blanks(
        self, tmp_path
    ) -> None:
        """A question deferred to here is due here, and reads the same as one nobody put."""
        (tmp_path / "brief.toml").write_text(
            'tier = "prototype"\nstage = "shape"\n\n'
            + "".join(
                f'[entries.{q.name}]\nstatus = "answered"\n'
                + f'recorded_at = "{STAMP}"\n'
                + ('asked_at = "shape"\n' if q.re_asked_each_stage else "")
                + 'answer = "settled"\n\n'
                for q in required_at("shape")
                if q.name != "ground_truth"
            )
            + '[entries.ground_truth]\nstatus = "deferred"\ndeferred_to = "shape"\n'
        )

        report = run_checks(tmp_path)
        result = next(c for c in report.checks if c.entry_id == "FT-24")

        assert result.outcome is Outcome.FAILED
        assert "ground_truth" in result.findings[0].message


class TestTheTaxonomyIsTheSourceOfTheMessages:
    def test_every_entry_parses_out_of_the_shipped_document(self) -> None:
        entries = taxonomy()

        assert len(entries) == 46
        assert all(entry.message for entry in entries)

    def test_an_entry_naming_a_stage_carries_it_and_the_rest_carry_none(self) -> None:
        """The `· Stage:` field is optional, and five entries carry it."""
        entries = taxonomy()

        assert entries["FT-31"].stage == "ship"
        assert entries["FT-34"].stage == "shape"
        assert entries["FT-37"].stage == "ship"
        # FT-40 names no stage: it runs at every one and decides there, since the count it
        # reports is expected at `shape` and a failure at `ship`.
        assert entries["FT-40"].stage is None
        # Document order: FT-37 closes Group A and FT-38 closes Group G.
        assert [e.id for e in entries if e.stage is not None] == [
            "FT-37",
            "FT-31",
            "FT-34",
            "FT-36",
            "FT-38",
        ]

    def test_an_entry_naming_a_stage_nobody_defined_is_refused(self, tmp_path) -> None:
        """A typo there would be a check that fires at no stage, so it fails at import."""
        document = tmp_path / "taxonomy.md"
        document.write_text(
            "### FT-31: Shipped on a development channel\n"
            "*Surface: artifact · Tier: prototype · Stage: shipping*\n\n"
            "**Check.** Nothing.\n\n"
            "**Failure message.**\n"
            "> Something went wrong.\n",
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="names stage 'shipping'"):
            taxonomy(document)

    def test_a_message_rendered_without_its_placeholder_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="rendered without alias"):
            taxonomy()["FT-14"].render()

    def test_a_placeholder_the_document_does_not_carry_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="no placeholder called reason"):
            taxonomy()["FT-01"].render(reason="none")

    def test_the_message_a_check_prints_is_the_document_s_own_text(self) -> None:
        """Word for word, so a message cannot drift from what the taxonomy specifies."""
        report = run_checks(project("one-split"))
        printed = report.failed[0].findings[0].message
        specified = taxonomy()["FT-02"].message

        assert printed == specified.replace(
            "`<reason>`", "`the example set declares one split, 'held_out'`"
        )

    def test_a_document_with_no_entries_is_refused(self, tmp_path) -> None:
        path = tmp_path / "failure-taxonomy.md"
        path.write_text("# Failure taxonomy\n\nNothing here.\n")

        with pytest.raises(ConfigurationError, match="holds no `### FT-nn"):
            taxonomy(path)

    def test_an_entry_with_no_failure_message_is_refused(self, tmp_path) -> None:
        path = tmp_path / "failure-taxonomy.md"
        path.write_text(
            "### FT-01: No evaluation at all\n*Surface: artifact · Tier: evaluated*\n\n"
            "**Check.** Something.\n"
        )

        with pytest.raises(ConfigurationError, match="no `\\*\\*Failure message"):
            taxonomy(path)


class TestTheEnumerationsInTheDocument:
    """Every sentence in `docs/conformance.md` that lists or counts checks, against the code.

    Four such sentences went false across P3-6, P3-7 and P3-8 and each was found by someone
    reading. These are derivable, unlike a gate's "these pass", which depends on what a project
    has produced rather than on the registry, and which `docs/procedure.md` stopped claiming.
    """

    def document(self) -> str:
        from simple_agents import docs_path

        return (docs_path() / "conformance.md").read_text(encoding="utf-8")

    def registered(self) -> list[str]:
        from simple_agents.conformance.checks import CHECKS

        return [entry_id for entry_id, _ in CHECKS]

    def test_the_prototype_row_counts_what_that_tier_runs(self) -> None:
        """Adding a `prototype` check invalidates the count and nothing else would say so."""
        from simple_agents.conformance.taxonomy import taxonomy

        entries = taxonomy()
        runs = [i for i in self.registered() if entries[i].tier == "prototype"]
        [row] = [
            line for line in self.document().splitlines() if line.startswith("| `prototype` |")
        ]

        assert len(runs) == 21
        assert "twenty-one of the twenty-nine" in row

    def test_the_checks_prototype_drops_are_the_ones_it_does_not_run(self) -> None:
        """The ids moved out of the table on 2026-08-19 and into the sentence under it, which
        names what the tier drops rather than what it runs. Both directions still have to be
        the registered set."""
        from simple_agents.conformance.taxonomy import taxonomy

        entries = taxonomy()
        dropped = sorted(i for i in self.registered() if entries[i].tier != "prototype")
        [sentence] = [
            line for line in self.document().splitlines() if line.startswith("**`prototype` drops")
        ]

        assert re.findall(r"FT-\d\d", sentence) == dropped

    def test_the_entries_said_to_name_a_stage_are_the_ones_that_do(self) -> None:
        from simple_agents.conformance.taxonomy import taxonomy

        entries = taxonomy()
        staged = sorted(i for i in self.registered() if entries[i].stage)
        [sentence] = [line for line in self.document().splitlines() if "also name a stage" in line]

        assert re.findall(r"FT-\d\d", sentence) == staged
        assert "the only entries that do" in sentence

    def test_the_count_of_checks_and_their_surface_hold(self) -> None:
        from simple_agents.conformance.taxonomy import taxonomy

        entries = taxonomy()
        surfaces = {entries[i].surface for i in self.registered()}

        assert len(self.registered()) == 29, "the document counts them in four places"
        assert surfaces == {"artifact"}
        assert "All twenty-nine are `artifact` surface" in self.document()

    def test_the_table_of_what_each_check_reads_lists_every_check(self) -> None:
        """`docs/conformance.md` §3 is a row per check, and nothing compared it to the set."""
        section = self.document()[
            self.document().index("## 3. What each check reads") : self.document().index("### 3.1")
        ]

        assert re.findall(r"^\| (FT-\d+) \|", section, re.M) == self.registered()

    def test_the_taxonomys_own_stage_sentence_names_the_staged_entries(self) -> None:
        """The same claim as `conformance.md`'s, in the other document, and unread until now.

        The claim is the first sentence, and only that: the paragraph names two of the entries
        again afterwards, so reading the whole of it lets an id dropped from the claim be
        covered by its own second mention.
        """
        import sys

        from simple_agents import docs_path
        from simple_agents.conformance.taxonomy import taxonomy

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from prose_check import NUMBER_WORDS  # noqa: E402

        document = (docs_path() / "failure-taxonomy.md").read_text(encoding="utf-8")
        [line] = [
            one for one in document.splitlines() if "entries name a stage as well as a tier" in one
        ]
        # Up to the emphasis, which is a second mention of two of them rather than the claim.
        claim = line.split("**")[0]
        staged = {e.id for e in taxonomy() if e.stage}

        assert set(re.findall(r"FT-\d\d", claim)) == staged
        assert claim.startswith(f"{NUMBER_WORDS[len(staged)].capitalize()} entries"), claim

    def test_ft_38_counts_the_entries_it_is_about(self) -> None:
        """Its `Why it's wrong` states how many brief entries describe the pipeline."""
        import sys

        from simple_agents import docs_path
        from simple_agents.conformance.elicitation import QUESTIONS

        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        from prose_check import NUMBER_WORDS  # noqa: E402

        document = (docs_path() / "failure-taxonomy.md").read_text(encoding="utf-8")
        # FT-38 closes Group G, so the slice runs on into Group H and its entry too.
        entry = document[document.index("### FT-38:") : document.index("## 9. Group H")]
        [line] = [one for one in entry.splitlines() if one.startswith("**Why it's wrong.**")]
        about = [question for question in QUESTIONS if question.about_the_pipeline]

        assert f"{NUMBER_WORDS[len(about)].capitalize()} of the brief's entries" in line
        assert f"One of the {NUMBER_WORDS[len(about)]} is read by another check" in line
        assert f"the other {NUMBER_WORDS[len(about) - 1]} are prose" in line

    def test_the_index_counts_what_the_index_lists(self) -> None:
        """The `Counts.` line against the index table it sits under.

        Nothing read it, and it was wrong by one in two buckets across at least two entries
        being added. The tiers come from the entries; the surfaces come from the index column,
        which is where they are written in the words the line counts.
        """
        from collections import Counter

        from simple_agents.conformance.taxonomy import taxonomy

        from simple_agents import docs_path

        entries = taxonomy()
        # The taxonomy rather than `conformance.md`, which is what this class otherwise reads.
        document = (docs_path() / "failure-taxonomy.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| (FT-\d+) \| (.+?) \| (.+?) \| (.+?) \|$", document, re.M)
        [line] = [one for one in document.splitlines() if one.startswith("**Counts.**")]

        assert len(rows) == len(entries), "every entry has an index row"
        tiers = Counter(str(entries[found].tier) for found, _, _, _ in rows)
        for tier, count in tiers.items():
            assert f"{count} `{tier}`" in line, tier
        assert f"{len(entries)} entries" in line

        # The line spells a two-part surface in one order and the index sometimes in the
        # other, so a bucket is its parts rather than its text.
        buckets = Counter(
            frozenset(surface.replace(" (enforced)", "").split(" + ")) for _, _, surface, _ in rows
        )
        for parts, count in buckets.items():
            spellings = ["+".join(order) for order in (sorted(parts), sorted(parts, reverse=True))]
            assert any(f"{count} {one}" in line for one in spellings), (sorted(parts), count)
        assert sum(buckets.values()) == len(entries)

    def test_the_number_of_entries_naming_the_tier_holds(self) -> None:
        """ "nine entries in the taxonomy name it in their failure message"."""
        from simple_agents.conformance.taxonomy import taxonomy

        entries = taxonomy()
        naming = [
            f"FT-{n:02d}"
            for n in range(1, 35)
            if "tier" in (entries[f"FT-{n:02d}"].message or "").lower()
        ]

        assert len(naming) == 9
        assert "nine entries in the taxonomy name it" in self.document().lower()


class TestTheSampleReportIsWhatTheSuitePrints:
    """`docs/conformance.md` §4 shows a report, and nothing ran it until this test.

    It showed four `pass` rows, counted "3 passed", and left FT-30 out, so ten of the eleven
    checks appeared. The block is compared against a real run of the suite over the
    `no-evaluation` fixture, which is the project the sample describes: one failure, five
    passes and five blocked. Regenerate it with::

        uv run python -c "from simple_agents.conformance import run_checks; \\
            print(run_checks('tests/fixtures/projects/no-evaluation').text())"

    then substitute the project root and the run directory the way the block does.
    """

    ROOT = "~/projects/inseam-agent"
    RUN = "runs/run_7f2a"

    def documented(self) -> str:
        from simple_agents import docs_path

        document = (docs_path() / "conformance.md").read_text(encoding="utf-8")
        section = document[document.index("## 4. Reading the report") :]
        [block] = [fenced for fenced in section.split("```") if "simple-agents check:" in fenced]
        return block.strip("\n")

    def printed(self) -> str:
        """The suite's own output, with the fixture's paths written the way the sample is."""
        import dataclasses

        root = project("no-evaluation")
        report = run_checks(root)
        # Read off the report rather than transcribed: the evaluation directory in the
        # fixture is named for a uuid that was fresh when the fixture was built.
        run = _by_id(report, "FT-13").read[0].rsplit("/", 1)[0]
        # The header line is wrapped when it is rendered, so the substitution happens on the
        # report and not on its text: replacing a long path in the output leaves the wrap
        # where the long path put it, and the sample would show a break the text does not
        # have.
        report = dataclasses.replace(
            report,
            root=self.ROOT,
            reading=(report.reading or "").replace(run, self.RUN) or None,
        )
        return report.text().replace(run, self.RUN)

    def test_the_document_holds_a_report(self) -> None:
        """Guards it, so renaming `docs/conformance.md` §3 cannot make this pass vacuously."""
        assert self.documented().startswith("simple-agents check:")

    def test_every_line_matches(self) -> None:
        assert self.documented().splitlines() == self.printed().splitlines()

    def test_it_shows_every_check(self) -> None:
        import re

        shown = re.findall(r"^\s*(?:pass|FAIL|blocked|n/a)  (FT-\d+)", self.documented(), re.M)

        assert len(shown) == 29
        assert len(set(shown)) == 29

    def test_the_counts_on_the_last_line_add_up_to_the_rows_above_them(self) -> None:
        import re

        counts = re.findall(r"(\d+) (?:failed|passed|blocked|not applicable)", self.documented())

        assert sum(int(found) for found in counts) == len(CHECKS)


class TestWhatTheSuiteDoesNotDo:
    """`docs/conformance.md` §5 states how many entries the library enforces at author
    time, and lists them."""

    def enforced(self) -> list[str]:
        return sorted(entry.id for entry in taxonomy() if "nforced" in entry.check)

    def section(self) -> str:
        from simple_agents import docs_path

        document = (docs_path() / "conformance.md").read_text(encoding="utf-8")
        return document[document.index("## 5. What the suite does not do") :]

    def test_it_counts_the_entries_that_enforce(self) -> None:
        """It said five and six say so, the sixth being FT-23, which does refuse."""
        spelled = {4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}

        assert f"the {spelled[len(self.enforced())]} the library enforces" in self.section()

    def test_it_names_each_of_them(self) -> None:
        section = self.section()

        assert all(entry_id in section for entry_id in self.enforced())

    def test_it_counts_the_checks_against_the_entries(self) -> None:
        """Both counts are read off the code, so registering a check moves the sentence.

        It said sixteen against seventeen registered checks from 2026-08-19, because the
        count beside it was updated and the words were not.
        """
        from simple_agents.conformance.checks import CHECKS

        spelled = {
            15: "Fifteen",
            16: "Sixteen",
            17: "Seventeen",
            18: "Eighteen",
            19: "Nineteen",
            20: "Twenty",
            21: "Twenty-one",
            22: "Twenty-two",
            23: "Twenty-three",
            24: "Twenty-four",
            25: "Twenty-five",
            26: "Twenty-six",
            28: "Twenty-eight",
            29: "Twenty-nine",
            33: "thirty-three",
            34: "thirty-four",
            35: "thirty-five",
            36: "thirty-six",
            37: "thirty-seven",
            38: "thirty-eight",
            39: "thirty-nine",
            40: "forty",
            41: "forty-one",
            42: "forty-two",
            43: "forty-three",
            45: "forty-five",
            46: "forty-six",
        }

        assert (
            f"{spelled[len(CHECKS)]} of the taxonomy's {spelled[len(taxonomy())]} entries"
            in self.section()
        )


class TestTheTrajectoryFieldsComeFromTheDocument:
    """The validator's field list against the document's own table, so a format change fails."""

    def test_the_common_fields_are_what_the_format_document_names(self) -> None:
        import re

        from simple_agents import docs_path

        section = (
            (docs_path() / "trajectory-format.md")
            .read_text(encoding="utf-8")
            .split("## 2. Common fields")[1]
            .split("## 3.")[0]
        )
        named = set(re.findall(r"^\| `([a-z_]+)` \|", section, re.MULTILINE))

        assert named == set(COMMON_RECORD_FIELDS)

    def test_every_record_type_is_one_the_format_document_names(self) -> None:
        from simple_agents import docs_path

        doc = (docs_path() / "trajectory-format.md").read_text(encoding="utf-8")

        for record_type in RECORD_TYPES:
            assert f"## 3. Record type: `{record_type}`" in doc or f"`{record_type}`" in doc


class TestTheAliasRule:
    @pytest.mark.parametrize(
        "identifier,floats",
        [
            ("mistral-small-2603", False),
            ("mistral-small-latest", True),
            ("gpt-4o-2024-08-06", False),
            ("claude-opus-4-20250514", False),
            ("open-mistral-nemo", False),
            ("gemini-2.5-pro-preview", True),
            ("Qwen/Qwen3-1.7B", False),
        ],
    )
    def test_what_the_rule_calls_an_alias(self, identifier: str, floats: bool) -> None:
        """A hosted name that floats without saying so passes, which FT-14 states."""
        assert _floats(identifier) is floats

    def test_self_hosted_weights_need_a_revision_and_a_repo_id_is_not_one(self, tmp_path) -> None:
        root = _self_hosted(tmp_path, revision=None)

        report = run_checks(root)

        assert report.failed[0].entry_id == "FT-14"
        assert "`Qwen/Qwen3-1.7B`" in report.failed[0].findings[0].message

    def test_a_branch_name_is_not_a_revision(self, tmp_path) -> None:
        root = _self_hosted(tmp_path, revision="main")

        report = run_checks(root)

        assert "`Qwen/Qwen3-1.7B@main`" in report.failed[0].findings[0].message

    def test_a_commit_sha_passes(self, tmp_path) -> None:
        root = _self_hosted(tmp_path, revision="70d244cc86ccca08cf5af4e1e306ecf908b1ad5e")

        assert run_checks(root).ok


class TestTheCommand:
    # `check` writes `view.html` beside the project it reads, so each run here gets its own
    # copy of the fixture rather than writing into the committed tree.
    @staticmethod
    def _copy(tmp_path, name: str) -> str:
        import shutil

        target = tmp_path / name
        shutil.copytree(project(name), target)
        return str(target)

    def test_it_exits_zero_when_nothing_failed(self, tmp_path) -> None:
        from simple_agents.cli import main

        assert main(["check", self._copy(tmp_path, "conforming")]) == 0

    def test_it_exits_one_when_a_check_failed(self, tmp_path) -> None:
        from simple_agents.cli import main

        assert main(["check", self._copy(tmp_path, "one-split")]) == 1

    def test_it_exits_two_when_the_suite_could_not_run(self, tmp_path) -> None:
        """A missing brief is not a check failure: nothing ran to fail."""
        from simple_agents.cli import main

        assert main(["check", str(tmp_path)]) == 2

    def test_json_carries_every_check_and_the_counts(self, capsys) -> None:
        from simple_agents.cli import main

        main(["check", str(project("no-evaluation")), "--json"])
        report = json.loads(capsys.readouterr().out)

        assert report["counts"] == {
            # FT-39 passes with no comments.toml on disk; FT-40 reads the fixture's manifest,
            # which records no planned step, since the fixture declares no agent.py to read;
            # FT-41 reads nine manifests, none of which carries a suspension; FT-42 reads
            # every name under `produces` against them; FT-45 is blocked with the rest that
            # read a results file this fixture does not have.
            "passed": 19,
            "failed": 1,
            "blocked": 6,
            "not_applicable": 3,  # FT-31, FT-37 and FT-38, which fire at `ship`
        }
        assert report["ok"] is False


def _self_hosted(tmp_path: Path, *, revision: str | None) -> Path:
    """A project whose one run was served by vLLM, with the revision under test."""
    source = project("conforming")
    shutil.copy(source / "idea.md", tmp_path / "idea.md")
    shutil.copy(source / "design.md", tmp_path / "design.md")
    shutil.copy(source / "research.md", tmp_path / "research.md")
    run = tmp_path / "runs" / "run_1"
    run.mkdir(parents=True)
    # Every required question answered, so the report turns on FT-14 alone.
    # `prototype` has no `measure` stage, so the stage and the deferral come down with the
    # tier. Everything naming `measure` in the source brief names a stage this one never
    # reaches.
    (tmp_path / "brief.toml").write_text(
        (project("conforming") / "brief.toml")
        .read_text(encoding="utf-8")
        .replace('tier = "evaluated"', 'tier = "prototype"')
        .replace('"measure"', '"build"'),
        encoding="utf-8",
    )
    manifest = json.loads(
        (sorted(source.glob("runs/**/manifest.json"))[0]).read_text(encoding="utf-8")
    )
    manifest["models"]["configured"] = {
        "backend": "self_hosted",
        "request_model": "Qwen/Qwen3-1.7B",
        "model_revision": revision,
    }
    (run / "manifest.json").write_text(json.dumps(manifest))
    trajectory = sorted(source.glob("runs/**/trajectory.jsonl"))[0]
    (run / "trajectory.jsonl").write_text(trajectory.read_text(encoding="utf-8"))
    return tmp_path


class TestWhichRunTheChecksRead:
    """A project has many runs and the checks read one, so which one is a decision.

    Dogfood #2 had eighteen and the checks read a run still executing, because the newest by
    start time is not the newest that finished.
    """

    def _add_run(
        self,
        root: Path,
        run_id: str,
        *,
        started_at: str,
        outcome: str | None,
        role: str | None = None,
    ) -> Path:
        """A copy of the project's own newest run, restamped and given an outcome."""
        source = sorted(root.glob("runs/**/manifest.json"))[-1].parent
        run = root / "runs" / run_id
        run.mkdir(parents=True)
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        manifest["run_id"] = run_id
        manifest["started_at"] = started_at
        manifest["outcome"] = outcome
        manifest["ended_at"] = None if outcome is None else started_at
        # Set or removed rather than left as the source run wrote it, so a test asking what a
        # manifest with no role reads as gets one with no role.
        if role is None:
            manifest.pop("role", None)
        else:
            manifest["role"] = role
        (run / "manifest.json").write_text(json.dumps(manifest))
        (run / "trajectory.jsonl").write_text(
            (source / "trajectory.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
        )
        return run

    def test_a_run_still_executing_is_not_the_one_read(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        finished = self._add_run(
            root, "run_finished", started_at="2099-01-01T00:00:00.000Z", outcome="completed"
        )
        self._add_run(root, "run_in_flight", started_at="2099-01-02T00:00:00.000Z", outcome=None)

        assert _latest_run(root, runs_by_pipeline(root)) == finished

    def test_a_run_that_errored_is_not_the_one_read(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        finished = self._add_run(
            root, "run_finished", started_at="2099-01-01T00:00:00.000Z", outcome="completed"
        )
        self._add_run(root, "run_crashed", started_at="2099-01-03T00:00:00.000Z", outcome="error")

        assert _latest_run(root, runs_by_pipeline(root)) == finished

    def test_a_run_stopped_early_by_a_budget_still_counts_as_finished(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        stopped = self._add_run(
            root, "run_stopped", started_at="2099-01-04T00:00:00.000Z", outcome="stopped_early"
        )

        assert _latest_run(root, runs_by_pipeline(root)) == stopped

    def test_a_project_whose_every_run_failed_still_reads_one(self, tmp_path) -> None:
        """Reporting no run at all would hide the runs that exist behind a missing-artifact
        message, and the checks are what say what is wrong with them."""
        root = tmp_path / "only_failures"
        shutil.copytree(project("conforming"), root)
        for manifest in root.glob("runs/**/manifest.json"):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["outcome"] = "error"
            manifest.write_text(json.dumps(data))

        assert _latest_run(root, runs_by_pipeline(root)) is not None

    def test_a_labelling_run_is_not_the_one_read(self, tmp_path) -> None:
        """`docs/evaluation.md` §1.4 writes a labelling pass into `runs/`, and it is the newest
        run there when a project labels before it evaluates."""
        root = copied("conforming", tmp_path)
        agent_run = self._add_run(
            root, "run_agent", started_at="2099-01-01T00:00:00.000Z", outcome="completed"
        )
        self._add_run(
            root,
            "run_labels",
            started_at="2099-01-02T00:00:00.000Z",
            outcome="completed",
            role="labelling",
        )

        assert _latest_run(root, runs_by_pipeline(root)) == agent_run

    def test_a_run_that_names_no_role_is_the_agent_s(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        newest = self._add_run(
            root, "run_newest", started_at="2099-01-05T00:00:00.000Z", outcome="completed"
        )

        assert "role" not in json.loads((newest / "manifest.json").read_text())
        assert _latest_run(root, runs_by_pipeline(root)) == newest

    def test_a_project_whose_every_run_is_a_labelling_pass_is_told_so(self, tmp_path) -> None:
        root = tmp_path / "only_labelling"
        shutil.copytree(project("conforming"), root)
        for manifest in root.glob("runs/**/manifest.json"):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["role"] = "labelling"
            manifest.write_text(json.dumps(data))

        report = run_checks(root)
        ft_13 = next(c for c in report.checks if c.entry_id == "FT-13")

        message = " ".join(finding.message for finding in ft_13.findings)
        assert ft_13.outcome is Outcome.FAILED
        assert "no run of the agent under runs/" in message
        assert "labelling" in message
        assert "RunEnvelope(role=...)" in message


class TestFT13AndASampledTrajectory:
    """FT-13 reads structure, not payloads, so it passes at every rate and says so."""

    def sampled(self, tmp_path):
        """The conforming project, with every rollout's payloads dropped by sampling."""
        root = copied("conforming", tmp_path)
        for trajectory in root.glob("runs/**/trajectory.jsonl"):
            records = [json.loads(line) for line in trajectory.read_text().splitlines() if line]
            for record in records:
                omitted = []
                for field in ("inputs", "outputs", "response"):
                    if record.get(field) is not None:
                        record[field] = {"type": "not_recorded", "reason": "sampling"}
                        omitted.append(field)
                record["omissions"] = omitted
            trajectory.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        for manifest in root.glob("runs/**/manifest.json"):
            found = json.loads(manifest.read_text())
            found["recording"] = {"payload_rate": 0.01, "payloads": "omitted", "reason": "sampling"}
            manifest.write_text(json.dumps(found, indent=2) + "\n")
        return root

    def test_it_passes(self, tmp_path) -> None:
        report = run_checks(self.sampled(tmp_path))

        assert next(c for c in report.checks if c.entry_id == "FT-13").outcome is Outcome.PASSED

    def test_it_reports_the_rate_it_read_from_the_manifest(self, tmp_path) -> None:
        report = run_checks(self.sampled(tmp_path))

        detail = next(c for c in report.checks if c.entry_id == "FT-13").detail
        assert detail is not None
        assert "dropped by sampling" in detail
        assert "0.01" in detail

    def test_a_run_that_kept_its_payloads_reports_nothing(self) -> None:
        report = run_checks(project("conforming"))

        assert next(c for c in report.checks if c.entry_id == "FT-13").detail is None

    def test_the_other_checks_are_unmoved(self, tmp_path) -> None:
        """Only FT-13 and FT-07 read a trajectory, and neither reads a payload."""
        whole = {c.entry_id: c.outcome for c in run_checks(project("conforming")).checks}
        dropped = {c.entry_id: c.outcome for c in run_checks(self.sampled(tmp_path)).checks}

        assert whole == dropped


class TestARunAndAResultsFileFromDifferentMeasurements:
    """Some checks read a run, some read a results file, and nothing joined them.

    Dogfood #3 passed 10 of 10 with FT-01 through FT-07 reading one evaluation and FT-13 and
    FT-14 reading a rollout of another, on a different example set and a different graph. The
    report named both files and said nothing about them being different measurements
    (`dev-docs/runs/dogfood-3/findings.md` DF3-D6).
    """

    def test_the_conforming_project_says_nothing(self) -> None:
        """One measurement, so there is nothing to report."""
        assert run_checks(project("conforming")).notes == ()

    def _a_later_run_of_another_evaluation(self, root: Path, directory: str) -> None:
        """A rollout of a second evaluation, started after everything the results file covers.

        The run directory is found by the manifest's start time rather than by the file's, so
        the copy has to say it ran later for recency to reach it.
        """
        later = root / "runs" / directory
        shutil.copytree(next((root / "runs").glob("**/eval_*/e1-0")), later)
        manifest = later / "manifest.json"
        record = json.loads(manifest.read_text())
        record["started_at"] = "2099-01-01T00:00:00.000Z"
        record["ended_at"] = "2099-01-01T00:01:00.000Z"
        manifest.write_text(json.dumps(record))

    def test_a_run_from_another_evaluation_is_reported(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        self._a_later_run_of_another_evaluation(root, "eval/eval_deadbeef0000/e9-0")

        report = run_checks(root)

        assert len(report.notes) == 1
        assert "different measurements" in report.notes[0]
        assert "runs/eval/eval_deadbeef0000/e9-0" in report.notes[0]
        assert report.ok, "the note is a note, and passes nothing and fails nothing"

    def test_it_reaches_the_json_record_and_the_text(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        self._a_later_run_of_another_evaluation(root, "eval/eval_deadbeef0000/e9-0")

        report = run_checks(root)

        assert report.to_record()["notes"] == list(report.notes)
        assert "different measurements" in report.text()

    def test_a_single_run_outside_any_evaluation_is_not_reported(self, tmp_path) -> None:
        """A project that ran its agent once by hand after measuring has done nothing wrong."""
        root = copied("conforming", tmp_path)
        self._a_later_run_of_another_evaluation(root, "run_20260811T120000Z_abcd")

        assert run_checks(root).notes == ()


class TestFT30AndDecisionsTheBuilderNeverSaw:
    """Every question asks the builder about their world; none asks what the agent decided.

    Dogfood #3 passed 10 of 10 having chosen its external catalogue, its pipeline shape, the
    number of books it reads before judging taste, a prompt rule the builder never gave, a
    174KB page and an evaluation that could not detect its own effect. All six alone
    (`dev-docs/runs/dogfood-3/findings.md` DF3-D8).
    """

    def test_the_conforming_project_records_all_six_kinds(self) -> None:
        brief = Brief.read(project("conforming") / "brief.toml")

        assert {d.kind for d in brief.decisions} == set(kind_names())
        assert brief.unseen_decisions() == []
        assert outcomes("conforming")["FT-30"] is Outcome.PASSED

    def test_a_decision_still_proposed_fails(self) -> None:
        report = run_checks(project("unsettled-decision"))
        failed = {c.entry_id for c in report.failed}

        assert failed == {"FT-30"}
        message = next(c for c in report.failed).findings[0].message
        assert "constant_of_this_project" in message

    def test_a_kind_with_no_entry_fails_too(self) -> None:
        """Absent is not the same as none, which is why `not_applicable` exists."""
        report = run_checks(project("missing-decision-kind"))

        assert {c.entry_id for c in report.failed} == {"FT-30"}
        assert "'dependency'" in report.failed[0].findings[0].message

    def test_not_applicable_settles_a_kind_a_project_has_nothing_of(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        brief = (root / "brief.toml").read_text()
        brief = brief.replace(
            f'[decisions.presentation_of_this_project]\nkind = "presentation"\n'
            f'status = "agreed"\nrecorded_at = "{STAMP}"',
            f'[decisions.presentation_of_this_project]\nkind = "presentation"\n'
            f'status = "not_applicable"\nrecorded_at = "{STAMP}"',
        )
        (root / "brief.toml").write_text(brief)

        assert run_checks(root).ok

    def test_the_message_is_the_taxonomy_s_own_text(self) -> None:
        report = run_checks(project("unsettled-decision"))
        printed = report.failed[0].findings[0].message

        assert printed == taxonomy()["FT-30"].message.replace(
            "`<reason>`", "`'constant_of_this_project' still recorded 'proposed'`"
        )

    def test_an_unknown_kind_is_refused_when_the_brief_is_read(self, tmp_path) -> None:
        brief = tmp_path / "brief.toml"
        brief.write_text(
            'tier = "prototype"\n\n[decisions.something]\nkind = "vibes"\nstatus = "agreed"\nrecorded_at = "2026-08-27T09:14:02Z"\n'
        )

        with pytest.raises(ConfigurationError) as caught:
            Brief.read(brief)

        assert "'vibes'" in str(caught.value)
        assert "dependency" in str(caught.value)

    def test_an_unknown_status_is_refused_too(self, tmp_path) -> None:
        brief = tmp_path / "brief.toml"
        brief.write_text(
            'tier = "prototype"\n\n[decisions.x]\nkind = "shape"\nstatus = "maybe"\nrecorded_at = "2026-08-27T09:14:02Z"\n'
        )

        with pytest.raises(ConfigurationError) as caught:
            Brief.read(brief)

        assert "'maybe'" in str(caught.value)
        assert "not_applicable" in str(caught.value)

    def test_the_six_kinds_each_carry_what_to_put_to_the_builder(self) -> None:
        for entry in DECISION_KINDS:
            assert entry.ask.endswith("?"), entry.name
            assert entry.covers and entry.example


class TestTheGroundWasNeverChecked:
    """FT-36 reads `research.md`. Dogfood #4's four-source table recorded award shortlists
    with a `\u2014` in the yield column, the prose beside it said they rode another
    mechanism, and five hundred lines later the coding agent recorded that awards were not
    sourced at all. Nothing was ever built."""

    def _project(self, tmp_path: Path, *, research: str | None = None) -> Path:
        root = copied("conforming", tmp_path)
        if research is None:
            (root / "research.md").unlink()
        else:
            (root / "research.md").write_text(research, encoding="utf-8")
        return root

    def _reason(self, root: Path) -> str:
        return str(_by_id(run_checks(root), "FT-36").findings[0].message)

    def _survey(self, outcome: str = "adopted", column: str = "Outcome") -> str:
        source = (project("conforming") / "research.md").read_text(encoding="utf-8")
        head, _, tail = source.partition("## What was found against each part")
        _, _, rest = tail.partition("## What this turns on, having looked")
        return (
            f"{head}## What was found against each part\n\n"
            f"| Part | Candidate | {column} |\n|---|---|---|\n"
            f"| Finding passages | BM25 | {outcome} |\n\n"
            f"## What this turns on, having looked{rest}"
        )

    def test_the_conforming_project_passes(self) -> None:
        assert _by_id(run_checks(project("conforming")), "FT-36").outcome is Outcome.PASSED

    def test_a_project_with_no_research_fails_naming_the_file(self, tmp_path) -> None:
        assert "no research.md" in self._reason(self._project(tmp_path))

    def test_a_blank_outcome_names_the_row(self, tmp_path) -> None:
        """The award row. A dash reads as covered and is what this exists to catch."""
        root = self._project(tmp_path, research=self._survey(outcome="\u2014"))

        reason = self._reason(root)

        assert "empty 'Outcome'" in reason
        assert "Finding passages / BM25" in reason

    def test_a_header_with_no_candidate_under_it_fails(self, tmp_path) -> None:
        """The cheapest way to defeat this check, and it passed every other branch."""
        research = self._survey()
        head, _, tail = research.partition("| Finding passages | BM25 | adopted |")
        root = self._project(tmp_path, research=head + tail)

        assert "no candidate under it" in self._reason(root)

    def test_a_row_cut_off_from_its_header_says_what_to_look_for(self, tmp_path) -> None:
        """Hit while writing a survey by hand. A blank line ends a markdown table, so the row
        is read as a table of its own and the section reads as a header with nothing under it.
        The message says so rather than leaving the cause to be found."""
        research = self._survey().replace(
            "|---|---|---|\n| Finding passages", "|---|---|---|\n\n| Finding passages"
        )

        reason = self._reason(self._project(tmp_path, research=research))

        assert "no candidate under it" in reason
        assert "blank line ends a markdown table" in reason
        assert "holds 2 of them" in reason

    def test_a_table_that_renamed_the_column_fails(self, tmp_path) -> None:
        """Reading the rows alone would report nothing here and pass."""
        root = self._project(tmp_path, research=self._survey(column="Notes"))

        assert "no 'Outcome' column" in self._reason(root)

    def test_a_row_too_short_to_reach_the_column_fails(self, tmp_path) -> None:
        """No outcome written at all, which is stronger than one written blank."""
        research = self._survey().replace(
            "| Finding passages | BM25 | adopted |", "| Finding passages | BM25 |"
        )

        assert "empty 'Outcome'" in self._reason(self._project(tmp_path, research=research))

    def test_a_second_table_is_read_against_its_own_header(self, tmp_path) -> None:
        """A blank line ends a table, so the next one does not inherit the first's columns."""
        research = self._survey().replace(
            "| Finding passages | BM25 | adopted |",
            "| Finding passages | BM25 | adopted |\n\n| Part | Outcome |\n|---|---|\n"
            "| Judging | \u2014 |",
        )

        assert "Judging" in self._reason(self._project(tmp_path, research=research))

    def test_a_survey_written_as_prose_fails(self, tmp_path) -> None:
        """A paragraph can say a candidate was looked at and leave every other one out."""
        research = self._survey()
        head, _, tail = research.partition("## What was found against each part")
        _, _, rest = tail.partition("## What this turns on, having looked")
        prose = (
            f"{head}## What was found against each part\n\n"
            f"BM25 was adopted for finding passages, and the hosted service was rejected.\n\n"
            f"## What this turns on, having looked{rest}"
        )

        assert "holds no table" in self._reason(self._project(tmp_path, research=prose))

    def test_a_section_left_empty_fails(self, tmp_path) -> None:
        research = (project("conforming") / "research.md").read_text(encoding="utf-8")
        head, _, _ = research.partition("## What this turns on, having looked")
        emptied = f'{head}## What this turns on, having looked\n\n## What the builder said about it\n\n> "Fine."\n'

        assert "has nothing under" in self._reason(self._project(tmp_path, research=emptied))

    def test_a_survey_quoting_nobody_fails(self, tmp_path) -> None:
        research = (project("conforming") / "research.md").read_text(encoding="utf-8")
        head, _, _ = research.partition("## What the builder said about it")
        unquoted = f"{head}## What the builder said about it\n\nThey agreed with all of it.\n"

        assert "quotes nobody" in self._reason(self._project(tmp_path, research=unquoted))

    def test_a_confirmation_older_than_the_stage_fails(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                'research_confirmed_at = "measure"', 'research_confirmed_at = "research"'
            ),
            encoding="utf-8",
        )

        assert "at stage 'research' and the project is at 'measure'" in self._reason(root)

    def test_it_is_not_applicable_before_the_research_stage(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\n', encoding="utf-8")

        assert _by_id(run_checks(tmp_path), "FT-36").outcome is Outcome.NOT_APPLICABLE


class TestTheShipStage:
    """The fifth gate. FT-31 reads who answers the agent once an end user is on the other end.

    Every fixture here starts from `conforming` and adds a run marked live, which is what
    moves a project to stage `ship` without the brief saying anything.
    """

    def _shipped(
        self,
        tmp_path: Path,
        *,
        answered_by: str | None = "end_user",
        live: bool = True,
        consultations: tuple[str, ...] = (),
        run_answerer: str | None = None,
    ) -> Path:
        """A project that has been through the ship stage, plus one run's channel."""
        root = copied("conforming", tmp_path)
        brief = root / "brief.toml"
        brief.write_text(
            # Advancing a stage means re-reading both accounts and recording the new one.
            brief.read_text(encoding="utf-8")
            .replace(
                'understanding_confirmed_at = "measure"', 'understanding_confirmed_at = "ship"'
            )
            .replace('design_confirmed_at = "measure"', 'design_confirmed_at = "ship"')
            .replace('research_confirmed_at = "measure"', 'research_confirmed_at = "ship"')
            # And the question every gate puts again, which is dated on its own entry.
            .replace('asked_at = "measure"', 'asked_at = "ship"')
            + _SHIP_ENTRIES,
            encoding="utf-8",
        )
        source = sorted(root.glob("runs/**/manifest.json"))[-1].parent
        run = root / "runs" / ("run_live" if live else "run_later")
        run.mkdir(parents=True)
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        manifest["run_id"] = run.name
        manifest["started_at"] = "2099-01-01T00:00:00.000Z"
        manifest["ended_at"] = "2099-01-01T00:00:01.000Z"
        manifest["outcome"] = "completed"
        manifest["live"] = live
        if answered_by is not None:
            manifest["tools"] = manifest["tools"] + [
                {
                    "name": "ask_the_user",
                    "version": "sha256:aaaaaaaaaaaa",
                    "side_effect_class": "read_only",
                    "declared_cost": None,
                    "re_executed": False,
                    "offered": True,
                    "answered_by": answered_by,
                    "permission": None,
                }
            ]
        if run_answerer is not None:
            manifest["end_user"] = {"answered_by": run_answerer}
        (run / "manifest.json").write_text(json.dumps(manifest))
        records = (source / "trajectory.jsonl").read_text(encoding="utf-8")
        for index, answerer in enumerate(consultations):
            records += (
                json.dumps(
                    {
                        "format_version": "0.22",
                        "record_type": "consultation",
                        "record_id": f"c{index}",
                        "run_id": run.name,
                        "parent_id": None,
                        "sequence": 900 + index,
                        "started_at": "2099-01-01T00:00:00.000Z",
                        "ended_at": "2099-01-01T00:00:00.500Z",
                        "error": None,
                        "redactions": [],
                        "omissions": [],
                        "resolution": "answered",
                        "answered_by": answerer,
                    }
                )
                + "\n"
            )
        (run / "trajectory.jsonl").write_text(records, encoding="utf-8")
        return root

    def test_it_does_not_fire_before_a_project_has_shipped(self) -> None:
        report = run_checks(project("conforming"))

        assert _by_id(report, "FT-31").outcome is Outcome.NOT_APPLICABLE
        assert "Fires at stage ship" in _by_id(report, "FT-31").detail

    def test_a_live_run_moves_the_project_to_ship_with_no_brief_change(self, tmp_path) -> None:
        """The one enforcement that fires on an artifact appearing rather than a declaration."""
        report = run_checks(self._shipped(tmp_path))

        assert _by_id(report, "FT-31").outcome is Outcome.PASSED

    def test_a_channel_reaching_the_coding_agent_fails(self, tmp_path) -> None:
        report = run_checks(self._shipped(tmp_path, answered_by="coding_agent"))
        found = _by_id(report, "FT-31")

        assert found.outcome is Outcome.FAILED
        assert "`coding_agent`" in found.findings[0].message

    @pytest.mark.parametrize("answerer", ["coding_agent", "simulated", "canned", "builder"])
    def test_every_stand_in_fails_and_the_two_readers_pass(self, tmp_path, answerer) -> None:
        """`builder` is the author standing in, which is not the person the agent is for."""
        assert (
            _by_id(run_checks(self._shipped(tmp_path, answered_by=answerer)), "FT-31").outcome
            is Outcome.FAILED
        )

    @pytest.mark.parametrize("answerer", ["end_user", "nobody"])
    def test_a_reader_and_a_declared_absence_both_pass(self, tmp_path, answerer) -> None:
        """`nobody` is `unattended()`, and whether that is right is the builder's answer."""
        assert (
            _by_id(run_checks(self._shipped(tmp_path, answered_by=answerer)), "FT-31").outcome
            is Outcome.PASSED
        )

    def test_a_project_with_no_consultation_tool_passes(self, tmp_path) -> None:
        found = _by_id(run_checks(self._shipped(tmp_path, answered_by=None)), "FT-31")

        assert found.outcome is Outcome.PASSED
        assert "No consultation tool is registered" in found.detail

    def test_what_the_run_did_beats_what_the_pipeline_declared(self, tmp_path) -> None:
        """A run can be given another channel, and the trajectory is what that run reached."""
        root = self._shipped(
            tmp_path, answered_by="coding_agent", consultations=("end_user", "end_user")
        )

        assert _by_id(run_checks(root), "FT-31").outcome is Outcome.PASSED

    def test_a_run_given_a_stand_in_fails_even_where_the_pipeline_registered_a_reader(
        self, tmp_path
    ) -> None:
        root = self._shipped(tmp_path, answered_by="end_user", run_answerer="canned")

        assert _by_id(run_checks(root), "FT-31").outcome is Outcome.FAILED

    def test_a_project_at_ship_with_nothing_marked_live_is_told_so(self, tmp_path) -> None:
        """The gate runs before the agent is handed over, so this is a note and not a failure."""
        root = self._shipped(tmp_path, live=False)
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace('stage = "measure"', 'stage = "ship"'),
            encoding="utf-8",
        )
        found = _by_id(run_checks(root), "FT-31")

        assert found.outcome is Outcome.PASSED
        assert "No run under runs/ is marked live" in found.detail

    def test_the_other_checks_read_the_run_that_is_not_live(self, tmp_path) -> None:
        """A live run belongs to an end user, and these checks are about what was built."""
        root = self._shipped(tmp_path)
        report = run_checks(root)

        assert "run_live" not in str(_by_id(report, "FT-13").read)
        assert report.ok

    def test_a_project_whose_every_run_is_live_still_gets_checked(self, tmp_path) -> None:
        """Failing a project that recorded everything would be a false positive."""
        root = self._shipped(tmp_path)
        for existing in sorted(root.glob("runs/**/manifest.json")):
            if existing.parent.name == "run_live":
                continue
            manifest = json.loads(existing.read_text(encoding="utf-8"))
            manifest["live"] = True
            existing.write_text(json.dumps(manifest))
        report = run_checks(root)

        assert _by_id(report, "FT-13").outcome is Outcome.PASSED
        assert any("the checks could read is marked live" in note for note in report.notes)


_SHIP_ENTRIES = """
[entries.someone_there]
status = "answered"
recorded_at = "2026-08-27T09:14:02Z"
answer = "One person, in the chat window, while the run waits."

[entries.live_records]
status = "answered"
recorded_at = "2026-08-27T09:14:02Z"
answer = "Everything, sampled at 1 in 10 once it is past a hundred runs a day."

[entries.watching_live]
status = "answered"
recorded_at = "2026-08-27T09:14:02Z"
answer = "The builder reads five live runs every Monday."

[entries.stored_output]
status = "answered"
recorded_at = "2026-08-27T09:14:02Z"
answer = "The run's own answer, in the chat window. Nothing is kept between runs."
"""


class TestFT25AndAConsultationTheGraphNoLongerHas:
    """Specified in the taxonomy since the first draft and registered 2026-08-16.

    Dogfood #4 elicited a consultation answer, built the tool onto a node, redesigned the back
    half, and shipped a graph with no consultation in it. The entry still read `answered` with
    the builder's own words, and every check passed over it.
    """

    def _project(self, tmp_path: Path, *, answer: str, tools: list[dict] | None = None) -> Path:
        root = copied("conforming", tmp_path)
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                'answer = "Nothing. Every input the agent needs is in the collection."',
                f"answer = {json.dumps(answer)}",
            ),
            encoding="utf-8",
        )
        if tools is not None:
            path = sorted(root.glob("runs/**/manifest.json"))[-1]
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["tools"] = tools
            path.write_text(json.dumps(manifest))
        return root

    def _consult(self, *, offered: bool = True) -> dict:
        return {
            "name": "ask_the_user",
            "version": "sha256:aaaaaaaaaaaa",
            "side_effect_class": "read_only",
            "declared_cost": None,
            "re_executed": False,
            "offered": offered,
            "answered_by": "end_user",
            "permission": None,
        }

    def test_an_elicited_capability_missing_from_the_graph_fails(self, tmp_path) -> None:
        root = self._project(
            tmp_path,
            answer="It should ask when it cannot decide, and about taste. Give it agency here.",
        )
        found = _by_id(run_checks(root), "FT-25")

        assert found.outcome is Outcome.FAILED
        assert "no consultation tool is registered" in found.findings[0].message

    def test_a_registered_tool_no_node_was_given_fails_too(self, tmp_path) -> None:
        """`offered` is false for a tool the project registered and handed to nobody."""
        root = self._project(
            tmp_path,
            answer="It should ask the reader which of two candidates they meant.",
            tools=[self._consult(offered=False)],
        )
        found = _by_id(run_checks(root), "FT-25")

        assert found.outcome is Outcome.FAILED
        assert "no node was given it" in found.findings[0].message

    def test_a_tool_reaching_a_node_passes(self, tmp_path) -> None:
        root = self._project(
            tmp_path,
            answer="It should ask the reader which of two candidates they meant.",
            tools=[self._consult()],
        )

        assert _by_id(run_checks(root), "FT-25").outcome is Outcome.PASSED

    def test_a_tool_that_asked_nothing_is_named_on_the_pass(self, tmp_path) -> None:
        """One project certified here evaluated a pipeline whose consult was unreachable."""
        root = self._project(
            tmp_path,
            answer="It should ask the reader which of two candidates they meant.",
            tools=[self._consult()],
        )
        found = _by_id(run_checks(root), "FT-25")

        assert found.outcome is Outcome.PASSED
        assert "asked nothing through it" in (found.detail or "")
        assert "ask_the_user" in (found.detail or "")

    def test_a_run_that_did_ask_is_not_named(self, tmp_path) -> None:
        root = self._project(
            tmp_path,
            answer="It should ask the reader which of two candidates they meant.",
            tools=[self._consult()],
        )
        path = sorted(root.glob("runs/**/manifest.json"))[-1]
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["counts"]["consultation"] = 2
        path.write_text(json.dumps(manifest))
        found = _by_id(run_checks(root), "FT-25")

        assert found.outcome is Outcome.PASSED
        assert "asked nothing" not in (found.detail or "")

    def test_the_rollouts_that_asked_nothing_are_named_too(self, tmp_path) -> None:
        """DF5-D20: a stand-in was configured on 249 rollouts and 276 of them asked nothing.

        A rollout is refused over a channel reaching a person, so an evaluation always answers
        with a stand-in, and a project reads its evaluation more often than any single run.
        """
        root = self._project(
            tmp_path,
            answer="It should ask the reader which of two candidates they meant.",
            tools=[self._consult()],
        )
        found = _by_id(run_checks(root), "FT-25")

        assert found.outcome is Outcome.PASSED
        assert "rollout(s) in the newest results file asked through it" in found.detail
        assert any(name.startswith("evals/results/") for name in found.read)

    def test_an_evaluation_that_did_ask_is_not_named(self, tmp_path) -> None:
        root = self._project(
            tmp_path,
            answer="It should ask the reader which of two candidates they meant.",
            tools=[self._consult()],
        )
        path = sorted(root.glob("evals/results/*.json"))[-1]
        results = json.loads(path.read_text(encoding="utf-8"))
        node = sorted(results["nodes"])[0]
        results["nodes"][node]["consultations"] = 3
        path.write_text(json.dumps(results))
        found = _by_id(run_checks(root), "FT-25")

        assert found.outcome is Outcome.PASSED
        assert "results file" not in (found.detail or "")
        assert "The run read here asked nothing through it" in found.detail

    def test_a_project_with_no_results_file_is_told_only_about_its_run(self, tmp_path) -> None:
        """A `prototype` produces none, and a note about one it does not have says nothing."""
        root = self._project(
            tmp_path,
            answer="It should ask the reader which of two candidates they meant.",
            tools=[self._consult()],
        )
        for stale in root.glob("evals/results/*.json"):
            stale.unlink()
        found = _by_id(run_checks(root), "FT-25")

        assert found.outcome is Outcome.PASSED
        assert "results file" not in (found.detail or "")

    def test_an_answer_opening_on_a_negation_is_nothing_to_ask(self) -> None:
        """The `conforming` fixture answers in a sentence, not with the bare word."""
        found = _by_id(run_checks(project("conforming")), "FT-25")

        assert found.outcome is Outcome.PASSED
        assert "nothing to ask" in (found.detail or "")

    def test_a_brief_with_no_consultation_entry_is_blocked_rather_than_failed(
        self, tmp_path
    ) -> None:
        """FT-24 is what reports a missing required answer, and it should report it once."""
        root = copied("conforming", tmp_path)
        brief = root / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        start = text.index("[entries.consultation]")
        brief.write_text(text[:start] + text[text.index("[entries.", start + 1) :], "utf-8")

        assert _by_id(run_checks(root), "FT-25").outcome is Outcome.BLOCKED


class TestFT32AndABriefThatStoppedDescribingTheCode:
    """Dogfood #4's `tool_effects` said three tools, all read-only. The code had six, two of
    which wrote. It was corrected only when the builder said "Update the brief"."""

    def _with_tools(self, tmp_path: Path, classes: list[str]) -> Path:
        root = copied("conforming", tmp_path)
        path = sorted(root.glob("runs/**/manifest.json"))[-1]
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["tools"] = [
            {
                "name": f"tool_{index}",
                "version": "sha256:aaaaaaaaaaaa",
                "side_effect_class": declared,
                "declared_cost": None,
                "re_executed": False,
                "offered": True,
            }
            for index, declared in enumerate(classes)
        ]
        path.write_text(json.dumps(manifest))
        return root

    def test_a_class_the_answer_never_mentions_fails(self, tmp_path) -> None:
        root = self._with_tools(tmp_path, ["read_only", "writes"])
        found = _by_id(run_checks(root), "FT-32")

        assert found.outcome is Outcome.FAILED
        assert "writes" in found.findings[0].message
        assert "tool_1 (writes)" in found.findings[0].message

    def test_the_answer_describing_the_class_in_the_builders_words_passes(self) -> None:
        """ "a read-only search" satisfies `read_only`. A code identifier is not a better answer."""
        assert _by_id(run_checks(project("conforming")), "FT-32").outcome is Outcome.PASSED

    def test_a_tool_the_answer_never_names_is_not_a_failure(self, tmp_path) -> None:
        """The entry is about what reaches outside the run, and a name is not that."""
        root = self._with_tools(tmp_path, ["read_only", "read_only"])

        assert _by_id(run_checks(root), "FT-32").outcome is Outcome.PASSED

    def test_read_only_is_not_a_class_the_answer_has_to_name(self, tmp_path) -> None:
        """`read_only` is the answer "nothing reaches outside the run", written in the
        builder's words as "it asks the reader". Found live: an answer describing both tools
        correctly failed on the word.
        """
        root = self._with_tools(tmp_path, ["read_only"])
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                'answer = "Nothing. The one tool is a read-only search over a fixed collection."',
                'answer = "It asks the reader, and it writes nothing anywhere."',
            ),
            encoding="utf-8",
        )

        assert _by_id(run_checks(root), "FT-32").outcome is Outcome.PASSED

    def test_a_run_with_no_tool_has_nothing_to_describe(self, tmp_path) -> None:
        root = self._with_tools(tmp_path, [])
        found = _by_id(run_checks(root), "FT-32")

        assert found.outcome is Outcome.PASSED
        assert "registered no tool" in (found.detail or "")


class TestFT33AndABuildLogThatStopped:
    """Dogfood #4's log is the best artifact any dogfood produced and its last write is two
    days before the run ended, so the run's largest methodological finding is not in it."""

    def _with_log(self, tmp_path: Path, *, written: str) -> Path:
        root = copied("conforming", tmp_path)
        log = root / "BUILD-LOG.md"
        log.write_text("# Build log\n\nWhat was asked, and what was decided.\n", "utf-8")
        stamp = datetime.fromisoformat(written).timestamp()
        os.utime(log, (stamp, stamp))
        return root

    def test_a_log_older_than_the_newest_run_fails(self, tmp_path) -> None:
        root = self._with_log(tmp_path, written="2020-01-01T00:00:00+00:00")
        found = _by_id(run_checks(root), "FT-33")

        assert found.outcome is Outcome.FAILED
        assert "2020-01-01" in found.findings[0].message

    def test_a_log_written_since_the_newest_run_passes(self, tmp_path) -> None:
        root = self._with_log(tmp_path, written="2099-01-01T00:00:00+00:00")

        assert _by_id(run_checks(root), "FT-33").outcome is Outcome.PASSED

    def test_a_project_keeping_no_log_passes(self) -> None:
        """Whether to keep one is the builder's, so this fires on a log that stopped."""
        found = _by_id(run_checks(project("conforming")), "FT-33")

        assert found.outcome is Outcome.PASSED
        assert "keeps no BUILD-LOG.md" in (found.detail or "")


class TestTheNoteThatFiresOnAChangeRatherThanAtAGate:
    """`DF4-D7`: every enforcement fires on time, and every failure dogfood #4 found fires on
    change. This is the one that reads the pipeline moving under the brief."""

    def _project(self, tmp_path: Path, *, recorded: str | None, confirmed: str | None) -> Path:
        root = copied("conforming", tmp_path)
        path = sorted(root.glob("runs/**/manifest.json"))[-1]
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if recorded is None:
            # A run an earlier version wrote, which the fixture's own runs no longer are.
            manifest.pop("behaviour_fingerprint", None)
        else:
            manifest["behaviour_fingerprint"] = recorded
        path.write_text(json.dumps(manifest))
        brief = root / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        line = [one for one in text.splitlines() if one.startswith("confirmed_against")][0]
        brief.write_text(
            text.replace(line, f'confirmed_against = "{confirmed}"' if confirmed else ""),
            encoding="utf-8",
        )
        return root

    def _note(self, report) -> str | None:
        wanted = ("pipeline has moved", "read against")
        return next((n for n in report.notes if any(w in n for w in wanted)), None)

    def test_a_moved_pipeline_names_the_entries_that_describe_it(self, tmp_path) -> None:
        root = self._project(tmp_path, recorded="sha256:new", confirmed="sha256:old")
        note = self._note(run_checks(root))

        assert note is not None
        assert "sha256:old" in note and "sha256:new" in note
        assert "agency_boundary" in note and "tool_effects" in note

    def test_it_quotes_no_answer(self, tmp_path) -> None:
        """An answer can be a paragraph, and a fragment is something to act on unread."""
        root = self._project(tmp_path, recorded="sha256:new", confirmed="sha256:old")
        note = self._note(run_checks(root))

        assert "Every input the agent needs" not in (note or "")

    def test_it_names_no_entry_the_brief_does_not_carry(self, tmp_path) -> None:
        root = self._project(tmp_path, recorded="sha256:new", confirmed="sha256:old")
        note = self._note(run_checks(root)) or ""

        assert "context_limit" not in note

    def test_it_names_no_entry_with_nothing_answered(self, tmp_path) -> None:
        """An `unanswered` entry has no answer to have gone stale, and FT-24 reports it."""
        root = self._project(tmp_path, recorded="sha256:new", confirmed="sha256:old")
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                '[entries.backend]\nstatus = "answered"',
                '[entries.backend]\nstatus = "unanswered"',
            ),
            encoding="utf-8",
        )
        note = self._note(run_checks(root)) or ""

        assert "backend" not in note
        assert "agency_boundary" in note

    def test_an_unmoved_pipeline_says_nothing(self, tmp_path) -> None:
        root = self._project(tmp_path, recorded="sha256:same", confirmed="sha256:same")

        assert self._note(run_checks(root)) is None

    def test_a_brief_that_never_recorded_one_is_told_to(self, tmp_path) -> None:
        root = self._project(tmp_path, recorded="sha256:new", confirmed=None)
        note = self._note(run_checks(root))

        assert note is not None
        assert 'confirmed_against = "sha256:new"' in note

    def test_a_run_written_before_the_field_existed_says_nothing(self, tmp_path) -> None:
        """Nothing is concluded from a manifest an earlier version wrote."""
        root = self._project(tmp_path, recorded=None, confirmed="sha256:old")

        assert self._note(run_checks(root)) is None

    def test_it_fails_nothing(self, tmp_path) -> None:
        root = self._project(tmp_path, recorded="sha256:new", confirmed="sha256:old")

        assert run_checks(root).ok


class TestFT37AndAHeadlineFromAPipelineThatIsGone:
    """Dogfood #5 shipped at tier `evaluated` on a headline of 0.0 from a six-node pipeline,
    with nine nodes in the shipped graph, and every gate green. Nothing in the results file
    said what produced it."""

    def _project(
        self, tmp_path: Path, *, measured: str | None, recorded: str = "sha256:same"
    ) -> Path:
        root = _shipped_copy(tmp_path, fingerprint=recorded)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text(encoding="utf-8"))
        if measured is None:
            results["config"].pop("behaviour_fingerprint", None)
        else:
            results["config"]["behaviour_fingerprint"] = measured
        path.write_text(json.dumps(results))
        return root

    def test_the_suite_writes_the_stamp_into_the_results_file(self) -> None:
        """Read off the fixture, which is a real evaluation replayed rather than hand-written."""
        results = json.loads(
            (project("conforming") / "evals/results/held-out.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            sorted(project("conforming").glob("runs/**/manifest.json"))[-1].read_text(
                encoding="utf-8"
            )
        )

        assert results["config"]["behaviour_fingerprint"] == manifest["behaviour_fingerprint"]

    def test_a_headline_from_the_current_pipeline_passes(self, tmp_path) -> None:
        root = self._project(tmp_path, measured="sha256:same")

        assert _by_id(run_checks(root), "FT-37").outcome is Outcome.PASSED

    def test_a_headline_from_a_pipeline_that_moved_fails(self, tmp_path) -> None:
        root = self._project(tmp_path, measured="sha256:old", recorded="sha256:new")
        found = _by_id(run_checks(root), "FT-37")

        assert found.outcome is Outcome.FAILED
        assert "sha256:old" in found.findings[0].message
        assert "sha256:new" in found.findings[0].message

    def test_a_results_file_written_before_the_field_existed_is_blocked(self, tmp_path) -> None:
        """Blocked and not passed: nothing joins the number to what produced it."""
        root = self._project(tmp_path, measured=None)
        found = _by_id(run_checks(root), "FT-37")

        assert found.outcome is Outcome.BLOCKED
        assert "records no behaviour_fingerprint" in (found.detail or "")

    def test_a_run_written_before_the_field_existed_blocks_it(self, tmp_path) -> None:
        """Blocked on the other side: the pipeline it describes is unrecorded."""
        root = self._project(tmp_path, measured="sha256:same")
        for path in root.glob("runs/**/manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest.pop("behaviour_fingerprint", None)
            path.write_text(json.dumps(manifest))
        found = _by_id(run_checks(root), "FT-37")

        assert found.outcome is Outcome.BLOCKED
        assert "carries no behaviour_fingerprint" in (found.detail or "")

    def test_it_is_not_applicable_before_the_ship_stage(self) -> None:
        """A pipeline moves several times an hour while it is built, and an evaluation is what
        clears this."""
        assert _by_id(run_checks(project("conforming")), "FT-37").outcome is (
            Outcome.NOT_APPLICABLE
        )

    def test_before_ship_the_same_comparison_is_a_note(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text(encoding="utf-8"))
        results["config"]["behaviour_fingerprint"] = "sha256:measured-under-something-else"
        path.write_text(json.dumps(results))
        report = run_checks(root)

        assert report.ok
        [note] = [n for n in report.notes if "was measured over" in n]
        assert "sha256:measured-under-something-else" in note
        assert "FT-37 fails on this from stage ship" in note


class TestFT38AndABriefNobodyReadAgain:
    """Dogfood #5's `agency_boundary` named two agentic steps in a project that had none at any
    commit. The note naming the entries due printed on all 21 runs of the suite the log records
    and was acted on none of them."""

    def _project(self, tmp_path: Path, *, confirmed: str | None) -> Path:
        root = _shipped_copy(tmp_path, fingerprint="sha256:same")
        brief = root / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        line = [one for one in text.splitlines() if one.startswith("confirmed_against")][0]
        brief.write_text(
            text.replace(line, f'confirmed_against = "{confirmed}"' if confirmed else ""),
            encoding="utf-8",
        )
        return root

    def test_a_brief_read_against_the_current_pipeline_passes(self, tmp_path) -> None:
        root = self._project(tmp_path, confirmed="sha256:same")

        assert _by_id(run_checks(root), "FT-38").outcome is Outcome.PASSED

    def test_a_brief_that_records_nothing_fails_and_names_the_entries(self, tmp_path) -> None:
        root = self._project(tmp_path, confirmed=None)
        found = _by_id(run_checks(root), "FT-38")

        assert found.outcome is Outcome.FAILED
        assert "nothing recorded" in found.findings[0].message
        assert "agency_boundary" in found.findings[0].message

    def test_a_brief_read_against_something_older_fails(self, tmp_path) -> None:
        root = self._project(tmp_path, confirmed="sha256:old")
        found = _by_id(run_checks(root), "FT-38")

        assert found.outcome is Outcome.FAILED
        assert "sha256:old" in found.findings[0].message

    def test_a_run_written_before_the_field_existed_blocks_it(self, tmp_path) -> None:
        """Nothing is concluded from a manifest an earlier version wrote."""
        root = self._project(tmp_path, confirmed="sha256:old")
        for path in root.glob("runs/**/manifest.json"):
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest.pop("behaviour_fingerprint", None)
            path.write_text(json.dumps(manifest))
        found = _by_id(run_checks(root), "FT-38")

        assert found.outcome is Outcome.BLOCKED
        assert "carries no behaviour_fingerprint" in (found.detail or "")

    def test_it_quotes_no_answer(self, tmp_path) -> None:
        """An answer can be a paragraph, and a fragment is something to act on unread."""
        root = self._project(tmp_path, confirmed="sha256:old")

        assert (
            "Every input the agent needs"
            not in _by_id(run_checks(root), "FT-38").findings[0].message
        )

    def test_the_note_stops_where_the_check_fires(self, tmp_path) -> None:
        """One comparison, reported once. It was a note at every stage until 2026-08-25."""
        root = self._project(tmp_path, confirmed="sha256:old")
        report = run_checks(root)

        assert [n for n in report.notes if "read against" in n] == []

    def test_it_is_not_applicable_before_the_ship_stage(self) -> None:
        assert _by_id(run_checks(project("conforming")), "FT-38").outcome is (
            Outcome.NOT_APPLICABLE
        )

    def test_a_brief_with_no_entry_about_the_pipeline_passes(self, tmp_path) -> None:
        """Nothing here goes stale when the pipeline moves, so there is nothing to re-read."""
        from simple_agents.conformance.checks import entries_about_the_pipeline

        root = self._project(tmp_path, confirmed=None)
        brief = root / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        for name in entries_about_the_pipeline(Brief.read(brief)):
            text = text.replace(
                f'[entries.{name}]\nstatus = "answered"',
                f'[entries.{name}]\nstatus = "unanswered"',
            )
        brief.write_text(text, encoding="utf-8")
        found = _by_id(run_checks(root), "FT-38")

        assert found.outcome is Outcome.PASSED
        assert "No answered entry describes the pipeline" in (found.detail or "")


class TestTheReportNamesWhatItRead:
    """Dogfood #5's corpus passes wrote 2,310 of its 2,669 runs under the default role, so the
    checks that read a run certified a two-node summariser. The report named the path and never
    the pipeline."""

    def test_the_header_names_the_nodes_of_the_run_the_checks_read(self) -> None:
        report = run_checks(project("conforming"))

        assert report.reading is not None
        assert "hunt → verify" in report.reading
        assert "2 node(s)" in report.reading

    def test_it_names_the_field_that_keeps_a_batch_pass_out(self) -> None:
        assert "RunEnvelope(role=...)" in (run_checks(project("conforming")).reading or "")

    def test_it_is_a_header_line_rather_than_a_note(self) -> None:
        """A clean project prints no notes, and this prints on every project."""
        report = run_checks(project("conforming"))

        assert report.notes == ()
        assert report.text().splitlines()[2].startswith("reading runs/")

    def test_the_json_carries_it(self) -> None:
        assert "hunt → verify" in (run_checks(project("conforming")).to_record()["reading"] or "")

    def test_a_project_with_no_run_says_nothing(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\n', encoding="utf-8")

        assert run_checks(tmp_path).reading is None


class TestTheRolloutsAResultsFileNoLongerDescribes:
    """Three cases in dogfood #5: a directory cleared and re-run into, a results file naming a
    directory that is not in the tree, and a directory with no results file. The recorded
    rollout paths were absolute into the tree the project ran in, so the join is by identity."""

    def _note(self, report) -> str | None:
        wanted = ("are not on disk", "rollout(s) that started after")
        return next((n for n in report.notes if any(w in n for w in wanted)), None)

    def test_a_results_file_whose_directory_is_gone_is_reported(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text(encoding="utf-8"))
        results["eval_id"] = "eval_000000000000"
        path.write_text(json.dumps(results))
        note = self._note(run_checks(root))

        assert note is not None
        assert "runs/eval_000000000000/ does not exist" in note

    def test_a_rollout_that_started_after_the_file_was_written_is_reported(self, tmp_path) -> None:
        root = copied("conforming", tmp_path)
        results = json.loads((root / "evals/results/held-out.json").read_text(encoding="utf-8"))
        rollout = sorted((root / "runs" / "eval" / results["eval_id"]).iterdir())[0]
        manifest = json.loads((rollout / "manifest.json").read_text(encoding="utf-8"))
        manifest["started_at"] = "2099-01-01T00:00:00.000Z"
        (rollout / "manifest.json").write_text(json.dumps(manifest))
        note = self._note(run_checks(root))

        assert note is not None
        assert rollout.name in note

    def test_the_conforming_project_says_nothing(self) -> None:
        assert self._note(run_checks(project("conforming"))) is None

    def test_a_rescored_file_is_not_read(self, tmp_path) -> None:
        """Its identity is the rescoring configuration's and names no directory, so this would
        tell the reader to re-score one that never existed."""
        root = copied("conforming", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text(encoding="utf-8"))
        results["eval_id"] = "eval_000000000000"
        results["config"]["scored_from"] = "run_directory"
        path.write_text(json.dumps(results))

        assert self._note(run_checks(root)) is None

    def test_it_fails_nothing(self, tmp_path) -> None:
        """The directory is named off the results file, so renaming the file's identity is what
        leaves the runs on disk and the join broken."""
        root = copied("conforming", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text(encoding="utf-8"))
        results["eval_id"] = "eval_000000000000"
        path.write_text(json.dumps(results))
        report = run_checks(root)

        assert report.ok
        assert self._note(report) is not None


class TestWhatTheLiveRunsDid:
    """45% of dogfood #5's log came after `ship`, and the only artifact that road leaves is the
    live run. Every check but FT-31 reads a run that is not live, and a project always has
    one."""

    def _note(self, report) -> str | None:
        return next((n for n in report.notes if "an end user made" in n), None)

    def test_a_shipped_project_is_told_which_runs_are_not_certified(self, tmp_path) -> None:
        root = _shipped_copy(tmp_path, fingerprint="sha256:same")
        note = self._note(run_checks(root))

        assert note is not None
        assert "runs/run_live" in note

    def test_it_names_the_run_the_checks_read_instead(self, tmp_path) -> None:
        root = _shipped_copy(tmp_path, fingerprint="sha256:same")
        note = self._note(run_checks(root)) or ""

        assert "made while building" in note

    def test_a_project_that_has_not_shipped_says_nothing(self) -> None:
        assert self._note(run_checks(project("conforming"))) is None

    def test_it_fails_nothing(self, tmp_path) -> None:
        assert run_checks(_shipped_copy(tmp_path, fingerprint="sha256:same")).ok


def _shipped_copy(tmp_path: Path, *, fingerprint: str) -> Path:
    """The conforming project with one live run, which is what puts it at stage `ship`.

    Every manifest carries `fingerprint`, so a test that moves the pipeline moves it in one
    place. The brief's `confirmed_against` is set to match unless the test changes it.
    """
    root = copied("conforming", tmp_path)
    brief = root / "brief.toml"
    text = brief.read_text(encoding="utf-8")
    line = [one for one in text.splitlines() if one.startswith("confirmed_against")][0]
    brief.write_text(
        text.replace(line, f'confirmed_against = "{fingerprint}"')
        .replace('understanding_confirmed_at = "measure"', 'understanding_confirmed_at = "ship"')
        .replace('design_confirmed_at = "measure"', 'design_confirmed_at = "ship"')
        .replace('research_confirmed_at = "measure"', 'research_confirmed_at = "ship"')
        # And the question every gate puts again, which is dated on its own entry.
        .replace('asked_at = "measure"', 'asked_at = "ship"')
        + _SHIP_ENTRIES,
        encoding="utf-8",
    )
    source = sorted(root.glob("runs/**/manifest.json"))[-1].parent
    for path in root.glob("runs/**/manifest.json"):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["behaviour_fingerprint"] = fingerprint
        path.write_text(json.dumps(manifest))
    results_path = root / "evals/results/held-out.json"
    results = json.loads(results_path.read_text(encoding="utf-8"))
    results["config"]["behaviour_fingerprint"] = fingerprint
    results_path.write_text(json.dumps(results))

    run = root / "runs" / "run_live"
    run.mkdir(parents=True)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["run_id"] = run.name
    manifest["started_at"] = "2099-01-01T00:00:00.000Z"
    manifest["ended_at"] = "2099-01-01T00:00:01.000Z"
    manifest["outcome"] = "completed"
    manifest["live"] = True
    manifest["behaviour_fingerprint"] = fingerprint
    (run / "manifest.json").write_text(json.dumps(manifest))
    (run / "trajectory.jsonl").write_text(
        (source / "trajectory.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return root


class TestTheDocumentedNotesAreWhatIsPrinted:
    """`docs/conformance.md` §4.4 shows the notes the report prints, and nothing ran them.

    The paths and stamps are one project's; the sentence around them is the code's. A sample
    that is trimmed to fit reads as the whole note, and the reader acts on what it does not
    say: two of these were written short and one omitted the sentence naming the action.
    """

    def documented(self) -> str:
        from simple_agents import docs_path

        text = (Path(docs_path()) / "conformance.md").read_text(encoding="utf-8")
        return " ".join(text[text.index("### 4.4 The notes under the checks") :].split())

    def _artifacts(self, root: Path, **fields):
        from simple_agents.conformance.artifacts import Artifacts

        return Artifacts(
            **{"root": root, "brief": None, "run_dir": None, "results": None, **fields}
        )

    def _run(self, where: Path, name: str, **manifest) -> Path:
        run = where / name
        run.mkdir(parents=True)
        (run / "manifest.json").write_text(json.dumps(manifest))
        return run

    def test_the_live_runs_note_is_what_is_printed(self, tmp_path) -> None:
        from simple_agents.conformance.run import _what_the_live_runs_did

        live = self._run(
            tmp_path / "runs" / "live" / "2026-08-24",
            "run_9e12",
            started_at="2026-08-24T21:51:59.618Z",
        )
        built = self._run(tmp_path / "runs" / "eval" / "eval_4b02", "cut-1")
        found = self._artifacts(tmp_path, run_dir=built, live_run=live)

        note = _what_the_live_runs_did(found, "ship")

        assert note is not None
        assert " ".join(note.split()) in self.documented()

    def test_the_open_comments_note_is_what_is_printed(self, tmp_path) -> None:
        from simple_agents.conformance.brief import Brief
        from simple_agents.conformance.run import _comments_awaiting

        (tmp_path / "comments.toml").write_text(
            "[[comment]]\n"
            'at = "recommend/judge_candidates"\n'
            'said = "Why does this rank the whole catalogue before truncating?"\n'
            'status = "open"\n',
            encoding="utf-8",
        )
        found = self._artifacts(tmp_path)

        note = _comments_awaiting(found, Brief(path=None, tier="prototype"))

        assert note is not None
        assert " ".join(note.split()) in self.documented()

    def test_the_stale_headline_note_is_what_is_printed(self, tmp_path) -> None:
        from simple_agents.conformance.run import _the_number_came_from_elsewhere

        built = self._run(
            tmp_path / "runs", "run_7f2a", behaviour_fingerprint="sha256:94e59c769d747f81"
        )
        results = tmp_path / "evals" / "results" / "held-out.json"
        results.parent.mkdir(parents=True)
        results.write_text(
            json.dumps({"config": {"behaviour_fingerprint": "sha256:213998182146fc28"}})
        )
        found = self._artifacts(tmp_path, run_dir=built, results=results)

        note = _the_number_came_from_elsewhere(
            Context(artifacts=found, brief=Brief(path=None, tier="evaluated"), taxonomy=taxonomy()),
            "measure",
        )

        assert note is not None
        assert " ".join(note.split()) in self.documented()

    def test_the_pipeline_moved_note_is_what_is_printed(self, tmp_path) -> None:
        """The fourth note in `docs/conformance.md` §4.4, which nothing ran until it went a
        sentence out of date."""
        import json

        from simple_agents.conformance.run import _config_of, _the_pipeline_moved

        run = tmp_path / "runs" / "run_7f2a"
        run.mkdir(parents=True)
        (run / "manifest.json").write_text(
            json.dumps(
                {
                    "run_id": "run_7f2a",
                    "behaviour_fingerprint": "sha256:94e59c769d747f81",
                    "started_at": "2026-09-01T00:00:00Z",
                    "outcome": "completed",
                    "evaluation": None,
                }
            ),
            encoding="utf-8",
        )
        brief = tmp_path / "brief.toml"
        brief.write_text(
            'tier = "evaluated"\nstage = "build"\n'
            'confirmed_against = "sha256:213998182146fc28"\n'
            + "".join(
                f'\n[entries.{name}]\nstatus = "answered"\n'
                f'recorded_at = "2026-08-27T09:14:02Z"\nanswer = "something"\n'
                for name in (
                    "agency_boundary",
                    "consultation",
                    "presentation",
                    "backend",
                    "budget",
                    "tool_effects",
                )
            ),
            encoding="utf-8",
        )
        found = Artifacts.discover(tmp_path)
        ctx = Context(artifacts=found, brief=Brief.read(brief), taxonomy=taxonomy())
        note = _the_pipeline_moved(ctx.brief, ctx, "build")

        assert note is not None
        assert " ".join(note.split()) in " ".join(self.documented().split())
        assert _config_of(ctx) is None, "no results file, so the read is the widened one"

    def test_the_rollout_drift_note_is_what_is_printed(self, tmp_path) -> None:
        from simple_agents.conformance.run import _rollouts_written_after

        directory = tmp_path / "runs" / "eval" / "eval_7423149289e3"
        # Named the way an evaluation names a rollout, `<example-id>-<k>`, because the note
        # shows the first three of a lexical sort and `cut-1, cut-10, cut-11` is what a run of
        # twenty-one plainly numbered ones would print.
        for day in range(23, 30):
            for k in range(3):
                self._run(
                    directory, f"cut-2024-09-{day}-{k}", started_at="2026-08-21T11:53:00.000Z"
                )
        results = tmp_path / "evals" / "results" / "held-out.json"
        results.parent.mkdir(parents=True)
        results.write_text("{}")
        found = self._artifacts(tmp_path, results=results)

        note = _rollouts_written_after(
            found, directory, "runs/eval/eval_7423149289e3/", "2026-08-21T11:46:26.485Z"
        )

        assert note is not None
        assert " ".join(note.split()) in self.documented()


class TestFT34AndTheDesignTheBuilderAgreedTo:
    """Dogfood #4's design was settled in conversation. `pipeline_shape` recorded one sentence,
    four alternatives were weighed, the right one was in a brainstorm answer one stage up, and
    the builder read the design by reading what was built, two stages and two days later."""

    def _project(self, tmp_path: Path, design: str | None, *, confirmed: str = "measure") -> Path:
        root = copied("conforming", tmp_path)
        if design is None:
            (root / "design.md").unlink()
        else:
            (root / "design.md").write_text(design, encoding="utf-8")
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                'design_confirmed_at = "measure"',
                f'design_confirmed_at = "{confirmed}"' if confirmed else "",
            ),
            encoding="utf-8",
        )
        return root

    THREE = (
        "# How it is built\n\n"
        "## What it does, step by step\nIt searches, then it answers.\n\n"
        "## What it holds on to between runs\nNothing.\n\n"
        "## The product\nA terminal; asking starts a run, and the printed answer is read once.\n\n"
        "## What the builder said about it\n"
    )

    def test_a_project_with_no_design_fails(self, tmp_path) -> None:
        found = _by_id(run_checks(self._project(tmp_path, None)), "FT-34")

        assert found.outcome is Outcome.FAILED
        assert "no design.md" in found.findings[0].message

    def test_the_four_sections_filled_and_quoted_pass(self, tmp_path) -> None:
        root = self._project(tmp_path, self.THREE + "> Yes, that is it.\n")

        assert _by_id(run_checks(root), "FT-34").outcome is Outcome.PASSED

    def test_a_missing_product_section_fails_and_names_it(self, tmp_path) -> None:
        """A design that never says what the end user opens is a display over stored output."""
        design = self.THREE.replace(
            "## The product\nA terminal; asking starts a run, and the printed answer "
            "is read once.\n\n",
            "",
        )
        found = _by_id(run_checks(self._project(tmp_path, design + "> Yes.\n")), "FT-34")

        assert found.outcome is Outcome.FAILED
        assert "The product" in found.findings[0].message

    def test_an_empty_section_fails_and_names_it(self, tmp_path) -> None:
        root = self._project(tmp_path, self.THREE.replace("Nothing.", ""))
        found = _by_id(run_checks(root), "FT-34")

        assert found.outcome is Outcome.FAILED
        assert "What it holds on to between runs" in found.findings[0].message

    def test_a_section_quoting_nobody_fails(self, tmp_path) -> None:
        """The builder's words go there verbatim, and prose about them is not that."""
        root = self._project(tmp_path, self.THREE + "The builder agreed with the plan.\n")
        found = _by_id(run_checks(root), "FT-34")

        assert found.outcome is Outcome.FAILED
        assert "quotes nobody" in found.findings[0].message

    @pytest.mark.parametrize(
        "quoted",
        ['> "This is not what I asked for."', 'He said "this is not what I asked for".'],
    )
    def test_either_way_of_quoting_passes(self, tmp_path, quoted) -> None:
        """A blockquote and quotation marks both say a passage is quoted."""
        root = self._project(tmp_path, self.THREE + quoted + "\n")

        assert _by_id(run_checks(root), "FT-34").outcome is Outcome.PASSED

    def test_a_confirmation_from_an_earlier_stage_fails(self, tmp_path) -> None:
        root = self._project(tmp_path, self.THREE + "> Yes.\n", confirmed="shape")
        found = _by_id(run_checks(root), "FT-34")

        assert found.outcome is Outcome.FAILED
        assert "confirms design.md at stage 'shape'" in found.findings[0].message

    def test_a_project_before_shape_is_not_held_to_it(self, tmp_path) -> None:
        """There is no design at `brainstorm`, which is why this is not FT-29's second file."""
        root = copied("conforming", tmp_path)
        (root / "design.md").unlink()
        shutil.rmtree(root / "runs")
        shutil.rmtree(root / "evals" / "results")
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8")
            .replace('tier = "evaluated"', 'tier = "prototype"')
            .replace('"measure"', '"brainstorm"'),
            encoding="utf-8",
        )
        found = _by_id(run_checks(root), "FT-34")

        assert found.outcome is Outcome.NOT_APPLICABLE
        assert "Fires at stage shape" in (found.detail or "")


class TestTheAnswersNoDecisionRestsOn:
    """`DF4-D2`: the answer that made the built design wrong was recorded on day one, one entry
    away from the answer that made it look right, and nothing put them side by side."""

    def _with_from(self, tmp_path: Path, named: list[str]) -> Path:
        root = copied("conforming", tmp_path)
        brief = root / "brief.toml"
        listed = ", ".join(f'"{name}"' for name in named)
        text = brief.read_text(encoding="utf-8")
        start = text.index("[decisions.shape_of_this_project]")
        end = text.index("[decisions.", start + 1)
        block = text[start:end]
        rewritten = re.sub(r"^from = \[.*\]$", f"from = [{listed}]", block, flags=re.M)
        brief.write_text(text[:start] + rewritten + text[end:], encoding="utf-8")
        return root

    def _note(self, report) -> str | None:
        return next((n for n in report.notes if "no shape or presentation" in n), None)

    def test_an_answer_no_decision_names_is_printed(self, tmp_path) -> None:
        root = self._with_from(tmp_path, ["what_it_does", "purpose", "end_user"])
        note = self._note(run_checks(root))

        assert note is not None
        assert "finished_version" in note and "smallest_worthwhile" in note

    def test_naming_every_one_says_nothing(self, tmp_path) -> None:
        """The list is read off the question set, so a new one leaves this failing."""
        from simple_agents.conformance import QUESTIONS

        wanted = [q.name for q in QUESTIONS if q.about_what_is_wanted]
        root = self._with_from(tmp_path, wanted)

        assert self._note(run_checks(root)) is None

    def test_it_reads_no_answer_about_how_or_how_well(self, tmp_path) -> None:
        """`budget` and `who_labels` bear on no shape decision, and printing them is noise."""
        root = self._with_from(tmp_path, [])
        note = self._note(run_checks(root)) or ""

        assert "budget" not in note and "who_labels" not in note

    def test_a_from_naming_nothing_is_reported(self, tmp_path) -> None:
        """A decision resting on a typo rests on nothing."""
        root = self._with_from(tmp_path, ["finished_vershion"])
        note = next((n for n in run_checks(root).notes if "no entry for" in n), None)

        assert note is not None
        assert "finished_vershion" in note

    def test_it_fails_nothing(self, tmp_path) -> None:
        root = self._with_from(tmp_path, [])

        assert run_checks(root).ok


class TestTheComplementOverNothing:
    def test_a_project_whose_shaping_kinds_are_not_applicable_says_nothing(self, tmp_path) -> None:
        """A complement over no decision is every answer the brief holds, which is noise."""
        root = copied("conforming", tmp_path)
        brief = root / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        for name in ("shape_of_this_project", "presentation_of_this_project"):
            start = text.index(f"[decisions.{name}]")
            rest = text[start + 1 :]
            end = start + 1 + rest.index("[decisions.") if "[decisions." in rest else len(text)
            block = text[start:end]
            text = text.replace(
                block, block.replace('status = "agreed"', 'status = "not_applicable"')
            )
        brief.write_text(text, encoding="utf-8")

        assert not [n for n in run_checks(root).notes if "no shape or presentation" in n]


class TestTheFixturesAreCurrent:
    """A fixture written under an older format is not the artifact a check will meet.

    `run_checks` parses these files itself, while `EvalResults.read` refuses a superseded
    version outright, so one reader refuses a stale file and the other accepts it silently.
    That is why the fixtures sat two results versions and one trajectory version behind
    without a single test going red. `scripts/build_conformance_fixtures.py` regenerates them
    from the committed cassette, offline, in seconds.
    """

    REGENERATE = "run `uv run python scripts/build_conformance_fixtures.py`"

    def _versions(self, pattern: str, key: str) -> dict[str, set[str]]:
        """Which version each matching file carries, keyed by version."""
        found: dict[str, set[str]] = {}
        for path in sorted(PROJECTS.glob(pattern)):
            record = json.loads(path.read_text())
            found.setdefault(str(record.get(key)), set()).add(str(path.relative_to(PROJECTS)))
        return found

    def test_every_manifest_carries_the_current_formats(self):
        from simple_agents.records.manifest import MANIFEST_FORMAT_VERSION
        from simple_agents.records.trajectory import FORMAT_VERSION as TRAJECTORY_VERSION

        for key, current in (
            ("format_version", MANIFEST_FORMAT_VERSION),
            ("trajectory_format_version", TRAJECTORY_VERSION),
        ):
            seen = self._versions("*/runs/**/manifest.json", key)
            assert seen, f"no fixture manifests found; {self.REGENERATE}"
            assert set(seen) == {current}, (
                f"fixture manifests carry {key} {sorted(seen)} and the writer writes "
                f"{current!r}, so a check that reads a {current}-only field would be "
                f"exercised against files that cannot carry one. {self.REGENERATE}."
            )

    def test_every_results_file_carries_the_current_format(self):
        from simple_agents.evaluation import EVAL_FORMAT_VERSION

        seen = self._versions("*/evals/results/*.json", "eval_format_version")
        assert seen, f"no fixture results files found; {self.REGENERATE}"
        assert set(seen) == {EVAL_FORMAT_VERSION}, (
            f"fixture results files carry {sorted(seen)} and the writer writes "
            f"{EVAL_FORMAT_VERSION!r}. {self.REGENERATE}."
        )

    def test_every_fixture_holds_what_the_library_writes_today(self, tmp_path):
        """Regenerate and compare, because a version claim is not the contents.

        The three tests above read what a fixture declares about its format. They passed while
        fourteen results files carried metric definitions the library had stopped writing, so
        what is checked here is every byte the generator produces, less the timestamps and
        durations that differ between two runs of it.
        """
        import sys

        sys.path.insert(0, str(PROJECTS.parents[2] / "scripts"))
        from build_conformance_fixtures import main as build

        build(tmp_path, announce=False)

        def settled(text: str) -> str:
            """The file, less what two runs of the generator legitimately disagree about.

            Record ids are renumbered in order of first appearance rather than blanked, so a
            parent that stopped pointing at its child still shows up as a difference.
            """
            text = re.sub(r"\d{4}-\d\d-\d\dT[\d:.]+Z", "<when>", text)
            text = re.sub(r'("[a-z_]*(?:ms|seconds)"): \d+', r"\1: <how long>", text)
            seen: dict[str, str] = {}
            return re.sub(
                r"rec_[0-9a-f]+",
                lambda m: seen.setdefault(m.group(0), f"rec_{len(seen)}"),
                text,
            )

        fresh = {p.relative_to(tmp_path): p for p in tmp_path.rglob("*") if p.is_file()}
        committed = {p.relative_to(PROJECTS): p for p in PROJECTS.rglob("*") if p.is_file()}

        assert set(fresh) == set(committed), (
            f"the generator no longer produces the committed fixture files. "
            f"only committed: {sorted(set(committed) - set(fresh))[:5]}; "
            f"only generated: {sorted(set(fresh) - set(committed))[:5]}. {self.REGENERATE}."
        )
        stale = [
            str(rel)
            for rel, path in sorted(committed.items())
            if settled(path.read_text()) != settled(fresh[rel].read_text())
        ]
        assert not stale, (
            f"{len(stale)} fixture file(s) hold contents the library no longer writes, "
            f"starting with {stale[:5]}. A check runs against these rather than against a "
            f"real project, so one written by an older library exercises nothing. "
            f"{self.REGENERATE}."
        )

    def test_every_trajectory_record_carries_the_current_format(self):
        from simple_agents.records.trajectory import FORMAT_VERSION

        # `unreadable-trajectory` holds a line that is not a record at all. A line carrying no
        # version makes no claim about one, so what has to be current is every claim made.
        seen: set[str] = set()
        for path in sorted(PROJECTS.glob("*/runs/**/trajectory.jsonl")):
            for line in path.read_text().splitlines():
                if line.strip():
                    version = json.loads(line).get("format_version")
                    if version is not None:
                        seen.add(str(version))
        assert seen, f"no fixture trajectories found; {self.REGENERATE}"
        assert seen == {FORMAT_VERSION}, (
            f"fixture trajectory records carry {sorted(seen)} and the writer writes "
            f"{FORMAT_VERSION!r}. {self.REGENERATE}."
        )


class TestFT40AndTheStepsNobodyBuilt:
    """What the check says about a `NotBuilt` step, at each gate and from each source.

    It read the newest run's manifest and nothing else until 2026-08-26, which meant it could
    only see steps a run had reached. A skeleton has not run, by definition, so a project whose
    every step was a placeholder reported `pass` at `ship`. It reads the code now, and the
    manifest is the fallback for a project whose code will not import or declares no pipeline
    the view can find.
    """

    VIEWS = Path(__file__).parent / "fixtures" / "view_projects"

    def report_at(self, tmp_path: Path, stage: str):
        """The skeleton fixture at one stage, which is the one project with every step owed."""
        target = tmp_path / "skeleton"
        shutil.copytree(self.VIEWS / "skeleton", target)
        brief = target / "brief.toml"
        brief.write_text(
            re.sub(
                r'^stage = ".*"$',
                f'stage = "{stage}"',
                brief.read_text(encoding="utf-8"),
                count=1,
                flags=re.MULTILINE,
            ),
            encoding="utf-8",
        )
        return _by_id(run_checks(target), "FT-40")

    def test_at_shape_the_count_is_the_shape_working(self, tmp_path) -> None:
        held = self.report_at(tmp_path, "shape")

        assert held.outcome is Outcome.PASSED
        assert "13 step(s) declared and not built" in held.detail
        assert "That is what `shape` produces" in held.detail

    def test_at_build_the_count_is_what_is_still_owed(self, tmp_path) -> None:
        held = self.report_at(tmp_path, "build")

        assert held.outcome is Outcome.PASSED
        assert "13 step(s) declared and not built" in held.detail
        assert "fails from stage `ship`" in held.detail

    def test_at_ship_it_fails_with_no_run_to_read(self, tmp_path) -> None:
        """The defect this closed: no run, so nothing to read, so `pass` at the ship gate."""
        held = self.report_at(tmp_path, "ship")

        assert held.outcome is Outcome.FAILED
        assert held.read == ("agent.py",)
        assert "13" in held.findings[0].message

    def test_a_step_is_named_the_way_the_view_addresses_it(self, tmp_path) -> None:
        """One step, one name, across the check and the page."""
        held = self.report_at(tmp_path, "shape")

        assert "triage/research.pick_sources" in held.detail
        assert "reindex/dedupe" in held.detail

    def test_a_built_pipeline_with_one_placeholder_counts_the_one(self, tmp_path) -> None:
        held = _by_id(run_checks(self.VIEWS / "branching"), "FT-40")

        assert held.outcome is Outcome.PASSED
        assert held.read == ("agent.py",)
        assert "1 step(s) declared and not built: reindex/dedupe." in held.detail

    def test_a_project_with_no_code_reads_its_manifest(self) -> None:
        """A brief and runs and no `agent.py`, which every conformance fixture is."""
        held = _by_id(run_checks(project("conforming")), "FT-40")

        assert held.outcome is Outcome.PASSED
        assert held.read and held.read[0].endswith("manifest.json")

    def test_a_project_with_no_code_and_no_run_has_declared_no_step(self, tmp_path) -> None:
        """Day zero: nothing to read on either side, and nothing owed either."""
        target = tmp_path / "day-zero"
        target.mkdir()
        (target / "brief.toml").write_text(
            'tier = "prototype"\nstage = "brainstorm"\n', encoding="utf-8"
        )
        held = _by_id(run_checks(target), "FT-40")

        assert held.outcome is Outcome.PASSED
        assert "No agent.py" in held.detail

    def test_code_that_declares_no_findable_pipeline_falls_back_to_the_manifest(
        self, tmp_path
    ) -> None:
        """A project predating the factory convention imports and yields nothing.

        Reporting `pass` off `agent.py` there would cite a reading that never happened, so the
        manifest answers and the report names it.
        """
        target = copied("no-evaluation", tmp_path)
        (target / "agent.py").write_text("VERSION = 1\n", encoding="utf-8")
        held = _by_id(run_checks(target), "FT-40")

        assert held.outcome is Outcome.PASSED
        assert held.read and held.read[0].endswith("manifest.json")

    def test_code_that_declares_nothing_and_never_ran_is_blocked(self, tmp_path) -> None:
        """Neither source can answer, which is `blocked` and not `pass`."""
        target = tmp_path / "bare"
        target.mkdir()
        (target / "brief.toml").write_text(
            'tier = "prototype"\nstage = "build"\n', encoding="utf-8"
        )
        (target / "agent.py").write_text("VERSION = 1\n", encoding="utf-8")
        held = _by_id(run_checks(target), "FT-40")

        assert held.outcome is Outcome.BLOCKED
        assert "no run to read a manifest from either" in held.detail

    def test_neither_source_readable_is_blocked_and_keeps_the_entry_ids_intact(
        self, tmp_path
    ) -> None:
        """`str.capitalize` lowercases the rest of the sentence, which cost FT-13 its name."""
        target = copied("no-evaluation", tmp_path)
        (target / "agent.py").write_text("VERSION = 1\n", encoding="utf-8")
        for manifest in target.rglob("manifest.json"):
            manifest.write_text("not json", encoding="utf-8")
        held = _by_id(run_checks(target), "FT-40")

        assert held.outcome is Outcome.BLOCKED
        assert held.detail.startswith("Agent.py declares no pipeline")
        assert "which FT-13 reports" in held.detail

    def test_code_that_will_not_import_is_blocked_and_the_rest_still_report(self, tmp_path) -> None:
        """A project whose `agent.py` raises still deserves its report."""
        target = copied("no-evaluation", tmp_path)
        (target / "agent.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
        report = run_checks(target)
        held = _by_id(report, "FT-40")

        assert held.outcome is Outcome.PASSED  # the manifest answered
        assert len(report.checks) == len(CHECKS)


class TestARunThatStoppedAndWasNeverContinued:
    """FT-41. Dogfood #5 wired the stopping half of consultation and never wrote the other.

    `engaged` mode was written, selected whenever anybody was on the site, and unreachable, so
    across 2,415 manifests none carried a suspension and none carried a `resumed_at`. The
    procedure's `build` step is what makes a project produce one; this is the backstop for a
    project whose runs do stop.
    """

    def stopped(self, tmp_path: Path, *, resumed: bool, stage: str) -> Path:
        """The conforming fixture with one run's manifest made to say it stopped."""
        target = copied("conforming", tmp_path)
        brief = target / "brief.toml"
        brief.write_text(
            re.sub(
                r'^stage = ".*"$',
                f'stage = "{stage}"',
                brief.read_text(encoding="utf-8"),
                count=1,
                flags=re.MULTILINE,
            ),
            encoding="utf-8",
        )
        manifest = sorted(target.rglob("manifest.json"))[0]
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        raw["suspensions"] = [
            {
                "suspended_at": "2026-08-26T10:00:00Z",
                "node_id": "hunt",
                "waiting_for": "which of these did they mean?",
                "resumed_at": "2026-08-26T10:04:00Z" if resumed else None,
            }
        ]
        manifest.write_text(json.dumps(raw), encoding="utf-8")
        return target

    def test_a_project_whose_runs_never_stopped_passes_and_says_so(self) -> None:
        held = _by_id(run_checks(project("conforming")), "FT-41")

        assert held.outcome is Outcome.PASSED
        assert "stopped to ask anything" in held.detail
        assert "`Shelved` or `Unavailable`" in held.detail

    def test_before_ship_an_open_suspension_is_a_note(self, tmp_path) -> None:
        held = _by_id(run_checks(self.stopped(tmp_path, resumed=False, stage="build")), "FT-41")

        assert held.outcome is Outcome.PASSED
        assert "1 still waiting, 0 continued" in held.detail
        assert "fails from stage `ship`" in held.detail

    def test_at_ship_an_open_suspension_with_nothing_ever_resumed_fails(self, tmp_path) -> None:
        held = _by_id(run_checks(self.stopped(tmp_path, resumed=False, stage="ship")), "FT-41")

        assert held.outcome is Outcome.FAILED
        assert held.read == ("runs/",)
        assert "Pipeline.resume" in held.findings[0].message

    def test_a_run_that_was_continued_passes_at_ship(self, tmp_path) -> None:
        """The half the failure is about is written, so a run waiting is a run waiting."""
        held = _by_id(run_checks(self.stopped(tmp_path, resumed=True, stage="ship")), "FT-41")

        assert held.outcome is Outcome.PASSED
        assert "1 still waiting" not in held.detail
        assert "0 still waiting, 1 continued" in held.detail

    def test_a_project_with_no_run_has_stopped_nothing(self, tmp_path) -> None:
        target = tmp_path / "day-zero"
        target.mkdir()
        (target / "brief.toml").write_text(
            'tier = "prototype"\nstage = "brainstorm"\n', encoding="utf-8"
        )
        held = _by_id(run_checks(target), "FT-41")

        assert held.outcome is Outcome.PASSED
        assert "No run under runs/ yet" in held.detail

    def test_it_reads_every_run_and_not_only_the_newest(self, tmp_path) -> None:
        """FT-35 scopes to one pipeline's runs. A resume is a fact about the project."""
        target = self.stopped(tmp_path, resumed=False, stage="ship")
        oldest = sorted(target.rglob("manifest.json"))[-1]
        raw = json.loads(oldest.read_text(encoding="utf-8"))
        raw["suspensions"] = [
            {
                "suspended_at": "2026-08-20T09:00:00Z",
                "node_id": "hunt",
                "waiting_for": "which one?",
                "resumed_at": "2026-08-20T09:30:00Z",
            }
        ]
        oldest.write_text(json.dumps(raw), encoding="utf-8")
        held = _by_id(run_checks(target), "FT-41")

        assert held.outcome is Outcome.PASSED
        assert "1 still waiting, 1 continued" in held.detail


class TestTheMCPServerChangedUnderTheProject:
    """FT-43. A description and a schema come from a server the project does not control, so
    both can move with nothing in the project changing."""

    def with_mcp(self, tmp_path: Path, entries: list[dict]) -> Path:
        """The conforming fixture, with its newest agent run recording these servers."""
        target = copied("conforming", tmp_path)
        # Every agent manifest, so which one the check reads as newest does not matter here.
        for path in target.glob("runs/**/manifest.json"):
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("role", "agent") != "agent":
                continue
            raw["mcp"] = entries
            path.write_text(json.dumps(raw), encoding="utf-8")
        return target

    def test_a_project_with_no_mcp_server_passes(self) -> None:
        held = _by_id(run_checks(project("conforming")), "FT-43")

        assert held.outcome is Outcome.PASSED
        assert "no MCP server" in held.detail

    def test_a_server_that_has_not_moved_passes(self, tmp_path) -> None:
        target = self.with_mcp(
            tmp_path, [{"server": "tickets", "read": "live", "drift": [], "undeclared": []}]
        )
        held = _by_id(run_checks(target), "FT-43")

        assert held.outcome is Outcome.PASSED
        assert "none had moved" in held.detail

    def test_a_replayed_run_has_nothing_to_compare(self, tmp_path) -> None:
        target = self.with_mcp(
            tmp_path, [{"server": "tickets", "read": "replayed", "drift": [], "undeclared": []}]
        )
        held = _by_id(run_checks(target), "FT-43")

        assert held.outcome is Outcome.PASSED
        assert "served from the recording" in held.detail

    def test_a_moved_server_fails_and_names_what_changed(self, tmp_path) -> None:
        target = self.with_mcp(
            tmp_path,
            [
                {
                    "server": "tickets",
                    "read": "live",
                    "drift": [
                        {"tool": "tickets_create", "difference": "schema"},
                        {"tool": "tickets_purge", "difference": "added"},
                    ],
                    "undeclared": [],
                }
            ],
        )
        held = _by_id(run_checks(target), "FT-43")

        assert held.outcome is Outcome.FAILED
        assert "tickets" in held.findings[0].message
        assert "tickets_create (schema)" in held.findings[0].message
        assert "tickets_purge (added)" in held.findings[0].message


class TestADecisionNamesSomethingNeverBuilt:
    """FT-42, and the report's complement. Dogfood #5's `agency_boundary` named two steps that
    decide for themselves and the project shipped with none, with every check passing.

    Both sides are exercised: a name under `produces` that no run recorded, and what the runs
    recorded that no decision names.
    """

    def at_stage(self, tmp_path: Path, name: str, stage: str) -> Path:
        """One fixture with its declared stage rewritten."""
        target = copied(name, tmp_path)
        brief = target / "brief.toml"
        brief.write_text(
            re.sub(
                r'^stage = ".*"$',
                f'stage = "{stage}"',
                brief.read_text(encoding="utf-8"),
                count=1,
                flags=re.MULTILINE,
            ),
            encoding="utf-8",
        )
        return target

    def test_names_that_every_run_recorded_pass(self) -> None:
        held = _by_id(run_checks(project("conforming")), "FT-42")

        assert held.outcome is Outcome.PASSED
        assert "were all recorded by runs under runs/" in held.detail

    def test_before_ship_a_name_no_run_recorded_is_a_note(self, tmp_path) -> None:
        target = self.at_stage(tmp_path, "decision-produced-nothing", "build")
        held = _by_id(run_checks(target), "FT-42")

        assert held.outcome is Outcome.PASSED
        assert "a_step_that_was_never_built (shape_of_this_project)" in held.detail
        assert "fails from stage `ship`" in held.detail

    def test_at_ship_a_name_no_run_recorded_fails(self, tmp_path) -> None:
        target = self.at_stage(tmp_path, "decision-produced-nothing", "ship")
        held = _by_id(run_checks(target), "FT-42")

        assert held.outcome is Outcome.FAILED
        assert "brief.toml" in held.read and "runs/" in held.read
        assert "a_step_that_was_never_built" in held.findings[0].message

    def test_a_project_naming_nothing_says_what_the_field_is_for(self, tmp_path) -> None:
        target = copied("conforming", tmp_path)
        brief = target / "brief.toml"
        brief.write_text(
            re.sub(r"^produces = .*$", "", brief.read_text(encoding="utf-8"), flags=re.MULTILINE),
            encoding="utf-8",
        )
        held = _by_id(run_checks(target), "FT-42")

        assert held.outcome is Outcome.PASSED
        assert "No decision names what it became" in held.detail

    def test_names_with_no_run_to_read_them_against_are_blocked(self, tmp_path) -> None:
        target = copied("conforming", tmp_path)
        for manifest in target.rglob("manifest.json"):
            manifest.write_text("not json at all", encoding="utf-8")
        held = _by_id(run_checks(target), "FT-42")

        assert held.outcome is Outcome.BLOCKED
        assert "no run under runs/ could be read" in held.detail

    def test_a_name_a_run_of_another_role_recorded_passes_and_says_which(self, tmp_path) -> None:
        """A decision about the corpus names the nodes of the pipeline that builds it."""
        target = copied("conforming", tmp_path)
        for manifest in target.rglob("manifest.json"):
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            raw["role"] = "corpus"
            manifest.write_text(json.dumps(raw), encoding="utf-8")
        held = _by_id(run_checks(target), "FT-42")

        assert held.outcome is Outcome.PASSED
        assert "hunt (recorded by corpus runs)" in held.detail

    def test_a_not_applicable_decision_names_nothing_to_look_for(self, tmp_path) -> None:
        """A project saying it has no decision of that kind is not a project with a claim."""
        target = self.at_stage(tmp_path, "decision-produced-nothing", "ship")
        brief = target / "brief.toml"
        text = brief.read_text(encoding="utf-8").replace(
            '[decisions.shape_of_this_project]\nkind = "shape"\nstatus = "agreed"\nrecorded_at = "2026-08-27T09:14:02Z"',
            '[decisions.shape_of_this_project]\nkind = "shape"\nstatus = "not_applicable"\nrecorded_at = "2026-08-27T09:14:02Z"',
        )
        brief.write_text(text, encoding="utf-8")
        held = _by_id(run_checks(target), "FT-42")

        assert held.outcome is Outcome.PASSED

    def test_it_reads_every_run_and_not_only_the_newest(self, tmp_path) -> None:
        """A project with more than one pipeline runs whichever it was asked for.

        `verify` is dropped from the newest run and stays in the older ones, which is what a
        second pipeline looks like to a check that reads one manifest.
        """
        target = self.at_stage(tmp_path, "conforming", "ship")
        newest = max(
            target.rglob("manifest.json"),
            key=lambda path: json.loads(path.read_text(encoding="utf-8"))["started_at"],
        )
        raw = json.loads(newest.read_text(encoding="utf-8"))
        raw["nodes"] = [n for n in raw["nodes"] if n["node_id"] != "verify"]
        newest.write_text(json.dumps(raw), encoding="utf-8")
        held = _by_id(run_checks(target), "FT-42")

        assert held.outcome is Outcome.PASSED, held.findings and held.findings[0].message
        assert "6 name(s)" in held.detail

    def test_the_report_names_nothing_where_every_name_is_covered(self) -> None:
        report = run_checks(project("conforming"))

        assert not [note for note in report.notes if "runs recorded that no decision" in note]

    def test_the_report_names_what_no_decision_covers(self, tmp_path) -> None:
        target = copied("conforming", tmp_path)
        brief = target / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace('produces = ["hunt", "verify"]', ""),
            encoding="utf-8",
        )
        note = _the_produced_note(run_checks(target))

        assert "2 of 2 node id(s): hunt, verify" in note
        assert "recorded `changed`" in note

    def test_the_report_dates_a_name_the_newest_run_does_not_carry(self, tmp_path) -> None:
        target = copied("conforming", tmp_path)
        brief = target / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace('produces = ["hunt", "verify"]', ""),
            encoding="utf-8",
        )
        oldest = sorted(
            (path for path in target.rglob("manifest.json")),
            key=lambda path: json.loads(path.read_text(encoding="utf-8"))["started_at"],
        )[0]
        raw = json.loads(oldest.read_text(encoding="utf-8"))
        raw["started_at"] = "2020-01-01T00:00:00.000Z"
        raw["nodes"] = raw["nodes"] + [{"node_id": "a_step_since_removed", "node_kind": "llm"}]
        oldest.write_text(json.dumps(raw), encoding="utf-8")
        note = _the_produced_note(run_checks(target))

        assert "a_step_since_removed (last seen 2020-01-01)" in note
        assert "1 of them were last seen before" in note

    def test_constants_a_run_predating_the_field_never_recorded_are_unread(self, tmp_path) -> None:
        """Silence would read as a project whose code defines no number."""
        target = copied("conforming", tmp_path)
        for manifest in target.rglob("manifest.json"):
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            raw.pop("constants", None)
            manifest.write_text(json.dumps(raw), encoding="utf-8")
        note = _the_produced_note(run_checks(target))

        assert "Constants: unread" in note
        assert "format 0.33" in note

    def test_the_note_waits_for_shape(self) -> None:
        """Before `shape` there is no code for a decision to have produced anything in."""
        brief = Brief.read(project("conforming") / "brief.toml")
        produced = produced_across(project("conforming") / "runs")

        assert _produced_by_no_decision(brief, produced, "research") is None
        assert _produced_by_no_decision(brief, produced, "brainstorm") is None


def _the_produced_note(report) -> str | None:
    """The report's note about what the runs recorded that no decision names."""
    found = [note for note in report.notes if "runs recorded that no decision" in note]
    return found[0] if found else None


class TestReadingProducesOutOfTheBrief:
    """What a brief may record under `produces`, and what it is refused for.

    Four kinds carry it. `presentation` and `measurement` leave nothing in a run record to
    join a name against, so a brief naming one on either is refused rather than ignored: a
    field nothing reads is a field a coding agent will fill in and trust.
    """

    def read(self, raw: dict) -> tuple:
        return decisions_from(raw, "brief.toml")

    def test_a_list_of_names_is_read_back(self) -> None:
        held = self.read(
            {
                "d": {
                    "kind": "shape",
                    "status": "agreed",
                    "recorded_at": "2026-08-27T09:14:02Z",
                    "produces": ["a", "b"],
                }
            }
        )

        assert held[0].produces == ("a", "b")

    def test_absent_is_an_empty_tuple(self) -> None:
        held = self.read(
            {"d": {"kind": "shape", "status": "agreed", "recorded_at": "2026-08-27T09:14:02Z"}}
        )

        assert held[0].produces == ()

    @pytest.mark.parametrize("kind", ["dependency", "shape", "constant", "prompt_rule"])
    def test_the_four_kinds_that_carry_it(self, kind: str) -> None:
        held = self.read(
            {
                "d": {
                    "kind": kind,
                    "status": "agreed",
                    "recorded_at": "2026-08-27T09:14:02Z",
                    "produces": ["x"],
                }
            }
        )

        assert held[0].produces == ("x",)

    @pytest.mark.parametrize("kind", ["presentation", "measurement"])
    def test_the_two_that_do_not_are_refused_by_name(self, kind: str) -> None:
        with pytest.raises(ConfigurationError) as raised:
            self.read(
                {
                    "d": {
                        "kind": kind,
                        "status": "agreed",
                        "recorded_at": "2026-08-27T09:14:02Z",
                        "produces": ["x"],
                    }
                }
            )

        assert "dependency, shape, constant, prompt_rule" in str(raised.value)
        assert "Remove `produces`" in str(raised.value)

    def test_a_bare_string_says_what_to_write_instead(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            self.read(
                {
                    "d": {
                        "kind": "shape",
                        "status": "agreed",
                        "recorded_at": "2026-08-27T09:14:02Z",
                        "produces": "hunt",
                    }
                }
            )

        assert 'produces = ["hunt"]' in str(raised.value)

    def test_every_kind_that_carries_it_says_what_it_names(self) -> None:
        """The CLI prints this, so a kind carrying the field with nothing to say is a gap."""
        for entry in DECISION_KINDS:
            assert (entry.produces is not None) == (entry.name in PRODUCING_KINDS)


class TestWhatTheRunsRecordedProducing:
    """`produced_across`, which both FT-42 and the report's note read."""

    def test_it_reads_every_run_under_the_directory(self) -> None:
        found = produced_across(project("conforming") / "runs")

        assert found.runs_read == 9
        assert set(found.nodes) == {"hunt", "verify"}
        assert set(found.tools) == {"catalogue_search"}
        assert found.constants_recorded

    def test_a_run_the_project_made_for_itself_is_read_and_says_which_role(self, tmp_path) -> None:
        """A decision about a corpus names the nodes of the pipeline that builds it.

        One project's `dependency` decision named four nodes and six constants of a
        `role="corpus"` pipeline, and reading the agent's runs alone reported ten built names
        as never recorded.
        """
        target = copied("conforming", tmp_path)
        for manifest in target.rglob("manifest.json"):
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            raw["role"] = "corpus"
            manifest.write_text(json.dumps(raw), encoding="utf-8")
        found = produced_across(target / "runs")

        assert found.runs_read == 9
        assert found.what_it_is("hunt") == "node id"
        assert found.where_from("hunt") == "recorded by corpus runs"

    def test_a_name_only_the_agents_runs_carry_says_nothing_about_where(self) -> None:
        found = produced_across(project("conforming") / "runs")

        assert found.where_from("hunt") == ""
        assert found.where_from("never recorded by anything") == ""

    def test_a_name_two_roles_recorded_is_the_agents(self, tmp_path) -> None:
        """A node the agent runs is the agent's, whatever else also ran it."""
        target = copied("conforming", tmp_path)
        one = sorted(target.rglob("manifest.json"))[0]
        raw = json.loads(one.read_text(encoding="utf-8"))
        raw["role"] = "corpus"
        one.write_text(json.dumps(raw), encoding="utf-8")
        found = produced_across(target / "runs")

        assert found.roles["hunt"] == {"agent", "corpus"}
        assert found.where_from("hunt") == ""

    def test_a_name_carries_the_day_of_the_newest_run_that_had_it(self, tmp_path) -> None:
        target = copied("conforming", tmp_path)
        oldest = min(
            target.rglob("manifest.json"),
            key=lambda path: json.loads(path.read_text(encoding="utf-8"))["started_at"],
        )
        raw = json.loads(oldest.read_text(encoding="utf-8"))
        raw["started_at"] = "2020-01-01T00:00:00.000Z"
        raw["nodes"] = raw["nodes"] + [{"node_id": "gone", "node_kind": "llm"}]
        oldest.write_text(json.dumps(raw), encoding="utf-8")
        found = produced_across(target / "runs")

        assert found.nodes["gone"] == "2020-01-01"
        assert found.nodes["hunt"] == found.newest_day
        assert found.what_it_is("gone") == "node id"

    def test_a_directory_that_is_not_there_reads_as_nothing(self, tmp_path) -> None:
        found = produced_across(tmp_path / "runs")

        assert found.runs_read == 0
        assert found.every_name() == set()
        assert found.what_it_is("hunt") is None


class TestTheProducedNoteOnAProjectWithNoRun:
    """A project before its first run has nothing for either direction to read.

    The constants sentence says the runs predate format `0.33`, which of a project with no
    run is a statement about runs that do not exist.
    """

    def test_it_says_nothing(self, tmp_path) -> None:
        target = tmp_path / "day-zero"
        target.mkdir()
        (target / "brief.toml").write_text(
            f'tier = "prototype"\nstage = "shape"\n\n[decisions.d]\n'
            f'kind = "shape"\nstatus = "agreed"\nrecorded_at = "{STAMP}"\n'
            f'chose = "two steps"\n',
            encoding="utf-8",
        )
        report = run_checks(target)

        assert not [note for note in report.notes if "runs recorded that no decision" in note]
        assert _by_id(report, "FT-42").outcome is Outcome.PASSED


class TestConstantsOnRunsThatPredateTheField:
    """Manifests carry `constants` from format `0.33`.

    A project that recorded `produces` on a `constant` decision and has not run since
    upgrading has nothing to join those names against, and failing it at `ship` would say the
    project never built numbers it has.
    """

    def older(self, tmp_path: Path, stage: str) -> Path:
        target = copied("conforming", tmp_path)
        for manifest in target.rglob("manifest.json"):
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            raw.pop("constants", None)
            raw["format_version"] = "0.32"
            manifest.write_text(json.dumps(raw), encoding="utf-8")
        brief = target / "brief.toml"
        brief.write_text(
            re.sub(
                r'^stage = ".*"$',
                f'stage = "{stage}"',
                brief.read_text(encoding="utf-8"),
                count=1,
                flags=re.MULTILINE,
            ),
            encoding="utf-8",
        )
        return target

    def test_a_constant_name_is_left_out_rather_than_failed(self, tmp_path) -> None:
        held = _by_id(run_checks(self.older(tmp_path, "ship")), "FT-42")

        assert held.outcome is Outcome.PASSED
        assert "3 name(s) only a `constant` decision records are left out" in held.detail
        assert "format 0.33" in held.detail

    def test_the_names_of_other_kinds_are_still_read(self, tmp_path) -> None:
        """Leaving the constants out is not leaving the check out."""
        target = self.older(tmp_path, "ship")
        brief = target / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                'produces = ["hunt", "verify"]', 'produces = ["hunt", "never_built"]', 1
            ),
            encoding="utf-8",
        )
        held = _by_id(run_checks(target), "FT-42")

        assert held.outcome is Outcome.FAILED
        assert "never_built" in held.findings[0].message

    def test_a_name_two_kinds_record_is_still_read(self, tmp_path) -> None:
        """Left out only where a `constant` decision is the one thing naming it."""
        target = self.older(tmp_path, "ship")
        brief = target / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                'produces = ["hunt", "verify"]', 'produces = ["hunt", "verify", "SEED"]', 1
            ),
            encoding="utf-8",
        )
        held = _by_id(run_checks(target), "FT-42")

        assert held.outcome is Outcome.FAILED
        assert "SEED" in held.findings[0].message


class TestReadingRunsNothingWrote:
    """`produced_across` reads files on disk, and a report that raised on one would say
    nothing about anything else it checked."""

    def written(self, tmp_path: Path, manifest: object) -> Path:
        run = tmp_path / "runs" / "run_1"
        run.mkdir(parents=True)
        (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return tmp_path / "runs"

    def test_a_node_entry_that_is_not_a_table_is_skipped(self, tmp_path) -> None:
        where = self.written(
            tmp_path,
            {"started_at": "2026-08-27T00:00:00.000Z", "nodes": ["hunt", {"node_id": "verify"}]},
        )
        found = produced_across(where)

        assert set(found.nodes) == {"verify"}

    def test_a_nodes_field_that_is_not_a_list_is_skipped(self, tmp_path) -> None:
        where = self.written(
            tmp_path, {"started_at": "2026-08-27T00:00:00.000Z", "nodes": {"node_id": "hunt"}}
        )

        assert produced_across(where).nodes == {}

    def test_a_node_id_that_is_not_a_string_is_skipped(self, tmp_path) -> None:
        where = self.written(
            tmp_path,
            {"started_at": "2026-08-27T00:00:00.000Z", "nodes": [{"node_id": 7}, {"a": 1}]},
        )

        assert produced_across(where).nodes == {}

    def test_a_manifest_nothing_can_parse_is_not_a_run_this_read(self, tmp_path) -> None:
        run = tmp_path / "runs" / "run_1"
        run.mkdir(parents=True)
        (run / "manifest.json").write_text("{ not json", encoding="utf-8")
        found = produced_across(tmp_path / "runs")

        assert found.runs_read == 0
        assert found.constants_recorded is False


class TestABriefWritingProducesWrongly:
    """A typo in the brief reaches a builder as guidance rather than as a traceback."""

    def read(self, value: dict) -> tuple:
        return decisions_from(
            {
                "d": {
                    "kind": "shape",
                    "status": "agreed",
                    "recorded_at": "2026-08-27T09:14:02Z",
                    **value,
                }
            },
            "brief.toml",
        )

    @pytest.mark.parametrize("field", ["produces", "from"])
    def test_a_number_says_what_the_field_takes(self, field: str) -> None:
        with pytest.raises(ConfigurationError) as raised:
            self.read({field: 5})

        assert f"{field} as int" in str(raised.value)
        assert f'{field} = ["first", "second"]' in str(raised.value)

    @pytest.mark.parametrize("field", ["produces", "from"])
    def test_a_table_says_the_same(self, field: str) -> None:
        with pytest.raises(ConfigurationError) as raised:
            self.read({field: {"a": 1}})

        assert f"{field} as dict" in str(raised.value)

    def test_an_empty_produces_on_a_kind_that_carries_none_is_still_refused(self) -> None:
        """`produces = []` reads as an answer, and these kinds have none to give."""
        with pytest.raises(ConfigurationError):
            decisions_from(
                {
                    "d": {
                        "kind": "measurement",
                        "status": "agreed",
                        "recorded_at": "2026-08-27T09:14:02Z",
                        "produces": [],
                    }
                },
                "brief.toml",
            )

    def test_an_empty_produces_on_a_kind_that_carries_one_is_read(self) -> None:
        assert self.read({"produces": []})[0].produces == ()


class TestWhichNodeProducesTheScoredAnswer:
    """`P3-46`. The walk `_absence_waived` reads, over shapes the fixtures do not hold."""

    def test_it_descends_into_a_pipeline_used_as_a_node(self) -> None:
        """What produces a nested pipeline's output is a node inside it."""
        inner = Pipeline(
            [
                LLMNode(_a_prompt, output_schema=_Out, node_id="look"),
                LLMNode(_a_prompt, output_schema=_Out, node_id="settle"),
            ],
            budget=_a_budget(),
            node_id="inner",
        )
        outer = Pipeline(
            [Deterministic(lambda i, c: i, node_id="prepare"), inner], budget=_a_budget()
        )
        nodes, _, _, containers = _node_entries(outer)

        answering = _answering_nodes({"nodes": nodes, "containers": containers})

        assert [n["node_id"] for n in answering] == ["inner.settle"]

    def test_a_pipeline_used_as_a_node_in_the_middle_is_not_the_answer(self) -> None:
        inner = Pipeline(
            [LLMNode(_a_prompt, output_schema=_Out, node_id="look")],
            budget=_a_budget(),
            node_id="inner",
        )
        outer = Pipeline(
            [inner, LLMNode(_a_prompt, output_schema=_Out, node_id="after")],
            budget=_a_budget(),
        )
        nodes, _, _, containers = _node_entries(outer)

        answering = _answering_nodes({"nodes": nodes, "containers": containers})

        assert [n["node_id"] for n in answering] == ["after"]

    def test_a_results_file_recording_no_graph_names_nothing(self) -> None:
        assert _answering_nodes({}) == []

    def test_entries_with_no_successors_all_count(self) -> None:
        """A file written before `successors` existed reads as every node being terminal.

        The conservative direction: more nodes have to declare, rather than fewer.
        """
        config = {
            "nodes": [
                {"node_id": "one", "node_kind": "llm", "allow_unknown": False},
                {"node_id": "two", "node_kind": "llm", "allow_unknown": False},
            ]
        }

        assert [n["node_id"] for n in _answering_nodes(config)] == ["one", "two"]
        assert _absence_waived({"config": config})

    def test_a_pipeline_that_loops_falls_back_to_its_last_unit(self) -> None:
        config = {
            "nodes": [
                {"node_id": "a", "node_kind": "llm", "successors": ["b"]},
                {"node_id": "b", "node_kind": "llm", "successors": ["a"]},
            ]
        }

        assert [n["node_id"] for n in _answering_nodes(config)] == ["b"]

    def test_an_answer_no_model_produced_waives_nothing(self) -> None:
        """Nothing declared absence impossible, so the gate is not turned off."""
        config = {
            "nodes": [
                {"node_id": "a", "node_kind": "deterministic", "successors": ["b"]},
                {"node_id": "b", "node_kind": "deterministic", "successors": []},
            ]
        }

        assert _answering_nodes(config) == []
        assert not _absence_waived({"config": config})
        assert "calls no model in this pipeline" in _where_absence_is_declared(config)


class TestWhenAnAnswerWasWrittenDown:
    """`P3-47`. The brief carried `asked_at` and `stage`, both holding a stage name.

    Nothing said when, so "has something changed since this was decided" had nothing to anchor
    against.
    """

    def _brief(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "brief.toml"
        path.write_text(f'tier = "prototype"\n\n{body}', encoding="utf-8")
        return path

    def test_an_answered_entry_carries_it(self, tmp_path) -> None:
        path = self._brief(
            tmp_path,
            f'[entries.what_it_does]\nstatus = "answered"\nrecorded_at = "{STAMP}"\n'
            'answer = "it reads the export"\n',
        )

        assert Brief.read(path).entry("what_it_does").recorded_at == STAMP

    def test_an_answered_entry_without_one_is_refused_by_name(self, tmp_path) -> None:
        path = self._brief(
            tmp_path,
            '[entries.what_it_does]\nstatus = "answered"\nanswer = "it reads the export"\n',
        )

        with pytest.raises(ConfigurationError) as raised:
            Brief.read(path)

        assert "records no recorded_at" in str(raised.value)
        assert "[entries.what_it_does]" in str(raised.value)

    def test_a_deferred_entry_needs_none(self, tmp_path) -> None:
        """Nothing was answered, so there is nothing to date."""
        path = self._brief(
            tmp_path,
            '[entries.what_it_does]\nstatus = "deferred"\ndeferred_to = "ship"\n',
        )

        assert Brief.read(path).entry("what_it_does").recorded_at is None

    def test_a_value_that_is_not_a_timestamp_is_refused(self, tmp_path) -> None:
        path = self._brief(
            tmp_path,
            '[entries.what_it_does]\nstatus = "answered"\nrecorded_at = "build"\n'
            'answer = "it reads the export"\n',
        )

        with pytest.raises(ConfigurationError) as raised:
            Brief.read(path)

        assert "is not a timestamp" in str(raised.value)

    def test_a_timestamp_with_no_zone_is_refused(self, tmp_path) -> None:
        """Two written on different machines cannot be put in order otherwise."""
        path = self._brief(
            tmp_path,
            '[entries.what_it_does]\nstatus = "answered"\n'
            'recorded_at = "2026-08-27T09:14:02"\nanswer = "it reads the export"\n',
        )

        with pytest.raises(ConfigurationError) as raised:
            Brief.read(path)

        assert "names no time zone" in str(raised.value)

    def test_an_offset_other_than_utc_is_accepted(self, tmp_path) -> None:
        """The coding agent reads its own clock, and what is checked is that it is a time."""
        path = self._brief(
            tmp_path,
            '[entries.what_it_does]\nstatus = "answered"\n'
            'recorded_at = "2026-08-27T11:14:02+02:00"\nanswer = "it reads the export"\n',
        )

        assert Brief.read(path).entry("what_it_does").recorded_at.endswith("+02:00")

    def test_every_decision_carries_it(self, tmp_path) -> None:
        path = self._brief(
            tmp_path,
            f'[decisions.d]\nkind = "shape"\nstatus = "agreed"\nrecorded_at = "{STAMP}"\n',
        )

        assert Brief.read(path).decisions[0].recorded_at == STAMP

    def test_a_decision_without_one_is_refused_by_name(self, tmp_path) -> None:
        """Every status, including one not yet put to the builder."""
        path = self._brief(tmp_path, '[decisions.d]\nkind = "shape"\nstatus = "proposed"\n')

        with pytest.raises(ConfigurationError) as raised:
            Brief.read(path)

        assert "records no recorded_at" in str(raised.value)
        assert "[decisions.d]" in str(raised.value)


def _newest_run(root: Path) -> Path:
    """The run directory the checks read, which is the newest one holding a manifest."""
    return max((root / "runs").glob("**/manifest.json"), key=lambda p: p.stat().st_mtime).parent


def _add_a_slice_run(root: Path, *, of: str) -> None:
    """A run beside the project's own, made by a slice of the pipeline ``of`` names.

    Written rather than run: what the note reads is the manifest's `slice` block, and building
    a real rung here would need the fixture's cassette to answer a different set of calls.
    """
    source = _newest_run(root)
    target = root / "runs" / "agent" / "2026-08-28" / "run_a_rung"
    shutil.copytree(source, target)
    manifest = json.loads((target / "manifest.json").read_text())
    manifest["run_id"] = "run_a_rung"
    manifest["slice"] = {
        "of": of,
        "nodes": ["verify"],
        "start": "verify",
        "end": None,
        "dropped": ["hunt"],
        "cut_edges": [{"from": "hunt", "to": "verify", "kind": "successor"}],
    }
    (target / "manifest.json").write_text(json.dumps(manifest))


class TestEveryFigureEndToEnd:
    """FT-08's note: a project that reports a number and nothing about where it came from.

    The entry has no check, and it never could have failed on this. The library computes the
    per-node section out of the trajectories with no project effort, so a project that
    localised nothing still has one, and the shipped text rules out a failure. This is the
    note that says so, and it reports and never fails.
    """

    def _note(self, name: str) -> str | None:
        report = run_checks(project(name))
        found = [note for note in report.notes if "end to end" in note]
        return found[0] if found else None

    def test_it_fires_where_no_step_carries_a_figure(self) -> None:
        note = self._note("end-to-end-only")

        assert note is not None
        assert "expected_by_node" in note and "node_metrics" in note
        assert "pipeline.slice(start=...)" in note

    def test_it_never_fails_the_project(self) -> None:
        report = run_checks(project("end-to-end-only"))

        assert report.ok
        assert not any(f.entry_id == "FT-08" for c in report.checks for f in c.findings)

    def test_a_labelled_step_clears_it(self) -> None:
        """The conforming project labels `hunt`, so a number that drops names a step."""
        assert self._note("conforming") is None

    def test_a_declared_per_node_figure_clears_it(self, tmp_path: Path) -> None:
        root = copied("end-to-end-only", tmp_path)
        path = root / "evals/results/held-out.json"
        results = json.loads(path.read_text())
        results["config"]["node_metrics"] = {
            "hunt": [{"name": "span_f1", "definition": "d", "kind": "mean"}]
        }
        path.write_text(json.dumps(results))

        report = run_checks(root)

        assert not any("end to end" in note for note in report.notes)

    def test_a_slice_run_of_this_pipeline_clears_it(self, tmp_path: Path) -> None:
        """A run made by `Pipeline.slice` of the pipeline the project has now."""
        root = copied("end-to-end-only", tmp_path)
        manifest = json.loads((_newest_run(root) / "manifest.json").read_text())
        _add_a_slice_run(root, of=manifest["graph_fingerprint"])

        report = run_checks(root)

        assert not any("end to end" in note for note in report.notes)

    def test_a_slice_of_a_pipeline_that_has_since_moved_does_not(self, tmp_path: Path) -> None:
        """The rung was taken of a graph the project no longer has, so it localises nothing now.

        This is what stops one slice run silencing the note for ever, and it is the comparison
        FT-37 already makes about the results file.
        """
        root = copied("end-to-end-only", tmp_path)
        _add_a_slice_run(root, of="sha256:a-graph-this-project-no-longer-has")

        report = run_checks(root)

        assert any("end to end" in note for note in report.notes)


class TestTheDesignAgainstTheDeclaredProduct:
    """FT-34 reads the surfaces a `Product` declares against `design.md`'s product section.

    `P3-56`. The section lists what the end user can do and classifies each interaction; a
    surface the code declares and the section never names is an interaction the builder was
    not shown, which is this entry's subject. A project declaring no product is untouched.
    """

    def sections(self, product: str) -> str:
        return (
            "# The design\n\n"
            "## What it does, step by step\n\nOne step, then another.\n\n"
            "## What it holds on to between runs\n\nThe catalogue.\n\n"
            f"## The product\n\n{product}\n\n"
            '## What the builder said about it\n\n> "That is what I asked for."\n'
        )

    def project(self, tmp_path, product: str, surfaces: str) -> Path:
        root = tmp_path / "project"
        root.mkdir()
        (root / "agent.py").write_text(
            "from simple_agents import (Budget, Deterministic, Pipeline, Product, Surface,\n"
            "                           pipeline_factory, product_factory)\n"
            "\n"
            "@pipeline_factory('one')\n"
            "def build():\n"
            "    return Pipeline([Deterministic(lambda i, c: i, node_id='gather')],\n"
            "                    budget=Budget(max_steps=2, max_tokens=None, max_cost=None,\n"
            "                                  max_wall_clock_ms=1000))\n"
            "\n"
            "@product_factory\n"
            "def product():\n"
            f"    return Product(surfaces=[{surfaces}])\n",
            encoding="utf-8",
        )
        (root / "design.md").write_text(self.sections(product), encoding="utf-8")
        (root / "brief.toml").write_text(
            'tier = "prototype"\nstage = "shape"\ndesign_confirmed_at = "shape"\n',
            encoding="utf-8",
        )
        return root

    def reason(self, root: Path) -> str:
        from simple_agents.conformance import run_checks

        held = next(c for c in run_checks(root).checks if c.entry_id == "FT-34")
        return " ".join(f.message for f in held.findings)

    def test_a_surface_the_product_section_never_names_fails(self, tmp_path) -> None:
        root = self.project(
            tmp_path,
            "**The inbox** is where a ticket arrives.",
            "Surface('the inbox', 'starts_a_run', pipeline='one'), "
            "Surface('the outbox', 'reads_the_artifact', reads='outbox')",
        )
        assert "classifies no interaction at 'the outbox'" in self.reason(root)

    def test_a_section_naming_every_surface_passes(self, tmp_path) -> None:
        root = self.project(
            tmp_path,
            "**The inbox** is where a ticket arrives, and the reply lands in **the outbox**.",
            "Surface('the inbox', 'starts_a_run', pipeline='one'), "
            "Surface('the outbox', 'reads_the_artifact', reads='outbox')",
        )
        assert self.reason(root) == ""

    def test_a_project_declaring_no_product_is_untouched(self, tmp_path) -> None:
        """Nothing here reaches a project that has not adopted the declaration."""
        root = self.project(tmp_path, "A script the builder runs.", "")
        (root / "agent.py").write_text(
            (root / "agent.py").read_text(encoding="utf-8").replace("@product_factory", "#"),
            encoding="utf-8",
        )
        assert self.reason(root) == ""
