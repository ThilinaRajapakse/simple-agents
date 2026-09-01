"""The page a builder meets at the `shape` gate, where the pipeline is declared and unbuilt.

``scripts/view_at_stage.py`` derives a `shape` page by subtraction: the built project with its
runs and evaluation removed. That page reports twelve built steps, which is what a project at
`shape` does not have. ``view_projects/skeleton`` is the same pipeline as ``branching`` written
the way a coding agent first writes one, so the drawing, the cards and the findings are tested
against thirteen `NotBuilt` steps rather than against one.

The pin below is what keeps the two from drifting: the skeleton declares `branching`'s node
ids, kinds, edges, error paths, tools and budgets, and a change to either that is not made to
the other fails here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simple_agents.view import assemble

FIXTURES = Path(__file__).parent / "fixtures" / "view_projects"


def shape(name: str) -> dict:
    return assemble(FIXTURES / name)


@pytest.fixture(scope="module")
def skeleton() -> dict:
    return shape("skeleton")


@pytest.fixture(scope="module")
def built() -> dict:
    return shape("branching")


def by_id(page: dict) -> dict[str, dict]:
    return {f"{p['name']}/{n['id']}": n for p in page["pipelines"] for n in p["nodes"]}


class TestPinnedToBranching:
    """The skeleton is `branching`'s shape, and drift in either is a failure here."""

    def test_the_same_pipelines_and_steps(self, skeleton: dict, built: dict) -> None:
        assert sorted(by_id(skeleton)) == sorted(by_id(built))

    def test_the_same_kind_of_step_throughout(self, skeleton: dict, built: dict) -> None:
        planned, real = by_id(skeleton), by_id(built)
        assert {k: n["kind"] for k, n in planned.items()} == {k: n["kind"] for k, n in real.items()}

    def test_the_same_edges_error_paths_and_fan_out(self, skeleton: dict, built: dict) -> None:
        planned, real = by_id(skeleton), by_id(built)
        for key, node in real.items():
            assert planned[key]["successors"] == node["successors"], key
            assert planned[key]["on_error"] == node["on_error"], key
            assert planned[key]["fan_out"] == node["fan_out"], key

    def test_the_same_tools_and_what_each_touches(self, skeleton: dict, built: dict) -> None:
        planned, real = by_id(skeleton), by_id(built)
        for key, node in real.items():
            assert [t["name"] for t in planned[key]["tools"]] == [
                t["name"] for t in node["tools"]
            ], key
            assert planned[key]["touches"] == node["touches"], key

    def test_the_same_budgets(self, skeleton: dict, built: dict) -> None:
        planned, real = by_id(skeleton), by_id(built)
        for key, node in real.items():
            assert planned[key]["budget"] == node["budget"], key

    def test_the_same_resources_and_who_reaches_each(self, skeleton: dict, built: dict) -> None:
        assert [r["name"] for r in skeleton["resources"]] == [r["name"] for r in built["resources"]]


class TestNothingIsBuilt:
    def test_every_step_is_planned(self, skeleton: dict) -> None:
        assert all(n["planned"] for n in by_id(skeleton).values())

    def test_each_carries_what_it_will_do(self, skeleton: dict) -> None:
        assert all(n["does"] for n in by_id(skeleton).values())

    def test_the_sentence_at_the_top_counts_what_is_owed(self, skeleton: dict) -> None:
        assert "0 steps built, 13 still to build" in skeleton["standing"]

    def test_a_step_with_no_schema_yet_says_so_rather_than_guessing(self, skeleton: dict) -> None:
        assert by_id(skeleton)["triage/intake"]["produces"] is None

    def test_what_each_step_receives_is_still_derived(self, skeleton: dict) -> None:
        """Nothing is built, and the edges still say what travels along them."""
        nodes = by_id(skeleton)
        assert nodes["triage/apologise"]["takes_in"]["says"].startswith("A NodeFailure")
        assert nodes["triage/publish"]["takes_in"]["join"] is True
        assert "Ticket, from classify" == nodes["triage/escalate"]["takes_in"]["says"]

    def test_no_store_has_a_flow_to_draw(self, skeleton: dict) -> None:
        """The system level's links have no width to take at this stage, and say nothing."""
        assert all(
            counts == {"runs": 0, "rollouts": 0}
            for r in skeleton["resources"]
            for counts in (r["flow"] or {}).values()
        )

    def test_no_run_overlay_anywhere(self, skeleton: dict) -> None:
        assert skeleton["measured"] is None
        assert skeleton["rollouts"]["runs"] == 0
        assert all(n.get("example") is None for n in by_id(skeleton).values())


class TestWhatItTellsTheBuilder:
    def test_the_skeleton_is_reported_and_is_not_urgent_at_this_stage(self, skeleton: dict) -> None:
        owed = [f for f in skeleton["findings"] if "13 steps not built" in f["head"]]
        assert owed and owed[0]["severity"] == "note"

    def test_an_answer_read_from_the_evaluation_waits_rather_than_disagreeing(
        self, skeleton: dict
    ) -> None:
        """`judged_steps` is scored by the evaluation, and `shape` has none.

        The answer names `classify`; the evaluation that would confirm it does not exist yet.
        Reporting that as a contradiction put a false alarm at the top of every `shape` page.
        """
        judged = next(c for c in skeleton["claims"] if c["entry"] == "judged_steps")
        assert judged["names"] == ["classify"]
        assert judged["unread"] == "the evaluation"
        assert judged["named_but_not"] == []
        assert not [f for f in skeleton["findings"] if "disagree" in f["head"]]

    def test_answers_read_from_the_code_still_compare(self, skeleton: dict) -> None:
        """The other five read the pipeline, which a skeleton has."""
        agency = next(c for c in skeleton["claims"] if c["entry"] == "agency_boundary")
        assert agency["unread"] is None
        assert agency["agreed"] == ["answer_directly"]

    def test_a_design_nobody_agreed_to_says_so(self, skeleton: dict) -> None:
        """The state every project is in at `shape`, which the page said nothing about.

        It marked a confirmed shape as agreed and a moved one as changed, and where no
        confirmation existed it printed neither, so a proposal read as a settled design.
        """
        led = skeleton["findings"][0]
        assert led["severity"] == "attention"
        assert "have not agreed to" in led["head"]
        assert led["target"]["pipeline"] in {"triage", "reindex"}
        assert "2 pipelines await" in skeleton["standing"]

    def test_a_confirmed_design_says_nothing_of_the_kind(self, built: dict) -> None:
        assert not [f for f in built["findings"] if "agreed to" in f["head"]]

    def test_a_question_is_named_for_the_builder_and_not_by_its_key(self, skeleton: dict) -> None:
        entries = {e["name"]: e for e in skeleton["brief"]["entries"]}
        assert entries["agency_boundary"]["title"] == "What the agent works out for itself"
        assert entries["agency_boundary"]["asks"].startswith("What would the builder like")
