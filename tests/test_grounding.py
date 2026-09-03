"""Checking that a claim is backed by material the run touched.

Every case here is a pair the test author fixed, because what a normalisation should and should
not accept is what is being pinned. The end-to-end test drives a real `AgentNode`, so
what a finish check is handed is what the loop hands it rather than what this file builds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simple_agents import (
    Prompt,
    AgentContext,
    AgentNode,
    Budget,
    FakeModelClient,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    ToolCallSummary,
    contains_normalised,
    normalise_text,
    same_url,
    tool,
    url_was_read,
    urls_read,
)
from simple_agents.models import ToolCallRequest, fake_response

from schemas import Answer


def _ctx(*calls: ToolCallSummary) -> AgentContext:
    return AgentContext(
        run_id="run_1",
        node_id="chase",
        workspace=Path("."),
        seed=41,
        budget=Budget.unbounded(),
        tool_calls=calls,
    )


def _call(name: str, ok: bool = True, **arguments: object) -> ToolCallSummary:
    return ToolCallSummary(name=name, arguments=dict(arguments), ok=ok, result=None)


# -- comparing text ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "haystack, needle, contained",
    [
        ("The Rankine cycle recycles water", "rankine cycle", True),
        ("The Rankine cycle recycles water", "RANKINE CYCLE", True),
        ("Beyonce sang at the opening", "Beyoncé", True),
        ("Beyoncé sang at the opening", "Beyonce", True),
        ("The café is closed", "cafe", True),
        ("The cafe is closed", "café", True),
        ("Müller reported it", "Muller", True),
        ("a naïve reading", "naive", True),
        ("measured in Ångström", "angstrom", True),
        ('the sign read "closed"', "“closed”", True),
        ("the O2 level fell", "O₂", True),
        ("the width is 52 cm", "52cm", False),
        ("no mention of it here", "rankine", False),
    ],
)
def test_what_normalisation_accepts(haystack: str, needle: str, contained: bool) -> None:
    assert contains_normalised(haystack, needle) is contained


def test_folding_an_accent_is_symmetric() -> None:
    """An asymmetric fold is worse than a plain miss: one direction silently passes."""
    for written, quoted in (("café", "cafe"), ("Beyoncé", "Beyonce"), ("naïve", "naive")):
        assert contains_normalised(f"the {written} is here", quoted) is True
        assert contains_normalised(f"the {quoted} is here", written) is True


def test_an_accented_word_is_one_word_rather_than_two() -> None:
    """An accent used to be treated as a separator, which split the word around it."""
    assert normalise_text("naïve") == "naive"
    assert normalise_text("Müller") == "muller"


def test_words_are_not_joined_across_a_separator() -> None:
    """The looser rule accepts text the source does not contain, which is what the check is for."""
    assert contains_normalised("the rapist was named", "therapist") is False
    assert contains_normalised("cost 30, 40 and 50", "3040") is False


def test_an_empty_claim_is_not_grounded() -> None:
    assert contains_normalised("anything at all", "") is False
    assert contains_normalised("anything at all", "   ") is False


def test_normalise_text_is_what_the_comparison_sees() -> None:
    assert normalise_text("O₂ (“saturation”)") == "o2 saturation"
    assert normalise_text("  Mixed   CASE  ") == "mixed case"


# -- comparing addresses ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "left, right, same",
    [
        ("https://WWW.Example.com/tee/", "https://example.com/tee", True),
        ("https://example.com/tee", "https://example.com/tee#sizing", True),
        ("https://example.com/tee?colour=black", "https://example.com/tee", False),
        ("https://example.com/tee", "https://example.com/shirt", False),
        ("https://example.com/tee", "http://example.com/tee", False),
        ("not a url", "not a url", False),
    ],
)
def test_which_addresses_name_one_page(left: str, right: str, same: bool) -> None:
    assert same_url(left, right) is same


# -- what the node read -------------------------------------------------------------------------


def test_a_url_passed_to_a_successful_call_was_read() -> None:
    ctx = _ctx(_call("read_page", url="https://shop.test/tee"))

    assert url_was_read(ctx, "https://shop.test/tee") is True
    assert url_was_read(ctx, "https://www.shop.test/tee/") is True
    assert url_was_read(ctx, "https://shop.test/other") is False


def test_a_page_the_agent_tried_and_did_not_get_was_not_read() -> None:
    ctx = _ctx(_call("read_page", ok=False, url="https://shop.test/tee"))

    assert url_was_read(ctx, "https://shop.test/tee") is False
    assert urls_read(ctx) == []


def test_any_tool_counts_rather_than_a_named_one() -> None:
    """What matters is that the run fetched the page, not which tool did it."""
    ctx = _ctx(_call("http_fetch", url="https://shop.test/tee"))

    assert url_was_read(ctx, "https://shop.test/tee") is True


def test_a_query_that_mentions_a_site_is_not_a_page_that_was_read() -> None:
    ctx = _ctx(_call("web_search", query="ridge tee site:shop.test"))

    assert urls_read(ctx) == []
    assert url_was_read(ctx, "https://shop.test/tee") is False


def test_the_addresses_read_come_back_as_they_were_passed() -> None:
    """A refusal message names what the model wrote, not a canonical form of it."""
    ctx = _ctx(
        _call("read_page", url="https://WWW.Shop.test/tee/"),
        _call("read_page", url="https://shop.test/tee"),
        _call("read_page", url="https://shop.test/guide"),
    )

    assert urls_read(ctx) == ["https://WWW.Shop.test/tee/", "https://shop.test/guide"]


def test_a_node_that_called_nothing_read_nothing() -> None:
    assert urls_read(_ctx()) == []
    assert url_was_read(_ctx(), "https://shop.test/tee") is False


# -- the documented pattern, end to end ----------------------------------------------------------


def test_a_finish_citing_a_page_the_node_never_read_is_refused(tmp_path: Path) -> None:
    """The worked example in `docs/tools.md` §5, run against a real AgentNode."""
    rejections: list[str] = []

    @tool(side_effect_class=SideEffectClass.READ_ONLY)
    def read_page(url: str) -> str:
        """Read one page and return its text."""
        return "The Ridge Tee measures 52cm across the chest."

    def cites_a_page_it_read(answer: Answer, ctx: AgentContext) -> str | None:
        if answer.source is None or url_was_read(ctx, answer.source):
            return None
        if ctx.finish_attempts:
            return None
        rejection = (
            f"source must be a page read in this step. Read: {urls_read(ctx)}. Cite one of "
            f"those, or answer with no source."
        )
        rejections.append(rejection)
        return rejection

    client = FakeModelClient(
        responses=[
            fake_response(
                tool_calls=[
                    ToolCallRequest(
                        id="c1", name="read_page", arguments={"url": "https://shop.test/tee"}
                    )
                ]
            ),
            fake_response(
                tool_calls=[
                    ToolCallRequest(
                        id="f1",
                        name="finish",
                        arguments={"answer": "52cm", "source": "https://invented.test/chart"},
                    )
                ]
            ),
            fake_response(
                tool_calls=[
                    ToolCallRequest(
                        id="f2",
                        name="finish",
                        arguments={"answer": "52cm", "source": "https://www.shop.test/tee/"},
                    )
                ]
            ),
        ]
    )

    result = Pipeline(
        [
            AgentNode(
                lambda inputs, ctx: Prompt.user("Find the chest measurement."),
                tools=[read_page],
                output_schema=Answer,
                finish_check=cites_a_page_it_read,
                budget=Budget(
                    max_steps=6, max_tokens=10_000, max_cost=None, max_wall_clock_ms=None
                ),
                node_id="chase",
            )
        ],
        budget=Budget.unbounded(),
    ).run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client)

    assert result.output.answer == "52cm"
    assert result.output.source == "https://www.shop.test/tee/"
    assert len(rejections) == 1
    assert "https://shop.test/tee" in rejections[0]
