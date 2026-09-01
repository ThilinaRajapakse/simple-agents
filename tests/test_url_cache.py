"""A page read once and not read again, across runs.

The cassette replays one recorded run. This is what stops a second run re-requesting what an
earlier one already read. No test here reaches the network.
"""

from __future__ import annotations

import json
import time
from typing import Any
from pathlib import Path

import httpx
import pytest

from simple_agents import ConfigurationError, DeclaredCost, SpendMeter
from simple_agents.builtins import HostPolicy, UrlCache, http_fetch, read_page, web_search

PAID = DeclaredCost(currency="USD", per_call=0.005)
PAGE = (
    "<html><body><h1>Ridge Tee</h1>"
    "<p>Ridge Tee, chest 52cm on a medium, 55cm on a large. Heavyweight cotton, cut "
    "straight through the body, pre-shrunk and finished with a twin-needle hem. The "
    "model is 183cm and wears a medium. Made in Portugal from long-staple yarn.</p>"
    "</body></html>"
)


def _counting() -> tuple[httpx.MockTransport, list[str]]:
    """A transport that answers every page, and the list of what it was asked for."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        asked.append(str(request.url))
        return httpx.Response(200, text=PAGE)

    return httpx.MockTransport(handler), asked


# -- the store ------------------------------------------------------------------------------


def test_a_value_stored_comes_back(tmp_path: Path) -> None:
    cache = UrlCache(tmp_path)

    cache.put("https://shop.test/a", "the body")

    assert cache.get("https://shop.test/a").value == "the body"
    assert cache.stored() == 1


def test_an_address_never_stored_is_a_miss(tmp_path: Path) -> None:
    assert UrlCache(tmp_path).get("https://shop.test/a") is None


def test_an_entry_older_than_the_limit_is_not_served(tmp_path: Path) -> None:
    cache = UrlCache(tmp_path, max_age_days=1)
    cache.put("https://shop.test/a", "the body")

    stored = json.loads(next(tmp_path.glob("*.json")).read_text())
    stored["stored_at"] = time.time() - 2 * 86400
    next(tmp_path.glob("*.json")).write_text(json.dumps(stored))

    assert cache.get("https://shop.test/a") is None


def test_an_age_of_zero_days_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as raised:
        UrlCache(tmp_path, max_age_days=0)

    assert "stores nothing that can be served" in str(raised.value)


def test_a_stored_entry_reports_its_age(tmp_path: Path) -> None:
    cache = UrlCache(tmp_path)
    cache.put("https://shop.test/a", "the body")

    assert cache.get("https://shop.test/a").age_days < 0.001


def test_an_unreadable_entry_is_a_miss_rather_than_a_failure(tmp_path: Path) -> None:
    cache = UrlCache(tmp_path)
    cache.put("https://shop.test/a", "the body")
    next(tmp_path.glob("*.json")).write_text("{not json")

    assert cache.get("https://shop.test/a") is None


# -- in front of a fetch ---------------------------------------------------------------------


def test_an_address_read_before_is_not_requested_again(tmp_path: Path) -> None:
    transport, asked = _counting()
    cache = UrlCache(tmp_path)
    fetch = http_fetch(cache=cache, transport=transport, obey_robots=False)

    first = fetch.call({"url": "https://shop.test/a"})
    second = fetch.call({"url": "https://shop.test/a"})

    assert first == second == PAGE
    assert asked == ["https://shop.test/a"]


def test_a_second_tool_over_the_same_directory_reads_what_the_first_stored(
    tmp_path: Path,
) -> None:
    """Which is a second run: the store outlives the tool that filled it."""
    transport, asked = _counting()
    http_fetch(cache=UrlCache(tmp_path), transport=transport, obey_robots=False).call(
        {"url": "https://shop.test/a"}
    )

    other, other_asked = _counting()
    body = http_fetch(cache=UrlCache(tmp_path), transport=other, obey_robots=False).call(
        {"url": "https://shop.test/a"}
    )

    assert body == PAGE
    assert other_asked == []


def test_a_cached_page_is_not_charged_against_the_run_s_fetch_ceiling(
    tmp_path: Path,
) -> None:
    """Nothing was requested, so nothing is spent."""
    transport, _ = _counting()
    policy = HostPolicy(["shop.test"], max_fetches=1)
    fetch = http_fetch(
        policy=policy, cache=UrlCache(tmp_path), transport=transport, obey_robots=False
    )
    bound = policy.for_run()

    fetch.call({"url": "https://shop.test/a"}, {"scope": bound})
    fetch.call({"url": "https://shop.test/a"}, {"scope": bound})

    assert bound.fetches == 1


def test_a_host_out_of_scope_is_refused_even_when_it_is_in_the_cache(
    tmp_path: Path,
) -> None:
    """The store is not a way around the check."""
    cache = UrlCache(tmp_path)
    cache.put("https://elsewhere.test/a", PAGE)
    transport, _ = _counting()
    policy = HostPolicy(["shop.test"])
    fetch = http_fetch(policy=policy, cache=cache, transport=transport, obey_robots=False)

    with pytest.raises(Exception) as raised:
        fetch.call({"url": "https://elsewhere.test/a"}, {"scope": policy.for_run()})

    assert "may not fetch from" in str(raised.value)


def test_read_page_says_a_page_came_from_the_store_and_how_old_it_is(
    tmp_path: Path,
) -> None:
    transport, asked = _counting()
    cache = UrlCache(tmp_path)
    tool = read_page(cache=cache, transport=transport, obey_robots=False)

    tool.call({"url": "https://shop.test/a"})
    second = tool.call({"url": "https://shop.test/a"})

    assert "read from a local copy stored 0.0 days ago" in second
    assert "Ridge Tee" in second
    assert asked == ["https://shop.test/a"]


def test_what_is_stored_is_the_page_rather_than_the_reduction(tmp_path: Path) -> None:
    """So changing what reduction does is not a reason to throw the store away."""
    transport, _ = _counting()
    cache = UrlCache(tmp_path)
    read_page(cache=cache, transport=transport, obey_robots=False).call(
        {"url": "https://shop.test/a"}
    )

    stored = json.loads(next(tmp_path.glob("*.json")).read_text())

    assert stored["value"] == PAGE


# The library fills `web_search`'s SpendMeter; these call the tool directly.
METER = {"meter": SpendMeter(_spend=lambda amount, currency=None, source="measured": None)}


# -- in front of a search ---------------------------------------------------------------------


def test_a_repeated_search_does_not_reach_the_provider(tmp_path: Path) -> None:
    calls: list[str] = []

    def provider(query: str, count: int):
        calls.append(query)
        return [{"title": "t", "url": "https://shop.test/a", "snippet": "s"}]

    search = web_search(provider, declared_cost=PAID, cache=UrlCache(tmp_path))

    first = search.call({"query": "ridge tee measurements"}, METER)
    second = search.call({"query": "ridge tee measurements"}, METER)

    assert first == second
    assert calls == ["ridge tee measurements"]


def test_a_scoped_search_is_not_served_a_whole_web_result(tmp_path: Path) -> None:
    """The key covers everything that identifies the request, domains included."""
    calls: list[Any] = []

    def provider(query: str, count: int, domains=None):
        calls.append(domains)
        return [{"title": "t", "url": "https://shop.test/a"}]

    search = web_search(provider, declared_cost=PAID, cache=UrlCache(tmp_path))

    search.call({"query": "tee"}, METER)
    search.call({"query": "tee", "domains": ["shop.test"]}, METER)

    assert calls == [None, ["shop.test"]]
