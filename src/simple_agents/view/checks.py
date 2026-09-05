"""The conformance checks as a board, for the `ship` page.

`simple-agents check` prints the same verdicts in a terminal, and the builder is not the one
reading a terminal. This runs the suite over the project and gives the page one row per
check: the entry's own title, whether it passed, failed or does not apply at this tier, and
on a failure what to do about it.

::

    read_checks(".")
    # {'ok': False, 'counts': {...}, 'rows': [{'entry': 'FT-31', 'outcome': 'failed', ...}]}

``None`` where the checks cannot run at all, which is a project whose brief is missing or
declares no tier. Which gates apply is then unknown, and the page says so rather than showing
an empty board.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["read_checks"]

# Where a failing check shows on the page, so a row can go there. Anything not named here
# carries no link, which is honest: most checks are about a file rather than about a region.
_WHERE: dict[str, dict[str, str]] = {
    "FT-31": {"section": "product"},
    "FT-34": {"section": "product"},
    "FT-38": {"section": "claims"},
    "FT-39": {"section": "conversation"},
    "FT-40": {"section": "progress"},
    "FT-42": {"section": "constants"},
    "FT-24": {"section": "questions"},
}


def read_checks(root: str | Path) -> dict[str, Any] | None:
    """Every conformance check over one project, as the page draws it."""
    from ..conformance import run_checks
    from ..errors import ConfigurationError

    try:
        report = run_checks(Path(root).expanduser())
    except (ConfigurationError, OSError, ValueError):
        return None

    rows = []
    counts = {"passed": 0, "failed": 0, "not_applicable": 0, "blocked": 0}
    for check in report.checks:
        outcome = str(check.outcome.value if hasattr(check.outcome, "value") else check.outcome)
        counts[outcome] = counts.get(outcome, 0) + 1
        rows.append(
            {
                "entry": check.entry_id,
                "name": check.name,
                "outcome": outcome,
                "tier": check.tier,
                "detail": check.detail or "",
                # The finding carries the whole instruction; the page shows the first sentence and
                # keeps the rest for the reader who opens it.
                "says": [f.message for f in check.findings][:2],
                "where": _WHERE.get(check.entry_id),
            }
        )
    order = {"failed": 0, "blocked": 1, "passed": 2, "not_applicable": 3}
    rows.sort(key=lambda row: (order.get(row["outcome"], 4), row["entry"]))
    return {
        "ok": report.ok,
        "tier": report.tier,
        "counts": counts,
        "rows": rows,
        "reading": report.reading,
        # Read while the checks ran, so the research page's own join opens no manifest again.
        "facilities": sorted(report.facilities),
    }
