"""Does what we emit actually satisfy `docs/trajectory-format.md`?

This is the first real test of the format against code. The field lists below are transcribed
from `docs/trajectory-format.md`. Every section reference below is to that document. If a
list here and the document disagree, the document is right and this file has drifted.

**Each of the four record types is compared as a symmetric difference**, so a field the
document names and the writer dropped fails, and so does a field the writer added and the
document does not name. One direction alone would let a new field ship undocumented, which is
how `route` and `loop` reached a released record type unnamed at item 8c.

The format is pre-adoption. If building against it reveals a field that is wrong or missing,
the correct response is to change the format and bump the version, not to work around it
here.
"""

from __future__ import annotations

import json

import pytest

from simple_agents.errors import CallerFacingError

from simple_agents import (
    AgentNode,
    Budget,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Pipeline,
    RunSuspended,
    SideEffectClass,
    Suspend,
    Tool,
    ToolRegistry,
    read_trajectory,
)
from simple_agents.builtins import consult
from simple_agents.models import ToolCallRequest, fake_response

from schemas import Answer
from conftest import RUN_ID

# --- transcribed from docs/trajectory-format.md ------------------------------------------

COMMON_FIELDS = {  # §2
    "format_version",
    "record_type",
    "record_id",
    "run_id",
    "parent_id",
    "sequence",
    "started_at",
    "ended_at",
    "error",
    "redactions",
    "omissions",
}

NODE_FIELDS = {  # §3
    "node_id",
    "node_kind",
    "inputs",
    "outputs",
    "seed",
    "budget",
    "termination",
    "route",
    "loop",
    "resumed_from",
}

MODEL_CALL_FIELDS = {  # §4.1
    "item_index",
    "backend",
    "request_model",
    "model_revision",
    "response_model",
    "params",
    "seed",
    "inputs",
    "outputs",
    "finish_reason",
    "tokens",
    "concurrent_requests",
    "replayed",
    "cassette_key",
    "context",
    "recorded_duration_ms",
    "held_back_ms",
    "rate_limit",
    "provider",
    "stream",
}

TOOL_CALL_FIELDS = {  # §4.2
    "tool_name",
    "tool_version",
    "side_effect_class",
    "inputs",
    "outputs",
    "replayed",
    "re_executed",
    "cassette_key",
    "declared_cost",
    "spent",
    "item_index",
}

BUDGET_KEYS = {"max_steps", "max_tokens", "max_cost", "max_wall_clock_ms"}  # §3.1
CONSULTATION_FIELDS = {  # §4.3
    "prompt",
    "options",
    "about",
    "asked",
    "answered_at",
    "response",
    "chose",
    "declared_choice",
    "read_by",
    "reaches",
    "resolution",
    "answered_by",
    "reason",
    "answered_by_model",
    "blocking",
    "answers",
    "answers_run_id",
    "item_index",
}

TOKEN_KEYS = {  # §4.1.2
    "input_uncached",
    "input_cache_read",
    "input_cache_write",
    "cache_ttl",
    "output",
}

# -----------------------------------------------------------------------------------------


def load_docs(inputs, ctx):
    return {"docs": "the inseam is 32 inches", "question": inputs["question"]}


def ask(inputs, ctx):
    return f"{inputs['docs']}\n\nQ: {inputs['question']}"


def question(inputs, ctx):
    """A prompt that needs nothing but the question, for runs that fail at the call."""
    return inputs["question"]


def explode(inputs, ctx):
    raise RuntimeError("the node itself failed")


class ExplodingClient(FakeModelClient):
    """Fails the way a backend does: after the request was built, before a response."""

    def complete(self, request):
        self.requests.append(request)
        raise RuntimeError("503 Service Unavailable")


@pytest.fixture
def two_node_run(envelope, trajectory):
    client = FakeModelClient(responses=[fake_response(content=json.dumps({"answer": "32 inches"}))])
    pipeline = Pipeline(
        [Deterministic(load_docs), LLMNode(ask, output_schema=Answer)],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=300_000),
    )
    result = pipeline.run(
        {"question": "what is the inseam?"},
        envelope=envelope,
        run_id=RUN_ID,
        model=client,
        seed=41,
    )
    return result, list(read_trajectory(trajectory))


class TestCommonFields:
    def test_every_record_carries_every_common_field(self, two_node_run):
        _, records = two_node_run
        assert records, "the run produced no records at all"
        for record in records:
            missing = COMMON_FIELDS - record.keys()
            assert not missing, f"{record['record_type']} record missing {sorted(missing)}"

    def test_format_version_is_declared_on_every_record(self, two_node_run):
        _, records = two_node_run
        # §2: present on every record so a single line is interpretable in isolation.
        assert {r["format_version"] for r in records} == {"0.29"}

    def test_seq_is_monotonic_in_emission_order(self, two_node_run):
        _, records = two_node_run
        sequences = [r["sequence"] for r in records]
        assert sequences == sorted(sequences), f"sequence not monotonic: {sequences}"
        assert len(set(sequences)) == len(sequences), f"sequence values repeat: {sequences}"

    def test_timestamps_are_utc_iso8601_with_milliseconds(self, two_node_run):
        _, records = two_node_run
        for record in records:
            assert record["started_at"].endswith("Z"), record["started_at"]
            # ISO 8601, millisecond precision: ...THH:MM:SS.mmmZ
            assert len(record["started_at"].split(".")[-1]) == 4, record["started_at"]

    def test_redactions_array_is_present_and_empty(self, two_node_run):
        """§5.3: an empty array positively claims nothing was altered.

        An absent array would be ambiguous between that and "this writer does not redact",
        which is the distinction the field exists to make.
        """
        _, records = two_node_run
        for record in records:
            assert record["redactions"] == []


class TestNodeRecords:
    def test_node_records_have_their_type_specific_fields(self, two_node_run):
        _, records = two_node_run
        nodes = [r for r in records if r["record_type"] == "node_execution"]
        assert len(nodes) == 2
        for record in nodes:
            # Symmetric, so a field the document names and the writer dropped fails, and so
            # does a field the writer added and the document does not name.
            drifted = NODE_FIELDS ^ (record.keys() - COMMON_FIELDS)
            assert not drifted, (
                f"§3 and the writer disagree about {sorted(drifted)}: one of them has a field "
                f"the other does not."
            )

    def test_parent_id_is_null_on_node_records_and_set_on_children(self, two_node_run):
        """§1.2: two record types are roots, and everything else hangs off a node.

        `run_start` belongs to the run rather than to a node, so it is a root like
        `node_execution` is. Everything else records something a node did.
        """
        _, records = two_node_run
        node_ids = {r["record_id"] for r in records if r["record_type"] == "node_execution"}
        for record in records:
            if record["record_type"] in ("node_execution", "run_start"):
                assert record["parent_id"] is None
            else:
                assert record["parent_id"] in node_ids, (
                    f"{record['record_type']} record points at "
                    f"{record['parent_id']!r}, which is not a node record"
                )

    def test_node_kind_is_recorded_per_kind(self, two_node_run):
        _, records = two_node_run
        kinds = [r["node_kind"] for r in records if r["record_type"] == "node_execution"]
        assert kinds == ["deterministic", "llm"]

    def test_deterministic_nodes_record_no_seed(self, two_node_run):
        """§3: seed is required-but-nullable, and null on deterministic nodes only.

        An optional field could not distinguish "deterministic, no seed applies" from
        "stochastic, seed not recorded", which is the whole failure FT-07 checks for.
        """
        _, records = two_node_run
        by_kind = {r["node_kind"]: r for r in records if r["record_type"] == "node_execution"}
        assert by_kind["deterministic"]["seed"] is None
        assert by_kind["llm"]["seed"] == 41

    def test_budget_carries_all_four_axes(self, two_node_run):
        _, records = two_node_run
        for record in records:
            if record["record_type"] == "node_execution":
                assert set(record["budget"]) == BUDGET_KEYS

    def test_termination_is_null_on_a_non_agent_node_that_succeeded(self, two_node_run):
        """§3: the budget axes and `finish` are agent-only. `error` is not.

        A node of any kind that failed records `termination: "error"`, which is what
        `TestFailedRunsAreRecorded` covers.
        """
        _, records = two_node_run
        for record in records:
            if record["record_type"] == "node_execution" and record["node_kind"] != "agent":
                assert record["termination"] is None


class TestModelCallRecords:
    def test_model_call_has_its_type_specific_fields(self, two_node_run):
        _, records = two_node_run
        calls = [r for r in records if r["record_type"] == "model_call"]
        assert len(calls) == 1
        drifted = MODEL_CALL_FIELDS ^ (calls[0].keys() - COMMON_FIELDS)
        assert not drifted, (
            f"§4.1 and the writer disagree about {sorted(drifted)}: one of them has a field "
            f"the other does not."
        )

    def test_token_breakdown_is_five_fields_not_one(self, two_node_run):
        """§4.1.2: a single input figure silently undercounts every cached call."""
        _, records = two_node_run
        call = next(r for r in records if r["record_type"] == "model_call")
        assert set(call["tokens"]) == TOKEN_KEYS

    def test_total_input_tokens_are_not_stored(self, two_node_run):
        """§6: derived from the three input fields, never stored."""
        _, records = two_node_run
        call = next(r for r in records if r["record_type"] == "model_call")
        assert "total_input" not in call["tokens"]
        assert "input_tokens" not in call["tokens"]

    def test_no_cost_field_anywhere(self, two_node_run):
        """§6: cost is derived against the manifest's basis, never stored."""
        _, records = two_node_run
        for record in records:
            assert "cost" not in record
            flat = json.dumps(record)
            assert '"cost"' not in flat, f"a cost figure leaked into {record['record_type']}"

    def test_no_duration_field(self, two_node_run):
        """§6: derived from started_at and ended_at."""
        _, records = two_node_run
        for record in records:
            assert "duration" not in record
            assert "duration_ms" not in record

    def test_request_and_response_model_are_separate(self, two_node_run):
        """§4.1: one `model` field would make FT-14 defeatable by a provider-side fallback."""
        _, records = two_node_run
        call = next(r for r in records if r["record_type"] == "model_call")
        assert "request_model" in call and "response_model" in call
        assert "model" not in call

    def test_backend_and_revision_are_recorded(self, two_node_run):
        """§4.1: a dated model string is a promise; a commit SHA is proof."""
        _, records = two_node_run
        call = next(r for r in records if r["record_type"] == "model_call")
        assert call["backend"] in ("hosted_api", "self_hosted")
        assert call["model_revision"] is not None

    def test_concurrency_is_recorded(self, two_node_run):
        """§4.1: this is what compute-basis cost divides by (§6)."""
        _, records = two_node_run
        call = next(r for r in records if r["record_type"] == "model_call")
        assert "concurrent_requests" in call


class TestAgentNodeRecords:
    """An AgentNode's inner steps are child records, not a collapsed summary.

    Collapsing them into a single summary record would destroy what ablation reads.
    """

    @pytest.fixture
    def agent_run(self, envelope, trajectory):
        calls: list[str] = []

        def look_up(query: str) -> str:
            """Look something up. Returns a string."""
            calls.append(query)
            return f"result for {query}"

        search = Tool(
            name="look_up",
            description="Look something up.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            side_effect_class=SideEffectClass.READ_ONLY,
            fn=look_up,
        )

        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c1", name="look_up", arguments={"query": "a"})]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="look_up", arguments={"query": "b"})]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c3", name="finish", arguments={"answer": "done", "source": None}
                        )
                    ]
                ),
            ]
        )

        def hunt(inputs, ctx):
            return f"Find it. Tools: {ctx.describe_tools()}"

        pipeline = Pipeline(
            [
                AgentNode(
                    hunt,
                    tools=[search],
                    output_schema=Answer,
                    budget=Budget(
                        max_steps=8,
                        max_tokens=50_000,
                        max_cost=None,
                        max_wall_clock_ms=120_000,
                    ),
                )
            ],
            budget=Budget(
                max_steps=None, max_tokens=200_000, max_cost=None, max_wall_clock_ms=600_000
            ),
        )
        result = pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client, seed=7)
        return result, list(read_trajectory(trajectory)), calls

    def test_inner_steps_are_child_records(self, agent_run):
        _, records, _ = agent_run
        node = next(r for r in records if r["record_type"] == "node_execution")
        children = [r for r in records if r["parent_id"] == node["record_id"]]
        # 3 model calls + 2 tool calls + 1 finish call
        assert len(children) == 6
        assert sum(1 for c in children if c["record_type"] == "model_call") == 3
        assert sum(1 for c in children if c["record_type"] == "tool_call") == 3

    def test_seq_is_monotonic_across_the_nested_case(self, agent_run):
        """Where the nesting is deepest is where emission order is easiest to get wrong.

        A node record is written *after* everything that happened inside it, so it carries a
        higher sequence than its own children. Allocating sequence at node start instead of at emission
        produced 1, 3, 2 and this is the test that caught it.
        """
        _, records, _ = agent_run
        sequences = [r["sequence"] for r in records]
        assert sequences == sorted(sequences), f"sequence not monotonic: {sequences}"
        assert len(set(sequences)) == len(sequences)
        # The node record is last, because it completes last.
        assert records[-1]["record_type"] == "node_execution"

    def test_tool_call_records_have_their_fields(self, agent_run):
        _, records, _ = agent_run
        calls = [r for r in records if r["record_type"] == "tool_call"]
        assert calls
        for record in calls:
            drifted = TOOL_CALL_FIELDS ^ (record.keys() - COMMON_FIELDS)
            assert not drifted, (
                f"§4.2 and the writer disagree about {sorted(drifted)}: one of them has a "
                f"field the other does not."
            )

    def test_side_effect_class_is_on_the_record_not_only_the_registry(self, agent_run):
        """§4.2: FT-20 asks a question about a past run, so the class must travel with it."""
        _, records, _ = agent_run
        tool_calls = [r for r in records if r["record_type"] == "tool_call"]
        assert all(r["side_effect_class"] == "read_only" for r in tool_calls)

    def test_termination_is_finish_when_the_model_calls_finish(self, agent_run):
        _, records, _ = agent_run
        node = next(r for r in records if r["record_type"] == "node_execution")
        assert node["termination"] == "finish"
        assert node["node_kind"] == "agent"

    def test_the_tools_actually_ran(self, agent_run):
        _, _, calls = agent_run
        assert calls == ["a", "b"]

    def test_output_is_the_validated_finish_payload(self, agent_run):
        result, _, _ = agent_run
        assert result.output.answer == "done"

    def test_effective_budget_is_the_per_axis_minimum(self, agent_run):
        """§3.1 "the budget in force": a node may narrow the run budget, never widen it."""
        _, records, _ = agent_run
        node = next(r for r in records if r["record_type"] == "node_execution")
        # node cap 8 steps vs run unbounded on steps -> 8; node 50k tokens vs run 200k -> 50k
        assert node["budget"]["max_steps"] == 8
        assert node["budget"]["max_tokens"] == 50_000
        assert node["budget"]["max_wall_clock_ms"] == 120_000


class TestFailedRunsAreRecorded:
    """§2: a record is written for an operation that never completed.

    The record is most needed when something breaks, which is FT-13's argument, and FT-13's
    check reads "one record per node execution" with no exception for a node that failed.
    Before this suite existed the error path was tested on `Deterministic` alone, which was
    the one node kind that implemented it.
    """

    def failing_run(self, envelope, trajectory, node):
        pipeline = Pipeline(
            [node],
            budget=Budget(
                max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=300_000
            ),
        )
        with pytest.raises(RuntimeError):
            pipeline.run(
                {"question": "q"},
                envelope=envelope,
                run_id=RUN_ID,
                model=ExplodingClient(),
                seed=41,
            )
        return list(read_trajectory(trajectory))

    def test_every_node_kind_records_its_own_failure(self, envelope, trajectory, tmp_path):
        """One node record per kind, each carrying termination `error`."""
        for node in (
            Deterministic(explode),
            LLMNode(question, output_schema=Answer, node_id="llm_node"),
            AgentNode(
                question,
                tools=[],
                output_schema=Answer,
                budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
                node_id="agent_node",
            ),
        ):
            trajectory.unlink(missing_ok=True)
            records = self.failing_run(envelope, trajectory, node)
            nodes = [r for r in records if r["record_type"] == "node_execution"]
            assert len(nodes) == 1, f"{node.node_kind} wrote {len(nodes)} node records"
            assert nodes[0]["termination"] == "error"
            assert nodes[0]["error"]["class"] == "caller_facing"
            assert nodes[0]["outputs"] is None

    def test_no_record_points_at_a_node_that_was_never_written(self, envelope, trajectory):
        """A `model_call` recorded under a node whose record is missing dangles.

        §2 defines `parent_id` as the node record this belongs to. Schema validation failing
        is the likeliest `LLMNode` failure, and it is the one that produced the dangling link.
        """
        pipeline = Pipeline(
            [LLMNode(question, output_schema=Answer, node_id="llm_node")],
            budget=Budget(
                max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None
            ),
        )
        client = FakeModelClient(responses=[fake_response(content="not json")])
        with pytest.raises(CallerFacingError):
            pipeline.run({"question": "q"}, envelope=envelope, run_id=RUN_ID, model=client, seed=41)

        records = list(read_trajectory(trajectory))
        node_ids = {r["record_id"] for r in records if r["record_type"] == "node_execution"}
        assert node_ids, "the node executed and wrote no record"
        for record in records:
            # `run_start` is the run's own record and hangs off no node (§1.3).
            if record["record_type"] not in ("node_execution", "run_start"):
                assert record["parent_id"] in node_ids

    def test_a_call_that_raised_is_recorded_as_one_that_never_completed(self, envelope, trajectory):
        """§2 ended_at, §4.1.2 tokens: an attempt leaves a record, and nothing claims a count."""
        records = self.failing_run(
            envelope, trajectory, LLMNode(question, output_schema=Answer, node_id="llm_node")
        )
        calls = [r for r in records if r["record_type"] == "model_call"]
        assert len(calls) == 1, "the attempted call left no record"
        call = calls[0]

        assert call["ended_at"] is None
        assert call["response_model"] is None
        assert call["finish_reason"] is None
        assert call["replayed"] is False
        assert call["error"]["class"] == "caller_facing"
        # §4.1.2: an unmeasured count is unknown, never 0. Zero is a claim.
        for key in ("input_uncached", "input_cache_read", "input_cache_write", "output"):
            assert call["tokens"][key]["type"] == "unknown", key

    def test_the_model_that_was_asked_for_is_recorded_on_a_failed_call(self, envelope, trajectory):
        """FT-14's pin has to survive the failure, or the run cannot be attributed at all."""
        records = self.failing_run(
            envelope, trajectory, LLMNode(question, output_schema=Answer, node_id="llm_node")
        )
        call = next(r for r in records if r["record_type"] == "model_call")
        assert call["request_model"] == "test/model"
        assert call["backend"] == "self_hosted"
        assert call["seed"] is not None


class TestConsultationRecords:
    """§4.3. The fourth record type, and the only one written in two halves.

    A question whose answer arrives in a later process is two records: one when it is asked and
    one when it is answered. Both are checked, because only the second carries `answers` filled
    and only the first carries a `null` `ended_at`.
    """

    @pytest.fixture
    def consulted(self, envelope, trajectory):
        registry = ToolRegistry()
        registry.add(
            consult(
                lambda q, o, a=None: (_ for _ in ()).throw(Suspend(waiting_for=q)),
                answered_by="end_user",
            )
        )
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: "Ask before answering.",
                    tools=registry,
                    output_schema=Answer,
                    budget=Budget(
                        max_steps=8,
                        max_tokens=50_000,
                        max_cost=None,
                        max_wall_clock_ms=120_000,
                    ),
                    node_id="hunt",
                )
            ],
            budget=Budget(
                max_steps=None, max_tokens=200_000, max_cost=None, max_wall_clock_ms=600_000
            ),
        )
        asking = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c1", name="consult", arguments={"question": "which one?"}
                        )
                    ]
                ),
            ]
        )
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=asking, seed=7)
        answering = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c2",
                            name="finish",
                            arguments={"answer": "the blue one", "source": None},
                        )
                    ]
                ),
            ]
        )
        pipeline.resume(RUN_ID, envelope=envelope, model=answering, answer="the blue one")
        records = list(read_trajectory(trajectory))
        return [r for r in records if r["record_type"] == "consultation"]

    def test_consultation_records_have_their_type_specific_fields(self, consulted):
        assert len(consulted) == 2
        for record in consulted:
            drifted = CONSULTATION_FIELDS ^ (record.keys() - COMMON_FIELDS)
            assert not drifted, (
                f"§4.3 and the writer disagree about {sorted(drifted)}: one of them has a "
                f"field the other does not."
            )

    def test_the_question_is_recorded_when_it_is_asked(self, consulted):
        """A run that is never continued still has to say what it was waiting for."""
        asked = consulted[0]
        assert asked["resolution"] == "pending"
        assert asked["response"] is None
        assert asked["ended_at"] is None
        assert asked["answers"] is None
        assert asked["blocking"] is False

    def test_the_answer_names_the_question_it_answers(self, consulted):
        asked, answered = consulted
        assert answered["answers"] == asked["record_id"]
        assert answered["resolution"] == "answered"
        assert answered["response"] == "the blue one"
        assert answered["ended_at"] is not None

    def test_counting_consultations_means_counting_unanswered_records(self, consulted):
        """§4.3: the pair describes one question, so counting every record double-counts."""
        assert len([r for r in consulted if r["answers"] is None]) == 1
