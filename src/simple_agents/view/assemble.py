"""Everything the page shows, computed from the project. Nothing here is asserted by hand.

The output is plain data: the template renders it, and the tests read it directly, so what
the page says is testable without a browser. Every sentence is written for the builder and
the coding agent; nothing in it explains the library to a maintainer.

`cards.py` draws what the code declares, `runs_overlay.py` and `evaluation.py` say what
happened when it ran, and `findings.py` turns the join into sentences. This module joins
them and is what a caller reaches for.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..records.comments import DEFAULT_COMMENTS, read_comments
from ..errors import ConfigurationError
from .cards import _pipeline_card, _resources
from .checks import read_checks
from .claims import read_claims, read_seams
from .constants import across_the_runs, read_constants, read_prompt_rules
from .product import read_product
from .prompts import read_prompts
from .discovery import load_project
from .evaluation import read_evaluation
from .elicitation import read_idea, read_stages
from .examples import read_examples
from .operating import read_operating
from .research import read_research
from .findings import _findings, _ledger, _standing
from .measured import _attach_measurements
from .record import read_record
from .runs_overlay import live_run, read_runs, rollout_runs
from ..envelope import runs
from .walk import walkable_runs
from .words import _clip


def _brief_data(root: Path, problems: list[str]) -> Any:
    from ..conformance.brief import Brief

    path = root / "brief.toml"
    if not path.exists():
        return None
    try:
        return Brief.read(path)
    except ConfigurationError as error:
        problems.append(f"brief.toml could not be read: {error}")
        return None


# The kinds whose `produces` names steps. A `dependency` names tools and a `constant` names
# numbers, so neither joins to a step by that field.
_NAMES_STEPS = ("shape", "prompt_rule")


def _joins_to(decision: Any, node_id: str, short: str) -> bool | None:
    """How this decision reaches this step: ``True`` exactly, ``False`` by its wording, or
    ``None`` where it does not reach it at all."""
    produces = tuple(getattr(decision, "produces", ()) or ())
    if produces and getattr(decision, "kind", None) in _NAMES_STEPS:
        return True if short in produces or node_id in produces else None
    haystack = " ".join(str(getattr(decision, key, "") or "") for key in ("chose", "because"))
    return False if re.search(rf"\b{re.escape(short)}\b", haystack) else None


def _join_decisions(pipelines: list[dict[str, Any]], brief: Any) -> dict[str, Any]:
    """Which recorded decision talks about which step.

    Read from ``produces`` where the decision records one, which names the step exactly. A
    decision that records none falls back to its prose naming the step, and a step agreed to in
    other words then reads as unagreed. Every card that shows this join says which it used.
    """
    decisions = list(getattr(brief, "decisions", ()) or ())
    claimed: set[str] = set()
    for pipeline in pipelines:
        for node in pipeline["nodes"]:
            short = node["id"].rsplit(".", 1)[-1]
            found = []
            for decision in decisions:
                exact = _joins_to(decision, node["id"], short)
                if exact is None:
                    continue
                found.append(
                    {
                        "name": decision.name,
                        "kind": getattr(decision, "kind", None),
                        "status": getattr(decision, "status", None),
                        "chose": str(getattr(decision, "chose", "") or ""),
                        "exact": exact,
                    }
                )
                claimed.add(decision.name)
            node["decisions"] = found
    return {
        "total": len(decisions),
        "naming_no_step": sorted({d.name for d in decisions} - claimed),
        "changed": sorted(d.name for d in decisions if str(getattr(d, "status", "")) == "changed"),
    }


def _closest_shape(
    pipeline: dict[str, Any], unclaimed: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """The recorded shape this pipeline most likely used to be, or ``None``.

    Matched by how many step names the two share, at half or better, which is what attaches a
    history to a pipeline whose code has moved since it last ran.
    """
    ids = {n["id"] for n in pipeline["nodes"]}
    scored = []
    for group in unclaimed:
        theirs = set((group.get("newest") or {}).get("nodes", {}))
        if not theirs:
            theirs = set(group["signature"].split(" → "))
        overlap = len(ids & theirs) / max(len(ids | theirs), 1)
        if overlap >= 0.5:
            scored.append((overlap, group))
    return max(scored, key=lambda pair: pair[0])[1] if scored else None


def _give_the_history(pipeline: dict[str, Any], chosen: dict[str, Any], moved: bool) -> None:
    """Hang one recorded shape's figures on the pipeline, and its values on each step."""
    pipeline["runs"] = {k: v for k, v in chosen.items() if k != "key"}
    pipeline["runs"]["code_moved_since"] = moved
    newest = (chosen.get("newest") or {}).get("nodes", {})
    asked: dict[str, list[dict[str, Any]]] = {}
    for question in (chosen.get("newest") or {}).get("questions") or []:
        asked.setdefault(question["asked_by"], []).append(question)
    for node in pipeline["nodes"]:
        node["ran"] = newest.get(node["id"])
        node["example"] = (node["ran"] or {}).get("example")
        node["asked"] = asked.get(node["id"], [])
    # The path is drawn from what the code declares and cannot know how much moved until a
    # run is attached, so it is filled here rather than where the rows are made.
    volumes = {n["id"]: n["example"] for n in pipeline["nodes"] if n["example"]}
    for row in pipeline.get("data_path") or []:
        held = volumes.get(row["id"])
        if held:
            row["took_in_volume"] = held.get("took_in_volume")
            row["handed_on_volume"] = held.get("handed_on_volume")


def _resolve_edge(pipeline: dict[str, Any], source: str, target: str) -> str | None:
    """One recorded edge as the drawing names it, or ``None`` where the drawing has no such edge.

    The record names what the graph declared: a local id inside a nested pipeline, and the
    container's own id on the edge into it. The drawing enters a container at its first step,
    so the two are joined here rather than at either end.
    """
    by_id = {n["id"]: n for n in pipeline["nodes"]}
    node = by_id.get(source)
    if node is None:
        return None
    full = f"{node['prefix']}{target}"
    full = pipeline.get("entry_of", {}).get(full, full)
    full = pipeline.get("entry_of", {}).get(target, full)
    return full if full in by_id else None


def _one_population(pipeline: dict[str, Any], held: dict[str, Any] | None, where: str) -> None:
    """Hang one population's figures on a pipeline: per step, per edge, per store."""
    if held is None:
        pipeline[where] = None
        return
    pipeline[where] = {
        "runs": held["runs"],
        "bases": held["bases"],
        "unreadable": held["unreadable"],
        "edges": {},
        "nodes": {},
    }
    for node in pipeline["nodes"]:
        found = held["nodes"].get(node["id"])
        if found is not None:
            pipeline[where]["nodes"][node["id"]] = found
    for edge in held["edges"]:
        target = _resolve_edge(pipeline, edge["from"], edge["to"])
        if target is not None:
            pipeline[where]["edges"][f"{edge['from']}->{target}"] = edge["runs"]
    pipeline[where]["accesses"] = held["accesses"]
    pipeline[where]["access_counts"] = held["access_counts"]
    pipeline[where]["tool_calls"] = held["tool_calls"]
    pipeline[where]["tool_call_counts"] = held["tool_call_counts"]


def _held_for(pipeline: dict[str, Any], record: dict[str, Any]) -> dict[str, Any] | None:
    """This pipeline's figures, including where the code has moved since its last run.

    The run overlay already resolved which recorded shape a moved pipeline used to be, so the
    same choice is followed here rather than made again: a pipeline whose fingerprint no longer
    matches would otherwise lose every figure at the moment its history matters most.
    """
    was = (pipeline.get("runs") or {}).get("fingerprint")
    return (
        record.get(pipeline.get("fingerprint") or "")
        or record.get(f"signature:{pipeline.get('signature')}")
        or (record.get(was) if was else None)
    )


def _attach_the_record(pipelines: list[dict[str, Any]], record: dict[str, dict[str, Any]]) -> None:
    """Hang both populations' figures on each pipeline, counted apart.

    A project's own runs say where real work goes; an evaluation's rollouts say where the
    measurement went. Adding them would report neither, so the page carries both and names
    which it is showing.
    """
    for pipeline in pipelines:
        _one_population(pipeline, _held_for(pipeline, record["runs"]), "over_runs")
        _one_population(pipeline, _held_for(pipeline, record["rollouts"]), "over_rollouts")
        for node in pipeline["nodes"]:
            node["over_the_record"] = (pipeline["over_runs"] or {}).get("nodes", {}).get(node["id"])


def _confirmations(pipelines: list[dict[str, Any]], brief: Any) -> None:
    """Whether each pipeline is still the shape the builder was last shown."""
    for pipeline in pipelines:
        agreed = brief.confirmed_shape(pipeline["name"]) if brief is not None else None
        pipeline["confirmed_shape"] = agreed
        pipeline["shape_moved"] = None if agreed is None else agreed != pipeline["fingerprint"]


def _mark_what_moved(pipeline: dict[str, Any]) -> None:
    """Say per step what changed since this pipeline last ran, for the drawing to show."""
    runs = pipeline.get("runs")
    then = ((runs or {}).get("newest") or {}).get("nodes") or {}
    for node in pipeline["nodes"]:
        node["changed"] = None
        if not then:
            continue
        was = then.get(node["id"])
        if was is None:
            node["changed"] = "new"
        elif was.get("planned") and not node["planned"]:
            node["changed"] = "built"
        elif was.get("kind") != node["kind"]:
            node["changed"] = "kind"


def _retired(group: dict[str, Any]) -> dict[str, Any]:
    """A shape the record holds and the code does not, as a pipeline card of its own."""
    names = group["signature"].split(" → ")
    return {
        "name": names[0] + (" → …" if len(names) > 1 else ""),
        "origin": "runs",
        "fingerprint": group["fingerprint"],
        "signature": group["signature"],
        "nodes": [],
        "status": "no longer in the code",
        "runs": {k: v for k, v in group.items() if k != "key"},
    }


def _attach_runs(
    pipelines: list[dict[str, Any]], groups: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Give each declared pipeline its history, and keep the shapes only the record has.

    Exact fingerprint match first. Where the code has moved since the last run the
    fingerprints differ, so the closest earlier shape is matched by how many step names the
    two share, and the difference becomes the "what changed" ledger.
    """
    unclaimed = list(groups)
    for pipeline in pipelines:
        exact = [g for g in unclaimed if g["fingerprint"] == pipeline["fingerprint"]]
        chosen, moved = (exact[0], False) if exact else (_closest_shape(pipeline, unclaimed), True)
        if chosen is None:
            continue
        unclaimed.remove(chosen)
        _give_the_history(pipeline, chosen, moved)
    return [_retired(group) for group in unclaimed]


def _title(name: str) -> str:
    """One brief key named for the builder, which is what a page shows in place of it."""
    from .claims import title_of

    return title_of(name)


def _asks(name: str) -> str | None:
    """The question itself, for an entry the library asked. Absent for one it did not."""
    from .claims import ask_of

    ask = ask_of(name)
    return _clip(ask, 180) if ask else None


def _questions_due(brief: Any, stage: str | None, comments: list[dict]) -> list[dict[str, Any]]:
    if brief is None or stage is None:
        return []
    from ..conformance.elicitation import required_at
    from ..conformance.stages import STAGES

    pending = {
        c["at"].removeprefix("question:")
        for c in comments
        if c["kind"] == "answer" and c["status"] == "open" and c["at"].startswith("question:")
    }
    due = []
    for question in required_at(stage, brief.tier):
        entry = brief.entry(question.name)
        if entry is None or entry.status == "unanswered":
            due.append(
                {
                    "name": question.name,
                    "title": question.title,
                    "asks": _clip(question.ask.split("\n")[0], 180),
                    "stage": question.stage,
                    "pending": question.name in pending,
                }
            )
        elif entry.status == "deferred" and entry.deferred_to:
            if STAGES.index(entry.deferred_to) <= STAGES.index(stage):
                due.append(
                    {
                        "name": question.name,
                        "title": question.title,
                        "asks": f"Deferred to {entry.deferred_to}, and the project is there now.",
                        "stage": question.stage,
                        "pending": question.name in pending,
                    }
                )
    return due


def _brief_panels(brief: Any) -> dict[str, list[dict[str, Any]]]:
    """The whole brief, legible: every question's answer and every decision.

    Each entry carries the question in the builder's words as well as the key it is recorded
    under, since a page headed `agency_boundary` names the library's vocabulary and not the
    project's. A decision is named by the project, so its key is made readable and no more.
    """
    if brief is None:
        return {"entries": [], "decisions": []}
    entries = [
        {
            "name": e.name,
            "title": _title(e.name),
            "asks": _asks(e.name),
            "status": e.status,
            "answer": str(getattr(e, "answer", "") or ""),
            "deferred_to": getattr(e, "deferred_to", None),
            "stage": _stage_of_entry(e),
        }
        for e in getattr(brief, "entries", ()) or ()
    ]
    decisions = [
        {
            "name": d.name,
            "title": _title(d.name),
            "kind": getattr(d, "kind", None),
            "status": getattr(d, "status", None),
            "chose": str(getattr(d, "chose", "") or ""),
            "because": str(getattr(d, "because", "") or ""),
        }
        for d in getattr(brief, "decisions", ()) or ()
    ]
    return {"entries": entries, "decisions": decisions}


def _stages_for_tier(brief: Any) -> tuple[str, ...]:
    """The stage pages this project has, from the tier it claims.

    A tier without `measure` has no measure page; a project with no brief is held to all
    six, the way the checks hold it.
    """
    from ..conformance.stages import stages_for

    return stages_for(getattr(brief, "tier", None) if brief is not None else None)


def _stage_of_entry(entry: Any) -> str | None:
    """The stage a brief entry belongs to, which is where its page files it.

    The stage the library asks the question at; for an entry the library never asked,
    the stage the project recorded asking it at (`asked_at`), or none.
    """
    from .claims import stage_of

    return stage_of(entry.name) or getattr(entry, "asked_at", None)


def _project_name(root: Path) -> str:
    """The project's own name, where its idea names one, or its directory otherwise."""
    idea = root / "idea.md"
    if idea.exists():
        try:
            for line in idea.read_text(encoding="utf-8").splitlines():
                if line.startswith("# ") and line[2:].strip():
                    return line[2:].strip()
        except OSError:
            pass
    return root.name


def _project_intent(brief: Any) -> dict[str, str | None]:
    """The builder's account of what this project is for, for the top of the page.

    The graph explains how a project works. Its opening needs the builder's reason for
    making it, or the rest of the picture becomes architecture without an outcome.
    """

    def answer(name: str) -> str | None:
        if brief is None:
            return None
        entry = brief.entry(name)
        if entry is None or getattr(entry, "status", None) != "answered":
            return None
        value = str(getattr(entry, "answer", "") or "").strip()
        return value or None

    return {
        "purpose": answer("purpose") or answer("what_it_does") or answer("smallest_worthwhile"),
        "for_whom": answer("end_user"),
        "outcome": answer("finished_version"),
        "surface": answer("used_through"),
    }


def _volume_moved(then: dict[str, Any], now: dict[str, Any], node_id: str) -> list[str]:
    """What one step produced in the newest run against the run before it."""
    was = (then.get("example") or {}).get("handed_on_volume")
    became = (now.get("example") or {}).get("handed_on_volume")
    if was and became and was != became:
        return [f"{node_id} produced {became}; the previous run produced {was}."]
    return []


def _time_moved(then: dict[str, Any], now: dict[str, Any], node_id: str) -> list[str]:
    """A step whose time moved by half again or better, over a fifth of a second."""
    before, after = then.get("ms") or 0.0, now.get("ms") or 0.0
    if after < 200 and before < 200:
        return []
    if before and (after > before * 1.5 or after * 1.5 < before):
        word = "slower" if after > before else "faster"
        return [f"{node_id} took {after:,.0f} ms, {word} than the {before:,.0f} ms before it."]
    return []


def _between_runs(pipeline: dict[str, Any]) -> list[str]:
    """What changed between this pipeline's newest run and the one before it.

    The change ledger says what moved in the code. This says what moved in the data, which is
    the half a builder cannot read off a diff.
    """
    runs = pipeline.get("runs") or {}
    newest, previous = runs.get("newest"), runs.get("previous")
    if not newest or not previous or newest["run"] == previous["run"]:
        return []
    lines: list[str] = []
    then, now = previous["nodes"], newest["nodes"]
    for node_id in sorted(set(now) & set(then)):
        lines += _volume_moved(then[node_id], now[node_id], node_id)
        lines += _time_moved(then[node_id], now[node_id], node_id)
        ran_then = bool(then[node_id].get("executions"))
        ran_now = bool(now[node_id].get("executions"))
        if ran_then != ran_now:
            lines.append(
                f"{node_id} {'ran' if ran_now else 'was not reached'} this time, and "
                f"{'was not reached' if ran_then else 'ran'} in the run before."
            )
    if previous.get("outcome") != newest.get("outcome"):
        lines.append(
            f"The run ended {newest.get('outcome')}, and the one before it ended "
            f"{previous.get('outcome')}."
        )
    return lines


def _every_question(pipelines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every question the newest run of each shape put to a person, with where it was asked."""
    asked = []
    for pipeline in pipelines:
        for question in ((pipeline.get("runs") or {}).get("newest") or {}).get("questions") or []:
            asked.append(
                {
                    **question,
                    "pipeline": pipeline.get("name") or pipeline.get("signature"),
                    "run": pipeline["runs"]["newest"]["run"],
                }
            )
    return asked


_EFFECT_DIRECTION = {
    "read_only": "read",
    "writes": "write",
    "irreversible": "write",
    "spends_money": "either way",
}


def _reached_in(
    over: dict[str, Any], card: dict[str, Any], pipeline: str
) -> tuple[list[dict[str, Any]], int]:
    """Every access to one store in one population, and how many there were in all."""
    found: list[dict[str, Any]] = []
    counted = (over.get("access_counts") or {}).get(card["name"], 0)
    for one in (over.get("accesses") or {}).get(card["name"]) or []:
        found.append({**one, "pipeline": pipeline, "how": "its own code"})
    for tool in card.get("through") or []:
        name = tool["name"]
        for one in (over.get("tool_calls") or {}).get(name) or []:
            found.append(
                {
                    **one,
                    "pipeline": pipeline,
                    "how": name,
                    "direction": _EFFECT_DIRECTION.get(str(tool["effect"]), "either way"),
                }
            )
        counted += (over.get("tool_call_counts") or {}).get(name, 0)
    return found, counted


def _give_resources_the_record(
    resources: list[dict[str, Any]], pipelines: list[dict[str, Any]]
) -> None:
    """Every access the record holds for each store, whichever way the step reached it.

    Two things count as an access and the card shows them together: a tool call, where the
    tool declares the resource it touches, and what a step's own code reported through
    ``ctx.record_access``. Both hold what was asked for and what came back, so a store's
    history reads the same whichever way a project happened to write the step.

    An evaluation's rollouts reach the real store too, and are counted apart: they are
    measurement traffic, and folding them in would overstate what the agent does.

    ``flow`` is the same counts split by pipeline, which is one end of every link the system
    level draws.
    """
    for card in resources:
        found: list[dict[str, Any]] = []
        counted = measuring = 0
        flow: dict[str, dict[str, int]] = {}
        for pipeline in pipelines:
            mine, count = _reached_in(pipeline.get("over_runs") or {}, card, pipeline["name"])
            found += mine
            counted += count
            _theirs, over_rollouts = _reached_in(
                pipeline.get("over_rollouts") or {}, card, pipeline["name"]
            )
            measuring += over_rollouts
            if count or over_rollouts:
                flow[pipeline["name"]] = {"runs": count, "rollouts": over_rollouts}
        card["accesses"] = found
        card["access_count"] = counted
        card["access_count_measuring"] = measuring
        # One entry per pipeline that reached this store, which is what the system level
        # draws its links from. `accesses` holds the project's own runs only, so a link
        # drawn over the evaluation has no row there to count.
        card["flow"] = flow
        _direction_from_the_record(card)


def _direction_from_the_record(card: dict[str, Any]) -> None:
    """Let a recorded access say which way a step's own `touches=` went.

    `touches=` carries no direction, so a step that plainly writes a store was drawn
    undirected. An access says `read` or `write`, so where one exists the record answers what
    the declaration never did, and the step moves to the side it recorded.
    """
    said: dict[str, set[str]] = {}
    for one in card["accesses"]:
        if one["how"] != "its own code" or one["direction"] not in ("read", "write"):
            continue
        said.setdefault(f"{one['pipeline']}/{one['node_id']}", set()).add(one["direction"])
    if not said:
        return
    for where, ways in said.items():
        if where not in card["unknown"]:
            continue
        if "read" in ways:
            card["readers"] = sorted({*card["readers"], where})
        if "write" in ways:
            card["writers"] = sorted({*card["writers"], where})
        card["unknown"] = [one for one in card["unknown"] if one != where]
        card["undeclared"] = [one for one in card["undeclared"] if one != where]
    card["direction_from_runs"] = sorted(said)


def _workspace(root: Path) -> dict[str, Any] | None:
    """What the newest run wrote into its own directory, which nothing on the page read.

    Every run gets one inside its own directory. A pipeline that produces a file produces it
    there, and a page that says nothing about it is missing what the run made.

    The newest run of the project's own agent is the one read, by what its manifest says it
    started at. An evaluation's rollouts each have a workspace too, and a seeded rollout's
    output is not what the project produced.
    """
    root_runs = root / "runs"
    if not root_runs.is_dir():
        return None
    newest = next(
        (
            handle.path / "workspace"
            # Every run wrote a workspace, whatever answered its model.
            for handle in runs(root_runs, scripted=None)
            if (handle.path / "workspace").is_dir()
        ),
        None,
    )
    if newest is None:
        return None
    files = sorted(
        (path for path in newest.rglob("*") if path.is_file()),
        key=lambda path: path.name,
    )
    return {
        "run": newest.parent.name,
        "files": [
            {"name": str(path.relative_to(newest)), "bytes": path.stat().st_size}
            for path in files[:40]
        ],
        "total": len(files),
        "bytes": sum(path.stat().st_size for path in files),
    }


def _comment_rows(root: Path, problems: list[str]) -> list[dict[str, Any]]:
    """Every thread as the page reads it, or an empty list and a problem to show."""
    try:
        held = read_comments(root / DEFAULT_COMMENTS)
    except ConfigurationError as error:
        problems.append(str(error))
        return []
    return [
        {
            "id": c.id,
            "at": c.at,
            "by": c.by,
            "kind": c.kind,
            "said": c.said,
            "about": c.about,
            "quoted": c.quoted,
            "quoted_chars": c.quoted_chars,
            "run": c.run,
            "instruction": c.instruction,
            "when": c.when,
            "status": c.status,
            "addressed_by": c.addressed_by,
            "addressed_when": c.addressed_when,
            "replies": [{"by": r.by, "said": r.said, "when": r.when} for r in c.replies],
        }
        for c in held.all
    ]


def _running_now(root: Path, pipelines: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The run moving right now, named for the pipeline it is moving through."""
    moving = live_run(root)
    if moving is None:
        return None
    match = next(
        (
            p
            for p in pipelines
            if p["origin"] == "declared" and p["fingerprint"] == moving["fingerprint"]
        ),
        None,
    )
    moving["pipeline"] = match["name"] if match else None
    return moving


def assemble(root: str | Path) -> dict[str, Any]:
    """Read one project and produce everything the page shows.

    ::

        data = assemble("~/projects/inseam-agent")
        data["standing"]                  # one sentence: where the project is
        data["findings"]                  # what needs eyes, most urgent first
        data["pipelines"][0]["nodes"]     # every declared fact about each step
    """
    root = Path(root).expanduser()
    problems: list[str] = []

    loaded = load_project(root)
    problems.extend(loaded.problems)
    brief = _brief_data(root, problems)
    comments = _comment_rows(root, problems)

    pipelines = [_pipeline_card(name, p) for name, p in loaded.pipelines.items()]
    pipelines += _attach_runs(pipelines, read_runs(root))
    declared = [p for p in pipelines if p["origin"] == "declared"]
    _attach_the_record(declared, read_record(root))
    _confirmations(declared, brief)
    for pipeline in declared:
        _mark_what_moved(pipeline)

    stage = getattr(brief, "stage", None)
    data = _first_pass(root, loaded, brief, comments, problems, pipelines, declared, stage)
    _second_pass(root, data, brief, declared, loaded)
    return data


def _first_pass(
    root: Path,
    loaded: Any,
    brief: Any,
    comments: list[dict[str, Any]],
    problems: list[str],
    pipelines: list[dict[str, Any]],
    declared: list[dict[str, Any]],
    stage: str | None,
) -> dict[str, Any]:
    """Everything the page shows that is read rather than joined."""
    return {
        "project": _project_name(root),
        "intent": _project_intent(brief),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "stage": stage,
        "tier": str(brief.tier) if brief is not None else None,
        "stages": list(_stages_for_tier(brief)),
        "code_imported": loaded.imported,
        "code_error": loaded.could_not_import,
        "problems": problems,
        "pipelines": pipelines,
        "resources": _resources(declared),
        "workspace": _workspace(root),
        "comments": comments,
        "running": _running_now(root, pipelines),
        "rollouts": rollout_runs(root),
        "questions_due": _questions_due(brief, stage, comments),
        "brief": _brief_panels(brief),
        "measured": read_evaluation(root),
        "checks": read_checks(root),
        "stages_asked": read_stages(brief),
        "idea": read_idea(root, brief),
        "research": read_research(root, brief),
        "operating": read_operating(root),
        "walks": None,
        "examples": read_examples(root),
        "decisions_join": _join_decisions(declared, brief)
        if brief is not None
        else {"total": 0, "naming_no_step": [], "changed": []},
    }


def _second_pass(
    root: Path, data: dict[str, Any], brief: Any, declared: list[dict[str, Any]], loaded: Any
) -> None:
    """The joins between what was read, and the sentences built from them."""
    # The runs a builder opens: the newest of each shape, and the rollouts whose examples
    # came out wrong, which is where "walk the run that went wrong" starts.
    wrong = [
        one["trajectory"].rsplit("/", 1)[0]
        for one in ((data["measured"] or {}).get("went_wrong") or [])
        if one.get("trajectory")
    ]
    data["walks"] = walkable_runs(root, wrong)
    _give_resources_the_record(data["resources"], declared)
    data["ledgers"] = {p["name"]: lines for p in declared if (lines := _ledger(p))}
    data["coverage"] = _attach_measurements(declared, data["measured"])
    data["claims"] = read_claims(declared, brief, data["coverage"], data["measured"])
    data["seams"] = read_seams(declared, brief, data["claims"])
    data["product"] = read_product(root, loaded, declared, data["resources"])
    # One reading of the newest manifests, shared by the three things that read them.
    across = across_the_runs(root)
    data["constants"] = read_constants(root, declared, brief, across)
    data["prompt_rules"] = read_prompt_rules(root, declared, brief, across)
    data["prompts"] = read_prompts(root, declared, brief, across[1])
    data["moved"] = {p["name"]: lines for p in declared if (lines := _between_runs(p))}
    data["asked"] = _every_question(data["pipelines"])
    data["findings"] = _findings(data)
    data["standing"] = _standing(data)
