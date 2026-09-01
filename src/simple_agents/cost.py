"""Deriving cost from a record and the cost basis declared in the manifest.

Records store no cost figure. Cost is computed from the record's inputs against the basis in
the manifest, so a trajectory read after a rate change re-prices correctly
(``docs/run-envelope.md`` §4).

Two bases, one per backend. :class:`PriceBasis` covers a hosted API and holds per-token-class
rates. :class:`ComputeBasis` covers self-hosted serving and holds a device rate, charged
across the requests the server had in flight.

Where an input needed for the sum is missing, :class:`Cost` reports the result as unknown or
as an upper bound and names what was missing::

    basis = PriceBasis(currency="USD", input_uncached_per_mtok=3.0, output_per_mtok=15.0)
    cost = total_cost(read_trajectory("runs/run_7/trajectory.jsonl"), basis)
    print(cost.describe())
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Iterable, Literal, Mapping

__all__ = [
    "Cost",
    "PriceBasis",
    "ComputeBasis",
    "DeviceBasis",
    "DEVICE_SECONDS",
    "CostBasis",
    "CostBases",
    "basis_for",
    "basis_to_manifest",
    "currencies_in",
    "cost_of",
    "total_cost",
    "tool_spend",
]

_PER_MILLION = 1_000_000


def _added(one: float | None, two: float | None) -> float | None:
    """Two floors added. Absent on both sides stays absent, and absent on one is skipped."""
    if one is None and two is None:
        return None
    return (one or 0.0) + (two or 0.0)


@dataclass(frozen=True, slots=True)
class Cost:
    """A derived cost, and what is known about the figure.

    ``value`` is ``None`` when the basis or an input needed to compute it was absent;
    ``reason`` names what was missing. ``is_upper_bound`` is ``True`` when the figure is at or
    above the real cost, which happens under a compute basis when the backend reports no
    concurrency.

    ``measured`` is what the calls that could be priced came to, and it survives a call that
    could not. So a total that is ``None`` still says what was spent, with ``priced_calls`` and
    ``unpriced_calls`` saying how much of the run it covers::

        total = total_cost(read_trajectory("runs/run_7/trajectory.jsonl"), basis)
        total.value          # None, because one call reported no token count
        total.measured       # 5.5024, over the calls that did
        total.unpriced_calls # 54

    ``value`` is the figure to report and ``measured`` is a floor beneath it, never a
    substitute: an unmeasured token count is not zero, so a run with one unpriced call has no
    total. Both are on the record, and :meth:`describe` states which is which.

    A budget may be enforced against an upper bound. A result reported to a reader states
    that it is one, which :meth:`describe` does.
    """

    value: float | None
    currency: str | None
    basis: str | None
    is_upper_bound: bool = False
    reason: str | None = None
    measured: float | None = None
    priced_calls: int = 0
    unpriced_calls: int = 0

    @property
    def known(self) -> bool:
        return self.value is not None

    @property
    def calls(self) -> int:
        """How many model calls this figure was derived over, priced and unpriced together."""
        return self.priced_calls + self.unpriced_calls

    def describe(self) -> str:
        """The figure as text, carrying its own qualification: ``at most 0.004120 USD``.

        A figure that has no total but does have a floor says both, and says how many calls
        are missing from it::

            cost.describe()
            # 'at least 5.502400 USD, and 54 of 994 call(s) could not be priced: ...'
        """
        if self.value is not None:
            figure = f"{self.value:.6f} {self.currency}"
            return f"at most {figure}" if self.is_upper_bound else figure
        if self.measured is not None:
            floor = f"at least {self.measured:.6f} {self.currency}".rstrip()
            missing = (
                f"{self.unpriced_calls:,} of {self.calls:,} call(s) could not be priced"
                if self.calls
                else "some calls could not be priced"
            )
            return f"{floor}, and {missing}" + (f": {self.reason}" if self.reason else "")
        return f"unknown ({self.reason})" if self.reason else "unknown"

    def to_record(self) -> dict[str, Any]:
        """The figure as plain data, for a manifest or a results file.

        All eight keys are always present. ``value`` is ``null`` where the total could not be
        derived and ``measured`` is ``null`` where nothing could be priced at all::

            total.to_record()
            # {'value': None, 'currency': 'USD', 'basis': 'price', 'is_upper_bound': False,
            #  'reason': '...', 'measured': 5.5024, 'priced_calls': 940,
            #  'unpriced_calls': 54}
        """
        return {
            "value": self.value,
            "currency": self.currency,
            "basis": self.basis,
            "is_upper_bound": self.is_upper_bound,
            "reason": self.reason,
            "measured": self.measured,
            "priced_calls": self.priced_calls,
            "unpriced_calls": self.unpriced_calls,
        }

    @classmethod
    def from_record(cls, raw: Mapping[str, Any] | None) -> Cost:
        """Read back what :meth:`to_record` wrote. A record missing a key reads its default."""
        raw = raw or {}
        return cls(
            value=raw.get("value"),
            currency=raw.get("currency"),
            basis=raw.get("basis"),
            is_upper_bound=bool(raw.get("is_upper_bound")),
            reason=raw.get("reason"),
            measured=raw.get("measured"),
            priced_calls=int(raw.get("priced_calls") or 0),
            unpriced_calls=int(raw.get("unpriced_calls") or 0),
        )

    def _floor(self) -> float | None:
        """What this figure contributes to a sum's floor.

        Its own ``measured`` where it has one, and its ``value`` where it does not: a figure
        that priced is its own floor, however it was built.
        """
        return self.measured if self.measured is not None else self.value

    def _carried(self, other: Cost) -> dict[str, Any]:
        """The fields a sum takes from its two sides whatever happens to the value."""
        return {
            "currency": self.currency or other.currency,
            "basis": self.basis or other.basis,
            "is_upper_bound": self.is_upper_bound or other.is_upper_bound,
            "priced_calls": self.priced_calls + other.priced_calls,
            "unpriced_calls": self.unpriced_calls + other.unpriced_calls,
        }

    def _mixed(self, other: Cost) -> Cost:
        """The sum of two figures in different units, which is no sum at all.

        Two currencies do not add, so neither do the two floors.
        """
        return Cost(
            value=None,
            reason=(
                f"this run prices some calls in {self.currency} and some in "
                f"{other.currency}, and the two do not add into one total"
            ),
            measured=None,
            **{**self._carried(other), "currency": None},
        )

    def plus(self, other: Cost) -> Cost:
        """Add two costs. Unknown plus anything is unknown, and the bound flag carries over.

        ``measured`` and the two call counts add whatever happens to ``value``, so the floor
        under an unknown total is the sum of the calls that priced.

        Two figures in different units do not add, and the sum is unknown naming both.
        ``device_seconds`` is what a run used and money is what it was charged, so a run
        pricing some calls one way and some the other has no single total::

            Cost(0.4, "device_seconds", "device").plus(Cost(0.01, "USD", "price")).value
            # None
        """
        if self.currency and other.currency and self.currency != other.currency:
            return self._mixed(other)
        unknown = next((one for one in (self, other) if one.value is None), None)
        return Cost(
            value=None if unknown else (self.value or 0.0) + (other.value or 0.0),
            reason=unknown.reason if unknown else None,
            measured=_added(self._floor(), other._floor()),
            **self._carried(other),
        )


@dataclass(frozen=True, slots=True)
class PriceBasis:
    """Per-token-class rates for a hosted API. Every rate is per million tokens.

    ``cache_write_per_mtok_by_ttl`` holds rates that vary by cache TTL, keyed by the TTL
    string as it appears on the record. ``input_cache_write_per_mtok`` covers a TTL not listed
    there, and a provider with one cache-write rate::

        PriceBasis(
            currency="USD",
            input_uncached_per_mtok=3.00,
            input_cache_read_per_mtok=0.30,
            output_per_mtok=15.00,
            cache_write_per_mtok_by_ttl={"5m": 3.75, "1h": 6.00},
        )

    A call that wrote cache tokens at a TTL with no rate prices as unknown rather than as
    zero.
    """

    currency: str
    input_uncached_per_mtok: float
    output_per_mtok: float
    input_cache_read_per_mtok: float = 0.0
    input_cache_write_per_mtok: float | None = None
    cache_write_per_mtok_by_ttl: Mapping[str, float] = field(default_factory=dict)

    kind: Literal["price"] = "price"

    def to_manifest(self) -> dict[str, Any]:
        """The basis as the run manifest records it."""
        return {
            "kind": "price",
            "currency": self.currency,
            "input_uncached_per_mtok": self.input_uncached_per_mtok,
            "input_cache_read_per_mtok": self.input_cache_read_per_mtok,
            "input_cache_write_per_mtok": self.input_cache_write_per_mtok,
            "cache_write_per_mtok_by_ttl": dict(self.cache_write_per_mtok_by_ttl),
            "output_per_mtok": self.output_per_mtok,
        }


@dataclass(frozen=True, slots=True)
class ComputeBasis:
    """Device rate for self-hosted serving.

    ``hourly_rate`` is the cost of one device for one hour. ``device_count`` is how many
    devices serve the model, so a model sharded over four GPUs charges four devices' time::

        ComputeBasis(currency="USD", device="H100-80GB", device_count=1, hourly_rate=2.69)

    A call is charged its own share of the device: duration times ``device_count``, divided by
    the requests in flight alongside it. Where the backend reports no concurrency, the whole
    device is charged to the call and the result is an upper bound.
    """

    currency: str
    device: str
    device_count: int
    hourly_rate: float

    kind: Literal["compute"] = "compute"

    def to_manifest(self) -> dict[str, Any]:
        """The basis as the run manifest records it."""
        return {
            "kind": "compute",
            "currency": self.currency,
            "device": self.device,
            "device_count": self.device_count,
            "hourly_rate": self.hourly_rate,
        }


DEVICE_SECONDS = "device_seconds"
"""The unit a ``DeviceBasis`` reports in. Not a currency: it names what was measured, so a
figure in it is never added to one in money."""


@dataclass(frozen=True, slots=True)
class DeviceBasis:
    """What a self-hosted run consumed, measured in device-seconds and priced at nothing.

    For a device the project already owns, where no hour is billed to anyone::

        DeviceBasis(device="RTX-3090", device_count=1)

    A call is charged ``duration × device_count ÷ concurrent_requests``, the same arithmetic
    ``ComputeBasis`` uses without the rate, so a run reports what it used rather than a figure
    derived from a rate nobody pays. ``max_cost`` cannot bind against it, because
    device-seconds are not money; bound such a run with ``max_wall_clock_ms``.

    Declare a ``ComputeBasis`` instead where the hour is billed to someone.
    """

    device: str
    device_count: int = 1

    kind: Literal["device"] = "device"

    def to_manifest(self) -> dict[str, Any]:
        """The basis as the run manifest records it."""
        return {
            "kind": "device",
            "device": self.device,
            "device_count": self.device_count,
        }


CostBasis = PriceBasis | ComputeBasis | DeviceBasis

CostBases = CostBasis | Mapping[str, "CostBasis"]
"""One basis, or one per model keyed by ``request_model``.

A run whose nodes call different models needs the second form, because per-token rates belong
to one model and a device rate to one deployment::

    {"mistral-large-2512": PriceBasis(currency="USD", input_uncached_per_mtok=2.0,
                                      output_per_mtok=6.0),
     "Qwen/Qwen3-1.7B":    ComputeBasis(currency="USD", device="RTX3090", device_count=1,
                                        hourly_rate=0.22)}
"""


def basis_for(basis: CostBases | None, request_model: Any) -> CostBasis | None:
    """The basis that prices a call to this model, or ``None`` where none does::

        basis_for(envelope.cost_basis, record["request_model"])

    One basis prices every call. A mapping prices the models it names and nothing else, so a
    model it does not name has no cost rather than a cost derived from another model's rates.
    """
    if basis is None:
        return None
    if isinstance(basis, Mapping):
        return basis.get(str(request_model or "")) if request_model else None
    return basis


def basis_to_manifest(basis: CostBases | None) -> dict[str, Any] | None:
    """The basis as the run manifest records it, in either form.

    One basis records the object it already recorded. A mapping records ``kind`` of
    ``by_model`` and the bases under ``bases``, so ``kind`` stays what a reader switches on.
    """
    if basis is None:
        return None
    if isinstance(basis, Mapping):
        return {
            "kind": "by_model",
            "bases": {model: one.to_manifest() for model, one in sorted(basis.items())},
        }
    return basis.to_manifest()


def basis_from_manifest(raw: Any) -> CostBases | None:
    """The basis a run recorded, rebuilt from its manifest, or ``None`` where it recorded none.

    The inverse of :func:`basis_to_manifest`, for a reader that has the runs and not the
    envelope that wrote them. Cost derived through it is the arithmetic the run itself did::

        basis = basis_from_manifest(run.manifest.get("cost_basis"))
        node_metrics("runs/", cost_basis=basis)["hunt"].cost

    Returns ``None`` for a block whose ``kind`` this library does not write, so a manifest from
    a later version reports unknown cost rather than a figure derived from a basis read
    wrongly.
    """
    if not isinstance(raw, Mapping):
        return None
    kind = raw.get("kind")
    if kind == "by_model":
        bases = {
            str(model): one
            for model, entry in (raw.get("bases") or {}).items()
            if (one := basis_from_manifest(entry)) is not None and not isinstance(one, Mapping)
        }
        return bases or None
    if kind == "price":
        # A rate that is not there is not a rate of zero: a basis missing one prices nothing
        # rather than pricing those tokens free, which is the rule `_add_tokens` follows for a
        # count the backend did not report.
        uncached = _as_float(raw.get("input_uncached_per_mtok"))
        output = _as_float(raw.get("output_per_mtok"))
        if uncached is None or output is None or not raw.get("currency"):
            return None
        return PriceBasis(
            currency=str(raw["currency"]),
            input_uncached_per_mtok=uncached,
            output_per_mtok=output,
            input_cache_read_per_mtok=_as_float(raw.get("input_cache_read_per_mtok")) or 0.0,
            input_cache_write_per_mtok=_as_float(raw.get("input_cache_write_per_mtok")),
            cache_write_per_mtok_by_ttl={
                str(ttl): float(rate)
                for ttl, rate in (raw.get("cache_write_per_mtok_by_ttl") or {}).items()
                if isinstance(rate, (int, float))
            },
        )
    if kind == "compute":
        hourly = _as_float(raw.get("hourly_rate"))
        if hourly is None or not raw.get("currency"):
            return None
        return ComputeBasis(
            currency=str(raw["currency"]),
            device=str(raw.get("device") or ""),
            device_count=int(raw.get("device_count") or 1),
            hourly_rate=hourly,
        )
    if kind == "device":
        return DeviceBasis(
            device=str(raw.get("device") or ""),
            device_count=int(raw.get("device_count") or 1),
        )
    return None


def _as_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def currencies_in(basis: CostBases | None) -> list[str]:
    """Every currency the basis declares, in the order the models sort.

    A ``DeviceBasis`` declares none: it reports device-seconds, which is a measurement rather
    than money, so it neither fixes a run's currency nor conflicts with one that does.
    """
    if basis is None:
        return []
    if isinstance(basis, Mapping):
        return [
            one.currency for _, one in sorted(basis.items()) if not isinstance(one, DeviceBasis)
        ]
    return [] if isinstance(basis, DeviceBasis) else [basis.currency]


def _unit_of(basis: CostBases | None) -> str | None:
    """What a figure under ``basis`` is denominated in, before any call has been priced.

    ``device_seconds`` under a :class:`DeviceBasis`, which is what :func:`cost_of` reports for
    a call priced under one. Without this a run that made no model call reports a figure of
    zero with no unit beside it, where a run that made one reports the unit.
    """
    if basis is None:
        return None
    if isinstance(basis, DeviceBasis):
        return DEVICE_SECONDS
    return (currencies_in(basis) or [None])[0]


def _basis_kind(basis: CostBases | None) -> str | None:
    if basis is None:
        return None
    return "by_model" if isinstance(basis, Mapping) else basis.kind


def cost_of(record: Mapping[str, Any], basis: CostBases | None) -> Cost:
    """Cost of one ``model_call`` record under ``basis``.

    Passing a record of any other type raises ``ValueError``. Only model calls carry the
    inputs a cost is derived from; a node's cost is the sum over the model calls beneath it,
    which :func:`total_cost` computes. A ``basis`` of ``None`` returns an unknown cost.

    The figure counts itself: one call that priced sets ``priced_calls`` to 1 and ``measured``
    to its own value, and one that did not sets ``unpriced_calls`` to 1. Summing them is what
    gives a total the floor beneath it.
    """
    return _counted(_cost_of(record, basis))


def _counted(figure: Cost) -> Cost:
    """One call's figure, counting itself so a sum of them carries its own provenance."""
    if figure.value is None:
        return replace(figure, measured=None, priced_calls=0, unpriced_calls=1)
    return replace(figure, measured=figure.value, priced_calls=1, unpriced_calls=0)


def _cost_of(record: Mapping[str, Any], basis: CostBases | None) -> Cost:
    """The figure for one call, before it counts itself."""
    if record.get("record_type") != "model_call":
        raise ValueError(
            f"cost_of() takes a model_call record, not {record.get('record_type')!r}. Only "
            f"model calls carry the token counts and duration a cost is derived from. For a "
            f"node's cost or a run's cost, pass the trajectory to total_cost() instead."
        )
    if basis is None:
        return Cost(
            value=None,
            currency=None,
            basis=None,
            reason="no cost basis declared in the manifest",
        )
    chosen = basis_for(basis, record.get("request_model"))
    if chosen is None:
        named = ", ".join(sorted(basis)) if isinstance(basis, Mapping) else ""
        return Cost(
            value=None,
            currency=(currencies_in(basis) or [None])[0],
            basis="by_model",
            reason=(
                f"the cost basis names no rate for model "
                f"{str(record.get('request_model') or 'unnamed')!r}, and it names {named}"
            ),
        )
    if isinstance(chosen, PriceBasis):
        return _price(record, chosen)
    if isinstance(chosen, DeviceBasis):
        return _device(record, chosen)
    return _compute(record, chosen)


def total_cost(records: Iterable[Mapping[str, Any]], basis: CostBases | None) -> Cost:
    """Cost of every ``model_call`` in ``records``. Records of other types are skipped.

    One unknown call makes the total unknown, and one upper bound makes the total an upper
    bound. A total that dropped the calls it could not price would report less than was spent.

    Where ``basis`` is one per model, each call is priced against the basis for the model that
    served it, so a run mixing a hosted model and a self-hosted one totals in one currency
    across two bases.
    """
    running: Cost | None = None
    for record in records:
        if record.get("record_type") != "model_call":
            continue
        one = cost_of(record, basis)
        running = one if running is None else running.plus(one)
    # The zero is returned rather than summed into, so a run that made no priced call reports
    # no floor instead of a floor of nothing. `basis` is the kind the run declared rather than
    # the kind of whichever call came first, which is what a per-model basis reports.
    if running is not None:
        return replace(running, basis=_basis_kind(basis))
    return Cost(value=0.0, currency=_unit_of(basis), basis=_basis_kind(basis))


def tool_spend(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """What the tools in a trajectory cost, summed over the calls that bought something.

    Reads ``spent`` on each ``tool_call``, which is ``null`` on a call served from a cassette,
    one that failed, and one a cache answered. Records of other types are skipped::

        tool_spend(read_trajectory("runs/run_7/trajectory.jsonl"))
        # {"amount": 1.315, "currency": "USD", "calls": 263, "source": "declared"}

    ``source`` is ``measured`` where every figure came from a tool reporting its own charge,
    ``declared`` where every figure came from a price, and ``mixed`` where both appear.
    ``amount`` is ``null`` and ``calls`` is ``0`` where nothing was spent. A run has one
    currency, so the total has one: a declared one that differs is refused before the run, and
    one a ``SpendMeter`` reports is refused at the call that reports it.
    """
    amount = 0.0
    calls = 0
    currency: str | None = None
    sources: set[str] = set()
    for record in records:
        if record.get("record_type") != "tool_call":
            continue
        spent = record.get("spent")
        if not isinstance(spent, Mapping):
            continue
        value = spent.get("amount")
        if not isinstance(value, (int, float)):
            continue
        amount += float(value)
        calls += 1
        currency = currency or spent.get("currency")
        sources.add(str(spent.get("source") or "declared"))
    return {
        "amount": amount if calls else None,
        "currency": currency,
        "calls": calls,
        "source": sources.pop() if len(sources) == 1 else ("mixed" if sources else None),
    }


def _price(record: Mapping[str, Any], basis: PriceBasis) -> Cost:
    tokens = record.get("tokens") or {}
    write_rate = _cache_write_rate(tokens.get("cache_ttl"), basis)

    components: list[tuple[str, float]] = [
        ("input_uncached", basis.input_uncached_per_mtok),
        ("input_cache_read", basis.input_cache_read_per_mtok),
        ("output", basis.output_per_mtok),
    ]
    if write_rate is not None:
        components.append(("input_cache_write", write_rate))

    subtotal = 0.0
    for name, rate in components:
        count = tokens.get(name)
        if _is_unknown(count):
            if rate == 0:
                # No value of this count changes the total, so the price is still exact.
                # A backend that bills a class it does not count is otherwise unpriceable on
                # every call: Gemini writes to a cache it reports no count for, and bills that
                # class per token-hour of storage rather than per token written.
                continue
            return Cost(
                value=None,
                currency=basis.currency,
                basis="price",
                reason=(
                    f"tokens.{name} is unknown on this call. An unmeasured token count is "
                    f"not zero, so the call has no price"
                ),
            )
        if not isinstance(count, (int, float)):
            return Cost(
                value=None,
                currency=basis.currency,
                basis="price",
                reason=f"tokens.{name} is missing from the record",
            )
        subtotal += count / _PER_MILLION * rate

    if write_rate is None and tokens.get("input_cache_write"):
        written = tokens["input_cache_write"]
        how_many = "an unknown number of" if _is_unknown(written) else str(written)
        return Cost(
            value=None,
            currency=basis.currency,
            basis="price",
            reason=(
                f"the call wrote {how_many} tokens to cache at TTL "
                f"{tokens.get('cache_ttl')!r}, and the price basis declares no cache-write "
                f"rate for it. Declare input_cache_write_per_mtok, at 0.0 where the provider "
                f"bills nothing for it"
            ),
        )

    return Cost(value=subtotal, currency=basis.currency, basis="price")


def _cache_write_rate(ttl: Any, basis: PriceBasis) -> float | None:
    if isinstance(ttl, str) and ttl in basis.cache_write_per_mtok_by_ttl:
        return basis.cache_write_per_mtok_by_ttl[ttl]
    return basis.input_cache_write_per_mtok


def _device(record: Mapping[str, Any], basis: DeviceBasis) -> Cost:
    """Device-seconds for one call, with no money in it.

    The same arithmetic ``_compute`` uses, stopping before the rate. ``currency`` is
    ``device_seconds``, which names the unit rather than a currency, so nothing adds this to a
    figure in money: the run's totals are one number and a second unit cannot join it.
    """
    duration_s = _device_seconds(record)
    if duration_s is None:
        return Cost(
            value=None,
            currency=DEVICE_SECONDS,
            basis="device",
            reason=(
                "the call was replayed from a cassette recorded before device time was stored"
                if record.get("replayed")
                else "the call has no ended_at, and device time is how long it ran"
            ),
        )

    concurrency = record.get("concurrent_requests")
    upper_bound = False
    reason: str | None = None
    if not isinstance(concurrency, int) or concurrency < 1:
        upper_bound = True
        reason = (
            "the serving backend reported no concurrency for this call, so the requests in "
            "flight alongside it are counted here too"
        )
        concurrency = 1

    return Cost(
        value=duration_s * basis.device_count / concurrency,
        currency=DEVICE_SECONDS,
        basis="device",
        is_upper_bound=upper_bound,
        reason=reason,
    )


def _compute(record: Mapping[str, Any], basis: ComputeBasis) -> Cost:
    duration_s = _device_seconds(record)
    if duration_s is None:
        if record.get("replayed"):
            return Cost(
                value=None,
                currency=basis.currency,
                basis="compute",
                reason=(
                    "the call was replayed from a cassette recorded before device time was "
                    "stored, so how long the live call took is not on file. Re-record the "
                    "cassette to price this run"
                ),
            )
        return Cost(
            value=None,
            currency=basis.currency,
            basis="compute",
            reason=("the call has no ended_at, and compute cost is duration times a device rate"),
        )

    concurrency = record.get("concurrent_requests")
    upper_bound = False
    reason: str | None = None
    if not isinstance(concurrency, int) or concurrency < 1:
        # Charging the whole device to one request is the largest cost that request could
        # have incurred, so the figure is a bound rather than a measurement.
        upper_bound = True
        reason = (
            "the serving backend reported no concurrency for this call, so the requests in "
            "flight alongside it are charged here too"
        )
        concurrency = 1

    device_seconds = duration_s * basis.device_count / concurrency
    return Cost(
        value=device_seconds * basis.hourly_rate / 3600,
        currency=basis.currency,
        basis="compute",
        is_upper_bound=upper_bound,
        reason=reason,
    )


def _device_seconds(record: Mapping[str, Any]) -> float | None:
    """How long the backend worked on this call, which on a replay is not this run's clock.

    A replayed call returns in microseconds, so its timestamps describe the replay rather than
    the work. ``recorded_duration_ms``, carried over from the cassette, is what the live call
    took, and it is what a compute basis charges.
    """
    if record.get("replayed"):
        recorded = record.get("recorded_duration_ms")
        return recorded / 1000 if isinstance(recorded, (int, float)) else None
    return duration_seconds(record)


def duration_seconds(record: Mapping[str, Any]) -> float | None:
    """How long a record took, or ``None`` when it never completed.

    Duration is derived from the two timestamps and never stored, so anything measuring
    elapsed time reads it from here rather than parsing the stamps again.
    """
    started, ended = record.get("started_at"), record.get("ended_at")
    if not isinstance(started, str) or not isinstance(ended, str):
        return None
    try:
        return (_parse(ended) - _parse(started)).total_seconds()
    except ValueError:
        return None


def _parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def _is_unknown(value: Any) -> bool:
    """The tagged ``unknown`` object from ``docs/trajectory-format.md`` §5.1."""
    return isinstance(value, Mapping) and value.get("type") == "unknown"
