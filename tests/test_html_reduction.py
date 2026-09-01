"""Reducing a page to the text worth sending, and the tool that composes it with a fetch.

The two fixture pages under `fixtures/pages/` are handcrafted, so what should survive reduction
is fixed before the code runs. No test here reaches the network.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from simple_agents import ModelFacingError, SideEffectClass
from simple_agents.builtins import PageLink, Reduced, read_page, reduce_html

PAGES = Path(__file__).parent / "fixtures" / "pages"
PRODUCT = (PAGES / "product.html").read_text(encoding="utf-8")
SHELL = (PAGES / "shell.html").read_text(encoding="utf-8")
URL = "https://shop.test/products/ridge-tee"


def _serving(body: str, content_type: str = "text/html") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text=body, headers={"content-type": content_type})

    return httpx.MockTransport(handler)


# -- what reduction keeps and drops --------------------------------------------------------


def test_script_style_and_navigation_are_dropped() -> None:
    reduced = reduce_html(PRODUCT, base_url=URL)

    assert "window.analytics" not in reduced.text
    assert "display:none" not in reduced.text
    assert "Sale" not in reduced.text
    assert "Returns" not in reduced.text


def test_the_prose_survives() -> None:
    reduced = reduce_html(PRODUCT, base_url=URL)

    assert "Heavyweight cotton" in reduced.text
    assert "Model is 183cm" in reduced.text


def test_a_table_keeps_its_rows_and_cells() -> None:
    [table] = reduce_html(PRODUCT, base_url=URL).tables

    assert table[0] == ["Size", "Chest (cm)", "Length (cm)"]
    assert table[2] == ["M", "52", "71"]


def test_a_one_row_table_is_layout_rather_than_data() -> None:
    """The banner table in the fixture has one row and is not returned as a table."""
    assert len(reduce_html(PRODUCT, base_url=URL).tables) == 1


def test_alt_text_long_enough_to_be_a_description_is_kept() -> None:
    assert "[image: Chest width 52cm on size medium]" in reduce_html(PRODUCT).text


def test_structured_data_is_returned_parsed_and_uninterpreted() -> None:
    """The blocks are located and parsed. What a vocabulary means is the project's to read."""
    [block] = reduce_html(PRODUCT, base_url=URL).json_ld

    assert block["@type"] == "Product"
    assert block["brand"]["name"] == "Corveth"
    assert block["offers"]["price"] == "38.00"


def test_only_links_to_the_page_s_own_host_are_kept() -> None:
    """A page cannot widen what an agent reaches by linking somewhere else."""
    urls = [link.url for link in reduce_html(PRODUCT, base_url=URL).links]

    assert "https://shop.test/pages/size-guide" in urls
    assert not any("elsewhere.test" in url for url in urls)


def test_links_are_matched_on_their_text_or_their_address() -> None:
    reduced = reduce_html(PRODUCT, base_url=URL)

    assert reduced.links_matching(("size guide",)) == [
        PageLink(url="https://shop.test/pages/size-guide", text="Full size guide")
    ]
    assert reduced.links_matching(()) == []
    assert reduced.links_matching(("nothing here",)) == []


def test_markup_that_will_not_parse_yields_what_was_read() -> None:
    reduced = reduce_html("<p>before<table><tr><td>x</td></tr", base_url=URL)

    assert "before" in reduced.text


def test_a_page_with_nothing_in_it_reduces_to_nothing() -> None:
    reduced = reduce_html(SHELL, base_url=URL)

    assert reduced.tables == []
    assert reduced.json_ld == []
    assert len(reduced.text) < 60


# -- rendering, and what survives truncation -----------------------------------------------


def test_the_default_order_puts_tables_before_prose() -> None:
    rendered = reduce_html(PRODUCT, base_url=URL).as_prompt()

    assert rendered.index("=== TABLES ===") < rendered.index("=== PAGE TEXT ===")


def test_the_order_is_the_project_s_to_choose() -> None:
    """A project whose pages carry prose rather than tables puts prose first."""
    reduced = reduce_html(PRODUCT, base_url=URL)

    rendered = reduced.as_prompt(order=("text", "tables"))

    assert rendered.index("=== PAGE TEXT ===") < rendered.index("=== TABLES ===")


def test_a_part_left_out_of_the_order_is_not_rendered() -> None:
    rendered = reduce_html(PRODUCT, base_url=URL).as_prompt(order=("tables",))

    assert "=== TABLES ===" in rendered
    assert "=== PAGE TEXT ===" not in rendered
    assert "=== STRUCTURED DATA ===" not in rendered


def test_truncation_says_it_truncated_and_keeps_what_came_first() -> None:
    reduced = reduce_html(PRODUCT, base_url=URL)

    rendered = reduced.as_prompt(120)

    assert "=== TABLES ===" in rendered
    assert "[truncated at 120 characters]" in rendered


def test_nothing_is_truncated_without_a_limit() -> None:
    reduced = reduce_html(PRODUCT, base_url=URL)

    assert "truncated" not in reduced.as_prompt()


def test_an_empty_page_renders_as_an_empty_string() -> None:
    assert Reduced().as_prompt() == ""


# -- read_page ------------------------------------------------------------------------------


class TestReadPage:
    def test_a_page_comes_back_reduced_rather_than_as_markup(self) -> None:
        tool = read_page(transport=_serving(PRODUCT), obey_robots=False)

        text = tool.call({"url": URL})

        assert "=== TABLES ===" in text
        assert "Size | Chest (cm) | Length (cm)" in text
        assert "<div" not in text

    def test_it_is_read_only_and_takes_one_url(self) -> None:
        tool = read_page(transport=_serving(PRODUCT), obey_robots=False)

        assert tool.side_effect_class is SideEffectClass.READ_ONLY
        assert tool.parameters["required"] == ["url"]

    def test_declared_link_words_are_listed_for_the_model_to_read_next(self) -> None:
        tool = read_page(transport=_serving(PRODUCT), obey_robots=False, link_words=("size guide",))

        text = tool.call({"url": URL})

        assert "LINKS ON THIS PAGE THAT MAY HOLD MORE" in text
        assert "https://shop.test/pages/size-guide" in text

    def test_no_link_words_means_no_link_section(self) -> None:
        tool = read_page(transport=_serving(PRODUCT), obey_robots=False)

        assert "LINKS ON THIS PAGE" not in tool.call({"url": URL})

    def test_a_page_rendered_by_javascript_says_the_whole_site_will_be(self) -> None:
        """Otherwise an agent works through such a site one address at a time."""
        tool = read_page(transport=_serving(SHELL), obey_robots=False)

        with pytest.raises(ModelFacingError) as raised:
            tool.call({"url": URL})

        message = str(raised.value)
        assert "rendered by JavaScript" in message
        assert "do not try another address here" in message
        assert raised.value.retryable is False

    def test_the_ordering_reaches_the_tool(self) -> None:
        tool = read_page(transport=_serving(PRODUCT), obey_robots=False, order=("text", "tables"))

        text = tool.call({"url": URL})

        assert text.index("=== PAGE TEXT ===") < text.index("=== TABLES ===")

    def test_fetch_options_are_passed_through_to_the_fetch(self) -> None:
        tool = read_page(transport=_serving(PRODUCT), obey_robots=False, allow_hosts=["other.test"])

        with pytest.raises(ModelFacingError) as raised:
            tool.call({"url": URL})

        assert "may not fetch from 'shop.test'" in str(raised.value)

    def test_the_reduced_text_is_bounded_by_max_chars(self) -> None:
        tool = read_page(transport=_serving(PRODUCT), obey_robots=False, max_chars=150)

        text = tool.call({"url": URL})

        assert len(text) < 220
        assert "truncated at 150 characters" in text
