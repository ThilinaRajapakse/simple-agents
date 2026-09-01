"""What a check produced, and how a run of the suite reads on a terminal and as JSON.

A check has four outcomes, printed as ``pass``, ``FAIL``, ``blocked`` and ``n/a``. It passed,
it failed and carries the taxonomy's message, it was blocked because the artifact it reads is
missing and another check already reports why, or it does not apply, which is a project
claiming a lower tier than the entry's or standing at a stage before the one the entry names.
The last two are printed rather than hidden: a project should see what it is not being held to.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["Finding", "Outcome", "CheckResult", "Report"]

_WIDTH = 92
_INDENT = " " * 8


class Outcome(str, Enum):
    """What became of one check."""

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class Finding:
    """One failure, carrying the taxonomy's own message for the entry that found it."""

    entry_id: str
    message: str

    def to_record(self) -> dict[str, Any]:
        return {"entry": self.entry_id, "message": self.message}


@dataclass(frozen=True, slots=True)
class CheckResult:
    """What one check did, what it read, and what it found.

    ``read`` names the artifacts the check opened, so a report says which run and which
    results file the numbers came from. ``detail`` says why on a blocked or inapplicable
    check, and on a passed one carries what the check found worth saying anyway, such as a
    trajectory whose payloads were dropped by sampling. It is empty on a failed check, whose
    findings carry the message.
    """

    entry_id: str
    name: str
    tier: str
    outcome: Outcome
    findings: tuple[Finding, ...] = ()
    read: tuple[str, ...] = ()
    detail: str | None = None

    @property
    def failed(self) -> bool:
        return self.outcome is Outcome.FAILED

    def to_record(self) -> dict[str, Any]:
        return {
            "entry": self.entry_id,
            "name": self.name,
            "tier": self.tier,
            "outcome": self.outcome.value,
            "findings": [f.to_record() for f in self.findings],
            "read": list(self.read),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class Report:
    """Every check that ran, over one project.

    ::

        report = run_checks(Path("."))
        report.failed            # the checks that failed
        print(report.text())
        json.dumps(report.to_record())

    ``ok`` is true when nothing failed, and is what the command's exit status follows.

    ``reading`` is the run the checks that read one read, named by its nodes rather than by its
    path alone. It sits in the header because it says what the report is about; a check that
    certified a batch pass rather than the agent reads as a clean report otherwise.
    """

    root: str
    tier: str
    brief: str | None
    checks: tuple[CheckResult, ...] = field(default=())
    notes: tuple[str, ...] = field(default=())
    reading: str | None = None

    @property
    def failed(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if check.failed)

    @property
    def ok(self) -> bool:
        return not self.failed

    def to_record(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "tier": self.tier,
            "brief": self.brief,
            "reading": self.reading,
            "checks": [check.to_record() for check in self.checks],
            "notes": list(self.notes),
            "counts": self.counts(),
            "ok": self.ok,
        }

    def counts(self) -> dict[str, int]:
        """How many checks fell into each outcome."""
        counts = {outcome.value: 0 for outcome in Outcome}
        for check in self.checks:
            counts[check.outcome.value] += 1
        return counts

    def text(self) -> str:
        """The report as it reads on a terminal."""
        lines = [f"simple-agents check: {self.root}"]
        lines.append(f"tier {self.tier}, declared in {self.brief or 'no brief'}")
        if self.reading:
            lines.extend(textwrap.wrap(self.reading, _WIDTH, break_on_hyphens=False))
        lines.append("")
        # One column width for the whole report, so the paths line up whatever names ran.
        width = max((len(check.name) for check in self.checks), default=0)
        for check in self.checks:
            lines.extend(_check_lines(check, width))
        for note in self.notes:
            lines.append("")
            lines.extend(_wrapped(note))
        lines.append("")
        lines.append(_summary(self.counts()))
        return "\n".join(lines)


# Right-aligned in the width of the longest, so the entry ids line up. Each says what it means
# on the line itself, and the last line of the report counts them in the same words.
LABELS = {
    Outcome.PASSED: "pass",
    Outcome.FAILED: "FAIL",
    Outcome.BLOCKED: "blocked",
    Outcome.NOT_APPLICABLE: "n/a",
}
_LABEL_WIDTH = max(len(label) for label in LABELS.values())


def _check_lines(check: CheckResult, width: int = 32) -> list[str]:
    label = LABELS[check.outcome]
    lines = [
        f"  {label:>{_LABEL_WIDTH}}  {check.entry_id}  "
        f"{check.name:<{width}}  {_read(check.read)}".rstrip()
    ]
    for finding in check.findings:
        lines.append("")
        lines.extend(_wrapped(finding.message))
        lines.append("")
    if check.detail:
        lines.extend(_wrapped(check.detail))
    return lines


def _read(paths: tuple[str, ...]) -> str:
    """What the check opened. A rollout has one trajectory each, so a list of them is folded."""
    if not paths:
        return ""
    if len(paths) <= 2:
        return ", ".join(paths)
    return f"{paths[0]} and {len(paths) - 1} more"


def _wrapped(text: str) -> list[str]:
    # `break_on_hyphens=False`, so a path or a document name stays one token: `docs/run-` at the
    # end of a line and `envelope.md` at the start of the next is not a name a reader can copy.
    return textwrap.wrap(
        text, _WIDTH, initial_indent=_INDENT, subsequent_indent=_INDENT, break_on_hyphens=False
    )


def _summary(counts: dict[str, int]) -> str:
    """The last line.

    `not applicable` covers three reasons: a tier below the entry's, a stage the project has
    not reached, and a check that does not apply to what the project declared. Each check's own
    line names which. The tier is on the report's second line, so it is not repeated here.
    """
    parts = [
        f"{counts['failed']} failed",
        f"{counts['passed']} passed",
    ]
    if counts["blocked"]:
        parts.append(f"{counts['blocked']} blocked")
    if counts["not_applicable"]:
        parts.append(f"{counts['not_applicable']} not applicable")
    return ", ".join(parts)
