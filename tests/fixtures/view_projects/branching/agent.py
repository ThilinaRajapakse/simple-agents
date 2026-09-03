"""A branching project: routes, a bounded loop, a fan-out, an error path and a nested pipeline.

Every shape the drawing has to survive is here in one pipeline: a three-way route, a step that
runs once per item, a revision loop with a bound, a failure path, a pipeline used as a node, a
step that is not built yet, and joins where several edges meet. A second pipeline fills the
resource the first one reads, so the system level has a real flow to draw.
"""

from pydantic import BaseModel

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    DeclaredCost,
    Deterministic,
    Join,
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
    return [f"The handbook has nothing on: {question}"]


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


# -- triage ------------------------------------------------------------------------------


def intake(inputs: dict, ctx) -> dict:
    """Take one ticket off the support inbox, which this step reaches in its own code."""
    ticket = inputs["ticket"]
    # The inbox is not behind a tool, so the access is recorded here. What it holds is what
    # this step chose to report: how much it looked at, and how much it kept.
    ctx.record_access(
        "inbox", "read",
        inputs={"status": "open"},
        outputs={"open_tickets": 128, "taken": 1, "characters": len(ticket)},
    )
    return {"ticket": ticket}


def classify(inputs: dict, ctx) -> str:
    return (
        Prompt.user('Read this support ticket and fill the fields. `needs_handbook` is true when ' 'answering it needs the product handbook. `questions` are the handbook questions ' 'worth asking, at most two. Say the topic is unknown only when the ticket makes no ' 'sense at all.\n\nTicket: {ticket}', ticket=inputs['ticket'])
    )


def where_next(output: Ticket, ctx) -> str:
    if isinstance(output.topic, Unknown):
        return "escalate"
    return "research" if output.needs_handbook else "answer_directly"


def pick_sources(inputs: Ticket, ctx) -> dict:
    questions = list(inputs.questions)[:2] or ["what does the product do"]
    return {"sources": [ctx.call_tool("handbook_lookup", question=q) for q in questions],
            "topic": inputs.topic}


def read_source(inputs: dict, ctx) -> str:
    return Prompt.user('In one sentence, what does this passage say?\n\n{sources}', sources=inputs['sources'])


def draft_reply(inputs: Join, ctx) -> str:
    earlier = "" if "critique" in inputs.absent else (
        f"\n\nThe last draft was turned down: {inputs['critique'].why}"
    )
    return Prompt.user('Write a short support reply from these notes:\n\n{research}{earlier}', research=inputs['research'], earlier=earlier)


def judge_draft(inputs: Reply, ctx) -> str:
    return (
        Prompt.user('Is this support reply good enough to send? It is good enough when it answers in ' 'plain words and invents nothing.\n\n{body}', body=inputs.body)
    )


def revise_or_send(output: Verdict, ctx) -> str:
    return "publish" if output.good_enough else "draft"


def answer_from_memory(inputs: Ticket, ctx) -> str:
    return (
        Prompt.user('Answer this ticket. The handbook comes first; the web search is for when the ' 'handbook has nothing; the rota answers one question where the handbook is ' 'unclear.\n\nTopic: {topic}', topic=inputs.topic)
    )


def hand_over(inputs: Ticket, ctx) -> Reply:
    return Reply(body=Unknown(reason="the topic was not clear enough to answer from the "
                                     "handbook, so the rota has the ticket"))


def apologise(failure, ctx) -> Reply:
    return Reply(body=Unknown(reason=f"{failure.node_id} failed, so nothing was drafted"))


def publish(inputs: Join, ctx) -> dict:
    """The rota presses send, so the run asks before the draft leaves."""
    for source in ("critique", "answer_directly", "escalate", "apologise"):
        if source in inputs.absent:
            continue
        reply = ctx.call_tool(
            "consult",
            question=f"The draft from {source} is ready. Send it?",
            options=["send it", "hold it for me"],
        )
        # A reply nobody could give has no `chose`, so the branch reads that rather than
        # the text: an unattended run holds the draft instead of sending it.
        chose = getattr(reply, "chose", None)
        sent = chose == "send it"
        # A copy of what left, in the run's own directory, which is what a workspace is for.
        (ctx.workspace / "sent.txt").write_text(str(inputs[source]), encoding="utf-8")
        # The outbox is reached here rather than through a tool, so the access is what puts
        # it on the record: without this the page can say the step touches it and no more.
        ctx.record_access(
            "outbox", "write",
            inputs={"from": source, "characters": len(str(inputs[source]))},
            outputs={"sent": sent},
        )
        return {"sent": sent, "from": source,
                "rota_said": str(reply) if chose else None}
    return {"sent": False, "from": None, "rota_said": None}


@pipeline_factory("triage")
def triage() -> Pipeline:
    return _triage(revisions=2)


def _triage(revisions: int) -> Pipeline:
    """The triage graph, with the revision loop's bound as a parameter for a variant."""
    research = Pipeline(
        [
            Deterministic(pick_sources, node_id="pick_sources", tools=[handbook_lookup]),
            LLMNode(read_source, output_schema=Passage, node_id="read_source",
                    over="sources", max_output_tokens=400),
        ],
        budget=Budget(max_steps=6, max_tokens=20_000, max_cost=None,
                      max_wall_clock_ms=None),
        node_id="research",
        successors=["draft"],
    )
    return Pipeline(
        [
            Deterministic(intake, node_id="intake", successors=["classify"],
                          touches="inbox"),
            LLMNode(
                classify, output_schema=Ticket, node_id="classify",
                successors=["research", "answer_directly", "escalate"],
                route=where_next, on_error="apologise",
                retry=RetryPolicy(attempts=2, backoff_ms=200), max_output_tokens=500,
            ),
            research,
            LLMNode(draft_reply, output_schema=Reply, node_id="draft",
                    successors=["critique"], max_output_tokens=600),
            LLMNode(
                judge_draft, output_schema=Verdict, node_id="critique",
                successors=["draft", "publish"], route=revise_or_send,
                loop=Loop(max_iterations=revisions, then="publish"), max_output_tokens=400,
            ),
            AgentNode(
                answer_from_memory, output_schema=Reply, node_id="answer_directly",
                tools=[handbook_lookup, web_search,
                       consult(ask_the_rota, answered_by="end_user")],
                budget=Budget(max_steps=4, max_tokens=8_000, max_cost=0.05,
                              max_wall_clock_ms=None),
                successors=["publish"], max_output_tokens=600,
            ),
            Deterministic(hand_over, node_id="escalate", successors=["publish"]),
            Deterministic(apologise, node_id="apologise", successors=["publish"]),
            Deterministic(publish, node_id="publish", successors=[], touches="outbox",
                          tools=[consult(ask_the_rota, answered_by="end_user")]),
        ],
        budget=Budget(max_steps=14, max_tokens=60_000, max_cost=0.20,
                      max_wall_clock_ms=None),
    )


# -- reindex -----------------------------------------------------------------------------


def read_new_notes(inputs: dict, ctx) -> list:
    """Read the handbook directly, and keep the notes it does not already hold."""
    notes = list(inputs.get("notes") or [])
    # Reading the handbook in plain code rather than through a tool. The counts are what the
    # step moved: what it looked at, and what survived.
    ctx.record_access(
        "handbook", "read",
        inputs={"looking_for": "notes the handbook already holds"},
        outputs={"passages": 4_102, "kept": len(notes)},
    )
    return notes


def file_them(inputs: list, ctx) -> int:
    return sum(ctx.call_tool("store_passage", passage=note) for note in inputs)


@pipeline_factory("reindex")
def reindex() -> Pipeline:
    return Pipeline(
        [
            Deterministic(read_new_notes, node_id="read_new_notes", touches="handbook"),
            Deterministic(NotBuilt("drops notes the handbook already holds"),
                          node_id="dedupe"),
            Deterministic(file_them, node_id="file_them", tools=[store_passage]),
        ],
        budget=Budget(max_steps=3, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )
