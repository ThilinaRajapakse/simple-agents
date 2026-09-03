"""Holding calls back when the backend says its window is nearly spent.

Both item 7 checkpoint sessions wrote this by hand and both estimated the remaining allowance
from an average of previous calls, over a per-question spend ranging from 4,700 to 122,000
tokens, while the exact figure was on every response.
"""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
import warnings
from dataclasses import replace

import pytest

from pydantic import BaseModel

from simple_agents import (
    Prompt,
    Budget,
    CallerFacingError,
    ConfigurationError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Maybe,
    ModelIdentity,
    ModelRequest,
    PacedClient,
    Pipeline,
    RunEnvelope,
)
from simple_agents.adapters.embeddings_local import SentenceTransformerEmbeddings
from simple_agents.builtins import DocumentIndex, document_search
from simple_agents.builtins.ranking import Semantic
from simple_agents.errors import SimpleAgentsWarning
from simple_agents.pacing import _held_back, warn_unpaced_wait
from simple_agents.models import (
    RateLimit,
    TokenUsage,
    fake_response,
    held_back_ms_of,
    note_held_back,
)

from conftest import run_path


ANSWER = '{"answer": "yes"}'


class _Answer(BaseModel):
    answer: Maybe[str]


def _pipeline() -> Pipeline:
    """Two model calls, so a once-per-run warning can be told from a once-per-call one."""
    return Pipeline(
        [
            LLMNode(lambda i, c: Prompt.user("ask"), output_schema=_Answer, node_id="first"),
            LLMNode(lambda i, c: Prompt.user("ask again"), output_schema=_Answer, node_id="second"),
        ],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None),
    )


IDENTITY = ModelIdentity(
    backend="hosted_api", request_model="mistral-small-2603", model_revision=None
)


class Backend:
    """A client that reports whatever allowance the test scripts, in order."""

    def __init__(self, allowances: list[RateLimit | None], tokens: int = 100) -> None:
        self.allowances = list(allowances)
        self.tokens = tokens
        self.calls = 0

    def identity(self) -> ModelIdentity:
        return IDENTITY

    def complete(self, request: ModelRequest) -> object:
        self.calls += 1
        response = fake_response(
            content="ok",
            tokens=TokenUsage(
                input_uncached=self.tokens,
                input_cache_read=0,
                input_cache_write=0,
                cache_ttl=None,
                output=0,
            ),
        )
        response.rate_limit = (
            self.allowances.pop(0) if self.allowances else RateLimit(remaining_requests=50)
        )
        return response


def request() -> ModelRequest:
    return ModelRequest(messages=[{"role": "user", "content": "how long?"}])


@pytest.fixture
def slept(monkeypatch) -> list[float]:
    """Every sleep the pacer asks for, without the test waiting for any of them."""
    recorded: list[float] = []
    clock = {"now": 0.0}

    def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr("simple_agents.pacing.time.sleep", fake_sleep)
    monkeypatch.setattr("simple_agents.pacing.time.monotonic", lambda: clock["now"])
    return recorded


# -- the seam -----------------------------------------------------------------------------


def test_identity_passes_straight_through(slept) -> None:
    """Pacing does not change which model is called, so the pin and the key are the adapter's."""
    client = PacedClient(Backend([]))

    assert client.identity() == IDENTITY


def test_a_backend_that_publishes_no_allowance_is_never_paced(slept) -> None:
    backend = Backend([None, None, None])
    client = PacedClient(backend)

    for _ in range(3):
        client.complete(request())

    assert slept == []
    assert client.waits == 0
    assert backend.calls == 3


class _Declaring:
    """An adapter shaped like the shipped ones, saying what its backend publishes."""

    def __init__(self, publishes: bool) -> None:
        self._backend = SimpleNamespace(publishes_allowance=publishes)
        self.inner = Backend([None])

    def identity(self):
        return self.inner.identity()

    def complete(self, req):
        return self.inner.complete(req)


def test_an_adapter_declaring_no_allowance_says_so_when_it_is_wrapped(slept) -> None:
    """Read off the adapter rather than a response, and before the first call: a response
    carrying no allowance says only that this call carried none."""
    with pytest.warns(SimpleAgentsWarning) as raised:
        PacedClient(_Declaring(publishes=False))

    assert len(raised) == 1
    assert "concurrency=" in str(raised[0].message)


def test_an_adapter_that_publishes_one_is_wrapped_in_silence(slept) -> None:
    """Mistral publishes an allowance and carries none on a streamed response, so inferring
    from the first response would have called it a backend that publishes nothing."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", SimpleAgentsWarning)
        PacedClient(_Declaring(publishes=True))
        PacedClient(Backend([None]))


def test_a_backend_that_published_and_stopped_still_says_so(slept) -> None:
    """The stopped-publishing warning is the one a streamed Mistral call needs, and nothing
    said earlier suppresses it."""
    client = PacedClient(Backend([RateLimit(remaining_requests=40, remaining_tokens=40_000), None]))

    client.complete(request())
    with pytest.warns(SimpleAgentsWarning, match="published a rate-limit allowance"):
        client.complete(request())


def test_something_that_is_not_a_model_client_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        PacedClient(object())

    assert "complete() and identity()" in str(raised.value)


def test_a_non_positive_wait_cap_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        PacedClient(Backend([]), max_wait_s=0)

    assert "positive" in str(raised.value)


# -- what a budget is charged --------------------------------------------------------------


def test_the_wait_is_reported_so_a_budget_is_not_charged_for_it(slept) -> None:
    """Measured on dogfood #1: 8 of 145 rollouts died on a 60s budget behind a 65s wait."""
    backend = Backend(
        [RateLimit(remaining_requests=0, resets_in_s=30.0), RateLimit(remaining_requests=49)]
    )
    client = PacedClient(backend)

    first = client.complete(request())
    second = client.complete(request())

    assert first.held_back_ms == 0
    assert second.held_back_ms == 30_000


def test_a_call_that_never_waited_reports_nothing_held_back(slept) -> None:
    client = PacedClient(Backend([RateLimit(remaining_requests=48, remaining_tokens=44_000)]))

    assert client.complete(request()).held_back_ms == 0


# -- pacing on what the backend published -------------------------------------------------


def test_a_low_request_allowance_holds_the_next_call_back(slept) -> None:
    backend = Backend(
        [RateLimit(remaining_requests=0, resets_in_s=30.0), RateLimit(remaining_requests=49)]
    )
    client = PacedClient(backend)

    client.complete(request())
    assert slept == []

    client.complete(request())

    assert slept == [30.0]
    assert client.waits == 1
    assert backend.calls == 2


def test_one_call_held_through_two_windows_counts_as_one_wait(monkeypatch) -> None:
    """`waits` is the number of calls held back, which is what a project sizes pacing on.

    Another caller's response can move the window while this call is asleep, which sends the
    loop round a second time. Counting the sleeps reports twice the calls that waited.
    """
    clock = {"now": 0.0}
    slept: list[float] = []
    client = PacedClient(Backend([]), max_wait_s=10.0)

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        clock["now"] += seconds
        if len(slept) == 1:
            client._resume_at = clock["now"] + 5.0

    monkeypatch.setattr("simple_agents.pacing.time.sleep", fake_sleep)
    monkeypatch.setattr("simple_agents.pacing.time.monotonic", lambda: clock["now"])
    client._resume_at = 8.0

    response = client.complete(request())

    assert slept == [8.0, 5.0]
    assert client.waits == 1
    assert response.held_back_ms == 13_000


def test_a_wait_before_a_call_that_failed_travels_on_the_exception(slept) -> None:
    """A run held behind a quota and then ended by it still reports what it waited."""

    class Refuses(Backend):
        def complete(self, request: ModelRequest) -> object:
            raise CallerFacingError("the backend rate-limited the run")

    backend = Refuses([])
    client = PacedClient(backend)
    client._resume_at = 30.0

    with pytest.raises(CallerFacingError) as raised:
        client.complete(request())

    assert slept == [30.0]
    assert held_back_ms_of(raised.value) == 30_000


def test_the_request_floor_is_the_number_of_callers_sharing_the_client(slept) -> None:
    """A window with three requests left will not carry four rollouts in flight."""
    backend = Backend(
        [RateLimit(remaining_requests=3, resets_in_s=30.0), RateLimit(remaining_requests=50)]
    )
    client = PacedClient(backend)
    client.expect_callers(4)

    client.complete(request())
    client.complete(request())

    assert client.request_floor == 4
    assert slept == [30.0]


def test_an_explicit_request_floor_is_not_replaced_by_the_caller_count(slept) -> None:
    client = PacedClient(Backend([RateLimit(remaining_requests=3)]), min_remaining_requests=1)
    client.expect_callers(4)

    assert client.request_floor == 1

    client.complete(request())
    client.complete(request())

    assert slept == []


def test_a_healthy_allowance_never_waits(slept) -> None:
    backend = Backend([RateLimit(remaining_requests=48, remaining_tokens=44_000)] * 3)
    client = PacedClient(backend)

    for _ in range(3):
        client.complete(request())

    assert slept == []


def test_the_token_floor_grows_to_the_largest_call_seen(slept) -> None:
    """Left unset, the floor is what a call of the biggest size so far would need."""
    backend = Backend(
        [
            RateLimit(remaining_tokens=40_000, resets_in_s=20.0),
            RateLimit(remaining_tokens=900, resets_in_s=20.0),
            RateLimit(remaining_tokens=40_000),
        ],
        tokens=1_000,
    )
    client = PacedClient(backend)

    client.complete(request())  # 40,000 left against a 1,000-token floor: fine
    client.complete(request())  # 900 left, below the floor: the next call waits
    assert slept == []

    client.complete(request())

    assert slept == [20.0]


def test_an_explicit_token_floor_replaces_the_measured_one(slept) -> None:
    backend = Backend(
        [RateLimit(remaining_tokens=5_000, resets_in_s=10.0), RateLimit(remaining_tokens=50_000)],
        tokens=100,
    )
    client = PacedClient(backend, min_remaining_tokens=10_000)

    client.complete(request())
    client.complete(request())

    assert slept == [10.0]


def test_a_backend_that_names_no_reset_waits_the_cap(slept) -> None:
    backend = Backend([RateLimit(remaining_requests=0), RateLimit(remaining_requests=50)])
    client = PacedClient(backend, max_wait_s=45.0)

    client.complete(request())
    client.complete(request())

    assert slept == [45.0]


def test_a_reset_longer_than_the_cap_is_capped(slept) -> None:
    backend = Backend(
        [RateLimit(remaining_requests=0, resets_in_s=3_600.0), RateLimit(remaining_requests=50)]
    )
    client = PacedClient(backend, max_wait_s=65.0)

    client.complete(request())
    client.complete(request())

    assert slept == [65.0]


# -- shared across rollouts ---------------------------------------------------------------


def test_parallel_callers_wait_for_one_instant_rather_than_one_each(slept) -> None:
    """Eight rollouts sharing a client pause until the window turns, not eight windows."""
    backend = Backend(
        [RateLimit(remaining_requests=0, resets_in_s=30.0)]
        + [RateLimit(remaining_requests=50)] * 16
    )
    client = PacedClient(backend)
    client.complete(request())

    barrier = threading.Barrier(8)

    def call() -> None:
        barrier.wait()
        client.complete(request())

    threads = [threading.Thread(target=call) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(slept) <= 30.0
    assert backend.calls == 9


# -- warning a run that waits through a client that does not pace --------------------------


def _hosted(waited_ms: int):
    """A response as a hosted backend would return it, after waiting `waited_ms` to be served."""
    response = fake_response(content=ANSWER)
    response.backend = "hosted_api"
    response.held_back_ms = waited_ms
    return response


def test_a_hosted_run_that_waits_through_an_unpaced_client_warns(tmp_path) -> None:
    """Dogfood #2 spent 47% of its wall clock on retry backoff and nothing said so."""
    with pytest.warns(SimpleAgentsWarning, match="does not pace"):
        _pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=FakeModelClient(responses=[_hosted(3000), _hosted(7000)]),
        )


def test_it_warns_once_per_run_rather_than_once_per_call(tmp_path) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=FakeModelClient(responses=[_hosted(3000), _hosted(7000)]),
        )

    paced = [w for w in caught if "does not pace" in str(w.message)]
    assert len(paced) == 1


def test_a_run_that_never_waited_is_quiet(tmp_path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=FakeModelClient(responses=[_hosted(0), _hosted(0)]),
        )


def test_a_self_hosted_backend_is_quiet_because_the_quota_is_the_builders(tmp_path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=FakeModelClient(
                responses=[fake_response(content=ANSWER), fake_response(content=ANSWER)]
            ),
        )


class TestTheRemedyMatchesTheBackend:
    """A backend that published no allowance cannot be paced, so the warning cannot say to."""

    def _response(self, *, allowance):
        return replace(
            fake_response(content="ok"),
            backend="hosted_api",
            held_back_ms=31_000,
            rate_limit=(
                RateLimit(remaining_requests=1, remaining_tokens=100, resets_in_s=30)
                if allowance
                else None
            ),
        )

    def test_an_allowance_on_the_response_names_the_pacing_client(self) -> None:
        with pytest.warns(SimpleAgentsWarning) as caught:
            warn_unpaced_wait(FakeModelClient(), self._response(allowance=True))

        assert "PacedClient" in str(caught[0].message)

    def test_no_allowance_names_the_concurrency_instead(self) -> None:
        """Measured against Gemini on the free tier: the wrapper paced nothing, `waits=0`,
        because the backend publishes no allowance to pace against."""
        with pytest.warns(SimpleAgentsWarning) as caught:
            warn_unpaced_wait(FakeModelClient(), self._response(allowance=False))

        message = str(caught[0].message)
        assert "concurrency=" in message
        assert "concurrent_items=" in message
        assert "PacedClient would leave the calls exactly as they are" in message


# -- the wait reaching the run total -------------------------------------------------------


class _HeldBackEmbeddings:
    """A real embedding backend reporting a wait, the way a `PacedClient` in front of a hosted
    one does. `_held_back` is the function that client uses."""

    def __init__(self, waited_ms: int) -> None:
        self.inner = SentenceTransformerEmbeddings()
        self.waited_s = waited_ms / 1000

    def identity(self) -> ModelIdentity:
        return self.inner.identity()

    def embed(self, request):
        return _held_back(self.inner.embed(request), self.waited_s)


class TestTheWaitReachesTheRunTotal:
    """`held_back_ms` on a record is what `totals.held_back_ms` sums. Both paths that set it
    on a record were leaving it out of the total."""

    def _totals(self, tmp_path, run_id):
        return json.loads(run_path(tmp_path, run_id, "manifest.json").read_text())["totals"][
            "held_back_ms"
        ]

    def _records(self, tmp_path, run_id):
        return [
            json.loads(line)
            for line in run_path(tmp_path, run_id, "trajectory.jsonl").read_text().splitlines()
            if json.loads(line)["record_type"] == "model_call"
        ]

    def test_a_call_that_exhausted_its_retries_reports_what_it_waited(self, tmp_path):
        """Measured at 7000 behind a server answering 429, where the total read 0: a run a
        rate limit ended is the run whose wall clock most needs explaining."""

        class Exhausted:
            def identity(self):
                return IDENTITY

            def complete(self, request):
                error = CallerFacingError("rate limited after 4 attempts")
                note_held_back(error, 7000)
                raise error

        with pytest.raises(CallerFacingError):
            _pipeline().run(
                {},
                envelope=RunEnvelope(run_dir=str(tmp_path)),
                model=Exhausted(),
                run_id="failed",
            )

        assert [r["held_back_ms"] for r in self._records(tmp_path, "failed")] == [7000]
        assert self._totals(tmp_path, "failed") == 7000

    def test_an_embedding_call_that_waited_reports_it_too(self, tmp_path):
        """The retrieval path set `held_back_ms` on the record and never added it to the
        total, so a completed run under-reported what it spent waiting."""
        index = DocumentIndex.from_texts(
            {"d0": "The depot at Ashford closes at six."},
            embeddings=_HeldBackEmbeddings(1500),
            ranking=Semantic(),
        )

        def search_twice(inputs, ctx):
            for query in ["when does the depot shut", "and at the weekend"]:
                ctx.call_tool("document_search", query=query)
            return "done"

        Pipeline(
            [
                Deterministic(
                    search_twice,
                    node_id="find",
                    tools=[document_search(index, top_k=1)],
                )
            ],
            budget=Budget.unbounded(),
        ).run({}, envelope=RunEnvelope(run_dir=str(tmp_path)), run_id="embedded")

        records = self._records(tmp_path, "embedded")
        assert [r["held_back_ms"] for r in records] == [1500, 1500]
        assert self._totals(tmp_path, "embedded") == 3000
