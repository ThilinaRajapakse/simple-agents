"""The measure page's head-to-head region: a session of judged pairs, read off its results file.

The reader is tested here against a session `paired_results` wrote into a scratch project, so
what the page draws is what the writer files. The page's own drawing of it is held in
`tests/test_view_runs.py` against the `measured` fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents.evaluation import Label, Pair, paired_figure, paired_results
from simple_agents.view.evaluation import _tally, read_evaluation


def chose(pair, verdict):
    return {"a": pair.a_arm, "b": pair.b_arm}.get(verdict, verdict)


def session(root: Path, *, name: str = "pairwise-glm-v-gemini", when: str = "2026-09-07") -> Path:
    """Seventeen pairs between two arms with a third verdict the mapping does not name."""
    pairs = [
        Pair(
            id=f"p{i}",
            a=f"show {i}a",
            b=f"show {i}b",
            a_arm="gemini" if i % 2 else "glm",
            b_arm="glm" if i % 2 else "gemini",
        )
        for i in range(17)
    ]
    verdicts = ["a"] * 7 + ["b"] * 5 + ["both_good"] * 2 + ["both_bad"] * 2 + ["unsure"]
    labels = {
        p.id: Label(
            id=p.id,
            verdict=v,
            decided_by="builder",
            decided_at=f"{when}T12:{i:02d}:00+00:00",
            reason="" if i else "close call",
        )
        for i, (p, v) in enumerate(zip(pairs, verdicts))
    }
    figure = paired_figure(
        pairs,
        labels,
        name="gemini_beats_glm",
        definition="d",
        numerator=lambda p, v: chose(p, v) == "gemini",
        denominator=lambda p, v: chose(p, v) in ("gemini", "glm"),
        resamples=200,
    )
    results = paired_results(
        pairs,
        labels,
        figures=[figure],
        eval_id=name,
        blind=True,
        verdicts_mean={"a": "a", "b": "b", "both_good": "both", "both_bad": "neither"},
    )
    return results.write(root / "evals" / "results" / f"{name}.json")


class TestTheTally:
    def test_it_credits_the_arm_a_verdict_picked_and_counts_the_ties(self) -> None:
        pairs = [
            {"a_arm": "x", "b_arm": "y", "verdict": "a", "decided_by": "h"},
            {"a_arm": "y", "b_arm": "x", "verdict": "a", "decided_by": "h"},
            {"a_arm": "x", "b_arm": "y", "verdict": "b", "decided_by": "h"},
            {"a_arm": "x", "b_arm": "y", "verdict": "tie_good", "decided_by": "h"},
            {"a_arm": "x", "b_arm": "y", "verdict": "tie_bad", "decided_by": "h"},
            {"a_arm": "x", "b_arm": "y", "verdict": "skipped", "decided_by": "h"},
            {"a_arm": "x", "b_arm": "y", "verdict": None, "decided_by": None},
            # Two things from one arm: a preference between them is counted apart, a tie as a tie.
            {"a_arm": "y", "b_arm": "y", "verdict": "a", "decided_by": "h"},
            {"a_arm": "y", "b_arm": "y", "verdict": "tie_good", "decided_by": "h"},
        ]
        held = _tally(pairs, {"a": "a", "b": "b", "tie_good": "both", "tie_bad": "neither"})
        assert held == {
            "for_arm": {"x": 1, "y": 2},
            "decided": 3,
            "within_arm": {"y": 1},
            "both": 2,
            "neither": 1,
            "other": {"skipped": 1},
            "unjudged": 1,
        }

    def test_an_unmapped_verdict_is_never_credited_to_a_side(self) -> None:
        pairs = [{"a_arm": "x", "b_arm": "y", "verdict": "a", "decided_by": "h"}]
        assert _tally(pairs, {})["other"] == {"a": 1}


class TestASessionOnThePage:
    @pytest.fixture()
    def project(self, tmp_path) -> Path:
        (tmp_path / "evals" / "results").mkdir(parents=True)
        session(tmp_path)
        session(tmp_path, name="pairwise-llm-v-ranking", when="2026-09-01")
        return tmp_path

    def test_every_session_is_read_newest_first(self, project) -> None:
        held = read_evaluation(project)
        assert [s["file"] for s in held["sessions"]] == [
            "pairwise-glm-v-gemini.json",
            "pairwise-llm-v-ranking.json",
        ]

    def test_a_session_carries_what_the_region_draws(self, project) -> None:
        (s,) = [s for s in read_evaluation(project)["sessions"] if "glm" in s["file"]]
        assert s["contest"] == ["gemini", "glm"]
        assert s["blind"] is True and s["decided_by"] == ["builder"]
        assert (s["n"], s["units"]) == (17, 17)
        # The arms alternate by pair, so the seven `a` verdicts credit glm four times and
        # gemini three, the five `b` verdicts glm three and gemini two, and the seventeenth
        # verdict is outside the mapping.
        assert s["tally"] == {
            "for_arm": {"gemini": 5, "glm": 7},
            "decided": 12,
            "within_arm": {},
            "both": 2,
            "neither": 2,
            "other": {"unsure": 1},
            "unjudged": 0,
        }
        assert [f["name"] for f in s["figures"]] == ["gemini_beats_glm"]
        assert (s["figures"][0]["numerator"], s["figures"][0]["denominator"]) == (5, 12)
        first = s["pairs"][0]
        assert first == {
            "id": "p0",
            "a": "show 0a",
            "b": "show 0b",
            "a_arm": "glm",
            "b_arm": "gemini",
            "example_id": None,
            "verdict": "a",
            "meaning": "a",
            "decided_by": "builder",
            "decided_at": "2026-09-07T12:00:00+00:00",
            "reason": "close call",
        }
        assert s["pairs"][-1]["meaning"] is None and s["pairs"][-1]["verdict"] == "unsure"

    def test_the_reported_session_is_marked_and_read_as_pairs(self, project) -> None:
        (project / "brief.toml").write_text(
            'results = "evals/results/pairwise-glm-v-gemini.json"\n', encoding="utf-8"
        )
        held = read_evaluation(project)
        assert held["kind"] == "pairs"
        assert held["path"] == "pairwise-glm-v-gemini.json"
        assert [s["reported"] for s in held["sessions"]] == [True, False]
        assert [h["kind"] for h in held["history"]] == ["pairs", "pairs"]

    def test_the_history_has_no_cut(self, tmp_path) -> None:
        (tmp_path / "evals" / "results").mkdir(parents=True)
        for i in range(15):
            session(tmp_path, name=f"s{i:02d}", when=f"2026-08-{1 + i:02d}")
        assert len(read_evaluation(tmp_path)["history"]) == 15

    def test_a_file_that_is_not_a_session_is_not_one(self, project) -> None:
        raw = json.loads((project / "evals" / "results" / "pairwise-glm-v-gemini.json").read_text())
        raw["config"]["kind"] = "pairwise"  # a project's own key, which nothing reads
        (project / "evals" / "results" / "pairwise-glm-v-gemini.json").write_text(json.dumps(raw))
        assert [s["file"] for s in read_evaluation(project)["sessions"]] == [
            "pairwise-llm-v-ranking.json"
        ]
