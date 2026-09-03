"""Simple Agents: a library for building an agent that can be evaluated, debugged, and improved.

The library holds the coding agent's hand so the coding agent can hold the builder's hand.

Start here::

    from pathlib import Path
    from pydantic import BaseModel
    from simple_agents import (Budget, Deterministic, LLMNode, Maybe, MistralClient,
                               NodeContext, Pipeline)

    class Answer(BaseModel):
        answer: Maybe[str]

    def load_docs(inputs: dict, ctx: NodeContext) -> str:
        return Path(inputs["corpus"]).read_text()

    def ask(docs: str, ctx: NodeContext) -> str:
        return f"Answer using only these documents:\\n{docs}"

    pipeline = Pipeline(
        [Deterministic(load_docs), LLMNode(ask, output_schema=Answer)],
        budget=Budget(max_steps=None, max_tokens=100_000,
                      max_cost=None, max_wall_clock_ms=300_000),
    )
    result = pipeline.run(
        {"corpus": "corpus.txt"}, model=MistralClient(model="mistral-small-2603")
    )

    result.output.answer    # what the last node returned
    result.paths.manifest   # runs/<run_id>/manifest.json

A node receives what the node before it returned, which is why ``ask`` takes the text
``load_docs`` returned rather than the pipeline's own inputs.

There are three node kinds. ``Deterministic`` is plain code. ``LLMNode`` is a single model
call at a fixed point in fixed control flow. ``AgentNode`` is the model deciding what happens
next, and is appropriate only where the path cannot be determined in advance.

A pipeline is a directed graph over those three kinds. Declaring ``successors=`` and ``route=``
on a node sends its output somewhere other than the next node in the list, ``loop=Loop(...)``
bounds a cycle, and ``on_error=`` names where a failure goes.

Every run writes a manifest, a trajectory, and a workspace into its own directory. Pass a
``RunEnvelope`` to configure where they go, what cost is derived against, what is redacted,
and whether calls are recorded or replayed.

See ``docs/pipeline.md`` for the node kinds, the output schema and the budget,
``docs/run-envelope.md`` for the manifest and the cassette,
``docs/trajectory-format.md`` for what is recorded on every run,
``docs/model-clients.md`` for pointing a run at a model,
``docs/context.md`` for what the model is sent on each call,
``docs/tools.md`` for the tool contract and the built-in set,
``docs/evaluation.md`` for labeled sets, k rollouts and the intervals over them, and
``docs/failure-taxonomy.md`` for what the conformance checks look for. Those files install
alongside the package, and ``docs_path()`` returns the directory holding them.
"""

from __future__ import annotations

from pathlib import Path

from .adapters import GeminiClient, MistralClient, VLLMClient
from .adapters._http import Retry, retry_after_seconds
from .budget import Budget, BudgetExceeded
from .records.cassette import Cassette, CassetteMiss
from .records.conversation import (
    CONVERSATION_FORMAT_VERSION,
    Conversation,
    ConversationStore,
    Thread,
    ThreadView,
    Turn,
)
from .context import (
    AgentContext,
    FinishAttempt,
    NodeContext,
    RouteContext,
    RunContext,
    TokenEvent,
    ToolCallSummary,
)
from .context_builder import (
    AppendAll,
    ContextBuilder,
    ContextOverflow,
    ContextResult,
    DropOldestTurns,
    Dropped,
    Estimate,
    message_chars,
)
from .cost import (
    ComputeBasis,
    Cost,
    CostBasis,
    DeviceBasis,
    PriceBasis,
    basis_from_manifest,
    cost_of,
    total_cost,
)
from .envelope import RunEnvelope, RunHandle, RunPaths, runs
from .errors import (
    CallerFacingError,
    ConfigurationError,
    LeftTheSlice,
    ModelFacingError,
    RunSuspended,
    SimpleAgentsError,
    StreamUsageMissing,
    SimpleAgentsWarning,
    Suspend,
    Throttled,
)
from .evaluation import (
    Ablations,
    AnswerKey,
    AnyOf,
    Comparison,
    Contains,
    Criteria,
    Criterion,
    ContaminationReport,
    EVAL_FORMAT_VERSION,
    EvalResults,
    Group,
    EvalSuite,
    Example,
    ExampleSet,
    RolloutProgress,
    SimulatedEndUser,
    node_metrics,
    progress_of,
    prompt_differences,
    Interval,
    Label,
    METRIC_DEFINITIONS,
    MINIMUM_EXAMPLES_FOR_A_VERDICT,
    Metric,
    MetricChange,
    NodeMetrics,
    NearestPair,
    NodePlan,
    Outcome,
    Over,
    Overlap,
    ProjectMetric,
    Pair,
    ProjectRatio,
    RATE,
    Recording,
    RolloutOutcome,
    Scoring,
    Verdict,
    WithinTolerance,
    VARIANT_FORMAT_VERSION,
    VARIANT_ROLE,
    VariantComparison,
    VariantPlan,
    ablate,
    bootstrap_ci,
    against_baseline,
    compare,
    compare_variants,
    plan_variant,
    read_every_label,
    read_labels,
    paired_figure,
    paired_ratio_ci,
    pairs_from_arms,
    ratio_ci,
    unjudged_pairs,
    wilson_ci,
    write_labels,
)
from .graph import Join, Loop, NodeFailure, RetryPolicy
from .grounding import (
    contains_normalised,
    normalise_text,
    same_url,
    url_was_read,
    urls_read,
)
from .records.suspension import SuspensionState
from .records.manifest import MANIFEST_FORMAT_VERSION, Manifest
from .embeddings import (
    EmbeddingClient,
    EmbeddingResponse,
    FakeEmbeddingClient,
    FakeRerankClient,
    RerankClient,
    RerankResponse,
    RerankScore,
)
from .models import (
    Backend,
    FakeModelClient,
    ModelClient,
    ModelIdentity,
    ModelRequest,
    ModelResponse,
    Reasoning,
    RateLimit,
    StreamingModelClient,
    TokenUsage,
    ToolCallRequest,
    fake_response,
)
from .pacing import PacedClient
from .progress import ProgressBar
from .redaction import Redaction
from .nodes import (
    AgentNode,
    Delegation,
    Deterministic,
    FanOutResult,
    ItemOutcome,
    LLMNode,
    Node,
    NotBuilt,
)
from .pipeline import (
    Answered,
    AnsweredQuestion,
    NodeEvent,
    Pipeline,
    RunResult,
    SliceOf,
)
from .product import (
    INTERACTION_KINDS,
    Product,
    Surface,
    clear_registered_product,
    product_factory,
    registered_product,
)
from .registry import clear_registered_pipelines, pipeline_factory, registered_pipelines
from .schema import Maybe, Unknown, decode_answer, encode_answer, value_or
from .memory import Memory, MemoryEntry, MemoryStore, ScopedMemory
from .tools import (
    DeclaredCost,
    ModelHandle,
    NodeInput,
    Reading,
    Retrieval,
    SpendMeter,
    SideEffectClass,
    Tool,
    ToolRegistry,
    Workspace,
    tool,
)
from .records.shelf import SHELF_FORMAT_VERSION, ShelvedQuestion
from .records.trajectory import FORMAT_VERSION, Trajectory, TrajectoryWriter, read_trajectory

__version__ = "0.1.2"


def docs_path() -> Path:
    """The directory holding the shipped documentation.

    The library's docstrings cite these files by name, and this is where an installed copy
    of them lives::

        from simple_agents import docs_path

        print((docs_path() / "model-clients.md").read_text())
        sorted(p.name for p in docs_path().glob("*.md"))

    Returns the copy installed beside the package, or the ``docs/`` directory of a source
    checkout when the library is installed from one. Raises ``FileNotFoundError`` when
    neither is present, which means the package was built without its documentation.
    """
    packaged = Path(__file__).parent / "docs"
    if packaged.is_dir():
        return packaged
    checkout = Path(__file__).resolve().parents[2] / "docs"
    if checkout.is_dir():
        return checkout
    raise FileNotFoundError(
        f"No documentation found at {packaged} or {checkout}. The library cites these files "
        f"from its docstrings, so an install without them is incomplete. Reinstall from a "
        f"wheel built by this project, or read them at "
        f"https://github.com/ThilinaRajapakse/simple-agents/tree/main/docs."
    )


from .prompting import Prompt, Section, Value

__all__ = [
    # Prompts
    "Prompt",
    "Value",
    "Section",
    # The shape
    "Pipeline",
    "RunResult",
    "SliceOf",
    "Node",
    "Deterministic",
    "LLMNode",
    "AgentNode",
    "Delegation",
    "NotBuilt",
    "pipeline_factory",
    "Product",
    "Surface",
    "INTERACTION_KINDS",
    "product_factory",
    "registered_product",
    "clear_registered_product",
    "registered_pipelines",
    "clear_registered_pipelines",
    "FanOutResult",
    "ItemOutcome",
    # The graph
    "Loop",
    "RetryPolicy",
    "Join",
    "NodeFailure",
    "NodeEvent",
    "TokenEvent",
    "RouteContext",
    # The run envelope
    "RunEnvelope",
    "RunPaths",
    "RunHandle",
    "runs",
    "Manifest",
    "SHELF_FORMAT_VERSION",
    "ShelvedQuestion",
    "Answered",
    "AnsweredQuestion",
    "MANIFEST_FORMAT_VERSION",
    "Cassette",
    "CassetteMiss",
    "Redaction",
    # Context building
    "ContextBuilder",
    "ContextResult",
    "AppendAll",
    "DropOldestTurns",
    "Dropped",
    "Estimate",
    "message_chars",
    "ContextOverflow",
    # Cost
    "PriceBasis",
    "ComputeBasis",
    "DeviceBasis",
    "CostBasis",
    "Conversation",
    "ConversationStore",
    "Thread",
    "ThreadView",
    "Turn",
    "CONVERSATION_FORMAT_VERSION",
    "Cost",
    "cost_of",
    "total_cost",
    "basis_from_manifest",
    # Budgets
    "Budget",
    "BudgetExceeded",
    # Grounding a claim
    "contains_normalised",
    "normalise_text",
    "url_was_read",
    "urls_read",
    "same_url",
    # Output discipline
    "Unknown",
    "Maybe",
    "value_or",
    "encode_answer",
    "decode_answer",
    # Tools
    "Tool",
    "tool",
    "ToolRegistry",
    "SideEffectClass",
    "DeclaredCost",
    "ModelHandle",
    "NodeInput",
    "Reading",
    "Retrieval",
    "SpendMeter",
    "Workspace",
    # Memory
    "Memory",
    "MemoryStore",
    "ScopedMemory",
    "MemoryEntry",
    # Models
    "ModelClient",
    "StreamingModelClient",
    "ModelRequest",
    "ModelResponse",
    "Reasoning",
    "TokenUsage",
    "ToolCallRequest",
    "RateLimit",
    "Backend",
    "ModelIdentity",
    "FakeModelClient",
    "EmbeddingClient",
    "EmbeddingResponse",
    "RerankClient",
    "RerankResponse",
    "RerankScore",
    "FakeEmbeddingClient",
    "FakeRerankClient",
    "fake_response",
    # Adapters
    "GeminiClient",
    "MistralClient",
    "VLLMClient",
    "Retry",
    "retry_after_seconds",
    "PacedClient",
    # Context
    "RunContext",
    "NodeContext",
    "AgentContext",
    "ToolCallSummary",
    "FinishAttempt",
    # Trajectory
    "FORMAT_VERSION",
    "Trajectory",
    "TrajectoryWriter",
    "read_trajectory",
    # Suspend and resume
    "Suspend",
    "LeftTheSlice",
    "RunSuspended",
    "SuspensionState",
    # Errors
    "SimpleAgentsError",
    "CallerFacingError",
    "ModelFacingError",
    "Throttled",
    "ConfigurationError",
    "SimpleAgentsWarning",
    "StreamUsageMissing",
    # Evaluation: the example set and what it was labelled with
    "Example",
    "ExampleSet",
    "AnswerKey",
    "AnyOf",
    "Contains",
    "WithinTolerance",
    "Criterion",
    "Criteria",
    "RolloutProgress",
    "SimulatedEndUser",
    "ProgressBar",
    "node_metrics",
    "progress_of",
    "prompt_differences",
    "NearestPair",
    "Overlap",
    "ContaminationReport",
    "Label",
    "read_every_label",
    "read_labels",
    "write_labels",
    # Evaluation: running one, and what it produced
    "EvalSuite",
    "Recording",
    "Outcome",
    "RolloutOutcome",
    "Scoring",
    "Verdict",
    "EvalResults",
    "Group",
    "EVAL_FORMAT_VERSION",
    # Evaluation: the numbers
    "Metric",
    "METRIC_DEFINITIONS",
    "ProjectMetric",
    "Pair",
    "ProjectRatio",
    "Over",
    "RATE",
    "NodeMetrics",
    "Interval",
    "bootstrap_ci",
    "paired_figure",
    "paired_ratio_ci",
    "pairs_from_arms",
    "ratio_ci",
    "unjudged_pairs",
    "wilson_ci",
    # Evaluation: comparing two of them
    "compare",
    "against_baseline",
    "Comparison",
    "MetricChange",
    "MINIMUM_EXAMPLES_FOR_A_VERDICT",
    "compare_variants",
    "plan_variant",
    "ablate",
    "Ablations",
    "VariantComparison",
    "VariantPlan",
    "NodePlan",
    "VARIANT_FORMAT_VERSION",
    "VARIANT_ROLE",
    # Documentation
    "docs_path",
    "__version__",
]
