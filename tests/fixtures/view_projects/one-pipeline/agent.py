"""A one-pipeline project: the view opens at the pipeline level."""

from pydantic import BaseModel

from simple_agents import Budget, Deterministic, LLMNode, Maybe, Pipeline, pipeline_factory


class Summary(BaseModel):
    lines: Maybe[str]


def load_note(inputs, ctx):
    return inputs["note"]


def write_summary(inputs, ctx):
    return f"Summarise in three lines:\n{inputs}"


@pipeline_factory("summarise")
def summarise() -> Pipeline:
    return Pipeline(
        [Deterministic(load_note), LLMNode(write_summary, output_schema=Summary)],
        budget=Budget(max_steps=4, max_tokens=20_000, max_cost=None, max_wall_clock_ms=None),
    )
