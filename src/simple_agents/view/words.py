"""Turning one value into the words a page sentence is made of.

Each is used by more than one family of findings, so they sit apart from all of them::

    _rate(0.842, "rate")     # '84.2%'
    fmt_runs(1)              # '1 run'
"""

from __future__ import annotations

from typing import Any


def _clip(text: str, limit: int = 90) -> str:
    """A quote cut at a word, with the cut shown, so nothing ends mid-sentence unmarked."""
    text = str(text)
    if len(text) <= limit:
        return text
    held = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return held + "…"


def _rate(value: Any, unit: str | None) -> str:
    """A figure as the page prints it: a percentage for a rate, the number otherwise."""
    if value is None:
        return "no figure"
    if unit == "rate":
        return f"{value * 100:.1f}%"
    return f"{value:,.6g}" + (f" {unit}" if unit else "")


def fmt_runs(count: int) -> str:
    return f"{count:,} run" + ("" if count == 1 else "s")
