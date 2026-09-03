"""Typed extraction from a passage, as a tool the model can reach for mid-run.

Most extraction is a node: ``LLMNode(build_prompt, output_schema=Facts)`` for one passage and
``LLMNode(..., over="documents")`` for many, both of which are one model call at a fixed point
in fixed control flow and cost nothing extra. Reach for this tool where the agent decides
during the run that it needs typed facts out of something it has just read, which no node can
express because a node is decided before the run starts.

The tool takes a :class:`~simple_agents.tools.ModelHandle`, so it is re-run during a replay
and the model call inside it is served from the cassette. A live run and a replay therefore
write the same records.
"""

from __future__ import annotations

import json
from typing import Any

from ..prompting import Prompt
from ..errors import ModelFacingError
from ..schema import (
    json_schema_for_model,
    require_a_schema_a_model_can_fill,
    require_unknown_branch,
)
from ..tools import ModelHandle, SideEffectClass, Tool, tool

__all__ = ["extract_to_schema"]

DEFAULT_INSTRUCTIONS = (
    "Extract the fields below from the passage. Use only what the passage states. Where the "
    'passage does not give a value, report it as {"type": "unknown", "reason": "..."} '
    "rather than inferring or guessing one. Answer with JSON matching the schema and nothing "
    "else."
)


def extract_to_schema(
    schema: Any,
    *,
    name: str | None = None,
    description: str | None = None,
    instructions: str = DEFAULT_INSTRUCTIONS,
    allow_unknown: bool = True,
    version: str | None = None,
) -> Tool:
    """A tool that reads a passage and returns the fields of ``schema`` found in it.

    One tool per schema, so the model selects what to extract by choosing a tool rather than
    by supplying a schema of its own::

        class ProductFacts(BaseModel):
            inseam_cm: Maybe[float]
            fabric: Maybe[str]

        registry.add(extract_to_schema(ProductFacts, name="extract_product_facts"))

    ``schema`` must admit ``unknown`` unless ``allow_unknown=False``, which is the same
    requirement a node's output schema carries and for the same reason: a field that cannot
    report absence gets a guess instead. Pass ``description`` where the schema's field names
    do not say what the tool is for.

    The passage is an argument, so the agent has already read it. Fetching and extracting are
    two tools, because a tool that fetched would fetch again on every replay.
    """
    tool_name = name or f"extract_{_schema_name(schema).lower()}"
    require_a_schema_a_model_can_fill(
        schema, where=f"extract_to_schema for {tool_name!r}", argument="schema"
    )
    require_unknown_branch(schema, node_name=tool_name, allow_unknown=allow_unknown)
    rendered = json.dumps(_json_schema(schema), indent=2)
    summary = description or (
        f"Extract {_schema_name(schema)} from a passage of text. Pass the passage as `text`; "
        f"the fields returned are {', '.join(_field_names(schema)) or 'those of the schema'}. "
        f"A field the passage does not state comes back as unknown rather than as a guess. "
        f"Call this on text already read, not on a url."
    )

    @tool(
        side_effect_class=SideEffectClass.READ_ONLY,
        name=tool_name,
        description=summary,
        version=version,
    )
    def extract(model: ModelHandle, text: str) -> dict[str, Any]:
        response = model.complete(
            Prompt.user(
                "{instructions}\n\nSchema:\n{schema}\n\nPassage:\n{passage}",
                instructions=instructions,
                schema=rendered,
                passage=text,
            ),
            output_schema=_json_schema(schema),
        )
        content = response.content or ""
        try:
            return _validate(schema, content).model_dump()
        except ModelFacingError:
            raise
        except Exception as exc:
            raise ModelFacingError(
                f"Extraction from that passage did not produce the required fields: {exc}. "
                f"The passage may not contain them. Try a passage that does, or report the "
                f"value as unknown."
            ) from exc

    return extract


def _validate(schema: Any, content: str) -> Any:
    validator = getattr(schema, "model_validate_json", None)
    if validator is None:
        raise ModelFacingError(
            "The extraction schema cannot validate a response, so nothing can be returned."
        )
    return validator(_json_only(content))


def _json_only(content: str) -> str:
    """The JSON object in a response, with any surrounding prose or code fence removed."""
    start, end = content.find("{"), content.rfind("}")
    return content[start : end + 1] if start != -1 and end > start else content


def _json_schema(schema: Any) -> dict[str, Any] | None:
    if getattr(schema, "model_json_schema", None) is None:
        return None
    return json_schema_for_model(schema)


def _schema_name(schema: Any) -> str:
    return getattr(schema, "__name__", None) or str(schema)


def _field_names(schema: Any) -> list[str]:
    return list(getattr(schema, "model_fields", {}))
