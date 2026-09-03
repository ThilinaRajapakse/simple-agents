"""A number the code no longer carries, on the page that offers to agree to it.

The manifest is a record of what the code held when it ran, so a number deleted from the code
stays in every older manifest. One project's page offered "PRIMARY should be 10. Record it as a
constant decision" about a name the code had lost, the builder clicked it, and the brief holds
a `changed` decision answering a constant nothing has.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import types
from pathlib import Path

import pytest

from simple_agents.view.constants import read_constants

TEMPLATE = Path(__file__).parent.parent / "src" / "simple_agents" / "view" / "template.html"

NO_DECISIONS = types.SimpleNamespace(decisions=[])


def _run(
    root: Path, run_id: str, *, pipeline: str | None, started_at: str, constants: list[str]
) -> None:
    """One run on disk, carrying the numbers its manifest recorded."""
    where = root / "runs" / "dev" / started_at[:10] / run_id
    where.mkdir(parents=True)
    (where / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "pipeline": pipeline,
                # A run says whether it is a rollout; without it the depth is what decides,
                # and a run filed under runs/dev/<date>/ sits as deep as one.
                "evaluation": None,
                "started_at": started_at,
                "outcome": "completed",
                "constants": [{"module": "agent", "name": name, "value": 10} for name in constants],
                "prompts": {},
                "nodes": [],
            }
        )
    )


def _by_name(root: Path) -> dict[str, dict]:
    return {row["name"]: row for row in read_constants(root, [], NO_DECISIONS)}


class TestANameTheNewestRunNoLongerCarries:
    def test_it_is_marked_gone_and_dated(self, tmp_path: Path) -> None:
        _run(
            tmp_path,
            "older",
            pipeline="recommend",
            started_at="2026-09-01T09:00:00.000Z",
            constants=["PRIMARY", "TOP_K"],
        )
        _run(
            tmp_path,
            "newer",
            pipeline="recommend",
            started_at="2026-09-03T09:00:00.000Z",
            constants=["TOP_K"],
        )
        rows = _by_name(tmp_path)

        assert rows["PRIMARY"]["gone"] is True
        assert rows["PRIMARY"]["last_seen"] == "2026-09-01"
        assert rows["TOP_K"]["gone"] is False

    def test_a_gone_name_sorts_last(self, tmp_path: Path) -> None:
        _run(
            tmp_path,
            "older",
            pipeline="recommend",
            started_at="2026-09-01T09:00:00.000Z",
            constants=["AAA", "TOP_K"],
        )
        _run(
            tmp_path,
            "newer",
            pipeline="recommend",
            started_at="2026-09-03T09:00:00.000Z",
            constants=["TOP_K"],
        )

        assert [row["name"] for row in read_constants(tmp_path, [], NO_DECISIONS)] == [
            "TOP_K",
            "AAA",
        ]

    def test_another_pipeline_still_carrying_it_keeps_it(self, tmp_path: Path) -> None:
        """A number two pipelines reach is gone only when neither of them reaches it."""
        _run(
            tmp_path,
            "recommend",
            pipeline="recommend",
            started_at="2026-09-03T09:00:00.000Z",
            constants=["TOP_K"],
        )
        _run(
            tmp_path,
            "freshen",
            pipeline="freshen",
            started_at="2026-09-04T06:00:00.000Z",
            constants=["TOP_K", "BATCH"],
        )
        rows = _by_name(tmp_path)

        assert rows["TOP_K"]["gone"] is False
        assert rows["BATCH"]["gone"] is False

    def test_a_background_pass_does_not_make_the_agents_numbers_gone(self, tmp_path: Path) -> None:
        """The newest run of each pipeline, rather than the newest run."""
        _run(
            tmp_path,
            "recommend",
            pipeline="recommend",
            started_at="2026-09-03T09:00:00.000Z",
            constants=["TOP_K"],
        )
        _run(
            tmp_path,
            "freshen",
            pipeline="freshen",
            started_at="2026-09-04T06:00:00.000Z",
            constants=["BATCH"],
        )

        assert _by_name(tmp_path)["TOP_K"]["gone"] is False

    def test_a_project_whose_runs_name_no_pipeline_marks_nothing_gone(self, tmp_path: Path) -> None:
        """Which pipeline ran last is unrecorded before manifest format 0.41."""
        _run(
            tmp_path,
            "older",
            pipeline=None,
            started_at="2026-09-01T09:00:00.000Z",
            constants=["PRIMARY", "TOP_K"],
        )
        _run(
            tmp_path,
            "newer",
            pipeline=None,
            started_at="2026-09-03T09:00:00.000Z",
            constants=["TOP_K"],
        )

        assert [row["gone"] for row in read_constants(tmp_path, [], NO_DECISIONS)] == [False, False]

    def test_a_project_with_no_runs_reads_as_nothing(self, tmp_path: Path) -> None:
        assert read_constants(tmp_path, [], NO_DECISIONS) == []


class TestWhatThePageDoesWithIt:
    """The row is drawn as removed from the code and offers no agreement."""

    def _region(self, rows: list[dict]) -> str:
        """The constants region's own script, run over these rows.

        The region is lifted out of the template and given the handful of helpers it calls, so
        what is asserted is the markup the page builds rather than a copy of it here.
        """
        if shutil.which("node") is None:
            pytest.skip("no JS engine on PATH")
        template = TEMPLATE.read_text(encoding="utf-8")
        source = template[template.index("function constantsRegion()") :]
        source = source[: source.index("\n}\n") + 3]
        script = f"""
        const esc = s => String(s);
        const fmt = n => String(n);
        const short = (s, n) => ({{said: String(s)}});
        const sentOr = (a, b) => b;
        const SAY = {{agreeNumber: (n, v) => ({{at: "project", said: n}})}};
        const measureTitle = (a, b) => `${{a}} ${{b}}`;
        const DATA = {{constants: {json.dumps(rows)}}};
        {source}
        console.log(constantsRegion());
        """
        done = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr
        return done.stdout

    def test_a_gone_row_says_so_and_offers_no_agreement(self, tmp_path: Path) -> None:
        _run(
            tmp_path,
            "older",
            pipeline="recommend",
            started_at="2026-09-01T09:00:00.000Z",
            constants=["PRIMARY", "TOP_K"],
        )
        _run(
            tmp_path,
            "newer",
            pipeline="recommend",
            started_at="2026-09-03T09:00:00.000Z",
            constants=["TOP_K"],
        )
        drawn = self._region(read_constants(tmp_path, [], NO_DECISIONS))

        assert "Not in the code" in drawn
        assert "Last recorded 2026-09-01" in drawn
        assert 'data-agreenum="PRIMARY"' not in drawn
        assert 'data-agreenum="TOP_K"' in drawn, "the one the code still has still offers it"

    def test_a_gone_row_is_not_counted_as_unconfirmed(self, tmp_path: Path) -> None:
        _run(
            tmp_path,
            "older",
            pipeline="recommend",
            started_at="2026-09-01T09:00:00.000Z",
            constants=["PRIMARY", "TOP_K"],
        )
        _run(
            tmp_path,
            "newer",
            pipeline="recommend",
            started_at="2026-09-03T09:00:00.000Z",
            constants=["TOP_K"],
        )
        drawn = self._region(read_constants(tmp_path, [], NO_DECISIONS))

        assert "2 · 1 unconfirmed" in drawn
        assert "1 number is not in the code any more" in drawn
