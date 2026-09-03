"""The background half of the shipped project: the nightly reconciliation.

`claims` is request-shaped and somebody is waiting on every run of it. This one is fired by a
schedule, so it is unattended: a question it cannot settle is shelved rather than waited on
(`docs/product.md` §4.2), and a claim it has to hold for a person suspends the run.

It calls no model. What it exists for on the `ship` and operate pages is the shape of what a
shipped project leaves behind: a run waiting on a person, a run waiting on a clock, a question
unanswered, and a conversation across turns.
"""

from typing import Any

from simple_agents import (
    Budget,
    Deterministic,
    Pipeline,
    Suspend,
    Throttled,
    pipeline_factory,
)
from simple_agents.builtins import Shelved, consult
from simple_agents.tools import SideEffectClass, tool

RECONCILE_BATCH = 40


def ask_the_finance_page(question: str, options: Any = None, about: Any = None) -> Any:
    """The questions page finance reads when they are next at their desk.

    The page is unattended when a nightly run asks, so the question is shelved and the run
    finishes rather than waiting for somebody who is not there.
    """
    return Shelved(reason="the nightly run is unattended")


@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="ledger")
def ledger_rows(since: str) -> list:
    """Every ledger entry posted since a date. Returns one row per entry."""
    return []


@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="supplier_registry")
def registry_health(_probe: bool = True) -> dict:
    """Ask the supplier registry whether it is answering. Returns its state."""
    raise Throttled("the supplier registry is rate limiting this agent.", retry_after_s=0.01)


def pick_up(inputs: Any, ctx: Any) -> dict:
    """Take the entries this run is to reconcile off the ledger.

    Reading ``ctx.conversation`` is what enrols this node in the conversation, where the run
    is a turn of one: the close of a month is several nightly passes and finance reads them
    as one thread.
    """
    ctx.call_tool("ledger_rows", since=str(inputs.get("since", "2026-08-01")))
    earlier = len(list(ctx.conversation or ()))
    return {
        "mode": str(inputs.get("mode", "settle")),
        "entries": RECONCILE_BATCH,
        "earlier_turns": earlier,
    }


def settle(inputs: Any, ctx: Any) -> dict:
    """Settle what the policy settles, and stop where a person has to decide.

    The four ways a background run ends, which is what the operate page draws.
    """
    mode = inputs["mode"]
    if mode == "waiting":
        raise Suspend(
            waiting_for="the finance desk to confirm the August write-off",
            options=["write it off", "chase it"],
        )
    if mode == "clock":
        raise Suspend(waiting_for="the month to close", resume_not_before="2026-09-01T09:00:00Z")
    if mode == "shelve":
        ctx.call_tool(
            "consult",
            question="Is the 12p line on PO-80115 per unit or for the whole order?",
            about="po-80115-unit",
        )
        return {"settled": 0, "asked": 1}
    if mode == "throttled":
        ctx.call_tool("registry_health")
    return {"settled": inputs["entries"], "asked": 0}


@pipeline_factory("reconcile")
def reconcile() -> Pipeline:
    """The nightly pass over the ledger."""
    return Pipeline(
        [
            Deterministic(pick_up, node_id="pick_up", successors=["settle"], tools=[ledger_rows]),
            Deterministic(
                settle,
                node_id="settle",
                successors=[],
                tools=[registry_health, consult(ask_the_finance_page, answered_by="end_user")],
            ),
        ],
        budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=600_000),
    )
