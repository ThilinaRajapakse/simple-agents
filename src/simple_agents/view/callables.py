"""Every function a project declares, read from the code the page already imported.

At the `shape` gate nothing has run, so the run record says nothing and the evaluation says
nothing. What exists is the code, and the code says more than the page was reading: a tool's
signature, what it returns, what its author wrote about it, and where it lives. None of it is
declared twice, so none of it can drift.

A return annotation naming a model is expanded into its fields, which is the closest thing to
"what a row of this store looks like" that exists before anything runs. A tool that annotates
nothing says so, which is a finding rather than a blank.
"""

from __future__ import annotations

import inspect
import typing
from pathlib import Path
from typing import Any
from .words import _clip

__all__ = ["read_callable", "signature_line", "MAX_SOURCE_LINES"]

MAX_SOURCE_LINES = 120
"""How much of one function's body the page carries. A longer one is clipped and says so."""

MAX_PARAMETERS = 12
"""Parameters listed from one signature."""

MAX_DOC_CHARS = 480
"""How much of a docstring travels. The whole of it is in the source, one click away."""

_LIBRARY = Path(__file__).resolve().parent.parent
"""Where the library itself lives, so a builtin tool is not shown as the project's own code."""


def _where(fn: Any) -> dict[str, Any] | None:
    """The file and line a function was written at, and whether it is the project's own."""
    try:
        path = inspect.getsourcefile(fn)
        line = inspect.getsourcelines(fn)[1]
    except (OSError, TypeError):
        return None
    if not path:
        return None
    resolved = Path(path).resolve()
    library = _LIBRARY in resolved.parents or resolved == _LIBRARY
    return {
        "file": resolved.name,
        "line": line,
        "at": f"{resolved.name}:{line}",
        "library": library,
    }


def _source(fn: Any) -> dict[str, Any] | None:
    """The function's body, clipped, with how much was left off."""
    try:
        text = inspect.getsource(fn)
    except (OSError, TypeError):
        return None
    lines = text.splitlines()
    if not lines:
        return None
    indent = min((len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()), default=0)
    trimmed = [ln[indent:] if len(ln) > indent else ln for ln in lines]
    return {
        "text": "\n".join(trimmed[:MAX_SOURCE_LINES]),
        "lines": len(lines),
        "clipped": max(0, len(lines) - MAX_SOURCE_LINES),
    }


def _fields_of(annotation: Any, name_of: Any) -> list[dict[str, Any]] | None:
    """A return type's fields where it names a model, else ``None``.

    This is what lets a store card say what a row looks like without anything having run: the
    tool that reads the store declares what it hands back, and a model says what is in it.
    """
    inner = annotation
    origin = typing.get_origin(annotation)
    if origin in (list, set, tuple, frozenset):
        args = [a for a in typing.get_args(annotation) if a is not Ellipsis]
        inner = args[0] if args else None
    fields = getattr(inner, "model_fields", None)
    if not isinstance(fields, dict):
        return None
    return [{"name": key, "type": name_of(info.annotation)} for key, info in fields.items()]


def _parameters(fn: Any, hints: dict[str, Any], name_of: Any) -> list[dict[str, Any]]:
    """What the function takes, in order, with the types it annotated."""
    try:
        signature = inspect.signature(fn)
    except (TypeError, ValueError):
        return []
    found = []
    for key, parameter in list(signature.parameters.items())[:MAX_PARAMETERS]:
        annotation = hints.get(key)
        found.append(
            {
                "name": key,
                "type": name_of(annotation) if annotation is not None else None,
                "has_default": parameter.default is not inspect.Parameter.empty,
            }
        )
    return found


def _hints(fn: Any) -> dict[str, Any]:
    try:
        return typing.get_type_hints(fn)
    except Exception:  # noqa: BLE001 - an annotation naming something unresolvable
        return {}


def _one_line(fn: Any) -> str:
    return " ".join((fn.__doc__ or "").strip().split("\n")[0].split())


def read_callable(fn: Any, name_of: Any, *, redact: Any = None) -> dict[str, Any] | None:
    """What the code says about one function, for the page to show beside its name.

    ``name_of`` writes a type the way the builder reads it, which is the view's own
    ``_type_name``. ``redact`` is applied to the source text before it travels, so a project
    with a credential written into a function body does not publish it in ``view.html``.

    ``None`` where the object has no readable source, which is a lambda, a callable object,
    and anything built at run time.
    """
    if fn is None or not callable(fn):
        return None
    where = _where(fn)
    hints = _hints(fn)
    returns = hints.get("return")
    source = _source(fn)
    if source is not None and redact is not None:
        source["text"] = redact(source["text"])
    return {
        "name": getattr(fn, "__name__", None) or type(fn).__name__,
        "parameters": _parameters(fn, hints, name_of),
        "returns": name_of(returns) if returns is not None else None,
        "return_fields": _fields_of(returns, name_of) if returns is not None else None,
        "says": _one_line(fn),
        "doc": _clip(" ".join((fn.__doc__ or "").split()), MAX_DOC_CHARS) or None,
        "where": where,
        "source": source,
    }


def signature_line(card: dict[str, Any] | None) -> str:
    """One function as a line the page prints: ``handbook_lookup(question: str) -> list``."""
    if not card:
        return ""
    written = ", ".join(
        p["name"] + (f": {p['type']}" if p["type"] else "") for p in card["parameters"]
    )
    tail = f" -> {card['returns']}" if card["returns"] else ""
    return f"{card['name']}({written}){tail}"
