"""Evaluation: labeled sets, k rollouts, intervals, per-node metrics, regression detection.

The library ships the machinery and the project holds the content. What counts as a correct
answer is a decision about the task, so no dataset ships and no scoring rule is assumed::

    from simple_agents.evaluation import EvalSuite, Example, ExampleSet

    examples = ExampleSet.from_jsonl("evals/examples.jsonl")
    suite = EvalSuite(pipeline, examples, answer=lambda out: out.answer, matches=exact_match)
    results = suite.run(envelope=env, model=client, split="held_out", k=5, seed=41)
    results.write("evals/results/held-out-v3.json")

``docs/evaluation.md`` is the schema of record for the example-set file and the results file,
and states what a bootstrap interval over k rollouts does and does not claim.
"""

from __future__ import annotations

from .compare import (
    MINIMUM_EXAMPLES_FOR_A_VERDICT,
    Comparison,
    MetricChange,
    against_baseline,
    compare,
)
from .answer_key import (
    AnswerKey,
    AnyOf,
    Contains,
    Criteria,
    Criterion,
    WithinTolerance,
)
from .end_user import DISCLOSURE, EndUser, Fact
from .examples import ContaminationReport, Example, ExampleSet, NearestPair, Overlap
from .stand_in import DEFAULT_INSTRUCTIONS, SimulatedEndUser
from .intervals import (
    Interval,
    bootstrap_ci,
    paired_ratio_ci,
    ratio_ci,
    wilson_ci,
)
from .judgements import (
    Judged,
    JudgementRequest,
    Judgements,
    UnjudgedAnswers,
    judgement_key,
)
from .labels import Label, read_every_label, read_labels, write_labels
from .metrics import METRIC_DEFINITIONS, RATE, Metric, Over, ProjectMetric
from .pairs import Pair, paired_figure, pairs_from_arms, unjudged_pairs
from .ratios import ProjectRatio
from .outcomes import Outcome, RolloutOutcome
from .scoring import Scoring, Verdict
from .per_node import NodeMetrics, node_metrics
from .results import EVAL_FORMAT_VERSION, EvalResults, Group
from ..envelope import evaluation_dir, rollouts_under
from .progress import RolloutProgress, progress_of
from .prompts_sent import prompt_differences
from .runner import (
    DEFAULT_CONCURRENCY,
    DEFAULT_JUDGEMENTS,
    EvalSuite,
    Recording,
)
from .stores import CopyPerRollout, Shared
from .variants import (
    VARIANT_FORMAT_VERSION,
    VARIANT_ROLE,
    Ablations,
    NodePlan,
    VariantComparison,
    VariantPlan,
    ablate,
    compare_variants,
    plan_variant,
)

__all__ = [
    # The example set
    "Example",
    "ExampleSet",
    "AnswerKey",
    "AnyOf",
    "Contains",
    "WithinTolerance",
    "Criterion",
    "Criteria",
    "EndUser",
    "Fact",
    "DISCLOSURE",
    "SimulatedEndUser",
    "DEFAULT_INSTRUCTIONS",
    "NearestPair",
    "Overlap",
    "ContaminationReport",
    # Judgements about what already exists
    "Label",
    "read_every_label",
    "read_labels",
    "write_labels",
    # A condition a model or a person decides
    "Judged",
    "JudgementRequest",
    "Judgements",
    "UnjudgedAnswers",
    "judgement_key",
    # Running it
    "EvalSuite",
    "CopyPerRollout",
    "Shared",
    "evaluation_dir",
    "rollouts_under",
    "Recording",
    "DEFAULT_CONCURRENCY",
    "DEFAULT_JUDGEMENTS",
    # What a rollout produced
    "Outcome",
    "RolloutOutcome",
    "Scoring",
    "Verdict",
    "RolloutProgress",
    "progress_of",
    "prompt_differences",
    # What is reported
    "EvalResults",
    "Group",
    "EVAL_FORMAT_VERSION",
    "Metric",
    "METRIC_DEFINITIONS",
    "ProjectMetric",
    "Pair",
    "ProjectRatio",
    "paired_figure",
    "pairs_from_arms",
    "unjudged_pairs",
    "Over",
    "RATE",
    "NodeMetrics",
    "node_metrics",
    "Interval",
    "bootstrap_ci",
    "paired_ratio_ci",
    "ratio_ci",
    "wilson_ci",
    # Between versions
    "compare",
    "against_baseline",
    "Comparison",
    "MetricChange",
    "MINIMUM_EXAMPLES_FOR_A_VERDICT",
    # Between two versions of the pipeline itself
    "compare_variants",
    "plan_variant",
    "ablate",
    "Ablations",
    "VariantComparison",
    "VariantPlan",
    "NodePlan",
    "VARIANT_FORMAT_VERSION",
    "VARIANT_ROLE",
]
