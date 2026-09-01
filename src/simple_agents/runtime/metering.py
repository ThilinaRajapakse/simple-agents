"""Metering what a call spends, at the moment the response comes back."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from ..context import RunContext
from ..errors import CallerFacingError, ConfigurationError, ModelFacingError
from ..tools import SpendMeter, Tool


class _Metered:
    """What one tool call spent, from the tool's own report or from its declaration.

    A tool taking a ``SpendMeter`` is authoritative and reporting nothing means the call cost
    nothing, which is how a cache hit inside a tool reaches ``spent: null``. Every other tool
    falls back to its declared per-call price.
    """

    def __init__(self, tool: Tool | None, run: RunContext | None = None) -> None:
        self._tool = tool
        self._run = run
        self._params = (
            [param for param, kind in tool.handles.items() if issubclass(kind, SpendMeter)]
            if tool is not None
            else []
        )
        self._reported: float | None = None
        self._currency: str | None = None
        self._sources: set[str] = set()
        self._written: dict[str, Any] | None = None

    @property
    def measured(self) -> bool:
        """Whether the tool reports its own spend rather than being priced by declaration."""
        return bool(self._params)

    def fill(self, handles: dict[str, Any] | None) -> dict[str, Any] | None:
        if not self._params:
            return handles
        filled = dict(handles or {})
        for param in self._params:
            filled[param] = SpendMeter(_spend=self._record)
        return filled

    def _record(self, amount: float, currency: str | None, source: str = "measured") -> None:
        self._refuse_a_second_currency(currency)
        self._reported = (self._reported or 0.0) + amount
        self._currency = currency or self._currency
        self._sources.add(source)
        if currency is not None and self._run is not None:
            self._run.fix_money_currency(currency, f"the spend reported by {self._name!r}")

    @property
    def _name(self) -> str:
        return self._tool.name if self._tool is not None else "a tool"

    def _refuse_a_second_currency(self, currency: str | None) -> None:
        """A run has one currency, and a reported figure is added to the run's totals.

        The declared currencies are checked before the run and a reported one is not, so this
        is the same rule applied where the value enters. Without it a tool reporting 100 JPY
        under a USD basis reaches ``charged_cost`` as 100, and ``max_cost`` is depleted by it.

        A run with no cost basis has nothing to check the first figure against, so that figure
        fixes the run's currency and every later one is checked against it. Otherwise two tools
        reporting different currencies would sum, which is the case a paid tool in a pipeline of
        `Deterministic` nodes reaches, where no basis is required.
        """
        if currency is None:
            return
        name = self._name
        # Nearest first, so the message names this call before the run and the run before a
        # declaration: each is true, and the nearest one is the edit that fixes it.
        against = [
            (self._currency, f"an earlier spend reported by {name!r}"),
            self._run.money_currency() if self._run is not None else None,
            (
                self._tool.declared_cost.currency
                if self._tool is not None and self._tool.declared_cost
                else None,
                f"the declared_cost of {name!r}",
            ),
        ]
        for fixed in against:
            if fixed is None:
                continue
            other, where = fixed
            if other and other != currency:
                raise ConfigurationError(
                    f"Tool {name!r} reported spend in {currency} and {where} is in {other}. "
                    f"A run's totals are one number and two currencies cannot be added, so "
                    f"this would reach charged_cost as though it were {other} and deplete "
                    f"max_cost by it.\n"
                    f"Report the figure in {other}, converting it in the tool where the "
                    f"vendor bills in something else, or run this tool under a cost basis "
                    f"declaring {currency}."
                )

    @property
    def amount(self) -> float | None:
        """What :meth:`report` wrote to the record, which is what the budget is charged."""
        return self._written["amount"] if self._written else None

    def report(self, *, replayed: bool, failed: bool) -> dict[str, Any] | None:
        """What this call cost, or ``None`` where it cost nothing.

        A call served from the cassette made no request, and a declared-price call that
        raised bought nothing. Both reach the tool's price and neither is spend. A tool
        holding a meter is taken at its word on both, so one charged for work that then
        failed reports what it was charged.
        """
        self._written = self._figure(replayed=replayed, failed=failed)
        return self._written

    def _figure(self, *, replayed: bool, failed: bool) -> dict[str, Any] | None:
        tool = self._tool
        if tool is None:
            return None
        declared = tool.declared_cost
        if self.measured:
            if self._reported is None:
                return None
            currency = self._currency or (declared.currency if declared else None)
            return {
                "currency": currency,
                "amount": self._reported,
                # A tool reporting a price it was told is not a measurement. Any measured
                # figure in the call makes the total one, since the rest was measured too.
                "source": "measured" if "measured" in self._sources else "declared",
            }
        if replayed or failed:
            return None
        if declared is None or declared.per_call is None:
            return None
        return {
            "currency": declared.currency,
            "amount": declared.per_call,
            "source": "declared",
        }


def _refuse_unaffordable_call(run: RunContext, tool: Tool) -> None:
    """Tell the model, before the call, that the cost limit leaves no room for it.

    Checked against the most one call can cost rather than against what it usually costs, so
    the limit holds without the run ever having to be stopped. A tool that declares no
    ceiling is checked against its per-call price, and the run can then exceed the limit by
    whatever one call cost beyond it.
    """
    limit = run.remaining_budget().max_cost
    declared = tool.declared_cost
    if limit is None or declared is None:
        return
    ceiling = declared.ceiling
    if ceiling is None or ceiling <= limit:
        return
    raise ModelFacingError(
        f"This run's cost limit leaves {limit:.6f} {declared.currency}, and one call to "
        f"{tool.name!r} costs up to {ceiling:.6f}. Do not call it again. Answer with what has "
        f"already been found, and say what is still unverified.",
        retryable=False,
    )


def _refuse_bounded_cost(run: RunContext, cost: Any) -> None:
    """End the run where ``max_cost`` would be enforced against a figure that is a bound.

    A compute-basis call whose backend reported no concurrency is charged the whole device,
    which is as much as several times what it cost. Terminating on that figure ends runs that
    were inside their limit, and the work discarded is paid for again on the re-run.
    """
    if not cost.is_upper_bound or run.budget.max_cost is None:
        return
    raise CallerFacingError(
        f"This run sets max_cost={run.budget.max_cost} and the cost of a call it just made is "
        f"an upper bound rather than a measurement: {cost.reason}. Enforcing the limit against "
        f"that figure would stop the run before its real spend reached the limit.\n"
        f"Have the backend report how many requests it had in flight: "
        f"VLLMClient(..., report_concurrency=True), which is the default. For a client that "
        f"cannot report it, bound the run with max_wall_clock_ms, which is exact and needs no "
        f"cost basis, or set max_cost=None to record the bound without enforcing it."
    )


def _cost_record(tool: Tool) -> dict[str, Any] | None:
    return tool.declared_cost.to_record() if tool.declared_cost is not None else None


@dataclass(frozen=True, slots=True)
class _ToolOutcome:
    """What one tool call produced, and what any model calls inside it consumed."""

    value: Any = None
    error: str | None = None
    raised: ModelFacingError | None = None
    """The failure itself, for a caller that catches a kind of it rather than reading the text.

    The agent loop hands the model ``error`` and never needs this. ``ctx.call_tool`` re-raises
    it, so a node body catching :class:`Throttled` catches the one the tool raised.
    """
    calls: int = 0
    tokens: int = 0
    cost: float | None = None
