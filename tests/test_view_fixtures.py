"""The view fixtures' records are what the library writes today.

A fixture written under an older format is not the artifact the view will meet: the view's
readers document fallbacks for older manifests, and a fixture set that only ever exercises
the fallback says nothing about the current field. The fixtures sat at manifest `0.32`
against `0.38` with every test green before this file existed.
`scripts/build_view_fixtures.py --record` re-records them live (about 0.005 USD), and its
offline default verifies the committed cassettes still serve the current library.

One run is exempt by name. `many-pipelines` asserts `code_moved_since` on `ingest`, and the
code that made its run was replaced by a `NotBuilt` afterwards and is gone, so that run
cannot be regenerated and its staleness is the property under test. The exemption is exact:
if that run ever carries current formats, the property is unproved and the test here fails
so the exemption is re-decided rather than kept out of habit.
"""

from __future__ import annotations

import functools
import json
from collections import Counter
from pathlib import Path

import pytest

from simple_agents.evaluation.outcomes import Outcome
from simple_agents.view import assemble

FIXTURES = Path(__file__).parent / "fixtures" / "view_projects"
REGENERATE = "run `uv run python scripts/build_view_fixtures.py`"

FROZEN = "many-pipelines/runs/run_20260826T005906Z_2d8817fc"


def _is_right(outcome: str) -> bool:
    try:
        return Outcome(outcome).succeeded
    except ValueError:
        return False


class TestTheViewFixturesAreCurrent:
    def _versions(self, pattern: str, key: str) -> dict[str, set[str]]:
        """Which version each matching file carries, keyed by version, less the frozen run."""
        found: dict[str, set[str]] = {}
        for path in sorted(FIXTURES.glob(pattern)):
            name = str(path.relative_to(FIXTURES))
            if name.startswith(FROZEN):
                continue
            record = json.loads(path.read_text())
            found.setdefault(str(record.get(key)), set()).add(name)
        return found

    def test_every_manifest_carries_the_current_formats(self):
        from simple_agents.records.manifest import MANIFEST_FORMAT_VERSION
        from simple_agents.records.trajectory import FORMAT_VERSION as TRAJECTORY_VERSION

        for key, current in (
            ("format_version", MANIFEST_FORMAT_VERSION),
            ("trajectory_format_version", TRAJECTORY_VERSION),
        ):
            seen = self._versions("*/runs/**/manifest.json", key)
            assert seen, f"no fixture manifests found; {REGENERATE}"
            assert set(seen) == {current}, (
                f"view fixture manifests carry {key} {sorted(seen)} and the writer writes "
                f"{current!r}, so the view's reader for a {current}-only field would be "
                f"exercised against files that cannot carry one. {REGENERATE}."
            )

    def test_every_results_file_carries_the_current_format(self):
        from simple_agents.evaluation import EVAL_FORMAT_VERSION

        seen = self._versions("*/evals/results/*.json", "eval_format_version")
        assert seen, f"no fixture results files found; {REGENERATE}"
        assert set(seen) == {EVAL_FORMAT_VERSION}, (
            f"view fixture results files carry {sorted(seen)} and the writer writes "
            f"{EVAL_FORMAT_VERSION!r}. {REGENERATE}."
        )

    def test_the_stage_copies_are_current_too(self):
        from simple_agents.records.manifest import MANIFEST_FORMAT_VERSION

        seen = self._versions("_stages/*/runs/**/manifest.json", "format_version")
        assert seen, f"no _stages manifests found; {REGENERATE}"
        assert set(seen) == {MANIFEST_FORMAT_VERSION}, (
            f"_stages is derived from branching and carries {sorted(seen)}; it was not "
            f"rebuilt with it. {REGENERATE}."
        )

    def test_the_frozen_run_is_still_the_stale_one(self):
        from simple_agents.records.manifest import MANIFEST_FORMAT_VERSION

        manifest = FIXTURES / FROZEN / "manifest.json"
        assert manifest.exists(), (
            f"{FROZEN} is gone. It cannot be regenerated (its generating code is gone) and "
            f"must be restored from git."
        )
        record = json.loads(manifest.read_text())
        assert record.get("format_version") != MANIFEST_FORMAT_VERSION, (
            f"{FROZEN} carries the current manifest format, so its staleness no longer "
            f"holds and `code_moved_since` is tested by nothing. Either restore the frozen "
            f"run or remove its exemption here and in scripts/build_view_fixtures.py."
        )


class TestTheAbsenceExampleIsOnTheRecord:
    """`DF5-X20`'s fixture: a right report of absence, checked page against report.

    The view held its own list of right outcomes naming two that do not exist, so every
    `correct_abstention` counted as wrong on the agent's line, on the floor's, and in the
    list of examples that went wrong, with 3,796 tests green over it: no view fixture held
    one. This is that fixture, and the page's counts are checked against the results file
    on the same data.
    """

    def _raw(self, project: str = "branching") -> dict:
        path = FIXTURES / project / "evals" / "results" / "held-out.json"
        return json.loads(path.read_text())

    def test_the_record_holds_a_right_report_of_absence(self):
        raw = self._raw()
        outcomes = Counter(str(r.get("outcome")) for r in raw["rollouts"])
        assert outcomes.get("correct_abstention", 0) >= 1, (
            f"branching's evaluation records no correct_abstention (outcomes: "
            f"{dict(outcomes)}). The t-nonsense example exists so the page's counting of a "
            f"right report of absence is exercised; run `uv run python scripts/build_view_fixtures.py --record`."
        )
        assert raw.get("baseline"), "branching's evaluation records no baseline block"

    @pytest.mark.parametrize("project", ["branching", "measured"])
    def test_the_page_counts_agree_with_the_record(self, project):
        raw = self._raw(project)
        measured = assemble(FIXTURES / project)["measured"]
        rights = sum(1 for r in raw["rollouts"] if _is_right(str(r.get("outcome"))))
        assert measured["counts"] == {"right": rights, "of": len(raw["rollouts"])}
        assert measured["outcomes"] == dict(Counter(str(r.get("outcome")) for r in raw["rollouts"]))
        floor_rights = sum(1 for e in raw["baseline"] if _is_right(str(e.get("outcome"))))
        assert measured["floor"] == {"right": floor_rights, "of": len(raw["baseline"])}
        wrong = {one["example"] for one in measured["went_wrong"]}
        succeeded_everywhere = {
            str(r.get("example")) for r in raw["rollouts"] if _is_right(str(r.get("outcome")))
        }
        assert not (wrong & succeeded_everywhere) or all(
            any(
                not _is_right(str(r.get("outcome")))
                for r in raw["rollouts"]
                if str(r.get("example")) == example
            )
            for example in wrong
        ), "an example every rollout got right is listed under went wrong"


@functools.lru_cache(maxsize=1)
def _measured() -> dict:
    return assemble(FIXTURES / "measured")["measured"]


class TestTheMeasuredFixtureHoldsEverySurface:
    """`measured` is the project the measure page was designed against: thirty held-out
    examples, a key with parts, two labelled steps, a paid tool, a sweep of two variants,
    two rungs, and three earlier evaluations. Every region of the page has data here, and
    a region that goes empty on it has lost its data rather than never had any.
    """

    @pytest.fixture(scope="class")
    def measured(self, request) -> dict:
        return _measured()

    def test_the_evaluation_is_big_enough_for_a_verdict(self, measured):
        assert measured["n"] >= 20 and measured["counts"]["of"] >= 40
        assert measured["floor"]["of"] == measured["n"]

    def test_every_kind_of_figure_is_on_the_record(self, measured):
        names = {f["name"] for f in measured["metrics"]}
        assert {"accuracy", "recall", "total_error_gbp", "money_approved_share"} <= names
        assert {c["name"] for c in measured["criteria"]} == {
            "decision",
            "vendor",
            "total",
            "category",
            "po_number",
        }
        assert measured["nodes"]["extract"]["accuracy"] and measured["nodes"]["decide"]["accuracy"]
        assert set(measured["groups"]["keys"]) == {"category", "source"}

    def test_the_sweep_holds_a_moved_verdict_and_a_held_one(self, measured):
        (sweep,) = measured["comparisons"]
        verdicts = {
            name: {k: c["moved"] for k, c in v["comparison"]["metrics"].items()}
            for name, v in sweep["variants"].items()
        }
        assert verdicts["finance without the registry"]["false_confidence_rate"] is True
        assert verdicts["audit cannot send back"]["accuracy"] is False

    def test_the_ladder_has_one_whole_rung_and_two_cut(self, measured):
        (ladder,) = measured["ladders"]
        assert [r["whole"] for r in ladder["rungs"]] == [True, False, False]
        assert [r["start"] for r in ladder["rungs"][1:]] == ["extract", "policy_check"]

    def test_the_trend_has_a_behaviour_break(self, measured):
        rows = [h for h in measured["history"] if not h["slice"]]
        assert len(rows) >= 4
        assert len({h["behaviour"] for h in rows}) >= 2

    def test_every_grid_row_says_what_it_expects(self, measured):
        assert len(measured["browser"]) == 30
        assert all(r["expects"] for r in measured["browser"])
        assert any(r["expects"].startswith("An absence") for r in measured["browser"])


class TestTheShippedFixtureHoldsWhatItIsFor:
    """`shipped` is `measured` at stage `ship` with its product declared (`P3-56`).

    It is derived rather than recorded, so what it has to hold is asserted here rather than
    trusted: the surfaces the ship page draws, a live run the operations page will read, and
    one surface the design section never names, which is what the widened FT-34 reports.
    """

    def project(self) -> Path:
        root = FIXTURES / "shipped"
        assert root.is_dir(), f"the shipped fixture is missing; {REGENERATE} --record"
        return root

    def test_it_declares_a_product_beside_the_pipeline(self) -> None:
        from simple_agents.view.discovery import load_project

        held = load_project(self.project())
        assert [s.name for s in held.product.surfaces] == [
            "the finance inbox",
            "the finance desk",
            "the ledger",
        ]
        assert held.product_module == "surface"

    def test_it_holds_live_runs_of_its_own(self) -> None:
        """What a shipped project's own traffic leaves behind, which is what `runs(live=True)`
        reads and what the dev runs are not."""
        from simple_agents import runs

        live = runs(self.project() / "runs", live=True)
        assert len(live) >= 2
        assert all(one.manifest.get("live") for one in live)
        # and one of each state the operate page reads
        assert sum(1 for one in live if one.outcome == "suspended") == 2
        assert sum(1 for one in live if one.outcome is None) == 1
        assert sum(1 for one in live if one.manifest.get("conversation")) == 2

    def test_one_surface_is_missing_from_the_design_section(self) -> None:
        from simple_agents.conformance.artifacts import PRODUCT_SECTION
        from simple_agents.conformance.checks import _section_of

        text = (self.project() / "design.md").read_text(encoding="utf-8")
        section = (_section_of(text, PRODUCT_SECTION) or "").casefold()
        assert "the finance inbox" in section and "the finance desk" in section
        assert "the ledger" not in section, (
            "the fixture's gap is what exercises FT-34's reading of the declaration"
        )

    def test_the_brief_is_at_ship_and_carries_what_that_gate_reads(self) -> None:
        import tomllib

        held = tomllib.loads((self.project() / "brief.toml").read_text(encoding="utf-8"))
        assert held["stage"] == "ship"
        assert held["confirmed_against"].startswith("sha256:")
        for name in ("someone_there", "live_records", "watching_live", "stored_output"):
            assert held["entries"][name]["status"] == "answered", name
