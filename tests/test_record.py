"""`simple-agents record`: an answer or a decision written into the brief, stamped by the clock.

Dogfood #6 wrote twenty of thirty-three stamps by hand in local time with a UTC suffix.
What is tested here is that the writer reads the clock, replaces one table and
nothing else, refuses what the brief would refuse before touching the file, and that FT-44
fires on a stamp ahead of the clock and stays quiet on one behind it.
"""

from __future__ import annotations

import re
import shutil
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from simple_agents.cli.main import main
from simple_agents.conformance import Brief, Outcome, record_answer, record_decision, run_checks
from simple_agents.conformance.checks import STAMP_TOLERANCE_S
from simple_agents.errors import ConfigurationError

PROJECTS = Path(__file__).parent / "fixtures" / "projects"
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def conforming(tmp_path: Path) -> Path:
    source = PROJECTS / "conforming"
    if not source.exists():
        pytest.skip("no conforming fixture; run scripts/build_conformance_fixtures.py")
    shutil.copytree(source, tmp_path / "conforming")
    return tmp_path / "conforming"


def minimal(tmp_path: Path) -> Path:
    """A brief holding a tier and a stage and nothing else."""
    brief = tmp_path / "brief.toml"
    brief.write_text('tier = "evaluated"\nstage = "measure"\n', encoding="utf-8")
    return brief


def _table(text: str, header: str) -> str:
    """The lines of one table, header to the blank line before the next."""
    start = text.index(f"[{header}]")
    rest = text[start:]
    end = rest.find("\n\n[")
    return rest if end < 0 else rest[:end]


class TestTheStampIsRead:
    def test_an_answer_is_stamped_from_the_clock_in_utc(self, tmp_path) -> None:
        brief = conforming(tmp_path) / "brief.toml"
        before = datetime.now(timezone.utc).replace(microsecond=0)

        written = record_answer(brief, "used_through", answer="A phone app over an HTTP API.")

        assert STAMP.match(written.recorded_at)
        stamped = datetime.fromisoformat(written.recorded_at.replace("Z", "+00:00"))
        assert before <= stamped <= datetime.now(timezone.utc) + timedelta(seconds=1)
        entry = Brief.read(brief).entry("used_through")
        assert entry is not None
        assert entry.recorded_at == written.recorded_at
        assert entry.answer == "A phone app over an HTTP API."

    def test_a_decision_is_stamped_the_same_way(self, tmp_path) -> None:
        brief = conforming(tmp_path) / "brief.toml"

        written = record_decision(
            brief,
            "pool_size",
            kind="constant",
            status="agreed",
            chose="200",
            considered=["60, the first guess"],
            produces=["CANDIDATES_RETRIEVED"],
            rests_on=["presentation"],
            because="the audit measured recall at 200",
        )

        assert STAMP.match(written.recorded_at)
        assert written.table == "decisions.pool_size" and not written.replaced
        [decision] = [d for d in Brief.read(brief).decisions if d.name == "pool_size"]
        assert decision.kind == "constant" and decision.status == "agreed"
        assert decision.produces == ("CANDIDATES_RETRIEVED",)
        assert decision.rests_on == ("presentation",)
        assert decision.considered == ("60, the first guess",)
        assert decision.recorded_at == written.recorded_at


class TestOneTableMovesAndNothingElse:
    def test_replacing_a_table_leaves_every_other_byte(self, tmp_path) -> None:
        brief = conforming(tmp_path) / "brief.toml"
        before = brief.read_text(encoding="utf-8")

        written = record_answer(brief, "used_through", answer="Rewritten.")

        after = brief.read_text(encoding="utf-8")
        assert written.replaced
        assert after.replace(_table(after, "entries.used_through"), "") == before.replace(
            _table(before, "entries.used_through"), ""
        )

    def test_a_key_the_call_did_not_name_is_kept(self, tmp_path) -> None:
        brief = conforming(tmp_path) / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        brief.write_text(
            text.replace(
                "[entries.used_through]\n",
                '[entries.used_through]\nconfirmed_against = "sha256:kept"\n',
                1,
            ),
            encoding="utf-8",
        )

        record_answer(brief, "used_through", answer="Rewritten.")

        raw = tomllib.loads(brief.read_text(encoding="utf-8"))
        assert raw["entries"]["used_through"]["confirmed_against"] == "sha256:kept"
        assert raw["entries"]["used_through"]["answer"] == "Rewritten."

    def test_a_new_table_is_appended_and_read_back(self, tmp_path) -> None:
        brief = minimal(tmp_path)
        before = brief.read_text(encoding="utf-8")

        written = record_answer(brief, "budget", status="deferred", deferred_to="measure")

        after = brief.read_text(encoding="utf-8")
        assert not written.replaced
        assert after.startswith(before.rstrip("\n"))
        entry = Brief.read(brief).entry("budget")
        assert entry is not None and entry.status == "deferred" and entry.deferred_to == "measure"

    def test_a_multi_line_answer_round_trips_with_quotes_and_backslashes(self, tmp_path) -> None:
        brief = conforming(tmp_path) / "brief.toml"
        text = (
            'line one\nline two, a "quote", a """triple""" and a \\ backslash\n[not a header]\nlast'
        )

        record_answer(brief, "used_through", answer=text)
        entry = Brief.read(brief).entry("used_through")

        assert entry is not None and entry.answer == text

    def test_a_line_opening_a_bracket_inside_an_answer_is_not_the_next_table(
        self, tmp_path
    ) -> None:
        brief = conforming(tmp_path) / "brief.toml"
        record_answer(
            brief, "used_through", answer="first\n[entries.what_it_does] is not here\nlast"
        )

        record_answer(brief, "used_through", answer="second")

        raw = tomllib.loads(brief.read_text(encoding="utf-8"))
        assert raw["entries"]["used_through"]["answer"] == "second"
        assert raw["entries"]["what_it_does"]["answer"].startswith("It answers")

    def test_a_header_with_a_trailing_comment_is_the_same_table(self, tmp_path) -> None:
        brief = conforming(tmp_path) / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        brief.write_text(
            text.replace("[entries.used_through]\n", "[entries.used_through]  # the surface\n", 1),
            encoding="utf-8",
        )

        written = record_answer(brief, "used_through", answer="Rewritten.")

        assert written.replaced
        raw = tomllib.loads(brief.read_text(encoding="utf-8"))
        assert raw["entries"]["used_through"]["answer"] == "Rewritten."

    def test_a_re_asked_question_needs_the_stage_it_was_asked_at(self, tmp_path) -> None:
        brief = minimal(tmp_path)

        with pytest.raises(ConfigurationError, match="asked_at"):
            record_answer(brief, "anything_else", answer="Nothing.")
        written = record_answer(brief, "anything_else", answer="Nothing.", asked_at="measure")

        entry = Brief.read(brief).entry("anything_else")
        assert entry is not None and entry.asked_at == "measure"
        assert written.recorded_at == entry.recorded_at


class TestWhatIsRefusedBeforeTheFileIsTouched:
    def test_a_name_that_is_not_a_question(self, tmp_path) -> None:
        brief = conforming(tmp_path) / "brief.toml"
        before = brief.read_text(encoding="utf-8")

        with pytest.raises(ConfigurationError, match="is not a question"):
            record_answer(brief, "nonsense", answer="x")

        assert brief.read_text(encoding="utf-8") == before

    def test_an_answered_entry_with_no_answer(self, tmp_path) -> None:
        brief = minimal(tmp_path)
        with pytest.raises(ConfigurationError, match="no answer"):
            record_answer(brief, "budget")

    def test_a_status_a_stage_and_a_source_outside_the_known_ones(self, tmp_path) -> None:
        brief = conforming(tmp_path) / "brief.toml"
        with pytest.raises(ConfigurationError, match="status="):
            record_answer(brief, "budget", status="maybe", answer="x")
        with pytest.raises(ConfigurationError, match="is not a stage"):
            record_answer(brief, "budget", status="deferred", deferred_to="later")
        with pytest.raises(ConfigurationError, match="source="):
            record_answer(brief, "budget", answer="x", source="me")

    def test_a_deferral_to_a_stage_the_tier_never_reaches_is_refused_by_the_brief(
        self, tmp_path
    ) -> None:
        """The file is re-read as a brief before it is written, so the brief's own refusals hold."""
        root = conforming(tmp_path)
        brief = root / "brief.toml"
        text = brief.read_text(encoding="utf-8")
        brief.write_text(
            text.replace('tier = "evaluated"', 'tier = "prototype"').replace(
                'stage = "measure"', 'stage = "build"'
            ),
            encoding="utf-8",
        )
        before = brief.read_text(encoding="utf-8")

        with pytest.raises(ConfigurationError, match="nothing was written"):
            record_answer(brief, "budget", status="deferred", deferred_to="measure")

        assert brief.read_text(encoding="utf-8") == before

    def test_a_decision_kind_status_and_from_are_checked(self, tmp_path) -> None:
        brief = conforming(tmp_path) / "brief.toml"
        with pytest.raises(ConfigurationError, match="no decision kind"):
            record_decision(brief, "x", kind="whim")
        with pytest.raises(ConfigurationError, match="status="):
            record_decision(brief, "x", kind="constant", status="maybe")
        with pytest.raises(ConfigurationError, match="rests_on names"):
            record_decision(brief, "x", kind="constant", rests_on=["states"])
        with pytest.raises(ConfigurationError, match="cannot name a decision"):
            record_decision(brief, "a b", kind="constant")

    def test_a_missing_brief(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError, match="No brief"):
            record_answer(tmp_path / "brief.toml", "budget", answer="x")


class TestTheCommand:
    def test_record_answer_from_a_flag(self, tmp_path, capsys) -> None:
        root = conforming(tmp_path)

        status = main(
            [
                "record",
                "answer",
                "used_through",
                "--brief",
                str(root / "brief.toml"),
                "--text",
                "A phone app.",
            ]
        )

        assert status == 0
        out = capsys.readouterr().out
        assert "replaced [entries.used_through]" in out and "recorded_at 2" in out
        entry = Brief.read(root / "brief.toml").entry("used_through")
        assert entry is not None and entry.answer == "A phone app."

    def test_record_answer_from_a_file_and_a_deferral(self, tmp_path, capsys) -> None:
        root = conforming(tmp_path)
        (tmp_path / "answer.md").write_text("From a file.\nTwo lines.\n", encoding="utf-8")

        assert (
            main(
                [
                    "record",
                    "answer",
                    "budget",
                    "--brief",
                    str(root / "brief.toml"),
                    "--file",
                    str(tmp_path / "answer.md"),
                ]
            )
            == 0
        )
        assert (
            main(
                [
                    "record",
                    "answer",
                    "leakage",
                    "--brief",
                    str(root / "brief.toml"),
                    "--status",
                    "deferred",
                    "--deferred-to",
                    "ship",
                ]
            )
            == 0
        )

        brief = Brief.read(root / "brief.toml")
        assert brief.entry("budget").answer == "From a file.\nTwo lines."
        assert brief.entry("leakage").deferred_to == "ship"
        assert "[entries.budget]" in capsys.readouterr().out

    def test_record_decision(self, tmp_path, capsys) -> None:
        root = conforming(tmp_path)

        status = main(
            [
                "record",
                "decision",
                "pool_size",
                "--brief",
                str(root / "brief.toml"),
                "--kind",
                "constant",
                "--status",
                "agreed",
                "--chose",
                "200",
                "--considered",
                "60",
                "--considered",
                "400",
                "--produces",
                "CANDIDATES_RETRIEVED",
                "--from",
                "presentation",
                "--because",
                "the audit",
            ]
        )

        assert status == 0
        [decision] = [d for d in Brief.read(root / "brief.toml").decisions if d.name == "pool_size"]
        assert decision.considered == ("60", "400")
        assert decision.rests_on == ("presentation",)

    def test_a_refusal_is_printed_and_exits_2(self, tmp_path, capsys) -> None:
        root = conforming(tmp_path)

        status = main(
            ["record", "answer", "nonsense", "--brief", str(root / "brief.toml"), "--text", "x"]
        )

        assert status == 2
        assert "is not a question" in capsys.readouterr().err

    def test_record_alone_prints_help_and_exits_2(self, capsys) -> None:
        with pytest.raises(SystemExit):
            main(["record"])


class TestFT44:
    def test_the_conforming_project_passes(self, tmp_path) -> None:
        root = conforming(tmp_path)
        [result] = [c for c in run_checks(root).checks if c.entry_id == "FT-44"]

        assert result.outcome is Outcome.PASSED
        assert "none ahead of the clock" in (result.detail or "")

    def test_a_stamp_ahead_of_the_clock_fails_and_is_named(self, tmp_path) -> None:
        root = conforming(tmp_path)
        brief = root / "brief.toml"
        ahead = (
            (datetime.now(timezone.utc) + timedelta(seconds=STAMP_TOLERANCE_S + 3600))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        text = brief.read_text(encoding="utf-8")
        table = _table(text, "entries.used_through")
        brief.write_text(
            text.replace(
                table, re.sub(r'recorded_at = "[^"]+"', f'recorded_at = "{ahead}"', table)
            ),
            encoding="utf-8",
        )

        [result] = [c for c in run_checks(root).checks if c.entry_id == "FT-44"]

        assert result.outcome is Outcome.FAILED
        message = result.findings[0].message
        assert "entries.used_through" in message and ahead in message
        assert "simple-agents record answer" in message

    def test_a_stamp_inside_the_tolerance_passes(self, tmp_path) -> None:
        root = conforming(tmp_path)
        brief = root / "brief.toml"
        soon = (
            (datetime.now(timezone.utc) + timedelta(seconds=STAMP_TOLERANCE_S - 60))
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        text = brief.read_text(encoding="utf-8")
        table = _table(text, "entries.used_through")
        brief.write_text(
            text.replace(table, re.sub(r'recorded_at = "[^"]+"', f'recorded_at = "{soon}"', table)),
            encoding="utf-8",
        )

        [result] = [c for c in run_checks(root).checks if c.entry_id == "FT-44"]

        assert result.outcome is Outcome.PASSED

    def test_what_the_writer_wrote_passes_it(self, tmp_path) -> None:
        root = conforming(tmp_path)
        record_answer(root / "brief.toml", "used_through", answer="A phone app.")
        record_decision(
            root / "brief.toml", "pool_size", kind="constant", status="agreed", chose="200"
        )

        [result] = [c for c in run_checks(root).checks if c.entry_id == "FT-44"]

        assert result.outcome is Outcome.PASSED


class TestTheKeysAboveTheTables:
    def test_a_key_already_there_is_replaced_in_place(self, tmp_path) -> None:
        from simple_agents.conformance import record_key

        brief = conforming(tmp_path) / "brief.toml"
        before = brief.read_text(encoding="utf-8")

        written = record_key(brief, "stage", "ship")

        after = brief.read_text(encoding="utf-8")
        assert written.replaced and written.table == "stage" and written.recorded_at == ""
        assert after.replace('stage = "ship"', 'stage = "measure"', 1) == before
        assert Brief.read(brief).stage == "ship"

    def test_a_key_not_there_lands_after_the_last_top_level_key(self, tmp_path) -> None:
        from simple_agents.conformance import record_key

        brief = minimal(tmp_path)

        record_key(brief, "design_confirmed_at", "shape")
        record_key(brief, "comments_block_gates", True)

        text = brief.read_text(encoding="utf-8")
        assert text == (
            'tier = "evaluated"\nstage = "measure"\ndesign_confirmed_at = "shape"\n'
            "comments_block_gates = true\n"
        )
        read = Brief.read(brief)
        assert read.design_confirmed_at == "shape" and read.comments_block_gates is True

    def test_what_the_brief_refuses_is_refused_and_nothing_written(self, tmp_path) -> None:
        from simple_agents.conformance import record_key

        brief = minimal(tmp_path)
        before = brief.read_text(encoding="utf-8")
        with pytest.raises(ConfigurationError, match="is not a key"):
            record_key(brief, "answer", "x")
        with pytest.raises(ConfigurationError, match="nothing was written"):
            record_key(brief, "stage", "later")
        with pytest.raises(ConfigurationError, match="names no file"):
            record_key(brief, "results", "evals/results/missing.json")
        with pytest.raises(ConfigurationError, match="not a fingerprint"):
            record_key(brief, "confirmed_against", "abc")
        with pytest.raises(ConfigurationError, match="true or false"):
            record_key(brief, "comments_block_gates", "yes")
        assert brief.read_text(encoding="utf-8") == before

    def test_a_shape_is_merged_into_the_table(self, tmp_path) -> None:
        from simple_agents.conformance import record_shape

        brief = minimal(tmp_path)
        record_shape(brief, "triage", "sha256:aaaa")
        record_shape(brief, "recommend", "sha256:bbbb")
        record_shape(brief, "triage", "sha256:cccc")

        read = Brief.read(brief)
        assert read.confirmed_shape("triage") == "sha256:cccc"
        assert read.confirmed_shape("recommend") == "sha256:bbbb"
        with pytest.raises(ConfigurationError, match="not a fingerprint"):
            record_shape(brief, "triage", "cccc")

    def test_the_newest_run_gives_the_stamps_the_checks_compare_to(self, tmp_path) -> None:
        from simple_agents.conformance import newest_run_fingerprints
        from simple_agents.conformance.checks import current_fingerprint
        from simple_agents.conformance.artifacts import Artifacts

        root = conforming(tmp_path)
        stamp, shape, run = newest_run_fingerprints(root)

        assert stamp == current_fingerprint(Artifacts.discover(root))[0]
        assert shape.startswith("sha256:") and run.is_dir()
        with pytest.raises(ConfigurationError, match="No run"):
            newest_run_fingerprints(tmp_path)

    def test_the_command_forms(self, tmp_path, capsys) -> None:
        root = conforming(tmp_path)
        brief = str(root / "brief.toml")

        assert main(["record", "set", "stage", "ship", "--brief", brief]) == 0
        assert main(["record", "confirmed", "design", "--at", "ship", "--brief", brief]) == 0
        assert main(["record", "read-against", "--brief", brief]) == 0
        assert main(["record", "shape", "triage", "--stamp", "sha256:dddd", "--brief", brief]) == 0
        assert main(["record", "set", "comments_block_gates", "true", "--brief", brief]) == 0
        assert main(["record", "set", "comments_block_gates", "yes", "--brief", brief]) == 2

        read = Brief.read(root / "brief.toml")
        assert read.stage == "ship" and read.design_confirmed_at == "ship"
        assert read.confirmed_against.startswith("sha256:")
        assert read.confirmed_shape("triage") == "sha256:dddd"
        assert read.comments_block_gates is True
        out = capsys.readouterr()
        assert "replaced [stage]" in out.out and "recorded_at" not in out.out
        assert "true or false" in out.err

    def test_shape_off_the_registered_pipeline(self, tmp_path, capsys) -> None:
        from simple_agents import Deterministic, Pipeline

        brief = minimal(tmp_path)
        (tmp_path / "agent.py").write_text(
            "from simple_agents import Deterministic, Pipeline, pipeline_factory\n"
            "\n"
            "def step(inputs, ctx):\n"
            "    return inputs\n"
            "\n"
            "@pipeline_factory('triage')\n"
            "def triage():\n"
            "    return Pipeline([Deterministic(step, node_id='step')])\n",
            encoding="utf-8",
        )
        expected = Pipeline([Deterministic(lambda i, c: i, node_id="step")]).graph_fingerprint()

        assert main(["record", "shape", "triage", "--brief", str(brief)]) == 0
        assert main(["record", "shape", "nonsense", "--brief", str(brief)]) == 2

        assert Brief.read(brief).confirmed_shape("triage") == expected
        assert "Registered: triage" in capsys.readouterr().err
