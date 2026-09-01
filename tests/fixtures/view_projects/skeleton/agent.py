"""The branching project as a coding agent would first write it: the shape, nothing built.

Same node ids, kinds, edges, routes, tools and budgets as
``tests/fixtures/view_projects/branching``. Every callable is a ``NotBuilt`` marker except the
routes, which decide the drawing's edges and so have to be real for the shape to be a shape.
"""

from pydantic import BaseModel

from simple_agents import (
    AgentNode,
    Budget,
    DeclaredCost,
    Deterministic,
    LLMNode,
    Loop,
    Maybe,
    NotBuilt,
    Pipeline,
    RetryPolicy,
    Unknown,
    pipeline_factory,
)
from simple_agents.builtins import consult
from simple_agents.tools import SideEffectClass, tool


class Ticket(BaseModel):
    topic: Maybe[str]
    needs_handbook: bool
    questions: list[str]


class Passage(BaseModel):
    quote: Maybe[str]


class Reply(BaseModel):
    body: Maybe[str]


class Verdict(BaseModel):
    good_enough: bool
    why: Maybe[str]


@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="handbook")
def handbook_lookup(question: str) -> list:
    """Read the support handbook for one question. Returns the passages that match."""
    return []


@tool(
    side_effect_class=SideEffectClass.SPENDS_MONEY,
    declared_cost=DeclaredCost(currency="USD", per_call=0.004),
    touches="web",
)
def web_search(query: str) -> list:
    """Search the web when the handbook has nothing. Costs money per call."""
    return []


@tool(side_effect_class=SideEffectClass.WRITES, touches="handbook")
def store_passage(passage: str) -> int:
    """Write one passage into the handbook. Returns how many were written."""
    return 1


def ask_the_rota(question, options=None, about=None):
    """Stand in for the person on the support rota."""
    return options[0] if options else "go ahead"


def where_next(output: Ticket, ctx) -> str:
    if isinstance(output.topic, Unknown):
        return "escalate"
    return "research" if output.needs_handbook else "answer_directly"


def revise_or_send(output: Verdict, ctx) -> str:
    return "publish" if output.good_enough else "draft"


@pipeline_factory("triage")
def triage() -> Pipeline:
    research = Pipeline(
        [
            Deterministic(NotBuilt("asks the handbook the two questions worth asking"),
                          node_id="pick_sources", tools=[handbook_lookup]),
            LLMNode(NotBuilt("says in one sentence what each passage says"),
                    output_schema=Passage, node_id="read_source",
                    over="sources", max_output_tokens=400),
        ],
        budget=Budget(max_steps=6, max_tokens=20_000, max_cost=None,
                      max_wall_clock_ms=None),
        node_id="research",
        successors=["draft"],
    )
    return Pipeline(
        [
            Deterministic(NotBuilt("takes one open ticket off the support inbox"),
                          node_id="intake", successors=["classify"], touches="inbox"),
            LLMNode(
                NotBuilt("reads the ticket for its topic and whether the handbook is needed"),
                output_schema=Ticket, node_id="classify",
                successors=["research", "answer_directly", "escalate"],
                route=where_next, on_error="apologise",
                retry=RetryPolicy(attempts=2, backoff_ms=200), max_output_tokens=500,
            ),
            research,
            LLMNode(NotBuilt("writes a short support reply from the notes"),
                    output_schema=Reply, node_id="draft",
                    successors=["critique"], max_output_tokens=600),
            LLMNode(
                NotBuilt("says whether the draft is good enough to send"),
                output_schema=Verdict, node_id="critique",
                successors=["draft", "publish"], route=revise_or_send,
                loop=Loop(max_iterations=2, then="publish"), max_output_tokens=400,
            ),
            AgentNode(
                NotBuilt("answers from the handbook, and searches the web where it cannot"),
                output_schema=Reply, node_id="answer_directly",
                tools=[handbook_lookup, web_search,
                       consult(ask_the_rota, answered_by="end_user")],
                budget=Budget(max_steps=4, max_tokens=8_000, max_cost=0.05,
                              max_wall_clock_ms=None),
                successors=["publish"], max_output_tokens=600,
            ),
            Deterministic(NotBuilt("hands the ticket to the rota with the reason"),
                          node_id="escalate", successors=["publish"]),
            Deterministic(NotBuilt("says nothing was drafted, and why"),
                          node_id="apologise", successors=["publish"]),
            Deterministic(NotBuilt("asks the rota to send, then writes to the outbox"),
                          node_id="publish", successors=[], touches="outbox",
                          tools=[consult(ask_the_rota, answered_by="end_user")]),
        ],
        budget=Budget(max_steps=14, max_tokens=60_000, max_cost=0.20,
                      max_wall_clock_ms=None),
    )


@pipeline_factory("reindex")
def reindex() -> Pipeline:
    return Pipeline(
        [
            Deterministic(NotBuilt("reads the handbook for notes it does not hold"),
                          node_id="read_new_notes", touches="handbook"),
            Deterministic(NotBuilt("drops notes the handbook already holds"),
                          node_id="dedupe"),
            Deterministic(NotBuilt("writes each kept note into the handbook"),
                          node_id="file_them", tools=[store_passage]),
        ],
        budget=Budget(max_steps=3, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )
