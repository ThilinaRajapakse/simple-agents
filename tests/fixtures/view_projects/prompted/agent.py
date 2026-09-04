"""Every shape the prompt page has to survive, one step each.

A capped value with an origin, a fan-out that sends one text per item, a loop with tools, a
section and a list of sections, a system message an end user wrote, a conversation carried in,
and a step whose instruction arrives as data. The graph is a straight line, and the words each
step sends are what this fixture is for.
"""

from pydantic import BaseModel

from simple_agents import (
    AgentNode,
    Budget,
    Deterministic,
    LLMNode,
    Maybe,
    Pipeline,
    Prompt,
    Section,
    Unknown,
    Value,
    pipeline_factory,
)
from simple_agents.tools import SideEffectClass, tool

# The house rule, in a constant beside the prompts that use it, which is what puts an edit to
# it inside the prompt's own version.
TONE = "Write in plain words, and never say that a plan was generated."


class Request(BaseModel):
    city: Maybe[str]
    days: Maybe[int]


class Places(BaseModel):
    places: Maybe[list[str]]


class Plan(BaseModel):
    itinerary: Maybe[str]


class Reply(BaseModel):
    body: Maybe[str]


@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="places")
def opening_hours(place: str) -> str:
    """When one place is open. Returns the hours as the listing prints them."""
    return f"{place}: 09:00-18:00, closed Tuesday"


@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="places")
def walking_time(start: str, end: str) -> str:
    """How long the walk between two places takes, on foot."""
    return f"{start} to {end}: 26 minutes"


def read_request(inputs: dict, ctx) -> Prompt:
    """Read the traveller's message for the city and the number of days."""
    return Prompt.user(
        "Read the traveller's message and return the city and how many days they have.\n\n"
        "{message}\n\nWhat we hold on this traveller: {notes}",
        message=Value(inputs["message"], origin="the traveller's own words, as the app took them"),
        notes=Value(inputs["notes"], cap=220, origin="the traveller_files store"),
    )


def to_cities(inputs: Request, ctx) -> dict:
    """Turn the request into the list the shortlist step runs over."""
    city = str(inputs.city) if inputs.city else "Paris"
    return {"cities": [city, "Lyon"], "days": inputs.days}


def shortlist(inputs: dict, ctx) -> Prompt:
    """Name a few places worth a stop in one city.

    Under ``over="cities"`` the step runs once per city, and the key keeps its name, so
    ``inputs["cities"]`` is the one city this call is for.
    """
    return Prompt.user(
        "Name three places worth a stop in {city}. One per line, nothing else.",
        city=inputs["cities"],
    )


def gather(inputs, ctx) -> dict:
    """Put the shortlists together for the step that plans the days."""
    found = [outcome.value.places for outcome in inputs if outcome.ok and outcome.value]
    places = [place for held in found if not isinstance(held, Unknown) for place in held]
    return {"places": places[:6], "days": ctx.run_inputs.get("days", 3)}


def plan_days(inputs: dict, ctx) -> Prompt:
    """Plan the days, checking the hours before committing to a stop."""
    return Prompt.system(TONE + " Check the opening hours before committing to a stop.") + Prompt.user(
        "Plan {days} days from these places.\n\n{shortlist}\n\n{context}",
        days=inputs["days"],
        shortlist=Section.joined(
            "shortlist",
            [Section("place", "- {name}", name=place) for place in inputs["places"]],
        ),
        context=Section(
            "context",
            "The traveller says: {says}",
            says=Value(ctx.run_inputs["message"], origin="the traveller's own words"),
        ),
    )


def reply_in_voice(inputs: Plan, ctx) -> Prompt:
    """Answer in the voice the traveller set, carrying the conversation so far."""
    return (
        Prompt.system("{voice}", voice=Value(ctx.run_inputs["voice"],
                                             origin="the app's settings screen"))
        + Prompt.turns(ctx.run_inputs["thread"])
        + Prompt.user(
            "Here is the plan: {plan}\n\nAnswer in at most 120 words.",
            plan=inputs.itinerary,
        )
    )


def house_style(inputs: Reply, ctx) -> Prompt:
    """Rewrite the reply against whichever house style the run was given."""
    return Prompt.user(ctx.run_inputs["template"], reply=inputs.body)


def keep_it(inputs: Reply, ctx) -> dict:
    """Save the reply the traveller is shown."""
    return {"sent": str(inputs.body)[:200]}


@pipeline_factory("trip")
def trip() -> Pipeline:
    return Pipeline(
        [
            LLMNode(read_request, output_schema=Request, max_output_tokens=400),
            Deterministic(to_cities),
            LLMNode(shortlist, output_schema=Places, over="cities", max_output_tokens=400),
            Deterministic(gather),
            AgentNode(
                plan_days,
                output_schema=Plan,
                tools=[opening_hours, walking_time],
                budget=Budget(max_steps=6, max_tokens=20_000, max_cost=0.05,
                              max_wall_clock_ms=None),
                max_output_tokens=900,
            ),
            LLMNode(reply_in_voice, output_schema=Reply, max_output_tokens=600),
            LLMNode(house_style, output_schema=Reply, max_output_tokens=600),
            Deterministic(keep_it),
        ],
        budget=Budget(max_steps=12, max_tokens=80_000, max_cost=0.20, max_wall_clock_ms=None),
    )
