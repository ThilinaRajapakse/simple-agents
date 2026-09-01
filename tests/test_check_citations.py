"""What `scripts/check_citations.py` resolves on its own, and what it declines.

The script guards documents that cite code by line against numbers that rot. It went untested
until 2026-08-12, when a two-line docstring edit moved five citations and `--fix` rewrote none
of them: it resolved `symbol-drift` and not `blank-line`, which is the class an edit above a
citation actually produces.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_citations.py"


def load(repo: Path):
    """The script, with its notion of the repository pointed at a temporary one."""
    spec = importlib.util.spec_from_file_location(f"cc_{repo.name}", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.REPO = repo
    return module


@pytest.fixture
def repo(tmp_path):
    """A repository holding one source file and one document citing it."""
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src" / "thing.py").write_text(
        "\n".join(
            [
                "def first():",  # 1
                "    return 1",  # 2
                "",  # 3
                "",  # 4
                "def second():",  # 5
                "    return 2",  # 6
                "",  # 7
                "def resolve():",  # 8
                "    return 3",  # 9
                "",  # 10
                "class Held:",  # 11
                "    def resolve(self):",  # 12
                "        return 4",  # 13
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


def cite(repo: Path, text: str) -> Path:
    document = repo / "docs" / "note.md"
    document.write_text(text, encoding="utf-8")
    return document


@pytest.fixture
def fields(tmp_path):
    """A repository whose source file declares fields, one of them an ordinary word."""
    (tmp_path / "src").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "src" / "record.py").write_text(
        "\n".join(
            [
                "from dataclasses import dataclass",  # 1
                "",  # 2
                "",  # 3
                "@dataclass",  # 4
                "class Example:",  # 5
                '    """One labeled input."""',  # 6
                "",  # 7
                "    inputs: Any",  # 8
                "    expected: Any",  # 9
                "    cost: float = 0.0",  # 10
                "",  # 11
                "",  # 12
                "def unrelated():",  # 13
                "    return 1",  # 14
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


class TestWhichNameIsTheSubject:
    """The label first, and a declared field counts there. Added 2026-08-16.

    Both were found by one citation. `[`inputs`]` pointing at the field was reported as drift
    against the `Example` named in the sentence above it, because the field was invisible to
    `definition_lines` and the class was not. Making fields visible everywhere then made
    `cost` in prose resolve to a field and reported 44 citations that were right.
    """

    def test_a_field_the_label_names_resolves(self, fields):
        document = cite(fields, "Not [`inputs`](../src/record.py#L8), not that.\n")

        assert load(fields).check_file(document) == []

    def test_a_field_named_in_prose_does_not_become_the_subject(self, fields):
        document = cite(
            fields, "What it holds is `cost`. See [record.py:13](../src/record.py#L13).\n"
        )

        assert load(fields).check_file(document) == []

    def test_the_label_beats_a_resolvable_name_in_the_sentence_before(self, fields):
        """`Example` resolves and is not what the citation is about."""
        document = cite(
            fields,
            "The whole `Example` is in scope.\nNot [`expected`](../src/record.py#L9), not that.\n",
        )

        assert load(fields).check_file(document) == []

    def test_a_dotted_label_resolves_inside_its_class(self, repo):
        """`Held.resolve` is the method on `Held`, not the module-level `resolve` above it.

        Until 2026-08-17 a dotted label matched no name at all, so it fell through to the
        prose and `--fix` moved a correct anchor onto whatever the sentence happened to name.
        """
        document = cite(repo, "The [`Held.resolve`](../src/thing.py#L1) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "symbol-drift"
        assert problem.fix == (
            "[`Held.resolve`](../src/thing.py#L1)",
            "[`Held.resolve`](../src/thing.py#L12)",
        )

    def test_a_module_qualified_label_resolves_to_the_plain_definition(self, repo):
        """`thing.second` names the file the citation already points at, not a class in it.

        `runner._node_outputs` was written this way, pointed at a bare `]`, and no check saw
        it until dotted labels resolved on 2026-08-17.
        """
        document = cite(repo, "The [`thing.second`](../src/thing.py#L1) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "symbol-drift"
        assert "at line 5" in problem.message

    def test_a_filename_in_the_label_is_not_read_as_a_member(self, repo):
        """`thing.py` is a dotted name and `py` is a suffix rather than something defined."""
        document = cite(repo, "See [`thing.py`](../src/thing.py#L1), which does it.\n")

        assert load(repo).check_file(document) == []

    def test_a_field_the_label_names_still_drifts_when_the_anchor_is_wrong(self, fields):
        document = cite(fields, "Not [`expected`](../src/record.py#L14), not that.\n")

        [problem] = load(fields).check_file(document)

        assert problem.kind == "symbol-drift"
        assert "at line 9" in problem.message


class TestWhatItResolvesOnItsOwn:
    def test_a_blank_line_names_the_line_holding_the_subject(self, repo):
        document = cite(repo, "The [`second`](../src/thing.py#L4) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "blank-line"
        assert "`second` beside it is at line 5" in problem.message

    def test_fix_moves_a_blank_line_anchor_to_its_subject(self, repo):
        document = cite(repo, "The [`second`](../src/thing.py#L4) does it.\n")
        module = load(repo)

        [problem] = module.check_file(document)
        assert problem.fix is not None
        document.write_text(document.read_text().replace(*problem.fix), encoding="utf-8")

        assert "#L5" in document.read_text()
        assert module.check_file(document) == []

    def test_a_label_ending_in_the_line_is_relabelled_with_the_new_one(self, repo):
        """Otherwise the label says one line and the anchor another, which is `label-mismatch`."""
        document = cite(repo, "`second` is at [thing.py:4](../src/thing.py#L4).\n")
        module = load(repo)

        [problem] = module.check_file(document)
        document.write_text(document.read_text().replace(*problem.fix), encoding="utf-8")

        assert "[thing.py:5](../src/thing.py#L5)" in document.read_text()
        assert module.check_file(document) == []

    def test_a_backticked_label_is_seen_at_all(self, repo):
        """The hole: `LABEL_LINE` wanted the digits at the end, and a backtick follows them.

        Backticks are the house style for a label, so the rule fired only on the form the
        conventions discourage and twenty-six labels drifted from their own anchors under it.
        """
        document = cite(repo, "The [`thing.py:1`](../src/thing.py#L5) does it.\n")

        kinds = [p.kind for p in load(repo).check_file(document)]

        assert "label-mismatch" in kinds

    def test_relabelling_a_backticked_label_keeps_its_backtick(self, repo):
        """A substitution that ate the closing one would leave the label unbalanced."""
        document = cite(repo, "The [`thing.py:1`](../src/thing.py#L5) does it.\n")
        module = load(repo)

        [problem] = [p for p in module.check_file(document) if p.kind == "label-mismatch"]
        document.write_text(document.read_text().replace(*problem.fix), encoding="utf-8")

        assert "[`thing.py:5`](../src/thing.py#L5)" in document.read_text()

    def test_a_label_that_agrees_with_its_anchor_is_not_reported(self, repo):
        """The other side, so the rule is not satisfied by refusing every label."""
        document = cite(repo, "The [`thing.py:5`](../src/thing.py#L5) does it.\n")

        kinds = [p.kind for p in load(repo).check_file(document)]

        assert "label-mismatch" not in kinds

    def test_symbol_drift_still_resolves(self, repo):
        """The class that always had a fix, checked here so folding the two did not lose it."""
        document = cite(repo, "The [`second`](../src/thing.py#L1) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "symbol-drift"
        assert problem.fix is not None


class TestANameTheFileDoesNotHold:
    """The hole this closes, found 2026-08-20 at the P3-27 build.

    Naming the symbol is what lets a citation be re-resolved after the code above it moves.
    `_subject_definition` skips a name it cannot find and moves on, so a typo or a rename left
    the citation passing every check with the one thing making it checkable gone. Written as
    `_spend_line` where the function is `_spend_lines`, anchored on a real line, it passed.
    """

    def test_a_name_the_file_does_not_hold_is_reported(self, repo):
        document = cite(repo, "The [`missing`](../src/thing.py#L1) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "no-such-symbol"
        assert "`missing`" in problem.message

    def test_a_name_that_is_only_part_of_a_real_one_is_reported(self, repo):
        """`resolv` sits inside `resolve` and is not a word the file holds."""
        document = cite(repo, "The [`resolv`](../src/thing.py#L8) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "no-such-symbol"

    def test_it_cannot_be_fixed_automatically(self, repo):
        """Nothing resolves it, so there is no line to move the anchor to."""
        document = cite(repo, "The [`missing`](../src/thing.py#L1) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.fix is None

    def test_a_name_the_file_holds_without_defining_raises_nothing(self, tmp_path):
        """A local, a class attribute and a string id are all findable by a reader.

        The definition test alone reported nine citations in this repository and seven were of
        this kind, which is the noise the module's docstring says stops it being read.
        """
        (tmp_path / "src").mkdir()
        (tmp_path / "docs").mkdir()
        (tmp_path / "src" / "held.py").write_text(
            "\n".join(
                [
                    "class Tier:",  # 1
                    '    ORDER = ("a", "b")',  # 2
                    "",  # 3
                    "",  # 4
                    "def build():",  # 5
                    "    observed = 1",  # 6
                    '    return question(name="ground_truth"), observed',  # 7
                ]
            ),
            encoding="utf-8",
        )
        module = load(tmp_path)
        for label, anchor in (("ORDER", 2), ("observed", 6), ("ground_truth", 7)):
            document = cite(tmp_path, f"The [`{label}`](../src/held.py#L{anchor}) does it.\n")

            assert module.check_file(document) == [], label

    def test_one_findable_name_beside_one_from_elsewhere_raises_nothing(self, repo):
        """Prose and labels legitimately name things defined in other files."""
        document = cite(repo, "[`thing.py`, `second`, `Elsewhere`](../src/thing.py#L5) does it.\n")

        assert load(repo).check_file(document) == []

    def test_a_label_naming_nothing_in_backticks_raises_only_unnamed(self, repo):
        """No symbol means no drift check, and since 2026-08-31 that is itself reported."""
        document = cite(repo, "See [thing.py:5](../src/thing.py#L5).\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "unnamed-anchor"


class TestWhatItDeclines:
    def test_a_blank_line_with_no_subject_named_gets_no_fix(self, repo):
        document = cite(repo, "See [thing.py:4](../src/thing.py#L4).\n")

        blank, unnamed = load(repo).check_file(document)

        assert blank.kind == "blank-line"
        assert blank.fix is None
        assert unnamed.kind == "unnamed-anchor"

    def test_a_name_defined_twice_is_not_guessed_at(self, repo):
        """`resolve` is a function and a method here, and which was meant is unstated."""
        document = cite(repo, "The [`resolve`](../src/thing.py#L4) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.fix is None

    def test_a_dotted_label_the_class_does_not_hold_resolves_to_nothing(self, repo):
        """A namesake elsewhere in the file is not the subject of `Held.first`."""
        document = cite(repo, "The [`Held.first`](../src/thing.py#L1) does it.\n")

        assert load(repo).check_file(document) == []

    def test_a_dotted_name_in_the_prose_is_not_read_as_a_subject(self, repo):
        document = cite(repo, "See [thing.py:4](../src/thing.py#L4), `Held.resolve`.\n")

        [problem] = load(repo).check_file(document)

        assert problem.fix is None

    def test_an_anchor_at_line_one_needs_no_name(self, repo):
        """Line 1 cites the module itself and cannot rot."""
        assert load(repo).check_file(cite(repo, "See [thing.py](../src/thing.py#L1).\n")) == []


class TestAMarkdownLink:
    def test_a_link_to_a_missing_file_is_dead(self, repo):
        document = cite(repo, "The record is [gone](missing.md).\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "dead-md-link"

    def test_an_anchor_past_the_end_is_dead(self, repo):
        (repo / "docs" / "other.md").write_text("one line\n")
        document = cite(repo, "See [other](other.md#L9).\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "dead-md-link"

    def test_a_link_written_for_another_directory_gets_the_clickable_path(self, repo):
        """Text moved between directories carries links for where it used to live."""
        (repo / "notes").mkdir()
        (repo / "notes" / "other.md").write_text("one line\n")
        document = cite(repo, "See [other](notes/other.md).\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "not-clickable"
        assert problem.fix == ("](notes/other.md", "](../notes/other.md")

    def test_a_resolving_link_raises_nothing(self, repo):
        (repo / "docs" / "other.md").write_text("one line\n")

        assert load(repo).check_file(cite(repo, "See [other](other.md#L1).\n")) == []


class TestWhatItDeclinesToo:
    def test_an_anchor_on_the_subject_raises_nothing(self, repo):
        assert load(repo).check_file(cite(repo, "[`second`](../src/thing.py#L5) does it.\n")) == []


class TestAnAnchorPastTheEndOfTheFile:
    """The hole this closes, found 2026-08-28 in `P3-52`'s sixth reverification cycle.

    Deleting code above a citation slides its anchor past the end of the file. That was
    reported and abandoned: `--fix` repaired a drifted anchor and a blank-line anchor and left
    this one, though the subject named beside it resolves the same way. Six citations of
    `_pace_for` in this tree were in that state.
    """

    def test_it_is_reported_with_the_line_the_subject_is_on(self, repo):
        document = cite(repo, "The [`second`](../src/thing.py#L900) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "unresolvable"
        assert "a file with 13 lines" in problem.message
        assert "`second` beside it is at line 5" in problem.message

    def test_fix_moves_the_anchor_to_the_subject(self, repo):
        document = cite(repo, "The [`second`](../src/thing.py#L900) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.fix == (
            "[`second`](../src/thing.py#L900)",
            "[`second`](../src/thing.py#L5)",
        )

    def test_a_past_the_end_anchor_naming_no_subject_gets_no_fix(self, repo):
        """Nothing names what it was about, so there is no line to move it to."""
        document = cite(repo, "The [thing.py:900](../src/thing.py#L900) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "unresolvable"
        assert problem.fix is None

    def test_a_missing_file_is_still_reported_and_unfixable(self, repo):
        """The other half of `unresolvable`: no file at all, so no line to resolve against."""
        document = cite(repo, "The [`second`](../src/gone.py#L5) does it.\n")

        [problem] = load(repo).check_file(document)

        assert problem.kind == "unresolvable"
        assert "no such file exists" in problem.message
        assert problem.fix is None
