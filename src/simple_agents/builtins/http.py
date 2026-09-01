"""Fetching a URL, with robots.txt honoured and a rate limit.

Distinct from search: search finds candidates, this reads one of them. ``http_fetch`` returns
what the server sent; ``read_page`` returns the same page reduced to text a model can be given
whole. Credentials are passed as ``pydantic.SecretStr``, which is redacted by its type wherever
the run records it.

The cassette stores each fetch under its arguments, so a recorded run replays every page it
read with no network, which is the caching an evaluation needs. It replays one run: a later run
asking for a page that run did not ask for fetches it. ``cache=UrlCache(...)`` is what serves a
page across runs.
"""

from __future__ import annotations

import ipaddress
import time
import urllib.robotparser
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import httpx

from ..adapters._http import retry_after_seconds
from ..errors import ConfigurationError, ModelFacingError, Throttled
from ..tools import DeclaredCost, SideEffectClass, Tool, tool
from ..tools import _CeilingReached
from .hostpolicy import HostPolicy
from .htmlreduce import DEFAULT_ORDER, reduce_html
from .urlcache import UrlCache

__all__ = ["http_fetch", "read_page"]

DEFAULT_USER_AGENT = "simple-agents"
MAX_ROBOTS_BYTES = 500_000

# How many redirects one fetch follows before refusing. Every destination is checked the way
# the first URL is, so a chain is a sequence of permitted fetches rather than one unchecked one.
MAX_REDIRECTS = 5

# Header names sent only to the host the agent addressed. A redirect to another host is a
# different party, and forwarding a credential to it discloses the credential.
CREDENTIAL_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie"})

# The prompt text both fetch variants carry. One constant, so a tool built with a policy and
# one built without describe themselves identically to the model.
FETCH_DESCRIPTION = """Fetch a web page and return its body as text.

Takes one absolute URL, including the scheme. Returns the response body as it came
back, which for a web page is its markup. Fails with the reason when the page is
missing, the site refuses, or the site's robots.txt disallows it; those failures mean
to try a different URL rather than the same one again. A site asking to be requested
less often is waited out and fetched again before any failure is reported, and if it is
still busy the failure says so: that page exists and was not read. This reads one page:
use a search tool to find pages.
"""

READ_DESCRIPTION = """Read one web page and return its text, with any tables on it laid out first.

Takes one absolute URL including the scheme. Returns the page as text: its tables,
the structured data it declared, then its prose. A table on the page is near the top
of what comes back.

Fails, with the reason, when the site refuses, when its robots.txt disallows the page,
when the page is missing, and when the page holds no readable text. Those failures mean
to try a different URL rather than the same one again. A site asking to be requested
less often is waited out and fetched again before any failure is reported, and if it is
still busy the failure says so: that page exists and was not read. This reads one page
from its address: use a search tool to find addresses.
"""


# What a site sends when the answer is "not now" rather than "not here". 408 is the request
# timing out at the server, 429 the rate limit, and 503 the service being unavailable, which
# is the status a site under load returns. Each is retried; every other 4xx and 5xx is not.
THROTTLED_STATUSES = frozenset({408, 429, 503})


def http_fetch(
    *,
    name: str = "http_fetch",
    policy: HostPolicy | None = None,
    cache: UrlCache | None = None,
    headers: Mapping[str, Any] | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout_s: float = 30.0,
    min_interval_s: float = 0.0,
    obey_robots: bool = True,
    allow_hosts: list[str] | None = None,
    allow_private: bool = False,
    max_chars: int | None = None,
    declared_cost: DeclaredCost | None = None,
    version: str | None = None,
    transport: Any = None,
) -> Tool:
    """A tool that fetches one URL and returns its body as text.

    ``headers`` carries anything the site needs, and a credential in it belongs in a
    ``SecretStr`` so the run records it as redacted::

        from pydantic import SecretStr

        registry.add(http_fetch(
            headers={"Authorization": SecretStr(os.environ["SUPPLIER_TOKEN"])},
            min_interval_s=1.0,
            allow_hosts=["docs.example.com"],
        ))

    ``min_interval_s`` waits that long between fetches. ``allow_hosts`` refuses any other host,
    and ``policy`` takes a :class:`HostPolicy` in its place for a reachable set that grows
    while the run proceeds; passing both is refused. ``cache`` serves an address read before
    without requesting it again.

    **The whole body comes back.** ``max_chars`` cuts it and says so in the returned text;
    ``read_page`` returns the same page as text small enough to send whole.

    Redirects are followed, up to five, each destination checked against ``allow_hosts``,
    robots.txt and the address rule. Credentialed headers go only to the host addressed. A URL
    naming the local machine or a private address is refused unless ``allow_private=True``,
    read off the URL, so a hostname resolving privately is not detected.

    Declared ``READ_ONLY``. A 404, a 500 and a timeout are model-facing, since the model chose
    the URL and can choose another. A 408, 429 or 503 raises :class:`Throttled`, which the
    library waits out and fetches again, honouring a ``Retry-After``.
    """
    if allow_hosts is not None and not allow_hosts:
        raise ConfigurationError(
            "http_fetch(allow_hosts=[]) permits no host at all, so every fetch is refused. "
            "Pass the hosts the agent may read, such as allow_hosts=['docs.example.com'], or "
            "allow_hosts=None to permit any."
        )
    if policy is not None and allow_hosts is not None:
        raise ConfigurationError(
            "http_fetch was given both policy= and allow_hosts=, which are two sources for "
            "one decision. Pass the policy alone; its hosts are the permitted set, and it can "
            "be given more while the run proceeds."
        )

    wire_headers = {"User-Agent": user_agent, **_unwrap(headers or {})}
    permitted = set(allow_hosts) if allow_hosts is not None else None
    robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
    last_fetch = [0.0]
    # Redirects are followed by the loop below rather than by the client, so every hop passes
    # through the same checks the first URL does.
    client = httpx.Client(timeout=timeout_s, follow_redirects=False, transport=transport)

    def _refuse(reason: str) -> ModelFacingError:
        return ModelFacingError(reason, retryable=False)

    def _allowed(url: str, bound: HostPolicy | None) -> None:
        host = urlparse(url).netloc
        if permitted is not None and host not in permitted:
            raise _refuse(
                f"This agent may not fetch from {host!r}. Permitted hosts: "
                f"{', '.join(sorted(permitted))}."
            )
        if bound is not None and not bound.in_scope(host):
            raise _refuse(bound.refusal_for(host))
        _refuse_reserved(url)
        if not obey_robots:
            return
        if host not in robots:
            robots[host] = _read_robots(client, url)
        parser = robots[host]
        if parser is not None and not parser.can_fetch(user_agent, url):
            raise _refuse(
                f"{url} is disallowed by that site's robots.txt for this agent. Do not fetch "
                f"it. Find the information on a site that permits it."
            )

    def _refuse_reserved(url: str) -> None:
        """Refuse a URL that names the local machine or a non-global address.

        Reads the URL itself, so an IP literal and ``localhost`` are caught and a hostname
        that resolves privately is not. Deployed where the network holds anything sensitive,
        the agent's host still needs its own egress policy.
        """
        if allow_private:
            return
        host = urlparse(url).hostname or ""
        if host == "localhost" or host.endswith(".localhost"):
            raise _refuse(
                f"{url} points at the local machine, which this agent may not fetch from. "
                f"Fetch a public URL. A project that serves its own content locally passes "
                f"http_fetch(allow_private=True)."
            )
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return
        if not address.is_global:
            raise _refuse(
                f"{url} points at {host}, a private or reserved address, which this agent "
                f"may not fetch from. Fetch a public URL. A project that reads from its own "
                f"network passes http_fetch(allow_private=True)."
            )

    def _cut(body: str) -> str:
        """The body, or as much of it as ``max_chars`` allows, saying where it was cut."""
        if max_chars is None or len(body) <= max_chars:
            return body
        return body[:max_chars] + f"\n[truncated at {max_chars} characters of {len(body)}]"

    def _paced_get(
        url: str, send_headers: Mapping[str, str], bound: HostPolicy | None
    ) -> httpx.Response:
        if bound is not None:
            try:
                bound.spend_fetch()
            except _CeilingReached as reached:
                raise _refuse(str(reached)) from reached
        waited = min_interval_s - (time.monotonic() - last_fetch[0])
        if min_interval_s and waited > 0:
            time.sleep(waited)
        last_fetch[0] = time.monotonic()
        try:
            return client.get(url, headers=dict(send_headers))
        except httpx.HTTPError as exc:
            raise _refuse(
                f"{url} could not be reached: {type(exc).__name__}. Try a different URL."
            ) from exc

    def _fetch(url: str, bound: HostPolicy | None) -> str:
        if not url.lower().startswith(("http://", "https://")):
            raise _refuse(
                f"{url!r} is not an absolute HTTP URL. Pass the whole address including the "
                f"scheme, such as 'https://example.com/page'."
            )
        _allowed(url, bound)

        if cache is not None:
            stored = cache.get(url)
            if stored is not None:
                return _cut(stored.value)

        origin = urlparse(url).netloc
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            send = wire_headers
            if urlparse(current).netloc != origin:
                send = {
                    k: v for k, v in wire_headers.items() if k.lower() not in CREDENTIAL_HEADERS
                }
            response = _paced_get(current, send, bound)
            if not response.is_redirect:
                break
            current = str(httpx.URL(current).join(response.headers["location"]))
            if not current.lower().startswith(("http://", "https://")):
                raise _refuse(
                    f"{url} redirected to {current!r}, which is not an HTTP URL. Try a "
                    f"different URL."
                )
            _allowed(current, bound)
        else:
            raise _refuse(
                f"{url} redirected more than {MAX_REDIRECTS} times without reaching a page. "
                f"Try a different URL."
            )
        if response.status_code in THROTTLED_STATUSES:
            # The rate rather than the request. Raised as `Throttled` so the library waits
            # and fetches again, since a throttle answered as data reads as the page not
            # being there. `Retry-After` is what the site asked for, where it sent one.
            raise Throttled(
                f"{current} answered {response.status_code}, which is this site asking to "
                f"be requested less often. It is not the page being missing.",
                retry_after_s=retry_after_seconds(response.headers.get("Retry-After")),
            )
        if response.status_code >= 400:
            raise _refuse(
                f"{current} answered {response.status_code}. Try a different URL; requesting "
                f"this one again will answer the same way."
            )
        body = response.text
        if cache is not None:
            cache.put(url, body)
        return _cut(body)

    # One description for both variants, so the prompt text cannot drift between them.
    if policy is None:

        def fetch(url: str) -> str:
            return _fetch(url, None)

    else:

        def fetch(url: str, scope: HostPolicy) -> str:  # type: ignore[misc]
            return _fetch(url, scope)

    fetch.__doc__ = FETCH_DESCRIPTION
    built = tool(
        side_effect_class=SideEffectClass.READ_ONLY,
        name=name,
        version=version,
        declared_cost=declared_cost,
    )(fetch)
    built.fetch_policy = policy
    return built


def _unwrap(headers: Mapping[str, Any]) -> dict[str, str]:
    """Header values as strings, reading a ``SecretStr`` for its value at send time.

    The type protects the value wherever the run records it. What goes on the wire is an
    ordinary string, and only the pattern rules see that.
    """
    out: dict[str, str] = {}
    for key, value in headers.items():
        reveal = getattr(value, "get_secret_value", None)
        out[key] = reveal() if callable(reveal) else str(value)
    return out


def _read_robots(client: httpx.Client, url: str) -> urllib.robotparser.RobotFileParser | None:
    """The site's robots.txt, or ``None`` when it has none or could not be read.

    A site with no robots.txt permits everything, which is what the standard says. A site
    whose robots.txt cannot be read is treated the same way, so a fetch is not refused on the
    strength of a failed request to a different file.
    """
    parsed = urlparse(url)
    parser = urllib.robotparser.RobotFileParser()
    try:
        response = client.get(
            f"{parsed.scheme}://{parsed.netloc}/robots.txt", follow_redirects=True
        )
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        return None
    parser.parse(response.text[:MAX_ROBOTS_BYTES].splitlines())
    return parser


# A page that fetches and reduces to less than this is rendered by JavaScript rather than
# served as markup. The number is a floor on "there is text here at all", not on usefulness.
MIN_USEFUL_CHARS = 200


def read_page(
    *,
    name: str = "read_page",
    cache: UrlCache | None = None,
    max_chars: int | None = 24_000,
    order: Any = DEFAULT_ORDER,
    link_words: Sequence[str] = (),
    min_useful_chars: int = MIN_USEFUL_CHARS,
    version: str | None = None,
    **fetch_options: Any,
) -> Tool:
    """A tool that fetches one URL and returns it reduced to text.

    Composes :func:`http_fetch` with :func:`reduce_html`, so a page arrives as its tables, its
    structured data and its prose rather than as markup::

        registry.add(read_page(
            allow_hosts=["www.example.com"],
            link_words=("size guide", "specifications"),
        ))

    Every :func:`http_fetch` keyword is accepted and passed on, except ``max_chars``, which
    bounds the reduced text here rather than the body. ``order`` is what is rendered and in
    what sequence (``docs/tools.md`` §4.3). ``link_words`` are the words that mark a link worth
    following, and matching same-host links are listed at the end of the reply.

    ``cache`` stores the page as it came back, so a reduction change does not discard what is
    stored, and a page served from it says how old it is.

    A page that reduces to less than ``min_useful_chars`` and holds no table fails
    model-facing, saying the site is rendered by JavaScript and the rest of it will be too.

    Declared ``READ_ONLY`` and keyed by its arguments: the reduction is a function of the body,
    so a replay reproduces it without fetching.
    """
    fetcher = http_fetch(cache=cache, **fetch_options)
    render_order = tuple(order)
    words = tuple(link_words)
    limit = max_chars
    takes_scope = any(issubclass(kind, HostPolicy) for kind in fetcher.handles.values())

    def _read(url: str, scope: HostPolicy | None) -> str:
        stored = cache.get(url) if cache is not None else None
        body = fetcher.fn(url=url, scope=scope) if takes_scope else fetcher.fn(url=url)
        reduced = reduce_html(body, base_url=url)
        text = reduced.as_prompt(limit, order=render_order)

        if len(text.strip()) < min_useful_chars and not reduced.tables:
            raise ModelFacingError(
                f"{url} was fetched successfully and holds no readable text, only "
                f"{len(text.strip())} characters, which is what a page rendered by JavaScript "
                f"returns. Every page on this site will behave the same way, so do not try "
                f"another address here. Look on a different site, or report what could not be "
                f"read.",
                retryable=False,
            )

        if stored is not None:
            text = f"[read from a local copy stored {stored.age_days:.1f} days ago]\n{text}"

        found = reduced.links_matching(words)
        if not found:
            return text
        listed = "\n".join(f"  {link.url}  ({link.text})" for link in found)
        return (
            f"{text}\n\n=== LINKS ON THIS PAGE THAT MAY HOLD MORE ===\n"
            f"These are on the same site. Read one with {name} if this page did not have "
            f"what was wanted:\n{listed}"
        )

    if takes_scope:

        def read(url: str, scope: HostPolicy) -> str:
            return _read(url, scope)

    else:

        def read(url: str) -> str:  # type: ignore[misc]
            return _read(url, None)

    read.__doc__ = READ_DESCRIPTION
    built = tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version=version)(read)
    built.fetch_policy = fetch_options.get("policy")
    return built
