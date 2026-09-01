"""What the builder was told the system does, against what the code says it does.

An answer in the brief and the shape in `agent.py` are written at different times by different
hands, and nothing compares them. A brief naming two steps that decide for themselves, over a
pipeline holding none, passed every gate 21 times across 116 commits on one project. Both
halves are on the page already; this is the join between them.

**Matched on a step's name, and nothing more.** An answer that describes a step in other words
reads here as naming nothing, and every sentence the page builds from this says so. What it
cannot do is read intent: it reports which steps an answer names, what the code says each of
them is, and what the code has that the answer never mentions.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["read_claims", "read_seams", "ask_of", "title_of"]

MAX_ANSWER_CHARS = 300
"""How much of an answer travels with a claim, for the page to quote."""


def _named_in(text: str, candidates: list[str]) -> list[str]:
    """Every candidate whose name appears in the text as a whole word."""
    return [name for name in candidates if re.search(rf"\b{re.escape(name)}\b", text)]


def _every_step(pipelines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [node for pipeline in pipelines for node in pipeline["nodes"]]


def _decides_for_itself(steps: list[dict[str, Any]]) -> list[str]:
    return [n["id"] for n in steps if n["kind"] == "agent"]


def _can_ask_a_person(steps: list[dict[str, Any]]) -> list[str]:
    return [n["id"] for n in steps if n["asks_a_person"]]


def _handles_its_own_failure(steps: list[dict[str, Any]]) -> list[str]:
    return [n["id"] for n in steps if n["on_error"] or n["retries"]]


def _capped(steps: list[dict[str, Any]]) -> list[str]:
    return [n["id"] for n in steps if n["budget"]]


# What the question asks about: "spend money, write somewhere permanent, or take an action
# that cannot be undone". A `WRITES` tool writes somewhere permanent, so leaving it out made a
# builder who named their writer read as disagreeing with the code.
_REACHES_OUTSIDE = ("spends_money", "writes", "irreversible")


def _spends_or_cannot_be_undone(steps: list[dict[str, Any]]) -> list[str]:
    return [n["id"] for n in steps if any(t["effect"] in _REACHES_OUTSIDE for t in n["tools"])]


def _scored_on_their_own(steps: list[dict[str, Any]], coverage: dict[str, Any]) -> list[str]:
    return list(coverage.get("scored") or [])


# One row per answer the code has an exact counterpart for. The two phrasings are what the
# page says of one step and of several, `find` is what the other side is, and `reads` names
# the artifact it comes out of. Five are read from the pipeline, which exists from the moment
# a skeleton is written; `judged_steps` is read from the evaluation, which exists from
# `measure`. A comparison against an artifact the project has not produced yet is reported as
# waiting rather than as a disagreement.
_CHECKED: tuple[tuple[str, str, str, Any, str], ...] = (
    ("agency_boundary", "decides for itself", "decide for themselves", _decides_for_itself, "code"),
    (
        "consultation",
        "can stop and ask a person",
        "can stop and ask a person",
        _can_ask_a_person,
        "code",
    ),
    (
        "what_goes_wrong",
        "says where a failure goes",
        "say where a failure goes",
        _handles_its_own_failure,
        "code",
    ),
    ("budget", "runs under a limit of its own", "run under a limit of their own", _capped, "code"),
    (
        "tool_effects",
        "spends money or writes somewhere permanent",
        "spend money or write somewhere permanent",
        _spends_or_cannot_be_undone,
        "code",
    ),
    (
        "judged_steps",
        "carries a right answer of its own",
        "carry a right answer of their own",
        _scored_on_their_own,
        "evaluation",
    ),
)


def title_of(name: str) -> str:
    """One brief key named for the builder.

    The library's own title where it asks that question, and the key spaced and capitalised
    where the project made the key up::

        title_of("agency_boundary")   # "What the agent works out for itself"
        title_of("pool_size")         # "Pool size"
    """
    from ..conformance.elicitation import question

    try:
        return question(name).title
    except Exception:  # noqa: BLE001 - an entry the library does not ask for has no title
        return name.replace("_", " ").capitalize()


def ask_of(name: str) -> str | None:
    """The first line of the question the library puts for one brief key.

    ``None`` where the library asks no such question, which a project's own entry is::

        ask_of("agency_boundary")   # "What would the builder like the agent to work out ..."
        ask_of("pool_size")         # None
    """
    from ..conformance.elicitation import question

    try:
        return question(name).ask.split("\n")[0]
    except Exception:  # noqa: BLE001 - a question the library no longer asks loses its text
        return None


def stage_of(name: str) -> str | None:
    """The stage the library asks one brief question at.

    ``None`` where the library asks no such question, which a project's own entry is::

        stage_of("what_it_does")    # "brainstorm"
        stage_of("pool_size")       # None
    """
    from ..conformance.elicitation import question

    try:
        return question(name).stage
    except Exception:  # noqa: BLE001 - a question the library no longer asks loses its stage
        return None


# The same six phrasings after "should", for the sentence the page sends when the builder
# says the code is wrong: "judge_books should decide for itself", not "should decides".
_SHOULD: dict[str, tuple[str, str]] = {
    "agency_boundary": ("decide for itself", "decide for themselves"),
    "consultation": ("be able to stop and ask a person", "be able to stop and ask a person"),
    "what_goes_wrong": ("say where a failure goes", "say where a failure goes"),
    "budget": ("run under a limit of its own", "run under limits of their own"),
    "tool_effects": (
        "spend money or write somewhere permanent",
        "spend money or write somewhere permanent",
    ),
    "judged_steps": ("carry a right answer of its own", "carry right answers of their own"),
}


def _one_claim(
    entry: dict[str, Any],
    one: str,
    many: str,
    in_code: list[str],
    every: list[str],
    unread: str | None = None,
) -> dict[str, Any]:
    """One answer against the code's counterpart, both ways round.

    ``unread`` names the artifact the other side would have come from, where the project has
    not produced it yet. Both difference lists are then empty: what an answer names is known,
    and what it should be compared against is not.
    """
    answer = str(entry.get("answer") or "")
    named = _named_in(answer, [n["id"] for n in every])
    short = [n["id"].rsplit(".", 1)[-1] for n in every]
    named += [
        full
        for full, tail in zip([n["id"] for n in every], short)
        if tail != full and re.search(rf"\b{re.escape(tail)}\b", answer)
    ]
    named = sorted(set(named))
    agreed = sorted(set(named) & set(in_code))
    kinds = {n["id"]: n["kind_word"] for n in every}
    return {
        "entry": entry["name"],
        "title": title_of(entry["name"]),
        "kinds": {name: kinds[name] for name in named if name in kinds},
        "asks": ask_of(entry["name"]),
        "answer": answer[:MAX_ANSWER_CHARS],
        "one": one,
        "many": many,
        "should_one": _SHOULD.get(entry["name"], (one, many))[0],
        "should_many": _SHOULD.get(entry["name"], (one, many))[1],
        "names": named,
        "unread": unread,
        "in_code": sorted(in_code),
        "agreed": agreed,
        "named_but_not": [] if unread else sorted(set(named) - set(in_code)),
        "in_code_but_unnamed": [] if unread else sorted(set(in_code) - set(named)),
    }


def read_claims(
    pipelines: list[dict[str, Any]],
    brief: Any,
    coverage: dict[str, Any],
    measured: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Every answer the code can be read against, with both sides of the comparison.

    ::

        claims = read_claims(declared, brief, coverage, measured)
        [c["entry"] for c in claims if c["named_but_not"]]
        [c["entry"] for c in claims if c["unread"]]     # waiting on an artifact

    ``measured`` is the evaluation the page read, and ``None`` where the project has none yet.
    One answer, `judged_steps`, is compared against the evaluation rather than against the
    pipeline; without one its claim carries ``unread`` and reports no difference, since an
    answer naming a step cannot disagree with a file that does not exist.

    Empty where the project has no brief or no declared pipeline, because there is then
    no comparable step. An answer naming no step at all is still returned, since a claim about
    steps that names none is what the page has to be able to say.
    """
    steps = _every_step(pipelines)
    if brief is None or not steps:
        return []
    claims = []
    for name, one, many, find, reads in _CHECKED:
        entry = brief.entry(name) if hasattr(brief, "entry") else None
        if entry is None or getattr(entry, "status", "") != "answered":
            continue
        in_code = find(steps, coverage) if find is _scored_on_their_own else find(steps)
        unread = "the evaluation" if reads == "evaluation" and measured is None else None
        claims.append(
            _one_claim(
                {"name": name, "answer": getattr(entry, "answer", "")},
                one,
                many,
                in_code,
                steps,
                unread,
            )
        )
    return claims


# The four answers the `shape` gate settles, and what each one's code side is. Three are read
# from the pipeline; `used_through` is the entry point, which no code declares, so it carries
# the builder's answer alone. `tool_effects` covers spending and permanence together, so its
# row holds both and reports one comparison.
_SEAMS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("agency_boundary", "Decides for itself", ("decides",)),
    ("consultation", "Asks a person", ("asks",)),
    ("tool_effects", "Spends money or writes somewhere permanent", ("spends", "permanent")),
    ("used_through", "The entry point", ()),
)

_SEAM_PARTS = {
    "decides": "Decides for itself",
    "asks": "Asks a person",
    "spends": "Spends money",
    "permanent": "Writes somewhere permanent",
}


def _through(node: dict[str, Any], kind: str) -> list[str]:
    """The tools that give one step one seam, by name, for the row to say how."""
    if kind == "asks":
        return sorted({t["name"] for t in node["tools"] if t["asks"]})
    if kind == "spends":
        return sorted({t["name"] for t in node["tools"] if t["effect"] == "spends_money"})
    if kind == "permanent":
        return sorted(
            {t["name"] for t in node["tools"] if t["effect"] in ("writes", "irreversible")}
        )
    return []


def _answered_by(node: dict[str, Any]) -> list[str]:
    """Who answers when this step asks, as the channel declared it."""
    return sorted({str(t["asks"]) for t in node["tools"] if t["asks"]})


def _seam_steps(pipelines: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    """Every step holding one seam, with the pipeline it is in and how it holds it."""
    found = []
    for pipeline in pipelines:
        for node in pipeline["nodes"]:
            has = (
                node["kind"] == "agent"
                if kind == "decides"
                else node["asks_a_person"]
                if kind == "asks"
                else any(t["effect"] == "spends_money" for t in node["tools"])
                if kind == "spends"
                else any(t["effect"] in ("writes", "irreversible") for t in node["tools"])
            )
            if not has:
                continue
            found.append(
                {
                    "id": node["id"],
                    "at": f"{pipeline['name']}/{node['id']}",
                    "pipeline": pipeline["name"],
                    "through": _through(node, kind),
                    "answered_by": _answered_by(node) if kind == "asks" else [],
                }
            )
    return found


def read_seams(
    pipelines: list[dict[str, Any]],
    brief: Any,
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The four things the `shape` gate settles, read off the code and the brief together.

    ::

        seams = read_seams(declared, brief, claims)
        [s["entry"] for s in seams if s["named_but_not"]]    # the brief promised, the code lacks

    One row per answer: what the builder said, which steps the code has, and the two
    differences between them. ``parts`` splits a row whose answer covers more than one thing,
    so spending and permanence are read apart while ``tool_effects`` is compared once.
    ``reads_code`` is ``False`` for the entry point, which no code declares.
    """
    by_entry = {c["entry"]: c for c in claims}
    rows = []
    for name, title, kinds in _SEAMS:
        entry = brief.entry(name) if brief is not None and hasattr(brief, "entry") else None
        status = str(getattr(entry, "status", "") or "unanswered")
        claim = by_entry.get(name, {})
        rows.append(
            {
                "entry": name,
                "title": title,
                "asked": title_of(name),
                "status": status,
                "answer": str(getattr(entry, "answer", "") or "")[:MAX_ANSWER_CHARS]
                if status == "answered"
                else "",
                "reads_code": bool(kinds),
                "parts": [
                    {
                        "kind": kind,
                        "words": _SEAM_PARTS[kind],
                        "steps": _seam_steps(pipelines, kind),
                    }
                    for kind in kinds
                ],
                "named_but_not": claim.get("named_but_not") or [],
                "in_code_but_unnamed": claim.get("in_code_but_unnamed") or [],
                "names": claim.get("names") or [],
            }
        )
    return rows
