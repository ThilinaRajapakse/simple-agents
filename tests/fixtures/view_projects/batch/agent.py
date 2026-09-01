"""A batch project: no consultation, no end-user surface, runs on a schedule."""

from pydantic import BaseModel

from simple_agents import Budget, Deterministic, LLMNode, Maybe, Pipeline, pipeline_factory
from simple_agents.tools import SideEffectClass, tool


class Digest(BaseModel):
    body: Maybe[str]


@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="article_store")
def stored_articles(day: str) -> list:
    """Read the articles stored for one day. Returns them oldest first."""
    return []


def gather(inputs, ctx):
    return ctx.call_tool("stored_articles", day=inputs["day"])


def write_digest(inputs, ctx):
    return f"Write the daily digest from: {inputs}"


def keep(inputs, ctx):
    return inputs


@pipeline_factory("daily_digest")
def daily_digest() -> Pipeline:
    return Pipeline(
        [
            Deterministic(gather, tools=[stored_articles]),
            LLMNode(write_digest, output_schema=Digest),
            Deterministic(keep, touches="digest_store"),
        ],
        budget=Budget(max_steps=5, max_tokens=30_000, max_cost=None, max_wall_clock_ms=None),
    )
