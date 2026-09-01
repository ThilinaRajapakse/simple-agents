"""What `Annotated[..., Field(...)]` on a tool parameter reaches.

`docs/tools.md` §1.1 says a `Field(description=...)` on a parameter is prompt text the model
reads, and shows a worked example carrying one. The metadata used to be stripped before the
schema was built, so the description never reached the model and a declared `ge`/`le` bound was
enforced nowhere. These hold both halves: what the backend is offered, and what the validator
refuses.
"""

from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import BaseModel, Field

from simple_agents import (
    DeclaredCost,
    ModelHandle,
    SideEffectClass,
    Workspace,
    tool,
)
from simple_agents.builtins import web_search
from simple_agents.errors import ModelFacingError


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def look_up(
    query: Annotated[str, Field(description="The search phrase, in the buyer's own words.")],
    top_k: Annotated[
        int, Field(description="How many to return. Above 10 crowds the turn.", ge=1, le=10)
    ] = 5,
) -> int:
    """Search the product catalogue for items matching a description."""
    return top_k


class TestTheOfferedSchema:
    def test_a_parameter_description_reaches_the_model(self) -> None:
        properties = look_up.parameters["properties"]

        assert properties["query"]["description"].startswith("The search phrase")
        assert "crowds the turn" in properties["top_k"]["description"]

    def test_a_declared_bound_reaches_the_model(self) -> None:
        top_k = look_up.parameters["properties"]["top_k"]

        assert top_k["minimum"] == 1
        assert top_k["maximum"] == 10

    def test_the_wire_schema_carries_them_too(self) -> None:
        """What `to_wire` produces is what the backend is sent."""
        offered = look_up.to_wire()["input_schema"]["properties"]

        assert offered["top_k"]["description"]
        assert offered["top_k"]["maximum"] == 10

    def test_the_default_survives_the_metadata(self) -> None:
        assert look_up.parameters["properties"]["top_k"]["default"] == 5
        assert look_up.parameters["required"] == ["query"]


class TestTheValidator:
    def test_a_value_past_the_bound_comes_back_for_correction(self) -> None:
        with pytest.raises(ModelFacingError) as raised:
            look_up.call({"query": "tee", "top_k": 400})

        assert "less than or equal to 10" in str(raised.value)

    def test_a_value_under_the_bound_is_refused_as_well(self) -> None:
        with pytest.raises(ModelFacingError):
            look_up.call({"query": "tee", "top_k": 0})

    def test_a_value_inside_the_bound_is_accepted(self) -> None:
        assert look_up.call({"query": "tee", "top_k": 7}) == 7


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def summarise(
    model: Annotated[ModelHandle, Field(description="filled by the library")],
    workspace: Annotated[Workspace, Field(description="filled by the library")],
    text: str,
) -> str:
    """Summarise some text and write the summary down."""
    return text


class TestHandlesStillResolve:
    """Keeping the metadata means a handle's annotation is no longer always a bare type."""

    def test_an_annotated_handle_is_still_recognised(self) -> None:
        assert summarise.handles == {"model": ModelHandle, "workspace": Workspace}

    def test_an_annotated_handle_is_still_kept_out_of_the_schema(self) -> None:
        assert sorted(summarise.parameters["properties"]) == ["text"]


class TestTheShippedToolsThatUseIt:
    def test_web_search_tells_the_model_what_a_domain_looks_like(self) -> None:
        """`websearch.py` declares `domains` with exactly this pattern."""
        search = web_search(
            lambda query, count: [],
            declared_cost=DeclaredCost(currency="USD", per_call=0.005),
        )

        description = search.parameters["properties"]["domains"]["description"]

        assert "example.com" in description


class Filter(BaseModel):
    """Narrow the search to one department."""

    department: str


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def find(narrow: Filter) -> str:
    """Search the catalogue."""
    return narrow.department


class TestAModelTypedParameterIsUnaffected:
    def test_its_docstring_still_reaches_the_schema(self) -> None:
        definition = find.parameters["$defs"]["Filter"]

        assert definition["description"] == "Narrow the search to one department."
