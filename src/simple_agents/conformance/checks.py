"""The twenty-six checks the suite runs, each reading the artifacts the project produced.

Every check here is `artifact` surface: it reads files and executes nothing. The order below
is the order they run in, which puts the ones that need no evaluation first. All but FT-35,
FT-41 and FT-42 read the newest run. FT-35 reads every run the pipeline as it stands has made,
and FT-41 and FT-42 every run under the directory whatever made it.

| Entry | Reads | Fires when |
|---|---|---|
| FT-13 | the run directory's trajectory | no trajectory, or one nothing can read |
| FT-14 | the run directory's manifest | the model identifier floats |
| FT-15 | `prompts` in the run directory's manifest | a prompt records no version, which is a prompt whose source could not be read |
| FT-24 | the brief, against the stage the project is at | a required question has no answer |
| FT-29 | `idea.md`, and the stage it was last confirmed at | the file is missing, a section is empty, or it is stale |
| FT-30 | the brief's decisions | one is still `proposed`, or a kind has no entry at all |
| FT-31 | the run's manifest, and a live run's consultations | a shipped project's consultations reach a stand-in |
| FT-25 | the brief's `consultation` answer, the manifest's tools, and the results file | the answer names something to ask and no tool reaches a node |
| FT-32 | the brief's `tool_effects` answer, and the manifest's tools | the run declares a side-effect class the answer never mentions |
| FT-33 | `BUILD-LOG.md`, and when the newest run started | the log was last written before that run |
| FT-34 | `design.md`, and the stage it was last confirmed at | a section is empty, the builder is not quoted, or it is stale |
| FT-35 | every run this pipeline made, through their manifests | a node spent an allowance without calling a tool |
| FT-36 | `research.md`, and the stage it was last confirmed at | a section is empty, a candidate has no outcome, or it is stale |
| FT-01 | the results file | no evaluation, at tier `evaluated` |
| FT-02 | the results file | one split, or a held-out split that is empty |
| FT-03 | the results file | the contamination report holds a pair spanning the splits |
| FT-04 | the results file | no held-out example expects absence, in its answer or in a condition of its key |
| FT-06 | the results file | a metric reported with no interval and no reason |
| FT-07 | the results file and the trajectories | a rollout or a sampling node with no seed |
| FT-37 | the results file's stamp, against the newest run's | the reported number came from a pipeline that has since moved |
| FT-38 | the brief's `confirmed_against`, against the newest run's stamp | the entries describing the pipeline were never re-read |
| FT-39 | `comments.toml`, and the brief's `comments_block_gates` | a comment the builder left is still open and the brief says open comments block |
| FT-40 | the pipelines `agent.py` declares, else the run directory's manifest | a step is still `NotBuilt`: counted at every stage, a failure from `ship` |
| FT-41 | every run under the run directory, through their manifests | a run stopped to ask and is still waiting, and none was ever resumed |
| FT-42 | the brief's `produces`, against the node ids, tools and constants of every agent run | a decision names something no run recorded: counted at every stage, a failure from `ship` |
| FT-43 | the newest run's `mcp`, one entry per MCP server it declared tools from | a server offers something other than what the project declared |

**FT-37 and FT-38 read a change rather than an arrival.** Every other check fires when a
project reaches a point and passes forever after. These two compare what an artifact records
against what the newest run was made by, so they fire again each time the pipeline moves. Both
name stage `ship`, and a stage a project has reached it stays at, so both go on firing.

Each returns a ``CheckResult`` carrying the taxonomy's own message, never one written here.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .artifacts import (
    DEFAULT_DESIGN,
    DEFAULT_IDEA,
    DEFAULT_RESEARCH,
    DEFAULT_RUNS,
    DESIGN_SECTIONS,
    OUTCOME_COLUMN,
    PRODUCT_SECTION,
    QUOTED_SECTION,
    RESEARCH_SECTIONS,
    SURVEY_SECTION,
    Artifacts,
    empty_sections,
    has_table,
    other_roles,
    quoted_in,
    read_json,
    read_jsonl,
    rows_with_no_outcome,
    survey_rows,
    tables_under,
)
from .brief import Brief, BriefEntry
from .elicitation import QUESTIONS, Question, required_at
from .produced import Produced
from .report import CheckResult, Finding, Outcome
from .spend import UnfinishedAcross
from .recorded import RecordedNodes, calls_a_model as _calls_a_model
from .stages import FIRST_STAGE, STAGES, reached
from .taxonomy import Entry, Taxonomy
from ..envelope import runs
from ..records.trajectory import RECORD_TYPES as TRAJECTORY_RECORD_TYPES

__all__ = [
    "Context",
    "CHECKS",
    "COMMON_RECORD_FIELDS",
    "RECORD_TYPES",
    "FLOATING_MARKERS",
    "current_fingerprint",
    "entries_about_the_pipeline",
]

# `docs/trajectory-format.md` §2. A record missing one of these cannot be read as a record of
# the format, whatever else it holds. `tests/test_conformance.py` compares this against the
# document's own field table, so a field added to the format fails the suite here.
COMMON_RECORD_FIELDS = frozenset(
    {
        "format_version",
        "record_type",
        "record_id",
        "run_id",
        "parent_id",
        "sequence",
        "started_at",
        "ended_at",
        "error",
        "redactions",
        "omissions",
    }
)

RECORD_TYPES = frozenset(TRAJECTORY_RECORD_TYPES)

# A hosted provider publishes its aliases and its dated names side by side and marks neither
# as canonical, so the identifier is the only signal. These are the words that say a name
# floats; a name that floats without saying so passes (FT-14).
FLOATING_MARKERS = frozenset({"latest", "stable", "preview", "experimental", "main"})

# `runs/` is where the check already looked, and the rest are directories a project holds that
# no run is written into. Pruned rather than filtered, so a large tree is not walked.
_NOT_WALKED = frozenset(
    {
        "runs",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        "dist",
        ".tox",
        ".pytest_cache",
        "site-packages",
        ".ruff_cache",
    }
)

_SHA = re.compile(r"^[0-9a-f]{7,}$")
_WORDS = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class DeclaredPipelines:
    """What importing a project's ``agent.py`` produced, for the one check that needs it.

    ``planned`` names every step standing in as ``NotBuilt``, pipeline-qualified. ``problem``
    says why the code could not be read, and where it is set nothing was read.
    """

    planned: tuple[str, ...] = ()
    problem: str | None = None
    imported: bool = False
    surfaces: tuple[str, ...] = ()
    """Every surface the project's `Product` declares, by name. Empty where it declares no
    product, which is every project that has not adopted the declaration."""


@dataclass(frozen=True, slots=True)
class Context:
    """What every check is given: where the files are, what the project claims, the entries.

    ``unfinished`` is read once for the whole suite rather than per check, because it opens
    every run's manifest and both FT-35 and the report's note read it.
    """

    artifacts: Artifacts
    brief: Brief
    taxonomy: Taxonomy
    unfinished: UnfinishedAcross = field(default_factory=lambda: UnfinishedAcross(where="runs"))
    produced: Produced = field(default_factory=Produced)
    """What every run under ``runs/`` recorded producing, read once for the same reason
    ``unfinished`` is: it opens every manifest, and FT-42 and the report's note both read it."""
    declared: DeclaredPipelines | None = None
    """The project's pipelines read out of its own code, where they could be read.

    Every other check reads files. This one is the exception, and only FT-40 uses it: what a
    step is stands in ``agent.py``, and a project that has not run yet has no manifest for a
    check to read it from. ``None`` says the code was not read, and the check that wants it
    falls back to the manifest and says which it used.
    """

    def entry(self, entry_id: str) -> Entry:
        return self.taxonomy[entry_id]

    def results(self) -> tuple[Any, str | None]:
        """The results file as plain data, or a reason it could not be read."""
        if self.artifacts.results is None:
            return None, "no results file under evals/results/"
        return read_json(self.artifacts.results)

    def stage(self) -> str:
        """The stage this project is at: what it declared, or what its artifacts show.

        The tier decides which stages the project has, so a results file on a project claiming
        ``prototype`` leaves it where it was (`docs/conformance.md` §1.1).
        """
        return reached(
            self.brief.stage,
            has_run=self.artifacts.run_dir is not None,
            has_results=self.artifacts.results is not None,
            has_live_run=self.artifacts.live_run is not None,
            tier=self.brief.tier,
        )


def _result(ctx: Context, entry_id: str, outcome: Outcome, **kwargs: Any) -> CheckResult:
    entry = ctx.entry(entry_id)
    return CheckResult(
        entry_id=entry.id, name=entry.name, tier=str(entry.tier), outcome=outcome, **kwargs
    )


def _failure(ctx: Context, entry_id: str, read: tuple[str, ...], **values: Any) -> CheckResult:
    entry = ctx.entry(entry_id)
    return _result(
        ctx,
        entry_id,
        Outcome.FAILED,
        findings=(Finding(entry.id, entry.render(**values)),),
        read=read,
    )


# -- FT-13: no trajectory logging -----------------------------------------------------------


def ft_13(ctx: Context) -> CheckResult:
    """A run directory holding a trajectory that reads as the shipped format."""
    if ctx.artifacts.run_dir is None:
        return _failure(ctx, "FT-13", (), reason=_no_run_directory(ctx))

    path = ctx.artifacts.run_dir / "trajectory.jsonl"
    where = ctx.artifacts.relative(path) or str(path)
    read = (where,)
    if not path.exists():
        run = ctx.artifacts.relative(ctx.artifacts.run_dir)
        return _failure(ctx, "FT-13", read, reason=f"no trajectory.jsonl in {run}")

    records, reason = read_jsonl(path)
    if reason is not None:
        return _failure(ctx, "FT-13", read, reason=reason)

    problem = _first_malformed(records, where)
    if problem is not None:
        return _failure(ctx, "FT-13", read, reason=problem)
    if not any(r.get("record_type") == "node_execution" for r in records):
        return _failure(ctx, "FT-13", read, reason=f"{where} holds no node_execution record")
    return _result(ctx, "FT-13", Outcome.PASSED, read=read, detail=_payload_note(ctx, records))


def _elsewhere(ctx: Context) -> str | None:
    """A run directory outside `runs/`, which is a layout mismatch rather than a missing one.

    A project whose envelope writes somewhere else has recorded everything and is reported as
    having recorded nothing, so the reason names what was found and what reads it.
    """
    for base, directories, files in os.walk(ctx.artifacts.root):
        directories[:] = sorted(d for d in directories if d not in _NOT_WALKED)
        if "manifest.json" in files and Path(base) != ctx.artifacts.root:
            return ctx.artifacts.relative(Path(base))
    return None


def _no_run_directory(ctx: Context) -> str:
    others = other_roles(ctx.artifacts.root)
    if others:
        listed = ", ".join(f"{count} {role}" for role, count in sorted(others.items()))
        return (
            f"no run of the agent under runs/, and {listed}. A run declares what it is for "
            f"through RunEnvelope(role=...), and only role='agent' is a run of the project's "
            f"agent; run the agent through an envelope that leaves the role unset"
        )
    where = _elsewhere(ctx)
    if where is None:
        return "no run directory under runs/"
    return (
        f"no run directory under runs/, and a run was found at {where}. The checks read runs/; "
        f"pass --run {where} to read that one, or set RunEnvelope(run_dir='runs')"
    )


def _payload_note(ctx: Context, records: list[Any]) -> str | None:
    """What share of the payloads this run kept, where it kept fewer than all of them.

    The check passes at every rate: it reads whether the trajectory exists and parses. A run
    whose payloads were dropped still says so, so a reader of the report is not left to infer
    it from a small file.
    """
    omitted = sum(1 for r in records if isinstance(r, dict) and r.get("omissions"))
    if not omitted:
        return None
    rate: Any = None
    if ctx.artifacts.run_dir is not None:
        manifest, _ = read_json(ctx.artifacts.run_dir / "manifest.json")
        if isinstance(manifest, dict):
            rate = (manifest.get("recording") or {}).get("payload_rate")
    at = f" The envelope keeps them on {rate} of runs." if rate is not None else ""
    return (
        f"{omitted} of {len(records)} records had their payload fields dropped by sampling, "
        f"so this run records what happened and not what was said.{at}"
    )


def _first_malformed(records: list[Any], where: str) -> str | None:
    for number, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            return f"record {number} of {where} is not an object"
        missing = sorted(COMMON_RECORD_FIELDS - set(record))
        if missing:
            named = ", ".join(missing[:3])
            rest = f" and {len(missing) - 3} other fields" if len(missing) > 3 else ""
            return f"record {number} of {where} is missing {named}{rest}"
        if record["record_type"] not in RECORD_TYPES:
            # The list is joined from `RECORD_TYPES` and no count is spelled beside it, so a
            # record type added to the format cannot leave this message naming a stale number.
            return (
                f"record {number} of {where} declares record_type "
                f"{record['record_type']!r}, and the record types are "
                f"{', '.join(sorted(RECORD_TYPES))}"
            )
    if not records:
        return f"{where} is empty"
    return None


# -- FT-15: prompts unversioned ---------------------------------------------------------------


def ft_15(ctx: Context) -> CheckResult:
    """Whether every prompt the run recorded carries a version.

    A prompt reaches the manifest with the version declared as ``prompt_version=`` or a hash of
    its source, so what fails here is a prompt whose source could not be read: one defined in a
    REPL or through ``eval``, which leaves an edit with nothing to trace it to.
    """
    if ctx.artifacts.run_dir is None:
        return _result(
            ctx,
            "FT-15",
            Outcome.BLOCKED,
            detail="No run directory under runs/, so no manifest names a prompt (FT-13).",
        )
    path = ctx.artifacts.run_dir / "manifest.json"
    where = ctx.artifacts.relative(path) or str(path)
    read = (where,)

    manifest, reason = read_json(path)
    if reason is not None or not isinstance(manifest, dict):
        return _result(
            ctx,
            "FT-15",
            Outcome.BLOCKED,
            read=read,
            detail=f"{reason or f'{where} is not an object'}, so no prompt version is readable.",
        )

    prompts = manifest.get("prompts") or {}
    if not prompts:
        return _result(
            ctx,
            "FT-15",
            Outcome.PASSED,
            read=read,
            detail="This run declared no prompt, so there is no version to record.",
        )
    unreadable = sorted(
        node_id
        for node_id, entry in prompts.items()
        if not isinstance(entry, dict) or not entry.get("version")
    )
    findings = tuple(
        Finding(ctx.entry("FT-15").id, ctx.entry("FT-15").render(where=node_id))
        for node_id in unreadable
    )
    if findings:
        return _result(ctx, "FT-15", Outcome.FAILED, findings=findings, read=read)
    return _result(
        ctx,
        "FT-15",
        Outcome.PASSED,
        read=read,
        detail=f"{len(prompts)} prompt(s), each with a version recorded.",
    )


# -- FT-14: model version unpinned ----------------------------------------------------------


def ft_14(ctx: Context) -> CheckResult:
    """Every model identity that could have served a call, and whether any of them floats.

    A node may declare its own client, so a run can hold more than one. Each is reported
    separately: a project that pinned one model and left another floating should be told which.
    """
    if ctx.artifacts.run_dir is None:
        return _result(
            ctx,
            "FT-14",
            Outcome.BLOCKED,
            detail="No run directory under runs/, so no manifest names a model (FT-13).",
        )
    path = ctx.artifacts.run_dir / "manifest.json"
    where = ctx.artifacts.relative(path) or str(path)
    read = (where,)

    manifest, reason = read_json(path)
    if reason is not None or not isinstance(manifest, dict):
        return _result(
            ctx,
            "FT-14",
            Outcome.BLOCKED,
            read=read,
            detail=f"{reason or f'{where} is not an object'}, so no model identity is readable.",
        )

    models = manifest.get("models") or {}
    configured = models.get("configured") or {}
    observed = models.get("observed") or []
    serving = _serving_models(manifest, configured)

    if not serving and not observed:
        return _result(
            ctx,
            "FT-14",
            Outcome.PASSED,
            read=read,
            detail="This run made no model call, so it names no model to pin.",
        )
    if not serving:
        return _failure(ctx, "FT-14", read, alias="none recorded", where="every node")

    findings = tuple(
        Finding(ctx.entry("FT-14").id, ctx.entry("FT-14").render(alias=alias, where=at))
        for alias, at in ((_unpinned(identity), at) for identity, at in serving)
        if alias is not None
    )
    if findings:
        return _result(ctx, "FT-14", Outcome.FAILED, findings=findings, read=read)
    return _result(ctx, "FT-14", Outcome.PASSED, read=read, detail=_pinned_note(serving))


def _serving_models(
    manifest: dict[str, Any], configured: dict[str, Any]
) -> list[tuple[dict[str, Any], str]]:
    """Each identity that could serve a call, with the nodes it serves, deduplicated.

    A node records the client it declared and `null` where it takes the run's, which is the
    resolution `docs/run-envelope.md` §2.2 states. A manifest with no `nodes` array is read for
    its configured pin alone, which is what a project writing its own manifest produces.

    An embedding or reranking model is on no node, because it is reached from a tool rather
    than declared by a step. `models.observed` is read for those, so a run whose corpus was
    embedded by an unpinned model is reported rather than passing.
    """
    entries = RecordedNodes(manifest).model_calling()
    found: dict[str, tuple[dict[str, Any], list[str]]] = {}
    if not entries:
        if configured:
            found[json.dumps(configured, sort_keys=True, default=str)] = (
                configured,
                ["every node"],
            )
    else:
        for entry in entries:
            identity = entry.get("model") or configured
            if not identity:
                continue
            key = json.dumps(identity, sort_keys=True, default=str)
            found.setdefault(key, (identity, []))[1].append(str(entry.get("node_id")))

    for entry in manifest.get("models", {}).get("observed") or []:
        if not isinstance(entry, dict):
            continue
        identity = {
            "backend": entry.get("backend"),
            "request_model": entry.get("request_model"),
            "model_revision": entry.get("model_revision"),
        }
        if not identity["request_model"]:
            continue
        key = json.dumps(identity, sort_keys=True, default=str)
        if key not in found:
            found[key] = (identity, ["calls it served"])
    return [(identity, ", ".join(nodes)) for identity, nodes in found.values()]


def _unpinned(identity: dict[str, Any]) -> str | None:
    """The identifier to report, or ``None`` where this identity is pinned."""
    request_model = str(identity.get("request_model") or "")
    revision = identity.get("model_revision")
    if not request_model:
        return "none recorded"
    if str(identity.get("backend") or "") == "self_hosted":
        if not _SHA.match(str(revision or "")):
            return request_model if revision is None else f"{request_model}@{revision}"
        return None
    return request_model if _floats(request_model) else None


def _pinned_note(serving: list[tuple[dict[str, Any], str]]) -> str | None:
    """What a passing run is worth saying about, which is more than one model serving it."""
    if len(serving) < 2:
        return None
    named = "; ".join(f"{identity.get('request_model')} on {at}" for identity, at in serving)
    return f"{len(serving)} models served this run, each pinned: {named}."


def _floats(identifier: str) -> bool:
    return bool(FLOATING_MARKERS & set(_WORDS.split(identifier.lower())))


# -- FT-24: elicitation skipped -------------------------------------------------------------


def ft_24(ctx: Context) -> CheckResult:
    """Every question required at the stage the project is at has an answer or a deferral."""
    stage = ctx.stage()
    read = _read(ctx, ctx.brief.path)

    missing = [
        q.name for q in required_at(stage, ctx.brief.tier) if not _settled(ctx.brief, q, stage)
    ]
    if missing:
        return _failure(ctx, "FT-24", read, stage=stage, list=", ".join(missing))
    return _result(ctx, "FT-24", Outcome.PASSED, read=read, detail=_stage_note(ctx, stage))


def _settled(brief: Brief, question: Question, stage: str) -> bool:
    """Whether the brief carries an answer to this question, or a deferral still ahead of it.

    A question with no entry at all counts as unanswered, which is what makes a brief that
    was never filled in fail rather than pass for want of anything to read.

    An answer sourced ``coding_agent`` counts as unanswered too. The coding agent wrote it and
    the builder has not seen it, which is what the field exists to say, and a gate that passed
    on it would leave the honest record costing more than the silent one.

    A deferral settles the question only until the project reaches the stage it names. At that
    stage the answer is due, and an entry still deferred to it leaves the decision as open as
    one nobody put.

    A question every gate puts again is settled only where ``asked_at`` names the stage the
    project is at or a later one. This is what `understanding_confirmed_at` does for a
    document, applied to a question: the answer is dated, and a date behind the project says
    it was not asked at this stage.
    """
    entry = brief.entry(question.name)
    if entry is None:
        return False
    if entry.status == "answered":
        if entry.source == "coding_agent":
            return False
        return not question.re_asked_each_stage or _asked_here(entry, stage)
    if entry.status != "deferred" or entry.deferred_to is None:
        return False
    return STAGES.index(entry.deferred_to) > STAGES.index(stage)


def _asked_here(entry: BriefEntry, stage: str) -> bool:
    """Whether the question was last put at the stage the project is at, or later."""
    if entry.asked_at is None:
        return False
    return STAGES.index(entry.asked_at) >= STAGES.index(stage)


def _stage_note(ctx: Context, stage: str) -> str | None:
    """Where the stage came from, when the artifacts moved it past what the brief declared."""
    if ctx.brief.stage == stage:
        return None
    shown = f"declares stage {ctx.brief.stage!r}" if ctx.brief.stage else "declares no stage"
    if stage == FIRST_STAGE:
        return f"The brief {shown}, so the questions of stage {stage!r} apply."
    return (
        f"The brief {shown} and the project has produced the artifacts of stage {stage!r}, "
        f"so the questions up to {stage!r} apply."
    )


# -- FT-29: no current account of the project -----------------------------------------------


def ft_29(ctx: Context) -> CheckResult:
    """`idea.md` carries its five sections, and the brief confirms it at the current stage."""
    stage = ctx.stage()
    read = _read(ctx, ctx.brief.path)
    reason = _account_reason(ctx, stage)
    if reason is not None:
        if ctx.artifacts.idea is not None:
            read = read + _read(ctx, ctx.artifacts.idea)
        return _failure(ctx, "FT-29", read, reason=reason, stage=stage)
    return _result(ctx, "FT-29", Outcome.PASSED, read=read + _read(ctx, ctx.artifacts.idea))


def _account_reason(ctx: Context, stage: str) -> str | None:
    """Why the account is not current, or `None` where it is."""
    if ctx.artifacts.idea is None:
        return f"no {DEFAULT_IDEA} at {ctx.artifacts.root}"
    try:
        text = ctx.artifacts.idea.read_text(encoding="utf-8")
    except OSError as exc:
        return f"{DEFAULT_IDEA} could not be read: {exc}"
    blank = empty_sections(text)
    if blank:
        return f"{DEFAULT_IDEA} has nothing under {', '.join(repr(name) for name in blank)}"
    confirmed = ctx.brief.understanding_confirmed_at
    if confirmed is None:
        return "the brief carries no understanding_confirmed_at"
    if STAGES.index(confirmed) < STAGES.index(stage):
        return (
            f"the brief confirms {DEFAULT_IDEA} at stage {confirmed!r} and the project is at "
            f"{stage!r}"
        )
    return None


# -- FT-34: the design the builder agreed to ------------------------------------------------


def ft_34(ctx: Context) -> CheckResult:
    """`design.md` carries its four sections, quotes the builder, and is confirmed here."""
    stage = ctx.stage()
    read = _read(ctx, ctx.brief.path)
    reason = _design_reason(ctx, stage)
    if reason is not None:
        if ctx.artifacts.design is not None:
            read = read + _read(ctx, ctx.artifacts.design)
        return _failure(ctx, "FT-34", read, reason=reason, stage=stage)
    return _result(ctx, "FT-34", Outcome.PASSED, read=read + _read(ctx, ctx.artifacts.design))


def _design_reason(ctx: Context, stage: str) -> str | None:
    """Why the design is not written down or not current, or `None` where it is."""
    if ctx.artifacts.design is None:
        return f"no {DEFAULT_DESIGN} at {ctx.artifacts.root}"
    try:
        text = ctx.artifacts.design.read_text(encoding="utf-8")
    except OSError as exc:
        return f"{DEFAULT_DESIGN} could not be read: {exc}"
    blank = empty_sections(text, DESIGN_SECTIONS)
    if blank:
        return f"{DEFAULT_DESIGN} has nothing under {', '.join(repr(name) for name in blank)}"
    if not quoted_in(text, QUOTED_SECTION):
        return f"{DEFAULT_DESIGN} quotes nobody under {QUOTED_SECTION!r}"
    unnamed = _surfaces_not_in(ctx, text)
    if unnamed:
        return (
            f"{DEFAULT_DESIGN} classifies no interaction at "
            f"{', '.join(repr(name) for name in unnamed)}, which the code declares as a "
            f"surface"
        )
    confirmed = ctx.brief.design_confirmed_at
    if confirmed is None:
        return "the brief carries no design_confirmed_at"
    if STAGES.index(confirmed) < STAGES.index(stage):
        return (
            f"the brief confirms {DEFAULT_DESIGN} at stage {confirmed!r} and the project is at "
            f"{stage!r}"
        )
    return None


def _surfaces_not_in(ctx: Context, text: str) -> tuple[str, ...]:
    """Declared surfaces the product section of `design.md` does not name.

    The product section lists what the end user can do and classifies each interaction
    (`docs/product.md` §2), and a `Product` declares the same surfaces in code. A surface the
    section never names is an interaction the builder was not shown, which is this entry's
    subject. Matched on the surface's own name, which the project chose, so this reports a
    name that is absent and never whether what the section says about a named one is right.

    Empty for a project declaring no product, so nothing here reaches a project that has not
    adopted the declaration.
    """
    declared = getattr(ctx.declared, "surfaces", ()) or ()
    if not declared:
        return ()
    section = _section_of(text, PRODUCT_SECTION)
    if section is None:
        return tuple(declared)
    said = _WORDS.sub(" ", section.casefold())
    return tuple(
        name for name in declared if _WORDS.sub(" ", str(name).casefold()).strip() not in said
    )


def _section_of(text: str, heading: str) -> str | None:
    """The body under one `##` heading, or ``None`` where the file has no such heading."""
    wanted = heading.casefold()
    body: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            if body is not None:
                break
            body = [] if line[3:].strip().casefold() == wanted else None
            continue
        if body is not None:
            body.append(line)
    return "\n".join(body) if body is not None else None


# -- FT-36: the ground was never checked ------------------------------------------------------


def ft_36(ctx: Context) -> CheckResult:
    """`research.md` carries its four sections, every candidate has an outcome, and it is current."""
    stage = ctx.stage()
    read = _read(ctx, ctx.brief.path)
    reason = _research_reason(ctx, stage)
    if reason is not None:
        if ctx.artifacts.research is not None:
            read = read + _read(ctx, ctx.artifacts.research)
        return _failure(ctx, "FT-36", read, reason=reason, stage=stage)
    return _result(ctx, "FT-36", Outcome.PASSED, read=read + _read(ctx, ctx.artifacts.research))


def _research_reason(ctx: Context, stage: str) -> str | None:
    """Why the research is missing, incomplete or stale, or `None` where it is none of those."""
    if ctx.artifacts.research is None:
        return f"no {DEFAULT_RESEARCH} at {ctx.artifacts.root}"
    try:
        text = ctx.artifacts.research.read_text(encoding="utf-8")
    except OSError as exc:
        return f"{DEFAULT_RESEARCH} could not be read: {exc}"
    blank = empty_sections(text, RESEARCH_SECTIONS)
    if blank:
        return f"{DEFAULT_RESEARCH} has nothing under {', '.join(repr(name) for name in blank)}"
    if not has_table(text, SURVEY_SECTION):
        return f"{SURVEY_SECTION!r} holds no table, and what was decided about each candidate"
    if not has_table(text, SURVEY_SECTION, OUTCOME_COLUMN):
        return (
            f"the table under {SURVEY_SECTION!r} has no {OUTCOME_COLUMN!r} column, so no row "
            f"says what was decided about the candidate it names"
        )
    if not survey_rows(text, SURVEY_SECTION, OUTCOME_COLUMN):
        reason = (
            f"the table under {SURVEY_SECTION!r} has a header and no candidate under it, so "
            f"nothing was looked at"
        )
        tables = tables_under(text, SURVEY_SECTION)
        if tables > 1:
            reason += (
                f". A blank line ends a markdown table, and this section holds {tables} of "
                f"them, so a row separated from its header by one is read as a table of its own"
            )
        return reason
    unfilled = rows_with_no_outcome(text, SURVEY_SECTION, OUTCOME_COLUMN)
    if unfilled:
        return (
            f"{len(unfilled)} row(s) under {SURVEY_SECTION!r} have an empty {OUTCOME_COLUMN!r}: "
            f"{', '.join(repr(name) for name in unfilled)}"
        )
    if not quoted_in(text, QUOTED_SECTION):
        return f"{DEFAULT_RESEARCH} quotes nobody under {QUOTED_SECTION!r}"
    confirmed = ctx.brief.research_confirmed_at
    if confirmed is None:
        return "the brief carries no research_confirmed_at"
    if STAGES.index(confirmed) < STAGES.index(stage):
        return (
            f"the brief confirms {DEFAULT_RESEARCH} at stage {confirmed!r} and the project is "
            f"at {stage!r}"
        )
    return None


# -- FT-30: design decisions the builder never saw -------------------------------------------


def ft_30(ctx: Context) -> CheckResult:
    """Every decision kind has an entry, and none is still `proposed`."""
    read = _read(ctx, ctx.brief.path)
    missing = ctx.brief.kinds_with_no_decision()
    unseen = ctx.brief.unseen_decisions()
    if not missing and not unseen:
        return _result(ctx, "FT-30", Outcome.PASSED, read=read)
    parts = []
    if unseen:
        parts.append(f"{', '.join(repr(name) for name in unseen)} still recorded 'proposed'")
    if missing:
        parts.append(f"nothing recorded for {', '.join(repr(name) for name in missing)}")
    return _failure(ctx, "FT-30", read, reason="; ".join(parts))


# -- FT-31: shipped on a development channel -------------------------------------------------

# `end_user` is a person the agent is for and `builder` is the author standing in for them, so
# only the first is a reader once the project has shipped. `nobody` is `unattended()`, which is
# a design the brief's `someone_there` answer settles rather than a check.
SHIPPED_ANSWERERS = frozenset({"end_user", "nobody"})


def ft_31(ctx: Context) -> CheckResult:
    """No consultation reaches a stand-in once the project has shipped."""
    from_run, where = _answerers_of(ctx)
    read = _read(ctx, where)
    stand_ins = sorted(name for name in from_run if name not in SHIPPED_ANSWERERS)
    if stand_ins:
        return _failure(
            ctx,
            "FT-31",
            read,
            answerer=", ".join(stand_ins),
            where=ctx.artifacts.relative(where) or "the manifest",
        )
    return _result(ctx, "FT-31", Outcome.PASSED, read=read, detail=_channel_note(ctx, from_run))


def _answerers_of(ctx: Context) -> tuple[set[str], Path | None]:
    """Who the project's consultations reach, and the file that says so.

    A live run's trajectory wins, because it records what that run did. Where the project has
    no live run, or none of its consultations reached the tool, the manifest's tool entries and
    the channel the run itself declared are read instead.
    """
    if ctx.artifacts.live_run is not None:
        answered = _answerers_in_trajectory(ctx.artifacts.live_run / "trajectory.jsonl")
        if answered:
            return answered, ctx.artifacts.live_run / "trajectory.jsonl"
    manifest = ctx.artifacts.live_run or ctx.artifacts.run_dir
    if manifest is None:
        return set(), None
    path = manifest / "manifest.json"
    data, reason = read_json(path)
    if reason is not None or not isinstance(data, dict):
        return set(), path
    declared = {
        str(tool.get("answered_by"))
        for tool in (data.get("tools") or [])
        if isinstance(tool, dict) and tool.get("answered_by")
    }
    supplied = (data.get("end_user") or {}).get("answered_by")
    return (({str(supplied)} if supplied else declared), path)


def _answerers_in_trajectory(path: Path) -> set[str]:
    """The `answered_by` of every consultation the run recorded."""
    records, _ = read_jsonl(path)
    return {
        str(record.get("answered_by"))
        for record in records
        if isinstance(record, dict)
        and record.get("record_type") == "consultation"
        and record.get("answered_by")
    }


def _channel_note(ctx: Context, answerers: set[str]) -> str | None:
    """What a passing FT-31 read, where the answer is worth naming.

    Both facts can be true at once, and neither is a failure: a project may have nothing to
    ask, and the gate runs before the agent is handed to anyone.
    """
    parts = []
    if not answerers:
        parts.append("No consultation tool is registered, so no channel reaches an end user.")
    if ctx.artifacts.live_run is None:
        parts.append(
            "No run under runs/ is marked live. RunEnvelope(live=True) is what separates the "
            "runs an end user made from the runs made building the project."
        )
    return " ".join(parts) or None


# -- FT-25: consultation treated as a fault path ---------------------------------------------

# The words an answer opens on when it records that there is nothing to ask. The scaffold asks
# for such an answer rather than a blank, and it arrives as a sentence: the `conforming` fixture
# answers "Nothing. Every input the agent needs is in the collection." Only the first word is
# read, because anything further is reading prose.
NOTHING_TO_ASK = frozenset({"none", "nothing", "no", "not", "never", "n", "na"})


def ft_25(ctx: Context) -> CheckResult:
    """A consultation tool exists and reaches a node, where the brief names something to ask."""
    entry = ctx.brief.entry("consultation")
    if entry is None or entry.status != "answered" or not (entry.answer or "").strip():
        return _result(
            ctx,
            "FT-25",
            Outcome.BLOCKED,
            detail="The brief carries no answered `consultation` entry, which FT-24 reports.",
        )
    if _says_nothing_to_ask(entry.answer or ""):
        return _result(
            ctx,
            "FT-25",
            Outcome.PASSED,
            read=(ctx.artifacts.relative(ctx.brief.path) or "brief.toml",),
            detail="The `consultation` answer records that there is nothing to ask.",
        )

    tools, where, reason = _manifest_tools(ctx)
    if reason is not None:
        return _result(ctx, "FT-25", Outcome.BLOCKED, read=_read(ctx, where), detail=reason)

    channels = [tool for tool in tools if tool.get("answered_by")]
    read = (ctx.artifacts.relative(ctx.brief.path) or "brief.toml", *_read(ctx, where))
    if not channels:
        return _failure(
            ctx, "FT-25", read, reason="no consultation tool is registered on the run's manifest"
        )
    if not any(tool.get("offered") for tool in channels):
        named = ", ".join(sorted(str(tool.get("name")) for tool in channels))
        return _failure(
            ctx,
            "FT-25",
            read,
            reason=f"the consultation tool {named} is registered and no node was given it",
        )
    note, also_read = _was_it_ever_reached(ctx, channels)
    return _result(ctx, "FT-25", Outcome.PASSED, read=(*read, *also_read), detail=note)


def _was_it_ever_reached(
    ctx: Context, channels: list[dict[str, Any]]
) -> tuple[str | None, tuple[str, ...]]:
    """What the run and the evaluation this check read did with the consultation tool.

    Returns the note and any artifact it named beyond the two FT-25 always reads.

    Registration and reachability are what FT-25 verifies. Whether a question was ever asked
    is not a requirement, since a run may legitimately have had nothing to ask, so this is a
    note on a pass. One project registered a tool this check certified and evaluated a
    pipeline whose only call site was unreachable, over 276 rollouts that asked nothing.

    The evaluation half is the one a project is least likely to look at. A rollout is refused
    over a channel that reaches a person, so every rollout answers with a stand-in or with
    ``Unavailable``, and an evaluation is the repeated execution a project watches most. A
    consultation that no rollout reached was measured by none of it.
    """
    named = ", ".join(sorted(str(tool.get("name")) for tool in channels))
    said, also_read = [], []
    if _the_run_asked_nothing(ctx):
        said.append("The run read here asked nothing through it")
    asked, rollouts = _consultations_in_the_results(ctx)
    if rollouts and not asked:
        said.append(
            f"None of the {rollouts:,} rollout(s) in the newest results file asked through it"
        )
        also_read.append(ctx.artifacts.relative(ctx.artifacts.results) or "")
    if not said:
        return None, ()
    return (
        f"{named} is registered and reaches a node. {'. '.join(said)}. This check reads "
        f"registration, never whether a question was asked."
    ), tuple(also_read)


def _the_run_asked_nothing(ctx: Context) -> bool:
    """Whether the run this check read recorded a consultation count of zero."""
    if ctx.artifacts.run_dir is None:
        return False
    manifest, _ = read_json(ctx.artifacts.run_dir / "manifest.json")
    counts = manifest.get("counts") if isinstance(manifest, dict) else None
    return isinstance(counts, dict) and counts.get("consultation") == 0


def _consultations_in_the_results(ctx: Context) -> tuple[int, int]:
    """Consultations and rollouts in the newest results file, or ``(0, 0)`` where it has none.

    Read off the per-node section, which counts a consultation under the node that made it,
    so a pipeline whose only call site is unreachable reports zero across every node.
    """
    raw, _ = ctx.results()
    if not isinstance(raw, dict):
        return 0, 0
    rollouts = raw.get("rollouts")
    if not isinstance(raw.get("nodes"), dict) or not isinstance(rollouts, list) or not rollouts:
        return 0, 0
    asked = sum(
        int(entry.get("consultations") or 0)
        for entry in _result_nodes(raw).values()
        if isinstance(entry.get("consultations"), int)
    )
    return asked, len(rollouts)


def _says_nothing_to_ask(answer: str) -> bool:
    """Whether the answer opens on a negation, which is how it records nothing to ask.

    An answer opening on one and then naming something passes this, and the taxonomy says so.
    The alternative is reading prose, which no check in the suite does.
    """
    words = _WORDS.sub(" ", answer.casefold()).split()
    return bool(words) and words[0] in NOTHING_TO_ASK


# -- FT-32: the brief describes a pipeline that no longer exists ------------------------------

# The classes `tool_effects` asks about: "what may this agent do that reaches outside the run".
# `read_only` is the answer "nothing", and a builder writes that as "it only reads" or "it asks
# the reader", so requiring the word would fail an answer that describes the tools correctly.
DECLARED_EFFECTS = frozenset({"writes", "spends_money", "irreversible"})


def ft_32(ctx: Context) -> CheckResult:
    """The `tool_effects` answer mentions every effect the run declares that reaches out."""
    entry = ctx.brief.entry("tool_effects")
    if entry is None or entry.status != "answered" or not (entry.answer or "").strip():
        return _result(
            ctx,
            "FT-32",
            Outcome.BLOCKED,
            detail="The brief carries no answered `tool_effects` entry, which FT-24 reports.",
        )

    tools, where, reason = _manifest_tools(ctx)
    if reason is not None:
        return _result(ctx, "FT-32", Outcome.BLOCKED, read=_read(ctx, where), detail=reason)

    read = (ctx.artifacts.relative(ctx.brief.path) or "brief.toml", *_read(ctx, where))
    if not tools:
        return _result(
            ctx,
            "FT-32",
            Outcome.PASSED,
            read=read,
            detail="This run registered no tool, so the answer has nothing to describe.",
        )

    said = _WORDS.sub(" ", (entry.answer or "").casefold())
    undescribed = sorted(
        {
            str(tool.get("side_effect_class"))
            for tool in tools
            if str(tool.get("side_effect_class")) in DECLARED_EFFECTS
            and _WORDS.sub(" ", str(tool.get("side_effect_class")).casefold()) not in said
        }
    )
    if not undescribed:
        return _result(ctx, "FT-32", Outcome.PASSED, read=read)

    named = ", ".join(
        sorted(
            f"{tool.get('name')} ({tool.get('side_effect_class')})"
            for tool in tools
            if str(tool.get("side_effect_class")) in undescribed
        )
    )
    return _failure(
        ctx,
        "FT-32",
        read,
        reason=(
            f"the run declares {', '.join(undescribed)} and the answer mentions no effect of "
            f"that kind, from {named}"
        ),
    )


def _manifest_tools(ctx: Context) -> tuple[list[dict[str, Any]], Path | None, str | None]:
    """The `tools` the newest run's manifest declares, or a reason there are none to read."""
    if ctx.artifacts.run_dir is None:
        return [], None, "No run directory under runs/, so no manifest names a tool (FT-13)."
    path = ctx.artifacts.run_dir / "manifest.json"
    manifest, reason = read_json(path)
    where = ctx.artifacts.relative(path) or str(path)
    if reason is not None or not isinstance(manifest, dict):
        return [], path, f"{reason or f'{where} is not an object'}, so no tool is readable."
    return (
        [tool for tool in (manifest.get("tools") or []) if isinstance(tool, dict)],
        path,
        None,
    )


# -- FT-33: the build log stopped before the work did -----------------------------------------

BUILD_LOG = "BUILD-LOG.md"


def ft_33(ctx: Context) -> CheckResult:
    """A build log the project keeps was written no earlier than its newest run started."""
    log = ctx.artifacts.root / BUILD_LOG
    if not log.is_file():
        return _result(
            ctx,
            "FT-33",
            Outcome.PASSED,
            detail=(
                f"This project keeps no {BUILD_LOG}. docs/procedure.md asks for one, recording "
                f"each exchange with the builder as it happens, and whether to keep one is the "
                f"builder's decision."
            ),
        )
    if ctx.artifacts.run_dir is None:
        return _result(
            ctx,
            "FT-33",
            Outcome.BLOCKED,
            read=_read(ctx, log),
            detail="No run directory under runs/, so nothing dates the work (FT-13).",
        )

    started = _run_finished_at(ctx.artifacts.run_dir / "manifest.json")
    if started is None:
        return _result(
            ctx,
            "FT-33",
            Outcome.BLOCKED,
            read=_read(ctx, log),
            detail="The newest run's manifest carries no timestamp, so nothing dates the work.",
        )
    written = datetime.fromtimestamp(log.stat().st_mtime, tz=timezone.utc)
    if written >= started:
        return _result(ctx, "FT-33", Outcome.PASSED, read=_read(ctx, log))
    return _failure(
        ctx,
        "FT-33",
        (*_read(ctx, log), *_read(ctx, ctx.artifacts.run_dir / "manifest.json")),
        log_written=written.isoformat(timespec="seconds"),
        run_started=started.isoformat(timespec="seconds"),
    )


def _run_finished_at(path: Path) -> datetime | None:
    """When the run this manifest describes ended, or ``None`` where it does not say.

    ``ended_at`` rather than ``started_at``, because a log entry about a run can only be
    written once that run has finished. It gives the comparison a margin the length of the run
    rather than an arbitrary tolerance, so a log written while a two-minute run was
    going is not reported as one that stopped. A run that crashed or is still going records no
    ``ended_at``, and its start is what dates it.
    """
    manifest, reason = read_json(path)
    if reason is not None or not isinstance(manifest, dict):
        return None
    for key in ("ended_at", "started_at"):
        raw = manifest.get(key)
        if not isinstance(raw, str) or not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


# -- FT-35: steps spent without a tool call -------------------------------------------------


def ft_35(ctx: Context) -> CheckResult:
    """Whether any node spent a whole allowance without acting, over the runs one pipeline made.

    The one check that reads more than the newest run. A project spending a quarter of its
    calls this way can have nine runs in ten come back clean, so a figure over one run says
    nothing, and the counts come from each run's manifest rather than its trajectory.
    """
    found = ctx.unfinished
    if not found.read:
        return _result(
            ctx,
            "FT-35",
            Outcome.BLOCKED,
            detail=_nothing_to_read(found),
        )

    read = (f"{found.where}/, {found.read} manifest(s)",)
    spinning = found.spinning()
    if spinning:
        entry = ctx.entry("FT-35")
        return _result(
            ctx,
            "FT-35",
            Outcome.FAILED,
            read=read,
            findings=tuple(
                Finding(
                    entry.id,
                    entry.render(
                        node=node_id,
                        units=f"{counts['without_tool_calls']:,}",
                        runs=found.covered(),
                        calls=f"{counts['model_calls_without_tool_calls']:,}",
                    ),
                )
                for node_id, counts in spinning.items()
            ),
        )
    return _result(ctx, "FT-35", Outcome.PASSED, read=read, detail=_what_was_read(found))


def _nothing_to_read(found: UnfinishedAcross) -> str:
    """Why the check had no counts to read, which is one of five things.

    A project with no run at all is FT-13's report. The other four are runs it has that this
    cannot read: none declaring the role, none with a readable manifest, none finished, and
    none new enough to carry the counts. Saying "no runs" to any of those would be false, and
    each names a different thing to do about it.
    """
    if not found.found:
        return f"No run under {found.where}/, so no run says what it produced (FT-13)."
    if found.without_counts:
        return (
            f"{found.without_counts:,} run(s) of this pipeline were written before the "
            f"manifest carried these counts, and no run since. Run the agent once against "
            f"this version of the library and the next check reads it."
        )
    if found.unreadable:
        return (
            f"{found.unreadable:,} run(s) under {found.where}/ carry a manifest nothing could "
            f"read, so none of them says which pipeline made it or what it produced (FT-13)."
        )
    if found.still_running:
        return (
            f"{found.still_running:,} run(s) under {found.where}/ have not finished, and a "
            f"run records what it produced when it ends. This reads them once they have."
        )
    narrowed = ", ".join(f"{name} {value}" for name, value in found.narrowed_by.items())
    if narrowed:
        return (
            f"{found.found:,} run(s) under {found.where}/ and none left to read after "
            f"{narrowed}. Nothing is measured, so nothing is reported."
        )
    return (
        f"{found.found:,} run(s) under {found.where}/ and none declaring role={found.role!r}. "
        f"A run declares what it is for through RunEnvelope(role=...), and only role='agent' "
        f"is a run of the project's agent, which is what every check reads (FT-13)."
    )


def _what_was_read(found: UnfinishedAcross) -> str:
    """What a passing check covered, so a pass can be read as narrowly as it was made."""
    waived = (
        f" {len(found.waived)} node(s) declare allow_unfinished=True: "
        f"{', '.join(sorted(found.waived))}."
        if found.waived
        else ""
    )
    # A pass over a scoped set reads as a pass over the project, and the runs left out can hold
    # what the check is for. The scope is right, since a figure over a pipeline that has changed
    # is a stale figure, so the line names where the rest can be read instead.
    elsewhere = (
        f" `simple-agents report {found.where}/` reads every run under it, including those."
        if found.other_pipeline or found.other_role or found.without_counts
        else ""
    )
    return f"Read {found.covered()}. No node spent an allowance without acting.{waived}{elsewhere}"


# -- FT-01: no evaluation at all ------------------------------------------------------------


def ft_01(ctx: Context) -> CheckResult:
    """A results file that was produced by scoring a labeled set."""
    results, reason = ctx.results()
    read = _read(ctx, ctx.artifacts.results)
    if reason is not None or not isinstance(results, dict):
        return _failure(ctx, "FT-01", read)

    config = results.get("config") or {}
    example_set = config.get("example_set") or {}
    if not results.get("rollouts") or not example_set.get("content_hash"):
        return _failure(ctx, "FT-01", read)
    return _result(ctx, "FT-01", Outcome.PASSED, read=read)


# -- FT-02: no held-out split ---------------------------------------------------------------


def ft_02(ctx: Context) -> CheckResult:
    """At least two splits, and the one named held-out is not empty."""
    results, _ = ctx.results()
    read = _read(ctx, ctx.artifacts.results)
    if not isinstance(results, dict):
        return _blocked_on_results(ctx, "FT-02")

    example_set = (results.get("config") or {}).get("example_set") or {}
    splits = example_set.get("splits")
    if not isinstance(splits, dict) or not splits:
        return _failure(ctx, "FT-02", read, reason="the results file records no splits")

    held_out = str(example_set.get("held_out") or "held_out")
    named = ", ".join(f"{name} ({count})" for name, count in splits.items())
    if held_out not in splits:
        return _failure(
            ctx,
            "FT-02",
            read,
            reason=f"the set names {held_out!r} as held out and its splits are {named}",
        )
    if not splits[held_out]:
        return _failure(ctx, "FT-02", read, reason=f"the {held_out!r} split is empty")
    if len(splits) < 2:
        return _failure(
            ctx, "FT-02", read, reason=f"the example set declares one split, {held_out!r}"
        )
    return _result(ctx, "FT-02", Outcome.PASSED, read=read)


# -- FT-03: dev examples leaked into the held-out set ---------------------------------------


def ft_03(ctx: Context) -> CheckResult:
    """The contamination report the evaluation wrote found no pair spanning the splits."""
    results, _ = ctx.results()
    read = _read(ctx, ctx.artifacts.results)
    if not isinstance(results, dict):
        return _blocked_on_results(ctx, "FT-03")

    report = results.get("contamination")
    if not isinstance(report, dict):
        # `n/a` and not `passed`: the example set is on disk and the property is computable,
        # so no check was made rather than none was needed.
        return _result(
            ctx,
            "FT-03",
            Outcome.NOT_APPLICABLE,
            read=read,
            detail=(
                "No threshold was set, so this evaluation ran no contamination check and this "
                "check made none. The brief's `too_similar` entry records what the project "
                "decided counts as the same example twice; pass contamination_threshold= to "
                "EvalSuite to run the check against it."
            ),
        )

    pairs = report.get("pairs") or []
    if pairs:
        return _failure(ctx, "FT-03", read, n=len(pairs), threshold=report.get("threshold"))
    return _result(ctx, "FT-03", Outcome.PASSED, read=read)


# -- FT-04: happy path only, no absent-data cases -------------------------------------------


def ft_04(ctx: Context) -> CheckResult:
    """The held-out split holds at least one example whose correct answer is absence.

    Absence in one condition of a decomposed answer key counts, so a project whose answer is a
    record and whose absent cases are single empty fields satisfies this with the examples it
    already has (``Criterion(expects_absence=True)``).

    A pipeline whose every model-calling node waived the absence branch has declared that this
    output has no absent state, and the check does not fire.
    """
    results, _ = ctx.results()
    read = _read(ctx, ctx.artifacts.results)
    if not isinstance(results, dict):
        return _blocked_on_results(ctx, "FT-04")

    if _absence_waived(results):
        return _result(
            ctx,
            "FT-04",
            Outcome.PASSED,
            read=read,
            detail=(
                "The node(s) producing the scored answer declare allow_unknown=False, so this "
                "output has no absent state and no example can carry one."
            ),
        )

    told = _what_the_builder_said(ctx, "absence_vs_error")
    where = _where_absence_is_declared(results.get("config") or {})

    examples = results.get("examples")
    if not isinstance(examples, dict):
        return _failure(ctx, "FT-04", read, node=where, said=told)

    held_out = str(
        ((results.get("config") or {}).get("example_set") or {}).get("held_out") or "held_out"
    )
    absent = sum(
        1
        for entry in examples.values()
        if isinstance(entry, dict)
        and entry.get("split") == held_out
        and (entry.get("expects_absence") or entry.get("absent_parts"))
    )
    if not absent:
        return _failure(ctx, "FT-04", read, node=where, said=told)
    return _result(ctx, "FT-04", Outcome.PASSED, read=read)


def _what_the_builder_said(ctx: Context, name: str) -> str:
    """One brief answer as a failure message quotes it, or what to do where there is none.

    The answer decides nothing here: the declaration on the node is what the manifest records
    and what a later reader can check. Quoting it puts the builder's own words beside the fix,
    where a coding agent that already asked is otherwise told the abstract version of it.
    """
    entry = ctx.brief.entry(name)
    answer = (getattr(entry, "answer", None) or "").strip() if entry else ""
    if not answer:
        return "nothing yet, and it is a question required at stage shape"
    first = answer.split("\n", 1)[0].strip()
    return first if len(first) <= 200 else first[:197] + "..."


def _where_absence_is_declared(config: dict[str, Any]) -> str:
    """The nodes to put ``allow_unknown=False`` on, as the failure message names them."""
    answering = _answering_nodes(config)
    named = [str(node.get("node_id")) for node in answering if node.get("node_id")]
    if not named:
        return "the node producing the scored answer, which calls no model in this pipeline"
    return ", ".join(named)


def _absence_waived(results: dict[str, Any]) -> bool:
    """Whether every node producing the scored answer declared ``allow_unknown=False``.

    A step on the way to the answer may have an absent state of its own: a lookup that finds
    no review, a match that does not resolve. What FT-04 is about is the answer, so those are
    outside the declaration and were inside it until 2026-08-27.

    A pipeline of `Deterministic` nodes reaches no model on that path, waives nothing, and does
    not turn the check off.
    """
    answering = _answering_nodes(results.get("config") or {})
    return bool(answering) and all(node.get("allow_unknown") is False for node in answering)


def _answering_nodes(config: dict[str, Any]) -> list[dict[str, Any]]:
    """The model-calling nodes whose output is what an example is scored against.

    The pipeline's last unit, and where that is a pipeline used as a node, its last unit in
    turn. Where the last unit calls no model, the model-calling nodes that feed it, since a
    `Deterministic` step assembling an answer carries no declaration of its own.

    Empty where the answer is produced without a model call anywhere behind it, and where the
    results file holds no ``nodes``. A file whose entries record no ``successors`` reads as a
    graph of terminal nodes, so every one of them has to declare rather than none.
    """
    recorded = RecordedNodes(config)
    if not recorded.declared:
        return []
    reached = recorded.last_units()
    answering = [recorded.entries[n] for n in reached if _calls_a_model(recorded.entries.get(n))]
    return answering or recorded.feeding(reached)


# -- FT-06: point estimate with no interval -------------------------------------------------


def ft_06(ctx: Context) -> CheckResult:
    """Every metric reported carries an interval and its n, or says why it has none."""
    results, _ = ctx.results()
    read = _read(ctx, ctx.artifacts.results)
    if not isinstance(results, dict):
        return _blocked_on_results(ctx, "FT-06")

    entry = ctx.entry("FT-06")
    findings = [
        Finding(entry.id, entry.render(name=name))
        for name, metric in _reported_metrics(results)
        if not _carries_interval(metric)
    ]
    if findings:
        return _result(ctx, "FT-06", Outcome.FAILED, findings=tuple(findings), read=read)
    return _result(ctx, "FT-06", Outcome.PASSED, read=read)


def _result_nodes(results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The per-node section of a results file, keyed by node id, non-mappings skipped."""
    nodes = results.get("nodes")
    if not isinstance(nodes, dict):
        return {}
    return {str(node_id): node for node_id, node in nodes.items() if isinstance(node, dict)}


def _reported_metrics(results: dict[str, Any]) -> list[tuple[str, Any]]:
    """Every figure the file reports, keyed by the name a message would name.

    A project metric is one of these wherever it appears, so a project reporting its own number
    meets this check on the same terms as the six (docs/evaluation.md §11).
    """
    found: list[tuple[str, Any]] = []
    for name, metric in (results.get("metrics") or {}).items():
        found.append((str(name), metric))
    for node_id, node in _result_nodes(results).items():
        for rate in ("reach", "accuracy"):
            # `null` is a node reporting no such rate, which is not a rate without an
            # interval: a node no example labels reports no accuracy (docs/evaluation.md §5.2).
            if node.get(rate) is not None:
                found.append((f"{node_id}.{rate}", node[rate]))
        for name, metric in (node.get("metrics") or {}).items():
            found.append((f"{node_id}.{name}", metric))
    return found


def _carries_interval(metric: Any) -> bool:
    """Whether this figure is one FT-06 accepts: an interval, or a declared reason for none.

    A figure with no interval passes on a declared state rather than on the text of ``reason``:
    it reports no value at all, which an empty population does, or the project declared it
    un-estimated, which a count over one run is.
    """
    if not isinstance(metric, dict):
        return False
    interval = metric.get("interval")
    if isinstance(interval, dict):
        return interval.get("n") is not None
    if not str(metric.get("reason") or "").strip():
        return False
    # No value is the undefined case, which an empty population produces. A figure that does
    # report one passes only where the project declared it a census rather than an estimate.
    return metric.get("numerator") is None or metric.get("estimated") is False


# -- FT-07: seeds uncontrolled --------------------------------------------------------------


def ft_07(ctx: Context) -> CheckResult:
    """A seed on every rollout, and on every record that sampled."""
    results, _ = ctx.results()
    if not isinstance(results, dict):
        return _blocked_on_results(ctx, "FT-07")

    read = list(_read(ctx, ctx.artifacts.results))
    rollouts = results.get("rollouts") or []
    if any(not isinstance(r, dict) or r.get("seed") is None for r in rollouts):
        return _failure(ctx, "FT-07", tuple(read))

    for path in _rollout_trajectories(ctx, rollouts):
        records, reason = read_jsonl(path)
        if reason is not None:
            continue
        read.append(ctx.artifacts.relative(path) or str(path))
        if _unseeded(records):
            return _failure(ctx, "FT-07", tuple(read))
    return _result(ctx, "FT-07", Outcome.PASSED, read=tuple(read))


def _rollout_trajectories(ctx: Context, rollouts: list[Any]) -> list[Path]:
    """The trajectories the results file points at, and the latest run as a fallback.

    A results file records absolute paths, so a run directory that has since moved leaves
    them dangling. The ones that resolve are read and the rest are left alone. A relative
    path resolves against the project root, which is what a copied run directory holds.
    """
    found = [
        ctx.artifacts.root / str(r["trajectory"])
        for r in rollouts
        if isinstance(r, dict) and r.get("trajectory")
    ]
    resolved = [p for p in found if p.exists()]
    if resolved:
        return resolved
    if ctx.artifacts.run_dir is not None:
        fallback = ctx.artifacts.run_dir / "trajectory.jsonl"
        return [fallback] if fallback.exists() else []
    return []


def _unseeded(records: list[Any]) -> bool:
    """Whether any record that samples was written without the seed it sampled at.

    A `deterministic` node records `null` and passes: it does not sample, and the field is
    present so "no seed applies" stays distinguishable from "seed not recorded". A `tool_call`
    and a `consultation` carry no seed field at all.

    A node the run routed around records `null` too, and passes for the same reason: it did not
    execute, so it sampled nothing, and `termination` of `"skipped"` is what says so. Reading it
    as an unseeded node leaves a project two ways to pass, and the cheap one is to stop routing
    around the node.
    """
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("record_type") == "node_execution":
            if (
                record.get("node_kind") != "deterministic"
                and record.get("termination") != "skipped"
                and record.get("seed") is None
            ):
                return True
        elif record.get("record_type") == "model_call" and "seed" not in record:
            return True
    return False


# -- the registry ---------------------------------------------------------------------------


def _read(ctx: Context, path: Path | None) -> tuple[str, ...]:
    shown = ctx.artifacts.relative(path)
    return (shown,) if shown else ()


def entries_about_the_pipeline(brief: Brief) -> tuple[str, ...]:
    """The answered entries that describe the pipeline rather than what the builder wants.

    These are the ones that go stale on a change rather than at a gate, so FT-38 and the note
    the report prints before `ship` both read this list::

        due = entries_about_the_pipeline(ctx.brief)      # ('agency_boundary', 'budget', ...)
    """
    answered = {
        entry.name for entry in brief.entries if entry.status == "answered" and entry.answer
    }
    return tuple(
        question.name
        for question in QUESTIONS
        if question.about_the_pipeline and question.name in answered
    )


def current_fingerprint(artifacts: Artifacts) -> tuple[str | None, str | None]:
    """What the newest agent run was made by, or a reason nothing says.

    The manifest rather than the pipeline, because the suite reads artifacts and never imports
    the project's code. ``(stamp, None)`` where it is on disk, ``(None, reason)`` where it is
    not.
    """
    if artifacts.run_dir is None:
        return None, "No run directory under runs/. The pipeline is unrecorded (FT-13)."
    manifest, reason = read_json(artifacts.run_dir / "manifest.json")
    if reason is not None or not isinstance(manifest, dict):
        return None, "The newest run's manifest could not be read, which FT-13 reports."
    stamp = manifest.get("behaviour_fingerprint")
    if not isinstance(stamp, str) or not stamp:
        return None, (
            "The newest run's manifest carries no behaviour_fingerprint, so it was written "
            "before the field existed, and the pipeline it describes is unrecorded."
        )
    return stamp, None


# -- FT-37: the reported number came from a pipeline the project no longer has ----------------


def ft_37(ctx: Context) -> CheckResult:
    """The stamp on the results file against the stamp on the newest run.

    Fails from stage `ship` and is a note before it. A pipeline moves several times an hour
    while it is being built, and what clears this is another evaluation.
    """
    results, _ = ctx.results()
    read = _read(ctx, ctx.artifacts.results)
    if not isinstance(results, dict):
        return _blocked_on_results(ctx, "FT-37")

    measured = (results.get("config") or {}).get("behaviour_fingerprint")
    if not isinstance(measured, str) or not measured:
        return _result(
            ctx,
            "FT-37",
            Outcome.BLOCKED,
            read=read,
            detail=(
                "This results file records no behaviour_fingerprint, so it was written before "
                "the field existed and nothing joins the number to what produced it. "
                "suite.run() records it, and suite.rescore() copies it off the rollouts."
            ),
        )
    current, reason = current_fingerprint(ctx.artifacts)
    if current is None:
        return _result(ctx, "FT-37", Outcome.BLOCKED, read=read, detail=reason)
    if current == measured:
        return _result(ctx, "FT-37", Outcome.PASSED, read=read)
    return _failure(
        ctx,
        "FT-37",
        (*read, *_read(ctx, ctx.artifacts.run_dir / "manifest.json")),
        results=ctx.artifacts.relative(ctx.artifacts.results) or "the results file",
        measured=measured,
        current=current,
    )


# -- FT-38: the brief was never read against the code again -----------------------------------


def ft_38(ctx: Context) -> CheckResult:
    """Whether the entries describing the pipeline were read against it since it last moved.

    Reads whether the value was recorded, never whether anyone read the entries.
    """
    read = (ctx.artifacts.relative(ctx.brief.path) or "brief.toml",)
    due = entries_about_the_pipeline(ctx.brief)
    if not due:
        return _result(
            ctx,
            "FT-38",
            Outcome.PASSED,
            read=read,
            detail=(
                "No answered entry describes the pipeline, so nothing here goes stale when it "
                "moves."
            ),
        )
    current, reason = current_fingerprint(ctx.artifacts)
    if current is None:
        return _result(ctx, "FT-38", Outcome.BLOCKED, read=read, detail=reason)

    confirmed = ctx.brief.confirmed_against
    if confirmed == current:
        return _result(
            ctx,
            "FT-38",
            Outcome.PASSED,
            read=read,
            detail=f"{len(due)} entry(s) describing the pipeline, read against {current}.",
        )
    return _failure(
        ctx,
        "FT-38",
        (*read, *_read(ctx, ctx.artifacts.run_dir / "manifest.json")),
        confirmed=confirmed or "nothing recorded",
        current=current,
        due=", ".join(due),
    )


def _blocked_on_results(ctx: Context, entry_id: str) -> CheckResult:
    return _result(
        ctx,
        entry_id,
        Outcome.BLOCKED,
        detail="No readable evaluation results, which FT-01 reports.",
    )


# -- FT-39: an unanswered comment ---------------------------------------------------------


def ft_39(ctx: Context) -> CheckResult:
    """Open comments are reported at every gate, and refuse it where the brief says so."""
    from ..records.comments import DEFAULT_COMMENTS, read_comments
    from ..errors import ConfigurationError

    path = ctx.artifacts.root / DEFAULT_COMMENTS
    read = _read(ctx, path if path.exists() else None) + _read(ctx, ctx.brief.path)
    try:
        comments = read_comments(path)
    except ConfigurationError as error:
        return _failure(ctx, "FT-39", read, reason=str(error))
    if comments.path is None:
        return _result(
            ctx,
            "FT-39",
            Outcome.PASSED,
            read=read,
            detail="No comments.toml; the builder has not commented on anything.",
        )
    held = comments.open
    if not held:
        return _result(
            ctx,
            "FT-39",
            Outcome.PASSED,
            read=read,
            detail=f"Every one of the {len(comments.all)} comment(s) is addressed.",
        )
    named = ", ".join(f"{c.at!r}: {c.said[:60]!r}" for c in held[:4]) + (
        f", and {len(held) - 4} more" if len(held) > 4 else ""
    )
    if ctx.brief.comments_block_gates:
        return _failure(
            ctx,
            "FT-39",
            read,
            reason=f"{len(held)} open: {named}",
        )
    return _result(
        ctx,
        "FT-39",
        Outcome.PASSED,
        read=read,
        detail=(
            f"{len(held)} open comment(s), reported and not blocking: {named}. "
            f"`comments_block_gates = true` in the brief makes them refuse the gate."
        ),
    )


# -- FT-40: a step that was declared and never built ------------------------------------------


def _planned_from_the_manifest(ctx: Context) -> tuple[list[str], tuple[str, ...], str | None]:
    """The steps the newest run recorded as planned, for a project whose code was not read.

    A manifest only ever holds the steps of the pipeline that ran, so this is the narrower
    answer and is used where the code could not be imported.
    """
    if ctx.artifacts.run_dir is None:
        return [], (), "no run to read a manifest from either"
    manifest, reason = read_json(ctx.artifacts.run_dir / "manifest.json")
    read = (f"{ctx.artifacts.relative(ctx.artifacts.run_dir)}/manifest.json",)
    if reason is not None or not isinstance(manifest, dict):
        return [], read, "the newest run's manifest could not be read either, which FT-13 reports"
    return RecordedNodes(manifest).planned(), read, None


def ft_40(ctx: Context) -> CheckResult:
    """Every step still standing in as `NotBuilt`: expected at `shape`, a failure at `ship`.

    Read from ``agent.py`` where the code imports, since that is where a step is declared and
    a project at `shape` has no run to record one. A project whose code could not be imported
    falls back to the newest run's manifest and says which it read.
    """
    declared = ctx.declared
    if declared is not None and declared.imported:
        planned, read, unreadable = list(declared.planned), ("agent.py",), None
    else:
        planned, read, unreadable = _planned_from_the_manifest(ctx)
        if unreadable is not None:
            why = declared.problem if declared is not None else "the code was not read"
            unreadable = f"{why}, and {unreadable}"
    if unreadable is not None:
        if not (ctx.artifacts.root / "agent.py").exists():
            return _result(
                ctx,
                "FT-40",
                Outcome.PASSED,
                detail="No agent.py, so no step is declared in code yet.",
            )
        # `str.capitalize` lowercases the rest, which turns FT-13 into ft-13.
        return _result(
            ctx,
            "FT-40",
            Outcome.BLOCKED,
            read=read,
            detail=unreadable[0].upper() + unreadable[1:] + ".",
        )
    if not planned:
        return _result(ctx, "FT-40", Outcome.PASSED, read=read)
    named = ", ".join(planned)
    if ctx.stage() == "ship":
        return _failure(ctx, "FT-40", read, count=str(len(planned)), list=named)
    counted = f"{len(planned)} step(s) declared and not built: {named}."
    return _result(
        ctx,
        "FT-40",
        Outcome.PASSED,
        read=read,
        detail=(
            f"{counted} That is what `shape` produces; each is drawn dashed in the view "
            f"with what it will do."
            if ctx.stage() == "shape"
            else f"{counted} This fails from stage `ship`."
        ),
    )


# -- FT-41: a run stopped to ask, and nothing continued it -------------------------------------


@dataclass(frozen=True, slots=True)
class Resumptions:
    """What the runs under one directory did about stopping, over every manifest there.

    ``stopped`` is how many carry a suspension at all, ``open_`` how many carry one with no
    ``resumed_at``, and ``resumed`` how many recorded one. A run counts under both of the last
    two where it stopped twice and continued once.
    """

    read: int = 0
    stopped: int = 0
    open_: int = 0
    resumed: int = 0


def _resumptions(run_dir: Path) -> Resumptions:
    """Read every manifest under ``run_dir`` for what it says about stopping and continuing.

    Every run, whatever role or pipeline it declares: a labelling pass that stopped to ask a
    person is a run that stopped, and a project resuming one of those has written the half
    this check is looking for.
    """
    if not run_dir.is_dir():
        return Resumptions()
    read = stopped = open_ = resumed = 0
    for handle in runs(run_dir, nested=True):
        read += 1
        entries = handle.manifest.get("suspensions")
        if not isinstance(entries, list) or not entries:
            continue
        stopped += 1
        closed = [bool(e.get("resumed_at")) for e in entries if isinstance(e, dict)]
        open_ += not all(closed)
        resumed += any(closed)
    return Resumptions(read=read, stopped=stopped, open_=open_, resumed=resumed)


def ft_41(ctx: Context) -> CheckResult:
    """A run that stopped and is still waiting, where nothing this project made was resumed.

    Counted at every stage and a failure from `ship`, on FT-40's pattern: a run waiting on an
    answer is ordinary while a project is being built, and a project that has never continued
    one has the half that continues it unwritten.
    """
    where = ctx.artifacts.root / DEFAULT_RUNS
    found = _resumptions(where)
    read = (f"{DEFAULT_RUNS}/",)
    if found.read == 0:
        return _result(
            ctx,
            "FT-41",
            Outcome.PASSED,
            detail=f"No run under {DEFAULT_RUNS}/ yet, so nothing has stopped.",
        )
    if not found.stopped:
        return _result(
            ctx,
            "FT-41",
            Outcome.PASSED,
            read=read,
            detail=(
                f"None of the {found.read:,} run(s) under {DEFAULT_RUNS}/ stopped to ask "
                f"anything. A channel returning `Shelved` or `Unavailable` never stops one."
            ),
        )
    counted = (
        f"{found.stopped:,} of {found.read:,} run(s) under {DEFAULT_RUNS}/ stopped to ask "
        f"something: {found.open_:,} still waiting, {found.resumed:,} continued."
    )
    if found.open_ and not found.resumed:
        if ctx.stage() == "ship":
            return _failure(ctx, "FT-41", read, count=f"{found.open_:,}")
        return _result(
            ctx,
            "FT-41",
            Outcome.PASSED,
            read=read,
            detail=f"{counted} `Pipeline.resume` is what continues one. This fails from "
            f"stage `ship`.",
        )
    return _result(ctx, "FT-41", Outcome.PASSED, read=read, detail=counted)


# -- FT-43: the MCP server changed under the project -------------------------------------------


def _newest_manifest(ctx: Context) -> tuple[dict[str, Any] | None, tuple[str, ...], str | None]:
    """The newest agent run's manifest, or a reason there is none to read."""
    if ctx.artifacts.run_dir is None:
        return None, (), "No run directory under runs/, so no manifest is readable (FT-13)."
    path = ctx.artifacts.run_dir / "manifest.json"
    manifest, reason = read_json(path)
    read = _read(ctx, path)
    if reason is not None or not isinstance(manifest, dict):
        return None, read, f"{reason or 'the manifest is not an object'}."
    return manifest, read, None


def _servers_read(servers: list[dict[str, Any]]) -> str:
    """What a passing FT-43 says about the servers it read."""
    replayed = [one for one in servers if one.get("read") == "replayed"]
    if not replayed:
        return f"{len(servers)} MCP server(s) read, and none had moved."
    return (
        f"{len(servers)} MCP server(s) declared, {len(replayed)} of them served from the "
        f"recording. A replayed run reaches no server, so it has nothing to compare."
    )


def ft_43(ctx: Context) -> CheckResult:
    """No MCP server the newest run declared tools from has moved since it was recorded.

    Reads the `drift` a live run recorded against the listing already on file. A replayed run
    records none, because it is being served the recording rather than compared against it.
    """
    manifest, read, reason = _newest_manifest(ctx)
    if manifest is None:
        outcome = Outcome.PASSED if not read else Outcome.BLOCKED
        return _result(ctx, "FT-43", outcome, read=read, detail=reason)
    servers = [one for one in (manifest.get("mcp") or []) if isinstance(one, dict)]
    if not servers:
        return _result(
            ctx,
            "FT-43",
            Outcome.PASSED,
            read=read,
            detail="This run declared tools from no MCP server.",
        )
    moved = [one for one in servers if one.get("drift")]
    if not moved:
        return _result(ctx, "FT-43", Outcome.PASSED, read=read, detail=_servers_read(servers))
    spelt = ", ".join(
        f"{one.get('tool')} ({one.get('difference')})" for one in (moved[0].get("drift") or [])
    )
    return _failure(ctx, "FT-43", read, server=str(moved[0].get("server")), list=spelt)


# -- FT-42: a decision names something the project never built ---------------------------------


def _named_under_produces(ctx: Context) -> dict[str, list[str]]:
    """Every name a settled decision records under ``produces``, against the decisions naming it.

    A ``not_applicable`` decision is a project saying it has no decision of that kind, so a
    ``produces`` on one names nothing to look for.
    """
    named: dict[str, list[str]] = {}
    for decision in ctx.brief.decisions:
        if decision.status == "not_applicable":
            continue
        for name in decision.produces:
            named.setdefault(name, []).append(decision.name)
    return named


def _only_a_constant_names(ctx: Context) -> set[str]:
    """The names under `produces` that no decision but a `constant` one records.

    Manifests carry `constants` from format `0.33`, so a project whose runs all predate it has
    none to join against, and every name that can only be a constant would read as a name the
    project never built. Those are left out and the pass says so.
    """
    by_kind: dict[str, set[str]] = {}
    for decision in ctx.brief.decisions:
        if decision.status == "not_applicable":
            continue
        for name in decision.produces:
            by_kind.setdefault(name, set()).add(decision.kind)
    return {name for name, kinds in by_kind.items() if kinds == {"constant"}}


def ft_42(ctx: Context) -> CheckResult:
    """Every name under `produces` against what the runs recorded: reported, a failure at `ship`.

    Read across every run rather than the newest, since a project with more than one pipeline
    runs whichever it was asked for and the newest describes one of them.
    """
    named = _named_under_produces(ctx)
    read = (ctx.artifacts.relative(ctx.brief.path) or "brief.toml", f"{DEFAULT_RUNS}/")
    if not named:
        return _result(
            ctx,
            "FT-42",
            Outcome.PASSED,
            detail=(
                "No decision names what it became. `produces` on a dependency, shape, "
                "constant or prompt_rule decision names the tools, nodes or numbers it "
                "produced, and this check reads those against what the runs recorded."
            ),
        )
    if not ctx.produced.runs_read:
        return _result(
            ctx,
            "FT-42",
            Outcome.BLOCKED,
            read=read,
            detail=(
                f"{len(named)} name(s) are recorded under `produces` and no run under "
                f"{DEFAULT_RUNS}/ has a role of `agent`, so there is nothing to read them "
                f"against. FT-13 reports the same absence."
            ),
        )

    every = ctx.produced.every_name()
    unread = set() if ctx.produced.constants_recorded else _only_a_constant_names(ctx)
    aside = (
        f" {len(unread)} name(s) only a `constant` decision records are left out: manifests "
        f"carry constants from format 0.33 and every run under {DEFAULT_RUNS}/ predates it."
        if unread
        else ""
    )
    missing = sorted(name for name in named if name not in every and name not in unread)
    if not missing:
        return _result(
            ctx,
            "FT-42",
            Outcome.PASSED,
            read=read,
            detail=(
                f"{len(named) - len(unread)} name(s) under `produces` were all recorded by "
                f"runs under {DEFAULT_RUNS}/.{aside}"
            ),
        )
    spelt = ", ".join(f"{name} ({', '.join(named[name])})" for name in missing)
    if ctx.stage() == "ship":
        return _failure(ctx, "FT-42", read, count=str(len(missing)), list=spelt)
    return _result(
        ctx,
        "FT-42",
        Outcome.PASSED,
        read=read,
        detail=(
            f"{len(missing)} of {len(named)} name(s) under `produces` were recorded by no run "
            f"of this project: {spelt}. A decision is agreed before the code exists, which is "
            f"what `build` is for. This fails from stage `ship`.{aside}"
        ),
    )


CHECKS: tuple[tuple[str, Callable[[Context], CheckResult]], ...] = (
    ("FT-13", ft_13),
    ("FT-14", ft_14),
    ("FT-15", ft_15),
    ("FT-24", ft_24),
    ("FT-29", ft_29),
    ("FT-30", ft_30),
    ("FT-31", ft_31),
    ("FT-25", ft_25),
    ("FT-32", ft_32),
    ("FT-33", ft_33),
    ("FT-34", ft_34),
    ("FT-35", ft_35),
    ("FT-36", ft_36),
    ("FT-01", ft_01),
    ("FT-02", ft_02),
    ("FT-03", ft_03),
    ("FT-04", ft_04),
    ("FT-06", ft_06),
    ("FT-07", ft_07),
    ("FT-37", ft_37),
    ("FT-38", ft_38),
    ("FT-39", ft_39),
    ("FT-40", ft_40),
    ("FT-41", ft_41),
    ("FT-42", ft_42),
    ("FT-43", ft_43),
)
