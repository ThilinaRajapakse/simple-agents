"""A node recording what its own code did to a resource it declared.

A store reached through a tool is a `tool_call` record and is fully accounted for. The same
store reached in a node's own code left `touches=` naming it and nothing else, so what a step
asked for, what came back, and which way the data went were invisible where the same step
reaching it through a tool would have recorded all three.

`ctx.record_access` closes that. The tests here are the contract: the record carries the
access, the resource has to be one the node declared, the direction is one of two words, a
fan-out item is attributed, and the payloads go through the run's redaction and its sampling
the way every other payload does.
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    ConfigurationError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Maybe,
    Pipeline,
    Redaction,
    RunEnvelope,
    Trajectory,
    read_trajectory,
)
from simple_agents.models import ToolCallRequest, fake_response


class Answer(BaseModel):
    text: Maybe[str]


def accesses(records: list[dict]) -> list[dict]:
    return [r for r in records if r["record_type"] == "resource_access"]


def read_all(path) -> list[dict]:
    return list(read_trajectory(path))


class TestWhatTheRecordSays:
    def test_it_records_the_resource_the_direction_and_both_payloads(self, tmp_path) -> None:
        def gather(inputs, ctx):
            ctx.record_access(
                "catalogue",
                "read",
                inputs={"eligible": True},
                outputs={"rows": 67_353, "kept": 12},
            )
            return {"kept": 12}

        pipeline = Pipeline([Deterministic(gather, touches="catalogue")])
        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))

        [record] = accesses(read_all(result.paths.trajectory))
        assert record["node_id"] == "gather"
        assert record["resource"] == "catalogue"
        assert record["direction"] == "read"
        assert record["inputs"] == {"eligible": True}
        assert record["outputs"] == {"rows": 67_353, "kept": 12}
        assert record["item_index"] is None

    def test_it_hangs_under_the_execution_that_made_it(self, tmp_path) -> None:
        def gather(inputs, ctx):
            ctx.record_access("catalogue", "read", outputs={"rows": 4})
            return {}

        result = Pipeline([Deterministic(gather, touches="catalogue")]).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path)
        )
        records = read_all(result.paths.trajectory)
        execution = next(r for r in records if r["record_type"] == "node_execution")

        assert accesses(records)[0]["parent_id"] == execution["record_id"]

    def test_a_step_that_reads_and_writes_records_one_each_way(self, tmp_path) -> None:
        def sync(inputs, ctx):
            ctx.record_access("inbox", "read", outputs={"messages": 9})
            ctx.record_access("inbox", "write", inputs={"archived": 9})
            return {}

        result = Pipeline([Deterministic(sync, touches="inbox")]).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path)
        )

        assert [r["direction"] for r in accesses(read_all(result.paths.trajectory))] == [
            "read",
            "write",
        ]

    def test_the_manifest_counts_them(self, tmp_path) -> None:
        def gather(inputs, ctx):
            ctx.record_access("catalogue", "read", outputs={"rows": 2})
            return {}

        result = Pipeline([Deterministic(gather, touches="catalogue")]).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path)
        )
        manifest = json.loads(result.paths.manifest.read_text())

        assert manifest["counts"]["resource_access"] == 1


class TestTheDeclarationAndTheRecordNameTheSameThing:
    def test_an_undeclared_resource_is_refused_and_names_what_to_declare(self, tmp_path):
        def gather(inputs, ctx):
            ctx.record_access("catalogue", "read", outputs={"rows": 1})
            return {}

        pipeline = Pipeline([Deterministic(gather, touches="handbook")])
        with pytest.raises(ConfigurationError) as caught:
            pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))

        message = str(caught.value)
        assert "'catalogue'" in message and "handbook" in message
        assert "touches='catalogue'" in message

    def test_a_node_declaring_nothing_says_so(self, tmp_path) -> None:
        def gather(inputs, ctx):
            ctx.record_access("catalogue", "read", outputs={"rows": 1})
            return {}

        with pytest.raises(ConfigurationError) as caught:
            Pipeline([Deterministic(gather)]).run({}, envelope=RunEnvelope(run_dir=tmp_path))

        assert "declares nothing" in str(caught.value)

    def test_a_direction_that_is_neither_word_is_refused(self, tmp_path) -> None:
        def gather(inputs, ctx):
            ctx.record_access("catalogue", "fetch", outputs={"rows": 1})
            return {}

        pipeline = Pipeline([Deterministic(gather, touches="catalogue")])
        with pytest.raises(ConfigurationError) as caught:
            pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))

        assert "'read' and 'write'" in str(caught.value)

    def test_a_context_outside_a_run_says_it_records_nothing(self) -> None:
        from simple_agents import NodeContext

        ctx = NodeContext(
            run_id="r",
            node_id="gather",
            workspace=None,
            seed=None,
            budget=Budget(max_steps=1, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        with pytest.raises(ConfigurationError) as caught:
            ctx.record_access("catalogue", "read")

        assert "records nothing" in str(caught.value)


class TestEveryNodeKindCanRecord:
    def test_an_llm_node_records_from_its_prompt_function(self, tmp_path) -> None:
        def build(inputs, ctx):
            ctx.record_access("handbook", "read", outputs={"passages": 3})
            return Prompt.user("say something")

        node = LLMNode(build, output_schema=Answer, node_id="ask", touches="handbook")
        result = Pipeline([node], budget=Budget.unbounded()).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(responses=[fake_response(content='{"text": "hello"}')]),
        )

        assert [r["resource"] for r in accesses(read_all(result.paths.trajectory))] == ["handbook"]

    def test_an_agent_node_records_from_its_prompt_function(self, tmp_path) -> None:
        def build(inputs, ctx):
            ctx.record_access("handbook", "read", outputs={"passages": 3})
            return Prompt.user("say something")

        node = AgentNode(
            build,
            output_schema=Answer,
            node_id="decide",
            touches="handbook",
            tools=[],
            budget=Budget(max_steps=2, max_tokens=1000, max_cost=None, max_wall_clock_ms=None),
        )
        model = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c1", name="finish", arguments={"text": "hello"})
                    ]
                )
            ]
        )
        result = Pipeline([node], budget=Budget.unbounded()).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=model
        )

        assert [r["node_id"] for r in accesses(read_all(result.paths.trajectory))] == ["decide"]


class TestAFanOutItemIsAttributed:
    def test_each_item_records_its_own_index(self, tmp_path) -> None:
        def one(inputs, ctx):
            ctx.record_access("catalogue", "read", outputs={"rows": inputs})
            return inputs

        node = Deterministic(one, node_id="each", over="items", touches="catalogue")
        result = Pipeline([node]).run({"items": [1, 2, 3]}, envelope=RunEnvelope(run_dir=tmp_path))

        found = accesses(read_all(result.paths.trajectory))
        assert sorted(r["item_index"] for r in found) == [0, 1, 2]


class TestThePayloadsFollowTheRunsRules:
    def test_a_declared_pattern_is_redacted(self, tmp_path) -> None:
        def gather(inputs, ctx):
            ctx.record_access("catalogue", "read", inputs={"token": "sk-live-abcdefghijklmnop"})
            return {}

        result = Pipeline([Deterministic(gather, touches="catalogue")]).run(
            {},
            envelope=RunEnvelope(
                run_dir=tmp_path, redaction=Redaction(patterns={"key": r"sk-live-\w+"})
            ),
        )

        [record] = accesses(read_all(result.paths.trajectory))
        assert "sk-live-abcdefghijklmnop" not in json.dumps(record["inputs"])
        assert record["redactions"]

    def test_sampling_drops_both_payloads_and_keeps_the_access(self, tmp_path) -> None:
        def gather(inputs, ctx):
            ctx.record_access("catalogue", "read", inputs={"q": "x"}, outputs={"rows": 4})
            return {}

        result = Pipeline([Deterministic(gather, touches="catalogue")]).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path, trajectory=Trajectory(rate=0.0))
        )

        [record] = accesses(read_all(result.paths.trajectory))
        assert record["resource"] == "catalogue"
        assert record["direction"] == "read"
        assert sorted(record["omissions"]) == ["inputs", "outputs"]


class TestItReachesThePerNodeFigures:
    def test_reads_and_writes_are_counted_by_resource(self, tmp_path) -> None:
        from simple_agents.evaluation.per_node import per_node

        def sync(inputs, ctx):
            ctx.record_access("inbox", "read", outputs={"messages": 2})
            ctx.record_access("inbox", "write", inputs={"archived": 2})
            ctx.record_access("inbox", "write", inputs={"archived": 1})
            return {}

        result = Pipeline([Deterministic(sync, touches="inbox")]).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path)
        )
        found = per_node([read_all(result.paths.trajectory)])

        assert found["sync"].resource_reads == {"inbox": 1}
        assert found["sync"].resource_writes == {"inbox": 2}
