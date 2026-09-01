"""What a `web_search` reports it spent, through the pipeline that fills its meter.

`docs/tools.md` §1.5 says a call a cache answered pays nothing, and §4.5 recommends
`web_search(provider, declared_cost=..., cache=cache)`. The tool used to take no `SpendMeter`,
so it had no route by which to say a hit bought nothing, and the declared price stood on every
call. These run the real composition and read what the trajectory and the manifest say.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Budget,
    DeclaredCost,
    Deterministic,
    Pipeline,
    RunEnvelope,
)
from simple_agents.builtins import UrlCache, web_search
from simple_agents.errors import ModelFacingError

PAID = DeclaredCost(currency="USD", per_call=0.005)
UNBOUNDED = Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def run_two_searches(tmp_path: Path, *, cache: UrlCache | None, budget: Budget = UNBOUNDED):
    """Two identical searches in one node, and what the run recorded for them."""
    calls: list[str] = []

    def provider(query: str, count: int):
        calls.append(query)
        return [{"title": "t", "url": "https://shop.test/a", "snippet": "s"}]

    def go(inputs, ctx):
        ctx.call_tool("web_search", query="ridge tee measurements")
        ctx.call_tool("web_search", query="ridge tee measurements")
        return "done"

    search = web_search(provider, declared_cost=PAID, cache=cache)
    runs = tmp_path / "runs"
    result = Pipeline([Deterministic(go, node_id="find", tools=[search])], budget=budget).run(
        {}, envelope=RunEnvelope(run_dir=str(runs))
    )
    directory = result.paths.root
    records = [
        json.loads(line) for line in (directory / "trajectory.jsonl").read_text().splitlines()
    ]
    manifest = json.loads((directory / "manifest.json").read_text())
    tool_calls = [r for r in records if r.get("record_type") == "tool_call"]
    return calls, tool_calls, manifest


class TestWithACache:
    def test_the_second_search_never_reaches_the_provider(self, tmp_path) -> None:
        calls, _, _ = run_two_searches(tmp_path, cache=UrlCache(tmp_path / "cache"))

        assert calls == ["ridge tee measurements"]

    def test_the_call_that_bought_something_reports_what_it_cost(self, tmp_path) -> None:
        """`source` is `declared`: the figure is the price passed in, not one Brave returned."""
        _, tool_calls, _ = run_two_searches(tmp_path, cache=UrlCache(tmp_path / "cache"))

        assert tool_calls[0]["spent"] == {
            "currency": "USD",
            "amount": 0.005,
            "source": "declared",
        }

    def test_the_call_the_cache_answered_reports_nothing(self, tmp_path) -> None:
        _, tool_calls, _ = run_two_searches(tmp_path, cache=UrlCache(tmp_path / "cache"))

        assert tool_calls[1]["spent"] is None

    def test_both_calls_still_carry_the_declared_price(self, tmp_path) -> None:
        """§1.5: adding up `declared_cost` counts every call; adding up `spent` does not."""
        _, tool_calls, _ = run_two_searches(tmp_path, cache=UrlCache(tmp_path / "cache"))

        assert [c["declared_cost"]["per_call"] for c in tool_calls] == [0.005, 0.005]

    def test_the_manifest_totals_only_what_was_bought(self, tmp_path) -> None:
        _, _, manifest = run_two_searches(tmp_path, cache=UrlCache(tmp_path / "cache"))

        assert manifest["totals"]["tool_spend"]["amount"] == 0.005
        assert manifest["totals"]["tool_spend"]["calls"] == 1


class TestWithoutACache:
    def test_every_search_reaches_the_provider_and_reports(self, tmp_path) -> None:
        calls, tool_calls, manifest = run_two_searches(tmp_path, cache=None)

        assert len(calls) == 2
        assert [c["spent"]["amount"] for c in tool_calls] == [0.005, 0.005]
        assert manifest["totals"]["tool_spend"]["amount"] == pytest.approx(0.01)


def run_three_searches(tmp_path: Path, *, cache: UrlCache | None, budget: Budget):
    """Three identical searches under a ceiling, and how far the run got."""
    calls: list[str] = []

    def provider(query: str, count: int):
        calls.append(query)
        return [{"title": "t", "url": "https://shop.test/a", "snippet": "s"}]

    refused: list[str] = []

    def go(inputs, ctx):
        for _ in range(3):
            try:
                ctx.call_tool("web_search", query="ridge tee measurements")
            except ModelFacingError as stopped:
                refused.append(str(stopped))
        return {"refused": refused}

    search = web_search(provider, declared_cost=PAID, cache=cache)
    runs = tmp_path / "runs"
    result = Pipeline([Deterministic(go, node_id="find", tools=[search])], budget=budget).run(
        {}, envelope=RunEnvelope(run_dir=str(runs))
    )
    records = [json.loads(line) for line in result.paths.trajectory.read_text().splitlines()]
    return calls, [r for r in records if r.get("record_type") == "tool_call"], refused


class TestWhatMaxCostSees:
    CEILING = Budget(max_steps=None, max_tokens=None, max_cost=0.011, max_wall_clock_ms=None)

    def test_a_cached_search_does_not_deplete_the_ceiling(self, tmp_path) -> None:
        """Three searches under a ceiling of two: the two the cache answered are free."""
        calls, tool_calls, refused = run_three_searches(
            tmp_path, cache=UrlCache(tmp_path / "cache"), budget=self.CEILING
        )

        assert calls == ["ridge tee measurements"]
        assert [c["spent"] for c in tool_calls][1:] == [None, None]
        assert refused == []

    def test_without_a_cache_the_same_three_reach_the_ceiling(self, tmp_path) -> None:
        """The contrast: what the ceiling does when every call really is paid."""
        calls, _, refused = run_three_searches(tmp_path, cache=None, budget=self.CEILING)

        assert calls == ["ridge tee measurements"] * 2
        assert len(refused) == 1
        assert "cost limit" in refused[0]


class TestTheMeterDoesNotChangeWhatTheModelSees:
    def test_the_meter_is_not_offered_as_an_argument(self, tmp_path) -> None:
        search = web_search(lambda query, count: [], declared_cost=PAID)

        assert "meter" not in search.parameters["properties"]
        assert sorted(search.parameters["properties"]) == [
            "domains",
            "max_results",
            "query",
        ]

    def test_the_tool_is_still_stored_in_the_cassette(self) -> None:
        """A `SpendMeter` reaches nothing outside the run, so it does not force a re-run."""
        search = web_search(lambda query, count: [], declared_cost=PAID)

        assert search.re_executed is False
