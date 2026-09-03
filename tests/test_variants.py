"""Two versions of a pipeline, planned and compared.

The plan is the part with a guarantee behind it: a node whose own configuration is unchanged
and whose every ancestor is unchanged issues byte-identical requests at identical seeds, so the
baseline's recording answers them. These tests hold that guarantee against real replays rather
than against the rule that produced it.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Mapping

import pytest

from simple_agents.pipeline.recording import _node_entries
from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    ConfigurationError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    Tool,
    ToolRegistry,
)
from simple_agents.evaluation import (
    VARIANT_FORMAT_VERSION,
    VARIANT_ROLE,
    Example,
    ExampleSet,
    EvalSuite,
    ProjectMetric,
    ablate,
    compare_variants,
    plan_variant,
)
from simple_agents.models import ToolCallRequest, fake_response

from schemas import Answer

RUN_BUDGET = Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None)
NODE_BUDGET = Budget(max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=None)
ANSWER = '{"answer": "32 inches", "source": "size chart"}'


def hunt_prompt(inputs, ctx):
    return Prompt.user("Find: {question}", question=inputs["question"])


def verify_prompt(inputs, ctx):
    return Prompt.user("Check: {inputs}", inputs=inputs)


def look_up() -> Tool:
    return Tool(
        name="look_up",
        description="Search the catalogue. Returns matching entries.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        side_effect_class=SideEffectClass.READ_ONLY,
        fn=lambda query: "The inseam is 32 inches.",
    )


def agent_then_llm() -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                hunt_prompt,
                tools=[look_up()],
                output_schema=Answer,
                budget=NODE_BUDGET,
                node_id="hunt",
            ),
            LLMNode(verify_prompt, output_schema=Answer, node_id="verify"),
        ],
        budget=RUN_BUDGET,
    )


def examples() -> ExampleSet:
    return ExampleSet(
        [
            Example(
                id="e1", inputs={"question": "inseam?"}, expected="32 inches", split="held_out"
            ),
            Example(id="dev1", inputs={"question": "rise?"}, expected="11 inches", split="dev"),
        ],
        held_out="held_out",
    )


def suite_over(pipeline: Pipeline) -> EvalSuite:
    return EvalSuite(
        pipeline,
        examples(),
        answer="answer",
        matches=lambda s: s.expected.lower() in str(s.answer).lower(),
    )


def scripted() -> FakeModelClient:
    """Two rollouts of the two-node pipeline: a tool call, a finish, then the verifier."""
    return FakeModelClient(
        responses=[
            fake_response(
                tool_calls=[ToolCallRequest(id="c1", name="look_up", arguments={"query": "inseam"})]
            ),
            fake_response(
                tool_calls=[
                    ToolCallRequest(
                        id="c2",
                        name="finish",
                        arguments={"answer": "32 inches", "source": "size chart"},
                    )
                ]
            ),
            fake_response(content=ANSWER),
        ]
        * 8
    )


class TestThePlan:
    def test_removing_a_terminal_node_leaves_everything_replayable(self) -> None:
        """The largest saving available, and the one FT-12's message describes.

        Nothing upstream of a removed node changes, so every remaining request keys the same.
        """
        base = agent_then_llm()
        plan = plan_variant(base, ablate(base)["verify removed"], name="verify removed")

        assert plan.live_calls == 0
        assert [n.calls for n in plan.nodes if n.node_id == "hunt"] == ["replayed"]

    def test_a_node_that_only_lost_a_successor_still_replays(self) -> None:
        """`successors` says where the output goes, not what the backend is sent.

        Deleting a terminal node changes its predecessor's entry, and the predecessor issues
        the requests it issued before.
        """
        base = agent_then_llm()
        variant = ablate(base)["verify removed"]

        plan = plan_variant(base, variant, name="verify removed")
        hunt = next(n for n in plan.nodes if n.node_id == "hunt")

        assert (hunt.status, hunt.calls) == ("changed", "replayed")

    def test_a_changed_node_makes_everything_after_it_live(self) -> None:
        base = agent_then_llm()
        plan = plan_variant(base, ablate(base)["hunt as one call"], name="hunt as one call")

        assert {n.node_id: n.calls for n in plan.nodes} == {"hunt": "live", "verify": "live"}

    def test_a_changed_node_does_not_make_anything_before_it_live(self) -> None:
        base = agent_then_llm()
        variant = Pipeline(
            [
                base.nodes[0],
                LLMNode(verify_prompt, output_schema=Answer, node_id="verify", temperature=0.9),
            ],
            budget=RUN_BUDGET,
        )

        plan = plan_variant(base, variant, name="warmer verifier")

        assert {n.node_id: n.calls for n in plan.nodes} == {"hunt": "replayed", "verify": "live"}
        assert "nodes.verify.sampling.temperature" in plan.changed

    def test_a_node_fed_by_a_different_predecessor_is_live(self) -> None:
        """Removing a middle node leaves its successor unchanged and fed by something else.

        Nothing about `verify` differs here, and it receives what `load` returned rather than
        what `hunt` returned, so its requests differ and the recording does not answer them.
        The removal is allowed because the two declare the same shape.
        """
        base = Pipeline(
            [
                Deterministic(lambda inputs, ctx: inputs, node_id="load", output_schema=Answer),
                LLMNode(hunt_prompt, output_schema=Answer, node_id="hunt"),
                LLMNode(verify_prompt, output_schema=Answer, node_id="verify"),
            ],
            budget=RUN_BUDGET,
        )
        variant = Pipeline(
            [
                Deterministic(lambda inputs, ctx: inputs, node_id="load", output_schema=Answer),
                LLMNode(verify_prompt, output_schema=Answer, node_id="verify"),
            ],
            budget=RUN_BUDGET,
        )

        plan = plan_variant(base, variant, name="hunt removed")

        assert next(n for n in plan.nodes if n.node_id == "verify").status == "unchanged"
        assert next(n for n in plan.nodes if n.node_id == "verify").calls == "live"

    def test_an_edited_prompt_is_a_difference(self) -> None:
        """A prompt lives outside the node entry, so a diff over entries alone misses it."""
        base = agent_then_llm()
        variant = Pipeline(
            [
                base.nodes[0],
                LLMNode(
                    lambda inputs, ctx: Prompt.user("Verify this instead: {inputs}", inputs=inputs),
                    output_schema=Answer,
                    node_id="verify",
                ),
            ],
            budget=RUN_BUDGET,
        )

        plan = plan_variant(base, variant, name="reworded verifier")

        assert next(n for n in plan.nodes if n.node_id == "verify").calls == "live"

    def test_the_change_is_named_per_node(self) -> None:
        base = agent_then_llm()
        plan = plan_variant(base, ablate(base)["hunt as one call"], name="hunt as one call")

        assert plan.changed["nodes.hunt.node_kind"] == ["agent", "llm"]
        assert plan.changed["nodes.hunt.tools"] == [["look_up"], []]
        assert plan.differs_at == ("hunt",)

    def test_an_agent_node_is_estimated_at_its_step_budget_before_it_has_run(self) -> None:
        base = agent_then_llm()
        variant = Pipeline(
            [
                AgentNode(
                    hunt_prompt, tools=[], output_schema=Answer, budget=NODE_BUDGET, node_id="hunt"
                ),
                base.nodes[1],
            ],
            budget=RUN_BUDGET,
        )

        plan = plan_variant(base, variant, name="hunt without tools")

        assert next(n for n in plan.nodes if n.node_id == "hunt").estimated_calls == 4


class TestComparabilityRefusals:
    def test_it_refuses_two_pipelines_sharing_no_node_id(self) -> None:
        other = Pipeline(
            [LLMNode(hunt_prompt, output_schema=Answer, node_id="something_else")],
            budget=RUN_BUDGET,
        )

        with pytest.raises(ConfigurationError) as raised:
            plan_variant(agent_then_llm(), other, name="unrelated")

        assert "shares no node id" in str(raised.value)
        assert "node_id" in str(raised.value)

    def test_it_refuses_a_variant_identical_to_the_baseline(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            plan_variant(agent_then_llm(), agent_then_llm(), name="the same thing")

        assert "same pipeline as the baseline" in str(raised.value)

    def test_it_refuses_a_rewiring_that_reshapes_a_node_s_input(self) -> None:
        """Nothing checks a successor accepts its predecessor's type, so this would fail on
        every rollout rather than report a comparison."""
        base = Pipeline(
            [
                Deterministic(lambda inputs, ctx: inputs, node_id="load"),
                LLMNode(hunt_prompt, output_schema=Answer, node_id="hunt"),
                LLMNode(verify_prompt, output_schema=Answer, node_id="verify"),
            ],
            budget=RUN_BUDGET,
        )
        variant = Pipeline(
            [
                Deterministic(lambda inputs, ctx: inputs, node_id="load"),
                LLMNode(verify_prompt, output_schema=Answer, node_id="verify"),
            ],
            budget=RUN_BUDGET,
        )

        with pytest.raises(ConfigurationError) as raised:
            plan_variant(base, variant, name="hunt removed")

        assert "different declared shape" in str(raised.value)
        assert "'verify'" in str(raised.value)

    def test_ablate_leaves_out_a_removal_that_would_reshape_an_input(self) -> None:
        base = Pipeline(
            [
                Deterministic(lambda inputs, ctx: inputs, node_id="load"),
                LLMNode(hunt_prompt, output_schema=Answer, node_id="hunt"),
                LLMNode(verify_prompt, output_schema=Answer, node_id="verify"),
            ],
            budget=RUN_BUDGET,
        )

        assert "hunt removed" not in ablate(base)
        assert "verify removed" in ablate(base)

    def test_it_refuses_a_sweep_with_no_variants(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            compare_variants(
                suite_over(agent_then_llm()),
                {},
                envelope=RunEnvelope(run_dir=tmp_path),
                split="held_out",
                k=2,
            )

        assert "no variants" in str(raised.value)
        assert "ablate(pipeline)" in str(raised.value)


class TestTheCeiling:
    def test_it_refuses_before_the_first_call_and_names_every_arm(self, tmp_path) -> None:
        base = agent_then_llm()

        with pytest.raises(ConfigurationError) as raised:
            compare_variants(
                suite_over(base),
                ablate(base),
                envelope=RunEnvelope(run_dir=tmp_path),
                model=scripted(),
                split="held_out",
                k=2,
                seed=41,
                max_live_calls=1,
            )

        message = str(raised.value)
        assert "Nothing has run yet" in message
        assert "hunt as one call" in message and "verify removed" in message
        assert not list(tmp_path.glob("**/trajectory.jsonl"))

    def test_no_ceiling_runs_whatever_it_costs(self, tmp_path) -> None:
        base = agent_then_llm()

        comparison = compare_variants(
            suite_over(base),
            {"verify removed": ablate(base)["verify removed"]},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=scripted(),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

        assert comparison.baseline.config["k"] == 2


class TestTheSweep:
    @pytest.fixture
    def swept(self, tmp_path):
        base = agent_then_llm()
        return compare_variants(
            suite_over(base),
            ablate(base),
            envelope=RunEnvelope(run_dir=tmp_path),
            model=scripted(),
            split="held_out",
            k=2,
            seed=41,
            max_live_calls=100,
            concurrency=1,
        )

    def test_the_plan_is_what_the_run_did(self, swept) -> None:
        """The guarantee, held against a real replay rather than against the rule."""
        results = swept.variants["verify removed"]

        assert swept.plans["verify removed"].live_calls == 0
        assert results.nodes["hunt"].replayed_calls == results.nodes["hunt"].model_calls

    def test_the_changed_node_itself_is_always_called_live(self, swept) -> None:
        """The node whose configuration changed sends a request nothing was recorded against."""
        results = swept.variants["hunt as one call"]

        assert results.nodes["hunt"].replayed_calls == 0

    def test_a_node_planned_live_can_still_replay(self, swept) -> None:
        """`live_calls` is an upper bound, and this is the case that makes it one.

        `verify` is downstream of the changed node and the plan calls it live. Where the
        changed node happens to produce the value it produced before, the request downstream
        is the one on file and it replays after all.
        """
        plan = swept.plans["hunt as one call"]
        results = swept.variants["hunt as one call"]

        assert next(n for n in plan.nodes if n.node_id == "verify").calls == "live"
        assert results.nodes["verify"].replayed_calls <= results.nodes["verify"].model_calls

    def test_a_live_envelope_is_refused_before_anything_runs(self, tmp_path) -> None:
        """An arm declares a role, and a run cannot be both a variant and one a person made.

        Refused up front rather than on the first arm, which is after the baseline has run and
        been paid for.
        """
        with pytest.raises(ConfigurationError) as caught:
            compare_variants(
                suite_over(agent_then_llm()),
                {"leaner": agent_then_llm()},
                envelope=RunEnvelope(run_dir=tmp_path).with_live(),
                model=scripted(),
                split="held_out",
                k=1,
            )

        assert "not runs an end user made" in str(caught.value)
        assert not list(tmp_path.glob("**/manifest.json"))

    def test_an_arm_declares_itself_and_the_baseline_does_not(self, tmp_path) -> None:
        """An arm is a pipeline the project does not have, so no check reads one as the agent.

        The baseline keeps `agent`, since it is the pipeline the project has run over the
        example set; a project that has only ever swept therefore still has runs to certify.
        """
        base = agent_then_llm()
        run_dir = tmp_path / "sweep"
        compare_variants(
            suite_over(base),
            ablate(base),
            envelope=RunEnvelope(run_dir=run_dir),
            model=scripted(),
            split="held_out",
            k=2,
            seed=41,
            max_live_calls=100,
            concurrency=1,
        )
        roles = Counter(
            json.loads(manifest.read_text())["role"] for manifest in run_dir.rglob("manifest.json")
        )

        assert set(roles) == {"agent", VARIANT_ROLE}
        # One baseline against several arms, so the baseline is the smaller share of the sweep.
        assert roles["agent"] < roles[VARIANT_ROLE]

    def test_every_arm_ran_over_the_same_examples(self, swept) -> None:
        for name, _results in swept.variants.items():
            assert swept.comparisons[name].only_before == ()
            assert swept.comparisons[name].only_after == ()

    def test_the_arms_are_marked_as_mixed_where_the_numbers_are_read(self, swept) -> None:
        """A variant arm serves some calls and makes others, and its own file says so."""
        assert swept.baseline.config["cassette"]["mode"] == "record"
        for results in swept.variants.values():
            assert results.config["cassette"]["mode"] == "update"

    def test_the_cassette_difference_the_operation_creates_is_not_reported(self, swept) -> None:
        for comparison in swept.comparisons.values():
            assert not [path for path in comparison.changed if path.startswith("cassette.")]

    def test_a_sweep_too_small_to_conclude_says_so(self, swept) -> None:
        """FT-06's question arriving inside FT-12's.

        One held-out example cannot separate the arms, and the operation reports the delta and
        the interval without the claim that the difference is real.
        """
        for _name, comparison in swept.comparisons.items():
            assert comparison.moved == []
            assert "accuracy" in comparison.undecided
            assert comparison.metrics["accuracy"].delta is not None

    def test_the_results_carry_the_shape_they_were_measured_over(self, swept) -> None:
        """FT-12 asks whether an ablation predates a change to the pipeline shape."""
        assert swept.baseline.config["graph_fingerprint"].startswith("sha256:")
        assert (
            swept.variants["hunt as one call"].config["graph_fingerprint"]
            != swept.baseline.config["graph_fingerprint"]
        )


class TestTheArtifact:
    def test_it_writes_what_a_later_reader_needs(self, tmp_path) -> None:
        base = agent_then_llm()
        comparison = compare_variants(
            suite_over(base),
            {"verify removed": ablate(base)["verify removed"]},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=scripted(),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

        written = json.loads(comparison.write(tmp_path / "variants.json").read_text())

        assert written["variant_format_version"] == VARIANT_FORMAT_VERSION
        entry = written["variants"]["verify removed"]
        assert entry["plan"]["live_calls"] == 0
        assert entry["plan"]["differs_at"] == ["hunt", "verify"]
        assert entry["graph_fingerprint"] != written["baseline"]["graph_fingerprint"]
        assert "accuracy" in entry["comparison"]["metrics"]
        assert set(entry["cost"]) == {"baseline", "variant"}
        assert set(entry["tokens"]) == {"baseline", "variant"}


class TestCriteriaTravelToTheArms:
    """A criterion's check is declared on the suite and has to reach every arm.

    It did not, and every sweep and every ablation over a `Criteria` example set was refused
    at arm construction: the arm found the ids on the examples and no check registered for
    them. Nothing caught it, because no variants test used a decomposed answer key.
    """

    def test_an_arm_carries_the_checks_the_baseline_registered(self) -> None:
        from simple_agents.evaluation import Criteria, Criterion
        from simple_agents.evaluation.variants import _with_pipeline

        base = agent_then_llm()
        key = Criteria([Criterion(id="answered_at_all", text="put an answer forward")])
        examples = ExampleSet(
            [Example(id="q1", inputs={"question": "?"}, expected=key, split="held_out")]
        )
        declared = EvalSuite(
            base,
            examples,
            answer="answer",
            matches=lambda s: True,
            criteria={"answered_at_all": lambda s: bool(s.answer)},
        )

        arm = _with_pipeline(declared, base)

        assert set(arm.criteria) == {"answered_at_all"}


class TestProjectMetricsTravelToTheArms:
    def test_a_declared_metric_is_scored_on_every_arm_and_compared(self, tmp_path) -> None:
        """A metric declared on the suite reaches each variant, and a per-node declaration
        for a node the variant removed is dropped rather than refusing the arm."""
        base = agent_then_llm()
        chars = ProjectMetric(
            name="answer_chars",
            definition="characters in the asserted answer",
            score=lambda s: float(len(str(s.answer))),
            unit=None,
        )
        declared = EvalSuite(
            base,
            examples(),
            answer="answer",
            matches=lambda s: s.expected.lower() in str(s.answer).lower(),
            metrics=[chars],
            node_metrics={"verify": [chars]},
        )

        comparison = compare_variants(
            declared,
            {"verify removed": ablate(base)["verify removed"]},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=scripted(),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

        arm = comparison.variants["verify removed"]
        assert "answer_chars" in arm.metrics
        change = comparison.comparisons["verify removed"].metrics["answer_chars"]
        assert change.before is not None
        assert change.after is not None


# -- a pipeline ablate() did not generate ---------------------------------------------------


NESTED_BUDGET = Budget(max_steps=6, max_tokens=20_000, max_cost=None, max_wall_clock_ms=None)


def write_prompt(inputs, ctx):
    return Prompt.user("Write: {inputs}", inputs=inputs)


def nested() -> Pipeline:
    """`research` = [hunt, verify] inside an outer pipeline that then writes."""
    research = Pipeline(
        [
            AgentNode(
                hunt_prompt,
                tools=[look_up()],
                output_schema=Answer,
                budget=NODE_BUDGET,
                node_id="hunt",
            ),
            LLMNode(verify_prompt, output_schema=Answer, node_id="verify"),
        ],
        budget=NESTED_BUDGET,
        node_id="research",
    )
    return Pipeline(
        [research, LLMNode(write_prompt, output_schema=Answer, node_id="write")],
        budget=RUN_BUDGET,
    )


class TestANestedPipeline:
    """`ablate()` rebuilt every arm from `declared_nodes()`, which returns leaves.

    A nested pipeline was flattened, so `research.hunt` came back as `hunt` and the comparison
    read one node as removed and its renamed twin as added.
    """

    def test_an_arm_keeps_every_node_id_the_baseline_declared(self) -> None:
        base = nested()

        for name, arm in ablate(base).items():
            declared = [node_id for node_id, _ in arm.declared_nodes()]
            removed = name[: -len(" removed")] if name.endswith(" removed") else None
            assert declared == [
                node_id for node_id, _ in base.declared_nodes() if node_id != removed
            ], name

    def test_an_arm_keeps_the_sub_pipelines_own_budget(self) -> None:
        arm = ablate(nested())["research.hunt as one call"]

        research = arm.manifest_containers()[0]
        assert research["node_id"] == "research"
        assert research["budget"] == NESTED_BUDGET.to_record()

    def test_an_arm_differs_at_the_one_node_it_is_named_for(self) -> None:
        base = nested()

        plan = plan_variant(
            base, ablate(base)["research.hunt as one call"], name="research.hunt as one call"
        )

        assert plan.differs_at == ("research.hunt",)
        assert {n.node_id: n.status for n in plan.nodes} == {
            "research.hunt": "changed",
            "research.verify": "unchanged",
            "write": "unchanged",
        }

    def test_a_change_inside_a_container_makes_what_follows_it_live(self) -> None:
        """The container's out-edge is on no leaf entry, so the taint walk stopped at it.

        `max_live_calls` is checked against this estimate, so a sweep could be admitted under a
        ceiling it then exceeded.
        """
        base = nested()
        arm = ablate(base)["research.hunt as one call"]

        plan = plan_variant(base, arm, name="research.hunt as one call")

        assert {n.node_id: n.calls for n in plan.nodes} == {
            "research.hunt": "live",
            "research.verify": "live",
            "write": "live",
        }

    def test_removing_the_node_that_ends_a_container_is_left_out_where_it_reshapes(self) -> None:
        """A node ending a nested pipeline reads as ending the run, and was offered unchecked.

        What it produces is what the container produces, so removing it changes what the next
        node in the outer graph receives.
        """
        research = Pipeline(
            [
                Deterministic(lambda inputs, ctx: {"notes": inputs}, node_id="hunt"),
                LLMNode(verify_prompt, output_schema=Answer, node_id="verify"),
            ],
            budget=NESTED_BUDGET,
            node_id="research",
        )
        base = Pipeline(
            [research, LLMNode(write_prompt, output_schema=Answer, node_id="write")],
            budget=RUN_BUDGET,
        )

        arms = ablate(base)

        assert "research.verify removed" not in arms
        assert "different declared shape" in arms.skipped["research.verify removed"]
        assert "'research.hunt'" in arms.skipped["research.verify removed"]

    def test_the_first_node_of_a_container_is_not_removable(self) -> None:
        arms = ablate(nested())

        assert "research.hunt removed" not in arms
        assert "run() was passed" in arms.skipped["research.hunt removed"]


class TestRemovingANodeAnEdgeNames:
    """`_without` dropped the node and left the edge, so `Pipeline` refused the arm.

    The refusal raised out of `ablate()`, which cost the whole standard set rather than one arm.
    """

    def declared(self) -> Pipeline:
        return Pipeline(
            [
                LLMNode(hunt_prompt, output_schema=Answer, node_id="hunt", successors=["verify"]),
                LLMNode(
                    verify_prompt, output_schema=Answer, node_id="verify", successors=["write"]
                ),
                LLMNode(write_prompt, output_schema=Answer, node_id="write"),
            ],
            budget=RUN_BUDGET,
        )

    def defaulted(self) -> Pipeline:
        return Pipeline(
            [
                LLMNode(hunt_prompt, output_schema=Answer, node_id="hunt"),
                LLMNode(verify_prompt, output_schema=Answer, node_id="verify"),
                LLMNode(write_prompt, output_schema=Answer, node_id="write"),
            ],
            budget=RUN_BUDGET,
        )

    def test_the_two_spellings_of_one_graph_generate_the_same_arms(self) -> None:
        """`successors=None` resolves to the next node in the list, so these are one graph."""
        assert sorted(ablate(self.declared())) == sorted(ablate(self.defaulted()))

    def test_the_predecessor_is_re_pointed_at_what_the_removed_node_led_to(self) -> None:
        arm = ablate(self.declared())["verify removed"]

        assert [entry["successors"] for entry in arm.manifest_nodes()] == [["write"], []]

    def test_removing_the_node_that_ends_the_run_leaves_its_predecessor_ending_it(self) -> None:
        arm = ablate(self.declared())["write removed"]

        assert [node_id for node_id, _ in arm.declared_nodes()] == ["hunt", "verify"]
        assert [entry["successors"] for entry in arm.manifest_nodes()] == [["verify"], []]


class TestWhatAblateSkips:
    def routed(self) -> Pipeline:
        """`hunt` chooses between `verify` and `write`, and `polish` is off the routed part."""
        return Pipeline(
            [
                LLMNode(hunt_prompt, output_schema=Answer, node_id="load"),
                LLMNode(
                    hunt_prompt,
                    output_schema=Answer,
                    node_id="hunt",
                    successors=["verify", "write"],
                    route=lambda output, ctx: "verify",
                ),
                LLMNode(
                    verify_prompt, output_schema=Answer, node_id="verify", successors=["write"]
                ),
                LLMNode(write_prompt, output_schema=Answer, node_id="write", successors=["polish"]),
                LLMNode(write_prompt, output_schema=Answer, node_id="polish"),
            ],
            budget=RUN_BUDGET,
        )

    def test_a_removal_the_graph_refuses_is_skipped_rather_than_raised(self) -> None:
        """Re-pointing `load` past `hunt` gives it two successors and no route to pick with.

        The whole standard set used to be lost to this: the refusal raised out of `ablate()`.
        """
        arms = ablate(self.routed())

        assert "hunt removed" not in arms
        assert "no route" in arms.skipped["hunt removed"]
        assert "polish removed" in arms

    def test_a_removal_that_collapses_a_route_is_skipped_too(self) -> None:
        """Both of `hunt`'s edges lead to `write` once `verify` goes, so nothing is chosen."""
        arms = ablate(self.routed())

        assert "verify removed" not in arms
        assert "nothing to choose between" in arms.skipped["verify removed"]

    def test_a_node_another_node_sends_a_failure_to_is_skipped(self) -> None:
        base = Pipeline(
            [
                LLMNode(
                    hunt_prompt,
                    output_schema=Answer,
                    node_id="hunt",
                    on_error="rescue",
                    successors=["rescue"],
                ),
                LLMNode(
                    verify_prompt, output_schema=Answer, node_id="rescue", successors=["write"]
                ),
                LLMNode(write_prompt, output_schema=Answer, node_id="write"),
            ],
            budget=RUN_BUDGET,
        )

        arms = ablate(base)

        assert "rescue removed" not in arms
        assert "NodeFailure" in arms.skipped["rescue removed"]

    def test_it_is_a_mapping_so_it_goes_straight_to_compare_variants(self) -> None:
        arms = ablate(agent_then_llm())

        assert isinstance(arms, Mapping)
        assert set(arms) == {"hunt as one call", "verify removed"}
        assert arms.skipped == {
            "hunt removed": "no edge reaches it, so it is where the run starts and its input "
            "is what run() was passed rather than another node's output."
        }

    def test_a_single_node_pipeline_generates_nothing_and_says_why(self) -> None:
        base = Pipeline(
            [LLMNode(hunt_prompt, output_schema=Answer, node_id="hunt")], budget=RUN_BUDGET
        )

        arms = ablate(base)

        assert dict(arms) == {}
        assert "only node" in arms.skipped["hunt removed"]


class TestAnArmCarriesWhatTheBaselineDeclared:
    def test_a_tool_registry_survives_the_rebuild(self) -> None:
        """`Pipeline(tools=)` feeds the manifest and the mixed-currency refusal, not only the
        manifest, so an arm that lost it is an arm that refuses less than the baseline."""
        registry = ToolRegistry([look_up()])
        base = Pipeline(
            [
                LLMNode(hunt_prompt, output_schema=Answer, node_id="hunt"),
                LLMNode(verify_prompt, output_schema=Answer, node_id="verify"),
            ],
            budget=RUN_BUDGET,
            tools=registry,
        )

        arm = ablate(base)["verify removed"]

        assert arm.tools is registry
        assert [entry["name"] for entry in _node_entries(arm)[2]] == ["look_up"]


class TestANestedSweepRuns:
    def test_both_arms_run_and_the_comparison_pairs_every_node(self, tmp_path) -> None:
        """The arm has to be runnable, not only well-shaped: the flattened one was neither."""
        base = nested()

        comparison = compare_variants(
            suite_over(base),
            {"research.write removed": ablate(base)["write removed"]},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=scripted(),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

        arm = comparison.variants["research.write removed"]
        assert set(comparison.baseline.nodes) == {"research.hunt", "research.verify", "write"}
        assert set(arm.nodes) == {"research.hunt", "research.verify"}


class TestASweepThatCannotWriteSaysWhichArm:
    """The refusal named a directory whose name is a digest, and the sweep runs several.

    Measured on the checkpoint: the baseline arm ran and was paid for, the next arm resolved to
    a used directory, and the message named neither the arm nor the sweep.
    """

    def _sweep(self, tmp_path):
        base = agent_then_llm()
        return compare_variants(
            suite_over(base),
            {"verify removed": ablate(base)["verify removed"]},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=scripted(),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

    def test_the_refusal_names_the_arm_and_the_sweep(self, tmp_path) -> None:
        self._sweep(tmp_path)

        with pytest.raises(ConfigurationError) as raised:
            self._sweep(tmp_path)

        message = str(raised.value)
        assert "compare_variants stopped on the 'baseline' arm" in message
        assert "The sweep is the baseline against 'verify removed'" in message
        assert "already holds an evaluation's rollouts" in message

    def test_a_variant_arm_names_what_has_already_been_paid_for(self, tmp_path) -> None:
        """The baseline is new and the arm is not, which is where the count earns its place."""
        base = agent_then_llm()
        arm = ablate(base)["verify removed"]
        # The arm measured on its own first, into the same run_dir, so its directory exists
        # while the baseline's does not.
        suite_over(arm).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=scripted(),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

        with pytest.raises(ConfigurationError) as raised:
            compare_variants(
                suite_over(base),
                {"verify removed": arm},
                envelope=RunEnvelope(run_dir=tmp_path),
                model=scripted(),
                split="held_out",
                k=2,
                seed=41,
                concurrency=1,
            )

        message = str(raised.value)
        assert "compare_variants stopped on the 'verify removed' arm" in message
        assert "1 arm(s) of this sweep have already run and been paid for" in message


class TestAnArmDifferingOnlyInSamplingRuns:
    """`docs/evaluation.md` §10 leads with "a temperature moved", and the sweep refused it
    on its own directory."""

    def test_a_temperature_arm_runs_rather_than_colliding(self, tmp_path) -> None:
        base = agent_then_llm()
        hotter = _same_but_hotter(base)

        comparison = compare_variants(
            suite_over(base),
            {"hunt at 0.7": hotter},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=scripted(),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

        assert comparison.baseline.eval_id != comparison.variants["hunt at 0.7"].eval_id
        assert comparison.plans["hunt at 0.7"].changed["nodes.hunt.sampling.temperature"] == [
            None,
            0.7,
        ]


def _same_but_hotter(base: Pipeline) -> Pipeline:
    """The same pipeline with `hunt` at a temperature, which moves no edge and no schema."""
    nodes = []
    for node in base.nodes:
        if getattr(node, "node_id", None) != "hunt":
            nodes.append(node)
            continue
        nodes.append(
            AgentNode(
                node.prompt,
                tools=list(node.tools),
                output_schema=node.output_schema,
                budget=node.budget,
                node_id=node.node_id,
                temperature=0.7,
            )
        )
    return Pipeline(nodes, budget=base.budget)
