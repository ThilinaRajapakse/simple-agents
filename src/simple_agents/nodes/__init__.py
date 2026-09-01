"""The three node kinds. The agency boundary, made type-level.

Much of what appears agentic is an ``LLMNode`` inside a fixed loop:
``while insufficient and attempts < 3: queries = llm(...)`` is ordinary control flow
containing a model call, not a model deciding what to do next. Choose the kind by which of
those the step is.

Each kind differs in what the caller supplies and what the library retains:

===============  ==========================================  =============================
Kind             Builder supplies                            Library owns
===============  ==========================================  =============================
Deterministic    ``fn(inputs, ctx: NodeContext)``             recording
LLMNode          ``prompt(inputs, ctx: NodeContext)``        exactly one call, validation
AgentNode        ``prompt(inputs, ctx: AgentContext)``       the loop, dispatch, stopping
===============  ==========================================  =============================

The kind is enforced rather than declared. ``Deterministic`` and ``LLMNode`` are never given
a model client, so neither can make a call that the recorded kind does not describe.
"""

from __future__ import annotations


from .agent import AgentNode
from .base import Execution, Node, NodeOutcome, NotBuilt, model_for
from .delegation import Delegation
from .deterministic import Deterministic
from .fanout import FanOutResult, ItemOutcome
from .llm import LLMNode

__all__ = [
    "Node",
    "Delegation",
    "Deterministic",
    "LLMNode",
    "AgentNode",
    "FanOutResult",
    "ItemOutcome",
    "Execution",
    "NodeOutcome",
    "model_for",
    "NotBuilt",
]
