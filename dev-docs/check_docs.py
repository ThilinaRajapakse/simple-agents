"""Checks over `dev-docs/` itself. Run it before presenting written work here.

    uv run python dev-docs/check_docs.py [--fix] [--self-test] [--today YYYY-MM-DD] [--since REF]

It lives here rather than in `tests/` because a builder reads `tests/`, and nothing about the
maintainer's own documents belongs on that surface. `scripts/prose_check.py` and
`scripts/check_citations.py` cover the shipped tree; this covers ours.

Every rule below is something a session has silently undone before. `CLAUDE.md` states them; this
enforces them, and each message says what to do rather than only what is wrong.

The required build-log headings are read out of `templates/build-log.md` rather than hardcoded, so
changing the standard means editing the template and nothing here.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# The tree under test. `--self-test` points these at a copy holding one deliberate defect, so
# every rule is exercised against data whose correct answer is known. A rule with no fixture in
# SELF_TESTS has no check, which makes that list the coverage map as well as the suite.
ROOT = HERE
REPO_ROOT = REPO

# The four files a session always starts from. Nothing else sits at the root.
ROOT_FILES = {"handoff.md", "plan.md", "simple-agents.md", "random-thoughts-questions.md"}
DIRECTORIES = {"items", "build-logs", "runs", "design", "templates", "archive"}

HANDOFF_CEILING = 120
# A §4 Done entry, in characters the reader sees (link targets left out). One line: what
# shipped, what it cost, a link. The paragraphs the section carried by 2026-08-29 ran to 2,500.
DONE_ENTRY_CEILING = 450

# Inbox entries are temporary. Reported, then failed.
INBOX_REPORT_DAYS = 3
INBOX_FAIL_DAYS = 7
DEFERRED_REPORT_DAYS = 21

QUEUE_ID = re.compile(r"\bP3-\d+\b")
DATE = re.compile(r"\b(2\d{3})-(\d{2})-(\d{2})\b")
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)#L\d+\)")  # group 1 is the target
# `Left open` saying this entry goes nowhere, which is a real answer and has to be stated.
# An entry wraps, so "Destination:" and its `nothing` land on different lines. Matching
# across the newline and not across a full stop is what keeps a prose "nothing" out.
NO_DESTINATION = re.compile(r"destination[^.]{0,40}\bnothing\b", re.I)
BARE_PATH = re.compile(r"`(?:build-logs|items|runs|design|archive)/[A-Za-z0-9._/-]+\.md`")


# Written before the six-section template existed. Rewriting them would be re-writing history to
# fit a form. The list is here so it is visible, and it shrinks if one is ever retrofitted.
# A survey written long before the item template, 1,700 lines with its own section scheme.
GRANDFATHERED_ITEMS = {"example-projects"}
# Findings and setups written before their templates existed.
GRANDFATHERED_RUNS = {"dogfood-1", "dogfood-2", "dogfood-3", "dogfood-4",
                      "checkpoint-item5", "checkpoint-item7"}

GRANDFATHERED_LOGS = {
    "ablate", "absorption-item1", "absorption-item2", "absorption-item3", "absorption-items4-7",
    "absorption-items8-9", "concurrency", "consultation", "decision-surface", "dogfood-3-fixes",
    "dogfood-4-fixes", "full-test-checkpoint", "gemini-adapter", "ground-truth", "item8a",
    "item8b", "item8c", "item8d", "item8e", "item8f", "item8g", "item9", "item10", "item13",
    "item14", "loop-accumulator", "memory", "paid-eval", "per-node-model", "pipeline-as-tool",
    "recording-default", "rescore", "semantic-recall", "ship-stage", "tool-spend",
    "typed-consultation",
}
# Ran before the inventory genre existed; their dispositions are inside findings.md §9.
RUNS_WITHOUT_INVENTORY = {"dogfood-1", "dogfood-2", "dogfood-3", "checkpoint-item5",
                          "checkpoint-item7"}
# A QA pass with its own eight-directory shape, which the run layout does not fit.
IRREGULAR_RUNS = {"full-test-2026-08-13"}
RUN_FILES = {"setup.md", "findings.md", "inventory.md"}
# A task run cold more than once keeps one findings record per run.
EXTRA_RUN = re.compile(r"^run\d+-findings\.md$")

# Dated records of a past sitting. They say what was true when they were written.
FROZEN = ("archive", "full-test-2026-08-13")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def fail(self, message: str) -> None:
        self.failures.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _age(text: str, today: date) -> int | None:
    """Days since the newest date mentioned, or None if the text carries no date."""
    found = [date(int(y), int(m), int(d)) for y, m, d in DATE.findall(text)]
    return (today - max(found)).days if found else None


def check_placement(report: Report) -> None:
    for entry in sorted(ROOT.iterdir()):
        if entry.name.startswith(".") or entry.name == "__pycache__":
            continue
        if entry.is_dir():
            if entry.name not in DIRECTORIES:
                report.fail(
                    f"{entry.name}/ is not one of the six directories "
                    f"({', '.join(sorted(DIRECTORIES))}). Move it into the one whose genre it is, "
                    "or argue for a seventh in CLAUDE.md first."
                )
            continue
        if entry.suffix == ".md" and entry.name not in ROOT_FILES:
            report.fail(
                f"{entry.name} is loose at the dev-docs root. Only {', '.join(sorted(ROOT_FILES))} "
                "belong there. A record of open work goes in items/, a built item in build-logs/, "
                "a run in runs/, standing design in design/."
            )

    for path in sorted(ROOT.rglob("*")):
        if path.is_dir() or path.suffix not in {".md", ".py"} or "__pycache__" in path.parts:
            continue
        if any(part in FROZEN for part in path.parts):
            continue
        if path.name != path.name.lower() or ("_" in path.stem and path.suffix == ".md"):
            report.fail(
                f"{path.relative_to(ROOT)} is not lowercase-hyphenated. Rename it; the directory "
                "names the genre and the file names the subject."
            )


def check_runs(report: Report) -> None:
    runs = ROOT / "runs"
    for entry in sorted(runs.iterdir()):
        if entry.is_file():
            continue
        if entry.name in IRREGULAR_RUNS:
            continue
        extra = {
            p.name for p in entry.iterdir()
            if p.is_file() and p.name not in RUN_FILES and not EXTRA_RUN.match(p.name)
        }
        if extra:
            report.fail(
                f"runs/{entry.name}/ holds {', '.join(sorted(extra))}. A run directory holds "
                f"{', '.join(sorted(RUN_FILES))} and nothing else."
            )
        names = {p.name for p in entry.iterdir()}
        if "findings.md" in names and "inventory.md" not in names:
            if entry.name not in RUNS_WITHOUT_INVENTORY:
                report.warn(
                    f"runs/{entry.name}/ has findings.md and no inventory.md. A findings record "
                    "says what was found; an inventory says what to do about each one. Without it "
                    "the findings have no queue."
                )
        if entry.name not in GRANDFATHERED_RUNS:
            for name, template in (("findings.md", "run-findings.md"),
                                   ("setup.md", "run-setup.md"),
                                   ("inventory.md", "run-inventory.md")):
                if (entry / name).exists():
                    check_against_template(report, entry / name, template)
                elif name != "inventory.md":
                    report.warn(
                        f"runs/{entry.name}/ has no {name}. A run records how it was set up and "
                        "what it found; both are read by the next run."
                    )
        if "inventory.md" in names:
            plan = _read(ROOT / "plan.md")
            if entry.name not in plan:
                report.warn(
                    f"runs/{entry.name}/inventory.md exists and plan.md names no item for it. "
                    "An inventory nobody is scheduled to work through is a queue with no owner."
                )


def check_items(report: Report) -> None:
    plan = _read(ROOT / "plan.md")
    for path in sorted((ROOT / "items").glob("*.md")):
        built = ROOT / "build-logs" / f"{path.stem}-build-log.md"
        if built.exists():
            report.fail(
                f"items/{path.name} exists and so does build-logs/{built.name}. An items/ record "
                "moves when the item is built: to build-logs/ if the log now says everything it "
                "said, to design/ if it is standing design of record, to archive/ if superseded."
            )
        if path.stem not in GRANDFATHERED_ITEMS:
            check_against_template(report, path, "item.md")
        if f"items/{path.name}" not in plan:
            report.fail(
                f"items/{path.name} is not linked from plan.md. Either it is work nobody "
                "scheduled, or the row that owns it is missing its link."
            )


def required_headings(template: str) -> list[str]:
    """The sections a record must carry, read from its template so there is one source of truth.

    Every genre with a template is held to it. Hardcoding one template is what let `items/`
    records ship with two of four sections for a day: the rule existed, in a file nothing read.
    """
    text = _read(ROOT / "templates" / template)
    return [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]


def _headings_of(path: Path) -> list[str]:
    """A record's own `##` headings, with any leading section number removed."""
    return [re.sub(r"^\d+\.\s*", "", line[3:].strip())
            for line in _read(path).splitlines() if line.startswith("## ")]


def check_against_template(report: Report, path: Path, template: str) -> None:
    wanted = [re.sub(r"^\d+\.\s*", "", h) for h in required_headings(template)]
    present = _headings_of(path)
    missing = [h for h in wanted if h not in present]
    if missing:
        report.fail(
            f"{path.relative_to(REPO_ROOT)} is missing {', '.join(missing)}. The required sections are "
            f"in templates/{template} and any of them may be one line."
        )


def check_build_logs(report: Report) -> None:
    wanted = required_headings("build-log.md")
    # v0's items and the absorption pass closed before §4 existed and are in the archive.
    logged = _read(ROOT / "plan.md") + _read(ROOT / "archive" / "plan-history.md")
    for path in sorted((ROOT / "build-logs").glob("*.md")):
        stem = path.stem.removesuffix("-build-log")
        if path.name not in logged:
            report.warn(
                f"build-logs/{path.name} is named by neither plan.md §4 nor the archive. A built "
                "item with no Done line is lost."
            )
        if stem in GRANDFATHERED_LOGS:
            continue
        text = _read(path)
        present = [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]
        missing = [h for h in wanted if h not in present]
        if missing:
            report.fail(
                f"build-logs/{path.name} is missing {', '.join(missing)}. The six sections are in "
                "templates/build-log.md and any of them may be one line."
            )
            continue
        tail = text[text.index("## " + wanted[-1]):]
        # Per entry rather than per section. Checking the section passed a `Left open` holding
        # six entries with destinations and a seventh without, which is what the message
        # already promised to catch.
        entries = _bullets(tail)
        if not entries:
            if "nothing" not in tail.lower():
                report.fail(
                    f"build-logs/{path.name}'s '{wanted[-1]}' names no destination. Each entry "
                    "links into plan.md, or the section says `nothing`."
                )
            continue
        for entry in entries:
            # A link, or a destination stated as `nothing`. A bare "nothing" anywhere in the
            # prose is not one: it passed an entry opening "Nothing has met a builder".
            if LINK.search(entry) or NO_DESTINATION.search(entry):
                continue
            opening = " ".join(entry.split())[:60]
            report.fail(
                f"build-logs/{path.name}'s '{wanted[-1]}' entry {opening!r} names no "
                "destination. Each entry links into plan.md, or says `nothing`."
            )


def _bullets(section: str) -> list[str]:
    """Each top-level bullet in a section, with the lines that continue it.

    A `Left open` entry runs over several lines and carries its destination on any of them, so
    an entry is a bullet and everything indented under it rather than one line.
    """
    entries: list[list[str]] = []
    for line in section.splitlines():
        if re.match(r"^\s*[-*]\s+\S", line) and not line.startswith((" ", "\t")):
            entries.append([line])
        elif entries and line.strip():
            entries[-1].append(line)
    return ["\n".join(entry) for entry in entries]


def check_plan(report: Report) -> None:
    text = _read(ROOT / "plan.md")
    # Every id the file mentions, so one spent by a closed item in §4 is not handed out again.
    # §4 lines written before the scheme carry no id, which is why this warns rather than fails.
    spent: set[str] = set()
    done = text[text.index("## 4. Done"):] if "## 4. Done" in text else ""
    # The P3-n scheme replaced queue positions partway through 2026-08-15, so an item that closed
    # on or before that day closed under the old one and never had an id to keep.
    unidentified = [line for line in done.splitlines()
                    if line.startswith("- **") and not QUEUE_ID.search(line)
                    and (m := DATE.search(line)) and "-".join(m.groups()) > "2026-08-15"]
    if unidentified:
        report.warn(
            f"plan.md §4 has {len(unidentified)} closed entries with no P3-n. An id is never "
            "reused, and nothing can hold that for an id the file no longer mentions. Backfill "
            "the ones scheduled under the scheme."
        )
    for entry in _bullets(done):
        seen = len(re.sub(r"\]\([^)]*\)", "]", " ".join(entry.split())))
        if seen > DONE_ENTRY_CEILING:
            head = re.sub(r"\*\*", "", entry.splitlines()[0])[2:60]
            report.fail(
                f"plan.md §4 entry {head!r} is {seen} characters against a ceiling of "
                f"{DONE_ENTRY_CEILING}. A Done entry is one line: what shipped, what it cost, and "
                "a link to the build log. What the item found is the build log's job, and a "
                "finding only stated here is lost to the record. Do not raise the ceiling."
            )
    # All four, because the message says four and because `check_deferred` indexes on §3's
    # heading and raised a traceback rather than a failure when it was missing.
    for heading in ("## 1. Scheduled", "## 2. Not scheduled", "## 3. Out of scope", "## 4. Done"):
        if heading not in text:
            report.fail(f"plan.md has no '{heading}'. The four sections are fixed.")
            return
    scheduled = text[text.index("## 1. Scheduled") : text.index("## 2. Not scheduled")]
    rows = [
        line for line in scheduled.splitlines()
        if line.startswith("| ") and not line.startswith("| Id") and "---" not in line
    ]
    if not rows:
        report.fail("plan.md §1 has no queue table.")
    for row in rows:
        cell = row.split("|")[1].strip()
        if not QUEUE_ID.match(cell):
            report.fail(
                f"plan.md §1 row {cell!r} has no P3-n id. An id is assigned when an item joins the "
                "table, never changes and is never reused."
            )
        elif cell in spent or QUEUE_ID.findall(done).count(cell) > 0:
            report.fail(
                f"plan.md reuses {cell}. An id is assigned once and never handed out again, "
                "including after the item closes."
            )
        else:
            spent.add(cell)
        if not LINK.search(row):
            report.fail(
                f"plan.md §1 row {cell!r} has no markdown link with a line anchor. A pointer is a "
                "link to a file and a line, not a bare backtick filename."
            )
    # §1 is the header rule and the table, and nothing after it. Four prose blocks had
    # accumulated by 2026-08-18, each restating a record that already said it, which is what the
    # header itself forbids. Prose here reads as queue state and goes stale where the record moves.
    after = scheduled.splitlines()
    last_row = max(
        (i for i, line in enumerate(after) if line.startswith("| ")), default=None
    )
    if last_row is not None:
        trailing = [line for line in after[last_row + 1:] if line.strip()]
        if trailing:
            report.fail(
                f"plan.md §1 has {len(trailing)} line(s) of prose after the table, opening "
                f"{trailing[0][:60]!r}. §1 is the header rule and the table. A row says what an "
                f"item is, its state and its record; why it sits where it does belongs in that "
                f"record, and anything not scheduled belongs in §2.1, §2.2 or §3."
            )

    for number, line in enumerate(text.splitlines(), start=1):
        linked = " ".join(LINK.findall(line))
        for bare in BARE_PATH.findall(line):
            if bare.strip("`") not in linked:
                report.fail(
                    f"plan.md:{number} names {bare} in backticks with no link. Every pointer here "
                    "is a markdown link with a #L anchor, and one link on the line does not cover "
                    "another pointer beside it."
                )


KINDS = {"fix", "change", "add", "absorb", "decide"}
SIZES = {"cheap", "item", "sitting"}
CANDIDATE = re.compile(r"^\| \*\*([A-Z0-9]+-I\d+)\*\* \|")


def check_inventories(report: Report) -> None:
    """A candidate carries all seven fields, and its status names somewhere real.

    Ids are run-prefixed because the categories they replaced collided: dogfood #4's `F-1` and the
    full-test record's `F-01` were different items, both cited.
    """
    plan = _read(ROOT / "plan.md")
    for path in sorted((ROOT / "runs").rglob("inventory.md")):
        if any(part in FROZEN for part in path.parts):
            continue
        rel = path.relative_to(REPO_ROOT)
        findings = path.parent / "findings.md"
        defined = set(re.findall(r"\b[A-Z0-9]+-[A-Z]\d+\b",
                                 _read(findings) if findings.exists() else ""))
        defined |= set(re.findall(r"^\*\*([A-Z0-9]+-N\d+)\.\*\*", _read(path), re.MULTILINE))
        ids: set[str] = set()
        rows: list[tuple[str, list[str]]] = []
        for line in _read(path).splitlines():
            match = CANDIDATE.match(line)
            if not match:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) != 7:
                report.fail(
                    f"{rel}: candidate {match.group(1)} has {len(cells)} fields, not 7. The row is "
                    "id, what, evidence, kind, size, blocked by, status."
                )
                continue
            ids.add(match.group(1))
            rows.append((match.group(1), cells))

        position = {candidate: i for i, (candidate, _) in enumerate(rows)}
        resolved = {
            candidate for candidate, cells in rows
            if cells[6] != "open" and not cells[6].startswith(("accepted ", "deferred "))
        }
        open_rows = [i for i, (candidate, _) in enumerate(rows) if candidate not in resolved]
        if open_rows:
            for candidate, _ in rows:
                if candidate in resolved and position[candidate] < max(open_rows):
                    report.fail(
                        f"{rel}: {candidate} is resolved and sits above open work. Resolved rows go "
                        "below every open one, so the working set is the top of the table."
                    )

        for candidate, cells in rows:
            _, what, evidence, kind, size, blocked, status = cells
            for blocker in re.findall(r"[A-Z0-9]+-I\d+", blocked):
                if blocker in resolved:
                    report.warn(
                        f"{rel}: {candidate} is blocked by {blocker}, which is resolved. Clear it; "
                        "`blocked by` names what blocks the candidate now, not what once did."
                    )
                elif blocker in position and position[blocker] > position[candidate]:
                    report.fail(
                        f"{rel}: {candidate} is blocked by {blocker}, which is below it in the "
                        "table. A live blocker appears above everything it blocks, so a sitting "
                        "reading top-down never hits work it cannot start."
                    )
            if not evidence or evidence == "—":
                report.fail(
                    f"{rel}: {candidate} names no evidence. A candidate with no finding behind it "
                    "is an opinion; cite the finding id."
                )
            for cited in re.findall(r"`([A-Z0-9]+-[A-Z]\d+)`", evidence):
                if cited not in defined:
                    report.fail(
                        f"{rel}: {candidate} cites {cited}, which this run's findings.md and "
                        "inventory do not define. **This catches a typo and not a wrong id**: on "
                        "2026-08-15 a bulk rewrite put eight real-but-wrong finding ids into this "
                        "table and every one of them resolved. Only reading the finding catches "
                        "that."
                    )
            if kind not in KINDS:
                report.fail(f"{rel}: {candidate} has kind {kind!r}, not one of {sorted(KINDS)}.")
            if size not in SIZES:
                report.fail(f"{rel}: {candidate} has size {size!r}, not one of {sorted(SIZES)}.")
            for blocker in re.findall(r"[A-Z0-9]+-I\d+", blocked):
                if blocker not in ids:
                    report.fail(
                        f"{rel}: {candidate} is blocked by {blocker}, which is not a candidate in "
                        "this table."
                    )
            if status.startswith("scheduled "):
                queue_id = status.removeprefix("scheduled ").strip()
                if queue_id not in plan:
                    report.fail(
                        f"{rel}: {candidate} says scheduled {queue_id}, and plan.md §1 has no such "
                        "id. Add the row, or correct the status."
                    )
            elif status.startswith("built "):
                log = status.removeprefix("built ").strip().strip("`")
                if not (ROOT / log).exists():
                    report.fail(f"{rel}: {candidate} says built {log}, which does not exist.")
            elif status.startswith("declined"):
                if ":" not in status:
                    report.fail(
                        f"{rel}: {candidate} is declined with no reason. A decision against is "
                        "recorded so it is not rediscovered."
                    )
            elif status not in {"open"} and not status.startswith(("accepted ", "deferred ")):
                report.fail(
                    f"{rel}: {candidate} has status {status!r}. It is open, accepted §2.1, "
                    "deferred §2.2, scheduled P3-n, built <log>, or declined: <reason>."
                )


def _unquoted(text: str) -> str:
    """The text with quoted spans removed, so a quotation is not read as a claim."""
    return re.sub(r'"[^"\n]*"', '""', text)


COUNTED = re.compile(r"(\d+) candidates,\s+(\d+) (?:still `open`|open)")


def check_counts(report: Report) -> None:
    """A stated count of candidates matches the rows counted.

    The number is written in three files and maintained by hand in all of them. On 2026-08-27
    the inventory said 14 open, `plan.md` said 24 of 37, and the table held 18 of 40: the header
    had been decremented once per item built while the rows it counted were already `built`.
    Nothing recomputed it, so each build made the number worse.

    An inventory's own count is checked against its own rows. A count in `plan.md` or
    `handoff.md` has to match some live inventory, since both cite one rather than owning it.

    A count inside double quotes is a quotation and is skipped, because §2 of an inventory
    records the false statement verbatim beside its correction.
    """
    counts: dict[str, tuple[int, int]] = {}
    for path in sorted((ROOT / "runs").rglob("inventory.md")):
        if any(part in FROZEN for part in path.parts):
            continue
        rows = [line for line in _read(path).splitlines() if CANDIDATE.match(line)]
        total = len(rows)
        still_open = sum(
            1 for line in rows if [c.strip() for c in line.strip().strip("|").split("|")][-1] == "open"
        )
        counts[str(path.relative_to(REPO_ROOT))] = (total, still_open)
        for stated_total, stated_open in COUNTED.findall(_unquoted(_read(path))):
            if (int(stated_total), int(stated_open)) != (total, still_open):
                report.fail(
                    f"{path.relative_to(REPO_ROOT)}: says {stated_total} candidates, "
                    f"{stated_open} open. The table holds {total} rows, {still_open} of them "
                    "`open`. The count is what tells a session how much of the item is left."
                )

    for name in ("plan.md", "handoff.md"):
        for stated_total, stated_open in COUNTED.findall(_unquoted(_read(ROOT / name))):
            pair = (int(stated_total), int(stated_open))
            if pair not in counts.values():
                report.fail(
                    f"{name}: says {stated_total} candidates, {stated_open} open, and no "
                    f"inventory holds that. Counted: "
                    + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in sorted(counts.items()))
                    + ". This file cites an inventory rather than owning its numbers."
                )


ACTED = re.compile(r"^\*\*Acted on:\*\* (.+)$", re.MULTILINE)
# A disposition, not a sentence. The line opens `**Closed` and names something that resolves:
# a commit, a build log, or a candidate id. `^\*\*Closed\b` alone matched prose, and dogfood #4's
# `DF4-D1` opens "Closed inside the run, and the finding stands anyway." — a sentence about the
# store that would have cleared the warning for a finding that is still open.
CLOSED = re.compile(
    r"^\*\*Closed\b[^\n]*?(?:`[0-9a-f]{7,40}`|build-logs/[a-z0-9-]+\.md|`[A-Z0-9]+-I\d+`)"
)


def check_symmetry(report: Report, fix: bool) -> None:
    """A citation between two records of one run resolves in both directions.

    The inventory is the source of truth and `--fix` writes the other side, because a rule needing
    two hand edits per link gets half-done. A finding with no candidate is reported rather than
    stamped `nothing`: two of dogfood #4's were already fixed elsewhere before the inventory
    existed, and writing `nothing` into the record would have been false.

    **A finding may say where it closed instead**, in a body line opening `**Closed` and naming a
    commit, a build log or a candidate id. That is the second branch this check's own message has
    always named and could not observe, so `DF4-D13` and `DF4-D14` warned on every run from the day
    the rule shipped. A warning that cannot be cleared is one a reader learns to skip, which is
    FT-18's argument made against our own tooling. Nothing false is written to satisfy it: the
    finding states where it closed in a form that resolves, or the warning stands.

    What this catches that resolving an id cannot: a candidate citing a real but wrong finding.
    The wrong finding does not name it back.
    """
    for run in sorted((ROOT / "runs").iterdir()):
        findings, inventory = run / "findings.md", run / "inventory.md"
        if not (run.is_dir() and findings.exists() and inventory.exists()):
            continue
        if any(part in FROZEN for part in run.parts):
            continue

        produced: dict[str, list[str]] = {}
        for line in _read(inventory).splitlines():
            match = re.match(r"^\| \*\*([A-Z0-9]+-I\d+)\*\* \|", line)
            if not match:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            for cited in re.findall(r"`([A-Z0-9]+-[DPN]\d+)`", cells[2]):
                produced.setdefault(cited, []).append(match.group(1))

        lines, out, stale = _read(findings).splitlines(), [], []
        # Strip what was generated last time, then insert from scratch, so running twice is a
        # no-op. Rebuilding in place is what makes the generated side safe to regenerate.
        stripped: list[str] = []
        for line in lines:
            if ACTED.match(line):
                if stripped and not stripped[-1].strip():
                    stripped.pop()
                continue
            stripped.append(line)

        # Which findings state their own closure, read before the rebuild so a section's body is
        # in hand when its heading comes round again.
        closed: set[str] = set()
        current: str | None = None
        for line in stripped:
            heading = re.match(r"^### ([A-Z0-9]+-[DP]\d+) — ", line)
            if heading:
                current = heading.group(1)
            elif current and CLOSED.match(line):
                closed.add(current)

        for line in stripped:
            out.append(line)
            heading = re.match(r"^### ([A-Z0-9]+-[DP]\d+) — ", line)
            if not heading:
                continue
            cites = produced.get(heading.group(1), [])
            if cites:
                out.extend(["", "**Acted on:** " + ", ".join(f"`{c}`" for c in cites) + "."])
            elif heading.group(1) not in closed:
                report.warn(
                    f"runs/{run.name}/findings.md: {heading.group(1)} produced no candidate and "
                    "does not say where it closed. File a candidate, or open a line of the "
                    "finding `**Closed ...` naming what closed it: a commit in backticks, a "
                    "build-logs/ path, or a candidate id. A sentence beginning `Closed` that "
                    "names none of those is prose, and this does not read it as a disposition."
                )
        rebuilt = "\n".join(out) + "\n"
        if rebuilt != _read(findings):
            if fix:
                findings.write_text(rebuilt, encoding="utf-8")
            else:
                report.fail(
                    f"runs/{run.name}/findings.md's back-references do not match the inventory. "
                    "Run `uv run python dev-docs/check_docs.py --fix`; the inventory is the "
                    "source of truth and this side is generated."
                )


def _moved_to(name: str) -> Path | None:
    """Where a record that is no longer at ``name`` went, or ``None`` where nothing matches.

    Two moves are followed. A record that kept its name, found anywhere under the tree; and an
    `items/` record that became a build log, which `CLAUDE.md` requires be renamed with a
    `-build-log` suffix.

    The second is the move the conventions mandate on every built item, and matching on the
    basename alone cannot follow it. Without it the most common restructuring in the tree reads
    as a deletion, and a deletion skips the size comparison, so an item whose text was lost on
    the way into its build log looked the same as one that moved intact.
    """
    if name.startswith(f"{ROOT.name}/items/"):
        built = ROOT / "build-logs" / f"{Path(name).stem}-build-log.md"
        if built.is_file():
            return built
    same = [q for q in ROOT.rglob(Path(name).name) if q.is_file()]
    return same[0] if len(same) == 1 else None


def check_shrinkage(report: Report, since: str) -> None:
    """Every record that lost material text against a git ref, and by how much.

    Structural checks pass over a lossy rewrite: the 2026-08-15 reorganisation cut seventeen rows
    of dogfood #4's inventory by half or more, including a recorded decision, and the file was the
    same size afterwards because other text replaced it. Nothing compares a document against what
    it said yesterday, and no check can judge whether a sentence was worth keeping. This reports
    the shrinkage and a human decides.

    Run it after any restructuring: `check_docs.py --since <ref>`.
    """
    try:
        names = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-tree", "-r", "--name-only", since, "dev-docs/"],
            capture_output=True, text=True, check=True).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        report.fail(f"--since {since}: no such git ref, or git is unavailable.")
        return

    for name in names:
        if not name.endswith(".md"):
            continue
        was = subprocess.run(["git", "-C", str(REPO_ROOT), "show", f"{since}:{name}"],
                             capture_output=True, text=True)
        if was.returncode:
            continue
        path = REPO_ROOT / name
        before = len(was.stdout)
        if not path.exists():
            moved = _moved_to(name)
            if moved is not None:
                path = moved
                name = f"{name} -> {path.relative_to(REPO_ROOT)}"
        now = len(_read(path)) if path.exists() else 0
        if now == 0:
            report.warn(
                f"{name} existed at {since} and does not now, under that name or any other. "
                "Confirm its text has a home; a merge is fine, silent deletion is not."
            )
        elif now < before * 0.75:
            report.warn(
                f"{name} is {round(100 - now / before * 100)}% shorter than at {since} "
                f"({before} to {now} chars). Confirm every removed passage landed somewhere, "
                "then say so in the file."
            )


def check_nested_links(report: Report) -> None:
    """A link wrapped around a link. Both halves resolve, so check_citations stays silent.

    Introduced by a bulk pass that linkified backticked paths over text that already had links
    written by hand. It renders as a broken link, and nothing else catches it.
    """
    nested = re.compile(r"\[\[[^\]]*\]\(")
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in FROZEN for part in path.parts):
            continue
        for number, line in enumerate(_read(path).splitlines(), start=1):
            if nested.search(line):
                report.fail(
                    f"{path.relative_to(REPO_ROOT)}:{number} has a link nested inside a link. Both "
                    "halves resolve so check_citations passes it, and it renders broken. Unwrap "
                    "it to one [label](target#Lnn)."
                )


def check_deferred(report: Report, today: date) -> None:
    text = _read(ROOT / "plan.md")
    opens, closes = "### 2.2 Deferred", "## 3. Out of scope"
    if opens not in text or closes not in text:
        # `check_plan` reports the missing heading. Indexing on it here raised a traceback
        # instead, which ends the run and hides every rule after this one.
        return
    section = text[text.index(opens) : text.index(closes)]
    for entry in re.findall(r"^- \*\*(.+?)\*\*(.*)$", section, re.MULTILINE):
        title, rest = entry
        if "*Deferred " not in rest or ".*" not in rest:
            report.fail(
                f"plan.md §2.2 entry {title!r} carries no '*Deferred YYYY-MM-DD.*' on its "
                "first line. Without a date nothing can tell how long it has sat there, and the "
                "marker is read off that line alone."
            )
            continue
        age = _age(rest[: rest.index(".*") + 2], today)
        if age is not None and age > DEFERRED_REPORT_DAYS:
            report.warn(
                f"plan.md §2.2 {title!r} was deferred {age} days ago. Re-decide it: schedule it, "
                "move it to §3, or restate what would still settle it."
            )


def check_inbox(report: Report, today: date) -> None:
    path = ROOT / "random-thoughts-questions.md"
    text = _read(path)

    # Thilina's own sections are his to resolve. Everything outside them is the inbox proper,
    # wherever it sits: an entry appended below his sections is still an inbox entry.
    body_lines: list[str] = []
    corner_lines: list[str] = []
    his = False
    for line in text.splitlines():
        if line.startswith("## "):
            his = "Thilina's Corner" in line or "To-do's for Thilina" in line
        (corner_lines if his else body_lines).append(line)
    body, corner_text = "\n".join(body_lines), "\n".join(corner_lines)

    if "## Unscoped" not in text:
        report.fail(
            "random-thoughts-questions.md has no `## Unscoped` section. That is where a new entry "
            "goes, and without it every inbox rule passes by having nothing to read."
        )

    for number, line in enumerate(body.splitlines(), start=1):
        if re.match(r"^\d+\.\s", line):
            report.fail(
                f"random-thoughts-questions.md:{number} is a numbered entry. Entries are not "
                "numbered: a number is an identity, an identity gets cited, and a citation is what "
                "creates the pressure to leave a husk behind when the entry moves."
            )

    for entry in re.findall(r"^- (.+)$", body, re.MULTILINE):
        age = _age(entry, today)
        if age is None:
            report.fail(
                f"random-thoughts-questions.md entry {entry[:50]!r} carries no date. An entry is "
                "temporary and its age is what says when it must move."
            )
        elif age > INBOX_FAIL_DAYS:
            report.fail(
                f"random-thoughts-questions.md entry {entry[:50]!r} is {age} days old. Give it a "
                "destination: plan.md §1, §2.1, §2.2, the document that owns the subject, or "
                "dropped with the reason recorded."
            )
        elif age > INBOX_REPORT_DAYS:
            report.warn(
                f"random-thoughts-questions.md entry {entry[:50]!r} is {age} days old and needs a "
                "destination."
            )

    age = _age(corner_text, today)
    if age is not None and age > INBOX_REPORT_DAYS:
        report.warn(
            f"Thilina's Corner has an item {age} days old. Propose a destination and ask him; "
            "never move one without permission."
        )

    for path_ in sorted(ROOT.rglob("*.md")):
        if any(part in FROZEN for part in path_.parts) or path_.name == path.name:
            continue
        for number, line in enumerate(_read(path_).splitlines(), start=1):
            if re.search(r"random-thoughts-questions\.md.{0,4}(#|item )\d", line):
                report.fail(
                    f"{path_.relative_to(REPO_ROOT)}:{number} cites a numbered entry in the inbox. "
                    "Nothing cites into it. Point at wherever the entry went instead."
                )


def check_handoff(report: Report) -> None:
    text = _read(ROOT / "handoff.md")
    lines = text.splitlines()
    if len(lines) > HANDOFF_CEILING:
        report.fail(
            f"handoff.md is {len(lines)} lines against a ceiling of {HANDOFF_CEILING}. It is a "
            "pointer, not a summary: move the new text to the file that owns the subject and cite "
            "it from here. Do not raise the ceiling."
        )
    if "pointer, not a summary" not in text:
        report.fail(
            "handoff.md must open by saying it is a pointer rather than a summary. That sentence "
            "is what a session reads before adding a section to it."
        )


def check_retired_sections(report: Report) -> None:
    """No citation to a plan.md section number the 2026-08-15 reorganisation retired."""
    retired = re.compile(r"`plan\.md`\s*§ ?(1\.\d|2(?!\.[12])|3\.\d|4\.\d|5|6|7)\b")
    for path in sorted(ROOT.rglob("*.md")):
        if any(part in FROZEN for part in path.parts):
            continue
        for number, line in enumerate(_read(path).splitlines(), start=1):
            if retired.search(line):
                report.fail(
                    f"{path.relative_to(REPO_ROOT)}:{number} cites a retired plan.md section. "
                    "archive/plan-history.md maps every old number to where it went; point there."
                )



# --------------------------------------------------------------------------------------------
# The fixture suite. One deliberate defect per rule, and the message it must produce.
#
# `CLAUDE.md` requires the library's own tests to use handcrafted fixtures, because machinery can
# only be verified against data whose correct answer is already known. This file is machinery and
# had none: every rule here was written against the one instance that prompted it, and four of
# them turned out to cover the instance rather than the rule. Adding a rule means adding a row.


def _sub(name: str, old: str, new: str):
    def mutate(root: Path) -> None:
        path = root / name
        text = path.read_text(encoding="utf-8")
        assert old in text, f"fixture text not found in {name}"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return mutate


def _sub_re(name: str, pattern: str, new: str, *, count: int = 1):
    """A substitution whose anchor is a shape rather than a quotation.

    A fixture quoting live text rots the day that text is edited, and a `P3-n` id or an
    `items/` filename is retired by every item that ships. Matching the shape keeps the
    fixture pointed at whatever is there now.
    """
    def mutate(root: Path) -> None:
        path = root / name
        text = path.read_text(encoding="utf-8")
        assert re.search(pattern, text, re.M), (
            f"fixture pattern {pattern!r} matches nothing in {name}"
        )
        path.write_text(re.sub(pattern, new, text, count=count, flags=re.M), encoding="utf-8")
    return mutate


def _a_queue_row_with_no_link(name: str = "plan.md"):
    """Strip every markdown link from one queue row.

    The defect the rule detects is a row carrying no pointer at all, so removing one link
    from a row that has several injects nothing. This fixture went silent on 2026-08-27 when
    `P3-38`'s row gained a second link and the one the fixture removed stopped being the only
    one. Anchor on the row, not on a link inside it.
    """
    def mutate(root: Path) -> None:
        path = root / name
        text = path.read_text(encoding="utf-8")
        rows = [line for line in text.splitlines() if re.match(r"^\| P3-\d+ \|", line)]
        linked = [line for line in rows if re.search(r"\[[^\]]+\]\([^)]+\)", line)]
        assert linked, f"{name} needs a queue row carrying a link for this fixture"
        row = linked[0]
        path.write_text(
            text.replace(row, re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", row), 1),
            encoding="utf-8",
        )
    return mutate


def _reuse_an_id(name: str = "plan.md"):
    """Give the second queue row the first one's id."""
    def mutate(root: Path) -> None:
        path = root / name
        text = path.read_text(encoding="utf-8")
        ids = re.findall(r"^\| (P3-\d+) \|", text, flags=re.M)
        assert len(ids) >= 2, f"{name} needs two queue rows for this fixture"
        path.write_text(
            text.replace(f"| {ids[1]} |", f"| {ids[0]} |", 1), encoding="utf-8"
        )
    return mutate


def _an_item_record(root: Path) -> str:
    """The name of some `items/` record, for a fixture that needs one to exist."""
    found = sorted(p.name for p in (root / "items").glob("*.md"))
    assert found, "no items/ record for this fixture to use"
    return found[0]


def _write(name: str, text: str):
    def mutate(root: Path) -> None:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return mutate


def _write_run(directory: str, findings: str):
    def mutate(root: Path) -> None:
        (root / directory).mkdir(parents=True, exist_ok=True)
        (root / directory / "findings.md").write_text(findings, encoding="utf-8")
        (root / directory / "inventory.md").write_text(
            "# Dogfood #5 — inventory\n\n## 1. What we learned\n\nx.\n\n"
            "## 2. What was corrected\n\nx.\n\n## 3. Candidates\n\nx.\n\n"
            "## 4. What the next run must measure\n\nx.\n", encoding="utf-8")
        (root / directory / "setup.md").write_text(
            "# Dogfood #5 — setup\n\n## 1. What is installed\n\nx.\n\n## 2. The task\n\nx.\n\n"
            "## 3. The prompt\n\nx.\n\n## 4. What this run is testing\n\nx.\n", encoding="utf-8")
    return mutate


def _move_an_item(to: str | None, text: str):
    """Move whichever `items/` record is there, so no fixture names one that can retire.

    ``to`` of ``None`` derives the destination from the record's own name, which is the move a
    built item really makes. A name that does not correspond is the other case: a record that
    left with nothing carrying its name.
    """
    def mutate(root: Path) -> None:
        record = _an_item_record(root)
        destination = to or f"build-logs/{record[:-3]}-build-log.md"
        _move(f"items/{record}", destination, text)(root)
    return mutate


def _move(name: str, to: str, text: str):
    """Move a record and leave `text` at the destination, which is how a lossy move looks."""
    def mutate(root: Path) -> None:
        (root / name).unlink()
        (root / to).parent.mkdir(parents=True, exist_ok=True)
        (root / to).write_text(text, encoding="utf-8")
    return mutate


def _commit(repo: Path) -> None:
    """Make the copy a git repository with one commit, so `--since HEAD` has a ref to read."""
    for command in (
        ["init", "-q"],
        ["-c", "user.email=x@y", "-c", "user.name=x", "add", "-A"],
        ["-c", "user.email=x@y", "-c", "user.name=x", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(["git", "-C", str(repo), *command], check=True, capture_output=True)


def _drop_section(name: str, heading: str, until: str):
    def mutate(root: Path) -> None:
        path = root / name
        text = path.read_text(encoding="utf-8")
        path.write_text(text[: text.index(heading)] + text[text.index(until):], encoding="utf-8")
    return mutate


# Each row is the defect's name, what introduces it, and the text the report must carry. A row
# ending in "git" has the copy committed before it is mutated, which is what lets a rule that
# compares against a ref be exercised at all.
SELF_TESTS: list[tuple] = [
    ("a loose file at the root", _write("stray.md", "# stray\n"), "loose at the dev-docs root"),
    ("an unknown directory", _write("scratch/x.md", "# x\n"), "not one of the six directories"),
    ("an uppercase filename", _write("items/Loud.md", "# loud\n"), "not lowercase-hyphenated"),
    ("a stray file in a run", _write("runs/dogfood-4/notes.md", "# n\n"),
     "A run directory holds"),
    ("an items record missing a section",
     _write("items/probe.md", "# probe\n\n## Where it came from\n\nx.\n"),
     "is missing What the problem is"),
    ("an items record nothing links to",
     _write("items/probe.md", "# probe\n\n## Where it came from\n\nx.\n\n## What the problem is"
            "\n\nx.\n\n## What has to be decided\n\nx.\n\n## What it waits on\n\nx.\n"),
     "is not linked from plan.md"),
    ("a queue row with no id", _sub_re("plan.md", r"^\| P3-\d+ \|", "| |"),
     "has no P3-n id"),
    ("an id used twice", _reuse_an_id(), "reuses P3-"),
    ("a queue row with no link", _a_queue_row_with_no_link(), "has no markdown link"),
    ("a Left open entry with no destination beside entries that have one",
     _sub("build-logs/answer-key-build-log.md", "## 6. Left open\n",
          "## 6. Left open\n\n- Something unresolved, with no destination at all.\n"),
     "names no destination"),
    ("plan.md missing a section other than the first two",
     _sub("plan.md", "## 3. Out of scope", "## 3x. Out of scope"),
     "The four sections are fixed"),
    ("a bare pointer outside a bullet",
     _sub_re("plan.md", r"^\| (P3-\d+) \| \*\*[^|]+\*\*",
             r"| \1 | **The review**, after `build-logs/memory-build-log.md`"),
     "in backticks with no link"),
    ("a link nested in a link",
     _sub_re("plan.md", r"(\[`items/[a-z0-9-]+\.md`\]\(items/[a-z0-9-]+\.md#L\d+\))",
             r"[\1](items/nested.md#L1)"),
     "link nested inside a link"),
    ("an inventory candidate with an unknown kind",
     _sub_re("runs/dogfood-4/inventory.md",
             r"^(\| \*\*DF4-I\d+\*\* \|(?:[^|]*\|){2})[^|]+(\|)", r"\1 ponder \2"),
     "not one of"),
    ("an inventory candidate blocked by nothing real",
     _sub_re("runs/dogfood-4/inventory.md",
             r"^(\| \*\*DF4-I\d+\*\* \|(?:[^|]*\|){4})[^|]+(\|)", r"\1 DF4-I99 \2"),
     "not a candidate in"),
    ("prose after the plan.md §1 table",
     _sub_re("plan.md", r"(\n## 2\. Not scheduled)",
             "\n**P3-9 slid again**, because the thing above it grew.\n\\1"),
     "prose after the table"),
    ("a candidate scheduled against an id plan.md lacks",
     _sub_re("runs/dogfood-4/inventory.md",
             r"^(\| \*\*DF4-I\d+\*\* \|(?:[^|]*\|){5})[^|]+\|$", r"\1 scheduled P3-99 |"),
     "plan.md §1 has no such id"),
    ("a candidate citing evidence that does not resolve",
     _sub("runs/dogfood-4/inventory.md", "| `DF4-D1` | decide", "| `DF4-D99` | decide"),
     "which this run's findings.md and"),
    ("a back-reference that disagrees with the inventory",
     _sub("runs/dogfood-4/findings.md", "**Acted on:**", "**Acted on:** `DF4-I99`. Was:"),
     "back-references do not match"),
    ("a Done entry over its ceiling",
     _sub_re("plan.md", r"^(- \*\*[^\n]*\(P3-\d+\)[^\n]*)$", r"\1 " + "found more. " * 40),
     "A Done entry is one line"),
    ("handoff over its ceiling", _sub("handoff.md", "# Handoff", "# Handoff\n" + "x\n" * 130),
     "against a ceiling of"),
    ("handoff without its contract",
     _sub("handoff.md", "pointer, not a summary", "a summary"), "must open by saying it is a"),
    ("a numbered inbox entry",
     _sub("random-thoughts-questions.md", "## Unscoped", "## Unscoped\n\n1. a numbered thought"),
     "is a numbered entry"),
    ("an undated inbox entry",
     _sub("random-thoughts-questions.md", "## Unscoped", "## Unscoped\n\n- a thought"),
     "carries no date"),
    ("the inbox with nowhere to put an entry",
     _drop_section("random-thoughts-questions.md", "## Unscoped", "## Thilina's Corner"),
     "has no `## Unscoped` section"),
    ("a citation into a numbered inbox entry",
     _sub("plan.md", "## 3. Out of scope",
          "See `random-thoughts-questions.md` item 2.\n\n## 3. Out of scope"),
     "cites a numbered entry in the inbox"),
    # The orphan rule only runs where both records exist, so the fixture supplies both.
    ("a finding that closed nowhere and produced no candidate",
     _write_run("runs/dogfood-5",
            "# Dogfood #5 — findings\n\n## 1. Method, and what did not survive verification\n\nx.\n\n"
            "## 2. What the run met\n\nx.\n\n## 3. Findings\n\n### DF5-D1 — a finding\n\nx.\n\n"
            "## 4. What is open\n\nx.\n"),
     "does not say where it closed"),
    # The second limb of the same rule: a disposition has to name something that resolves. This
    # fixture is the sentence `DF4-D1` really opens with, which cleared the warning before the
    # marker required a commit, a build log or a candidate id.
    ("a closure marker that names nothing resolvable",
     _write_run("runs/dogfood-6",
            "# Dogfood #6 — findings\n\n## 1. Method, and what did not survive verification\n\nx.\n\n"
            "## 2. What the run met\n\nx.\n\n## 3. Findings\n\n### DF6-D1 — a finding\n\n"
            "**Closed inside the run, and the finding stands anyway.** x.\n\n"
            "## 4. What is open\n\nx.\n"),
     "does not say where it closed"),
    ("a stated candidate count that does not match the rows",
     _sub_re("runs/dogfood-5/inventory.md", r"\d+ candidates, \d+ open",
             "99 candidates, 98 open"),
     "The count is what tells a session"),
    ("handoff citing a count no inventory holds",
     _sub_re("handoff.md", r"\d+ candidates,\s+\d+ open", "99 candidates, 98 open"),
     "and no inventory holds that"),
    ("a citation to a retired section",
     _sub("plan.md", "## 3. Out of scope", "See `plan.md` §3.2.1.\n\n## 3. Out of scope"),
     "cites a retired plan.md section"),
    # The last two need a git ref to compare against, so the harness commits the copy first.
    ("an item moved into its build log, having lost most of its text",
     _move_an_item(None, "# gone\n\nx.\n"),
     "shorter than at HEAD", "git"),
    ("a record deleted with nothing carrying its name",
     _move_an_item("build-logs/unrelated-build-log.md", "# gone\n\nx.\n"),
     "does not now, under that name or any other", "git"),
]


def self_test() -> int:
    """Run every fixture against a copy of the tree and report any rule that stayed silent."""
    global ROOT, REPO_ROOT
    import shutil, tempfile

    real_root, real_repo = ROOT, REPO_ROOT
    missed: list[str] = []
    for name, mutate, expected, *rest in SELF_TESTS:
        versioned = "git" in rest
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "dev-docs"
            shutil.copytree(real_root, copy, ignore=shutil.ignore_patterns("__pycache__"))
            if versioned:
                _commit(Path(tmp))
            try:
                mutate(copy)
            except AssertionError as exc:
                ROOT, REPO_ROOT = real_root, real_repo
                missed.append(
                    f"{name}: the fixture no longer applies ({exc}). It anchors on text this "
                    f"tree has changed. Re-anchor it on the shape rather than the wording, "
                    f"the way _sub_re and _move_an_item do."
                )
                continue
            ROOT, REPO_ROOT = copy, Path(tmp)
            report = Report()
            for check in (check_placement, check_runs, check_items, check_build_logs,
                          check_plan, check_inventories, check_counts, check_nested_links,
                          check_handoff,
                          check_retired_sections):
                try:
                    check(report)
                except Exception as exc:  # a rule that crashes is a rule that does not hold
                    report.fail(f"{check.__name__} raised {exc!r}")
            check_symmetry(report, False)
            check_deferred(report, date(2026, 8, 16))
            check_inbox(report, date(2026, 8, 16))
            if versioned:
                check_shrinkage(report, "HEAD")
            said = " ".join(report.failures + report.warnings)
            if expected not in said:
                missed.append(f"{name}: nothing said {expected!r}")
    ROOT, REPO_ROOT = real_root, real_repo

    for miss in missed:
        print(f"  SILENT: {miss}")
    print(f"self-test: {len(SELF_TESTS) - len(missed)}/{len(SELF_TESTS)} rules fire")
    return 1 if missed else 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    fix = "--fix" in argv
    # The fixture suite runs here too, at about 1.7s against 0.1s for the rules alone. It is
    # the coverage map, and a map that only rots when somebody thinks to run it is weaker than
    # it reads: a fixture anchored on a retired `P3-n` row sat broken through a green 2403-test
    # suite. `--self-test` still runs it alone, for working on a rule.
    if self_test() != 0:
        print("\ncheck_docs: the fixture suite above is what proves each rule fires.")
        return 1
    today = date.today()
    if "--today" in argv:
        today = date.fromisoformat(argv[argv.index("--today") + 1])

    report = Report()
    check_placement(report)
    check_runs(report)
    check_items(report)
    check_build_logs(report)
    check_plan(report)
    check_inventories(report)
    check_counts(report)
    check_symmetry(report, "--fix" in argv)
    if "--since" in argv:
        check_shrinkage(report, argv[argv.index("--since") + 1])
    check_nested_links(report)
    check_deferred(report, today)
    check_inbox(report, today)
    check_handoff(report)
    check_retired_sections(report)

    for warning in report.warnings:
        print(f"  warn: {warning}")
    for failure in report.failures:
        print(f"  FAIL: {failure}")
    if report.failures:
        print(f"\ncheck_docs: {len(report.failures)} problem(s), {len(report.warnings)} warning(s)")
        return 1
    print(f"check_docs: clean, {len(report.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
