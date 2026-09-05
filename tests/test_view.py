"""The view, against the five project shapes it has to serve.

The fixtures under ``tests/fixtures/view_projects/`` are one project per shape: day zero,
mid-build with a placeholder step and comments, a single pipeline, many pipelines sharing
resources, and a batch project. ``one-pipeline`` and ``many-pipelines`` carry a real run
each, so the run overlay and the change ledger are tested against real manifests. What the
page *says* is asserted here, off ``assemble``; how it looks is verified against rendered
screenshots, which a suite cannot do.
"""

from __future__ import annotations

import copy
import functools
import json
import re
from pathlib import Path

import pytest

from simple_agents import Deterministic, LLMNode, NotBuilt, Pipeline, pipeline_factory
from simple_agents.errors import ConfigurationError
from simple_agents.registry import clear_registered_pipelines, registered_pipelines
from simple_agents.view import assemble, generate_view, render

FIXTURES = Path(__file__).parent / "fixtures" / "view_projects"


@functools.lru_cache(maxsize=None)
def _assembled(name: str) -> dict:
    return assemble(FIXTURES / name)


def shape(name: str) -> dict:
    return copy.deepcopy(_assembled(name))


class TestNotBuilt:
    def test_a_planned_node_declares_itself(self) -> None:
        node = Deterministic(NotBuilt("filters the pool"), node_id="pool")
        assert node.planned
        assert node.fn_entry["source"] == "not_built"
        assert node.fn_entry["does"] == "filters the pool"

    def test_one_with_no_id_is_refused_naming_the_fix(self) -> None:
        with pytest.raises(ConfigurationError, match="node_id="):
            Deterministic(NotBuilt("filters the pool"))

    def test_one_with_no_description_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="what the step will do"):
            NotBuilt("   ")

    def test_an_llm_node_may_leave_the_schema_unsettled(self) -> None:
        node = LLMNode(NotBuilt("writes the recap"), output_schema=None, node_id="recap")
        assert node.planned and node.output_schema is None

    def test_executing_one_refuses_and_names_the_step(self) -> None:
        node = Deterministic(NotBuilt("filters the pool"), node_id="pool")
        with pytest.raises(ConfigurationError, match="pool.*filters the pool"):
            node.execute({}, run=None)

    def test_the_rest_of_the_pipeline_still_runs(self, tmp_path) -> None:
        """A part-built pipeline is runnable down its built paths."""
        from simple_agents import Budget, RunEnvelope

        done = Deterministic(lambda inputs, ctx: "made it", node_id="works")
        held = Deterministic(NotBuilt("second half"), node_id="rest")
        pipeline = Pipeline([done, held], budget=Budget.unbounded())
        with pytest.raises(ConfigurationError, match="rest"):
            pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path / "runs"))
        manifest = json.loads(next((tmp_path / "runs").glob("**/manifest.json")).read_text())
        planned = {n["node_id"]: n["planned"] for n in manifest["nodes"]}
        assert planned == {"works": False, "rest": True}


class TestTheFactoryRegistry:
    def test_registering_and_reading_back(self) -> None:
        clear_registered_pipelines()

        @pipeline_factory("one")
        def one():  # pragma: no cover - never called here
            return None

        assert list(registered_pipelines()) == ["one"]
        clear_registered_pipelines()

    def test_a_second_factory_under_one_name_is_refused(self) -> None:
        clear_registered_pipelines()

        @pipeline_factory("taken")
        def first():  # pragma: no cover
            return None

        with pytest.raises(ConfigurationError, match="taken"):

            @pipeline_factory("taken")
            def second():  # pragma: no cover
                return None

        clear_registered_pipelines()


class TestDayZero:
    def test_the_page_is_calm_and_honest(self) -> None:
        data = shape("day-zero")
        assert data["pipelines"] == []
        assert "no pipeline yet" in data["standing"]
        assert data["problems"] == []

    def test_the_only_urgency_is_the_stage_questions(self) -> None:
        data = shape("day-zero")
        urgent = [f for f in data["findings"] if f["severity"] == "attention"]
        assert len(urgent) == 1
        assert "question" in urgent[0]["head"]


class TestOnePipeline:
    def test_it_declares_one_built_pipeline(self) -> None:
        data = shape("one-pipeline")
        [pipeline] = data["pipelines"]
        assert (pipeline["name"], pipeline["status"]) == ("summarise", "built")

    def test_the_real_run_is_attached_with_per_step_figures(self) -> None:
        """The run on disk was made live by Gemini; the overlay reads its manifest."""
        data = shape("one-pipeline")
        [pipeline] = data["pipelines"]
        assert pipeline["runs"]["runs"] == 1
        assert pipeline["runs"]["models"] == ["gemini-3.1-flash-lite"]
        assert not pipeline["runs"]["code_moved_since"]
        ran = {n["id"]: n["ran"]["executions"] for n in pipeline["nodes"]}
        assert ran == {"load_note": 1, "write_summary": 1}

    def test_nothing_changed_so_no_ledger(self) -> None:
        assert shape("one-pipeline")["ledgers"] == {}


class TestTheBuildersIntent:
    def test_the_project_opens_with_what_the_builder_is_trying_to_do(self) -> None:
        intent = shape("branching")["intent"]
        assert intent == {
            "purpose": "The rota spends its mornings answering the same handbook questions. This should take those away.",
            "for_whom": "The person on the support rota. They know the product and not the handbook by heart.",
            "outcome": "It answers most tickets from the handbook, asks the rota when unsure, and is never confidently wrong.",
            "surface": "A script the support inbox calls. The reply is saved to the outbox as a draft.",
        }

    def test_a_project_with_only_a_purpose_still_has_a_useful_opening(self) -> None:
        intent = shape("mid-build")["intent"]
        assert intent["purpose"] == "Track my reading list and tell me what to pick up next."
        assert intent["for_whom"] is None


class TestMidBuild:
    def test_the_placeholder_carries_its_words(self) -> None:
        data = shape("mid-build")
        [pipeline] = data["pipelines"]
        judge = next(n for n in pipeline["nodes"] if n["id"] == "judge_books")
        assert judge["planned"]
        assert judge["does"] == "weighs each candidate against what was read recently"
        assert judge["produces"] is None
        assert pipeline["status"] == "in progress"

    def test_the_open_comment_reaches_the_findings(self) -> None:
        data = shape("mid-build")
        heads = [f["head"] for f in data["findings"]]
        # The coding agent spoke last on the fixture's open thread, so it waits on the builder.
        assert any("coding agent has answered" in h for h in heads)
        assert "judge_books: not built." in heads

    def test_the_decision_join_names_the_step_it_talks_about(self) -> None:
        data = shape("mid-build")
        [pipeline] = data["pipelines"]
        pool = next(n for n in pipeline["nodes"] if n["id"] == "gather_pool")
        assert [d["name"] for d in pool["decisions"]] == ["candidate_pool"]
        assert data["decisions_join"]["naming_no_step"] == ["presentation"]
        assert data["decisions_join"]["changed"] == ["presentation"]


class TestManyPipelines:
    def test_the_resources_join_the_pipelines(self) -> None:
        data = shape("many-pipelines")
        catalogue = next(r for r in data["resources"] if r["name"] == "catalogue")
        assert catalogue["writers"] == ["ingest/keep"]
        assert set(catalogue["readers"]) == {
            "recommend/choose_titles",
            "weekly_recap/gather_watched",
        }

    def test_each_link_carries_what_that_pipeline_moves_through_that_store(self) -> None:
        """One end of every link the system level draws.

        The drawing takes its width from this divided by that pipeline's run count, so a
        pipeline that ran often does not draw a thick line for having run often.
        """
        catalogue = next(
            r for r in shape("many-pipelines")["resources"] if r["name"] == "catalogue"
        )
        assert set(catalogue["flow"]) <= {"ingest", "recommend", "weekly_recap"}
        assert all(set(counts) == {"runs", "rollouts"} for counts in catalogue["flow"].values())

    def test_a_paid_call_is_neither_a_reader_nor_a_writer(self) -> None:
        web = next(r for r in shape("many-pipelines")["resources"] if r["name"] == "web")
        assert web["readers"] == [] and web["writers"] == []
        assert web["unknown"] == ["recommend/choose_titles"]

    def test_the_ledger_reads_the_change_since_the_real_run(self) -> None:
        """`dedupe` was added to `ingest` after the run on disk, so the ledger always
        has a real change to report against this fixture."""
        data = shape("many-pipelines")
        assert data["ledgers"] == {"ingest": ["dedupe is new since the last run (planned)."]}
        ingest = next(p for p in data["pipelines"] if p["name"] == "ingest")
        assert ingest["runs"]["code_moved_since"]
        # It leads what is only worth knowing; what waits on the builder sorts above it.
        knowing = [f for f in data["findings"] if not f.get("waits")]
        assert knowing[0]["head"] == "ingest has changed since it last ran."

    def test_a_step_that_decides_for_itself_reads_as_a_noun_in_a_sentence(self) -> None:
        """`decides for itself` is a label and reads as one on a card. Put into a sentence it
        gave "resolve_show is a decides for itself", which shipped on the build page, in the
        attention cards, and into a comment thread's recorded label. Dogfood #6, 2026-09-02.

        The kind words stay as they are, since a card is where they read correctly; what a
        sentence takes is `kind_noun`.
        """
        from simple_agents.view.cards import _KIND_NOUNS, _KIND_WORDS
        from simple_agents.view.findings import _the_brief_disagrees

        assert _KIND_WORDS["agent"] == "decides for itself", "the card label is unchanged"
        for kind, noun in _KIND_NOUNS.items():
            # What follows "a" is a noun. A first word ending in `s` is the third-person verb
            # this went wrong on, and is a plural, which "a" does not take either.
            assert not noun.split()[0].endswith("s"), f"a {noun} does not read as a noun ({kind})"

        found = _the_brief_disagrees(
            {
                "claims": [
                    {
                        "title": "Steps with their own right answer",
                        "named_but_not": ["resolve_show"],
                        "kinds": {"resolve_show": _KIND_NOUNS["agent"]},
                        "one": "carries a right answer of its own",
                        "many": "carry a right answer of their own",
                        "in_code": [],
                    }
                ]
            }
        )
        assert "resolve_show is a step that decides for itself" in found[0]["body"]

    def test_a_step_changing_kind_reads_as_a_sentence(self) -> None:
        """The ledger's other half of the same bug: "changed from fixed step to decides for
        itself"."""
        from simple_agents.view.findings import _ledger

        said = _ledger(
            {
                "runs": {"newest": {"nodes": {"resolve_show": {"kind": "deterministic"}}}},
                "nodes": [
                    {
                        "id": "resolve_show",
                        "kind": "agent",
                        "kind_word": "decides for itself",
                        "kind_noun": "step that decides for itself",
                        "planned": False,
                    }
                ],
            }
        )
        assert said == ["resolve_show changed from a fixed step to a step that decides for itself."]

    def test_money_is_reported_capped_because_the_budget_caps_it(self) -> None:
        data = shape("many-pipelines")
        money = next(f for f in data["findings"] if f["head"] == "Where money can leave.")
        assert money["severity"] == "info"
        assert "$0.002" in money["body"]
        assert "cost cap" in money["body"]

    def test_the_agent_step_says_it_can_ask(self) -> None:
        data = shape("many-pipelines")
        recommend = next(p for p in data["pipelines"] if p["name"] == "recommend")
        [chooser] = recommend["nodes"]
        assert chooser["kind"] == "agent" and chooser["asks_a_person"]
        assert chooser["produces"]["fields"] == [{"name": "titles", "type": "str, or unknown"}]


class TestBatch:
    def test_no_person_anywhere_and_that_is_fine(self) -> None:
        data = shape("batch")
        assert all(not n["asks_a_person"] for p in data["pipelines"] for n in p["nodes"])
        assert all(
            f["severity"] != "attention" or "question" in f["head"] for f in data["findings"]
        )


class TestTheRenderedPage:
    def test_it_is_self_contained_and_carries_the_data(self, tmp_path) -> None:
        written = generate_view(FIXTURES / "mid-build", out=tmp_path / "view.html")
        html = written.read_text()
        assert "judge_books" in html
        assert "__DATA__" not in html and "__TITLE__" not in html
        # A project view is safe to open offline and does not notify a third party that it was opened.
        outside = set(re.findall(r'(?:href|src)="(https?://[^/"]+)', html))
        assert outside == set()

    def test_the_data_path_states_what_a_step_produces_without_proving_an_absence(self) -> None:
        html = render(shape("branching"))
        assert "Produces" in html
        assert "hands on" not in html
        assert "Nothing it produces outlives" not in html

    def test_a_large_pipeline_can_focus_on_the_selected_step_and_its_links(self) -> None:
        html = render(shape("branching"))
        assert "Selected step and links" in html
        assert "Showing the selected step and its direct links." in html

    def test_the_builder_s_purpose_precedes_the_status_summary(self) -> None:
        html = render(shape("branching"))
        assert html.index('id="intent"') < html.index('id="t-standing"')

    def test_the_system_level_says_what_it_is_over_and_what_the_bar_shows(self) -> None:
        """The pipeline level's two controls, one level up (`design/view.md` decision 13)."""
        html = render(shape("branching"))
        assert 'id="sysdials"' in html and 'id="sysnote"' in html
        assert "data-syspop" in html and "data-sysmeasure" in html

    def test_a_link_is_weighted_by_what_moves_along_it_per_run(self) -> None:
        html = render(shape("branching"))
        assert "flowBetween" in html
        assert "A thicker line means more of that store is moved in one run" in html

    def test_the_record_is_a_page_per_stage(self) -> None:
        """The sitting's shell: a stage strip, the homepage anchored to the brief's stage,
        and every section filed on one stage's page."""
        html = render(shape("branching"))
        assert 'id="stagestrip"' in html
        assert "anchorStage" in html and "pageFor" in html
        assert "Boundaries that need checking" in html

    def test_no_library_internals_reach_the_builder(self) -> None:
        """The audience is the builder and the coding agent, never the maintainer.

        The embedded data block is machine-read and may key on internal names; what is
        asserted is everything the page can show: the markup and the script that writes it.
        """
        html = render(shape("mid-build"))
        visible = re.sub(r'<script id="view-data"[^>]*>.*?</script>', "", html, flags=re.DOTALL)
        for internal in ("FT-", "P3-", "manifest", "fingerprint", "conformance"):
            assert internal not in visible, internal

    def test_the_page_says_the_state_and_not_who_did_not_act(self) -> None:
        """Thilina, 2026-08-29, banned the "Nobody …" construction in favour of naming
        the state, which `prose_check`'s `nobody` rule holds; and *"What this turns on"* is
        the phrase decision 29 struck. Both are held off every fixture's page: the
        markup, the script that writes it, and the brief text it shows."""
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from prose_check import NOBODY  # noqa: E402

        for project in (
            "brainstorming",
            "day-zero",
            "skeleton",
            "mid-build",
            "measured",
            "shipped",
            "branching",
            "many-pipelines",
            "batch",
        ):
            html = render(shape(project))
            visible = re.sub(r'<script id="view-data"[^>]*>.*?</script>', "", html, flags=re.DOTALL)
            hit = NOBODY.search(visible)
            assert hit is None, f"{project}: {hit.group(0)!r}"
            assert "turns on" not in visible, project

    def test_the_cli_writes_the_page(self, tmp_path, capsys) -> None:
        from simple_agents.cli import main

        code = main(["view", str(FIXTURES / "batch"), "-o", str(tmp_path / "out.html")])
        assert code == 0
        assert (tmp_path / "out.html").exists()
        assert str(tmp_path / "out.html") in capsys.readouterr().out


class TestTheGateRegeneratesIt:
    def test_check_rewrites_the_page_beside_the_project(self, tmp_path, capsys) -> None:
        import shutil

        from simple_agents.cli import main

        root = tmp_path / "project"
        shutil.copytree(FIXTURES / "mid-build", root)
        main(["check", str(root)])
        out = capsys.readouterr().out
        assert (root / "view.html").exists()
        assert "view.html regenerated" in out

    def test_a_page_that_cannot_generate_never_changes_the_verdict(self, tmp_path, capsys) -> None:
        import shutil

        from simple_agents.cli import main

        root = tmp_path / "project"
        shutil.copytree(FIXTURES / "mid-build", root)
        (root / "agent.py").write_text("this is not python\n")
        code = main(["check", str(root)])
        capsys.readouterr()
        # The import failure reaches the page's problems, not the gate's verdict; the page
        # itself is still written, showing what could be read.
        assert (root / "view.html").exists()
        assert "could not be imported" in (root / "view.html").read_text()
        assert code in (0, 1)


class TestBranching:
    """The sixth shape: routes, a bounded loop, a fan-out, an error path and a nested pipeline.

    It carries a real Gemini run and a real evaluation, both made by ``record.py`` beside it,
    so the derived answers, the run overlay and the measure section are all read against
    records a backend wrote.
    """

    def steps(self) -> dict:
        data = shape("branching")
        triage = next(p for p in data["pipelines"] if p["name"] == "triage")
        return {n["id"]: n for n in triage["nodes"]}

    def test_an_edge_into_a_nested_pipeline_reaches_the_step_inside_it(self) -> None:
        held = self.steps()
        assert "research.pick_sources" in held["classify"]["successors"]
        assert held["research.read_source"]["successors"] == ["draft"]
        assert held["research.pick_sources"]["inside"] == "research"

    def test_what_a_step_takes_in_is_derived_and_never_a_non_answer(self) -> None:
        held = self.steps()
        said = {k: v["takes_in"]["says"] for k, v in held.items()}
        assert said["intake"] == "dict, what the run is given"
        assert said["research.pick_sources"] == "Ticket, from classify"
        assert said["research.read_source"].endswith("once per item in sources")
        assert said["draft"].startswith("A Join with one key per edge:")
        assert "critique (Verdict)" in said["draft"]
        assert said["apologise"].startswith("A NodeFailure from classify")
        assert not any("whatever the step before" in s for s in said.values())

    def test_the_edge_that_closes_a_cycle_is_named(self) -> None:
        assert self.steps()["critique"]["closes_a_cycle"] == ["draft"]

    def test_a_step_the_run_skipped_is_not_a_step_that_ran(self) -> None:
        held = self.steps()
        assert held["publish"]["ran"]["executions"] == 1
        ran = held["answer_directly"]["ran"]
        assert (ran["executions"], ran["skipped"], ran["example"]) == (0, 1, None)
        assert ran["ended"] == {"skipped": 1}

    def test_a_real_value_from_the_run_reaches_the_card(self) -> None:
        held = self.steps()
        example = held["intake"]["example"]
        assert example["run"].startswith("run_")
        [row] = example["took_in"]
        assert row["key"] == "ticket" and "Thanks, that sorted it" in row["value"]
        assert held["answer_directly"]["example"] is None

    def test_the_data_path_reads_end_to_end(self) -> None:
        data = shape("branching")
        triage = next(p for p in data["pipelines"] if p["name"] == "triage")
        path = {row["id"]: row for row in triage["data_path"]}
        assert path["publish"]["ends"] is True
        assert path["research.pick_sources"]["reads"] == ["handbook"]
        # A step's own touches= says nothing about direction, so the page does not either.
        assert path["publish"]["writes"] == [] and path["publish"]["touches"] == ["outbox"]
        assert path["answer_directly"]["touches"] == ["web"]
        assert path["draft"]["hands_on"] == "Reply"

    def test_the_evaluation_joins_onto_the_steps_it_measured(self) -> None:
        data = shape("branching")
        held = self.steps()
        assert data["measured"]["headline"]["name"] == "accuracy"
        assert data["measured"]["headline"]["low"] is not None
        assert held["classify"]["measured"]["accuracy"]["point"] == 1.0
        assert held["answer_directly"]["measured"]["paid_tool_calls"] == 1
        assert data["coverage"]["never_reached"] == ["apologise"]
        assert data["coverage"]["scored"] == ["classify"]
        assert data["coverage"]["unmeasured_pipelines"] == ["reindex"]

    def test_the_floor_travels_with_the_figure(self) -> None:
        data = shape("branching")
        assert data["measured"]["floor"] == {"right": 0, "of": 4}
        assert "Its declared baseline scored 0 of 4" in data["standing"]

    def test_what_the_evaluation_left_alone_reaches_the_findings(self) -> None:
        heads = [f["head"] for f in shape("branching")["findings"]]
        assert "apologise: unreached by the evaluation." in heads
        assert "reindex: unmeasured." in heads

    def test_an_undirected_touch_says_why_it_is_undirected(self) -> None:
        bodies = {f["head"]: f["body"] for f in shape("branching")["findings"]}
        assert "A paid call may read or write" in bodies["web: direction undeclared."]
        assert (
            "declares a direction"
            in {f["head"]: f["body"] for f in shape("batch")["findings"]}[
                "digest_store: direction undeclared."
            ]
        )

    def test_a_recorded_access_settles_a_direction_touches_never_carried(self) -> None:
        """`touches=` says a step reaches a store; the access says which way it went."""
        held = shape("branching")
        outbox = next(r for r in held["resources"] if r["name"] == "outbox")
        heads = {f["head"] for f in held["findings"]}

        assert outbox["writers"] == ["triage/publish"]
        assert outbox["unknown"] == []
        assert outbox["direction_from_runs"] == ["triage/publish"]
        assert "outbox: direction undeclared." not in heads


class TestWhatTheViewCallsARightAnswer:
    """The view's counts and the report's accuracy read the same outcomes.

    Found 2026-08-28 in `P3-52`'s seventh reverification cycle. The view held its own list of
    right outcomes, `{"correct", "correct_absent", "right_abstention"}`, and the outcomes are
    `correct` and `correct_abstention`. So a right report of absence counted as wrong on the
    agent's line and on the floor's: measured on three rollouts whose report said accuracy
    100%, the view said 1 of 3, and a floor of two right abstentions said 0 of 3. The whole
    suite was green. It reads `Outcome.succeeded` now, so the two cannot part again.
    """

    @staticmethod
    def _entries(*outcomes: str) -> dict:
        return {
            "rollouts": [{"outcome": o, "example_id": f"e{i}"} for i, o in enumerate(outcomes)],
            "baseline": [{"outcome": o, "example_id": f"e{i}"} for i, o in enumerate(outcomes)],
        }

    def test_a_right_report_of_absence_counts_as_right(self) -> None:
        from simple_agents.view.evaluation import _floor, _rollout_counts

        raw = self._entries("correct", "correct_abstention", "correct_abstention")

        assert _rollout_counts(raw) == {"right": 3, "of": 3}
        assert _floor(raw) == {"right": 3, "of": 3}

    def test_every_outcome_the_library_has_is_sorted_the_way_it_sorts_it(self) -> None:
        """The list this replaced named two outcomes that do not exist and missed one that does."""
        from simple_agents.evaluation import Outcome
        from simple_agents.view.evaluation import _is_right

        for outcome in Outcome:
            assert _is_right(outcome.value) is outcome.succeeded

    def test_an_outcome_this_version_does_not_know_is_not_right(self) -> None:
        from simple_agents.view.evaluation import _is_right

        assert _is_right("some_later_outcome") is False
        assert _is_right("") is False

    def test_an_example_that_abstained_rightly_is_not_listed_as_gone_wrong(self) -> None:
        from simple_agents.view.evaluation import _went_wrong

        raw = self._entries("correct_abstention", "missed")

        assert [e["example"] for e in _went_wrong(raw)] == ["e1"]


class TestReadingAnEvaluation:
    def test_a_project_with_no_results_directory_has_no_section(self) -> None:
        from simple_agents.view.evaluation import read_evaluation

        assert read_evaluation(FIXTURES / "mid-build") is None

    def test_a_file_from_an_older_format_still_renders_and_says_so(self, tmp_path) -> None:
        from simple_agents.view.evaluation import read_evaluation

        results = tmp_path / "evals" / "results"
        results.mkdir(parents=True)
        (results / "old.json").write_text(
            json.dumps(
                {
                    "eval_format_version": "0.1",
                    "eval_id": "old",
                    "created_at": "2026-01-01T00:00:00Z",
                    "config": {"split": "held_out", "k": 1, "n": 2},
                    "metrics": {
                        "accuracy": {
                            "definition": "d",
                            "population": "all rollouts",
                            "unit": "rate",
                            "rollouts": 2,
                            "examples": 2,
                            "interval": {"point": 0.5, "low": 0.1, "high": 0.9},
                        }
                    },
                }
            )
        )
        held = read_evaluation(tmp_path)
        assert held["headline"]["point"] == 0.5
        assert "evaluation format 0.1" in held["problems"][0]

    def test_reporting_an_older_file_than_the_newest_is_a_finding(self, tmp_path) -> None:
        import shutil

        root = tmp_path / "project"
        shutil.copytree(FIXTURES / "branching", root)
        newer = json.loads((root / "evals/results/held-out.json").read_text())
        newer["created_at"] = "2027-01-01T00:00:00Z"
        newer["eval_id"] = "later"
        (root / "evals/results/later.json").write_text(json.dumps(newer))
        # The fixture's brief already names held-out.json as the one it reports.
        assert 'results = "evals/results/held-out.json"' in (root / "brief.toml").read_text()
        heads = [f["head"] for f in assemble(root)["findings"]]
        assert "The evaluation this project reports is not the most recent one." in heads


class TestWhatAnEvaluationLeavesUnderRuns:
    """An evaluation writes a directory per rollout, one level below the project's own runs.

    `runs("runs/")` stops at the top level, so the page's per-shape figures are the project's
    own runs. Saying nothing about the rest would leave the page reporting one run where the
    gate reports seven.
    """

    def test_rollouts_are_counted_apart_from_the_project_s_own_runs(self) -> None:
        data = shape("branching")
        [triage] = [p for p in data["pipelines"] if p["name"] == "triage"]
        assert triage["runs"]["runs"] == 2
        assert data["rollouts"]["runs"] == 32
        # Four evaluations left rollouts: the reported one, the rung, and the sweep's two arms.
        assert len(data["rollouts"]["evaluations"]) == 4
        evaluation = data["measured"]["eval_id"]
        assert evaluation in data["rollouts"]["evaluations"]
        assert evaluation.startswith("eval_")

    def test_a_project_that_never_evaluated_has_none(self) -> None:
        assert shape("one-pipeline")["rollouts"] == {"runs": 0, "evaluations": []}


class TestHowMuchDataMoved:
    """What a step received and produced, counted.

    A slice of a payload written out is not the data side: 220 characters of a 40-item list
    is 220 characters of the first item. `DF5-N3`'s complaint was about a step that ranked a
    catalogue and truncated it, and what makes that visible is the count.
    """

    def test_a_list_is_its_length(self) -> None:
        from simple_agents.view.runs_overlay import _volume

        assert _volume([1, 2, 3]) == "3 items"
        assert _volume({"pool": list(range(40)), "survey": list(range(2000))}) == (
            "survey 2,000 · pool 40"
        )

    def test_a_record_of_scalars_names_its_longest_text(self) -> None:
        from simple_agents.view.runs_overlay import _volume

        assert _volume({"ticket": "x" * 74, "seen": True}) == "ticket 74 characters"

    def test_a_join_counts_the_edges_that_fired(self) -> None:
        from simple_agents.view.runs_overlay import _volume

        held = _volume(
            {
                "type": "join",
                "edges": {
                    "critique": {"items": [1, 2]},
                    "escalate": {"type": "unknown", "reason": "skipped"},
                    "apologise": {"type": "unknown", "reason": "skipped"},
                },
            }
        )
        assert held == "critique items 2 · 2 edges did not fire"

    def test_a_record_of_many_fields_shows_the_ones_that_hold_a_count(self) -> None:
        """Truncating in declaration order is what hides the field the step is about."""
        from simple_agents.view.runs_overlay import _shape

        value = {f"f{i}": "x" for i in range(16)}
        value["pool"] = list(range(40))
        assert "pool" in _shape(value)["fields"]

    def test_the_volumes_reach_the_steps_and_the_path(self) -> None:
        data = shape("branching")
        triage = next(p for p in data["pipelines"] if p["name"] == "triage")
        steps = {n["id"]: n for n in triage["nodes"]}
        assert steps["classify"]["example"]["took_in_volume"] == "ticket 72 characters"
        assert steps["classify"]["example"]["handed_on_volume"].startswith("questions ")
        path = {row["id"]: row for row in triage["data_path"]}
        assert path["research.read_source"]["took_in_volume"] == "sources 2"
        assert path["answer_directly"]["took_in_volume"] is None

    def test_the_shape_of_what_arrived_travels_with_it(self) -> None:
        data = shape("branching")
        triage = next(p for p in data["pipelines"] if p["name"] == "triage")
        steps = {n["id"]: n for n in triage["nodes"]}
        held = steps["research.pick_sources"]["example"]["handed_on_shape"]
        assert held["kind"] == "record"
        sources = held["fields"]["sources"]
        assert (sources["kind"], sources["count"]) == ("list", 2)
        assert sources["of"]["kind"] == "list"
        assert sources["of"]["of"]["kind"] == "text"


class TestTheDataItIsMeasuredOn:
    def test_the_splits_and_the_fields_are_counted(self) -> None:
        held = shape("branching")["examples"]
        assert held["total"] == 6
        assert held["splits"] == {"dev": 2, "held_out": 4}
        assert held["fields"] == ["ticket"]
        assert held["labelled_steps"] == ["classify", "intake"]

    def test_the_worked_example_comes_from_an_inspectable_split(self) -> None:
        """Held-out examples remain reserved for evaluation (FT-02)."""
        held = shape("branching")["examples"]
        assert held["worked"]["split"] == "dev"
        assert held["worked"]["inputs"][0]["key"] == "ticket"

    def test_a_set_that_is_all_held_out_shows_none_of_it(self, tmp_path) -> None:
        from simple_agents.view.examples import read_examples

        (tmp_path / "evals").mkdir()
        (tmp_path / "evals" / "examples.jsonl").write_text(
            json.dumps({"id": "a", "inputs": {"q": "x"}, "expected": "y", "split": "held_out"})
            + "\n"
        )
        held = read_examples(tmp_path)
        assert held["total"] == 1 and held["worked"] is None

    def test_an_absent_answer_is_counted_per_split(self, tmp_path) -> None:
        from simple_agents.view.examples import read_examples

        (tmp_path / "evals").mkdir()
        (tmp_path / "evals" / "examples.jsonl").write_text(
            "\n".join(
                json.dumps(row)
                for row in [
                    {"id": "a", "inputs": {"q": "x"}, "expected": "y", "split": "held_out"},
                    {
                        "id": "b",
                        "inputs": {"q": "x"},
                        "expected": {"type": "unknown", "reason": "not there"},
                        "split": "held_out",
                    },
                ]
            )
        )
        assert read_examples(tmp_path)["absent"] == {"held_out": 1}

    def test_a_project_with_no_example_set_has_none(self) -> None:
        assert shape("mid-build")["examples"] is None


class TestAResourceCard:
    def test_a_resource_names_the_tools_that_reach_it(self) -> None:
        data = shape("branching")
        handbook = next(r for r in data["resources"] if r["name"] == "handbook")
        through = {t["name"]: t for t in handbook["through"]}
        assert set(through) == {"handbook_lookup", "store_passage"}
        assert through["store_passage"]["effect"] == "writes"
        assert through["store_passage"]["used_by"] == ["reindex/file_them"]
        assert "Write one passage" in through["store_passage"]["description"]

    def test_a_resource_only_a_step_touches_names_no_tool(self) -> None:
        data = shape("branching")
        outbox = next(r for r in data["resources"] if r["name"] == "outbox")
        assert outbox["through"] == []


class TestWhatWasSaidAgainstWhatTheCodeDoes:
    """The brief and the code, joined on a step's name.

    `DF5-D7`: a brief naming two steps that decide for themselves, over a pipeline holding
    none, passed 21 gate runs across 116 commits. Both halves were already on the page and
    nothing compared them.
    """

    def test_an_answer_naming_a_step_the_code_disagrees_about(self) -> None:
        data = shape("mid-build")
        agency = next(c for c in data["claims"] if c["entry"] == "agency_boundary")
        assert agency["names"] == ["judge_books"]
        assert agency["named_but_not"] == ["judge_books"]
        assert agency["in_code"] == []
        assert agency["kinds"]["judge_books"] == "model call"

    def test_the_disagreement_leads_the_findings(self) -> None:
        from simple_agents.view.claims import title_of

        urgent = [f for f in shape("mid-build")["findings"] if f["severity"] == "attention"]
        held = next(f for f in urgent if title_of("agency_boundary") in f["head"])
        assert "judge_books is a model call" in held["body"]
        assert "Steps that do: none." in held["body"]

    def test_an_answer_the_code_agrees_with_is_not_a_finding(self) -> None:
        from simple_agents.view.claims import title_of

        data = shape("branching")
        agency = next(c for c in data["claims"] if c["entry"] == "agency_boundary")
        assert agency["named_but_not"] == [] and agency["in_code_but_unnamed"] == []
        assert not any(
            f["head"].startswith(f"{title_of('agency_boundary')}:") for f in data["findings"]
        )

    def test_an_answer_naming_no_step_says_so_rather_than_disagreeing(self) -> None:
        from simple_agents.view.claims import title_of

        data = shape("branching")
        effects = next(c for c in data["claims"] if c["entry"] == "tool_effects")
        # `answer_directly` pays for a web search and `file_them` writes the handbook; the
        # question asks about both, and the answer names neither.
        assert effects["names"] == []
        assert effects["in_code"] == ["answer_directly", "file_them"]
        heads = [f["head"] for f in data["findings"]]
        said = f"{title_of('tool_effects')}:"
        assert any(h.startswith(said) and "names no step" in h for h in heads)

    def test_what_waits_on_the_builder_leads_and_says_what_to_do(self) -> None:
        """A fact about the design is not a task, and one heading over both taught a reader
        to skip the count: `branching` reported eight items needing attention, and none of
        the eight was anything to do."""
        data = shape("many-pipelines")
        waiting = [f for f in data["findings"] if f.get("waits")]
        assert waiting, "a project with unanswered questions has something waiting"
        assert data["findings"][: len(waiting)] == waiting
        assert all(f["waits"] for f in waiting)

    def test_a_finished_project_is_waiting_on_nobody(
        self,
    ) -> None:
        assert not [f for f in shape("branching")["findings"] if f.get("waits")]

    def test_a_question_is_named_for_the_builder_in_every_sentence(self) -> None:
        """A finding headed `agency_boundary` names the library's vocabulary, not the
        project's. The brief key stays the address a comment is filed under."""
        heads = [f["head"] for f in shape("mid-build")["findings"]]
        assert not any(h.startswith("agency_boundary") for h in heads)
        assert any(h.startswith("What the agent works out for itself") for h in heads)

    def test_a_brief_answering_none_of_the_checked_questions_has_no_claims(self) -> None:
        """Only an answered entry is compared: an unanswered one is the gate's business."""
        assert shape("one-pipeline")["claims"] == []
        from simple_agents.view.claims import read_claims

        assert read_claims([], None, {}) == []


class TestTheSeamsTheShapeSettles:
    """The four answers the `shape` gate settles, read off the code and the brief together.

    `P3-61`. Each row carries what the code has, what was answered about it, and the two
    differences between them; the `shape` page draws it and the story marks the same seams on
    each step.
    """

    def seam(self, project: str, entry: str) -> dict:
        return next(s for s in shape(project)["seams"] if s["entry"] == entry)

    def test_the_four_are_the_four_the_gate_settles(self) -> None:
        assert [s["entry"] for s in shape("skeleton")["seams"]] == [
            "agency_boundary",
            "consultation",
            "tool_effects",
            "used_through",
        ]

    def test_a_row_names_the_steps_and_how_each_one_holds_the_seam(self) -> None:
        asks = self.seam("skeleton", "consultation")
        held = asks["parts"][0]
        assert [s["id"] for s in held["steps"]] == ["answer_directly", "publish"]
        assert held["steps"][0]["through"] == ["consult"]
        assert held["steps"][0]["answered_by"] == ["end_user"]

    def test_one_answer_covering_two_things_reads_them_apart(self) -> None:
        """`tool_effects` covers spending and writing somewhere permanent, so the row holds
        both, each with its own steps."""
        effects = self.seam("skeleton", "tool_effects")
        spends, permanent = effects["parts"]
        assert [s["id"] for s in spends["steps"]] == ["answer_directly"]
        assert spends["steps"][0]["through"] == ["web_search"]
        assert [s["id"] for s in permanent["steps"]] == ["file_them"]
        assert permanent["steps"][0]["through"] == ["store_passage"]

    def test_the_entry_point_has_no_code_side(self) -> None:
        """No code declares what the end user opens, so the row carries the answer alone."""
        entry = self.seam("skeleton", "used_through")
        assert entry["reads_code"] is False and entry["parts"] == []
        assert "A script the support inbox calls" in entry["answer"]

    def test_a_seam_the_brief_promises_and_the_code_lacks_is_carried(self) -> None:
        """The loud one: the answer says a step decides for itself and the code says it is a
        model call."""
        agency = self.seam("mid-build", "agency_boundary")
        assert agency["named_but_not"] == ["judge_books"]

    def test_a_seam_nobody_answered_says_which_question_settles_it(self) -> None:
        effects = self.seam("skeleton", "tool_effects")
        assert effects["status"] == "unanswered" and effects["answer"] == ""
        assert effects["asked"] == "What it may do outside the run"

    def test_a_project_with_no_brief_still_gets_every_row(self) -> None:
        """The rows are what the gate asks, so they exist before anything answers them."""
        from simple_agents.view.claims import read_seams

        rows = read_seams([], None, [])
        assert len(rows) == 4
        assert all(r["status"] == "unanswered" for r in rows)


class TestTheStoryEachStepTells:
    """What a step is for and the seams it holds, on the data path's own rows (`P3-61`)."""

    def rows(self, project: str) -> dict:
        path = shape(project)["pipelines"][0]["data_path"]
        return {r["id"]: r for r in path}

    def test_a_step_not_built_yet_carries_the_words_its_marker_was_given(self) -> None:
        held = self.rows("skeleton")["intake"]
        assert held["intent"] == "takes one open ticket off the support inbox"

    def test_a_built_step_carries_the_first_line_of_its_own_docstring(self) -> None:
        held = self.rows("branching")["intake"]
        assert held["intent"] and "ticket" in held["intent"].lower()

    def test_every_seam_a_step_holds_is_on_its_row(self) -> None:
        held = self.rows("skeleton")["answer_directly"]
        assert [s["kind"] for s in held["seams"]] == ["decides", "asks", "spends", "touches"]
        assert held["seams"][3]["name"] == "web"

    def test_a_bound_loop_and_a_route_are_both_seams(self) -> None:
        held = self.rows("skeleton")["critique"]
        assert [s["kind"] for s in held["seams"]] == ["branches", "loops"]
        assert held["seams"][1]["words"] == "Loops back up to 2×"

    def test_a_step_that_only_reads_holds_no_seam(self) -> None:
        """A read changes nothing outside the run, so it is not a seam."""
        assert self.rows("skeleton")["research.pick_sources"]["seams"] == []


class TestDeclaringTheProduct:
    """`Product`, `Surface` and `product_factory` (`P3-56`).

    Nothing in a run reaches the surface the end user meets, so introspection cannot find it.
    This is the declaration that puts it on the page, and the refusals that keep a declaration
    from saying nothing.
    """

    def test_a_surface_says_what_kind_of_interaction_it_is(self) -> None:
        from simple_agents import Surface

        held = Surface(
            "the rota",
            "answers_a_waiting_run",
            pipeline="triage",
            through="consult",
            does="the rota answers when the agent asks",
        )
        assert held.kind_words == "Answers a waiting run"
        assert held.reaches_the_agent

    def test_a_surface_that_only_shows_stored_output_says_so(self) -> None:
        from simple_agents import Surface

        assert not Surface("the outbox", "reads_the_artifact", reads="outbox").reaches_the_agent

    def test_a_kind_outside_the_four_is_refused_naming_them(self) -> None:
        from simple_agents import ConfigurationError, Surface

        with pytest.raises(ConfigurationError, match="reads_the_artifact"):
            Surface("the outbox", "shows_a_thing")

    def test_a_kind_whose_required_name_is_missing_is_refused_naming_the_field(self) -> None:
        from simple_agents import ConfigurationError, Surface

        with pytest.raises(ConfigurationError, match="names no pipeline"):
            Surface("the inbox", "starts_a_run")
        with pytest.raises(ConfigurationError, match="names no reads"):
            Surface("the outbox", "reads_the_artifact")

    def test_two_surfaces_under_one_name_are_refused(self) -> None:
        from simple_agents import ConfigurationError, Product, Surface

        with pytest.raises(ConfigurationError, match="more than once"):
            Product(
                surfaces=[
                    Surface("the inbox", "starts_a_run", pipeline="one"),
                    Surface("the inbox", "starts_a_run", pipeline="two"),
                ]
            )

    def test_a_job_says_which_pipeline_it_runs_and_what_it_follows(self) -> None:
        from simple_agents import Job, Product

        nightly = Job("nightly", pipeline="reconcile", does="every night at 02:00")
        close = Job("close", pipeline="reconcile", after="nightly")
        held = Product(jobs=[nightly, close])
        assert nightly.kind_words == "Job" and close.kind_words == "Job · after nightly"
        assert held.job("close") is close and held.job("weekly") is None

    def test_a_job_with_no_name_or_no_pipeline_is_refused(self) -> None:
        from simple_agents import ConfigurationError, Job

        with pytest.raises(ConfigurationError, match="no name"):
            Job("", pipeline="reconcile")
        with pytest.raises(ConfigurationError, match="names no pipeline"):
            Job("nightly", pipeline="")

    def test_a_job_following_a_job_the_product_does_not_declare_is_refused(self) -> None:
        from simple_agents import ConfigurationError, Job, Product

        with pytest.raises(ConfigurationError, match="declares no job of that name"):
            Product(jobs=[Job("close", pipeline="reconcile", after="nightly")])
        with pytest.raises(ConfigurationError, match="itself"):
            Job("close", pipeline="reconcile", after="close")

    def test_two_jobs_under_one_name_are_refused(self) -> None:
        """A run records the job's name as its trigger, so one name names one job."""
        from simple_agents import ConfigurationError, Job, Product

        with pytest.raises(ConfigurationError, match="more than once"):
            Product(jobs=[Job("nightly", pipeline="a"), Job("nightly", pipeline="b")])

    def test_a_second_product_is_refused(self) -> None:
        from simple_agents import ConfigurationError, Product, product_factory
        from simple_agents.product import clear_registered_product

        clear_registered_product()
        try:

            @product_factory
            def one() -> Product:
                return Product()

            with pytest.raises(ConfigurationError, match="one product"):

                @product_factory
                def two() -> Product:
                    return Product()
        finally:
            clear_registered_product()


class TestTheProductOnThePage:
    """The declaration joined to the code, which is what the `ship` page draws."""

    def product(self, name: str = "shipped") -> dict:
        return shape(name)["product"]

    def test_every_surface_joins_to_what_it_names(self) -> None:
        held = {s["name"]: s for s in self.product()["surfaces"]}
        assert held["the finance inbox"]["pipeline"] == "claims"
        assert held["the finance desk"]["channel"]["at"] == ["claims/finance"]
        assert held["the finance desk"]["channel"]["answered_by"] == ["end_user"]
        assert held["the ledger"]["writers"] == ["claims/book"]
        assert all(not s["missing"] for s in self.product()["surfaces"])

    def test_a_channel_answered_by_a_stand_in_is_marked(self) -> None:
        """FT-31's own rule, read from the check rather than restated."""
        from simple_agents.view.product import _stand_in

        assert not _stand_in(["end_user"]) and not _stand_in(["nobody"])
        assert _stand_in(["coding_agent"]) and _stand_in(["simulated"])

    def test_the_parameters_are_the_declaring_modules_own(self) -> None:
        held = self.product()
        assert held["declared_in"] == "surface"
        assert [p["name"] for p in held["parameters"]] == [
            "CLAIMS_PER_PAGE",
            "REASON_CHARS",
            "STALE_AFTER_HOURS",
        ]

    def test_a_job_joins_to_the_pipeline_it_runs(self) -> None:
        held = {j["name"]: j for j in self.product()["jobs"]}
        assert held["nightly reconcile"]["pipeline"] == "reconcile"
        assert held["nightly reconcile"]["after"] is None
        assert held["month-end close"]["after"] == "nightly reconcile"
        assert held["month-end close"]["kind_words"] == "Job · after nightly reconcile"
        assert all(not j["missing"] for j in held.values())

    def test_a_job_naming_a_pipeline_the_code_does_not_register_is_reported(self) -> None:
        from simple_agents import Job
        from simple_agents.view.product import _one_job

        held = _one_job(Job("nightly", pipeline="reconcil"), [{"name": "reconcile"}])
        assert held["pipeline"] is None and held["pipeline_named"] == "reconcil"
        assert held["missing"] == ["no pipeline is registered as reconcil"]

    def test_a_project_declaring_none_has_none(self) -> None:
        assert shape("measured")["product"] is None

    def test_loading_a_project_twice_finds_its_product_twice(self) -> None:
        """A module Python has imported does not run again, so a registration in a module
        beside `agent.py` happened on the first load and on no later one. The page and the
        checks both load a project in one process."""
        from simple_agents.view.discovery import load_project

        root = FIXTURES / "shipped"
        assert load_project(root).product is not None
        assert load_project(root).product is not None

    def test_a_project_holding_its_own_environment_keeps_the_library_imported(
        self, tmp_path: Path
    ) -> None:
        """`uv` writes the environment to `<project>/.venv`, which puts every installed
        package under the project root. Forgetting those unimports the library itself: the
        registry the project just registered into is replaced, so a second load declares
        nothing, and every exception class gains a second identity, so `except` stops
        matching. Measured against dogfood #6 on 2026-09-01: three pipelines on the first
        load and none on any after it."""
        import sys

        from simple_agents.view.discovery import load_project

        project = tmp_path / "project"
        installed = project / ".venv" / "lib" / "python3.13" / "site-packages" / "stand_in"
        installed.mkdir(parents=True)
        (installed / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
        (project / "beside.py").write_text(
            "from simple_agents import Budget, Deterministic, Pipeline, pipeline_factory\n"
            "def step(inputs, ctx):\n"
            "    return inputs\n"
            "@pipeline_factory('only')\n"
            "def build():\n"
            "    return Pipeline(\n"
            "        [Deterministic(step, node_id='step')],\n"
            "        budget=Budget(1, None, None, None),\n"
            "    )\n",
            encoding="utf-8",
        )
        (project / "agent.py").write_text("import beside  # noqa: F401\n", encoding="utf-8")

        sys.path.insert(0, str(installed.parent))
        try:
            import stand_in  # type: ignore[import-not-found]

            first = load_project(project)
            assert list(first.pipelines) == ["only"], first.problems
            assert sys.modules.get("stand_in") is stand_in
            assert "simple_agents.errors" in sys.modules
            assert "beside" not in sys.modules
            second = load_project(project)
            assert list(second.pipelines) == ["only"], second.problems
        finally:
            sys.path.remove(str(installed.parent))
            sys.modules.pop("stand_in", None)


class TestWhatARunDidWrong:
    def test_how_each_step_ended_reaches_its_card(self) -> None:
        data = shape("branching")
        triage = next(p for p in data["pipelines"] if p["name"] == "triage")
        steps = {n["id"]: n for n in triage["nodes"]}
        assert steps["apologise"]["ran"]["ended"] == {"skipped": 1}
        assert steps["publish"]["ran"]["ended"] == {}

    def test_runs_that_did_not_complete_are_one_sentence_for_the_project(self, tmp_path) -> None:
        """One per shape is eighteen sentences on a real project, which goes unread."""
        import shutil

        root = tmp_path / "p"
        shutil.copytree(FIXTURES / "branching", root)
        for manifest in root.glob("runs/dev/*/run_*/manifest.json"):
            held = json.loads(manifest.read_text())
            held["outcome"] = "error"
            manifest.write_text(json.dumps(held))
        heads = [f["head"] for f in assemble(root)["findings"]]
        assert "2 runs of 2 did not complete." in heads

    def test_a_failure_path_that_fired_is_named(self, tmp_path) -> None:
        import shutil

        root = tmp_path / "p"
        shutil.copytree(FIXTURES / "branching", root)
        newest = sorted(root.glob("runs/dev/*/run_*/trajectory.jsonl"))[-1]
        rows = []
        for line in newest.read_text().splitlines():
            record = json.loads(line)
            if record.get("node_id") == "apologise":
                record["termination"] = None
            rows.append(json.dumps(record))
        newest.write_text("\n".join(rows) + "\n")
        heads = [f["head"] for f in assemble(root)["findings"]]
        assert "The failure path into apologise fired in the last run." in heads


class TestWhatTheAgentAskedAPerson:
    def test_the_question_and_the_answer_reach_the_page(self) -> None:
        data = shape("branching")
        [question] = data["asked"]
        assert question["asked_by"] == "publish"
        assert question["resolution"] == "answered"
        assert question["chose"] == "send it"
        assert question["options"] == ["send it", "hold it for me"]
        assert question["blocking"] is True

    def test_the_step_that_asked_carries_it(self) -> None:
        triage = next(p for p in shape("branching")["pipelines"] if p["name"] == "triage")
        steps = {n["id"]: n for n in triage["nodes"]}
        assert len(steps["publish"]["asked"]) == 1
        assert steps["classify"]["asked"] == []

    def test_a_question_nobody_answered_is_a_finding(self, tmp_path) -> None:
        import shutil

        root = tmp_path / "p"
        shutil.copytree(FIXTURES / "branching", root)
        newest = sorted(root.glob("runs/dev/*/run_*/trajectory.jsonl"))[-1]
        rows = []
        for line in newest.read_text().splitlines():
            record = json.loads(line)
            if record.get("record_type") == "consultation":
                record["resolution"] = "unavailable"
                record["response"] = None
                record["reason"] = "the run was unattended"
            rows.append(json.dumps(record))
        newest.write_text("\n".join(rows) + "\n")
        heads = [f["head"] for f in assemble(root)["findings"]]
        assert "A question the last run asked came back without an answer." in heads


class TestWhatMovedBetweenTwoRuns:
    def test_a_step_that_produced_a_different_amount(self) -> None:
        moved = shape("branching")["moved"]["triage"]
        assert any(
            "intake produced ticket 72 characters; the previous run produced ticket 74 "
            "characters." == line
            for line in moved
        )

    def test_a_step_whose_time_moved(self, tmp_path) -> None:
        """Two live recordings of one shape can take the same time to the millisecond, so
        the movement is made: the newest run's classify is given thirty seconds more."""
        import shutil
        from datetime import datetime, timedelta

        root = tmp_path / "p"
        shutil.copytree(FIXTURES / "branching", root)
        newest = sorted(root.glob("runs/dev/*/run_*/trajectory.jsonl"))[-1]
        rows = []
        for line in newest.read_text().splitlines():
            record = json.loads(line)
            if (
                record.get("record_type") == "node_execution"
                and record.get("node_id") == "classify"
            ):
                ended = datetime.fromisoformat(record["ended_at"].replace("Z", "+00:00"))
                record["ended_at"] = (
                    (ended + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
                )
            rows.append(json.dumps(record))
        newest.write_text("\n".join(rows) + "\n")
        moved = assemble(root)["moved"]["triage"]
        assert any("slower than" in line or "faster than" in line for line in moved), moved

    def test_a_pipeline_with_one_run_has_nothing_to_compare(self) -> None:
        assert shape("one-pipeline")["moved"] == {}


class TestAFigureWithNoInterval:
    """The page renders what the results file holds, and a census has a number and no interval.

    `_figure` read the point off the interval, so a count over the run reached the page as
    absent. Filling it in then exposed the second half: at the default unit the page drew it as
    a percentage with a 0-to-100 bar.
    """

    def _read(self, tmp_path, **declared):
        from simple_agents.evaluation import ProjectRatio
        from simple_agents.evaluation.metrics import aggregate
        from simple_agents.evaluation.outcomes import Outcome, RolloutOutcome
        from simple_agents.evaluation.results import EvalResults
        from simple_agents.view.evaluation import read_evaluation

        figure = ProjectRatio(name="counted", definition="d", numerator=lambda s: 0, **declared)
        rollouts = tuple(
            RolloutOutcome(
                example_id=e, rollout=0, seed=0, outcome=Outcome.CORRECT, ratios={"counted": (n, d)}
            )
            for e, n, d in [("a", 1, 10), ("b", 1, 2)]
        )
        results = EvalResults(
            eval_id="e",
            created_at="t",
            config={"n": 2, "k": 1},
            metrics=aggregate(rollouts, {"a": False, "b": False}, project=[figure], resamples=300),
            nodes={},
            rollouts=rollouts,
            examples={"a": {}, "b": {}},
        )
        root = tmp_path / "project"
        (root / "evals" / "results").mkdir(parents=True)
        results.write(root / "evals" / "results" / "held-out.json")
        got = read_evaluation(root)
        return {f["name"]: f for f in got["metrics"]}["counted"]

    def test_a_census_reaches_the_page_with_its_number(self, tmp_path) -> None:
        figure = self._read(tmp_path, no_interval="a count over this run")
        assert figure["point"] == 2.0
        assert figure["estimated"] is False
        assert figure["reason"] == "a count over this run"

    def test_a_ratio_reaches_the_page_with_both_totals(self, tmp_path) -> None:
        figure = self._read(tmp_path, denominator=lambda s: 0)
        assert (figure["numerator"], figure["denominator"]) == (2, 12)
        assert figure["estimated"] is True
        assert figure["point"] == pytest.approx(2 / 12)


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


class TestWhatALiveProjectIsDoing:
    """The six records a live project leaves behind, which the page read none of (`P3-57`)."""

    def held(self, name: str = "shipped") -> dict:
        from simple_agents.view.operating import read_operating

        return read_operating(FIXTURES / name)

    def test_a_project_with_no_live_run_has_none_of_this(self) -> None:
        """The figures are what real traffic did, and a development run is not that."""
        assert self.held("measured") is None
        assert self.held("branching") is None

    def test_a_suspension_says_what_it_waits_for_and_whether_a_clock_or_a_person(self) -> None:
        stuck = {one["waiting_for"]: one for one in self.held()["stuck"] if one["waiting_for"]}
        person = stuck["the finance desk to confirm the August write-off"]
        assert person["on"] == "a person" and person["until"] is None
        assert person["options"] == ["write it off", "chase it"]
        clock = stuck["the month to close"]
        assert clock["on"] == "a clock" and clock["until"] == "2026-09-01T09:00:00Z"

    def test_each_declared_job_reads_what_its_runs_did(self) -> None:
        """The runs that name a job as their trigger, joined to the declaration."""
        from simple_agents.view.discovery import load_project
        from simple_agents.view.operating import read_operating

        loaded = load_project(FIXTURES / "shipped")
        jobs = {j["name"]: j for j in read_operating(FIXTURES / "shipped", loaded.product)["jobs"]}
        nightly = jobs["nightly reconcile"]
        assert nightly["declared"] and nightly["pipeline"] == "reconcile"
        assert nightly["runs"] == 5 and nightly["waiting"] == 1 and nightly["shelved"] == 1
        assert nightly["on_clock"] == 1  # the month-to-close wait is a clock, not a person
        assert nightly["ended"] == "finished" and nightly["ago"]
        close = jobs["month-end close"]
        assert close["runs"] == 2 and close["after"] == "nightly reconcile"

    def test_a_trigger_no_job_declares_is_listed_and_marked(self) -> None:
        """The killed run names a job the product never declared."""
        from simple_agents.view.discovery import load_project
        from simple_agents.view.operating import read_operating

        loaded = load_project(FIXTURES / "shipped")
        jobs = {j["name"]: j for j in read_operating(FIXTURES / "shipped", loaded.product)["jobs"]}
        weekly = jobs["weekly digest"]
        assert not weekly["declared"] and weekly["runs"] == 1 and weekly["does"] == ""
        assert weekly["ended"] in ("running", "abandoned", "unknown")

    def test_a_declared_job_with_no_run_says_so(self, tmp_path: Path) -> None:
        from simple_agents import Job, Product
        from simple_agents.view.operating import _jobs

        held = _jobs([], Product(jobs=[Job("nightly", pipeline="x")]), [], [], _now())
        assert held == [
            {
                "name": "nightly",
                "declared": True,
                "pipeline": "x",
                "does": "",
                "after": None,
                "runs": 0,
                "last": None,
                "ago": "",
                "ended": "",
                "waiting": 0,
                "on_clock": 0,
                "shelved": 0,
            }
        ]

    def test_without_a_product_the_jobs_are_the_triggers_the_runs_recorded(self) -> None:
        """A project declaring no product still has runs saying what started them."""
        jobs = {j["name"]: j for j in self.held()["jobs"]}
        assert set(jobs) == {"nightly reconcile", "month-end close", "weekly digest"}
        assert not any(j["declared"] for j in jobs.values())

    def test_a_shelved_question_carries_why_nobody_answered_it(self) -> None:
        held = self.held()["shelf"]
        assert len(held) == 1
        assert held[0]["about"] == "po-80115-unit"
        assert held[0]["reason"] == "the nightly run is unattended"

    def test_the_day_is_counted_by_how_its_runs_ended(self) -> None:
        day = self.held()["history"][-1]
        assert day["finished"] and day["failed"] and day["stopped"]
        assert day["runs"] == day["finished"] + day["failed"] + day["stopped"]

    def test_a_call_that_ended_throttled_is_counted(self) -> None:
        """A throttle the library waited out and then succeeded leaves no record; what is
        counted is a call whose attempts were spent."""
        assert sum(d["throttled"] for d in self.held()["history"]) == 1

    def test_a_behaviour_change_is_read_within_one_graph(self) -> None:
        """Two pipelines have two behaviours, and reading a switch between them as a change
        would report one on every day a project runs both."""
        changes = self.held()["changes"]
        assert len(changes) == 1
        assert len({c["graph"] for c in changes}) == 1

    def test_the_runs_are_counted_by_what_each_was_for(self) -> None:
        roles = {one["role"]: one for one in self.held()["roles"]}
        assert set(roles) == {"live", "development", "evaluation"}
        assert roles["evaluation"]["runs"] > roles["live"]["runs"] > roles["development"]["runs"]

    def test_a_run_with_no_outcome_is_running_or_abandoned_and_never_both(self) -> None:
        """`liveness` is derived from the clock, so a fixture read minutes after it is built
        reads `running` and the same one read an hour later reads `abandoned`."""
        now = self.held()["now"]
        assert now["running"] + now["abandoned"] + now["unknown"] == 1


class TestTheStagingOfTheElicitation:
    """Which questions a stage asks, and which are still ahead (`P3-55`)."""

    def stages(self, project: str) -> dict:
        return shape(project)["stages_asked"]

    def test_a_question_a_later_stage_asks_is_not_open_here(self) -> None:
        """The brief has three states and the page needs four: an unanswered question
        and one not yet asked read the same in the record."""
        held = self.stages("brainstorming")
        assert held["brainstorm"]["open"] == 7
        assert all(row["state"] == "ahead" for row in held["shape"]["rows"])

    def test_a_deferred_entry_names_the_stage_it_moved_to(self) -> None:
        rows = {r["name"]: r for r in self.stages("brainstorming")["brainstorm"]["rows"]}
        assert rows["used_through"]["state"] == "deferred"
        assert rows["used_through"]["deferred_to"] == "shape"

    def test_each_stage_carries_answered_of_asked(self) -> None:
        held = self.stages("brainstorming")
        assert (held["brainstorm"]["answered"], held["brainstorm"]["asks"]) == (7, 15)
        assert held["research"]["answered"] == 0
        assert held["brainstorm"]["here"] and not held["research"]["reached"]

    def test_a_tier_without_measure_is_asked_nothing_of_it(self) -> None:
        assert "measure" not in self.stages("day-zero")

    def test_a_project_with_no_brief_has_no_staging(self) -> None:
        from simple_agents.view.elicitation import read_stages

        assert read_stages(None) is None


class TestTheResearchRecord:
    """`research.md`'s survey, read back as the page draws it (`P3-55`)."""

    def held(self, project: str = "shipped") -> dict:
        return shape(project)["research"]

    def test_the_survey_is_grouped_by_the_part_it_names(self) -> None:
        parts = {p["part"]: p for p in self.held()["parts"]}
        assert set(parts) == {
            "Reading the fields",
            "Applying the policy",
            "Deciding",
            "Checking the supplier",
        }
        assert len(parts["Reading the fields"]["candidates"]) == 2

    def test_each_candidate_carries_what_became_of_it_and_why(self) -> None:
        parts = {p["part"]: p for p in self.held()["parts"]}
        adopted, unread = parts["Reading the fields"]["candidates"]
        assert adopted["outcome"] == "adopted"
        assert unread["outcome"] == "not_investigated"
        assert unread["said"] == "No claim in the archive has an image attached"

    def test_a_dependency_decision_joins_to_the_candidates_it_weighed(self) -> None:
        held = self.held()
        resting = {d["name"]: d for d in held["resting_on"]}
        assert set(resting) == {"the_supplier_registry"}
        assert resting["the_supplier_registry"]["cites"] == [
            "The approved-supplier registry",
            "A copy refreshed nightly",
        ]

    def test_the_deciding_factor_and_the_quotation_are_read_back(self) -> None:
        held = self.held()
        assert held["turns_on"].startswith("Whether the decision never approves")
        assert "The audit step is the one I would not drop" in held["said"]

    def test_a_project_with_no_research_file_has_none(self) -> None:
        assert self.held("brainstorming") is None
        assert self.held("measured") is None
