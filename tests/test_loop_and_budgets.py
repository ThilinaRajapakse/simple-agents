"""The AgentNode loop, budget composition, and the model-facing / caller-facing split."""

from __future__ import annotations

import json
import time

import pytest

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    BudgetExceeded,
    CallerFacingError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    ModelFacingError,
    Pipeline,
    SideEffectClass,
    Tool,
    read_trajectory,
    tool,
)
from simple_agents.errors import ConfigurationError
from simple_agents.budget import Spend
from simple_agents.models import ToolCallRequest, TokenUsage, fake_response

from schemas import Answer
from conftest import RUN_ID


def _finish(answer: str = "done") -> ToolCallRequest:
    return ToolCallRequest(id="f", name="finish", arguments={"answer": answer, "source": None})


def _prompt(inputs, ctx):
    return Prompt.user("go")


def _tokens(output: int = 5) -> TokenUsage:
    return TokenUsage(
        input_uncached=10,
        input_cache_read=0,
        input_cache_write=0,
        cache_ttl=None,
        output=output,
    )


class TestTermination:
    def test_finish_terminates_the_loop(self, envelope, trajectory):
        client = FakeModelClient(responses=[fake_response(tool_calls=[_finish()])])
        result = Pipeline(
            [AgentNode(_prompt, tools=[], output_schema=Answer, budget=Budget.unbounded())],
            budget=Budget.unbounded(),
        ).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        node = next(r for r in read_trajectory(trajectory) if r["record_type"] == "node_execution")
        assert node["termination"] == "finish"
        assert result.output.answer == "done"

    def test_max_steps_is_a_normal_outcome_not_an_error(self, envelope, trajectory):
        """A budget stop is a recorded outcome. The run completes; it does not raise."""
        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[ToolCallRequest(id="c", name="noop", arguments={})])
                for _ in range(5)
            ]
        )

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def noop() -> str:
            """Does nothing at all."""
            return "ok"

        result = Pipeline(
            [
                AgentNode(
                    _prompt,
                    tools=[noop],
                    output_schema=Answer,
                    budget=Budget(
                        max_steps=2,
                        max_tokens=None,
                        max_cost=None,
                        max_wall_clock_ms=None,
                    ),
                )
            ],
            budget=Budget.unbounded(),
        ).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        node = next(r for r in read_trajectory(trajectory) if r["record_type"] == "node_execution")
        assert node["termination"] == "max_steps"
        assert node["error"] is None, "a budget stop is not an error"
        assert result.output is None

    def test_a_response_with_no_tool_call_does_not_end_the_loop(self, envelope, trajectory):
        """Termination is an explicit `finish` call, never a heuristic on prose."""
        client = FakeModelClient(
            responses=[
                fake_response(content="I think the answer is probably 32."),
                fake_response(tool_calls=[_finish("32")]),
            ]
        )
        result = Pipeline(
            [AgentNode(_prompt, tools=[], output_schema=Answer, budget=Budget.unbounded())],
            budget=Budget.unbounded(),
        ).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        assert result.output.answer == "32"
        # Two calls: the prose one was pushed back, not accepted as an answer.
        assert len(client.requests) == 2
        nudge = client.requests[1].messages[-1]
        assert "finish" in nudge["content"]

    def test_malformed_finish_is_handed_back_to_the_model(self, envelope, trajectory):
        """A schema violation on finish is model-facing: it can try again."""
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="f1", name="finish", arguments={"wrong": "shape"})
                    ]
                ),
                fake_response(tool_calls=[_finish("recovered")]),
            ]
        )
        result = Pipeline(
            [AgentNode(_prompt, tools=[], output_schema=Answer, budget=Budget.unbounded())],
            budget=Budget.unbounded(),
        ).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        assert result.output.answer == "recovered"
        records = list(read_trajectory(trajectory))
        failed = [r for r in records if r["record_type"] == "tool_call" and r["error"] is not None]
        assert len(failed) == 1
        assert failed[0]["error"]["class"] == "model_facing"


class TestErrorSplit:
    def test_model_facing_error_becomes_an_observation(self, envelope, trajectory):
        """A tool failing in a way the model can react to is data, not a fault."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def flaky(query: str) -> str:
            """Search for something."""
            raise ModelFacingError("No results for that query. Try a broader one.")

        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c1", name="flaky", arguments={"query": "x"})]
                ),
                fake_response(tool_calls=[_finish("gave up")]),
            ]
        )
        result = Pipeline(
            [AgentNode(_prompt, tools=[flaky], output_schema=Answer, budget=Budget.unbounded())],
            budget=Budget.unbounded(),
        ).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        assert result.output.answer == "gave up"
        observation = client.requests[1].messages[-1]
        assert observation["role"] == "tool"
        assert "No results" in observation["content"]

        record = next(r for r in read_trajectory(trajectory) if r["record_type"] == "tool_call")
        assert record["error"]["class"] == "model_facing"
        assert record["error"]["retryable"] is True

    def test_undeclared_exception_is_caller_facing_and_stops_the_run(self, envelope, trajectory):
        """FT-22: swallowing infrastructure failure produces an agent that invents around it."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def broken(query: str) -> str:
            """Search an index that happens to be down."""
            raise ConnectionError("index unreachable")

        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c1", name="broken", arguments={"query": "x"})]
                )
            ]
        )
        with pytest.raises(CallerFacingError) as exc:
            Pipeline(
                [
                    AgentNode(
                        _prompt,
                        tools=[broken],
                        output_schema=Answer,
                        budget=Budget.unbounded(),
                    )
                ],
                budget=Budget.unbounded(),
            ).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        assert "not declared as model-facing" in str(exc.value)
        assert "ModelFacingError" in str(exc.value)

    def test_the_trajectory_survives_a_failed_run(self, envelope, trajectory):
        """A crashed run still leaves the records written before the failure."""

        def explode(inputs, ctx):
            raise ValueError("boom")

        with pytest.raises(ValueError):
            Pipeline([Deterministic(explode)]).run({}, envelope=envelope, run_id=RUN_ID)

        records = list(read_trajectory(trajectory))
        # The `run_start` record and the node's own, which is the failure being read here.
        assert [r["record_type"] for r in records] == ["run_start", "node_execution"]
        node = records[1]
        assert node["termination"] == "error"
        assert node["error"]["type"] == "ValueError"
        assert node["error"]["class"] == "caller_facing"


class TestWaitingIsChargedToNothing:
    """`max_wall_clock` bounds what the agent does, not how long the backend made it wait.

    Measured on dogfood #1: a budget derived from a 2,000 ms run, as the `budget` scaffold
    says to derive it, was 60,000 ms. One paced call waited 65,954 ms and the run was
    discarded, on 8 of 145 rollouts.
    """

    class Held:
        """A client whose calls return instantly and report having waited a long time."""

        def __init__(self, held_back_ms: int) -> None:
            self.held_back_ms = held_back_ms

        def identity(self):
            from simple_agents import ModelIdentity

            return ModelIdentity(backend="hosted_api", request_model="fake-1", model_revision=None)

        def complete(self, request):
            import dataclasses

            response = fake_response(json.dumps({"answer": "a"}), tokens=_tokens(output=5))
            return dataclasses.replace(response, held_back_ms=self.held_back_ms)

    def test_a_paced_wait_does_not_exhaust_the_wall_clock_axis(self, envelope, trajectory):
        def prompt(inputs, ctx):
            return Prompt.user("x")

        result = Pipeline(
            [LLMNode(prompt, output_schema=Answer, node_id="answer")],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=1_000),
        ).run({}, envelope=envelope, run_id=RUN_ID, model=self.Held(65_000))

        assert result.outcome == "completed"

    def test_the_record_still_brackets_the_whole_call(self, envelope, trajectory):
        """The trajectory says what happened; the budget says what the run is charged."""

        def prompt(inputs, ctx):
            return Prompt.user("x")

        Pipeline(
            [LLMNode(prompt, output_schema=Answer, node_id="answer")],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=1_000),
        ).run({}, envelope=envelope, run_id=RUN_ID, model=self.Held(65_000))

        calls = [r for r in read_trajectory(trajectory) if r["record_type"] == "model_call"]
        assert len(calls) == 1
        assert calls[0]["started_at"] <= calls[0]["ended_at"]


class TestBudgetComposition:
    def test_node_budget_narrows_the_run_budget(self):
        run = Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=60_000)
        node = Budget(max_steps=8, max_tokens=50_000, max_cost=1.0, max_wall_clock_ms=120_000)
        effective = run.narrowed_by(node)
        assert effective.max_steps == 8  # run unbounded -> node's cap applies
        assert effective.max_tokens == 50_000  # node is tighter
        assert effective.max_cost == 1.0  # run unbounded -> node's cap applies
        assert effective.max_wall_clock_ms == 60_000  # run is tighter; node cannot widen it

    def test_run_budget_depletes_across_nodes(self, envelope, trajectory):
        """Later nodes see less budget than earlier ones."""
        seen: list[int | None] = []

        def observe(inputs, ctx):
            seen.append(ctx.budget.max_tokens)
            return inputs

        def prompt(inputs, ctx):
            return Prompt.user("x")

        client = FakeModelClient(
            responses=[fake_response(json.dumps({"answer": "a"}), tokens=_tokens(output=90))]
        )
        Pipeline(
            [
                Deterministic(observe, node_id="before"),
                LLMNode(prompt, output_schema=Answer),
                Deterministic(observe, node_id="after"),
            ],
            budget=Budget(max_steps=None, max_tokens=1_000, max_cost=None, max_wall_clock_ms=None),
        ).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        assert seen[0] == 1_000
        assert seen[1] == 1_000 - 100  # 10 input + 90 output

    def test_run_budget_exhaustion_stops_the_pipeline(self, envelope, trajectory):
        def prompt(inputs, ctx):
            return Prompt.user("x")

        def plain(inputs, ctx):
            return inputs

        client = FakeModelClient(
            responses=[fake_response(json.dumps({"answer": "a"}), tokens=_tokens(output=200))]
        )
        with pytest.raises(BudgetExceeded) as exc:
            Pipeline(
                [
                    LLMNode(prompt, output_schema=Answer),
                    Deterministic(plain, node_id="never_runs"),
                ],
                budget=Budget(
                    max_steps=None, max_tokens=100, max_cost=None, max_wall_clock_ms=None
                ),
            ).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        assert exc.value.axis == "max_tokens"
        assert "max_tokens" in str(exc.value)
        # The message names the fix, not just the fact.
        assert "None" in str(exc.value)

        kinds = [r.get("node_id") for r in read_trajectory(trajectory)]
        assert "never_runs" not in kinds

    def test_unbounded_axis_never_trips(self):
        budget = Budget.unbounded()
        assert budget.exceeded_by(Spend(steps=10**9, tokens=10**9)) is None

    def test_cost_terminates_the_loop_once_a_figure_exists(self):
        from simple_agents.runtime.budgets import _budget_tripped

        budget = Budget(max_steps=None, max_tokens=None, max_cost=0.01, max_wall_clock_ms=None)

        tripped = _budget_tripped(budget, steps=1, tokens=1, cost=0.02, wall_clock_ms=1)

        assert tripped == "max_cost"

    def test_cost_is_not_checked_when_no_figure_could_be_derived(self):
        """A run with no cost basis derives no cost, and the axis is then not checked.

        A pipeline that sets max_cost without declaring a basis is refused before it runs, so
        this state is reachable only for a budget that left max_cost unset.
        """
        from simple_agents.runtime.budgets import _budget_tripped

        budget = Budget(max_steps=None, max_tokens=None, max_cost=0.01, max_wall_clock_ms=None)

        assert _budget_tripped(budget, steps=1, tokens=1, cost=None, wall_clock_ms=1) is None


class TestToolContract:
    def test_a_tool_cannot_be_registered_without_a_side_effect_class(self):
        from simple_agents import ConfigurationError

        with pytest.raises(ConfigurationError) as exc:
            Tool(
                name="x",
                description="does a thing",
                parameters={},
                side_effect_class="read_only",  # type: ignore[arg-type]
                fn=lambda: None,
            )
        assert "FT-19" in str(exc.value)
        assert "is not READ_ONLY" in str(exc.value)

    def test_a_tool_needs_a_model_facing_description(self):
        from simple_agents import ConfigurationError

        with pytest.raises(ConfigurationError) as exc:
            Tool(
                name="x",
                description="   ",
                parameters={},
                side_effect_class=SideEffectClass.READ_ONLY,
                fn=lambda: None,
            )
        assert "prompt text" in str(exc.value)

    def test_finish_is_a_reserved_tool_name(self):
        from simple_agents import ConfigurationError

        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="finish")
        def impostor() -> str:
            """Pretends to be the termination primitive."""
            return ""

        with pytest.raises(ConfigurationError) as exc:
            AgentNode(_prompt, tools=[impostor], output_schema=Answer, budget=Budget.unbounded())
        assert "reserved" in str(exc.value)

    def test_duplicate_tool_names_are_refused(self):
        from simple_agents import ConfigurationError

        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="dup")
        def a() -> str:
            """One."""
            return ""

        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="dup")
        def b() -> str:
            """Two."""
            return ""

        with pytest.raises(ConfigurationError) as exc:
            AgentNode(_prompt, tools=[a, b], output_schema=Answer, budget=Budget.unbounded())
        assert "ambiguous" in str(exc.value)

    def test_spending_and_irreversible_are_the_classes_that_reach_outside_the_run(self):
        """A write confined to the run's own workspace repeats harmlessly; these do not."""
        for confined in (SideEffectClass.READ_ONLY, SideEffectClass.WRITES):
            assert confined.reaches_outside_the_run is False
        for outside in (SideEffectClass.SPENDS_MONEY, SideEffectClass.IRREVERSIBLE):
            assert outside.reaches_outside_the_run is True


class TestUnknown:
    def test_unknown_serialises_as_a_tagged_object(self, envelope, trajectory):
        """null, "", and absence never mean unknown."""

        def prompt(inputs, ctx):
            return Prompt.user("x")

        client = FakeModelClient(
            responses=[
                fake_response(
                    json.dumps({"answer": {"type": "unknown", "reason": "not published"}})
                )
            ]
        )
        result = Pipeline([LLMNode(prompt, output_schema=Answer)], budget=Budget.unbounded()).run(
            {}, envelope=envelope, run_id=RUN_ID, model=client
        )

        assert result.output.answer.type == "unknown"
        assert result.output.answer.reason == "not published"

        node = next(r for r in read_trajectory(trajectory) if r["record_type"] == "node_execution")
        assert node["outputs"]["answer"] == {"type": "unknown", "reason": "not published"}

    def test_unknown_is_falsy_so_it_is_not_mistaken_for_an_answer(self):
        from simple_agents import Unknown

        assert not Unknown(reason="not there")
        assert Unknown(reason="x").type == "unknown"

    def test_value_or_replaces_absence_and_leaves_every_other_value(self):
        from simple_agents import Unknown, value_or

        assert value_or(Unknown(reason="not published"), 0.0) == 0.0
        assert value_or(32.0, 0.0) == 32.0

    def test_value_or_does_not_treat_an_empty_value_as_absence(self):
        """`None`, `""` and `0` are values, and only `Unknown` says the agent looked."""
        from simple_agents import value_or

        assert value_or(None, "fallback") is None
        assert value_or("", "fallback") == ""
        assert value_or(0, 5) == 0


class TestStepsBindEveryNodeKind:
    """One step is one model call, whichever node kind makes it.

    The axis was charged inside the agent loop while tokens, cost and wall clock were charged
    in the shared call helper, so a pipeline of `LLMNode`s was bounded by three axes and told
    it had four.
    """

    def test_max_steps_stops_a_pipeline_of_llm_nodes(self, envelope, trajectory):
        nodes = [LLMNode(_prompt, output_schema=Answer, node_id=f"n{i}") for i in range(3)]
        client = FakeModelClient(
            responses=[fake_response(content='{"answer": "done"}') for _ in range(3)]
        )
        pipeline = Pipeline(
            nodes,
            budget=Budget(max_steps=2, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        with pytest.raises(BudgetExceeded) as exc:
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client, seed=41)

        assert exc.value.axis == "max_steps"
        # Two calls were made and charged; the third node never ran.
        assert len(client.requests) == 2

    def test_an_agent_node_still_charges_one_step_per_call(self, envelope, trajectory):
        """Moving the charge must not double it, and must not stop charging it."""
        client = FakeModelClient(responses=[fake_response(tool_calls=[_finish()])])
        node = AgentNode(
            _prompt,
            tools=[],
            output_schema=Answer,
            budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
            node_id="ag",
        )
        pipeline = Pipeline(
            [node],
            budget=Budget(max_steps=10, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client, seed=41)
        records = list(read_trajectory(trajectory))
        node_record = next(r for r in records if r["record_type"] == "node_execution")
        assert node_record["termination"] == "finish"
        assert len(client.requests) == 1


class TestDuplicateNodeIds:
    def test_two_nodes_with_the_same_id_are_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            Pipeline(
                [
                    LLMNode(_prompt, output_schema=Answer),
                    LLMNode(_prompt, output_schema=Answer),
                ],
                budget=Budget(
                    max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                ),
            )
        assert "more than one node called _prompt" in str(exc.value)
        assert "node_id=" in str(exc.value)

    def test_a_node_id_with_a_dot_is_refused(self):
        """A pipeline used as a node prefixes its children with its id and a dot, so a dotted
        id at the top level is indistinguishable from a node inside a container."""
        with pytest.raises(ConfigurationError) as exc:
            Pipeline(
                [LLMNode(_prompt, output_schema=Answer, node_id="research.hunt")],
                budget=Budget(
                    max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                ),
            )
        message = str(exc.value)
        assert "node_id contains a dot" in message
        assert "'research_hunt'" in message
        assert "node_id='research'" in message

    def test_the_same_function_twice_is_fine_with_explicit_ids(self):
        pipeline = Pipeline(
            [
                LLMNode(_prompt, output_schema=Answer, node_id="draft"),
                LLMNode(_prompt, output_schema=Answer, node_id="revise"),
            ],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        assert [n.node_id for n in pipeline.nodes] == ["draft", "revise"]


class TestToolTimeIsRunWallClock:
    """A minute a tool spends working binds the same budget a minute of model work does."""

    def _slow_tool(self, seconds: float):
        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="slow_lookup")
        def slow_lookup() -> str:
            """Wait, then answer."""
            time.sleep(seconds)
            return "found"

        return slow_lookup

    def test_an_agents_tool_time_counts_against_the_run_wall_clock(self, envelope) -> None:
        node = AgentNode(
            lambda inputs, ctx: Prompt.user("call the tool"),
            tools=[self._slow_tool(0.08)],
            output_schema=Answer,
            budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
            node_id="agent",
        )
        after = Deterministic(lambda inputs, ctx: inputs, node_id="after")
        pipeline = Pipeline(
            [node, after],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=40),
        )
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c1", name="slow_lookup", arguments={})]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c2", name="finish", arguments={"answer": "found"})
                    ]
                ),
            ]
        )

        with pytest.raises(BudgetExceeded) as caught:
            pipeline.run({}, envelope=envelope, model=client, run_id=RUN_ID)

        assert caught.value.axis == "max_wall_clock"

    def test_a_deterministic_nodes_tool_time_is_charged_once(self, envelope) -> None:
        def read(inputs, ctx):
            return ctx.call_tool("slow_lookup")

        pipeline = Pipeline(
            [
                Deterministic(read, tools=[self._slow_tool(0.06)], node_id="read"),
                Deterministic(lambda inputs, ctx: inputs, node_id="after"),
            ],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=90),
        )

        assert pipeline.run({}, envelope=envelope, run_id=RUN_ID).output == "found"
