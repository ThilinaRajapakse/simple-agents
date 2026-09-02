"""The conformance suite: what `docs/failure-taxonomy.md` specifies, run against a project.

The checks read the files a project produced and execute nothing. Eleven ship::

    from simple_agents.conformance import run_checks

    report = run_checks("~/projects/inseam-agent")
    report.ok                      # False when any check failed
    print(report.text())

The same run is what ``simple-agents check`` prints, and ``--json`` is ``report.to_record()``.

Failure messages are parsed out of the shipped taxonomy rather than restated here, so the text
a coding agent acts on and the text the document specifies are one string. `docs/conformance.md`
covers what each check reads and how a project declares its tier.
"""

from __future__ import annotations

from .artifacts import Artifacts
from .brief import SOURCES, Brief, BriefEntry
from .decisions import DECISION_KINDS, Decision, DecisionKind, kind, kind_names
from .checks import CHECKS, Context
from .elicitation import QUESTIONS, Question, question, questions_at, required_at
from .report import CheckResult, Finding, Outcome, Report
from .run import run_checks
from .spend import Scope, UnfinishedAcross, unfinished_across
from .stages import FIRST_STAGE, STAGES, STAGES_BY_TIER, reached, stages_for, up_to
from .taxonomy import Entry, Taxonomy, Tier, taxonomy
from .writing import Recorded, clock_stamp, record_answer, record_decision

__all__ = [
    "run_checks",
    "Scope",
    "UnfinishedAcross",
    "unfinished_across",
    "Report",
    "CheckResult",
    "Finding",
    "Outcome",
    "Brief",
    "BriefEntry",
    "SOURCES",
    "Artifacts",
    "Context",
    "CHECKS",
    "QUESTIONS",
    "Question",
    "question",
    "questions_at",
    "required_at",
    "STAGES",
    "STAGES_BY_TIER",
    "FIRST_STAGE",
    "reached",
    "stages_for",
    "up_to",
    "DECISION_KINDS",
    "DecisionKind",
    "Decision",
    "kind",
    "kind_names",
    "Entry",
    "Taxonomy",
    "Tier",
    "taxonomy",
    "record_answer",
    "record_decision",
    "Recorded",
    "clock_stamp",
]
