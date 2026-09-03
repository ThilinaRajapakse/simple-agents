"""What the run writes down: node records, manifest entries, and reading them back."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from ..records.cassette import CASSETTE_NAME
from ..context import RunContext
from ..envelope import TRAJECTORY_NAME
from ..cost import basis_to_manifest, tool_spend, total_cost
from ..envelope import RunEnvelope, RunPaths
from ..errors import ConfigurationError
from ..records.manifest import Manifest
from ..models import ModelClient
from ..nodes import Deterministic
from ..shapes import accepted_by, digest_of
from ..records.trajectory import strip_payloads
from ..graph import Graph, Join, NodeFailure
from ..nodes import Execution, FanOutResult, Node
from ..tools import Tool, derived_version
from ..records.trajectory import PENDING_SEQUENCE, NodeRecord, read_trajectory, utc_now
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Pipeline


def _emit_node_record(
    *,
    run: RunContext,
    node: Node,
    execution: Execution,
    inputs: Any,
    outputs: Any,
    termination: str | None,
    route: Sequence[str],
    loop: dict[str, Any] | None = None,
    resumed_from: str | None = None,
    error: dict[str, Any] | None = None,
    parent_id: str | None = None,
) -> None:
    # sequence is allocated at emission, not when the node started: it must be monotonic in the
    # order records are written, and a node record is written after everything that happened
    # inside it.
    from .core import Pipeline

    if isinstance(node, Pipeline):
        # A pipeline used as a node writes no record of its own. Its nodes wrote theirs, under
        # ids prefixed by it, and every `node_kind` in a trajectory is one of the three kinds.
        return
    run.emit(
        NodeRecord(
            record_id=execution.record_id,
            run_id=run.run_id,
            parent_id=parent_id,
            sequence=PENDING_SEQUENCE,
            started_at=execution.started_at,
            ended_at=utc_now(),
            node_id=execution.node_id,
            node_kind=node.node_kind,  # type: ignore[arg-type]
            inputs=_recorded(inputs),
            outputs=_recorded(outputs),
            seed=execution.seed,
            budget=execution.budget.to_record(),
            termination=termination,
            route=list(route),
            loop=loop,
            resumed_from=resumed_from,
            error=error,
        )
    )


def _note_where_it_came_from(exc: BaseException, node: Node, inputs: Any) -> None:
    """Say which node raised and what it was reading, on the exception itself.

    The exception propagates unchanged, so a caller catching ``ValueError`` still catches it
    and the note appears under the message in the traceback. A nested pipeline adds none of
    its own, so the chain names one real node per line.
    """
    from .core import Pipeline

    if isinstance(node, Pipeline):
        return
    exc.add_note(
        f"Node {node.node_id!r} raised this while reading the {type(inputs).__name__} it received."
    )


def _recorded(value: Any) -> Any:
    """What a record stores for a value a node received or produced.

    A ``FanOutResult`` holds its failures apart from its values and the record keeps both. A
    ``Join`` is tagged, so a reader tells it from a node that returned a plain mapping.
    """
    if isinstance(value, FanOutResult):
        return value.to_record()
    if isinstance(value, Join):
        return value.to_record()
    if isinstance(value, NodeFailure):
        return value.to_record()
    return value


_STRUCTURAL = ("node_id", "node_kind", "successors", "loop", "on_error", "retry", "schema")


# A container declares no schema of its own, since what it produces is its terminal child's and
# that child is digested already. `nodes` is here because a node moving between two containers
# is a change of shape, and both containers keep the ids they had.
_CONTAINER_STRUCTURAL = ("node_id", "node_kind", "nodes", "successors", "loop", "on_error", "retry")


def _end_user_entry(end_user: Any) -> dict[str, Any] | None:
    """What the manifest records about the channel this run was given, or ``null`` for none.

    A run can replace the registered channel with ``RunEnvelope(end_user=...)``, and what the
    tool entries under ``tools`` declare is then not who this run reached. ``answered_by`` is
    the replacement's own declaration, which the envelope refuses to accept without. A run
    answering more than one person records each by the name its tools reach.
    """
    if end_user is None:
        return None
    if isinstance(end_user, Mapping):
        return {
            "answered_by": None,
            "reaches": {
                str(name): getattr(one, "answered_by", None)
                for name, one in sorted(end_user.items())
            },
        }
    return {"answered_by": getattr(end_user, "answered_by", None)}


def _tool_derived(tool: Tool) -> dict[str, Any]:
    """``derived`` for a tool whose recorded version is not the hash of its own body.

    A tool built by :func:`~simple_agents.tool` with no ``version=`` records the hash as its
    version, so a second copy of it would name one edit twice. A declared version and a
    ``Tool`` constructed by hand with none both leave the body untraced without this.
    """
    held = tool._derived
    return {} if held is None or held == tool.version else {"derived": held}


def _tool_entry(tool: Tool, *, offered: bool) -> dict[str, Any]:
    """What the manifest records for one tool: the declarations, never the code.

    ``offered`` is false for a tool the project registered and no node was given, which is a
    tool that was declared and cannot be called.

    ``retrieval`` is set on a tool that searches a ``DocumentIndex`` and ``null`` on every
    other kind. It carries what decides which documents come back, and leaves out how many
    there are, which the manifest records separately.

    ``answered_by`` is set on a consultation tool and ``null`` on every other kind, so which
    tools reach a person is read from the manifest rather than guessed from a name a project
    chose. ``permission`` carries the builder's agreement where the answerer is the coding
    agent. Both are the channel registered on the pipeline; a run given another one records
    that on each consultation instead.

    ``reader`` is which model read the answers into the option each meant, and the prompt it
    read them with, for a tool registered with ``consult(read=...)``. It is not part of
    ``version``, which a consultation's cassette key covers, so an edited reader prompt misses
    on the reading's own model call rather than on every recorded answer.
    """
    return {
        "name": tool.name,
        "version": tool.version,
        # The hash of the body where the declared version is not already it, so a declaration
        # that stayed put while the tool moved is visible to a reader comparing two runs. Only
        # `version` is digested; `_without_derived` takes this out first.
        **_tool_derived(tool),
        "side_effect_class": tool.side_effect_class.value,
        "declared_cost": tool.declared_cost.to_record() if tool.declared_cost else None,
        # The resources the tool declares, so what two pipelines share is read from their
        # manifests. Direction follows the class: READ_ONLY reads, the rest write.
        "touches": sorted(tool.touches or ()),
        "re_executed": tool.re_executed,
        "offered": offered,
        "answered_by": getattr(tool, "answered_by", None),
        "reaches": getattr(tool, "reaches", None),
        "permission": getattr(tool, "permission", None),
        "reader": _reader_entry(getattr(tool, "reader", None)),
        # The server, its hints, the class they proposed and the class the project
        # declared, so a disagreement between a claim and a declaration is read from the
        # run. `null` on every tool that is not an MCP tool.
        "mcp": getattr(tool, "mcp_entry", None),
        # How the index this tool searches ranks, which store answers it and what embedded
        # the corpus. `null` on every tool that searches no index. How many documents the
        # index holds is on the manifest's own `retrieval` instead, because this entry is
        # part of `behaviour_fingerprint` and a corpus that grew has not changed how the
        # pipeline behaves.
        "retrieval": (
            tool.searches.to_record() if getattr(tool, "searches", None) is not None else None
        ),
    }


def _reader_entry(reader: Any) -> dict[str, Any] | None:
    """What the manifest records about a consultation's reader.

    A reader carrying an ``identity`` describes itself. One written as a plain function is
    recorded as its source version, which is what a reader with no identity can offer.
    """
    if reader is None:
        return None
    identity = getattr(reader, "identity", None)
    if not callable(identity):
        return {"kind": "function", "version": derived_version(reader)}
    try:
        return dict(identity())
    except Exception as exc:
        # The manifest is written at the end of the run, so raising here would lose the record
        # of a run that has already happened over a reader that cannot describe itself.
        return {"kind": "model", "identity_error": f"{type(exc).__name__}: {exc}"}


def _without_channels(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The tool entries with each consultation tool's version taken out.

    A consult tool's version is derived from the project's channel, so two pipelines differing
    only in which channel they ask through carry different versions. Which channel a run asks
    through is a fact about the run: a product asks a person who is on the site and shelves the
    question when the site is unattended, and both are the same pipeline. Leaving the version in stamped a
    result written while somebody was there as produced by a pipeline that would never be seen
    again, so it read as stale against itself forever.

    The version still keys the cassette and is still compared on a resume, where two channels
    are two different things to record and to continue under.
    """
    return [
        {k: v for k, v in tool.items() if k != "version"}
        if tool.get("answered_by") is not None
        else tool
        for tool in tools
    ]


def _without_derived(value: Any) -> Any:
    """The same structure with every ``derived`` hash taken out.

    A declared version is what decides identity, so an edit made under one moves no digest and
    no evaluation directory. The hash recorded beside it says the edit happened, and is removed
    before anything is digested or compared field by field.
    """
    if isinstance(value, dict):
        return {k: _without_derived(v) for k, v in value.items() if k != "derived"}
    if isinstance(value, list):
        return [_without_derived(v) for v in value]
    return value


def _structure(entry: dict[str, Any]) -> dict[str, Any]:
    """The part of a manifest node entry that a resumed run cannot tolerate a change in."""
    return {key: entry.get(key) for key in _STRUCTURAL}


def _container_structure(entry: dict[str, Any]) -> dict[str, Any]:
    """The same, for a pipeline used as a node or reached as a delegate.

    A delegate's `reached_by` contributes only which node reaches it, since that is what its
    children's ids are prefixed by. The description and the call ceiling are configuration
    rather than shape, and are compared as waivable changes the way a prompt is.
    """
    structure = {key: entry.get(key) for key in _CONTAINER_STRUCTURAL}
    reached_by = entry.get("reached_by") or {}
    structure["reached_by"] = (
        {"kind": reached_by.get("kind"), "node_id": reached_by.get("node_id")}
        if reached_by
        else None
    )
    return structure


def _digest(value: Any) -> str:
    import hashlib

    material = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return f"sha256:{hashlib.sha256(material).hexdigest()[:16]}"


def _schema_digest(schema: Any) -> str | None:
    """A digest of what a node declared it produces, or ``None`` where it declared nothing.

    The schema itself is not recorded. What a reader needs is whether it is the same one, and
    what a resumed run needs is to refuse where it is not.
    """
    if schema is None:
        return None
    from ..schema import json_schema_for_model

    return _digest(json_schema_for_model(schema))


def _describe_shape_change(was: dict[str, Any], now: dict[str, Any]) -> str:
    """What differs between the shape a run recorded and the one being resumed against it."""
    gone = sorted(set(was) - set(now))
    added = sorted(set(now) - set(was))
    lines = []
    if gone:
        lines.append(f"  Nodes the run had and this pipeline does not: {', '.join(gone)}.")
    if added:
        lines.append(f"  Nodes this pipeline has and the run did not: {', '.join(added)}.")
    for node_id in sorted(set(was) & set(now)):
        # `.get` on both sides, because a leaf and a pipeline used as a node are described by
        # different fields, so an id that was one and is now the other has keys on one side only.
        keys = sorted(set(was[node_id]) | set(now[node_id]))
        differing = [k for k in keys if was[node_id].get(k) != now[node_id].get(k)]
        if differing:
            lines.append(f"  Node {node_id!r} differs in: {', '.join(differing)}.")
    return "\n".join(lines) or "  The nodes match, so an edge or a bound differs."


def _loop_entry(loop: Any, prefix: str = "") -> dict[str, Any] | None:
    if loop is None:
        return None
    return {"max_iterations": loop.max_iterations, "then": f"{prefix}{loop.then}"}


def _prefixed(node_id: str | None, prefix: str) -> str | None:
    """An edge target written under the id the node it names records under."""
    return None if node_id is None else f"{prefix}{node_id}"


def _container_entry(
    node_id: str, container: Pipeline, graph: Graph | None, delegation: Any = None
) -> dict[str, Any]:
    """What the manifest records for one pipeline used as a node or reached as a delegate.

    Its edges are here rather than on any of its children. An error edge fires from wherever
    inside it the failure happened, so putting it on the child that ends it would say the
    failure was there, and a child may declare a ``retry`` of its own that governs re-executing
    that child rather than the whole pipeline.

    A delegate declares no edges, because it is reached by a model call rather than along one.
    Its entry carries `reached_by` instead, which is what makes the delegation readable as part
    of the graph rather than as a pipeline nothing points at.
    """
    prefix = node_id[: -len(container.node_id)]
    entry: dict[str, Any] = {
        "node_id": node_id,
        "node_kind": container.node_kind,
        # The direct children, in declaration order, under the ids they record under. The
        # first is where a value arriving at this pipeline goes.
        "nodes": [f"{node_id}.{child.node_id}" for child in container.nodes],
        "successors": []
        if graph is None
        else [f"{prefix}{s}" for s in graph.successors[container.node_id]],
        "route": None if graph is None else getattr(container, "route_entry", None),
        "loop": None if graph is None else _loop_entry(container.loop, prefix),
        "on_error": None if graph is None else _prefixed(container.on_error, prefix),
        "retry": None if graph is None else _retry_entry(container.retry),
        "suspend_before": bool(graph is not None and container.suspend_before),
        # Recorded and outside the graph fingerprint, the same as a leaf's `node_budget`. A
        # budget that changed is a run that may stop somewhere else, not a graph whose stored
        # state has stopped meaning anything.
        "budget": container.budget.to_record(),
        "reached_by": None,
    }
    if delegation is not None:
        entry["reached_by"] = {
            "kind": "delegation",
            # The node whose model chooses to call this, which is the prefix minus the
            # delegation's own name. `successors` is empty, so this field is what joins the
            # delegate to the rest of the graph.
            "node_id": node_id[: -(len(container.node_id) + 1)],
            "max_calls": delegation.max_calls,
            # Prompt text and the schema the model fills in. Both change what the model was
            # shown without changing any prompt function, so both are traced here (FT-15).
            "description": _digest(delegation.description),
            "input_schema": _digest(delegation.to_wire()["input_schema"]),
        }
    return entry


def _retry_entry(retry: Any) -> dict[str, Any] | None:
    if retry is None:
        return None
    return {"attempts": retry.attempts, "backoff_ms": retry.backoff_ms}


def _context_builder_entry(builder: Any) -> dict[str, Any] | None:
    """The manifest's record of which context builder a node ran with.

    ``config`` is what the context builder's own ``to_manifest`` reports, and ``{}`` for one
    that has none. The name is always there, which is what identifies the context builder
    that produced an old run.
    """
    if builder is None:
        return None
    to_manifest = getattr(builder, "to_manifest", None)
    return {
        "name": type(builder).__name__,
        "config": to_manifest() if callable(to_manifest) else {},
    }


def _stream_waivers(clients: Iterable[Any]) -> list[str]:
    """Which clients accept a streamed call whose token counts the backend did not report.

    Read through any wrappers, since the waiver sits on the adapter and a ``PacedClient`` or a
    project's own wrapper stands in front of it. A waived run reports `unknown` counts on its
    streamed calls, so the manifest names what allowed that rather than leaving a reader to
    infer it from the records.

    Every client the run can call is read, since nodes may declare their own, and the result
    is deduplicated: one entry per client class that waives, whatever number of nodes reach it.
    """
    found: list[str] = []
    seen: set[int] = set()
    for client in clients:
        while client is not None and id(client) not in seen:
            seen.add(id(client))
            if getattr(client, "stream_without_usage", False):
                name = type(client).__name__
                if name not in found:
                    found.append(name)
            client = getattr(client, "inner", None)
    return found


def _what_a_run_was_given(directory: Path) -> tuple[Any, int | None]:
    """The inputs and seed a run recorded for itself, off its `run_start` record.

    Raises `ConfigurationError` naming what to do instead where the directory holds no
    trajectory, where the record is absent, and where it holds no payload. Those are three
    different situations and each says which it is.

    **The last `run_start` wins.** Two runs written into one directory append into one
    trajectory, and the one to continue is the one that ran last.
    """
    trajectory = directory / TRAJECTORY_NAME
    if not trajectory.exists():
        raise ConfigurationError(
            f"{directory} holds no {TRAJECTORY_NAME}, so it is not a run this can read.\n"
            f"Pass the directory of one run, which holds a manifest.json and a "
            f"{TRAJECTORY_NAME}. `runs('runs/')` lists them, and `run.path` is what to pass."
        )
    starts = [
        record for record in read_trajectory(trajectory) if record.get("record_type") == "run_start"
    ]
    if not starts:
        raise _no_inputs_on_disk(
            directory,
            f"{directory} holds no run_start record, so what that run was given is not on "
            f"disk. Runs written before trajectory format 0.29 carry none.",
        )
    inputs = starts[-1].get("inputs")
    if isinstance(inputs, Mapping) and inputs.get("type") == "not_recorded":
        raise _no_inputs_on_disk(
            directory,
            f"{directory} kept no payloads, so what that run was given is not on disk "
            f"({inputs.get('reason')}).",
        )
    return inputs, starts[-1].get("seed")


def _no_inputs_on_disk(directory: Path, why: str) -> ConfigurationError:
    """The refusal for a run whose inputs cannot be read, naming what to call instead."""
    return ConfigurationError(
        f"{why}\n"
        f"Call Pipeline.run(inputs, ...) with the inputs, passing "
        f"envelope=RunEnvelope(cassette=Cassette.update("
        f"{str(directory / CASSETTE_NAME)!r})) to replay the calls it did record."
    )


def _node_entries(
    pipeline: "Pipeline",
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """One entry per node that can emit a record, with the prompts, tools and containers."""

    prompts: dict[str, dict[str, Any]] = {}
    nodes: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    seen_tools: set[str] = set()

    for node_id, node, graph in pipeline._declared_with_graph():
        # What the ids in this node's own edges are prefixed by, which is the empty string
        # at the top level. Every id an entry names is written the way the node it names
        # records, so a reader never has to know which pipeline an edge was declared in.
        prefix = node_id[: -len(node.node_id)]
        entry: dict[str, Any] = {
            "node_id": node_id,
            "node_kind": node.node_kind,
            # The resolved edges rather than what was declared, so a node that took the
            # default of the next in the list reads the same as one that named it.
            "successors": [f"{prefix}{s}" for s in graph.successors[node.node_id]],
            # A route decides which nodes run at all, so an edit to one moves numbers the
            # same way a prompt edit does and is traced the same way (FT-15).
            "route": getattr(node, "route_entry", None),
            # What a route built by `on_reply` maps, and `null` for any other route. A
            # factory returns a closure, and `source_version` digests the closure's source,
            # which is identical whatever mapping it closed over: two routes sending the
            # run to different nodes hash the same above. The mapping is recorded here so
            # a change to it is traced. Carries `exhaustive`, the waiver of the unmatched
            # and declined branches.
            "consultation_route": getattr(getattr(node, "route", None), "consultation_route", None),
            "loop": _loop_entry(getattr(node, "loop", None), prefix),
            "on_error": _prefixed(getattr(node, "on_error", None), prefix),
            "retry": _retry_entry(getattr(node, "retry", None)),
            # Not the schema, which a manifest has no reader for, but whether it is the
            # same one. A resumed run rebuilds values from it, so a change is refused.
            "schema": _schema_digest(getattr(node, "output_schema", None)),
            # What this node reads its input as, where its function says. A node whose
            # successor stopped agreeing with it produced the same output as before, so
            # the change is on this side and nothing else records it.
            "accepts": digest_of(accepted_by(node)),
            # Which tools this node was given, rather than which the pipeline holds.
            # Removing a tool from one node leaves the pipeline-wide list unchanged when
            # another node still declares it.
            "tools": sorted(t.name for t in getattr(node, "tools", [])),
            # A NotBuilt skeleton node: declared, drawn, and refused if executed. From
            # stage `ship` the checks fail while a run's pipeline still carries one.
            "planned": bool(getattr(node, "planned", False)),
            # The resources this node declares it reads or writes directly, beside the
            # ones its tools declare, so what flows between pipelines is read rather
            # than guessed.
            "touches": sorted(getattr(node, "touches", ()) or ()),
        }
        if not isinstance(node, Deterministic):
            entry["allow_unknown"] = getattr(node, "allow_unknown", None)
            # Only an `AgentNode` can end a unit of work without producing an output, so
            # only an `AgentNode` carries the waiver of the gate on that (FT-35).
            if node.node_kind == "agent":
                entry["allow_unfinished"] = bool(getattr(node, "allow_unfinished", False))
            # Which context builder decided what the model saw. Swapping one changes the
            # request without changing the prompt function's source, so `prompts` alone
            # would leave that change with nothing to trace it to (FT-15).
            entry["context_builder"] = _context_builder_entry(getattr(node, "context", None))
            # Whether this node's calls may be streamed. A streamed call can carry weaker
            # token counts than one made whole, so which nodes asked for it is part of what
            # produced the run's numbers.
            entry["stream"] = bool(getattr(node, "stream", False))
            # The client this node declared, and `null` where it takes the one the run was
            # given. What the node declared rather than what it resolved to, because this
            # is read without a run in scope: by the resume check, by a variant plan, and
            # by the evaluation's config block. `models.configured` holds the run's.
            entry["model"] = (
                node.model.identity().to_manifest()
                if getattr(node, "model", None) is not None
                else None
            )
            # The sampling parameters this node declared. They reach the backend on every
            # call it makes, so a run whose numbers moved because a temperature changed has
            # the change recorded beside the node rather than only inside each request.
            entry["sampling"] = {
                "temperature": getattr(node, "temperature", None),
                "max_output_tokens": getattr(node, "max_output_tokens", None),
                "extra": dict(getattr(node, "extra", {}) or {}),
            }
            # A finish check ends a loop early, so editing one moves terminations and
            # step counts. Versioned the way a route is, for the same reason.
            entry["finish_check"] = getattr(node, "finish_check_entry", None)
            entry["node_budget"] = (
                node.budget.to_record() if getattr(node, "budget", None) else None
            )
            # `null` where a fan-out declared no per-item budget, which is the axis the
            # construction warning names as left open. A reader of the results sees which
            # of the two bounded the work without re-reading the code.
            per_item = getattr(node, "budget_per_item", None)
            entry["node_budget_per_item"] = per_item.to_record() if per_item else None
            entry["fan_out"] = {
                "over": getattr(node, "over", None),
                # Which inputs travel past the fan-out. Adding or removing one changes what
                # the next node is handed without changing any prompt (FT-15).
                "keep": list(getattr(node, "keep", ()) or ()),
                "max_failures": getattr(node, "max_failures", None),
            }
            prompts[node_id] = node.prompt_entry
        else:
            # This node's whole behaviour is its function, and nothing else on the entry
            # moves when the body is edited. Versioned the way a prompt is, and declared
            # the same way, through `Deterministic(version=)` (FT-15).
            entry["fn"] = node.fn_entry
        nodes.append(entry)

        for tool in getattr(node, "tools", []):
            if tool.name in seen_tools:
                continue
            seen_tools.add(tool.name)
            tools.append(_tool_entry(tool, offered=True))

    # A tool the project registered and gave to no node. It cannot be called, and it is
    # what the project declared, which is what the elicitation question `tool_effects`
    # and any reader of the manifest are asking about. Read from every pipeline in the
    # tree, because a registry passed to a nested one was declared by the same project.
    for inner in pipeline._every_pipeline():
        for tool in inner.tools or ():
            if tool.name not in seen_tools:
                seen_tools.add(tool.name)
                tools.append(_tool_entry(tool, offered=False))

    containers = [
        _container_entry(node_id, container, graph, delegation)
        for node_id, container, graph, delegation in pipeline.declared_containers()
    ]

    return nodes, prompts, tools, containers


def _searching_tools(pipeline: "Pipeline") -> list[Any]:
    """Every tool in the tree that searches a ``DocumentIndex``, each named once."""
    found: dict[str, Any] = {}
    for inner in pipeline._every_pipeline():
        for node in inner.nodes:
            for tool in getattr(node, "tools", None) or ():
                if getattr(tool, "searches", None) is not None:
                    found.setdefault(tool.name, tool)
        for tool in inner.tools or ():
            if getattr(tool, "searches", None) is not None:
                found.setdefault(tool.name, tool)
    return list(found.values())


def _new_manifest(
    pipeline: "Pipeline",
    *,
    run_id: str,
    seed: int,
    envelope: RunEnvelope,
    paths: RunPaths,
    model: ModelClient | None,
    concurrency: int = 1,
    conversation: Any = None,
    memory: Any = None,
) -> Manifest:
    from .. import __version__

    nodes, prompts, tools, containers = _node_entries(pipeline)
    return Manifest(
        run_id=run_id,
        started_at=utc_now(),
        seed=seed,
        concurrency=concurrency,
        budget=pipeline.budget.to_record(),
        library_version=__version__,
        role=envelope.role,
        live=envelope.live,
        end_user=_end_user_entry(envelope.end_user),
        evaluation=(envelope.evaluation.to_json() if envelope.evaluation is not None else None),
        conversation=(
            {
                "directory": str(envelope.conversations.directory),
                "id": conversation.conversation_id,
                "turn": conversation.turn_count + 1,
                "carried_in": 0,
            }
            if conversation is not None and envelope.conversations is not None
            else None
        ),
        trajectory_path=str(paths.trajectory),
        workspace_path=str(paths.workspace),
        cost_basis=basis_to_manifest(envelope.cost_basis),
        redaction=envelope.redaction.to_manifest(),
        cassette=envelope.cassette.to_manifest(),
        memory=memory.to_manifest() if memory is not None else None,
        recording=envelope.trajectory.to_record(),
        slice=pipeline.slice_of.to_record() if pipeline.slice_of is not None else None,
        nodes=nodes,
        containers=containers,
        prompts=prompts,
        tools=tools,
        configured_model=model.identity().to_manifest() if model is not None else None,
        constants=pipeline.manifest_constants(),
        graph_fingerprint=pipeline.graph_fingerprint(),
        behaviour_fingerprint=pipeline.behaviour_fingerprint(model),
        stream_waivers=_stream_waivers(client for _, _, client in pipeline._calling_nodes(model)),
    )


def _close_manifest(
    pipeline: "Pipeline",
    *,
    manifest: Manifest,
    paths: RunPaths,
    envelope: RunEnvelope,
    outcome: str,
    stopped_early: str | None,
    charged: float | None = None,
    defaulted_cassette: bool = False,
    run: Any = None,
) -> dict[str, Any]:
    settled = "stopped_early" if stopped_early else outcome
    # A run that errored or suspended keeps its payloads whatever the rate: it is the run
    # worth reading, and a suspended one is not finished, so its resume decides.
    if settled in ("completed", "stopped_early") and not envelope.trajectory.keeps(manifest.run_id):
        strip_payloads(paths.trajectory, reason="sampling")
        manifest.note_payloads_omitted(reason="sampling")
        # The default recording holds what the trajectory just dropped, so it goes with
        # them. A cassette the project named is its own file and is left alone.
        if defaulted_cassette and envelope.cassette.discard():
            manifest.note_cassette_dropped(reason="sampling")

    records = list(read_trajectory(paths.trajectory))
    # Read off the trajectory this run just wrote, rather than accumulated a second time
    # while it ran, so the manifest and the file agree by construction: a sampled run's
    # payloads are already gone by here, and what is counted is what a reader can see.
    # Imported here because the metric lives beside `NodeMetrics`, which reads it back.
    from ..evaluation.per_node import unfinished_work

    manifest.unfinished = unfinished_work(records)
    cost = total_cost(records, envelope.cost_basis)
    manifest.set_tool_spend(tool_spend(records))
    manifest.set_charged_cost(charged)
    manifest.set_cost(cost.to_record())
    # The run's own copy is what counted, so its numbers are this run's and not the
    # declaration's cumulative state, which holds nothing since HostPolicy became a
    # declaration each run binds a copy of.
    manifest.fetch_policy = [
        {
            "declared_by": node_id,
            **(
                run.fetch_policy_record(inner.fetch_policy)
                if run is not None
                else inner.fetch_policy.to_record()
            ),
        }
        for node_id, inner in pipeline._pipelines_by_id()
        if inner.fetch_policy is not None
    ]
    if run is not None and run.memory is not None:
        # Counted again at the end, because the run is what put things in it.
        manifest.memory = run.memory.to_manifest()
    # Counted at the end for the same reason: a run that adds documents to an index leaves a
    # larger corpus than it started with, and the count of what was searched is a fact about
    # the run rather than about what the pipeline declares.
    manifest.retrieval = [
        {"tool": tool.name, **tool.searches.to_manifest()} for tool in _searching_tools(pipeline)
    ]
    manifest.close(
        ended_at=utc_now(),
        outcome="stopped_early" if stopped_early else outcome,
        stopped_early=stopped_early,
    )
    manifest.write(paths.manifest)
    return manifest.to_json()
