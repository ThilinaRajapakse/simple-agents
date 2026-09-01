"""The node kind is a promise the library keeps, not a label the builder applies.

This is the structural half of FT-11. A `Deterministic` node's function cannot make a model
call because it is never handed anything that can make one, not because the docs discourage
it. If these tests fail, `node_kind` has become a field that can lie, and per-node metrics,
FT-11 and the ablation machinery are all reading it.

One model call is recorded under this node kind and is not the function's: the reader a
consultation registers with `consult(read=...)`. `test_consultation_reading.py` covers it, and
`ctx` still carries no client either way.
"""

from __future__ import annotations

import json

import pytest

from simple_agents import (
    AgentNode,
    Budget,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Pipeline,
    read_trajectory,
)
from simple_agents.context import AgentContext, NodeContext
from simple_agents.models import ToolCallRequest, fake_response

from schemas import Answer
from conftest import RUN_ID


class TestDeterministicHasNoModelAccess:
    def test_context_exposes_no_model_client(self, envelope, trajectory):
        seen: list[NodeContext] = []

        def capture(inputs, ctx):
            seen.append(ctx)
            return inputs

        Pipeline([Deterministic(capture)]).run({}, envelope=envelope, run_id=RUN_ID)

        ctx = seen[0]
        for forbidden in ("model", "client", "complete", "tools", "call_model"):
            assert not hasattr(ctx, forbidden), (
                f"a Deterministic node's context exposes {forbidden!r}, so the node kind can "
                f"now lie about what it did"
            )

    def test_context_is_frozen(self, envelope, trajectory):
        """A node cannot smuggle a client onto its own context and call it later."""
        seen: list[NodeContext] = []

        def capture(inputs, ctx):
            seen.append(ctx)
            return inputs

        Pipeline([Deterministic(capture)]).run({}, envelope=envelope, run_id=RUN_ID)
        with pytest.raises(AttributeError):
            seen[0].model = object()  # type: ignore[attr-defined]

    def test_deterministic_emits_no_model_call_records(self, envelope, trajectory):
        def work(inputs, ctx):
            return {"doubled": inputs["n"] * 2}

        Pipeline([Deterministic(work)]).run({"n": 21}, envelope=envelope, run_id=RUN_ID)
        records = list(read_trajectory(trajectory))
        assert [r["record_type"] for r in records] == ["run_start", "node_execution"]
        assert records[0]["inputs"] == {"n": 21}
        assert records[1]["outputs"] == {"doubled": 42}


class TestLLMNodeMakesExactlyOneCall:
    """ "One call, one place, one output shape" has to be true, not aspirational.

    The builder supplies a prompt builder, so there is no code path in which their function
    could issue a second call.
    """

    def test_prompt_function_receives_no_model_client(self, envelope, trajectory):
        seen: list[NodeContext] = []

        def prompt(inputs, ctx):
            seen.append(ctx)
            return "hello"

        client = FakeModelClient(responses=[fake_response(json.dumps({"answer": "hi"}))])
        Pipeline([LLMNode(prompt, output_schema=Answer)], budget=Budget.unbounded()).run(
            {}, envelope=envelope, run_id=RUN_ID, model=client
        )

        for forbidden in ("model", "client", "complete", "tools"):
            assert not hasattr(seen[0], forbidden)

    def test_exactly_one_model_call_is_emitted(self, envelope, trajectory):
        def prompt(inputs, ctx):
            return "hello"

        client = FakeModelClient(responses=[fake_response(json.dumps({"answer": "hi"}))])
        Pipeline([LLMNode(prompt, output_schema=Answer)], budget=Budget.unbounded()).run(
            {}, envelope=envelope, run_id=RUN_ID, model=client
        )

        records = list(read_trajectory(trajectory))
        assert sum(1 for r in records if r["record_type"] == "model_call") == 1
        # And the client was asked exactly once, not once-per-retry.
        assert len(client.requests) == 1


class TestAgentNodeIsTheOnlyLoop:
    def test_agent_context_still_hides_the_client(self, envelope, trajectory):
        """The loop is the library's. The prompt function only describes the tools."""
        seen: list[AgentContext] = []

        def prompt(inputs, ctx):
            seen.append(ctx)
            return "go"

        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c1", name="finish", arguments={"answer": "x", "source": None}
                        )
                    ]
                )
            ]
        )
        Pipeline(
            [AgentNode(prompt, tools=[], output_schema=Answer, budget=Budget.unbounded())],
            budget=Budget.unbounded(),
        ).run({}, envelope=envelope, run_id=RUN_ID, model=client)

        ctx = seen[0]
        assert isinstance(ctx, AgentContext)
        for forbidden in ("model", "client", "complete"):
            assert not hasattr(ctx, forbidden)
        # It does get to know tool *names*, so a prompt can describe them.
        assert ctx.describe_tools() == "(none)"


class TestAgencyBoundaryIsCountable:
    def test_pipeline_reports_its_node_kinds(self):
        """What FT-11 reads: an all-agent pipeline skipped the question rather than answering it."""

        def prompt(inputs, ctx):
            return "x"

        def plain(inputs, ctx):
            return inputs

        pipeline = Pipeline(
            [
                Deterministic(plain),
                Deterministic(plain, node_id="second"),
                LLMNode(prompt, output_schema=Answer),
                AgentNode(
                    prompt,
                    tools=[],
                    output_schema=Answer,
                    budget=Budget.unbounded(),
                    node_id="hunt",
                ),
            ],
            budget=Budget.unbounded(),
        )
        assert pipeline.node_kinds == {"deterministic": 2, "llm": 1, "agent": 1}
