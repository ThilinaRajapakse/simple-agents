"""Eight pipelines and nine stores: a system rather than a pipeline.

`audit_trail` reaches every one of the nine, which is what makes its own graph's store column
taller than its rows of steps. Nine stores is also more than one row of the system map holds.
Both were drawn outside their frame, where nothing showed them at all.
"""

from pydantic import BaseModel

from simple_agents import Budget, Deterministic, Maybe, NotBuilt, Pipeline, pipeline_factory
from simple_agents.tools import SideEffectClass, tool


class Item(BaseModel):
    what: Maybe[str]


@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="catalogue")
def reach_catalogue(key: str) -> list:
    """Reach the catalogue."""
    return []

@tool(side_effect_class=SideEffectClass.WRITES, touches="inbox")
def reach_inbox(key: str) -> list:
    """Reach the inbox."""
    return []

@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="outbox")
def reach_outbox(key: str) -> list:
    """Reach the outbox."""
    return []

@tool(side_effect_class=SideEffectClass.WRITES, touches="profiles")
def reach_profiles(key: str) -> list:
    """Reach the profiles."""
    return []

@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="embeddings")
def reach_embeddings(key: str) -> list:
    """Reach the embeddings."""
    return []

@tool(side_effect_class=SideEffectClass.WRITES, touches="audit_log")
def reach_audit_log(key: str) -> list:
    """Reach the audit_log."""
    return []

@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="web")
def reach_web(key: str) -> list:
    """Reach the web."""
    return []

@tool(side_effect_class=SideEffectClass.WRITES, touches="cache")
def reach_cache(key: str) -> list:
    """Reach the cache."""
    return []

@tool(side_effect_class=SideEffectClass.READ_ONLY, touches="reports")
def reach_reports(key: str) -> list:
    """Reach the reports."""
    return []

@pipeline_factory("intake")
def intake() -> Pipeline:
    return Pipeline(
        [
            Deterministic(NotBuilt("takes what intake is given"), node_id="start_0",
                          tools=[reach_catalogue, reach_inbox]),
            Deterministic(NotBuilt("finishes intake"), node_id="finish_0"),
        ],
        budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )

@pipeline_factory("enrich")
def enrich() -> Pipeline:
    return Pipeline(
        [
            Deterministic(NotBuilt("takes what enrich is given"), node_id="start_1",
                          tools=[reach_inbox, reach_outbox, reach_profiles]),
            Deterministic(NotBuilt("finishes enrich"), node_id="finish_1"),
        ],
        budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )

@pipeline_factory("classify_batch")
def classify_batch() -> Pipeline:
    return Pipeline(
        [
            Deterministic(NotBuilt("takes what classify_batch is given"), node_id="start_2",
                          tools=[reach_outbox, reach_profiles, reach_embeddings, reach_audit_log]),
            Deterministic(NotBuilt("finishes classify_batch"), node_id="finish_2"),
        ],
        budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )

@pipeline_factory("summarise")
def summarise() -> Pipeline:
    return Pipeline(
        [
            Deterministic(NotBuilt("takes what summarise is given"), node_id="start_3",
                          tools=[reach_profiles, reach_embeddings]),
            Deterministic(NotBuilt("finishes summarise"), node_id="finish_3"),
        ],
        budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )

@pipeline_factory("recommend")
def recommend() -> Pipeline:
    return Pipeline(
        [
            Deterministic(NotBuilt("takes what recommend is given"), node_id="start_4",
                          tools=[reach_embeddings, reach_audit_log, reach_web]),
            Deterministic(NotBuilt("finishes recommend"), node_id="finish_4"),
        ],
        budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )

@pipeline_factory("weekly_digest")
def weekly_digest() -> Pipeline:
    return Pipeline(
        [
            Deterministic(NotBuilt("takes what weekly_digest is given"), node_id="start_5",
                          tools=[reach_audit_log, reach_web, reach_cache, reach_reports]),
            Deterministic(NotBuilt("finishes weekly_digest"), node_id="finish_5"),
        ],
        budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )

@pipeline_factory("reindex")
def reindex() -> Pipeline:
    return Pipeline(
        [
            Deterministic(NotBuilt("takes what reindex is given"), node_id="start_6",
                          tools=[reach_web, reach_cache]),
            Deterministic(NotBuilt("finishes reindex"), node_id="finish_6"),
        ],
        budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )

@pipeline_factory("audit_trail")
def audit_trail() -> Pipeline:
    return Pipeline(
        [
            Deterministic(NotBuilt("takes what audit_trail is given"), node_id="start_7",
                          tools=[reach_catalogue, reach_inbox, reach_outbox, reach_profiles, reach_embeddings, reach_audit_log, reach_web, reach_cache, reach_reports]),
            Deterministic(NotBuilt("finishes audit_trail"), node_id="finish_7"),
        ],
        budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )
