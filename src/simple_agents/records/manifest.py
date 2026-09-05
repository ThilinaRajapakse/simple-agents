"""The run manifest: what was configured, as against what happened.

``docs/run-envelope.md`` §2 is the schema of record; this module writes it. A value that is the
same for every record in a run belongs here rather than on each record: the seed, the budget,
the model pin, the prompt versions, the cost basis, the redaction rules, the cassette.

The manifest joins to the trajectory by ``run_id``. It is written when the run starts and
rewritten when it ends, so a run that crashed still has one, carrying the outcome ``error``.

FT-14 reads ``models`` for the pin. FT-27 reads ``cost_basis``, without which no cost derived
from the trajectory can be audited.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import sys
import sysconfig
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Iterable

from ..prompting import text_globals
from .trajectory import RECORD_TYPES
from .trajectory import FORMAT_VERSION as TRAJECTORY_FORMAT_VERSION

__all__ = ["MANIFEST_FORMAT_VERSION", "Manifest", "source_version"]

MANIFEST_FORMAT_VERSION = "0.43"

DEFAULT_ROLE = "agent"

_TOKEN_FIELDS = ("input_uncached", "input_cache_read", "input_cache_write", "output")


def _basis_kinds(basis: dict[str, Any] | None) -> set[str]:
    """Which kinds of cost basis a run declared, across both forms the manifest records.

    One basis gives one kind. A `by_model` mapping gives the kinds of the bases under it, so a
    reader asking whether any call was priced in device-seconds asks this rather than reading
    the two shapes itself.
    """
    if not basis:
        return set()
    if basis.get("kind") != "by_model":
        return {str(basis.get("kind"))}
    return {str(one.get("kind")) for one in (basis.get("bases") or {}).values()}


@dataclass(slots=True)
class Manifest:
    """What a run was configured with, accumulated as it proceeds.

    Constructed by the run envelope and written twice: once at the start with everything known
    then, once at the end with the outcome and the totals. Reading one back is a
    ``json.loads`` of the file at ``<run_dir>/<run_id>/manifest.json``.
    """

    run_id: str
    started_at: str
    seed: int
    budget: dict[str, Any]
    library_version: str
    trajectory_path: str
    workspace_path: str

    pipeline: str | None = None
    """Which registered pipeline this run is, from ``Pipeline.name``, and ``null`` where the
    pipeline was built outside a ``@pipeline_factory``. A run of a slice records the name of
    the pipeline it was sliced from, and ``slice`` says which nodes it held, so the two
    together identify what ran. The conformance checks that read one pipeline's runs read
    this."""

    scripted: bool = False
    """Whether the model this run called was a scripted stand-in rather than a backend, from
    the client's own ``scripted``. ``FakeModelClient`` declares it, and a project's own stub
    declares it the same way. A scripted run spent nothing and answered from a list, so
    ``runs()``, ``simple-agents report`` and the checks leave it out unless asked for it."""

    role: str = DEFAULT_ROLE
    """What the run was for, from ``RunEnvelope.role``. ``agent`` is the project's own agent
    and is what the conformance checks read; any other value is project-side work that used the
    envelope, such as a labelling pass, a judge or an ablation."""
    live: bool = False
    """Whether an end user was on the other end of this run, from ``RunEnvelope.live``. False
    is a run made while building. `docs/shipping.md` §1."""
    end_user: dict[str, Any] | None = None
    """Who the run's own consultation channel says it reaches, where the envelope replaced the
    registered one, and ``null`` where it did not. The tool entries under ``tools`` carry what
    the pipeline registered; this carries what this run was given."""
    conversation: dict[str, Any] | None = None
    """The conversation this run is a turn of, from ``Pipeline.run(conversation_id=...)``, and ``null``
    where the run is not part of one. Carries the store's ``directory``, the ``thread`` as the
    project gave it, the ``turn`` this run was, and ``carried_in``, how many earlier messages
    a node actually read. ``carried_in`` of zero on a turn past the first is a conversation
    that is being written and not read."""
    trigger: str | None = None
    """Which declared job started this run, from ``Pipeline.run(trigger=...)``, and ``null``
    where the run was asked for: a request, or the builder by hand. The value is the name of
    a ``Job`` in the project's ``Product``, which is how the view joins a run back to the
    schedule the builder agreed to."""
    evaluation: dict[str, Any] | None = None
    """Which rollout of which evaluation this run is, from ``RunEnvelope.evaluation``, and
    ``null`` for a run of the agent. Carries ``eval_id``, ``example`` and ``rollout``, so a
    rollout says what it is rather than being identified by how deep its directory sits."""
    concurrency: int = 1
    """The most calls this run could have in flight at once, from
    ``Pipeline.run(concurrency=...)``. 1 means nothing overlapped."""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    """Guards the counters. A run whose work overlaps reaches them from several threads, and
    a count read and written back without it is a count that can be lost."""

    cost_basis: dict[str, Any] | None = None
    redaction: dict[str, Any] = field(default_factory=dict)
    cassette: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] | None = None
    """The store a tool taking a `Memory` reached, or `null` where the envelope declared none.
    Holds the directory, a digest of the scope, and how many entries the store held when the
    run ended. The scope itself is not recorded: it usually identifies a person."""

    retrieval: list[dict[str, Any]] = field(default_factory=list)
    """One entry per tool that searched a `DocumentIndex`, counted when the run ended: the
    `tool`, how many `documents` the index held, how many of them have `vectors`, the `store`
    holding those and whether it is `exact`, and what `embedded_by` produced them. A run that
    adds documents leaves the count it finished with. How the index ranks is on the tool's own
    entry under `tools`, because that decides what a search returns and this does not."""

    slice: dict[str, Any] | None = None
    """What this run's pipeline is a slice of, from ``Pipeline.slice``, and ``null`` where the
    run is of a whole pipeline. Carries ``of``, the source pipeline's ``graph_fingerprint``;
    the ``nodes`` the slice holds; the ``start`` and ``end`` it was taken with, both ``null``
    where the set was named; the ids it ``dropped``; and one entry per edge in ``cut_edges``,
    each a ``from``, a ``to`` and a ``kind``. Two evaluations of two rungs of one pipeline are
    joined on ``of``."""

    nodes: list[dict[str, Any]] = field(default_factory=list)
    containers: list[dict[str, Any]] = field(default_factory=list)
    """One entry per pipeline used as a node, holding what only it declares: its budget, its
    edges in the graph that contains it, and the ids of its direct children. `nodes` holds the
    leaves alone, because a pipeline used as a node writes no `node_execution` record."""

    prompts: dict[str, dict[str, Any]] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    constants: list[dict[str, Any]] = field(default_factory=list)
    """Every module-level number the project's own code defines, reached from the node
    callables, as `Pipeline.manifest_constants` gathers it. Each entry is a `module`, a `name`
    and the `value` the run started with. Outside `behaviour_fingerprint`: a number in a module
    the pipeline imports is not something the pipeline declares, and a stamp that moved when any
    of them changed would make a stored result stale that was not."""
    configured_model: dict[str, Any] | None = None
    suspensions: list[dict[str, Any]] = field(default_factory=list)
    graph_fingerprint: str | None = None
    behaviour_fingerprint: str | None = None
    """What the pipeline declares about how it behaves, as
    `Pipeline.behaviour_fingerprint` computes it: the shape, the prompts, every `Deterministic`
    node's function version, the sampling, every tool's version and declared cost, the model each
    node calls, and the budgets. A project that keeps its results writes this beside each one,
    and reads it back from here to say which run produced which stored value. It covers the client the run was given, so a project
    computing it itself passes the same one: `pipeline.behaviour_fingerprint(model=client)`.
    Wider than `graph_fingerprint`, which is shape alone."""

    mcp: list[dict[str, Any]] = field(default_factory=list)
    """One entry per MCP server this run declared tools from: `server`, how the run `read` its
    declarations, the `drift` between what it offers now and what the recording holds, and the
    tools it offers that this project did not declare. Empty where the project declared none.

    A server's tools are read once per run and are what the agent was actually offered, so a
    server that changed under a project is readable from the run rather than from a memory of
    what it used to say (FT-43)."""

    fetch_policy: list[dict[str, Any]] = field(default_factory=list)
    """What each `HostPolicy` permitted and what it admitted while running, one entry per
    pipeline that declared one. `declared_by` is the id of that pipeline, and `null` for the
    pipeline the run was started with. Empty where the project declared none. A reachable set
    that grows during a run is not knowable from the tool declarations alone, and this is where
    it is recorded."""

    unfinished: dict[str, dict[str, int]] = field(default_factory=dict)
    """Per node, the units of work that ended without producing an output, and what they spent.

    Read off this run's own trajectory when the run ends, so a reader aggregating many runs
    opens one small file each rather than every record they wrote. A node with nothing to
    report is absent, so an empty object is a run in which every unit of work produced
    something. ``simple_agents.evaluation.unfinished_work`` is what computes it, and FT-35
    reads it over every run one pipeline made.
    """

    resume_waivers: list[str] = field(default_factory=list)
    stream_waivers: list[str] = field(default_factory=list)
    """Model clients built to accept streamed calls whose token counts the backend did not
    report. Every count on those calls is `unknown`, so a reader of the numbers has this to
    trace it to."""

    recording: dict[str, Any] = field(
        default_factory=lambda: {"payload_rate": 1.0, "payloads": "kept"}
    )
    """What the envelope's `Trajectory` was set to, and whether this run kept its payloads.
    A reader of a trajectory with `not_recorded` payloads finds the rate here."""

    ended_at: str | None = None
    outcome: str | None = None
    stopped_early: str | None = None

    _observed: dict[tuple[str, str, str | None, str | None], int] = field(
        default_factory=dict, init=False, repr=False
    )
    _counts: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _held_back_ms: int = field(default=0, init=False, repr=False)
    _tokens: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _unknown_tokens: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _cost: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _tool_spend: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _charged_cost: float | None = field(default=None, init=False, repr=False)
    _schemas: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _observed_instructions: dict[str, dict[str, int]] = field(
        default_factory=dict, init=False, repr=False
    )
    _cassette_counts: dict[str, int] = field(
        default_factory=lambda: {"hits": 0, "misses": 0, "recorded": 0, "diverged": 0},
        init=False,
        repr=False,
    )

    # -- accumulation ---------------------------------------------------------------------

    def count_record(self, record_type: str) -> None:
        """Note that a record of this type was written."""
        with self._lock:
            self._counts[record_type] = self._counts.get(record_type, 0) + 1

    def observe_model(
        self,
        *,
        backend: str,
        request_model: str,
        response_model: str | None,
        model_revision: str | None,
    ) -> None:
        """Note which model served a call.

        Recorded alongside the configured pin because a provider can serve a different model
        from the one requested, and a manifest showing only what was asked for would not say
        so.
        """
        key = (backend, request_model, response_model, model_revision)
        with self._lock:
            self._observed[key] = self._observed.get(key, 0) + 1

    def observe_tokens(self, tokens: dict[str, Any]) -> None:
        """Add one call's token counts to the run totals.

        A count the backend reported as unknown makes that total unknown for the run. Adding
        zero in its place would report a total lower than what was spent.
        """
        with self._lock:
            for name in _TOKEN_FIELDS:
                value = tokens.get(name)
                if isinstance(value, dict) and value.get("type") == "unknown":
                    self._unknown_tokens.setdefault(
                        name, str(value.get("reason") or "reported as unknown")
                    )
                elif isinstance(value, (int, float)):
                    self._tokens[name] = self._tokens.get(name, 0) + int(value)

    def _prompts_record(self) -> dict[str, dict[str, Any]]:
        """Each prompt as declared, with the fixed text this run saw it send.

        ``observed`` holds one entry per distinct instruction, ``{digest: calls}``, capped at
        `MOST_INSTRUCTIONS` with ``distinct`` carrying the true count. A step whose instruction is
        data can send thousands, and the manifest is not where they belong. Only a node's own
        prompt is counted, since only a node's own prompt has an entry here.
        """
        held = {}
        for node_id, entry in self.prompts.items():
            seen = self._observed_instructions.get(node_id) or {}
            if not seen:
                held[node_id] = entry
                continue
            ranked = sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
            held[node_id] = {
                **entry,
                "observed": dict(ranked[:MOST_INSTRUCTIONS]),
                "distinct": len(seen),
            }
        return held

    def observe_instruction(self, node_id: str, digest: str) -> None:
        """Note the instruction one call was built from, by digest.

        A step whose prompt is written in the project's code sends one instruction however many
        sections it has, so this is one digest and a count of the calls that used it. A step
        whose instruction arrives as data, which is a persona from a store or an end user's own
        words, sends a different one each time, and the count is what says so.
        """
        with self._lock:
            seen = self._observed_instructions.setdefault(node_id, {})
            seen[digest] = seen.get(digest, 0) + 1

    def observe_held_back(self, held_back_ms: int) -> None:
        """Add one call's waiting to the run total.

        ``held_back_ms`` on a model call is retry backoff and rate-limit pacing, which no
        budget is charged for. Summed here because reading it off the trajectory means adding
        a field across every model call, and a run that spent half its wall clock waiting for a
        rate-limit window looks like a slow run until that sum exists.
        """
        if held_back_ms:
            with self._lock:
                self._held_back_ms += int(held_back_ms)

    @property
    def held_back_ms(self) -> int:
        """How long this run's model calls have spent waiting, in milliseconds, so far."""
        return self._held_back_ms

    def set_cost(self, cost: dict[str, Any] | None) -> None:
        """Set the run's derived model cost. Called once, at close."""
        self._cost = cost

    def set_tool_spend(self, spend: dict[str, Any] | None) -> None:
        """Set what the run's tools cost, summed from the records. Called once, at close."""
        self._tool_spend = spend

    def set_charged_cost(self, charged: float | None) -> None:
        """Set what `max_cost` was charged over the whole run. Called once, at close.

        Model cost and tool spend together, which is what the limit bounds. `null` where
        nothing costed ran. A run measured in device-seconds reports its tool spend alone,
        which :meth:`to_json` derives.
        """
        self._charged_cost = charged

    def _money_charged(self) -> float | None:
        """The money figure `charged_cost` reports, which is what `max_cost` bounds.

        Model spend and tool spend together, in the run's one currency. A call priced under a
        device basis contributes none: device-seconds are what the run used rather than money,
        so that figure stays in `totals.cost` and the money charged is the tool spend alone.

        A run pricing some models in device-seconds and others in money is `null`, because the
        money part of a total the two were added into cannot be recovered here. `totals.cost`
        on such a run is unknown for the same reason.
        """
        kinds = _basis_kinds(self.cost_basis)
        if "device" not in kinds:
            return self._charged_cost
        if kinds != {"device"}:
            return None
        return (self._tool_spend or {}).get("amount")

    def count_cassette(
        self, *, hits: int = 0, misses: int = 0, recorded: int = 0, diverged: int = 0
    ) -> None:
        """Count one cassette outcome.

        ``diverged`` counts requests already recorded whose response came back different. A
        non-zero count means the backend does not reproduce its own sampling, so replay rather
        than the seed is what makes the run repeatable.
        """
        with self._lock:
            self._cassette_counts["hits"] += hits
            self._cassette_counts["misses"] += misses
            self._cassette_counts["recorded"] += recorded
            self._cassette_counts["diverged"] += diverged

    def register_schema(self, value: Any) -> str | None:
        """Store a schema block once and return the reference a record carries instead::

            record_params["tools_ref"] = manifest.register_schema(request.tools)

        The reference is a SHA-256 of the block, as `nodes[].schema` and `prompts` already
        use. ``None`` in gives ``None`` back, which is what a call offering no tools and no
        output schema records. A block offered on many calls is stored once.
        """
        if value is None:
            return None
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        ref = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        with self._lock:
            self._schemas.setdefault(ref, value)
        return ref

    def note_payloads_omitted(self, *, reason: str) -> None:
        """Record that this run's payload fields were dropped, and why."""
        self.recording = {**self.recording, "payloads": "omitted", "reason": reason}

    def note_cassette_dropped(self, *, reason: str) -> None:
        """Record that this run's recording was deleted, and why.

        The counts under `cassette` still say what the run recorded while it ran, so a reader
        finding calls recorded and `dropped` set knows the file is gone rather than empty.
        """
        self.cassette = {**self.cassette, "dropped": reason}

    def close(self, *, ended_at: str, outcome: str, stopped_early: str | None = None) -> None:
        """Record how the run ended. ``outcome`` is ``completed``, ``suspended``,
        ``stopped_early``, or ``error``."""
        self.ended_at = ended_at
        self.outcome = outcome
        self.stopped_early = stopped_early

    # -- serialization --------------------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        """The manifest as it is written to disk."""
        return {
            "format_version": MANIFEST_FORMAT_VERSION,
            "trajectory_format_version": TRAJECTORY_FORMAT_VERSION,
            "library_version": self.library_version,
            "run_id": self.run_id,
            "pipeline": self.pipeline,
            "role": self.role,
            "scripted": self.scripted,
            "live": self.live,
            "end_user": self.end_user,
            "evaluation": self.evaluation,
            "conversation": self.conversation,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "outcome": self.outcome,
            "stopped_early": self.stopped_early,
            "seed": self.seed,
            "concurrency": self.concurrency,
            "budget": self.budget,
            "cost_basis": self.cost_basis,
            "models": {
                "configured": self.configured_model,
                "observed": [
                    {
                        "backend": backend,
                        "request_model": request_model,
                        "response_model": response_model,
                        "model_revision": revision,
                        "calls": calls,
                    }
                    for (backend, request_model, response_model, revision), calls in sorted(
                        self._observed.items(), key=lambda item: str(item[0])
                    )
                ],
            },
            "prompts": self._prompts_record(),
            "slice": self.slice,
            "nodes": self.nodes,
            "containers": self.containers,
            "tools": self.tools,
            "constants": self.constants,
            "redaction": self.redaction,
            "recording": dict(self.recording),
            "schemas": dict(self._schemas),
            "graph_fingerprint": self.graph_fingerprint,
            "behaviour_fingerprint": self.behaviour_fingerprint,
            "fetch_policy": self.fetch_policy,
            "mcp": self.mcp,
            "unfinished": self.unfinished,
            "suspensions": self.suspensions,
            "resume_waivers": self.resume_waivers,
            "stream_waivers": self.stream_waivers,
            "cassette": {**self.cassette, **self._cassette_counts},
            "memory": self.memory,
            "retrieval": self.retrieval,
            "paths": {
                "trajectory": self.trajectory_path,
                "workspace": self.workspace_path,
            },
            "counts": {
                "records": sum(self._counts.values()),
                # Read off RECORD_TYPES rather than listed here, so a type added to the format
                # is counted without anyone remembering to add it in this module.
                **{kind: self._counts.get(kind, 0) for kind in RECORD_TYPES},
            },
            "totals": {
                "tokens": self._token_totals(),
                "cost": self._cost,
                "tool_spend": self._tool_spend,
                "charged_cost": self._money_charged(),
                "held_back_ms": self._held_back_ms,
            },
        }

    def _token_totals(self) -> dict[str, Any]:
        totals: dict[str, Any] = {}
        for name in _TOKEN_FIELDS:
            if name in self._unknown_tokens:
                totals[name] = {"type": "unknown", "reason": self._unknown_tokens[name]}
            else:
                totals[name] = self._tokens.get(name, 0)
        return totals

    def note_suspension(self, *, at: str, node_id: str, waiting_for: str) -> None:
        """Record that the run stopped here, and later that it started again.

        One entry per node that stopped, gaining ``resumed_at`` when the run continues. A run
        that stopped in several nodes at once has one entry each, so the manifest names every
        question the run is waiting on. The gap between the two is time no budget was charged
        for, which is what makes a run that waited a day on a person auditable rather than a
        wall-clock figure nothing explains.
        """
        with self._lock:
            self.suspensions.append(
                {
                    "suspended_at": at,
                    "node_id": node_id,
                    "waiting_for": waiting_for,
                    "resumed_at": None,
                }
            )

    def note_resumption(self, at: str) -> None:
        """Close every open suspension. A resume continues all the nodes the run stopped in."""
        for entry in self.suspensions:
            if entry.get("resumed_at") is None:
                entry["resumed_at"] = at

    @classmethod
    def restore(cls, raw: dict[str, Any], **overrides: Any) -> Manifest:
        """A manifest read back from disk, with its running totals intact.

        A resumed run continues one run's manifest rather than starting a second: the token
        totals, the record counts and the cassette counts are the whole run's, across every
        process it ran in.

        ``role``, ``live`` and ``end_user`` come from the file rather than from the envelope the
        resume was given, so a labelling pass that stopped to wait for a person is still a
        labelling pass when it continues, and a run a person made is still one. A manifest
        written before those fields existed reads as ``agent``, not live, and with no channel
        of its own.

        **Everything the run recorded before it stopped is read back**, including what nothing
        after the stop would write again: the ``schemas`` blocks its records reference, the
        ``mcp`` servers it read, and the ``memory`` it reached. A field left out here is one
        the resumed run's manifest drops on the floor.
        """
        manifest = cls(
            run_id=raw["run_id"],
            started_at=raw["started_at"],
            seed=raw["seed"],
            concurrency=raw.get("concurrency", 1),
            role=str(raw.get("role") or DEFAULT_ROLE),
            live=bool(raw.get("live")),
            end_user=raw.get("end_user"),
            evaluation=raw.get("evaluation"),
            conversation=raw.get("conversation"),
            trigger=raw.get("trigger"),
            memory=raw.get("memory"),
            retrieval=raw.get("retrieval") or [],
            mcp=list(raw.get("mcp") or []),
            budget=raw["budget"],
            library_version=raw["library_version"],
            slice=raw.get("slice"),
            trajectory_path=raw["paths"]["trajectory"],
            workspace_path=raw["paths"]["workspace"],
            cost_basis=raw.get("cost_basis"),
            unfinished={
                str(node_id): {str(k): int(v) for k, v in (counts or {}).items()}
                for node_id, counts in (raw.get("unfinished") or {}).items()
            },
            redaction=raw.get("redaction") or {},
            cassette=raw.get("cassette") or {},
            nodes=raw.get("nodes") or [],
            containers=raw.get("containers") or [],
            prompts=raw.get("prompts") or {},
            tools=raw.get("tools") or [],
            constants=list(raw.get("constants") or []),
            configured_model=(raw.get("models") or {}).get("configured"),
            suspensions=list(raw.get("suspensions") or []),
            graph_fingerprint=raw.get("graph_fingerprint"),
            behaviour_fingerprint=raw.get("behaviour_fingerprint"),
            fetch_policy=list(raw.get("fetch_policy") or []),
            resume_waivers=list(raw.get("resume_waivers") or []),
            stream_waivers=list(raw.get("stream_waivers") or []),
            recording=dict(raw.get("recording") or {"payload_rate": 1.0, "payloads": "kept"}),
            **overrides,
        )
        manifest._schemas.update(dict(raw.get("schemas") or {}))
        for entry in (raw.get("models") or {}).get("observed", []):
            key = (
                entry["backend"],
                entry["request_model"],
                entry["response_model"],
                entry["model_revision"],
            )
            manifest._observed[key] = int(entry["calls"])
        counts = raw.get("counts") or {}
        # Read off RECORD_TYPES for the reason `to_json` does: a type added to the format is
        # carried across a resume without anyone remembering to add it here.
        for kind in RECORD_TYPES:
            if counts.get(kind):
                manifest._counts[kind] = int(counts[kind])
        manifest._held_back_ms = int((raw.get("totals") or {}).get("held_back_ms") or 0)
        for name, value in ((raw.get("totals") or {}).get("tokens") or {}).items():
            if isinstance(value, dict):
                manifest._unknown_tokens[name] = str(value.get("reason") or "unknown")
            elif isinstance(value, (int, float)):
                manifest._tokens[name] = int(value)
        for name, value in (raw.get("cassette") or {}).items():
            if name in manifest._cassette_counts:
                manifest._cassette_counts[name] = int(value)
        return manifest

    def write(self, path: str | os.PathLike[str]) -> None:
        """Write the manifest, replacing any earlier version of it."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_json(), indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )


def _stable_text(value: Any, depth: int = 0) -> str:
    """A value rendered so that equal values give equal text in every process.

    ``repr`` is not that: most objects render with a memory address, which differs on every
    run and would make a version that changes when nothing did. Only data whose ``repr`` is
    fixed by its value is rendered; anything else contributes its type name, so a function
    closing over one is versioned by its source alone, as before.

    A filesystem path is rendered by value. Two functions closing over different files record
    different versions, which is what a version is for.
    """
    if depth > 4:
        return "..."
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return repr(value)
    if isinstance(value, os.PathLike):
        return repr(os.fspath(value))
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_stable_text(item, depth + 1) for item in value) + "]"
    if isinstance(value, (set, frozenset)):
        return "{" + ", ".join(sorted(_stable_text(item, depth + 1) for item in value)) + "}"
    if isinstance(value, dict):
        pairs = sorted(value.items(), key=lambda item: repr(item[0]))
        return (
            "{"
            + ", ".join(
                f"{_stable_text(k, depth + 1)}: {_stable_text(v, depth + 1)}" for k, v in pairs
            )
            + "}"
        )
    return f"<{type(value).__name__}>"


def _closed_over(fn: Callable[..., Any]) -> str:
    """What a closure captured, rendered by :func:`_stable_text`. Empty for a plain function."""
    cells = getattr(fn, "__closure__", None)
    if not cells:
        return ""
    names = getattr(getattr(fn, "__code__", None), "co_freevars", ())
    captured = []
    for name, cell in zip(names, cells):
        try:
            captured.append(f"{name}={_stable_text(cell.cell_contents)}")
        except ValueError:
            continue  # a cell still empty, in a function referring to itself while defined
    return "\n".join(sorted(captured))


MOST_INSTRUCTIONS = 20
"""How many distinct instructions one step carries on the manifest."""


def source_version(
    fn: Callable[..., Any],
    declared: str | None = None,
    *,
    closure: bool = True,
    text: bool = False,
) -> dict[str, Any]:
    """The version recorded for a function a node was given: its prompt, or its route.

    ``declared`` is what the node was given as ``prompt_version``. Where it is absent, the
    version is a hash of the function's source and of what it closed over, marked ``derived``,
    which changes when the function changes and identifies nothing else to a reader (FT-15).

    **What a function closed over is part of the version.** A function built by a factory has
    the source of whatever the factory returns, the same text for every call to it::

        def road(mapping):
            def route(output, ctx):
                return mapping[output]
            return route

        source_version(road({"a": "1"})) != source_version(road({"b": "2"}))

    Only captured data whose text is fixed by its value counts, so a function closing over a
    client is versioned by its source alone.

    A function whose source cannot be read, such as one defined in a REPL, records
    ``unavailable``.

    ``derived`` is the hash where a version was declared, and absent where it would equal
    ``version``, so an edit under a declaration is visible and named once::

        source_version(build_prompt, "4")
        # {'version': '4', 'source': 'declared', 'derived': 'sha256:e08ba8d1f3e1'}

    ``closure=False`` versions the source alone, which is how a `Deterministic` node's function
    is versioned: one holding state across its own calls would otherwise change version mid-run.
    ``text=True`` also versions the strings the function passes as fixed text (`text_globals`),
    which is how a prompt is versioned.
    """
    digest = _source_digest(fn, closure=closure, text=text)
    if declared:
        found = {"version": declared, "source": "declared"}
        return found if digest is None else {**found, "derived": digest}
    if digest is None:
        return {"version": None, "source": "unavailable"}
    # No `derived` where it would equal `version`, so a comparison names one edit once.
    return {"version": digest, "source": "derived"}


def _source_digest(
    fn: Callable[..., Any], *, closure: bool = True, text: bool = False
) -> str | None:
    """A hash of a function's source, what it closed over and the text it names.

    ``None`` where the source cannot be read. ``text`` adds the module-level strings the
    function passes to `Prompt` or `Section` as fixed text, so a prompt written into a constant
    beside the function is inside the version rather than outside it.
    """
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return None
    captured = _closed_over(fn) if closure else ""
    material = f"{source}\n--closed-over--\n{captured}" if captured else source
    if text:
        named = text_globals(fn)
        if named:
            written = "\n".join(f"{name}={named[name]}" for name in sorted(named))
            material = f"{material}\n--text--\n{written}"
    return f"sha256:{hashlib.sha256(material.encode('utf-8')).hexdigest()[:12]}"


# Where an installed distribution and the standard library live. A module under one of these
# was not written by the project, so its numbers are not the builder's to decide.
_INSTALLED = tuple(
    sorted(
        {
            path
            for path in (
                sysconfig.get_paths().get(name)
                for name in ("purelib", "platlib", "stdlib", "platstdlib")
            )
            if path
        }
        | {sys.base_prefix}
    )
)


def _is_the_project_s(module: ModuleType) -> bool:
    """Whether ``module`` was written by the project rather than installed into it.

    Simple Agents is excluded by name as well as by location, so a library run from a source
    checkout does not record its own constants as the project's.
    """
    if module.__name__ == "simple_agents" or module.__name__.startswith("simple_agents."):
        return False
    origin = getattr(module, "__file__", None)
    if not origin:
        return False
    try:
        resolved = Path(origin).resolve()
    except OSError:
        return False
    # Compared by path component. A prefix match on the text would put a project at
    # `/home/x/library` under an installed path at `/home/x/lib`.
    return not any(resolved.is_relative_to(where) for where in _INSTALLED)


def _imports_of(module: ModuleType) -> list[str]:
    """The modules ``module``'s own source imports, by name, relative ones resolved.

    Read from the source rather than from the namespace, because what a module imports and
    what its namespace holds are different sets: ``from .config import LIMITS`` binds a dict,
    which names no module to walk to, and the numbers beside ``LIMITS`` are what this is for.

    Both spellings of a package import are offered, since ``from . import config`` binds the
    submodule under the package's name and ``from .config import x`` names it directly. The
    caller keeps whichever is in ``sys.modules``.
    """
    try:
        tree = ast.parse(inspect.getsource(module))
    except (OSError, TypeError, SyntaxError, UnicodeDecodeError):
        return []
    package = getattr(module, "__package__", None) or ""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _base_of(node, package)
            if base:
                found.append(base)
                found.extend(f"{base}.{alias.name}" for alias in node.names)
    return found


def _base_of(node: ast.ImportFrom, package: str) -> str:
    """The module name a ``from ... import`` names, with a relative one resolved.

    ``package`` is the importing module's own, so one dot is that package and each further
    dot is one above it.
    """
    if not node.level:
        return node.module or ""
    parts = package.split(".") if package else []
    above = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
    return ".".join([*above, node.module]) if node.module else ".".join(above)


def _reached_from(modules: Iterable[ModuleType]) -> dict[str, ModuleType]:
    """``modules`` and every module of the project's they reach, keyed by name.

    A project keeps its node callables in one module and its work in others, so the modules
    the callables come from are the way in rather than the whole of it. Anything installed
    stops the walk, which is what keeps a dependency's constants out.
    """
    found: dict[str, ModuleType] = {}
    frontier = [module for module in modules if _is_the_project_s(module)]
    while frontier:
        module = frontier.pop()
        if module.__name__ in found:
            continue
        found[module.__name__] = module
        for reached in _neighbours(module):
            if reached.__name__ not in found and _is_the_project_s(reached):
                frontier.append(reached)
    return found


def _neighbours(module: ModuleType) -> list[ModuleType]:
    """Every module ``module`` reaches, through its namespace and through its imports."""
    out: list[ModuleType] = []
    for value in vars(module).values():
        if inspect.ismodule(value):
            out.append(value)
        elif inspect.isfunction(value) or inspect.isclass(value):
            held = inspect.getmodule(value)
            if held is not None:
                out.append(held)
    for name in _imports_of(module):
        held = sys.modules.get(name)
        if held is not None:
            out.append(held)
    return out


_ASSIGNED: dict[tuple[str, str, int], tuple[str, ...]] = {}


def _numeric_names(module: ModuleType) -> tuple[str, ...]:
    """The names ``module`` assigns a numeric literal to at module level, in source order.

    Read from the source rather than from the module's namespace, so a constant imported from
    somewhere else is recorded where it was written and not again beside every import of it.
    A module whose source cannot be read contributes nothing.

    Cached per module, since a run reads the same modules as the one before it.
    """
    origin = getattr(module, "__file__", None) or ""
    # The file's own mtime is in the key, so a module edited and re-imported inside one
    # process is read again rather than answered from what it used to say.
    try:
        stamp = Path(origin).stat().st_mtime_ns if origin else 0
    except OSError:
        stamp = 0
    key = (module.__name__, origin, stamp)
    held = _ASSIGNED.get(key)
    if held is not None:
        return held
    try:
        tree = ast.parse(inspect.getsource(module))
    except (OSError, TypeError, SyntaxError, UnicodeDecodeError):
        _ASSIGNED[key] = ()
        return ()
    names = [name for statement in tree.body for name in _assigned_a_number(statement)]
    found = tuple(dict.fromkeys(names))
    _ASSIGNED[key] = found
    return found


def _assigned_a_number(statement: ast.stmt) -> list[str]:
    """The names one module-level statement binds to a numeric literal, public ones only."""
    if isinstance(statement, ast.Assign):
        targets = [t.id for t in statement.targets if isinstance(t, ast.Name)]
        assigned = statement.value
    elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        targets, assigned = [statement.target.id], statement.value
    else:
        return []
    if assigned is None or not _is_a_number(assigned):
        return []
    return [name for name in targets if not name.startswith("_")]


def _is_a_number(node: ast.expr) -> bool:
    """Whether an assignment's right-hand side is a numeric literal, negative ones included.

    ``True`` is an ``int`` to Python and a flag to a reader, so it is not one.
    """
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not (isinstance(node.value, bool))
    )


def module_constants(functions: Iterable[Callable[..., Any]]) -> list[dict[str, Any]]:
    """Every module-level number the project's own code defines, reached from ``functions``.

    ``functions`` are a pipeline's node callables: its prompts, its `Deterministic` bodies, its
    routes and its tools. The modules those come from are the way in, and the project's own
    modules they import are walked from there; an installed package stops the walk::

        module_constants([build_prompt, rank])
        # [{'module': 'catalogue.ranking', 'name': 'WEIGHT', 'value': 0.0024}, ...]

    The name comes from the module's source and the value from the module as it stands when
    the run starts, so a number rebound at import time is recorded as what the run used.

    A number here changes what the agent does and was chosen by somebody. Naming it under
    `produces` on a `constant` decision is what records who (`docs/conformance.md` §2.2).
    """
    modules = _reached_from(
        found for found in (inspect.getmodule(fn) for fn in functions) if found is not None
    )
    constants: list[dict[str, Any]] = []
    for name, module in sorted(modules.items()):
        held = vars(module)
        for assigned in _numeric_names(module):
            value = held.get(assigned)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            constants.append({"module": name, "name": assigned, "value": value})
    return constants
