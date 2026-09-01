"""Three pipelines sharing a catalogue: the system level earns its place here."""

from pydantic import BaseModel

from simple_agents import (
    AgentNode,
    NotBuilt,
    Budget,
    DeclaredCost,
    Deterministic,
    LLMNode,
    Maybe,
    Pipeline,
    pipeline_factory,
)
from simple_agents.builtins import consult
from simple_agents.tools import SideEffectClass, tool


class Shortlist(BaseModel):
    titles: Maybe[str]


class Recap(BaseModel):
    body: Maybe[str]


@tool(side_effect_class=SideEffectClass.WRITES, touches="catalogue")
def store_titles(rows: list) -> int:
    """Write fetched titles into the catalogue. Returns how many were written."""
    return len(rows)


@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="catalogue")
def catalogue_rows(query: str) -> list:
    """Read catalogue rows matching a query. Returns them best first."""
    return []


@tool(
    side_effect_class=SideEffectClass.SPENDS_MONEY,
    declared_cost=DeclaredCost(currency="USD", per_call=0.002),
    touches="web",
)
def search_web(query: str) -> list:
    """Search the web for a title. Costs money per call."""
    return []


def ask_in_terminal(question, options=None, about=None):
    return options[0] if options else "go ahead"


def fetch_source(inputs, ctx):
    return inputs["rows"]


def keep(inputs, ctx):
    return ctx.call_tool("store_titles", rows=inputs)


def choose(inputs, ctx):
    return "Pick the titles worth recommending, search the web where unsure."


def write_recap(inputs, ctx):
    return f"Write a recap of: {inputs}"


@pipeline_factory("ingest")
def ingest() -> Pipeline:
    # `dedupe` was added after the run on disk, so the view's "what changed since the last
    # run" ledger always has something true to say about this fixture.
    return Pipeline(
        [
            Deterministic(fetch_source),
            Deterministic(NotBuilt("drops rows already in the catalogue"), node_id="dedupe"),
            Deterministic(keep, tools=[store_titles]),
        ],
        budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )


@pipeline_factory("recommend")
def recommend() -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                choose,
                tools=[catalogue_rows, search_web,
                       consult(ask_in_terminal, answered_by="end_user")],
                output_schema=Shortlist,
                budget=Budget(max_steps=8, max_tokens=30_000, max_cost=0.10,
                              max_wall_clock_ms=None),
                node_id="choose_titles",
            ),
        ],
        budget=Budget(max_steps=10, max_tokens=50_000, max_cost=0.25, max_wall_clock_ms=None),
    )


@pipeline_factory("weekly_recap")
def weekly_recap() -> Pipeline:
    return Pipeline(
        [
            Deterministic(fetch_source, tools=[catalogue_rows], node_id="gather_watched"),
            LLMNode(write_recap, output_schema=Recap),
        ],
        budget=Budget(max_steps=4, max_tokens=30_000, max_cost=None, max_wall_clock_ms=None),
    )
