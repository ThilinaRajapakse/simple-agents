"""`max_steps` is exact on every path a model call is made from.

One step is one model call, the step is taken before the call, and a call does not start
unless one remains. Three paths reached the backend without consulting the allowance first:
the arms of a branch that were listed as overlapping, the items of a fan-out, and the
embedding and rerank calls inside a search. The reservation now lives where the call is made,
so all three are bounded and so is a chain.
"""

from __future__ import annotations

import json
import threading

import pytest
from pydantic import BaseModel

from simple_agents import (
    AgentNode,
    Budget,
    Deterministic,
    FakeEmbeddingClient,
    FakeRerankClient,
    LLMNode,
    Maybe,
    Pipeline,
)
from simple_agents.budget import BudgetExceeded
from simple_agents.builtins import CrossEncoderRerank, DocumentIndex, document_search
from simple_agents.builtins.ranking import Semantic
from simple_agents.models import FakeModelClient, ToolCallRequest, fake_response

from conftest import run_path

RUN_ID = "run_exact_steps"


class Word(BaseModel):
    word: Maybe[str]


def _steps(limit: int | None) -> Budget:
    return Budget(max_steps=limit, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def _counting_client() -> tuple[FakeModelClient, dict[str, int]]:
    """A client that answers every request and counts what it was asked."""
    made = {"calls": 0}
    lock = threading.Lock()

    def answer(request):
        with lock:
            made["calls"] += 1
        return fake_response('{"word": "x"}')

    return FakeModelClient(answer=answer), made


def _branch(arms: int) -> Pipeline:
    """A node routing to `arms` LLMNodes, all of them declared to overlap."""
    names = [f"a{index}" for index in range(arms)]
    nodes: list = [
        Deterministic(
            lambda i, c: i,
            node_id="plan",
            successors=names,
            route=lambda o, c: names,
        )
    ]
    nodes += [
        LLMNode(lambda i, c: "go", output_schema=Word, node_id=name, successors=["end"])
        for name in names
    ]
    nodes.append(Deterministic(lambda i, c: "end", node_id="end", successors=[]))
    return Pipeline(nodes, budget=_steps(1), concurrent_nodes=[names])


class TestBranchArms:
    """Arms listed in one `concurrent_nodes` group are one batch, and the batch was
    unbounded: the budget was consulted between batches and never inside one."""

    @pytest.mark.parametrize("limit", [1, 3, 5])
    @pytest.mark.parametrize("concurrency", [1, 2, 4, 8])
    def test_eight_arms_make_exactly_max_steps_calls(self, envelope, limit, concurrency):
        pipeline = _branch(8)
        pipeline.budget = _steps(limit)
        client, made = _counting_client()

        with pytest.raises(BudgetExceeded) as stop:
            pipeline.run(
                {},
                envelope=envelope,
                run_id=RUN_ID,
                model=client,
                seed=41,
                concurrency=concurrency,
            )

        assert stop.value.axis == "max_steps"
        assert made["calls"] == limit

    def test_arms_that_fit_all_run(self, envelope):
        """The bound stops arms only where there is nothing left to spend."""
        pipeline = _branch(4)
        pipeline.budget = _steps(8)
        client, made = _counting_client()

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client, seed=41, concurrency=4)

        assert made["calls"] == 4


class TestTheOtherPaths:
    def test_a_chain_is_still_exact(self, envelope):
        nodes = [
            LLMNode(lambda i, c: "go", output_schema=Word, node_id=f"n{index}")
            for index in range(6)
        ]
        client, made = _counting_client()

        with pytest.raises(BudgetExceeded):
            Pipeline(nodes, budget=_steps(3)).run(
                {}, envelope=envelope, run_id=RUN_ID, model=client, seed=41
            )

        assert made["calls"] == 3

    @pytest.mark.parametrize("concurrency", [1, 4])
    def test_a_fan_out_is_still_exact(self, envelope, concurrency):
        node = LLMNode(
            lambda i, c: "go",
            output_schema=Word,
            over="items",
            concurrent_items=4,
            node_id="each",
        )
        client, made = _counting_client()

        with pytest.raises(BudgetExceeded):
            Pipeline([node], budget=_steps(3)).run(
                {"items": list(range(8))},
                envelope=envelope,
                run_id=RUN_ID,
                model=client,
                seed=41,
                concurrency=concurrency,
            )

        assert made["calls"] == 3

    def test_an_agent_node_makes_one_call_per_step(self, envelope):
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="f", name="finish", arguments={"word": "x"})]
                )
            ]
        )
        node = AgentNode(
            lambda i, c: "go",
            tools=[],
            output_schema=Word,
            budget=_steps(4),
            node_id="ag",
        )

        Pipeline([node], budget=_steps(4)).run(
            {}, envelope=envelope, run_id=RUN_ID, model=client, seed=41
        )

        assert len(client.requests) == 1


class TestASearchInsideANode:
    """An embedding and a rerank are model calls, and were charged after the fact. A node
    that searched was therefore unbounded when nothing ran after it."""

    def _index(self) -> DocumentIndex:
        return DocumentIndex.from_texts(
            {f"d{index}": f"document {index} about ashford" for index in range(6)},
            embeddings=FakeEmbeddingClient(),
            ranking=Semantic(),
            rerank=CrossEncoderRerank(FakeRerankClient(), top_n=3),
        )

    def test_a_node_that_searches_is_bounded(self, envelope, tmp_path):
        def go(inputs, ctx):
            for _ in range(4):
                ctx.call_tool("document_search", query="ashford depot")
            return "done"

        pipeline = Pipeline(
            [Deterministic(go, node_id="find", tools=[document_search(self._index(), top_k=2)])],
            budget=Budget(max_steps=1, max_tokens=10, max_cost=None, max_wall_clock_ms=None),
        )

        with pytest.raises(BudgetExceeded) as stop:
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        assert stop.value.axis == "max_steps"
        records = [
            json.loads(line)
            for line in run_path(tmp_path, RUN_ID, "trajectory.jsonl").read_text().splitlines()
        ]
        assert sum(1 for r in records if r["record_type"] == "model_call") == 1

    def test_an_embedding_is_parented_to_the_call_that_made_it(self, envelope, tmp_path):
        """The handles were built from the node's record id, before the tool call had one."""

        def go(inputs, ctx):
            ctx.call_tool("document_search", query="ashford depot")
            ctx.call_tool("document_search", query="depot hours")
            return "done"

        Pipeline(
            [Deterministic(go, node_id="find", tools=[document_search(self._index(), top_k=2)])],
            budget=Budget.unbounded(),
        ).run({}, envelope=envelope, run_id=RUN_ID, seed=41)

        records = [
            json.loads(line)
            for line in run_path(tmp_path, RUN_ID, "trajectory.jsonl").read_text().splitlines()
        ]
        searches = {r["record_id"] for r in records if r.get("tool_name") == "document_search"}
        embeddings = [r for r in records if r["record_type"] == "model_call"]
        assert len(searches) == 2
        assert embeddings
        assert {r["parent_id"] for r in embeddings} == searches
