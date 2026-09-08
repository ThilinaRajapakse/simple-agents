"""The page's own script, executed, against every project shape the view has to serve.

Everything else about the view is asserted off ``assemble`` or by reading the rendered markup.
Neither can say whether the script runs. About 3,000 lines of it ship inside the wheel, and a
control that hid the one measure a project had went out under a green 3,353-test suite: the
markup was there to grep, and what the page *decided* was wrong.

``view_harness.mjs`` runs one rendered page under a DOM small enough to be read in one sitting,
then drives every control on it: each pipeline selected, each step opened, each store opened,
each measure and each population. It reports what was drawn. It is not a browser, so what it
establishes is that the page runs and what it chose; how it looks is still read by eye.

**These tests need `node` and skip without it**, the way the recorded-cassette tests skip
without their recording. CI installs it, so they run there on every commit.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from simple_agents.view import generate_view

HERE = Path(__file__).parent
HARNESS = HERE / "view_harness.mjs"
FIXTURES = HERE / "fixtures" / "view_projects"

SHAPES = (
    "day-zero",
    "skeleton",
    "measured",
    "mid-build",
    "one-pipeline",
    "many-pipelines",
    "batch",
    "branching",
    "prompted",
    "shipped",
    "brainstorming",
)


def node_or_skip() -> str:
    found = shutil.which("node")
    if found is None:
        pytest.skip("no node on PATH; install Node.js to run the view's own script")
    return found


def run(name: str, tmp_path: Path) -> dict:
    """One fixture rendered and run, or a failure carrying what the page threw."""
    node = node_or_skip()
    page = tmp_path / f"{name}.html"
    generate_view(FIXTURES / name, out=page)
    done = subprocess.run(
        [node, str(HARNESS), str(page)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if done.returncode != 0:
        pytest.fail(f"{name}: the page threw while rendering or being driven\n{done.stderr}")
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def pages(tmp_path_factory) -> dict[str, dict]:
    node_or_skip()
    out = tmp_path_factory.mktemp("pages")
    return {name: run(name, out) for name in SHAPES}


class TestEveryShapeRuns:
    @pytest.mark.parametrize("name", SHAPES)
    def test_it_renders_and_survives_every_control(self, name: str, pages) -> None:
        """Selected, opened, switched: the paths a builder takes in the first minute."""
        held = pages[name]
        assert held["pipelines_selected"] == [p["name"] for p in _declared(name)]
        assert held["after_every_control"]["graph_drawn"] or not _declared(name)

    @pytest.mark.parametrize("name", SHAPES)
    def test_the_sentence_at_the_top_is_written(self, name: str, pages) -> None:
        assert pages[name]["standing"].strip()


class TestThePromptsPage:
    """`P3-79`: every instruction the project sends, drawn from what the runs recorded.

    The reader is tested in `tests/test_prompt_page.py`; what is held here is that the page
    draws it, that both readings of a prompt come out of the same record, and that a
    selection files under a digest of the words with the run and the instruction beside it.
    """

    def test_the_page_appears_only_where_a_step_calls_a_model(self, pages) -> None:
        assert "prompts" in pages["prompted"]["stage_pages"]
        assert "prompts" not in pages["day-zero"]["stage_pages"]

    def test_every_prompt_the_project_sends_is_on_it(self, pages) -> None:
        held = pages["prompted"]["prompts"]
        assert [one["node_id"] for one in held["steps"]] == [
            "read_request",
            "shortlist",
            "plan_days",
            "reply_in_voice",
            "house_style",
        ]
        assert all(one["filled"] for one in held["steps"])

    def test_it_opens_as_sent_and_the_written_text_is_one_click_away(self, pages) -> None:
        """A cut sentence shows itself in the filled text, so that is what opens."""
        held = pages["prompted"]["prompts"]
        assert "Two days in Lyon in June" in held["as_sent"]
        assert "{message}" not in held["as_sent"]
        assert "{message}" in held["as_written"]
        assert "Two days in Lyon in June" not in held["as_written"]

    def test_a_value_the_step_cut_says_what_never_reached_the_model(self, pages) -> None:
        assert "never reached it" in pages["prompted"]["prompts"]["as_sent"]

    def test_a_message_an_end_user_wrote_is_labelled_on_the_page(self, pages) -> None:
        held = pages["prompted"]["prompts"]["opened"]
        assert "set outside the code: the app's settings screen" in held
        assert "carried from the conversation" in held

    def test_a_filter_narrows_the_path_and_the_prompts_together(self, pages) -> None:
        held = pages["prompted"]["prompts"]
        assert "house_style" in held["only_unagreed"]
        assert "read_request" not in held["only_unagreed"], "an agreed rule survived the filter"
        assert "No prompt matches this filter" in held["only_changed"]

    def test_opening_a_value_says_how_long_it_is_and_where_it_came_from(self, pages) -> None:
        """The panel is where a value's origin and its cut are read."""
        held = pages["prompted"]["prompts"]
        assert held["value_on"] == "message"
        panel = held["value_open"]
        assert "the traveller's own words, as the app took them" in panel
        assert "characters" in panel
        assert "Comment on this value" in panel

    def test_a_shut_fan_out_says_whether_its_items_sent_one_text(self, pages) -> None:
        """A fan-out is one entry, so what its items had in common belongs on that entry."""
        held = pages["prompted"]["prompts"]["shut"]
        assert "No agreed rule. All 2 items used the same text. Open to read it." in held

    def test_collapsing_a_pipeline_in_the_path_survives_the_redraw(self, pages) -> None:
        """The path is redrawn by every control, so a collapse written onto the DOM alone
        sprang open again. The mark is what the state draws."""
        held = pages["prompted"]["prompts"]
        assert "▾ trip" in held["opened"], "an open pipeline is not marked open"
        assert "▸ trip" in held["collapsed"], "the collapse did not survive the redraw"

    def test_the_page_splits_an_address_the_way_the_record_does(self, pages) -> None:
        """Three places on the page read a prompt address; one function does the reading."""
        held = pages["prompted"]["prompts"]["parsed"]
        assert held["whole"] == {
            "pipeline": "trip",
            "step": "plan",
            "where": "trip/plan",
            "part": "",
        }
        assert held["value"]["part"] == "notes"
        assert held["stepless"] is None and held["other"] is None

    def test_a_selection_files_under_the_words_it_quotes(self, pages) -> None:
        held = pages["prompted"]["prompts"]["selection"]
        assert held["address"].startswith("prompt:trip/read_request#words-")
        assert held["quoted"] == "some words in the prompt"
        assert held["run"].startswith("run_") and held["instruction"].startswith("sha256:")


class TestTheStagePages:
    """The shell: a page per stage, the homepage anchored to the project's own stage."""

    def test_the_homepage_is_the_projects_stage(self, pages) -> None:
        assert pages["branching"]["opened_on"] == "measure"
        assert pages["skeleton"]["opened_on"] == "shape"
        assert pages["day-zero"]["opened_on"] == "brainstorm"

    def test_the_page_set_derives_from_the_tier(self, pages) -> None:
        """day-zero claims `prototype`, and a tier without `measure` has no measure page."""
        assert "measure" not in pages["day-zero"]["stage_pages"]
        assert pages["branching"]["stage_pages"] == [
            "brainstorm",
            "research",
            "shape",
            "build",
            # Not a stage: a page of the words the project sends, beside where they are written.
            "prompts",
            "measure",
            "ship",
        ]

    def test_the_drawing_sits_on_the_making_pages(self, pages) -> None:
        boards = {k: v["board"] for k, v in pages["branching"]["pages"].items()}
        assert boards == {
            "brainstorm": False,
            "research": False,
            "shape": True,
            "build": True,
            "prompts": False,
            "measure": True,
            "ship": False,
        }

    def test_each_section_sits_on_its_page(self, pages) -> None:
        held = pages["branching"]["pages"]
        assert "Seams" in held["shape"]["sections"]
        # The data path's rows carry how much moved, which only a run fills, so the table is
        # with the runs and the shape page reads the same steps as the story.
        assert "Where the data goes" in held["build"]["sections"]
        assert "Where the data goes" not in held["shape"]["sections"]
        assert "How the rollouts ended" in held["measure"]["sections"]
        # The run that proves the build works is read where the building is.
        assert "The last run" in held["build"]["sections"]
        assert "How the rollouts ended" not in held["ship"]["sections"]
        assert "The last run" not in held["measure"]["sections"]

    def test_a_page_with_nothing_filed_says_so(self, pages) -> None:
        """At day zero the shape page has no drawing, no decision and no question of its own,
        which the earlier stages no longer do: they draw the idea and the survey."""
        shape = pages["day-zero"]["pages"]["shape"]["sections"]
        assert "The project has no pipeline yet" in shape
        assert "This page then holds" in shape


class TestTheShapePage:
    """Is this the agent I asked for: the story beside the drawing, the seams, the state.

    The regions are `P3-61`'s, read off the skeleton, which is the one fixture whose every
    step is a `NotBuilt` and whose pipelines are unconfirmed.
    """

    def test_the_story_is_the_pipeline_in_order_with_what_each_step_is_for(self, pages) -> None:
        held = pages["skeleton"]["story"]
        assert held.index("intake") < held.index("classify") < held.index("publish")
        # the sentence the `NotBuilt` marker was given, capitalised, beside the step
        assert "Takes one open ticket off the support inbox" in held
        assert "Asks the rota to send, then writes to the outbox" in held

    def test_the_story_marks_every_seam_the_step_holds(self, pages) -> None:
        held = pages["skeleton"]["story"]
        for seam in (
            "Decides for itself",
            "Asks a person",
            "Spends money",
            "Branches",
            "Loops back up to 2×",
            "Touches",
        ):
            assert seam in held, seam

    def test_the_story_is_only_on_the_shape_page(self, pages) -> None:
        """It is the shape page's reading of the pipeline; the other pages ask other things."""
        assert pages["mid-build"]["story"] == ""
        assert pages["branching"]["story"] == ""  # opens on measure
        assert pages["skeleton"]["story"] != ""  # opens on shape
        held = pages["shipped"]["pages"]
        # Either pipeline's steps: for the hour after the fixture is rebuilt its killed run
        # reads as running, and the page opens on the pipeline a run is moving through.
        assert held["shape"]["story"]
        assert "intake" in held["shape"]["story"] or "pick_up" in held["shape"]["story"]
        assert all(held[page]["story"] == "" for page in held if page != "shape")

    def test_a_project_with_no_pipeline_has_no_story(self, pages) -> None:
        assert pages["day-zero"]["story"] == ""

    def test_the_seams_read_the_code_beside_the_answer(self, pages) -> None:
        held = pages["skeleton"]["pages"]["shape"]["sections"]
        assert "Seams" in held and "4 to settle" in held
        assert "Decides for itself" in held and "Asks a person" in held
        assert "Spends money or writes somewhere permanent" in held
        assert "The entry point" in held
        # the code's side, with how each step holds the seam
        assert "answer_directly through web_search" in held
        assert "answered by end user" in held

    def test_a_seam_the_brief_never_answered_says_so(self, pages) -> None:
        """`tool_effects` is unanswered in this brief, and the row names the question."""
        held = pages["skeleton"]["pages"]["shape"]["sections"]
        assert "Unanswered: What it may do outside the run" in held

    def test_the_shared_state_names_both_sides_of_every_resource(self, pages) -> None:
        held = pages["skeleton"]["pages"]["shape"]["sections"]
        assert "Shared state" in held and "4 resources" in held
        assert "Read by triage/answer_directly" in held
        assert "Written by reindex/file_them" in held
        assert "Direction undeclared" in held

    def test_the_decisions_carry_their_status_and_the_click_that_agrees(self, pages) -> None:
        held = pages["skeleton"]["pages"]["shape"]["sections"]
        assert "Decisions" in held and "2 agreed · 1 changed · 1 proposed" in held
        assert "Proposed" in held and "Changed since it was agreed" in held
        assert "Agree" in held and "Amend" in held

    def test_the_shape_page_holds_no_decision_of_another_stage(self, pages) -> None:
        """`escalation` is a `presentation` decision, so it belongs to the ship page."""
        held = pages["skeleton"]["pages"]
        assert "Escalation" not in held["shape"]["sections"]
        assert "Escalation" in held["ship"]["sections"]

    def test_agreeing_to_the_design_is_offered_where_it_is_unconfirmed(self, pages) -> None:
        held = pages["skeleton"]["findings"]
        assert "2 pipelines are drawn" in held
        assert "Agree" in held and "Something is wrong" in held


class TestTheBuildPage:
    """Is it being built as agreed, and what changed (`P3-62`).

    `mid-build` is the project part-built with an answer the code contradicts; `measured` is
    the one whose runs carry numbers and prompts to confirm.
    """

    def test_progress_counts_the_steps_and_marks_each_one(self, pages) -> None:
        held = pages["mid-build"]["pages"]["build"]["sections"]
        assert "Progress" in held and "2 of 3 steps built" in held
        assert "0 proven by a run" in held
        assert "Built, and no run has reached it" in held and "Not built yet" in held

    def test_progress_says_whether_the_shape_is_the_agreed_one(self, pages) -> None:
        assert "Not agreed to yet: next_pick" in pages["mid-build"]["pages"]["build"]["sections"]
        assert "Still the shape" in pages["measured"]["pages"]["build"]["sections"]

    def test_a_step_proven_by_a_run_is_marked_apart_from_one_that_is_not(self, pages) -> None:
        held = pages["measured"]["pages"]["build"]["sections"]
        assert "9 of 9 steps built · 9 proven by a run" in held

    def test_every_number_the_run_carried_is_drawn_with_its_decision(self, pages) -> None:
        held = pages["measured"]["pages"]["build"]["sections"]
        assert "Constants" in held and "2 · 1 unconfirmed" in held
        assert "MAX_AGE_DAYS" in held and "RECEIPT_REQUIRED_OVER" in held
        # where it bites, read from the source the page already shows
        assert "policy_check" in held and "through policy_lookup" in held
        assert "Receipt threshold" in held  # the decision that settled one
        assert "Agree" in held  # and the click that settles the other

    def test_a_prompt_no_decision_names_is_unconfirmed(self, pages) -> None:
        held = pages["measured"]["pages"]["build"]["sections"]
        assert "Prompt rules" in held and "4 · 3 unconfirmed" in held
        assert "No rule is recorded for this prompt" in held
        assert "refuse a claim failing the receipt or age rule" in held

    def test_the_numbers_are_gathered_across_the_runs_not_off_the_newest(self, pages) -> None:
        """`shipped` has two pipelines, and the newest run is the background one. Off the
        newest run alone the page would show its one number and none of the agent's."""
        held = pages["shipped"]["pages"]["build"]["sections"]
        assert "RECONCILE_BATCH" in held  # the background pipeline's
        assert "MAX_AGE_DAYS" in held  # the agent's
        assert "CLAIMS_PER_PAGE" in held  # the surface's
        assert "4 · 3 unconfirmed" in held  # and every prompt, not the last run's none

    def test_a_project_with_no_run_says_why_there_are_no_numbers(self, pages) -> None:
        held = pages["mid-build"]["pages"]["build"]["sections"]
        assert "A run records every module-level number the code reached" in held
        assert "A run records the prompt each model call used" in held

    def test_a_departure_carries_both_ways_out_of_it(self, pages) -> None:
        held = pages["mid-build"]["pages"]["build"]["sections"]
        assert "Build inconsistent with the design" in held
        assert "The answer says judge_books decides for itself" in held
        assert "In the code, judge_books is a model call" in held
        assert "The answer is wrong" in held and "The code is wrong" in held

    def test_a_step_the_answer_never_named_asks_for_the_answer_alone(self, pages) -> None:
        """The quieter half: the code does it and the answer names something else."""
        held = pages["measured"]["pages"]["build"]["sections"]
        assert "the answer names only book" in held
        assert "Add it to the answer" in held

    def test_the_last_run_is_a_strip_of_the_steps_it_took(self, pages) -> None:
        held = pages["measured"]["pages"]["build"]["sections"]
        assert "The last run" in held and "8 steps ran" in held
        assert "It was given" in held and "Team dinner" in held
        assert "Never reached: book" in held
        assert held.index("intake") < held.index("notify")

    def test_the_strip_offers_the_projects_own_runs_and_never_a_rollout(self, pages) -> None:
        """A rollout is what the evaluation did, opened from the grid on the measure page."""
        held = pages["measured"]["pages"]["build"]["sections"]
        assert "c-006-0" not in held and "c-009-0" not in held

    def test_a_project_with_no_run_has_no_last_run(self, pages) -> None:
        assert "The last run" not in pages["mid-build"]["pages"]["build"]["sections"]


class TestTheShipPage:
    """Can other people use this, and what will they meet (`P3-56`).

    `shipped` is `measured` taken to `ship` with its product declared: 24 checks pass, one
    fails, and the one that fails is the design's product section not naming a surface the
    code declares.
    """

    def test_the_checks_are_a_board_with_the_failing_ones_first(self, pages) -> None:
        held = pages["shipped"]["pages"]["ship"]["sections"]
        assert "Checks" in held and "26 of 28 pass" in held
        assert "1 not at this stage" in held
        # the design's product section names two of the three declared surfaces, and the
        # fixture's two suspended runs are what FT-41 is about
        assert "The design the builder agreed to was never written down" in held
        assert "A run stopped to ask, and nothing continued it" in held
        assert held.index("FT-34") < held.index("What passes")
        assert "Show me" in held

    def test_a_check_that_does_not_apply_says_why(self, pages) -> None:
        held = pages["shipped"]["pages"]["ship"]["sections"]
        assert "Development examples leaked into the held-out set" in held
        assert "No threshold was set" in held

    def test_passing_is_counted_out_of_what_ran(self, pages) -> None:
        """A check waiting on an artifact that does not exist yet is not a failure, and
        counting it as one reads a project at its first stage as one in trouble."""
        held = pages["brainstorming"]["pages"]["ship"]["sections"]
        assert "7 of 12 pass" in held
        assert "12 could not run" in held and "5 not at this stage" in held
        # and a blocked row says what it waits on
        assert "which FT-01 reports" in held

    def test_the_product_is_drawn_from_the_declaration(self, pages) -> None:
        held = pages["shipped"]["pages"]["ship"]["sections"]
        assert "The product" in held and "3 surfaces" in held
        for name in ("the finance inbox", "the finance desk", "the ledger"):
            assert name in held, name
        assert "Starts a run" in held and "Answers a waiting run" in held

    def test_a_job_is_drawn_beside_the_surfaces(self, pages) -> None:
        """A declared job is a row of the product with the pipeline it runs and the name the
        scheduler passes, and a job that follows another says so."""
        held = pages["shipped"]["pages"]["ship"]["sections"]
        assert "2 jobs" in held
        for name in ("nightly reconcile", "month-end close"):
            assert name in held, name
        assert "Job · after nightly reconcile" in held
        assert "scheduler starts it and passes trigger=" in held

    def test_a_surface_carries_what_the_code_says_about_what_it_names(self, pages) -> None:
        held = pages["shipped"]["pages"]["ship"]["sections"]
        # the channel it answers through, where it is, and who that channel says answers
        assert "consult" in held and "claims/finance" in held
        assert "answered by end user" in held
        # and the store an artifact surface shows, with the step that writes it
        assert "Written by" in held and "claims/book" in held

    def test_the_surfaces_own_numbers_are_its_own(self, pages) -> None:
        """The declaring module's numbers, which no run reaches and no manifest records."""
        held = pages["shipped"]["pages"]["ship"]["sections"]
        assert "CLAIMS_PER_PAGE" in held and "REASON_CHARS" in held
        assert "MAX_AGE_DAYS" not in held  # the pipeline's, on the build page

    def test_a_project_declaring_no_product_says_how_to_declare_one(self, pages) -> None:
        held = pages["measured"]["pages"]["ship"]["sections"]
        assert "The product" in held and "Not declared" in held
        assert "product_factory" in held

    def test_retention_is_the_builders_own_answers(self, pages) -> None:
        held = pages["shipped"]["pages"]["ship"]["sections"]
        assert "Retention" in held
        assert "kept for a year" in held

    def test_the_brief_board_is_a_tick_list_and_names_no_brief_key(self, pages) -> None:
        held = pages["shipped"]["pages"]["ship"]["sections"]
        assert "Brief against code" in held and "6 of 6 agree" in held
        assert "What the agent works out for itself" in held
        assert "agency_boundary" not in held


class TestTheOperatePage:
    """Is anything stuck, dying or costing money, and what changed (`P3-57`).

    A seventh page, which is not a stage: it appears once the project has live runs. `shipped`
    holds one of each state a live project leaves behind.
    """

    def test_the_tab_appears_once_there_are_live_runs(self, pages) -> None:
        assert pages["shipped"]["stage_pages"][-1] == "operate"
        assert "operate" not in pages["measured"]["stage_pages"]
        assert "operate" not in pages["mid-build"]["stage_pages"]

    def test_now_counts_what_needs_a_person(self, pages) -> None:
        held = pages["shipped"]["pages"]["operate"]["sections"]
        assert "Now" in held and "10 live runs on record" in held
        assert "Waiting" in held and "1 on a person, 1 on a clock" in held
        assert "Shelved questions" in held
        assert "Spent today" in held and "Abandoned" in held

    def test_the_history_is_a_bar_a_day_with_what_it_cost(self, pages) -> None:
        held = pages["shipped"]["pages"]["operate"]["sections"]
        assert "History" in held and "One bar per day" in held
        assert "7 days" in held and "30 days" in held and "90 days" in held
        assert "a call ended throttled" in held

    def test_a_stopped_run_says_what_it_waits_for_and_for_how_long(self, pages) -> None:
        held = pages["shipped"]["pages"]["operate"]["sections"]
        assert "Stuck" in held
        assert "the finance desk to confirm the August write-off" in held
        assert "Waiting on a clock" in held and "not before 2026-09-01" in held

    def test_a_shelved_question_says_who_asked_it_and_why_it_went_unanswered(self, pages) -> None:
        held = pages["shipped"]["pages"]["operate"]["sections"]
        assert "Shelved" in held and "po-80115-unit" in held
        assert "the nightly run is unattended" in held

    def test_the_jobs_are_read_against_what_started_each_run(self, pages) -> None:
        held = pages["shipped"]["pages"]["operate"]["sections"]
        assert "Jobs" in held and "2 declared" in held and "1 undeclared" in held
        assert "nightly reconcile" in held and "5 runs" in held
        assert "month-end close" in held and "after nightly reconcile" in held
        assert "weekly digest" in held and "Not declared" in held
        assert "Product(jobs=[...])" in held

    def test_a_conversation_nothing_reads_says_so(self, pages) -> None:
        held = pages["shipped"]["pages"]["operate"]["sections"]
        assert "finance-august-close" in held and "2 runs" in held
        assert "No step has read or written it" in held

    def test_what_has_run_is_split_by_what_each_run_was_for(self, pages) -> None:
        held = pages["shipped"]["pages"]["operate"]["sections"]
        assert "What has run" in held
        assert "Real traffic" in held and "Made while building" in held
        assert "Rollouts of an evaluation" in held

    def test_the_run_record_left_the_ship_page(self, pages) -> None:
        """It moved here, split by role. A project with no live run keeps it on ship."""
        assert "What has run" not in pages["shipped"]["pages"]["ship"]["sections"]
        assert "What has run" in pages["measured"]["pages"]["ship"]["sections"]


class TestTheBrainstormPage:
    """What am I building, and what have I not yet said (`P3-55`).

    `day-zero` is a brief with a tier and a stage and nothing else; `brainstorming` is the
    same project part way through its first conversation.
    """

    def test_the_idea_is_five_boxes(self, pages) -> None:
        held = pages["brainstorming"]["pages"]["brainstorm"]["sections"]
        assert "The idea" in held
        # the label is set uppercase by the stylesheet, so the text is the source's own
        for words in (
            "Who uses it",
            "Entry point",
            "The agent",
            "What they get",
            "What it receives",
        ):
            assert words in held, words

    def test_an_unanswered_box_is_a_ghost_and_a_deferred_one_says_where_it_went(
        self, pages
    ) -> None:
        held = pages["brainstorming"]["pages"]["brainstorm"]["sections"]
        # The fifth box is `presentation`, a shape question: not unanswered yet, ahead.
        assert "1 asked at a later stage" in held
        assert "Asked at shape" in held and "Put off to shape" in held

    def test_on_day_zero_every_box_is_a_ghost(self, pages) -> None:
        held = pages["day-zero"]["pages"]["brainstorm"]["sections"]
        assert "4 of 5 unanswered" in held and "Asked at shape" in held

    def test_the_questions_read_in_four_states(self, pages) -> None:
        held = pages["brainstorming"]["pages"]["brainstorm"]["sections"]
        assert "Questions" in held and "7 of 15 answered" in held
        assert "Put off to shape" in held  # deferred
        assert "optional" in held  # not required
        assert "Amend" in held and "Answer" in held  # what each state offers

    def test_the_stages_carry_answered_of_asked(self, pages) -> None:
        held = pages["brainstorming"]["pages"]["brainstorm"]["sections"]
        assert "Stages" in held
        assert "7/15" in held  # brainstorm, where the project is
        assert "0/5" in held  # research, still ahead

    def test_the_idea_file_is_read_back_with_one_click_to_confirm(self, pages) -> None:
        held = pages["brainstorming"]["pages"]["brainstorm"]["sections"]
        assert "The idea file" in held and "Not confirmed" in held
        assert "What this is" in held and "Where this is going and where it is not" in held
        assert "This is right" in held

    def test_a_project_with_no_idea_file_says_what_it_is_for(self, pages) -> None:
        held = pages["day-zero"]["pages"]["brainstorm"]["sections"]
        assert "Not written yet" in held and "idea.md" in held


class TestTheResearchPage:
    """What was found, and what the design rests on (`P3-55`)."""

    def test_the_deciding_factor_is_the_one_sentence_the_stage_produces(self, pages) -> None:
        held = pages["shipped"]["pages"]["research"]["sections"]
        assert "The deciding factor" in held
        assert "Whether the decision never approves a claim the policy refuses." in held

    def test_the_candidates_are_a_column_a_part_with_what_became_of_each(self, pages) -> None:
        held = pages["shipped"]["pages"]["research"]["sections"]
        assert "Parts and candidates" in held and "4 parts" in held
        assert "Reading the fields" in held and "Checking the supplier" in held
        assert "Adopted: The fields are all in the text" in held
        assert "Rejected: The limits changed twice in the archive" in held
        assert "Not investigated: No claim in the archive has an image attached" in held

    def test_a_decision_is_joined_to_the_candidates_it_weighed(self, pages) -> None:
        held = pages["shipped"]["pages"]["research"]["sections"]
        assert "the_supplier_registry rests on it" in held
        assert "Decisions resting on it" in held
        assert "The approved-supplier registry" in held and "A copy refreshed nightly" in held

    def test_the_builders_own_words_are_quoted_at_the_foot(self, pages) -> None:
        held = pages["shipped"]["pages"]["research"]["sections"]
        assert "What the builder said about it" in held
        assert "The audit step is the one I would not drop" in held

    def test_a_project_with_no_research_says_what_would_fill_it(self, pages) -> None:
        held = pages["brainstorming"]["pages"]["research"]["sections"]
        assert "research.md" in held and "Not written yet" in held


class TestTheMeasurePage:
    """The results visualiser: the three questions, in order, with the grid as the hub."""

    def test_the_strip_answers_how_good_it_is(self, pages) -> None:
        held = pages["branching"]["pages"]["measure"]["sections"]
        assert "accuracy" in held and "Doing nothing" in held
        assert "Since last time" in held and "What measuring cost" in held
        assert "a rollout" in held and "Steps it reached" in held

    def test_the_grid_lists_every_example_wrong_first(self, pages) -> None:
        held = pages["branching"]["pages"]["measure"]["sections"]
        assert "Every example" in held
        assert held.index("t-thanks") < held.index("t-export-filter")  # the one that missed

    def test_the_outcomes_are_one_bar_with_a_right_side_and_a_wrong_side(self, pages) -> None:
        held = pages["branching"]["pages"]["measure"]["sections"]
        assert "How the rollouts ended" in held
        assert "right" in held and "wrong" in held and "Right, by reporting absence" in held

    def test_every_figure_sits_on_one_axis(self, pages) -> None:
        held = pages["branching"]["pages"]["measure"]["sections"]
        assert "All the figures" in held and "Plausible range" in held

    def test_the_comparison_is_drawn_from_the_written_record(self, pages) -> None:
        held = pages["branching"]["pages"]["measure"]["sections"]
        assert "Did the last change help?" in held
        assert "no revision, against the baseline" in held
        assert "What differed" in held
        assert "Moved" in held or "Held" in held or "Undecided" in held

    def test_the_ladder_is_drawn_on_the_steps(self, pages) -> None:
        held = pages["branching"]["pages"]["measure"]["sections"]
        assert "Where it loses it, step by step" in held
        assert "held-out-from-classify.json" in held and "The whole pipeline" in held
        assert "an observation and not a paired difference" in held

    def test_the_trend_joins_only_comparable_points(self, pages) -> None:
        held = pages["branching"]["pages"]["measure"]["sections"]
        assert "over time" in held
        # `branching`'s second results file is a sweep's arm, an experiment rather than the
        # project's history, so it is off the line and the line has one point.
        assert "One evaluation on record" in held
        held = pages["measured"]["pages"]["measure"]["sections"]
        # `measured` changed its decide prompt between its second and third evaluation.
        assert "dashed break" in held and "sweep's 2 arms" in held

    def test_a_project_that_measured_nothing_says_what_it_will(self, pages) -> None:
        held = pages["skeleton"]["pages"]["measure"]["sections"]
        assert "Nothing measured yet" in held
        assert "Examples on file" in held

    def test_the_measured_fixture_fills_every_region(self, pages) -> None:
        """`measured` holds a moved verdict, a ladder, conditions, groups and six evaluations."""
        held = pages["measured"]["pages"]["measure"]["sections"]
        assert "Which condition fails most" in held and "fell short" in held
        assert "finance without the registry, against the baseline" in held
        assert "The tool vendor_registry" in held and "Moved" in held and "Held" in held
        assert "From extract on" in held and "From policy_check on" in held
        assert "4 evaluations" in held  # seven on record: two a sweep's arms, one judged pairs
        assert "the decision is approve" in held  # what an example expects, in words

    def test_a_session_of_judged_pairs_is_drawn_head_to_head(self, pages) -> None:
        """`measured` files one session: the baseline against the registry-less arm."""
        held = pages["measured"]["pages"]["measure"]["sections"]
        assert "Head to head" in held and "baseline v no registry" in held
        assert "decided" in held and "both wanted" in held and "neither wanted" in held
        assert "no_registry_beats_baseline" in held and "The pairs" in held
        # The session stays off the trend, which says where it went instead.
        assert "One session of judged pairs is drawn under Head to head" in held
        # And the n column reads the two totals behind a ratio.
        assert " of 30" in held


class TestTheMeasurePageDrillDowns:
    """Driven through the page's own functions: a drill-down lights the grid, a rung the graph."""

    @pytest.fixture(scope="class")
    def driven(self, tmp_path_factory) -> dict:
        node = node_or_skip()
        root = tmp_path_factory.mktemp("measure")
        page = generate_view(FIXTURES / "branching", out=root / "view.html")
        done = subprocess.run(
            [node, str(HERE / "view_measure_drive.mjs"), str(page)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    def test_an_outcome_lights_the_rollouts_behind_it(self, driven) -> None:
        held = driven["after_outcome"]
        assert held["filter"]["kind"] == "outcome"
        assert held["filter"]["examples"]
        assert "Show all" in held["sections"]
        assert driven["cleared"] is None

    def test_a_group_lights_its_examples(self, driven) -> None:
        held = driven["after_group"]
        assert held["filter"]["kind"] == "group"
        assert set(held["filter"]["examples"]) == set(held["examples"])

    def test_a_figure_opens_to_its_numbers(self, driven) -> None:
        held = driven["after_figure"]
        assert "How the range was made" in held["sections"]
        assert "Plausible range" in held["sections"]

    def test_a_rollout_opens_to_what_it_answered(self, driven) -> None:
        held = driven["after_cell"]
        assert "Answered" in held["sections"]
        # A still page carries the runs that came out wrong; a rollout it does not carry says
        # so rather than offering a button that does nothing.
        assert "Walk this rollout" in held["sections"] or "Not in this file" in held["sections"]

    def test_a_rollout_is_walked_on_the_build_page_and_says_which_it_is(self, driven) -> None:
        """The walk lives where the building is; a rollout is the evaluation's run and not
        the project's, so the region says so and offers the way back."""
        held = driven["after_walk"]
        assert held["page"] == "build"
        assert "One rollout of the evaluation" in held["sections"]
        assert "opened from the measure page" in held["sections"]

    def test_a_rung_shades_the_drawing_to_its_node_set(self, driven) -> None:
        """The rung starts at classify, so intake is shaded and everything from classify on
        is drawn in full, nested steps included."""
        held = driven["after_rung"]
        assert "intake" in held["shaded"]
        assert "classify" not in held["shaded"]
        assert "research.pick_sources" in held["drawn"]
        assert "research.pick_sources" not in held["shaded"]


class TestTheSystemLevel:
    def test_it_is_drawn_only_where_there_is_a_system(self, pages) -> None:
        """One pipeline is a pipeline; the level appears when there is more than one."""
        assert pages["branching"]["system_shown"]
        assert pages["many-pipelines"]["system_shown"]
        assert not pages["one-pipeline"]["system_shown"]
        assert not pages["batch"]["system_shown"]

    def test_one_link_per_pipeline_and_store_that_touch(self, pages) -> None:
        held = pages["branching"]
        assert held["system_links"] == 6
        assert held["system_boxes"] == 6  # two pipelines and four stores

    def test_a_redraw_replaces_what_was_drawn(self, pages) -> None:
        """Every control redraws, and a drawing that accumulates is a drawing that lies."""
        held = pages["branching"]
        assert held["after_every_control"]["system_links"] == held["system_links"]
        assert held["after_every_control"]["system_boxes"] == held["system_boxes"]

    def test_the_controls_offer_what_the_record_can_fill(self, pages) -> None:
        dials = pages["branching"]["system_dials"]
        assert "runs · 2" in dials and "The evaluation · 16" in dials
        for words in ("What it cost", "How long it took", "Model calls", "Items handled"):
            assert words in dials

    def test_a_project_with_one_fillable_measure_still_offers_it(self, pages) -> None:
        """The defect this file was written for.

        `many-pipelines` has one run whose only figure is `ms`. The control appeared only
        where more than one measure was fillable, so the bar never drew and the one measure
        the project had was unreachable.
        """
        held = pages["many-pipelines"]
        assert "How long it took" in held["system_dials"]
        assert "The bar is how long it took" in held["system_note"]

    def test_nothing_recorded_means_no_bar_and_no_width(self, pages) -> None:
        """At `shape` the level draws structure, and claims no figure it does not have."""
        held = pages["skeleton"]
        assert held["system_shown"]
        assert held["system_dials"] == ""
        assert held["system_note"] == ""


class TestWhatTheBuilderMeetsFirst:
    def test_a_skeleton_leads_with_the_unconfirmed_design(self, pages) -> None:
        assert "have not agreed to" in pages["skeleton"]["findings"]
        assert "2 pipelines await" in pages["skeleton"]["standing"]

    def test_a_project_before_its_first_line_of_code_still_renders(self, pages) -> None:
        """A brief in progress and no `agent.py`. The panel says so rather than staying empty."""
        held = pages["day-zero"]
        assert held["standing"].strip()
        assert held["graph_nodes"] == 0
        # The homepage at day zero is the brainstorm page, with no drawing; the shape page
        # draws the sentence about there being nothing to draw yet.
        assert held["opened_on"] == "brainstorm"
        assert not held["pages"]["shape"]["graph_drawn"]
        assert "The project has no pipeline yet" in held["pages"]["shape"]["sections"]

    def test_a_question_reaches_the_page_under_its_own_name(self, pages) -> None:
        """The brief key is the address a comment is filed under, never a heading.

        The answers file one stage page each now, so the record read is every page's."""
        held = pages["branching"]["pages"]
        sections = " ".join(one["sections"] for one in held.values())
        assert "What the agent works out for itself" in sections
        assert "What the end user opens" in sections  # the question under its own name
        assert "agency_boundary" not in sections and "used_through" not in sections

    def test_a_step_card_carries_what_the_step_declares(self, pages) -> None:
        card = pages["branching"]["step_card"]
        assert "Takes in" in card and "Produces" in card


def _declared(name: str) -> list[dict]:
    from simple_agents.view import assemble

    return [p for p in assemble(FIXTURES / name)["pipelines"] if p["origin"] == "declared"]


class TestTheStepDecisionJoin:
    """`produces` names the step exactly, and the wording is the fallback.

    Before `produces` existed the join was a name match over `chose` and `because`. A brief
    that follows the convention keeps identifiers out of that prose, so every well-formed
    project read as though no decision named any step.
    """

    def joined(self, decisions: str, tmp_path):
        from simple_agents.view.assemble import assemble

        root = tmp_path / "project"
        root.mkdir()
        (root / "agent.py").write_text(
            "from simple_agents import Budget, Deterministic, Pipeline, pipeline_factory\n"
            "\n"
            "@pipeline_factory('one')\n"
            "def build():\n"
            "    return Pipeline([Deterministic(lambda i, c: i, node_id='gather')],\n"
            "                    budget=Budget(max_steps=2, max_tokens=None, max_cost=None,\n"
            "                                  max_wall_clock_ms=1000))\n",
            encoding="utf-8",
        )
        (root / "brief.toml").write_text(
            'tier = "prototype"\nstage = "build"\n' + decisions, encoding="utf-8"
        )
        data = assemble(str(root))
        node = data["pipelines"][0]["nodes"][0]
        return node["decisions"], data["decisions_join"]["naming_no_step"]

    def test_produces_names_the_step_exactly(self, tmp_path) -> None:
        found, orphans = self.joined(
            '\n[decisions.two_steps]\nkind = "shape"\nstatus = "agreed"\nrecorded_at = "2026-08-27T09:14:02Z"\n'
            'chose = "a cut, then one judgement over what it kept"\n'
            'produces = ["gather"]\n',
            tmp_path,
        )

        assert [(d["name"], d["exact"]) for d in found] == [("two_steps", True)]
        assert orphans == []

    def test_a_decision_recording_none_falls_back_to_its_wording(self, tmp_path) -> None:
        found, orphans = self.joined(
            '\n[decisions.two_steps]\nkind = "shape"\nstatus = "agreed"\nrecorded_at = "2026-08-27T09:14:02Z"\n'
            'chose = "gather runs first"\n',
            tmp_path,
        )

        assert [(d["name"], d["exact"]) for d in found] == [("two_steps", False)]
        assert orphans == []

    def test_a_kind_whose_produces_names_no_step_does_not_join(self, tmp_path) -> None:
        """A `constant` names numbers and a `dependency` names tools."""
        found, orphans = self.joined(
            '\n[decisions.the_bar]\nkind = "constant"\nstatus = "agreed"\nrecorded_at = "2026-08-27T09:14:02Z"\n'
            'chose = "6.0"\nproduces = ["MIN_RATING"]\n',
            tmp_path,
        )

        assert found == []
        assert orphans == ["the_bar"]

    def test_prose_naming_a_step_is_ignored_once_produces_records_one(self, tmp_path) -> None:
        """The exact field is the answer where it is there, so the two cannot disagree."""
        found, _ = self.joined(
            '\n[decisions.two_steps]\nkind = "shape"\nstatus = "agreed"\nrecorded_at = "2026-08-27T09:14:02Z"\n'
            'chose = "gather runs first"\nproduces = ["something_else"]\n',
            tmp_path,
        )

        assert found == []


class TestAFigureWithAFloorAndNoTotal:
    """A step whose cost was summed over the calls that priced says so on the page.

    `P3-50`: an unmeasured token count is not zero, so a step with one unpriced call has no
    total, and reporting the calls that did price as though they were the whole is what the
    view's own reading of a rate-limited evaluation did before this. Nothing tested these two
    lines of the page in either direction.
    """

    def page_with_a_floor(self, tmp_path: Path) -> dict:
        """`one-pipeline`, with an unpriced count on its one step that spent anything."""
        from simple_agents.view.assemble import assemble
        from simple_agents.view.render import render

        data = assemble(FIXTURES / "one-pipeline")
        touched = 0
        for pipeline in data.get("pipelines") or []:
            for node in pipeline.get("nodes") or []:
                record = node.get("over_the_record") or {}
                if record.get("cost_by_basis"):
                    record["cost_unknown"] = 4
                    touched += 1
        assert touched, "the fixture no longer has a step that spent anything"

        out = tmp_path / "floor.html"
        out.write_text(render(data, title="floor"), encoding="utf-8")
        done = subprocess.run(
            [node_or_skip(), str(HARNESS), str(out)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if done.returncode != 0:
            pytest.fail(f"the page threw with a floor on a step\n{done.stderr}")
        return json.loads(done.stdout)

    def test_the_step_card_says_it_is_a_floor_and_what_is_missing(self, tmp_path) -> None:
        card = self.page_with_a_floor(tmp_path)["after_every_control"]["step_card"]

        assert "Its model calls cost at least" in card
        assert "4 call(s) could not be priced" in card

    def test_a_step_whose_every_call_priced_claims_no_floor(self, tmp_path) -> None:
        """The other direction: `in all` is a total and must not read as `at least`."""
        node = node_or_skip()
        page = tmp_path / "whole.html"
        generate_view(FIXTURES / "one-pipeline", out=page)
        done = subprocess.run(
            [node, str(HARNESS), str(page)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert done.returncode == 0, done.stderr
        card = json.loads(done.stdout)["after_every_control"]["step_card"]

        assert "Its model calls cost" in card
        assert "at least" not in card
