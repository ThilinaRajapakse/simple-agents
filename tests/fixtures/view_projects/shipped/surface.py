"""What the end user meets, and the numbers the surface itself carries.

The claims agent runs behind three surfaces: the finance inbox that starts a run, the person
in finance who answers when it asks, and the ledger a person reads afterwards. None of them
is reached from a run, so none of them can be found by introspection; this declares them.

The numbers here are the surface's own, not the pipeline's. A run's manifest records the
numbers its own code reached, and these belong to the page rather than to the agent.
"""

from simple_agents import Product, Surface, product_factory

CLAIMS_PER_PAGE = 25
REASON_CHARS = 240
STALE_AFTER_HOURS = 48


@product_factory
def product() -> Product:
    """Every place the end user meets this agent."""
    return Product(surfaces=[
        Surface(
            "the finance inbox", "starts_a_run", pipeline="claims",
            does="a claim submitted by an employee starts one run",
        ),
        Surface(
            "the finance desk", "answers_a_waiting_run", pipeline="claims", through="consult",
            does="the person in finance answers when the agent cannot settle a claim alone",
        ),
        Surface(
            "the ledger", "reads_the_artifact", reads="ledger",
            does="an approved claim is posted there, and finance reads it",
        ),
    ])
