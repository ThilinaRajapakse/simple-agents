"""The pipeline: a directed graph over the three node kinds, and the run context.

Edges are declared on the node. A node that declares none hands its output to the next node in
the list, so a plain list runs as a chain and every pipeline written before edges existed keeps
its meaning. ``graph.py`` holds the edge model and the checks over it; what is here is the walk.

The walk is single-threaded and its order comes from the declared graph rather than from the
list. A node runs once every edge into it has resolved, a node whose edges all resolved absent
is recorded as skipped, and a cycle carrying a ``Loop`` runs a bounded number of times.

A node that runs once per item in a list is still one node, whichever kind it is, declared with
``over=``: the amount of work varies with the data, and the set of nodes does not.

``docs/pipeline.md`` is this module's document: the graph, the three node kinds, what a node
receives, the output schema, and the budget.
"""

from __future__ import annotations

import os
import json
import random
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Sequence

from ..budget import Budget, BudgetExceeded, Spend
from ..records.cassette import CASSETTE_NAME, Cassette, CassetteEntry, CassetteMiss, CassetteMode
from ..mcp import MCP_CASSETTE_KIND as MCP_LISTING_KIND
from ..concurrency import WorkPool
from ..context import RouteContext, RunContext, TokenEvent, error_object, new_run_id
from ..cost import basis_to_manifest
from ..envelope import RunEnvelope, RunPaths, find_run
from ..errors import CallerFacingError, ConfigurationError, LeftTheSlice
from ..graph import (
    CutEdge,
    Graph,
    NodeFailure,
    RetryPolicy,
    reaching as _reaching,
    selected_by,
    _reachable,
    _safe,
)
from ..records.manifest import Manifest
from ..models import ModelClient
from ..nodes import AgentNode, Deterministic, Execution, LLMNode, model_for, Node, NodeOutcome
from ..nodes.base import _declare_edges
from ..runtime.budgets import _refuse_over_budget, _spent_since
from ..runtime.suspending import _Suspending
from ..memory import refuse_another_scope
from ..tools import Tool, ToolRegistry
from ..shapes import refuse_value_arriving
from ..records.shelf import (
    SHELF_NAME,
    Shelf,
    ShelvedQuestion,
    read_shelf,
    release_shelf,
    settle_shelf,
    write_shelf,
)
from ..records.suspension import (
    SUSPENSION_NAME,
    RunSuspended,
    Suspend,
    SuspensionState,
    ValueCodec,
    claim_state,
    discard_claim,
    read_state,
    release_claim,
    write_state,
)
from ..records.trajectory import PENDING_SEQUENCE, RunStartRecord, TrajectoryWriter, utc_now
from .answering import (
    Answered,
    AnsweredQuestion,
    _claim_the_question,
    _read_a_filed_answer,
    _record_the_answer,
)
from .edges import _Attempted, _EdgeState, _Frame
from .events import NodeEvent, RunResult, _announce
from .preflight import (
    _refuse_a_bad_slice,
    _refuse_a_disconnected_slice,
    _refuse_a_model_pipeline_without_budget,
    _refuse_a_nameless_nested_pipeline,
    _refuse_an_unfillable_policy,
    _refuse_non_nodes,
    _refuse_unusable_ids,
    _refuse_an_unstored_conversation,
    _refuse_delegation_cycle,
    _refuse_mixed_currencies,
    _refuse_unauditable_cost,
    _refuse_unpriceable,
    _refuse_unreachable_memory,
    _refuse_unserved,
    _refuse_unstreamable,
    _warn_bounded_cost_limit,
    _warn_declarations_the_run_cuts,
)
from .recording import (
    _close_manifest,
    _container_structure,
    _describe_shape_change,
    _digest,
    _emit_node_record,
    _new_manifest,
    _node_entries,
    _note_where_it_came_from,
    _structure,
    _what_a_run_was_given,
    _without_channels,
    _without_derived,
)


@dataclass(frozen=True, slots=True)
class SliceOf:
    """What a pipeline produced by :meth:`Pipeline.slice` is a slice of.

    Written into the manifest under ``slice`` and into a results file's ``config``, so two
    evaluations of two rungs of one pipeline are relatable rather than unrelated::

        rung = pipeline.slice(start="judge")
        rung.slice_of.of        # the source pipeline's graph_fingerprint
        rung.slice_of.dropped   # the node ids left out

    ``start`` and ``end`` are ``None`` where the node set was named rather than computed.
    """

    of: str
    nodes: tuple[str, ...]
    dropped: tuple[str, ...]
    cut_edges: tuple[CutEdge, ...] = ()
    start: str | None = None
    end: str | None = None

    def to_record(self) -> dict[str, Any]:
        """What the manifest and the results file store about the slice."""
        return {
            "of": self.of,
            "nodes": list(self.nodes),
            "start": self.start,
            "end": self.end,
            "dropped": list(self.dropped),
            "cut_edges": [
                {"from": edge.source, "to": edge.target, "kind": edge.kind}
                for edge in self.cut_edges
            ],
        }


class Pipeline:
    """A directed graph over the three node kinds, executed from its first node.

    A node that declares no successors hands its output to the next node in the list, so a
    plain list runs as a chain. A budget is required whenever the pipeline contains a node that
    can call a model. Any axis may be ``None``, and a pipeline of ``Deterministic`` nodes only
    may omit the argument::

        pipeline = Pipeline(
            [Deterministic(load_docs), LLMNode(build_prompt, output_schema=Answer)],
            budget=Budget(max_steps=None, max_tokens=100_000,
                          max_cost=None, max_wall_clock_ms=300_000),
        )

    A pipeline is also a node in another pipeline, given a ``node_id``. Its nodes keep their own
    ids prefixed by it, so ``hunt`` inside ``research`` records as ``research.hunt``::

        research = Pipeline([...], budget=..., node_id="research")
        outer = Pipeline([research, LLMNode(write, output_schema=Report)], budget=...)
    """

    node_kind = "pipeline"

    def __init__(
        self,
        nodes: Sequence[Node],
        *,
        budget: Budget | None = None,
        node_id: str | None = None,
        tools: ToolRegistry | None = None,
        fetch_policy: Any = None,
        concurrent_nodes: Sequence[Sequence[str]] | None = None,
        successors: Sequence[str] | None = None,
        route: Any = None,
        loop: Any = None,
        on_error: str | None = None,
        retry: RetryPolicy | None = None,
        suspend_before: bool = False,
        slice_of: SliceOf | None = None,
    ) -> None:
        self.nodes = list(nodes)
        self.node_id = node_id
        self.tools = tools
        self.fetch_policy = fetch_policy
        self.slice_of = slice_of
        _declare_edges(
            self,
            successors=successors,
            route=route,
            loop=loop,
            on_error=on_error,
            retry=retry,
            suspend_before=suspend_before,
        )
        _refuse_non_nodes(self.nodes)
        _refuse_a_nameless_nested_pipeline(self.nodes, kind=Pipeline)
        _refuse_unusable_ids([n.node_id for n in self.nodes])
        _refuse_a_model_pipeline_without_budget(self.nodes, budget, kinds=(LLMNode, AgentNode))
        self.budget = budget if budget is not None else Budget.unbounded()
        self.concurrent_nodes = tuple(tuple(group) for group in (concurrent_nodes or ()))
        self.graph = Graph(
            self.nodes,
            self.concurrent_nodes,
            cut_edges=slice_of.cut_edges if slice_of is not None else (),
        )
        _refuse_an_unfillable_policy(self.nodes, self.fetch_policy)

    @property
    def output_schema(self) -> Any:
        """What this pipeline produces, which is the output schema of its terminal node.

        ``None`` where that node declares none. Used to rebuild a value in flight when a
        suspended run is resumed, so a pipeline used as a node answers the same question a
        single node does.
        """
        return getattr(self.graph.by_id[self.graph.terminal], "output_schema", None)

    def to_mermaid(self) -> str:
        """The declared graph as a Mermaid flowchart, for checking the shape against what was
        meant::

            print(pipeline.to_mermaid())

        A pipeline a node may delegate to is drawn as one box, joined to that node by a dashed
        edge labelled with the ceiling on how many subtasks it may be sent.
        """
        return "\n".join([self.graph.to_mermaid(), *self._mermaid_delegates()])

    def _mermaid_delegates(self) -> list[str]:
        """The delegation edges, which the graph does not hold: nothing declares them on a node
        as an edge, because a model call is what reaches a delegate."""
        lines: list[str] = []
        for node in self.nodes:
            for delegate in getattr(node, "delegates", ()):
                target = f"{node.node_id}.{delegate.name}"
                label = (
                    f"|delegates, up to {delegate.max_calls}x|"
                    if delegate.max_calls is not None
                    else "|delegates|"
                )
                lines.append(f'    {_safe(target)}[["{target}<br/><i>pipeline</i>"]]')
                lines.append(f"    {_safe(node.node_id)} -.->{label} {_safe(target)}")
        return lines

    def declared_nodes(self, prefix: str = "") -> list[tuple[str, Node]]:
        """Every node that can emit a record, with the id it will record under.

        A nested pipeline is replaced by its own nodes, each prefixed by its ``node_id``, and a
        pipeline an ``AgentNode`` may delegate to is replaced the same way, prefixed by the
        calling node as well. The result holds the ids a trajectory will carry, and no
        containers::

            [node_id for node_id, _ in pipeline.declared_nodes()]
            # ['research.hunt', 'research.verify', 'orchestrate',
            #  'orchestrate.sources.find', 'write']
        """
        return [(node_id, node) for node_id, node, _ in self._declared_with_graph(prefix)]

    def _declared_with_graph(
        self, prefix: str = "", seen: tuple[int, ...] = ()
    ) -> list[tuple[str, Node, Graph]]:
        """As :meth:`declared_nodes`, with the graph each node's edges are declared in.

        ``seen`` is the pipelines on the path to this one, which is what makes a delegation
        cycle a refusal rather than a stack overflow.
        """
        _refuse_delegation_cycle(self, prefix, seen)
        below = (*seen, id(self))
        found: list[tuple[str, Node, Graph]] = []
        for node in self.nodes:
            if isinstance(node, Pipeline):
                found.extend(node._declared_with_graph(f"{prefix}{node.node_id}.", below))
            else:
                node_id = f"{prefix}{node.node_id}"
                found.append((node_id, node, self.graph))
                # A delegate's nodes run, record and spend, so every walk that reasons about
                # what this pipeline can reach has to see them. The eval runner's refusal is
                # the one that matters: a `spends_money` tool inside a delegate would otherwise
                # execute once per rollout with nothing having declared it.
                for delegate in getattr(node, "delegates", ()):
                    found.extend(
                        delegate.pipeline._declared_with_graph(f"{node_id}.{delegate.name}.", below)
                    )
        return found

    def declared_containers(
        self, prefix: str = "", seen: tuple[int, ...] = ()
    ) -> list[tuple[str, "Pipeline", Graph | None, Any]]:
        """Every pipeline used as a node or as a delegate, with the id it records under.

        A pipeline nested two deep is here under both its prefixes, so the list holds the whole
        tree and not only its first level. The pipeline this is called on is not in it::

            [node_id for node_id, _, _, _ in outer.declared_containers()]
            # ['research', 'research.sources', 'orchestrate.research']

        The last two say how each is reached, and exactly one of them is set. A pipeline used
        as a node has the graph its edges are declared in; a delegate has the
        :class:`~simple_agents.Delegation` a model reaches it through, and no graph, because it
        is reached by a model call rather than along an edge.
        """
        _refuse_delegation_cycle(self, prefix, seen)
        below = (*seen, id(self))
        found: list[tuple[str, Pipeline, Graph | None, Any]] = []
        for node in self.nodes:
            if isinstance(node, Pipeline):
                node_id = f"{prefix}{node.node_id}"
                found.append((node_id, node, self.graph, None))
                found.extend(node.declared_containers(f"{node_id}.", below))
            else:
                for delegate in getattr(node, "delegates", ()):
                    node_id = f"{prefix}{node.node_id}.{delegate.name}"
                    found.append((node_id, delegate.pipeline, None, delegate))
                    found.extend(delegate.pipeline.declared_containers(f"{node_id}.", below))
        return found

    def _every_pipeline(self) -> list["Pipeline"]:
        """This pipeline and every one nested below it."""
        return [pipeline for _, pipeline in self._pipelines_by_id()]

    def _pipelines_by_id(self) -> list[tuple[str | None, "Pipeline"]]:
        """This pipeline and every one nested below it, each with the id it records under.

        The id is ``None`` for this one, which is the pipeline the run was started with and
        records under no node id of its own.
        """
        return [(None, self)] + [
            (node_id, pipeline) for node_id, pipeline, _, _ in self.declared_containers()
        ]

    @property
    def node_kinds(self) -> dict[str, int]:
        """Count of nodes by kind, keyed by ``node_kind``. A nested pipeline counts its own."""
        counts: dict[str, int] = {}
        for _, node in self.declared_nodes():
            counts[node.node_kind] = counts.get(node.node_kind, 0) + 1
        return counts

    def slice(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        nodes: Sequence[str] | None = None,
    ) -> "Pipeline":
        """Part of this pipeline as a pipeline of its own, for scoring one step at a time.

        A rung runs, writes a trajectory and a manifest, and is evaluated like any other
        pipeline::

            rung = pipeline.slice(start="judge")
            suite = EvalSuite(rung, examples.entering(rung), answer="answer", matches=exact)

        ``start`` and ``end`` are inclusive and either may be left out. The set is what
        ``start`` reaches and what reaches ``end``::

            pipeline.slice(start="judge")                 # judge to the end
            pipeline.slice(end="select")                  # the head up to select
            pipeline.slice(start="select", end="judge")   # between them
            pipeline.slice(start="judge", end="judge")    # judge alone

        ``nodes`` names the set instead, for a branching graph where two bounds cannot say
        which arm is wanted. It cannot be combined with ``start`` or ``end``::

            pipeline.slice(nodes=["select", "judge", "merge"])

        **An edge whose other end is outside the slice stays declared.** A node that took a
        :class:`~simple_agents.graph.Join` still receives one, with the cut arm in
        ``Join.absent``. A route on an earlier node may select an arm the slice does not hold,
        and the run ends there, raising :class:`~simple_agents.errors.LeftTheSlice`. The last
        node is where the run finishes, and its output is what the run returns.

        The slice keeps this pipeline's budget, tools and fetch policy, its ``node_id`` is
        ``None``, and ``slice_of`` says what it is a slice of.

        Raises :class:`~simple_agents.errors.ConfigurationError` for a node id this pipeline
        does not hold, for a set whose nodes are not all reachable from the earliest of them,
        for a set with more than one node that ends it, and for a call naming no bound at all.
        """
        held = [node.node_id for node in self.nodes]
        _refuse_a_bad_slice(self, start=start, end=end, nodes=nodes, held=held)
        kept = self._sliced_set(start=start, end=end, nodes=nodes, held=held)
        _refuse_a_disconnected_slice(self, kept, start=start, end=end, named=nodes is not None)

        cut: list[CutEdge] = []
        sliced: list[Node] = []
        for node in self.nodes:
            if node.node_id in kept:
                sliced.append(self._node_within(node, kept, cut))
            else:
                self._edges_into(node, kept, cut)

        groups = [
            [node_id for node_id in group if node_id in kept] for group in self.concurrent_nodes
        ]
        return Pipeline(
            sliced,
            budget=self.budget,
            tools=self.tools,
            fetch_policy=self.fetch_policy,
            concurrent_nodes=[group for group in groups if len(set(group)) > 1] or None,
            slice_of=SliceOf(
                of=self.graph_fingerprint(),
                nodes=tuple(kept),
                dropped=tuple(node_id for node_id in held if node_id not in kept),
                cut_edges=tuple(cut),
                start=start,
                end=end,
            ),
        )

    def _node_within(self, node: Node, kept: list[str], cut: list[CutEdge]) -> Node:
        """One node with its edges narrowed to the slice, and each edge it lost recorded.

        A copy, so slicing a pipeline leaves the pipeline it was sliced out of untouched. The
        function, prompt, tools and declared versions are the same objects, so a rung's
        `behaviour_fingerprint` differs from the whole pipeline's in shape alone.
        """
        import copy

        within = copy.copy(node)
        here = node.node_id
        # Resolved rather than read off the node, because `successors=None` means the next node
        # in the list and the slice's list is a different one.
        declared = self.graph.successors[here]
        within.successors = [target for target in declared if target in kept]
        for target in declared:
            if target not in kept:
                cut.append(CutEdge(source=here, target=target, kind="successor"))

        handler = getattr(node, "on_error", None)
        if handler and handler not in kept:
            cut.append(CutEdge(source=here, target=handler, kind="on_error"))

        loop = getattr(node, "loop", None)
        if loop is not None and loop.then not in kept:
            cut.append(CutEdge(source=here, target=loop.then, kind="loop_then"))
        return within

    def _edges_into(self, node: Node, kept: list[str], cut: list[CutEdge]) -> None:
        """Each edge from a node outside the slice to one inside it, recorded as cut.

        These are what keeps a joining node receiving a :class:`~simple_agents.graph.Join`.
        Its in-edges are the shape of the graph rather than of what ran, so an arm the slice
        does not hold is a key that never fires rather than a key that is gone.
        """
        here = node.node_id
        for target in self.graph.successors[here]:
            if target in kept:
                cut.append(CutEdge(source=here, target=target, kind="successor"))
        handler = getattr(node, "on_error", None)
        if handler in kept:
            cut.append(CutEdge(source=here, target=str(handler), kind="on_error"))
        loop = getattr(node, "loop", None)
        if loop is not None and loop.then in kept:
            cut.append(CutEdge(source=here, target=loop.then, kind="loop_then"))

    def _sliced_set(
        self,
        *,
        start: str | None,
        end: str | None,
        nodes: Sequence[str] | None,
        held: list[str],
    ) -> list[str]:
        """The node ids this slice holds, in this pipeline's own order."""
        if nodes is not None:
            named = set(nodes)
            return [node_id for node_id in held if node_id in named]
        edges = self.graph.edges
        forward = set(held) if start is None else {start} | _reachable(edges, start)
        backward = set(held) if end is None else {end} | _reaching(edges, end)
        return [node_id for node_id in held if node_id in forward and node_id in backward]

    def run(
        self,
        inputs: Any,
        *,
        envelope: RunEnvelope | None = None,
        model: ModelClient | None = None,
        seed: int | None = None,
        run_id: str | None = None,
        conversation_id: str | None = None,
        memory_scope: str | None = None,
        on_progress: Callable[[NodeEvent], None] | None = None,
        on_token: Callable[[TokenEvent], None] | None = None,
        on_reasoning: Callable[[TokenEvent], None] | None = None,
        stop_when: Callable[[], bool] | None = None,
        concurrency: int = 1,
    ) -> RunResult:
        """Execute the pipeline, threading each node's output into the next.

        The manifest and the trajectory are written whether or not the run completes, so a
        failure keeps the records written before it::

            env = RunEnvelope(run_dir="runs/")
            result = pipeline.run({"corpus": "corpus/"}, envelope=env, model=client, seed=41)

            result.output           # what the last node returned
            result.cost             # derived against the envelope's basis
            result.paths.manifest   # runs/<run_id>/manifest.json

        ``seed`` governs sampling throughout the run, and unset it is generated and recorded.
        ``concurrency`` is the most calls in flight at once, over work declared as overlapping::

            pipeline.run(inputs, envelope=env, model=client, concurrency=8)

        ``conversation_id`` names the conversation this run is a turn of, which a node takes
        part in by reading ``ctx.conversation`` in its prompt (``docs/conversation.md``)::

            pipeline.run(question, envelope=env, model=client,
                         conversation_id=f"chat-{chat_id}")

        ``memory_scope`` names whose memory this run reads and writes (``docs/memory.md``)::

            pipeline.run(question, envelope=env, model=client,
                         memory_scope=f"user-{user_id}")

        ``stop_when`` is checked before each node and stops the run where it returns true,
        which parks the work for a process about to be replaced. The run is resumable::

            paused = threading.Event()
            pipeline.run(inputs, envelope=env, model=client, stop_when=paused.is_set)

        ``on_token`` receives a :class:`~simple_agents.TokenEvent` for each piece of content a
        node declaring ``stream=True`` produces, and passing it is what turns streaming on::

            pipeline.run(inputs, envelope=env, model=client,
                         on_token=lambda e: sys.stdout.write(e.text))

        ``on_reasoning`` takes the same events for a chain of thought reported separately, and
        is independent of ``on_token``. A reasoning model can send thousands of tokens before
        its first word of answer, so a display showing progress reads this one::

            pipeline.run(inputs, envelope=env, model=client, on_token=render,
                         on_reasoning=lambda e: status.update(e.text))

        Raises :class:`ConfigurationError` where no node declares ``stream=True``, the client
        cannot stream, or ``on_reasoning`` was given to one whose ``stream`` refuses it;
        :class:`BudgetExceeded` when the budget is exhausted between nodes; and
        :class:`RunSuspended` when the run stopped and can be continued.
        """
        envelope = envelope if envelope is not None else RunEnvelope()
        _refuse_unserved(self, model)
        _refuse_unauditable_cost(self, envelope, model)
        _refuse_unpriceable(self, envelope, model)
        _refuse_mixed_currencies(self, envelope)
        _refuse_unreachable_memory(self, envelope, memory_scope, "Pipeline.run")
        _refuse_an_unstored_conversation(self, envelope, conversation_id)
        _warn_bounded_cost_limit(self, envelope)
        _refuse_unstreamable(self, on_token, model, on_reasoning)

        started = self._start_run(
            run_id=run_id,
            envelope=envelope,
            model=model,
            seed=seed,
            concurrency=concurrency,
            inputs=inputs,
            on_token=on_token,
            on_reasoning=on_reasoning,
            on_progress=on_progress,
            conversation_id=conversation_id,
            memory_scope=memory_scope,
        )
        run, envelope, paths, writer, manifest, defaulted_cassette = started

        # Before the first node, so a run whose process is killed still says what it was asked
        # to do. A `node_execution` record lands when its node finishes, and a run that died
        # inside its first node would otherwise record its inputs nowhere.
        writer.write(
            RunStartRecord(
                record_id=run.new_record_id(),
                run_id=run.run_id,
                sequence=PENDING_SEQUENCE,
                started_at=utc_now(),
                inputs=inputs,
                seed=run.seed,
            ),
            number=run.next_sequence,
        )
        manifest.count_record("run_start")

        return self._drive(
            inputs=inputs,
            run=run,
            envelope=envelope,
            paths=paths,
            writer=writer,
            manifest=manifest,
            model=model,
            on_progress=on_progress,
            stop_when=stop_when,
            defaulted_cassette=defaulted_cassette,
        )

    def rerun(
        self,
        run_dir: str | os.PathLike[str],
        *,
        envelope: RunEnvelope,
        model: ModelClient | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """Run again what a dead run was given, replaying the calls it already paid for.

        For a run whose process ended without writing an outcome: an out-of-memory kill, a
        container eviction, a deploy restart. It reads that run's inputs and seed off its
        record and serves its recorded calls from its own cassette, so the nodes that finished
        re-execute for free and only what never finished is paid for::

            dead = [r for r in runs("runs/") if r.liveness == "abandoned"]
            result = pipeline.rerun(dead[0].path, envelope=env, model=client)

        Anything :meth:`run` takes may be passed through, and ``envelope`` is required because
        the new run needs somewhere of its own to write. Passing ``seed=`` overrides the dead
        run's, which changes what the cassette can answer and is rarely what is wanted.

        **The result is a new run.** It takes its own id and its own directory, and its record
        says a run that replayed most of its calls. The dead run stays on disk as it was.

        **A node body that reads a clock or ``random`` directly rather than through a tool
        diverges**, and from that point the calls hash to keys the cassette has no entry for
        and are made live. That costs money rather than being wrong.

        Raises :class:`~simple_agents.errors.ConfigurationError` where the run recorded no
        inputs, which is a run written before this library recorded them and one whose payloads
        were not kept.
        """
        directory = Path(run_dir)
        inputs, seed = _what_a_run_was_given(directory)
        cassette = envelope.cassette
        # The dead run's own recording is the default and not an override: a caller who named
        # a cassette gets theirs, and one who named none gets the file with the calls in it.
        if cassette.awaiting_path or cassette.mode is CassetteMode.OFF:
            cassette = Cassette.update(directory / CASSETTE_NAME)
        # The dead run's seed unless the caller named one, so passing `seed=` overrides rather
        # than raising for two values of one argument.
        kwargs.setdefault("seed", seed)
        return self.run(
            inputs, envelope=replace(envelope, cassette=cassette), model=model, **kwargs
        )

    def resume(
        self,
        run_id: str,
        *,
        envelope: RunEnvelope | None = None,
        model: ModelClient | None = None,
        answer: Any = None,
        answers: dict[str, Any] | None = None,
        memory_scope: str | None = None,
        on_progress: Callable[[NodeEvent], None] | None = None,
        on_token: Callable[[TokenEvent], None] | None = None,
        on_reasoning: Callable[[TokenEvent], None] | None = None,
        stop_when: Callable[[], bool] | None = None,
        wait: bool = False,
        accept_changed: Sequence[str] = (),
        concurrency: int = 1,
    ) -> RunResult:
        """Continue a suspended run, against the pipeline it was started with.

        The run keeps its id, its trajectory and its manifest, so what comes out is one run::

            try:
                result = pipeline.run(inputs, envelope=env, model=client)
            except RunSuspended as stop:
                answer = ask_someone(stop.waiting_for, stop.options)
                result = pipeline.resume(stop.run_id, envelope=env, model=client,
                                         answer=answer)

        ``answer`` is what the suspended call returns: the end user's reply to a ``consult``,
        or what the tool that raised ``Suspend`` waited for. A run stopped at a node boundary
        takes none; one stopped in several nodes takes ``answers``, keyed by node::

            answers = {stop["node_id"]: ask_someone(stop["waiting_for"], stop["options"])
                       for stop in suspended.stops}
            pipeline.resume(run_id, envelope=env, model=client, answers=answers)

        ``memory_scope`` is given again because the manifest records it as a digest, and one
        whose digest differs from the run's is refused (``docs/memory.md``)::

            pipeline.resume(run_id, envelope=env, model=client, answer=reply,
                            memory_scope=f"user-{user_id}")

        The suspension is claimed before anything runs, so two workers cannot both continue
        one run. A resume that fails part-way leaves the suspension where it found it, so the
        run is resumed again and the nodes the failed attempt completed write their records
        twice.

        The pipeline is checked against what the run recorded before any state is restored.
        A change of shape is refused outright, and a change of prompt, route, tool version,
        model pin, cost basis or redaction rules unless it is named::

            pipeline.resume(run_id, envelope=env, model=client, answer=answer,
                            accept_changed=["prompts.hunt"])

        The waiver is recorded in the manifest, so a number that moved can be traced to it.

        Raises :class:`CallerFacingError` where the run is not suspended, where the pipeline
        differs, or where it waits on a time that has not passed; ``wait=True`` blocks instead.
        """
        envelope = envelope if envelope is not None else RunEnvelope()
        _refuse_unserved(self, model)
        _refuse_unreachable_memory(self, envelope, memory_scope, "Pipeline.resume")
        _refuse_unstreamable(self, on_token, model, on_reasoning)
        root = find_run(envelope.run_dir, run_id) or Path(envelope.run_dir) / run_id
        state = claim_state(root)
        try:
            self._refuse_early(state, root, wait)
            paths = envelope.paths_at(root)
            envelope, defaulted_cassette = _resolve_cassette(envelope, paths.root)
            manifest = self._restored_manifest(paths, state, envelope, model, accept_changed)
            refuse_another_scope(memory_scope, (manifest.memory or {}).get("scope_digest"))
            writer = TrajectoryWriter(paths.trajectory, redactor=envelope.redaction)
            run = self._restored_context(
                run_id=run_id,
                paths=paths,
                state=state,
                envelope=envelope,
                manifest=manifest,
                writer=writer,
                memory_scope=memory_scope,
                concurrency=concurrency,
                sinks=(on_token, on_reasoning, on_progress),
            )
            _pace_clients(self, model, concurrency, replaying=envelope.cassette.is_replaying)
            _warn_declarations_the_run_cuts(
                self, concurrency, replaying=envelope.cassette.is_replaying
            )
            run.spend = Spend.from_record(state.spend)
            run.restore_counters(state.counters)
            codec = self._codec()
            frame = _Frame.restored(self.graph, state.frames[0], codec)
            # Everything that can refuse this resume runs while the claim can still be put
            # back. A typo in `answers=` is the likeliest mistake a caller makes here, and the
            # refusal invites a corrected retry, which needs the suspension to still be there.
            restored_inputs = codec.decode(state.inputs, source=None)
            # Set here rather than on the constructor: the inputs are rebuilt from the
            # suspension through the codec, which needs the graph's declared schemas.
            run.run_inputs = restored_inputs
            for_nodes = self._answers_for(state, answer, answers)
        except Exception:
            release_claim(root)
            raise

        return self._drive_resumed(
            root,
            state,
            envelope.redaction,
            inputs=restored_inputs,
            run=run,
            envelope=envelope,
            paths=paths,
            writer=writer,
            manifest=manifest,
            model=model,
            on_progress=on_progress,
            stop_when=stop_when,
            defaulted_cassette=defaulted_cassette,
            frame=frame,
            answers=for_nodes,
        )

    def _drive_resumed(
        self, root: Path, state: SuspensionState, redaction: Any, **driving: Any
    ) -> RunResult:
        """Drive a resumed run, leaving its suspension where it was found if the run fails.

        A resume that failed part-way is tried again rather than the run being started over.
        The state is written back rather than renamed back, so nothing holds a claim while
        the run executes and two workers still cannot both continue one run.
        """
        discard_claim(root)
        try:
            return self._drive(**driving)
        except RunSuspended:
            # The run stopped again and wrote its own state, which is later than this one.
            raise
        except BaseException:
            write_state(root, state, redaction)
            raise

    def _restored_context(
        self,
        *,
        run_id: str,
        paths: RunPaths,
        state: SuspensionState,
        envelope: RunEnvelope,
        manifest: Manifest,
        writer: TrajectoryWriter,
        memory_scope: str | None,
        concurrency: int,
        sinks: tuple[Any, Any, Any],
    ) -> RunContext:
        """The run context a resumed run continues in, off what the suspension recorded.

        ``sinks`` are the token, reasoning and progress callbacks in that order. The spend and
        the counters are restored by the caller, which holds the codec that decodes them.
        """
        token_sink, reasoning_sink, progress_sink = sinks
        return RunContext(
            run_id=run_id,
            writer=writer,
            budget=self.budget,
            workspace=paths.workspace,
            seed=state.seed,
            manifest=manifest,
            cassette=envelope.cassette,
            cost_basis=envelope.cost_basis,
            redaction=envelope.redaction,
            memory=_scoped_memory(envelope, memory_scope),
            end_user=envelope.end_user,
            # Which conversation this run is a turn of comes from what it recorded when it
            # started, so a resume continues the turn it stopped in rather than needing to be
            # told again which chat it was.
            conversation=_restored_conversation(envelope, manifest),
            token_sink=token_sink,
            reasoning_sink=reasoning_sink,
            progress_sink=progress_sink,
            pool=WorkPool(ceiling=concurrency),
            fetch_policy_declaration=self.fetch_policy,
        )

    def _answers_for(
        self, state: SuspensionState, answer: Any, answers: dict[str, Any] | None
    ) -> dict[str, Any]:
        """What each stopped node is handed, keyed by node.

        ``answers`` is taken as given. A bare ``answer`` belongs to the one node that stopped,
        and is refused where several did, since which of them it is for is undeclared.
        """
        if answers is not None:
            unknown = sorted(set(answers) - {stop["node_id"] for stop in state.stops})
            if unknown:
                raise CallerFacingError(
                    f"resume(answers=...) names {', '.join(repr(u) for u in unknown)}, and "
                    f"this run did not stop in "
                    f"{'that node' if len(unknown) == 1 else 'those nodes'}. It stopped in "
                    f"{', '.join(repr(stop['node_id']) for stop in state.stops)}.\n"
                    f"Key each answer by the node it belongs to, which `stop.stops` names."
                )
            return dict(answers)
        if answer is None:
            return {}
        if len(state.stops) > 1:
            raise CallerFacingError(
                f"This run stopped in "
                f"{', '.join(repr(stop['node_id']) for stop in state.stops)} at once, and "
                f"resume(answer=...) is one answer with nothing saying which of them it is "
                f"for.\n"
                f"Pass resume(answers={{...}}) instead, keyed by node: "
                f"{{{', '.join(repr(stop['node_id']) + ': ...' for stop in state.stops)}}}."
            )
        return {state.stops[0]["node_id"]: answer}

    def _refuse_early(self, state: SuspensionState, root: Path, wait: bool) -> None:
        """Refuse a resume whose time has not come, or block until it has.

        Nothing here runs on its own. ``wait=True`` sleeps in the caller's process, which is
        the caller's choice with its duration visible; the default states how long is left and
        leaves the waiting to whatever restarts the process.
        """
        left = state.wait_seconds()
        if left <= 0:
            return
        if wait:
            time.sleep(left)
            return
        raise CallerFacingError(
            f"Run {state.run_id} is waiting for {state.waiting_for} and cannot be resumed "
            f"before {state.resume_not_before}, which is {int(left)}s away.\n"
            f"Resume it after that time, or pass wait=True to block until then. "
            f"Pipeline.suspensions({str(root.parent)!r}) reports which runs are ready."
        )

    def _restored_manifest(
        self,
        paths: RunPaths,
        state: SuspensionState,
        envelope: RunEnvelope,
        model: ModelClient | None,
        accept_changed: Sequence[str],
    ) -> Manifest:
        """The suspended run's manifest, continued rather than started again.

        The pipeline being resumed is checked against what that manifest recorded before any
        state is restored.
        """
        raw = json.loads(paths.manifest.read_text(encoding="utf-8"))
        self._verify_against(raw, envelope, model, accept_changed)
        manifest = Manifest.restore(raw)
        manifest.resume_waivers = sorted({*manifest.resume_waivers, *accept_changed})
        manifest.note_resumption(utc_now())
        return manifest

    def _verify_against(
        self,
        raw: dict[str, Any],
        envelope: RunEnvelope,
        model: ModelClient | None,
        accept_changed: Sequence[str],
    ) -> None:
        """Refuse a resume against a pipeline that is not the one the run was started with.

        Two tiers. A change of shape is refused outright, because the stored state is keyed on
        node ids and a different graph makes it meaningless rather than stale. A change of
        version is refused unless it is named in ``accept_changed``, and the waiver is recorded
        in the manifest so a number that moves has something to be traced to (FT-15).
        """
        self._refuse_a_changed_shape(raw)
        nodes, prompts, tools, containers = _node_entries(self)
        changed: list[str] = []
        for node_id, version in prompts.items():
            was_version = ((raw.get("prompts") or {}).get(node_id) or {}).get("version")
            if was_version != version["version"]:
                changed.append(f"prompts.{node_id}")
        # A delegation's description and argument schema are prompt text and are compared the
        # way a prompt is: an edit changes what the model was shown without changing the graph.
        for entry in containers:
            if entry.get("reached_by") is None:
                continue
            was = next(
                (c for c in raw.get("containers") or [] if c["node_id"] == entry["node_id"]),
                {},
            )
            for field_name in ("description", "input_schema"):
                if (was.get("reached_by") or {}).get(field_name) != entry["reached_by"][field_name]:
                    changed.append(f"delegates.{entry['node_id']}.{field_name}")
        for entry in nodes:
            was = next((n for n in raw.get("nodes") or [] if n["node_id"] == entry["node_id"]), {})
            if was.get("route") != entry["route"]:
                changed.append(f"route.{entry['node_id']}")
            if (was.get("fn") or {}).get("version") != (entry.get("fn") or {}).get("version"):
                changed.append(f"fn.{entry['node_id']}")
        for entry in tools:
            was = next((t for t in raw.get("tools") or [] if t["name"] == entry["name"]), {})
            if was.get("version") != entry["version"]:
                changed.append(f"tools.{entry['name']}")
        pinned = model.identity().to_manifest() if model is not None else None
        if (raw.get("models") or {}).get("configured") != pinned:
            changed.append("model")
        for entry in nodes:
            was = next((n for n in raw.get("nodes") or [] if n["node_id"] == entry["node_id"]), {})
            if was.get("model") != entry.get("model"):
                changed.append(f"model.{entry['node_id']}")
        basis = basis_to_manifest(envelope.cost_basis)
        if raw.get("cost_basis") != basis:
            changed.append("cost_basis")
        if raw.get("redaction") != envelope.redaction.to_manifest():
            changed.append("redaction")

        unwaived = sorted(set(changed) - set(accept_changed))
        if unwaived:
            raise CallerFacingError(
                f"Run {raw['run_id']} was suspended under a different "
                f"{'configuration' if len(unwaived) > 1 else unwaived[0]}, and half its "
                f"trajectory was produced by what it had then: "
                f"{', '.join(unwaived)}.\n"
                f"Resume against what the run was started with, or accept the difference "
                f"explicitly with accept_changed={unwaived!r}, which is recorded in the "
                f"manifest so a number that moved can be traced to it."
            )

    def _refuse_a_changed_shape(self, raw: dict[str, Any]) -> None:
        """Refuse a resume against a graph of a different shape, naming what moved.

        The stored state is keyed on node ids, so a different graph makes it meaningless
        rather than stale, and no waiver covers it.
        """
        if raw.get("graph_fingerprint") == self.graph_fingerprint():
            return
        was = {entry["node_id"]: _structure(entry) for entry in raw.get("nodes") or []} | {
            entry["node_id"]: _container_structure(entry) for entry in raw.get("containers") or []
        }
        now = {entry["node_id"]: _structure(entry) for entry in self.manifest_nodes()} | {
            entry["node_id"]: _container_structure(entry) for entry in self.manifest_containers()
        }
        raise CallerFacingError(
            f"Run {raw['run_id']} was suspended by a pipeline of a different shape, and "
            f"its state is keyed on node ids, so restoring it here would put values on "
            f"edges that no longer mean the same thing.\n"
            f"{_describe_shape_change(was, now)}\n"
            f"Resume against the pipeline the run was started with. This one cannot be "
            f"waived: start a new run instead."
        )

    @staticmethod
    def suspensions(run_dir: Any) -> list[SuspensionState]:
        """Every suspended run under ``run_dir``, whether or not it is ready to continue.

        What a project's own worker reads to drive resumption. The library runs no worker of
        its own::

            for state in Pipeline.suspensions("runs/"):
                if state.ready:
                    rebuild(state.run_id).resume(state.run_id, envelope=env, model=client)
        """
        found: list[SuspensionState] = []
        for child in sorted(Path(run_dir).glob(f"**/{SUSPENSION_NAME}")):
            state = read_state(child.parent)
            if state is not None:
                found.append(state)
        return found

    @staticmethod
    def answer_shelved(
        run_dir: Any,
        *,
        answer: Any,
        about: str | None = None,
        record_id: str | None = None,
        pipeline: "Pipeline | None" = None,
        envelope: RunEnvelope | None = None,
        model: ModelClient | None = None,
        run_id: str | None = None,
        seed: int | None = None,
        memory_scope: str | None = None,
    ) -> "AnsweredQuestion":
        """File an answer to a question a finished run shelved, and act on it.

        The run that asked has ended, so there is nothing to resume. This starts a run of its
        own: the answer is its first record, and ``pipeline`` is the work the answer triggers::

            Pipeline.answer_shelved("runs/", about="show:1421", answer="gave up on it",
                                    pipeline=drop_from_up_next, envelope=env)

        Called from whatever handles the reply, and nothing in the library watches for one.

        ``pipeline`` receives an :class:`Answered` and may be left unset, where the answer is
        recorded and nothing else runs. ``about`` names which question, and ``record_id`` names
        one exactly where two are outstanding about the same thing.

        ``answer`` is what the person said, matched against the options the question offered
        by the same whole-answer rule :func:`~simple_agents.builtins.consult` uses; a project
        whose rule reads more builds the ``Reply`` itself. ``None`` is recorded ``declined``.

        ``memory_scope`` names whose memory the answering run reaches (``docs/memory.md``).

        Raises :class:`~simple_agents.errors.CallerFacingError` where no question matches and
        where another worker holds the shelf. Everything that can refuse runs before the answer
        is recorded, so the question stays outstanding; once it is recorded the question leaves
        the shelf, and a failure in ``pipeline`` is reported by that run.
        """
        found, root, shelf = _claim_the_question(run_dir, about=about, record_id=record_id)
        try:
            # Everything that can refuse runs while the claim can still be put back, which is
            # what `resume` does with a suspension and for the same reason.
            reply = _read_a_filed_answer(answer, found.options)
            acting = pipeline if pipeline is not None else _JUST_RECORDS_IT
            envelope = envelope if envelope is not None else RunEnvelope(run_dir=run_dir)
            _refuse_unreachable_memory(acting, envelope, memory_scope, "answer_shelved")
            # Built before the run starts, because it is what the run is given and so what
            # `ctx.run_inputs` reads.
            answered = Answered(
                about=found.about,
                prompt=found.prompt,
                options=found.options,
                answer=reply,
                asked_at=found.asked_at,
                asking_run_id=found.run_id,
                asking_record_id=found.record_id,
            )
            run, envelope, paths, writer, manifest, defaulted = acting._start_run(
                run_id=run_id,
                envelope=envelope,
                model=model,
                seed=seed,
                concurrency=1,
                inputs=answered,
                memory_scope=memory_scope,
            )
        except BaseException:
            release_shelf(root)
            raise

        # The answer is on the record from here, so the question leaves the shelf whatever the
        # work makes of it. Putting it back would leave one question with a record saying it
        # was answered and a shelf saying it was not, and answering it again would write a
        # second answering record for it.
        answering_id = _record_the_answer(run, found, reply)
        settle_shelf(root, shelf.without(found.record_id), envelope.redaction)
        result = acting._drive(
            inputs=answered,
            run=run,
            envelope=envelope,
            paths=paths,
            writer=writer,
            manifest=manifest,
            model=model,
            on_progress=None,
            stop_when=None,
            defaulted_cassette=defaulted,
        )
        return AnsweredQuestion(
            run_id=run.run_id, record_id=answering_id, question=found, result=result
        )

    def _start_run(
        self,
        *,
        run_id: str | None,
        envelope: RunEnvelope,
        model: ModelClient | None,
        seed: int | None,
        concurrency: int,
        inputs: Any = None,
        on_token: Any = None,
        on_reasoning: Any = None,
        on_progress: Any = None,
        conversation_id: str | None = None,
        memory_scope: str | None = None,
    ) -> tuple[RunContext, RunEnvelope, Any, TrajectoryWriter, Manifest, bool]:
        """Everything a run needs before its first node: its id, its files and its context.

        Shared by :meth:`run` and :meth:`answer_shelved`, so a run that exists to record an
        answer writes the same artifacts as one that exists to do work.
        """
        run_id = run_id or new_run_id()
        paths = envelope.prepare(run_id)
        envelope, defaulted_cassette = _resolve_cassette(envelope, paths.root)
        seed = seed if seed is not None else _seed_for(envelope.cassette)

        # Before the manifest, because reading a server fills in every declared tool's
        # description, schema and version, and the manifest records all three.
        mcp = _read_mcp_servers(self, envelope.cassette)

        conversation = (
            envelope.conversations.under(envelope.redaction).thread(conversation_id)
            if conversation_id is not None and envelope.conversations is not None
            else None
        )
        memory = _scoped_memory(envelope, memory_scope)
        manifest = _new_manifest(
            self,
            run_id=run_id,
            seed=seed,
            envelope=envelope,
            paths=paths,
            model=model,
            concurrency=concurrency,
            conversation=conversation,
            memory=memory,
        )
        manifest.mcp = mcp
        manifest.write(paths.manifest)

        writer = TrajectoryWriter(paths.trajectory, redactor=envelope.redaction)
        run = RunContext(
            run_id=run_id,
            writer=writer,
            budget=self.budget,
            workspace=paths.workspace,
            run_inputs=inputs,
            seed=seed,
            manifest=manifest,
            cassette=envelope.cassette,
            cost_basis=envelope.cost_basis,
            redaction=envelope.redaction,
            memory=memory,
            end_user=envelope.end_user,
            conversation=conversation,
            token_sink=on_token,
            reasoning_sink=on_reasoning,
            progress_sink=on_progress,
            pool=WorkPool(ceiling=concurrency),
            fetch_policy_declaration=self.fetch_policy,
        )
        _pace_clients(self, model, concurrency, replaying=envelope.cassette.is_replaying)
        _warn_declarations_the_run_cuts(self, concurrency, replaying=envelope.cassette.is_replaying)
        return run, envelope, paths, writer, manifest, defaulted_cassette

    @staticmethod
    def shelved(run_dir: Any) -> list[ShelvedQuestion]:
        """Every question left outstanding under ``run_dir``, oldest run first.

        What a surface renders as a list of open questions, and what a project's own worker
        reads to decide what to ask about next. The library runs no worker of its own::

            for question in Pipeline.shelved("runs/"):
                page.show(question.prompt, question.options, key=question.about)

        Read from a file each run writes beside its manifest rather than from the
        trajectories, so listing them costs one read per run that shelved something.
        :meth:`answer_shelved` is how one is answered.
        """
        found: list[ShelvedQuestion] = []
        for child in sorted(Path(run_dir).glob(f"**/{SHELF_NAME}")):
            shelf = read_shelf(child.parent)
            if shelf is not None:
                found.extend(shelf.questions)
        return found

    def _drive(
        self,
        *,
        inputs: Any,
        run: RunContext,
        envelope: RunEnvelope,
        paths: RunPaths,
        writer: TrajectoryWriter,
        manifest: Manifest,
        model: ModelClient | None,
        on_progress: Callable[[NodeEvent], None] | None,
        stop_when: Callable[[], bool] | None,
        defaulted_cassette: bool = False,
        frame: _Frame | None = None,
        answers: dict[str, Any] | None = None,
    ) -> RunResult:
        """Walk the graph and close the run out, whether it is starting or being resumed.

        Shared by :meth:`run` and :meth:`resume`, so a resumed run writes the same artifacts
        and reports the same way as one that never stopped.
        """
        value = inputs
        stopped_early: str | None = None
        outcome = "error"
        suspended: _Suspending | None = None

        try:
            try:
                try:
                    # The wall-clock axis is elapsed time while the run is executing, so the
                    # clock runs here and stops when the walk returns or the run goes to disk.
                    with run.executing():
                        value = self._walk(
                            inputs,
                            run,
                            model,
                            on_progress=on_progress,
                            frame=frame,
                            stop_when=stop_when,
                            answers=answers,
                        )
                except BudgetExceeded as exc:
                    stopped_early = exc.axis
                    raise
                except LeftTheSlice:
                    stopped_early = "left_the_slice"
                    raise
                except _Suspending as exc:
                    suspended = exc
                    outcome = "suspended"
                    stopped_at = utc_now()
                    # One entry per node that stopped. Arms that were overlapping stop
                    # together, and the manifest is the durable record of what the run was
                    # waiting on, so each of them is named rather than only the first.
                    for stop in exc.stops:
                        manifest.note_suspension(
                            at=stopped_at,
                            node_id=stop.node_id,
                            waiting_for=stop.suspend.waiting_for,
                        )
                    raise
                _refuse_a_swallowed_suspension(run)
                outcome = "completed"
            finally:
                writer.close()
                # A question left for somebody to answer later outlives the run that asked it,
                # and reading them out of the trajectories is not something a surface can do
                # per page load.
                write_shelf(
                    Path(paths.root),
                    Shelf(run_id=run.run_id, questions=run.shelved_questions()),
                    envelope.redaction,
                )
                closed = _close_manifest(
                    self,
                    manifest=manifest,
                    paths=paths,
                    envelope=envelope,
                    outcome=outcome,
                    stopped_early=stopped_early,
                    charged=run.spend.cost,
                    defaulted_cassette=defaulted_cassette,
                    run=run,
                )
        except _Suspending:
            assert suspended is not None
            state = SuspensionState(
                run_id=run.run_id,
                seed=run.seed,
                suspended_at=utc_now(),
                stops=[
                    {
                        "node_id": stop.node_id,
                        "waiting_for": stop.suspend.waiting_for,
                        "options": stop.suspend.options,
                        "resume_not_before": stop.suspend.resume_not_before,
                    }
                    for stop in suspended.stops
                ],
                inputs=self._codec().encode(inputs, source=None),
                spend=run.spend.to_record(),
                counters=run.counters(),
                frames=suspended.frames,
            )
            written = write_state(paths.root, state, envelope.redaction)
            raise RunSuspended(
                run_id=run.run_id,
                state_path=written,
                waiting_for=state.waiting_for,
                node_id=state.node_id,
                options=state.options,
                resume_not_before=state.resume_not_before,
                stops=tuple(state.stops),
            ) from None

        return RunResult(
            run_id=run.run_id, output=value, paths=paths, seed=run.seed, manifest=closed
        )

    # -- the walk -------------------------------------------------------------------------

    def execute(
        self,
        inputs: Any,
        run: RunContext,
        model: ModelClient | None = None,
        execution: Execution | None = None,
        on_progress: Callable[[NodeEvent], None] | None = None,
        frames: list[dict[str, Any]] | None = None,
        stop_when: Callable[[], bool] | None = None,
        answer: Any = None,
        answers: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> NodeOutcome:
        """Run this pipeline as one node of another, or as a subtask a model delegated.

        No ``node_execution`` record is written for the pipeline itself. Its nodes write their
        own, under ids prefixed by this pipeline's ``node_id``, so per-node metrics and ablation
        stay keyed on something unique and every record names one of the three node kinds.

        ``frames`` is what a resumed run stopped inside this pipeline carries: its own frame,
        which holds the frames of anything nested below it.

        ``answer`` is what one delegated subtask was waiting for, and ``answers`` is what each
        node inside this pipeline was waiting for, keyed by node. A pipeline used as a node
        takes the second, because the stop is in one of its own nodes rather than in it.

        ``parent_id`` is the ``delegation`` record every node here writes inside, and ``None``
        for a pipeline the run reached along an edge.
        """
        frame = None
        if frames:
            frame = _Frame.restored(self.graph, frames[0], self._codec())
            # A resumed delegation writes a new record, so the restored frame's parent names a
            # record from the process that stopped and is replaced here.
            frame.parent_id = parent_id
        prefix = f"{execution.node_id}." if execution is not None else f"{self.node_id}."
        return NodeOutcome(
            outputs=self._walk(
                inputs,
                run,
                model,
                prefix=prefix,
                on_progress=on_progress,
                frame=frame,
                stop_when=stop_when,
                answers=(
                    answers
                    if answers is not None
                    else {f"{prefix}{node_id}": answer for node_id in frame.in_progress}
                    if frame is not None and answer is not None
                    else None
                ),
                parent_id=parent_id,
            )
        )

    def _walk(
        self,
        inputs: Any,
        run: RunContext,
        model: ModelClient | None,
        *,
        prefix: str = "",
        on_progress: Callable[[NodeEvent], None] | None = None,
        frame: _Frame | None = None,
        stop_when: Callable[[], bool] | None = None,
        answers: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> Any:
        """Execute the graph, and return what the node with no successors produced.

        A node runs once every declared in-edge has resolved. An in-edge resolves either
        carrying a value or absent, and a node whose in-edges are all absent does not run.
        Nodes that are ready run one at a time, in the order they appear in the list, unless
        the pipeline listed them in one ``concurrent_nodes`` group.

        ``frame`` is a restored :class:`_Frame` for a run being resumed. The nodes named by its
        ``in_progress`` run first, before the walk starts choosing again, a node the run
        stopped inside is not charged or counted a second time, and its ``node_state`` is what
        that node held.

        ``stop_when`` is the caller's own reason to stop, checked between nodes. ``answers``
        holds what each stopped node was waiting for, keyed by node. ``parent_id`` is the
        record every node here writes inside.
        """
        graph = self.graph
        frame = frame if frame is not None else self._new_frame(run, prefix, parent_id)
        edges = frame.edges
        produced = frame.produced
        opened = frame.opened
        prefix = frame.prefix
        answers = dict(answers or {})
        # Taken off the frame once: the nodes it belongs to run first, and a node reached later
        # in the same walk starts from nothing.
        held, frame.node_state = frame.node_state, {}
        nested, frame.below = frame.below, {}

        while True:
            if frame.in_progress:
                batch, frame.in_progress = list(frame.in_progress), []
                resumed = True
            else:
                batch = self._batch(edges)
                resumed = False
            if not batch:
                break

            if not resumed:
                batch = self._skip_unreached(
                    batch, run, edges, prefix, frame.parent_id, on_progress
                )
                if not batch:
                    continue
                # Nothing has run yet in this batch, so one check answers for all of it.
                self._charge_or_stop(run, opened)
                batch = self._up_to_a_declared_stop(batch, frame, stop_when, prefix)

            prepared: list[tuple[str, Any]] = []
            for node_id in batch:
                node = graph.by_id[node_id]
                if not (resumed and node_id in edges.done):
                    edges.enter(node_id)
                prepared.append((node_id, node))

            def unit(node_id: str = "", node: Any = None, resumed: bool = resumed) -> Any:
                iteration = edges.visits.get(node_id, 1)
                node_inputs = edges.inputs_for(node_id, inputs)
                # What the node reads, against the value itself. The graph is checked at
                # construction, and a node before this one that declares nothing is checked
                # here.
                refuse_value_arriving(node, node_inputs, edges.source_of(node_id))
                _announce(on_progress, "started", f"{prefix}{node_id}", node, iteration=iteration)
                return node_inputs, self._attempt(
                    node,
                    node_inputs,
                    run,
                    model,
                    edges,
                    prefix,
                    on_progress,
                    # Only a node the run stopped at is handed what was captured below it. A
                    # node reached later in the same walk starts from nothing.
                    frames=nested.get(node_id) if resumed else None,
                    stop_when=stop_when,
                    node_state=held.get(node_id) if resumed else None,
                    answer=answers.pop(f"{prefix}{node_id}", None) if resumed else None,
                    # A pipeline used as a node did not stop: one of its own nodes did, and
                    # `stop.stops` names that node. What is keyed by node therefore travels
                    # down rather than being looked up under the container's id.
                    answers=answers if resumed and isinstance(node, Pipeline) else None,
                    parent_id=frame.parent_id,
                )

            outcomes = run.pool.map(
                [
                    lambda node_id=node_id, node=node: unit(node_id, node)
                    for node_id, node in prepared
                ],
                limit=len(prepared),
                stops_on=lambda exc: True,
            )

            stopping: BaseException | None = None
            suspending: _Suspending | None = None
            for (node_id, node), result in zip(prepared, outcomes):
                if result.error is not None:
                    if isinstance(result.error, _Suspending):
                        suspending = self._collect_stop(suspending, result.error, frame, node_id)
                    elif stopping is None:
                        stopping = result.error
                    continue
                if not result.started:
                    # Drained before it began: its entry is taken back, so the walk chooses it
                    # again and its loop count is what it would have been.
                    edges.unenter(node_id)
                    continue
                node_inputs, outcome = result.value
                self._settle(
                    node=node,
                    node_id=node_id,
                    outcome=outcome,
                    node_inputs=node_inputs,
                    run=run,
                    edges=edges,
                    produced=produced,
                    frame=frame,
                    prefix=prefix,
                    on_progress=on_progress,
                    resumed=resumed,
                    held=held.get(node_id),
                )

            if suspending is not None:
                suspending.frames = [frame.snapshot(self._codec())]
                raise suspending
            if stopping is not None:
                raise stopping
            if edges.left_the_slice is not None:
                raise edges.left_the_slice

        if graph.terminal not in produced:
            raise CallerFacingError(
                f"No path through this pipeline reached {graph.terminal!r}, the node whose "
                f"output the run returns, so the run produced nothing. Every route selects at "
                f"least one successor, so a branch that ends early has to route to "
                f"{graph.terminal!r} rather than stopping.\n"
                f"The nodes that ran were {', '.join(repr(p) for p in produced) or 'none'}."
            )
        return produced[graph.terminal]

    def _settle(
        self,
        *,
        node: Any,
        node_id: str,
        outcome: Any,
        node_inputs: Any,
        run: RunContext,
        edges: _EdgeState,
        produced: dict[str, Any],
        frame: _Frame,
        prefix: str,
        on_progress: Callable[[NodeEvent], None] | None,
        resumed: bool,
        held: dict[str, Any] | None,
    ) -> None:
        """Write one finished node's record and resolve the edges out of it.

        Done in the walk rather than in the node, and in the order the batch was taken, so
        nodes that overlapped resolve their edges one at a time and a route reads a settled
        graph. A record is written after everything the node did, so a child's ``sequence`` is
        lower than its parent's whichever order the work ran in.
        """
        iteration = edges.visits.get(node_id, 1)
        if isinstance(outcome, NodeFailure):
            _announce(
                on_progress,
                "failed",
                f"{prefix}{node_id}",
                node,
                attempt=outcome.attempts,
                route=(str(node.on_error),),
                error=outcome.error,
            )
            # The node failed and declares an error edge, so the failure travels as data and
            # the run continues along it.
            edges.divert(node_id, str(node.on_error), outcome)
            edges.note_the_boundary(node_id, (str(node.on_error),), kind="on_error")
            return

        chosen, exhausted = self._chosen(node, outcome.outputs, run, edges, iteration)
        left = edges.note_the_boundary(node_id, chosen)
        _emit_node_record(
            run=run,
            node=node,
            execution=outcome.execution,
            inputs=node_inputs,
            outputs=outcome.outputs,
            # A node that knows why it stopped keeps its own reason. `max_iterations` is the
            # graph's reason, and `loop.exhausted` carries it where the node has one.
            termination=(
                "left_the_slice"
                if left
                else outcome.termination or ("max_iterations" if exhausted else None)
            ),
            route=chosen,
            loop=edges.loop_record(node_id),
            resumed_from=(held or {}).get("record_id") if resumed else None,
            parent_id=frame.parent_id,
        )
        _announce(
            on_progress,
            "completed",
            f"{prefix}{node_id}",
            node,
            iteration=iteration,
            route=chosen,
        )
        produced[node_id] = outcome.outputs
        edges.advance(node_id, outcome.outputs, chosen)

    def _batch(self, edges: _EdgeState) -> list[str]:
        """The ready nodes to run next: one, or a group the pipeline said may overlap.

        Taken in the order the nodes appear in the list. The first ready node is always in it,
        and a later one joins where every node already chosen may overlap it, so a group is
        entered only when the pipeline said each pair in it may run at the same time.
        """
        ready = [
            node.node_id
            for node in self.nodes
            if node.node_id not in edges.done and edges.ready(node.node_id)
        ]
        if not ready:
            return []
        batch = [ready[0]]
        for node_id in ready[1:]:
            if all(self.graph.may_overlap(node_id, chosen) for chosen in batch):
                batch.append(node_id)
        return batch

    def _skip_unreached(
        self,
        batch: list[str],
        run: RunContext,
        edges: _EdgeState,
        prefix: str,
        parent_id: str | None,
        on_progress: Callable[[NodeEvent], None] | None,
    ) -> list[str]:
        """Settle the nodes nothing reached, so a skipped node never occupies the pool."""
        remaining: list[str] = []
        for node_id in batch:
            node = self.graph.by_id[node_id]
            if not edges.all_absent(node_id):
                remaining.append(node_id)
                continue
            edges.done.add(node_id)
            self._emit_skip(node, run, edges, prefix, parent_id)
            edges.resolve_all_absent(node_id, f"{node_id!r} was skipped")
            _announce(on_progress, "skipped", f"{prefix}{node_id}", node)
        return remaining

    def _up_to_a_declared_stop(
        self,
        batch: list[str],
        frame: _Frame,
        stop_when: Callable[[], bool] | None,
        prefix: str = "",
    ) -> list[str]:
        """The batch truncated at the first node the run is to stop before.

        A node declaring ``suspend_before``, or the caller's ``stop_when`` returning true,
        stops the run rather than joining the batch. A node later in the batch that declares
        one is left for the next round, where it is first and stops the run then.
        """
        for position, node_id in enumerate(batch):
            node = self.graph.by_id[node_id]
            stops = getattr(node, "suspend_before", False) or (
                stop_when is not None and stop_when()
            )
            if not stops:
                continue
            if position == 0:
                frame.in_progress = [node_id]
                raise self._stop_before(node, frame, stop_when, prefix)
            return batch[:position]
        return batch

    def _collect_stop(
        self,
        suspending: _Suspending | None,
        raised: _Suspending,
        frame: _Frame,
        node_id: str,
    ) -> _Suspending:
        """Fold one node's stop into this level's, keeping what that node held.

        Each stopped node keeps its own held state and its own stack of frames below, so two
        arms that stopped together are two independent places to start from.
        """
        frame.in_progress.append(node_id)
        state = raised.take_node_state()
        if state is not None:
            frame.node_state[node_id] = state
        if raised.frames:
            frame.below[node_id] = list(raised.frames)
        if suspending is None:
            raised.frames = []
            return raised
        suspending.stops.extend(raised.stops)
        return suspending

    def _new_frame(self, run: RunContext, prefix: str, parent_id: str | None = None) -> _Frame:
        """A frame for a walk that is starting rather than being resumed."""
        return _Frame(
            prefix=prefix,
            edges=_EdgeState(self.graph),
            produced={},
            opened=run.spend,
            parent_id=parent_id,
        )

    def _codec(self) -> ValueCodec:
        """How this pipeline's values in flight are written down and read back.

        Built from the declared graph, so the schema a node declared is what its output is
        rebuilt with and no type name is stored.
        """
        return ValueCodec(schema_of=self.graph.schema_of, in_edges=self.graph.in_edges)

    def _stop_before(
        self,
        node: Node,
        frame: _Frame,
        stop_when: Callable[[], bool] | None,
        prefix: str = "",
    ) -> _Suspending:
        """A suspension at a node that has not started, and this frame to restart it from."""
        waiting_for = (
            f"a declared stop before {node.node_id!r}"
            if getattr(node, "suspend_before", False)
            else "the caller's stop_when"
        )
        suspending = _Suspending(Suspend(waiting_for=waiting_for), f"{prefix}{node.node_id}")
        suspending.frames.append(frame.snapshot(self._codec()))
        return suspending

    def _charge_or_stop(self, run: RunContext, opened: Spend) -> None:
        """Raise where a budget is spent, before the next node starts.

        The run budget is checked against everything spent so far. A pipeline nested inside
        another is also checked against its own, over what it has spent since it started, so
        its budget bounds it rather than being tripped by what ran before it.
        """
        _refuse_over_budget(run.budget, run.spend)
        if self.budget is not run.budget:
            _refuse_over_budget(self.budget, _spent_since(opened, run.spend))

    def _attempt(
        self,
        node: Node,
        inputs: Any,
        run: RunContext,
        model: ModelClient | None,
        edges: _EdgeState,
        prefix: str = "",
        on_progress: Callable[[NodeEvent], None] | None = None,
        frames: list[dict[str, Any]] | None = None,
        stop_when: Callable[[], bool] | None = None,
        node_state: dict[str, Any] | None = None,
        answer: Any = None,
        answers: dict[str, Any] | None = None,
        parent_id: str | None = None,
    ) -> _Attempted | NodeFailure:
        """Run one node, retrying it where it declares a policy.

        Every attempt writes its own record, so the failed ones are in the trajectory rather
        than lost behind the one that worked. A failure that survives the last attempt travels
        along ``on_error`` where the node declares one, and propagates where it does not.

        A node that raises has its record written here, since the route that would say where
        its output went never runs.
        """
        policy: RetryPolicy | None = getattr(node, "retry", None)
        attempts = policy.attempts if policy is not None else 1
        # What each kind picks up on the execution the run stopped inside: an AgentNode
        # continues its loop, an LLMNode continues a fan-out at the item it stopped on, and a
        # Deterministic node runs again from the beginning with the call that stopped handed
        # its answer rather than being made a second time.
        node_resume = (
            {"resume_state": node_state, "answer": answer}
            if node_state is not None and isinstance(node, (AgentNode, LLMNode, Deterministic))
            else {}
        )
        # An agent node whose model delegated is handed the frames of the pipeline it stopped
        # inside, the way a container is. A node that made no delegation gets none.
        if frames and isinstance(node, AgentNode):
            node_resume["frames"] = frames
        handler = getattr(node, "on_error", None)
        # The budget a node declares bounds the node, retries included, so what earlier
        # attempts spent is taken off before the next one starts.
        opened = run.spend

        for attempt in range(1, attempts + 1):
            execution = self._execution(node, run, opened, prefix)
            try:
                outcome = (
                    node.execute(
                        inputs,
                        run,
                        model,
                        execution,
                        on_progress,
                        frames=frames,
                        stop_when=stop_when,
                        answers=answers,
                        parent_id=parent_id,
                    )
                    if isinstance(node, Pipeline)
                    else node.execute(inputs, run, model, execution, **node_resume)
                )
            except Suspend as exc:
                # Not this node's failure, so it is never retried and never follows on_error.
                # The record says the node suspended; the resumed run writes its own, naming
                # this one, so a reader can tell one execution split in two from two.
                if exc.node_state is not None:
                    exc.node_state["record_id"] = execution.record_id
                self._emit_unfinished(
                    run, node, execution, inputs, edges, "suspended", parent_id=parent_id
                )
                # The qualified id, which is what the trajectory, the manifest and
                # per-node metrics use. Two nested pipelines holding a node of the
                # same name would otherwise produce indistinguishable stops.
                raise _Suspending(exc, execution.node_id) from None
            except _Suspending as exc:
                # The run stopped inside a pipeline this node delegated to. The node caught it
                # on the way past and attached what it was holding, so all that is left here is
                # the record saying this execution stopped.
                if exc.node_state is not None:
                    exc.node_state["record_id"] = execution.record_id
                self._emit_unfinished(
                    run, node, execution, inputs, edges, "suspended", parent_id=parent_id
                )
                raise
            except (CassetteMiss, BudgetExceeded) as exc:
                # Neither is this node's failure. One says the run is not the run that was
                # recorded, the other that there is nothing left to spend.
                self._emit_unfinished(
                    run,
                    node,
                    execution,
                    inputs,
                    edges,
                    "error",
                    error=error_object(exc, model_facing=False),
                    parent_id=parent_id,
                )
                raise
            except Exception as exc:
                final = attempt == attempts
                self._emit_unfinished(
                    run,
                    node,
                    execution,
                    inputs,
                    edges,
                    "error",
                    route=(handler,) if final and handler else (),
                    error=error_object(exc, model_facing=False),
                    parent_id=parent_id,
                )
                if not final:
                    _announce(
                        on_progress,
                        "failed",
                        execution.node_id,
                        node,
                        attempt=attempt,
                        error=error_object(exc, model_facing=False),
                    )
                    if policy is not None and policy.backoff_ms:
                        time.sleep(policy.backoff_ms / 1000)
                    continue
                if handler is None:
                    _note_where_it_came_from(exc, node, inputs)
                    raise
                return NodeFailure(
                    node_id=node.node_id,
                    inputs=inputs,
                    error=error_object(exc, model_facing=False),
                    attempts=attempt,
                )
            return _Attempted(
                execution=execution, outputs=outcome.outputs, termination=outcome.termination
            )
        raise AssertionError("unreachable: the loop returns or raises on the last attempt")

    @staticmethod
    def _emit_unfinished(
        run: RunContext,
        node: Node,
        execution: Execution,
        inputs: Any,
        edges: _EdgeState,
        termination: str,
        *,
        route: tuple = (),
        error: Any = None,
        parent_id: str | None = None,
    ) -> None:
        """The record of an execution that produced no output: it suspended or it raised.

        ``parent_id`` is carried on every one, so a node that failed inside a delegated
        pipeline still names the delegation record that contains it.
        """
        _emit_node_record(
            run=run,
            node=node,
            execution=execution,
            inputs=inputs,
            outputs=None,
            termination=termination,
            route=route,
            loop=edges.loop_record(node.node_id),
            error=error,
            parent_id=parent_id,
        )

    def _execution(self, node: Node, run: RunContext, opened: Spend, prefix: str = "") -> Execution:
        cap = getattr(node, "budget", None)
        if cap is not None:
            cap = cap.remaining(_spent_since(opened, run.spend))
        return Execution(
            node_id=f"{prefix}{node.node_id}",
            record_id=run.new_record_id(),
            started_at=utc_now(),
            budget=run.remaining_budget().narrowed_by(cap),
            seed=None if node.node_kind == "deterministic" else run.seed,
        )

    def _chosen(
        self,
        node: Node,
        outputs: Any,
        run: RunContext,
        edges: _EdgeState,
        iteration: int,
    ) -> tuple[tuple[str, ...], bool]:
        """Which successors this execution's output goes to, and whether a cycle ran out.

        A bounded cycle that has reached its count takes ``then`` whatever the route would have
        said, so the bound holds even where a route would go round again.
        """
        # Routable rather than the successors this pipeline holds: a slice keeps a cut edge
        # declared, so a route selects the arm it would have selected in the whole pipeline
        # and the run ends at the boundary rather than being sent down a surviving arm.
        declared = self.graph.routable(node.node_id)
        cycle = self.graph.loop_at(node.node_id)
        if cycle is not None and iteration >= cycle.loop.max_iterations:
            return (cycle.loop.then,), True

        route = getattr(node, "route", None)
        if route is None:
            return declared, False

        ctx = RouteContext(
            run_id=run.run_id,
            node_id=node.node_id,
            workspace=run.workspace,
            seed=None if node.node_kind == "deterministic" else run.seed,
            budget=run.remaining_budget(),
            successors=declared,
            iteration=iteration if self.graph.cycle_around(node.node_id) else None,
            fetch_policy=run.node_fetch_policy(),
        )
        return (
            selected_by(route, outputs, ctx, node_id=node.node_id, declared=declared),
            False,
        )

    def _emit_skip(
        self,
        node: Node,
        run: RunContext,
        edges: _EdgeState,
        prefix: str = "",
        parent_id: str | None = None,
    ) -> None:
        """Record a node that did not run because every edge into it was absent."""
        execution = Execution(
            node_id=f"{prefix}{node.node_id}",
            record_id=run.new_record_id(),
            started_at=utc_now(),
            budget=run.remaining_budget(),
            seed=None,
        )
        _emit_node_record(
            run=run,
            node=node,
            execution=execution,
            inputs=edges.inputs_for(node.node_id, None),
            outputs=None,
            termination="skipped",
            route=(),
            loop=edges.loop_record(node.node_id),
            parent_id=parent_id,
        )

    # -- manifest -------------------------------------------------------------------------

    def _declared_tools(self) -> list[Tool]:
        """Every tool this pipeline can reach, plus any the project registered and gave away.

        A registry given to a nested pipeline is read here too, so a tool declared one level
        down is refused or recorded on the same terms as one declared at the top.
        """
        found: dict[str, Tool] = {}
        for _, node in self.declared_nodes():
            for tool in getattr(node, "tools", []):
                found.setdefault(tool.name, tool)
        for pipeline in self._every_pipeline():
            for tool in pipeline.tools or ():
                found.setdefault(tool.name, tool)
        return list(found.values())

    def _calling_nodes(
        self, model: ModelClient | None
    ) -> list[tuple[str, Node, ModelClient | None]]:
        """Every node that can call a model, with the client its calls would go to.

        The client is the node's own where it declares one and the run's where it does not, so
        a check reasons about what the call is made against rather than what the run was given.
        """
        return [
            (node_id, node, model_for(node, model))
            for node_id, node in self.declared_nodes()
            if node.node_kind in ("llm", "agent")
        ]

    def manifest_nodes(self) -> list[dict[str, Any]]:
        """The ``nodes`` array the manifest writes, with nested pipelines expanded.

        Leaves only, because a pipeline used as a node writes no ``node_execution`` record. Its
        edges into the graph around it are in :meth:`manifest_containers`, and reading the two
        together is what gives the whole graph.
        """
        return _node_entries(self)[0]

    def manifest_containers(self) -> list[dict[str, Any]]:
        """The ``containers`` array the manifest writes, one entry per pipeline used as a node.

        Holds what only a container declares: its budget, its edges in the graph that contains
        it, and its direct children in declaration order::

            outer.manifest_containers()[0]["nodes"]
            # ['research.hunt', 'research.verify']
        """
        return _node_entries(self)[3]

    def manifest_tools(self) -> list[dict[str, Any]]:
        """The ``tools`` array the manifest writes, one entry per distinct tool.

        Every tool any node was given, plus every tool the project registered and gave to no
        node, which is what ``offered`` separates::

            pipeline.manifest_tools()[0]["version"]   # 'sha256:0f3c1a9d4b22'
        """
        return _node_entries(self)[2]

    def manifest_constants(self) -> list[dict[str, Any]]:
        """The ``constants`` array the manifest writes: every module-level number this
        pipeline's own code defines.

        Reached from the node callables: the prompt functions, the `Deterministic` bodies, the
        routes, the finish checks and the tool functions. The modules those live in are the way
        in, and the project's own modules they import are walked from there::

            pipeline.manifest_constants()[0]
            # {'module': 'catalogue.ranking', 'name': 'WEIGHT', 'value': 0.0024}

        A number here changes what the agent does and somebody chose it. Naming it under
        `produces` on a `constant` decision records who (`docs/conformance.md` §2.2).

        Outside :meth:`behaviour_fingerprint`, which covers what the pipeline declares. Editing
        one of these does not move the stamp.
        """
        from ..records.manifest import module_constants

        return module_constants(self._node_callables())

    def _node_callables(self) -> list[Callable[..., Any]]:
        """Every function this pipeline was given, across the leaves and the nested pipelines.

        The way in to the project's own modules. A node holds its work in one of five places
        depending on its kind, and a tool holds its own.
        """
        found: list[Callable[..., Any]] = []
        for _, node, _ in self._declared_with_graph():
            for held in ("fn", "prompt", "route", "finish_check"):
                value = getattr(node, held, None)
                if callable(value):
                    found.append(value)
            for tool in getattr(node, "tools", ()) or ():
                value = getattr(tool, "fn", None)
                if callable(value):
                    found.append(value)
        for pipeline in self._every_pipeline():
            for tool in pipeline.tools or ():
                value = getattr(tool, "fn", None)
                if callable(value):
                    found.append(value)
        return found

    def manifest_prompts(self) -> dict[str, dict[str, Any]]:
        """The ``prompts`` object the manifest writes, keyed by node id.

        A version digest per node that builds a prompt, so a comparison between two pipelines
        can tell an edited prompt from an unchanged one::

            before.manifest_prompts()["hunt"]["version"]   # 'sha256:eb76a45a9605'
        """
        return _node_entries(self)[1]

    def graph_fingerprint(self) -> str:
        """A digest of the shape of this pipeline, ignoring what its functions say.

        Node ids, kinds, edges, loop bounds, error edges, retry policies and output schemas,
        for the leaves and for every pipeline used as a node. A resumed run compares this
        before restoring anything: a changed shape does not make the stored state stale, it
        makes it meaningless, because the state is keyed on node ids. Prompts, versions and
        budgets are outside it and are compared separately.
        """
        nodes, _, _, containers = _node_entries(self)
        return _digest(
            [_structure(entry) for entry in nodes]
            + [_container_structure(entry) for entry in containers]
        )

    def behaviour_fingerprint(self, model: ModelClient | None = None) -> str:
        """A digest of what this pipeline declares about how it behaves.

        The shape, every prompt's version, every `Deterministic` node's function version, the
        sampling parameters, every tool's version and declared cost, the model, `allow_unknown`
        and the budgets, at every depth. A project writes it beside each result it keeps::

            stamp = pipeline.behaviour_fingerprint(model=client)
            store.write(judgement, produced_by=stamp)

        ``model`` is the client :meth:`run` is passed, since a node declaring none calls
        whatever the run was handed. A pipeline whose model-calling nodes all declare their own
        needs no argument, and one with a node that takes the run's refuses without it.

        A stored value without one cannot be told from a current one, and finding the stale
        ones is a query the project writes against this (``docs/shipping.md`` §6).

        **A consultation channel is left out**, since who was watching is a fact about the run.
        `answered_by`, `reaches` and `permission` stay in, so a channel that stops reaching a
        person moves this.

        Wider than :meth:`graph_fingerprint`, which is shape alone: an edited prompt, tool body
        or `Deterministic` body, a changed temperature and a swapped model move this and not
        that. A version the caller declared and did not move does not, which is what declaring
        one is for. `runs()` reads it back from each run's manifest.
        """
        nodes, prompts, tools, containers = _node_entries(self)
        identity = self._run_client_identity(model)
        return _digest(
            _without_derived(
                [
                    nodes,
                    containers,
                    prompts,
                    _without_channels(tools),
                    self.budget.to_record(),
                    identity,
                ]
            )
        )

    def _run_client_identity(self, model: ModelClient | None) -> dict[str, Any] | None:
        """What the run's client contributes to the fingerprint, and ``None`` where nothing.

        A node declaring its own client records it in its own entry, so the run's client is
        only part of what this pipeline produces where some node takes it. Where one does and
        no client is given, this refuses: the alternative is a stamp that reads as covering the
        model and does not, which is worse than no stamp, since a project queries against it.
        """
        takes_the_run_s = [
            node_id for node_id, _, client in self._calling_nodes(None) if client is None
        ]
        if not takes_the_run_s:
            return None
        if model is None:
            raise ConfigurationError(
                f"Node(s) {', '.join(repr(n) for n in takes_the_run_s)} call whatever client "
                f"the run is given, so what this pipeline produces depends on it and a "
                f"fingerprint computed without it would not move when the model changed.\n"
                f"Pass the client the run is passed: "
                f"pipeline.behaviour_fingerprint(model=client).\n"
                f"A pipeline whose model-calling nodes all declare their own client needs no "
                f"argument here."
            )
        return model.identity().to_manifest()


def _pace_clients(
    pipeline: Pipeline, model: ModelClient | None, concurrency: int, *, replaying: bool
) -> None:
    """Tell every client this run may reach how many callers it may have at once.

    A `PacedClient` given no `min_remaining_requests` paces against the number of callers
    sharing it, and a run whose work overlaps is that many callers. The ceiling is what each is
    told rather than what each will see, so a client reached by one node paces early rather
    than late.
    """
    if concurrency <= 1 or replaying:
        return
    seen: list[ModelClient] = []
    for _, node in pipeline.declared_nodes():
        client = getattr(node, "model", None) or model
        if client is not None and not any(client is found for found in seen):
            seen.append(client)
    for client in seen:
        expect = getattr(client, "expect_callers", None)
        if expect is not None:
            expect(concurrency)


def _no_further_work(inputs: Any, ctx: Any) -> Any:
    """The whole of an answering run where the project declared no work for the answer."""
    return inputs


def _refuse_a_swallowed_suspension(run: RunContext) -> None:
    """End a run that reached its end after a ``Suspend`` left one of its tool calls.

    The only way to get here is for something between the raise and the library to have caught
    it. The consultation is already recorded ``pending`` and the run would otherwise finish
    with no suspension on the manifest, no state on disk and nothing saying what happened.
    """
    waiting_for = run.suspension_was_swallowed()
    if waiting_for is None:
        return
    raise CallerFacingError(
        f"This run finished, and a Suspend raised in it never reached the library: it stopped "
        f"to wait for {waiting_for!r} and then carried on. Something between the tool call and "
        f"the pipeline caught it, which is what `except Exception` around ctx.call_tool does. "
        f"The question is recorded `pending`, no state was written, and the run cannot be "
        f"resumed.\n"
        f"Let it out. Suspend is a BaseException so that `except Exception` does not catch it, "
        f"so this run catches BaseException, or Suspend itself, somewhere between the call and "
        f"here. Where a node has to keep going when there is nobody to ask, the channel returns "
        f"Unavailable(reason=...) or Shelved(reason=...) instead of raising, and the node reads "
        f"the reply."
    )


def _mcp_servers_in(pipeline: Pipeline) -> list[Any]:
    """Every MCP server this pipeline and its nested ones declare a tool from."""
    from ..mcp import servers_of

    tools: list[Tool] = []
    for pipe in pipeline._every_pipeline():
        for node in pipe.nodes:
            tools.extend(getattr(node, "tools", []) or [])
        tools.extend(pipe.tools or ())
    return servers_of(tools)


def _read_one_mcp_server(server: Any, cassette: Cassette) -> dict[str, Any]:
    """Fill one server's declared tools, and say what the run read them from.

    A replayed run is served the recording and reaches no server, which is what lets a recorded
    evaluation run with no network. A live run reads the server, and where a recording is being
    updated it also reports the drift between the two. FT-43 reads that.
    """
    from ..mcp import mcp_listing_key

    key = mcp_listing_key(server.name)
    recorded = cassette.lookup(key) if cassette.enabled else None
    if cassette.is_replaying and recorded is None:
        raise CassetteMiss(
            f"{cassette.path} holds no tool listing for MCPServer({server.name!r}), so this "
            f"replay cannot say what the server offered. A listing is recorded on the run "
            f"that reaches the server.\n"
            f"Record the run again against a reachable server, or check that this is the "
            f"cassette the run was recorded into."
        )
    if recorded is not None and not cassette.is_recording:
        server.restore(recorded.response)
        return {"server": server.name, "read": "replayed", "drift": [], "undeclared": []}

    listing = server.resolve()
    if cassette.is_recording:
        cassette.store(
            CassetteEntry(
                key=key,
                kind=MCP_LISTING_KIND,
                node_id="",
                call_index=0,
                recorded_at=utc_now(),
                request={"server": server.name},
                response=listing,
            )
        )
    return {
        "server": server.name,
        "read": "live",
        "drift": server.drift(recorded.response) if recorded is not None else [],
        "undeclared": list(server.undeclared()),
    }


def _read_mcp_servers(pipeline: Pipeline, cassette: Cassette) -> list[dict[str, Any]]:
    """Fill every MCP tool's declaration, and report what each server was read from."""
    return [_read_one_mcp_server(one, cassette) for one in _mcp_servers_in(pipeline)]


def _scoped_memory(envelope: RunEnvelope, scope: str | None) -> Any:
    """The memory a run reaches: the envelope's store under the scope the call named.

    ``None`` where the envelope declares no store or the call named no scope, which is what a
    tool taking a ``Memory`` is refused over before the run starts.
    """
    if scope is None or envelope.memory is None:
        return None
    return envelope.memory.scoped(scope)


def _restored_conversation(envelope: RunEnvelope, manifest: Manifest) -> Any:
    """The conversation a suspended run was a turn of, read back off its own manifest.

    ``thread`` is what a manifest written before format ``0.37`` called ``id``. It is read here
    because the alternative is a run that stopped mid-conversation resuming, completing, and
    leaving its turn open with nothing reporting it.
    """
    recorded = getattr(manifest, "conversation", None) or {}
    conversation_id = recorded.get("id") or recorded.get("thread")
    if not conversation_id or envelope.conversations is None:
        return None
    return envelope.conversations.under(envelope.redaction).thread(str(conversation_id))


def _resolve_cassette(envelope: RunEnvelope, root: Path) -> tuple[RunEnvelope, bool]:
    """The envelope this run executes under, and whether its cassette is the default one.

    The default recording has no file until the run's directory exists, so it is given one
    here. The flag is what the close reads: a default recording is deleted with the payloads it
    duplicates, and a cassette the project named is left where the project put it.
    """
    if not envelope.cassette.awaiting_path:
        return envelope, False
    return envelope.with_cassette(envelope.cassette.for_run(root)), True


def _seed_for(cassette: Cassette) -> int:
    """The seed a run takes when it was given none.

    A cassette being read from decides it, because a model call's seed derives from the run's
    and is part of the key: a generated seed would miss on the first call. A file naming
    several seeds is refused rather than guessed at, and anything else generates one.
    """
    if not cassette.serves_hits:
        return random.SystemRandom().randrange(2**31)
    seeds = cassette.recorded_seeds()
    if len(seeds) == 1:
        return next(iter(seeds))
    if len(seeds) > 1:
        raise ConfigurationError(
            f"{cassette.path} holds calls recorded by {len(seeds)} runs at different seeds, so "
            f"there is no one seed to replay it at. A file like this is what an evaluation "
            f"writes, one rollout per seed.\n"
            f"Pass the seed of the run to replay, as seed=, or replay the whole evaluation "
            f"with EvalSuite.run, which passes each rollout its own."
        )
    return random.SystemRandom().randrange(2**31)


_JUST_RECORDS_IT = Pipeline(
    [Deterministic(_no_further_work, node_id="answered", successors=[], output_schema=None)],
    budget=Budget(max_steps=1, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
)
"""The run an answer gets where the project declared no work for it: one node that does
nothing, so the answer is on the record and the artifacts read like any other run's."""
