"""What the research stage found, and what the design rests on.

`research.md`'s survey is a table, required and machine-read since FT-36, so the material is
structured and the page showed none of it. This reads it back: the parts, the candidates
weighed against each, what became of each one, and the decisions that cite them.

::

    held = read_research(".", brief)
    [part["part"] for part in held["parts"]]
    [d["name"] for d in held["parts"][0]["candidates"][0]["decisions"]]

``None`` where the project has no `research.md`, which is every project before that stage.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

__all__ = ["read_research"]

# What an outcome cell says, in the words the survey uses, and how the page draws each.
_OUTCOMES = {
    "adopted": "adopted",
    "chosen": "adopted",
    "rejected": "rejected",
    "not investigated": "not_investigated",
    "not looked at": "not_investigated",
    "deferred": "not_investigated",
}


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).casefold()).strip()


def _outcome(cell: str) -> tuple[str, str]:
    """One outcome cell as a state and the reason beside it.

    The survey's own words: a cell reading ``Rejected: lost the detail`` is a state and why.
    A cell the page does not recognise is kept whole and drawn as its own words, because the
    project chose them and the page is not the place to argue.
    """
    words = str(cell).strip(" *_`")
    head, _, tail = words.partition(":")
    state = _OUTCOMES.get(_key(head))
    if state is None:
        state = _OUTCOMES.get(_key(words), "other")
        return state, "" if state != "other" else words
    return state, tail.strip()


def _column(header: list[str], *names: str) -> int | None:
    keys = [_key(cell) for cell in header]
    for name in names:
        if _key(name) in keys:
            return keys.index(_key(name))
    return None


def _cites(decision: Any, part: str, candidate: str) -> bool:
    """Whether one decision's own words name this candidate or this part.

    The same join the brief-against-code comparison uses, and with the same limit: it reads
    which words appear, never what the decision meant.
    """
    said = _key(
        " ".join(str(getattr(decision, key, "") or "") for key in ("chose", "because"))
        + " "
        + " ".join(str(one) for one in (getattr(decision, "considered", ()) or ()))
    )
    return bool(candidate and _key(candidate) in said) or bool(part and _key(part) in said)


def read_research(root: str | Path, brief: Any) -> dict[str, Any] | None:
    """`research.md` as the page draws it: the deciding factor, the parts, and what rests on them."""
    from ..conformance.artifacts import OUTCOME_COLUMN, RESEARCH_SECTIONS, SURVEY_SECTION
    from ..conformance.artifacts import _tables_under
    from ..conformance.checks import _section_of

    path = Path(root).expanduser() / "research.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    decisions = [
        d
        for d in (getattr(brief, "decisions", ()) or ())
        if getattr(d, "kind", None) == "dependency"
    ]
    parts: dict[str, dict[str, Any]] = {}
    for rows in _tables_under(text, SURVEY_SECTION):
        header, *body = rows
        outcome_at = _column(header, OUTCOME_COLUMN)
        part_at = _column(header, "Part", "The part")
        candidate_at = _column(header, "Candidate", "Option", "Approach")
        why_at = _column(header, "Why", "Reason", "Notes")
        for cells in body:
            if all(set(cell) <= set("-: ") for cell in cells):
                continue
            named = (
                cells[part_at].strip(" *_`") if part_at is not None and part_at < len(cells) else ""
            )
            candidate = (
                cells[candidate_at].strip(" *_`")
                if candidate_at is not None and candidate_at < len(cells)
                else (cells[0].strip(" *_`") if cells else "")
            )
            state, said = _outcome(
                cells[outcome_at] if outcome_at is not None and outcome_at < len(cells) else ""
            )
            why = cells[why_at].strip(" *_`") if why_at is not None and why_at < len(cells) else ""
            held = parts.setdefault(
                named or "The whole of it", {"part": named or "The whole of it", "candidates": []}
            )
            held["candidates"].append(
                {
                    "candidate": candidate,
                    "outcome": state,
                    "said": said or why,
                    "decisions": [
                        {
                            "name": d.name,
                            "chose": str(getattr(d, "chose", "") or ""),
                            "status": getattr(d, "status", None),
                        }
                        for d in decisions
                        if _cites(d, named, candidate)
                    ],
                }
            )
    quoted = _section_of(text, RESEARCH_SECTIONS[3]) or ""
    return {
        "turns_on": (_section_of(text, RESEARCH_SECTIONS[2]) or "").strip(),
        "parts_said": (_section_of(text, RESEARCH_SECTIONS[0]) or "").strip(),
        "parts": list(parts.values()),
        "said": quoted.strip(),
        "resting_on": [
            {
                "name": d.name,
                "chose": str(getattr(d, "chose", "") or ""),
                "because": str(getattr(d, "because", "") or ""),
                "status": getattr(d, "status", None),
                "cites": [
                    candidate["candidate"]
                    for part in parts.values()
                    for candidate in part["candidates"]
                    if any(one["name"] == d.name for one in candidate["decisions"])
                ],
            }
            for d in decisions
        ],
    }
