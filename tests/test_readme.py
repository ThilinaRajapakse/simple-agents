"""`README.md` is the landing page, and nothing read it until this file.

It shipped an unanswered editorial question in the middle of a feature description, a heading
with nothing under it, and two counts of what the documents hold that were both stale. Each
class of defect is held by a test here rather than by anyone remembering.

What renders is what is checked: HTML comments are review notes and are removed first.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from simple_agents.conformance import taxonomy
from simple_agents.conformance.checks import RECORD_TYPES

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
FENCE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)

NUMBERS = {
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
}


def text() -> str:
    return README.read_text(encoding="utf-8")


def rendered() -> str:
    """What a reader sees: the file with its review comments removed."""
    return COMMENT.sub("", text())


def prose() -> str:
    """The rendered file with its code blocks removed, which is the part written as English."""
    return FENCE.sub("", rendered())


class TestNothingUnfinishedRenders:
    def test_no_placeholder_is_left_in_the_prose(self) -> None:
        """One read "Registration without one is refused, to ensure <what does this
        provide?>", and it was not in a comment."""
        found = re.findall(r"<[^>\n]{2,}>", prose())

        assert found == []

    def test_no_heading_is_left_without_a_name(self) -> None:
        """A bare `##` line rendered as an empty heading between the summary and the banner."""
        found = [
            line
            for line in rendered().splitlines()
            if line.strip().strip("#") == "" and line.strip().startswith("#")
        ]

        assert found == []

    def test_every_heading_has_something_under_it(self) -> None:
        """`## Cassettes and Replays` had a review note under it and nothing else."""
        sections = re.split(r"^(#{1,6} .*)$", rendered(), flags=re.MULTILINE)
        headings = [
            sections[index].strip()
            for index in range(1, len(sections), 2)
            if not sections[index + 1].strip()
        ]

        assert headings == []


class TestTheCountsAreTheCountsThatShip:
    def test_every_taxonomy_count_it_states_is_the_entry_count(self) -> None:
        """Read every mention. The count sat in one table row until the coding-agent section
        also had a reason to state it, and a test that unpacks a single match breaks on the
        second one existing rather than on either being wrong."""
        named = re.findall(r"(\d+) characteristic failures", prose())

        assert named
        assert [int(n) for n in named] == [len(taxonomy())] * len(named)

    def test_the_trajectory_row_counts_the_record_types_that_exist(self) -> None:
        [named] = re.findall(r"record schema with (\w+) record types", prose())

        assert named == NUMBERS[len(RECORD_TYPES)]

    def test_every_shipped_file_naming_the_stages_names_all_of_them(self) -> None:
        """`research` shipped as the second of six on 2026-08-20 and three shipped statements
        still said five, in the README and twice in `docs/conformance.md`. Every count beside
        it had a test here and the stage list had none, so it was the one that drifted.

        The stages are named in running prose and in a shell comment, so this reads any run
        of them and asks whether one is missing rather than matching a fixed sentence.
        """
        from simple_agents.conformance.stages import STAGES

        # A listing separates the names with a comma, a connective, or both, and wraps
        # across lines: `docs/procedure.md` has "`measure`\nand `ship`".
        separator = r"(?:\s*,)?\s*(?:#\s*)?(?:and\s+|or\s+|then\s+)?"
        run = re.compile(
            rf"`?{STAGES[0]}`?(?:{separator}`?(?:{'|'.join(STAGES)})`?){{2,}}",
            re.IGNORECASE,
        )
        shipped = [README, *sorted((ROOT / "docs").rglob("*.md"))]

        incomplete = []
        for path in shipped:
            for listing in run.findall(path.read_text(encoding="utf-8")):
                missing = [stage for stage in STAGES if stage not in listing.lower()]
                # `prototype` has no `measure`, so a tier-scoped list may leave that one out.
                if missing and missing != ["measure"]:
                    incomplete.append((path.name, listing.strip(), missing))

        assert not incomplete, "a shipped file lists the stages and leaves one out: " + "; ".join(
            f"{name}: {listing!r} is missing {missing}" for name, listing, missing in incomplete
        )

    def test_it_counts_the_rates_the_evaluation_reports(self) -> None:
        """`prose_check` guards a count through the definite article, and this one dropped it:
        "the eight rates" promises a set the README does not show. The guard moves here."""
        from simple_agents.evaluation.metrics import METRIC_DEFINITIONS

        named = [n.lower() for n in re.findall(r"(\w+) rates are reported", prose())]

        assert named
        assert named == [NUMBERS[len(METRIC_DEFINITIONS)]] * len(named)


class TestEveryDocumentItPointsAtExists:
    @pytest.mark.parametrize("path", sorted(set(re.findall(r"docs/[\w./-]+\.md", text()))))
    def test_it_is_a_file(self, path: str) -> None:
        assert (ROOT / path).exists()

    def test_every_shipped_document_is_in_the_table(self) -> None:
        """The reverse of the rule above, which is the direction that failed: `retrieval.md`,
        `memory.md` and `shipping.md` shipped and the table never gained a row, while every
        path it did name resolved."""
        named = set(re.findall(r"docs/[\w./-]+\.md", rendered()))
        shipped = {str(p.relative_to(ROOT)) for p in (ROOT / "docs").rglob("*.md")}

        assert shipped - named == set()


class TestTheQuickStart:
    def test_every_command_it_names_is_one_the_cli_has(self) -> None:
        from simple_agents.cli.main import _parser

        named = set(re.findall(r"simple-agents ([a-z-]+)", rendered()))
        available = set(_parser()._subparsers._group_actions[0].choices)

        assert named
        assert named <= available

    def test_every_name_it_imports_is_one_the_library_exports(self) -> None:
        """The snippets are the first code a reader runs, and an import that fails stops it."""
        import simple_agents

        imported = re.findall(r"^from simple_agents import (.+)$", text(), re.MULTILINE)

        assert imported
        for line in imported:
            for name in (part.strip() for part in line.split(",")):
                assert hasattr(simple_agents, name), name

    def test_the_backend_it_names_is_a_hosted_one_and_names_its_credential(self) -> None:
        """A reader has an API key before they have a server, so the first snippet names a
        hosted backend, and names the environment variable that backend reads beside it."""
        hosted = {"MistralClient": "MISTRAL_API_KEY", "GeminiClient": "GEMINI_API_KEY"}
        snippet = text().split("## A first agent")[1].split("\n##")[0]

        named = [client for client in hosted if f"{client}(" in snippet]

        assert len(named) == 1, named
        assert hosted[named[0]] in snippet

    def test_it_says_cost_is_derived_from_what_the_run_recorded(self) -> None:
        """It said "derived against the declared basis" beside a snippet that declares none.
        The claim left the first example, where it was a reference detail, and the guard
        followed it: `result.cost` is a dict and a README that shows it has to say so."""
        section = rendered().split("## What the library provides")[1].split("\n## ")[0]

        assert "Cost is worked out from those counts" in section
        assert "re-priced from the record it already holds" in section
        assert "result.cost" not in text().split("## A first agent")[1].split("\n## ")[0]

    def test_every_name_the_builtins_snippet_imports_exists(self) -> None:
        """The first example reaches into `simple_agents.builtins`, which the export check
        above cannot see: its pattern anchors on the top-level package."""
        import simple_agents.builtins as builtins

        imported = re.findall(r"^from simple_agents\.builtins import (.+)$", text(), re.MULTILINE)

        assert imported
        for line in imported:
            for name in (part.strip() for part in line.split(",")):
                assert hasattr(builtins, name), name
