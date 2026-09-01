"""The pipeline: a directed graph over the three node kinds, and the run context.

Edges are declared on the node. A node that declares none hands its output to the next node in
the list, so a plain list runs as a chain and every pipeline written before edges existed keeps
its meaning. ``graph.py`` holds the edge model and the checks over it; ``core.py`` holds the
walk, ``edges.py`` its working state, ``events.py`` what a run reports and returns,
``answering.py`` the shelf's answer path, ``preflight.py`` what a run refuses before starting,
and ``recording.py`` what the run writes down.

``docs/pipeline.md`` is this package's document: the graph, the three node kinds, what a node
receives, the output schema, and the budget.
"""

from .answering import Answered, AnsweredQuestion
from .core import Pipeline, SliceOf
from .events import NodeEvent, RunResult

__all__ = [
    "Pipeline",
    "RunResult",
    "NodeEvent",
    "Answered",
    "AnsweredQuestion",
    "SliceOf",
]
