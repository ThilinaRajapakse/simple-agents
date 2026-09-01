"""Cost is derived from the record and the manifest's basis, and says how good the figure is.

FT-27 fails a stored cost figure under either basis. These tests cover the two derivations,
the cases where an input is missing, and the qualification that has to survive to the reader.
"""

from __future__ import annotations

import pytest

from simple_agents.cost import (
    ComputeBasis,
    Cost,
    DeviceBasis,
    PriceBasis,
    cost_of,
    total_cost,
)

PRICE = PriceBasis(
    currency="USD",
    input_uncached_per_mtok=3.00,
    input_cache_read_per_mtok=0.30,
    output_per_mtok=15.00,
    cache_write_per_mtok_by_ttl={"5m": 3.75, "1h": 6.00},
)

COMPUTE = ComputeBasis(currency="USD", device="H100-80GB", device_count=1, hourly_rate=3.60)


def model_call(
    *,
    tokens: dict[str, object] | None = None,
    started_at: str = "2026-07-26T09:00:00.000Z",
    ended_at: str | None = "2026-07-26T09:00:10.000Z",
    concurrent_requests: int | None = 4,
) -> dict[str, object]:
    return {
        "record_type": "model_call",
        "record_id": "r2",
        "started_at": started_at,
        "ended_at": ended_at,
        "concurrent_requests": concurrent_requests,
        "tokens": tokens
        if tokens is not None
        else {
            "input_uncached": 1_000_000,
            "input_cache_read": 0,
            "input_cache_write": 0,
            "cache_ttl": None,
            "output": 0,
        },
    }


class TestPriceBasis:
    def test_each_token_class_is_priced_at_its_own_rate(self) -> None:
        cost = cost_of(
            model_call(
                tokens={
                    "input_uncached": 1_000_000,
                    "input_cache_read": 1_000_000,
                    "input_cache_write": 1_000_000,
                    "cache_ttl": "5m",
                    "output": 1_000_000,
                }
            ),
            PRICE,
        )

        assert cost.value == pytest.approx(3.00 + 0.30 + 3.75 + 15.00)
        assert cost.is_upper_bound is False

    def test_cache_read_is_not_charged_at_the_uncached_rate(self) -> None:
        # A single input figure costed at the uncached rate would return 3.00 here. On a
        # workload with a large cached prefix that error is most of the bill.
        cost = cost_of(
            model_call(
                tokens={
                    "input_uncached": 0,
                    "input_cache_read": 1_000_000,
                    "input_cache_write": 0,
                    "cache_ttl": None,
                    "output": 0,
                }
            ),
            PRICE,
        )

        assert cost.value == pytest.approx(0.30)

    def test_cache_write_rate_is_selected_by_ttl(self) -> None:
        long_ttl = cost_of(
            model_call(
                tokens={
                    "input_uncached": 0,
                    "input_cache_read": 0,
                    "input_cache_write": 1_000_000,
                    "cache_ttl": "1h",
                    "output": 0,
                }
            ),
            PRICE,
        )

        assert long_ttl.value == pytest.approx(6.00)

    def test_cache_write_at_an_undeclared_ttl_is_unknown_not_free(self) -> None:
        basis = PriceBasis(
            currency="USD",
            input_uncached_per_mtok=3.00,
            output_per_mtok=15.00,
            cache_write_per_mtok_by_ttl={"5m": 3.75},
        )

        cost = cost_of(
            model_call(
                tokens={
                    "input_uncached": 0,
                    "input_cache_read": 0,
                    "input_cache_write": 500,
                    "cache_ttl": "24h",
                    "output": 0,
                }
            ),
            basis,
        )

        assert cost.value is None
        assert "no cache-write rate" in (cost.reason or "")

    def test_unknown_token_count_prices_as_unknown(self) -> None:
        # `input_cache_read` is unknown when a backend does not report cached prefix tokens.
        # Treating it as zero would understate the call.
        cost = cost_of(
            model_call(
                tokens={
                    "input_uncached": 1000,
                    "input_cache_read": {"type": "unknown", "reason": "not reported"},
                    "input_cache_write": 0,
                    "cache_ttl": None,
                    "output": 100,
                }
            ),
            PRICE,
        )

        assert cost.value is None
        assert "tokens.input_cache_read is unknown" in (cost.reason or "")

    def test_missing_token_field_prices_as_unknown(self) -> None:
        cost = cost_of(model_call(tokens={"input_uncached": 10}), PRICE)

        assert cost.value is None
        assert "missing from the record" in (cost.reason or "")

    def test_an_unknown_count_at_a_zero_rate_still_prices(self) -> None:
        # Gemini writes to a cache it reports no count for and bills that class per
        # token-hour of storage rather than per token written. A basis declaring the rate as
        # 0.0 prices the call exactly, since no value of that count changes the total.
        basis = PriceBasis(
            currency="USD",
            input_uncached_per_mtok=0.25,
            input_cache_read_per_mtok=0.025,
            input_cache_write_per_mtok=0.0,
            output_per_mtok=1.50,
        )

        cost = cost_of(
            model_call(
                tokens={
                    "input_uncached": 1_000_000,
                    "input_cache_read": 0,
                    "input_cache_write": {"type": "unknown", "reason": "no count reported"},
                    "cache_ttl": None,
                    "output": 0,
                }
            ),
            basis,
        )

        assert cost.value == pytest.approx(0.25)
        assert cost.reason is None


class TestComputeBasis:
    def test_duration_is_divided_by_requests_in_flight(self) -> None:
        # Ten seconds on one device at 3.60/hour is 0.01. Four requests shared it.
        cost = cost_of(model_call(concurrent_requests=4), COMPUTE)

        assert cost.value == pytest.approx(0.01 / 4)
        assert cost.is_upper_bound is False

    def test_device_count_multiplies(self) -> None:
        sharded = ComputeBasis(currency="USD", device="H100-80GB", device_count=4, hourly_rate=3.60)

        cost = cost_of(model_call(concurrent_requests=1), sharded)

        assert cost.value == pytest.approx(0.04)

    def test_unreported_concurrency_gives_an_upper_bound(self) -> None:
        cost = cost_of(model_call(concurrent_requests=None), COMPUTE)

        assert cost.value == pytest.approx(0.01)
        assert cost.is_upper_bound is True
        assert "no concurrency" in (cost.reason or "")

    def test_upper_bound_says_so_when_described(self) -> None:
        assert (
            cost_of(model_call(concurrent_requests=None), COMPUTE).describe().startswith("at most")
        )

    def test_nonsense_concurrency_is_treated_as_unreported(self) -> None:
        cost = cost_of(model_call(concurrent_requests=0), COMPUTE)

        assert cost.is_upper_bound is True

    def test_a_call_that_never_ended_has_no_cost(self) -> None:
        cost = cost_of(model_call(ended_at=None), COMPUTE)

        assert cost.value is None
        assert "no ended_at" in (cost.reason or "")


class TestNoBasis:
    def test_absent_basis_gives_unknown_rather_than_zero(self) -> None:
        cost = cost_of(model_call(), None)

        assert cost.value is None
        assert cost.reason == "no cost basis declared in the manifest"
        assert cost.describe().startswith("unknown")

    def test_non_model_records_are_refused(self) -> None:
        with pytest.raises(ValueError, match="takes a model_call record"):
            cost_of({"record_type": "node_execution"}, PRICE)


class TestTotals:
    def test_only_model_calls_contribute(self) -> None:
        records = [
            {"record_type": "node_execution"},
            model_call(concurrent_requests=1),
            {"record_type": "tool_call"},
            model_call(concurrent_requests=1),
        ]

        assert total_cost(records, COMPUTE).value == pytest.approx(0.02)

    def test_one_unknown_call_makes_the_total_unknown(self) -> None:
        total = total_cost([model_call(), model_call(ended_at=None)], COMPUTE)

        assert total.value is None
        assert "no ended_at" in (total.reason or "")

    def test_one_bounded_call_makes_the_total_a_bound(self) -> None:
        total = total_cost(
            [model_call(concurrent_requests=2), model_call(concurrent_requests=None)], COMPUTE
        )

        assert total.is_upper_bound is True

    def test_an_empty_trajectory_costs_zero(self) -> None:
        assert total_cost([], PRICE) == Cost(value=0.0, currency="USD", basis="price")

    def test_two_units_do_not_add_into_one_total(self) -> None:
        """Device-seconds are what a run used and money is what it was charged."""
        total = Cost(value=0.387, currency="device_seconds", basis="device").plus(
            Cost(value=0.01, currency="USD", basis="price")
        )

        assert total.value is None
        assert "device_seconds" in (total.reason or "") and "USD" in (total.reason or "")

    def test_a_run_mixing_a_device_basis_and_a_price_basis_totals_unknown(self) -> None:
        hosted = model_call(concurrent_requests=1)
        hosted["request_model"] = "mistral-small-2603"
        local = model_call(concurrent_requests=1)
        local["request_model"] = "Qwen/Qwen3-8B"

        total = total_cost(
            [hosted, local],
            {"mistral-small-2603": PRICE, "Qwen/Qwen3-8B": DeviceBasis(device="RTX-3090")},
        )

        assert total.value is None
        assert "do not add" in (total.reason or "")


class TestManifest:
    def test_price_basis_round_trips_its_rates(self) -> None:
        recorded = PRICE.to_manifest()

        assert recorded["kind"] == "price"
        assert recorded["cache_write_per_mtok_by_ttl"] == {"5m": 3.75, "1h": 6.00}

    def test_compute_basis_records_the_device(self) -> None:
        recorded = COMPUTE.to_manifest()

        assert recorded["kind"] == "compute"
        assert recorded["device"] == "H100-80GB"
        assert recorded["hourly_rate"] == 3.60
