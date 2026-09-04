"""`unknown` as a first-class value, and the check that a schema can express it.

``unknown`` is never coerced to an error, an empty string, or a guess. It encodes as a
tagged object: ``null``, ``""``, and a missing field never mean ``unknown``.

Representing absence explicitly separates two rates that are otherwise averaged together:
how often the agent asserts something incorrect, and how often it finds nothing.

``docs/pipeline.md`` §4 covers the output schema this checks, and
``docs/trajectory-format.md`` §5.1 the encoding on a record.
"""

from __future__ import annotations

import types
import typing
import warnings
from typing import Annotated, Any, Literal, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field

from .errors import ConfigurationError, SimpleAgentsWarning

__all__ = [
    "Unknown",
    "Maybe",
    "MAYBE_DESCRIPTION",
    "value_or",
    "encode_answer",
    "decode_answer",
    "schema_admits_unknown",
    "require_unknown_branch",
    "require_a_schema_a_model_can_fill",
    "warn_literal_absence_union",
    "describes_absence",
    "json_schema_for_model",
]


class Unknown(BaseModel):
    """The agent looked and the information was not there.

    Distinct from an error, where the lookup itself failed, and from ``None``, which is a
    value that happens to be empty. ``reason`` is free text and may be ``None``::

        Unknown(reason="not published on the product page")

    Falsy, so ``if value:`` does not treat it as an answer. Use ``isinstance(value, Unknown)``
    to test for it.
    """

    # A `json_schema_extra` description replaces the one pydantic takes from the docstring
    # above, which is written for someone reading this source. This is what the model reads.
    model_config = ConfigDict(
        json_schema_extra={
            "description": "The value the field asks for, where the agent established that it "
            "is not available. Supply `reason` saying what was looked for and what was found "
            "instead."
        }
    )

    type: Literal["unknown"] = "unknown"
    reason: str | None = Field(
        default=None,
        description="What was looked for, and what was found instead.",
    )

    def __str__(self) -> str:
        """``unknown (reason)``, or ``unknown`` where there is none.

        What a log line, a template, or a value dropped into a prompt renders. The word comes
        first and always, so a value that is an absence cannot read as an answer::

            Prompt.user("Airs: {airs}", airs=finding.airs)   # 'Airs: unknown (the schedule …)'

        ``repr`` is unchanged and still shows the fields, which is what a traceback wants.
        Where the branch matters, test for it: ``isinstance(value, Unknown)``.
        """
        return f"unknown ({self.reason})" if self.reason else "unknown"

    def __bool__(self) -> bool:
        # Falsy, so `if value:` does not treat an unknown as a present answer. Use
        # isinstance() to distinguish the two.
        return False


T = TypeVar("T")

# What a `Maybe[T]` field tells the model. `describes_absence` reads a replacement against it.
MAYBE_DESCRIPTION = (
    'The value itself, or {"type": "unknown", "reason": "..."} where it is not '
    'available. Send the object, not the word "unknown".'
)

ABSENCE_SENTENCE = (
    'If it is not available, send {"type": "unknown", "reason": "..."} rather than the word'
    ' "unknown".'
)
"""Appended to a `Maybe` field whose own description says nothing about the tag.

What the model is told about the absence branch where a `Field(description=...)` replaced
`MAYBE_DESCRIPTION`. Shorter than that one, because it follows a sentence that has already
said what the value is.
"""

Maybe = Annotated[
    Union[T, Unknown],
    Field(description=MAYBE_DESCRIPTION),
]
"""``Maybe[int]`` is ``int | Unknown``::

    class Answer(BaseModel):
        answer: Maybe[str]
        source: str | None = None

One field typed this way satisfies the check that a node's output schema admits absence.

The field carries a description saying how to send each of the two forms, because a model shown
a union of a string and an object has no other way to tell which one absence goes in.

A ``Field(description=...)`` declared on the field **replaces** that, rather than adding to it,
so a replacement says both what the value is and how to send an absence::

    answer: Maybe[str] = Field(
        description='The shortest span that answers the question. If the documents do not '
        'answer it, send {"type": "unknown", "reason": "..."}.'
    )

A node built over a description that names neither warns at construction.
"""


def value_or(value: Any, default: Any) -> Any:
    """The value, or ``default`` where the agent reported absence::

        chest_cm = value_or(finding.chest_cm, 0.0)

    **Both shapes of an absence are replaced**: the ``Unknown`` a node returned, and the
    ``{"type": "unknown", "reason": ...}`` it becomes through ``model_dump()`` or a stored
    artifact, which is the encoding ``encode_answer`` writes::

        value_or(finding.chest_cm, 0.0)                              # the object
        value_or(stored["chest_cm"], 0.0)                            # the same, from a file

    ``None``, ``""`` and ``0`` are values and come back as they are, so a field that has to
    treat one of those as missing tests for it as well. **The bare word ``"unknown"`` is a
    value too** and is not replaced, since a field whose answer is that word is ordinary; a
    model sending it in place of the object is what the ``Maybe`` description prevents.

    Where the branch matters rather than the value, test for absence directly::

        if isinstance(finding.chest_cm, Unknown):
            return "measure"
    """
    if isinstance(value, Unknown):
        return default
    if isinstance(value, dict) and value.get("type") == "unknown":
        return default
    return value


def encode_answer(value: Any) -> Any:
    """A value as a file stores it. Absence becomes the tagged object, models become dicts.

    The encoding is the one ``docs/trajectory-format.md`` §5.1 defines, so an example's label
    and a rollout's answer are written the same way and compare after a round trip::

        encode_answer({"answer": Unknown(reason="not published")})
        # {"answer": {"type": "unknown", "reason": "not published"}}

    Dicts and lists are walked, because a node returns a schema object and an absence sits in
    one of its fields rather than being the whole value.
    """
    if isinstance(value, Unknown):
        return value.model_dump()
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    if isinstance(value, dict):
        return {key: encode_answer(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode_answer(item) for item in value]
    return value


def decode_answer(raw: Any) -> Any:
    """The inverse. Every tagged unknown object becomes ``Unknown``; everything else is itself.

    ``null``, ``""`` and a missing field never mean ``unknown``, so none of them decode to it::

        decode_answer({"answer": {"type": "unknown", "reason": "not published"}})
        # {"answer": Unknown(reason="not published")}

    Applied wherever the library hands back a value a node produced, so
    ``isinstance(value, Unknown)`` is the absence test on a value read out of a run as much as
    on one a node just returned. ``read_trajectory`` is the exception and yields records as
    they are on disk, because a record is data rather than a value.
    """
    if isinstance(raw, dict):
        if raw.get("type") == "unknown":
            return Unknown(reason=raw.get("reason"))
        return {key: decode_answer(value) for key, value in raw.items()}
    if isinstance(raw, list):
        return [decode_answer(value) for value in raw]
    return raw


def _flatten(annotation: Any) -> list[Any]:
    """All the types a single annotation can produce, unwrapping unions and Annotated."""
    origin = typing.get_origin(annotation)
    if origin is Annotated:
        return _flatten(typing.get_args(annotation)[0])
    if origin is Union or origin is types.UnionType:
        out: list[Any] = []
        for arg in typing.get_args(annotation):
            out.extend(_flatten(arg))
        return out
    return [annotation]


def _is_unknown(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, Unknown)


def json_schema_for_model(model: Any) -> dict[str, Any]:
    """The JSON schema for a model, as the model under test is shown it.

    Every description in the schema is prompt text. Pydantic takes one from a class docstring
    and from ``Field(description=...)``, and both are sent, including the docstring of a model
    used as a field's type::

        class Product(BaseModel):
            \"\"\"Sent to the model.\"\"\"

            inseam_cm: Maybe[int] = Field(description="Sent to the model.")

    A ``json_schema_extra`` description on a model replaces the one taken from its docstring.
    A model with no ``model_json_schema`` produces an empty object schema.

    **A field that can hold an absence is always told how to send one.** A
    ``Field(description=...)`` on a ``Maybe`` field replaces the description ``Maybe`` carries
    rather than adding to it, and so does a union around the union such as ``Maybe[str] |
    None``. Where what is left says nothing about the tag, this appends the sentence naming
    it, so the field says what the value is and how to send an absence. A description that
    already names the tag is sent as it was written.
    """
    generator = getattr(model, "model_json_schema", None)
    if generator is None:
        return {"type": "object", "properties": {}}
    return _absence_described(generator(), model)


def _absence_described(schema: dict[str, Any], model: Any) -> dict[str, Any]:
    """``schema``, with the absence sentence on every field that can hold one and omits it.

    Pydantic hoists every nested model into one ``$defs`` at the top, however deep it sits, so
    the models are collected by following the annotations and each ``$defs`` entry is matched
    to the one that produced it. Walking the schema a level at a time instead reaches only the
    models one hop from the root.
    """
    _describe_fields(schema, model)
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict):
        return schema
    by_name = {member.__name__: member for member in _models_under(model)}
    for defined in definitions.values():
        if not isinstance(defined, dict):
            continue
        member = by_name.get(defined.get("title"))
        if member is not None:
            _describe_fields(defined, member)
    return schema


def _describe_fields(schema: dict[str, Any], model: Any) -> None:
    """Complete the description of every field of ``model`` that can hold an absence.

    Read off the annotations rather than the rendered schema, so a field reaches this by what
    it is typed as however its union was spelled.
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    for name, field in getattr(model, "model_fields", {}).items():
        rendered = properties.get(name)
        if not isinstance(rendered, dict):
            continue
        if not any(_is_unknown(member) for member in _flatten(field.annotation)):
            continue
        if describes_absence(rendered.get("description")):
            continue
        said = rendered.get("description")
        rendered["description"] = f"{said} {ABSENCE_SENTENCE}" if said else MAYBE_DESCRIPTION


def _models_under(model: Any) -> list[Any]:
    """``model`` and every model reachable through its fields, however deep.

    ``Unknown`` is left out: it is the absence itself, and its own fields hold no absence.
    """
    found: list[Any] = []
    pending = [model]
    while pending:
        member = pending.pop()
        if member in found or member is Unknown:
            continue
        if not (isinstance(member, type) and issubclass(member, BaseModel)):
            continue
        found.append(member)
        for field in getattr(member, "model_fields", {}).values():
            pending.extend(_flatten(field.annotation))
    return found


def schema_admits_unknown(schema: Any) -> bool:
    """Whether ``schema`` can represent "the information is not there".

    True when the schema is ``Unknown``, is a union containing it, or is a model with at
    least one field that is. One field is sufficient; every field is not required.
    """
    for member in _flatten(schema):
        if _is_unknown(member):
            return True

    for member in _flatten(schema):
        if isinstance(member, type) and issubclass(member, BaseModel):
            for field in member.model_fields.values():
                if any(_is_unknown(t) for t in _flatten(field.annotation)):
                    return True
    return False


def require_a_schema_a_model_can_fill(schema: Any, *, where: str, argument: str) -> None:
    """Refuse a schema the model cannot be shown, where the model is what fills it in.

    Pydantic is what renders a schema into the JSON the model is offered and what validates
    what comes back. A type without ``model_json_schema`` is offered as an object with no
    properties, so the model is told the call takes no arguments, and a type without
    ``model_validate`` accepts whatever it sends. Neither says anything while it happens.

    ``where`` names the node or tool and ``argument`` the parameter, since the same refusal
    covers ``output_schema=`` on a node and ``schema=`` on a tool.
    """
    if getattr(schema, "model_json_schema", None) is not None:
        return
    # A builtin such as `dict`, and anything that is not a class at all, has no name worth
    # putting in front of `(BaseModel)`: the example would be invalid Python.
    named = (
        _describe(schema)
        if isinstance(schema, type) and schema.__module__ != "builtins"
        else "Answer"
    )
    raise ConfigurationError(
        f"{where} declares {argument}={_describe(schema)}, and the model has to be shown a "
        f"schema it can fill in. Anything without one is offered as an object with no "
        f"properties, so the model is told the call takes no arguments and whatever it sends "
        f"back is accepted without being validated against this type.\n"
        f"Declare it as a pydantic model:\n"
        f"    class {named}(BaseModel):\n"
        f"        ...\n"
        f"A dataclass and a TypedDict are refused here for that reason. "
        f"Deterministic(output_schema=...) takes either, since nothing is shown to a model."
    )


def require_unknown_branch(schema: Any, *, node_name: str, allow_unknown: bool) -> None:
    """Refuse an output schema that cannot express absence, unless waived explicitly.

    ``allow_unknown=False`` waives the requirement, for outputs that have no absent state,
    such as a classification over a fixed label set. The waiver is recorded in the run
    manifest.
    """
    if allow_unknown is False:
        return
    if schema_admits_unknown(schema):
        return

    raise ConfigurationError(
        f"The output schema for node {node_name!r} ({_describe(schema)}) has no `unknown` "
        f"variant. An agent that cannot report absence reports a guess instead, and in the "
        f"trajectory that guess is indistinguishable from a real answer (FT-09).\n"
        f"\n"
        f"There are two fixes:\n"
        f"  1. Add `unknown` as a first-class value. Type the field as `Maybe[T]`, which is "
        f"`T | Unknown`, or make the whole schema `{_describe(schema)} | Unknown`. An empty "
        f"string or a null is not a substitute; both are coerced and compared as answers.\n"
        f"  2. If the output has no absent state, such as a classification over a fixed "
        f"label set, pass `allow_unknown=False`. The waiver is recorded in the run manifest."
    )


def describes_absence(description: str | None) -> bool:
    """Whether a field description tells the model how to encode an absence.

    The test is whether it names the ``unknown`` tag, which is the discriminator between the
    two branches of ``Maybe[T]``. ``MAYBE_DESCRIPTION`` names it; a description written about
    the value alone does not.
    """
    return description is not None and "unknown" in description.lower()


def warn_literal_absence_union(schema: Any, *, node_name: str) -> None:
    """Warn where a field unions a fixed label set with ``Unknown``.

    ``Maybe[Literal["a", "b"]]`` offers the model a closed list of words and an object, and
    the word ``unknown`` belongs to neither: it is not in the list, and it is not the tagged
    object. A model reaching for it produces a response that fails validation, which costs a
    step and a retry rather than being recorded as a wrong answer.

    Naming the tag in the description does not prevent it, so this warns on the shape rather
    than on the wording, which :func:`json_schema_for_model` completes on its own.
    """
    for member in _flatten(schema):
        if not (isinstance(member, type) and issubclass(member, BaseModel)):
            continue
        for name, field in member.model_fields.items():
            parts = _flatten(field.annotation)
            if not any(_is_unknown(t) for t in parts):
                continue
            labels = [t for t in parts if typing.get_origin(t) is Literal]
            if not labels:
                continue
            existing = [repr(v) for label in labels for v in typing.get_args(label)]
            warnings.warn(
                f"{member.__name__}.{name} on node {node_name!r} unions a fixed label set with "
                f"`Unknown`. The label set is closed and the absence is a tagged object, so "
                f'the word "unknown" satisfies neither branch: a model that writes it produces '
                f"a response that fails validation and costs a step, rather than one that is "
                f"recorded as an asserted answer (FT-09).\n"
                f"Put the absence in the label set and waive the requirement:\n"
                f"    {name}: Literal[{', '.join(existing)}, 'not_found']\n"
                f"    LLMNode(..., allow_unknown=False)\n"
                f"The waiver is recorded in the run manifest. Keep the union where the reason "
                f"for an absence has to travel with it, and expect the retry.",
                SimpleAgentsWarning,
                stacklevel=4,
            )


def _describe(schema: Any) -> str:
    return getattr(schema, "__name__", None) or str(schema)
