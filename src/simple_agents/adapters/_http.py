"""JSON over HTTP, shared by the shipped adapters.

Both backends speak JSON over HTTPS, so both use this. It owns four things an adapter should
not each solve differently: timeouts, retries on the statuses worth retrying, classification
of everything else into a caller-facing error, and the error text that names the fix.

Every failure here is caller-facing. A model call that did not happen invalidates the run, so
it is raised rather than handed to the model as data (``simple_agents.errors``).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, replace
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

import httpx

from ..context_builder import ContextOverflow
from ..errors import CallerFacingError, Suspend
from ..models import note_held_back

__all__ = ["Retry", "HTTPBackend", "HttpResult", "retry_after_seconds"]

# 529 is what Anthropic answers an overload with, documented as a status to retry with backoff
# the way a 503 is. Added 2026-09-06.
RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504, 529})

# What each backend says when the request is longer than the model's context window. Mistral
# and vLLM were measured 2026-07-27 by `scripts/probe_context_overflow.py` and Gemini
# 2026-08-12 at the adapter build: all three answered 400, none carried a usage block, and each
# message contained one of the phrases below. The bodies are stored verbatim as
# `tests/fixtures/wire/mistral/error_context_overflow.json` and the vllm and gemini
# equivalents, which is what the matcher's tests read.
#
# A backend phrasing it differently falls through to the general refusal below, which carries
# the backend's own message. Only the phrases that were observed are matched.
OVERFLOW_PHRASES = (
    "maximum context length",
    "input token count exceeds the maximum number of tokens allowed",
    "prompt is too long",  # Anthropic, measured 2026-09-06
    "prompt exceeds max length",  # GLM, measured 2026-09-07
    "exceeded model token limit",  # Kimi, measured 2026-09-07
)
OVERFLOW_STATUSES = frozenset({400, 413, 422})

# A backend that answers a bad key with 400 rather than 401, which Gemini does. Matched so the
# refusal says to check the key rather than to check the parameters of a request that was
# fine. The body is `tests/fixtures/wire/gemini/error_bad_key.json`.
CREDENTIAL_PHRASES = ("api key not valid",)

# What a backend says when the allowance it refused against resets on a scale retries cannot
# reach. A per-minute window clears inside a backoff ladder; a spending cap or a monthly quota
# does not, so climbing the ladder against one spends the run's wall clock and clears nothing.
#
# Gemini's spend-cap refusal was measured on 2026-08-24 across 54 calls of one evaluation, each
# of which waited the full 31-second ladder and raised. That backend publishes no `Retry-After`
# and no rate-limit headers, so the message is what says which kind of 429 it is. The body is
# `tests/fixtures/wire/gemini/error_spend_cap.json`.
#
# Gemini's depleted-prepayment refusal was measured on 2026-09-02 across a 150-item fan-out
# retried six times each, three times over, none of which cleared it. The body is
# `tests/fixtures/wire/gemini/error_prepaid_spent.json`.
#
# Only phrases that were observed are matched, as with OVERFLOW_PHRASES above. A backend
# phrasing it differently falls through to the retry ladder. A project that meets such a
# backend names the wording itself with `Retry(spent_quota_phrases=...)`, which adds to these.
QUOTA_PHRASES = (
    "monthly spending cap",  # Mistral
    "prepayment credits are depleted",  # Gemini
    # Documented rather than measured, 2026-09-06, from each provider's error page. None could
    # be triggered from a funded account.
    "current quota, please check",  # OpenAI, `insufficient_quota`
    "api usage limits",  # Anthropic: the tier's cap (a 429), a self-set limit (a 400)
    "credit balance is too low",  # Anthropic, a prepaid balance spent, a 400
    # Measured 2026-09-07 against a spent DeepSeek balance and a GLM account with none.
    "insufficient balance",  # DeepSeek (a 402), GLM (a 429, beside code 1113)
    "balance is insufficient",  # Kimi, the other word order
    "token quota is insufficient",  # Kimi, a spent allowance that is not the balance
)

# Error codes that say the same thing, for a backend that names one beside its message. OpenAI
# puts it in `error.code`, Anthropic in `error.details.error_code` and Kimi in `error.type`;
# `_codes_from` reads all three. The OpenAI and Anthropic codes are documented rather than
# measured, 2026-09-06. Matched exactly, since a code is one token.
QUOTA_CODES = frozenset(
    {
        "insufficient_quota",  # OpenAI
        "credit_balance_exhausted",  # OpenAI
        "organization_spend_limit_exceeded",  # OpenAI
        "project_spend_limit_exceeded",  # OpenAI
        "organization_usage_limit_exceeded",  # OpenAI
        "enforced_spend_limit_reached",  # Anthropic
        "exceeded_current_quota_error",  # Kimi, in `error.type`, measured 2026-09-07
    }
)

# Anthropic answers a spent self-set limit and a spent prepaid balance with 400 rather than
# 429, and DeepSeek answers a spent balance with 402, so a spent allowance is looked for on
# all three statuses. A 400 that matches no phrase and no code is still a bad request. 402 is
# outside RETRYABLE_STATUSES, so a body that matches nothing raises rather than retrying.
SPENT_STATUSES = frozenset({400, 402, 429})


@dataclass(frozen=True, slots=True)
class HttpResult:
    """A decoded response body, with the headers that came with it.

    ``headers`` are lower-cased. An adapter reads the ones its backend documents into
    ``ModelResponse`` fields and passes the rest through.

    ``held_back_ms`` is how long the request waited before the attempt that succeeded, which is
    retry backoff here. An adapter passes it to ``ModelResponse`` so a budget charges the run
    for working rather than for waiting.
    """

    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)
    held_back_ms: int = 0


@dataclass(frozen=True, slots=True)
class Retry:
    """How many times a request is retried, and how long between attempts.

    Applies to 408, 429, 500, 502, 503, 504 and 529, and to a connection that failed to open. A
    response carrying ``Retry-After`` waits for the interval it names instead of the backoff,
    up to ``max_backoff_s``, which caps the named interval as it caps the backoff::

        Retry(max_attempts=10)  # waits up to a minute more per extra attempt
        Retry(max_attempts=1)   # no retries

    Backoff doubles each attempt up to ``max_backoff_s``, so the defaults wait 1, 2, 4, 8 and
    16 seconds and the call blocks for 31 seconds before it raises. Retries happen inside one
    call, so the trajectory records one ``model_call`` whose duration includes every attempt,
    and under a compute cost basis the charge covers the whole duration.

    **A 429 whose message says the allowance does not reset inside a retry window is not
    retried at all.** It raises ``Suspend``, so the run writes its state and can be continued
    once the allowance is back (``docs/model-clients.md`` §4).

    ``spent_quota_phrases`` names more such wordings, for a backend whose phrasing the library
    has not met. They add to the ones it ships and are matched the same way, case-insensitively
    anywhere in the refusal's message::

        GeminiClient(model="gemini-3.1-flash-lite",
                     retry=Retry(spent_quota_phrases=("account balance is too low",)))

    ``spent_quota_codes`` does the same for a code named beside the message, matched whole.
    An endpoint whose codes are bare numbers is named here, since a number in the shipped set
    would collide with another endpoint's::

        OpenAIClient(model="glm-4.7-flash", base_url="https://api.z.ai/api/paas/v4",
                     retry=Retry(spent_quota_codes=("1113",)))
    """

    max_attempts: int = 6
    initial_backoff_s: float = 1.0
    max_backoff_s: float = 60.0
    spent_quota_phrases: tuple[str, ...] = ()
    spent_quota_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(
                f"Retry(max_attempts={self.max_attempts}) makes no request at all. Pass 1 for "
                f"a single attempt with no retries."
            )
        if isinstance(self.spent_quota_phrases, str):
            raise ValueError(
                f"Retry(spent_quota_phrases={self.spent_quota_phrases!r}) is one string, which "
                f"reads as a phrase per character, so every 429 carrying any of those letters "
                f"would stop the run.\n"
                f"Pass a sequence: spent_quota_phrases=({self.spent_quota_phrases!r},)."
            )
        if isinstance(self.spent_quota_codes, str):
            raise ValueError(
                f"Retry(spent_quota_codes={self.spent_quota_codes!r}) is one string, which "
                f"reads as a code per character, so a refusal naming any of those letters "
                f"would stop the run.\n"
                f"Pass a sequence: spent_quota_codes=({self.spent_quota_codes!r},)."
            )


@dataclass(slots=True)
class HTTPBackend:
    """A JSON endpoint an adapter posts to.

    ``base_url`` is the root the paths are relative to, and ``headers`` carries whatever
    authenticates the request::

        backend = HTTPBackend(
            base_url="https://api.mistral.ai/v1",
            headers={"Authorization": f"Bearer {key}"},
        )
        body = backend.post_json("/chat/completions", {"model": ..., "messages": [...]})

    Pass ``client`` to supply a preconfigured ``httpx.Client``, for a proxy, a custom
    transport, or a test that serves recorded responses. The backend then uses it as given and
    does not close it. ``headers`` are sent on every request either way, so a client supplied
    here authenticates without having to be built with the credentials itself.

    ``publishes_allowance`` says whether this backend reports a rate-limit allowance on a
    response. An adapter that sets ``ModelResponse.rate_limit`` to ``None`` on every call sets
    this ``False``, and a rate-limit refusal then advises fewer calls at once rather than a
    ``PacedClient``, which has nothing to read.
    """

    base_url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    timeout_s: float = 120.0
    retry: Retry = Retry()
    client: httpx.Client | None = None
    sleep: Callable[[float], None] = time.sleep
    publishes_allowance: bool = True

    def post_json(self, path: str, payload: Mapping[str, Any]) -> HttpResult:
        """POST ``payload`` as JSON and return the decoded body with the response headers.

        The headers are returned rather than read here: what a backend reports alongside a
        response is the adapter's to interpret and the caller's to use.

        Raises ``CallerFacingError`` for any status other than 2xx, for a connection that
        could not be made, and for a body that is not JSON.
        """
        client = self.client or httpx.Client(
            base_url=self.base_url, headers=dict(self.headers), timeout=self.timeout_s
        )
        owned = self.client is None
        try:
            return self._attempt(client, path, payload)
        finally:
            if owned:
                client.close()

    def post_stream(
        self, path: str, payload: Mapping[str, Any], on_event: Callable[[dict[str, Any]], None]
    ) -> HttpResult:
        """POST ``payload`` and hand each server-sent event to ``on_event`` as it arrives.

        Returns the final ``[DONE]`` marker's headers with an empty body: a streamed response
        has no single body, so what the caller assembles comes from the events::

            backend.post_stream("/chat/completions", {**payload, "stream": True}, on_event)

        **Retries cover the connection and the status, which arrive before any event.** Once
        an event has been delivered the request is not retried, because retrying would send an
        end user text they have already seen. A stream that breaks part-way raises, naming how
        many events had arrived.

        Raises ``CallerFacingError`` for the same statuses ``post_json`` does, with the same
        messages, since the failure happens before the stream begins.
        """
        client = self.client or httpx.Client(
            base_url=self.base_url, headers=dict(self.headers), timeout=self.timeout_s
        )
        owned = self.client is None
        try:
            return self._attempt_stream(client, path, payload, on_event)
        finally:
            if owned:
                client.close()

    def _attempt_stream(
        self,
        client: httpx.Client,
        path: str,
        payload: Mapping[str, Any],
        on_event: Callable[[dict[str, Any]], None],
    ) -> HttpResult:
        waited = 0.0
        for attempt in range(1, self.retry.max_attempts + 1):
            delivered = 0
            try:
                with client.stream(
                    "POST", path, json=dict(payload), headers=dict(self.headers)
                ) as response:
                    if response.status_code >= 300:
                        response.read()
                        self._stop_if_spent(response, path, waited)
                        if (
                            response.status_code in RETRYABLE_STATUSES
                            and attempt < self.retry.max_attempts
                        ):
                            waited += self._wait(attempt, response.headers.get("retry-after"))
                            continue
                        raise self._classify(response, path, attempt, waited)
                    for event in _sse_events(response.iter_lines()):
                        delivered += 1
                        on_event(event)
                    return HttpResult(
                        body={},
                        headers={k.lower(): v for k, v in response.headers.items()},
                        held_back_ms=int(waited * 1000),
                    )
            except httpx.RequestError as exc:
                if delivered:
                    raise CallerFacingError(
                        f"The stream from {self.base_url}{path} broke after {delivered} "
                        f"event(s): {type(exc).__name__}: {exc}\n"
                        f"It is not retried, because the pieces already delivered cannot be "
                        f"taken back and a second attempt would repeat them. The call made no "
                        f"complete response, so nothing was recorded for it."
                    ) from exc
                if attempt == self.retry.max_attempts:
                    raise self._unreachable(path, attempt, exc, waited) from exc
                waited += self._wait(attempt, None)

        raise CallerFacingError(  # unreachable while max_attempts >= 1, kept for the type
            f"{self.base_url}{path} could not be streamed on any attempt."
        )

    def _unreachable(
        self, path: str, attempts: int, exc: Exception, waited: float
    ) -> CallerFacingError:
        """The error for a connection that never opened, carrying what it waited between tries."""
        error = CallerFacingError(
            f"Could not reach {self.base_url}{path} after {attempts} attempt(s): "
            f"{type(exc).__name__}: {exc}\n"
            f"The run made no model call, so nothing was recorded for it. Check "
            f"that the address is right and the server is running."
        )
        note_held_back(error, int(waited * 1000))
        return error

    def scrape_metric(self, url: str, name: str) -> float | None:
        """One gauge from a Prometheus text endpoint, or ``None`` if it cannot be read.

        For a figure the backend publishes outside its API responses, such as how many
        requests a server has in flight::

            backend.scrape_metric("http://localhost:8000/metrics", "vllm:num_requests_running")

        A metric that is absent, an endpoint that is unreachable, and a body that is not
        Prometheus text all return ``None``. Nothing here raises: this is a figure a run is
        better off without than wrong about, and its absence is recorded rather than guessed.
        """
        client = self.client or httpx.Client(timeout=self.timeout_s)
        owned = self.client is None
        try:
            body = client.get(url).text
        except httpx.HTTPError:
            return None
        finally:
            if owned:
                client.close()
        return _gauge(body, name)

    def _attempt(self, client: httpx.Client, path: str, payload: Mapping[str, Any]) -> HttpResult:
        last_status: int | None = None
        last_body: str = ""
        waited = 0.0
        for attempt in range(1, self.retry.max_attempts + 1):
            try:
                response = client.post(path, json=dict(payload), headers=dict(self.headers))
            except httpx.RequestError as exc:
                if attempt == self.retry.max_attempts:
                    raise self._unreachable(path, attempt, exc, waited) from exc
                waited += self._wait(attempt, None)
                continue

            if response.status_code < 300:
                return replace(self._decode(response), held_back_ms=int(waited * 1000))

            last_status, last_body = response.status_code, response.text[:600]
            self._stop_if_spent(response, path, waited)
            if response.status_code in RETRYABLE_STATUSES and attempt < self.retry.max_attempts:
                waited += self._wait(attempt, response.headers.get("retry-after"))
                continue
            raise self._classify(response, path, attempt, waited)

        raise CallerFacingError(  # unreachable while max_attempts >= 1, kept for the type
            f"{self.base_url}{path} returned {last_status} on every attempt: {last_body}"
        )

    def _stop_if_spent(self, response: httpx.Response, path: str, waited: float) -> None:
        """Stop the run where this refusal says the allowance does not reset in a retry."""
        _stop_if_spent(
            response,
            f"{self.base_url}{path}",
            waited,
            self.retry.spent_quota_phrases,
            self.retry.spent_quota_codes,
        )

    def _decode(self, response: httpx.Response) -> HttpResult:
        try:
            body = response.json()
        except ValueError as exc:
            raise CallerFacingError(
                f"{response.request.url} returned {response.status_code} with a body that is "
                f"not JSON: {response.text[:300]!r}\n"
                f"A response that cannot be parsed cannot be recorded, so the run is invalid. "
                f"This is usually a proxy or a gateway answering in place of the backend."
            ) from exc
        if not isinstance(body, dict):
            raise CallerFacingError(
                f"{response.request.url} returned JSON that is not an object: {str(body)[:200]!r}"
            )
        return HttpResult(body=body, headers={k.lower(): v for k, v in response.headers.items()})

    def _wait(self, attempt: int, retry_after: str | None) -> float:
        """Sleep before the next attempt, and report how long it was.

        A ``Retry-After`` interval replaces the backoff: it is the backend stating when its
        window reopens, where the backoff is a guess made without one. Both forms RFC 9110
        allows are read, seconds and an HTTP-date. A header in neither form is ignored and the
        backoff stands.

        **``max_backoff_s`` caps it.** A budget is checked between steps and not inside a
        call, so a header naming an hour would hold one call for an hour with nothing able to
        interrupt it. A builder who wants to wait that long raises the cap.
        """
        backoff = min(self.retry.initial_backoff_s * (2 ** (attempt - 1)), self.retry.max_backoff_s)
        named = retry_after_seconds(retry_after)
        if named is not None:
            backoff = min(named, self.retry.max_backoff_s)
        self.sleep(backoff)
        return backoff

    def _classify(
        self, response: httpx.Response, path: str, attempts: int, waited: float = 0.0
    ) -> CallerFacingError:
        """The error for a response that will not be retried, carrying what it waited.

        The wait travels on the exception because a call that raised produced no
        ``ModelResponse`` to carry it, and the run was charged elapsed time for it either way.
        """
        error = self._error_for(response, path, attempts, waited)
        note_held_back(error, int(waited * 1000))
        return error

    def _error_for(
        self, response: httpx.Response, path: str, attempts: int, waited: float = 0.0
    ) -> CallerFacingError:
        status = response.status_code
        detail = _message_from(response)
        where = f"{self.base_url}{path}"

        if status in (401, 403) or _is_bad_credential(status, detail):
            return CallerFacingError(
                f"{where} rejected the credentials ({status}: {detail}).\n"
                f"Check that the key is set in the environment the run reads, that it is "
                f"current, and that it is a key for this backend."
            )
        if status == 404:
            return CallerFacingError(
                f"{where} has no such model or endpoint ({status}: {detail}).\n"
                f"Check the model identifier against the ids the backend serves, which "
                f"`GET {self.base_url}/models` lists."
            )
        if status in OVERFLOW_STATUSES and _is_context_overflow(detail):
            return ContextOverflow(
                f"{where} refused the request as longer than the model's context window "
                f"({status}: {detail}).\n"
                f"\n"
                f"What should happen instead is a build-time decision: give the node less, "
                f"fan out over it with over='documents', or pass context= a "
                f"context builder that shortens the list and reports what it dropped "
                f"(FT-17). "
                f"AppendAll(max_input_tokens=...) stops a run before it reaches the backend, "
                f"from the second call of a node onward."
            )
        if status == 422 or status == 400:
            return CallerFacingError(
                f"{where} refused the request ({status}: {detail}).\n"
                f"The request reached the backend and was rejected, so this is the request "
                f"rather than the connection. The message above names the parameter."
            )
        if status == 429:
            return CallerFacingError(
                f"{where} rate-limited the run and {attempts} attempt(s) did not clear it "
                f"({status}: {detail}).\n"
                f"Those attempts waited {waited:.0f}s in total and the window had not reset. "
                f"{_pacing_advice(self.publishes_allowance)}"
            )
        return CallerFacingError(
            f"{where} returned {status} after {attempts} attempt(s): {detail}\n"
            f"The run made no usable model call. A 5xx that persists is a backend outage "
            f"rather than a fault in the request."
        )


def _pacing_advice(publishes_allowance: bool) -> str:
    """What to do about a rate limit, which depends on whether there is an allowance to read."""
    if publishes_allowance:
        return (
            "Pace the calls against the backend's published allowance: PacedClient(client) "
            "waits once for every caller sharing it. Raising Retry(max_attempts=...) waits "
            "longer inside this one call instead."
        )
    return (
        "This backend publishes no allowance on a response, so a PacedClient in front of it "
        "has nothing to read. Make fewer calls at once with EvalSuite.run(concurrency=...) or "
        "Pipeline.run(concurrency=...), or wait longer inside one call with "
        "Retry(max_attempts=...)."
    )


def _sse_events(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """The JSON payloads of a server-sent event stream, in order.

    Both backends send ``data: {...}`` lines terminated by ``data: [DONE]``. Blank lines and
    comment lines are separators and carry nothing. A ``data:`` line that is not JSON is
    skipped rather than raising: the stream is still arriving, and one unreadable frame is not
    a reason to discard the pieces that follow it.
    """
    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if payload == "[DONE]":
            return
        try:
            event = json.loads(payload)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def _stop_if_spent(
    response: httpx.Response,
    where: str,
    waited: float,
    declared: Sequence[str] = (),
    declared_codes: Sequence[str] = (),
) -> None:
    """Stop the run where a refusal says its allowance does not reset inside a retry window."""
    if response.status_code in SPENT_STATUSES and _is_spent_quota(
        _message_from(response), declared, _codes_from(response), declared_codes
    ):
        raise _spent_quota(response, where, waited)


def _spent_quota(response: httpx.Response, where: str, waited: float) -> Suspend:
    """The stop for a 429 whose allowance does not reset inside a retry window.

    A ``Suspend`` rather than an error: the allowance comes back, and a run that wrote its
    state can be continued when it does rather than starting again and re-paying for the work
    it had already done. ``resume_not_before`` is unset because the backend said the allowance
    was spent and did not say when it returns, and a guessed date would refuse a resume that
    would have worked.
    """
    stop = Suspend(
        waiting_for=(
            f"{where} refused the call against a spent allowance "
            f"({response.status_code}: {_message_from(response)}). Retrying does not clear "
            f"it, so the run stopped instead of waiting. Continue it with Pipeline.resume "
            f"once the allowance is back."
        ),
    )
    # `note_held_back` takes a BaseException, so a stop that followed some retries reports what
    # those retries waited the way a raised error does.
    note_held_back(stop, int(waited * 1000))
    return stop


def _is_spent_quota(
    detail: str,
    declared: Sequence[str] = (),
    codes: Sequence[str] = (),
    declared_codes: Sequence[str] = (),
) -> bool:
    """Whether a refusal says its allowance resets on a scale retries cannot reach.

    ``declared`` is what the caller's ``Retry`` names, which adds to the shipped phrases, and
    ``declared_codes`` the same for codes. ``codes`` is what the body carried, where the
    backend names any.
    """
    if any(code in QUOTA_CODES or code in declared_codes for code in codes):
        return True
    lowered = detail.lower()
    return any(phrase.lower() in lowered for phrase in (*QUOTA_PHRASES, *declared))


def retry_after_seconds(value: str | None, now: float | None = None) -> float | None:
    """How long a ``Retry-After`` header asks for, in seconds, or ``None`` for no reading.

    RFC 9110 allows two forms, and both are read::

        retry_after_seconds("30")                              # 30.0
        retry_after_seconds("Wed, 13 Aug 2026 07:28:00 GMT")   # seconds until that instant

    ``now`` is the epoch seconds the date form is measured against, defaulting to the clock.
    A date already past reads as ``0.0``, and a header in neither form returns ``None``.
    """
    if not value:
        return None
    text = value.strip()
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, moment.timestamp() - (time.time() if now is None else now))


def _is_context_overflow(detail: str) -> bool:
    """Whether a refusal is the backend saying the request does not fit its window."""
    lowered = detail.lower()
    return any(phrase in lowered for phrase in OVERFLOW_PHRASES)


def _is_bad_credential(status: int, detail: str) -> bool:
    """Whether a 400 is the backend saying the key is wrong rather than the request."""
    lowered = detail.lower()
    return status == 400 and any(phrase in lowered for phrase in CREDENTIAL_PHRASES)


def _message_from(response: httpx.Response) -> str:
    """The most useful text in an error body, across the shapes the backends return.

    Mistral answers a bad request with ``{"message": ...}`` and an unauthorized one with
    ``{"detail": ...}``. vLLM answers with ``{"error": {"message": ...}}``. A body in none of
    those shapes is returned as text.
    """
    try:
        body = response.json()
    except ValueError:
        return response.text[:300].strip() or "no body"
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        for key in ("message", "detail", "error"):
            if body.get(key):
                return str(body[key])
    return str(body)[:300]


def _codes_from(response: httpx.Response) -> tuple[str, ...]:
    """Every error code an error body names, in the places the backends put one.

    OpenAI carries it as ``error.code``, Anthropic as ``error.details.error_code``, and Kimi
    as ``error.type``. All three are read rather than the first one found, since a backend
    that fills two puts the discriminating one in either: Kimi's spent allowance is a
    ``type`` beside no ``code``, and DeepSeek's is a ``code`` that says only that the request
    was rejected. Measured 2026-09-07.
    """
    try:
        body = response.json()
    except ValueError:
        return ()
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return ()
    found = []
    for value in (error.get("code"), error.get("type")):
        if isinstance(value, str) and value:
            found.append(value)
    details = error.get("details")
    if isinstance(details, dict) and isinstance(details.get("error_code"), str):
        found.append(details["error_code"])
    return tuple(found)


def _gauge(body: str, name: str) -> float | None:
    """The value of one gauge in Prometheus text format, ignoring its labels."""
    pattern = re.compile(rf"^{re.escape(name)}(?:\{{[^}}]*\}})?\s+([0-9.eE+-]+)\s*$", re.MULTILINE)
    found = pattern.search(body)
    if found is None:
        return None
    try:
        return float(found.group(1))
    except ValueError:
        return None
