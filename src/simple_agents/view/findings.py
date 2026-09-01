"""The sentences the page leads with, and the one that says where the project stands.

Each is computed from the data the rest of the package assembles, so every sentence on the
page is a value a test can read. The reader is the builder: what a finding says is what it
means for their project, in their words.
"""

from __future__ import annotations

from typing import Any

from .cards import _KIND_WORDS
from .measured import _measure_findings
from .words import _clip, _rate, fmt_runs


def _ledger(pipeline: dict[str, Any]) -> list[str]:
    """What changed in one pipeline since its last run, as plain sentences."""
    runs = pipeline.get("runs")
    if not runs or not runs.get("newest"):
        return []
    then = runs["newest"]["nodes"]
    now = {n["id"]: n for n in pipeline["nodes"]}
    lines = []
    for node_id in sorted(set(now) - set(then)):
        word = "planned" if now[node_id]["planned"] else "built"
        lines.append(f"{node_id} is new since the last run ({word}).")
    for node_id in sorted(set(then) - set(now)):
        lines.append(f"{node_id} was in the last run and is gone from the code.")
    for node_id in sorted(set(now) & set(then)):
        was, isnow = then[node_id], now[node_id]
        if was.get("planned") and not isnow["planned"]:
            lines.append(f"{node_id} was a placeholder and is now built.")
        elif was.get("kind") != isnow["kind"]:
            lines.append(
                f"{node_id} changed from {_KIND_WORDS.get(was.get('kind'), was.get('kind'))} "
                f"to {isnow['kind_word']}."
            )
    return lines


def _changed_since_it_ran(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A pipeline whose code moved since the run that measured it."""
    found: list[dict[str, Any]] = []
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    changed = [(p["name"], _ledger(p)) for p in declared]
    changed = [(name, lines) for name, lines in changed if lines]
    for name, lines in changed:
        found.append(
            {
                "severity": "attention",
                "head": f"{name} has changed since it last ran.",
                "body": " ".join(lines[:3])
                + (f" And {len(lines) - 3} more." if len(lines) > 3 else ""),
                "target": {"pipeline": name},
            }
        )
    return found


def _address_name(data: dict[str, Any], address: str) -> str:
    """One comment's address named for a reader, which for a brief key is the question."""
    from .claims import title_of

    for prefix in ("question:", "decision:"):
        if address.startswith(prefix):
            return title_of(address[len(prefix) :])
    return address


def _last_word(comment: dict[str, Any]) -> str:
    """Who spoke last on a thread: the opener where nothing has been replied."""
    replies = comment.get("replies") or []
    return str((replies[-1].get("by") if replies else comment.get("by")) or "builder")


def _thread_target(comment: dict[str, Any]) -> dict[str, Any]:
    """Where a thread is read: the step it is on where it is on one, else the conversation."""
    at = str(comment.get("at") or "")
    if "/" in at and not at.startswith(("question:", "decision:", "resource:")):
        pipeline, _, node = at.partition("/")
        if "->" not in node:
            return {"pipeline": pipeline, "node": node}
    return {"section": "conversation"}


def _open_threads(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Open comment threads, split by whose turn it is.

    A thread the coding agent answered last waits on the builder to read it. One the builder
    spoke on last, which includes every sentence a one-click sent, is with the coding agent
    and is listed as worth knowing.
    """
    found: list[dict[str, Any]] = []
    open_comments = [c for c in data["comments"] if c["status"] == "open" and c["kind"] != "answer"]
    to_read = [c for c in open_comments if _last_word(c) != "builder"]
    with_agent = [c for c in open_comments if _last_word(c) == "builder"]
    if to_read:
        found.append(
            {
                "severity": "attention",
                "waits": "Read the thread",
                "head": (
                    "Your coding agent has answered one of your comments."
                    if len(to_read) == 1
                    else f"Your coding agent has answered {len(to_read)} of your comments."
                ),
                "body": " ".join(
                    f"On {_address_name(data, c['at'])}: “{_clip(c['said'])}”" for c in to_read[:2]
                ),
                "target": _thread_target(to_read[0]),
            }
        )
    if with_agent:
        found.append(
            {
                "severity": "note",
                "head": (
                    "One of your comments is with your coding agent."
                    if len(with_agent) == 1
                    else f"{len(with_agent)} of your comments are with your coding agent."
                ),
                "body": " ".join(
                    f"On {_address_name(data, c['at'])}: “{_clip(c['said'])}”"
                    for c in with_agent[:2]
                )
                + " Nothing here waits on you until it answers.",
                "target": _thread_target(with_agent[0]),
            }
        )
    return found


def _by_stage_words(here: list[dict], earlier: list[dict]) -> str:
    """How the unanswered questions split between this stage and the ones before it."""
    if here and earlier:
        return (
            f" {len(here)} of them this stage asks and {len(earlier)} "
            f"{'was' if len(earlier) == 1 else 'were'} asked at an earlier stage."
        )
    if earlier:
        return (
            " Every one was asked at an earlier stage."
            if len(earlier) > 1
            else " It was asked at an earlier stage."
        )
    return ""


def _already_sent_words(sent: int) -> str:
    """The answers typed on the page that the coding agent has not recorded yet."""
    if sent == 1:
        return " One more already has an answer with the coding agent."
    return f" {sent} more already have answers with the coding agent." if sent else ""


def _the_code_would_not_import(data: dict[str, Any]) -> list[dict[str, Any]]:
    """`agent.py` raised on import, so every step, seam and figure on the page is missing.

    Nothing else the page says about the code can be trusted while this stands, so it goes
    first among the findings.
    """
    error = data.get("code_error")
    if not error:
        return []
    return [
        {
            "severity": "attention",
            "waits": "See what it says",
            "head": "agent.py could not be imported.",
            "body": f"{error}. The page is drawing the run record alone: the steps, the "
            f"seams and every figure over them are missing until it imports. Importing it "
            f"must be free of effects, so build clients and pipelines inside functions.",
            "target": {"section": "problems", "page": "ship"},
        }
    ]


def _questions_this_stage_needs(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Questions the gate requires that are unanswered.

    What the gate requires is cumulative, so a project at build can owe brainstorm answers.
    The count is split by the stage that asks, and the button lands on the page that asks
    first: "27 remain for this stage" pointing at a section of six was two numbers for one
    fact.
    """
    waiting = [q for q in data["questions_due"] or [] if not q.get("pending")]
    if not waiting:
        return []
    sent = len(data["questions_due"]) - len(waiting)
    stage = data.get("stage")
    here = [q for q in waiting if q.get("stage") == stage]
    earlier = [q for q in waiting if q.get("stage") != stage]
    first = here[:3] if here else earlier[:3]
    names = ", ".join(q.get("title") or q["name"] for q in first)
    return [
        {
            "severity": "attention",
            "waits": "Answer it",
            "head": (
                "One question is unanswered."
                if len(waiting) == 1
                else f"{len(waiting)} questions are unanswered."
            ),
            "body": f"Starting with {names}.{_by_stage_words(here, earlier)} Answer them right "
            f"here, or when your coding agent brings them; the stage's gate waits until "
            f"they are answered." + _already_sent_words(sent),
            "target": {"section": "questions", "page": first[0].get("stage") or stage},
        }
    ]


def _steps_that_decide(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Steps that choose their own next move, and which can ask a person."""
    found: list[dict[str, Any]] = []
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    every_node = [(p, n) for p in declared for n in p["nodes"]]
    deciders = [(p, n) for p, n in every_node if n["kind"] == "agent"]
    if deciders:
        names = ", ".join(n["id"] for _, n in deciders)
        askers = [n["id"] for _, n in deciders if n["asks_a_person"]]
        found.append(
            {
                "severity": "note",
                "head": (
                    f"{deciders[0][1]['id']}: decides for itself."
                    if len(deciders) == 1
                    else f"{len(deciders)} steps decide for themselves."
                ),
                "body": (
                    "It chooses its own next move within its budget."
                    if len(deciders) == 1
                    else f"{names}: each chooses its own next move within its budget."
                )
                + (f" {', '.join(askers)} can also stop and ask a person." if askers else ""),
                "target": {"pipeline": deciders[0][0]["name"], "node": deciders[0][1]["id"]},
            }
        )
    return found


def _steps_not_built(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Steps standing in as placeholders for code that does not exist."""
    found: list[dict[str, Any]] = []
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    every_node = [(p, n) for p in declared for n in p["nodes"]]
    todo = [(p, n) for p, n in every_node if n["planned"]]
    if todo:
        found.append(
            {
                "severity": "note",
                "head": (
                    f"{todo[0][1]['id']}: not built."
                    if len(todo) == 1
                    else f"{len(todo)} steps not built."
                ),
                "body": (
                    f"{todo[0][1]['does']}. Drawn dashed."
                    if len(todo) == 1
                    else ", ".join(f"{n['id']} ({n['does']})" for _, n in todo[:3])
                    + (f", and {len(todo) - 3} more" if len(todo) > 3 else "")
                    + ". Each drawn dashed, with what it will do on its card."
                ),
                "target": {"pipeline": todo[0][0]["name"], "node": todo[0][1]["id"]},
            }
        )
    return found


def _one_sided_resources(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A resource with only one side, or one nothing gives a direction."""
    found: list[dict[str, Any]] = []
    for resource in data["resources"]:
        if resource["writers"] and not resource["readers"] and not resource["unknown"]:
            found.append(
                {
                    "severity": "note",
                    "head": f"{resource['name']}: writers only.",
                    "body": f"Written by {', '.join(resource['writers'][:3])}. Any reader is "
                    f"outside this project. If there is none, these writes go nowhere.",
                    "target": {"resource": resource["name"]},
                }
            )
        if resource["unknown"] and not resource["readers"] and not resource["writers"]:
            why = (
                "A paid call may read or write. Its side-effect class covers neither."
                if resource["paid"] and not resource["undeclared"]
                else "A step's touches= names the resource. A tool's side-effect class declares "
                "a direction, and ctx.record_access records one."
            )
            found.append(
                {
                    "severity": "info",
                    "head": f"{resource['name']}: direction undeclared.",
                    "body": f"Touched by {', '.join(resource['unknown'][:3])}. {why}",
                    "target": {"resource": resource["name"]},
                }
            )
        if resource["readers"] and not resource["writers"] and not resource["unknown"]:
            found.append(
                {
                    "severity": "info",
                    "head": f"{resource['name']}: readers only.",
                    "body": f"Read by {', '.join(resource['readers'][:3])}. Any writer is "
                    f"outside this project. If there is none, these steps read an "
                    f"empty thing.",
                    "target": {"resource": resource["name"]},
                }
            )
    return found


def _cost_capped(pipeline: dict[str, Any], node: dict[str, Any]) -> bool:
    """Whether a cost cap covers this step, its own or its pipeline's."""
    for budget in (node.get("budget"), pipeline.get("budget")):
        if budget and budget.get("max_cost") is not None:
            return True
    return False


def _priced(spenders: list[tuple[Any, Any, Any]]) -> list[str]:
    """Each paid tool once, with its declared price where it declared one."""
    written = []
    for name in sorted({t["name"] for _, _, t in spenders}):
        tool = next(t for _, _, t in spenders if t["name"] == name)
        if tool["cost_per_call"] is not None and tool["currency"] == "USD":
            written.append(f"{name} (${tool['cost_per_call']} a call)")
        else:
            written.append(name)
    return written


def _where_money_leaves(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Every point that can spend, and whether a cap covers it."""
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    spenders = [
        (p, n, t)
        for p in declared
        for n in p["nodes"]
        for t in n["tools"]
        if t["effect"] == "spends_money"
    ]
    if not spenders:
        return []
    capped = all(_cost_capped(p, n) for p, n, _ in spenders)
    p0, n0, _t0 = spenders[0]
    return [
        {
            "severity": "info" if capped else "note",
            "head": "Where money can leave.",
            "body": ", ".join(_priced(spenders))
            + (
                ". Every place that can spend runs under a cost cap."
                if capped
                else ". At least one place that can spend has no cost cap over it."
            ),
            "target": {"pipeline": p0["name"], "node": n0["id"]},
        }
    ]


def _shapes_only_the_record_has(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pipeline shapes that ran and are no longer in the code."""
    found: list[dict[str, Any]] = []
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    retired = [p for p in data["pipelines"] if p["origin"] == "runs"]
    if retired and declared:
        total = sum(p["runs"]["runs"] for p in retired)
        found.append(
            {
                "severity": "info",
                "head": (
                    "One earlier shape exists only in the run record."
                    if len(retired) == 1
                    else f"{len(retired)} earlier shapes exist only in the run record."
                ),
                "body": f"{fmt_runs(total)} were made by versions of the system that are no "
                f"longer in the code. They are kept in the history, dimmed.",
                "target": {"section": "history"},
            }
        )
    if retired and not declared:
        total = sum(p["runs"]["runs"] for p in retired)
        found.append(
            {
                "severity": "note",
                "head": "The run record is rich and the picture is empty.",
                "body": f"{fmt_runs(total)} across {len(retired)} pipeline shapes are in the "
                f"record. Registered pipelines: none. Register each under a name and "
                f"the picture follows from the code.",
                "target": {"section": "history"},
            }
        )
    return found


def _decisions_naming_no_step(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Recorded decisions the join could not place against a step."""
    found: list[dict[str, Any]] = []
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    join = data["decisions_join"]
    if join and join["total"] and declared:
        orphans = len(join["naming_no_step"])
        if orphans:
            found.append(
                {
                    "severity": "info",
                    "head": f"{orphans} of {join['total']} decisions name no step.",
                    "body": "A decision is matched to a step by the steps it lists, or by its "
                    "wording. A decision that is not about a step lands here too.",
                    "target": {"section": "decisions"},
                }
            )
    return found


def _the_brief_disagrees(data: dict[str, Any]) -> list[dict[str, Any]]:
    """An answer that names a step, where the code says that step is something else.

    This is the loud one. A brief naming two steps that decide for themselves, over a
    pipeline holding none, is a claim the builder agreed to that the code never met.
    """
    found = []
    for claim in data.get("claims") or []:
        wrong = claim["named_but_not"]
        if not wrong:
            continue
        told = ", ".join(
            f"{name} is a {claim['kinds'].get(name, 'step the code does not have')}"
            for name in wrong
        )
        found.append(
            {
                "severity": "attention",
                "waits": "See the step",
                "head": f"{claim['title']}: your answer and the code disagree.",
                "body": f"You said {', '.join(wrong)} "
                f"{claim['one'] if len(wrong) == 1 else claim['many']}. In the code, "
                f"{told}."
                + (
                    f" The steps that do: {', '.join(claim['in_code'])}."
                    if claim["in_code"]
                    else " Steps that do: none."
                ),
                "target": {"section": "claims"},
            }
        )
    return found


def _the_brief_is_short(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The code does something the answer names steps for and did not name this one."""
    found = []
    for claim in data.get("claims") or []:
        missing = claim["in_code_but_unnamed"]
        if not missing or not claim["names"]:
            continue
        found.append(
            {
                "severity": "note",
                "head": f"A step you did not name {claim['one']}.",
                "body": f"You named {', '.join(claim['names'])} under “{claim['title']}”. "
                f"{', '.join(missing)} also "
                f"{claim['one'] if len(missing) == 1 else claim['many']} and "
                f"{'is' if len(missing) == 1 else 'are'} not mentioned.",
                "target": {"section": "claims"},
            }
        )
    return found


def _nothing_was_claimed(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A step that decides for itself or spends, under an answer naming no step at all."""
    loud = {"agency_boundary", "tool_effects"}
    found = []
    for claim in data.get("claims") or []:
        if claim["entry"] not in loud or claim["names"] or not claim["in_code"]:
            continue
        found.append(
            {
                "severity": "info",
                "head": f"{claim['title']}: your answer names no step.",
                "body": f"{', '.join(claim['in_code'])} "
                f"{claim['one'] if len(claim['in_code']) == 1 else claim['many']}. "
                f"Answers are matched to steps by name.",
                "target": {"section": "claims"},
            }
        )
    return found


# A step ends on one of these when the work finished. Anything else is a failure, a limit
# reached, or an untraversed branch, and each reads differently to a builder.
_ORDINARY_ENDINGS = ("finish", "finished", "complete", "completed", "skipped")


def _outcomes_over_the_record(data: dict[str, Any]) -> tuple[dict[str, int], int, list]:
    """Every outcome that is not completion, the total run count, and the worst shapes."""
    bad: dict[str, int] = {}
    total = 0
    worst: list[tuple[int, str]] = []
    for pipeline in data["pipelines"]:
        outcomes = (pipeline.get("runs") or {}).get("outcomes") or {}
        total += sum(outcomes.values())
        here = {name: count for name, count in outcomes.items() if name != "completed"}
        for name, count in here.items():
            bad[name] = bad.get(name, 0) + count
        if here:
            worst.append(
                (
                    sum(here.values()),
                    pipeline.get("name") or pipeline.get("signature") or "one shape",
                )
            )
    worst.sort(reverse=True)
    return bad, total, worst


def _runs_that_did_not_finish(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Runs in the record whose outcome was not completion, over the whole record.

    One sentence for the project rather than one per shape: a project with eighteen shapes
    has eighteen of these, and a list that long goes unread.
    """
    bad, total, worst = _outcomes_over_the_record(data)
    if not bad:
        return []
    off = sum(bad.values())
    said = ", ".join(
        f"{count:,} {name.replace('_', ' ')}"
        for name, count in sorted(bad.items(), key=lambda pair: -pair[1])
    )
    named = ", ".join(f"{name} ({count:,})" for count, name in worst[:3])
    return [
        {
            "severity": "attention" if total and off > total / 4 else "note",
            "head": (
                f"One run of {total:,} did not complete."
                if off == 1
                else f"{off:,} runs of {total:,} did not complete."
            ),
            "body": f"{said}. Most of them in {named}. `simple-agents report runs/` prints what "
            f"every step spent beside what it produced.",
            "target": {"section": "history"},
        }
    ]


def _steps_that_hit_a_limit(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A step whose last run ended on a budget, an error, or anything but finishing."""
    found = []
    for pipeline in data["pipelines"]:
        if pipeline["origin"] != "declared":
            continue
        for node in pipeline["nodes"]:
            ended = (node.get("ran") or {}).get("ended") or {}
            odd = {k: v for k, v in ended.items() if k not in _ORDINARY_ENDINGS}
            if not odd:
                continue
            said = ", ".join(f"{k.replace('_', ' ')} {v:,}" for k, v in sorted(odd.items()))
            found.append(
                {
                    "severity": "attention",
                    "head": f"{node['id']} did not finish the work in the last run.",
                    "body": f"It ended: {said}. It produced no value for the next step, and "
                    f"the run continued.",
                    "target": {"pipeline": pipeline["name"], "node": node["id"]},
                }
            )
    return found


def _failure_paths_that_fired(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A step reached only when something before it failed, that the last run reached."""
    found = []
    for pipeline in data["pipelines"]:
        if pipeline["origin"] != "declared":
            continue
        handlers = {n["on_error"]: n["id"] for n in pipeline["nodes"] if n["on_error"]}
        for node in pipeline["nodes"]:
            if node["id"] not in handlers:
                continue
            if not (node.get("ran") or {}).get("executions"):
                continue
            found.append(
                {
                    "severity": "attention",
                    "head": f"The failure path into {node['id']} fired in the last run.",
                    "body": f"{handlers[node['id']]} failed and the run went to {node['id']} "
                    f"instead of carrying on.",
                    "target": {"pipeline": pipeline["name"], "node": node["id"]},
                }
            )
    return found


def _questions_nobody_answered(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A question the run put to a person that came back without an answer."""
    unanswered = [q for q in data.get("asked") or [] if q["resolution"] not in ("answered",)]
    if not unanswered:
        return []
    by_kind: dict[str, int] = {}
    for question in unanswered:
        by_kind[question["resolution"]] = by_kind.get(question["resolution"], 0) + 1
    said = ", ".join(f"{count} {kind}" for kind, count in sorted(by_kind.items()))
    return [
        {
            "severity": "note",
            "head": (
                "A question the last run asked came back without an answer."
                if len(unanswered) == 1
                else f"{len(unanswered)} questions the last runs asked came back without an answer."
            ),
            "body": f"{said}. {unanswered[0]['asked_by']} asked: "
            f"“{_clip(unanswered[0]['prompt'] or '')}”"
            + (f" {unanswered[0]['reason']}" if unanswered[0].get("reason") else ""),
            "target": {"section": "asked"},
        }
    ]


def _answers_read_as_something_else(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A person said which option they meant and the rule read a different one."""
    misread = [q for q in data.get("asked") or [] if q.get("misread")]
    if not misread:
        return []
    one = misread[0]
    return [
        {
            "severity": "attention",
            "head": "An answer was read as a different option than the one it was.",
            "body": f"{one['asked_by']} asked “{_clip(one['prompt'] or '')}”. The channel said "
            f"the answer was {one['declared_choice']!r} and the rule read "
            f"{one['chose']!r}, so the branch behind it was never taken.",
            "target": {"section": "asked"},
        }
    ]


def _what_moved_between_runs(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The data moved between the last two runs of one shape."""
    found = []
    for name, lines in (data.get("moved") or {}).items():
        found.append(
            {
                "severity": "note",
                "head": f"{name} moved different data than it did last time.",
                "body": " ".join(lines[:2])
                + (f" And {len(lines) - 2} more." if len(lines) > 2 else ""),
                "target": {"section": "moved"},
            }
        )
    return found


def _branch_words(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 1 else f"{value}"


def _arms_never_taken(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A declared way on that no run has ever gone.

    A route arm, a failure path or a cycle's return that has never fired is a part of the
    system nothing has exercised, and no reading of the code produces the fact.
    """
    found: list[dict[str, Any]] = []
    for pipeline in [p for p in data["pipelines"] if p["origin"] == "declared"]:
        over = pipeline.get("over_runs") or {}
        edges = over.get("edges") or {}
        if not over.get("runs") or not edges:
            continue
        routed = {name.split("->")[0] for name in edges}
        quiet = []
        for node in pipeline["nodes"]:
            if node["id"] not in routed:
                continue
            ways = list(node["successors"]) + ([node["on_error"]] if node["on_error"] else [])
            quiet += [
                f"{node['id']} → {target}"
                for target in ways
                if not edges.get(f"{node['id']}->{target}")
            ]
        if not quiet:
            continue
        found.append(
            {
                "severity": "note",
                "head": f"{pipeline['name']}: {len(quiet)} "
                f"edge{'' if len(quiet) == 1 else 's'} untaken.",
                "body": ", ".join(quiet[:4])
                + (f", and {len(quiet) - 4} more" if len(quiet) > 4 else "")
                + f". Over {fmt_runs(over['runs'])} on record.",
                "target": {"pipeline": pipeline["name"]},
            }
        )
    return found


def _one_step_costs_most(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A step taking most of what a pipeline spends, over every run rather than the newest."""
    found: list[dict[str, Any]] = []
    for pipeline in [p for p in data["pipelines"] if p["origin"] == "declared"]:
        for where, whose in (("over_runs", "your runs"), ("over_rollouts", "the evaluation")):
            over = pipeline.get(where) or {}
            if not over.get("runs") or len(over.get("bases") or []) != 1:
                continue
            basis = over["bases"][0]
            costs = {
                node_id: sum(held["cost_by_basis"].values())
                + sum(held["spend_by_currency"].values())
                for node_id, held in (over.get("nodes") or {}).items()
            }
            total = sum(costs.values())
            if total <= 0 or len(costs) < 2:
                continue
            node_id, most = max(costs.items(), key=lambda pair: pair[1])
            share = most / total
            if share < 0.5:
                continue
            found.append(
                {
                    "severity": "info",
                    "head": f"{node_id} is where the money goes in {pipeline['name']}.",
                    "body": f"{round(share * 100)}% of what {whose} spent, "
                    f"{_branch_words(most)} of {_branch_words(total)} {basis}, over "
                    f"{fmt_runs(over['runs'])}.",
                    "target": {"pipeline": pipeline["name"], "node": node_id},
                }
            )
            break
    return found


def _stores_only_the_evaluation_reaches(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A store the agent's own runs have never touched, and a measurement has."""
    return [
        {
            "severity": "note",
            "head": f"{card['name']}: reached only by the evaluation.",
            "body": f"{card['access_count_measuring']:,} access"
            f"{'' if card['access_count_measuring'] == 1 else 'es'} from rollouts, "
            f"0 from the project's own runs. Measured by the evaluation and never "
            f"reached in real use.",
            "target": {"resource": card["name"]},
        }
        for card in data.get("resources") or []
        if not card.get("access_count") and card.get("access_count_measuring")
    ]


def _stores_nothing_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A resource declared, reached by no tool, and never recorded by the step that names it."""
    found = [
        card
        for card in data.get("resources") or []
        if not (card.get("through") or [])
        and not card.get("access_count")
        and not card.get("access_count_measuring")
        and card.get("undeclared")
    ]
    if not found:
        return []
    ran = any(
        (p.get("over_runs") or {}).get("runs")
        for p in data["pipelines"]
        if p["origin"] == "declared"
    )
    if not ran:
        return []
    return [
        {
            "severity": "note",
            "head": f"{card['name']}: contents and direction unknown.",
            "body": f"Touched by {', '.join(card['undeclared'][:3])}, reached by no tool, and "
            f"unrecorded. Record an access to fill it in: "
            f'ctx.record_access("{card["name"]}", "read", outputs=...).',
            "target": {"resource": card["name"]},
        }
        for card in found
    ]


def _never_agreed_to(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A pipeline the builder has never confirmed the shape of.

    The page says *"Changed since you agreed to it"* and *"Still the shape you agreed to"*,
    and said nothing at all where no confirmation exists. That is the state every project is
    in at `shape`, which is the gate this page was built for: the coding agent shows a
    proposal and the builder agrees to it or says what is wrong. A proposal that does not
    say it is one reads as a decision already taken.
    """
    unconfirmed = [
        p["name"]
        for p in data["pipelines"]
        if p.get("origin") == "declared" and p.get("confirmed_shape") is None
    ]
    if not unconfirmed:
        return []
    at_shape = data.get("stage") == "shape"
    named = ", ".join(unconfirmed[:3])
    more = f" and {len(unconfirmed) - 3} more" if len(unconfirmed) > 3 else ""
    every = ", ".join(unconfirmed)
    return [
        {
            "severity": "attention" if at_shape else "note",
            "waits": "Walk the drawing",
            # Agreeing is one act on the whole design, so it is one thread against the project
            # rather than one per pipeline. An action carrying words is sent on the click; one
            # carrying none opens the writing panel, because saying what is wrong takes words.
            "actions": [
                {
                    "words": "Agree",
                    "at": "project",
                    "kind": "comment",
                    "said": f"I agree to the design as drawn: {every}.",
                },
                {"words": "Something is wrong", "at": "project", "kind": "comment", "said": None},
            ],
            "head": (
                "You have not agreed to this design yet."
                if len(unconfirmed) == 1
                else f"{len(unconfirmed)} pipelines are drawn that you have not agreed to."
            ),
            "body": f"{named}{more}: proposed and unconfirmed. Say what is wrong with it, or "
            f"agree to it. The shape you agree to is recorded, and the page marks every "
            f"later change against it." + ("" if at_shape else " What is built below rests on it."),
            "target": {"pipeline": unconfirmed[0]},
        }
    ]


def _findings(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Everything that needs eyes, most urgent first.

    ::

        [f["head"] for f in _findings(assemble("."))]

    Each family is its own function above, and each returns the findings it has to make. The
    order here is the order two findings of one severity appear in.
    """
    found: list[dict[str, Any]] = []
    for family in (
        _the_code_would_not_import,
        _changed_since_it_ran,
        _open_threads,
        _questions_this_stage_needs,
        _never_agreed_to,
        _steps_that_decide,
        _steps_not_built,
        _one_sided_resources,
        _where_money_leaves,
        _shapes_only_the_record_has,
        _decisions_naming_no_step,
        _the_brief_disagrees,
        _the_brief_is_short,
        _nothing_was_claimed,
        _runs_that_did_not_finish,
        _steps_that_hit_a_limit,
        _failure_paths_that_fired,
        _questions_nobody_answered,
        _answers_read_as_something_else,
        _what_moved_between_runs,
        _arms_never_taken,
        _one_step_costs_most,
        _stores_only_the_evaluation_reaches,
        _stores_nothing_records,
    ):
        found.extend(family(data))
    _measure_findings(data, found)

    # Something the builder has to act on comes before something they only have to know,
    # whatever its severity: a page that mixes the two trains a reader to skip both.
    order = {"attention": 0, "note": 1, "info": 2}
    found.sort(key=lambda f: (0 if f.get("waits") else 1, order[f["severity"]]))
    return found


def _only_the_record(data: dict[str, Any]) -> list[str]:
    """What a project with runs and no registered pipeline has to say for itself."""
    history = [p for p in data["pipelines"] if p["origin"] == "runs"]
    if history:
        total = sum(p["runs"]["runs"] for p in history)
        return [
            f"{len(history)} pipeline shapes have made {fmt_runs(total)}; none is "
            f"registered for the picture yet."
        ]
    if not data["pipelines"]:
        return ["The project has no pipeline yet. The picture starts with the first one."]
    return []


def _what_is_built(data: dict[str, Any]) -> list[str]:
    """How much of the system exists, or what stands in for it where none does."""
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    if not declared:
        return _only_the_record(data)
    built = sum(1 for p in declared for n in p["nodes"] if not n["planned"])
    todo = sum(1 for p in declared for n in p["nodes"] if n["planned"])
    what = (
        f"{len(declared)} pipeline{'s' if len(declared) != 1 else ''}, "
        f"{built} step{'s' if built != 1 else ''} built"
    )
    if todo:
        what += f", {todo} still to build"
    return [what + "."]


def _what_waits_on_the_builder(data: dict[str, Any]) -> list[str]:
    """Open comments and unanswered questions, counted."""
    parts: list[str] = []
    open_comments = len(
        [c for c in data["comments"] if c["status"] == "open" and c["kind"] != "answer"]
    )
    if open_comments:
        parts.append(
            f"{open_comments} of your comments "
            f"{'waits' if open_comments == 1 else 'wait'} on an answer."
        )
    waiting = [q for q in data["questions_due"] if not q.get("pending")]
    if waiting:
        parts.append(
            "One question is unanswered."
            if len(waiting) == 1
            else f"{len(waiting)} questions are unanswered."
        )
    unconfirmed = [
        p
        for p in data["pipelines"]
        if p.get("origin") == "declared" and p.get("confirmed_shape") is None
    ]
    if unconfirmed:
        parts.append(
            f"{len(unconfirmed)} pipeline{'s' if len(unconfirmed) != 1 else ''} "
            f"await{'' if len(unconfirmed) != 1 else 's'} your agreement."
        )
    return parts


def _what_was_measured(data: dict[str, Any]) -> list[str]:
    """The headline figure with its interval, and the floor it is read against."""
    parts: list[str] = []
    measured = data.get("measured") or {}
    floor = measured.get("floor")
    if floor is not None:
        counts = measured.get("counts") or {}
        parts.append(
            f"The evaluation scored {counts.get('right', 0)} of {counts.get('of', 0)} "
            f"rollouts right. Its declared baseline scored {floor['right']} of "
            f"{floor['of']}."
        )
    headline = measured.get("headline")
    if headline and headline["point"] is not None:
        span = ""
        if headline["low"] is not None and headline["high"] is not None:
            span = (
                f" ({_rate(headline['low'], headline['unit'])} to "
                f"{_rate(headline['high'], headline['unit'])})"
            )
        parts.append(
            f"It scored {_rate(headline['point'], headline['unit'])}{span} on "
            f"{headline['name']}, over {measured.get('n')} examples "
            f"× {measured.get('k')} rollouts."
        )
    return parts


def _standing(data: dict[str, Any]) -> str:
    """The one sentence at the top: where the project stands right now.

    ::

        _standing(assemble("."))
        # 'At the build stage. 2 pipelines, 5 steps built, 1 still to build.'
    """
    parts: list[str] = []
    if data.get("stage"):
        parts.append(f"At the {data['stage']} stage.")
    moving = data.get("running")
    if moving:
        parts.append(
            f"A run is moving through {moving['pipeline']} right now."
            if moving.get("pipeline")
            else "A run is moving right now."
        )
    for more in (_what_is_built, _what_waits_on_the_builder, _what_was_measured):
        parts.extend(more(data))
    return " ".join(parts)
