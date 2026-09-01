"""Budget declaration and the refusals a budget raises between steps."""

from __future__ import annotations

import warnings
from typing import Any
from ..budget import AXIS_FIELDS, Budget, BudgetExceeded, Spend
from ..errors import ConfigurationError, SimpleAgentsWarning


def _refuse_over_budget(budget: Budget, spend: Spend) -> None:
    tripped = budget.exceeded_by(spend)
    if tripped is None:
        return
    limit_attr, spent_attr = AXIS_FIELDS[tripped]
    raise BudgetExceeded(tripped, getattr(budget, limit_attr) or 0, getattr(spend, spent_attr) or 0)


def _spent_since(opened: Spend, now: Spend) -> Spend:
    """What has been spent since a node's first attempt started."""
    return Spend(
        steps=now.steps - opened.steps,
        tokens=now.tokens - opened.tokens,
        cost=None if now.cost is None else now.cost - (opened.cost or 0.0),
        wall_clock_ms=now.wall_clock_ms - opened.wall_clock_ms,
    )


def _declare_agent_budgets(
    node: Any, *, budget: Budget | None, budget_per_item: Budget | None
) -> None:
    """Attach an ``AgentNode``'s budgets, refusing the combinations that bound nothing.

    ``budget`` bounds one execution of the node. ``budget_per_item`` bounds one item of a
    fan-out, and means nothing on a node that runs once, so it is refused there. A fan-out
    takes either or both, and declaring one of the two leaves the other axis open: with
    ``budget`` alone one runaway item can consume the node's whole allowance and the items
    after it terminate having done nothing, and with ``budget_per_item`` alone the node's total
    is the item count times the item's allowance, bounded by the run and by nothing nearer.
    Both are declared on the node so a reader of the manifest sees which was left open.
    """
    if budget_per_item is not None and not isinstance(budget_per_item, Budget):
        raise ConfigurationError(
            f"AgentNode {node.node_id!r} was given budget_per_item={budget_per_item!r}. It "
            f"is a Budget bounding one item of a fan-out: "
            f"budget_per_item=Budget(max_steps=8, max_tokens=20_000, max_cost=None, "
            f"max_wall_clock_ms=60_000)."
        )
    if budget is not None and not isinstance(budget, Budget):
        raise ConfigurationError(
            f"AgentNode {node.node_id!r} was given budget={budget!r}, which is not a Budget. "
            f"Pass budget=Budget(max_steps=..., max_tokens=..., max_cost=..., "
            f"max_wall_clock_ms=...)."
        )
    if node.over is None and budget_per_item is not None:
        raise ConfigurationError(
            f"AgentNode {node.node_id!r} sets budget_per_item without over=. A node that "
            f"runs once has one budget, and there are no items for a per-item one to bound.\n"
            f"Pass over= to fan out over a sequence, or pass this budget as budget= instead."
        )
    if node.over is None and budget is None:
        raise ConfigurationError(
            f"AgentNode {node.node_id!r} was constructed without a Budget. An agent loop "
            f"decides for itself whether to keep going, so an unbounded one can iterate "
            f"until an external limit stops it. This is a refusal rather than a "
            f"warning (FT-18).\n"
            f"Pass budget=Budget(max_steps=..., max_tokens=..., max_cost=..., "
            f"max_wall_clock_ms=...). Any axis may be None to leave it unbounded; what "
            f"is refused is the absence of a decision."
        )
    if node.over is not None and budget is None and budget_per_item is None:
        raise ConfigurationError(
            f"AgentNode {node.node_id!r} fans out over {node.over!r} and was constructed "
            f"without a Budget. Every item is an agent loop that decides for itself whether "
            f"to keep going, so an unbounded fan-out can iterate until an external limit "
            f"stops it. This is a refusal rather than a warning (FT-18).\n"
            f"Pass budget_per_item=Budget(...) to bound one item, budget=Budget(...) to "
            f"bound the node, or both."
        )
    if node.over is not None and (budget is None or budget_per_item is None):
        open_axis, given, fix = (
            ("one item", "budget", "budget_per_item=Budget(...)")
            if budget_per_item is None
            else ("the node as a whole", "budget_per_item", "budget=Budget(...)")
        )
        warnings.warn(
            f"AgentNode {node.node_id!r} fans out over {node.over!r} with {given}= alone, so "
            f"nothing bounds {open_axis} except the run. The node's manifest entry records "
            f"which was left open. Pass {fix} as well to bound both.",
            SimpleAgentsWarning,
            stacklevel=3,
        )

    node.budget = budget
    node.budget_per_item = budget_per_item


def _budget_tripped(
    budget: Budget, *, steps: int, tokens: int, cost: float | None, wall_clock_ms: int
) -> str | None:
    """Which axis, if any, has been reached. Names match the recorded ``termination`` values.

    ``cost`` is ``None`` when no cost basis is declared, and the cost axis is then not checked.
    A pipeline that sets ``max_cost`` without a basis is refused before it runs.
    """
    if budget.max_steps is not None and steps >= budget.max_steps:
        return "max_steps"
    if budget.max_tokens is not None and tokens >= budget.max_tokens:
        return "max_tokens"
    if budget.max_cost is not None and cost is not None and cost >= budget.max_cost:
        return "max_cost"
    if budget.max_wall_clock_ms is not None and wall_clock_ms >= budget.max_wall_clock_ms:
        return "max_wall_clock"
    return None
