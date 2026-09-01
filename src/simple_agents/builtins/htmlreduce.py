"""A web page reduced to the text worth sending to a model.

Markup is mostly navigation, script and styling. What a page is read for is its prose, its
tables, and whatever structured data it declared. This turns one into the other, in the
standard library, so no HTML dependency is added for it.

Reduction never raises. A page that will not parse cleanly yields whatever was read before the
trouble, and a page holding nothing yields nothing, which is a fact about the page.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Iterable, Sequence
from urllib.parse import urljoin, urlsplit

__all__ = ["reduce_html", "Reduced", "PageLink", "DEFAULT_ORDER"]

# Nothing inside these is content, and script is where most of a page's bytes are.
SKIPPED = frozenset(
    {"script", "style", "noscript", "svg", "canvas", "iframe", "head", "nav", "footer"}
)

# A newline goes before and after these, so a run of divs does not become one long line.
BLOCK = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "header",
        "main",
        "ul",
        "ol",
        "li",
        "br",
        "hr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "thead",
        "tbody",
        "caption",
        "form",
        "figure",
        "blockquote",
        "dl",
        "dt",
        "dd",
        "details",
        "summary",
        "select",
        "option",
    }
)

DEFAULT_ORDER = ("tables", "json_ld", "text")
"""What ``as_prompt`` renders, and in what order. Anything left out is not rendered."""

# Alt text shorter than this is decorative, and a page has many of them.
MIN_ALT_CHARS = 12

WHITESPACE = re.compile(r"[ \t\r\f\v]+")
BLANK_LINES = re.compile(r"\n{3,}")


@dataclass(frozen=True, slots=True)
class PageLink:
    """One link on a page: where it goes, and what it was labelled."""

    url: str
    text: str


@dataclass(slots=True)
class Reduced:
    """What a page held, in the four shapes worth sending to a model separately.

    ``text`` is the prose with markup removed. ``tables`` is each table as rows of cells.
    ``json_ld`` is the page's ``application/ld+json`` blocks, parsed and otherwise untouched.
    ``links`` is every link to the page's own host::

        reduced = reduce_html(body, base_url=url)
        reduced.tables[0]                       # [['Size', 'Chest'], ['M', '52cm']]
        reduced.links_matching(("size guide",))
        reduced.as_prompt(max_chars=20_000)

    The parts are separate because which of them matters is the project's to decide: a size
    chart is a table, an article is prose, and a listing is its structured data.
    """

    text: str = ""
    tables: list[list[list[str]]] = field(default_factory=list)
    json_ld: list[Any] = field(default_factory=list)
    links: list[PageLink] = field(default_factory=list)

    def links_matching(self, words: Iterable[str]) -> list[PageLink]:
        """The links whose url or label contains one of ``words``, compared lowercased::

            reduced.links_matching(("size guide", "measurements"))

        A page often puts what is wanted on a second page and links to it, and this is how
        that link is found. Empty ``words`` matches nothing.
        """
        wanted = [word.lower() for word in words if word]
        if not wanted:
            return []
        return [
            link
            for link in self.links
            if any(word in f"{link.text} {link.url}".lower() for word in wanted)
        ]

    def as_prompt(
        self,
        max_chars: int | None = None,
        *,
        order: Sequence[str] = DEFAULT_ORDER,
    ) -> str:
        """The page as one string, each part under a heading, in ``order``.

        ``order`` names the parts to render and the sequence they appear in, so what survives
        truncation is the project's choice::

            reduced.as_prompt(20_000)                              # tables, then data, prose
            reduced.as_prompt(20_000, order=("text", "tables"))    # prose first
            reduced.as_prompt(order=("tables",))                   # tables alone

        The names are ``tables``, ``json_ld``, ``text`` and ``links``. ``max_chars`` truncates
        the whole string and says so where it did; ``None`` returns all of it.
        """
        parts: list[str] = []
        for name in order:
            rendered = self._render(name)
            if rendered:
                parts.append(rendered)
        whole = "\n\n".join(parts)
        if max_chars is None or len(whole) <= max_chars:
            return whole
        return whole[:max_chars] + f"\n\n[truncated at {max_chars} characters]"

    def _render(self, name: str) -> str:
        if name == "tables" and self.tables:
            rendered = "\n\n".join(
                f"[table {i + 1}]\n" + "\n".join(" | ".join(row) for row in table)
                for i, table in enumerate(self.tables)
            )
            return f"=== TABLES ===\n{rendered}"
        if name == "json_ld" and self.json_ld:
            blocks = "\n".join(
                json.dumps(block, ensure_ascii=False, default=str) for block in self.json_ld
            )
            return f"=== STRUCTURED DATA ===\n{blocks}"
        if name == "text" and self.text:
            return f"=== PAGE TEXT ===\n{self.text}"
        if name == "links" and self.links:
            listed = "\n".join(f"  {link.url}  ({link.text})" for link in self.links)
            return f"=== LINKS ===\n{listed}"
        return ""


class _Reader(HTMLParser):
    """Walks the markup once, collecting the four parts as it goes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.tables: list[list[list[str]]] = []
        self.json_ld: list[Any] = []
        self.links: list[tuple[str, list[str]]] = []
        self._skip_depth = 0
        self._in_ld_json = False
        self._ld_buffer: list[str] = []
        # A stack, because pages nest tables inside layout tables.
        self._table_stack: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._link: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            if "ld+json" in (dict(attrs).get("type") or "").lower():
                self._in_ld_json = True
                self._ld_buffer = []
                return
        if tag in SKIPPED:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "table":
            self._table_stack.append([])
        elif tag == "tr" and self._table_stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._link = (href, [])
                self.links.append(self._link)
        elif tag == "img":
            # Alt text is sometimes the only place a chart's numbers are written.
            alt = dict(attrs).get("alt")
            if alt and len(alt) > MIN_ALT_CHARS:
                self.chunks.append(f"[image: {alt}]")
        if tag in BLOCK:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_ld_json:
            self._in_ld_json = False
            self._absorb_ld("".join(self._ld_buffer))
            return
        if tag in SKIPPED:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "a":
            self._link = None
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(WHITESPACE.sub(" ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._table_stack and any(cell for cell in self._row):
                self._table_stack[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._table_stack:
            finished = self._table_stack.pop()
            # A one-row table is layout rather than data.
            if len(finished) > 1:
                self.tables.append(finished)
        if tag in BLOCK:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_ld_json:
            self._ld_buffer.append(data)
            return
        if self._skip_depth or not data.strip():
            return
        if self._link is not None:
            self._link[1].append(data)
        if self._cell is not None:
            self._cell.append(data)
        else:
            self.chunks.append(data)

    def _absorb_ld(self, raw: str) -> None:
        try:
            self.json_ld.append(json.loads(raw))
        except (ValueError, RecursionError):
            # A malformed block is one source of data missing, not a failed read.
            pass


def reduce_html(body: str, base_url: str = "") -> Reduced:
    """One page's markup, reduced to its text, tables, structured data and links::

        reduced = reduce_html(response_body, base_url="https://example.com/product")
        reduced.as_prompt(20_000)

    ``base_url`` resolves relative links and decides which host is the page's own. Without it,
    links are kept as they were written and none is dropped.

    Script, style, navigation and footers are dropped. Tables keep their structure, a table of
    one row is treated as layout, image alt text is kept where it is long enough to be a
    description, and ``application/ld+json`` blocks are parsed and returned as they are. What
    those blocks mean is the project's to read: no vocabulary is interpreted here.

    Only links to the page's own host are kept, so a page cannot widen what an agent reaches
    by linking elsewhere. Whether any of them may be fetched is still the fetch tool's
    decision.
    """
    reader = _Reader()
    try:
        reader.feed(body)
        reader.close()
    except AssertionError:
        # HTMLParser asserts on some malformed input. Keep whatever was read before it.
        pass
    text = WHITESPACE.sub(" ", "".join(reader.chunks))
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = BLANK_LINES.sub("\n\n", text).strip()
    return Reduced(
        text=text,
        tables=reader.tables,
        json_ld=reader.json_ld,
        links=_same_host_links(reader.links, base_url),
    )


def _same_host_links(links: list[tuple[str, list[str]]], base_url: str) -> list[PageLink]:
    """The page's links to its own host, absolute and in the order they appeared, once each."""
    origin = urlsplit(base_url).netloc.lower() if base_url else ""
    found: dict[str, PageLink] = {}
    for href, parts in links:
        label = WHITESPACE.sub(" ", "".join(parts)).strip()
        absolute = urljoin(base_url, href) if base_url else href
        if origin and urlsplit(absolute).netloc.lower() != origin:
            continue
        if absolute not in found:
            found[absolute] = PageLink(url=absolute, text=label)
    return list(found.values())
