"""The `constants` the manifest records: which modules are read, and what counts as one.

`tests/fixtures/constants_project/` is the stand-in project. It is laid out the way a project
is, with the node callables in one module and the numbers in another beside it, because the
mechanism is a walk from the first to the second and a fixture in one file would not exercise
it (`docs/run-envelope.md` §2.9).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from simple_agents import Budget, Deterministic, Pipeline
from simple_agents.records.manifest import MANIFEST_FORMAT_VERSION, Manifest, module_constants

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from constants_project.pkg import ranking, steps  # noqa: E402


def _names(found: list[dict[str, object]]) -> set[str]:
    return {str(row["name"]) for row in found}


def _one(found: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(row for row in found if row["name"] == name)


class TestWhichModulesAreRead:
    def test_the_module_a_callable_is_written_in_is_read(self) -> None:
        assert "LIMIT" in _names(module_constants([steps.step]))

    def test_a_project_module_it_imports_is_reached(self) -> None:
        """The way in is the callable; the numbers are usually somewhere else."""
        found = module_constants([steps.step])

        assert _one(found, "WEIGHT")["module"] == "constants_project.pkg.ranking"

    def test_simple_agents_own_numbers_are_not_the_builders(self) -> None:
        """Run from a source checkout the library is not under an installed path either."""
        from simple_agents import pipeline as library_module

        found = module_constants([library_module.Pipeline.run])

        assert not [row for row in found if str(row["module"]).startswith("simple_agents")]

    def test_a_callable_with_no_module_is_skipped(self) -> None:
        assert module_constants([len]) == []

    def test_nothing_in_reaches_nothing_out(self) -> None:
        assert module_constants([]) == []

    def test_a_module_whose_source_cannot_be_read_contributes_nothing(self) -> None:
        """A module built at runtime has no file, so there is no definition site to read."""
        made = types.ModuleType("made_at_runtime")
        made.THRESHOLD = 5
        exec("def fn():\n    return THRESHOLD", vars(made))
        sys.modules["made_at_runtime"] = made
        try:
            assert module_constants([made.fn]) == []
        finally:
            del sys.modules["made_at_runtime"]


class TestWhatCountsAsOne:
    def test_a_numeric_literal_counts(self) -> None:
        assert _one(module_constants([steps.step]), "SHORTLIST")["value"] == 12

    def test_a_negative_literal_counts(self) -> None:
        assert _one(module_constants([steps.step]), "BACKWARDS")["value"] == -3

    def test_a_leading_underscore_does_not(self) -> None:
        assert "_INTERNAL" not in _names(module_constants([steps.step]))

    def test_a_string_does_not(self) -> None:
        assert "NAME" not in _names(module_constants([steps.step]))

    def test_true_is_a_flag_and_not_a_number(self) -> None:
        assert "ENABLED" not in _names(module_constants([steps.step]))

    def test_an_expression_is_not_a_literal(self) -> None:
        """A number the code computes was not written down as a choice."""
        assert "COMPUTED" not in _names(module_constants([steps.step]))

    def test_a_name_is_recorded_where_it_is_written(self) -> None:
        """`steps` imports `SHORTLIST`, and a project would read two entries as two numbers."""
        found = module_constants([steps.step])
        written = [row for row in found if row["name"] == "SHORTLIST"]

        assert len(written) == 1
        assert written[0]["module"] == "constants_project.pkg.ranking"

    def test_the_value_is_what_the_run_started_with(self, monkeypatch) -> None:
        """The name comes from the source and the value from the module as it stands."""
        monkeypatch.setattr(ranking, "SHORTLIST", 40)

        assert _one(module_constants([steps.step]), "SHORTLIST")["value"] == 40

    def test_a_name_rebound_to_something_that_is_not_a_number_drops_out(self, monkeypatch) -> None:
        monkeypatch.setattr(ranking, "SHORTLIST", "all of them")

        assert "SHORTLIST" not in _names(module_constants([steps.step]))


class TestWhatThePipelineRecords:
    def _pipeline(self) -> Pipeline:
        return Pipeline(
            [Deterministic(steps.step, node_id="rank")],
            budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

    def test_the_pipeline_reaches_its_own_node_callables(self) -> None:
        assert _names(self._pipeline().manifest_constants()) == {
            "WEIGHT",
            "SHORTLIST",
            "BACKWARDS",
            "LIMIT",
            "THRESHOLD",
        }

    def test_editing_a_constant_does_not_move_the_behaviour_fingerprint(self, monkeypatch) -> None:
        """A number in a module the pipeline imports is not something the pipeline declares.

        A stamp that moved on one would make a stored result stale that was not.
        """
        before = self._pipeline().behaviour_fingerprint()
        monkeypatch.setattr(ranking, "SHORTLIST", 40)

        assert self._pipeline().behaviour_fingerprint() == before
        assert _one(self._pipeline().manifest_constants(), "SHORTLIST")["value"] == 40

    def test_a_manifest_carries_them_and_reads_them_back(self) -> None:
        manifest = Manifest(
            run_id="run_1",
            started_at="2026-08-27T00:00:00.000Z",
            seed=1,
            budget={},
            library_version="0",
            trajectory_path="t.jsonl",
            workspace_path="w",
            constants=self._pipeline().manifest_constants(),
        )
        written = manifest.to_json()
        back = Manifest.restore(written)

        assert written["format_version"] == MANIFEST_FORMAT_VERSION
        assert _names(written["constants"]) == _names(back.constants)

    def test_a_manifest_written_before_the_field_reads_back_empty(self) -> None:
        """A resumed run continues one manifest, and an older one carries no array."""
        raw = Manifest(
            run_id="run_1",
            started_at="2026-08-27T00:00:00.000Z",
            seed=1,
            budget={},
            library_version="0",
            trajectory_path="t.jsonl",
            workspace_path="w",
        ).to_json()
        raw.pop("constants")

        assert Manifest.restore(raw).constants == []


@pytest.mark.parametrize("kind", ["presentation", "measurement"])
def test_the_two_kinds_that_name_nothing_carry_no_produces(kind: str) -> None:
    from simple_agents.conformance import kind as decision_kind

    assert decision_kind(kind).produces is None


class TestAModuleReachedOnlyByItsData:
    """A module whose only export the caller uses is a value reaches nothing in the namespace.

    `from .settings import LIMITS` binds a dict, which is not a function, a class or a module,
    so a walk over what the namespace holds stops there. The numbers beside `LIMITS` are the
    ones this whole mechanism exists to find, so the imports are read from the source too.
    """

    def test_it_is_reached_through_the_import_and_not_the_namespace(self) -> None:
        assert "THRESHOLD" in _names(module_constants([steps.step]))

    def test_it_is_recorded_under_its_own_module(self) -> None:
        found = _one(module_constants([steps.step]), "THRESHOLD")

        assert found["module"] == "constants_project.pkg.settings"

    def test_walking_the_namespace_alone_would_miss_it(self) -> None:
        """Guards the reason the import walk is there, so removing it fails here."""
        from simple_agents.records.manifest import _neighbours

        reached = {module.__name__ for module in _neighbours(steps)}

        assert "constants_project.pkg.settings" in reached
        assert not [
            value for value in vars(steps).values() if getattr(value, "__name__", "") == "settings"
        ]


class TestTheCacheReadsAnEditedModuleAgain:
    def test_a_module_rewritten_in_place_is_parsed_again(self, tmp_path, monkeypatch) -> None:
        """`view --serve` imports a project repeatedly while the builder edits it."""
        import importlib

        package = tmp_path / "edited_project"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "numbers.py").write_text("FIRST = 1\n\n\ndef fn():\n    return FIRST\n")
        monkeypatch.syspath_prepend(str(tmp_path))
        module = importlib.import_module("edited_project.numbers")
        try:
            assert _names(module_constants([module.fn])) == {"FIRST"}

            (package / "numbers.py").write_text(
                "FIRST = 1\nSECOND = 2\n\n\ndef fn():\n    return FIRST\n"
            )
            importlib.reload(module)

            assert _names(module_constants([module.fn])) == {"FIRST", "SECOND"}
        finally:
            sys.modules.pop("edited_project.numbers", None)
            sys.modules.pop("edited_project", None)


class TestWhatCountsAsInstalled:
    def test_a_path_is_compared_by_component_and_not_by_text(self, tmp_path) -> None:
        """A project at `/x/library` is not under an installed path at `/x/lib`."""
        from simple_agents.records.manifest import _INSTALLED, _is_the_project_s

        made = types.ModuleType("beside_an_installed_path")
        beside = Path(str(Path(_INSTALLED[0])) + "rary") / "agent.py"
        made.__file__ = str(beside)

        assert _is_the_project_s(made)
