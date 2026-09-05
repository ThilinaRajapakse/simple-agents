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
    state = _state_of(head)
    if state is None:
        state = _state_of(words)
        if state is None:
            return "other", _said(words)
        return state, ""
    return state, _said(tail)


def _said(words: str) -> str:
    """The reason beside an outcome, as prose.

    A survey writes a name in backticks and the page renders text rather than markdown, so a
    cell reading ``adopted: `document_search` in `docs/tools.md``` would otherwise show an
    unbalanced backtick. What a row names is read from the cell separately.
    """
    return str(words).replace("`", "").strip()


def _state_of(words: str) -> str | None:
    """Which state a phrase says, or ``None`` where it says none of them.

    Read as a prefix, so `Adopted alongside BM25` is adopted and `Rejected for the reported
    number` is rejected. The report's own note reads an outcome the same way
    (`docs/conformance.md` §4.4), so the page and the note agree about what a row says.
    """
    key = _key(words)
    for said, state in _OUTCOMES.items():
        if key == said or key.startswith(f"{said} "):
            return state
    return None


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


def _facilities_unreached(cell: str, reached: set[str]) -> list[str]:
    """The library facilities one adopted outcome cell names that no run has recorded.

    Only what the cell wrote in backticks is read, the way the report's own note reads it, so
    a row calling something "the library's page fetcher" names nothing here.
    """
    from ..conformance.adopted import facilities_named

    return [name for name in facilities_named(cell) if name not in reached]


def _cell(cells: list[str], at: int | None) -> str:
    """One cell of a survey row, or ``""`` where the row is too short to reach the column."""
    return cells[at].strip(" *_`") if at is not None and at < len(cells) else ""


def _candidate(cells: list[str], columns: dict[str, int | None], reached: set[str], decisions):
    """One survey row as the page draws it: what it was, what became of it, and what cites it."""
    named = _cell(cells, columns["part"])
    candidate = _cell(cells, columns["candidate"]) or (cells[0].strip(" *_`") if cells else "")
    outcome_at = columns["outcome"]
    raw = cells[outcome_at] if outcome_at is not None and outcome_at < len(cells) else ""
    state, said = _outcome(raw)
    return named, {
        "candidate": candidate,
        "outcome": state,
        "said": said or _cell(cells, columns["why"]),
        "unreached": _facilities_unreached(raw, reached) if state == "adopted" else [],
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


def _survey(text: str, decisions: list[Any], reached: set[str]) -> dict[str, dict[str, Any]]:
    """The survey's tables as one part per column, each holding the candidates weighed for it.

    A blank line ends a markdown table, so a section holding two of them reads each against
    its own header, the way FT-36 reads them.
    """
    from ..conformance.artifacts import OUTCOME_COLUMN, SURVEY_SECTION, _tables_under

    parts: dict[str, dict[str, Any]] = {}
    for rows in _tables_under(text, SURVEY_SECTION):
        header, *body = rows
        columns = {
            "outcome": _column(header, OUTCOME_COLUMN),
            "part": _column(header, "Part", "The part"),
            "candidate": _column(header, "Candidate", "Option", "Approach"),
            "why": _column(header, "Why", "Reason", "Notes"),
        }
        for cells in body:
            if all(set(cell) <= set("-: ") for cell in cells):
                continue
            named, candidate = _candidate(cells, columns, reached, decisions)
            key = named or "The whole of it"
            parts.setdefault(key, {"part": key, "candidates": []})["candidates"].append(candidate)
    return parts


def _resting_on(decisions: list[Any], parts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Each dependency decision with what it chose, why, and the candidates it weighed.

    A candidate is cited where the decision's own words reach it, so one described in other
    words is absent from `cites` rather than joined by guesswork.
    """
    return [
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
    ]


def read_research(
    root: str | Path, brief: Any, reached: set[str] | None = None
) -> dict[str, Any] | None:
    """`research.md` as the page draws it: the deciding factor, the parts, and what rests on them.

    ``reached`` is the library facilities the project's runs recorded, for marking a candidate
    adopted that nothing reached. A caller that has already read the runs passes what it read;
    one that has not leaves it out and this opens every manifest itself.
    """
    from ..conformance.artifacts import RESEARCH_SECTIONS
    from ..conformance.checks import _section_of
    from ..conformance.produced import produced_across

    path = Path(root).expanduser() / "research.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # What the runs reached, for marking an adopted candidate that nothing did. The report
    # prints the same join in words (`docs/conformance.md` §4.4).
    if reached is None:
        reached = produced_across(Path(root).expanduser() / "runs").facilities

    decisions = [
        d
        for d in (getattr(brief, "decisions", ()) or ())
        if getattr(d, "kind", None) == "dependency"
    ]
    parts = _survey(text, decisions, reached)
    quoted = _section_of(text, RESEARCH_SECTIONS[3]) or ""
    return {
        "turns_on": (_section_of(text, RESEARCH_SECTIONS[2]) or "").strip(),
        "parts_said": (_section_of(text, RESEARCH_SECTIONS[0]) or "").strip(),
        "parts": list(parts.values()),
        "said": quoted.strip(),
        "resting_on": _resting_on(decisions, parts),
    }
