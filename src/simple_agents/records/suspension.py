"""Stopping a run at a declared point, and starting it again in another process.

A run stops for one of three reasons: something it called raised :class:`Suspend`, a node was
declared with ``suspend_before=``, or the caller's ``stop_when=`` returned true. All three write
the same state to ``suspension.json`` in the run directory, and all three are restarted by
``Pipeline.resume``.

The library owns no execution outside a call the caller made. A suspension is a file and a
refusal, never a timer: nothing here wakes a run up.

``docs/pipeline.md`` is this module's document.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError

from ..errors import CallerFacingError, RunSuspended, Suspend
from ..graph import Join, NodeFailure
from ..nodes import FanOutResult, ItemOutcome
from ..schema import Unknown

__all__ = [
    "Suspend",
    "RunSuspended",
    "ValueCodec",
    "SuspensionState",
    "SUSPENSION_FORMAT_VERSION",
    "SUSPENSION_NAME",
]

SUSPENSION_FORMAT_VERSION = "0.5"

SUSPENSION_NAME = "suspension.json"
"""What a suspended run's state is called, inside that run's directory."""

_CLAIMED_NAME = "suspension.claimed.json"

_JSON_SCALARS = (str, int, float, bool)


@dataclass(slots=True)
class SuspensionState:
    """What a resumed run needs in order to continue.

    Read with :func:`read_state` and written with :func:`write_state`. Those two are the whole
    surface, so putting the state somewhere other than the run directory is a change to them
    and to nothing else.
    """

    run_id: str
    seed: int
    suspended_at: str
    # One entry per node that stopped, each with its own `node_id`, `waiting_for`, `options`
    # and `resume_not_before`. There is more than one where arms that were overlapping stopped
    # together, and `resume(answers=...)` is keyed by the same node ids.
    stops: list[dict[str, Any]] = field(default_factory=list)
    inputs: Any = None
    spend: dict[str, Any] = field(default_factory=dict)
    counters: dict[str, Any] = field(default_factory=dict)
    # The outermost frame, which holds the frames of everything nested below it. A level where
    # two arms stopped branches, so what is stored is a tree rather than a stack.
    frames: list[dict[str, Any]] = field(default_factory=list)

    @property
    def node_id(self) -> str:
        """The node the first stop is in. A run that stopped in several has ``stops``."""
        return str(self.stops[0]["node_id"])

    @property
    def waiting_for(self) -> str:
        """What the first stop is waiting for."""
        return str(self.stops[0]["waiting_for"])

    @property
    def options(self) -> list[str] | None:
        """The options the first stop offered, where it offered any."""
        return self.stops[0].get("options")

    @property
    def resume_not_before(self) -> str | None:
        """The earliest any stop may be continued, which is the latest of them."""
        times = [stop.get("resume_not_before") for stop in self.stops]
        found = sorted(t for t in times if t)
        return found[-1] if found else None

    def to_json(self) -> dict[str, Any]:
        return {
            "format_version": SUSPENSION_FORMAT_VERSION,
            "run_id": self.run_id,
            "seed": self.seed,
            "suspended_at": self.suspended_at,
            "stops": self.stops,
            "inputs": self.inputs,
            "spend": self.spend,
            "counters": self.counters,
            "frames": self.frames,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> SuspensionState:
        found = str(raw.get("format_version"))
        if found != SUSPENSION_FORMAT_VERSION:
            raise CallerFacingError(
                f"This suspended run was written in suspension format {found}, and this "
                f"version of the library reads {SUSPENSION_FORMAT_VERSION}. The state holds "
                f"values in flight, so reading it under a format it was not written for would "
                f"hand a node something the run never produced.\n"
                f"Resume it with the library version that wrote it, or start the run again."
            )
        return cls(
            run_id=raw["run_id"],
            seed=raw["seed"],
            suspended_at=raw["suspended_at"],
            stops=list(raw["stops"]),
            inputs=raw["inputs"],
            spend=raw["spend"],
            counters=raw["counters"],
            frames=raw["frames"],
        )

    @property
    def ready(self) -> bool:
        """Whether the time this run is waiting for has passed. True where it waits on a
        person rather than on a clock."""
        return self.wait_seconds() <= 0

    def wait_seconds(self) -> float:
        """How long is left before this run may be resumed, or ``0`` where it may be now."""
        if not self.resume_not_before:
            return 0.0
        left = (
            datetime.fromisoformat(self.resume_not_before.replace("Z", "+00:00"))
            - datetime.now(timezone.utc)
        ).total_seconds()
        return max(0.0, left)


def write_state(run_root: Path, state: SuspensionState, redaction: Any = None) -> Path:
    """Write one suspended run's state into its run directory, and return where it went.

    The state carries a node's conversation verbatim, so it goes through the run's redaction
    rules like every other recorded value.
    """
    body: Any = state.to_json()
    if redaction is not None:
        body, _ = redaction.redact(body)
    path = Path(run_root) / SUSPENSION_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    return path


def read_state(run_root: Path) -> SuspensionState | None:
    """One suspended run's state, or ``None`` where that run is not suspended."""
    path = Path(run_root) / SUSPENSION_NAME
    if not path.exists():
        return None
    return SuspensionState.from_json(json.loads(path.read_text(encoding="utf-8")))


def claim_state(run_root: Path) -> SuspensionState:
    """Take this suspension, so nothing else can resume the same run.

    The file is renamed before anything runs. A rename is atomic on one filesystem, so two
    workers reading the same run directory cannot both continue the run and both write into
    its trajectory. The second gets the refusal below.

    A state this version cannot read is put back before the refusal is raised, so the run is
    still listed by :func:`Pipeline.suspensions` and can be resumed by a version that reads it.
    """
    path = Path(run_root) / SUSPENSION_NAME
    claimed = Path(run_root) / _CLAIMED_NAME
    try:
        os.rename(path, claimed)
    except FileNotFoundError:
        raise CallerFacingError(
            f"There is no suspended run in {run_root}. Either the run was never suspended, or "
            f"it has already been resumed, or another worker took it first.\n"
            f"Pipeline.suspensions(run_dir) lists the runs that are waiting."
        ) from None
    try:
        return SuspensionState.from_json(json.loads(claimed.read_text(encoding="utf-8")))
    except Exception:
        release_claim(run_root)
        raise


def discard_claim(run_root: Path) -> None:
    """Remove a claimed suspension, once the run it belonged to has moved past it."""
    Path(run_root, _CLAIMED_NAME).unlink(missing_ok=True)


def release_claim(run_root: Path) -> None:
    """Put a claimed suspension back, for a resume that refused before running anything."""
    claimed = Path(run_root) / _CLAIMED_NAME
    if claimed.exists():
        os.replace(claimed, Path(run_root) / SUSPENSION_NAME)


class ValueCodec:
    """Turns a value in flight into data a resumed run rebuilds the same value from.

    The type is never written to the file. It comes from the declared graph: a value produced
    by node ``hunt`` is rebuilt with the schema ``hunt`` declares, so renaming the class is
    invisible and a schema that changed fails on the way back in rather than handing the next
    node a ``dict``.

    ``schema_of`` takes a node id and returns that node's ``output_schema``, or ``None`` for a
    node that declares none. A value from a node with no schema has to be plain data: ``None``,
    a string, a number, a boolean, or a list or dict of those.
    """

    def __init__(self, schema_of: Any, in_edges: Any) -> None:
        self._schema_of = schema_of
        self._in_edges = in_edges

    # -- out --------------------------------------------------------------------------------

    def encode(self, value: Any, *, source: str | None) -> Any:
        """``value``, produced by node ``source``, as data.

        Raises :class:`CallerFacingError` naming the node when the value cannot cross a
        suspend point.
        """
        if value is None:
            return {"kind": "none"}
        if isinstance(value, Unknown):
            # Tagged ahead of the schema path, so a node reporting absence round-trips whether
            # or not its schema is the thing that admits absence.
            return {"kind": "unknown", "reason": value.reason}
        if isinstance(value, Join):
            record = value.to_record()
            return {
                "kind": "join",
                "node_id": value.node_id,
                "absent": record["absent"],
                "edges": {key: self.encode(edge, source=key) for key, edge in value.items()},
            }
        if isinstance(value, NodeFailure):
            return {
                "kind": "node_failure",
                "node_id": value.node_id,
                "error": value.error,
                "attempts": value.attempts,
                "inputs": self.encode(value.inputs, source=self._sole_source(value.node_id)),
            }
        if isinstance(value, FanOutResult):
            return {
                "kind": "fan_out",
                # Carried past the fan-out from the node before it, so it is written down
                # against no schema, the same rule the items themselves cross under.
                "kept": {
                    key: self.encode(carried, source=None) for key, carried in value.kept.items()
                },
                "items": [
                    {
                        "index": outcome.index,
                        "item": self.encode(outcome.item, source=None),
                        **(
                            {"value": self.encode(outcome.value, source=source)}
                            if outcome.ok
                            else {"error": outcome.error}
                        ),
                    }
                    for outcome in value.outcomes
                ],
            }

        schema = self._schema_of(source) if source is not None else None
        if schema is not None and _fits(schema, value):
            return {
                "kind": "typed",
                "value": _adapter(schema).dump_python(value, mode="json", warnings="error"),
            }
        if _is_plain_data(value):
            return {"kind": "data", "value": value}
        raise self._refusal(value, source, schema)

    # -- back in ----------------------------------------------------------------------------

    def decode(self, payload: Any, *, source: str | None) -> Any:
        """The value ``encode`` was given, rebuilt against the declared graph."""
        kind = payload["kind"]
        if kind == "none":
            return None
        if kind == "data":
            return payload["value"]
        if kind == "unknown":
            return Unknown(reason=payload["reason"])
        if kind == "typed":
            schema = self._schema_of(source) if source is not None else None
            if schema is None:
                raise CallerFacingError(
                    f"The suspended run stored a value from node {source!r} against that "
                    f"node's output schema, and the pipeline being resumed declares none for "
                    f"it. The value cannot be rebuilt.\n"
                    f"Resume against the pipeline the run was started with, or declare the "
                    f"same output_schema= on {source!r}."
                )
            return _adapter(schema).validate_python(payload["value"])
        if kind == "join":
            return Join(
                {key: self.decode(edge, source=key) for key, edge in payload["edges"].items()},
                node_id=payload["node_id"],
                absent=frozenset(payload["absent"]),
            )
        if kind == "node_failure":
            return NodeFailure(
                node_id=payload["node_id"],
                inputs=self.decode(payload["inputs"], source=self._sole_source(payload["node_id"])),
                error=payload["error"],
                attempts=payload["attempts"],
            )
        if kind == "fan_out":
            return FanOutResult(
                kept={
                    key: self.decode(carried, source=None)
                    for key, carried in (payload.get("kept") or {}).items()
                },
                outcomes=tuple(
                    ItemOutcome(
                        index=item["index"],
                        item=self.decode(item["item"], source=None),
                        value=(
                            self.decode(item["value"], source=source) if "value" in item else None
                        ),
                        error=item.get("error"),
                    )
                    for item in payload["items"]
                ),
            )
        raise CallerFacingError(
            f"A suspended run holds a value tagged {kind!r}, which this version of the library "
            f"does not read. The file was written by a different version.\n"
            f"Resume it with the version that wrote it, or start the run again."
        )

    # -- helpers ----------------------------------------------------------------------------

    def _sole_source(self, node_id: str) -> str | None:
        """The one node whose output reaches ``node_id``, or ``None`` where more than one does.

        A node with several in-edges receives a ``Join``, which names its own sources, so only
        the single-edge case needs looking up.
        """
        incoming = self._in_edges(node_id)
        return incoming[0] if len(incoming) == 1 else None

    def _refusal(self, value: Any, source: str | None, schema: Any) -> CallerFacingError:
        named = f"Node {source!r} produced" if source else "The run was given"
        declared = (
            f"It declares output_schema={getattr(schema, '__name__', schema)!r}, and the "
            f"value does not validate against it. "
            if schema is not None
            else ""
        )
        return CallerFacingError(
            f"{named} a {type(value).__name__}, which cannot cross a suspend point. {declared}"
            f"A resumed run rebuilds the value from the schema the node declares, so a value "
            f"with no schema behind it has to be plain data.\n"
            f"Declare what the node returns with output_schema=, which every node kind takes, "
            f"or return plain data: None, a string, a number, a boolean, or a list or dict of "
            f"those."
        )


def _adapter(schema: Any) -> TypeAdapter[Any]:
    """A validator for whatever a node declared. Handles a model, a union and an alias."""
    return TypeAdapter(schema)


def _fits(schema: Any, value: Any) -> bool:
    """Whether ``value`` is what ``schema`` describes, checked strictly.

    Strict, because serializing is not a test of the type. Pydantic dumps a model of one class
    against another class's schema by taking whatever fields line up, which for two models with
    no field in common produces ``{}`` and no warning, and a resumed run would then receive a
    value the live run never produced. Strict validation refuses the same case.
    """
    try:
        _adapter(schema).validate_python(value, strict=True)
    except (ValidationError, PydanticSerializationError, TypeError, ValueError):
        return False
    return True


def _is_plain_data(value: Any) -> bool:
    """Whether a value is already what JSON holds, all the way down."""
    if value is None or isinstance(value, _JSON_SCALARS):
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_plain_data(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_plain_data(item) for key, item in value.items())
    return False
