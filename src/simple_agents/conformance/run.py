"""Running the checks over one project, and deciding which of them apply.

A gate fires only when the project claims the tier it belongs to or higher, so the brief is
read first and the tier decides which checks run at all. One entry also names a stage, and its
check waits until the project has reached it. A check that does not apply is reported rather
than dropped, so a project sees what it is not being held to.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..envelope import EVAL_BUCKET
from .artifacts import DEFAULT_RUNS, Artifacts, read_json
from .brief import Brief
from .checks import (
    CHECKS,
    Context,
    DeclaredPipelines,
    current_fingerprint,
    entries_about_the_pipeline,
)
from .elicitation import QUESTIONS
from .produced import Produced, produced_across
from .report import CheckResult, Outcome, Report
from .spend import Scope, UnfinishedAcross, unfinished_across
from .stages import STAGES, stages_for
from .taxonomy import Entry, Taxonomy, Tier, taxonomy

__all__ = ["run_checks"]

# How many node ids a note names before it counts the rest. Long enough to recognise a
# pipeline by, short enough to stay one wrapped line.
_NODES_NAMED = 4


def run_checks(
    root: str | Path = ".",
    *,
    brief: str | Path | None = None,
    run_dir: str | Path | None = None,
    results: str | Path | None = None,
    entries: Taxonomy | None = None,
    scope: Scope | None = None,
) -> Report:
    """Run the conformance suite over a project directory.

    ::

        from simple_agents.conformance import run_checks

        report = run_checks("~/projects/inseam-agent")
        report.ok                # False when any check failed
        print(report.text())

    Looks for ``brief.toml``, the most recent run under ``runs/``, and the most recent
    results file under ``evals/results/``. Pass ``brief``, ``run_dir`` or ``results`` to read
    somewhere else. Raises ``ConfigurationError`` when the brief is missing or declares no
    tier, since nothing can tell which gates apply without one.

    ``scope`` narrows the runs FT-35 reads, which is the one check that reads more than the
    newest run. It reaches no other check::

        run_checks(".", scope=Scope(since="2026-08-14"))
    """
    root = Path(root).expanduser()
    found = Artifacts.discover(
        root,
        brief=Path(brief).expanduser() if brief else None,
        run_dir=Path(run_dir).expanduser() if run_dir else None,
        results=Path(results).expanduser() if results else None,
    )
    declared = Brief.read(found.brief or root / "brief.toml")
    ctx = Context(
        artifacts=found,
        brief=declared,
        taxonomy=entries or taxonomy(),
        unfinished=unfinished_across(root / DEFAULT_RUNS, scope or Scope()),
        produced=produced_across(root / DEFAULT_RUNS),
        declared=_pipelines_in_the_code(root),
    )

    stage = ctx.stage()

    checks: list[CheckResult] = []
    for entry_id, check in CHECKS:
        entry = ctx.taxonomy[entry_id]
        skipped = _not_applicable(entry, declared.tier, stage)
        if skipped is not None:
            checks.append(
                CheckResult(
                    entry_id=entry.id,
                    name=entry.name,
                    tier=str(entry.tier),
                    outcome=Outcome.NOT_APPLICABLE,
                    detail=skipped,
                )
            )
            continue
        checks.append(check(ctx))

    return Report(
        root=str(root),
        tier=str(declared.tier),
        brief=found.relative(declared.path),
        checks=tuple(checks),
        reading=_what_the_checks_read(found),
        notes=tuple(
            note
            for note in (
                found.different_evaluations(),
                found.reading_a_live_run(),
                _what_the_live_runs_did(found, stage),
                _stages_the_tier_drops(declared.tier, found),
                _the_pipeline_moved(declared, found, stage),
                _the_number_came_from_elsewhere(found, stage),
                _rollouts_the_results_file_does_not_describe(found),
                _answers_no_decision_rests_on(declared, stage),
                _dependencies_no_research_rests_under(declared, stage),
                _produced_by_no_decision(declared, ctx.produced, stage),
                _spend_that_produced_nothing(ctx.unfinished),
                _no_step_carries_a_figure(declared, found, ctx.produced, stage),
            )
            if note
        ),
    )


def _what_the_checks_read(found: Artifacts) -> str | None:
    """Which pipeline the run-reading checks read, named by its nodes, for the report's header.

    Each check names the path it opened, and a path does not say what was in it. A project
    whose corpus build, labelling pass or batch script goes through the envelope with no
    ``role`` writes those runs beside the agent's, and the newest of them is what every
    run-reading check then reads. Naming the nodes is what makes that visible: `write_summary
    → keep_summaries` under a recommender's conformance report is not the recommender.

    The library cannot tell a batch pass from the agent, which is what
    ``RunEnvelope(role=...)`` is for (`docs/run-envelope.md` §2.1).
    """
    if found.run_dir is None:
        return None
    manifest, reason = read_json(found.run_dir / "manifest.json")
    if reason is not None or not isinstance(manifest, dict):
        return None
    nodes = [
        str(node.get("node_id"))
        for node in (manifest.get("nodes") or [])
        if isinstance(node, dict) and node.get("node_id")
    ]
    if not nodes:
        return None
    shape = " → ".join(nodes[:_NODES_NAMED])
    if len(nodes) > _NODES_NAMED:
        shape += f" and {len(nodes) - _NODES_NAMED} more"
    return (
        f"reading {found.relative(found.run_dir)}, {len(nodes)} node(s): {shape}. A pass the "
        f"project makes for itself declares RunEnvelope(role=...) so it is not read as the "
        f"agent (docs/run-envelope.md §2.1)."
    )


def _what_the_live_runs_did(found: Artifacts, stage: str) -> str | None:
    """What the runs an end user made were, on a project that has shipped.

    Every check but FT-31 reads a run that is not live, and a shipped project accumulates both.
    A live run is the end user's material and may be sampled down to no payloads, so it is not
    what the suite certifies; it is also the only artifact the project produces after the last
    gate, so a report that never mentions one leaves that road unnamed.

    It reports and never fails.
    """
    if stage != "ship" or found.live_run is None or found.run_dir == found.live_run:
        return None
    when = _text_in(found.live_run / "manifest.json", "started_at")
    started = f", started {when}" if when else ""
    return (
        f"The newest run an end user made is {found.relative(found.live_run)}{started}, and "
        f"the checks above read {found.relative(found.run_dir)}, which is a run made while "
        f"building. Live runs are what this project does now, and they are not certified here: "
        f"a live run carries the end user's material and can be sampled down to no payloads. "
        f'FT-31 reads one, and `runs("runs/", live=True)` reads them all.'
    )


def _the_number_came_from_elsewhere(found: Artifacts, stage: str) -> str | None:
    """FT-37 before the project has reached `ship`, where that check does not fire yet.

    The same comparison, reported rather than failed. A pipeline moves several times an hour
    while it is being built, and what clears the failure is another evaluation, so the gate
    waits for `ship` and this covers the ground until then.
    """
    if stage == "ship" or found.results is None or found.run_dir is None:
        return None
    measured = _text_in(found.results, "config", "behaviour_fingerprint")
    current, _ = current_fingerprint(found)
    if measured is None or current is None or current == measured:
        return None
    return (
        f"The number in {found.relative(found.results)} was measured over "
        f"{measured}, and the newest run under runs/ was made by {current}. A prompt, a node's "
        f"version, a sampling parameter, a tool, the model or a budget has moved since that "
        f"file was written. FT-37 fails on this from stage ship; until then it is reported, "
        f"because what clears it is another evaluation."
    )


def _no_step_carries_a_figure(
    brief: Brief, found: Artifacts, produced: Produced, stage: str
) -> str | None:
    """FT-08, as a note: every figure this project reports is end to end.

    FT-08's shipped text rules out a failure, and the library computes per-node metrics out of
    the trajectories with no project effort, so the entry passes on a project that localised
    nothing. What it is about is whether a number that drops names a step, and three things
    answer that: a node an example labels, a figure declared for a node, and a rung evaluated
    on its own.

    Each has to be current. A slice run is evidence while the pipeline it was taken of is the
    pipeline the project has, which is the comparison FT-37 makes about the results file.
    Where FT-37 already reports the evidence stale this says nothing, because that is one
    finding and printing it twice reads as two.
    """
    if stage == "shape" or not Tier(str(brief.tier)).covers(Tier("evaluated")):
        return None
    if found.results is None or found.run_dir is None:
        return None
    if _the_number_came_from_elsewhere(found, stage) is not None:
        return None
    results, reason = read_json(found.results)
    if reason is not None or not isinstance(results, dict):
        return None

    nodes = results.get("nodes")
    nodes = nodes if isinstance(nodes, dict) else {}
    if any((one or {}).get("accuracy") for one in nodes.values() if isinstance(one, dict)):
        return None
    if (results.get("config") or {}).get("node_metrics"):
        return None
    if _text_in(found.run_dir / "manifest.json", "graph_fingerprint") in produced.sliced_from:
        return None
    if not nodes:
        return None
    return (
        f"Every figure in {found.relative(found.results)} is end to end. {len(nodes)} node(s) "
        f"ran and none carries a figure of its own: no example labels a node through "
        f"expected_by_node, node_metrics declares nothing, and no run under runs/ was made by "
        f"a slice of this pipeline. A number that drops names no step, which leaves bisecting "
        f"by hand through prompt edits (FT-08). Three things answer it, and any one is enough: "
        f"label a step with Example.expected_by_node and EvalSuite(node_matches=...), declare "
        f"a figure for a step with EvalSuite(node_metrics=...), or score a step on its own "
        f"with pipeline.slice(start=...) (`docs/evaluation.md` §5.6)."
    )


def _text_in(path: Path, *at: str) -> str | None:
    """The value a JSON file records at ``at``, where it is a non-empty string.

    ``None`` covers every way it can be absent: the file does not parse, a key on the way is
    missing, or what is there is not a string. Each of those is reported by the check that owns
    the artifact, so a note reading two files says nothing rather than saying it twice.
    """
    value: object
    value, reason = read_json(path)
    if reason is not None:
        return None
    for key in at:
        value = value.get(key) if isinstance(value, dict) else None
    return value if isinstance(value, str) and value else None


def _rollouts_the_results_file_does_not_describe(found: Artifacts) -> str | None:
    """Where the evaluation directory a results file names no longer holds its rollouts.

    Joined by the evaluation's identity rather than by the paths in the file. An evaluation's
    directory is named for its identity (`docs/evaluation.md` §6), and a project that was
    copied or moved has every recorded path pointing at the tree it was run in.

    Two things separate. The directory is missing, so the file describes rollouts that are not
    on disk. Or a rollout in it started after the file was written, which is a re-run into a
    directory that was cleared: the seeds match, the totals do not, and nothing else says so.

    **A file written by ``rescore`` is not read.** Its identity is the rescoring
    configuration's and names no directory: the rollouts it scored are wherever the caller
    pointed it, which the file records only as a path per rollout. ``config.scored_from`` is
    what separates the two, and reading a rescored file here would tell the reader to
    re-score a directory that never existed.
    """
    if found.results is None:
        return None
    results, reason = read_json(found.results)
    if reason is not None or not isinstance(results, dict):
        return None
    if (results.get("config") or {}).get("scored_from") != "rollouts":
        return None
    eval_id = results.get("eval_id")
    if not isinstance(eval_id, str) or not eval_id:
        return None
    # An evaluation is filed under runs/eval/, and a project that ran one before the layout
    # settled wrote it directly under runs/. Both are read.
    directory = found.root / DEFAULT_RUNS / EVAL_BUCKET / eval_id
    if not directory.is_dir():
        directory = found.root / DEFAULT_RUNS / eval_id
    where = f"{DEFAULT_RUNS}/{directory.parent.name}/{eval_id}/".replace(
        f"{DEFAULT_RUNS}/{DEFAULT_RUNS}/", f"{DEFAULT_RUNS}/"
    )
    if not directory.is_dir():
        return (
            f"{found.relative(found.results)} reports an evaluation whose rollouts are not on "
            f"disk: {where} does not exist. The figures in the file stand; what cannot be "
            f're-read is the trajectory behind any of them. suite.rescore("{where}") is '
            f"what re-scores rollouts that are still there."
        )
    written = results.get("created_at")
    if not isinstance(written, str) or not written:
        return None
    return _rollouts_written_after(found, directory, where, written)


def _rollouts_written_after(
    found: Artifacts, directory: Path, where: str, written: str
) -> str | None:
    """The rollouts in ``directory`` that began after the results file was written, if any.

    An evaluation re-run into a directory that was cleared writes under the same identity, so
    when each rollout started is what separates the two.
    """
    later = sorted(
        rollout.name
        for rollout in directory.iterdir()
        if rollout.is_dir() and _started_after(rollout / "manifest.json", written)
    )
    if not later:
        return None
    rest = f" and {len(later) - 3} more" if len(later) > 3 else ""
    return (
        f"{where} holds {len(later)} rollout(s) that started after "
        f"{found.relative(found.results)} was written at {written}, so the file does not "
        f"describe them: {', '.join(later[:3])}{rest}. An evaluation re-run into the same "
        f"directory writes under the same identity, and the seeds match while the figures are "
        f"of the earlier rollouts. Re-score against what is there, or point the brief's "
        f"`results` key at the file that describes it."
    )


def _started_after(manifest_path: Path, written: str) -> bool:
    """Whether the run this manifest describes began after ``written``.

    Parsed rather than compared as text. Both are written by ``utc_now()`` at millisecond
    precision, so a comparison of the strings would be right for every file the library
    writes; one written at second precision sorts after the same instant with milliseconds,
    because `Z` is above `.`. A stamp nothing can parse is not reported.
    """
    manifest, reason = read_json(manifest_path)
    if reason is not None or not isinstance(manifest, dict):
        return False
    started = manifest.get("started_at")
    if not isinstance(started, str) or not started:
        return False
    try:
        return datetime.fromisoformat(started.replace("Z", "+00:00")) > datetime.fromisoformat(
            written.replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return False


def _the_pipeline_moved(brief: Brief, found: Artifacts, stage: str) -> str | None:
    """The entries due for re-reading, where the pipeline has moved under them.

    Every gate fires when a project reaches a point. What makes a brief entry wrong is a
    change, so nothing is looking when it happens: the answer is still `answered`, the code
    beneath it is not what it describes, and the next gate is however far away it is. This
    reads the run's `behaviour_fingerprint` against the one the brief was confirmed at.

    Addressed to the coding agent, and it names entries rather than quoting answers: an answer
    can be a paragraph, and a truncated quote is something to act on without opening the file.

    It reports and never fails **until stage `ship`, where FT-38 fails on the same comparison**
    and this stops so the report does not carry it twice. A graph moves several times an hour
    while a project is built, which is why the gate waits.
    """
    if stage == "ship":
        return None
    current, _ = current_fingerprint(found)
    if current is None:
        return None

    due = ", ".join(entries_about_the_pipeline(brief))
    if not due:
        return None
    if brief.confirmed_against is None:
        return (
            f"The brief does not record what its entries were last read against. An entry goes "
            f"stale when the pipeline changes rather than when a gate is reached, so nothing "
            f"reports it. Read these against the code and record "
            f'confirmed_against = "{current}" in the brief: {due}.'
        )
    if brief.confirmed_against == current:
        return None
    return (
        f"The pipeline has moved since the brief was confirmed at "
        f"{brief.confirmed_against}, and the run at {found.relative(found.run_dir)} recorded "
        f"{current}. These entries describe the pipeline and are due for re-reading against "
        f"the code, and so is design.md; correct what has gone stale, then record "
        f'confirmed_against = "{current}": {due}.'
    )


def _spend_that_produced_nothing(found: UnfinishedAcross) -> str | None:
    """What the runs bought nothing with, per node, where any of them did.

    An `AgentNode` produces its output from a `finish` call, so an execution that stopped on a
    budget axis returns `None` to the node after it, and the run completes recording no error.
    FT-35 gates on the subset that never acted, which has no benign reading; this reports the
    rest, because a cap that binds after real work is the cap doing its job and the library
    cannot tell which of the two a project has.

    Addressed to the coding agent. It reports and never fails.
    """
    # A node whose every such unit is one FT-35 already named is left out: that message
    # carries the same two figures, and printing them twice reads as two findings.
    nodes = {
        node_id: counts
        for node_id, counts in found.produced_nothing().items()
        if node_id in found.waived
        or counts["executions"] + counts["items"] > counts["without_tool_calls"]
    }
    if not nodes:
        return None
    named = "; ".join(
        f"{node_id} {_units(counts)}, spending {counts['model_calls']:,} model call(s)"
        for node_id, counts in nodes.items()
    )
    return (
        f"Over {found.covered()}, these produced no output and spent to do it: {named}. An "
        f"execution that ends on a budget axis returns None to the node after it and the run "
        f"completes, so no other figure reports it. `simple-agents report runs/` prints what "
        f"every node spent, beside what it produced."
    )


def _units(counts: dict[str, int]) -> str:
    """How many executions and fan-out items ended without an output, naming both units."""
    parts = []
    if counts["executions"]:
        parts.append(f"{counts['executions']:,} execution(s)")
    if counts["items"]:
        parts.append(f"{counts['items']:,} fan-out item(s)")
    return " and ".join(parts)


def _answers_no_decision_rests_on(brief: Brief, stage: str) -> str | None:
    """The answers about what the builder wants that no design decision claims to rest on.

    A decision names what it was derived from under `from`, and this is the complement. The
    list itself catches nothing, because it is read by whoever wrote it; what a reader has no
    way to miss is the answer that appears in none of them.

    One project is the case. `finished_version` said the system owns the reader's shelves and
    ratings; `not_building` said the interface was out of scope until the schema settled. The
    shape rested on the second, the first was never read against it, and two days of building
    followed. Both were recorded, both were the builder's own words, and nothing put them side
    by side.

    Addressed to the coding agent. A `from` entry naming nothing in the brief is reported
    beside it, since a name that resolves to nothing is a decision resting on a typo.
    """
    if STAGES.index(stage) < STAGES.index("shape"):
        return None
    # `not_applicable` is a project saying it has no decision of that kind, and a complement
    # over nothing is every answer the brief holds.
    shaping = [
        d
        for d in brief.decisions
        if d.kind in ("shape", "presentation") and d.status != "not_applicable"
    ]
    if not shaping:
        return None

    named = {name for decision in shaping for name in decision.rests_on}
    answered = {
        entry.name for entry in brief.entries if entry.status == "answered" and entry.answer
    }
    unread = [
        question.name
        for question in QUESTIONS
        if question.about_what_is_wanted
        and question.name in answered
        and question.name not in named
    ]
    unknown = sorted(name for name in named if name not in {e.name for e in brief.entries})
    if not unread and not unknown:
        return None

    parts = []
    if unread:
        parts.append(
            f"Answers about what the builder wants that no shape or presentation decision "
            f"rests on: {', '.join(unread)}. Read each against what is being built. Where one "
            f"does not bear on the shape, say so in the decision that supersedes it; where it "
            f"does, name it under `from`."
        )
    if unknown:
        parts.append(
            f"A decision's `from` names {', '.join(unknown)}, which the brief has no entry "
            f"for. Name the entries the decision was derived from, or correct the spelling."
        )
    return " ".join(parts)


# The entries a `dependency` decision draws its options from. Naming one says the alternatives
# were gathered rather than recalled.
RESEARCH_ENTRIES = frozenset({"approaches", "available_material"})


def _dependencies_no_research_rests_under(brief: Brief, stage: str) -> str | None:
    """The dependency decisions whose `from` names no research entry.

    The complement of the note above, over the other half of the surface. One project recorded
    four `dependency` decisions weighing thirteen alternatives between them, and all thirteen
    were variants of two catalogues the project already had. The four sources that came from
    outside went through no decision at all.

    Addressed to the coding agent, and it reports rather than failing: a project whose options
    genuinely were all in the room says so in `research.md` and names it here.
    """
    if STAGES.index(stage) < STAGES.index("shape"):
        return None
    if not any(entry.name in RESEARCH_ENTRIES for entry in brief.entries):
        return None
    adrift = [
        decision.name
        for decision in brief.decisions
        if decision.kind == "dependency"
        and decision.status != "not_applicable"
        and not (set(decision.rests_on) & RESEARCH_ENTRIES)
    ]
    if not adrift:
        return None
    return (
        f"Dependency decisions resting on no research: {', '.join(adrift)}. What each weighed "
        f"under `considered` is the option set, and `research.md` is where it was widened. "
        f"Read each against the survey, and name {' or '.join(sorted(RESEARCH_ENTRIES))} under "
        f"`from` where it bears on the choice. Where the alternatives came from somewhere the "
        f"research did not reach, say so under `because`."
    )


# How many names the note spells out per kind before it counts the rest. Long enough to act on
# without opening the brief, short enough that three kinds stay readable together.
_PRODUCED_NAMED = 12


def _produced_by_no_decision(brief: Brief, produced: Produced, stage: str) -> str | None:
    """What the project's runs recorded that no decision names, per kind, with what is stale.

    The complement of FT-42, over the same two sides. A decision names what it became under
    `produces` and this is everything the runs hold that no decision named: a tool that ran, a
    step that ran, a number the code defines.

    One project is the case for the first. Five tools ran that the brief never named, one of them
    holding all four candidate sources the builder had to prompt for, and eleven checks passed
    over 3,293 manifests. Another is the case for the third: 51 of its 56 module-level
    numbers appeared in no decision, and its own roadmap recorded four chosen in one session
    "by the coding agent alone and named in no document".

    **It reports and never fails.** Which of a project's numbers change what the agent does and
    which are a source's published rate limit is a judgement, and a gate over all of them would
    be cleared by naming them rather than by reading them.

    Each name carries the day of the newest run that recorded it, shown where that is earlier
    than the day of the newest run read, so a step the project removed reads as removed.
    Addressed to the coding agent.
    """
    if STAGES.index(stage) < STAGES.index("shape") or not produced.runs_read:
        return None
    named = {
        name
        for decision in brief.decisions
        if decision.status != "not_applicable"
        for name in decision.produces
    }
    parts = [
        found
        for word, held in produced.by_kind()
        if (found := _unnamed_of_one_kind(word, held, named, produced.newest_day))
    ]
    # Manifests carry `constants` from format 0.33. Saying nothing where none of the runs read
    # carried one would read as a project whose code defines no number. A project with no run
    # at all is out above: it has nothing for either direction to read.
    if not produced.constants_recorded:
        parts.append(
            "Constants: unread. Manifests record them from format 0.33 and every run under "
            f"{DEFAULT_RUNS}/ predates it. Run the pipeline once and they are recorded."
        )
    if not parts:
        return None
    return " ".join(
        [
            "What the runs recorded that no decision names, which `produces` on a dependency, "
            "shape, constant or prompt_rule decision records:",
            *parts,
            "A name that is gone goes under `produces` on the decision that removed it, "
            "recorded `changed`.",
        ]
    )


def _unnamed_of_one_kind(
    word: str, held: dict[str, str], named: set[str], newest_day: str
) -> str | None:
    """One kind's sentence: how many no decision names, which, and which were last seen earlier."""
    unnamed = sorted(
        (name for name in held if name not in named),
        key=lambda name: (held[name] < newest_day, name),
    )
    if not unnamed:
        return None
    shown = [
        name if held[name] >= newest_day else f"{name} (last seen {held[name]})"
        for name in unnamed[:_PRODUCED_NAMED]
    ]
    rest = f" and {len(unnamed) - _PRODUCED_NAMED} more" if len(unnamed) > _PRODUCED_NAMED else ""
    stale = sum(1 for name in unnamed if held[name] < newest_day)
    trailing = f" {stale} of them were last seen before {newest_day}." if stale else ""
    return f"{len(unnamed)} of {len(held)} {word}(s): {', '.join(shown)}{rest}.{trailing}"


def _pipelines_in_the_code(root: Path) -> DeclaredPipelines:
    """The project's own pipelines, for FT-40, which asks what the code declares.

    Importing a project is what `simple-agents view` does and what no other check does. It is
    guarded here rather than trusted: a project whose `agent.py` raises still gets its report,
    and the one check that reads this falls back to the manifest and says which it used.
    """
    if not (root / "agent.py").exists():
        return DeclaredPipelines(problem="no agent.py, so no pipeline is declared in code")
    try:
        from ..view.discovery import load_project

        loaded = load_project(root)
    except Exception as error:  # noqa: BLE001 - a project that will not import still reports
        return DeclaredPipelines(problem=f"agent.py could not be imported: {error}")
    if not loaded.imported or not loaded.pipelines:
        # An `agent.py` that imports and declares nothing the convention can find has told
        # this check nothing. Saying `pass` off it would cite a reading that never happened,
        # so the manifest answers instead.
        return DeclaredPipelines(
            problem="; ".join(loaded.problems)
            or "agent.py declares no pipeline a @pipeline_factory or a module-level "
            "Pipeline makes findable"
        )
    many = len(loaded.pipelines) > 1
    planned = tuple(
        f"{name}/{step}" if many else step
        for name, pipeline in loaded.pipelines.items()
        for step in _planned_in(pipeline)
    )
    surfaces = tuple(str(surface.name) for surface in getattr(loaded.product, "surfaces", ()) or ())
    return DeclaredPipelines(planned=planned, imported=True, surfaces=surfaces)


def _planned_in(pipeline: object, prefix: str = "") -> list[str]:
    """Every step standing in as `NotBuilt`, named the way the view addresses it.

    A pipeline used as a node names its own steps under its `node_id`, so one step has one
    name across the check and the page rather than two.
    """
    from ..pipeline import Pipeline

    found: list[str] = []
    for node in getattr(pipeline, "nodes", ()) or ():
        node_id = str(getattr(node, "node_id", ""))
        if isinstance(node, Pipeline):
            found.extend(_planned_in(node, f"{prefix}{node_id}."))
        elif getattr(node, "planned", False):
            found.append(f"{prefix}{node_id}")
    return found


def _not_applicable(entry: Entry, tier: Tier, stage: str) -> str | None:
    """Why this entry's check does not run here, or ``None`` where it does.

    A tier below the entry's is one reason and is the usual one. A stage the project has not
    reached is the other, and applies to an entry that names one.
    """
    if not tier.covers(entry.tier):
        return f"Fires at tier {entry.tier}, and this project claims {tier}."
    if entry.stage is not None and STAGES.index(stage) < STAGES.index(entry.stage):
        return f"Fires at stage {entry.stage}, and this project is at {stage}."
    return None


def _stages_the_tier_drops(tier: Tier, found: Artifacts) -> str | None:
    """A note where the tier holds a project to fewer questions than its artifacts show.

    A project with a results file has done the work of ``measure``, and at tier ``prototype``
    that stage is not part of its road, so the questions of it are not required. What the
    project produced and what it is asked are then different things, and the report says so.
    """
    if found.results is None or "measure" in stages_for(tier):
        return None
    return (
        f"This project has a results file and claims tier {str(tier)!r}, whose stages are "
        f"{', '.join(stages_for(tier))}. The questions of `measure` are not required of it and "
        f"the checks that read a results file do not fire. A project reporting a number about "
        f'how well it works declares tier = "evaluated".'
    )
