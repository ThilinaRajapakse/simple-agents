"""The registered name on a run, and what reads within one pipeline.

Six dogfood findings sit behind this. A project with six pipelines ran a background pass every
morning, and three checks read the newest run of any of them, so all three fired on every
morning; an evaluation over a pipeline assembled inside the evaluation script passed every
gate; a decision about the corpus named the nodes of a `role="corpus"` pipeline and was
reported as naming ten things the project never built; and a scripted client's runs were
counted as spend.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Budget,
    Deterministic,
    FakeModelClient,
    Pipeline,
    RunEnvelope,
    pipeline_factory,
    runs,
)
from simple_agents.registry import clear_registered_pipelines, registered_pipelines


def _step(inputs, ctx):
    return inputs


def _built(node_id: str = "step") -> Pipeline:
    return Pipeline([Deterministic(_step, node_id=node_id)], budget=Budget.unbounded())


@pytest.fixture(autouse=True)
def _empty_registry():
    clear_registered_pipelines()
    yield
    clear_registered_pipelines()


class TestTheNameOnThePipeline:
    """`@pipeline_factory` names what it builds, which is where every record gets the name."""

    def test_a_registered_factory_names_what_it_returns(self) -> None:
        @pipeline_factory("recommend")
        def recommend() -> Pipeline:
            return _built()

        assert recommend().name == "recommend"

    def test_the_project_calls_the_function_exactly_as_before(self) -> None:
        @pipeline_factory("recommend")
        def recommend() -> Pipeline:
            """What the builder wrote."""
            return _built()

        assert recommend.__name__ == "recommend"
        assert recommend.__doc__ == "What the builder wrote."
        assert isinstance(recommend(), Pipeline)

    def test_a_pipeline_built_outside_a_factory_is_unnamed(self) -> None:
        assert _built().name is None

    def test_one_decorator_applied_twice_registers_one_pipeline(self) -> None:
        """A module imported under two names decorates one function twice."""

        def recommend() -> Pipeline:
            return _built()

        first = pipeline_factory("recommend")(recommend)
        second = pipeline_factory("recommend")(recommend)

        assert list(registered_pipelines()) == ["recommend"]
        assert first().name == second().name == "recommend"

    def test_two_factories_under_one_name_are_still_refused(self) -> None:
        from simple_agents.errors import ConfigurationError

        @pipeline_factory("recommend")
        def recommend() -> Pipeline:
            return _built()

        with pytest.raises(ConfigurationError, match="already registered"):

            @pipeline_factory("recommend")
            def other() -> Pipeline:
                return _built()

    def test_a_factory_returning_something_else_is_handed_back_untouched(self) -> None:
        @pipeline_factory("not_a_pipeline")
        def broken() -> str:
            return "nothing"

        assert broken() == "nothing"

    def test_a_slice_keeps_the_name_of_the_pipeline_it_came_from(self) -> None:
        @pipeline_factory("recommend")
        def recommend() -> Pipeline:
            return Pipeline(
                [Deterministic(_step, node_id="a"), Deterministic(_step, node_id="b")],
                budget=Budget.unbounded(),
            )

        rung = recommend().slice(start="b")

        assert rung.name == "recommend"
        assert rung.slice_of.nodes == ("b",)


class TestWhereElseAPipelineIsBuilt:
    """Every path that derives a pipeline from another one keeps its name."""

    def test_a_variant_arm_says_which_pipeline_it_is_an_arm_of(self) -> None:
        """The arms declare `role="variant"`, which is what keeps them out of the checks."""
        from simple_agents.evaluation.variants import _same_but

        @pipeline_factory("recommend")
        def recommend() -> Pipeline:
            return Pipeline(
                [Deterministic(_step, node_id="a"), Deterministic(_step, node_id="b")],
                budget=Budget.unbounded(),
            )

        built = recommend()
        arm = _same_but(built, built.nodes[:1])

        assert arm.name == "recommend"

    def test_an_unregistered_pipeline_gives_an_unnamed_arm(self) -> None:
        from simple_agents.evaluation.variants import _same_but

        built = _built()
        assert _same_but(built, built.nodes).name is None


class TestWhatARunRecords:
    """The manifest carries the name, and `runs()` reads within it."""

    def _ran(self, tmp_path: Path, name: str | None, node_id: str = "step") -> Path:
        built = _built(node_id)
        if name is not None:
            built.name = name
        return Path(built.run({}, envelope=RunEnvelope(run_dir=tmp_path)).manifest_path)

    def test_the_manifest_records_which_pipeline_the_run_is(self, tmp_path: Path) -> None:
        where = self._ran(tmp_path, "recommend")
        manifest = json.loads(where.read_text())

        assert manifest["pipeline"] == "recommend"

    def test_a_pipeline_no_factory_registered_records_null(self, tmp_path: Path) -> None:
        where = self._ran(tmp_path, None)
        manifest = json.loads(where.read_text())

        assert manifest["pipeline"] is None

    def test_runs_reads_one_pipeline(self, tmp_path: Path) -> None:
        self._ran(tmp_path, "recommend")
        self._ran(tmp_path, "freshen", node_id="refresh")

        assert [run.pipeline for run in runs(tmp_path, pipeline="freshen")] == ["freshen"]
        assert {run.pipeline for run in runs(tmp_path)} == {"recommend", "freshen"}

    def test_a_run_written_before_the_field_existed_reads_as_none(self, tmp_path: Path) -> None:
        where = self._ran(tmp_path, "recommend")
        manifest = json.loads(where.read_text())
        del manifest["pipeline"]
        where.write_text(json.dumps(manifest))

        (found,) = runs(tmp_path)
        assert found.pipeline is None


class TestAScriptedRun:
    """A run whose model answered from a list, and what leaves it out."""

    def _ran(self, tmp_path: Path, client) -> Path:
        from schemas import Answer

        from simple_agents import LLMNode

        pipeline = Pipeline(
            [LLMNode(lambda inputs, ctx: "q", output_schema=Answer, node_id="ask")],
            budget=Budget(max_steps=2, max_tokens=1000, max_cost=None, max_wall_clock_ms=10_000),
        )
        return Path(
            pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client).manifest_path
        )

    def _scripted(self, count: int = 1, **kwargs):
        from simple_agents.models import fake_response

        return FakeModelClient(
            responses=[fake_response(content='{"answer": "ok"}') for _ in range(count)], **kwargs
        )

    def test_the_manifest_says_the_model_answered_from_a_script(self, tmp_path: Path) -> None:
        where = self._ran(tmp_path, self._scripted())
        manifest = json.loads(where.read_text())

        assert manifest["scripted"] is True

    def test_a_stand_in_for_a_backend_says_it_is_not(self, tmp_path: Path) -> None:
        where = self._ran(tmp_path, self._scripted(scripted=False))
        manifest = json.loads(where.read_text())

        assert manifest["scripted"] is False

    def test_a_pipeline_that_calls_no_model_is_not_scripted(self, tmp_path: Path) -> None:
        where = Path(_built().run({}, envelope=RunEnvelope(run_dir=tmp_path)).manifest_path)
        manifest = json.loads(where.read_text())

        assert manifest["scripted"] is False

    def test_a_wrapper_in_front_of_it_is_read_through(self, tmp_path: Path) -> None:
        from simple_agents import PacedClient

        where = self._ran(tmp_path, PacedClient(self._scripted()))
        manifest = json.loads(where.read_text())

        assert manifest["scripted"] is True

    def test_runs_leaves_it_out_and_says_so_when_asked(self, tmp_path: Path) -> None:
        self._ran(tmp_path, self._scripted())
        self._ran(tmp_path, self._scripted(scripted=False))

        assert [run.scripted for run in runs(tmp_path)] == [False]
        assert len(runs(tmp_path, scripted=None)) == 2
        assert [run.scripted for run in runs(tmp_path, scripted=True)] == [True]

    def test_the_report_counts_what_it_left_out(self, tmp_path: Path) -> None:
        from simple_agents.cli.reporting import report_over_runs

        self._ran(tmp_path, self._scripted())
        self._ran(tmp_path, self._scripted(scripted=False))
        report = report_over_runs(tmp_path)

        assert report.read == 1
        assert report.found == 2
        assert report.scripted_left_out == 1
        assert "1 run(s) whose model answered from a script are left out" in report.text()

    def test_a_project_whose_every_run_is_scripted_is_told_why(self, tmp_path: Path) -> None:
        """It has runs, and a report saying it read none would be describing another directory."""
        from simple_agents.cli.reporting import report_over_runs

        self._ran(tmp_path, self._scripted())
        self._ran(tmp_path, self._scripted())
        printed = report_over_runs(tmp_path).text()

        assert "Every run under this path answered from a script" in printed
        assert "--scripted" in printed

    def test_some_scripted_among_others_is_still_named(self, tmp_path: Path) -> None:
        """A report over no runs names the scripted ones even where they are not all of them."""
        from simple_agents.cli.reporting import report_over_runs

        self._ran(tmp_path, self._scripted())
        self._ran(tmp_path, self._scripted())
        broken = tmp_path / "dev" / "2026-09-05" / "run_broken"
        broken.mkdir(parents=True)
        (broken / "manifest.json").write_text("{ not json")
        printed = report_over_runs(tmp_path).text()

        assert "2 of the 3 run(s) under this path answered from a script" in printed
        assert "`--scripted` reads those" in printed

    def test_the_checks_say_the_same_rather_than_no_run_directory(self, tmp_path: Path) -> None:
        import shutil

        from simple_agents.conformance import run_checks

        root = tmp_path / "project"
        root.mkdir()
        fixture = Path(__file__).parent / "fixtures" / "projects" / "conforming" / "brief.toml"
        if not fixture.exists():
            pytest.skip("no conforming fixture; run scripts/build_conformance_fixtures.py")
        shutil.copy(fixture, root / "brief.toml")
        self._ran(root / "runs", self._scripted())
        held = [c for c in run_checks(root).checks if c.entry_id == "FT-13"][0]

        said = " ".join(f.message for f in held.findings)
        assert "whose model answered from a script" in said
        assert "no run directory under runs/" not in said

    def test_no_check_tells_it_that_it_has_no_runs(self, tmp_path: Path) -> None:
        """Each reader that reports no figure names the reason: the runs were scripted."""
        import shutil

        from simple_agents.conformance import run_checks

        root = tmp_path / "project"
        root.mkdir()
        fixture = Path(__file__).parent / "fixtures" / "projects" / "conforming" / "brief.toml"
        if not fixture.exists():
            pytest.skip("no conforming fixture; run scripts/build_conformance_fixtures.py")
        shutil.copy(fixture, root / "brief.toml")
        for _ in range(3):
            self._ran(root / "runs", self._scripted())
        report = run_checks(root)

        said = {
            check.entry_id: (check.detail or " ".join(f.message for f in check.findings))
            for check in report.checks
        }
        for entry_id in ("FT-13", "FT-35", "FT-43"):
            assert "answered from a script" in said[entry_id], (entry_id, said[entry_id])
        assert "no run under runs/ could be read" not in said["FT-42"]
        assert "None of the 3 run(s)" in said["FT-41"], "FT-41 reads every run whatever made it"

    def test_the_view_counts_it_like_any_other_run(self, tmp_path: Path) -> None:
        """The page is a census of what ran, not a figure about the agent."""
        from simple_agents.view.operating import _by_role

        self._ran(tmp_path / "runs", self._scripted())
        self._ran(tmp_path / "runs", self._scripted(scripted=False))
        counted = {one["role"]: one["runs"] for one in _by_role(tmp_path / "runs")}

        assert sum(counted.values()) == 2, counted

    def test_asking_for_them_reads_both(self, tmp_path: Path) -> None:
        from simple_agents.cli.reporting import report_over_runs

        self._ran(tmp_path, self._scripted())
        self._ran(tmp_path, self._scripted(scripted=False))
        report = report_over_runs(tmp_path, scripted=None)

        assert report.read == 2
        assert report.scripted_left_out == 0
