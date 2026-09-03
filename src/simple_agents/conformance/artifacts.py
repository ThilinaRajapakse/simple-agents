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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..envelope import RunHandle, runs
from ..records.manifest import DEFAULT_ROLE

__all__ = [
    "Artifacts",
    "ByPipeline",
    "TheOneRead",
    "runs_by_pipeline",
    "measured_pipeline",
    "slice_nodes",
    "the_run_to_compare",
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

    by_pipeline: ByPipeline = field(default_factory=lambda: ByPipeline())
    """The newest run of each registered pipeline, read once for every check that needs it.

    Every manifest under ``runs/`` is opened to build it, so it is read here rather than per
    check. ``run_dir`` is chosen out of it."""

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

        **The run is the newest run of the pipeline that results file measured**, so a project
        running a background pass every morning is not read by that pass
        (``docs/conformance.md`` §3.8). ``run_dir`` given explicitly wins over all of it.
        """
        root = Path(root)
        found_brief = brief if brief is not None else _first_existing(root / DEFAULT_BRIEF)
        declared = _declared_results(found_brief)
        found_results = (
            results
            if results is not None
            else (root / declared if declared else _latest_results(root))
        )
        grouped = runs_by_pipeline(root)
        return cls(
            root=root,
            brief=found_brief,
            run_dir=(
                run_dir
                if run_dir is not None
                else _latest_run(root, grouped, _config_in(found_results))
            ),
            results=found_results,
            idea=_first_existing(root / DEFAULT_IDEA),
            design=_first_existing(root / DEFAULT_DESIGN),
            research=_first_existing(root / DEFAULT_RESEARCH),
            live_run=_latest_live_run(root),
            by_pipeline=grouped,
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
        """A note where the pipeline the checks read has nothing but live runs.

        ``None`` where that pipeline has a run made while building, which is what the checks
        are about. A project that shipped and kept nothing else still gets its checks run,
        against a run an end user made. It names the pipeline rather than the directory: the
        checks read one pipeline's runs, and another may have plenty made while building
        (`docs/conformance.md` §3.8).
        """
        if self.run_dir is None or self.live_run is None:
            return None
        if self.run_dir != self.live_run:
            return None
        manifest, _ = read_json(self.run_dir / "manifest.json")
        named = (manifest or {}).get("pipeline") if isinstance(manifest, dict) else None
        whose = f"Every run of {named!r}" if isinstance(named, str) and named else "Every run"
        return (
            f"{whose} the checks could read is marked live, so they read one an end user "
            f"made: {self.relative(self.run_dir)}. These checks are about what the project "
            f"built, and a live run can be sampled down to no payloads. A run made while "
            f"building is what they usually read."
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


def _config_in(results: Path | None) -> Any:
    """The ``config`` of a results file, or ``None`` where there is none to read."""
    if results is None:
        return None
    held, reason = read_json(results)
    if reason is not None or not isinstance(held, dict):
        return None
    return held.get("config")


def _latest_run(root: Path, grouped: ByPipeline, config: Any = None) -> Path | None:
    """The run every check that reads one run reads, or ``None`` where the project has none.

    **The newest run of the pipeline the results file measured** (`docs/conformance.md` §3.8).
    A project runs whichever pipeline it was asked for, so the newest run of any of them is
    usually a pipeline the project reports no number about: on one running a background pass
    every morning it is that pass, and a check reading it reads a graph with no model call, no
    prompt and no tool. Where nothing names a pipeline, the newest run of any is read, which is
    what this always did.

    **Only runs whose role is `agent` are read**, and a run whose model answered from a script
    is left out: a labelling pass, a judge, an ablation and a stand-in are not the agent
    (`docs/run-envelope.md` §2.1).

    **A run marked live is read only where the pipeline has no other**, and a run that finished
    is preferred to one still executing or one that crashed on its first node. A live run
    belongs to an end user: it can be sampled down to no payloads and it carries their
    material. Where a pipeline has nothing else, the newest is read anyway, so the checks
    report what is wrong with it rather than reporting no run at all.
    """
    wanted, _nodes = measured_pipeline(config)
    if wanted is not None and grouped.names_recorded:
        held = grouped.for_pipeline(wanted)
        if held is not None:
            return held.path
    found = runs(root / DEFAULT_RUNS, nested=True, role=DEFAULT_ROLE)
    pool = [handle for handle in found if not handle.live] or found
    if not pool:
        return None
    finished = [handle for handle in pool if handle.finished]
    return (finished or pool)[0].path


@dataclass(frozen=True, slots=True)
class ByPipeline:
    """The newest run of each registered pipeline, read once for the checks that need it.

    ``newest`` is keyed by the name a run recorded under ``pipeline``, with ``None`` holding
    the newest run that recorded no name. ``names_recorded`` is false where no run read
    carries the field at all, which is every project whose runs predate manifest format
    ``0.41``, and the checks fall back to reading the newest run of any pipeline and say so.
    """

    newest: dict[str | None, RunHandle] = field(default_factory=dict)
    matching: dict[tuple[str | None, tuple[str, ...] | None], RunHandle] = field(
        default_factory=dict
    )
    """The newest run of each (pipeline, slice) pair, which is what identifies what ran."""

    names_recorded: bool = False
    runs_read: int = 0

    def named(self) -> tuple[str, ...]:
        """Every pipeline name a run recorded, in the order a report reads them."""
        return tuple(sorted(name for name in self.newest if name))

    def of(self, name: str | None, nodes: tuple[str, ...] | None) -> RunHandle | None:
        """The newest run of one pipeline that held these nodes, or ``None`` where none did.

        ``nodes`` is what the results file's ``slice`` held, and ``None`` for a whole pipeline.
        A rung of ``recommend`` and the whole of it record one name, so the nodes are what
        separate them: without that a project whose evaluation measured a rung reads its figure
        against the whole pipeline's stamp, and the two never agree.
        """
        return self.matching.get((name, nodes))

    def for_pipeline(self, name: str) -> RunHandle | None:
        """The run that speaks for one pipeline: its newest whole run, else its newest rung.

        What every reader that wants "this project's `recommend`" takes, so the run the checks
        read and the run a stamp is compared against cannot drift apart. ``None`` where nothing
        has run it.
        """
        return self.of(name, None) or self.newest.get(name)


def slice_nodes(record: Any) -> tuple[str, ...] | None:
    """The nodes a ``slice`` record held, and ``None`` where the pipeline was whole.

    Reads the same shape from a manifest and from a results file's ``config``, since
    ``SliceOf.to_record`` writes both. A slice holds at least one node, so a record naming
    none is read as a whole pipeline rather than as a slice of nothing: a run and a results
    file that disagree about that would never match each other.
    """
    if not isinstance(record, dict):
        return None
    held = record.get("nodes")
    if not isinstance(held, list) or not held:
        return None
    return tuple(str(node) for node in held)


def runs_by_pipeline(root: Path) -> ByPipeline:
    """Read every run under ``root/runs`` for the newest of each registered pipeline.

    Read once for the whole suite rather than per check, for the reason ``produced_across``
    is: it opens every manifest, and FT-25, FT-37 and FT-38 all want it.

    **A run made by a scripted client is left out**, and so is one whose role is not ``agent``:
    these checks are about what the project's own agent recorded. Within one pipeline, a run
    that finished is read before one still executing, and a run made while building before a
    live one, since a live run belongs to an end user and carries their material.
    """
    found = runs(root / DEFAULT_RUNS, nested=True, role=DEFAULT_ROLE)
    readable = [handle for handle in found if handle.unreadable is None]
    newest: dict[str | None, RunHandle] = {}
    matching: dict[tuple[str | None, tuple[str, ...] | None], RunHandle] = {}
    for handle in _preferred(readable):
        newest.setdefault(handle.pipeline, handle)
        matching.setdefault((handle.pipeline, slice_nodes(handle.manifest.get("slice"))), handle)
    return ByPipeline(
        newest=newest,
        names_recorded=any(handle.pipeline for handle in readable),
        runs_read=len(readable),
        matching=matching,
    )


@dataclass(frozen=True, slots=True)
class TheOneRead:
    """Which run the checks that read within one pipeline compare against, and how it was chosen.

    ``stamp`` is that run's ``behaviour_fingerprint`` and ``where`` the manifest it came from.
    ``reason`` is set where no run could be chosen, and is what a check reports as blocked.
    ``note`` says the read was widened to the newest run of any pipeline, and is ``None`` where
    the pipeline was named.
    """

    stamp: str | None = None
    where: Path | None = None
    reason: str | None = None
    note: str | None = None


def measured_pipeline(config: Any) -> tuple[str | None, tuple[str, ...] | None]:
    """Which pipeline a results file's ``config`` measured, and which nodes of it.

    ``(None, None)`` where it names none, which is a file written before the field existed.
    """
    if not isinstance(config, dict):
        return None, None
    named = config.get("pipeline")
    if not isinstance(named, str) or not named:
        return None, None
    return named, slice_nodes(config.get("slice"))


def the_run_to_compare(artifacts: Artifacts, config: Any, *, whole: bool) -> TheOneRead:
    """The newest run of the pipeline a results file measured, for FT-37 and FT-38.

    ``whole=True`` reads the pipeline rather than the rung, which is what FT-38 wants: the
    brief's entries describe the agent. FT-37 passes ``False`` and matches the nodes too, so a
    number is compared against the run it was measured over. Both fall back to the newest run
    of any pipeline where nothing names one, which is what these checks read before the name
    existed.

    `simple-agents record read-against` writes what this returns, so the command that clears
    FT-38 and the check that reports it read one run.
    """
    grouped = artifacts.by_pipeline
    wanted, nodes = measured_pipeline(config)
    if wanted is None or not grouped.names_recorded:
        return _the_newest_run_of_any(artifacts, wanted)
    handle = grouped.of(wanted, None if whole else nodes)
    if handle is not None:
        return _made_by(handle, wanted)
    if not whole:
        return TheOneRead(reason=_nothing_has_run(grouped, wanted, sliced=bool(nodes)))
    only_rungs = grouped.for_pipeline(wanted)
    if only_rungs is None:
        return TheOneRead(reason=_nothing_has_run(grouped, wanted, sliced=False))
    found = _made_by(only_rungs, wanted)
    return TheOneRead(
        stamp=found.stamp,
        where=found.where,
        reason=found.reason,
        note=(
            f"Every run of {wanted!r} on disk is of a slice of it, so these entries are read "
            f"against the newest of those. Running the whole pipeline once is what gives the "
            f"brief the stamp it describes."
        ),
    )


def _made_by(handle: RunHandle, wanted: str) -> TheOneRead:
    """One run's stamp, or a reason it carries none."""
    where = handle.path / "manifest.json"
    stamp = handle.manifest.get("behaviour_fingerprint")
    if not isinstance(stamp, str) or not stamp:
        return TheOneRead(
            where=where,
            reason=(
                f"The newest run of {wanted!r} carries no behaviour_fingerprint, so it was "
                f"written before the field existed and what it was made by is unrecorded."
            ),
        )
    return TheOneRead(stamp=stamp, where=where)


def _nothing_has_run(grouped: ByPipeline, wanted: str, *, sliced: bool) -> str:
    """Why no run answers for this pipeline, naming the ones that do."""
    named = ", ".join(grouped.named()) or "none"
    of_it = " over the nodes this evaluation measured" if sliced else ""
    return (
        f"Nothing under {DEFAULT_RUNS}/ has run the pipeline {wanted!r}{of_it}, so no run "
        f"says whether it has moved since this results file was written. The pipelines the "
        f"runs record are: {named}. Run {wanted!r} once, or re-run the evaluation over the "
        f"pipeline the project now has."
    )


def _the_newest_run_of_any(artifacts: Artifacts, wanted: object) -> TheOneRead:
    """What these checks read before a pipeline name was on either artifact."""
    where = artifacts.run_dir / "manifest.json" if artifacts.run_dir else None
    if artifacts.run_dir is None:
        return TheOneRead(
            reason="No run directory under runs/. The pipeline is unrecorded (FT-13)."
        )
    manifest, reason = read_json(where)
    if reason is not None or not isinstance(manifest, dict):
        return TheOneRead(
            where=where, reason="The newest run's manifest could not be read, which FT-13 reports."
        )
    stamp = manifest.get("behaviour_fingerprint")
    if not isinstance(stamp, str) or not stamp:
        return TheOneRead(
            where=where,
            reason=(
                "The newest run's manifest carries no behaviour_fingerprint, so it was written "
                "before the field existed, and the pipeline it describes is unrecorded."
            ),
        )
    return TheOneRead(stamp=stamp, where=where, note=_why_it_widened(artifacts.by_pipeline, wanted))


def _why_it_widened(grouped: ByPipeline, wanted: object) -> str | None:
    """Why the read fell back to the newest run of any pipeline, or ``None`` where it did not.

    Two projects reach this. One evaluated before the results file carried a pipeline name;
    the other has runs that all predate the manifest field. Both read as they did before, and
    the difference is worth naming, since on a project with more than one pipeline the run that
    answers may be one nothing reported a number for.
    """
    if not grouped.names_recorded and grouped.runs_read:
        return (
            f"No run under {DEFAULT_RUNS}/ records which pipeline it is, so this read the "
            f"newest run of any of them. Runs record it from manifest format 0.41."
        )
    named = len(grouped.named())
    if (not isinstance(wanted, str) or not wanted) and named > 1:
        return (
            f"The results file records no pipeline name, so this read the newest run of any of "
            f"the {named} pipelines the runs record. A results file written by this version "
            f"records which pipeline it measured."
        )
    return None


def _preferred(found: list[RunHandle]) -> list[RunHandle]:
    """The runs in the order these checks read them: finished before unfinished, built before live.

    ``runs`` returns newest first and this is stable, so the newest of each group keeps its
    place within it. A run still executing, or one that crashed on its first node, writes a
    manifest like any other, and a live run carries an end user's material, so both are read
    where a pipeline has nothing else and not before.
    """
    return (
        [handle for handle in found if handle.finished and not handle.live]
        + [handle for handle in found if handle.finished and handle.live]
        + [handle for handle in found if not handle.finished and not handle.live]
        + [handle for handle in found if not handle.finished and handle.live]
    )


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
