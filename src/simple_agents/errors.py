"""Errors, split by who is expected to act on them.

The split is made by the tool author at authoring time, not by the loop at run time. The loop
cannot tell whether an empty result means "the search found nothing, try a different query"
or "the search index is unreachable". Only the tool author can.

Getting the split wrong produces one of two failures. Handling every exception as
model-facing hides a broken dependency behind a confident answer. Handling every exception as
caller-facing ends runs that the model could have recovered from.
"""

from __future__ import annotations

from typing import Any, Sequence


class SimpleAgentsError(Exception):
    """Base for everything the library raises."""


class CallerFacingError(SimpleAgentsError):
    """Infrastructure is broken and the run is invalid.

    Raised, never passed to the model.
    """


class ModelFacingError(SimpleAgentsError):
    """A tool failed in a way the model can reasonably react to.

    Carried as data into the trajectory and the context rather than propagated. Raise it
    from a tool for an empty result set, a 404, or a malformed response.

    ``retryable`` is recorded on the tool call and read by nothing else: the library does not
    retry on it, and it is there for whoever reads the trajectory afterwards. The failure the
    library does retry is :class:`Throttled`.
    """

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class Throttled(ModelFacingError):
    """A source refused because it is being asked too often, and will answer later.

    Raise it from a tool where the failure is the rate rather than the request: a 429, a 503,
    or a provider saying to come back. **The library waits and calls the tool again** rather
    than passing it to the model, because a throttle answered as data reads as the source
    having nothing, and an agent told that stops looking::

        raise Throttled(
            "example.com is rate limiting this agent.",
            retry_after_s=retry_after_seconds(response.headers.get("Retry-After")),
        )

    ``retry_after_s`` is what the source asked for, where it said. Without one the wait
    doubles from a second. When the attempts are spent the failure does reach the model,
    saying the source was busy, so an agent can report that rather than absence.

    A 404, an empty result set and a malformed response are ``ModelFacingError``: the request
    was wrong, and repeating it answers the same way.
    """

    def __init__(self, message: str, *, retry_after_s: float | None = None) -> None:
        super().__init__(message, retryable=True)
        self.retry_after_s = retry_after_s


class SimpleAgentsWarning(UserWarning):
    """A run will proceed, but something it records is weaker than it could be.

    Raised through ``warnings.warn`` rather than as an exception, for a condition the caller
    can fix without the run being wrong: a backend that reports no cached-token split, for
    instance. What was lost is also recorded on the affected records, so a trajectory read
    later says the same thing the warning did.
    """


class ConfigurationError(CallerFacingError):
    """The project is wired up wrongly, and it was detectable before the run started.

    Raised at construction rather than at run time: a loop with no budget, an output schema
    with no `unknown` branch, a tool with no declared side-effect class.
    """


class StreamUsageMissing(CallerFacingError):
    """A streamed response carried no token counts, and the client did not waive them.

    Raised by an adapter, which knows the backend and its own waiver argument but not which
    node made the call. The library catches it where the call was made and adds the node, the
    call index, and which of this run's budget axes and cost basis the missing counts affect::

        raise StreamUsageMissing(message, model="my-model-v2", adapter="MyClient")

    An adapter that reports usage on a stream never raises it. One whose backend does not
    should, rather than recording zeros: a token count of zero and a token count that was
    never reported price and bound differently, and only one of them is true.

    ``summary`` is the first sentence, without the fixes, so the library can rewrite the
    message around it rather than repeating what the adapter already said.
    """

    def __init__(
        self, message: str, *, model: str, adapter: str, summary: str | None = None
    ) -> None:
        super().__init__(message)
        self.model = model
        self.adapter = adapter
        self.summary = summary if summary is not None else message


class Suspend(BaseException):
    """Raised to stop the run here and continue it later, in another process.

    It derives from ``BaseException``, as ``SystemExit`` and ``KeyboardInterrupt`` do, so that
    an ``except Exception`` around a call does not catch it. A run that finishes after one was
    raised is refused.

    Raise it from a tool, from a ``Deterministic`` function, from an ``LLMNode`` prompt
    function, or from a ``ModelClient``. The commonest place is the channel a ``consult`` tool
    asks through, when the person it asks is not waiting at a terminal::

        def ask_by_email(question, options, about):
            send_email(question, options)
            raise Suspend(waiting_for=question, options=options)

        registry.add(consult(ask_by_email))

    ``waiting_for`` is what the run is waiting on. It is written to ``suspension.json`` and
    reported by ``Pipeline.suspensions``, so whoever finds the run later can tell what it needs.

    ``resume_not_before`` is an ISO 8601 UTC timestamp, for a run waiting on a clock rather than
    on a person, such as one that has spent a monthly token quota::

        raise Suspend(waiting_for="monthly token quota",
                      resume_not_before="2026-09-01T00:00:00Z")

    ``Pipeline.resume`` refuses before that time and says how long is left. Nothing in the
    library counts it down.

    The run then ends by raising :class:`RunSuspended`, which the caller sees and which is an
    ordinary ``Exception``. A ``Suspend`` is never retried and never follows ``on_error``: the
    node did not fail.
    """

    def __init__(
        self,
        *,
        waiting_for: str,
        options: Sequence[str] | None = None,
        resume_not_before: str | None = None,
        payload: Any = None,
    ) -> None:
        self.waiting_for = waiting_for
        self.options = list(options) if options is not None else None
        self.resume_not_before = resume_not_before
        self.payload = payload
        # Filled by the library as the exception travels out, for a stop inside an agent
        # loop: what that node held when it stopped, which call was waiting, and where the
        # question was recorded. Nothing raising a Suspend sets these.
        self.node_state: dict[str, Any] | None = None
        self.tool_occurrence: int | None = None
        self.asked_record_id: str | None = None
        super().__init__(waiting_for)


class RunSuspended(CallerFacingError):
    """The run stopped and its state was written. It has produced no output yet.

    Raised by ``Pipeline.run`` in place of returning a ``RunResult``, so a caller that did not
    plan for a suspension stops rather than reading an output that is ``None``::

        try:
            result = pipeline.run(inputs, envelope=env, model=client)
        except RunSuspended as stop:
            queue.put({"run_id": stop.run_id, "question": stop.waiting_for})

    The manifest and the trajectory are written, as they are for a run stopped by its budget.
    ``state_path`` is the ``suspension.json`` holding what is needed to continue, and ``run_id``
    is what ``Pipeline.resume`` is called with.
    """

    def __init__(
        self,
        *,
        run_id: str,
        state_path: Any,
        waiting_for: str,
        node_id: str,
        options: Sequence[str] | None = None,
        resume_not_before: str | None = None,
        stops: Sequence[dict] = (),
    ) -> None:
        self.run_id = run_id
        self.state_path = state_path
        self.waiting_for = waiting_for
        self.node_id = node_id
        self.options = list(options) if options is not None else None
        self.resume_not_before = resume_not_before
        self.stops = list(stops)
        """Every node the run stopped in, each with its own ``node_id``, ``waiting_for``,
        ``options`` and ``resume_not_before``. More than one where arms that were overlapping
        stopped together, and ``resume(answers=...)`` is keyed by the same node ids."""
        when = f" It cannot be resumed before {resume_not_before}." if resume_not_before else ""
        if len(self.stops) > 1:
            others = ", ".join(repr(stop["node_id"]) for stop in self.stops)
            super().__init__(
                f"Run {run_id} suspended in {len(self.stops)} nodes at once ({others}). Its "
                f"state is in {state_path}, and it has produced no output yet. `stops` says "
                f"what each is waiting for. Continue it with "
                f"Pipeline.resume({run_id!r}, envelope=..., model=..., answers={{...}}), "
                f"keyed by node, against the same pipeline this run was started with."
            )
            return
        super().__init__(
            f"Run {run_id} suspended at node {node_id!r}, waiting for: {waiting_for}.{when} "
            f"Its state is in {state_path}, and it has produced no output yet. Continue it "
            f"with Pipeline.resume({run_id!r}, envelope=..., model=..., answer=...), against "
            f"the same pipeline this run was started with."
        )


class LeftTheSlice(CallerFacingError):
    """The run reached an edge whose other end is outside the slice, and ended there.

    Raised by ``Pipeline.run`` on a pipeline produced by ``Pipeline.slice``, in place of
    returning a ``RunResult``. A slice holds part of a graph, so a route may select an arm the
    slice does not hold, and a node may fail with its ``on_error`` handler outside it. The run
    is not sent somewhere it would not have gone; it ends::

        try:
            result = rung.run(inputs, envelope=env, model=client)
        except LeftTheSlice as stop:
            print(f"{stop.node_id} went to {stop.target}, which this rung does not hold")

    The manifest and the trajectory are written, as they are for a run stopped by its budget.
    The manifest records ``outcome`` as ``stopped_early`` and ``stopped_early`` as
    ``left_the_slice``, and the node's record carries the same ``termination``.

    An evaluation catches this rather than raising: the rollout is left out of every figure
    under ``left_the_slice``, and each figure reports the count beside it.
    """

    def __init__(self, *, node_id: str, target: str, kind: str = "successor") -> None:
        self.node_id = node_id
        self.target = target
        self.kind = kind
        super().__init__(
            f"Node {node_id!r} went to {target!r}, which is outside this slice of the "
            f"pipeline, so the run ended there and produced no output.\n"
            f"This is what a slice does at its boundary rather than a fault. To measure the "
            f"path through {target!r} as well, take a slice that holds it: "
            f"pipeline.slice(nodes=[..., {target!r}])."
        )
