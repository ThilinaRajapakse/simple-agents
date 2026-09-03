"""Two versions of a pipeline, run against the same backend, compared on the same examples.

An ablation is one use of this: replace an ``AgentNode`` with an ``LLMNode`` and see what the
metric does. Adding a tool, removing one, changing a prompt, swapping a model and rewiring the
graph are the same operation with a different variant.

The unit is a pair of pipelines. The builder writes both::

    comparison = compare_variants(
        suite,
        {"hunt without its tools": leaner_pipeline},
        envelope=envelope,
        model=client,
        split="held_out",
        k=5,
        max_live_calls=400,
    )
    comparison.comparisons["hunt without its tools"].moved   # ['recall']

Every arm runs in one session against one backend. The same pipeline re-run on another day
moves its own metrics, so an arm compared against an older results file reports the difference
between two days rather than between two pipelines.
"""

from __future__ import annotations

import copy
import json
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from ..records.cassette import Cassette
from ..envelope import RunEnvelope
from ..errors import CallerFacingError, ConfigurationError
from ..graph import Loop
from ..models import ModelClient
from ..pipeline import Pipeline
from .compare import Comparison, compare
from .declared import config_differences
from .results import EvalResults
from .stores import Isolation, refuse_a_collision, refuse_an_unisolated_store
from .runner import (
    DEFAULT_CONCURRENCY,
    DEFAULT_CONFIDENCE,
    DEFAULT_RESAMPLES,
    EvalSuite,
    UsedRunDirectory,
)

__all__ = [
    "VARIANT_FORMAT_VERSION",
    "VARIANT_ROLE",
    "Ablations",
    "NodePlan",
    "VariantPlan",
    "VariantComparison",
    "plan_variant",
    "compare_variants",
    "ablate",
]

# JSON, in the `variant_format_version` field of a written comparison.
VARIANT_FORMAT_VERSION = "0.3"

# The role every arm but the baseline runs under, so `runs("runs/", role="variant")` reads a
# sweep back and no conformance check reads an arm as a run of the agent.
VARIANT_ROLE = "variant"

# Node kinds that issue model calls. A `deterministic` node makes none, so it neither replays
# nor costs anything, whatever else changed around it.
_CALLING_KINDS = frozenset({"agent", "llm"})


@dataclass(frozen=True)
class NodePlan:
    """What one node will do when its arm runs, decided before any call is made.

    ``calls`` is ``replayed`` when every call this node makes is already on file, ``live`` when
    they have to be made, and ``none`` for a node that makes no model calls::

        [n.node_id for n in plan.nodes if n.calls == "live"]

    A node is ``replayed`` only when its own configuration is unchanged and every node that can
    reach it is unchanged too. Its requests are then byte-identical and its derived seeds are
    the same, so the recording answers them. Anything else is ``live``, which over-counts: a
    changed node upstream can still produce the value it produced before.
    """

    node_id: str
    status: str
    calls: str
    estimated_calls: int
    estimated_cost: float | None

    def to_record(self) -> dict[str, Any]:
        """What a written comparison stores for this node."""
        return {
            "node_id": self.node_id,
            "status": self.status,
            "calls": self.calls,
            "estimated_calls": self.estimated_calls,
            "estimated_cost": self.estimated_cost,
        }


@dataclass(frozen=True)
class VariantPlan:
    """What one variant differs in, and what running it will cost.

    Reachable without running anything, so a builder can look before spending::

        plan = plan_variant(baseline, variant, name="no tools")
        plan.differs_at        # ('hunt',)
        plan.changed           # {'nodes.hunt.tools': [['search'], []]}
        plan.live_calls        # 45

    ``live_calls`` is an upper bound and ``replayed_calls`` a lower one.
    """

    name: str
    differs_at: tuple[str, ...]
    changed: dict[str, list[Any]]
    nodes: tuple[NodePlan, ...]

    @property
    def live_calls(self) -> int:
        """Model calls that have to be made against the backend, at most."""
        return sum(n.estimated_calls for n in self.nodes if n.calls == "live")

    @property
    def replayed_calls(self) -> int:
        """Model calls the recording answers, at least."""
        return sum(n.estimated_calls for n in self.nodes if n.calls == "replayed")

    @property
    def estimated_cost(self) -> float | None:
        """What the live calls cost, or ``None`` where no price basis was configured."""
        costs = [n.estimated_cost for n in self.nodes if n.calls == "live"]
        known = [c for c in costs if c is not None]
        return sum(known) if known else None

    def to_record(self) -> dict[str, Any]:
        """What a written comparison stores for this plan."""
        return {
            "name": self.name,
            "differs_at": list(self.differs_at),
            "changed": self.changed,
            "live_calls": self.live_calls,
            "replayed_calls": self.replayed_calls,
            "estimated_cost": self.estimated_cost,
            "nodes": [n.to_record() for n in self.nodes],
        }


@dataclass
class VariantComparison:
    """The baseline, every variant, and what moved between each variant and the baseline.

    ::

        comparison.plans["no tools"].live_calls
        comparison.comparisons["no tools"].moved
        comparison.comparisons["no tools"].metrics["accuracy"].delta
        comparison.write("evals/variants/no-tools.json")

    Every arm ran against the same backend in one session, so a difference here is the variant
    rather than the provider.
    """

    baseline: EvalResults
    variants: dict[str, EvalResults] = field(default_factory=dict)
    comparisons: dict[str, Comparison] = field(default_factory=dict)
    plans: dict[str, VariantPlan] = field(default_factory=dict)

    @property
    def moved(self) -> dict[str, list[str]]:
        """The metrics that moved, per variant."""
        return {name: c.moved for name, c in self.comparisons.items()}

    def to_record(self) -> dict[str, Any]:
        """What a written comparison holds."""
        return {
            "variant_format_version": VARIANT_FORMAT_VERSION,
            "baseline": {
                "eval_id": self.baseline.eval_id,
                "graph_fingerprint": self.baseline.config.get("graph_fingerprint"),
                "behaviour_fingerprint": self.baseline.config.get("behaviour_fingerprint"),
            },
            "variants": {
                name: {
                    "plan": self.plans[name].to_record(),
                    "eval_id": results.eval_id,
                    "graph_fingerprint": results.config.get("graph_fingerprint"),
                    "behaviour_fingerprint": results.config.get("behaviour_fingerprint"),
                    "comparison": self.comparisons[name].to_record(),
                    "cost": {
                        "baseline": _cost_of(self.baseline),
                        "variant": _cost_of(results),
                    },
                    "tool_spend": {
                        "baseline": _tool_spend_of(self.baseline),
                        "variant": _tool_spend_of(results),
                    },
                    "tokens": {
                        "baseline": self.baseline.totals.get("tokens"),
                        "variant": results.totals.get("tokens"),
                    },
                }
                for name, results in self.variants.items()
            },
        }

    def write(self, path: str | Path) -> Path:
        """Write the comparison as JSON and return where it landed."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_record(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target


def plan_variant(
    baseline: Pipeline,
    variant: Pipeline,
    *,
    name: str,
    measured: EvalResults | None = None,
) -> VariantPlan:
    """What differs between two pipelines, and which of the variant's calls the recording answers.

    Makes no calls and needs no run::

        plan = plan_variant(pipeline, leaner, name="hunt without its tools")
        plan.live_calls, plan.estimated_cost

    ``measured`` is a baseline evaluation whose per-node call counts and costs sharpen the
    estimate. Without one the estimate comes from each node's declared budget, which counts an
    ``AgentNode`` at its ``max_steps`` and so reads high.

    Raises :class:`~simple_agents.errors.ConfigurationError` where the two cannot be compared:
    no node id in common, nothing different at all, or a rewiring that feeds a node a value of
    a different declared shape.
    """
    was = _shape_of(baseline.manifest_nodes(), baseline.manifest_containers())
    now = _shape_of(variant.manifest_nodes(), variant.manifest_containers())
    before, after = was.entries, now.entries
    prompts_before, prompts_after = baseline.manifest_prompts(), variant.manifest_prompts()

    _refuse_incomparable(was, now, prompts=(prompts_before, prompts_after), name=name)

    added = set(after) - set(before)
    removed = set(before) - set(after)
    edited = {
        node_id
        for node_id in set(before) & set(after)
        if before[node_id] != after[node_id] or was.carries[node_id] != now.carries[node_id]
    }

    tainted = _taint(
        now,
        seeds=added
        | {
            node_id
            for node_id in set(before) & set(after)
            if _requests_differ(before[node_id], after[node_id])
            or prompts_before.get(node_id) != prompts_after.get(node_id)
            or was.predecessors(node_id) != now.predecessors(node_id)
        },
    )

    nodes = tuple(
        NodePlan(
            node_id=node_id,
            status=(
                "added" if node_id in added else "changed" if node_id in edited else "unchanged"
            ),
            calls=(
                "none"
                if entry["node_kind"] not in _CALLING_KINDS
                else "live"
                if node_id in tainted
                else "replayed"
            ),
            estimated_calls=_estimated_calls(node_id, entry, measured),
            estimated_cost=_estimated_cost(node_id, measured),
        )
        for node_id, entry in after.items()
    )
    nodes += tuple(
        NodePlan(
            node_id=node_id, status="removed", calls="none", estimated_calls=0, estimated_cost=None
        )
        for node_id in sorted(removed)
    )

    return VariantPlan(
        name=name,
        differs_at=tuple(sorted(added | removed | edited)),
        # The containers as well as the leaves, so a sub-pipeline whose budget or edges moved
        # has somewhere for a builder to read the cause of a moved metric (FT-15).
        changed=config_differences(
            {"nodes": baseline.manifest_nodes(), "containers": baseline.manifest_containers()},
            {"nodes": variant.manifest_nodes(), "containers": variant.manifest_containers()},
        ),
        nodes=nodes,
    )


def compare_variants(
    baseline: EvalSuite,
    variants: Mapping[str, Pipeline],
    *,
    envelope: RunEnvelope,
    model: ModelClient | None = None,
    split: str,
    k: int,
    seed: int | None = None,
    max_live_calls: int | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    run_concurrency: int = 1,
    resamples: int = DEFAULT_RESAMPLES,
    confidence: float = DEFAULT_CONFIDENCE,
    end_user: Any = None,
    judge: Any = None,
    max_spend: float | None = None,
    stores: Mapping[str, Isolation] | None = None,
) -> VariantComparison:
    """Run the baseline and every variant in one session, and report what moved.

    ::

        comparison = compare_variants(
            suite,
            {"hunt as one call": flattened, "verify removed": shorter},
            envelope=envelope,
            model=client,
            split="held_out",
            k=5,
            max_live_calls=600,
        )

    The baseline records a cassette. Each variant then serves from it every call whose request
    the change cannot have altered, and calls the backend for the rest, so the two arms share
    the calls they have in common rather than differing by whatever the backend did that day.
    A variant's results file records the split under ``nodes[].replayed_calls``, with
    ``config.cassette.mode`` of ``update``.

    ``max_live_calls`` is checked against the plan before the first call is made and raises
    rather than spending. It counts across every arm, and unset runs whatever the sweep costs.

    ``judge`` answers each arm's judgements, and is required where a condition is ``Judged()``.

    ``end_user`` answers the consultations in every arm (``docs/evaluation.md`` §5.4).

    ``max_spend`` bounds each arm, as it does :meth:`EvalSuite.run`.

    Raises :class:`~simple_agents.errors.ConfigurationError` before anything runs when a variant
    cannot be compared with the baseline, or when the plan exceeds ``max_live_calls``.
    """
    _refuse_before_planning(variants, envelope)
    # Every arm, before the baseline is paid for: an arm whose steps declare a store the
    # baseline's do not would otherwise raise after the baseline had run.
    stores = dict(stores or {})
    refuse_a_collision(stores)
    for arm, pipeline in [("baseline", baseline.pipeline), *variants.items()]:
        refuse_an_unisolated_store(pipeline, stores, f"compare the {arm!r} arm of")

    plans = {
        name: plan_variant(baseline.pipeline, pipeline, name=name)
        for name, pipeline in variants.items()
    }
    baseline_calls = _declared_calls(baseline.pipeline) * len(baseline.examples.in_split(split)) * k
    _refuse_over_ceiling(
        plans,
        baseline_calls,
        examples=len(baseline.examples.in_split(split)),
        k=k,
        max_live_calls=max_live_calls,
    )

    cassettes = Path(envelope.run_dir) / "variant_cassettes"
    cassettes.mkdir(parents=True, exist_ok=True)
    baseline_cassette = cassettes / "baseline.jsonl"
    baseline_cassette.unlink(missing_ok=True)

    with _naming_the_arm("baseline", sweep=list(variants)):
        baseline_results = baseline.run(
            envelope=envelope.with_cassette(Cassette.record(baseline_cassette)),
            model=model,
            split=split,
            k=k,
            seed=seed,
            concurrency=concurrency,
            run_concurrency=run_concurrency,
            resamples=resamples,
            confidence=confidence,
            end_user=end_user,
            judge=judge,
            max_spend=max_spend,
            stores=stores,
        )

    comparison = VariantComparison(baseline=baseline_results)
    for name, pipeline in variants.items():
        # Re-planned against what the baseline actually did, so the recorded estimate is the
        # measured one rather than the declared ceiling the budget gives.
        plan = plan_variant(baseline.pipeline, pipeline, name=name, measured=baseline_results)
        arm_cassette = cassettes / f"{_slug(name)}.jsonl"
        shutil.copyfile(baseline_cassette, arm_cassette)
        with _naming_the_arm(name, sweep=list(variants), spent=len(comparison.variants) + 1):
            results = _with_pipeline(baseline, pipeline).run(
                # An arm is a pipeline this project does not have, so its rollouts declare
                # themselves and no check reads one as a run of the agent
                # (`docs/run-envelope.md` §2.1). The baseline keeps `agent`, because it is the
                # pipeline the project has, run over the example set.
                envelope=envelope.with_cassette(Cassette.update(arm_cassette)).with_role(
                    VARIANT_ROLE
                ),
                model=model,
                split=split,
                k=k,
                seed=seed if seed is not None else baseline_results.config["seed"],
                concurrency=concurrency,
                run_concurrency=run_concurrency,
                resamples=resamples,
                confidence=confidence,
                end_user=end_user,
                judge=judge,
                max_spend=max_spend,
                stores=stores,
                allow_mixed_cassette=True,
            )
        comparison.plans[name] = plan
        comparison.variants[name] = results
        comparison.comparisons[name] = _without_own_noise(
            compare(baseline_results, results, confidence=confidence, resamples=resamples)
        )
    return comparison


@contextmanager
def _naming_the_arm(name: str, *, sweep: Sequence[str], spent: int = 0) -> Iterator[None]:
    """Re-raise a used-directory refusal from inside a sweep, naming which arm hit it.

    A sweep runs one evaluation per arm, each into a directory named for what that arm
    measures. The refusal the runner raises names the directory, and a directory name is a
    digest, so on its own it does not say which arm of which sweep stopped or how many arms
    have already been paid for.
    """
    try:
        yield
    except UsedRunDirectory as exc:
        arms = ", ".join(repr(arm) for arm in sweep)
        already = (
            f"{spent} arm(s) of this sweep have already run and been paid for.\n" if spent else ""
        )
        raise ConfigurationError(
            f"compare_variants stopped on the {name!r} arm: it resolves to "
            f"{str(exc.run_dir)!r}, which already holds an evaluation's rollouts. A rollout "
            f"appends to the trajectory it finds, so running into that directory again would "
            f"produce trajectories holding two runs.\n"
            f"{already}"
            f"The sweep is the baseline against {arms}. A directory is named for what decides "
            f"what an arm measures, so two arms land in one only where they measure the same "
            f"thing, and an arm lands on an earlier sweep's directory when that sweep was run "
            f"into the same run_dir.\n"
            f"Pass an envelope with a run_dir of its own for this sweep, delete the directory "
            f"above to measure again, or drop the arm if it is the baseline under another "
            f"name."
        ) from exc


def _without_own_noise(comparison: Comparison) -> Comparison:
    """Drop the two differences this operation creates itself.

    Each arm records to its own cassette file, so `cassette.mode` and `cassette.path` differ in
    every variant comparison and say nothing about the pipeline. `changed` is where a builder
    looks for the cause of a moved metric, and two entries that are always there are two
    entries they have to learn to ignore.
    """
    return replace(
        comparison,
        changed={
            path: value
            for path, value in comparison.changed.items()
            if not path.startswith("cassette.")
        },
    )


class Ablations(Mapping[str, Pipeline]):
    """The standard downgrades of one pipeline, and the ones that were not generated.

    A mapping from the name of a variant to the pipeline that is it, so it goes straight to
    :func:`compare_variants`::

        arms = ablate(suite.pipeline)
        comparison = compare_variants(suite, arms, envelope=env, model=client,
                                      split="held_out", k=5)

    ``skipped`` names the variants that were not generated, each with why, so a node with no
    arm is distinguishable from a node whose arm measured nothing::

        arms.skipped
        # {'hunt removed': "no edge reaches it, so it is where the run starts and its input
        #                   is what run() was passed rather than another node's output."}

    A skipped variant is one to write by hand and pass to :func:`compare_variants`, which
    covers anything this does not generate.
    """

    __slots__ = ("_variants", "_skipped")

    def __init__(self, variants: Mapping[str, Pipeline], skipped: Mapping[str, str]) -> None:
        self._variants = dict(variants)
        self._skipped = dict(skipped)

    def __getitem__(self, name: str) -> Pipeline:
        return self._variants[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._variants)

    def __len__(self) -> int:
        return len(self._variants)

    def __repr__(self) -> str:
        return f"Ablations({sorted(self._variants)!r}, skipped={sorted(self._skipped)!r})"

    @property
    def skipped(self) -> dict[str, str]:
        """The variants that were not generated, each holding why."""
        return dict(self._skipped)


def ablate(pipeline: Pipeline) -> Ablations:
    """The standard downgrades of one pipeline, one variant per node worth trying.

    ::

        comparison = compare_variants(suite, ablate(suite.pipeline), envelope=env,
                                      model=client, split="held_out", k=5)

    Two kinds are generated. Every ``AgentNode`` gets a variant where it is an ``LLMNode`` with
    the same prompt, schema and sampling and no tools, which asks whether the loop pays. Every
    node whose declared output schema matches its predecessor's, and the node that ends the
    run, gets a variant with it removed, which asks whether the node pays at all. A node inside
    a nested pipeline keeps its id and its container keeps its own budget, so an arm pairs with
    the baseline node for node.

    Removing a node re-points every edge that named it at what it led to. Where that leaves a
    graph the pipeline refuses, such as a predecessor holding two successors and no route, the
    variant is not generated and :attr:`Ablations.skipped` says so::

        arms = ablate(pipeline)
        sorted(arms)          # ['hunt as one call', 'verify removed', 'report removed']
        arms.skipped          # {'hunt removed': '...'}
    """
    from ..nodes import AgentNode, LLMNode

    found: dict[str, Pipeline] = {}
    skipped: dict[str, str] = {}
    shape = _shape_of(pipeline.manifest_nodes(), pipeline.manifest_containers())

    for node_id, node in pipeline.declared_nodes():
        if isinstance(node, AgentNode):
            flattened = LLMNode(
                node.prompt,
                output_schema=node.output_schema,
                node_id=node.node_id,
                prompt_version=node.prompt_version,
                allow_unknown=node.allow_unknown,
                temperature=node.temperature,
                max_output_tokens=node.max_output_tokens,
                extra=dict(node.extra),
                stream=node.stream,
                # Without this the arm runs on whatever the run was given, so it would measure
                # the loop coming out and the model changing at the same time.
                model=node.model,
                context=node.context,
                successors=_declared_successors(node),
                route=node.route,
                loop=node.loop,
                on_error=node.on_error,
                retry=node.retry,
            )
            _collect(
                found,
                skipped,
                f"{node_id} as one call",
                lambda node_id=node_id, flattened=flattened: _replacing(
                    pipeline, node_id, flattened
                ),
            )

        name = f"{node_id} removed"
        reason = _removable(node_id, shape)
        if reason is not None:
            skipped[name] = reason
            continue
        _collect(found, skipped, name, lambda node_id=node_id: _without(pipeline, node_id))
    return Ablations(found, skipped)


def _collect(
    found: dict[str, Pipeline],
    skipped: dict[str, str],
    name: str,
    build: Callable[[], Pipeline],
) -> None:
    """Generate one variant, or record why the graph refused it.

    Only a `ConfigurationError` is caught, which is what every graph check raises. A variant
    this module built wrongly raises `CallerFacingError` and is not swallowed.
    """
    try:
        found[name] = build()
    except ConfigurationError as refusal:
        skipped[name] = str(refusal)


# -- refusals ------------------------------------------------------------------------------


def _refuse_incomparable(
    was: _Shape,
    now: _Shape,
    *,
    prompts: tuple[Mapping[str, Any], Mapping[str, Any]],
    name: str,
) -> None:
    before, after = was.entries, now.entries
    shared = set(before) & set(after)
    if not shared:
        raise ConfigurationError(
            f"Variant {name!r} shares no node id with the baseline: the baseline declares "
            f"{', '.join(repr(n) for n in sorted(before))} and the variant declares "
            f"{', '.join(repr(n) for n in sorted(after))}. Per-node figures are keyed on "
            f"node_id, so nothing pairs and a difference could not be attributed to any node.\n"
            f"Keep the node ids of the nodes that did not change."
        )
    # The prompts are compared here as well as the entries. A prompt is versioned outside the
    # node entry, so entries alone call two pipelines differing only in their wording identical,
    # which is the comparison a builder makes most often. The containers are compared for the
    # same reason: a sub-pipeline's budget is on no leaf's entry.
    if (
        before == dict(after)
        and was.containers == dict(now.containers)
        and prompts[0] == dict(prompts[1])
    ):
        raise ConfigurationError(
            f"Variant {name!r} is the same pipeline as the baseline: every node declares the "
            f"same kind, edges, tools, sampling parameters, schema and prompt. Running it "
            f"would measure the backend rather than a change.\n"
            f"Change something in the variant, or drop it from the sweep."
        )
    _refuse_reshaped_inputs(was, now, name=name)


def _refuse_reshaped_inputs(before: _Shape, after: _Shape, *, name: str) -> None:
    """Refuse a rewiring that feeds a node a value of a different declared shape.

    Nothing checks that a successor accepts its predecessor's type, so this would fail on every
    rollout rather than report a comparison.
    """
    for node_id in sorted(set(before.entries) & set(after.entries)):
        if not before.feeding(node_id) or not after.feeding(node_id):
            continue
        if before.feeding(node_id) == after.feeding(node_id):
            continue
        raise ConfigurationError(
            f"Variant {name!r} feeds node {node_id!r} a value of a different declared shape: "
            f"{_reshaping(before, after, node_id)}. A node receives what the node before it "
            f"returned, so every rollout would fail there instead of measuring anything.\n"
            f"Give the replacement the same output_schema as the node it stands in for, or "
            f"change the successor's prompt to accept what it now receives."
        )


def _reshaping(before: _Shape, after: _Shape, node_id: str) -> str:
    """Which node started feeding this one something else, in ids rather than schema digests."""
    was, now = before.sources(node_id), after.sources(node_id)
    if was == now:
        return f"{_names(now)} declares a different output_schema from before"
    return (
        f"its input came from {_names(was)} and now comes from {_names(now)}, which declares a "
        f"different output_schema"
    )


def _refuse_before_planning(variants: Mapping[str, Pipeline], envelope: RunEnvelope) -> None:
    """What is wrong with the call itself, before a plan is made or anything is paid for."""
    if not variants:
        raise ConfigurationError(
            "compare_variants was given no variants, so there is nothing to compare the "
            "baseline against.\n"
            "Pass at least one, as compare_variants(suite, {'no tools': leaner}, ...), or "
            "call ablate(pipeline) for the standard set."
        )
    if envelope.live:
        raise ConfigurationError(
            "compare_variants was given an envelope declaring live=True, and a sweep's "
            "rollouts are not runs an end user made: they run the example set, and every arm "
            "but the baseline is a pipeline this project does not have.\n"
            "Pass the envelope the evaluation uses, without with_live(), and mark the runs a "
            "person makes where the agent is actually served (docs/shipping.md §1)."
        )


def _refuse_over_ceiling(
    plans: Mapping[str, VariantPlan],
    baseline_calls: int,
    *,
    examples: int,
    k: int,
    max_live_calls: int | None,
) -> None:
    if max_live_calls is None:
        return
    per_variant = {name: plan.live_calls * examples * k for name, plan in plans.items()}
    total = baseline_calls + sum(per_variant.values())
    if total <= max_live_calls:
        return
    lines = "\n".join(
        f"  {name}: at most {calls} live calls, differing at {', '.join(plans[name].differs_at)}"
        for name, calls in per_variant.items()
    )
    raise ConfigurationError(
        f"This sweep would make at most {total} live model calls and max_live_calls is "
        f"{max_live_calls}. Nothing has run yet.\n"
        f"  baseline: at most {baseline_calls} live calls\n"
        f"{lines}\n"
        f"Raise max_live_calls to {total}, drop a variant, or lower k or the size of the "
        f"split. A variant differing only at a terminal node makes no live calls at all, "
        f"because the recording answers every request the change cannot have altered."
    )


# -- the estimate --------------------------------------------------------------------------


# The parts of a node entry that decide what it sends. A node whose only difference is where
# its output goes issues the requests it issued before, so its calls still replay: deleting a
# terminal node changes its predecessor's `successors` and changes nothing the backend sees.
# `route`, `on_error` and `retry` are outside this for the same reason. A retried call repeats
# the request it failed on, which keys the same. `model` is in it because the cassette key
# covers model identity, so a node whose model changed has no recorded response to serve.
_REQUEST_FIELDS = (
    "node_kind",
    "model",
    "schema",
    "allow_unknown",
    "context_builder",
    "stream",
    "sampling",
    "tools",
    "finish_check",
    "node_budget",
    "loop",
)


def _requests_differ(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    return any(before.get(field) != after.get(field) for field in _REQUEST_FIELDS)


def _taint(after: _Shape, *, seeds: set[str]) -> set[str]:
    """The seeds, plus everything reachable from them along declared edges.

    A changed node's output reaches every node it can reach, so their requests can differ too.
    Declared edges rather than the ones a route would pick, since which a route picks depends
    on values this has not seen. Error edges are followed as well: a handler receives a
    `NodeFailure` naming the node that failed, so a change there changes what it is called with.
    """
    tainted = set(seeds)
    frontier = list(seeds)
    while frontier:
        for successor in after.reaches.get(frontier.pop(), ()):
            if successor in after.entries and successor not in tainted:
                tainted.add(successor)
                frontier.append(successor)
    return tainted


def _estimated_calls(node_id: str, entry: Mapping[str, Any], measured: EvalResults | None) -> int:
    if entry["node_kind"] not in _CALLING_KINDS:
        return 0
    if measured is not None and node_id in measured.nodes:
        node = measured.nodes[node_id]
        return node.model_calls if node.runs == 0 else round(node.model_calls / node.runs)
    return _declared_calls_of(entry)


def _estimated_cost(node_id: str, measured: EvalResults | None) -> float | None:
    if measured is None or node_id not in measured.nodes:
        return None
    cost = measured.nodes[node_id].cost
    if cost is None or cost.value is None:
        return None
    return cost.value


def _declared_calls_of(entry: Mapping[str, Any]) -> int:
    """One call for an `LLMNode`, and an `AgentNode`'s whole step budget."""
    if entry["node_kind"] == "llm":
        return 1
    budget = entry.get("node_budget") or {}
    return int(budget.get("max_steps") or 1)


def _declared_calls(pipeline: Pipeline) -> int:
    return sum(
        _declared_calls_of(entry)
        for entry in pipeline.manifest_nodes()
        if entry["node_kind"] in _CALLING_KINDS
    )


# -- pipeline surgery ----------------------------------------------------------------------


def _replacing(pipeline: Pipeline, node_id: str, replacement: Any) -> Pipeline:
    """The pipeline with one node swapped for another, and nothing else changed.

    A node inside a nested pipeline is swapped inside that pipeline, so it keeps its id, its
    container keeps its own budget and edges, and the arm pairs with the baseline node for node.
    """
    arm = _rebuilt(pipeline, node_id, replacement)
    _refuse_own_defect(pipeline, arm, node_id, removed=False)
    return arm


def _without(pipeline: Pipeline, node_id: str) -> Pipeline:
    """The pipeline with one node removed and the edges that named it spliced past it.

    Every edge into the removed node is re-pointed at what the removed node led to, and where
    it ended its pipeline the edge is dropped so its predecessor ends it instead. That is what
    a pipeline whose edges were left to the default already does, since a successor nobody
    named resolves to the next node in the list.

    Raises :class:`~simple_agents.errors.ConfigurationError` where the splice leaves a graph
    the pipeline refuses, such as a predecessor holding two successors and no route.
    """
    arm = _rebuilt(pipeline, node_id, None)
    _refuse_own_defect(pipeline, arm, node_id, removed=True)
    return arm


def _rebuilt(pipeline: Pipeline, node_id: str, replacement: Any, prefix: str = "") -> Pipeline:
    """One node swapped or removed, rebuilding only the pipelines on the path down to it."""
    target = node_id[len(prefix) :]
    children: list[Any] = []
    dropped: str | None = None
    for child in pipeline.nodes:
        if isinstance(child, Pipeline) and target.startswith(f"{child.node_id}."):
            children.append(_rebuilt(child, node_id, replacement, f"{prefix}{child.node_id}."))
        elif child.node_id != target:
            children.append(child)
        elif replacement is not None:
            children.append(replacement)
        else:
            dropped = child.node_id

    if dropped is not None:
        children = _spliced(pipeline, children, dropped)
    if not children:
        raise ConfigurationError(
            f"Removing node {node_id!r} would leave the pipeline it is in with no nodes, and a "
            f"pipeline needs at least one node to run.\n"
            f"Remove the pipeline that holds it from the pipeline that holds that, by writing "
            f"the variant by hand and passing it to compare_variants."
        )
    return _same_but(pipeline, children)


def _spliced(pipeline: Pipeline, children: Sequence[Any], dropped: str) -> list[Any]:
    """The remaining nodes, with every edge that named the dropped one re-pointed past it.

    Each node's resolved edges are declared explicitly on the copy, because the default of the
    next node in the list stops meaning what it meant once a node leaves the list.
    """
    onward = pipeline.graph.successors[dropped]
    for holder in children:
        if getattr(holder, "on_error", None) == dropped:
            raise ConfigurationError(
                f"Node {dropped!r} is where {holder.node_id!r} sends a failure, so removing it "
                f"leaves that failure with no handler. What travels an error edge is a "
                f"NodeFailure rather than an output, so re-pointing it at what {dropped!r} led "
                f"to would hand that node a value of a different shape.\n"
                f"Write the variant by hand and pass it to compare_variants, deciding there "
                f"what should handle the failure instead."
            )

    spliced: list[Any] = []
    for child in children:
        targets: list[str] = []
        for target in pipeline.graph.successors[child.node_id]:
            targets.extend(onward if target == dropped else (target,))
        loop = getattr(child, "loop", None)
        if loop is not None and loop.then == dropped:
            if len(onward) != 1:
                raise ConfigurationError(
                    f"Node {child.node_id!r} has loop=Loop(then={dropped!r}), and {dropped!r} "
                    f"leads to {len(onward)} nodes, so there is no single successor for the "
                    f"run to take once the iteration count is reached.\n"
                    f"Write the variant by hand and pass it to compare_variants, naming there "
                    f"where the run should continue."
                )
            loop = Loop(max_iterations=loop.max_iterations, then=onward[0])
        spliced.append(_with_edges(child, successors=tuple(dict.fromkeys(targets)), loop=loop))
    return spliced


def _with_edges(node: Any, *, successors: tuple[str, ...], loop: Any) -> Any:
    """A copy of this node declaring these edges, sharing everything else with the original.

    Shallow, so the copy calls the same prompt function with the same tools and the same model
    client. The baseline is untouched, which is what lets the two arms run in one session.
    """
    copied = copy.copy(node)
    copied.successors = list(successors)
    copied.loop = loop
    return copied


def _groups_over(
    groups: Sequence[Sequence[str]], nodes: Sequence[Any]
) -> tuple[tuple[str, ...], ...]:
    """The concurrency groups narrowed to the nodes an arm still has.

    A node an ablation removed leaves the group it was in, and a group left with fewer than two
    members says nothing and is dropped. Narrowing rather than refusing is what lets a pipeline
    that declares a group be ablated at all.
    """
    kept = {node.node_id for node in nodes}
    narrowed = [tuple(n for n in group if n in kept) for group in groups]
    return tuple(group for group in narrowed if len(set(group)) > 1)


def _same_but(pipeline: Pipeline, nodes: Sequence[Any]) -> Pipeline:
    """The pipeline it was handed, over these nodes and unchanged in every other way.

    Every constructor argument travels, so an arm keeps the budget, the tool registry, the
    fetch policy and the concurrency groups of the pipeline it was derived from, at every level
    of nesting. An arm that dropped a group would run one after another what the baseline ran
    at the same time, which is a second difference in a comparison meant to hold one.

    The registered ``name`` travels too, so a sweep's runs say which pipeline they are arms of.
    They declare ``role="variant"``, which is what keeps them out of every check that reads the
    agent's runs.
    """
    arm = Pipeline(
        nodes,
        budget=pipeline.budget,
        node_id=pipeline.node_id,
        tools=pipeline.tools,
        fetch_policy=pipeline.fetch_policy,
        concurrent_nodes=_groups_over(pipeline.concurrent_nodes, nodes),
        successors=pipeline.successors,
        route=pipeline.route,
        loop=pipeline.loop,
        on_error=pipeline.on_error,
        retry=pipeline.retry,
        suspend_before=pipeline.suspend_before,
    )
    arm.name = pipeline.name
    return arm


def _refuse_own_defect(baseline: Pipeline, arm: Pipeline, node_id: str, *, removed: bool) -> None:
    """Refuse an arm whose nodes are not the baseline's, which is this module's own defect.

    Every figure a variant comparison reports is keyed on node_id, so an arm that renamed
    anything reports a difference at nodes nobody changed.
    """
    want = [declared for declared, _ in baseline.declared_nodes()]
    if removed:
        want = [declared for declared in want if declared != node_id]
    got = [declared for declared, _ in arm.declared_nodes()]
    if got != want:
        raise CallerFacingError(
            f"Building the variant for node {node_id!r} produced a pipeline declaring "
            f"{', '.join(repr(g) for g in got)} where it should declare "
            f"{', '.join(repr(w) for w in want)}. Per-node figures are keyed on node_id, so "
            f"this arm would report differences at nodes nothing changed.\n"
            f"This is a defect in Simple Agents rather than in the pipeline. Please report it "
            f"with the shape of the pipeline that produced it."
        )


def _removable(node_id: str, shape: _Shape) -> str | None:
    """Why removing this node would not measure it, or ``None`` where nothing stands in the way.

    A node that ends the whole run is removable: its output was the run's, and what a shorter
    run answers is the measurement. Anything else hands its successors what its predecessors
    produced, so those have to declare the shape it declared.
    """
    entry = shape.entries[node_id]
    if len(shape.entries) == 1:
        return "it is the only node in the pipeline, so removing it would leave nothing to run."
    if shape.ends_the_run(node_id):
        return None
    feeding = shape.feeding(node_id)
    if not feeding:
        return (
            "no edge reaches it, so it is where the run starts and its input is what run() was "
            "passed rather than another node's output."
        )
    if feeding != {entry.get("schema")}:
        return (
            f"{_names(shape.sources(node_id))} feeds it and declares a different "
            f"output_schema, so removing it would hand {_names(shape.carries[node_id])} a "
            f"value of a different declared shape and every rollout would fail there."
        )
    return None


def _declared_successors(node: Any) -> Sequence[str] | None:
    declared = getattr(node, "successors", None)
    return list(declared) if declared else None


def _with_pipeline(suite: EvalSuite, pipeline: Pipeline) -> EvalSuite:
    """The baseline suite, re-declared over a variant's pipeline.

    Everything the suite declares travels to the arm, so a project metric is scored on both
    sides and the comparison can pair it. A per-node declaration for a node the variant
    removed is dropped rather than refused: the comparison already reports that node as
    removed, and refusing the arm would make removal the one change that cannot be measured.
    """
    declared = {node_id for node_id, _ in pipeline.declared_nodes()}
    return EvalSuite(
        pipeline,
        suite.examples,
        answer=suite.answer,
        matches=suite.matches,
        criteria=suite.criteria,
        contamination_threshold=suite.contamination_threshold,
        node_matches={
            node_id: fn for node_id, fn in suite.node_matches.items() if node_id in declared
        },
        metrics=suite.metrics,
        node_metrics={
            node_id: fns for node_id, fns in suite.node_metrics.items() if node_id in declared
        },
        baseline=suite.baseline,
        judgements=suite.judgements_path,
    )


# -- the graph the entries describe ---------------------------------------------------------


@dataclass(frozen=True)
class _Shape:
    """The graph two manifests describe, over the ids per-node figures are keyed on.

    `nodes` holds leaves and `containers` holds the pipelines used as nodes, so neither on its
    own is a connected graph: an edge naming a container has no entry to point at, and a leaf
    that ends its container reads as ending the run. This stitches them.

    `carries` is where a node's output travels, which is what a declared shape is read along.
    `reaches` adds the error edges, which carry a `NodeFailure` rather than an output, so they
    reach a node without feeding it one.
    """

    entries: dict[str, Any]
    containers: dict[str, Any]
    carries: dict[str, tuple[str, ...]]
    reaches: dict[str, tuple[str, ...]]

    def sources(self, node_id: str) -> set[str]:
        """Every node whose output arrives at this one."""
        return {source for source, targets in self.carries.items() if node_id in targets}

    def feeding(self, node_id: str) -> set[str | None]:
        """The declared output schemas of every node whose output arrives at this one."""
        return {self.entries[source].get("schema") for source in self.sources(node_id)}

    def predecessors(self, node_id: str) -> set[str]:
        """Every node that can reach this one along one edge, error edges included."""
        return {source for source, targets in self.reaches.items() if node_id in targets}

    def ends_the_run(self, node_id: str) -> bool:
        """Whether this node's output is the run's, rather than another node's input."""
        return not self.carries.get(node_id)


def _shape_of(nodes: Sequence[Any], containers: Sequence[Any]) -> _Shape:
    entries = {entry["node_id"]: entry for entry in nodes}
    holders = {entry["node_id"]: entry for entry in containers}
    holding = {child: entry["node_id"] for entry in containers for child in entry["nodes"]}

    def entered_at(node_id: str) -> str:
        """The leaf a value arriving at this id reaches first."""
        while node_id in holders:
            node_id = holders[node_id]["nodes"][0]
        return node_id

    def carried_to(node_id: str) -> tuple[str, ...]:
        """Where the value this id produced goes, following container boundaries outward."""
        declared = (entries.get(node_id) or holders.get(node_id) or {}).get("successors") or ()
        if declared:
            return tuple(entered_at(target) for target in declared)
        above = holding.get(node_id)
        return carried_to(above) if above is not None else ()

    def handlers(node_id: str) -> tuple[str, ...]:
        """Every error edge that a failure at this node can take, its containers' included."""
        found = []
        at: str | None = node_id
        while at is not None:
            handler = (entries.get(at) or holders.get(at) or {}).get("on_error")
            if handler:
                found.append(entered_at(handler))
            at = holding.get(at)
        return tuple(found)

    carries = {node_id: carried_to(node_id) for node_id in entries}
    reaches = {
        node_id: tuple(dict.fromkeys(targets + handlers(node_id)))
        for node_id, targets in carries.items()
    }
    return _Shape(entries=entries, containers=holders, carries=carries, reaches=reaches)


# -- reading the entries -------------------------------------------------------------------


def _cost_of(results: EvalResults) -> Any:
    return (results.totals.get("cost") or {}).get("value")


def _tool_spend_of(results: EvalResults) -> Any:
    """What this arm's tools cost. A variant that drops a paid tool moves this and not `cost`."""
    return (results.totals.get("tool_spend") or {}).get("amount")


def _names(node_ids: Iterable[str]) -> str:
    return ", ".join(repr(node_id) for node_id in sorted(node_ids)) or "nothing"


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name).strip("-").lower() or "variant"
