"""The model client seam.

One interface, one adapter per backend. Callers use the same interface regardless of
backend, and each adapter translates to its backend's wire format. ``ModelClient`` is a
Protocol, so an adapter for an unsupported backend can be supplied without modifying the
library.

The common surface is limited to what the library reads:

* **Common.** The call signature, the model identity, the five-field token breakdown,
  backend, requested model, revision, serving model, finish reason, concurrency, content and
  tool calls. These appear in every trajectory record, and the conformance checks for model
  pinning and cost auditability read them from there.
* **Passed through.** Backend-specific request parameters reach the adapter unchanged rather
  than being translated. Fixed settings
  belong in an adapter's constructor. Per-call parameters travel in ``extra``, which the
  library does not inspect and passes to the backend unchanged.
* **Not emulated.** A backend that lacks a capability raises a caller-facing error naming the
  backend and the feature. The library does not substitute an implementation.

An adapter implements ``complete`` and ``identity``, populates every field of
``ModelResponse`` from what the backend reported, and takes backend-specific configuration in
its constructor. A field reported without measurement, such as a zero token count or an
assumed concurrency, corrupts every figure later derived from the trajectory.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping, Protocol

from .errors import CallerFacingError
from .schema import Unknown

__all__ = [
    "Backend",
    "ModelIdentity",
    "TokenUsage",
    "RateLimit",
    "Reasoning",
    "ToolCallRequest",
    "ModelRequest",
    "ModelResponse",
    "ModelClient",
    "StreamingModelClient",
    "FakeModelClient",
    "fake_response",
    "held_back_ms_of",
    "note_held_back",
]

Backend = Literal["hosted_api", "self_hosted"]

HELD_BACK_ATTRIBUTE = "held_back_ms"
"""Where a failed call's wait is carried, on the exception that ended it."""


def held_back_ms_of(exc: BaseException) -> int:
    """How long the call that raised this had waited, or ``0`` where it did not wait.

    A call that answered carries its wait on ``ModelResponse.held_back_ms``. One that
    exhausted its retries produced no response, so the figure is on the exception instead::

        try:
            response = client.complete(request)
        except CallerFacingError as exc:
            waited_ms = held_back_ms_of(exc)
            raise

    The run was charged ``max_wall_clock`` for that time whether the call answered or not, so
    a total that dropped it would report a throttled run as a slow one.
    """
    return int(getattr(exc, HELD_BACK_ATTRIBUTE, 0) or 0)


def note_held_back(exc: BaseException, waited_ms: int) -> None:
    """Record on ``exc`` that the call waited this long before giving up.

    Called by an adapter that retried and then raised, and by any client wrapping one::

        note_held_back(error, int(waited * 1000))

    Adds to whatever is already there, so a `PacedClient` in front of an adapter reports its
    own wait and the adapter's rather than replacing one with the other.
    """
    if waited_ms <= 0:
        return
    setattr(exc, HELD_BACK_ATTRIBUTE, held_back_ms_of(exc) + int(waited_ms))


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    """Which model an adapter calls, available before any call is made.

    Read by the run manifest and by the cassette key. A replay whose identity differs from the
    recording has no entry, so switching models cannot serve the previous model's responses::

        ModelIdentity(backend="self_hosted", request_model="Qwen/Qwen3-8B",
                      model_revision="a1b2c3d")

    ``model_revision`` is the commit the weights came from. It is ``None`` under
    ``hosted_api``, where no provider exposes one, and a bare repo ID or a branch name is an
    alias rather than a revision (FT-14).
    """

    backend: Backend
    request_model: str
    model_revision: str | None = None

    def to_manifest(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "request_model": self.request_model,
            "model_revision": self.model_revision,
        }


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """The token breakdown recorded on every model call.

    ``input_uncached``, ``input_cache_read`` and ``input_cache_write`` are separate, disjoint
    counts and an adapter populates all three. Provider APIs commonly report only the uncached
    remainder as "input tokens", which is not the prompt size::

        TokenUsage(input_uncached=8, input_cache_read=3216, input_cache_write=0,
                   cache_ttl=None, output=2)

    A count the backend did not report is :class:`~simple_agents.Unknown`, never ``0``. Where
    a backend reports the prompt size but not the split, the whole prompt goes in
    ``input_uncached`` and the two cache counts are ``Unknown``::

        TokenUsage(input_uncached=3224,
                   input_cache_read=Unknown(reason="server reports no prompt_tokens_details"),
                   input_cache_write=Unknown(reason="..."), cache_ttl=None, output=2)

    ``total_input`` and ``total`` are computed from the fields and are not stored. They sum
    the counts that were measured, so a budget charged against them charges less than was
    spent on any axis the backend left unknown.
    """

    input_uncached: int | Unknown
    input_cache_read: int | Unknown
    input_cache_write: int | Unknown
    cache_ttl: str | None
    output: int | Unknown

    @property
    def total_input(self) -> int:
        return (
            _known(self.input_uncached)
            + _known(self.input_cache_read)
            + _known(self.input_cache_write)
        )

    @property
    def measured_input(self) -> int | Unknown:
        """The prompt size, or ``Unknown`` when any input class went unmeasured.

        ``total_input`` sums the counts it has and so understates a prompt whose split was
        not reported. This says so instead, which is what a caller extrapolating from the
        figure needs::

            usage.measured_input   # 9600, or Unknown(reason=...)
        """
        for count in (self.input_uncached, self.input_cache_read, self.input_cache_write):
            if isinstance(count, Unknown):
                return Unknown(
                    reason=f"the backend left an input token class unmeasured: {count.reason}"
                )
        return self.total_input

    @property
    def total(self) -> int:
        return self.total_input + _known(self.output)

    def to_record(self) -> dict[str, Any]:
        return {
            "input_uncached": _count_for_record(self.input_uncached),
            "input_cache_read": _count_for_record(self.input_cache_read),
            "input_cache_write": _count_for_record(self.input_cache_write),
            "cache_ttl": self.cache_ttl,
            "output": _count_for_record(self.output),
        }


def _known(count: int | Unknown) -> int:
    """A count's contribution to a sum. An unmeasured count contributes nothing."""
    return 0 if isinstance(count, Unknown) else count


def _count_for_record(count: int | Unknown) -> Any:
    return count.model_dump() if isinstance(count, Unknown) else count


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    """A tool the model asked to call.

    ``provider`` is what the backend sent alongside this call and requires back on the next
    request, in the backend's own shape. An adapter fills it from the response and returns it
    unchanged when it translates the conversation::

        ToolCallRequest(
            id="c1",
            name="search",
            arguments={"query": "34 inch inseam"},
            provider={"thought_signature": "EjQKMgERTTIP..."},
        )

    It is empty on a backend that sends nothing of the kind, which is both shipped
    OpenAI-dialect adapters. A backend that requires it and does not get it back refuses the
    next turn, so the value travels into the assistant turn and onto the record rather than
    being held on the client: a resumed run rebuilds the conversation from what was written
    down.
    """

    id: str
    name: str
    arguments: dict[str, Any]
    provider: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        """The call as a trajectory record, a cassette entry and the conversation store it.

        ``provider`` is absent rather than empty where the backend sent nothing, so a
        conversation built from a backend that sends none is byte-identical to one built
        before this field existed, and every cassette key over it still matches.
        """
        record: dict[str, Any] = {"id": self.id, "name": self.name, "arguments": self.arguments}
        if self.provider:
            record["provider"] = dict(self.provider)
        return record

    @classmethod
    def from_record(cls, raw: Mapping[str, Any]) -> ToolCallRequest:
        """Rebuild a call from what ``to_record`` wrote."""
        provider = raw.get("provider")
        return cls(
            id=raw["id"],
            name=raw["name"],
            arguments=raw.get("arguments") or {},
            provider=dict(provider) if isinstance(provider, Mapping) else {},
        )


@dataclass(frozen=True, slots=True)
class Reasoning:
    """A chain of thought the backend reported separately from the answer.

    ``text`` is the reasoning as text, for a reader and for the record. ``blocks`` is what the
    backend sent, in its own shape, for an adapter to return on the next request::

        Reasoning(text="The shelf is 32 inches and two books take 10, so 22 remain.")

    A backend that reports reasoning as text alone fills ``text`` and leaves ``blocks`` empty.
    A backend whose reasoning carries state that has to be returned verbatim, such as a
    signature over the text or an opaque encrypted payload, puts each piece in ``blocks``
    unchanged::

        Reasoning(
            text="The shelf is 32 inches...",
            blocks=({"type": "thinking", "thinking": "The shelf is...", "signature": "Er0B..."},),
        )

    ``text`` is ``None`` where the backend sent only an opaque payload, since inventing a
    readable form would describe reasoning the model did not report. A backend that reports no
    reasoning at all sets ``ModelResponse.reasoning`` to ``None`` rather than an empty
    ``Reasoning``.

    Reasoning is charged as output tokens whether or not a backend returns it, so a call whose
    output count exceeds its content is explained by this field rather than unaccounted for.
    """

    text: str | None = None
    blocks: tuple[Mapping[str, Any], ...] = ()

    def to_record(self) -> dict[str, Any]:
        """The reasoning as a trajectory record and a cassette entry store it."""
        return {"text": self.text, "blocks": [dict(block) for block in self.blocks]}

    @classmethod
    def from_record(cls, raw: Any) -> Reasoning | None:
        """What a record or a cassette entry stored, or ``None`` where it stored nothing."""
        if not isinstance(raw, Mapping):
            return None
        blocks = tuple(dict(block) for block in raw.get("blocks") or [])
        text = raw.get("text")
        if text is None and not blocks:
            return None
        return cls(text=text, blocks=blocks)


@dataclass(frozen=True, slots=True)
class RateLimit:
    """What the backend said is left of the current window, when it says anything.

    A quota measured per minute is not cleared by retrying inside one call, so pacing a batch
    is the caller's job and this is the figure to pace against::

        response = client.complete(request)
        if (left := response.rate_limit) and left.remaining_tokens is not None:
            if left.remaining_tokens < next_prompt_estimate:
                time.sleep(left.resets_in_s or 60)

    ``None`` on any field means the backend did not report it. A backend that reports none of
    them sets ``rate_limit`` to ``None`` rather than a record of three nulls.
    """

    remaining_requests: int | None = None
    remaining_tokens: int | None = None
    resets_in_s: float | None = None

    def to_record(self) -> dict[str, Any]:
        """All three keys always present; ``null`` means the backend reported no figure."""
        return {
            "remaining_requests": self.remaining_requests,
            "remaining_tokens": self.remaining_tokens,
            "resets_in_s": self.resets_in_s,
        }


@dataclass(slots=True)
class ModelRequest:
    """What the library asks a backend for.

    ``extra`` is the passthrough for backend-specific parameters: guided decoding, thinking
    configuration, and sampling options that one backend supports and another does not. The
    library does not read it. The dict reaches the adapter unchanged, and an unrecognised key
    is reported by the backend.
    """

    messages: list[dict[str, Any]]
    seed: int | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    output_schema: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def params_for_key(self) -> dict[str, Any]:
        """Configuration as sent, in full, for the cassette key and the cassette's stored
        request.

        Carries the sampling parameters, ``extra``, and the tool declarations and output
        schema the request offered. A replay key that omitted the offered set would serve a
        response recorded against other tools.
        """
        return {
            "seed": self.seed,
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "extra": dict(self.extra),
            "tools": list(self.tools),
            "output_schema": self.output_schema,
        }

    def params_for_record(self, register: Callable[[Any], str | None]) -> dict[str, Any]:
        """Configuration as sent, for the record's ``params`` field::

            params = request.params_for_record(manifest.register_schema)

        The tool declarations and the output schema are the same block on every call a node
        makes, so the record carries ``tools_ref`` and ``output_schema_ref`` and ``register``
        puts the block itself in the manifest under that reference. Two calls offered
        different tools carry different references.
        """
        return {
            "seed": self.seed,
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "extra": dict(self.extra),
            "tools_ref": register(list(self.tools) if self.tools else None),
            "output_schema_ref": register(self.output_schema),
        }


@dataclass(slots=True)
class ModelResponse:
    """What a backend returns.

    The library normalises what it reads itself, passes through what it does not, and emulates
    nothing. A backend that reports no equivalent of a field reports ``None`` for it rather
    than a value the adapter invented.

    ``concurrent_requests`` is the divisor for compute-basis cost: the requests the backend had
    in flight during this call, sampled, so an adapter able to report a time-weighted average
    should report that. ``None`` means the backend does not report it, and cost derived from it
    is an upper bound rather than a figure.

    ``rate_limit`` is what the backend said is left of the current window; ``provider`` carries
    whatever else it sent, untouched.

    ``reasoning`` is the chain of thought where the backend reported one separately from the
    answer. A backend leaving it inside ``content`` reports ``None``: splitting it out would be
    the adapter deciding where an answer begins.

    ``held_back_ms`` is how long the client waited before the backend was asked, which
    ``max_wall_clock`` is charged for because the wait is elapsed time.
    """

    content: str | None
    tool_calls: list[ToolCallRequest]
    finish_reason: str | None
    backend: Backend
    request_model: str
    response_model: str | None
    model_revision: str | None
    tokens: TokenUsage
    concurrent_requests: int | None = None
    rate_limit: RateLimit | None = None
    provider: dict[str, str] = field(default_factory=dict)
    reasoning: Reasoning | None = None
    # Retry backoff inside an adapter, and pacing in a `PacedClient` in front of it. The
    # trajectory record's timestamps bracket the whole call and are unaffected by this.
    held_back_ms: int = 0


class ModelClient(Protocol):
    """The seam. Two methods.

    An adapter implements these and nothing else. Backend-specific configuration belongs in
    its constructor; per-call backend knobs arrive in ``ModelRequest.extra``.

    ``identity`` reports which model the adapter calls without making a call. The manifest
    records it, and the cassette key includes it, so a replay after a model change finds no
    entry rather than serving the previous model's responses.
    """

    def complete(self, request: ModelRequest) -> ModelResponse: ...

    def identity(self) -> ModelIdentity: ...


class StreamingModelClient(ModelClient, Protocol):
    """A model client that can also deliver content as it arrives.

    ``stream`` is ``complete`` with a sink: it calls ``on_chunk`` with each piece of content
    and returns the same assembled response, so a caller that ignores the pieces gets exactly
    what ``complete`` returns::

        class MyClient:
            def identity(self) -> ModelIdentity: ...
            def complete(self, request: ModelRequest) -> ModelResponse: ...

            def stream(self, request: ModelRequest,
                       on_chunk: Callable[[str], None]) -> ModelResponse:
                ...

    Implementing this is optional. A client without ``stream`` is a ``ModelClient`` and works
    everywhere one does; a node declaring ``stream=True`` run against it is refused by name.
    The pieces passed to ``on_chunk`` must join to the response's ``content`` exactly, since a
    recording's chunk boundaries are offsets into it, and reasoning never goes to that sink.

    Delivering reasoning as it arrives is a further option, taken by accepting a keyword-only
    ``on_reasoning`` whose pieces join to ``response.reasoning.text``::

        def stream(self, request: ModelRequest, on_chunk: Callable[[str], None],
                   *, on_reasoning: Callable[[str], None] | None = None) -> ModelResponse:
            ...

    It is passed only to a ``stream`` whose signature accepts it, so an adapter written with
    two parameters keeps working, and a run given ``on_reasoning=`` against one is refused by
    name. A wrapper standing in front of an adapter delegates both the way it delegates
    ``complete``; ``PacedClient`` is the shipped example.
    """

    def stream(self, request: ModelRequest, on_chunk: Callable[[str], None]) -> ModelResponse: ...


@dataclass(slots=True)
class FakeModelClient:
    """A scripted client for tests.

    Returns queued responses in order and does not interpret the request. Raises
    ``AssertionError`` when more calls are made than were scripted::

        client = FakeModelClient(responses=[
            fake_response(content='{"answer": "32 inches"}'),
        ])
        pipeline.run(inputs, envelope=RunEnvelope(run_dir=tmp_path), model=client)

        client.requests  # every ModelRequest the pipeline sent, in order

    ``answer`` replaces the list with a function of the request, which is what a run whose
    calls overlap needs: a queue hands out whatever is next, so which call gets which response
    depends on which arrived first::

        client = FakeModelClient(
            answer=lambda request: fake_response(content=request.messages[-1]["content"])
        )

    ``model_identity`` is what :meth:`identity` reports. Change it to test behaviour that
    depends on which model is configured, such as a cassette recorded against another one.

    ``scripted`` is true, so every run through this client records ``scripted`` on its
    manifest and is left out of ``runs()``, ``simple-agents report`` and the conformance
    checks unless they are asked for it. A project's own stand-in declares the same attribute
    to be read the same way (``docs/model-clients.md`` §7).

    Set it false where the run is meant to be read back as an ordinary one, which is what a
    test of a project's own reporting wants::

        client = FakeModelClient(responses=[...], scripted=False)
    """

    responses: list[ModelResponse] = field(default_factory=list)
    requests: list[ModelRequest] = field(default_factory=list)
    model_identity: ModelIdentity = ModelIdentity(
        backend="self_hosted", request_model="test/model", model_revision="0" * 40
    )
    answer: Callable[[ModelRequest], ModelResponse] | None = None
    scripted: bool = True
    """Whether a run through this client records itself as answered from a script."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _in_flight: int = 0

    def identity(self) -> ModelIdentity:
        return self.model_identity

    def complete(self, request: ModelRequest) -> ModelResponse:
        with self._lock:
            self.requests.append(request)
            if self.answer is None and self._in_flight:
                raise CallerFacingError(
                    "FakeModelClient was called from two places at once and answers with the "
                    "next response in its list without reading the request, so which call "
                    "gets which response is decided by which arrived first.\n"
                    "Pass answer=, a function of the request, so each call gets the response "
                    "its own request asks for: FakeModelClient(answer=lambda request: "
                    "fake_response(content='...')). A cassette needs nothing of the kind, "
                    "because an entry is found by hashing the request."
                )
            if self.answer is None and not self.responses:
                raise AssertionError(
                    "FakeModelClient ran out of scripted responses. The code under test made "
                    f"{len(self.requests)} model call(s) but only "
                    f"{len(self.requests) - 1} were scripted. Either the loop iterated more "
                    "times than the test expected, or the script is short by one response."
                )
            self._in_flight += 1
            queued = None if self.answer is not None else self.responses.pop(0)
        try:
            return queued if queued is not None else self.answer(request)  # type: ignore[misc]
        finally:
            with self._lock:
                self._in_flight -= 1


def fake_response(
    content: str | None = None,
    *,
    tool_calls: list[ToolCallRequest] | None = None,
    finish_reason: str = "end_turn",
    backend: Backend = "self_hosted",
    request_model: str = "test/model",
    model_revision: str | None = "0" * 40,
    tokens: TokenUsage | None = None,
    concurrent_requests: int | None = 1,
) -> ModelResponse:
    """Builder for test responses. Defaults to a self-hosted call with a pinned revision."""
    return ModelResponse(
        content=content,
        tool_calls=tool_calls if tool_calls is not None else [],
        finish_reason=finish_reason,
        backend=backend,
        request_model=request_model,
        response_model=request_model,
        model_revision=model_revision,
        tokens=tokens
        if tokens is not None
        else TokenUsage(
            input_uncached=10,
            input_cache_read=0,
            input_cache_write=0,
            cache_ttl=None,
            output=5,
        ),
        concurrent_requests=concurrent_requests,
    )
