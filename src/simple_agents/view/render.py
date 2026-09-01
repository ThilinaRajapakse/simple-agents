"""Turning assembled data into one self-contained HTML file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .assemble import assemble

DEFAULT_OUT = "view.html"

_TEMPLATE = Path(__file__).parent / "template.html"


def render(data: dict[str, Any], *, title: str | None = None) -> str:
    """The page for one project's assembled data, as a string.

    ::

        html = render(assemble("."))
    """
    template = _TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, default=str).replace("</", "<\\/")
    shown = title or f"{data.get('project') or 'project'} · view"
    return template.replace("__TITLE__", shown).replace("__DATA__", payload)


def generate_view(
    root: str | Path = ".", *, out: str | Path | None = None, title: str | None = None
) -> Path:
    """Assemble one project and write its page. Returns the path written.

    ::

        generate_view(".")                          # <root>/view.html
        generate_view(".", out="docs/system.html")  # somewhere else
    """
    root = Path(root).expanduser()
    target = Path(out).expanduser() if out is not None else root / DEFAULT_OUT
    target.write_text(render(assemble(root), title=title), encoding="utf-8")
    return target
