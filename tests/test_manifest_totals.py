"""What the manifest's `counts` and `totals` report, across a resume and across two units.

Both were measured wrong: a resumed run dropped its delegation count, and a run measured in
device-seconds added them to a tool's money spend and reported the sum as `charged_cost`.
"""

from __future__ import annotations

import json

from simple_agents.cost import DeviceBasis, PriceBasis, basis_to_manifest
from simple_agents.records.manifest import Manifest
from simple_agents.records.trajectory import RECORD_TYPES

PRICE = PriceBasis(currency="USD", input_uncached_per_mtok=3.0, output_per_mtok=15.0)


def manifest(**overrides: object) -> Manifest:
    fields: dict[str, object] = {
        "run_id": "run_1",
        "started_at": "2026-08-13T09:00:00.000Z",
        "seed": 41,
        "budget": {
            "max_steps": None,
            "max_tokens": None,
            "max_cost": None,
            "max_wall_clock_ms": None,
        },
        "library_version": "0.0.0",
        "trajectory_path": "runs/run_1/trajectory.jsonl",
        "workspace_path": "runs/run_1/workspace",
    }
    fields.update(overrides)
    return Manifest(**fields)  # type: ignore[arg-type]


class TestCountsAcrossAResume:
    def test_every_record_type_survives_a_restore(self) -> None:
        """A resumed run continues one manifest, so its counts are the whole run's."""
        first = manifest()
        for kind in RECORD_TYPES:
            first.count_record(kind)

        restored = Manifest.restore(json.loads(json.dumps(first.to_json())))

        counts = restored.to_json()["counts"]
        assert all(counts[kind] == 1 for kind in RECORD_TYPES)
        assert counts["records"] == len(RECORD_TYPES)

    def test_a_delegation_made_before_the_stop_is_still_counted_after_it(self) -> None:
        first = manifest()
        first.count_record("delegation")
        first.count_record("delegation")
        first.count_record("model_call")

        restored = Manifest.restore(json.loads(json.dumps(first.to_json())))
        restored.count_record("model_call")

        counts = restored.to_json()["counts"]
        assert counts["delegation"] == 2
        assert counts["model_call"] == 2
        assert counts["records"] == 4


class TestChargedCost:
    def test_money_is_model_spend_and_tool_spend_together(self) -> None:
        one = manifest(cost_basis=basis_to_manifest(PRICE))
        one.set_tool_spend({"amount": 0.01, "currency": "USD", "calls": 1, "source": "declared"})
        one.set_charged_cost(0.397)

        assert one.to_json()["totals"]["charged_cost"] == 0.397

    def test_a_device_run_charges_its_tool_spend_and_not_its_device_seconds(self) -> None:
        """Device-seconds are what the run used. Adding them to money totals nothing."""
        one = manifest(cost_basis=basis_to_manifest(DeviceBasis(device="RTX-3090")))
        one.set_cost({"value": 0.387, "currency": "device_seconds", "basis": "device"})
        one.set_tool_spend({"amount": 0.01, "currency": "USD", "calls": 1, "source": "declared"})
        one.set_charged_cost(0.397)

        totals = one.to_json()["totals"]
        assert totals["charged_cost"] == 0.01
        assert totals["cost"]["currency"] == "device_seconds"

    def test_a_device_run_that_bought_nothing_charges_nothing(self) -> None:
        one = manifest(cost_basis=basis_to_manifest(DeviceBasis(device="RTX-3090")))
        one.set_tool_spend({"amount": None, "currency": None, "calls": 0, "source": None})
        one.set_charged_cost(0.387)

        assert one.to_json()["totals"]["charged_cost"] is None

    def test_a_run_pricing_some_models_in_each_unit_reports_no_money_figure(self) -> None:
        basis = basis_to_manifest(
            {"mistral-small-2603": PRICE, "Qwen/Qwen3-8B": DeviceBasis(device="RTX-3090")}
        )
        one = manifest(cost_basis=basis)
        one.set_tool_spend({"amount": 0.01, "currency": "USD", "calls": 1, "source": "declared"})
        one.set_charged_cost(0.397)

        assert one.to_json()["totals"]["charged_cost"] is None

    def test_a_run_with_no_basis_reports_what_it_was_charged(self) -> None:
        one = manifest()
        one.set_charged_cost(None)

        assert one.to_json()["totals"]["charged_cost"] is None
