"""The staged procedure: the stages, the questions, the elicitation gate, and `init`.

The last class is the six pins that hold the skill. It is prose, and prose drifts, so every
command, stage, path and citation it names is checked against the thing it names.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from simple_agents import docs_path
from simple_agents.cli import main
from simple_agents.conformance import (
    DECISION_KINDS,
    QUESTIONS,
    STAGES,
    Brief,
    Outcome,
    kind_names,
    question,
    questions_at,
    reached,
    required_at,
    run_checks,
    stages_for,
    up_to,
)
from simple_agents.conformance.artifacts import DEFAULT_BRIEF, DEFAULT_RESULTS, DEFAULT_RUNS
from simple_agents.conformance.checks import COMMON_RECORD_FIELDS
from simple_agents.errors import ConfigurationError

ROOT = Path(__file__).resolve().parents[1]


def _tool_factories() -> list:
    """Every built-in that returns a `Tool`, read off the signature rather than listed here."""
    import inspect
    import sys

    import simple_agents.builtins as builtins
    from simple_agents.tools import Tool

    found = []
    for name in builtins.__all__:
        candidate = getattr(builtins, name)
        if not callable(candidate) or inspect.isclass(candidate):
            continue
        returns = inspect.signature(candidate).return_annotation
        if isinstance(returns, str):
            returns = getattr(sys.modules[candidate.__module__], returns, None)
        if isinstance(returns, type) and issubclass(returns, Tool):
            found.append(candidate)
    return found


PROCEDURE = ROOT / "docs" / "procedure.md"
# Raised from 1815 at P3-28, which added the `research` stage and the three homes a
# project's own files have, from 2160 at P3-34, which added the role a pass declares for
# itself and what the ship gate goes on doing after it is passed, from 2400 at P3-36,
# which added the question every gate puts again and names it at each of the six, from
# 2550 at P3-35, which added the view every gate rewrites, the skeleton at `shape` and the
# comment record, and from 2600 at P3-37, which added the four rules for how a question is
# put, that an evaluation puts none of them to a person, and the one run at `build` that
# reaches a consultation and is continued, from 3200 at P3-66, which added the feature
# index: one line per document naming every capability the library ships, so a coding agent
# finds one without knowing which document owns it, and from 3800 on 2026-09-01, when the
# first installed-package session ran `find /` hunting for the docs: the file now says
# `docs_path()` prints the directory its 39 `docs/*.md` names live in. New content rather
# than a restatement of another document, which is what the budget is against. And from 3860
# on 2026-09-03, for two things the library did not have: a writer for a decision the builder
# settled by a click, since eight of those on one project produced eight decisions whose
# `because` opened with the same two lines, and the feature index line for naming a pipeline.
# And from 3897 on 2026-09-03 for the prompts document, which the index has to name: a
# capability nothing in the index points at is one a coding agent has to find by accident.
# And from 3959 on 2026-09-05, for the prompts page: a builder who never sees a prompt cannot
# agree to one, and a coding agent that does not know the page exists cannot point at it.
# And from 3998 on 2026-09-05, for three instructions the procedure did not carry. `rerun` for
# a run whose process was killed: one project read the resume paragraph, correctly ruled it
# out, and rebuilt chunked checkpointing around a facility the library already had. A
# `prompt_rule` decision put with the prompt rather than a summary of it, which is what hid
# eighteen truncation sites on that project. And designing the product with the builder at
# `ship`, for the second project running that built it after the last gate. The paragraph
# restating `involvement`'s own scaffold was written and then cut, which is what the budget is
# against.
WORD_BUDGET = 4190
# Raised from 4177 at P3-77, 2026-09-05: the `ship` step declares a job beside a surface and the
# feature index names `Job` and `trigger=`, thirteen words across two sentences, against a page
# that stood at 4175.
# Raised from 3840 at P3-72, 2026-09-02: every gate's hand edit of the brief (`stage`, the
# three `*_confirmed_at` keys, `shape_confirmed`, `confirmed_against`) became a
# `simple-agents record` command, seven words over the ceiling across eight sentences.
# Raised from 3000 on 2026-08-28, on Thilina's call at `P3-53`. Stage 5 stood at 2999 of 3000,
# so the paragraph naming per-step reporting could not go in without cutting prose that was
# carrying its own instruction. What the budget is against is restatement, and the ceiling is
# the crude proxy for it; raising it is the decision that a stage gaining a new instruction
# should not be paid for by another stage losing one.


STAMP = "2026-08-27T09:14:02Z"


def _brief(
    tmp_path: Path,
    *,
    tier: str = "prototype",
    stage: str | None = None,
    deferred_to: str = "ship",
    **entries,
):
    re_asked = {q.name for q in QUESTIONS if q.re_asked_each_stage}
    lines = [f'tier = "{tier}"']
    if stage:
        lines.append(f'stage = "{stage}"')
    for name, status in entries.items():
        lines += ["", f"[entries.{name}]", f'status = "{status}"']
        if status == "deferred":
            # `ship` is the one stage every tier has, so a deferral to it is legal whatever
            # the brief claims. `measure` is not, at `prototype`.
            lines.append(f'deferred_to = "{deferred_to}"')
        if status == "answered":
            lines.append(f'recorded_at = "{STAMP}"')
            if name in re_asked:
                # A question every gate puts again is settled only where `asked_at` names
                # the stage the project is at, and a brief declaring none is at the first.
                lines.append(f'asked_at = "{stage or STAGES[0]}"')
            lines.append('answer = "what the builder said"')
    (tmp_path / "brief.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


class TestTheStages:
    def test_the_six_are_ordered(self) -> None:
        assert STAGES == ("brainstorm", "research", "shape", "build", "measure", "ship")

    def test_a_gate_holds_a_project_to_every_earlier_stage(self) -> None:
        """Cumulative, so declaring a later stage adds questions rather than skipping them."""
        assert up_to("shape") == ("brainstorm", "research", "shape")
        assert up_to("measure") == ("brainstorm", "research", "shape", "build", "measure")

    def test_the_tier_decides_which_stages_a_project_has(self) -> None:
        """A project reporting no number has no `measure`, and every tier has `ship`."""
        assert stages_for("prototype") == ("brainstorm", "research", "shape", "build", "ship")
        assert stages_for("evaluated") == STAGES
        assert up_to("ship", "prototype") == (
            "brainstorm",
            "research",
            "shape",
            "build",
            "ship",
        )

    def test_an_unknown_tier_is_held_to_every_stage(self) -> None:
        """Fail closed: a caller that cannot say what the project claims is asked everything."""
        assert stages_for(None) == STAGES
        assert stages_for("something-else") == STAGES

    def test_a_live_run_moves_a_project_to_ship(self) -> None:
        assert reached("build", has_run=True, has_results=False, has_live_run=True) == "ship"

    def test_a_results_file_leaves_a_prototype_where_it_was(self) -> None:
        """That tier has no `measure`, so producing its artifact does not move the project."""
        assert reached("build", has_run=True, has_results=True, tier="prototype") == "build"
        assert reached("build", has_run=True, has_results=True, tier="evaluated") == "measure"

    def test_a_name_that_is_not_a_stage_covers_nothing(self) -> None:
        assert up_to("shipped") == ()

    def test_a_project_with_no_brief_stage_is_at_the_first_one(self) -> None:
        assert reached(None, has_run=False, has_results=False) == "brainstorm"

    def test_a_run_directory_moves_a_project_to_build_whatever_it_declared(self) -> None:
        assert reached("shape", has_run=True, has_results=False) == "build"

    def test_a_results_file_moves_it_to_measure(self) -> None:
        assert reached(None, has_run=False, has_results=True) == "measure"

    def test_declaring_a_later_stage_is_taken_at_its_word(self) -> None:
        """The library cannot know what the builder intends, so a claim is not argued with."""
        assert reached("measure", has_run=False, has_results=False) == "measure"

    def test_artifacts_never_move_a_project_backwards(self) -> None:
        assert reached("measure", has_run=True, has_results=False) == "measure"


class TestTheQuestions:
    def test_every_question_names_a_stage_that_exists(self) -> None:
        assert all(q.stage in STAGES for q in QUESTIONS)

    def test_every_question_carries_a_scaffold(self) -> None:
        """A required question a builder cannot answer cold is a wall, and a wall gets a guess."""
        assert all(q.scaffold.strip() for q in QUESTIONS)
        assert all(q.ask.strip().endswith("?") for q in QUESTIONS)

    def test_no_ask_puts_the_library_s_own_words_to_the_builder(self) -> None:
        """`ask` is the text the builder reads, and these words mean nothing to one.

        Dogfood #4's builder was asked `too_similar` and reported being asked for a number in
        a vocabulary he had not been given. `Question.name` may be library vocabulary and
        `scaffold` is written for the coding agent; this is the one field a builder sees.
        """
        vocabulary = (
            "node",
            "schema",
            "rollout",
            "trajectory",
            "envelope",
            "split",
            "pipeline",
            "manifest",
            "cassette",
            "fingerprint",
            "side-effect class",
            "threshold",
            "abstention",
            "tier",
            "gate",
            "conformance",
        )
        found = {
            q.name: [word for word in vocabulary if re.search(rf"\b{word}s?\b", q.ask, re.I)]
            for q in QUESTIONS
        }

        assert {name: words for name, words in found.items() if words} == {}

    def test_no_ask_cites_a_document_or_a_taxonomy_entry(self) -> None:
        """A citation is an instruction to the coding agent, and the builder reads `ask`.

        Dogfood #5's builder, on a question composed at `measure`: "So much jargon and no
        clear question, options, or recommendation." A `docs/` path or an `FT-nn` in the text
        put to them is the plainest form of that. 27 of the scaffolds carry one, which is
        where they belong.
        """
        citation = re.compile(r"docs/[A-Za-z0-9_./-]+|\bFT-\d\d\b")
        found = {q.name: citation.findall(q.ask) for q in QUESTIONS}

        assert {name: cited for name, cited in found.items() if cited} == {}

    def test_the_four_rules_for_putting_a_question_reach_both_places(self) -> None:
        """The scaffold saying it was measured not to be enough.

        `answer_form`'s scaffold said "offer the five against one of the builder's own inputs"
        at dogfood #5's freeze, and the coding agent took the five library type-names out of
        it and asked against an invented example. The builder could not answer it as put. So
        the rule sits where a question is composed rather than in one scaffold, and both
        places carry it.
        """
        from simple_agents.cli.main import HOW_A_QUESTION_IS_PUT

        procedure = PROCEDURE.read_text(encoding="utf-8")

        for text in (procedure, HOW_A_QUESTION_IS_PUT):
            # Both wrap, and one wraps at a different width, so the claim is about the words.
            place = " ".join(text.split())
            assert "How to ask a question" in place
            assert "something of the builder's own" in place
            assert "where the number came from" in place
            assert "recommended" in place
            assert "the project's own code" in place
            assert "Do not mix prose questions" in place

    def test_the_five_rewritten_asks_name_what_goes_in_front_of_the_builder(self) -> None:
        """Each of the five offered a choice, or asked for a value, with no instance in it."""
        anchored = {
            "answer_form": "one of the builder's own inputs",
            "absence_vs_error": "one of the builder's own inputs",
            "judged_steps": "Here are the steps this agent takes",
            "budget": "has been measured",
            "unevaluated_effects": "Here is what this agent does for real",
        }

        for name, phrase in anchored.items():
            assert phrase in question(name).ask, name

    def test_the_consultation_scaffold_reads_the_mode_off_used_through(self) -> None:
        """DF5-I38. The trigger decides the mode, and `used_through` already carries it.

        Named in the builder's terms first: dogfood #5's product needed shelving for all
        1,654 of its consultations and had to spell it `Unavailable`.
        """
        scaffold = question("consultation").scaffold

        assert "`used_through`" in scaffold
        assert "can be kept waiting" in scaffold
        assert "cannot stop" in scaffold
        assert "finishes without one" in scaffold
        assert "`Suspend`, `Shelved` and `Unavailable`" in scaffold

    def test_the_shape_questions_name_every_answer_key_the_library_ships(self) -> None:
        """P3-11's finding: the keys shipped and no question a builder is asked reached them.

        The names are read off the library rather than transcribed, so a key added or renamed
        leaves this failing rather than passing against a list that has gone stale.
        """
        from simple_agents.evaluation import AnyOf, Contains, Criteria, WithinTolerance

        text = " ".join(q.ask + q.scaffold for q in questions_at("shape"))

        for key in (AnyOf, Contains, WithinTolerance, Criteria):
            assert key.__name__ in text, key.__name__

    def test_the_shape_questions_reach_the_per_node_seam(self) -> None:
        """49 results files over four dogfoods carried the section and none carried a label."""
        import inspect

        from simple_agents.evaluation import EvalSuite, Example

        text = " ".join(q.scaffold for q in questions_at("shape"))

        assert "expected_by_node" in Example.__dataclass_fields__
        assert "node_matches" in inspect.signature(EvalSuite.__init__).parameters
        assert "expected_by_node" in text
        assert "node_matches" in text

    def test_the_set_at_a_stage_includes_the_stages_before_it(self) -> None:
        brainstorm = {q.name for q in questions_at("brainstorm")}
        shape = {q.name for q in questions_at("shape")}
        build = {q.name for q in questions_at("build")}

        assert brainstorm < shape < build
        assert shape == {q.name for q in QUESTIONS if q.stage in up_to("shape")}

    def test_required_is_a_subset_of_what_is_asked(self) -> None:
        for stage in STAGES:
            assert set(required_at(stage)) <= set(questions_at(stage))

    def test_a_question_is_reachable_by_the_entry_name_that_records_it(self) -> None:
        assert question("budget").stage == "build"

    def test_an_unknown_name_names_the_ones_that_exist(self) -> None:
        with pytest.raises(KeyError, match="ground_truth"):
            question("what_colour")

    def test_every_taxonomy_entry_the_scaffolds_cite_exists(self) -> None:
        """A scaffold is read at the moment a question is put, so a dead citation costs there."""
        from simple_agents.conformance import taxonomy

        known = {entry.id for entry in taxonomy()}
        cited = {found for q in QUESTIONS for found in re.findall(r"FT-\d\d", q.ask + q.scaffold)}

        assert cited
        assert cited <= known


class TestTheElicitationGate:
    def test_a_brief_with_no_entries_fails_at_the_first_stage(self, tmp_path) -> None:
        """Measured before this item: such a brief passed every check the suite ran."""
        found = run_checks(_brief(tmp_path))

        assert {c.entry_id for c in found.failed} == {"FT-13", "FT-24", "FT-29", "FT-30"}

    def test_it_names_the_entries_that_are_missing(self, tmp_path) -> None:
        found = run_checks(_brief(tmp_path))
        message = [c for c in found.checks if c.entry_id == "FT-24"][0].findings[0].message

        assert "what_it_does" in message
        assert "stage `brainstorm`" in message

    def test_a_question_with_no_entry_reads_the_same_as_one_recorded_unanswered(
        self, tmp_path
    ) -> None:
        answered = {q.name: "answered" for q in required_at("shape")}
        with_one_unanswered = dict(answered, ground_truth="unanswered")
        # `shape` is cumulative, so this set already carries the brainstorm questions.

        assert _fired(_brief(tmp_path, stage="shape", **answered)) is False
        assert _fired(_brief(tmp_path, stage="shape", **with_one_unanswered)) is True

    def test_a_deferral_satisfies_the_gate(self, tmp_path) -> None:
        # Every question but the one each gate puts again, which has no later stage to be
        # deferred to and is answered here instead.
        entries = {
            q.name: "deferred" if not q.re_asked_each_stage else "answered"
            for q in required_at("shape")
        }

        assert _fired(_brief(tmp_path, **entries)) is False

    def test_an_optional_question_is_never_required(self, tmp_path) -> None:
        """The names are transcribed rather than read from the set the gate reads."""
        answered = {
            "what_it_does": "answered",
            "used_through": "answered",
            "how_far": "answered",
            "involvement": "answered",
            "purpose": "answered",
            "end_user": "answered",
            "one_real_input": "answered",
            "smallest_worthwhile": "answered",
            "finished_version": "answered",
            "parts": "answered",
            "approaches": "answered",
            "available_material": "answered",
            "what_goes_wrong": "answered",
            "what_this_turns_on": "answered",
            "ground_truth": "answered",
            "answer_form": "answered",
            "judged_steps": "answered",
            "judged_path": "answered",
            "absence_vs_error": "answered",
            "agency_boundary": "answered",
            "consultation": "answered",
            "presentation": "answered",
            "comments_block_gates": "answered",
            "backend": "answered",
            "budget": "answered",
            "tool_effects": "answered",
            "unproven_answer": "answered",
            "keep_payloads": "answered",
            "who_labels": "answered",
            "anything_else": "answered",
        }
        optional = {
            "existing_solution",
            "success_story",
            "alternatives",
            "not_building",
            "abandon_condition",
            "unknown_literal",
            "context_limit",
            "rerun_cost",
            "reproduce",
        }

        assert optional == {q.name for q in questions_at("build") if not q.required}
        assert set(answered) == {q.name for q in required_at("build")}
        assert _fired(_brief(tmp_path, stage="build", **answered)) is False

    def test_declaring_a_later_stage_requires_more_rather_than_less(self, tmp_path) -> None:
        entries = {q.name: "answered" for q in required_at("shape")}

        assert _fired(_brief(tmp_path, stage="shape", **entries)) is False
        assert _fired(_brief(tmp_path, tier="evaluated", stage="measure", **entries)) is True

    def test_a_results_file_makes_the_measure_questions_required(self, tmp_path) -> None:
        """A project that evaluated is at `measure` whatever its brief declares."""
        entries = {q.name: "answered" for q in required_at("build")}
        root = _brief(tmp_path, tier="evaluated", stage="build", **entries)

        assert _fired(root) is False

        results = root / "evals" / "results"
        results.mkdir(parents=True)
        (results / "v1.json").write_text('{"created_at": "2026-08-06T00:00:00Z"}')

        assert _fired(root) is True

    def test_a_results_file_asks_a_prototype_nothing_new(self, tmp_path) -> None:
        """That tier has no `measure` stage, and the report says the questions were dropped."""
        entries = {q.name: "answered" for q in required_at("build")}
        root = _brief(tmp_path, tier="prototype", stage="build", **entries)
        results = root / "evals" / "results"
        results.mkdir(parents=True)
        (results / "v1.json").write_text('{"created_at": "2026-08-06T00:00:00Z"}')

        assert _fired(root) is False
        assert any(
            "The questions of `measure` are not required" in note for note in run_checks(root).notes
        )

    def test_the_report_says_where_the_stage_came_from(self, tmp_path) -> None:
        entries = {q.name: "answered" for q in required_at("shape")}
        found = run_checks(_brief(tmp_path, stage="shape", **entries))
        detail = [c for c in found.checks if c.entry_id == "FT-24"][0].detail

        assert detail is None or "shape" in detail


class TestTheBriefValidatesAStage:
    def test_a_stage_nobody_defined_is_refused(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\nstage = "shipping"\n')

        with pytest.raises(ConfigurationError, match="shape, build, measure"):
            Brief.read(tmp_path / "brief.toml")

    def test_a_deferral_to_something_that_is_not_a_stage_is_refused(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text(
            'tier = "prototype"\n\n[entries.budget]\nstatus = "deferred"\ndeferred_to = "someday"\n'
        )

        with pytest.raises(ConfigurationError, match="shape, build, measure"):
            Brief.read(tmp_path / "brief.toml")

    def test_a_brief_with_no_stage_is_still_valid(self, tmp_path) -> None:
        assert Brief.read(_brief(tmp_path) / "brief.toml").stage is None


class TestTheCommands:
    def test_questions_prints_the_stage_and_what_makes_each_answerable(self, capsys) -> None:
        assert main(["questions", "--stage", "shape"]) == 0
        out = capsys.readouterr().out

        assert "ground_truth" in out
        assert "scaffold:" in out
        assert "[entries.ground_truth]" in out

    def test_questions_names_the_source_a_coding_agent_can_record(self, capsys) -> None:
        """The honest option is only reachable if the surface a coding agent reads names it.

        `too_similar` in dogfood #4 was answered in the coding agent's own words and passed,
        because recording an answer was the only move the command described.
        """
        assert main(["questions", "--stage", "measure"]) == 0

        out = capsys.readouterr().out

        assert 'source = "coding_agent"' in out
        assert "FT-24" in out

    def test_questions_as_json_carries_every_field_a_gate_reads(self, capsys) -> None:
        assert main(["questions", "--stage", "build", "--json"]) == 0
        found = json.loads(capsys.readouterr().out)

        assert {q["name"] for q in found} == {q.name for q in questions_at("build")}
        assert all(
            set(q)
            == {"name", "title", "stage", "required", "re_asked_each_stage", "ask", "scaffold"}
            for q in found
        )

    def test_a_stage_that_does_not_exist_exits_two_and_names_the_ones_that_do(self, capsys) -> None:
        """It named none, which is the one refusal in the suite that said nothing to write."""
        assert main(["questions", "--stage", "shipping"]) == 2
        printed = capsys.readouterr().err

        assert all(stage in printed for stage in STAGES)

    def test_the_help_names_every_stage_that_can_be_passed(self, capsys) -> None:
        """`brainstorm` was absent from it, and it is the stage a new project is at."""
        with pytest.raises(SystemExit):
            main(["questions", "--help"])
        printed = capsys.readouterr().out

        assert all(stage in printed for stage in STAGES)

    @pytest.mark.parametrize("stage", STAGES)
    def test_every_stage_the_help_names_prints_its_questions(self, stage: str, capsys) -> None:
        assert main(["questions", "--stage", stage]) == 0

        assert capsys.readouterr().out.strip()

    def test_running_the_module_is_the_same_as_the_console_script(self) -> None:
        """`python -m simple_agents.cli check` used to import and exit 0 on every project."""
        import runpy

        with pytest.raises(SystemExit) as raised:
            runpy.run_module("simple_agents.cli", run_name="__main__")
        assert raised.value.code == 2  # no subcommand, so it prints help


class TestInit:
    def test_it_registers_the_procedure_where_a_neutral_harness_reads_it(self, tmp_path) -> None:
        assert main(["init", str(tmp_path)]) == 0

        skill = tmp_path / ".agents" / "skills" / "simple-agents" / "SKILL.md"
        assert skill.exists()
        assert skill.read_text(encoding="utf-8") == PROCEDURE.read_text(encoding="utf-8")

    def test_claude_code_gets_its_own_directory(self, tmp_path) -> None:
        assert main(["init", str(tmp_path), "--claude"]) == 0

        assert (tmp_path / ".claude" / "skills" / "simple-agents" / "SKILL.md").exists()

    def test_any_other_directory_can_be_named(self, tmp_path) -> None:
        assert main(["init", str(tmp_path), "--to", "vendor/skills"]) == 0

        assert (tmp_path / "vendor" / "skills" / "simple-agents" / "SKILL.md").exists()

    def test_a_copy_is_available_where_a_symlink_is_not(self, tmp_path) -> None:
        assert main(["init", str(tmp_path), "--copy"]) == 0
        skill = tmp_path / ".agents" / "skills" / "simple-agents" / "SKILL.md"

        assert not skill.is_symlink()
        assert skill.read_text(encoding="utf-8") == PROCEDURE.read_text(encoding="utf-8")

    def test_a_link_is_what_a_platform_that_allows_one_gets(self, tmp_path) -> None:
        """A link means the procedure tracks the installed version rather than going stale."""
        assert main(["init", str(tmp_path)]) == 0
        skill = tmp_path / ".agents" / "skills" / "simple-agents" / "SKILL.md"

        assert skill.is_symlink() or (skill.parent).is_symlink()

    def test_it_leaves_an_existing_installation_alone_and_says_it_did_nothing(
        self, tmp_path, capsys
    ) -> None:
        """The refusal exits 1: a command that did not do what was asked did not succeed."""
        main(["init", str(tmp_path)])
        capsys.readouterr()

        assert main(["init", str(tmp_path)]) == 1
        assert "already exists" in capsys.readouterr().err

    def test_a_re_run_restores_an_agents_file_that_was_deleted(self, tmp_path) -> None:
        """The refusal is about the skill directory, and the pointer is a separate file."""
        main(["init", str(tmp_path)])
        (tmp_path / "AGENTS.md").unlink()

        main(["init", str(tmp_path)])

        assert "SKILL.md" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

    def test_force_replaces_it(self, tmp_path, capsys) -> None:
        main(["init", str(tmp_path)])
        capsys.readouterr()

        assert main(["init", str(tmp_path), "--force"]) == 0
        assert "already exists" not in capsys.readouterr().out

    def test_it_names_the_procedure_in_the_file_every_harness_reads(self, tmp_path) -> None:
        main(["init", str(tmp_path)])

        assert "simple-agents" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

    def test_it_appends_rather_than_overwriting_a_project_s_own_notes(self, tmp_path) -> None:
        (tmp_path / "AGENTS.md").write_text("# House rules\n\nRun the linter.\n")
        main(["init", str(tmp_path)])
        found = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

        assert "House rules" in found
        assert "simple-agents" in found

    def test_it_does_not_write_the_same_note_twice(self, tmp_path) -> None:
        main(["init", str(tmp_path)])
        main(["init", str(tmp_path), "--force"])
        found = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

        assert found.count("## Simple Agents") == 1

    def test_the_note_can_be_declined(self, tmp_path) -> None:
        main(["init", str(tmp_path), "--no-agents-file"])

        assert not (tmp_path / "AGENTS.md").exists()


class TestTheNotePointsAtWhereTheSkillWent:
    """The note was one constant naming `.agents/skills/`, whatever the flags put there.

    Two of the four flag combinations wrote a path the project did not have, and the README's
    own quick start offers one of them on its second line.
    """

    @pytest.mark.parametrize(
        "flags,expected",
        [
            ([], ".agents/skills/simple-agents/SKILL.md"),
            (["--claude"], ".claude/skills/simple-agents/SKILL.md"),
            (["--to", "vendor/skills"], "vendor/skills/simple-agents/SKILL.md"),
            (["--copy"], ".agents/skills/simple-agents/SKILL.md"),
        ],
    )
    def test_the_path_it_names_is_the_path_that_exists(
        self, tmp_path, flags: list[str], expected: str
    ) -> None:
        assert main(["init", str(tmp_path), *flags]) == 0
        note = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

        assert f"`{expected}`" in note
        assert (tmp_path / expected).exists()

    def test_the_only_path_it_names_is_that_one(self, tmp_path) -> None:
        """A note naming both would leave the coding agent to pick, and one is dead."""
        main(["init", str(tmp_path), "--claude"])
        note = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

        assert ".agents/skills" not in note

    def test_registering_somewhere_else_moves_the_pointer(self, tmp_path) -> None:
        main(["init", str(tmp_path)])
        main(["init", str(tmp_path), "--claude"])
        note = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

        assert note.count("## Simple Agents") == 1
        assert ".claude/skills/simple-agents/SKILL.md" in note
        assert ".agents/skills" not in note

    def test_a_project_s_own_text_below_the_note_survives_the_move(self, tmp_path) -> None:
        main(["init", str(tmp_path)])
        note = tmp_path / "AGENTS.md"
        note.write_text(note.read_text(encoding="utf-8") + "\n## House rules\n\nRun the linter.\n")

        main(["init", str(tmp_path), "--claude"])
        found = note.read_text(encoding="utf-8")

        assert "Run the linter." in found
        assert found.count("## House rules") == 1
        assert ".claude/skills/simple-agents/SKILL.md" in found

    def test_an_install_line_naming_the_package_is_not_the_note(self, tmp_path) -> None:
        """The test was a substring search for `simple-agents` over the whole file, and the
        README's own install line supplies it."""
        (tmp_path / "AGENTS.md").write_text(
            "Install with: uv add simple-agents\n", encoding="utf-8"
        )

        main(["init", str(tmp_path)])
        found = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

        assert "uv add simple-agents" in found
        assert ".agents/skills/simple-agents/SKILL.md" in found


class TestACountSpelledBesideAListMatchesTheList:
    """Three shipped messages named a number and then printed a different number of things.

    The count is what a reader trusts when the list runs off the end of a terminal, and it is
    what nothing re-derives. Each message below is provoked and read.
    """

    NUMBERS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}

    def test_the_deferral_refusal_counts_the_stages_it_lists(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text(
            'tier = "prototype"\n\n[entries.budget]\nstatus = "deferred"\ndeferred_to = "someday"\n'
        )

        with pytest.raises(ConfigurationError) as caught:
            Brief.read(tmp_path / "brief.toml")

        assert f"the {self.NUMBERS[len(STAGES)]} stages are {', '.join(STAGES)}" in str(
            caught.value
        )

    def test_the_stage_refusal_counts_the_stages_it_lists(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\nstage = "shipping"\n')

        with pytest.raises(ConfigurationError) as caught:
            Brief.read(tmp_path / "brief.toml")

        assert f"the {self.NUMBERS[len(STAGES)]} are {', '.join(STAGES)}" in str(caught.value)

    def test_the_confirmation_refusal_counts_the_stages_it_lists(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text(
            'tier = "prototype"\nunderstanding_confirmed_at = "someday"\n'
        )

        with pytest.raises(ConfigurationError) as caught:
            Brief.read(tmp_path / "brief.toml")

        assert f"the {self.NUMBERS[len(STAGES)]} stages are {', '.join(STAGES)}" in str(
            caught.value
        )

    def test_the_command_s_stage_refusal_counts_them_too(self, capsys) -> None:
        main(["questions", "--stage", "shipping"])

        assert f"The {self.NUMBERS[len(STAGES)]} are {', '.join(STAGES)}" in capsys.readouterr().err

    def test_the_record_type_refusal_lists_every_type_and_spells_no_count(self, tmp_path) -> None:
        """It said "the four are" and listed five. The count is gone, so it cannot go stale."""
        from simple_agents.conformance.checks import RECORD_TYPES

        root = _brief(tmp_path)
        run = root / "runs" / "run_1"
        run.mkdir(parents=True)
        (run / "manifest.json").write_text('{"started_at": "2026-08-06T00:00:00Z"}')
        record = dict.fromkeys(COMMON_RECORD_FIELDS)
        record["record_type"] = "invented"
        (run / "trajectory.jsonl").write_text(json.dumps(record) + "\n")

        message = (
            [c for c in run_checks(root).checks if c.entry_id == "FT-13"][0].findings[0].message
        )

        assert f"the record types are {', '.join(sorted(RECORD_TYPES))}" in message
        assert not re.search(r"the (three|four|five|six) are", message)


class TestWhatHoldsTheSkill:
    """The skill is prose, so everything it names is checked against the thing it names.

    This docstring counted the pins until 2026-08-12, and the count was stale, which is the
    defect every test below exists to catch.
    """

    @property
    def text(self) -> str:
        return PROCEDURE.read_text(encoding="utf-8")

    def test_every_stage_names_the_question_its_gate_puts_again(self) -> None:
        """`DF5-L3`: `check` is named at every gate and ran; `report` at one and never did.

        A question re-asked at every stage is only re-asked where the stage says so, so this
        reads each stage section rather than the document as a whole.
        """
        re_asked = [q.name for q in QUESTIONS if q.re_asked_each_stage]
        sections = re.split(r"^## Stage \d+: ", self.text, flags=re.M)[1:]

        assert len(sections) == len(STAGES)
        for name in re_asked:
            missing = [one.splitlines()[0] for one in sections if f"Ask `{name}`" not in one]
            assert not missing, f"{name} is not asked at: {missing}"

    def test_the_number_of_built_in_tools_it_names_is_the_number_that_ship(self) -> None:
        """It said eight, then nine, while ten shipped: a count nothing reads goes stale.

        Counted off the return annotation rather than a list kept here, so a tool added to
        `simple_agents.builtins` is counted without anything being remembered.
        """
        spelled = {
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
        }
        named = re.search(r"(\w+) tools\s+come with it", self.text)

        assert named, "the skill no longer says how many tools ship"
        assert spelled[named.group(1)] == len(_tool_factories())

    def test_the_elicitation_scaffold_counts_the_tools_that_ship(self) -> None:
        """The `approaches` scaffold said thirteen while fourteen shipped.

        The same count as the two tests beside this one, on the third surface naming it.
        """
        from simple_agents.conformance.elicitation import QUESTIONS

        spelled = {
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
        }
        [approaches] = [question for question in QUESTIONS if question.name == "approaches"]
        named = re.search(r"(\w+) tools\b", approaches.scaffold)

        assert named, "the scaffold no longer says how many tools ship"
        assert spelled[named.group(1)] == len(_tool_factories())

    def test_the_built_in_set_it_counts_is_the_one_the_tools_document_lists(self) -> None:
        """Two documents naming one set, and the count was right in one of them."""
        section = (docs_path() / "tools.md").read_text(encoding="utf-8")
        section = section.split("## 4. The built-in set")[1].split("### 4.1")[0]
        rows = set(re.findall(r"^\| `([a-z_]+)` \|", section, re.M))

        assert rows == {tool.__name__ for tool in _tool_factories()}

    def test_the_question_counts_it_names_are_the_counts_at_that_stage(self) -> None:
        """It said fourteen at `brainstorm` while thirteen shipped, after two were added.

        The tool count above has been pinned since it went stale the same way. This one was
        not, so the sentence rotted when the stage gained questions. Each count is read
        against whichever stage the command above it names, so a stage that gains a sentence
        later is checked without anything being listed here.
        """
        spelled = {
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
            "twenty": 20,
            "twenty-one": 21,
            "twenty-two": 22,
            "twenty-three": 23,
            "twenty-nine": 29,
            "thirty-two": 32,
            "thirty-three": 33,
        }
        named = list(re.finditer(r"([\w-]+) questions, ([\w-]+) required", self.text))

        assert named, "the skill no longer says how many questions a stage asks"
        for sentence in named:
            preceding = re.findall(r"--stage (\w+)", self.text[: sentence.start()])
            assert preceding, f"{sentence.group(0)!r} names no stage above it"
            stage = preceding[-1]
            asked, required = sentence.group(1).lower(), sentence.group(2).lower()

            assert asked in spelled, f"{asked!r} is not a number this test can read"
            assert required in spelled, f"{required!r} is not a number this test can read"
            assert spelled[asked] == len(questions_at(stage)), stage
            assert spelled[required] == len(required_at(stage)), stage

    def test_it_is_under_the_word_budget(self) -> None:
        """A skill that restates the documents is a second copy of something that moves."""
        assert len(self.text.split()) <= WORD_BUDGET

    def test_it_carries_the_frontmatter_a_skill_needs(self) -> None:
        assert self.text.startswith("---\n")
        head = self.text.split("---", 2)[1]
        assert "name: simple-agents" in head
        assert "description:" in head

    def test_every_command_it_names_is_one_the_cli_has(self) -> None:
        """Read off the parser, so a command the CLI drops fails here rather than a list."""
        from simple_agents.cli.main import _parser

        [subcommands] = [
            action
            for action in _parser()._actions
            if getattr(action, "choices", None) and action.dest == "command"
        ]
        named = set(re.findall(r"simple-agents ([a-z-]+)", self.text))

        assert named
        assert named <= set(subcommands.choices)

    def test_every_stage_it_names_is_a_stage(self) -> None:
        """Read off `STAGES`, so adding a stage cannot leave this asserting the old list."""
        named = set(re.findall(rf"`({'|'.join(STAGES)})`", self.text))

        assert named == set(STAGES)

    def test_every_project_path_it_names_is_where_the_checks_look(self) -> None:
        assert f"`{DEFAULT_BRIEF}`" in self.text
        assert f"`{DEFAULT_RUNS}/`" in self.text
        assert f"{DEFAULT_RESULTS}/" in self.text

    def test_every_document_it_points_at_is_installed_beside_the_package(self) -> None:
        named = set(re.findall(r"`(docs/[a-z-]+\.md)`", self.text))

        assert named
        assert all((docs_path() / Path(name).name).exists() for name in named)

    def test_it_ships_at_both_paths_in_the_wheel(self) -> None:
        """One source file, two destinations, so the document and the skill cannot drift."""
        config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        assert '"docs" = "simple_agents/docs"' in config
        assert (
            '"docs/procedure.md" = "simple_agents/.agents/skills/simple-agents/SKILL.md"' in config
        )


def _fired(root: Path) -> bool:
    found = run_checks(root)
    return [c for c in found.checks if c.entry_id == "FT-24"][0].outcome is Outcome.FAILED


class TestTheTwoDefectsFiledAtTheSitting:
    """Both were measured at `dev-docs/build-logs/item10-build-log.md` §1.3 and §1.7,
    and filed rather than fixed there."""

    def test_a_pipeline_that_calls_no_model_has_no_model_to_pin(self, tmp_path) -> None:
        from simple_agents import Deterministic, Pipeline, RunEnvelope

        root = _brief(tmp_path, **{q.name: "answered" for q in required_at("build")})
        Pipeline([Deterministic(lambda i, c: {"a": 1}, node_id="n")]).run(
            {}, envelope=RunEnvelope(run_dir=root / "runs")
        )
        found = [c for c in run_checks(root).checks if c.entry_id == "FT-14"][0]

        assert found.outcome is Outcome.PASSED
        assert "made no model call" in (found.detail or "")

    def test_a_manifest_naming_no_model_after_a_model_call_still_fails(self, tmp_path) -> None:
        """`observed` is what happened, so a call with nothing pinned is the failure FT-14 is."""
        root = _brief(tmp_path)
        run = root / "runs" / "run_1"
        run.mkdir(parents=True)
        (run / "manifest.json").write_text(
            json.dumps(
                {
                    "started_at": "2026-08-06T00:00:00Z",
                    "models": {"configured": None, "observed": [{"calls": 1}]},
                }
            )
        )
        found = [c for c in run_checks(root).checks if c.entry_id == "FT-14"][0]

        assert found.outcome is Outcome.FAILED

    def test_a_run_directory_somewhere_else_is_named_rather_than_called_missing(
        self, tmp_path
    ) -> None:
        from simple_agents import Deterministic, Pipeline, RunEnvelope

        root = _brief(tmp_path)
        Pipeline([Deterministic(lambda i, c: {"a": 1}, node_id="n")]).run(
            {}, envelope=RunEnvelope(run_dir=root / "output")
        )
        message = (
            [c for c in run_checks(root).checks if c.entry_id == "FT-13"][0].findings[0].message
        )

        assert "a run was found at output/" in message
        assert "--run output/" in message

    def test_a_project_with_no_run_anywhere_says_only_that(self, tmp_path) -> None:
        """A manifest inside a virtualenv is not this project's run, so it is not walked."""
        root = _brief(tmp_path)
        buried = root / ".venv" / "lib" / "site-packages" / "somepkg"
        buried.mkdir(parents=True)
        (buried / "manifest.json").write_text("{}")

        message = (
            [c for c in run_checks(root).checks if c.entry_id == "FT-13"][0].findings[0].message
        )

        assert "no run directory under runs/`" in message
        assert "a run was found at" not in message


class TestAnEvaluationNamesItsDirectory:
    """`dev-docs/build-logs/item10-build-log.md` §5.3: the one part of an evaluation
    that was not reproducible from its seed."""

    def suite(self, matches=None, prompt=None):
        from pydantic import BaseModel

        from simple_agents import Budget, LLMNode, Maybe, Pipeline
        from simple_agents.evaluation import EvalSuite, Example, ExampleSet

        class Answer(BaseModel):
            answer: Maybe[str]

        pipeline = Pipeline(
            [
                LLMNode(
                    prompt or (lambda inputs, ctx: "answer it"),
                    output_schema=Answer,
                    node_id="hunt",
                )
            ],
            budget=Budget(max_steps=None, max_tokens=1000, max_cost=None, max_wall_clock_ms=1000),
        )
        examples = ExampleSet(
            [
                Example(id="q1", inputs={"q": "a"}, expected="a", split="dev"),
                Example(id="q2", inputs={"q": "b"}, expected="b", split="held_out"),
            ]
        )
        return EvalSuite(
            pipeline,
            examples,
            answer="answer",
            matches=matches or (lambda s: s.answer == s.expected),
            contamination_threshold=0.8,
        )

    def test_the_same_evaluation_names_the_same_directory(self) -> None:
        assert self.suite()._eval_id(41, "held_out", 3, None) == self.suite()._eval_id(
            41, "held_out", 3, None
        )

    def test_a_different_seed_names_a_different_one(self) -> None:
        suite = self.suite()

        assert suite._eval_id(41, "held_out", 3, None) != suite._eval_id(42, "held_out", 3, None)

    def test_a_different_split_or_k_names_a_different_one(self) -> None:
        suite = self.suite()

        assert suite._eval_id(41, "held_out", 3, None) != suite._eval_id(41, "dev", 3, None)
        assert suite._eval_id(41, "held_out", 3, None) != suite._eval_id(41, "held_out", 5, None)

    def test_an_edited_prompt_names_a_different_one(self) -> None:
        """Two versions compared against each other must not write into one directory."""
        before = self.suite(prompt=lambda inputs, ctx: "answer it")
        after = self.suite(prompt=lambda inputs, ctx: "answer it carefully")

        assert before._eval_id(41, "held_out", 3, None) != after._eval_id(41, "held_out", 3, None)

    def test_a_different_model_names_a_different_one(self) -> None:
        """Two arms of a model comparison must not write into one directory."""
        from simple_agents import FakeModelClient

        suite = self.suite()
        from simple_agents.models import ModelIdentity

        small = FakeModelClient(
            model_identity=ModelIdentity(
                backend="hosted_api", request_model="mistral-small-2603", model_revision=None
            )
        )
        medium = FakeModelClient(
            model_identity=ModelIdentity(
                backend="hosted_api", request_model="mistral-medium-2604", model_revision=None
            )
        )

        assert suite._eval_id(41, "held_out", 3, small) != suite._eval_id(41, "held_out", 3, medium)

    def test_it_looks_like_a_run_directory(self) -> None:
        assert re.fullmatch(r"eval_[0-9a-f]{12}", self.suite()._eval_id(41, "held_out", 3, None))


class TestWhatTheSkillTellsACodingAgentToDo:
    """Three instructions a build showed were missing, each held by a test.

    The word budget is what keeps the skill from restating the documents, so an instruction
    added here has to earn its place against something else being cut.
    """

    text = (Path(__file__).parent.parent / "docs" / "procedure.md").read_text()

    def test_it_asks_for_a_build_log(self) -> None:
        """Three builds were asked for one by hand. The fourth was not, and had none."""
        assert "BUILD-LOG.md" in self.text

    def test_it_puts_the_design_discussion_before_the_pipeline_is_written(self) -> None:
        """The decisions are settled where the code is written, not only named at the start."""
        build = self.text.split("## Stage 4: `build`")[1].split("## Stage 5")[0]

        flat = " ".join(build.split())

        assert "Agree how it will be built before writing it" in flat
        assert "`shape`, `constant` and `prompt_rule`" in flat

    def test_stage_three_reads_the_design_stage_two_agreed(self) -> None:
        """Stages 2 and 3 agree different things, and nothing compared them until 2026-08-17.

        Stage 2 settles what the agent does, stage 3 how it is built, and a node that cannot do
        what the design promised is a change to the design rather than a detail.
        """
        build = self.text.split("## Stage 4: `build`")[1].split("## Stage 5")[0]

        assert "design.md" in build
        assert "design_confirmed_at" in build

    def test_no_gate_enumerates_the_checks_it_expects(self) -> None:
        """A hand-written list of ids goes stale whenever a check is added, and four did.

        The gate names the command and what it should report. One id is a pointer to the check
        a stage is about, which is stage 5 naming FT-31; a list is a claim that rots.
        """
        for block in self.text.split("**Gate.**")[1:]:
            gate = block.split("\n\n")[0]

            assert len(re.findall(r"FT-\d\d", gate)) <= 1, gate

    def test_it_asks_what_an_agent_doing_nothing_would_score(self) -> None:
        """A build passed every gate twice with a measure that could not detect its effect."""
        measure = self.text.split("## Stage 5: `measure`")[1]

        assert "an agent\nthat did nothing would score" in measure or (
            "agent that did nothing would score" in measure.replace("\n", " ")
        )


class TestTheDecisionKindsCommand:
    """`simple-agents questions --decisions` is how a coding agent finds the six."""

    def test_it_prints_every_kind_with_what_to_ask(self, capsys) -> None:
        assert main(["questions", "--decisions"]) == 0

        printed = capsys.readouterr().out
        for entry in DECISION_KINDS:
            assert entry.name in printed
            assert entry.ask in printed

    def test_as_json_it_carries_the_same(self, capsys) -> None:
        assert main(["questions", "--decisions", "--json"]) == 0

        parsed = json.loads(capsys.readouterr().out)
        assert [entry["name"] for entry in parsed] == list(kind_names())
        assert all(entry["covers"] and entry["example"] for entry in parsed)


class TestTheInvolvementQuestion:
    """The dial the builder sets before any design happens."""

    def test_it_is_required_at_the_first_stage(self) -> None:
        assert question("involvement").stage == "brainstorm"
        assert question("involvement").required

    def test_it_offers_two_granularities_and_says_what_it_does_not_move(self) -> None:
        """It sets how coarsely the six kinds are put to the builder, not whether."""
        scaffold = question("involvement").scaffold

        assert "each decision as it arises" in scaffold
        assert "a batch put at the point" in scaffold
        assert "not whether" in scaffold
        assert "FT-30" in scaffold

    def test_a_review_after_the_code_is_not_on_offer(self) -> None:
        """One project answered "batch at each stage gate", where the code is already written.

        A decision put then costs a rebuild to change, so the review is a formality, and
        FT-30 cannot tell agreement from a rubber stamp.
        """
        scaffold = question("involvement").scaffold

        assert "before the thing it decides is built" in scaffold
        assert "That is not a choice" in scaffold
        assert "stage gate" not in scaffold

    def test_a_decision_found_mid_build_is_not_held_for_a_batch(self) -> None:
        """Writing the code is where a threshold or a prompt rule is discovered."""
        assert "not held for the next batch" in question("involvement").scaffold

    def test_the_two_expensive_kinds_are_never_batched(self) -> None:
        scaffold = question("involvement").scaffold

        assert "`dependency` and `shape` are put on their own" in scaffold


class TestThePresentationQuestion:
    def test_it_is_required_at_shape_where_it_changes_the_output_schema(self) -> None:
        assert question("presentation").stage == "shape"
        assert question("presentation").required
        assert "output schema" in question("presentation").scaffold


class TestTheTierAndTheStagesItHas:
    """The collision the ship sitting resolved: a report that asked for what it did not check."""

    def test_a_stage_the_tier_does_not_have_is_refused(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\nstage = "measure"\n')

        with pytest.raises(ConfigurationError) as caught:
            Brief.read(tmp_path / "brief.toml")

        assert 'tier = "evaluated"' in str(caught.value)
        assert 'stage = "build"' in str(caught.value)

    def test_the_same_stage_at_a_tier_that_has_it_is_read(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "evaluated"\nstage = "measure"\n')

        assert Brief.read(tmp_path / "brief.toml").stage == "measure"

    def test_every_tier_has_ship(self, tmp_path) -> None:
        (tmp_path / "brief.toml").write_text('tier = "prototype"\nstage = "ship"\n')

        assert Brief.read(tmp_path / "brief.toml").stage == "ship"

    def test_a_deferral_to_a_stage_the_tier_never_reaches_is_refused(self, tmp_path) -> None:
        """An answer deferred to a stage that never arrives never has to be given."""
        (tmp_path / "brief.toml").write_text(
            'tier = "prototype"\n\n[entries.prices]\nstatus = "deferred"\ndeferred_to = "measure"\n'
        )

        with pytest.raises(ConfigurationError) as caught:
            Brief.read(tmp_path / "brief.toml")

        assert "never reaches 'measure'" in str(caught.value)
        assert 'Defer it to "ship"' in str(caught.value)

    def test_the_ship_questions_are_required_at_ship_whatever_the_tier(self) -> None:
        prototype = {q.name for q in required_at("ship", "prototype")}
        evaluated = {q.name for q in required_at("ship", "evaluated")}
        ship = {"someone_there", "live_records", "watching_live", "stored_output"}

        assert ship <= prototype
        assert ship <= evaluated
        assert evaluated - prototype == {q.name for q in required_at("measure") if q.required} - {
            q.name for q in required_at("build")
        }

    def test_a_prototype_is_never_asked_the_measure_questions(self) -> None:
        asked = {q.name for q in questions_at("ship", "prototype")}

        assert not asked & {q.name for q in QUESTIONS if q.stage == "measure"}

    def test_the_command_can_be_given_a_tier(self, capsys) -> None:
        main(["questions", "--stage", "ship", "--tier", "prototype"])
        printed = capsys.readouterr().out

        # The heading is the question named for a builder; the key is on its own line.
        assert "[ship] Whether anyone is there" in printed
        assert "key:      someone_there" in printed
        assert "[measure]" not in printed

    def test_the_command_refuses_a_tier_nobody_defined(self, capsys) -> None:
        assert main(["questions", "--stage", "ship", "--tier", "gold"]) == 2
        assert "is not a tier" in capsys.readouterr().err


class TestWhereAnAnswerCameFrom:
    """`DF4-D2` and dogfood #4's `too_similar`: the coding agent's own words, recorded as an
    answer, passing the gate. `source` is how an entry says so, and FT-24 fails on it."""

    def _root(self, tmp_path: Path, source: str | None) -> Path:
        entries = {q.name: "answered" for q in required_at("build")}
        root = _brief(tmp_path, stage="build", **entries)
        brief = root / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        if source is not None:
            text = text.replace(
                f'[entries.budget]\nstatus = "answered"\nrecorded_at = "{STAMP}"',
                f'[entries.budget]\nstatus = "answered"\nrecorded_at = "{STAMP}"\n'
                f'source = "{source}"',
            )
        brief.write_text(text, encoding="utf-8")
        return root

    def test_an_answer_the_builder_has_not_seen_fails_the_gate(self, tmp_path) -> None:
        assert _fired(self._root(tmp_path, "coding_agent")) is True

    def test_an_answer_out_of_the_research_does_not(self, tmp_path) -> None:
        """A research finding put to the builder and agreed is their answer."""
        assert _fired(self._root(tmp_path, "research")) is False

    def test_an_entry_with_no_source_is_the_builder_s(self, tmp_path) -> None:
        assert _fired(self._root(tmp_path, None)) is False

    def test_a_source_outside_the_four_is_refused_by_name(self, tmp_path) -> None:
        root = self._root(tmp_path, "somebody")

        with pytest.raises(ConfigurationError, match="The four are"):
            Brief.read(root / "brief.toml")


class TestTheQuestionEveryGatePutsAgain:
    """`DF5-D9`: none of the questions was open-ended, and the builder's own wish arrived
    after the last gate. `anything_else` is the one question the builder owns, and it is put
    again at every stage. `understanding_confirmed_at` dates a document that way; this dates
    a question, and the entry's `asked_at` is where the date lives."""

    def _root(self, tmp_path: Path, asked_at: str | None, stage: str = "build") -> Path:
        entries = {q.name: "answered" for q in required_at(stage)}
        root = _brief(tmp_path, stage=stage, **entries)
        brief = root / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        line = (
            f'[entries.anything_else]\nstatus = "answered"\n'
            f'recorded_at = "{STAMP}"\nasked_at = "{stage}"'
        )
        # The helper writes the date at the declared stage, so a test that moves it has to
        # find that line. Asserting it changed is what stops a rename passing every case.
        assert line in text
        if asked_at is None:
            text = text.replace(
                line, f'[entries.anything_else]\nstatus = "answered"\nrecorded_at = "{STAMP}"'
            )
        else:
            text = text.replace(
                line,
                f'[entries.anything_else]\nstatus = "answered"\nrecorded_at = "{STAMP}"\n'
                f'asked_at = "{asked_at}"',
            )
        assert text != brief.read_text(encoding="utf-8") or asked_at == stage
        brief.write_text(text, encoding="utf-8")
        return root

    def test_exactly_one_question_is_put_again(self) -> None:
        assert [q.name for q in QUESTIONS if q.re_asked_each_stage] == ["anything_else"]

    def test_it_is_required_at_every_stage(self) -> None:
        assert all("anything_else" in {q.name for q in required_at(s)} for s in STAGES)

    def test_it_is_the_last_question_printed_at_every_stage(self) -> None:
        """It is asked after the stage's own questions, so it prints after them."""
        assert all(questions_at(s)[-1].name == "anything_else" for s in STAGES)

    def test_an_answer_dated_at_this_stage_settles_it(self, tmp_path) -> None:
        assert _fired(self._root(tmp_path, "build")) is False

    def test_an_answer_dated_at_an_earlier_stage_fails(self, tmp_path) -> None:
        """The answer is there and the question was not put again at this stage."""
        assert _fired(self._root(tmp_path, "shape")) is True

    def test_an_answer_dated_later_settles_it(self, tmp_path) -> None:
        """Nothing moves a project backwards, so a date ahead of it is not stale."""
        assert _fired(self._root(tmp_path, "ship")) is False

    def test_an_answer_with_no_date_fails(self, tmp_path) -> None:
        assert _fired(self._root(tmp_path, None)) is True

    def test_the_failure_names_the_entry_and_what_makes_it_count(self, tmp_path) -> None:
        found = run_checks(self._root(tmp_path, "shape"))
        message = [c for c in found.checks if c.entry_id == "FT-24"][0].findings[0].message

        assert "anything_else" in message
        assert "asked_at" in message

    def test_the_failure_does_not_send_the_reader_at_a_deferral_it_would_refuse(
        self, tmp_path
    ) -> None:
        """The message offers a deferral for every other entry, and `Brief.read` refuses one
        here, so it has to say which entries that offer covers."""
        found = run_checks(self._root(tmp_path, "shape"))
        message = [c for c in found.checks if c.entry_id == "FT-24"][0].findings[0].message

        assert "takes no deferral" in message

    def test_a_date_that_is_not_a_stage_is_refused_by_name(self, tmp_path) -> None:
        root = self._root(tmp_path, "yesterday")

        with pytest.raises(ConfigurationError, match="was asked at 'yesterday'"):
            Brief.read(root / "brief.toml")

    def test_deferring_it_is_refused(self, tmp_path) -> None:
        """There is no later stage to defer it to: a deferral silences it for good."""
        (tmp_path / "brief.toml").write_text(
            'tier = "prototype"\nstage = "build"\n\n'
            '[entries.anything_else]\nstatus = "deferred"\ndeferred_to = "ship"\n',
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="every gate puts again"):
            Brief.read(tmp_path / "brief.toml")

    def test_a_date_on_an_ordinary_entry_is_recorded_and_gates_nothing(self, tmp_path) -> None:
        entries = {q.name: "answered" for q in required_at("build")}
        root = _brief(tmp_path, stage="build", **entries)
        brief = root / "brief.toml"
        brief.write_text(
            brief.read_text(encoding="utf-8").replace(
                f'[entries.budget]\nstatus = "answered"\nrecorded_at = "{STAMP}"',
                f'[entries.budget]\nstatus = "answered"\nrecorded_at = "{STAMP}"\n'
                f'asked_at = "brainstorm"',
            ),
            encoding="utf-8",
        )

        assert Brief.read(brief).entry("budget").asked_at == "brainstorm"
        assert _fired(root) is False

    def test_the_command_prints_the_key_to_write_at_the_stage_asked_for(self, capsys) -> None:
        assert main(["questions", "--stage", "shape"]) == 0
        printed = capsys.readouterr().out

        assert 'asked_at = "shape"' in printed
        assert "asked again at every stage" in printed

    def test_the_scaffold_says_that_nothing_is_an_answer(self) -> None:
        """A blank and *nothing* are different states, and the gate reads only the blank."""
        assert "nothing" in question("anything_else").scaffold.lower()


class TestAgencyIsAskedAsAWant:
    """`DF5-D9`: the scaffold framed agency as a cost to justify, and no question asked what
    the builder wanted the agent to do on its own. The builder's answer to that arrived after
    `ship`, in their own words, as the thing they wanted to start with."""

    def test_it_asks_what_the_builder_would_like_before_naming_a_node_kind(self) -> None:
        asked = question("agency_boundary")

        assert "would the builder like" in asked.ask
        assert asked.ask.index("work out for itself") < asked.ask.index("told")

    def test_it_is_an_answer_about_what_is_wanted(self) -> None:
        """So a `shape` decision names it under `from`, and the report says when none does."""
        assert question("agency_boundary").about_what_is_wanted is True

    def test_the_scaffold_still_reaches_the_node_kinds(self) -> None:
        """The want is written down first; the reading back into node kinds is what follows."""
        scaffold = question("agency_boundary").scaffold

        assert "AgentNode" in scaffold and "FT-11" in scaffold
        assert scaffold.index("in the terms of their own") < scaffold.index("AgentNode")

    def test_it_is_put_together_with_consultation(self) -> None:
        """What a step settles alone and what it takes to a person are one conversation."""
        assert "agency_boundary" in question("consultation").scaffold
        assert "check with a person" in question("agency_boundary").scaffold
        assert question("consultation").stage == question("agency_boundary").stage


class TestWhatTheCommandTellsTheCodingAgentToWrite:
    """`questions` prints the line to write, so a required key missing from it is a brief
    the library refuses on its own instruction. Found at `P3-47`'s cycle 4."""

    def _printed(self, *args: str) -> str:
        import contextlib
        import io

        from simple_agents.cli import main

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["questions", *args])
        return out.getvalue()

    def test_the_entry_line_names_every_key_an_answered_entry_needs(self) -> None:
        printed = self._printed("--stage", "brainstorm")

        for line in [l for l in printed.splitlines() if l.strip().startswith("record:")]:
            assert 'status = "answered"' in line
            assert "recorded_at" in line

    def test_the_decision_preamble_names_it_too(self) -> None:
        assert "recorded_at" in self._printed("--decisions")

    def test_an_entry_written_the_way_it_says_reads_back(self, tmp_path) -> None:
        """Copy the printed shape and the brief reads back."""
        (tmp_path / "brief.toml").write_text(
            f'tier = "prototype"\n\n[entries.what_it_does]\nstatus = "answered", \n'
            f'recorded_at = "{STAMP}"\nanswer = "it reads the export"\n'.replace(", \n", "\n"),
            encoding="utf-8",
        )

        assert Brief.read(tmp_path / "brief.toml").entry("what_it_does").recorded_at == STAMP
