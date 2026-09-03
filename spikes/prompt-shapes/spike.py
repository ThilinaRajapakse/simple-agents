"""Spike: can a recorded-assembly prompt API express every prompt shape?

Bar: each corpus entry is written twice, once the way it is written today (an f-string or a
message list) and once through the proposed API, and the two must render byte-identical.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

SYNTAX = "brace"  # or "angle"


def _pattern() -> re.Pattern[str]:
    return re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}" if SYNTAX == "brace" else r"<<([a-zA-Z_][a-zA-Z0-9_]*)>>")


@dataclass
class Value:
    """One interpolated value: data the template drops in."""
    name: str
    text: str
    cap: int | None = None

    @property
    def rendered(self) -> str:
        if self.cap is not None and len(self.text) > self.cap:
            return self.text[: self.cap]
        return self.text

    def record(self) -> dict[str, Any]:
        held: dict[str, Any] = {"name": self.name, "chars": len(self.rendered)}
        if self.cap is not None and len(self.text) > self.cap:
            held["capped_from"] = len(self.text)
        return held


@dataclass
class Part:
    """Fixed text with named holes, and what went in them."""
    template: str
    values: dict[str, Any] = field(default_factory=dict)
    name: str | None = None

    @property
    def rendered(self) -> str:
        """Single pass. A value is inserted verbatim and never rescanned."""
        text, out, i, named = self.template, [], 0, set()
        opener, closer = ("{", "}") if SYNTAX == "brace" else ("<<", ">>")
        n = len(opener)
        while i < len(text):
            if text.startswith(opener * 2, i):
                out.append(opener)
                i += 2 * n
                continue
            if text.startswith(closer * 2, i):
                out.append(closer)
                i += 2 * n
                continue
            if text.startswith(opener, i):
                end = text.find(closer, i + n)
                key = text[i + n:end] if end >= 0 else ""
                if end < 0 or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", key):
                    raise KeyError(
                        f"a bare {opener!r} at character {i} of the template. Double it as "
                        f"{opener * 2!r} to write one, or name a value: {opener}name{closer}."
                    )
                if key not in self.values:
                    raise KeyError(f"template names {opener}{key}{closer} and no value was given")
                out.append(_render(self.values[key]))
                named.add(key)
                i = end + n
                continue
            out.append(text[i])
            i += 1
        unused = set(self.values) - named
        if unused:
            raise KeyError(f"values given and not named by the template: {sorted(unused)}")
        return "".join(out)

    def record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "template": self.template,
            "values": [_record(v) for v in self.values.values()],
        }


def _render(one: Any) -> str:
    if isinstance(one, (Value, Part, Repeat)):
        return one.rendered
    if isinstance(one, list):
        return "".join(_render(x) for x in one)
    return str(one)


def _record(one: Any) -> Any:
    if isinstance(one, (Value, Part, Repeat)):
        return one.record()
    if isinstance(one, list):
        return [_record(x) for x in one]
    return {"literal": str(one)[:40]}


@dataclass
class Repeat:
    """One template rendered once per item."""
    name: str
    template: str
    items: list[Part]
    sep: str = "\n"

    @property
    def rendered(self) -> str:
        return self.sep.join(p.rendered for p in self.items)

    def record(self) -> dict[str, Any]:
        return {"name": self.name, "each": self.template, "items": len(self.items),
                "values": [_record(v) for v in (self.items[0].values.values() if self.items else [])]}


@dataclass
class Msg:
    role: str
    content: Any                      # Part, or a list of blocks
    extra: dict[str, Any] = field(default_factory=dict)

    def wire(self) -> dict[str, Any]:
        if isinstance(self.content, list):
            body: Any = [b.wire() if isinstance(b, Block) else b for b in self.content]
        else:
            body = _render(self.content)
        return {"role": self.role, "content": body, **self.extra}


@dataclass
class Block:
    """One non-text block: an image, a document, a tool result."""
    raw: dict[str, Any]
    text: Part | None = None

    def wire(self) -> dict[str, Any]:
        if self.text is not None:
            return {**self.raw, "text": self.text.rendered}
        return dict(self.raw)


class Ctx:
    """The surface a prompt function reaches."""

    def value(self, name: str, text: Any, cap: int | None = None) -> Value:
        return Value(name, "" if text is None else str(text), cap)

    def part(self, name: str, template: str, **values: Any) -> Part:
        return Part(template, values, name)

    def each(self, name: str, items: list[Any], template: str, *, sep: str = "\n",
             **build: Any) -> Part:
        made = [Part(template, {k: fn(item, i) for k, fn in build.items()}, f"{name}[{i}]")
                for i, item in enumerate(items)]
        held = Repeat(name, template, made, sep)
        return held

    def join(self, name: str, parts: list[Any], *, sep: str = "\n\n") -> Part:
        keys = {f"p{i}": p for i, p in enumerate(parts)}
        template = sep.join("{" + k + "}" if SYNTAX == "brace" else f"<<{k}>>" for k in keys)
        return Part(template, keys, name)

    def system(self, template: str, **values: Any) -> Msg:
        return Msg("system", Part(template, values))

    def user(self, template: str, **values: Any) -> Msg:
        return Msg("user", Part(template, values))

    def assistant(self, template: str, **values: Any) -> Msg:
        return Msg("assistant", Part(template, values))

    def prompt(self, template: str, **values: Any) -> list[Msg]:
        return [Msg("user", Part(template, values))]

    def turns(self, history: list[dict[str, Any]]) -> list[Msg]:
        return [Msg(h["role"], Part(h["content"]), {k: v for k, v in h.items()
                                                    if k not in ("role", "content")})
                for h in history]

    def blocks(self, role: str, blocks: list[Any], **extra: Any) -> Msg:
        return Msg(role, blocks, extra)


def wire(prompt: Any) -> list[dict[str, Any]]:
    """What goes on the wire, from either style."""
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    out = []
    for one in prompt:
        out.append(one.wire() if isinstance(one, Msg) else dict(one))
    return out
