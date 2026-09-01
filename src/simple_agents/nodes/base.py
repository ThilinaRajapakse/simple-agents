"""What every node kind shares: the protocol, outcomes and declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence
from ..budget import Budget
from ..context import RunContext
from ..errors import ConfigurationError
from ..graph import Loop, RetryPolicy
from ..records.manifest import source_version
from ..models import ModelClient
from ..tools import ModelHandle, Tool, ToolRegistry
from ..records.trajectory import utc_now


class NotBuilt:
    """A step declared before its implementation exists.

    Stands in a node's callable slot, so a pipeline's shape can be written and shown before
    the code behind each step is. The one argument is what the step will do, in the builder's
    terms; `simple-agents view` prints it on the step's card::

        Deterministic(NotBuilt("filters the catalogue to eligible titles"), node_id="pool")
        LLMNode(NotBuilt("writes the recap"), output_schema=None, node_id="recap")

    A node built on one declares `node_id=`, since there is no function to take a name from,
    and an `LLMNode` or `AgentNode` may declare `output_schema=None` until the schema is
    settled. Executing the node raises `ConfigurationError`; the other nodes in the pipeline
    still run, so a part-built pipeline is runnable down its built paths. The manifest records
    the node with `planned: true`. `simple-agents check` counts every one at every stage,
    reading them out of `agent.py`, and fails from stage `ship` while one remains (FT-40).
    """

    def __init__(self, does: str) -> None:
        if not isinstance(does, str) or not does.strip():
            raise ConfigurationError(
                "NotBuilt was given no description. The one argument is what the step will "
                "do, in the builder's terms, and the view prints it on the step's card: "
                "NotBuilt('filters the catalogue to eligible titles')."
            )
        self.does = does.strip()

    def __repr__(self) -> str:
        return f"NotBuilt({self.does!r})"


def _not_built_entry(marker: NotBuilt) -> dict[str, Any]:
    """What the manifest records where a version entry is owed and no code exists yet."""
    import hashlib

    digest = hashlib.sha256(f"not_built:{marker.does}".encode("utf-8")).hexdigest()[:12]
    return {
        "version": f"sha256:{digest}",
        "source": "not_built",
        "does": marker.does,
    }


def _not_built_message(node: Any) -> str:
    """The refusal an execution of a planned node raises, naming what is missing."""
    marker = node.fn if isinstance(getattr(node, "fn", None), NotBuilt) else node.prompt
    return (
        f"Node {node.node_id!r} is declared NotBuilt: {marker.does!r}. It has no "
        f"implementation to run. The rest of the pipeline runs; this step refuses until the "
        f"code exists. Implement it and replace NotBuilt({marker.does!r}) with the function."
    )


def _declare_planned(node: Any, callable_slot: Any, node_id: str | None, kind: str) -> bool:
    """Whether the node is a `NotBuilt` skeleton, refusing one with no id to draw it by."""
    if not isinstance(callable_slot, NotBuilt):
        return False
    if node_id is None:
        raise ConfigurationError(
            f"{kind}(NotBuilt(...)) was constructed without node_id=. A planned step has no "
            f"function to take a name from, and the graph, the view and the manifest all key "
            f"on the id. Pass node_id=, such as "
            f"{kind}(NotBuilt({callable_slot.does!r}), node_id='pool')."
        )
    return True


@dataclass(frozen=True, slots=True)
class Execution:
    """What the pipeline settles about one execution of a node before the node runs.

    Built by the pipeline, which owns the graph and therefore knows the id a node runs under,
    the budget in force and the record its children hang from. A node that raises leaves
    nothing behind, so the pipeline holds these rather than the node.
    """

    node_id: str
    record_id: str
    started_at: str
    budget: Budget
    seed: int | None

    @classmethod
    def for_node(cls, node: Any, run: RunContext) -> Execution:
        """The execution a node gets when it is run outside a pipeline."""
        return cls(
            node_id=node.node_id,
            record_id=run.new_record_id(),
            started_at=utc_now(),
            budget=run.remaining_budget().narrowed_by(getattr(node, "budget", None)),
            seed=None if node.node_kind == "deterministic" else run.seed,
        )


@dataclass(frozen=True, slots=True)
class NodeOutcome:
    """What one execution of a node produced.

    ``termination`` says why the node stopped where the node itself knows: a ``finish`` call, a
    rejected one, or a budget axis. It is ``None`` for a node that ran to the end of its own
    work, and the pipeline fills in the reasons only it knows.
    """

    outputs: Any
    termination: str | None = None


class Node(Protocol):
    """What a pipeline can hold.

    The three kinds are fixed. This states what the pipeline calls, so the kinds and the
    scheduler can be typed against each other.
    """

    node_id: str
    node_kind: str

    def execute(
        self,
        inputs: Any,
        run: RunContext,
        model: ModelClient | None,
        execution: Execution | None = None,
    ) -> NodeOutcome: ...


def model_for(node: Any, default: ModelClient | None) -> ModelClient | None:
    """Which client a node's calls are made against: its own, or the run's::

        client = model_for(node, run_client)

    ``default`` is what ``Pipeline.run(model=...)`` was given. A node declaring none takes it,
    and a ``Deterministic`` node declares none and makes no call. Returns ``None`` where
    neither is set, which the caller refuses.

    Read wherever the answer is needed before the run as well as during it, so the client a
    streaming check reasons about is the one the call is made against.
    """
    return getattr(node, "model", None) or default


def _declare_edges(
    node: Any,
    *,
    successors: Sequence[str] | None,
    route: Callable[[Any, Any], Any] | None,
    loop: Loop | None,
    on_error: str | None,
    retry: RetryPolicy | None,
    suspend_before: bool = False,
) -> None:
    """Attach the graph arguments every node kind takes, refusing the shapes that misread.

    The pipeline checks the graph as a whole. What is checked here is one node's own
    arguments, which is what can be checked without knowing the other nodes.
    """
    if isinstance(successors, str):
        raise ConfigurationError(
            f"Node {node.node_id!r} was given successors={successors!r}, a string. `successors` "
            f"holds node ids, so a bare string is read one character at a time. Pass a list, "
            f"even for one: successors=['{successors}']."
        )
    if route is not None and not callable(route):
        raise ConfigurationError(
            f"Node {node.node_id!r} was given route={route!r}, which is not callable. A route "
            f"is a function over the node's validated output, returning the successor id it "
            f"goes to: route=lambda output, ctx: 'verify' if output.answer else 'report'."
        )
    if loop is not None and not isinstance(loop, Loop):
        raise ConfigurationError(
            f"Node {node.node_id!r} was given loop={loop!r}. A cycle's bound is a Loop: "
            f"loop=Loop(max_iterations=3, then='publish'), where `then` names the successor "
            f"taken once the count is reached."
        )
    if retry is not None and not isinstance(retry, RetryPolicy):
        raise ConfigurationError(
            f"Node {node.node_id!r} was given retry={retry!r}. A node's retry is a "
            f"RetryPolicy: retry=RetryPolicy(attempts=3). `attempts` counts every execution, "
            f"so attempts=1 is no retry."
        )
    node.successors = list(successors) if successors is not None else None
    node.route = route
    # Versioned here rather than when the manifest is read: a route built by a factory over
    # state that is later mutated would otherwise record a different version on each read,
    # and a stored result is joined on the fingerprint those versions build (FT-15).
    node.route_entry = source_version(route) if route is not None else None
    node.loop = loop
    node.on_error = on_error
    node.retry = retry
    node.suspend_before = bool(suspend_before)


def _declared_tools(node: Any, tools: Sequence[Tool] | ToolRegistry) -> list[Tool]:
    """The tools a node calls itself, refusing the ones it cannot.

    ``ctx.call_tool`` is the only route to one, and the node decides that the call happens, so
    there is no model to correct a bad one. A tool taking a ``ModelHandle`` would make a model
    call this node's own accounting does not expect, and a duplicate name makes ``call_tool``
    ambiguous.
    """
    declared = list(tools)
    kind = type(node).__name__
    for one in declared:
        if any(issubclass(h, ModelHandle) for h in one.handles.values()):
            raise ConfigurationError(
                f"{kind} node {node.node_id!r} was given tool {one.name!r}, which takes a "
                f"ModelHandle. A tool this node calls makes no model call of its own, and a "
                f"run's per-node accounting reads that: FT-07 treats a `deterministic` "
                f"record as one that did not sample.\n"
                f"Put the step in an LLMNode or an AgentNode, or split the tool so the part "
                f"needing a model is a node and the rest takes no handle.\n"
                f"The one model call this node kind can carry is a consultation's reader, "
                f"registered with consult(read=ModelReader(model=cheap)), which the library "
                f"makes and records on the consultation (`docs/tools.md` §4.6.1)."
            )
    names = [one.name for one in declared]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ConfigurationError(
            f"{kind} node {node.node_id!r} has more than one tool named "
            f"{', '.join(sorted(duplicates))}. `ctx.call_tool` selects by name, so a "
            f"duplicate makes the call ambiguous. Give each tool a distinct name."
        )
    return declared
