"""The run context, and the scoped views each node kind receives of it.

A ``Deterministic`` node is never given anything that can make a model call. An ``LLMNode``
function is given none either; it returns a prompt and the library makes the call.

The run context holds the sequence counter, the parent-record links, the run seed, the
depleting run budget, and the cassette every external call goes through. Node functions do not
write to the trajectory; records are emitted around them.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from .budget import AXIS_FIELDS, Budget, BudgetExceeded, NodeBudgetExceeded, Spend
from .records.cassette import (
    Cassette,
    CassetteEntry,
    decode_embedding_response,
    decode_model_response,
    decode_rerank_response,
    decode_tool_response,
    embedding_key,
    encode_embedding_response,
    encode_model_response,
    encode_rerank_response,
    encode_tool_failure,
    encode_tool_result,
    miss_error,
    model_call_key,
    rerank_key,
    tool_call_key,
)
from .concurrency import WorkPool
from .cost import CostBasis, cost_of
from .errors import (
    CallerFacingError,
    ConfigurationError,
    ModelFacingError,
    Suspend,
    Throttled,
)
from .records.manifest import Manifest
from .memory import ScopedMemory
from .models import ModelClient, ModelRequest
from .redaction import Redaction
from .schema import Unknown
from .tools import Tool
from .records.trajectory import Record, TrajectoryWriter, utc_now

__all__ = [
    "RunContext",
    "NodeContext",
    "AgentContext",
    "RouteContext",
    "ToolCallSummary",
    "CallOutcome",
    "StreamCapture",
    "ChunkRecorder",
    "TokenEvent",
    "derive_seed",
    "new_run_id",
]


def new_run_id() -> str:
    """An identifier for one run. Joins the manifest to the trajectory.

    ``run_20260809T014233Z_a3f92c1d``: the UTC start to the second, then eight random
    characters that separate runs starting inside one second, enough that runs a product
    serves concurrently do not collide. Directory names therefore sort into the order the
    runs happened, so ``ls runs/`` and a plain glob both read chronologically.

    Nothing in the library parses this. A run whose id came from somewhere else, such as an
    evaluation naming its rollouts ``e1-0``, is read the same way.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}"


def derive_seed(run_seed: int, node_id: str, call_index: int, item_index: int | None = None) -> int:
    """The seed for one call, derived from the run seed.

    Every call in a run gets a distinct seed, and all of them reconstruct from the single
    integer the manifest records. Re-running with that seed reproduces the same per-call
    seeds, which is what lets a cassette recorded from one run replay against another.

    ``item_index`` is the fan-out item the call belongs to, and ``call_index`` counts within
    that item. A call outside a fan-out passes ``None`` and seeds from the node alone, so a
    node's calls are numbered by position and a fan-out's by which item they are for. That is
    what keeps an item's seed the same whether or not the items overlapped.
    """
    within = (
        f"{node_id}:{call_index}"
        if item_index is None
        else (f"{node_id}:{item_index}:{call_index}")
    )
    material = f"{run_seed}:{within}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:4], "big") & 0x7FFFFFFF


def _slot(item_index: int | None) -> str:
    """The key a per-item counter is held under. ``""`` is the node's own, outside any item."""
    return "" if item_index is None else str(item_index)


@dataclass
class _Scope:
    """What one node execution has spent, against what it declared.

    The run's own accumulator bounds the run and cannot bound a node, because a fan-out's
    items overlap and each holds its own counters. This is the run-wide accumulator's shape
    at node scope, under the same lock, so a node's total is a sum rather than a per-item
    ceiling.
    """

    budget: Budget
    spend: Spend
    started: float
    in_flight: int = 0


class ChunkRecorder:
    """The sink an adapter is handed: forwards each piece and notes where it fell.

    Held by the caller rather than created inside the call, so a call that raises part-way
    still says what reached the end user::

        recorder = ChunkRecorder(deliver=render)
        response = client.stream(request, recorder)
        recorder.capture()      # StreamCapture(cuts=(3, 9), first_chunk_ms=180)
        recorder.text           # what was delivered, whether or not the call finished
    """

    def __init__(self, deliver: Any) -> None:
        self.deliver = deliver
        self.parts: list[str] = []
        self.cuts: list[int] = []
        self.started = time.monotonic()
        self.first: float | None = None

    def __call__(self, text: str) -> None:
        if self.first is None:
            self.first = time.monotonic()
        self.parts.append(text)
        self.cuts.append(self.cuts[-1] + len(text) if self.cuts else len(text))
        self.deliver(text)

    @property
    def text(self) -> str:
        return "".join(self.parts)

    def capture(self, *, reasoning_cuts: tuple[int, ...] = ()) -> StreamCapture:
        return StreamCapture(
            cuts=tuple(self.cuts),
            first_chunk_ms=(
                int((self.first - self.started) * 1000) if self.first is not None else None
            ),
            reasoning_cuts=reasoning_cuts,
        )


def accepts_reasoning_sink(model: Any) -> bool:
    """Whether this client's ``stream`` takes an ``on_reasoning`` keyword.

    Presence of the parameter is the capability declaration, on the same rule that makes
    presence of ``stream`` the declaration for streaming at all. An adapter written with two
    parameters is never called with a third, so one written before reasoning existed keeps
    working.
    """
    stream = getattr(model, "stream", None)
    if stream is None:
        return False
    try:
        parameters = inspect.signature(stream).parameters
    except (TypeError, ValueError):
        return False
    if "on_reasoning" in parameters:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())


def stream_call(
    model: ModelClient,
    request: ModelRequest,
    recorder: ChunkRecorder,
    reasoning_recorder: ChunkRecorder | None = None,
) -> tuple[Any, StreamCapture]:
    """One streamed call, checking that what was delivered is what came back.

    Raises ``CallerFacingError`` where the pieces do not reconstruct the response's content, or
    where the reasoning pieces do not reconstruct the response's reasoning text. An adapter
    that forwards something else produces a recording whose chunk boundaries index into text
    that is not there, and a replay of it would hand the sink pieces of the wrong string.
    """
    if reasoning_recorder is None:
        response = model.stream(request, recorder)  # type: ignore[attr-defined]
    else:
        response = model.stream(  # type: ignore[attr-defined]
            request, recorder, on_reasoning=reasoning_recorder
        )

    content = response.content or ""
    if recorder.text != content:
        raise CallerFacingError(
            f"{type(model).__name__}.stream delivered {len(recorder.text)} characters but "
            f"returned a response whose content is {len(content)}. The pieces passed to the "
            f"sink have to reconstruct ModelResponse.content exactly, or a recording's chunk "
            f"boundaries index into text the replay does not have.\n"
            f"Forward the response's content deltas and nothing else. Reasoning goes to the "
            f"on_reasoning sink, never to this one."
        )

    if reasoning_recorder is not None:
        reasoning_text = response.reasoning.text or "" if response.reasoning is not None else ""
        if reasoning_recorder.text != reasoning_text:
            raise CallerFacingError(
                f"{type(model).__name__}.stream delivered "
                f"{len(reasoning_recorder.text)} characters to on_reasoning but returned a "
                f"response whose reasoning text is {len(reasoning_text)}. The pieces passed "
                f"to that sink have to reconstruct ModelResponse.reasoning.text exactly, on "
                f"the same rule as the content sink.\n"
                f"Forward the response's reasoning deltas and nothing else."
            )
    return response, recorder.capture(
        reasoning_cuts=(tuple(reasoning_recorder.cuts) if reasoning_recorder is not None else ())
    )


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """One piece of text a model produced, delivered as it arrived.

    Received by the callback passed to ``Pipeline.run(on_token=...)``, for a node declaring
    ``stream=True``::

        def render(event: TokenEvent) -> None:
            if event.node_id == "answer":
                sys.stdout.write(event.text)

        pipeline.run(inputs, envelope=env, model=client, on_token=render)

    A token event always falls between the ``started`` and the ``completed`` or ``failed``
    ``NodeEvent`` of the node that produced it, and carries the same ``node_id``, so a caller
    watching both channels attributes tokens to a node without correlating anything.

    ``call_index`` is the index of the model call within the node, counting from zero, which
    is what tells one turn of an agent loop from the next. ``item_index`` is filled inside a
    fan-out and ``None`` elsewhere.

    Raised nowhere and awaited by nothing: an exception from the callback ends the run like any
    other, so a display that fails does not pass silently. A node whose ``output_schema`` is
    set produces JSON fragments rather than prose, since that is what the model emits.

    ``kind`` is ``"content"`` on the answer and ``"reasoning"`` on a chain of thought, so one
    function passed to both ``on_token=`` and ``on_reasoning=`` can tell them apart.
    """

    node_id: str
    node_kind: str
    call_index: int
    text: str
    item_index: int | None = None
    kind: str = "content"


@dataclass(frozen=True, slots=True)
class StreamCapture:
    """Where one streamed call's chunks fell, and when the first one arrived.

    ``cuts`` are offsets into the assembled content, one per chunk boundary, so the pieces are
    recoverable without storing the text twice. A cassette entry stores this, and a replay
    re-emits the same pieces::

        capture.cuts            # (3, 9, 14, 22)
        capture.chunks          # 4
        capture.first_chunk_ms  # 180, or None where nothing was delivered

    ``first_chunk_ms`` is measured from the moment the request was sent.
    """

    cuts: tuple[int, ...]
    first_chunk_ms: int | None
    reasoning_cuts: tuple[int, ...] = ()

    @property
    def chunks(self) -> int:
        return len(self.cuts)

    @property
    def reasoning_chunks(self) -> int:
        return len(self.reasoning_cuts)

    def pieces(self, content: str) -> list[str]:
        """The chunks the recording delivered, cut back out of ``content``."""
        return _pieces(content, self.cuts)

    def reasoning_pieces(self, text: str) -> list[str]:
        """The reasoning chunks the recording delivered, cut back out of its text."""
        return _pieces(text, self.reasoning_cuts)

    def to_record(self) -> dict[str, Any]:
        """The stream as a trajectory record and a cassette entry store it."""
        return {
            "chunks": self.chunks,
            "first_chunk_ms": self.first_chunk_ms,
            "reasoning_chunks": self.reasoning_chunks,
        }

    def to_entry(self) -> dict[str, Any]:
        """The stream as a cassette entry stores it, keeping the boundaries."""
        return {
            "cuts": list(self.cuts),
            "first_chunk_ms": self.first_chunk_ms,
            "reasoning_cuts": list(self.reasoning_cuts),
        }

    @classmethod
    def from_entry(cls, raw: Any) -> StreamCapture | None:
        """What a cassette entry recorded, or ``None`` for one recorded without streaming."""
        if not isinstance(raw, dict) or "cuts" not in raw:
            return None
        return cls(
            cuts=tuple(int(cut) for cut in raw["cuts"]),
            first_chunk_ms=raw.get("first_chunk_ms"),
            reasoning_cuts=tuple(int(cut) for cut in raw.get("reasoning_cuts") or ()),
        )


def _pieces(text: str, cuts: tuple[int, ...]) -> list[str]:
    """Text cut back into the pieces a set of boundary offsets describes."""
    edges = [0, *cuts]
    return [text[edges[i] : edges[i + 1]] for i in range(len(cuts))]


@dataclass(frozen=True, slots=True)
class CallOutcome:
    """The result of one external call, and how it was served."""

    value: Any
    cassette_key: str | None
    replayed: bool
    recorded_duration_ms: int | None = None
    """How long the live call took, on a call served from a cassette. ``None`` otherwise."""
    stream: StreamCapture | None = None
    """Where the chunks fell, on a call that streamed. ``None`` on one that did not."""


@dataclass
class RunContext:
    """State shared across every node in one run.

    Node functions receive a :class:`NodeContext` or :class:`AgentContext` view of this
    object, never the object itself.
    """

    run_id: str
    writer: TrajectoryWriter
    budget: Budget
    workspace: Path
    seed: int
    manifest: Manifest
    cassette: Cassette = field(default_factory=Cassette.off)
    cost_basis: CostBasis | None = None
    redaction: Redaction = field(default_factory=Redaction)
    memory: ScopedMemory | None = None
    """The memory a tool taking a ``Memory`` handle reaches: the envelope's store under the
    scope this run named. ``None`` where the envelope declares no store or the run named no
    scope. A node reaches it only through such a tool."""
    end_user: Any = None
    """Who answers a consultation in this run, from ``RunEnvelope(end_user=...)``. ``None``
    leaves each ``consult`` tool asking the channel it was registered with."""
    conversation: Any = None
    """The conversation this run is a turn of, from ``Pipeline.run(conversation_id=...)``, or ``None``
    where the run is not part of one. A node reads it in its prompt function and the library
    writes what the node produces."""
    pool: WorkPool = field(default_factory=WorkPool)
    """The run's ceiling on calls in flight, and the drain rule. Built from
    ``Pipeline.run(concurrency=...)``; the default overlaps nothing."""
    _spend: Spend = field(default_factory=Spend)
    _steps_in_flight: int = 0
    _clock_since: float | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    token_sink: Any = None
    """What ``Pipeline.run(on_token=...)`` was given, or ``None``. A node declaring
    ``stream=True`` streams only where this is set, so a run that supplies no sink makes the
    same calls a non-streaming one does."""
    reasoning_sink: Any = None
    """What ``Pipeline.run(on_reasoning=...)`` was given, or ``None``. Independent of
    ``token_sink``: a run may take the chain of thought, the answer, or both."""
    progress_sink: Any = None
    """What ``Pipeline.run(on_progress=...)`` was given, or ``None``. A fan-out announces each
    item on it as that item finishes, which the executor cannot do: it sees the node."""
    _sequence: int = 0
    _scopes: dict[str, _Scope] = field(default_factory=dict)
    _model_calls: dict[str, dict[str, int]] = field(default_factory=dict)
    _tool_calls: dict[str, int] = field(default_factory=dict)
    _tool_occurrences: dict[str, int] = field(default_factory=dict)
    _last_input: dict[str, tuple[Any, int, int, int | None]] = field(default_factory=dict)
    _money_currency: tuple[str, str] | None = None
    _no_one_to_ask: dict[str, str] = field(default_factory=dict)
    _suspension_left_a_call: str | None = field(default=None, repr=False)
    _shelved: list[Any] = field(default_factory=list, repr=False)
    fetch_policy_declaration: Any = None
    """The pipeline's declared ``HostPolicy``, or ``None``. The declaration only; what a node
    or tool receives is this run's own copy, through :meth:`bound_fetch_policy`."""
    _fetch_bindings: dict[int, tuple[Any, Any]] = field(default_factory=dict)

    # -- the fetch policy this run counts against -------------------------------------------

    def bound_fetch_policy(self, declaration: Any) -> Any:
        """This run's own copy of a ``HostPolicy`` declaration, bound once per declaration.

        Each run counts fetches and holds admissions on its own copy, so two runs through one
        declaration never share a tally. The declaration is kept beside the copy so the id it
        is keyed on stays valid for the run's whole life.
        """
        with self._lock:
            held = self._fetch_bindings.get(id(declaration))
            if held is None:
                held = (declaration, declaration.for_run())
                self._fetch_bindings[id(declaration)] = held
            return held[1]

    def node_fetch_policy(self) -> Any:
        """The run's copy of the pipeline's declared policy, or ``None`` with none declared."""
        if self.fetch_policy_declaration is None:
            return None
        return self.bound_fetch_policy(self.fetch_policy_declaration)

    def fetch_policy_record(self, declaration: Any) -> dict[str, Any]:
        """What this run's manifest stores for one declaration.

        The run's own counts where this run bound a copy, and the declaration's zeros where
        nothing in the run touched it.
        """
        with self._lock:
            held = self._fetch_bindings.get(id(declaration))
        return (held[1] if held is not None else declaration).to_record()

    # -- spend, and the clock one of its axes is read from ---------------------------------

    @property
    def spend(self) -> Spend:
        """What this run has consumed, with ``wall_clock_ms`` read from the run clock.

        The three counted axes accumulate as calls are made. The wall clock is elapsed time
        while the run is executing, so a run whose calls overlap is charged the time that
        passed rather than the sum of what each call took, and a run waiting on a person or a
        clock is charged nothing while it waits.
        """
        with self._lock:
            return replace(self._spend, wall_clock_ms=self._elapsed_ms())

    @spend.setter
    def spend(self, value: Spend) -> None:
        """Put back a spend, whose ``wall_clock_ms`` becomes what the clock counts up from."""
        with self._lock:
            self._spend = value
            if self._clock_since is not None:
                self._clock_since = time.monotonic()

    def _elapsed_ms(self) -> int:
        """The wall clock: what was carried in, plus this stretch of executing."""
        carried = self._spend.wall_clock_ms
        if self._clock_since is None:
            return carried
        return carried + int((time.monotonic() - self._clock_since) * 1000)

    @contextmanager
    def executing(self) -> Iterator[None]:
        """Run the clock for as long as this run is executing::

            with run.executing():
                result = self._walk(...)

        A run that stops and is started again folds what it had already elapsed into the
        total, so time between the two is charged to nothing.
        """
        with self._lock:
            self._clock_since = time.monotonic()
        try:
            yield
        finally:
            with self._lock:
                self._spend = replace(self._spend, wall_clock_ms=self._elapsed_ms())
                self._clock_since = None

    def money_currency(self) -> tuple[str, str] | None:
        """The currency every money figure in this run is in, and what fixed it.

        The cost basis fixes it where the run declares one. A run with no basis has nothing to
        anchor to until a figure arrives, so the first tool to report a spend fixes it through
        :meth:`fix_money_currency`. ``None`` before either has happened.

        The run's totals are one number, so a second currency cannot be added to them.
        """
        if self._money_currency is None and self.cost_basis is not None:
            self._money_currency = (self.cost_basis.currency, "the run's cost basis")
        return self._money_currency

    def fix_money_currency(self, currency: str, source: str) -> None:
        """Fix the run's currency where nothing has yet, naming what fixed it.

        Does nothing where one is already fixed, so the cost basis wins and the first reported
        figure wins over every later one. ``source`` is what a refusal names.
        """
        with self._lock:
            if self.money_currency() is None:
                self._money_currency = (currency, source)

    def next_sequence(self) -> int:
        """Monotonic within the run, in emission order.

        Trajectories are ordered by ``sequence``, not by timestamp. Two calls that overlap can
        share a millisecond, and the clock can be adjusted mid-run. Under a run whose work
        overlaps this says which record was written first and not which happened first, and
        ``parent_id`` is what says where a record belongs.
        """
        with self._lock:
            self._sequence += 1
            return self._sequence

    def new_record_id(self) -> str:
        """A unique id, carrying no ordering information. Order by ``sequence`` instead."""
        return f"rec_{uuid.uuid4().hex[:12]}"

    def emit(self, record: Record) -> None:
        """Write one record, numbered as it is written.

        The number comes from inside the writer's lock, so a trajectory read line by line is
        in ``sequence`` order however many threads were writing into it.
        """
        self.writer.write(record, number=self.next_sequence)
        self.manifest.count_record(str(record.get("record_type")))

    def remaining_budget(self) -> Budget:
        return self.budget.remaining(self.spend)

    # -- what a suspended run carries across the process boundary -------------------------

    def counters(self) -> dict[str, Any]:
        """The run-level counters a resumed run has to restore.

        Restoring the seed alone is not enough. ``derive_seed`` reads the per-node model-call
        index, and the tool occurrence count is part of a tool call's cassette key, so a
        resumed run that started them again would seed its calls differently from the run that
        recorded them and every lookup would miss. The money currency is here for the same
        reason: the spend it belongs to is restored, so a resumed run that had forgotten it
        would add a second currency to the total the first half of the run built.
        """
        return {
            "sequence": self._sequence,
            "model_calls": {node: dict(slots) for node, slots in self._model_calls.items()},
            "tool_calls": dict(self._tool_calls),
            "tool_occurrences": dict(self._tool_occurrences),
            "last_input": {
                node_id: {
                    "tokens": tokens,
                    "chars": chars,
                    "call_index": call_index,
                    "item_index": item_index,
                }
                for node_id, (
                    tokens,
                    chars,
                    call_index,
                    item_index,
                ) in self._last_input.items()
            },
            "money_currency": list(self._money_currency) if self._money_currency else None,
        }

    def restore_counters(self, state: dict[str, Any]) -> None:
        """Put back what :meth:`counters` recorded, before the walk is re-entered."""
        self._sequence = int(state["sequence"])
        self._model_calls = {node: dict(slots) for node, slots in state["model_calls"].items()}
        self._tool_calls = dict(state["tool_calls"])
        self._tool_occurrences = dict(state["tool_occurrences"])
        self._last_input = {
            node_id: (
                last["tokens"],
                last["chars"],
                last["call_index"],
                last.get("item_index"),
            )
            for node_id, last in state["last_input"].items()
        }
        fixed = state["money_currency"]
        self._money_currency = (str(fixed[0]), str(fixed[1])) if fixed else None

    @contextmanager
    def one_step(self, budget: Budget, scope: str | None = None) -> Iterator[None]:
        """Hold a step of ``budget`` for the duration of one call, or refuse to start it.

        A step is one model call and is known before the call is made, so it is taken before
        the work rather than counted after it. Calls that overlap therefore stop exactly on
        ``max_steps`` rather than overshooting by however many were in flight::

            with run.one_step(run.budget):
                answer = make_the_call()

        The other three axes are measured by what the call turns out to consume, so they are
        checked here against what has been spent and can overshoot by what was already
        running.

        ``scope`` names an open :meth:`scoped_budget`, and the call is held against that as
        well as against ``budget``. Exhausting the scope raises ``NodeBudgetExceeded``, which
        stops the node rather than the run.
        """
        with self._lock:
            reserved = replace(
                self._spend,
                steps=self._spend.steps + self._steps_in_flight,
                wall_clock_ms=self._elapsed_ms(),
            )
            tripped = budget.exceeded_by(reserved)
            if tripped is not None:
                limit, spent = AXIS_FIELDS[tripped]
                raise BudgetExceeded(
                    tripped, getattr(budget, limit) or 0, getattr(reserved, spent) or 0
                )
            held = self._scopes.get(scope) if scope is not None else None
            if held is not None:
                at_scope = replace(
                    held.spend,
                    steps=held.spend.steps + held.in_flight,
                    wall_clock_ms=int((time.monotonic() - held.started) * 1000),
                )
                tripped = held.budget.exceeded_by(at_scope)
                if tripped is not None:
                    limit, spent = AXIS_FIELDS[tripped]
                    raise NodeBudgetExceeded(
                        tripped,
                        getattr(held.budget, limit) or 0,
                        getattr(at_scope, spent) or 0,
                    )
                held.in_flight += 1
            self._steps_in_flight += 1
        try:
            yield
        finally:
            with self._lock:
                self._steps_in_flight -= 1
                if held is not None:
                    held.in_flight -= 1

    def charge(
        self,
        *,
        steps: int = 0,
        tokens: int = 0,
        cost: float | None = None,
        scope: str | None = None,
    ) -> None:
        """Add to what this run has spent. The wall clock is not charged here: it is elapsed
        time, read from the run clock rather than accumulated per call.

        ``scope`` names an open :meth:`scoped_budget`, which is charged the same amount. A
        scope that is not open is not an error: the node did not declare a budget of its own.
        """
        with self._lock:
            self._spend = self._spend.plus(steps=steps, tokens=tokens, cost=cost)
            held = self._scopes.get(scope) if scope is not None else None
            if held is not None:
                held.spend = held.spend.plus(steps=steps, tokens=tokens, cost=cost)

    def charge_scope(
        self, scope: str, *, steps: int = 0, tokens: int = 0, cost: float | None = None
    ) -> None:
        """Add to an open scope alone, for spend the run was already charged for.

        A model call made inside a tool or inside a delegated pipeline is charged to the run
        where it happens, under its own parent. The node that reached it has to pick it up too,
        or its budget would not bind what its tools and delegates spend, and :meth:`charge`
        would charge the run a second time.
        """
        with self._lock:
            held = self._scopes.get(scope)
            if held is not None:
                held.spend = held.spend.plus(steps=steps, tokens=tokens, cost=cost)

    @contextmanager
    def scoped_budget(self, scope: str, budget: Budget | None) -> Iterator[None]:
        """Bound what one node execution spends in total, on top of the run's own ceiling.

        A node that runs once is bounded by the budget its ``Execution`` was narrowed to, and
        needs none of this. A fan-out's items each hold their own counters and overlap, so a
        sum across them exists nowhere: this is where it lives, under the lock the run's own
        accumulator already takes.

        ``budget`` of ``None`` opens nothing, which is the node that declared no total.
        """
        if budget is None:
            yield
            return
        with self._lock:
            self._scopes[scope] = _Scope(budget=budget, spend=Spend(), started=time.monotonic())
        try:
            yield
        finally:
            with self._lock:
                self._scopes.pop(scope, None)

    # -- seeds ----------------------------------------------------------------------------

    def next_model_call(self, node_id: str, item_index: int | None = None) -> int:
        """The index of the next model call in this node, counting from zero.

        Counted within one fan-out item where ``item_index`` is given, and within the node
        otherwise. An item's calls are therefore numbered by their position in that item's own
        work rather than by how the items interleaved, which is what makes the seed an item is
        called with the same whatever order the items ran in.
        """
        with self._lock:
            slots = self._model_calls.setdefault(node_id, {})
            slot = _slot(item_index)
            index = slots.get(slot, 0)
            slots[slot] = index + 1
            return index

    def saw_model_call(self, node_id: str, call_index: int, item_index: int | None = None) -> None:
        """Note that this node has made the call at ``call_index``, for a caller that chose it.

        A resumed run has to carry on past the calls the stopped run already made.
        """
        with self._lock:
            slots = self._model_calls.setdefault(node_id, {})
            slot = _slot(item_index)
            slots[slot] = max(slots.get(slot, 0), call_index + 1)

    def seed_for(self, node_id: str, call_index: int, item_index: int | None = None) -> int:
        return derive_seed(self.seed, node_id, call_index, item_index)

    # -- what the last call in a node measured -------------------------------------------

    def note_input_size(
        self,
        node_id: str,
        *,
        tokens: Any,
        chars: int,
        call_index: int,
        item_index: int | None = None,
    ) -> None:
        """Remember what one call's prompt cost, for the next call's context builder.

        Kept per node rather than per fan-out item. What a builder reads from it is a ratio of
        tokens to characters for this node against this backend, which any call of the node
        measures; keeping it per item would leave every item of an ``LLMNode`` fan-out with no
        previous call and no estimate at all. A node whose calls overlap therefore remembers
        whichever of them finished last, and a builder extrapolating from it reads a
        measurement from one of this node's calls rather than from a particular one.

        ``item_index`` is stored beside the measurement rather than keyed on, so the estimate
        can name the call it came from. Inside a fan-out ``call_index`` counts within its item,
        so the pair is what identifies a call and either half alone points at several.
        """
        with self._lock:
            self._last_input[node_id] = (tokens, chars, call_index, item_index)

    def context_view(self, ctx: Any, node_id: str) -> Any:
        """``ctx`` with what the previous call in this node measured filled in.

        A context builder is the only caller. Before the first call of a node there is
        nothing to fill in, and the fields stay ``None``.
        """
        last = self._last_input.get(node_id)
        if last is None:
            return ctx
        tokens, chars, call_index, item_index = last
        return replace(
            ctx,
            last_input_tokens=tokens,
            last_input_chars=chars,
            last_call_index=call_index,
            last_item_index=item_index,
        )

    # -- external calls -------------------------------------------------------------------

    def call_model(
        self,
        request: ModelRequest,
        model: ModelClient,
        *,
        node_id: str,
        call_index: int,
        item_index: int | None = None,
        on_chunk: Any = None,
        on_reasoning: Any = None,
    ) -> CallOutcome:
        """Make one model call, through the cassette when one is in force.

        Returns the response along with the key it was stored under and whether it was
        replayed. In ``replay`` mode a request with no entry raises ``CassetteMiss``.

        ``on_chunk`` is called with each piece of content as it arrives, on a call that
        streams, and ``on_reasoning`` with each piece of the chain of thought. A replayed call
        delivers the pieces the recording delivered, so both sinks see the same sequence
        whether the response came from the backend or from the file.
        """
        identity = model.identity()
        keyed = {
            "backend": identity.backend,
            "request_model": identity.request_model,
            "model_revision": identity.model_revision,
            "messages": request.messages,
            "params": request.params_for_key(),
        }

        if not self.cassette.enabled:
            with self.pool.slot():
                response, capture = self._invoke(model, request, on_chunk, on_reasoning)
            return CallOutcome(response, None, False, stream=capture)

        key = model_call_key(**keyed)  # type: ignore[arg-type]
        stored, _ = self.redaction.redact(keyed)

        if self.cassette.serves_hits:
            entry = self.cassette.lookup(key)
            if entry is not None:
                self.manifest.count_cassette(hits=1)
                response = decode_model_response(entry.response)
                capture = self._replay_chunks(entry, response, on_chunk, on_reasoning)
                return CallOutcome(response, key, True, entry.duration_ms, stream=capture)
            self.manifest.count_cassette(misses=1)
            if self.cassette.is_replaying:
                raise miss_error(
                    cassette=self.cassette,
                    kind="model_call",
                    node_id=node_id,
                    call_index=call_index,
                    item_index=item_index,
                    request=stored,
                )

        started = time.monotonic()
        with self.pool.slot():
            response, capture = self._invoke(model, request, on_chunk, on_reasoning)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        self._store(
            key,
            "model_call",
            node_id,
            call_index,
            stored,
            encode_model_response(response),
            duration_ms=elapsed_ms,
            stream=capture.to_entry() if capture is not None else None,
            item_index=item_index,
        )
        return CallOutcome(response, key, False, stream=capture)

    def call_embedding(
        self,
        client: Any,
        texts: Sequence[str],
        *,
        node_id: str,
        call_index: int,
    ) -> CallOutcome:
        """Embed texts, through the cassette when one is in force.

        Keyed on the model identity and the texts, so a replay after an embedding-model change
        finds no entry rather than serving vectors the new model would not have produced. In
        ``replay`` mode a request with no entry raises ``CassetteMiss``.
        """
        identity = client.identity()
        keyed = {
            "backend": identity.backend,
            "request_model": identity.request_model,
            "model_revision": identity.model_revision,
            "texts": list(texts),
        }
        if not self.cassette.enabled:
            return CallOutcome(client.embed(list(texts)), None, False)
        return self._call_recorded(
            kind="embedding",
            key=embedding_key(**keyed),  # type: ignore[arg-type]
            keyed=keyed,
            invoke=lambda: client.embed(list(texts)),
            encode=encode_embedding_response,
            decode=decode_embedding_response,
            node_id=node_id,
            call_index=call_index,
        )

    def call_rerank(
        self,
        client: Any,
        query: str,
        documents: Sequence[str],
        *,
        node_id: str,
        call_index: int,
    ) -> CallOutcome:
        """Score documents against a query, through the cassette when one is in force.

        Keyed on the model identity, the query and the documents in the order given, since a
        reranker returns a score per position.
        """
        identity = client.identity()
        keyed = {
            "backend": identity.backend,
            "request_model": identity.request_model,
            "model_revision": identity.model_revision,
            "query": query,
            "documents": list(documents),
        }
        if not self.cassette.enabled:
            return CallOutcome(client.rerank(query, list(documents)), None, False)
        return self._call_recorded(
            kind="rerank",
            key=rerank_key(**keyed),  # type: ignore[arg-type]
            keyed=keyed,
            invoke=lambda: client.rerank(query, list(documents)),
            encode=encode_rerank_response,
            decode=decode_rerank_response,
            node_id=node_id,
            call_index=call_index,
        )

    def _call_recorded(
        self,
        *,
        kind: str,
        key: str,
        keyed: dict[str, Any],
        invoke: Callable[[], Any],
        encode: Callable[[Any], Any],
        decode: Callable[[Any], Any],
        node_id: str,
        call_index: int,
    ) -> CallOutcome:
        """One non-streaming call through the cassette: a hit is served, a replay miss
        raises, and anything else is made live and stored.

        ``call_embedding`` and ``call_rerank`` differ only in their key, their codec and the
        call itself, which is what the arguments carry. ``call_model`` keeps its own body,
        because a model call streams and runs inside the pool's slot.
        """
        stored, _ = self.redaction.redact(keyed)
        if self.cassette.serves_hits:
            entry = self.cassette.lookup(key)
            if entry is not None:
                self.manifest.count_cassette(hits=1)
                return CallOutcome(decode(entry.response), key, True, entry.duration_ms)
            self.manifest.count_cassette(misses=1)
            if self.cassette.is_replaying:
                raise miss_error(
                    cassette=self.cassette,
                    kind=kind,
                    node_id=node_id,
                    call_index=call_index,
                    request=stored,
                )
        started = time.monotonic()
        response = invoke()
        elapsed_ms = int((time.monotonic() - started) * 1000)
        self._store(
            key,
            kind,
            node_id,
            call_index,
            stored,
            encode(response),
            duration_ms=elapsed_ms,
        )
        return CallOutcome(response, key, False)

    def _invoke(
        self,
        model: ModelClient,
        request: ModelRequest,
        on_chunk: Any,
        on_reasoning: Any = None,
    ) -> tuple[Any, StreamCapture | None]:
        """One live call, streamed where a recorder was supplied and whole where it was not."""
        if on_chunk is None:
            return model.complete(request), None
        return stream_call(model, request, on_chunk, on_reasoning)

    def _replay_chunks(
        self, entry: CassetteEntry, response: Any, on_chunk: Any, on_reasoning: Any = None
    ) -> StreamCapture | None:
        """Hand a replayed response to the sinks in the pieces the recording delivered.

        An entry recorded without streaming has no boundaries to reproduce, so its whole
        content arrives as one piece and the record says the call did not stream. Nothing is
        invented, and no timing is simulated: how long the live call took is on
        ``recorded_duration_ms``.

        Reasoning replays the same way and on its own sink. An entry recorded before reasoning
        was stored, or one whose call produced none, delivers nothing there.
        """
        if on_chunk is None:
            return None
        capture = StreamCapture.from_entry(entry.stream)
        content = response.content or ""
        reasoning = response.reasoning.text or "" if response.reasoning is not None else ""
        if capture is None:
            if content:
                on_chunk(content)
            if on_reasoning is not None and reasoning:
                on_reasoning(reasoning)
            return None
        if on_reasoning is not None and reasoning:
            pieces = capture.reasoning_pieces(reasoning) or [reasoning]
            for piece in pieces:
                on_reasoning(piece)
        for piece in capture.pieces(content):
            on_chunk(piece)
        return capture

    def next_tool_call(self, node_id: str) -> int:
        """The index of the next tool call in this node, counting from zero."""
        with self._lock:
            index = self._tool_calls.get(node_id, 0)
            self._tool_calls[node_id] = index + 1
            return index

    def _call_waiting_out_a_throttle(
        self, tool: Tool, arguments: dict[str, Any], handles: dict[str, Any] | None
    ) -> Any:
        """Call the tool, waiting and calling again where the source says it is being asked
        too often.

        A throttle is the rate rather than the request, so passing it to the model reads as
        the source having nothing and an agent told that stops looking. The wait happens
        outside the run's slot, since a thread sitting still is not a call in flight.

        One ``tool_call`` record covers every attempt, as one ``model_call`` does for a
        client's retries. When the attempts are spent the failure does reach the model, since
        it is a ``ModelFacingError``, saying the source was busy.
        """
        for attempt in range(TOOL_RETRY_ATTEMPTS):
            try:
                with self.pool.slot():
                    return tool.call(arguments, handles)
            except Throttled as exc:
                if attempt == TOOL_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(_throttle_wait(attempt, exc.retry_after_s))
        raise AssertionError("unreachable: the loop returns or raises")

    def call_tool(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        *,
        node_id: str,
        call_index: int,
        handles: dict[str, Any] | None = None,
        occurrence: int | None = None,
        item_index: int | None = None,
    ) -> CallOutcome:
        """Invoke one tool, through the cassette when one is in force.

        ``occurrence`` is the number this call records under, where the caller reserved it
        with :meth:`reserve_tool_occurrences` before dispatching a turn's calls together.
        Left unset it is taken here, which is right for a call made on its own.

        A ``ModelFacingError`` raised by the tool is recorded and re-raised, so a replay
        reproduces the failure rather than turning it into a success. Any other exception is
        left to the caller and nothing is stored: the run is invalid, and recording it would
        make the failure replay as though it were the tool's behaviour.

        A tool taking a handle is re-run rather than stored, in every mode. Whatever it does
        through its handles is recorded and replayed on its own, so the records a replay
        writes match the live run's.
        """
        if occurrence is None:
            occurrence = self._note_tool_occurrence(tool, arguments, node_id, item_index)

        if tool.re_executed or not self.cassette.enabled:
            return CallOutcome(
                self._call_waiting_out_a_throttle(tool, arguments, handles), None, False
            )

        key = tool_call_key(
            node_id=node_id,
            tool_name=tool.name,
            tool_version=tool.version,
            arguments=arguments,
            occurrence=occurrence,
            item_index=item_index,
        )
        keyed = {
            "node_id": node_id,
            "tool_name": tool.name,
            "tool_version": tool.version,
            "arguments": arguments,
            "occurrence": occurrence,
        }
        stored, _ = self.redaction.redact(keyed)

        if self.cassette.serves_hits:
            entry = self.cassette.lookup(key)
            if entry is not None:
                self.manifest.count_cassette(hits=1)
                return CallOutcome(decode_tool_response(entry.response), key, True)
            self.manifest.count_cassette(misses=1)
            if self.cassette.is_replaying:
                raise miss_error(
                    cassette=self.cassette,
                    kind="tool_call",
                    node_id=node_id,
                    call_index=call_index,
                    request=stored,
                )

        try:
            value = self._call_waiting_out_a_throttle(tool, arguments, handles)
            if tool.redact_result:
                # Once, here, rather than at the model boundary: the cassette stores what
                # the model was given, so a replay serves the same string and the call
                # after it is the same request. A tool that declares this returns plain
                # data to its caller too.
                value, _ = self.redaction.redact_for_model(value)
        except ModelFacingError as exc:
            self._store(
                key,
                "tool_call",
                node_id,
                call_index,
                stored,
                encode_tool_failure(exc),
                item_index=item_index,
            )
            raise
        except Suspend as exc:
            # Nothing is filed: the call has no answer yet. The occurrence travels with the
            # suspension so the resumed run can file the answer under this same key, which is
            # what keeps a suspended run replayable.
            exc.tool_occurrence = occurrence
            raise
        self._store(
            key,
            "tool_call",
            node_id,
            call_index,
            stored,
            encode_tool_result(value),
            at_boundary=tool.redact_result,
            item_index=item_index,
        )
        return CallOutcome(value, key, False)

    def file_answer(
        self,
        *,
        tool: Tool,
        arguments: dict[str, Any],
        occurrence: int,
        answer: Any,
        node_id: str,
        call_index: int,
        item_index: int | None = None,
    ) -> str | None:
        """File an answer that arrived after the run stopped, under the key its call had.

        A tool that suspends raises rather than returning, so nothing was stored when the
        question was asked. Filing the answer here is what lets a replay of this run serve it
        and never suspend, which is what an evaluation over a consulting agent needs.
        """
        key = tool_call_key(
            node_id=node_id,
            tool_name=tool.name,
            tool_version=tool.version,
            arguments=arguments,
            occurrence=occurrence,
            item_index=item_index,
        )
        if not self.cassette.is_recording:
            return key
        stored, _ = self.redaction.redact(
            {
                "node_id": node_id,
                "tool_name": tool.name,
                "tool_version": tool.version,
                "arguments": arguments,
                "occurrence": occurrence,
            }
        )
        self._store(
            key,
            "tool_call",
            node_id,
            call_index,
            stored,
            encode_tool_result(answer),
            item_index=item_index,
        )
        return key

    def reserve_tool_occurrences(
        self,
        calls: Sequence[tuple[Tool, dict[str, Any]]],
        node_id: str,
        item_index: int | None = None,
    ) -> list[int]:
        """The occurrence each of these calls records under, taken in the order given::

            occurrences = run.reserve_tool_occurrences(
                [(search, {"query": "a"}), (search, {"query": "a"})], node_id="hunt"
            )                                                          # [0, 1]

        Taken before any of them runs, so calls that overlap record under the numbers their
        positions give them rather than under the order they happened to finish in.
        """
        with self._lock:
            return [
                self._note_tool_occurrence(tool, args, node_id, item_index) for tool, args in calls
            ]

    def _note_tool_occurrence(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        node_id: str,
        item_index: int | None = None,
    ) -> int:
        """How many times this call has already been made here, counting from zero.

        Part of the cassette key, so a tool answering differently at two moments records two
        entries rather than colliding onto one. Counted within the node, so a call recorded in
        one node keeps its key when another node's calls change, and within one fan-out item,
        so two items making one call are not numbered by whichever arrived first.
        """
        identity = json.dumps(
            {
                "node_id": node_id,
                "item_index": item_index,
                "name": tool.name,
                "version": tool.version,
                "arguments": arguments,
            },
            sort_keys=True,
            default=str,
        )
        with self._lock:
            seen = self._tool_occurrences.get(identity, 0)
            self._tool_occurrences[identity] = seen + 1
            return seen

    def cost_of_call(self, record: Record) -> Any:
        """Derived cost of one ``model_call`` record under this run's basis."""
        return cost_of(record, self.cost_basis)

    # -- a consultation with no answerer ------------------------------------------

    def note_no_one_to_ask(self, tool_name: str, reason: str) -> None:
        """Record that a consultation tool reported nobody to ask.

        The first such answer is what the model is told. Every later call to that tool in this
        run is answered from here instead of reaching the channel again, which is what stops an
        agent asking a question a hundred times in a run where no one can hear it.
        """
        with self._lock:
            self._no_one_to_ask.setdefault(tool_name, reason)

    def note_shelved(self, question: Any) -> None:
        """Record that this run left a question for somebody to answer later.

        Written to the run's shelf when it closes, which is what ``Pipeline.shelved`` reads.
        """
        with self._lock:
            self._shelved.append(question)

    def shelved_questions(self) -> list[Any]:
        """Every question this run left outstanding, in the order they were asked."""
        with self._lock:
            return list(self._shelved)

    def note_suspension_left(self, waiting_for: str) -> None:
        """Record that a ``Suspend`` travelled out of a tool call in this run.

        Read by :meth:`suspension_was_swallowed` when the run finishes. Nothing else uses it.
        """
        with self._lock:
            if self._suspension_left_a_call is None:
                self._suspension_left_a_call = waiting_for

    def suspension_was_swallowed(self) -> str | None:
        """What a run that finished normally had stopped for, or ``None``.

        A run reaching its end after a ``Suspend`` left a tool call means something between
        the raise and the library caught it. ``Suspend`` derives from ``BaseException`` so
        that an ``except Exception`` does not, and this catches the rest.
        """
        with self._lock:
            return self._suspension_left_a_call

    def no_one_to_ask(self, tool_name: str) -> str | None:
        """Why nobody could be asked through this tool, or ``None`` where one still can be.

        A resumed run starts empty, since the process that continues it may have somebody the
        one that stopped did not.
        """
        with self._lock:
            return self._no_one_to_ask.get(tool_name)

    def _store(
        self,
        key: str,
        kind: str,
        node_id: str,
        call_index: int,
        request: Any,
        response: Any,
        duration_ms: int | None = None,
        stream: dict[str, Any] | None = None,
        at_boundary: bool = False,
        item_index: int | None = None,
    ) -> None:
        if not self.cassette.is_recording:
            return
        # A response already redacted for the model is stored as the model saw it. Redacting
        # it again by every rule would store a string the run never used, and the replay would
        # serve that string where the recorded run had this one.
        redacted_response, _ = (
            self.redaction.redact_for_model(response)
            if at_boundary
            else self.redaction.redact(response)
        )
        outcome = self.cassette.store(
            CassetteEntry(
                key=key,
                kind=kind,
                node_id=node_id,
                call_index=call_index,
                item_index=item_index,
                recorded_at=utc_now(),
                run_id=self.run_id,
                run_seed=self.seed,
                duration_ms=duration_ms,
                stream=stream,
                request=request,
                response=redacted_response,
            )
        )
        if not outcome.written:
            return
        self.manifest.count_cassette(recorded=1)
        if outcome.diverged:
            # The identical request came back different, so both are now on file. On a hosted
            # API this is ordinary: a seed is best-effort and batching makes it so. The count
            # is what tells a reader whether this backend reproduces its own sampling.
            self.manifest.count_cassette(diverged=1)


@dataclass(frozen=True)
class NodeContext:
    """What a ``Deterministic`` or ``LLMNode`` function receives, and what a context builder
    is handed.

    Carries no model client. An ``LLMNode``'s function builds a prompt and returns it; the
    library makes the call.

    :meth:`call_tool` reaches the tools a ``Deterministic`` node declared, and is the only
    route to one. A node that declared none refuses the call.

    The last four fields describe the model call about to be made and are set only for a
    context builder. ``last_input_tokens`` is the prompt size the backend reported for the
    previous call in this node, paired with ``last_input_chars`` so a context builder can divide
    them
    for the ratio that node actually exhibited. Both are ``None`` before the first call
    completes, and the tokens are ``Unknown`` when the backend measured no prompt size.
    ``last_call_index`` and ``last_item_index`` say which call that was. Inside a fan-out the
    index counts within its item, so both are needed to name one call.
    """

    run_id: str
    node_id: str
    workspace: Path
    seed: int | None
    budget: Budget
    item_index: int | None = None
    conversation: Any = None
    """The conversation this run is a turn of, from ``Pipeline.run(conversation_id=...)``, and ``None``
    where the run is not part of one. A prompt function splats it where the history belongs::

        return [{"role": "system", "content": SYSTEM},
                *ctx.conversation,
                {"role": "user", "content": inputs["question"]}]

    Reading it is what enrols this node in the conversation: the library then writes what the
    node produces back to the thread. `docs/conversation.md` is the whole surface."""
    fetch_policy: Any = None
    """This run's copy of the pipeline's declared ``HostPolicy``, or ``None`` where the
    pipeline declares none. ``ctx.fetch_policy.admit(host, reason=...)`` brings a host into
    scope for the rest of the run."""
    last_input_tokens: int | Unknown | None = None
    last_input_chars: int | None = None
    last_call_index: int | None = None
    last_item_index: int | None = None
    _tool_caller: Callable[[str, dict[str, Any]], Any] | None = field(
        default=None, repr=False, compare=False
    )
    _access_recorder: Callable[..., None] | None = field(default=None, repr=False, compare=False)

    def call_tool(self, name: str, /, **arguments: Any) -> Any:
        """Call one of this node's tools and return what it returned.

        The call is recorded as a ``tool_call`` and served from the cassette like any other,
        so a replay reproduces it and an evaluation prices it::

            def fetch_the_page(inputs, ctx):
                return ctx.call_tool("http_fetch", url=inputs["url"])

            node = Deterministic(fetch_the_page, tools=[http_fetch()])

        The tool's name is positional, so every keyword is one of the tool's own arguments and
        a tool with a parameter called ``name`` is reachable like any other.

        The node decides that this call happens, so there is no model to correct a bad one: a
        tool raising ``ModelFacingError`` raises here rather than coming back as an
        observation. Catch it where the node can do something else, or let it end the run.

        Raises ``ConfigurationError`` naming the tools this node declared when ``name`` is not
        one of them, and when the node declared none.
        """
        if self._tool_caller is None:
            raise ConfigurationError(
                f"Node {self.node_id!r} called tool {name!r} and declared no tools. A tool "
                f"reached any other way is not recorded, not served from the cassette, and "
                f"not seen by an evaluation deciding what a rollout may execute.\n"
                f"Declare it on the node: Deterministic(fn, tools=[{name}]). Only an "
                f"AgentNode lets the model choose which tool to call."
            )
        return self._tool_caller(name, arguments)

    def record_access(
        self,
        resource: str,
        direction: str,
        *,
        inputs: Any = None,
        outputs: Any = None,
    ) -> None:
        """Record one access this node's own code made to a resource it declared.

        A store reached through ``ctx.call_tool`` is already on record. This is the same
        account for code that reaches one directly, so what the step asked for and what came
        back can be read from the trajectory either way::

            def publish(inputs, ctx):
                sent = mailer.send(inputs["body"])
                ctx.record_access("outbox", "write", inputs={"to": inputs["to"]},
                                  outputs={"sent": sent})
                return {"sent": sent}

            node = Deterministic(publish, touches="outbox")

        ``direction`` is ``"read"`` or ``"write"``. ``inputs`` is what was asked for and
        ``outputs`` what came back; both are payload fields, so the run's redaction applies and
        sampling drops them. What they hold is this node's choice, so a step that read 67,353
        rows and kept 12 records the counts rather than the rows::

            ctx.record_access("catalogue", "read", inputs={"eligible": True},
                              outputs={"rows": 67353, "kept": 12})

        ``resource`` must be one the node declared: ``Deterministic(fn, touches="outbox")``.
        Raises ``ConfigurationError`` naming what to declare when it is not, so the
        declaration and the record always name the same thing.
        """
        if self._access_recorder is None:
            raise ConfigurationError(
                f"Node {self.node_id!r} called record_access({resource!r}) and this context "
                f"records nothing. A node reached outside a run has no trajectory to write "
                f"to.\n"
                f"Run the pipeline: Pipeline([...]).run(inputs)."
            )
        if direction not in ("read", "write"):
            raise ConfigurationError(
                f"Node {self.node_id!r} recorded an access to {resource!r} in direction "
                f"{direction!r}, and the directions are 'read' and 'write'. A step that does "
                f"both records one access each way.\n"
                f'Pass one of them: ctx.record_access({resource!r}, "read", outputs=...).'
            )
        self._access_recorder(resource, direction, inputs, outputs, self.item_index)

    def now_ms(self) -> int:
        """Monotonic milliseconds, for measuring elapsed time. Use `now()` for timestamps."""
        return int(time.monotonic() * 1000)

    def now(self) -> str:
        """Wall-clock timestamp, ISO 8601 UTC."""
        return utc_now()


@dataclass(frozen=True)
class RouteContext(NodeContext):
    """What a node's ``route`` receives alongside the output it is choosing on.

    ``successors`` holds the ids this node declared, which are the only ones a route may
    return. ``iteration`` is which time round the enclosing cycle this execution was, counting
    from 1 per entry to the cycle, and is ``None`` for a node in no cycle::

        def again_or_done(output: Verdict, ctx: RouteContext) -> str:
            return "publish" if output.accepted else "draft"

    A route makes no model call and is given nothing that could. A step whose choice needs the
    model is made by the model filling a field of the output schema, which the route then
    reads.
    """

    successors: tuple[str, ...] = ()
    iteration: int | None = None


@dataclass(frozen=True, slots=True)
class ToolCallSummary:
    """One tool call an ``AgentNode`` has already made, as a finish check sees it.

    ``ok`` is false when the tool returned a model-facing failure, so a check can tell a
    lookup that found nothing from one that was never attempted. ``result`` is what the tool
    returned, or the model-facing error when it failed, so a check can test what came back
    rather than recomputing it from the arguments::

        found = {hit["doc_id"] for c in ctx.tool_calls
                 if c.name == "document_search" and c.ok
                 for hit in c.result["results"]}
    """

    name: str
    arguments: dict[str, Any]
    ok: bool
    result: Any = None


@dataclass(frozen=True, slots=True)
class FinishAttempt:
    """One rejected ``finish`` call, as the next finish check sees it.

    A check that rejects an answer the model believes it has already given produces a loop the
    model cannot escape, because nothing it can see says the last attempt was refused. Compare
    against this before rejecting again::

        if any(a.arguments == arguments for a in ctx.finish_attempts):
            return None   # already refused this once; refusing again will not change it
    """

    arguments: dict[str, Any]
    rejection: str


@dataclass(frozen=True)
class AgentContext(NodeContext):
    """What an ``AgentNode``'s prompt function, context builder and finish check receive.

    Carries no model client and no tool dispatch; the loop owns both. It adds the available
    tool names, so a prompt can describe them, ``step``, the loop iteration about to run, and
    ``tool_calls``, what this node has called so far.

    ``step`` is ``0`` for the prompt function, which runs once before the loop starts, and
    counts from ``1`` for the context builder, which runs once per iteration.

    ``tool_calls`` is empty for the prompt function and holds every call made so far when a
    finish check runs, including the ones made in the turn being finished, which is what lets a
    check reject an answer citing something the agent never opened.

    ``finish_attempts`` holds the ``finish`` calls this check has already rejected. A check that
    refuses the same answer twice has learned nothing the model can act on, so read this before
    refusing again.
    """

    tool_names: tuple[str, ...] = ()
    step: int = 0
    tool_calls: tuple[ToolCallSummary, ...] = ()
    finish_attempts: tuple[FinishAttempt, ...] = ()

    def describe_tools(self) -> str:
        return ", ".join(self.tool_names) if self.tool_names else "(none)"


# How a throttled tool is retried. Smaller than the model clients' ladder
# (`adapters/_http.py`, `Retry`), because a tool call sits inside a node's step budget and a
# 31-second block per call spends a run's wall clock on waiting. A `Retry-After` the source
# published replaces the backoff, capped the same way.
TOOL_RETRY_ATTEMPTS = 3
TOOL_RETRY_INITIAL_S = 1.0
TOOL_RETRY_MAX_S = 30.0


def _throttle_wait(attempt: int, asked_for: float | None) -> float:
    """How long to wait before attempt ``attempt``, counting the first as 0.

    What the source asked for wins, since it is the one that knows. Without a figure the
    backoff doubles from the initial. Both are capped: a source asking for an hour is asking
    for longer than a run should sit still for, and the attempts run out either way.
    """
    if asked_for is not None:
        return min(asked_for, TOOL_RETRY_MAX_S)
    return min(TOOL_RETRY_INITIAL_S * (2**attempt), TOOL_RETRY_MAX_S)


def error_object(
    exc: BaseException, *, model_facing: bool, retryable: bool = False
) -> dict[str, Any]:
    """The ``error`` object for a trajectory record.

    ``class`` is ``model_facing`` when the failure was passed to the model as data,
    ``caller_facing`` when it ended the run, and ``suspended`` where the run stopped here and
    will continue at this same operation. A suspension is not a failure, so counting
    caller-facing failures over a trajectory does not count it.
    """
    return {
        "class": _error_class(exc, model_facing=model_facing),
        "type": type(exc).__name__,
        "message": str(exc),
        "retryable": retryable,
    }


def _error_class(exc: BaseException, *, model_facing: bool) -> str:
    if isinstance(exc, Suspend):
        return "suspended"
    return "model_facing" if model_facing else "caller_facing"
