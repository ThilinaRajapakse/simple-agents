"""`simple-agents view`: one page showing a project's system, for the builder.

Everything on the page is computed from the project itself: the pipelines `agent.py`
declares, the brief, `comments.toml`, and the run record where one exists. Nothing on it is
maintained by hand, so it cannot drift from the project the way prose does.

::

    from simple_agents.view import generate_view

    generate_view(".")               # writes view.html in the project root

The command form is `simple-agents view`, and `simple-agents check` regenerates the page at
every gate.
"""

from __future__ import annotations

from .assemble import assemble
from .render import generate_view, render

__all__ = ["assemble", "render", "generate_view"]
