"""A mid-build project: some steps real, one a placeholder, one decision changed."""

from pydantic import BaseModel

from simple_agents import (
    Budget,
    Deterministic,
    LLMNode,
    Maybe,
    NotBuilt,
    Pipeline,
    pipeline_factory,
)
from simple_agents.tools import SideEffectClass, tool


class Picks(BaseModel):
    titles: Maybe[str]


@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="shelf")
def shelf_rows(only_unread: bool) -> list:
    """Read the shelf. Returns one row per book, unread first."""
    return []


def gather_pool(inputs, ctx):
    return ctx.call_tool("shelf_rows", only_unread=True)


def present(inputs, ctx):
    return f"Write three picks, one line each: {inputs}"


@pipeline_factory("next_pick")
def next_pick() -> Pipeline:
    return Pipeline(
        [
            Deterministic(gather_pool, tools=[shelf_rows]),
            LLMNode(
                NotBuilt("weighs each candidate against what was read recently"),
                output_schema=None,
                node_id="judge_books",
            ),
            LLMNode(present, output_schema=Picks),
        ],
        budget=Budget(max_steps=6, max_tokens=40_000, max_cost=None, max_wall_clock_ms=None),
    )
