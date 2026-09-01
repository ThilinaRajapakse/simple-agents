"""A reachable set that grows while a run proceeds, and what the run records about it.

Every host here is invented and no test reaches the network: the transport is a mock that
answers whatever the test set up.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from simple_agents import (
    Budget,
    ConfigurationError,
    Deterministic,
    ModelFacingError,
    Pipeline,
    RunEnvelope,
)
from simple_agents.builtins import Admission, HostPolicy, http_fetch

from conftest import run_path

BODY = "<html><body><p>Ridge Tee, chest 52cm.</p></body></html>"


def _serving(body: str = BODY) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=body)

    return httpx.MockTransport(handler)


# -- scope ----------------------------------------------------------------------------------


def test_a_configured_host_is_in_scope() -> None:
    policy = HostPolicy(["shop.test"])

    assert policy.in_scope("shop.test")
    assert not policy.in_scope("elsewhere.test")


def test_a_subdomain_of_a_host_in_scope_is_in_scope() -> None:
    """A site's help pages are on the site, and refusing them refuses what was permitted."""
    policy = HostPolicy(["shop.test"])

    assert policy.in_scope("help.shop.test")
    assert policy.in_scope("faq-uk.shop.test")


def test_a_leading_www_is_the_same_site() -> None:
    assert HostPolicy(["shop.test"]).in_scope("www.shop.test")
    assert HostPolicy(["www.shop.test"]).in_scope("shop.test")


def test_a_policy_with_no_hosts_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        HostPolicy([])

    assert "no hosts" in str(raised.value)


def test_a_ceiling_of_zero_requests_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        HostPolicy(["shop.test"], max_fetches=0)

    assert "permits no request" in str(raised.value)


# -- admission ------------------------------------------------------------------------------


def test_admitting_a_host_brings_it_into_scope_with_its_reason() -> None:
    bound = HostPolicy(["shop.test"], max_admitted=2).for_run()

    admission = bound.admit("brand.test", reason="named as the maker on a listing")

    assert admission == Admission(host="brand.test", reason="named as the maker on a listing")
    assert bound.in_scope("brand.test")


def test_admitting_a_host_already_in_scope_costs_no_slot() -> None:
    """A configured site addressed under another prefix is not a new site."""
    bound = HostPolicy(["shop.test"], max_admitted=1).for_run()

    bound.admit("www.shop.test", reason="seen again")

    assert bound.admit("brand.test", reason="the one real admission").host == "brand.test"


def test_admission_beyond_the_cap_is_refused_naming_what_was_admitted() -> None:
    bound = HostPolicy(["shop.test"], max_admitted=1).for_run()
    bound.admit("first.test", reason="one")

    with pytest.raises(ConfigurationError) as raised:
        bound.admit("second.test", reason="two")

    message = str(raised.value)
    assert "1 of 1 hosts" in message
    assert "first.test" in message


def test_no_admission_is_permitted_by_default() -> None:
    bound = HostPolicy(["shop.test"]).for_run()

    with pytest.raises(ConfigurationError):
        bound.admit("brand.test", reason="nothing was allowed for")


def test_the_declaration_itself_refuses_to_admit_or_count() -> None:
    """An admission made on the declaration would reach no run, so both mutators refuse."""
    policy = HostPolicy(["shop.test"], max_admitted=2, max_fetches=5)

    with pytest.raises(ConfigurationError) as admit_raised:
        policy.admit("brand.test", reason="named on a listing")
    with pytest.raises(ConfigurationError) as spend_raised:
        policy.spend_fetch()

    assert "ctx.fetch_policy" in str(admit_raised.value)
    assert "ctx.fetch_policy" in str(spend_raised.value)


def test_a_bound_copy_leaves_the_declaration_untouched() -> None:
    policy = HostPolicy(["shop.test"], max_admitted=1, max_fetches=5)
    bound = policy.for_run()

    bound.admit("brand.test", reason="one run's admission")
    bound.spend_fetch()

    assert policy.admitted == {}
    assert policy.fetches == 0
    assert bound.fetches == 1


# -- what the fetch tool does with it --------------------------------------------------------


def test_a_host_out_of_scope_is_refused_and_told_what_is_in_scope() -> None:
    policy = HostPolicy(["shop.test"])
    fetch = http_fetch(policy=policy, transport=_serving(), obey_robots=False)

    with pytest.raises(ModelFacingError) as raised:
        fetch.call({"url": "https://elsewhere.test/a"}, {"scope": policy.for_run()})

    assert "may not fetch from 'elsewhere.test'" in str(raised.value)
    assert "shop.test" in str(raised.value)


def test_a_host_admitted_mid_run_becomes_fetchable() -> None:
    policy = HostPolicy(["shop.test"], max_admitted=1)
    fetch = http_fetch(policy=policy, transport=_serving(), obey_robots=False)
    bound = policy.for_run()

    with pytest.raises(ModelFacingError):
        fetch.call({"url": "https://brand.test/tee"}, {"scope": bound})

    bound.admit("brand.test", reason="the maker's own site")

    assert "Ridge Tee" in fetch.call({"url": "https://brand.test/tee"}, {"scope": bound})


def test_the_ceiling_stops_the_run_reading_more_pages() -> None:
    policy = HostPolicy(["shop.test"], max_fetches=2)
    fetch = http_fetch(policy=policy, transport=_serving(), obey_robots=False)
    bound = policy.for_run()

    fetch.call({"url": "https://shop.test/a"}, {"scope": bound})
    fetch.call({"url": "https://shop.test/b"}, {"scope": bound})

    with pytest.raises(ModelFacingError) as raised:
        fetch.call({"url": "https://shop.test/c"}, {"scope": bound})

    assert "limit of 2 page requests" in str(raised.value)
    assert bound.fetches == 2


def test_declaring_hosts_twice_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        http_fetch(policy=HostPolicy(["shop.test"]), allow_hosts=["shop.test"])

    assert "two sources for one decision" in str(raised.value)


# -- what the run records ---------------------------------------------------------------------


def test_the_manifest_records_what_was_permitted_and_what_was_admitted(tmp_path: Path) -> None:
    """The declared set stops being the whole answer once a run can add to it."""
    policy = HostPolicy(["shop.test"], max_admitted=2, max_fetches=10)
    fetch = http_fetch(policy=policy, transport=_serving(), obey_robots=False)

    def read(inputs: dict, ctx) -> str:
        ctx.fetch_policy.admit("brand.test", reason="named as the maker on a listing")
        return ctx.call_tool("http_fetch", url="https://brand.test/tee")

    result = Pipeline(
        [Deterministic(read, tools=[fetch], node_id="read")],
        budget=Budget.unbounded(),
        fetch_policy=policy,
    ).run({}, envelope=RunEnvelope(run_dir=tmp_path))

    policies = json.loads(run_path(tmp_path, result.run_id, "manifest.json").read_text())[
        "fetch_policy"
    ]

    assert len(policies) == 1
    recorded = policies[0]
    # `null` is the pipeline the run was started with, as against one used as a node.
    assert recorded["declared_by"] is None
    assert recorded["hosts"] == ["shop.test"]
    assert recorded["admitted"] == [
        {"host": "brand.test", "reason": "named as the maker on a listing"}
    ]
    assert recorded["fetches"] == 1
    assert recorded["max_admitted"] == 2
    assert recorded["max_fetches"] == 10


def test_a_policy_on_a_nested_pipeline_is_recorded_under_the_pipeline_that_declared_it(
    tmp_path: Path,
) -> None:
    """`Pipeline(fetch_policy=)` is accepted at every level and used to be read at one.

    A policy given to a pipeline used as a node was dropped, so the run recorded nothing about
    what those nodes were allowed to reach.
    """
    outer_policy = HostPolicy(["shop.test"], max_fetches=10)
    inner_policy = HostPolicy(["docs.test"], max_fetches=4)

    inner = Pipeline(
        [Deterministic(lambda inputs, ctx: "read", node_id="read", successors=[])],
        budget=Budget.unbounded(),
        node_id="research",
        fetch_policy=inner_policy,
    )
    result = Pipeline(
        [inner, Deterministic(lambda inputs, ctx: "done", node_id="report", successors=[])],
        budget=Budget.unbounded(),
        fetch_policy=outer_policy,
    ).run({}, envelope=RunEnvelope(run_dir=tmp_path))

    recorded = json.loads(run_path(tmp_path, result.run_id, "manifest.json").read_text())[
        "fetch_policy"
    ]

    assert [(entry["declared_by"], entry["hosts"]) for entry in recorded] == [
        (None, ["shop.test"]),
        ("research", ["docs.test"]),
    ]


def test_a_run_declaring_no_policy_records_none(tmp_path: Path) -> None:
    result = Pipeline(
        [Deterministic(lambda inputs, ctx: "done", node_id="n")], budget=Budget.unbounded()
    ).run({}, envelope=RunEnvelope(run_dir=tmp_path))

    assert result.manifest["fetch_policy"] == []


def test_a_refused_then_admitted_then_fetched_sequence_replays_as_that_sequence(
    tmp_path: Path,
) -> None:
    """The policy is intra-run mutable state read by a filed tool.

    The occurrence ordinal in the tool-call key is what keeps that sound: the refused call and
    the successful one are two entries under one argument set, and replay serves them in order.
    """
    from simple_agents import Cassette

    def build() -> tuple[HostPolicy, Pipeline]:
        policy = HostPolicy(["shop.test"], max_admitted=1)
        fetch = http_fetch(policy=policy, transport=_serving(), obey_robots=False)

        def read(inputs: dict, ctx) -> list[str]:
            seen: list[str] = []
            try:
                ctx.call_tool("http_fetch", url="https://brand.test/tee")
                seen.append("fetched")
            except ModelFacingError:
                seen.append("refused")
            ctx.fetch_policy.admit("brand.test", reason="the maker's own site")
            seen.append(
                "fetched" if ctx.call_tool("http_fetch", url="https://brand.test/tee") else "empty"
            )
            return seen

        return policy, Pipeline(
            [Deterministic(read, tools=[fetch], node_id="read")],
            budget=Budget.unbounded(),
            fetch_policy=policy,
        )

    cassette_path = tmp_path / "c.jsonl"
    _, recording = build()
    live = recording.run(
        {}, envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path))
    )

    _, replaying = build()
    replayed = replaying.run(
        {},
        envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)),
    )

    assert live.output == ["refused", "fetched"]
    assert replayed.output == ["refused", "fetched"]


def test_two_runs_through_one_declaration_count_separately(tmp_path: Path) -> None:
    """A product serves many runs from one process, and each counts its own fetches."""
    policy = HostPolicy(["shop.test"], max_fetches=10)
    fetch = http_fetch(policy=policy, transport=_serving(), obey_robots=False)

    pipeline = Pipeline(
        [
            Deterministic(
                lambda inputs, ctx: ctx.call_tool("http_fetch", url="https://shop.test/a"),
                tools=[fetch],
                node_id="read",
            )
        ],
        budget=Budget.unbounded(),
        fetch_policy=policy,
    )
    first = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))
    second = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))

    for result in (first, second):
        assert result.manifest["fetch_policy"][0]["fetches"] == 1
    assert policy.fetches == 0


def test_a_policy_taking_tool_with_no_declaration_anywhere_is_refused() -> None:
    """The run would have nothing to fill the parameter with, so construction refuses."""
    fetch = http_fetch(policy=HostPolicy(["shop.test"]), transport=_serving())
    fetch.fetch_policy = None

    with pytest.raises(ConfigurationError) as raised:
        Pipeline(
            [Deterministic(lambda inputs, ctx: "x", tools=[fetch], node_id="read")],
            budget=Budget.unbounded(),
        )

    assert "Pipeline(fetch_policy=...)" in str(raised.value)
