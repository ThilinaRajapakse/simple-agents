"""Finding the files a check reads, and reading them without trusting their shape.

Every check in the v0 suite reads an artifact: the brief, a run directory, or an evaluation
results file. A project accumulates many of each, so the runner picks the most recent and the
report names what it read.

No typed reader is used on the way in. `EvalResults.read` refuses a file whose format version
this library does not write, and a file it did not write is what several checks exist to catch,
so a malformed artifact has to arrive at the check that reads it rather than raising here.
`runs()` is used to find a run directory, and it satisfies the same requirement: a run whose
manifest cannot be parsed is still returned, and the check that reads it reports why.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..envelope import runs
from ..records.manifest import DEFAULT_ROLE

__all__ = [
    "Artifacts",
    "IDEA_SECTIONS",
    "PRODUCT_SECTION",
    "empty_sections",
    "other_roles",
    "read_json",
    "read_jsonl",
]

DEFAULT_BRIEF = "brief.toml"
DEFAULT_IDEA = "idea.md"
DEFAULT_DESIGN = "design.md"
DEFAULT_RESEARCH = "research.md"
DEFAULT_RUNS = "runs"
DEFAULT_RESULTS = "evals/results"

# The five sections `docs/procedure.md` and FT-29 both name, spelled as they spell them. A
# project writes its headings from those documents, so the two have to agree word for word.
IDEA_SECTIONS: tuple[str, ...] = (
    "What this is",
    "Who it is for",
    "What it works on",
    "Where this is going and where it is not",
    "What is still open",
)

# The four `docs/procedure.md` and FT-34 both name, spelled as they spell them. Four rather
# than six: what each step decides for itself is the brief's `agency_boundary` and what it
# will not do is `not_building`, and a project asked to write either twice fills in a form.
PRODUCT_SECTION = "The product"
"""The `design.md` section listing what the end user can do, classified (`docs/product.md`
§2). FT-34 reads it against the surfaces a project's `Product` declares."""

DESIGN_SECTIONS: tuple[str, ...] = (
    "What it does, step by step",
    "What it holds on to between runs",
    "The product",
    "What the builder said about it",
)

# The four `docs/procedure.md` and FT-36 both name, spelled as they spell them. The second is
# the survey and carries a table with an `Outcome` column, which is what OUTCOME_COLUMN reads.
RESEARCH_SECTIONS: tuple[str, ...] = (
    "The parts, and what each has to do",
    "What was found against each part",
    "What this turns on, having looked",
    "What the builder said about it",
)

# The section holding the survey, and the column every row of it fills. A candidate with an
# empty outcome is a source the research stage listed and never looked at.
SURVEY_SECTION = "What was found against each part"
OUTCOME_COLUMN = "Outcome"

# The section that has to carry the builder's own words. A blockquote or quotation marks say
# a passage is quoted; neither says the words are the builder's, and nothing can.
QUOTED_SECTION = "What the builder said about it"


@dataclass(frozen=True, slots=True)
class Artifacts:
    """Where a project's files are, after looking in the conventional places.

    ::

        found = Artifacts.discover(Path("."))
        found.run_dir       # runs/<the most recent one holding a manifest>
        found.results       # evals/results/<the most recent results file>

    Any of the three can be given explicitly, which is what the command line's ``--brief``,
    ``--run`` and ``--results`` do. A field is ``None`` when nothing was found, and the check
    that reads it says so rather than this raising.
    """

    root: Path
    brief: Path | None
    run_dir: Path | None
    results: Path | None
    idea: Path | None = None
    design: Path | None = None
    """The account of how the agent is built, and ``None`` where the project has none. FT-34
    reads it from stage ``shape``."""

    research: Path | None = None
    """What was found about each part before anything was designed, and ``None`` where the
    project has none. FT-36 reads it from stage ``research``."""

    live_run: Path | None = None
    """The newest run an end user made, and ``None`` where the project has none. FT-31 reads
    it, and its presence is what shows the project reached stage ``ship``."""

    @classmethod
    def discover(
        cls,
        root: Path,
        *,
        brief: Path | None = None,
        run_dir: Path | None = None,
        results: Path | None = None,
    ) -> Artifacts:
        """Look in the conventional places, keeping anything passed explicitly.

        A project with several results files says which one it reports through ``results`` in
        the brief, and that one is read. Without it the most recent by ``created_at`` is read,
        which on a project that measured a variant last is the variant.
        """
        root = Path(root)
        found_brief = brief if brief is not None else _first_existing(root / DEFAULT_BRIEF)
        declared = _declared_results(found_brief)
        return cls(
            root=root,
            brief=found_brief,
            run_dir=run_dir if run_dir is not None else _latest_run(root),
            results=(
                results
                if results is not None
                else (root / declared if declared else _latest_results(root))
            ),
            idea=_first_existing(root / DEFAULT_IDEA),
            design=_first_existing(root / DEFAULT_DESIGN),
            research=_first_existing(root / DEFAULT_RESEARCH),
            live_run=_latest_live_run(root),
        )

    def relative(self, path: Path | None) -> str | None:
        """A path as the report shows it, relative to the project root where it sits under."""
        if path is None:
            return None
        try:
            return str(Path(path).relative_to(self.root))
        except ValueError:
            return str(path)

    def reading_a_live_run(self) -> str | None:
        """A note where the checks had no run but a live one to read.

        ``None`` where the project has a run made while building, which is what the checks are
        about. A project that shipped and kept nothing else still gets its checks run, against
        a run an end user made.
        """
        if self.run_dir is None or self.live_run is None:
            return None
        if self.run_dir != self.live_run:
            return None
        return (
            f"Every run under {DEFAULT_RUNS}/ is marked live, so the checks read one an end "
            f"user made: {self.relative(self.run_dir)}. These checks are about what the "
            f"project built, and a live run can be sampled down to no payloads. A run made "
            f"while building is what they usually read."
        )

    def different_evaluations(self) -> str | None:
        """A note where the run checks and the results checks read different measurements.

        ``None`` where they agree, where either is missing, or where the run was not part of an
        evaluation at all, which is an ordinary thing for a project to have lying about.

        Some checks read a run directory and some read a results file. Nothing requires them to
        describe the same measurement, and a project that measures, improves, then measures
        again can have them describe different ones: the brief's ``results`` key is written by
        hand and stays where it was put, while the run directory is found by recency.
        """
        if self.results is None or self.run_dir is None:
            return None
        data, reason = read_json(self.results)
        if reason is not None or not isinstance(data, dict):
            return None
        covered = {
            str(Path(rollout["trajectory"]).parent)
            for rollout in (data.get("rollouts") or [])
            if isinstance(rollout, dict) and rollout.get("trajectory")
        }
        if not covered:
            return None
        run = self.relative(self.run_dir) or ""
        if run in covered or self.run_dir.name.startswith("run_"):
            return None
        evaluations = sorted({str(Path(entry).parent) for entry in covered})
        return (
            f"The checks that read a run and the checks that read a results file are "
            f"describing different measurements. The run is {run}; the results file "
            f"{self.relative(self.results)} was scored from "
            f"{', '.join(evaluations)}. Both are reported, and neither says anything about "
            f"the other. Point the brief's `results` key at the measurement this project "
            f"reports, or pass --results and --run naming one measurement."
        )


def empty_sections(text: str, sections: tuple[str, ...] = IDEA_SECTIONS) -> tuple[str, ...]:
    """The `sections` that a document is missing or has left blank, in order.

    A section is a markdown heading at any level whose text matches, and it counts as filled
    when anything other than whitespace follows it before the next heading::

        empty_sections(Path("idea.md").read_text())     # ('What is still open',)

    Matching ignores case, punctuation and spacing, so a project writing `## What this is:`
    is not failed for the colon and `## Where this is going, and where it is not` counts as
    `Where this is going and where it is not`.
    """
    found: dict[str, list[str]] = {}
    current: str | None = None
    wanted = {_heading_key(name): name for name in sections}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            current = wanted.get(_heading_key(line.lstrip("#")))
            if current is not None:
                found.setdefault(current, [])
        elif current is not None and line.strip():
            found[current].append(line)
    return tuple(name for name in sections if not found.get(name))


def survey_rows(text: str, section: str, column: str) -> tuple[tuple[str, str], ...]:
    """Every candidate under `section`, as the name a reader would call it and its outcome.

    The survey is a markdown table, one row per candidate, and `column` says what was decided
    about each::

        survey_rows(research, "What was found against each part", "Outcome")

    The name is every cell before the column, joined, so a row keyed on both a part and a
    candidate names both. A row too short to reach the column has an outcome of ``""``, which
    is what a row with none written looks like.

    A blank line ends a markdown table, so a section holding two of them reads each against its
    own header, and a table whose header does not name the column contributes nothing.
    """
    found: list[tuple[str, str]] = []
    for rows in _tables_under(text, section):
        header, *body = rows
        keys = [_heading_key(cell) for cell in header]
        if _heading_key(column) not in keys:
            continue
        index = keys.index(_heading_key(column))
        for cells in body:
            if all(set(cell) <= set("-: ") for cell in cells):
                continue
            before = [cell.strip("*_` ") for cell in cells[:index] if cell.strip("*_` ")]
            outcome = cells[index].strip("*_` ") if index < len(cells) else ""
            found.append((" / ".join(before) or "an unnamed row", outcome))
    return tuple(found)


def rows_with_no_outcome(text: str, section: str, column: str) -> tuple[str, ...]:
    """The candidates under `section` whose `column` cell says nothing, named.

    A cell holding nothing, a dash or an ellipsis says nothing, and so does a row too short to
    reach the column::

        rows_with_no_outcome(research, "What was found against each part", "Outcome")
    """
    return tuple(
        name for name, outcome in survey_rows(text, section, column) if _heading_key(outcome) == ""
    )


def _tables_under(text: str, section: str) -> list[list[list[str]]]:
    """Each markdown table under `section`, as rows of stripped cells.

    A run of lines opening with a pipe is one table, so a blank line or any other line ends
    one and the next run is read against its own header.
    """
    wanted = _heading_key(section)
    inside = False
    tables: list[list[list[str]]] = []
    current: list[list[str]] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            inside = _heading_key(stripped.lstrip("#")) == wanted
            current = None
            continue
        if inside and stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if current is None:
                current = []
                tables.append(current)
            current.append(cells)
        else:
            current = None
    return tables


def tables_under(text: str, section: str) -> int:
    """How many markdown tables `section` holds.

    A blank line ends a markdown table, for a renderer as for this, so a section reporting two
    where one was written is a row separated from its header by a blank line.
    """
    return len(_tables_under(text, section))


def has_table(text: str, section: str, column: str | None = None) -> bool:
    """Whether `section` holds a markdown table, and where given, one whose header names
    `column`.

    A table whose header does not name the column is what a project that renamed it produces,
    and reading only the rows would report nothing and pass. Only the header row is read, so a
    cell further down holding the word does not satisfy it.
    """
    tables = _tables_under(text, section)
    if column is None:
        return bool(tables)
    return any(
        _heading_key(column) in {_heading_key(cell) for cell in header} for header, *_ in tables
    )


def quoted_in(text: str, section: str) -> bool:
    """Whether a passage under `section` is presented as a quotation.

    A markdown blockquote or a run of text in double or single quotation marks. Both are ways
    of writing "these are their words", and a project that used one is not failed for not
    using the other::

        quoted_in(design, "What the builder said about it")     # True

    **This reads a shape, never a fact.** Nothing in the file says whose words are inside the
    quotation, or that anyone said them, and no check can.
    """
    wanted = _heading_key(section)
    inside = False
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            inside = _heading_key(line.lstrip("#")) == wanted
            continue
        if not inside:
            continue
        stripped = line.strip()
        if stripped.startswith(">"):
            return True
        if _QUOTATION.search(stripped):
            return True
    return False


# A pair of quotation marks with something between them, in the straight and curly forms a
# markdown file arrives in.
_QUOTATION = re.compile(r"[\"\u201c'\u2018][^\"\u201d'\u2019]+[\"\u201d'\u2019]")

_PUNCTUATION = re.compile(r"[^a-z0-9]+")


def _heading_key(text: str) -> str:
    """A heading reduced to the words in it, so punctuation and spacing cannot fail a match."""
    return _PUNCTUATION.sub(" ", text.casefold()).strip()


def read_json(path: Path) -> tuple[Any, str | None]:
    """Parse a JSON file, returning the value and a reason when it could not be read.

    Returns ``(None, reason)`` on anything unreadable, so a check reports the file rather
    than raising::

        data, reason = read_json(Path("evals/results/v3.json"))
        if reason is not None:
            ...
    """
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"{path.name} does not exist"
    except json.JSONDecodeError as exc:
        return None, f"{path.name} is not JSON: {exc}"
    except OSError as exc:
        return None, f"{path.name} could not be read: {exc}"


def read_jsonl(path: Path) -> tuple[list[Any], str | None]:
    """Parse a JSON-lines file, returning the records and a reason on the first bad line.

    Blank lines are skipped. The records read before a bad line are returned with it, so a
    check can report both what it found and where reading stopped.
    """
    records: list[Any] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return records, f"{path.name} does not exist"
    except OSError as exc:
        return records, f"{path.name} could not be read: {exc}"
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            return records, f"line {number} of {path.name} is not JSON: {exc}"
    return records, None


def _first_existing(path: Path) -> Path | None:
    return path if path.exists() else None


def _latest_run(root: Path) -> Path | None:
    """The most recent run of the project's agent that finished, by the manifest's start time.

    `nested=True` because an evaluation writes a directory per rollout under one for the
    evaluation, and a project that only ever evaluated has its runs there and nowhere else.

    **Only runs whose role is `agent` are read.** A project's labelling pass, judge or ablation
    goes through the same envelope and writes the same directory, and the checks are about the
    agent, so a run declaring another role is not one of them.

    **A run marked live is read only where the project has no other.** These checks are about
    what the project built, and a live run belongs to an end user: it can be sampled down to no
    payloads and it carries their material. A project whose every run is live has still
    recorded everything, so the newest is read and the report says which it was.

    A run that is still executing, or that crashed on its first node, writes a manifest and a
    trajectory like any other, so picking the newest by start time alone reads whichever run
    began last rather than the one the project has to show. Runs that finished are preferred,
    and where none did the newest is returned so the checks report what is wrong with it rather
    than reporting no run at all.
    """
    found = runs(root / DEFAULT_RUNS, nested=True, role=DEFAULT_ROLE)
    pool = [handle for handle in found if not handle.live] or found
    if not pool:
        return None
    finished = [handle for handle in pool if handle.finished]
    return (finished or pool)[0].path


def _latest_live_run(root: Path) -> Path | None:
    """The most recent live run, which is what the ship gate reads (FT-31)."""
    found = runs(root / DEFAULT_RUNS, nested=True, role=DEFAULT_ROLE, live=True)
    if not found:
        return None
    finished = [handle for handle in found if handle.finished]
    return (finished or found)[0].path


def other_roles(root: Path) -> dict[str, int]:
    """Runs under `runs/` that are not the agent's, counted by role.

    What a project has when every run it wrote was a labelling pass or a judge, which is a
    different report from having written no run at all.
    """
    counted: dict[str, int] = {}
    for handle in runs(root / DEFAULT_RUNS, nested=True):
        if handle.role != DEFAULT_ROLE:
            counted[handle.role] = counted.get(handle.role, 0) + 1
    return counted


def _declared_results(brief: Path | None) -> str | None:
    """The results file the brief names, or ``None`` where it names none.

    Read with tomllib rather than through ``Brief``, because a brief this cannot parse is
    what the elicitation check exists to report, and it has to reach that check.
    """
    if brief is None or not brief.exists():
        return None
    try:
        declared = tomllib.loads(brief.read_text(encoding="utf-8")).get("results")
    except (tomllib.TOMLDecodeError, OSError):
        return None
    return str(declared) if isinstance(declared, str) and declared.strip() else None


def _latest_results(root: Path) -> Path | None:
    """The most recent results file, by its own `created_at`."""
    files = sorted((root / DEFAULT_RESULTS).glob("*.json"))
    if not files:
        return None
    return max(files, key=_created_at)


def _created_at(path: Path) -> tuple[str, float]:
    data, _ = read_json(path)
    stamp = data.get("created_at") if isinstance(data, dict) else None
    return (str(stamp or ""), path.stat().st_mtime)
