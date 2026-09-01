"""Checking that a claim is backed by material the run observably touched.

An agent that cites a source it never opened, or quotes text the source does not contain, is
asserting something it did not establish (FT-09, FT-10). Both are checkable from what the run
already records: which tools were called, with what, and what they returned.

What counts as grounded is the project's to decide. An exact span, the same host, a matching
quote and how many strikes to allow are all task-specific. What is here is the plumbing those
decisions are written in: comparing text that is written two ways, and asking whether a URL was
read.

``docs/tools.md`` §5 shows the check these are written into.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit, urlunsplit

__all__ = ["contains_normalised", "normalise_text", "url_was_read", "urls_read", "same_url"]

_SEPARATORS = re.compile(r"[^0-9a-z]+")


def normalise_text(text: str) -> str:
    """Text reduced to the form :func:`contains_normalised` compares on.

    Compatibility-decomposed, stripped of the combining marks that decomposition exposes,
    casefolded, and every run of characters that is not a letter or a digit replaced by one
    space::

        normalise_text("O₂ (“saturation”)")   # 'o2 saturation'
        normalise_text("Beyoncé")             # 'beyonce'

    Separators become one space rather than nothing, so words are not joined across them.

    Stripping combining marks is what folds an accent onto its base letter, so ``"café"``
    reduces to ``"cafe"``. **Only ``0-9`` and ``a-z`` survive**, so text in a script that does
    not decompose to them reduces to the empty string. A project comparing such text compares
    on its own rule.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    folded = unicodedata.normalize("NFKC", without_marks).casefold()
    return _SEPARATORS.sub(" ", folded).strip()


def contains_normalised(haystack: str, needle: str) -> bool:
    """Whether ``needle`` appears in ``haystack``, ignoring case, accents and punctuation.

    For checking that a quoted span is really in the passage it was taken from::

        if not contains_normalised(passage, answer.quote):
            return Answer(answer=Unknown(reason="the quote is not in the cited passage"))

    Both sides go through :func:`normalise_text`, so ``"O₂"`` matches ``"O2"``, a curly quote
    matches a straight one, and ``"Beyoncé"`` matches ``"Beyonce"`` in either direction.

    **Words are not joined across a separator**, so ``"therapist"`` does not match
    ``"the rapist"``, and equally ``"O₂"`` does not match ``"O 2"``. A project whose sources
    write one word two ways compares on its own rule.

    An empty ``needle`` is never contained: a claim with nothing in it is not grounded.
    """
    wanted = normalise_text(needle)
    return bool(wanted) and wanted in normalise_text(haystack)


def same_url(left: str, right: str) -> bool:
    """Whether two addresses name the same page.

    The scheme and host are compared lowercased, a leading ``www.`` is ignored, a trailing
    slash on the path is ignored, and a fragment is dropped. A query string is part of the
    address and is compared::

        same_url("https://WWW.Example.com/tee/", "https://example.com/tee")   # True
    """
    return _canonical(left) == _canonical(right) != ""


def urls_read(ctx: Any) -> list[str]:
    """Every URL this node passed to a tool call that succeeded, as it was passed.

    In call order, once each. What a refusal message names, so the model is told which
    addresses it did open::

        return f"evidence_url must be a page read in this step. Read: {urls_read(ctx)}."

    Reads ``ctx.tool_calls``, which an ``AgentNode``'s finish check is given. A failed call is
    left out: a page the agent tried and did not get is not one it read.
    """
    found: dict[str, str] = {}
    for call in getattr(ctx, "tool_calls", ()) or ():
        if not getattr(call, "ok", False):
            continue
        for value in (getattr(call, "arguments", None) or {}).values():
            if isinstance(value, str) and _canonical(value):
                found.setdefault(_canonical(value), value)
    return list(found.values())


def url_was_read(ctx: Any, url: str) -> bool:
    """Whether this URL was an argument to a tool call this node made and that succeeded.

    The check behind a rule that an answer must cite a page the node opened::

        def cites_a_page_it_read(answer: Finding, ctx: AgentContext) -> str | None:
            if url_was_read(ctx, answer.evidence_url):
                return None
            return f"evidence_url must be a page read in this step. Read: {urls_read(ctx)}."

    Addresses are compared with :func:`same_url`, so a trailing slash or a ``www.`` does not
    make a page the agent read look like one it did not. Any tool counts: what matters is that
    the run fetched the page, not which tool did it.
    """
    return any(same_url(candidate, url) for candidate in urls_read(ctx))


def _canonical(url: str) -> str:
    """One address in the form two of them are compared in, or ``""`` if it is not one.

    Only an absolute ``http`` or ``https`` address is one, so a query string that happens to
    mention a site is not mistaken for a page that was read.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return ""
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))
