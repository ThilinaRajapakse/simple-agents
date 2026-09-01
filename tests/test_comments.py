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
