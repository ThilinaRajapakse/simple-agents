"""A model client that waits when the backend says its window is nearly spent.

A per-minute quota is not what retries are for. Backoff doubles from a fraction of a second, so
clearing a one-minute window takes more attempts than any sane limit allows, and a 429 from a
quota means the caller is going too fast rather than that something failed. The fix is to pace
the calls, and the figure to pace against is on every response.

This sits in front of an adapter rather than inside it, so nothing about the seam changes and
the two compose::

    client = PacedClient(MistralClient(model="mistral-small-2603"))
    results = suite.run(envelope=env, model=client, split="held_out", k=5)

A backend that publishes no allowance leaves this a passthrough: there is nothing to pace
against, and inventing a rate would be a claim about a limit nobody stated.
"""

from __future__ import annotations

import dataclasses
import threading
import time
import warnings
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from .context import accepts_reasoning_sink
from .errors import ConfigurationError, SimpleAgentsWarning
from .models import (
    ModelClient,
    ModelIdentity,
    ModelRequest,
    ModelResponse,
    note_held_back,
)

__all__ = ["PacedClient", "warn_unpaced_wait"]

# A published window is per minute on every shipped backend that publishes one, so waiting
# longer than one is waiting for something that has already happened.
DEFAULT_MAX_WAIT_S = 65.0

ALLOWANCE_STOPPED = (
    "This backend published a rate-limit allowance and has stopped, so PacedClient has "
    "nothing to pace the calls that stopped it against and they go straight through. Mistral "
    "does this on a streamed response, which carries none of the x-ratelimit headers a "
    "non-streamed one carries. Drop stream=True from the node, or pace those calls some other "
    "way."
)


class PacedClient:
    """Wraps a model client and holds calls back when the published allowance runs low.

    After each call it reads ``ModelResponse.rate_limit``, and before the next one it waits if
    the window will not hold it. Every caller sharing the client waits for the same instant, so
    parallel rollouts pause once rather than once each::

        client = PacedClient(MistralClient(model="mistral-small-2603"))
        client.identity()            # the wrapped adapter's, unchanged

    ``min_remaining_requests`` is the request count at or below which the next call waits.
    Left unset it is the number of callers sharing the client, which :meth:`expect_callers`
    sets and ``EvalSuite.run`` sets from its concurrency: a window with one request left is a
    window that four rollouts in flight will overrun, and the calls that overrun it come back
    rate limited. ``min_remaining_tokens`` is the same for tokens; left unset it is the largest
    number of tokens any single call has used so far, so the floor grows to fit the work rather
    than being guessed at.

    ``stream`` is delegated the same way, and exists only where the wrapped client has one, so
    pacing an adapter that cannot stream leaves it unable to. Its reasoning sink is delegated
    on the same rule: the wrapper takes one where the wrapped client does.
    """

    def __init__(
        self,
        inner: ModelClient,
        *,
        min_remaining_requests: int | None = None,
        min_remaining_tokens: int | None = None,
        max_wait_s: float = DEFAULT_MAX_WAIT_S,
    ) -> None:
        if not (hasattr(inner, "complete") and hasattr(inner, "identity")):
            raise ConfigurationError(
                f"PacedClient was given {type(inner).__name__}, which is not a model client. "
                f"It wraps one: PacedClient(MistralClient(model='mistral-small-2603')). A "
                f"model client has complete() and identity()."
            )
        if max_wait_s <= 0:
            raise ConfigurationError(
                f"PacedClient(max_wait_s={max_wait_s}) has to be positive. It caps how long "
                f"one wait lasts; a published window is per minute, so the default of "
                f"{DEFAULT_MAX_WAIT_S} covers one."
            )
        self.inner = inner
        self.min_remaining_requests = min_remaining_requests
        self.min_remaining_tokens = min_remaining_tokens
        self.max_wait_s = max_wait_s
        self._callers = 1

        if hasattr(inner, "stream"):
            self.stream = (
                self._stream_with_reasoning if accepts_reasoning_sink(inner) else self._stream
            )

        self._lock = threading.Lock()
        self._resume_at = 0.0
        self._largest_call = 0
        self._seen_allowance = False
        self._warned = False
        self.waits = 0
        """How many calls were held back. Zero means the allowance was never close.

        One call counts once however many windows it waited through, so this is the number to
        size a run's pacing against rather than a count of sleeps.
        """

    def identity(self) -> ModelIdentity:
        """The wrapped adapter's identity, unchanged.

        Pacing does not change which model is called, so the manifest pin and the cassette key
        are the adapter's.
        """
        return self.inner.identity()

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Wait if the window will not hold this call, then make it."""
        waited = self._wait()
        with _waiting_reported(waited):
            response = self.inner.complete(request)
        self._observe(response)
        return _held_back(response, waited)

    def _stream(self, request: ModelRequest, on_chunk: Callable[[str], None]) -> ModelResponse:
        """The same wait, then the wrapped client's stream.

        Bound to ``stream`` in ``__init__`` only where the wrapped client has one. Defining it
        on the class would make every ``PacedClient`` answer ``hasattr(client, "stream")``
        with true, and wrapping an adapter that cannot stream would turn a refusal before the
        run into an ``AttributeError`` during it.
        """
        waited = self._wait()
        with _waiting_reported(waited):
            response = self.inner.stream(request, on_chunk)  # type: ignore[attr-defined]
        self._observe(response)
        return _held_back(response, waited)

    def _stream_with_reasoning(
        self,
        request: ModelRequest,
        on_chunk: Callable[[str], None],
        *,
        on_reasoning: Callable[[str], None] | None = None,
    ) -> ModelResponse:
        """The variant bound where the wrapped client takes a reasoning sink.

        The capability is read off the wrapped client's signature and republished on this one,
        so a wrapper never claims more than what it stands in front of and never claims less.
        """
        waited = self._wait()
        with _waiting_reported(waited):
            response = self.inner.stream(  # type: ignore[attr-defined]
                request, on_chunk, on_reasoning=on_reasoning
            )
        self._observe(response)
        return _held_back(response, waited)

    def _wait(self) -> float:
        """Hold the call back until the window reopens, and report how long that took."""
        started = time.monotonic()
        counted = False
        while True:
            with self._lock:
                remaining = self._resume_at - time.monotonic()
                if remaining <= 0:
                    return time.monotonic() - started
                if not counted:
                    self.waits += 1
                    counted = True
            time.sleep(min(remaining, self.max_wait_s))

    def _observe(self, response: ModelResponse) -> None:
        """Note what the backend said is left, and set the instant the next call may go."""
        left = getattr(response, "rate_limit", None)
        with self._lock:
            self._largest_call = max(self._largest_call, _tokens_used(response))
            if left is None:
                if self._seen_allowance:
                    self._warn_allowance_gone()
                return
            self._seen_allowance = True
            if not self._is_low(left):
                return
            wait = left.resets_in_s if left.resets_in_s is not None else self.max_wait_s
            self._resume_at = max(
                self._resume_at, time.monotonic() + min(float(wait), self.max_wait_s)
            )

    def _warn_allowance_gone(self) -> None:
        """Say once that the allowance this client paces against has stopped arriving.

        Measured against Mistral on 2026-08-04: a non-streamed response carries five
        ``x-ratelimit-*`` headers and a streamed one carries none, so a node declaring
        ``stream=True`` gives this client nothing to pace against. A backend that never
        publishes an allowance is a passthrough and says nothing, because there is nothing to
        report; one that published and then stopped is a control that has quietly gone dead.
        """
        if self._warned:
            return
        self._warned = True
        warnings.warn(ALLOWANCE_STOPPED, SimpleAgentsWarning, stacklevel=4)

    @property
    def request_floor(self) -> int:
        """The remaining-request count at or below which the next call waits.

        ``min_remaining_requests`` where it was given, and otherwise the number of callers
        sharing this client, which :meth:`expect_callers` sets.
        """
        if self.min_remaining_requests is not None:
            return self.min_remaining_requests
        return self._callers

    def expect_callers(self, callers: int) -> None:
        """Say how many callers share this client, which sets the floor when it was not given.

        A window reporting one request left is a window that four rollouts in flight will
        overrun, and the calls that overrun it are rate limited::

            client = PacedClient(MistralClient(model="mistral-small-2603"))
            client.expect_callers(4)
            client.request_floor         # 4

        ``EvalSuite.run`` calls this with its concurrency, so an evaluation paces for the
        rollouts it is running. A ``min_remaining_requests`` given to the constructor is the
        caller's decision and is not overridden.
        """
        self._callers = max(1, int(callers))

    def _is_low(self, left: Any) -> bool:
        requests = left.remaining_requests
        if requests is not None and requests <= self.request_floor:
            return True
        tokens = left.remaining_tokens
        floor = (
            self.min_remaining_tokens
            if self.min_remaining_tokens is not None
            else self._largest_call
        )
        return tokens is not None and tokens <= floor


def _tokens_used(response: ModelResponse) -> int:
    """One call's total, counting only what the backend measured."""
    tokens = getattr(response, "tokens", None)
    return int(getattr(tokens, "total", 0) or 0)


@contextmanager
def _waiting_reported(waited_s: float) -> Iterator[None]:
    """Put this client's wait on whatever the wrapped call raises, then let it through.

    A call that answered carries the wait on its response. One that failed carries it on the
    exception instead, so a run held behind a quota and then ended by it still reports the
    time it spent waiting rather than reporting none.
    """
    try:
        yield
    except Exception as exc:
        note_held_back(exc, int(waited_s * 1000))
        raise


def _held_back(response: ModelResponse, waited_s: float) -> ModelResponse:
    """Add this client's wait to whatever the adapter already reported waiting.

    Reported rather than subtracted: the wait is elapsed time and a run's ``max_wall_clock``
    budget is charged for it, so an evaluation behind a per-minute quota can stop on that axis
    having made few calls. Summing this across the run is what says so.
    """
    if waited_s <= 0:
        return response
    return dataclasses.replace(response, held_back_ms=response.held_back_ms + int(waited_s * 1000))


def warn_unpaced_wait(model: ModelClient, response: ModelResponse) -> None:
    """Warn the first time a run waits on a hosted backend through a client that does not pace.

    Called once per run, on the first call that comes back having been held back. Retry backoff
    means the backend answered with a rate-limit error, and a rate-limited call reports no token
    counts, so enough of them leave a run's cost unknown. The waiting is elapsed time, so
    ``max_wall_clock_ms`` is charged for it.

    **What the warning tells the builder to do depends on the response.** A backend that
    published an allowance can be paced against it, and one that published none cannot: wrapping
    it changes nothing, so the remedy there is to send less at once.

    Silent on a `PacedClient`, on a self-hosted backend, and on a replay, none of which is
    waiting on someone else's quota.
    """
    if isinstance(model, PacedClient) or getattr(response, "replayed", False):
        return
    if getattr(response, "backend", None) != "hosted_api":
        return
    if getattr(response, "rate_limit", None) is None:
        remedy = (
            "This backend published no allowance on the response, so there is nothing to pace "
            "against and PacedClient would leave the calls exactly as they are. What bounds "
            "the rate here is how much the run sends at once: lower concurrency= on "
            "Pipeline.run, or concurrent_items= on the node that fans out."
        )
    else:
        remedy = (
            f"Wrap the adapter: model=PacedClient({type(model).__name__}(...)). It reads the "
            f"allowance off each response and holds the next call back before the backend "
            f"refuses it."
        )
    warnings.warn(
        f"A model call waited {response.held_back_ms} ms before the attempt that answered, "
        f"against a hosted backend through a client that does not pace. That wait is retry "
        f"backoff after the backend refused the call, retries do not clear a per-minute quota, "
        f"and a rate-limited call reports no token counts, so enough of them leave the run's "
        f"cost unknown. The waiting is elapsed time, so max_wall_clock_ms is charged for it and "
        f"a run held behind a quota can stop on that axis having done little work.\n"
        f"{remedy} The run total is `totals.held_back_ms` in the manifest.\n"
        f"This warning fires once per run.",
        SimpleAgentsWarning,
        stacklevel=4,
    )
