"""Runs the writing rules that can be checked mechanically.

The rules themselves and their failure messages live in `scripts/prose_check.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from prose_check import (  # noqa: E402
    ADDRESSES_THE_READER,
    CHECKED,
    COUNTED,
    HINTS,
    NUMBER_WORDS,
    check_file,
    collect,
)


def test_prose_rules() -> None:
    violations = collect()
    if violations:
        report = "\n".join(v.render() for v in violations)
        raise AssertionError(
            f"{len(violations)} writing rule violation(s):\n\n{report}\n"
            "Mark a legitimate use with `# prose-ok: <reason>` and state the reason."
        )


class TestTheCountRule:
    """A sentence counting a set the code defines, checked against the code.

    Six places said six rates after an evaluation began reporting eight, across `src/`,
    `docs/` and prompt text a coding agent executes. Four earlier enumerations went false the
    same way and each was found by someone reading rather than by a failure.
    """

    def _rules(self, tmp_path, body: str) -> set[str]:
        probe = tmp_path / "probe.py"
        probe.write_text(body, encoding="utf-8")
        return {v.rule for v in check_file(probe, builder_facing=True)}

    def test_a_stale_count_is_reported(self, tmp_path) -> None:
        assert "miscount" in self._rules(tmp_path, '"""x.\n\nIt prints the six rates.\n"""\n')

    def test_the_right_count_is_not(self, tmp_path) -> None:
        assert "miscount" not in self._rules(tmp_path, '"""x.\n\nIt prints the eight rates.\n"""\n')

    def test_a_count_without_the_article_is_left_alone(self, tmp_path) -> None:
        """`schema.py` separates "two rates", which is two of them rather than all of them."""
        assert "miscount" not in self._rules(
            tmp_path, '"""x.\n\nThis separates two rates that are averaged.\n"""\n'
        )

    def test_every_counted_noun_resolves_to_a_number(self) -> None:
        """A noun whose source moved would otherwise raise rather than report."""
        for noun, size in COUNTED.items():
            assert isinstance(size(), int), noun
            assert size() in NUMBER_WORDS, (noun, size())


class TestTheProseLengthRule:
    """A docstring over the limit, and what the message tells its author to do about it.

    The rule had no fixture until 2026-08-28, so nothing fired it: `test_prose_rules` runs the
    checker over a clean tree, which reports nothing whether the rule works or not. Its
    guidance said to check whether the unit wants decomposing *before* trimming, and called
    two shorter docstrings the fix. Splitting is not a fix for prose length: two docstrings
    under the limit carry more text than the one that failed, and the check goes quiet.
    """

    def _rules(self, tmp_path, body: str) -> set[str]:
        probe = tmp_path / "probe.py"
        probe.write_text(body, encoding="utf-8")
        return {v.rule for v in check_file(probe, builder_facing=True)}

    def _docstring(self, lines: int) -> str:
        prose = "\n\n".join(f"Sentence number {n} about the thing." for n in range(lines))
        return f'def f():\n    """A thing.\n\n{prose}\n    """\n'

    def test_prose_over_the_limit_is_reported(self, tmp_path) -> None:
        assert "long_docstring" in self._rules(tmp_path, self._docstring(30))

    def test_prose_under_it_is_not(self, tmp_path) -> None:
        assert "long_docstring" not in self._rules(tmp_path, self._docstring(3))

    def test_an_example_block_does_not_count_toward_it(self, tmp_path) -> None:
        """A worked example is what the rules ask for, so its length is not held against it."""
        example = "\n".join(f"        line_{n} = {n}" for n in range(40))
        body = f'def f():\n    """A thing.\n\n    How to use it::\n\n{example}\n    """\n'
        assert "long_docstring" not in self._rules(tmp_path, body)

    def test_the_guidance_does_not_offer_splitting_as_the_fix(self) -> None:
        """The message is read at the point of violation, so what it recommends is the rule.

        It recommended decomposition first, and a session followed it: a 74-line function was
        split into three and the same paragraph ended up in two of them, under the limit.
        """
        guidance = HINTS["long_docstring"]
        assert "Trim it." in guidance
        assert "separate question" in guidance
        assert "not based on convenience" in guidance


class TestTheStateIsNamed:
    """The "Nobody …" construction written for a state that has a name.

    Thilina, 2026-08-29, banned it: name the state instead. The rule fires on the
    construction and leaves the bare word alone,
    since `nobody` is one of the library's answerer values.
    """

    def _rules(self, tmp_path, body: str) -> set[str]:
        probe = tmp_path / "probe.py"
        probe.write_text(f'"""x.\n\n{body}\n"""\n', encoding="utf-8")
        return {v.rule for v in check_file(probe, builder_facing=True)}

    def test_the_construction_is_reported(self, tmp_path) -> None:
        found = self._rules(tmp_path, "A design nobody has agreed to says so.")
        assert "nobody" in found

    def test_the_opener_is_reported(self, tmp_path) -> None:
        found = self._rules(tmp_path, "Nobody opens a window; the reply lands in the outbox.")
        assert "nobody" in found

    def test_the_state_named_is_not(self, tmp_path) -> None:
        found = self._rules(tmp_path, "An unconfirmed design says so.")
        assert "nobody" not in found

    def test_the_answerer_value_is_left_alone(self, tmp_path) -> None:
        found = self._rules(tmp_path, "The channel declares it is answered by nobody.")
        assert "nobody" not in found


class TestAbsenceIsStatedPositively:
    """Absence written as a chain of negatives, which the page said in seven places.

    Thilina, 2026-08-28: *"Do not describe absence using chains of negative constructions.
    State the positive conclusion directly."* The rule fires on the epistemology form and on
    the cascade, and leaves a plain statement of a mechanism alone.
    """

    def _rules(self, tmp_path, body: str) -> set[str]:
        probe = tmp_path / "probe.py"
        probe.write_text(f'"""x.\n\n{body}\n"""\n', encoding="utf-8")
        return {v.rule for v in check_file(probe, builder_facing=True)}

    def test_the_epistemology_form_is_reported(self, tmp_path) -> None:
        found = self._rules(tmp_path, "Nothing here says what the store holds.")

        assert "negation_cascade" in found

    def test_a_cascade_reaching_a_conclusion_is_reported(self, tmp_path) -> None:
        found = self._rules(
            tmp_path, "No tool names it and no step records it, so nothing describes it."
        )

        assert "negation_cascade" in found

    def test_reasoning_written_out_is_reported(self, tmp_path) -> None:
        found = self._rules(
            tmp_path, "The class cannot say which it was, so the direction is left out."
        )

        assert "negation_cascade" in found

    def test_the_positive_statement_is_not(self, tmp_path) -> None:
        found = self._rules(tmp_path, "Contents and direction are unknown.")

        assert "negation_cascade" not in found

    def test_a_mechanism_with_a_consequence_is_left_alone(self, tmp_path) -> None:
        """ "so nothing is lost" states what happens, and is what the rules ask for."""
        found = self._rules(
            tmp_path, "The number comes from inside the lock, so nothing is out of order."
        )

        assert "negation_cascade" not in found

    def test_a_bare_absence_is_left_alone(self, tmp_path) -> None:
        found = self._rules(tmp_path, "Tools reaching it: none.")

        assert "negation_cascade" not in found


class TestTheExampleChecks:
    """A silent check and a working one look the same, so each rule is fired once.

    Every example in the documentation was unverified until these landed: four blocks did not
    parse and one named a constructor argument that had been renamed, in both a shipped
    document and the docstring it was copied from.
    """

    def _rules(self, tmp_path, name: str, body: str) -> list[str]:
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        return [v.rule for v in check_file(path, builder_facing=True)]

    def test_a_markdown_block_that_does_not_parse(self, tmp_path) -> None:
        found = self._rules(
            tmp_path, "d.md", '```python\nDocumentIndex.from_texts({"a": "x", ...})\n```\n'
        )

        assert found == ["unparseable_example"]

    def test_a_docstring_block_that_does_not_parse(self, tmp_path) -> None:
        found = self._rules(
            tmp_path,
            "m.py",
            'def f():\n    """One line::\n\n        g(envelope=env, ...)\n    """\n',
        )

        assert found == ["unparseable_example"]

    def test_an_import_of_a_name_the_library_does_not_export(self, tmp_path) -> None:
        found = self._rules(
            tmp_path, "d.md", "```python\nfrom simple_agents import Pipeline, Sprocket\n```\n"
        )

        assert found == ["unknown_name"]

    def test_an_argument_the_callable_does_not_take(self, tmp_path) -> None:
        found = self._rules(tmp_path, "d.md", '```python\nTool(call=lambda a: a, name="x")\n```\n')

        assert found == ["unknown_argument"]

    def test_a_shell_block_is_not_read_as_python(self, tmp_path) -> None:
        """A literal block cannot say which it is, and the docs show three commands."""
        found = self._rules(
            tmp_path,
            "m.py",
            'def f():\n    """One line::\n\n        vllm serve Qwen/Qwen3-8B --revision <sha>\n    """\n',
        )

        assert found == []

    def test_an_example_naming_only_the_project_is_left_alone(self, tmp_path) -> None:
        """An example calls the project's own functions, and those are not here to check."""
        found = self._rules(
            tmp_path,
            "d.md",
            "```python\nsuite = build_suite(matches=exact, answer='answer')\n"
            "results = suite.run(split='held_out', k=5)\n```\n",
        )

        assert found == []


class TestARoleAndAModuleResolve:
    """The two rot classes the 2026-08-31 reverification found by hand, fired once each.

    A stale example imported a module retired weeks earlier and a docstring named a method
    its class does not have, and both passed clean: imports were resolved from the package
    root alone, and role targets not at all.
    """

    def _rules(self, tmp_path, name: str, body: str) -> list[str]:
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        return [v.rule for v in check_file(path, builder_facing=True)]

    def test_an_import_from_a_module_the_library_does_not_have(self, tmp_path) -> None:
        found = self._rules(
            tmp_path, "d.md", "```python\nfrom simple_agents.reporting import report\n```\n"
        )

        assert found == ["unknown_module"]

    def test_an_import_from_a_submodule_it_does_have(self, tmp_path) -> None:
        found = self._rules(
            tmp_path,
            "d.md",
            "```python\nfrom simple_agents.cli.reporting import report_over_runs\n```\n",
        )

        assert found == []

    def test_a_role_naming_nothing_is_reported(self, tmp_path) -> None:
        found = self._rules(
            tmp_path, "m.py", '"""One.\n\nReturned by :meth:`MemoryStore.no_such_method`.\n"""\n'
        )

        assert found == ["unknown_role_target"]

    def test_a_role_resolving_absolutely_passes(self, tmp_path) -> None:
        found = self._rules(
            tmp_path,
            "m.py",
            '"""One.\n\nSee :class:`simple_agents.Pipeline` and :meth:`Pipeline.run`.\n"""\n',
        )

        assert found == []


class TestTheSecondPersonRule:
    """`README.md` addresses its reader directly and every other shipped file does not.

    The exemption is one file name, so a widened rule and a working one look identical from
    inside `README.md`. Both sides are fired: the file that is exempt, and a file that is not.
    """

    def _rules(self, tmp_path, name: str, body: str) -> list[str]:
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        return [v.rule for v in check_file(path, builder_facing=True)]

    def test_the_landing_page_may_address_its_reader(self, tmp_path) -> None:
        found = self._rules(tmp_path, "README.md", "You write the pipeline.\n")

        assert "second_person" not in found

    def test_a_shipped_document_still_may_not(self, tmp_path) -> None:
        found = self._rules(tmp_path, "pipeline.md", "You write the pipeline.\n")

        assert "second_person" in found

    def test_the_landing_page_keeps_every_other_rule(self, tmp_path) -> None:
        """Exempting one rule for one file is not exempting the file."""
        found = self._rules(tmp_path, "README.md", "Your run is the most important thing.\n")

        assert found == ["intensifier"]

    def test_the_exemption_reaches_one_file_in_the_checked_trees(self) -> None:
        """The rule matches on a file name, so a second file carrying one of these names would
        be exempted without anyone choosing that. There is one today, at the repository root."""
        exempted = [
            path
            for entry in CHECKED
            for path in ([REPO / entry] if (REPO / entry).is_file() else (REPO / entry).rglob("*"))
            if path.name in ADDRESSES_THE_READER
        ]

        assert exempted == [
            REPO / "src/simple_agents/view/findings.py",
            REPO / "README.md",
        ]


class TestAnInternalIdInAShippedFile:
    """An id resolves only inside `dev-docs/`, and a filename is not the only form it takes.

    `DF4-D6` shipped inside the wheel in a `checks.py` docstring, because the sweep that
    cleared the internal citations searched for filenames and this one carried none.
    """

    def _rules(self, tmp_path, relative: str, body: str) -> list[str]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return [v.rule for v in check_file(path, builder_facing=True)]

    def test_a_finding_id_is_reported(self, tmp_path) -> None:
        found = self._rules(
            tmp_path, "probe.py", '"""x.\n\nA routed node passes (`DF4-D6`).\n"""\n'
        )

        assert "internal_ref" in found

    def test_a_queue_id_is_reported(self, tmp_path) -> None:
        found = self._rules(tmp_path, "probe.py", '"""x.\n\nAdded at `P3-22` stage 2.\n"""\n')

        assert "internal_ref" in found

    def test_a_maintainer_tree_may_carry_one(self, tmp_path) -> None:
        """`tests/` is absent from the wheel, so the reader of a citation there holds it."""
        found = self._rules(tmp_path, "tests/probe.py", '"""x.\n\nAdded at `P3-22` stage 2.\n"""\n')

        assert "internal_ref" not in found

    def test_the_maintainer_tree_keeps_every_other_rule(self, tmp_path) -> None:
        found = self._rules(tmp_path, "tests/probe.py", '"""x.\n\nThe most important rule.\n"""\n')

        assert found == ["intensifier"]

    def test_a_run_of_ours_named_in_prose_is_reported(self, tmp_path) -> None:
        """The id pattern reads `P3-n` and `DF5-Inn`, so a run named in prose passed both. Six
        instances were in shipped files when the rule was written, two of them in `docs/`."""
        found = self._rules(tmp_path, "probe.py", '"""x.\n\nDogfood #4 is the case here.\n"""\n')

        assert "own_run" in found

    def test_the_hyphenated_form_is_reported_too(self, tmp_path) -> None:
        found = self._rules(
            tmp_path, "probe.py", '"""x.\n\nMeasured over `dogfood-5-frozen`.\n"""\n'
        )

        assert "own_run" in found

    def test_saying_what_it_showed_without_the_run_is_quiet(self, tmp_path) -> None:
        found = self._rules(tmp_path, "probe.py", '"""x.\n\nOne project is the case here.\n"""\n')

        assert "own_run" not in found

    def test_the_changelog_keeps_its_history(self, tmp_path) -> None:
        """An entry says what was true at a release, and which run a change came out of is part
        of that record. The same reason `miscount` exempts it."""
        found = self._rules(
            tmp_path, "CHANGELOG.md", "## Unreleased\n\nMeasured on dogfood #5: two nodes.\n"
        )

        assert "own_run" not in found

    def test_a_path_on_this_machine_is_reported(self, tmp_path) -> None:
        found = self._rules(
            tmp_path, "probe.py", '"""x.\n\nThe wheel is at /home/maintainer/Projects/x.\n"""\n'
        )

        assert "machine_path" in found

    def test_a_placeholder_home_is_quiet(self, tmp_path) -> None:
        """`/home/x/library` under `/home/x/lib` is an example of two paths one prefix apart."""
        found = self._rules(
            tmp_path,
            "probe.py",
            '"""x.\n\nA project at /home/x/library, installed at /home/x/lib.\n"""\n',
        )

        assert "machine_path" not in found

    def test_no_shipped_file_carries_one(self) -> None:
        """The wheel is what a builder receives, and `tests/` is not in it."""
        shipped = [
            path
            for entry in CHECKED
            if "tests" not in Path(entry).parts
            for path in ([REPO / entry] if (REPO / entry).is_file() else (REPO / entry).rglob("*"))
            if path.suffix in {".py", ".md"} and "__pycache__" not in path.parts
        ]
        assert shipped
        assert [v.render() for f in shipped for v in check_file(f, builder_facing=True)] == []


class TestASectionReferenceNamingNoDocument:
    """A bare `§6.2` names a section of nothing, and sixteen documents have one.

    Thilina, 2026-08-09: *"Section 6 of which doc and where? If I can't follow them, it's
    unlikely that a coding agent or builder can either."* A `.md` file under `docs/` anchors
    its own references; a `.py` file has to say which document it means.
    """

    def _rules(self, tmp_path, body: str) -> list[str]:
        probe = tmp_path / "probe.py"
        probe.write_text(body, encoding="utf-8")
        return [v.rule for v in check_file(probe, builder_facing=True)]

    def test_a_bare_reference_is_reported(self, tmp_path) -> None:
        found = self._rules(tmp_path, '"""x.\n\n§5.4 is the schema of record.\n"""\n')

        assert "unanchored_section" in found

    def test_a_path_on_the_same_line_anchors_it(self, tmp_path) -> None:
        found = self._rules(tmp_path, '"""x.\n\n`docs/evaluation.md` §5.4 is the schema.\n"""\n')

        assert found == []

    def test_a_path_on_the_line_above_anchors_it(self, tmp_path) -> None:
        """Where a sentence wraps, the path and the reference land on different lines."""
        found = self._rules(
            tmp_path, '"""x.\n\nThe encoded form is stated in `docs/evaluation.md`\n§5.4.\n"""\n'
        )

        assert found == []

    def test_a_module_docstring_anchors_every_reference_below_it(self, tmp_path) -> None:
        """`tests/test_trajectory_conformance.py` anchors twenty-nine that way, in one line."""
        found = self._rules(
            tmp_path,
            '"""Checked against `docs/evaluation.md`. Every reference below is to it."""\n\n\n'
            'def f() -> None:\n    """§5.4 is the schema of record."""\n',
        )

        assert found == []

    def test_two_documents_in_a_module_docstring_anchor_nothing(self, tmp_path) -> None:
        found = self._rules(
            tmp_path,
            '"""Checked against `docs/evaluation.md` and `docs/tools.md`."""\n\n\n'
            'def f() -> None:\n    """§5.4 is the schema of record."""\n',
        )

        assert "unanchored_section" in found

    def test_an_anchored_reference_to_a_section_that_does_not_exist(self, tmp_path) -> None:
        """Naming a document is what lets the reference be resolved at all."""
        found = self._rules(tmp_path, '"""x.\n\n`docs/evaluation.md` §99.1 says so.\n"""\n')

        assert found == ["missing_section"]

    def test_a_reference_into_a_document_with_no_numbered_sections_at_all(self, tmp_path) -> None:
        """The hole the rule had: an empty heading set disabled it rather than failing it.

        `docs/procedure.md` numbers no heading, so every `§n` into it resolved to nothing and
        passed. One shipped pointer, in `conformance/decisions.py`, was exactly that.
        """
        found = self._rules(tmp_path, '"""x.\n\n`docs/procedure.md` §4 says so.\n"""\n')

        assert found == ["missing_section"]

    def test_a_reference_to_a_section_that_does_exist_passes(self, tmp_path) -> None:
        """The other side, so the rule is not satisfied by refusing everything."""
        found = self._rules(tmp_path, '"""x.\n\n`docs/evaluation.md` §1 says so.\n"""\n')

        assert found == []


class TestAnExampleChannelTakesTheArgumentsItIsGiven:
    """A doc example that parses can still be uncallable, and nothing executes one.

    `consult` calls its channel with `(question, options, about)`. Six shipped examples were
    left at two arguments when the third was added, and every one of them parsed, resolved and
    would have raised `TypeError` on the first question a builder asked through it.
    """

    CHANNEL = re.compile(
        r"^\s*def (?!_)(\w+)\(\s*(question\b[^)]*\boptions\b[^)]*)\)", re.MULTILINE
    )
    """A channel is a public function whose first two parameters are the question and the
    offered options. A private helper of the same shape is not one."""

    def _channels(self) -> list[tuple[str, str, str]]:
        found = []
        for path in sorted((REPO / "docs").rglob("*.md")):
            for name, params in self.CHANNEL.findall(path.read_text(encoding="utf-8")):
                found.append((str(path.relative_to(REPO)), name, params))
        for path in sorted((REPO / "src").rglob("*.py")):
            for name, params in self.CHANNEL.findall(path.read_text(encoding="utf-8")):
                found.append((str(path.relative_to(REPO)), name, params))
        return found

    def test_there_are_channels_to_check(self) -> None:
        assert self._channels()

    def test_every_one_takes_three_arguments(self) -> None:
        short = [
            f"{where}: {name}({params})"
            for where, name, params in self._channels()
            if len([p for p in params.split(",") if p.strip()]) < 3
        ]
        assert short == [], (
            "A consult channel is called with (question, options, about). These take fewer, so "
            "the first question asked through one raises TypeError: " + "; ".join(short)
        )
