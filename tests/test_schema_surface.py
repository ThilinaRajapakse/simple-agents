"""What a model is shown when the library turns a project's schema into JSON.

The model reads the schema as prompt text, and every description in it is sent: the one
pydantic takes from a class docstring, one declared in ``json_schema_extra``, and one on a
``Field``. These tests pin that the library ships pydantic's mapping rather than its own, and
pin the descriptions the library itself declares.

Both item 7 checkpoint sessions produced a run where the model answered the string ``"unknown"``
where the absence object belonged, against a schema that never showed either form.
"""

from __future__ import annotations

import ast
import warnings
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field

from simple_agents import LLMNode, Maybe, Prompt
from simple_agents.errors import SimpleAgentsWarning
from simple_agents.schema import Unknown, json_schema_for_model, value_or
from simple_agents.tools import FinishTool

SRC = Path(__file__).resolve().parent.parent / "src" / "simple_agents"


class FromDocstring(BaseModel):
    """Taken from the docstring."""

    x: int


class Declared(BaseModel):
    """Replaced by the declaration below."""

    model_config = ConfigDict(json_schema_extra={"description": "Declared for the model."})
    x: int


class Nested(BaseModel):
    """The outer model."""

    from_docstring: FromDocstring
    declared: Declared


class TestWhatReachesTheModel:
    def test_a_class_docstring_does(self):
        assert json_schema_for_model(FromDocstring)["description"] == "Taken from the docstring."

    def test_a_declared_description_replaces_the_docstring(self):
        assert json_schema_for_model(Declared)["description"] == "Declared for the model."

    def test_a_field_description_does(self):
        class Described(BaseModel):
            """The model itself."""

            x: int = Field(description="Written for the model.")

        properties = json_schema_for_model(Described)["properties"]
        assert properties["x"]["description"] == "Written for the model."

    def test_the_mapping_recurses_into_a_nested_model(self):
        """A field's type carries its own description, wherever that description came from."""
        definitions = json_schema_for_model(Nested)["$defs"]

        assert definitions["FromDocstring"]["description"] == "Taken from the docstring."
        assert definitions["Declared"]["description"] == "Declared for the model."

    def test_a_schema_that_is_not_a_model_produces_an_empty_object(self):
        assert json_schema_for_model(object()) == {"type": "object", "properties": {}}


class TestAbsenceIsShownRatherThanNamed:
    def test_a_maybe_field_says_how_to_send_each_form(self):
        class Answer(BaseModel):
            answer: Maybe[str]

        described = json_schema_for_model(Answer)["properties"]["answer"]["description"]
        assert '{"type": "unknown"' in described
        assert 'not the word "unknown"' in described

    def test_a_declared_field_description_is_completed_rather_than_replacing_it(self):
        """Measured on dogfood #1: 13% of rollouts wrote the word into the value branch.

        Pydantic's own rule is that the field's `Field` wins, so what the builder wrote is
        all the model used to see. The sentence naming the tag is appended to it.
        """

        class Answer(BaseModel):
            answer: Maybe[str] = Field(description="The retailer's name.")

        described = json_schema_for_model(Answer)["properties"]["answer"]["description"]
        assert described.startswith("The retailer's name.")
        assert '{"type": "unknown"' in described

    def test_a_node_over_a_replaced_description_is_quiet_because_nothing_is_missing(self):
        class Answer(BaseModel):
            answer: Maybe[str] = Field(description="The retailer's name.")

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            LLMNode(lambda inputs, ctx: Prompt.user("ask"), output_schema=Answer, node_id="hunt")

    def test_a_replacement_that_says_how_to_send_an_absence_is_quiet(self):
        class Answer(BaseModel):
            answer: Maybe[str] = Field(
                description='The retailer\'s name, or {"type": "unknown", "reason": "..."} '
                "where the passage does not name one."
            )

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            LLMNode(lambda inputs, ctx: Prompt.user("ask"), output_schema=Answer, node_id="hunt")

    def test_maybe_on_its_own_is_quiet_because_it_carries_its_own_description(self):
        class Answer(BaseModel):
            answer: Maybe[str]

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            LLMNode(lambda inputs, ctx: Prompt.user("ask"), output_schema=Answer, node_id="hunt")

    def test_a_union_wrapped_around_maybe_is_described_too(self):
        """`Maybe[T] | None` is a union around a union, and pydantic keeps no metadata.

        The walk reads the annotation rather than the rendered schema, so a field reaches the
        sentence by what it is typed as however the union was spelled.
        """

        class Answer(BaseModel):
            answer: Maybe[str] | None = None

        described = json_schema_for_model(Answer)["properties"]["answer"]["description"]
        assert '{"type": "unknown"' in described

    def test_a_nested_model_gets_the_same_completion(self):
        class Finding(BaseModel):
            airs: Maybe[str] = Field(description="When it is on.")

        class Answer(BaseModel):
            finding: Finding

        nested = json_schema_for_model(Answer)["$defs"]["Finding"]["properties"]["airs"]
        assert nested["description"].startswith("When it is on.")
        assert '{"type": "unknown"' in nested["description"]

    def test_a_model_two_levels_down_is_reached(self):
        """Pydantic hoists every nested model into one `$defs` at the top, so a walk that
        goes a level at a time reaches only the models one hop from the root."""

        class Deep(BaseModel):
            airs: Maybe[str] = Field(description="When it is on.")

        class Middle(BaseModel):
            deep: Deep

        class Top(BaseModel):
            middle: Middle

        described = json_schema_for_model(Top)["$defs"]["Deep"]["properties"]["airs"]
        assert described["description"].startswith("When it is on.")
        assert '{"type": "unknown"' in described["description"]

    def test_the_absence_object_itself_is_left_alone(self):
        class Answer(BaseModel):
            answer: Maybe[str]

        reason = json_schema_for_model(Answer)["$defs"]["Unknown"]["properties"]["reason"]
        assert reason["description"] == "What was looked for, and what was found instead."

    def test_a_description_that_already_names_the_tag_is_sent_as_written(self):
        class Answer(BaseModel):
            answer: Maybe[str] = Field(
                description='The name, or {"type": "unknown", "reason": "..."} where absent.'
            )

        described = json_schema_for_model(Answer)["properties"]["answer"]["description"]
        assert described == ('The name, or {"type": "unknown", "reason": "..."} where absent.')

    def test_a_fixed_label_set_unioned_with_unknown_warns_on_the_shape(self):
        """The word satisfies neither branch, so it costs a step rather than a wrong answer."""

        class Finding(BaseModel):
            source: Maybe[Literal["page", "chart"]] = Field(
                description='Where it came from, or {"type": "unknown", "reason": "..."}.'
            )

        with pytest.warns(SimpleAgentsWarning, match="unions a fixed label set"):
            LLMNode(lambda inputs, ctx: Prompt.user("ask"), output_schema=Finding, node_id="chase")

    def test_the_label_warning_names_the_existing_labels_and_the_waiver(self):
        class Finding(BaseModel):
            source: Maybe[Literal["page", "chart"]]

        with pytest.warns(SimpleAgentsWarning) as caught:
            LLMNode(lambda inputs, ctx: Prompt.user("ask"), output_schema=Finding, node_id="chase")

        message = str(caught[0].message)
        assert "'page', 'chart', 'not_found'" in message
        assert "allow_unknown=False" in message

    def test_a_fixed_label_set_holding_its_own_absence_is_quiet(self):
        class Finding(BaseModel):
            source: Literal["page", "chart", "not_found"]

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            LLMNode(
                lambda inputs, ctx: Prompt.user("ask"),
                output_schema=Finding,
                node_id="chase",
                allow_unknown=False,
            )

    def test_a_free_text_maybe_does_not_draw_the_label_warning(self):
        class Finding(BaseModel):
            notes: Maybe[str]

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            LLMNode(lambda inputs, ctx: Prompt.user("ask"), output_schema=Finding, node_id="chase")

    def test_unknown_carries_a_description_written_for_the_model(self):
        described = json_schema_for_model(Unknown)["description"]

        assert "not available" in described
        assert "isinstance" not in described

    def test_the_finish_tool_shows_a_value_and_an_absence(self):
        """One worked example of absence and none of an answer would weight the choice."""

        class Answer(BaseModel):
            answer: Maybe[str]

        description = FinishTool(Answer).as_tool().description

        assert '"inseam_cm": 81' in description
        assert '"inseam_cm": {"type": "unknown"' in description


def _reaches_model_json_schema(node: ast.AST) -> bool:
    """Attribute access or ``getattr`` with the name as a string, which read the same method."""
    if isinstance(node, ast.Attribute):
        return node.attr == "model_json_schema"
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "model_json_schema"
    )


class TestEveryCallSiteGoesThroughTheHelper:
    """One definition of the schema the model is shown, including for a non-model.

    A test over the schemas that exist today would pass while a new call site diverged, so
    this reads the source for the call instead. Asking for the method to test whether a schema
    has one is allowed; using what comes back is not.
    """

    def test_nothing_calls_model_json_schema_directly(self):
        offenders: list[str] = []
        for path in SRC.rglob("*.py"):
            if path.name == "schema.py":
                continue  # where the helper itself lives
            tree = ast.parse(path.read_text(), filename=str(path))
            # A presence test compares the lookup against something and never calls it.
            tested = {
                id(operand)
                for node in ast.walk(tree)
                if isinstance(node, ast.Compare)
                for operand in [node.left, *node.comparators]
            }
            for node in ast.walk(tree):
                if _reaches_model_json_schema(node) and id(node) not in tested:
                    offenders.append(f"{path.relative_to(SRC)}:{node.lineno}")

        assert offenders == [], (
            "These reach model_json_schema() rather than going through the helper, so what "
            f"the model is shown is defined in more than one place: {offenders}. Use "
            f"simple_agents.schema.json_schema_for_model instead."
        )


class TestAnAbsenceThatReachesASurface:
    """Dogfood #5 put a tagged absence in front of an end user four times (`DF5-D27`)."""

    def test_value_or_replaces_the_encoded_form_as_well_as_the_object(self):
        """`model_dump()` and a stored artifact both produce the dict the library writes."""
        finding = Unknown(reason="not published")

        assert value_or(finding, "-") == "-"
        assert value_or(finding.model_dump(), "-") == "-"
        assert value_or({"type": "unknown"}, "-") == "-"

    def test_value_or_leaves_a_value_that_is_only_shaped_like_one(self):
        assert value_or({"type": "page", "reason": "x"}, "-") == {"type": "page", "reason": "x"}

    def test_the_bare_word_is_a_value_and_is_not_replaced(self):
        """A field whose answer is that word is ordinary, so matching it would lose it."""
        assert value_or("unknown", "-") == "unknown"

    def test_none_and_empty_and_zero_are_values(self):
        assert value_or(None, "-") is None
        assert value_or("", "-") == ""
        assert value_or(0, "-") == 0

    def test_rendering_an_absence_says_the_word_first(self):
        """An f-string in a template or a prompt is the unguarded path, and it must not read
        as an answer."""
        assert str(Unknown(reason="the schedule does not say")) == (
            "unknown (the schedule does not say)"
        )
        assert str(Unknown()) == "unknown"

    def test_repr_still_shows_the_fields(self):
        """What a traceback wants is unchanged, and it is what a parent model renders with."""
        assert repr(Unknown(reason="x")) == "Unknown(type='unknown', reason='x')"

        class Answer(BaseModel):
            answer: Maybe[str]

        assert "Unknown(type='unknown'" in str(Answer(answer=Unknown(reason="x")))
