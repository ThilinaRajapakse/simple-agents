"""Prompts written as fixed text with named values, so the record holds both.

A prompt function returns a `Prompt`. The fixed text is the instruction, written in the
project's code; the values are the data dropped into it at run time. The library keeps the two
apart, so a run records what the model was told as well as what it was sent, and one step's
instruction can be read on its own across every example::

    from simple_agents import Prompt, Value

    def build_prompt(inputs, ctx) -> Prompt:
        return Prompt.user(
            "Plan {days} days in {city} for a traveller who likes {tastes}.",
            days=inputs["days"],
            city=inputs["city"],
            tastes=Value(inputs["notes"], cap=220),
        )

A gap is written ``{name}`` and is filled by the keyword of that name. A literal brace is
doubled, ``{{`` and ``}}``. Substitution is one pass and a value is inserted exactly as it is,
so a value carrying braces of its own needs no escaping.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import re
import textwrap
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

from .errors import ConfigurationError

__all__ = ["Prompt", "Value", "Section"]

_NAME = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")

ROLES = ("system", "user", "assistant")
"""The roles a message can carry. A backend that names others takes them through `Prompt.turns`."""


@dataclass(frozen=True)
class Value:
    """One value dropped into a prompt, where the keyword alone will not do.

    A plain keyword is already a value, so this is for the cases that carry more::

        Prompt.user("Notes: {notes}", notes=Value(text, cap=220, origin="traveller_files"))

    ``cap`` cuts the text at that many characters and records what was cut, so a truncation is
    visible in the record rather than silent. ``origin`` says where the text came from, in the
    builder's own words, and reaches the page beside the value.
    """

    text: Any
    cap: int | None = None
    origin: str | None = None

    def __post_init__(self) -> None:
        if self.cap is not None and self.cap < 1:
            raise ConfigurationError(
                f"Value(cap={self.cap!r}) cuts the text to nothing. Pass a positive number of "
                f"characters, or leave cap out to send the text whole."
            )

    @property
    def written(self) -> str:
        text = str(self.text)
        return text[: self.cap] if self.cap is not None and len(text) > self.cap else text

    def record(self, name: str) -> dict[str, Any]:
        text = str(self.text)
        held: dict[str, Any] = {"name": name, "chars": len(self.written)}
        if self.cap is not None and len(text) > self.cap:
            held["capped_from"] = len(text)
        if self.origin:
            held["origin"] = self.origin
        return held


@dataclass(frozen=True, init=False)
class Section:
    """A named piece of fixed text with its own values, used as a value in another piece.

    A section is how one part of a prompt is named, so a comment or a decision can be about
    that part rather than about the whole::

        Prompt.user(
            "Answer the question.\\n\\n{context}\\n\\n{question}",
            context=Section("context", "Use only these notes:\\n{notes}", notes=notes),
            question=question,
        )

    `Section.joined` builds a variable number of them, which is a list of passages, a plan's
    steps, or a tree rendered to whatever depth the data has.
    """

    name: str
    template: str
    values: Mapping[str, Any]
    parts: tuple[Any, ...]
    separator: str

    @classmethod
    def joined(cls, name: str, parts: Iterable[Any], *, separator: str = "\n") -> Section:
        """A section built from a list, joined by ``separator``::

            Section.joined("passages", [
                Section("passage", "[{n}] {text}", n=i + 1, text=chunk.text)
                for i, chunk in enumerate(chunks)
            ])

        The parts may be sections, values or plain data. Where every part carries the same
        template, the record keeps that template once and counts the parts.
        """
        made = cls(name)
        object.__setattr__(made, "parts", tuple(parts))
        object.__setattr__(made, "separator", separator)
        return made

    # `name` and `template` are positional-only, so a value may carry either name. Every
    # keyword reaching here fills a gap in the text, and a prompt that says {template} is
    # ordinary.
    def __init__(self, name: str, template: str = "", /, **values: Any) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "template", template)
        object.__setattr__(self, "values", dict(values))
        object.__setattr__(self, "parts", ())
        object.__setattr__(self, "separator", "")

    @property
    def written(self) -> str:
        if self.parts:
            return self.separator.join(_written(part) for part in self.parts)
        where = f"section {self.name!r}" if self.name else "a message"
        return _fill(self.template, self.values, where=where)

    def record(self, name: str | None = None) -> dict[str, Any]:
        held: dict[str, Any] = {"name": name or self.name}
        if self.parts:
            templates = {getattr(p, "template", None) for p in self.parts}
            held["parts"] = len(self.parts)
            if len(templates) == 1 and next(iter(templates)):
                held["each"] = next(iter(templates))
            else:
                held["values"] = [_record_of(p, str(i)) for i, p in enumerate(self.parts)]
            return held
        held["template"] = self.template
        held["values"] = [_record_of(v, key) for key, v in self.values.items()]
        return held


@dataclass(frozen=True)
class _Message:
    role: str
    content: Any
    extra: Mapping[str, Any] = field(default_factory=dict)

    def wire(self) -> Any:
        # A carried message goes on the wire as the object it arrived as. A conversation
        # matches what a node sent against what it holds by identity first, so a copy would
        # be recorded as a second message saying the same thing.
        if isinstance(self.content, _Carried):
            return self.content.source
        if isinstance(self.content, tuple):
            body: Any = [_block(one) for one in self.content]
        else:
            body = _written(self.content)
        return {"role": self.role, "content": body, **dict(self.extra)}

    def record(self) -> dict[str, Any]:
        held: dict[str, Any] = {"role": self.role}
        if isinstance(self.content, tuple):
            held["blocks"] = [
                one.record() if isinstance(one, Section) else {"kind": _kind_of(one)}
                for one in self.content
            ]
        else:
            written = self.content.record()
            held.update({k: v for k, v in written.items() if k != "name" or v})
        if self.extra:
            held["extra"] = sorted(self.extra)
        return held


@dataclass(frozen=True)
class Prompt:
    """What a prompt function returns: the messages one model call is built from.

    One message is the common case, and two messages are built by adding them together::

        Prompt.system("Answer in two sentences.") + Prompt.user("{q}", q=question)

    `Prompt.turns` carries messages a run already recorded, and `Prompt.blocks` carries an
    image, a document or anything else a backend takes as message content rather than as text.
    """

    messages: tuple[_Message, ...] = ()

    @classmethod
    def system(cls, template: str, /, **values: Any) -> Prompt:
        """One system message, built from fixed text and named values."""
        return cls((_Message("system", Section("", template, **values)),))

    @classmethod
    def user(cls, template: str, /, **values: Any) -> Prompt:
        """One user message, built from fixed text and named values::

        Prompt.user("Summarise this in one sentence:\\n\\n{document}", document=text)
        """
        return cls((_Message("user", Section("", template, **values)),))

    @classmethod
    def assistant(cls, template: str, /, **values: Any) -> Prompt:
        """One assistant message, which is how a reply is begun for the model to continue."""
        return cls((_Message("assistant", Section("", template, **values)),))

    @classmethod
    def blocks(cls, role: str, blocks: Sequence[Any]) -> Prompt:
        """One message whose content is a list of blocks rather than text::

            Prompt.blocks("user", [
                {"type": "image", "source": {"data": encoded}},
                Section("ask", "Read the total off this invoice."),
            ])

        A `Section` becomes a text block and every other entry is passed to the backend as it
        is, so a block shape the library does not know about still goes through.
        """
        _refuse_a_role(role, "Prompt.blocks")
        return cls((_Message(role, tuple(blocks)),))

    @classmethod
    def turns(cls, history: Iterable[Mapping[str, Any]]) -> Prompt:
        """Messages a run already recorded, carried into this call as they are::

            Prompt.system("{voice}", voice=persona) + Prompt.turns(thread.messages)

        Nothing here is fixed text the project wrote, so the record marks these as carried and
        the page shows them as conversation rather than as instruction.
        """
        made = []
        for one in history:
            if "role" not in one or "content" not in one:
                raise ConfigurationError(
                    f"Prompt.turns was given {sorted(one)} and a turn needs 'role' and "
                    f"'content'. Pass the messages a Thread or a trajectory recorded."
                )
            made.append(_Message(str(one["role"]), _Carried(one)))
        return cls(tuple(made))

    def marked(self, **fields: Any) -> Prompt:
        """The same prompt with backend fields set on its last message::

            Prompt.system("{voice}", voice=persona).marked(cache_control={"type": "ephemeral"})

        Used for what a backend reads off a message and the library does not model, such as a
        cache marker. The fields travel to the backend unchanged.
        """
        if not self.messages:
            raise ConfigurationError(
                "marked() was called on a prompt with no messages, so there is nothing to mark. "
                "Build a message first: Prompt.system(...).marked(...)."
            )
        last = self.messages[-1]
        marked = replace(last, extra={**dict(last.extra), **fields})
        return Prompt(self.messages[:-1] + (marked,))

    def __add__(self, other: Any) -> Prompt:
        if not isinstance(other, Prompt):
            raise ConfigurationError(
                f"A Prompt was added to {type(other).__name__}, and only another Prompt can "
                f"follow one. Wrap the text: Prompt.user(...)."
            )
        return Prompt(self.messages + other.messages)

    def to_messages(self) -> list[dict[str, Any]]:
        """What goes on the wire: one dict per message, in order."""
        return [one.wire() for one in self.messages]

    def to_record(self) -> dict[str, Any]:
        """What the run records about how this prompt was built.

        One entry per message, each carrying the fixed text, the values that filled it, and
        what any of them cut. `instruction` identifies the whole prompt and `templates` the
        distinct pieces it was built from.
        """
        return {
            "messages": [one.record() for one in self.messages],
            "instruction": self.instruction(),
            "templates": sorted(self.template_digests()),
        }

    def instruction(self) -> str:
        """A digest of everything fixed about this prompt, in the order it is sent.

        This is what identifies a step's instruction across runs and examples: two calls
        differing only in the data that filled them digest alike, and an edit anywhere in the
        fixed text moves it. A prompt built from sections is one instruction rather than one per
        section, and a carried message counts for nothing, so a chat step keeps one instruction
        however long the conversation grows.
        """
        pieces: list[str] = []
        for one in self.messages:
            if isinstance(one.content, _Carried):
                continue
            pieces.append(one.role)
            _texts_of(one.content, pieces)
        return _template_digest("\n".join(pieces))

    def template_digests(self) -> set[str]:
        """A digest of each distinct piece of fixed text this prompt was built from."""
        found: set[str] = set()
        for one in self.messages:
            _digests_of(one.content, found)
        return found


@dataclass(frozen=True)
class _Carried:
    """A message a run already recorded, carried into a call rather than written for it."""

    source: Mapping[str, Any]

    @property
    def written(self) -> Any:
        return self.source.get("content")

    def record(self, name: str | None = None) -> dict[str, Any]:
        return {"carried": True, "chars": len(str(self.source.get("content")))}


def _kind_of(block: Any) -> str:
    if isinstance(block, Mapping):
        return str(block.get("type") or "block")
    return type(block).__name__


def _block(one: Any) -> Any:
    if isinstance(one, Section):
        return {"type": "text", "text": one.written}
    return one


def _written(one: Any) -> str:
    """One value as text, written the way Python writes it.

    A list arrives as ``['a', 'b']`` rather than joined, and `Section.joined` is what joins one.
    ``None`` arrives as ``None`` rather than as nothing, so a value that should have been there
    reads as missing instead of disappearing.
    """
    if isinstance(one, (Section, Value, _Carried)):
        return str(one.written)
    return str(one)


def _record_of(one: Any, name: str) -> dict[str, Any]:
    if isinstance(one, (Section, Value, _Carried)):
        return one.record(name)
    return {"name": name, "chars": len(_written(one))}


def _texts_of(one: Any, into: list[str]) -> None:
    """Every piece of fixed text in one message, in the order it is sent."""
    if isinstance(one, Section):
        into.append(one.template)
        for value in one.values.values():
            _texts_of(value, into)
        for part in one.parts:
            _texts_of(part, into)
    elif isinstance(one, tuple):
        for part in one:
            _texts_of(part, into)


def _digests_of(one: Any, found: set[str]) -> None:
    if isinstance(one, Section):
        if one.template:
            found.add(_template_digest(one.template))
        for value in one.values.values():
            _digests_of(value, found)
        for part in one.parts:
            _digests_of(part, found)
    elif isinstance(one, tuple):
        for part in one:
            _digests_of(part, found)


def _template_digest(template: str) -> str:
    """The identity of one piece of fixed text, which is what runs are compared on."""
    return "sha256:" + hashlib.sha256(template.encode("utf-8")).hexdigest()[:12]


def _refuse_a_role(role: str, where: str) -> None:
    if role not in ROLES:
        raise ConfigurationError(
            f"{where} was given role={role!r}, and the three are {', '.join(ROLES)}. "
            f"A role a backend of its own defines goes through Prompt.turns."
        )


def _fill(template: str, values: Mapping[str, Any], *, where: str) -> str:
    """Fill ``{name}`` gaps in one pass, inserting each value exactly as it is.

    A doubled brace is a literal brace. A value is never rescanned, so a value carrying braces
    of its own arrives unchanged.
    """
    out: list[str] = []
    named: set[str] = set()
    i = 0
    while i < len(template):
        here = template[i]
        if here in "{}" and template[i : i + 2] == here * 2:
            out.append(here)
            i += 2
            continue
        if here == "{":
            end = template.find("}", i + 1)
            key = template[i + 1 : end] if end >= 0 else ""
            if end < 0 or not _NAME.fullmatch(key):
                raise ConfigurationError(
                    f"A prompt template for {where} has a '{{' at character {i} that opens no "
                    f"gap: {template[i : i + 24]!r}. Write '{{{{' for a literal brace, or name a "
                    f"value: '{{name}}'."
                )
            if key not in values:
                raise ConfigurationError(
                    f"A prompt template for {where} names {{{key}}} and no {key}= was passed. "
                    f"Given: {', '.join(sorted(values)) or 'nothing'}."
                )
            out.append(_written(values[key]))
            named.add(key)
            i = end + 1
            continue
        if here == "}":
            raise ConfigurationError(
                f"A prompt template for {where} has a '}}' at character {i} that closes no gap. "
                f"Write '}}}}' for a literal brace."
            )
        out.append(here)
        i += 1
    unused = sorted(set(values) - named)
    if unused:
        raise ConfigurationError(
            f"A prompt template for {where} was passed {', '.join(unused)} and names "
            f"{'no gap' if not named else 'only ' + ', '.join(sorted(named))}. Every value is "
            f"named by the text it fills, so a value nothing names would not reach the model."
        )
    return "".join(out)


def text_globals(fn: Any) -> dict[str, str]:
    """The module-level strings a prompt function uses as fixed text, by name.

    A prompt's words often live in a constant beside the function rather than inside it::

        TONE = "Answer in two sentences."

        def build_prompt(inputs, ctx):
            return Prompt.user(TONE + " {question}", question=inputs["q"])

    Editing `TONE` changes what the model reads, and the function's own source does not move.
    Reading the names it passes as text is what puts them in the version a run records and in
    `Pipeline.behaviour_fingerprint`.

    Only a name the function hands to `Prompt` or `Section` as its text is read, and only where
    the module binds it to a string. Text the function fetches at run time, from a store or from
    an end user, exists only once the run happens, and the run records it as a value. Text a
    helper builds is versioned with the helper rather than here.

    ``{}`` where the source cannot be read, which is a function defined in a REPL.
    """
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError, SyntaxError, IndentationError):
        return {}
    held = getattr(fn, "__globals__", {}) or {}
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        where = _text_argument(node)
        if where is None:
            continue
        for inner in ast.walk(where):
            if isinstance(inner, ast.Name) and isinstance(held.get(inner.id), str):
                found[inner.id] = held[inner.id]
    return found


def text_shape(fn: Any) -> str:
    """Whether a prompt function's fixed text is written or built by interpolation.

    ``"written"`` where every piece of text the function passes is a literal, a constant, or
    text it chose or fetched whole, which is a template read from a store or picked from a
    table. ``"interpolated"`` where a value was formatted into the text itself::

        Prompt.user(f"Answer {question}")        # interpolated: no instruction to read
        Prompt.user("Answer {q}", q=question)    # written

    An interpolated prompt sends a different instruction for every example, so nothing can read
    the step's instruction, compare it between runs, or put it to the builder to agree. FT-46
    reports it. ``"unreadable"`` where the function's source cannot be read.

    The prompt function's own source is what is read, so text a helper it calls interpolates is
    not seen here. What the run records says what actually happened: a step whose recorded
    templates differ on every example has no fixed instruction whatever this says.
    """
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError, SyntaxError, IndentationError):
        return "unreadable"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        where = _text_argument(node)
        if where is not None and _is_interpolated(where):
            return "interpolated"
    return "written"


def _is_interpolated(node: ast.AST) -> bool:
    """Whether this expression bakes a value into the text rather than naming a gap."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.JoinedStr):
            return True
        if isinstance(inner, ast.BinOp) and isinstance(inner.op, ast.Mod):
            return True
        if (
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Attribute)
            and inner.func.attr == "format"
        ):
            return True
    return False


def _text_argument(node: ast.Call) -> ast.AST | None:
    """The argument one call passes as fixed text, or ``None`` where it passes none.

    Read off the names as written, so ``sa.Prompt.user(...)`` is read and a prompt function
    that hands the work to a helper is not: what the helper does is in the helper's source.
    """
    func = node.func
    if isinstance(func, ast.Attribute) and _named(func.value) == "Prompt" and func.attr in ROLES:
        return node.args[0] if node.args else None
    if _named(func) == "Section" and node.args:
        return node.args[1] if len(node.args) > 1 else None
    return None


def _named(node: ast.AST) -> str | None:
    """The last name in ``a.b.C``, which is how a class reached through a module is read."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
