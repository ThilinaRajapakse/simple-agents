"""The builder's comment record, and the gate that reads it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents.records.comments import (
    append_comment,
    append_reply,
    read_comments,
    set_status,
)
from simple_agents.errors import ConfigurationError


def write(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "comments.toml"
    target.write_text(body, encoding="utf-8")
    return target


class TestReading:
    def test_a_missing_file_is_an_empty_record(self, tmp_path) -> None:
        comments = read_comments(tmp_path / "comments.toml")
        assert comments.path is None and comments.all == ()

    def test_entries_read_back_in_order_with_their_status(self, tmp_path) -> None:
        target = write(
            tmp_path,
            """
[[comment]]
at = "recommend/judge"
said = "Why the whole pool?"
date = "2026-08-26"

[[comment]]
at = "resource:catalogue"
said = "Refresh weekly, not daily."
status = "addressed"
addressed_by = "decisions.schedule"
""",
        )
        comments = read_comments(target)
        assert [c.at for c in comments.all] == ["recommend/judge", "resource:catalogue"]
        assert [c.status for c in comments.all] == ["open", "addressed"]
        assert comments.open[0].said == "Why the whole pool?"
        assert comments.all[1].addressed_by == "decisions.schedule"

    def test_at_returns_open_first(self, tmp_path) -> None:
        target = write(
            tmp_path,
            """
[[comment]]
at = "a/b"
said = "done long ago"
status = "addressed"

[[comment]]
at = "a/b"
said = "still waiting"
""",
        )
        found = read_comments(target).at("a/b")
        assert [c.said for c in found] == ["still waiting", "done long ago"]

    def test_a_missing_said_is_refused_naming_the_entry(self, tmp_path) -> None:
        target = write(tmp_path, '[[comment]]\nat = "a/b"\n')
        with pytest.raises(ConfigurationError, match="entry 1"):
            read_comments(target)

    def test_an_unknown_status_is_refused_with_the_two_that_exist(self, tmp_path) -> None:
        target = write(tmp_path, '[[comment]]\nat = "a"\nsaid = "x"\nstatus = "done"\n')
        with pytest.raises(ConfigurationError, match="'open'.*'addressed'"):
            read_comments(target)


class TestThePromptAddresses:
    """`P3-79`: three shapes under one prefix, read by the page, the record and the gates."""

    def test_the_address_splits_the_same_way_everywhere(self):
        from simple_agents.records.comments import prompt_address

        assert prompt_address("prompt:trip/research.read#notes") == (
            "trip",
            "research.read",
            "notes",
        )
        assert prompt_address("prompt:trip/plan") == ("trip", "plan", "")
        assert prompt_address("trip/plan") is None

    def test_an_address_naming_no_step_is_not_one(self):
        """Nothing writes these; a hand-edited file can hold one, and it names no step."""
        from simple_agents.records.comments import prompt_address

        assert prompt_address("prompt:") is None
        assert prompt_address("prompt:trip") is None
        assert prompt_address("prompt:/plan") is None

    def test_each_shape_says_what_it_is_about(self):
        from simple_agents.records.comments import names_a_prompt, names_a_thread

        assert names_a_prompt("", "plan") == "the prompt for plan"
        assert names_a_prompt("notes", "plan") == "the notes value in the prompt for plan"
        assert names_a_prompt("words-3f9a", "plan") == "words in the prompt for plan"
        assert names_a_thread("prompt:trip/plan#notes") == (
            "the notes value in the prompt for plan"
        )
        assert names_a_thread("trip/plan") is None


class TestWriting:
    def test_a_thread_round_trips_with_its_snapshot(self, tmp_path) -> None:
        target = tmp_path / "comments.toml"
        thread = append_comment(
            target,
            at="recommend/judge",
            said='Why "the whole pool"?\nUnread only.',
            kind="comment",
            about="judge, a model call in recommend",
            stage="build",
            shape="sha256:abc123def456",
        )
        held = read_comments(target).thread(thread.id)
        assert held.said == 'Why "the whole pool"?\nUnread only.'
        assert held.about == "judge, a model call in recommend"
        assert (held.stage, held.shape) == ("build", "sha256:abc123def456")
        assert held.when and held.by == "builder"

    def test_a_thread_on_words_in_a_prompt_keeps_what_it_needs(self, tmp_path) -> None:
        """`P3-79`: a selection has to read after the words it quotes have been rewritten."""
        target = tmp_path / "comments.toml"
        thread = append_comment(
            target,
            at="trip/plan#words-3f9a1c2d5e70",
            said="120 words is too short once there are four days.",
            about="words in the prompt for plan, a model call in trip",
            quoted="Answer in at most 120 words",
            run="run_20260903T140233Z_9c1f0a2b",
            instruction="sha256:aa4d52b117e0",
        )
        held = read_comments(target).thread(thread.id)
        assert held.quoted == "Answer in at most 120 words"
        assert held.run == "run_20260903T140233Z_9c1f0a2b"
        assert held.instruction == "sha256:aa4d52b117e0"
        assert held.quoted_chars is None

    def test_a_long_selection_is_cut_and_says_how_long_it_was(self, tmp_path) -> None:
        target = tmp_path / "comments.toml"
        thread = append_comment(
            target, at="trip/plan#words-aaaaaaaaaaaa", said="too much", quoted="x" * 2_500
        )
        held = read_comments(target).thread(thread.id)
        assert len(held.quoted) == 2_000
        assert held.quoted_chars == 2_500
        assert thread.quoted_chars == 2_500

    def test_a_file_written_before_the_snapshot_grew_still_reads(self, tmp_path) -> None:
        """Every field a selection carries is optional, so a `1` file reads as it always did."""
        target = tmp_path / "comments.toml"
        target.write_text(
            'version = "1"\n\n[[comment]]\nid = "c1"\nat = "a/b"\nsaid = "older"\n',
            encoding="utf-8",
        )
        held = read_comments(target)
        assert held.version == "1"
        assert held.all[0].said == "older"
        assert (held.all[0].quoted, held.all[0].run, held.all[0].instruction) == (None,) * 3

    def test_a_length_that_is_not_a_number_is_read_as_none(self, tmp_path) -> None:
        """The file is hand-editable, and one bad value should not stop the rest reading."""
        target = tmp_path / "comments.toml"
        target.write_text(
            'version = "2"\n\n[[comment]]\nid = "c1"\nat = "a/b"\nsaid = "x"\n'
            'quoted = "some words"\nquoted_chars = "lots"\n',
            encoding="utf-8",
        )
        held = read_comments(target).all[0]
        assert held.quoted == "some words" and held.quoted_chars is None

    def test_replies_accumulate_in_order(self, tmp_path) -> None:
        target = tmp_path / "comments.toml"
        thread = append_comment(target, at="a/b", said="first")
        append_reply(target, thread.id, by="coding_agent", said="doing it")
        append_reply(target, thread.id, by="builder", said="thanks")
        held = read_comments(target).thread(thread.id)
        assert [(r.by, r.said) for r in held.replies] == [
            ("coding_agent", "doing it"),
            ("builder", "thanks"),
        ]

    def test_addressing_stamps_who_and_when(self, tmp_path) -> None:
        target = tmp_path / "comments.toml"
        thread = append_comment(target, at="a/b", said="cap it")
        set_status(target, thread.id, "addressed", addressed_by="decisions.pool_cap")
        held = read_comments(target).thread(thread.id)
        assert held.addressed_by == "decisions.pool_cap"
        assert held.addressed_when

    def test_withdrawing_and_reopening(self, tmp_path) -> None:
        target = tmp_path / "comments.toml"
        thread = append_comment(target, at="a/b", said="never mind")
        assert set_status(target, thread.id, "withdrawn").status == "withdrawn"
        assert set_status(target, thread.id, "open").status == "open"

    def test_a_reply_to_a_missing_thread_names_the_fix(self, tmp_path) -> None:
        target = tmp_path / "comments.toml"
        append_comment(target, at="a/b", said="something")
        with pytest.raises(ConfigurationError, match="read_comments"):
            append_reply(target, "c9", by="builder", said="lost")

    def test_an_unknown_kind_is_refused(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError, match="amendment"):
            append_comment(tmp_path / "c.toml", at="a", said="x", kind="objection")

    def test_the_cli_prints_the_exchange(self, tmp_path, capsys) -> None:
        from simple_agents.cli import main

        target = tmp_path / "comments.toml"
        thread = append_comment(
            target, at="recommend/judge", said="why?", about="judge, a model call in recommend"
        )
        append_reply(target, thread.id, by="coding_agent", said="fixing")
        main(["comments", str(tmp_path)])
        out = capsys.readouterr().out
        assert "OPEN" in out and "recommend/judge" in out
        assert "builder: why?" in out and "coding_agent: fixing" in out
        main(["comments", str(tmp_path), "--json"])
        held = json.loads(capsys.readouterr().out)
        assert held[0]["about"] == "judge, a model call in recommend"

    def test_the_cli_prints_the_words_a_thread_is_about(self, tmp_path, capsys) -> None:
        """The coding agent has to find those words in the source to change them."""
        from simple_agents.cli import main

        target = tmp_path / "comments.toml"
        append_comment(
            target,
            at="trip/plan#words-3f9a1c2d5e70",
            said="Too short once there are four days.",
            about="words in the prompt for plan, a model call in trip",
            quoted="Answer in at most 120 words",
            run="run_20260903T140233Z_9c1f0a2b",
            instruction="sha256:aa4d52b117e0",
        )
        main(["comments", str(tmp_path)])
        out = capsys.readouterr().out
        assert 'words: "Answer in at most 120 words"' in out
        assert "read in: run_20260903T140233Z_9c1f0a2b" in out
        main(["comments", str(tmp_path), "--json"])
        held = json.loads(capsys.readouterr().out)
        assert held[0]["quoted"] == "Answer in at most 120 words"
        assert held[0]["instruction"] == "sha256:aa4d52b117e0"


class TestTheGate:
    """FT-39 over real check runs, driven through fixture copies."""

    @staticmethod
    def project(tmp_path: Path, *, comments: str | None, blocking: bool) -> Path:
        import shutil

        source = Path(__file__).parent / "fixtures" / "projects" / "conforming"
        root = tmp_path / "project"
        shutil.copytree(source, root)
        if comments is not None:
            (root / "comments.toml").write_text(comments, encoding="utf-8")
        if blocking:
            # Prepended: appended text would land inside the brief's last table.
            brief = root / "brief.toml"
            brief.write_text(
                "comments_block_gates = true\n" + brief.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        return root

    @staticmethod
    def ft_39(root: Path):
        from simple_agents.conformance import run_checks

        report = run_checks(root)
        return next(c for c in report.checks if c.entry_id == "FT-39")

    def test_a_thread_on_a_prompt_is_named_in_words_not_as_an_address(self, tmp_path) -> None:
        """A gate message is read by the builder, and a digest of the words says nothing."""
        root = self.project(
            tmp_path,
            comments=(
                'version = "2"\n\n[[comment]]\nid = "c1"\n'
                'at = "prompt:trip/plan#words-3f9a1c2d5e70"\n'
                'said = "120 words is too short."\nquoted = "Answer in at most 120 words"\n'
            ),
            blocking=False,
        )
        result = self.ft_39(root)
        assert "words in the prompt for plan" in result.detail
        assert "words-3f9a1c2d5e70" not in result.detail

    def test_the_gate_note_names_it_the_same_way(self, tmp_path) -> None:
        from simple_agents.conformance import run_checks

        root = self.project(
            tmp_path,
            comments=(
                'version = "2"\n\n[[comment]]\nid = "c1"\n'
                'at = "prompt:trip/plan#words-3f9a1c2d5e70"\n'
                'said = "120 words is too short."\n'
            ),
            blocking=False,
        )
        notes = " ".join(run_checks(root).notes or [])
        assert "words in the prompt for plan" in notes
        assert "words-3f9a1c2d5e70" not in notes

    def test_no_file_passes_and_says_why(self, tmp_path) -> None:
        result = self.ft_39(self.project(tmp_path, comments=None, blocking=False))
        assert result.outcome.value == "passed"
        assert "has not commented" in (result.detail or "")

    def test_an_open_comment_reports_under_a_pass_by_default(self, tmp_path) -> None:
        result = self.ft_39(
            self.project(
                tmp_path, comments='[[comment]]\nat = "a/b"\nsaid = "why?"\n', blocking=False
            )
        )
        assert result.outcome.value == "passed"
        assert "1 open comment" in (result.detail or "")

    def test_the_builders_toggle_makes_it_refuse(self, tmp_path) -> None:
        result = self.ft_39(
            self.project(
                tmp_path, comments='[[comment]]\nat = "a/b"\nsaid = "why?"\n', blocking=True
            )
        )
        assert result.outcome.value == "failed"
        assert "why?" in result.findings[0].message

    def test_an_addressed_comment_blocks_nothing(self, tmp_path) -> None:
        result = self.ft_39(
            self.project(
                tmp_path,
                comments='[[comment]]\nat = "a/b"\nsaid = "why?"\nstatus = "addressed"\n',
                blocking=True,
            )
        )
        assert result.outcome.value == "passed"
