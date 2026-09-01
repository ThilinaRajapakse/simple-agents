"""The staging of the elicitation, and the idea the builder confirmed.

The page carried the answers and not their structure: which questions a stage asks, which are
still ahead, and which entries are deferred and to where. Elicitation is staged, and the
staging was invisible on the one surface a builder reads.

::

    read_stages(brief)["brainstorm"]["rows"][0]
    # {'name': 'what_it_does', 'title': 'What it does', 'state': 'answered', ...}

Four states, and they are not the brief's three: an unanswered question this stage asks is
open, and one a later stage asks has not been put yet. Both read as unanswered in
the brief, and only one of them is anybody's business today.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["read_stages", "read_idea"]


def _state(entry: Any, asked_here: bool) -> str:
    """One question's state as the page draws it."""
    if entry is not None and getattr(entry, "status", None) == "answered":
        return "answered"
    if entry is not None and getattr(entry, "status", None) == "deferred":
        return "deferred"
    return "open" if asked_here else "ahead"


def read_stages(brief: Any) -> dict[str, Any] | None:
    """Every stage's questions, in the four states, with the counts under each.

    ``None`` where the project has no brief, since which questions apply follows from the tier
    it claims. A stage the tier does not have is left out entirely.
    """
    if brief is None:
        return None
    from ..conformance.elicitation import questions_at
    from ..conformance.stages import stages_for

    tier = getattr(brief, "tier", None)
    every = stages_for(tier)
    at = getattr(brief, "stage", None)
    reached = list(every).index(at) if at in every else -1
    held: dict[str, Any] = {}
    for index, stage in enumerate(every):
        asked = [q for q in questions_at(stage, tier) if q.stage == stage]
        rows = []
        for question in asked:
            entry = brief.entry(question.name) if hasattr(brief, "entry") else None
            rows.append(
                {
                    "name": question.name,
                    "title": question.title,
                    "asks": question.ask.split("\n")[0][:200],
                    "required": question.required,
                    "again": question.re_asked_each_stage,
                    "state": _state(entry, index <= reached if reached >= 0 else False),
                    "answer": str(getattr(entry, "answer", "") or "")[:600],
                    "deferred_to": getattr(entry, "deferred_to", None),
                }
            )
        answered = sum(1 for row in rows if row["state"] == "answered")
        held[stage] = {
            "stage": stage,
            "rows": rows,
            "asks": len(rows),
            "answered": answered,
            "open": sum(1 for row in rows if row["state"] == "open"),
            "deferred": sum(1 for row in rows if row["state"] == "deferred"),
            "reached": reached >= 0 and index <= reached,
            "here": stage == at,
        }
    return held


def read_idea(root: str | Path, brief: Any) -> dict[str, Any] | None:
    """``idea.md``'s sections, and the stage the builder last confirmed it at.

    ``None`` where the file is absent, which is a project before anybody wrote one down.
    ``stale`` says the confirmation names an earlier stage than the project is at, which is
    what FT-29 fails on.
    """
    from ..conformance.artifacts import IDEA_SECTIONS
    from ..conformance.checks import _section_of
    from ..conformance.stages import STAGES

    path = Path(root).expanduser() / "idea.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    confirmed = getattr(brief, "understanding_confirmed_at", None) if brief else None
    at = getattr(brief, "stage", None) if brief else None
    stale = bool(
        confirmed
        and at in STAGES
        and confirmed in STAGES
        and STAGES.index(confirmed) < STAGES.index(at)
    )
    return {
        "sections": [
            {"title": name, "body": (_section_of(text, name) or "").strip()[:1200]}
            for name in IDEA_SECTIONS
        ],
        "confirmed_at": confirmed,
        "stale": stale,
        "empty": [name for name in IDEA_SECTIONS if not (_section_of(text, name) or "").strip()],
    }
