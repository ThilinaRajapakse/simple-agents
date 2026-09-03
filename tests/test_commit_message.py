"""Runs the commit-message rules.

The rules themselves and their failure messages live in `scripts/check_commit_message.py`.
Each one has a fixture in that file's `SELF_TESTS`: one deliberate defect and the message it
has to produce, so a rule with no fixture there has no coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from check_commit_message import (  # noqa: E402
    HOOK,
    SELF_TESTS,
    check,
    main,
    self_test,
)


def test_every_rule_fires_against_its_fixture() -> None:
    broken = self_test()
    assert not broken, "\n".join(broken)


def test_the_fixtures_cover_every_rule() -> None:
    """The fixture list is the coverage map, so a rule that fires nowhere in it is untested."""
    fired = {problem.rule for _name, message, _expected in SELF_TESTS for problem in check(message)}
    from check_commit_message import GUIDANCE

    assert set(GUIDANCE) - fired == set(), "a rule with no fixture has no coverage"


class TestWhatPasses:
    def test_a_subject_alone(self) -> None:
        assert check("Add the numpy vector store") == []

    def test_a_subject_and_a_short_body(self) -> None:
        message = (
            "Refuse a release whose changelog says nothing\n"
            "\n"
            "The heading is a link in this format, so a release also writes the\n"
            "definition that makes it resolve.\n"
        )
        assert check(message) == []

    def test_one_and_is_not_a_clause_chain(self) -> None:
        """Two things named in one short subject is a sentence. Four is a diffstat."""
        assert check("Add the numpy and FAISS vector stores") == []

    def test_a_public_identifier_is_not_internal_jargon(self) -> None:
        """A conformance id and a format version ship to a builder and are read outside here."""
        assert check("Fail FT-44 on a stamp ahead of the clock") == []
        assert check("Bump the manifest format to 0.40") == []

    def test_the_comment_block_git_appends_is_ignored(self) -> None:
        message = (
            "Add the numpy vector store\n"
            "\n"
            "# Lines starting with '#' are ignored, and an empty message aborts\n"
            "# the commit. This is the block `git commit` appends to the file.\n"
            "#\n"
            "# On branch main (P3-73)\n"
        )
        assert check(message) == []

    def test_a_diff_below_the_scissors_line_is_ignored(self) -> None:
        message = (
            "Add the numpy vector store\n"
            "\n"
            "# ------------------------ >8 ------------------------\n"
            "diff --git a/x b/x\n"
            "+The brief has one writer: it does this and that and the other (P3-72)\n"
        )
        assert check(message) == []


class TestTheCommandLine:
    def test_a_message_file_is_checked(self, tmp_path: Path, capsys) -> None:
        path = tmp_path / "COMMIT_EDITMSG"
        path.write_text("The brief has one writer (P3-72)\n", encoding="utf-8")

        assert main([str(path)]) == 1
        said = capsys.readouterr().out
        assert "internal id" in said
        assert "COMMIT_EDITMSG" in said, "the report names what it read"

    def test_a_clean_message_file_passes(self, tmp_path: Path) -> None:
        path = tmp_path / "COMMIT_EDITMSG"
        path.write_text("Add the numpy vector store\n", encoding="utf-8")

        assert main([str(path)]) == 0

    def test_the_self_test_runs_alone(self, capsys) -> None:
        assert main(["--self-test"]) == 0
        assert "rules fire" in capsys.readouterr().out


def test_the_hook_runs_this_script() -> None:
    """The hook is a shell line, so a rename here has to reach it."""
    assert "scripts/check_commit_message.py" in HOOK
    assert HOOK.startswith("#!/bin/sh")
