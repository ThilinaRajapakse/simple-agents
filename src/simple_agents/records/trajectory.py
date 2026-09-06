"""The five trajectory record types, and the writer that puts them on disk.

``docs/trajectory-format.md`` is the schema of record; this module implements
it. Where the two disagree, the document is right and this module has a bug.

Five record types, linked by ``parent_id``: ``node_execution``, ``model_call``, ``tool_call``,
``consultation``, and ``delegation``. They are not the three node kinds. Every node execution
emits one ``node_execution`` record whichever kind it was, with ``node_kind`` as a field on it.
The other four are things a node *does*: call a model, call a tool, ask the end user, hand a
subtask to a pipeline.

``parent_id`` names the record a thing happened inside: the ``node_execution`` for a call the
node made itself, the ``tool_call`` for a model call made inside a tool, and the ``delegation``
for a node execution inside a delegated pipeline. A parent is always written after its
children, so a child's ``sequence`` is lower.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, Protocol, get_args

from ..errors import ConfigurationError

PENDING_SEQUENCE = 0
"""What a record carries until the writer numbers it. Records are numbered as they are written,
so the order in the file is the order of the numbers."""

__all__ = [
    "FORMAT_VERSION",
    "PENDING_SEQUENCE",
    "Record",
    "NodeRecord",
    "ModelCallRecord",
    "RECORD_TYPES",
    "RunStartRecord",
    "ToolCallRecord",
    "ConsultationRecord",
    "ResourceAccessRecord",
    "DelegationRecord",
    "Trajectory",
    "TrajectoryWriter",
    "Redactor",
    "NullRedactor",
    "utc_now",
]

FORMAT_VERSION = "0.31"

RecordType = Literal[
    "run_start",
    "node_execution",
    "model_call",
    "tool_call",
    "consultation",
    "delegation",
    "resource_access",
]

RECORD_TYPES: tuple[str, ...] = get_args(RecordType)
"""Every record type this format version defines, in the order the format lists them.

Read from ``RecordType`` rather than written out again, so a type added to the format reaches
every reader that counts or validates by type. Adding one is routine; remembering a second list
in another module is not.
"""

SECRET_MARKER = "[redacted:secret_type]"

MAX_RECORD_DEPTH = 50

# The fields a run's payloads live in, per record type. A `consultation` carries no `inputs`
# and no `outputs`; the end user's answer is `response`.
PAYLOAD_FIELDS: dict[str, tuple[str, ...]] = {
    "run_start": ("inputs",),
    "node_execution": ("inputs", "outputs"),
    "model_call": ("inputs", "outputs"),
    "tool_call": ("inputs", "outputs"),
    "consultation": ("response",),
    "delegation": ("inputs", "outputs"),
    "resource_access": ("inputs", "outputs"),
}


def not_recorded(reason: str) -> dict[str, str]:
    """The value a payload field holds where the run did not keep it.

    Distinct from ``{"type": "unknown"}``, which is a value the agent produced, and from
    ``null``, which says a node produced nothing::

        {"type": "not_recorded", "reason": "sampling"}
    """
    return {"type": "not_recorded", "reason": reason}


def is_secret_value(value: Any) -> bool:
    """Whether a value declares itself secret by carrying ``get_secret_value``.

    ``pydantic.SecretStr``, ``SecretBytes`` and ``Secret[T]`` all match, and so does any type
    following the same convention. A value that matches is written as
    ``[redacted:secret_type]`` and never in full::

        http_fetch(headers={"authorization": SecretStr(os.environ["TOKEN"])})

    The type protects the value it wraps, not what is derived from it. Interpolating one into
    a string, as in ``f"Bearer {token.get_secret_value()}"``, produces an ordinary string that
    only the pattern rules can catch.
    """
    return callable(getattr(value, "get_secret_value", None))


def to_record_data(value: Any, *, depth: int = 0) -> Any:
    """Convert a value to the plain data a record stores, before redaction runs over it.

    Redaction walks dicts, lists and strings. Anything else is opaque to it, so a credential
    held in a field of an object reaches the file in full while the same credential in a dict
    is replaced. Converting first means the rules see every string the record will contain::

        to_record_data(FetchArgs(url="https://x", bearer="sk-live-..."))
        # {"url": "https://x", "bearer": "sk-live-..."}, which redaction then scrubs

    A secret-carrying value is left in place for the redactor to replace and list in
    ``redactions``. An object nested deeper than ``MAX_RECORD_DEPTH`` is rendered as text,
    which is what a cyclic structure reduces to.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_secret_value(value):
        return value
    if depth >= MAX_RECORD_DEPTH:
        return str(value)
    if isinstance(value, dict):
        return {k: to_record_data(v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_record_data(item, depth=depth + 1) for item in value]
    if isinstance(value, Enum):
        return to_record_data(value.value, depth=depth + 1)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return to_record_data(dump(), depth=depth + 1)
    if hasattr(value, "__dict__"):
        return to_record_data(vars(value), depth=depth + 1)
    return str(value)


def utc_now() -> str:
    """ISO 8601, UTC, millisecond precision. No local time, no epoch integers."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Record(dict[str, Any]):
    """A trajectory record.

    A plain dict subclass rather than a typed model, so an unrecognised field survives a
    round trip rather than being dropped. The constructors below enforce the schema.
    """


def _common(
    *,
    record_type: RecordType,
    record_id: str,
    run_id: str,
    parent_id: str | None,
    sequence: int,
    started_at: str,
    ended_at: str | None,
    error: dict[str, Any] | None,
    redactions: list[str],
) -> Record:
    """The fields every record carries regardless of type."""
    return Record(
        format_version=FORMAT_VERSION,
        record_type=record_type,
        record_id=record_id,
        run_id=run_id,
        parent_id=parent_id,
        sequence=sequence,
        started_at=started_at,
        ended_at=ended_at,
        error=error,
        redactions=redactions,
        omissions=[],
    )


def RunStartRecord(
    *,
    record_id: str,
    run_id: str,
    sequence: int,
    started_at: str,
    inputs: Any,
    seed: int | None,
    redactions: list[str] | None = None,
) -> Record:
    """One per run, written before the first node, carrying what the run was given.

    Every other record says what happened during the run. This one says what the run was
    asked to do, which is the input the rest of the causal chain follows from::

        started = next(r for r in read_trajectory(path) if r["record_type"] == "run_start")
        started["inputs"]        # what `Pipeline.run` was passed
        started["seed"]          # the seed the run derived everything else from

    It is written at the start rather than at the end, so a run whose process was killed still
    says what it was doing. A ``node_execution`` record lands when its node finishes, so a run
    that died inside its first node records its inputs nowhere else.

    ``inputs`` is a payload, so it is redacted like any other and is replaced by
    ``not_recorded`` on a run whose payloads were not kept.
    """
    record = _common(
        record_type="run_start",
        record_id=record_id,
        run_id=run_id,
        parent_id=None,
        sequence=sequence,
        started_at=started_at,
        ended_at=None,
        error=None,
        redactions=redactions if redactions is not None else [],
    )
    record.update(inputs=inputs, seed=seed)
    return record


def NodeRecord(
    *,
    record_id: str,
    run_id: str,
    sequence: int,
    started_at: str,
    ended_at: str | None,
    node_id: str,
    node_kind: Literal["deterministic", "llm", "agent"],
    inputs: Any,
    outputs: Any,
    seed: int | None,
    budget: dict[str, Any],
    termination: str | None,
    parent_id: str | None = None,
    route: list[str] | None = None,
    loop: dict[str, Any] | None = None,
    resumed_from: str | None = None,
    error: dict[str, Any] | None = None,
    redactions: list[str] | None = None,
) -> Record:
    """One per node execution, whichever kind the node was.

    ``parent_id`` is the ``delegation`` record this execution happened inside, and ``None``
    for a node the pipeline reached along an edge, which is the top of the tree. A pipeline
    used as a node emits no record, so its children are ``None`` too.

    ``route`` names the successors this execution handed its output to, which is what makes the
    path a run took readable from the trajectory. It is empty on the node the run returns from
    and on a node that was skipped.

    ``loop`` is the iteration this execution was, for a node inside a bounded cycle, and
    ``null`` for a node in none. ``iteration`` counts per entry to the cycle, so it is not the
    number of records this node wrote.

    ``resumed_from`` names the record of the execution this one continues, on a run that
    stopped inside the node and was resumed. Both records describe one logical execution, so a
    reader counting executions of a node counts the ones where it is ``null``.
    """
    record = _common(
        record_type="node_execution",
        record_id=record_id,
        run_id=run_id,
        parent_id=parent_id,
        sequence=sequence,
        started_at=started_at,
        ended_at=ended_at,
        error=error,
        redactions=redactions if redactions is not None else [],
    )
    record.update(
        node_id=node_id,
        node_kind=node_kind,
        inputs=inputs,
        outputs=outputs,
        seed=seed,
        budget=budget,
        termination=termination,
        route=list(route) if route is not None else [],
        loop=loop,
        resumed_from=resumed_from,
    )
    return record


def ModelCallRecord(
    *,
    record_id: str,
    run_id: str,
    parent_id: str,
    sequence: int,
    started_at: str,
    ended_at: str | None,
    backend: Literal["hosted_api", "self_hosted"],
    request_model: str,
    model_revision: str | None,
    response_model: str | None,
    params: dict[str, Any],
    seed: int | None,
    inputs: Any,
    outputs: Any,
    finish_reason: str | None,
    tokens: dict[str, Any],
    concurrent_requests: int | None,
    replayed: bool,
    cassette_key: str | None,
    context: dict[str, Any],
    recorded_duration_ms: int | None = None,
    held_back_ms: int = 0,
    rate_limit: dict[str, Any] | None = None,
    provider: dict[str, Any] | None = None,
    stream: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    redactions: list[str] | None = None,
    item_index: int | None = None,
) -> Record:
    """One model call.

    ``request_model`` is the model requested and ``response_model`` the one that served the
    response; a provider may substitute. ``backend`` determines how the identity fields are
    read and which cost basis applies.

    ``replayed`` is ``True`` when the response came from a cassette. A key can be present on a
    live call that was recorded into one, so the two fields answer different questions.

    ``context`` names the context builder that produced ``inputs.messages`` and lists every
    message it left out.

    ``rate_limit`` is what the backend said was left of the current window and is ``null``
    where it reports none; ``provider`` is whatever else it sent, and ``{}`` where it sent
    nothing.

    ``recorded_duration_ms`` is how long the live call took and ``stream`` is where its
    chunks fell: both ``null`` on a call that neither replayed nor streamed, and both carried
    from the cassette on one that did. ``held_back_ms`` is how long the call waited to be
    allowed, ``0`` where nothing waited. ``item_index`` is the fan-out item it belongs to.
    """
    record = _common(
        record_type="model_call",
        record_id=record_id,
        run_id=run_id,
        parent_id=parent_id,
        sequence=sequence,
        started_at=started_at,
        ended_at=ended_at,
        error=error,
        redactions=redactions if redactions is not None else [],
    )
    record.update(
        backend=backend,
        request_model=request_model,
        model_revision=model_revision,
        response_model=response_model,
        params=params,
        seed=seed,
        inputs=inputs,
        outputs=outputs,
        finish_reason=finish_reason,
        tokens=tokens,
        concurrent_requests=concurrent_requests,
        replayed=replayed,
        cassette_key=cassette_key,
        context=context,
        recorded_duration_ms=recorded_duration_ms,
        held_back_ms=held_back_ms,
        rate_limit=rate_limit,
        provider=provider if provider is not None else {},
        stream=stream,
        item_index=item_index,
    )
    return record


def ToolCallRecord(
    *,
    record_id: str,
    run_id: str,
    parent_id: str,
    sequence: int,
    started_at: str,
    ended_at: str | None,
    tool_name: str,
    tool_version: str | None,
    side_effect_class: str,
    inputs: Any,
    outputs: Any,
    replayed: bool,
    re_executed: bool,
    cassette_key: str | None,
    declared_cost: dict[str, Any] | None,
    spent: dict[str, Any] | None = None,
    item_index: int | None = None,
    error: dict[str, Any] | None = None,
    redactions: list[str] | None = None,
) -> Record:
    """One tool invocation.

    ``side_effect_class`` records the class in force at the time of the run. Re-declaring a
    tool later does not change what an old trajectory says.

    ``re_executed`` is true for a tool the cassette does not store, which runs again during a
    replay. Such a call reports ``replayed: false`` in a replayed run because it did run, and
    the two fields together say why no cassette entry was served.

    ``declared_cost`` is the tool's declaration, recorded whether or not this call cost
    anything. ``spent`` is what this call cost, and is ``null`` where it cost nothing: a call
    served from a cassette, one that failed, and one a cache answered all reach the tool's
    price and buy nothing. Sum ``spent`` for a run's tool spend; summing ``declared_cost``
    counts calls that never reached a vendor.

    ``item_index`` is the fan-out item this call was made for, and ``null`` outside one. A
    fan-out's items share one ``parent_id`` and can overlap, so this is what attributes a
    call to an item.
    """
    record = _common(
        record_type="tool_call",
        record_id=record_id,
        run_id=run_id,
        parent_id=parent_id,
        sequence=sequence,
        started_at=started_at,
        ended_at=ended_at,
        error=error,
        redactions=redactions if redactions is not None else [],
    )
    record.update(
        tool_name=tool_name,
        tool_version=tool_version,
        side_effect_class=side_effect_class,
        inputs=inputs,
        outputs=outputs,
        replayed=replayed,
        re_executed=re_executed,
        cassette_key=cassette_key,
        declared_cost=declared_cost,
        spent=spent,
        item_index=item_index,
    )
    return record


def ConsultationRecord(
    *,
    record_id: str,
    run_id: str,
    parent_id: str,
    sequence: int,
    started_at: str,
    ended_at: str | None,
    prompt: str,
    options: list[Any] | None,
    response: Any,
    resolution: Literal["pending", "answered", "unmatched", "declined", "unavailable", "shelved"],
    blocking: bool,
    asked: bool = True,
    about: str | None = None,
    answered_at: str | None = None,
    chose: str | None = None,
    declared_choice: str | None = None,
    read_by: str | None = None,
    reaches: str | None = None,
    answered_by: str | None = None,
    reason: str | None = None,
    answered_by_model: dict[str, Any] | None = None,
    answers: str | None = None,
    answers_run_id: str | None = None,
    item_index: int | None = None,
    error: dict[str, Any] | None = None,
    redactions: list[str] | None = None,
) -> Record:
    """The agent asking the end user something mid-run.

    ``resolution`` distinguishes ``answered``, ``unmatched``, ``declined``, ``unavailable`` and
    ``shelved``, which an empty ``response`` alone does not, and ``reason`` says why nobody
    could be asked or where a shelved question went. ``shelved`` is asked-and-outstanding.
    ``chose`` names the option the answer was, and is ``null`` on a question offering none.

    ``asked`` is ``false`` where an earlier ``unavailable`` in the same run answered this one
    without the channel being reached, which is what separates a count of records from a count
    of questions put to anybody. ``about`` is the stable name the caller gave the subject, and
    ``answered_at`` when the person said it, for a channel serving an answer it stored earlier.

    ``declared_choice`` is the option the channel said its answer was and ``chose`` what the
    tool's rule read, so the two differing means that rule read the answer another way.

    A question whose answer arrives in a later process is two records: the first carries
    ``pending``, ``blocking: false`` and a ``null`` ``response``, and the second names it in
    ``answers``, with ``answers_run_id`` where that question was asked by another run.
    Counting consultations means counting where ``answers`` is ``null``.
    ``docs/trajectory-format.md`` §5 is the field table.
    """
    record = _common(
        record_type="consultation",
        record_id=record_id,
        run_id=run_id,
        parent_id=parent_id,
        sequence=sequence,
        started_at=started_at,
        ended_at=ended_at,
        error=error,
        redactions=redactions if redactions is not None else [],
    )
    record.update(
        prompt=prompt,
        options=options,
        about=about,
        asked=asked,
        answered_at=answered_at,
        response=response,
        chose=chose,
        declared_choice=declared_choice,
        read_by=read_by,
        reaches=reaches,
        resolution=resolution,
        blocking=blocking,
        answered_by=answered_by,
        reason=reason,
        answered_by_model=answered_by_model,
        answers=answers,
        answers_run_id=answers_run_id,
        item_index=item_index,
    )
    return record


def DelegationRecord(
    *,
    record_id: str,
    run_id: str,
    parent_id: str,
    sequence: int,
    started_at: str,
    ended_at: str | None,
    node_id: str,
    invocation: int,
    graph_fingerprint: str,
    inputs: Any,
    outputs: Any,
    termination: str,
    resumed_from: str | None = None,
    item_index: int | None = None,
    error: dict[str, Any] | None = None,
    redactions: list[str] | None = None,
) -> Record:
    """One subtask an ``AgentNode``'s model handed to a delegated pipeline.

    ``node_id`` is the delegated pipeline's, so the executions it produced are the
    ``node_execution`` records whose ``node_id`` starts with it and whose ``parent_id`` is this
    record. That is what separates one invocation from the next: the ids repeat across
    invocations and the parent does not.

    ``inputs`` is what the model chose to send, validated against the type the pipeline's entry
    node reads. ``outputs`` is what the pipeline's terminal node produced, and ``null`` where it
    stopped before producing anything.

    ``invocation`` counts this delegation's calls within one execution of the calling node,
    from 1, and ``item_index`` is the fan-out item it was sent for. ``termination`` is
    ``completed``, ``budget`` where the pipeline's own budget was spent, ``rejected`` where the
    arguments did not satisfy the entry node's type, or ``suspended``. ``resumed_from`` names
    the subtask this one continues, on a run that stopped inside the delegate; both records
    describe one subtask, so a reader counting subtasks counts where it is ``null``.

    No ``side_effect_class`` and no ``declared_cost``: a pipeline declares neither. What it
    spends is on the records its nodes and tools wrote, each of which declares its own.
    """
    record = _common(
        record_type="delegation",
        record_id=record_id,
        run_id=run_id,
        parent_id=parent_id,
        sequence=sequence,
        started_at=started_at,
        ended_at=ended_at,
        error=error,
        redactions=redactions if redactions is not None else [],
    )
    record.update(
        node_id=node_id,
        invocation=invocation,
        graph_fingerprint=graph_fingerprint,
        inputs=inputs,
        outputs=outputs,
        termination=termination,
        resumed_from=resumed_from,
        item_index=item_index,
    )
    return record


def ResourceAccessRecord(
    *,
    record_id: str,
    run_id: str,
    parent_id: str,
    sequence: int,
    started_at: str,
    ended_at: str | None,
    node_id: str,
    resource: str,
    direction: Literal["read", "write"],
    inputs: Any,
    outputs: Any,
    item_index: int | None = None,
    error: dict[str, Any] | None = None,
    redactions: list[str] | None = None,
) -> Record:
    """One access a node made to a resource in its own code, rather than through a tool.

    A store reached through a tool is already on record as a ``tool_call``. This is the same
    account of an access made by plain code: which resource, which way the data went, what was
    asked for and what came back. ``resource`` is the string the node declared in ``touches=``,
    so the declaration and the record name the same thing.

    ``direction`` is ``read`` or ``write``, which a node's ``touches=`` does not say on its own.
    A step that both reads and writes records one access each way.

    ``inputs`` and ``outputs`` are payload fields like any other: they go through the run's
    redaction and are dropped by sampling. What they hold is the node's choice, so a step that
    read 67,353 rows and kept 12 can record the two counts rather than the rows.

    No ``side_effect_class`` and no ``spent``: this is an observation the node volunteered, not
    a call the library made. What a node's own code costs is not separable from the node.
    """
    record = _common(
        record_type="resource_access",
        record_id=record_id,
        run_id=run_id,
        parent_id=parent_id,
        sequence=sequence,
        started_at=started_at,
        ended_at=ended_at,
        error=error,
        redactions=redactions if redactions is not None else [],
    )
    record.update(
        node_id=node_id,
        resource=resource,
        direction=direction,
        inputs=inputs,
        outputs=outputs,
        item_index=item_index,
    )
    return record


@dataclass(frozen=True, slots=True)
class Trajectory:
    """How much of each run's trajectory is kept.

    Every run writes one whatever this is set to, so the records, their counts, their timings,
    their token figures and their seeds are always there. ``rate`` governs the payload fields
    alone: ``inputs`` and ``outputs`` on a ``node_execution``, ``model_call`` and
    ``tool_call``, and ``response`` on a ``consultation``::

        env = RunEnvelope(run_dir="runs/", trajectory=Trajectory.sampled(0.01))

    One run in a hundred keeps its payloads. In the rest they are replaced by
    ``{"type": "not_recorded", "reason": "sampling"}``, and each replaced field is named in the
    record's ``omissions`` array. **A run that errored or suspended keeps its payloads whatever
    the rate**, which is the run most worth reading.

    Which runs keep them follows from the ``run_id``, so the same run directory always answers
    the question the same way. The manifest records the rate and what this run did under
    ``recording``.

    An evaluation refuses a sampled envelope: per-node accuracy and ``absent_outputs`` are
    computed from what the trajectory holds, so sampling inside one moves the numbers rather
    than the volume (``docs/evaluation.md`` §5).
    """

    rate: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.rate, (int, float)) or isinstance(self.rate, bool):
            raise ConfigurationError(
                f"Trajectory(rate=...) takes a number between 0 and 1, not "
                f"{type(self.rate).__name__}. Pass Trajectory.sampled(0.01) to keep the "
                f"payloads of one run in a hundred, or Trajectory.full() to keep every one."
            )
        if not 0.0 <= float(self.rate) <= 1.0:
            raise ConfigurationError(
                f"Trajectory(rate={self.rate}) is outside 0 to 1. The rate is the fraction of "
                f"runs that keep their payload fields, so 0.01 keeps one run in a hundred, "
                f"1.0 keeps every run, and 0.0 keeps none."
            )

    @classmethod
    def full(cls) -> Trajectory:
        """Keep every payload on every run. The default."""
        return cls(rate=1.0)

    @classmethod
    def sampled(cls, rate: float) -> Trajectory:
        """Keep the payloads of ``rate`` of runs, chosen by ``run_id``::

            RunEnvelope(run_dir="runs/", trajectory=Trajectory.sampled(0.01))

        ``0.0`` keeps none. Counts, timings, tokens, seeds and cost stay complete at every
        rate, and so does a run that errored or suspended.
        """
        return cls(rate=float(rate))

    @property
    def samples(self) -> bool:
        """Whether any run through this loses payloads."""
        return self.rate < 1.0

    def keeps(self, run_id: str) -> bool:
        """Whether this run keeps its payloads, read off its ``run_id``.

        Deterministic, so re-reading a run directory says what happened rather than guessing::

            Trajectory.sampled(0.01).keeps("run_00f24af7eb28")
        """
        if self.rate >= 1.0:
            return True
        if self.rate <= 0.0:
            return False
        digest = hashlib.sha256(run_id.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") / 2**64 < self.rate

    def to_record(self) -> dict[str, Any]:
        """What the manifest stores under ``recording``, before the run's outcome is known."""
        return {"payload_rate": self.rate, "payloads": "kept"}


def strip_payloads(path: str | os.PathLike[str], *, reason: str = "sampling") -> tuple[int, int]:
    """Replace every payload a written trajectory holds, in place.

    Called after the writer has closed, for a run whose payloads are not being kept::

        records, fields = strip_payloads(paths.trajectory)

    Returns the number of records changed and the number of fields replaced. A payload that is
    already ``null`` is left alone, since ``null`` says a node produced nothing and is not the
    same statement as a payload that was dropped. Each replaced field is named in the record's
    ``omissions`` array.
    """
    source = Path(path)
    if not source.exists():
        return 0, 0

    changed = fields = 0
    scratch = source.with_suffix(source.suffix + ".stripping")
    with scratch.open("w", encoding="utf-8") as out:
        with source.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                omitted = _omit(record, reason)
                if omitted:
                    changed += 1
                    fields += omitted
                out.write(json.dumps(record, default=_fallback, ensure_ascii=False) + "\n")
    os.replace(scratch, source)
    return changed, fields


def _omit(record: dict[str, Any], reason: str) -> int:
    """Replace one record's payloads, recording each in ``omissions``. Returns how many."""
    omissions = list(record.get("omissions") or [])
    replaced = 0
    for name in PAYLOAD_FIELDS.get(str(record.get("record_type")), ()):
        if record.get(name) is None or name not in record:
            continue
        record[name] = not_recorded(reason)
        if name not in omissions:
            omissions.append(name)
        replaced += 1
    if replaced:
        record["omissions"] = omissions
    return replaced


class Redactor(Protocol):
    """Removes secrets from a record on its way to disk.

    Called by the writer on every record. An implementation lists what it changed in the
    record's ``redactions`` array, which is how a reader tells "this field was empty" from
    "this field was removed".
    """

    def __call__(self, record: Record) -> Record: ...


class NullRedactor:
    """Redacts nothing. The v0 default.

    Supplying a :class:`Redactor` to the writer enables redaction; nothing else changes.
    ``redactions`` is still emitted as an empty array, which states that nothing was altered.
    """

    def __call__(self, record: Record) -> Record:
        return record


class TrajectoryWriter:
    """Appends records to a JSONL file, one record per line.

    Append-only and flat, so a crashed run leaves a readable prefix rather than a corrupt
    document. One record reaches the file whole: a run whose nodes overlap writes from several
    threads, and a line interleaved with another is not readable by anything.
    """

    def __init__(self, path: str | os.PathLike[str], *, redactor: Redactor | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._redactor: Redactor = redactor if redactor is not None else NullRedactor()
        self._file = self.path.open("a", encoding="utf-8")
        self._closed = False
        self._lock = threading.Lock()

    def write(self, record: Record, number: Callable[[], int] | None = None) -> None:
        """Append one record, numbering it as it is written where ``number`` is given.

        The number is taken inside the lock that orders the file, so a record's ``sequence``
        and its position in the file agree. Taken outside it, two records written from
        different threads could be numbered in one order and land in the other.
        """
        record = Record(to_record_data(record))
        record = self._redactor(record)
        with self._lock:
            if number is not None:
                record["sequence"] = number()
            line = json.dumps(record, default=_fallback, ensure_ascii=False) + "\n"
            self._file.write(line)
            self._file.flush()

    def close(self) -> None:
        if not self._closed:
            self._file.close()
            self._closed = True

    def __enter__(self) -> TrajectoryWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_trajectory(path: str | os.PathLike[str]) -> Iterator[Record]:
    """Read a trajectory back, yielding each record as a dict in file order::

        for record in read_trajectory("runs/run_7/trajectory.jsonl"):
            if record["record_type"] == "model_call":
                print(record["request_model"], record["tokens"])

    Records for one node are found by matching ``parent_id`` to the node's ``record_id``.
    """
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield Record(json.loads(line))


def _fallback(value: Any) -> Any:
    """The last resort for a value :func:`to_record_data` did not reduce to plain data.

    A secret-carrying value reaches here when the writer has no redactor, and is written as
    the marker rather than in full. Everything else is rendered as text, which loses the
    structure but writes nothing the record path has not seen.
    """
    if is_secret_value(value):
        return SECRET_MARKER
    return str(value)
