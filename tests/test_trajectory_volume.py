"""What a run keeps, and what it drops, when the envelope samples its payloads.

`docs/run-envelope.md` §7 is the behaviour of record and `docs/trajectory-format.md` §5.4 the
encoding. Two things are under test that are easy to get right in isolation and wrong
together: that everything derived from a trajectory stays correct when the payloads go, and
that a dropped payload never reads as a value the agent produced.
"""

from __future__ import annotations

import json

import pytest

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    Cassette,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Pipeline,
    RunEnvelope,
    RunSuspended,
    SideEffectClass,
    Suspend,
    tool,
    ToolRegistry,
    Trajectory,
    read_trajectory,
)
from simple_agents.errors import ConfigurationError
from simple_agents.evaluation.per_node import per_node
from simple_agents.models import ToolCallRequest, fake_response

from conftest import run_path, RUN_ID
from schemas import Answer

# -----------------------------------------------------------------------------------------


def load_docs(inputs, ctx):
    return {"docs": "the inseam is 32 inches", "question": inputs["question"]}


def ask(inputs, ctx):
    return Prompt.user("{docs}\n\nQ: {question}", docs=inputs["docs"], question=inputs["question"])


def explode(inputs, ctx):
    raise RuntimeError("the node itself failed")


def two_node_pipeline() -> Pipeline:
    return Pipeline(
        [Deterministic(load_docs), LLMNode(ask, output_schema=Answer)],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=300_000),
    )


def run_with(envelope, *, run_id=RUN_ID, pipeline=None, answer="32 inches"):
    client = FakeModelClient(responses=[fake_response(content=json.dumps({"answer": answer}))])
    return (pipeline or two_node_pipeline()).run(
        {"question": "what is the inseam?"},
        envelope=envelope,
        run_id=run_id,
        model=client,
        seed=41,
    )


def records_of(result):
    return list(read_trajectory(result.paths.trajectory))


def manifest_of(result):
    return json.loads(result.paths.manifest.read_text())


class TestTheRate:
    """`Trajectory` on its own, before any run."""

    def test_the_envelope_keeps_every_payload_by_default(self):
        assert RunEnvelope().trajectory == Trajectory.full()
        assert RunEnvelope().trajectory.keeps("any run at all")

    def test_a_rate_of_zero_keeps_nothing_and_a_rate_of_one_keeps_everything(self):
        assert Trajectory.sampled(0.0).keeps("run_1") is False
        assert Trajectory.sampled(1.0).keeps("run_1") is True

    def test_the_same_run_id_always_gets_the_same_answer(self):
        sampler = Trajectory.sampled(0.5)
        assert [sampler.keeps("run_7") for _ in range(5)] == [sampler.keeps("run_7")] * 5

    def test_the_share_of_runs_kept_is_the_rate(self):
        """Over ten thousand run ids, within a percentage point of the rate asked for."""
        sampler = Trajectory.sampled(0.1)
        kept = sum(sampler.keeps(f"run_{n:012x}") for n in range(10_000))
        assert 0.09 < kept / 10_000 < 0.11

    @pytest.mark.parametrize("rate", [-0.1, 1.5, 2])
    def test_a_rate_outside_zero_to_one_is_refused(self, rate):
        with pytest.raises(ConfigurationError, match="outside 0 to 1"):
            Trajectory.sampled(rate)

    def test_something_that_is_not_a_number_is_refused(self):
        with pytest.raises(ConfigurationError, match="takes a number"):
            Trajectory(rate="0.01")  # type: ignore[arg-type]

    def test_the_envelope_refuses_anything_that_is_not_a_trajectory(self):
        with pytest.raises(ConfigurationError, match="takes a Trajectory"):
            RunEnvelope(trajectory=0.01)  # type: ignore[arg-type]

    def test_a_copy_of_the_envelope_carries_the_rate(self, tmp_path):
        env = RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.01))
        assert env.with_run_dir(tmp_path).trajectory == Trajectory.sampled(0.01)
        assert env.with_cassette(Cassette.off()).trajectory == Trajectory.sampled(0.01)
        assert env.with_trajectory(Trajectory.full()).trajectory == Trajectory.full()


class TestWhatARunKeeps:
    def test_at_the_full_rate_every_payload_is_there_and_nothing_is_omitted(self, tmp_path):
        result = run_with(RunEnvelope(run_dir=tmp_path))

        for record in records_of(result):
            assert record["omissions"] == []
        assert manifest_of(result)["recording"] == {"payload_rate": 1.0, "payloads": "kept"}

    def test_at_rate_zero_every_payload_is_replaced_and_named(self, tmp_path):
        result = run_with(RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.0)))

        for record in records_of(result):
            assert record["inputs"] == {"type": "not_recorded", "reason": "sampling"}
            assert "inputs" in record["omissions"]
            # `run_start` holds inputs and no outputs, so only what a record has is checked.
            if "outputs" in record:
                assert record["outputs"] == {"type": "not_recorded", "reason": "sampling"}
                assert "outputs" in record["omissions"]

    def test_the_manifest_says_the_rate_and_what_this_run_did(self, tmp_path):
        result = run_with(RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.0)))

        assert manifest_of(result)["recording"] == {
            "payload_rate": 0.0,
            "payloads": "omitted",
            "reason": "sampling",
        }

    def test_a_run_the_rate_selected_keeps_its_payloads(self, tmp_path):
        """A rate of 1 in 2 over enough run ids keeps some runs whole and strips others."""
        env = RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.5))
        outcomes = set()
        for n in range(12):
            result = run_with(env, run_id=f"run_{n}")
            node = [r for r in records_of(result) if r["record_type"] == "node_execution"][0]
            outcomes.add(node["omissions"] == [])
        assert outcomes == {True, False}

    def test_a_payload_that_was_already_null_stays_null(self, tmp_path):
        """`outputs: null` says a node produced nothing, which a dropped payload does not.

        A skipped node is the shape that produces one on a run that completed, and a completed
        run is the only kind whose payloads are dropped.
        """
        pipeline = Pipeline(
            [
                Deterministic(
                    load_docs,
                    node_id="load",
                    successors=["taken", "dropped"],
                    route=lambda output, ctx: "taken",
                ),
                Deterministic(
                    lambda inputs, ctx: {"went": "left"}, node_id="taken", successors=["report"]
                ),
                Deterministic(
                    lambda inputs, ctx: {"went": "right"}, node_id="dropped", successors=["report"]
                ),
                Deterministic(lambda inputs, ctx: {"done": True}, node_id="report", successors=[]),
            ],
            budget=Budget.unbounded(),
        )
        env = RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.0))
        result = run_with(env, pipeline=pipeline)

        records = {
            r["node_id"]: r for r in records_of(result) if r["record_type"] == "node_execution"
        }
        assert records["dropped"]["termination"] == "skipped"
        assert records["dropped"]["outputs"] is None
        assert records["dropped"]["omissions"] == ["inputs"]
        assert records["taken"]["omissions"] == ["inputs", "outputs"]


class TestARunWorthReadingKeepsItsPayloads:
    def test_a_run_that_errored_keeps_them_at_rate_zero(self, tmp_path):
        pipeline = Pipeline(
            [Deterministic(load_docs), Deterministic(explode, node_id="boom")],
            budget=Budget.unbounded(),
        )
        env = RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.0))
        with pytest.raises(RuntimeError):
            run_with(env, pipeline=pipeline)

        records = list(read_trajectory(run_path(tmp_path, RUN_ID, "trajectory.jsonl")))
        first = [
            r
            for r in records
            if r["record_type"] == "node_execution" and r.get("node_id") != "boom"
        ][0]
        assert first["outputs"] == {
            "docs": "the inseam is 32 inches",
            "question": "what is the inseam?",
        }
        assert first["omissions"] == []
        manifest = json.loads((run_path(tmp_path, RUN_ID, "manifest.json")).read_text())
        assert manifest["outcome"] == "error"
        assert manifest["recording"]["payloads"] == "kept"

    def test_a_suspended_run_keeps_them_at_rate_zero(self, tmp_path):
        def wait(inputs, ctx):
            raise Suspend(waiting_for="the size")

        pipeline = Pipeline([Deterministic(wait, node_id="wait")], budget=Budget.unbounded())
        env = RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.0))
        with pytest.raises(RunSuspended):
            pipeline.run({"question": "how long"}, envelope=env, run_id=RUN_ID)

        records = list(read_trajectory(run_path(tmp_path, RUN_ID, "trajectory.jsonl")))
        assert [r["omissions"] for r in records] == [[] for _ in records]
        assert records[0]["inputs"] == {"question": "how long"}


class TestWhatSurvivesTheDrop:
    """Everything derived from a trajectory is derived from fields the rate does not touch."""

    @pytest.fixture
    def both(self, tmp_path):
        whole = run_with(RunEnvelope(run_dir=tmp_path / "whole"), run_id="r")
        sampled = run_with(
            RunEnvelope(run_dir=tmp_path / "sampled", trajectory=Trajectory.sampled(0.0)),
            run_id="r",
        )
        return whole, sampled

    def test_the_manifest_counts_and_totals_are_the_same(self, both):
        whole, sampled = both
        for key in ("counts", "totals", "seed", "budget", "outcome"):
            assert manifest_of(whole)[key] == manifest_of(sampled)[key]

    def test_every_field_but_the_payloads_is_the_same(self, both):
        whole, sampled = both
        untouched = {
            "inputs",
            "outputs",
            "omissions",
            "started_at",
            "ended_at",
            "record_id",
            "parent_id",
            "cassette_key",
        }
        for left, right in zip(records_of(whole), records_of(sampled)):
            for field in set(left) - untouched:
                assert left[field] == right[field], field

    def test_per_node_metrics_read_the_same_numbers(self, both):
        whole, sampled = both
        one = per_node([records_of(whole)])
        two = per_node([records_of(sampled)])
        assert set(one) == set(two)
        for node_id, metrics in one.items():
            assert metrics.executions == two[node_id].executions
            assert metrics.model_calls == two[node_id].model_calls
            assert metrics.tokens == two[node_id].tokens
            assert metrics.terminations == two[node_id].terminations

    def test_a_dropped_payload_does_not_count_as_an_absence(self, tmp_path):
        """The regression this encoding exists to prevent.

        `{"type": "unknown"}` is what a node reports when it did not find the value, and
        `absent_outputs` counts it. A payload dropped by sampling is a different statement and
        must not be counted as one.
        """
        whole = run_with(RunEnvelope(run_dir=tmp_path / "whole"), run_id="r")
        sampled = run_with(
            RunEnvelope(run_dir=tmp_path / "sampled", trajectory=Trajectory.sampled(0.0)),
            run_id="r",
        )
        assert per_node([records_of(whole)])["ask"].absent_outputs == 0
        assert per_node([records_of(sampled)])["ask"].absent_outputs == 0

    def test_a_node_that_did_report_an_absence_is_still_counted(self, tmp_path):
        result = run_with(
            RunEnvelope(run_dir=tmp_path),
            answer={"type": "unknown", "reason": "the documents do not say"},
        )
        assert per_node([records_of(result)])["ask"].absent_outputs == 1


class TestTheSchemaReference:
    @pytest.fixture
    def agent_run(self, tmp_path):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def search(query: str) -> str:
            """Search the catalogue. Returns matching entries."""
            return "the inseam is 32 inches"

        registry = ToolRegistry([search])
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c1", name="search", arguments={"query": "inseam"})
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c2", name="finish", arguments={"answer": "32 inches"})
                    ]
                ),
            ]
        )
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: Prompt.user("go"),
                    tools=registry,
                    output_schema=Answer,
                    node_id="hunt",
                    budget=Budget(
                        max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=30_000
                    ),
                )
            ],
            budget=Budget.unbounded(),
        )
        result = pipeline.run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID, model=client, seed=41
        )
        return result

    def test_a_record_carries_a_reference_and_the_manifest_carries_the_block(self, agent_run):
        calls = [r for r in records_of(agent_run) if r["record_type"] == "model_call"]
        schemas = manifest_of(agent_run)["schemas"]

        assert calls
        for call in calls:
            assert "tools" not in call["params"]
            assert call["params"]["tools_ref"] in schemas
        offered = schemas[calls[0]["params"]["tools_ref"]]
        assert {t["name"] for t in offered} == {"search", "finish"}

    def test_one_block_is_stored_once_however_many_calls_offered_it(self, agent_run):
        calls = [r for r in records_of(agent_run) if r["record_type"] == "model_call"]
        refs = {c["params"]["tools_ref"] for c in calls}

        assert len(calls) > 1
        assert len(refs) == 1
        assert len(manifest_of(agent_run)["schemas"]) == len(
            {c["params"]["tools_ref"] for c in calls}
            | {c["params"]["output_schema_ref"] for c in calls if c["params"]["output_schema_ref"]}
        )

    def test_a_call_offering_neither_records_null_for_both(self, tmp_path):
        result = run_with(RunEnvelope(run_dir=tmp_path))
        call = [r for r in records_of(result) if r["record_type"] == "model_call"][0]

        assert call["params"]["tools_ref"] is None
        assert call["params"]["output_schema_ref"] is not None

    def test_two_nodes_offering_different_tools_carry_different_references(self, tmp_path):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def one(query: str) -> str:
            """Tool one. Returns text."""
            return "a"

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def two(query: str) -> str:
            """Tool two. Returns text."""
            return "b"

        def agent(name, offered):
            return AgentNode(
                lambda inputs, ctx: Prompt.user("go"),
                tools=ToolRegistry([offered]),
                output_schema=Answer,
                node_id=name,
                budget=Budget(
                    max_steps=2, max_tokens=10_000, max_cost=None, max_wall_clock_ms=30_000
                ),
            )

        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="a", name="finish", arguments={"answer": "x"})]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="b", name="finish", arguments={"answer": "y"})]
                ),
            ]
        )
        pipeline = Pipeline([agent("first", one), agent("second", two)], budget=Budget.unbounded())
        result = pipeline.run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID, model=client, seed=41
        )

        refs = [
            r["params"]["tools_ref"] for r in records_of(result) if r["record_type"] == "model_call"
        ]
        assert len(set(refs)) == 2
        assert set(refs) <= set(manifest_of(result)["schemas"])


class TestTheCassetteIsUnaffected:
    """The reference is a record shape. The key still hashes the declarations in full."""

    def test_a_recording_made_now_replays_into_a_run_that_reads_references(self, tmp_path):
        path = tmp_path / "cassette.jsonl"
        recorded = run_with(
            RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(path)),
            run_id="rec",
        )
        replayed = run_with(
            RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(path)),
            run_id="rep",
        )

        assert recorded.output.answer == replayed.output.answer
        assert manifest_of(replayed)["cassette"]["hits"] == 1
        assert manifest_of(replayed)["cassette"]["misses"] == 0

    def test_the_stored_request_keeps_the_declarations_in_full(self, tmp_path):
        path = tmp_path / "cassette.jsonl"
        run_with(
            RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(path)),
            run_id="rec",
        )
        entries = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

        params = entries[0]["request"]["params"]
        assert "tools" in params and "output_schema" in params
        assert "tools_ref" not in params


class TestConsultationRecords:
    """A consultation has no `inputs` and no `outputs`. Its payload is `response`."""

    def test_the_end_user_s_answer_is_dropped_and_the_question_is_not(self, tmp_path):
        from simple_agents.builtins import consult

        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c1", name="consult", arguments={"question": "which size?"}
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="c2", name="finish", arguments={"answer": "32 inches"})
                    ]
                ),
            ]
        )
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: Prompt.user("go"),
                    tools=ToolRegistry(
                        [
                            consult(
                                lambda question, options, about=None: "slim", answered_by="end_user"
                            )
                        ]
                    ),
                    output_schema=Answer,
                    node_id="hunt",
                    budget=Budget(
                        max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=30_000
                    ),
                )
            ],
            budget=Budget.unbounded(),
        )
        result = pipeline.run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.0)),
            run_id=RUN_ID,
            model=client,
            seed=41,
        )

        consultations = [r for r in records_of(result) if r["record_type"] == "consultation"]
        assert consultations
        for record in consultations:
            assert record["response"] == {"type": "not_recorded", "reason": "sampling"}
            assert record["omissions"] == ["response"]
            assert record["prompt"] == "which size?"
            assert record["resolution"] == "answered"


class TestTheProviderBlock:
    def test_a_header_already_parsed_into_rate_limit_is_not_recorded_twice(self):
        from simple_agents.adapters.mistral import RATE_LIMIT_HEADERS, _passthrough

        headers = {
            "x-ratelimit-remaining-req-minute": "48",
            "x-ratelimit-remaining-tokens-minute": "49348",
            "x-ratelimit-limit-tokens-minute": "500000",
            "x-request-id": "req_9f2c",
        }

        kept = _passthrough(headers)

        assert set(kept) == {"x-ratelimit-limit-tokens-minute", "x-request-id"}
        assert set(RATE_LIMIT_HEADERS).isdisjoint(kept)


class TestAnEvaluationRefusesASampledEnvelope:
    """Per-node accuracy and `absent_outputs` are read back out of each rollout's trajectory."""

    @pytest.fixture
    def suite(self):
        from simple_agents.evaluation import EvalSuite, Example, ExampleSet

        return EvalSuite(
            two_node_pipeline(),
            ExampleSet(
                [
                    Example(
                        id="e1",
                        inputs={"question": "what is the inseam?"},
                        expected="32 inches",
                        split="held_out",
                    )
                ]
            ),
            answer="answer",
            matches=lambda s: str(s.answer) == s.expected,
        )

    def test_it_refuses_before_any_rollout_runs(self, suite, tmp_path):
        env = RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.01))

        with pytest.raises(ConfigurationError, match="Trajectory.sampled"):
            suite.run(envelope=env, model=FakeModelClient(responses=[]), split="held_out", k=1)

        assert not list(tmp_path.glob("eval_*"))

    def test_the_message_names_the_envelope_that_would_work(self, suite, tmp_path):
        env = RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.01))

        with pytest.raises(ConfigurationError) as raised:
            suite.run(envelope=env, model=FakeModelClient(responses=[]), split="held_out", k=1)

        assert "with_trajectory(Trajectory.full())" in str(raised.value)

    def test_the_full_rate_runs(self, suite, tmp_path):
        env = RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.01))
        client = FakeModelClient(
            responses=[fake_response(content=json.dumps({"answer": "32 inches"}))]
        )

        results = suite.run(
            envelope=env.with_trajectory(Trajectory.full()),
            model=client,
            split="held_out",
            k=1,
            seed=41,
        )

        assert len(results.rollouts) == 1
