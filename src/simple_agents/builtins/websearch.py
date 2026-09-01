"""Web search, over a provider the project supplies.

The library owns the declarations and the normalised result shape; the project owns the
provider, because a search API is a vendor choice with a key and a price attached and those
belong where the rest of the project's configuration is.

A provider is a function taking the query and how many results to return, and returning a
sequence of mappings carrying a title, a url and a snippet. With ``http_fetch`` registered,
writing one is a request and a parse.
"""

from __future__ import annotations

import inspect
import json
from typing import Annotated, Any, Callable, Mapping, Sequence

from pydantic import Field

from ..errors import ConfigurationError, ModelFacingError
from ..tools import DeclaredCost, SideEffectClass, SpendMeter, Tool, tool
from .urlcache import UrlCache, request_key

__all__ = ["web_search", "SearchProvider"]

SearchProvider = Callable[..., Sequence[Mapping[str, Any]]]

TITLE_KEYS = ("title", "name", "heading")
URL_KEYS = ("url", "link", "href")
SNIPPET_KEYS = ("snippet", "description", "summary", "content", "text")


def web_search(
    provider: SearchProvider,
    *,
    declared_cost: DeclaredCost,
    name: str = "web_search",
    max_results: int = 5,
    provider_options: Mapping[str, Any] | None = None,
    cache: UrlCache | None = None,
    version: str | None = None,
) -> Tool:
    """A tool that searches the web through ``provider``.

    Declared ``SPENDS_MONEY``, so ``declared_cost`` is required: an evaluation runs k rollouts
    over n examples and the bill is k×n times the per-call figure::

        def brave(query: str, count: int) -> list[dict]:
            body = json.loads(fetch(f"https://api.example.com/search?q={quote(query)}"))
            return body["results"]

        registry.add(web_search(
            brave, declared_cost=DeclaredCost(currency="USD", per_call=0.005)
        ))

    Results are normalised to ``title``, ``url`` and ``snippet``, read from the usual key
    names. One carrying no recognisable url is dropped, since a link the agent cannot follow
    is not a result.

    **A provider that accepts ``domains`` lets the model restrict a search to named sites**,
    under the library's name for it, which the provider translates to whatever its API calls::

        def brave(query: str, count: int, domains: list[str] | None = None) -> list[dict]:
            if domains:
                query = " ".join(f"site:{d}" for d in domains) + " " + query
            ...

    A provider without the parameter keeps working, and a search asking for domains against
    one is refused by name rather than run unscoped.

    ``provider_options`` reaches every call uninterpreted, for settings the builder fixes
    rather than the model chooses. ``cache`` answers a request made before without calling the
    provider, keyed on everything that identifies it::

        web_search(brave, declared_cost=PAID, provider_options={"country": "fi"},
                   cache=UrlCache("cache/search", max_age_days=7))

    **A search the cache answered reports no spend**, so it depletes no ``max_cost`` and
    reaches no ``totals.tool_spend``. A search that reached the provider reports
    ``declared_cost.per_call``, which is what the tool knows: a provider returns results and
    no price. `docs/tools.md` §1.5 covers what that means for adding the two up.
    """
    if not callable(provider):
        raise ConfigurationError(
            "web_search(provider=...) takes a function of (query, count) returning a sequence "
            "of results. The library ships no provider, because a search API is a vendor "
            "choice with a key and a price. Write one against whichever API the project uses."
        )
    default_count = max_results
    options = dict(provider_options or {})
    takes_domains = _accepts(provider, "domains")

    @tool(
        side_effect_class=SideEffectClass.SPENDS_MONEY,
        name=name,
        version=version,
        declared_cost=declared_cost,
    )
    def search_the_web(
        meter: SpendMeter,
        query: str,
        max_results: int = default_count,
        domains: Annotated[
            list[str] | None,
            Field(
                description="Restrict the search to these sites, as bare hosts such as "
                "'example.com'. Omit to search the whole web."
            ),
        ] = None,
    ) -> list[dict[str, Any]]:
        """Search the web and return the best matching pages.

        Each result carries a title, a url and a short snippet. The snippet is an extract
        rather than the page: fetch the url to read one. Returns an empty list when the search
        finds nothing, which is worth trying different terms for. This costs money on every
        call, so prefer one well-chosen query to several broad ones.

        Pass `domains` to search named sites only, which is how to check a claim on the site
        that published it.
        """
        key = request_key("web_search", name, query, max_results, sorted(domains or ()), options)
        if cache is not None:
            stored = cache.get(key)
            if stored is not None:
                return json.loads(stored.value)

        extra = dict(options)
        if domains:
            if not takes_domains:
                raise ModelFacingError(
                    f"This search cannot be restricted to named sites, so searching "
                    f"{', '.join(domains)} is not possible here. Search without domains and "
                    f"read the results, or fetch a page from that site directly.",
                    retryable=False,
                )
            extra["domains"] = list(domains)
        try:
            raw = provider(query, max_results, **extra)
        except ModelFacingError:
            raise
        except Exception as exc:
            raise ModelFacingError(
                f"The search provider failed on {query!r}: {type(exc).__name__}: {exc}. Try a "
                f"different query, or answer from what is already known.",
                retryable=True,
            ) from exc
        if declared_cost.per_call is not None:
            # The price is the one declared here, not one the provider returned.
            # The meter is what lets a cache hit report nothing.
            meter.spend(declared_cost.per_call, source="declared")
        results = [normalised for item in raw if (normalised := _normalise(item)) is not None]
        if cache is not None:
            cache.put(key, json.dumps(results))
        return results

    return search_the_web


def _accepts(provider: SearchProvider, parameter: str) -> bool:
    """Whether the provider takes this keyword, read off its signature.

    Presence of the parameter is the capability declaration, so a provider written before it
    existed keeps working and one that cannot serve a request is refused by name. A provider
    taking ``**kwargs`` accepts everything.
    """
    try:
        signature = inspect.signature(provider)
    except (TypeError, ValueError):
        return False
    for candidate in signature.parameters.values():
        if candidate.kind is candidate.VAR_KEYWORD:
            return True
        if candidate.name == parameter and candidate.kind is not candidate.POSITIONAL_ONLY:
            return True
    return False


def _normalise(item: Mapping[str, Any]) -> dict[str, Any] | None:
    """One provider result in the shape the model is shown, or ``None`` if it has no url."""
    if not isinstance(item, Mapping):
        return None
    url = _first(item, URL_KEYS)
    if not url:
        return None
    return {
        "title": _first(item, TITLE_KEYS) or "",
        "url": url,
        "snippet": _first(item, SNIPPET_KEYS) or "",
    }


def _first(item: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""
