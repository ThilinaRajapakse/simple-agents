"""Contract tests for the shipped tools: each proves what its docstring claims.

The docstring is what the model reads to decide how to call a tool, so a docstring that has
drifted from the code produces call errors that read as reasoning errors and send debugging to
the prompt (FT-23). Every fixture here is handcrafted, with content the test author fixed, so
each assertion is about behaviour rather than about whatever a real corpus happens to hold.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from types import SimpleNamespace
from pydantic import BaseModel, SecretStr

from simple_agents import (
    AgentNode,
    Cassette,
    Budget,
    DeclaredCost,
    FakeModelClient,
    Maybe,
    Deterministic,
    ModelFacingError,
    ModelHandle,
    Pipeline,
    RunEnvelope,
    RunSuspended,
    SideEffectClass,
    Suspend,
    Throttled,
    read_trajectory,
    tool,
)
from simple_agents.builtins import (
    DocumentIndex,
    Reply,
    consult,
    on_reply,
    document_search,
    extract_to_schema,
    http_fetch,
    now,
    web_search,
    workspace_list,
    workspace_read,
    workspace_write,
)
from simple_agents.context import (
    TOOL_RETRY_ATTEMPTS,
    TOOL_RETRY_INITIAL_S,
    TOOL_RETRY_MAX_S,
    _throttle_wait,
)
from simple_agents.errors import CallerFacingError, ConfigurationError
from simple_agents.models import ToolCallRequest, fake_response
from simple_agents.tools import SpendMeter, Workspace

from schemas import Answer
from conftest import run_path, RUN_ID

CORPUS = {
    "bees.txt": "The Ostley Institute studies solitary bees in upland meadows.",
    "funding.txt": "Corveth closed a seed round led by Harbour Lane in March.",
    "staffing.txt": "Corveth employs forty people across two offices.",
}


def _prompt(inputs, ctx):
    return "go"


def _finish() -> ToolCallRequest:
    return ToolCallRequest(id="f", name="finish", arguments={"answer": "done", "source": None})


def _call(name: str, **arguments) -> ToolCallRequest:
    return ToolCallRequest(id=f"c_{name}", name=name, arguments=arguments)


# -----------------------------------------------------------------------------------------
# document_search
# -----------------------------------------------------------------------------------------


class TestDocumentSearch:
    @pytest.fixture
    def search(self):
        return document_search(DocumentIndex.from_texts(CORPUS))

    def test_a_hit_carries_the_identifier_the_score_and_the_text(self, search):
        [hit] = search.call({"query": "solitary bees"})["results"]

        assert hit["doc_id"] == "bees.txt"
        assert hit["text"] == CORPUS["bees.txt"]
        assert hit["score"] > 0

    def test_a_query_matching_nothing_returns_an_empty_list(self, search):
        """Finding nothing is a result the model acts on, not a failure."""
        assert search.call({"query": "hydroelectric turbine"})["results"] == []

    def test_it_reports_how_many_documents_hold_each_word(self, search):
        """Which says what to search next, and nothing about whether the fact is there."""
        counts = search.call({"query": "solitary hydroelectric"})["documents_containing"]

        assert counts["solitary"] > 0
        assert counts["hydroelectric"] == 0

    def test_the_best_match_comes_first(self, search):
        hits = search.call({"query": "Corveth seed round Harbour Lane"})["results"]

        assert hits[0]["doc_id"] == "funding.txt"
        assert {h["doc_id"] for h in hits} == {"funding.txt", "staffing.txt"}

    def test_the_model_may_ask_for_fewer_results(self, search):
        assert len(search.call({"query": "Corveth", "top_k": 1})["results"]) == 1

    def test_it_is_read_only_and_takes_a_query(self, search):
        assert search.side_effect_class is SideEffectClass.READ_ONLY
        assert search.parameters["required"] == ["query"]

    def test_long_documents_can_be_truncated(self):
        search = document_search(DocumentIndex.from_texts(CORPUS), max_chars=10)

        assert search.call({"query": "bees"})["results"][0]["text"] == CORPUS["bees.txt"][:10]

    def test_an_empty_collection_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            DocumentIndex.from_texts({})

        assert "no documents" in str(exc.value)

    def test_a_directory_that_is_not_there_is_refused(self, tmp_path):
        with pytest.raises(ConfigurationError) as exc:
            DocumentIndex.from_directory(tmp_path / "absent")

        assert "No directory at" in str(exc.value)

    def test_a_glob_matching_nothing_names_the_glob(self, tmp_path):
        (tmp_path / "a.md").write_text("text")

        with pytest.raises(ConfigurationError) as exc:
            DocumentIndex.from_directory(tmp_path)

        assert "'*.txt'" in str(exc.value)

    def test_a_directory_index_keys_on_the_file_name(self, tmp_path):
        (tmp_path / "bees.txt").write_text(CORPUS["bees.txt"])
        search = document_search(DocumentIndex.from_directory(tmp_path))

        assert search.call({"query": "bees"})["results"][0]["doc_id"] == "bees.txt"


class TestStopwords:
    def test_an_english_list_ships_and_is_the_default(self):
        index = DocumentIndex.from_texts(CORPUS)

        assert index.query_terms("What does Corveth do?") == ["corveth"]

    def test_an_empty_list_searches_every_word(self):
        index = DocumentIndex.from_texts(CORPUS, stopwords=())

        assert index.query_terms("What does Corveth do?") == ["what", "does", "corveth", "do"]

    def test_the_shipped_list_leaves_negations_alone(self):
        index = DocumentIndex.from_texts(CORPUS)

        assert index.query_terms("is the depot not open") == ["depot", "not", "open"]

    def test_a_declared_stopword_is_dropped_from_the_query(self):
        index = DocumentIndex.from_texts(CORPUS, stopwords={"what", "does", "do"})

        assert index.query_terms("What does Corveth do?") == ["corveth"]

    def test_a_query_of_nothing_but_stopwords_is_searched_as_written(self):
        """Otherwise a question made of common words returns nothing at all."""
        index = DocumentIndex.from_texts(CORPUS, stopwords={"what", "does", "do"})

        assert index.query_terms("What does do?") == ["what", "does", "do"]
        assert index.search("What does do?") == []

    def test_a_word_declared_in_any_case_matches_the_query(self):
        index = DocumentIndex.from_texts(CORPUS, stopwords={"What", "THE"})

        assert index.query_terms("What the bees") == ["bees"]

    def test_the_counts_report_the_words_the_query_was_searched_on(self):
        index = DocumentIndex.from_texts(CORPUS, stopwords={"what"})
        search = document_search(index)

        counts = search.call({"query": "What solitary bees"})["documents_containing"]

        assert set(counts) == {"solitary", "bees"}

    def test_dropping_a_word_changes_which_documents_rank(self):
        query = "Who does Corveth employ across two offices"
        plain = DocumentIndex.from_texts(CORPUS)
        filtered = DocumentIndex.from_texts(CORPUS, stopwords={"who", "does", "across"})

        assert [h.doc_id for h in plain.search(query)][0] == "staffing.txt"
        assert [h.doc_id for h in filtered.search(query)][0] == "staffing.txt"
        assert plain.search(query)[0].score != filtered.search(query)[0].score

    def test_a_title_is_indexed_by_writing_it_into_the_text(self):
        """The documented composition, rather than a second field on the index."""
        titled = DocumentIndex.from_texts(
            {"d1": f"Pollinator survey {CORPUS['bees.txt']}", "d2": CORPUS["funding.txt"]}
        )

        assert [h.doc_id for h in titled.search("pollinator survey")] == ["d1"]


# -----------------------------------------------------------------------------------------
# the workspace tools
# -----------------------------------------------------------------------------------------


class TestWorkspaceTools:
    def test_a_write_returns_the_path_and_a_read_returns_it(self, tmp_path):
        workspace = Workspace(root=tmp_path)
        write, read = workspace_write(), workspace_read()

        assert write.call({"path": "notes.txt", "content": "hello"}, {"workspace": workspace}) == (
            "notes.txt"
        )
        assert read.call({"path": "notes.txt"}, {"workspace": workspace}) == "hello"

    def test_a_write_creates_parent_directories(self, tmp_path):
        workspace = Workspace(root=tmp_path)
        workspace_write().call(
            {"path": "drafts/summary.md", "content": "x"}, {"workspace": workspace}
        )

        assert (tmp_path / "drafts" / "summary.md").read_text() == "x"

    def test_reading_a_missing_file_names_what_is_present(self, tmp_path):
        workspace = Workspace(root=tmp_path)
        workspace.write_text("notes.txt", "hello")

        with pytest.raises(ModelFacingError) as exc:
            workspace_read().call({"path": "other.txt"}, {"workspace": workspace})

        assert "notes.txt" in str(exc.value)

    def test_a_path_outside_the_workspace_is_refused(self, tmp_path):
        workspace = Workspace(root=tmp_path / "run")
        workspace.root.mkdir()

        with pytest.raises(ModelFacingError) as exc:
            workspace_write().call(
                {"path": "../escaped.txt", "content": "x"}, {"workspace": workspace}
            )

        assert "outside the run's workspace" in str(exc.value)
        assert not (tmp_path / "escaped.txt").exists()

    def test_the_listing_starts_empty_and_reports_relative_paths(self, tmp_path):
        workspace = Workspace(root=tmp_path)
        listing = workspace_list()

        assert listing.call({}, {"workspace": workspace}) == []
        workspace.write_text("drafts/summary.md", "x")
        assert listing.call({}, {"workspace": workspace}) == ["drafts/summary.md"]

    def test_the_writer_declares_writes_and_the_readers_do_not(self):
        assert workspace_write().side_effect_class is SideEffectClass.WRITES
        assert workspace_read().side_effect_class is SideEffectClass.READ_ONLY
        assert workspace_list().side_effect_class is SideEffectClass.READ_ONLY

    def test_the_workspace_is_not_offered_to_the_model(self):
        assert set(workspace_write().parameters["properties"]) == {"path", "content"}
        assert workspace_list().parameters["properties"] == {}


# -----------------------------------------------------------------------------------------
# now
# -----------------------------------------------------------------------------------------


class TestNow:
    def test_it_returns_an_iso_8601_utc_timestamp(self):
        stamp = now().call({})

        assert stamp.endswith("Z")
        assert stamp[4] == "-" and stamp[10] == "T"

    def test_it_takes_no_arguments(self):
        assert now().parameters["properties"] == {}


# -----------------------------------------------------------------------------------------
# http_fetch
# -----------------------------------------------------------------------------------------


def _transport(handler):
    return httpx.MockTransport(handler)


def _serving(body: str = "<html>page</html>", status: int = 200, robots: str = ""):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200 if robots else 404, text=robots)
        return httpx.Response(status, text=body)

    return _transport(handle)


class TestHttpFetch:
    def test_it_returns_the_body(self):
        fetch = http_fetch(transport=_serving())

        assert fetch.call({"url": "https://example.com/a"}) == "<html>page</html>"

    def test_a_404_is_a_model_facing_failure_naming_the_status(self):
        fetch = http_fetch(transport=_serving(status=404))

        with pytest.raises(ModelFacingError) as exc:
            fetch.call({"url": "https://example.com/a"})

        assert "404" in str(exc.value)

    def test_a_server_error_is_also_model_facing(self):
        """The model chose the URL and choosing another is a reasonable next action."""
        fetch = http_fetch(transport=_serving(status=503))

        with pytest.raises(ModelFacingError):
            fetch.call({"url": "https://example.com/a"})

    def test_robots_disallow_refuses_the_fetch(self):
        fetch = http_fetch(
            transport=_serving(robots="User-agent: *\nDisallow: /private"),
        )

        with pytest.raises(ModelFacingError) as exc:
            fetch.call({"url": "https://example.com/private/x"})

        assert "robots.txt" in str(exc.value)
        assert fetch.call({"url": "https://example.com/public/x"}) == "<html>page</html>"

    def test_a_site_with_no_robots_permits_everything(self):
        fetch = http_fetch(transport=_serving())

        assert fetch.call({"url": "https://example.com/private/x"})

    def test_a_host_outside_allow_hosts_is_refused(self):
        fetch = http_fetch(transport=_serving(), allow_hosts=["docs.example.com"])

        with pytest.raises(ModelFacingError) as exc:
            fetch.call({"url": "https://elsewhere.test/a"})

        assert "docs.example.com" in str(exc.value)

    def test_a_relative_url_is_refused(self):
        fetch = http_fetch(transport=_serving())

        with pytest.raises(ModelFacingError) as exc:
            fetch.call({"url": "/a"})

        assert "absolute HTTP URL" in str(exc.value)

    def test_an_unreachable_host_is_model_facing(self):
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        fetch = http_fetch(transport=_transport(refuse), obey_robots=False)

        with pytest.raises(ModelFacingError) as exc:
            fetch.call({"url": "https://example.com/a"})

        assert "could not be reached" in str(exc.value)

    def test_a_rate_limit_is_a_throttle_rather_than_a_missing_page(self):
        """Dogfood #5 recorded 736 of these, and the model read them as "no article"."""

        def busy(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "15"}, text="slow down")

        fetch = http_fetch(transport=_transport(busy), obey_robots=False)

        with pytest.raises(Throttled) as exc:
            fetch.call({"url": "https://example.com/a"})

        assert exc.value.retry_after_s == 15.0
        assert "requested less often" in str(exc.value)
        assert "not the page being missing" in str(exc.value)

    def test_a_404_is_still_the_request_being_wrong(self):
        fetch = http_fetch(transport=_serving(status=404), obey_robots=False)

        with pytest.raises(ModelFacingError) as exc:
            fetch.call({"url": "https://example.com/a"})

        assert not isinstance(exc.value, Throttled)
        assert "will answer the same way" in str(exc.value)

    def test_every_throttled_status_is_read_the_same_way(self):
        for status in (408, 429, 503):
            fetch = http_fetch(transport=_serving(status=status), obey_robots=False)

            with pytest.raises(Throttled):
                fetch.call({"url": "https://example.com/a"})

    def test_a_site_that_sends_no_retry_after_still_throttles(self):
        fetch = http_fetch(transport=_serving(status=429), obey_robots=False)

        with pytest.raises(Throttled) as exc:
            fetch.call({"url": "https://example.com/a"})

        assert exc.value.retry_after_s is None

    def test_the_description_the_model_reads_no_longer_says_to_give_up(self):
        """It is prompt text, and it was false for a 429."""
        fetch = http_fetch(transport=_serving(), obey_robots=False)

        assert "waited out and fetched again" in fetch.description

    def test_a_secret_header_is_sent_as_its_value(self):
        seen: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("authorization", ""))
            return httpx.Response(200, text="ok")

        fetch = http_fetch(
            transport=_transport(handle),
            headers={"Authorization": SecretStr("Bearer sk-live-abc")},
            obey_robots=False,
        )
        fetch.call({"url": "https://example.com/a"})

        assert seen == ["Bearer sk-live-abc"]

    def test_the_whole_body_comes_back_by_default(self):
        fetch = http_fetch(transport=_serving(body="x" * 200_000), obey_robots=False)

        assert fetch.call({"url": "https://example.com/a"}) == "x" * 200_000

    def test_a_truncated_body_says_it_was_truncated(self):
        """A page cut without a word reads as a page that ended there."""
        fetch = http_fetch(transport=_serving(body="x" * 100), max_chars=10, obey_robots=False)

        body = fetch.call({"url": "https://example.com/a"})

        assert body.startswith("x" * 10)
        assert "truncated at 10 characters of 100" in body

    def test_an_empty_allow_list_is_refused_at_construction(self):
        with pytest.raises(ConfigurationError) as exc:
            http_fetch(allow_hosts=[])

        assert "permits no host at all" in str(exc.value)


class TestHttpFetchRedirects:
    def _bouncing(self, hops: dict[str, str], body: str = "<html>landed</html>"):
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            target = hops.get(str(request.url))
            if target is not None:
                return httpx.Response(302, headers={"location": target})
            return httpx.Response(200, text=body)

        return _transport(handle)

    def test_a_redirect_is_followed_to_the_page(self):
        fetch = http_fetch(transport=self._bouncing({"https://example.com/a": "/b"}))

        assert fetch.call({"url": "https://example.com/a"}) == "<html>landed</html>"

    def test_a_redirect_off_the_allow_list_is_refused(self):
        fetch = http_fetch(
            transport=self._bouncing({"https://docs.example.com/a": "https://elsewhere.test/b"}),
            allow_hosts=["docs.example.com"],
        )

        with pytest.raises(ModelFacingError) as exc:
            fetch.call({"url": "https://docs.example.com/a"})

        assert "elsewhere.test" in str(exc.value)

    def test_a_chain_longer_than_the_cap_is_refused(self):
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            step = int(request.url.path.strip("/") or 0)
            return httpx.Response(302, headers={"location": f"/{step + 1}"})

        fetch = http_fetch(transport=_transport(handle))

        with pytest.raises(ModelFacingError) as exc:
            fetch.call({"url": "https://example.com/0"})

        assert "redirected more than" in str(exc.value)

    def test_credentials_stay_with_the_host_the_agent_addressed(self):
        seen: dict[str, str | None] = {}

        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            seen[request.url.host] = request.headers.get("authorization")
            if request.url.host == "docs.example.com":
                return httpx.Response(302, headers={"location": "https://elsewhere.test/b"})
            return httpx.Response(200, text="ok")

        fetch = http_fetch(
            transport=_transport(handle),
            headers={"Authorization": SecretStr("Bearer sk-live-abc")},
        )
        fetch.call({"url": "https://docs.example.com/a"})

        assert seen["docs.example.com"] == "Bearer sk-live-abc"
        assert seen["elsewhere.test"] is None


class TestHttpFetchStaysOffThePrivateNetwork:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/health",
            "http://localhost/admin",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/internal",
            "http://[::1]/",
        ],
    )
    def test_a_private_or_reserved_address_is_refused(self, url):
        fetch = http_fetch(transport=_serving())

        with pytest.raises(ModelFacingError) as exc:
            fetch.call({"url": url})

        assert "allow_private" in str(exc.value)

    def test_a_redirect_into_the_private_network_is_refused(self):
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(302, headers={"location": "http://169.254.169.254/x"})

        fetch = http_fetch(transport=_transport(handle))

        with pytest.raises(ModelFacingError) as exc:
            fetch.call({"url": "https://example.com/a"})

        assert "169.254.169.254" in str(exc.value)

    def test_allow_private_permits_a_local_service(self):
        fetch = http_fetch(transport=_serving(), allow_private=True, obey_robots=False)

        assert fetch.call({"url": "http://127.0.0.1/health"}) == "<html>page</html>"


# -----------------------------------------------------------------------------------------
# web_search
# -----------------------------------------------------------------------------------------


PAID = DeclaredCost(currency="USD", per_call=0.005)

# The library fills `web_search`'s SpendMeter. These call the tool directly, so they fill one
# that records nothing; `test_web_search_spend.py` runs the real one through a pipeline.
METER = {"meter": SpendMeter(_spend=lambda amount, currency=None, source="measured": None)}


class TestWebSearch:
    def test_results_are_normalised_to_title_url_and_snippet(self):
        def provider(query: str, count: int):
            return [{"name": "Corveth", "link": "https://x.test/1", "description": "seed round"}]

        [result] = web_search(provider, declared_cost=PAID).call({"query": "corveth"}, METER)

        assert result == {
            "title": "Corveth",
            "url": "https://x.test/1",
            "snippet": "seed round",
        }

    def test_a_result_with_no_url_is_dropped(self):
        """A link the agent cannot follow is not a result."""

        def provider(query: str, count: int):
            return [{"title": "no link"}, {"title": "ok", "url": "https://x.test/1"}]

        results = web_search(provider, declared_cost=PAID).call({"query": "q"}, METER)

        assert [r["url"] for r in results] == ["https://x.test/1"]

    def test_nothing_found_is_an_empty_list(self):
        results = web_search(lambda q, n: [], declared_cost=PAID).call({"query": "q"}, METER)

        assert results == []

    def test_a_provider_failure_comes_back_to_the_model(self):
        def provider(query: str, count: int):
            raise RuntimeError("quota exhausted")

        with pytest.raises(ModelFacingError) as exc:
            web_search(provider, declared_cost=PAID).call({"query": "q"}, METER)

        assert "quota exhausted" in str(exc.value)

    def test_a_search_can_be_restricted_to_named_sites(self):
        seen: list[Any] = []

        def provider(query: str, count: int, domains=None):
            seen.append(domains)
            return [{"title": "t", "url": "https://asket.com/tee"}]

        web_search(provider, declared_cost=PAID).call(
            {"query": "t-shirt measurements", "domains": ["asket.com"]}, METER
        )

        assert seen == [["asket.com"]]

    def test_a_search_without_domains_passes_none_of_it_to_the_provider(self):
        seen: list[Any] = []

        def provider(query: str, count: int, **extra):
            seen.append(extra)
            return []

        web_search(provider, declared_cost=PAID).call({"query": "q"}, METER)

        assert seen == [{}]

    def test_the_model_is_shown_the_domains_argument(self):
        search = web_search(lambda q, n, domains=None: [], declared_cost=PAID)

        assert "domains" in search.parameters["properties"]
        assert search.parameters["required"] == ["query"]

    def test_a_provider_that_cannot_scope_refuses_by_name_rather_than_searching_everything(
        self,
    ):
        """An unscoped search reported as a scoped one is a false claim about the source."""
        called: list[str] = []

        def provider(query: str, count: int):
            called.append(query)
            return [{"title": "t", "url": "https://elsewhere.test/1"}]

        with pytest.raises(ModelFacingError) as exc:
            web_search(provider, declared_cost=PAID).call(
                {"query": "q", "domains": ["asket.com"]}, METER
            )

        assert "cannot be restricted to named sites" in str(exc.value)
        assert called == []

    def test_a_provider_taking_kwargs_can_be_scoped(self):
        seen: list[Any] = []

        def provider(query: str, count: int, **extra):
            seen.append(extra)
            return []

        web_search(provider, declared_cost=PAID).call({"query": "q", "domains": ["x.test"]}, METER)

        assert seen == [{"domains": ["x.test"]}]

    def test_provider_options_reach_every_call_uninterpreted(self):
        seen: list[Any] = []

        def provider(query: str, count: int, **extra):
            seen.append(extra)
            return []

        search = web_search(
            provider, declared_cost=PAID, provider_options={"country": "fi", "depth": "deep"}
        )
        search.call({"query": "one"}, METER)
        search.call({"query": "two", "domains": ["x.test"]}, METER)

        assert seen[0] == {"country": "fi", "depth": "deep"}
        assert seen[1] == {"country": "fi", "depth": "deep", "domains": ["x.test"]}

    def test_the_requested_count_reaches_the_provider(self):
        seen: list[int] = []
        search = web_search(lambda q, n: seen.append(n) or [], declared_cost=PAID, max_results=7)

        search.call({"query": "q"}, METER)
        search.call({"query": "q", "max_results": 2}, METER)

        assert seen == [7, 2]

    def test_it_declares_spending_and_a_cost(self):
        search = web_search(lambda q, n: [], declared_cost=PAID)

        assert search.side_effect_class is SideEffectClass.SPENDS_MONEY
        assert search.declared_cost == PAID

    def test_a_provider_that_is_not_callable_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            web_search(None, declared_cost=PAID)  # type: ignore[arg-type]

        assert "ships no provider" in str(exc.value)


# -----------------------------------------------------------------------------------------
# extract_to_schema
# -----------------------------------------------------------------------------------------


class ProductFacts(BaseModel):
    """Handcrafted, and both fields admit absence."""

    inseam_cm: Maybe[float]
    fabric: Maybe[str]


def _handle(content: str) -> ModelHandle:
    return ModelHandle(_complete=lambda prompt, **kwargs: fake_response(content=content))


class TestExtractToSchema:
    def test_it_returns_the_fields_the_passage_states(self):
        extract = extract_to_schema(ProductFacts)
        handle = _handle('{"inseam_cm": 81.0, "fabric": "denim"}')

        result = extract.call({"text": "81 cm inseam, denim"}, {"model": handle})

        assert result == {"inseam_cm": 81.0, "fabric": "denim"}

    def test_an_absent_field_comes_back_as_unknown_rather_than_a_guess(self):
        extract = extract_to_schema(ProductFacts)
        handle = _handle(
            '{"inseam_cm": {"type": "unknown", "reason": "not published"}, "fabric": "denim"}'
        )

        result = extract.call({"text": "denim"}, {"model": handle})

        assert result["inseam_cm"] == {"type": "unknown", "reason": "not published"}

    def test_prose_around_the_json_is_tolerated(self):
        extract = extract_to_schema(ProductFacts)
        handle = _handle('Here it is:\n{"inseam_cm": 81.0, "fabric": "denim"}\nDone.')

        assert extract.call({"text": "x"}, {"model": handle})["inseam_cm"] == 81.0

    def test_a_response_that_does_not_validate_comes_back_to_the_model(self):
        extract = extract_to_schema(ProductFacts)

        with pytest.raises(ModelFacingError) as exc:
            extract.call({"text": "x"}, {"model": _handle("no idea")})

        assert "did not produce the required fields" in str(exc.value)

    def test_the_model_is_offered_only_the_passage(self):
        extract = extract_to_schema(ProductFacts)

        assert set(extract.parameters["properties"]) == {"text"}
        assert extract.re_executed is True

    def test_the_name_defaults_from_the_schema(self):
        assert extract_to_schema(ProductFacts).name == "extract_productfacts"

    def test_a_schema_that_cannot_report_absence_is_refused(self):
        class Rigid(BaseModel):
            inseam_cm: float

        with pytest.raises(ConfigurationError) as exc:
            extract_to_schema(Rigid)

        assert "`unknown` variant" in str(exc.value)

    def test_the_waiver_is_available(self):
        class Rigid(BaseModel):
            label: str

        assert extract_to_schema(Rigid, allow_unknown=False).name == "extract_rigid"


# -----------------------------------------------------------------------------------------
# consult
# -----------------------------------------------------------------------------------------


class TestConsult:
    def _pipeline(self, ask):
        return Pipeline(
            [
                AgentNode(
                    _prompt,
                    tools=[consult(ask, answered_by="end_user")],
                    output_schema=Answer,
                    budget=Budget.unbounded(),
                )
            ],
            budget=Budget.unbounded(),
        )

    def _client(self):
        return FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        _call("consult", question="Trousers or jeans?", options=["trousers"])
                    ]
                ),
                fake_response(tool_calls=[_finish()]),
            ]
        )

    def _consultations(self, trajectory):
        return [r for r in read_trajectory(trajectory) if r["record_type"] == "consultation"]

    def test_an_answer_is_recorded_as_a_consultation(self, envelope, trajectory):
        self._pipeline(lambda q, o, a=None: "trousers").run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        [record] = self._consultations(trajectory)
        assert record["prompt"] == "Trousers or jeans?"
        assert record["options"] == ["trousers"]
        assert record["response"] == "trousers"
        assert record["resolution"] == "answered"
        assert record["blocking"] is True

    def test_no_tool_call_record_is_written_for_it(self, envelope, trajectory):
        self._pipeline(lambda q, o, a=None: "trousers").run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        names = [
            r["tool_name"] for r in read_trajectory(trajectory) if r["record_type"] == "tool_call"
        ]
        assert names == ["finish"]

    def test_declining_is_recorded_as_declined(self, envelope, trajectory):
        self._pipeline(lambda q, o, a=None: None).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        assert self._consultations(trajectory)[0]["resolution"] == "declined"

    def test_the_option_the_answer_was_is_recorded(self, envelope, trajectory):
        self._pipeline(lambda q, o, a=None: "trousers").run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        assert self._consultations(trajectory)[0]["chose"] == "trousers"

    def test_an_answer_outside_the_options_is_recorded_as_unmatched(self, envelope, trajectory):
        """Distinct from `declined`: they said something, and it is kept in `response`."""
        self._pipeline(lambda q, o, a=None: "shorts").run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        [record] = self._consultations(trajectory)
        assert record["resolution"] == "unmatched"
        assert record["response"] == "shorts"
        assert record["chose"] is None

    def test_a_replayed_answer_records_the_same_thing_the_live_run_did(self, tmp_path):
        """A `Reply` is a string, so a cassette stores the text and not which option it was.

        Deriving that again on replay is what keeps a replayed evaluation agreeing with the
        run it was recorded from. Without it the second run here reads `answered`.
        """
        from simple_agents import Cassette, RunEnvelope

        cassette = tmp_path / "c.jsonl"
        resolutions = []
        for mode in ("record", "replay"):
            envelope = RunEnvelope(
                run_dir=tmp_path / mode,
                cassette=getattr(Cassette, mode)(cassette),
            )
            self._pipeline(lambda q, o, a=None: "shorts").run(
                {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
            )
            records = read_trajectory(run_path(tmp_path / mode, RUN_ID, "trajectory.jsonl"))
            [record] = [r for r in records if r["record_type"] == "consultation"]
            resolutions.append((record["resolution"], record["chose"], record["response"]))

        assert resolutions[0] == ("unmatched", None, "shorts")
        assert resolutions[1] == resolutions[0]

    def test_an_answer_arriving_on_a_resume_is_read_the_same_way(self, envelope, trajectory):
        """The suspend path is where an untyped answer would come back in."""
        pipeline = self._pipeline(
            lambda q, o, a=None: (_ for _ in ()).throw(Suspend(waiting_for="them"))
        )
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client())
        pipeline.resume(
            RUN_ID,
            envelope=envelope,
            answer="trousers",
            model=FakeModelClient(responses=[fake_response(tool_calls=[_finish()])]),
        )

        answered = [r for r in self._consultations(trajectory) if r["answers"] is not None]
        assert [(r["resolution"], r["chose"]) for r in answered] == [("answered", "trousers")]

    def test_an_open_question_is_answered_rather_than_unmatched(self, envelope, trajectory):
        """Nothing was offered, so there is nothing for the answer to fail to match."""
        pipeline = self._pipeline(lambda q, o, a=None: "linen")
        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_call("consult", question="Which fabric?")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41, model=client)

        [record] = self._consultations(trajectory)
        assert record["resolution"] == "answered"
        assert record["chose"] is None

    def test_the_answer_reaches_the_model(self, envelope):
        seen: list[str] = []
        self._pipeline(lambda q, o, a=None: seen.append(q) or "trousers").run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=self._client()
        )

        assert seen == ["Trousers or jeans?"]

    def test_a_channel_that_is_not_callable_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            consult(None)  # type: ignore[arg-type]

        assert "never reads from a terminal itself" in str(exc.value)

    def test_it_is_read_only_and_asks_a_question(self):
        asked = consult(lambda q, o, a=None: None, answered_by="end_user")

        assert asked.side_effect_class is SideEffectClass.READ_ONLY
        assert asked.parameters["required"] == ["question"]


class TestWhichOptionTheAnswerWas:
    """`options` decides how an answer is read, and constrains nothing the end user says."""

    def _reply(self, answer, options=("yes", "no"), **kwargs):
        asked = consult(lambda q, o, a=None: answer, answered_by="end_user", **kwargs)
        return asked.fn(question="Ship it?", options=list(options) if options else None)

    def test_an_answer_matching_an_option_records_which(self):
        reply = self._reply("yes")

        assert reply == "yes"
        assert reply.chose == "yes"
        assert reply.matched is True

    def test_matching_folds_case_and_punctuation(self):
        """`normalise_text`, so the end user is not held to the exact spelling offered."""
        assert self._reply("Yes.").chose == "yes"
        assert self._reply("  NO  ").chose == "no"

    def test_an_answer_matching_nothing_is_kept_with_no_option(self):
        """The amendment case: they said something, and it is neither offered choice."""
        reply = self._reply("actually make it 3 stars")

        assert reply == "actually make it 3 stars"
        assert reply.chose is None
        assert reply.matched is False

    def test_a_question_offering_no_options_matches_nothing(self):
        reply = self._reply("blue", options=None)

        assert reply == "blue"
        assert reply.chose is None
        assert reply.options == ()

    def test_declining_is_none_rather_than_a_reply(self):
        """What `consult` has always returned for a refusal, so the contract is unchanged."""
        assert self._reply(None) is None

    def test_a_reply_is_a_string_so_it_reaches_the_model_as_the_text(self):
        reply = self._reply("yes")

        assert isinstance(reply, str)
        assert f"{reply}" == "yes"

    def test_a_project_matcher_replaces_the_rule(self):
        reply = self._reply("aye", match=lambda answer, options: "yes" if answer else None)

        assert reply.chose == "yes"

    def test_a_matcher_returning_something_not_offered_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            self._reply("aye", match=lambda answer, options: "maybe")

        assert "not one of the options" in str(exc.value)

    def test_a_matcher_that_is_not_callable_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            consult(lambda q, o, a=None: None, answered_by="end_user", match="nearest")  # type: ignore[arg-type]

        assert "returning the option the answer is" in str(exc.value)


class TestRoutingOnTheAnswer:
    def _route(self, **kwargs):
        if "unmatched" in kwargs and not kwargs.get("exhaustive"):
            kwargs.setdefault("unavailable", "proceed")
            kwargs.setdefault("shelved", "proceed")
        return on_reply({"yes": "apply", "no": "stop"}, **kwargs)

    def test_each_option_goes_to_its_successor(self):
        route = self._route(unmatched="amend", declined="stop")

        assert route(Reply("yes", chose="yes", options=("yes", "no")), None) == "apply"
        assert route(Reply("no", chose="no", options=("yes", "no")), None) == "stop"

    def test_an_unmatched_answer_takes_the_unmatched_branch(self):
        route = self._route(unmatched="amend", declined="stop")
        reply = Reply("make it 3 stars", chose=None, options=("yes", "no"))

        assert route(reply, None) == "amend"

    def test_declining_takes_the_declined_branch(self):
        assert self._route(unmatched="amend", declined="stop")(None, None) == "stop"

    def test_it_reads_the_reply_off_a_named_field(self):
        route = self._route(field="answer", unmatched="amend", declined="stop")
        carrier = SimpleNamespace(answer=Reply("yes", chose="yes", options=("yes", "no")))

        assert route(carrier, None) == "apply"

    def test_a_route_with_no_branch_for_the_unexpected_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            self._route()

        assert "no branch for unmatched and declined and unavailable and shelved" in str(exc.value)
        assert "exhaustive=True" in str(exc.value)

    def test_the_refusal_names_only_the_branch_that_is_missing(self):
        with pytest.raises(ConfigurationError) as exc:
            on_reply({"yes": "apply"}, declined="stop", unavailable="proceed", shelved="proceed")

        assert "no branch for unmatched." in str(exc.value)

    def test_exhaustive_waives_all_four_branches(self):
        route = self._route(exhaustive=True)

        assert route(Reply("yes", chose="yes", options=("yes", "no")), None) == "apply"

    def test_exhaustive_beside_a_branch_is_refused_as_a_contradiction(self):
        with pytest.raises(ConfigurationError) as exc:
            self._route(exhaustive=True, unmatched="amend")

        assert "contradict each other" in str(exc.value)

    def test_an_unmatched_answer_under_exhaustive_ends_the_run(self):
        """The project asserted it could not happen. Picking a branch anyway would guess."""
        route = self._route(exhaustive=True)
        reply = Reply("make it 3 stars", chose=None, options=("yes", "no"))

        with pytest.raises(CallerFacingError) as exc:
            route(reply, None)

        assert "'make it 3 stars'" in str(exc.value)
        assert "exhaustive=True" in str(exc.value)

    def test_declining_under_exhaustive_ends_the_run(self):
        with pytest.raises(CallerFacingError) as exc:
            self._route(exhaustive=True)(None, None)

        assert "declined to answer" in str(exc.value)

    def test_an_option_with_no_successor_ends_the_run(self):
        route = on_reply(
            {"yes": "apply"},
            unmatched="amend",
            declined="stop",
            unavailable="proceed",
            shelved="proceed",
        )
        reply = Reply("no", chose="no", options=("yes", "no"))

        with pytest.raises(CallerFacingError) as exc:
            route(reply, None)

        assert "nothing says where it goes" in str(exc.value)

    def test_an_empty_mapping_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            on_reply(
                {},
                unmatched="amend",
                declined="stop",
                unavailable="proceed",
                shelved="proceed",
            )

        assert "at least one option" in str(exc.value)

    def test_it_carries_what_it_maps_for_the_manifest(self):
        """A closure's source digest is the same whatever it closed over, so the mapping is
        recorded structurally or two different routes are indistinguishable in the manifest."""
        route = self._route(exhaustive=True)

        assert route.consultation_route == {
            "chose": {"yes": "apply", "no": "stop"},
            "unmatched": None,
            "declined": None,
            "unavailable": None,
            "shelved": None,
            "field": None,
            "exhaustive": True,
        }


class TestTheLibraryWaitsOutAThrottle:
    """`Throttled` is the one tool failure the library acts on rather than records."""

    def _node(self, calls, tool_fn):
        pipeline = Pipeline(
            [Deterministic(lambda inputs, ctx: ctx.call_tool("busy"), tools=[tool_fn])],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        return pipeline

    def test_it_calls_again_and_the_second_answer_is_what_comes_back(self, tmp_path):
        attempts = []

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def busy() -> str:
            "A source that is busy once."
            attempts.append(1)
            if len(attempts) == 1:
                raise Throttled("busy", retry_after_s=0.0)
            return "the page"

        result = self._node(attempts, busy).run({}, envelope=RunEnvelope(run_dir=tmp_path / "a"))

        assert result.output == "the page"
        assert len(attempts) == 2

    def test_a_source_still_busy_when_the_attempts_run_out_reaches_the_caller(self, tmp_path):
        attempts = []

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def busy() -> str:
            "A source that is always busy."
            attempts.append(1)
            raise Throttled("still busy", retry_after_s=0.0)

        with pytest.raises(ModelFacingError) as exc:
            self._node(attempts, busy).run({}, envelope=RunEnvelope(run_dir=tmp_path / "b"))

        assert "still busy" in str(exc.value)
        assert len(attempts) == TOOL_RETRY_ATTEMPTS

    def test_an_ordinary_failure_is_not_retried(self, tmp_path):
        attempts = []

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def busy() -> str:
            "A source with nothing to give."
            attempts.append(1)
            raise ModelFacingError("no match")

        with pytest.raises(ModelFacingError):
            self._node(attempts, busy).run({}, envelope=RunEnvelope(run_dir=tmp_path / "c"))

        assert len(attempts) == 1

    def test_what_the_source_asked_for_wins_over_the_backoff(self):
        assert _throttle_wait(0, 15.0) == 15.0
        assert _throttle_wait(0, None) == TOOL_RETRY_INITIAL_S
        assert _throttle_wait(1, None) == TOOL_RETRY_INITIAL_S * 2

    def test_a_source_asking_for_longer_than_the_cap_gets_the_cap(self):
        assert _throttle_wait(0, 3600.0) == TOOL_RETRY_MAX_S
        assert _throttle_wait(20, None) == TOOL_RETRY_MAX_S

    def test_a_node_body_catches_the_kind_of_failure_the_tool_raised(self, tmp_path):
        """`ctx.call_tool` re-raises the failure itself. It rebuilt a plain `ModelFacingError`
        from the text until `Throttled` existed to be flattened."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def busy() -> str:
            "Always busy."
            raise Throttled("the source is busy", retry_after_s=0.0)

        seen = {}

        def body(inputs, ctx):
            try:
                return ctx.call_tool("busy")
            except Throttled as exc:
                seen["retry_after_s"] = exc.retry_after_s
                return "handled"

        pipeline = Pipeline(
            [Deterministic(body, node_id="n", tools=[busy])],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))

        assert result.output == "handled"
        assert seen == {"retry_after_s": 0.0}

    def test_a_replayed_throttle_is_still_a_throttle(self, tmp_path, monkeypatch):
        """A recording is made after the retries are spent, so replay raises rather than
        waiting again, and it raises the same kind.

        The wait is patched out: what is under test is what crosses the cassette, and the
        recording pays the real ladder otherwise.
        """
        monkeypatch.setattr("simple_agents.context._throttle_wait", lambda *a: 0.0)

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def busy() -> str:
            "Always busy."
            raise Throttled("the source is busy", retry_after_s=12.0)

        seen = []

        def body(inputs, ctx):
            try:
                return ctx.call_tool("busy")
            except Throttled as exc:
                seen.append(exc.retry_after_s)
                return "handled"

        pipeline = Pipeline(
            [Deterministic(body, node_id="n", tools=[busy])],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        cassette = tmp_path / "c.jsonl"
        pipeline.run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette)),
        )

        result = pipeline.run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette)),
        )

        assert result.output == "handled"
        assert seen == [12.0, 12.0]

    def test_an_ordinary_tool_failure_is_still_a_model_facing_error(self, tmp_path):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def empty() -> str:
            "Nothing to give."
            raise ModelFacingError("no match")

        def body(inputs, ctx):
            try:
                return ctx.call_tool("empty")
            except Throttled:
                return "wrongly caught as a throttle"
            except ModelFacingError as exc:
                return str(exc)

        pipeline = Pipeline(
            [Deterministic(body, node_id="n", tools=[empty])],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

        assert pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path)).output == "no match"
