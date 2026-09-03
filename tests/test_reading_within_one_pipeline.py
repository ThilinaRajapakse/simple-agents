"""What the checks read on a project that runs more than one pipeline.

Before the manifest carried a pipeline name, every check that reads one run read the newest run
of any of them. On a project whose scheduler ran a background pass every morning, that run was
whichever pass ran last: FT-25, FT-37 and FT-38 fired on most mornings, and the standing
workaround was a paid run of the measured pipeline before every gate. The quieter half is
FT-14, which passed on that pass because a background pipeline calls no model.

The fixtures here are the `conforming` project with runs added: one pipeline the evaluation
measured, and one background pass that ran after it.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from simple_agents.conformance import run_checks
from simple_agents.conformance.report import Outcome

PROJECTS = Path(__file__).parent / "fixtures" / "projects"

MEASURED = "answer"
"""The name the fixture's registered factory gives the pipeline the evaluation measured."""


def _fixture(tmp_path: Path) -> Path:
    source = PROJECTS / "conforming"
    if not source.exists():
        pytest.skip("no conforming fixture; run scripts/build_conformance_fixtures.py")
    target = tmp_path / "project"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def _a_rollout(root: Path) -> Path:
    return sorted((root / "runs").rglob("manifest.json"))[0].parent


def _added_run(root: Path, run_id: str, **fields) -> Path:
    """One more run under `runs/`, copied off a rollout and given the fields the test needs."""
    where = root / "runs" / "dev" / "2026-09-04" / run_id
    where.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_a_rollout(root), where)
    manifest = json.loads((where / "manifest.json").read_text())
    manifest.update({"run_id": run_id, "evaluation": None, **fields})
    (where / "manifest.json").write_text(json.dumps(manifest))
    return where


def _at_ship(root: Path) -> Path:
    """The fixture at stage `ship`, which is where FT-37 and FT-38 fail rather than report."""
    live = root / "runs" / "live" / "2026-09-03" / "run_live"
    live.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_a_rollout(root), live)
    manifest = json.loads((live / "manifest.json").read_text())
    manifest.update(
        {
            "run_id": "run_live",
            "evaluation": None,
            "live": True,
            "started_at": "2026-09-03T16:00:00.000Z",
        }
    )
    (live / "manifest.json").write_text(json.dumps(manifest))
    return root


def _background_pass(root: Path) -> Path:
    """A run of another pipeline, newer than every run of the measured one."""
    return _added_run(
        root,
        "run_freshen",
        pipeline="freshen",
        started_at="2026-09-04T06:00:00.000Z",
        behaviour_fingerprint="sha256:aaaaaaaaaaaaaaaa",
        nodes=[{"node_id": "refresh", "node_kind": "deterministic"}],
        tools=[],
    )


def _held(root: Path, entry_id: str):
    return [c for c in run_checks(root).checks if c.entry_id == entry_id][0]


class TestABackgroundPassIsNotTheMeasuredPipeline:
    """FT-25, FT-37 and FT-38 read the pipeline the results file names."""

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        root = _at_ship(_fixture(tmp_path))
        _background_pass(root)
        return root

    def test_the_reported_number_is_read_against_its_own_pipeline(self, project: Path) -> None:
        assert _held(project, "FT-37").outcome is Outcome.PASSED

    def test_the_brief_is_read_against_its_own_pipeline(self, project: Path) -> None:
        assert _held(project, "FT-38").outcome is Outcome.PASSED

    def test_a_consultation_tool_on_any_pipeline_answers_the_brief(self, tmp_path: Path) -> None:
        """The question is whether the project built a way to ask, not whether one pipeline did."""
        root = _fixture(tmp_path)
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text().replace(
                'answer = "Nothing. Every input the agent needs is in the collection."',
                'answer = "The reader is asked which passage answers, where two disagree."',
            )
        )
        for manifest_path in (root / "runs").rglob("manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            manifest["tools"] = [
                *manifest["tools"],
                {"name": "ask_the_reader", "answered_by": "end_user", "offered": True},
            ]
            manifest_path.write_text(json.dumps(manifest))
        _background_pass(root)

        held = _held(root, "FT-25")
        assert held.outcome is Outcome.PASSED
        assert "ask_the_reader" in (held.detail or "")

    def test_no_pipeline_offering_one_still_fails(self, tmp_path: Path) -> None:
        root = _fixture(tmp_path)
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text().replace(
                'answer = "Nothing. Every input the agent needs is in the collection."',
                'answer = "The reader is asked which passage answers, where two disagree."',
            )
        )
        _background_pass(root)

        held = _held(root, "FT-25")
        assert held.outcome is Outcome.FAILED
        assert "2 pipeline(s)" in held.findings[0].message


class TestEveryCheckThatReadsOneRun:
    """The run itself, not only the three that compare a stamp.

    Measured on a live two-pipeline project: the background pass calls no model, so FT-14
    reported that the run names no model to pin, and a project whose measured pipeline floats
    its model passed.
    """

    def _floating(self, tmp_path: Path) -> Path:
        """The measured pipeline on an alias that moves, and a background pass after it."""
        root = _fixture(tmp_path)
        for manifest_path in (root / "runs").rglob("manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("pipeline") != MEASURED:
                continue
            manifest["models"]["configured"]["request_model"] = "mistral-small-latest"
            for one in manifest["models"]["observed"]:
                one["request_model"] = "mistral-small-latest"
            for node in manifest["nodes"]:
                if isinstance(node.get("model"), dict):
                    node["model"]["request_model"] = "mistral-small-latest"
            manifest_path.write_text(json.dumps(manifest))
        _background_pass(root)
        return root

    def test_a_floating_model_on_the_measured_pipeline_is_reported(self, tmp_path: Path) -> None:
        assert _held(self._floating(tmp_path), "FT-14").outcome is Outcome.FAILED

    def test_the_run_read_is_the_measured_pipelines(self, tmp_path: Path) -> None:
        root = _fixture(tmp_path)
        _background_pass(root)
        report = run_checks(root)

        assert f"the newest run of {MEASURED!r}" in (report.reading or "")
        assert "run_freshen" not in (report.reading or "")

    def test_a_run_named_explicitly_wins(self, tmp_path: Path) -> None:
        root = _fixture(tmp_path)
        where = _background_pass(root)
        report = run_checks(root, run_dir=where)

        assert "run_freshen" in (report.reading or "")

    def test_a_project_whose_runs_predate_the_field_reads_the_newest(self, tmp_path: Path) -> None:
        root = _fixture(tmp_path)
        where = _background_pass(root)
        for manifest_path in (root / "runs").rglob("manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            manifest.pop("pipeline", None)
            manifest_path.write_text(json.dumps(manifest))

        assert "run_freshen" in (run_checks(root).reading or ""), where.name


class TestWhenNoRunAnswersForThePipeline:
    """Blocked with a reason, rather than compared against another pipeline's stamp."""

    def test_a_pipeline_nothing_has_run_is_blocked(self, tmp_path: Path) -> None:
        root = _at_ship(_fixture(tmp_path))
        _background_pass(root)
        results = root / "evals" / "results" / "held-out.json"
        held = json.loads(results.read_text())
        held["config"]["pipeline"] = "recommend"
        results.write_text(json.dumps(held))

        for entry_id in ("FT-37", "FT-38"):
            found = _held(root, entry_id)
            assert found.outcome is Outcome.BLOCKED, entry_id
            assert "has run the pipeline 'recommend'" in found.detail
            assert MEASURED in found.detail, "the report names the pipelines the runs do record"

    def test_a_failure_says_the_read_was_widened(self, tmp_path: Path) -> None:
        """The note matters most on a failure: the stamp named is whichever pipeline ran last."""
        root = _at_ship(_fixture(tmp_path))
        _background_pass(root)
        for manifest_path in (root / "runs").rglob("manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            manifest.pop("pipeline", None)
            manifest_path.write_text(json.dumps(manifest))
        brief = root / "brief.toml"
        brief.write_text(
            re.sub(
                r"^confirmed_against = .*$",
                'confirmed_against = "sha256:stale"',
                brief.read_text(),
                flags=re.M,
            )
        )
        held = _held(root, "FT-38")

        assert held.outcome is Outcome.FAILED
        assert "records which pipeline it is" in (held.detail or "")

    def test_a_project_whose_runs_predate_the_field_reads_as_it_did(self, tmp_path: Path) -> None:
        root = _at_ship(_fixture(tmp_path))
        for manifest_path in (root / "runs").rglob("manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            manifest.pop("pipeline", None)
            manifest_path.write_text(json.dumps(manifest))

        held = _held(root, "FT-38")
        assert held.outcome is Outcome.PASSED
        assert "records which pipeline it is" in (held.detail or "")


class TestTheWriterAndTheCheckReadOneRun:
    """`record read-against` writes what FT-38 compares to, or running it clears nothing.

    Found on a live two-pipeline project: the command wrote the background pass's stamp, FT-38
    wanted the measured pipeline's, and the documented way to clear the check left it failing.
    """

    def test_the_stamp_it_writes_clears_the_check(self, tmp_path: Path) -> None:
        from simple_agents.cli.main import main

        root = _at_ship(_fixture(tmp_path))
        _background_pass(root)
        brief = root / "brief.toml"
        brief.write_text(
            re.sub(
                r"^confirmed_against = .*$",
                'confirmed_against = "sha256:stale"',
                brief.read_text(),
                flags=re.M,
            )
        )
        assert _held(root, "FT-38").outcome is Outcome.FAILED, "the brief is stale to begin with"

        assert main(["record", "read-against", "--brief", str(brief)]) == 0

        assert _held(root, "FT-38").outcome is Outcome.PASSED

    def test_it_reads_the_measured_pipeline_rather_than_whichever_ran_last(
        self, tmp_path: Path
    ) -> None:
        from simple_agents.conformance import newest_run_fingerprints

        root = _at_ship(_fixture(tmp_path))
        _background_pass(root)
        stamp, _shape, where = newest_run_fingerprints(root)

        held = json.loads((where / "manifest.json").read_text())
        assert held["pipeline"] == MEASURED
        assert stamp != "sha256:aaaaaaaaaaaaaaaa", "the background pass's stamp"


class TestAnEvaluationOverARung:
    """FT-37 compares like for like; FT-38 reads the whole pipeline the brief describes."""

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        root = _at_ship(_fixture(tmp_path))
        results = root / "evals" / "results" / "held-out.json"
        held = json.loads(results.read_text())
        held["config"]["pipeline"] = MEASURED
        held["config"]["slice"] = {"of": "sha256:whole", "nodes": ["verify"], "dropped": ["hunt"]}
        held["config"]["behaviour_fingerprint"] = "sha256:cccccccccccccccc"
        results.write_text(json.dumps(held))
        _added_run(
            root,
            "run_rung",
            pipeline=MEASURED,
            started_at="2026-09-04T09:00:00.000Z",
            behaviour_fingerprint="sha256:cccccccccccccccc",
            slice={"of": "sha256:whole", "nodes": ["verify"], "dropped": ["hunt"]},
        )
        return root

    def test_the_rungs_number_is_read_against_the_rung(self, project: Path) -> None:
        """Matching on the name alone would find the whole pipeline and report a false failure."""
        assert _held(project, "FT-37").outcome is Outcome.PASSED

    def test_the_brief_is_read_against_the_whole_pipeline(self, project: Path) -> None:
        """The brief's entries describe the agent, and a rung is one step of it."""
        held = _held(project, "FT-38")

        assert held.outcome is Outcome.PASSED
        assert "sha256:cccccccccccccccc" not in (held.detail or "")

    def test_a_project_that_has_only_run_rungs_says_so(self, tmp_path: Path) -> None:
        root = _at_ship(_fixture(tmp_path))
        rung = {"of": "sha256:whole", "nodes": ["verify"], "dropped": ["hunt"]}
        for manifest_path in (root / "runs").rglob("manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            manifest["slice"] = rung
            manifest_path.write_text(json.dumps(manifest))
        results = root / "evals" / "results" / "held-out.json"
        held = json.loads(results.read_text())
        held["config"]["slice"] = rung
        results.write_text(json.dumps(held))

        found = _held(root, "FT-38")
        assert found.outcome is Outcome.PASSED
        assert "is of a slice of it" in (found.detail or "")


class TestTheNotesUnderTheChecksStayTrue:
    """Two notes whose truth rested on the run being the newest of any pipeline."""

    def _all_live(self, tmp_path: Path) -> Path:
        """The measured pipeline with nothing but live runs, and another pipeline newer."""
        root = _fixture(tmp_path)
        for manifest_path in (root / "runs").rglob("manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            manifest["live"] = True
            manifest_path.write_text(json.dumps(manifest))
        _added_run(
            root,
            "run_freshen_live",
            pipeline="freshen",
            live=True,
            started_at="2026-09-06T06:00:00.000Z",
        )
        return root

    def test_it_does_not_claim_every_run_is_live(self, tmp_path: Path) -> None:
        root = _fixture(tmp_path)
        for manifest_path in (root / "runs").rglob("manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            manifest["live"] = True
            manifest_path.write_text(json.dumps(manifest))
        # Copied off a run this test has already marked live, so it says what it is.
        _added_run(
            root,
            "run_freshen",
            pipeline="freshen",
            live=False,
            started_at="2026-09-04T06:00:00.000Z",
        )

        said = " ".join(run_checks(root).notes)
        assert f"Every run of {MEASURED!r} the checks could read is marked live" in said
        assert "Every run under runs/ is marked live" not in said

    def test_it_does_not_call_a_live_run_one_made_while_building(self, tmp_path: Path) -> None:
        said = " ".join(run_checks(self._all_live(tmp_path)).notes)

        assert "which is another run an end user made" in said
        assert "which is a run made while building" not in said


class TestOneRuleForWhichRunSpeaksForAPipeline:
    """The run the checks read and the run a stamp is compared against are the same run."""

    def test_they_agree_on_a_project_that_has_only_run_rungs(self, tmp_path: Path) -> None:
        from simple_agents.conformance import newest_run_fingerprints

        root = _at_ship(_fixture(tmp_path))
        rung = {"of": "sha256:whole", "nodes": ["verify"], "dropped": ["hunt"]}
        for manifest_path in (root / "runs").rglob("manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            manifest["slice"] = rung
            manifest_path.write_text(json.dumps(manifest))
        _background_pass(root)

        read = run_checks(root)
        _stamp, _shape, compared = newest_run_fingerprints(root)

        assert compared.name in " ".join(_held(root, "FT-13").read)
        assert "run_freshen" not in (read.reading or "")


class TestASliceRecordNothingCanRead:
    """A record naming no nodes is read as a whole pipeline, on both sides of the match."""

    def test_a_run_and_a_results_file_that_both_hold_one_still_match(self, tmp_path: Path) -> None:
        root = _at_ship(_fixture(tmp_path))
        for manifest_path in (root / "runs").rglob("manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            manifest["slice"] = {"of": "sha256:whole", "nodes": []}
            manifest_path.write_text(json.dumps(manifest))
        results = root / "evals" / "results" / "held-out.json"
        held = json.loads(results.read_text())
        held["config"]["slice"] = {"of": "sha256:whole", "nodes": []}
        results.write_text(json.dumps(held))

        found = _held(root, "FT-38")
        assert found.outcome is Outcome.PASSED
        assert "is of a slice of it" not in (found.detail or "")


class TestTheEvaluatedPipelineIsOneTheProjectDeclares:
    """FT-45, read off the results file alone."""

    def test_a_registered_pipeline_passes(self, tmp_path: Path) -> None:
        held = _held(_fixture(tmp_path), "FT-45")

        assert held.outcome is Outcome.PASSED
        assert f"Measured over {MEASURED!r}" in held.detail

    def test_a_rung_of_one_passes_and_says_how_many_nodes(self, tmp_path: Path) -> None:
        root = _fixture(tmp_path)
        results = root / "evals" / "results" / "held-out.json"
        held = json.loads(results.read_text())
        held["config"]["slice"] = {"of": "sha256:whole", "nodes": ["verify"], "dropped": ["hunt"]}
        results.write_text(json.dumps(held))

        found = _held(root, "FT-45")
        assert found.outcome is Outcome.PASSED
        assert "1 node(s) of it this evaluation sliced" in found.detail

    def test_a_pipeline_registered_nowhere_fails(self, tmp_path: Path) -> None:
        """One project measured a graph built inside its evaluation script and reported it."""
        root = _fixture(tmp_path)
        results = root / "evals" / "results" / "held-out.json"
        held = json.loads(results.read_text())
        held["config"]["pipeline"] = None
        results.write_text(json.dumps(held))

        found = _held(root, "FT-45")
        assert found.outcome is Outcome.FAILED
        assert "@pipeline_factory" in found.findings[0].message

    def test_a_results_file_written_before_the_field_is_blocked(self, tmp_path: Path) -> None:
        root = _fixture(tmp_path)
        results = root / "evals" / "results" / "held-out.json"
        held = json.loads(results.read_text())
        del held["config"]["pipeline"]
        results.write_text(json.dumps(held))

        found = _held(root, "FT-45")
        assert found.outcome is Outcome.BLOCKED
        assert "format 0.31" in found.detail

    def test_a_project_with_no_results_file_is_blocked(self, tmp_path: Path) -> None:
        root = _fixture(tmp_path)
        shutil.rmtree(root / "evals" / "results")

        assert _held(root, "FT-45").outcome is Outcome.BLOCKED
