"""The run envelope: where a run's artifacts go and what governs them.

A ``RunEnvelope`` holds what stays the same across runs of one project. Values that change
from run to run, the input and the seed, are arguments to ``Pipeline.run``, so no setting has
two places it could come from.

Each run gets a directory under ``run_dir`` holding its manifest, its trajectory, and a
workspace scoped to it::

    env = RunEnvelope(
        run_dir="runs/",
        cost_basis=PriceBasis(currency="USD", input_uncached_per_mtok=3.0,
                              output_per_mtok=15.0),
        redaction=Redaction(secret_env=["MISTRAL_API_KEY"]),
        cassette=Cassette.record("cassettes/qa.jsonl"),
    )

    result = pipeline.run(inputs, envelope=env, model=client, seed=41)

An evaluation reuses one envelope for every rollout and varies the seed.

``runs()`` reads those directories back, which is the other half of writing them::

    for run in runs("runs/"):
        print(run.run_id, run.outcome, run.outputs_of("report"))
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .records.cassette import Cassette, CassetteMode
from .records.conversation import ConversationStore
from .cost import CostBases
from .errors import ConfigurationError
from .records.manifest import DEFAULT_ROLE
from .memory import MemoryStore
from .redaction import Redaction
from .schema import decode_answer
from .tools import ANSWERED_BY
from .records.trajectory import Trajectory, read_trajectory

__all__ = [
    "EVAL_BUCKET",
    "RESERVED_BUCKETS",
    "EvaluationRef",
    "RunEnvelope",
    "RunPaths",
    "RunHandle",
    "evaluation_dir",
    "find_run",
    "rollouts_under",
    "is_a_rollout",
    "manifest_paths",
    "narrowed",
    "runs",
]

LIVE_BUCKET = "live"
DEV_BUCKET = "dev"
EVAL_BUCKET = "eval"

RESERVED_BUCKETS = (LIVE_BUCKET, DEV_BUCKET, EVAL_BUCKET)
"""The directory names under ``run_dir`` the library writes into itself.

A project's own ``role`` names its own directory beside them, so these three are refused as
role names rather than being silently merged with runs the library placed there.
"""


def _today() -> str:
    """The UTC date a run's directory is filed under, as ``YYYY-MM-DD``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass(frozen=True, slots=True)
class EvaluationRef:
    """Which rollout of which evaluation a run is.

    An evaluation sets this on the envelope it gives each rollout, and the manifest records it,
    so a rollout says what it is rather than being identified by how deep its directory sits::

        ref = EvaluationRef(eval_id="eval_a1226bc495df", example="q4", rollout=2)

    ``runs()`` reads it to tell a rollout from a run of the agent. A manifest written before
    format ``0.35`` carries none, and those are recognised by their depth instead.
    """

    eval_id: str
    example: str
    rollout: int
    turn: int = 1
    """Which turn of the rollout's conversation this run was, and 1 for a rollout that is one
    run. An example carrying ``turns`` is scored on its last, so this is what says which."""

    def to_json(self) -> dict[str, Any]:
        return {
            "eval_id": self.eval_id,
            "example": self.example,
            "rollout": self.rollout,
            "turn": self.turn,
        }

    @classmethod
    def from_json(cls, raw: Any) -> "EvaluationRef | None":
        """The reference a manifest carries, or ``None`` where it carries none."""
        if not isinstance(raw, Mapping):
            return None
        eval_id = raw.get("eval_id")
        if not isinstance(eval_id, str) or not eval_id:
            return None
        try:
            rollout = int(raw.get("rollout") or 0)
        except (TypeError, ValueError):
            rollout = 0
        try:
            turn = int(raw.get("turn") or 1)
        except (TypeError, ValueError):
            turn = 1
        return cls(
            eval_id=eval_id,
            example=str(raw.get("example") or ""),
            rollout=rollout,
            turn=turn,
        )


def _declaring(end_user: Any, answered_by: str | None) -> Any:
    """A channel carrying who it reaches, for the one a run supplies rather than registers."""
    if answered_by is None:
        return end_user
    if isinstance(end_user, Mapping):
        raise ConfigurationError(
            f"with_end_user({{...}}, answered_by={answered_by!r}) gives one declaration to "
            f"{len(end_user)} channels, and each of them reaches somebody different.\n"
            f"Declare each where it is written: consult(ask, answered_by='end_user'), or "
            f"`ask.answered_by = 'end_user'` beside a channel this run supplies."
        )
    if answered_by not in ANSWERED_BY:
        raise ConfigurationError(
            f"with_end_user(answered_by={answered_by!r}) is not one of "
            f"{', '.join(ANSWERED_BY)}. Declare the closest one: 'end_user' for the people the "
            f"agent is for, 'builder' for the project's own author standing in for them, "
            f"'coding_agent', 'simulated' for a model playing them, 'canned' for a fixed "
            f"answer, 'nobody' for a channel that answers nothing."
        )

    def declared(question: Any, options: Any = None, about: Any = None) -> Any:
        return end_user(question, options, about)

    declared.answered_by = answered_by  # type: ignore[attr-defined]
    return declared


def _refuse_an_undeclared_end_user(end_user: Any) -> None:
    """Refuse a replacement channel that does not say who it reaches.

    Every consultation records who answered it, and the answer comes from the channel's own
    declaration. A channel supplied here with none would leave the run recording whoever the
    pipeline registered, which is the reader that did not answer.

    A run answering more than one person supplies a channel per name, and each one declares.
    """
    if isinstance(end_user, Mapping):
        for name, one in end_user.items():
            if not str(name).strip():
                raise ConfigurationError(
                    "RunEnvelope(end_user={...}) was given an answerer with an empty name. "
                    "The names are the ones the consult tools declare in reaches=, and a tool "
                    "asks the answerer whose name matches its own.\n"
                    "Key them: env.with_end_user({'requester': ask_analyst, "
                    "'approver': ask_director})."
                )
            _refuse_an_undeclared_end_user(one)
        return
    if getattr(end_user, "answered_by", None) is not None:
        return
    if getattr(end_user, "playing", None) is not None:
        raise ConfigurationError(
            f"RunEnvelope(end_user={type(end_user).__name__}(...)) takes a channel, which is "
            f"a function of the question, the offered options and what it is about. This one "
            f"answers as a "
            f"different person on every rollout, so an evaluation binds it rather than a "
            f"single run.\n"
            f"Pass it there instead: suite.run(envelope=env, model=client, split='held_out', "
            f"k=3, end_user={type(end_user).__name__}(model=cheap))."
        )
    raise ConfigurationError(
        f"RunEnvelope(end_user={end_user!r}) does not say who it reaches, so every "
        f"consultation in the run would record the channel the pipeline registered rather "
        f"than the one that answered.\n"
        f"Declare it: env.with_end_user(channel, answered_by='builder'). unattended() "
        f"declares its own."
    )


MANIFEST_NAME = "manifest.json"
TRAJECTORY_NAME = "trajectory.jsonl"
WORKSPACE_NAME = "workspace"


FINISHED_OUTCOMES = ("completed", "stopped_early")

_TAIL_BYTES = 4 * 1024 * 1024
"""How much of a trajectory's end is read to date its last record.

One record can be megabytes, so the file is not parsed to answer when it was last written to.
The timestamps are matched out of the tail and the latest is taken.
"""

_STAMP = re.compile(rb'"(?:started_at|ended_at)":\s*"([0-9]{4}-[0-9]{2}-[0-9]{2}T[^"]+)"')

RUNNING = "running"
ABANDONED = "abandoned"
LIVENESS_UNKNOWN = "unknown"

SILENT_FOR_S = 3600.0
"""How long a run declaring no wall clock may write nothing and still read as running.

A run writes a record for every model call, every tool call and every step, so silence is what
there is to read where the run set no bound on itself. An hour is longer than any single call
this library has measured, so it reports `running` rather than guessing on a slow one.
"""

ABANDONED_GRACE_S = 3600.0
"""How far past its own declared wall clock a run may be and still read as running.

`max_wall_clock_ms` is checked between steps rather than inside a call, so a run held inside
one long call passes its own bound while still executing. What it can overshoot by is one
call, which a client's own timeout bounds, so the slack is a fixed margin and not a share of
the budget: scaling it would give a run declaring four hours sixteen hours of slack, for an
overshoot that cannot exceed minutes either way.
"""


@dataclass(slots=True)
class RunHandle:
    """One run on disk, read back.

    Produced by :func:`runs`. Holds no file open and executes nothing::

        run = runs("runs/")[0]
        run.run_id                    # 'run_20260809T014233Z_a3f92c1d'
        run.outcome                   # 'completed'
        run.manifest["totals"]        # tokens, cost and waiting for the whole run
        run.outputs_of("report")      # what the `report` node last produced

    ``manifest`` is ``{}`` and ``outcome`` is ``None`` on a run whose manifest could not be
    parsed, with ``unreadable`` naming the reason. Such a run is still listed, because a
    project with one broken manifest has a run and reporting none would say otherwise.
    """

    path: Path
    manifest: dict[str, Any]
    unreadable: str | None = None
    _outputs: dict[str, Any] | None = field(default=None, init=False, repr=False)

    @property
    def run_id(self) -> str:
        """The run's id, which is also its directory name."""
        recorded = self.manifest.get("run_id")
        return str(recorded) if recorded else self.path.name

    @property
    def outcome(self) -> str | None:
        """``completed``, ``stopped_early``, ``suspended`` or ``error``.

        ``None`` on a run still executing, and on one whose manifest could not be read.
        """
        recorded = self.manifest.get("outcome")
        return str(recorded) if recorded is not None else None

    @property
    def role(self) -> str:
        """What the run was for, from the envelope that wrote it.

        ``agent`` on a run of the project's own agent, and on a run written before the
        manifest carried the field. Any other value is project-side work: a labelling pass, a
        judge, an ablation::

            labelling = [run for run in runs("runs/") if run.role == "labelling"]
        """
        recorded = self.manifest.get("role")
        return str(recorded) if recorded else DEFAULT_ROLE

    @property
    def pipeline(self) -> str | None:
        """Which registered pipeline this run is, or ``None`` where it records none.

        ``None`` on a run of a pipeline built outside a ``@pipeline_factory``, and on a run
        written before the manifest carried the field::

            mornings = [run for run in runs("runs/") if run.pipeline == "freshen"]

        A run of a slice records the name of the pipeline it was sliced from, so this and
        ``manifest["slice"]`` together say what ran.
        """
        recorded = self.manifest.get("pipeline")
        return str(recorded) if recorded else None

    @property
    def scripted(self) -> bool:
        """Whether every model this run called answered from a script rather than a backend.

        True where the run was made with ``FakeModelClient``, or with a project's own client
        declaring ``scripted``. False on a run written before the manifest carried the field::

            paid = [run for run in runs("runs/", scripted=None) if not run.scripted]

        :func:`runs` leaves these out by default, since a scripted run spent nothing and its
        answers were written by whoever wrote the script.
        """
        return bool(self.manifest.get("scripted"))

    @property
    def live(self) -> bool:
        """Whether an end user was on the other end of this run.

        False on a run made while the project was being built, and on a run written before the
        manifest carried the field::

            real = [run for run in runs("runs/") if run.live]
        """
        return bool(self.manifest.get("live"))

    @property
    def evaluation(self) -> EvaluationRef | None:
        """Which rollout of which evaluation this run was, or ``None`` for a run of the agent.

        Read off the manifest, so a rollout says what it is wherever its directory sits::

            for run in runs("runs/", nested=True):
                if run.evaluation is not None:
                    print(run.evaluation.eval_id, run.evaluation.example)

        A manifest written before format ``0.35`` carries no such field, and ``None`` here
        does not settle it for those: :func:`runs` falls back to the run's depth, which is
        what identified a rollout before the field existed.
        """
        return EvaluationRef.from_json(self.manifest.get("evaluation"))

    @property
    def finished(self) -> bool:
        """Whether the run reached an end its outputs can be read against.

        True for ``completed`` and for ``stopped_early``, which stopped on a budget axis after
        doing real work. A suspended run has not finished, and a run that errored did not::

            done = [run for run in runs("runs/") if run.finished]
        """
        return self.outcome in FINISHED_OUTCOMES

    @property
    def liveness(self) -> str | None:
        """Whether a run with no recorded outcome is still executing: three answers.

        ``running`` while the run could still be going, ``abandoned`` where it cannot be, and
        ``unknown`` where nothing on disk settles it. ``None`` on a run that recorded an
        outcome, which ended and is ``outcome``'s question rather than this one, so exactly one
        of the two is set on any run::

            for run in runs("runs/"):
                if run.liveness == "abandoned":
                    print(run.run_id, "was killed before it wrote what it produced")

        **A killed process writes nothing**, so this is derived rather than recorded. The
        manifest is written when the run starts and rewritten when it ends, and a process that
        died between the two leaves the start copy forever.

        What settles it, in order: the run's own ``max_wall_clock_ms``, since the library would
        have stopped it; then the last record in its trajectory, since a run writes as it goes.
        A run declaring no bound and holding no trajectory is ``unknown``, which is the honest
        answer rather than a guess in either direction.

        **A run reads as ``running`` until its own bound has passed**, so a process killed one
        minute into an hour-long budget reads as running for the rest of that hour. Nothing on
        disk distinguishes it from one that is still working, and the bound is what the run
        said about itself.
        """
        if self.outcome is not None:
            return None
        return self._liveness_of_an_unfinished_run()

    def _liveness_of_an_unfinished_run(self) -> str:
        """The three-way answer for a run whose manifest records no outcome."""
        started = _moment(str(self.manifest.get("started_at") or ""))
        bound = (self.manifest.get("budget") or {}).get("max_wall_clock_ms")
        now = datetime.now(timezone.utc)
        if started is not None and isinstance(bound, (int, float)) and bound > 0:
            deadline = (
                started
                + timedelta(milliseconds=float(bound))
                + timedelta(seconds=ABANDONED_GRACE_S)
            )
            return ABANDONED if now > deadline else RUNNING
        last = self.last_activity_at
        if last is not None:
            # No declared bound, so the evidence is silence: a run writes a record per model
            # call, per tool call and per step, and one that has written nothing for this long
            # is not executing. The trajectory dates itself, so a manifest whose `started_at`
            # cannot be read is still answerable here.
            return ABANDONED if now > last + timedelta(seconds=SILENT_FOR_S) else RUNNING
        return LIVENESS_UNKNOWN

    @property
    def last_activity_at(self) -> datetime | None:
        """When this run last wrote a trajectory record, or ``None`` where it wrote none.

        Read by streaming the file and keeping the last timestamp, so a run whose trajectory is
        large is not parsed into memory to answer it.
        """
        return _last_record_moment(self.trajectory_path)

    @property
    def trajectory_path(self) -> Path:
        """The run's trajectory file, whether or not it exists.

        Derived from the directory rather than read from the manifest, so a run directory that
        was moved or is being read from elsewhere still resolves.
        """
        return self.path / TRAJECTORY_NAME

    @property
    def manifest_path(self) -> Path:
        """The run's manifest file, whether or not it could be parsed."""
        return self.path / MANIFEST_NAME

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Every node that executed, in the order each first ran.

        A node the run skipped is not here, and neither is one the run never reached. Read it
        before asking for an output on a run that may have stopped early::

            if "report" in run.node_ids:
                shortlist.extend(run.outputs_of("report")["suggestions"])
        """
        return tuple(self._node_outputs())

    def outputs_of(self, node_id: str) -> Any:
        """What a node produced, on its last execution in this run.

        The value is decoded, so a recorded absence is an ``Unknown`` wherever it sits in the
        output rather than the tagged object the file holds::

            source = run.outputs_of("chase")["source"]
            if isinstance(source, Unknown):
                ...

        A node inside a bounded cycle answers for its last iteration, and a run that suspended
        and resumed answers for the execution that finished. ``read_trajectory`` is what reads
        every iteration.

        ``None`` means the node produced nothing. A node that did not run raises
        ``LookupError`` naming the ones that did, so the two are never the same answer. On a
        run whose payloads were dropped by sampling this returns what the record holds, which
        is ``{"type": "not_recorded", "reason": "sampling"}``.
        """
        outputs = self._node_outputs()
        if node_id not in outputs:
            raise LookupError(self._nothing_for(node_id, outputs))
        return outputs[node_id]

    def _node_outputs(self) -> dict[str, Any]:
        """Each node's last recorded output, read once and kept."""
        if self._outputs is None:
            found: dict[str, Any] = {}
            if self.trajectory_path.exists():
                for record in read_trajectory(self.trajectory_path):
                    if (
                        record.get("record_type") == "node_execution"
                        and record.get("termination") != "skipped"
                    ):
                        found[str(record.get("node_id"))] = decode_answer(record.get("outputs"))
            self._outputs = found
        return self._outputs

    def _nothing_for(self, node_id: str, outputs: dict[str, Any]) -> str:
        if not self.trajectory_path.exists():
            return (
                f"Run {self.run_id} wrote no trajectory, and what {node_id!r} "
                f"produced. Check run.finished before reading a node's output, or read "
                f"run.manifest['outcome'] for why the run has no records."
            )
        ran = ", ".join(outputs) or "no node"
        return (
            f"Node {node_id!r} did not run in {self.run_id}, which executed {ran}. A run that "
            f"stopped early reaches only some of the graph, so test `{node_id!r} in "
            f"run.node_ids` before asking, or filter to finished runs first."
        )


def runs(
    run_dir: str | os.PathLike[str],
    *,
    nested: bool = False,
    role: str | None = None,
    live: bool | None = None,
    pipeline: str | None = None,
    scripted: bool | None = False,
    since: str | None = None,
    last: int | None = None,
) -> list[RunHandle]:
    """Every run written under ``run_dir``, newest first.

    Reads the directories the envelope wrote, without running a pipeline::

        from simple_agents import runs

        for run in runs("runs/"):
            if run.finished and "report" in run.node_ids:
                print(run.run_id, run.outputs_of("report"))

    Newest is by the manifest's ``started_at``. A directory holding a ``manifest.json`` is a
    run whatever that file contains, and the whole tree is read at any depth, so a project
    holding runs written under an older layout reads the same as one written today.

    **An evaluation's rollouts are left out**, and ``nested=True`` includes them::

        rollouts = runs("runs/eval/eval_e5a1bbef5a22", nested=True)

    ``role`` separates the project's own agent from work it did for itself, ``live`` the runs
    an end user made from the runs made building it (``docs/shipping.md`` §2), ``pipeline`` the
    runs of one registered pipeline (``docs/pipeline.md`` §1.15), ``since`` the runs that
    started at or after an ISO timestamp, matched as text, and ``last`` the newest that many of
    what the others left::

        agent_runs = runs("runs/", role="agent")
        real = runs("runs/", live=True)
        mornings = runs("runs/", pipeline="freshen")
        recent = runs("runs/", nested=True, since="2026-08-14", last=500)

    A run written before the manifest carried those fields counts as ``agent``, as not live and
    as a rollout where it sits below ``run_dir``; a ``run_dir`` that is not there is empty.

    **A run whose model answered from a script is left out**: it spent nothing and its answers
    were written rather than produced. ``scripted=None`` includes them, ``scripted=True``
    returns only those::

        every = runs("runs/", scripted=None)
    """
    root = Path(run_dir)
    found = [_handle(path) for path in sorted(root.glob(f"**/{MANIFEST_NAME}"))]
    if not nested:
        found = [handle for handle in found if not is_a_rollout(handle.path, handle.manifest, root)]
    return narrowed(
        found,
        role=role,
        live=live,
        pipeline=pipeline,
        scripted=scripted,
        since=since,
        last=last,
    )


def is_a_rollout(run_root: Path, manifest: Mapping[str, Any], under: Path) -> bool:
    """Whether a run is one rollout of an evaluation rather than a run of the agent.

    The manifest is the answer where it carries one. Where it does not, which is every
    manifest written before format ``0.35``, the run's depth is: an evaluation has always
    written its rollouts one directory further down than a run of the agent::

        rollout = is_a_rollout(path.parent, manifest, Path("runs"))

    ``under`` is the directory the run was found beneath, and a run that is not beneath it is
    not a rollout of anything found there.
    """
    if EvaluationRef.from_json(manifest.get("evaluation")) is not None:
        return True
    if "evaluation" in manifest:
        return False
    try:
        depth = len(Path(run_root).relative_to(under).parts)
    except ValueError:
        return False
    return depth > 1


def manifest_paths(run_dir: str | os.PathLike[str], *, rollouts: bool | None = False) -> list[Path]:
    """Every ``manifest.json`` under ``run_dir``, at any depth, sorted.

    ``rollouts=False`` leaves out the rollouts an evaluation wrote, which is what a reader
    counting the project's own runs wants; ``True`` keeps only those; ``None`` keeps every
    run::

        for path in manifest_paths("runs/"):
            manifest = json.loads(path.read_text(encoding="utf-8"))

    A manifest that cannot be parsed is kept where rollouts are not being separated, and left
    out where they are, since what it is cannot be read.
    """
    root = Path(run_dir)
    found = sorted(root.glob(f"**/{MANIFEST_NAME}"))
    if rollouts is None:
        return found
    kept: list[Path] = []
    for path in found:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = None
        if not isinstance(manifest, dict):
            if rollouts is False:
                kept.append(path)
            continue
        if is_a_rollout(path.parent, manifest, root) is rollouts:
            kept.append(path)
    return kept


def evaluation_dir(run_dir: str | os.PathLike[str], eval_id: str) -> Path:
    """Where one evaluation's rollouts are, under ``run_dir``.

    An evaluation writes its rollouts into ``<run_dir>/eval/<eval_id>/``, and this is what
    resolves that without the caller assembling it::

        suite.rescore(run_dir=evaluation_dir("runs/", results.eval_id), split="held_out")

    A project that ran an evaluation before the layout settled wrote it directly under
    ``run_dir``, and that is returned where it is what exists. The path is returned whether or
    not it exists, so a caller reads the same refusal it would have read anyway.
    """
    root = Path(run_dir)
    filed = root / EVAL_BUCKET / eval_id
    if filed.is_dir() or not (root / eval_id).is_dir():
        return filed
    return root / eval_id


def rollouts_under(eval_dir: str | os.PathLike[str]) -> list[Any]:
    """Every rollout directly inside one evaluation's own directory, newest first.

    An evaluation writes a directory per rollout inside its own, and a rollout says so on its
    manifest, so ``runs()`` leaves them out of a project's runs. This is what reads them back::

        for handle in rollouts_under("runs/eval/eval_a1226bc495df"):
            print(handle.run_id, handle.outcome)

    Only the directories directly inside are returned, so a path holding evaluations rather
    than rollouts gives an empty list rather than every rollout of every evaluation under it.

    A rollout made by a scripted client is returned like any other. The caller named one
    evaluation's directory, so what is in it is the answer; leaving scripted runs out is what
    a reader summarising a project's runs does.
    """
    root = Path(eval_dir)
    return [
        handle for handle in runs(root, nested=True, scripted=None) if handle.path.parent == root
    ]


def find_run(run_dir: str | os.PathLike[str], run_id: str) -> Path | None:
    """Where one run's directory is, found by its id rather than computed from it.

    A run is filed by what it is (:meth:`RunEnvelope.placement`), so nothing outside the
    envelope can derive the path, and a run written under an older layout is somewhere else
    again::

        root = find_run("runs/", "req-8817")

    ``None`` where no run of that id is under ``run_dir``. Where more than one is, the one
    that began last wins, which is what a re-used id means.
    """
    root = Path(run_dir)
    if not root.is_dir():
        return None
    candidates = [
        path.parent
        for path in sorted(root.glob(f"**/{MANIFEST_NAME}"))
        if path.parent.name == run_id
    ]
    if not candidates:
        direct = root / run_id
        return direct if direct.is_dir() else None
    if len(candidates) == 1:
        return candidates[0]
    return max(candidates, key=lambda path: _started_at(_handle(path / MANIFEST_NAME)))


def narrowed(
    found: Sequence[RunHandle],
    *,
    role: str | None = None,
    live: bool | None = None,
    pipeline: str | None = None,
    scripted: bool | None = False,
    since: str | None = None,
    last: int | None = None,
) -> list[RunHandle]:
    """The runs of ``found`` these filters leave, newest first.

    What :func:`runs` applies, over handles already read, for a caller that reads a directory
    once and reports over more than one selection of it. Read everything to select from::

        every = runs("runs/", nested=True, scripted=None)
        recent = narrowed(every, role="agent", last=500)
        paid = narrowed(every, scripted=False)

    ``scripted`` is the one filter that narrows when it is left unset, matching :func:`runs`:
    a scripted run is left out unless ``None`` or ``True`` is passed. Every other filter left
    unset keeps everything.
    """
    kept = list(found)
    if role is not None:
        kept = [handle for handle in kept if handle.role == role]
    if live is not None:
        kept = [handle for handle in kept if handle.live is live]
    if pipeline is not None:
        kept = [handle for handle in kept if handle.pipeline == pipeline]
    if scripted is not None:
        kept = [handle for handle in kept if handle.scripted is scripted]
    if since is not None:
        kept = [handle for handle in kept if str(handle.manifest.get("started_at") or "") >= since]
    ordered = sorted(kept, key=_started_at, reverse=True)
    return ordered[: max(0, last)] if last is not None else ordered


def _handle(manifest_path: Path) -> RunHandle:
    try:
        parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return RunHandle(manifest_path.parent, {}, f"{manifest_path.name} is not JSON: {exc}")
    except OSError as exc:
        return RunHandle(manifest_path.parent, {}, f"{manifest_path.name} could not be read: {exc}")
    if not isinstance(parsed, dict):
        return RunHandle(manifest_path.parent, {}, f"{manifest_path.name} is not an object")
    return RunHandle(manifest_path.parent, parsed)


def _started_at(handle: RunHandle) -> tuple[str, float]:
    """When the run began, falling back to the file's own time where it does not say.

    A manifest that could not be parsed sorts before every run that names a time, rather than
    dropping out of the listing.
    """
    stamp = handle.manifest.get("started_at")
    try:
        modified = handle.manifest_path.stat().st_mtime
    except OSError:
        modified = 0.0
    return (str(stamp or ""), modified)


@dataclass(frozen=True, slots=True)
class RunPaths:
    """Where one run's artifacts live. Produced by :meth:`RunEnvelope.prepare`."""

    root: Path
    manifest: Path
    trajectory: Path
    workspace: Path


@dataclass(slots=True)
class RunEnvelope:
    """What governs every run of a project.

    ``cost_basis`` is what cost is derived against. Leaving it ``None`` means cost is unknown
    for every run through this envelope, and a budget with ``max_cost`` set is refused (FT-27).
    A run calling more than one model takes a basis each (``docs/run-envelope.md`` §4.1)::

        env = RunEnvelope(run_dir="runs/", cost_basis={
            "mistral-large-2512": PriceBasis(currency="USD", input_uncached_per_mtok=2.0,
                                             output_per_mtok=6.0),
            "Qwen/Qwen3-1.7B": ComputeBasis(currency="USD", device="RTX3090",
                                            device_count=1, hourly_rate=0.22),
        })

    ``redaction`` defaults to the built-in credential rules. ``cassette`` defaults to
    :meth:`Cassette.into_run`, which records every call into the run's own directory::

        env = RunEnvelope(run_dir="runs/")                            # records
        env = RunEnvelope(run_dir="runs/", cassette=Cassette.off())   # records nothing

    ``trajectory`` defaults to :meth:`Trajectory.full`, which keeps every payload on every run.
    Sampling bounds what a project accumulates, and drops the default recording with them::

        env = RunEnvelope(run_dir="runs/", trajectory=Trajectory.sampled(0.01))

    ``role`` says what the runs through this envelope are for, and defaults to ``agent``, the
    only role the conformance checks read (``docs/run-envelope.md`` §2.1)::

        labelling = env.with_role("labelling")

    ``memory`` is the store a tool taking a ``Memory`` handle reaches. It outlives the run, so
    an evaluation replaces it per rollout, and a memory tool with no store is refused::

        env = RunEnvelope(run_dir="runs/",
                          memory=MemoryStore("memory/"))

    ``end_user`` is who answers a consultation in runs through this envelope, in place of the
    channel the ``consult`` tool was registered with (``docs/tools.md`` §4.6.2)::

        smoke = env.with_end_user(unattended())      # a run with nobody to ask

    ``conversations`` is where a conversation that outlives the run is kept, and which one a
    run is a turn of is an argument to ``Pipeline.run`` (``docs/conversation.md``)::

        env = RunEnvelope(run_dir="runs/",
                          conversations=ConversationStore("conversations/"))

    ``live`` says an end user is on the other end. It defaults to false, which is a run made
    while the project is being built, and those are the runs the conformance checks read
    (``docs/shipping.md`` §1)::

        real = env.with_live()                       # what a person actually used
    """

    run_dir: Path = Path("runs")
    cost_basis: CostBases | None = None
    redaction: Redaction = field(default_factory=Redaction)
    cassette: Cassette = field(default_factory=Cassette.into_run)
    trajectory: Trajectory = field(default_factory=Trajectory.full)
    role: str = DEFAULT_ROLE
    memory: MemoryStore | None = None
    end_user: Any = None
    live: bool = False
    evaluation: EvaluationRef | None = None
    conversations: ConversationStore | None = None

    def __post_init__(self) -> None:
        self.run_dir = Path(self.run_dir)
        if not isinstance(self.role, str) or not self.role.strip():
            raise ConfigurationError(
                f"RunEnvelope(role={self.role!r}) takes a non-empty string. Leave it unset for "
                f"the project's own agent, or name what the run is for: "
                f"RunEnvelope(run_dir='runs/', role='labelling'). Only role='agent' is read by "
                f"the conformance checks."
            )
        if self.role in RESERVED_BUCKETS:
            raise ConfigurationError(
                f"RunEnvelope(role={self.role!r}) collides with the directory the library "
                f"files runs into. A run goes under runs/live/, runs/dev/ or runs/eval/ "
                f"according to what it is, and a role names its own directory beside those, "
                f"so {self.role!r} would mix two kinds of run in one place.\n"
                f"Name what the run is for instead: role='labelling', role='judge', "
                f"role='variant'."
            )
        if self.live and self.role != DEFAULT_ROLE:
            raise ConfigurationError(
                f"RunEnvelope(role={self.role!r}, live=True) says both that this run was "
                f"something other than the agent and that an end user was on the other end of "
                f"it. A live run is a run of the agent.\n"
                f"Drop the role for a run a person made, or drop live=True for {self.role!r} "
                f"work the project did for itself."
            )
        if not isinstance(self.trajectory, Trajectory):
            raise ConfigurationError(
                f"RunEnvelope(trajectory=...) takes a Trajectory, not "
                f"{type(self.trajectory).__name__}. Pass Trajectory.full() to keep every "
                f"payload, or Trajectory.sampled(0.01) to keep one run in a hundred."
            )
        if not isinstance(self.redaction, Redaction):
            raise ConfigurationError(
                f"RunEnvelope(redaction=...) takes a Redaction, not "
                f"{type(self.redaction).__name__}. Pass Redaction(secret_env=[...]) to declare "
                f"which environment variables hold secrets, or Redaction.none() to record "
                f"that nothing is redacted."
            )
        if self.end_user is not None:
            _refuse_an_undeclared_end_user(self.end_user)
        if not isinstance(self.cassette, Cassette):
            raise ConfigurationError(
                f"RunEnvelope(cassette=...) takes a Cassette, not "
                f"{type(self.cassette).__name__}. Leave it unset to record each run into its "
                f"own directory, or pass Cassette.off(), Cassette.record(path), or "
                f"Cassette.replay(path)."
            )

    def placement(self) -> Path:
        """Where under ``run_dir`` this run's own directory goes.

        A run is filed by what it is, so a directory listing answers what a project has done.
        A run an end user made goes under ``live/`` and one made while building under ``dev/``,
        each inside a directory named for the UTC date. A run declaring a ``role`` goes under
        that name instead. One rollout of an evaluation goes under ``eval/`` beside the others
        of its evaluation, which has already scoped ``run_dir``, so a rollout adds nothing
        further and returns an empty path here.

        Every reader finds a run by its manifest and reads what that says, so a project
        holding runs written under an older layout keeps working and its directories stay
        where they are.
        """
        if self.evaluation is not None:
            return Path()
        if self.role != DEFAULT_ROLE:
            return Path(self.role) / _today()
        return Path(LIVE_BUCKET if self.live else DEV_BUCKET) / _today()

    def prepare(self, run_id: str) -> RunPaths:
        """Create this run's directory and return the paths inside it.

        The directory sits under ``run_dir`` at what :meth:`placement` returns, so a run of
        the agent an end user made and a labelling pass are in separate places.

        Raises ``ConfigurationError`` when the envelope replays from a cassette file that does
        not exist, which would otherwise surface as a miss on the run's first model call.
        """
        self._refuse_a_missing_cassette()
        return self.paths_at(self.run_dir / self.placement() / run_id)

    def paths_at(self, root: str | os.PathLike[str]) -> RunPaths:
        """The paths inside a run directory that already exists, and the workspace created.

        What a resume uses: the run was filed when it started and continues where it is,
        rather than being filed again on the day it was picked back up.
        """
        self._refuse_a_missing_cassette()
        root = Path(root)
        paths = RunPaths(
            root=root,
            manifest=root / MANIFEST_NAME,
            trajectory=root / TRAJECTORY_NAME,
            workspace=root / WORKSPACE_NAME,
        )
        paths.workspace.mkdir(parents=True, exist_ok=True)
        return paths

    def _refuse_a_missing_cassette(self) -> None:
        if self.cassette.mode is not CassetteMode.REPLAY:
            return
        path = self.cassette.path
        if path is None or not Path(path).exists():
            raise ConfigurationError(
                f"The envelope replays from {path}, and that file does not exist. Replay "
                f"serves every model and tool call from the file, so there is nothing to "
                f"run against. Record it first with Cassette.record({str(path)!r}), or "
                f"pass Cassette.off() to make live calls."
            )

    def with_run_dir(self, run_dir: str | os.PathLike[str]) -> RunEnvelope:
        """A copy writing runs somewhere else. Everything else is shared with the original."""
        return replace(self, run_dir=Path(run_dir))

    def with_conversations(self, conversations: ConversationStore | None) -> RunEnvelope:
        """A copy keeping conversations somewhere else. Everything else is shared."""
        return replace(self, conversations=conversations)

    def with_evaluation(self, evaluation: EvaluationRef | None) -> RunEnvelope:
        """A copy whose runs say which rollout of which evaluation they are::

            scoped = env.with_evaluation(
                EvaluationRef(eval_id=eval_id, example=example.id, rollout=k)
            )

        What :meth:`EvalSuite.run` gives each rollout, so the manifest says what the run is.
        A rollout adds nothing to ``run_dir``, since the evaluation has already scoped it.
        """
        return replace(self, evaluation=evaluation)

    def with_live(self, live: bool = True) -> RunEnvelope:
        """A copy whose runs say an end user was on the other end. Everything else is shared::

            env = RunEnvelope(run_dir="runs/", cost_basis=PRICES)
            real = env.with_live()

        The conformance checks read the runs that are not live, and ``runs(live=True)`` reads
        these (``docs/shipping.md`` §1). Pass ``False`` for a copy that goes back to being a
        run made while building.
        """
        return replace(self, live=live)

    def with_role(self, role: str) -> RunEnvelope:
        """A copy whose runs say they are something other than the agent. Everything else is
        shared, so one configured envelope serves both::

            env = RunEnvelope(run_dir="runs/", cost_basis=PRICES)
            labelling = env.with_role("labelling")

        The cost basis, the redaction rules and the cassette come from the envelope that was
        configured once, and the labelling pass's runs are excluded from the checks that read
        the project's agent.
        """
        return replace(self, role=role)

    def with_trajectory(self, trajectory: Trajectory) -> RunEnvelope:
        """A copy keeping a different share of the payloads. Everything else is shared::

            production = RunEnvelope(run_dir="runs/", trajectory=Trajectory.sampled(0.01))
            evaluating = production.with_trajectory(Trajectory.full())

        An evaluation needs the full payloads, and this is how one envelope serves both.
        """
        return replace(self, trajectory=trajectory)

    def with_end_user(self, end_user: Any, *, answered_by: str | None = None) -> RunEnvelope:
        """A copy whose runs ask someone else. Everything else is shared::

            smoke = env.with_end_user(unattended())
            mine = env.with_end_user(ask_the_qa_channel, answered_by="builder")

        This replaces the registered channel for one kind of run without the pipeline being
        rebuilt: a smoke run with nobody at a terminal, a sweep, or an evaluation's stand-in.
        ``answered_by`` says who the replacement reaches and is what each consultation then
        records; a shipped channel declares its own and needs nothing here.

        A pipeline that asks more than one person takes a channel per name, keyed by what its
        consult tools declare in ``reaches``. Each declares its own answerer::

            env.with_end_user({"requester": ask_analyst, "approver": ask_director})
        """
        return replace(self, end_user=_declaring(end_user, answered_by))

    def with_cassette(self, cassette: Cassette) -> RunEnvelope:
        """A copy recording or replaying somewhere else. Everything else is shared::

            envelope.with_cassette(Cassette.record("evals/cassettes/v3.jsonl"))

        A variant comparison uses this to give each arm its own file while the run directory,
        the cost basis and the redaction rules stay the ones configured once.
        """
        return replace(self, cassette=cassette)


def _moment(stamp: str) -> datetime | None:
    """One ISO 8601 timestamp as an aware datetime, or ``None`` where it cannot be read."""
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _last_record_moment(path: Path) -> datetime | None:
    """When a trajectory was last written to, read from the timestamps in its tail.

    ``None`` where the file is absent, empty, or holds no timestamp in the tail that is read.
    A run that wrote nothing has no last activity, which is a different answer from a run that
    wrote something a long time ago.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - _TAIL_BYTES))
            tail = handle.read(min(size, _TAIL_BYTES))
    except OSError:
        return None
    found = [_moment(match.decode("utf-8", "replace")) for match in _STAMP.findall(tail)]
    stamps = [moment for moment in found if moment is not None]
    return max(stamps) if stamps else None
