"""Fan-out: one call per item, and the line between an absent answer and a failed call.

`unknown` is an answer. A failure is the absence of one. An evaluation reads the first as a
recall result and the second as a broken run, so the two must not be reachable from each
other (FT-09, FT-10).
"""

from __future__ import annotations

import json
import time
import warnings

import pytest

from simple_agents import (
    AgentNode,
    Budget,
    Cassette,
    BudgetExceeded,
    Deterministic,
    FakeModelClient,
    FanOutResult,
    LLMNode,
    Pipeline,
    RetryPolicy,
    RunEnvelope,
    SideEffectClass,
    Unknown,
    read_trajectory,
    tool,
)
from simple_agents.errors import (
    CallerFacingError,
    ConfigurationError,
    SimpleAgentsWarning,
)
from simple_agents.models import ToolCallRequest, fake_response
from simple_agents.nodes import ItemOutcome
from simple_agents.nodes.fanout import _refuse_one_failure_wearing_a_tolerance
from simple_agents.tools import ModelHandle

from schemas import Answer
from conftest import RUN_ID

FOUND = json.dumps({"answer": "32 inches"})
ABSENT = json.dumps({"answer": {"type": "unknown", "reason": "not published"}})


def summarise(inputs, ctx):
    return f"summarise: {inputs['documents']}"


def load(inputs, ctx):
    return {"documents": list(inputs["documents"])}


def pipeline_over(items_node=None, **kw):
    return Pipeline(
        [Deterministic(load), LLMNode(summarise, output_schema=Answer, over="documents", **kw)],
        budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )


class TestOneCallPerItem:
    def test_each_item_gets_its_own_call_and_its_own_seed(self, envelope, trajectory):
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(3)])
        result = pipeline_over().run(
            {"documents": ["a", "b", "c"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        assert len(client.requests) == 3
        assert isinstance(result.output, FanOutResult)
        assert len(result.output) == 3
        assert result.output.ok

        calls = [r for r in read_trajectory(trajectory) if r["record_type"] == "model_call"]
        assert len({c["seed"] for c in calls}) == 3, "items must not share a seed"

    def test_the_prompt_function_receives_one_item_at_a_time(self, envelope):
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(2)])
        pipeline_over().run(
            {"documents": ["first", "second"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        sent = [r.messages[0]["content"] for r in client.requests]
        assert sent == ["summarise: first", "summarise: second"]

    def test_one_node_record_with_every_call_beneath_it(self, envelope, trajectory):
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(3)])
        pipeline_over().run(
            {"documents": ["a", "b", "c"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        records = list(read_trajectory(trajectory))
        nodes = [r for r in records if r["record_type"] == "node_execution"]
        fan = next(r for r in nodes if r["node_kind"] == "llm")
        children = [r for r in records if r.get("parent_id") == fan["record_id"]]
        assert len(nodes) == 2  # the deterministic node and the fan-out node
        assert len(children) == 3


class TestUnknownIsNotAFailure:
    def test_an_unknown_answer_is_a_success(self, envelope):
        """The model answered, and the answer was absence. It belongs with the successes."""
        client = FakeModelClient(
            responses=[fake_response(content=FOUND), fake_response(content=ABSENT)]
        )
        result = pipeline_over().run(
            {"documents": ["a", "b"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        out = result.output
        assert out.ok, "an unknown answer must not register as a failure"
        assert out.failures == []
        assert len(out.outcomes) == 2
        assert isinstance(out.outcomes[1].value.answer, Unknown)

    def test_a_failed_item_produces_no_value_at_all(self, envelope):
        """No schema instance exists, so there is nothing that could be read as an answer."""
        client = FakeModelClient(
            responses=[fake_response(content=FOUND), fake_response(content="not json")]
        )
        result = pipeline_over().run(
            {"documents": ["a", "b"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        out = result.output
        assert not out.ok
        assert [o.index for o in out.outcomes if o.ok] == [0], (
            "a failure must not register as a success"
        )
        assert [f.index for f in out.failures] == [1]
        assert out.failures[0].value is None
        assert out.failures[0].error["class"] == "caller_facing"
        assert out.failures[0].item == "b", "the failed input travels with the failure"

    def test_the_two_are_distinguishable_in_the_trajectory(self, envelope, trajectory):
        client = FakeModelClient(
            responses=[fake_response(content=ABSENT), fake_response(content="not json")]
        )
        pipeline_over().run(
            {"documents": ["a", "b"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        records = list(read_trajectory(trajectory))
        fan = next(
            r for r in records if r["record_type"] == "node_execution" and r["node_kind"] == "llm"
        )
        items = fan["outputs"]["items"]
        # One entry per input item, in input order, so an entry's position is its item.
        assert [i["index"] for i in items] == [0, 1]
        assert items[0]["value"]["answer"]["type"] == "unknown"
        assert "value" not in items[1]
        assert items[1]["error"]["class"] == "caller_facing"

    def test_the_node_record_names_failures_even_when_the_caller_ignores_them(
        self, envelope, trajectory
    ):
        """A caller reading only the successes still leaves the failures on the record (FT-13)."""
        client = FakeModelClient(
            responses=[fake_response(content=f"not json {n}") for n in range(2)]
        )
        pipeline_over().run(
            {"documents": ["a", "b"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        fan = next(
            r
            for r in read_trajectory(trajectory)
            if r["record_type"] == "node_execution" and r["node_kind"] == "llm"
        )
        items = fan["outputs"]["items"]
        assert [i["index"] for i in items] == [0, 1]
        assert all("error" in i for i in items)


class TestFailureBudget:
    def test_max_failures_stops_a_batch_that_is_failing_systematically(self, envelope):
        client = FakeModelClient(responses=[fake_response(content="not json") for _ in range(5)])
        with pytest.raises(CallerFacingError) as exc:
            pipeline_over(max_failures=1).run(
                {"documents": ["a", "b", "c", "d", "e"]},
                envelope=envelope,
                run_id=RUN_ID,
                model=client,
                seed=41,
            )
        assert "above max_failures=1" in str(exc.value)
        assert len(client.requests) == 2, "it must stop rather than finish the batch"

    def test_collecting_is_the_default(self, envelope):
        """Every item failing for its own reason is collected, however many there are.

        The responses differ, so the failures differ, which is what separates a batch of
        items that each went wrong from one failure the whole node shares.
        """
        client = FakeModelClient(
            responses=[fake_response(content=f"not json {n}") for n in range(4)]
        )
        result = pipeline_over().run(
            {"documents": ["a", "b", "c", "d"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        assert len(result.output.failures) == 4

    def test_every_item_failing_the_same_way_raises_whatever_the_tolerance_says(self, envelope):
        """Not a rate. The tolerance says how many items may fail; this says the node did not
        work at all, so it fires with max_failures set high enough to permit every one."""
        client = FakeModelClient(responses=[fake_response(content="not json") for _ in range(4)])

        with pytest.raises(CallerFacingError) as exc:
            pipeline_over(max_failures=99).run(
                {"documents": ["a", "b", "c", "d"]},
                envelope=envelope,
                run_id=RUN_ID,
                model=client,
                seed=41,
            )

        assert "every one of them failed with the same" in str(exc.value)

    def test_a_node_that_ran_out_of_its_own_budget_is_not_a_broken_node(self):
        """An item the node's own budget stopped did not fail, which is why it is outside
        `max_failures` too. Saying the prompt is wrong for every item would be false."""
        outcomes = [
            ItemOutcome(
                index=index,
                item=index,
                error={"type": "NodeBudgetExceeded", "message": "max_steps: 4 of 4"},
            )
            for index in range(3)
        ]

        _refuse_one_failure_wearing_a_tolerance(outcomes, "ask", 3)

    def test_a_fan_out_over_one_item_is_left_alone(self, envelope):
        """At one item every failure is trivially the same failure, so the rule says nothing
        and the item is collected as it always was."""
        client = FakeModelClient(responses=[fake_response(content="not json")])

        result = pipeline_over().run(
            {"documents": ["a"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )

        assert len(result.output.failures) == 1

    def test_some_items_failing_the_same_way_is_not_the_node_failing(self, envelope):
        """The majority went through, which is what a tolerance is for."""
        client = FakeModelClient(
            responses=[
                fake_response(content="not json"),
                fake_response(content="not json"),
                fake_response(content=FOUND),
                fake_response(content=FOUND),
            ]
        )

        result = pipeline_over().run(
            {"documents": ["a", "b", "c", "d"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )

        assert len(result.output.failures) == 2

    def test_the_run_budget_still_bounds_the_fan_out(self, envelope):
        """A fan-out is many calls, so the axis has to be checked between items."""
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(10)])
        pipeline = Pipeline(
            [Deterministic(load), LLMNode(summarise, output_schema=Answer, over="documents")],
            budget=Budget(max_steps=3, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        with pytest.raises(BudgetExceeded) as exc:
            pipeline.run(
                {"documents": list("abcdefghij")},
                envelope=envelope,
                run_id=RUN_ID,
                model=client,
                seed=41,
            )
        assert exc.value.axis == "max_steps"
        assert len(client.requests) == 3


class TestRefusals:
    def test_a_missing_key_names_what_was_found(self):
        node = LLMNode(summarise, output_schema=Answer, over="documents")
        pipeline = Pipeline(
            [node],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        client = FakeModelClient(responses=[fake_response(content=FOUND)])
        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({"docs": ["a"]}, envelope=RunEnvelope(), model=client)
        assert "has no such key" in str(exc.value)
        assert "['docs']" in str(exc.value)

    def test_a_string_is_not_a_sequence_of_items(self, envelope):
        """Iterating a string would fan out over its characters."""
        pipeline = Pipeline(
            [LLMNode(summarise, output_schema=Answer, over="documents")],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        client = FakeModelClient(responses=[fake_response(content=FOUND)])
        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({"documents": "abc"}, envelope=envelope, run_id=RUN_ID, model=client)
        assert "a string is a single value" in str(exc.value)

    def test_max_failures_without_over_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            LLMNode(summarise, output_schema=Answer, max_failures=2)
        assert "without over=" in str(exc.value)

    def test_a_retry_that_collecting_makes_inert_is_refused(self):
        """A project added one to close a measured 2.3% item loss and it never fired.

        `_Failures.saw` returns without raising while the count is within the limit, and a
        `RetryPolicy` re-executes a node only when the node raises (`DF4-D4`).
        """
        with pytest.raises(ConfigurationError) as exc:
            LLMNode(
                summarise,
                output_schema=Answer,
                over="documents",
                retry=RetryPolicy(attempts=2),
            )
        assert "never reaches this one" in str(exc.value)
        assert "max_failures=0" in str(exc.value)

    def test_a_retry_beside_a_failure_limit_is_accepted(self):
        node = LLMNode(
            summarise,
            output_schema=Answer,
            over="documents",
            max_failures=0,
            retry=RetryPolicy(attempts=2),
        )

        assert node.max_failures == 0

    def test_a_retry_on_a_node_that_does_not_fan_out_is_accepted(self):
        assert (
            LLMNode(summarise, output_schema=Answer, retry=RetryPolicy(attempts=2)).node_id
            == "summarise"
        )

    def test_the_retry_fires_once_a_failed_item_can_raise(self, envelope):
        """The whole node re-executes, which is what makes the refusal's advice honest."""
        client = FakeModelClient(responses=[fake_response(content="not json") for _ in range(8)])
        with pytest.raises(CallerFacingError):
            pipeline_over(max_failures=0, retry=RetryPolicy(attempts=2)).run(
                {"documents": ["a", "b"]},
                envelope=envelope,
                run_id=RUN_ID,
                model=client,
                seed=41,
            )

        assert len(client.requests) > 1


def load_with_extras(inputs, ctx):
    return {
        "documents": list(inputs["documents"]),
        "question": inputs["question"],
        "unreadable": ["u3"],
    }


def pipeline_keeping(keep, **kw):
    return Pipeline(
        [
            Deterministic(load_with_extras),
            LLMNode(summarise, output_schema=Answer, over="documents", keep=keep, **kw),
        ],
        budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )


class TestKeepingValuesPastTheFanOut:
    """`keep=` is the answer to a value that arrived beside the sequence and stops here.

    Without it the node's output is the outcomes alone, so anything else the previous node
    produced reaches no later node on any edge (`docs/pipeline.md` §1.2).
    """

    def test_without_keep_the_result_carries_nothing_but_the_outcomes(self, envelope):
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(2)])
        result = pipeline_keeping(None).run(
            {"documents": ["a", "b"], "question": "how wide?"},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        assert result.output.kept == {}

    def test_a_kept_key_reaches_the_next_node(self, envelope):
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(2)])
        result = pipeline_keeping(["question", "unreadable"]).run(
            {"documents": ["a", "b"], "question": "how wide?"},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        assert result.output.kept == {"question": "how wide?", "unreadable": ["u3"]}
        assert len(result.output) == 2, "the outcomes are unchanged"

    def test_what_was_kept_is_on_the_record(self, envelope, trajectory):
        client = FakeModelClient(responses=[fake_response(content=FOUND)])
        pipeline_keeping(["question"]).run(
            {"documents": ["a"], "question": "how wide?"},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        fan = [
            r
            for r in read_trajectory(trajectory)
            if r["record_type"] == "node_execution" and r["node_id"] == "summarise"
        ][0]
        assert fan["outputs"]["kept"] == {"question": "how wide?"}

    def test_a_node_that_keeps_nothing_records_no_kept_key(self, envelope, trajectory):
        """A record written before `keep=` existed reads the same as one written now."""
        client = FakeModelClient(responses=[fake_response(content=FOUND)])
        pipeline_over().run(
            {"documents": ["a"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )
        fan = [
            r
            for r in read_trajectory(trajectory)
            if r["record_type"] == "node_execution" and r["node_id"] == "summarise"
        ][0]
        assert "kept" not in fan["outputs"]

    def test_a_kept_key_that_is_not_there_is_refused_rather_than_dropped(self, envelope):
        """Dropping it silently is the failure `keep=` exists to prevent."""
        client = FakeModelClient(responses=[fake_response(content=FOUND)])
        with pytest.raises(CallerFacingError) as exc:
            pipeline_keeping(["quesiton"]).run(
                {"documents": ["a"], "question": "how wide?"},
                envelope=envelope,
                run_id=RUN_ID,
                model=client,
                seed=41,
            )
        assert "'quesiton'" in str(exc.value)
        assert "'question'" in str(exc.value), "it names the keys that are there"

    def test_keep_without_over_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            LLMNode(summarise, output_schema=Answer, keep=["question"])
        assert "sets keep without over=" in str(exc.value)

    def test_keeping_the_key_being_fanned_out_over_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            LLMNode(summarise, output_schema=Answer, over="documents", keep=["documents"])
        assert "writes each one twice" in str(exc.value)

    def test_a_bare_string_is_not_a_list_of_keys(self):
        """`keep="question"` would otherwise keep four keys named q, u, e and s."""
        with pytest.raises(ConfigurationError) as exc:
            LLMNode(summarise, output_schema=Answer, over="documents", keep="question")
        assert "as a sequence of strings" in str(exc.value)


class TestReplay:
    def test_each_item_records_and_replays_as_its_own_call(self, tmp_path):
        """A fan-out is many calls, each keyed on its own request."""
        from simple_agents import Cassette

        path = tmp_path / "c.jsonl"
        answers = [json.dumps({"answer": a}) for a in ("x", "y", "z")]

        live = pipeline_over().run(
            {"documents": ["a", "b", "c"]},
            envelope=RunEnvelope(run_dir=tmp_path / "one", cassette=Cassette.record(path)),
            model=FakeModelClient(responses=[fake_response(content=a) for a in answers]),
            seed=41,
        )
        assert live.manifest["cassette"]["recorded"] == 3

        class Dead(FakeModelClient):
            def complete(self, request):
                raise AssertionError("replay must not reach the model")

        replayed = pipeline_over().run(
            {"documents": ["a", "b", "c"]},
            envelope=RunEnvelope(run_dir=tmp_path / "two", cassette=Cassette.replay(path)),
            model=Dead(),
            seed=41,
        )
        assert replayed.manifest["cassette"] == {
            **replayed.manifest["cassette"],
            "hits": 3,
            "misses": 0,
        }
        assert [o.value.answer for o in replayed.output] == ["x", "y", "z"]

        calls = [
            r for r in read_trajectory(replayed.trajectory_path) if r["record_type"] == "model_call"
        ]
        assert all(c["replayed"] for c in calls)
        assert len({c["cassette_key"] for c in calls}) == 3


# --- Fanning out a node kind other than an LLMNode -------------------------------------


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def look_up(name: str) -> str:
    """Look up a retailer's city. Returns the city."""
    return "York"


def read_one(inputs, ctx):
    return f"read: {inputs['documents']} {ctx.describe_tools()}"


def parse_one(inputs, ctx):
    return {"seen": inputs["documents"].upper()}


def _asks_for_a_tool(request):
    return fake_response(
        tool_calls=[ToolCallRequest(id="c", name="look_up", arguments={"name": "N"})]
    )


ITEM_BUDGET = Budget(max_steps=3, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def agent_over(**kw):
    """A fan-out over an AgentNode, silencing the one-budget warning the tests assert on."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SimpleAgentsWarning)
        node = AgentNode(
            read_one,
            tools=[look_up],
            output_schema=Answer,
            over="documents",
            node_id="read",
            **kw,
        )
    return Pipeline(
        [Deterministic(load), node],
        budget=Budget(max_steps=500, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )


class TestARetriedFanOut:
    def test_the_second_attempt_asks_again_rather_than_re_sending(self, envelope, trajectory):
        """A retry that re-sent an identical request could not replay.

        A cassette is keyed on the request, and the seed is part of it, so two attempts sending
        one seed are one entry: the recording holds the failure that caused the retry, and a
        replay serves it again. Numbering a call within its item rather than by the item's index
        gives the second attempt its own number, as a retried node that does not fan out has
        always had.
        """
        sent = {"n": 0}

        def answer(request):
            sent["n"] += 1
            return fake_response(content="nonsense" if sent["n"] == 1 else FOUND)

        pipeline = pipeline_over(max_failures=0, retry=RetryPolicy(attempts=2), node_id="fan")

        pipeline.run(
            {"documents": ["a", "b"]},
            envelope=envelope,
            model=FakeModelClient(answer=answer),
            run_id=RUN_ID,
        )

        seeds = [
            r["seed"]
            for r in read_trajectory(trajectory)
            if r["record_type"] == "model_call" and r["item_index"] == 0
        ]
        assert len(seeds) == 2
        assert len(set(seeds)) == 2


class TestADeterministicNodeFansOut:
    def test_the_function_runs_once_per_item(self, envelope):
        pipeline = Pipeline(
            [Deterministic(load), Deterministic(parse_one, over="documents")],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

        result = pipeline.run({"documents": ["a", "b"]}, envelope=envelope, run_id=RUN_ID)

        assert isinstance(result.output, FanOutResult)
        assert [o.value["seen"] for o in result.output] == ["A", "B"]

    def test_a_failed_item_is_collected_and_the_rest_still_run(self, envelope):
        def parse_or_raise(inputs, ctx):
            if inputs["documents"] == "b":
                raise ValueError("no")
            return inputs["documents"]

        pipeline = Pipeline(
            [Deterministic(load), Deterministic(parse_or_raise, over="documents")],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

        result = pipeline.run({"documents": ["a", "b", "c"]}, envelope=envelope, run_id=RUN_ID)

        assert [o.ok for o in result.output] == [True, False, True]
        assert result.output.failures[0].error["type"] == "ValueError"


class TestAnAgentNodeFansOut:
    def test_each_item_runs_its_own_loop_and_says_how_it_stopped(self, envelope):
        pipeline = agent_over(budget_per_item=ITEM_BUDGET)
        client = FakeModelClient(answer=_asks_for_a_tool)

        result = pipeline.run(
            {"documents": ["a", "b"]}, envelope=envelope, model=client, run_id=RUN_ID
        )

        # Three steps each, and nothing ever calls `finish`, so each item stops on its own
        # budget rather than on the node's or the run's.
        assert [o.termination for o in result.output] == ["max_steps", "max_steps"]

    def test_each_item_is_seeded_by_its_index_rather_than_by_the_order_it_ran(
        self, envelope, trajectory
    ):
        pipeline = agent_over(budget_per_item=ITEM_BUDGET, concurrent_items=4)
        client = FakeModelClient(answer=_asks_for_a_tool)

        pipeline.run({"documents": ["a", "b", "c"]}, envelope=envelope, model=client, run_id=RUN_ID)

        calls = [r for r in read_trajectory(trajectory) if r["record_type"] == "model_call"]
        by_item: dict[int, list[int]] = {}
        for call in calls:
            by_item.setdefault(call["item_index"], []).append(call["seed"])
        # Every call names the item it was for, and an item's seeds come from its own index
        # and its own position, so they hold whatever order the items interleaved in.
        assert sorted(by_item) == [0, 1, 2]
        assert all(len(seeds) == 3 for seeds in by_item.values())
        assert len({s for seeds in by_item.values() for s in seeds}) == 9


class TestWhichItemACallBelongsTo:
    """A fan-out's items share one `parent_id` and overlap, so each record names its item."""

    def test_every_tool_call_names_the_item_that_made_it(self, envelope, trajectory):
        pipeline = agent_over(budget_per_item=ITEM_BUDGET, concurrent_items=4)
        client = FakeModelClient(answer=_asks_for_a_tool)

        pipeline.run({"documents": ["a", "b", "c"]}, envelope=envelope, model=client, run_id=RUN_ID)

        by_item: dict[int, int] = {}
        for record in read_trajectory(trajectory):
            if record["record_type"] == "tool_call":
                by_item[record["item_index"]] = by_item.get(record["item_index"], 0) + 1
        # Three items, three steps each, one tool call per step. Without `item_index` all
        # nine are one undifferentiated set under the node's record.
        assert by_item == {0: 3, 1: 3, 2: 3}

    def test_a_tool_call_outside_a_fan_out_names_no_item(self, envelope, trajectory):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SimpleAgentsWarning)
            node = AgentNode(
                read_one,
                tools=[look_up],
                output_schema=Answer,
                node_id="read",
                budget=ITEM_BUDGET,
            )
        pipeline = Pipeline(
            [node],
            budget=Budget(max_steps=500, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

        pipeline.run(
            {"documents": ["a"]},
            envelope=envelope,
            model=FakeModelClient(answer=_asks_for_a_tool),
            run_id=RUN_ID,
        )

        calls = [r for r in read_trajectory(trajectory) if r["record_type"] == "tool_call"]
        assert calls
        assert all(record["item_index"] is None for record in calls)


class TestACallMadeUnderneathAnItem:
    """Everything a fan-out item spends is attributable to it, however it was spent.

    A search's embedding call and a consultation reader's call go through their own paths, and
    both carried no item until `P3-22`. What a spun item spent is read off these.
    """

    def test_a_search_inside_an_item_names_the_item(self, envelope, trajectory):
        from simple_agents.builtins import DocumentIndex, Semantic, document_search
        from simple_agents.embeddings import FakeEmbeddingClient

        index = DocumentIndex.from_texts(
            {"p1": "Deliveries are refused after 4pm.", "p2": "The depot closes at weekends."},
            embeddings=FakeEmbeddingClient(),
            ranking=Semantic(),
        )

        def look(inputs, ctx):
            return {"found": len(ctx.call_tool("document_search", query=inputs["q"])["results"])}

        pipeline = Pipeline(
            [
                Deterministic(
                    look,
                    node_id="look",
                    over="q",
                    tools=[document_search(index, top_k=1)],
                    output_schema=dict,
                )
            ],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

        pipeline.run(
            {"q": ["when do deliveries stop", "weekend hours"]},
            envelope=envelope,
            run_id=RUN_ID,
        )

        embeddings = [
            r
            for r in read_trajectory(trajectory)
            if r["record_type"] == "model_call"
            and (r.get("params") or {}).get("call_kind") == "embedding"
        ]
        assert [r["item_index"] for r in embeddings] == [0, 1]


class TestTwoItemsMakingTheSameCall:
    """A fan-out's items overlap, so a cassette key that ignores them mixes their answers.

    Measured 2026-08-19 before the fix: two items calling one tool with identical arguments
    took their occurrences in arrival order, so a replay that interleaved the other way handed
    each item the other's answer. A tool whose answer varies is what makes it visible.
    """

    def _run(self, tmp_path, *, hold_back: str, cassette):
        counted: list[int] = []

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def next_number() -> str:
            """Answer differently on every call."""
            counted.append(len(counted))
            return f"value-{len(counted)}"

        def ask(inputs, ctx):
            if inputs["book"] == hold_back:
                time.sleep(0.2)
            return {"book": inputs["book"], "got": ctx.call_tool("next_number")}

        pipeline = Pipeline(
            [
                Deterministic(
                    ask,
                    node_id="ask",
                    over="book",
                    concurrent_items=2,
                    tools=[next_number],
                    output_schema=dict,
                )
            ],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        result = pipeline.run(
            {"book": ["Ubik", "Solaris"]},
            envelope=RunEnvelope(run_dir=tmp_path).with_cassette(cassette),
            seed=41,
        )
        return {o.value["book"]: o.value["got"] for o in result.output}

    def test_each_item_replays_its_own_answer(self, tmp_path):
        path = tmp_path / "c.jsonl"
        recorded = self._run(tmp_path / "rec", hold_back="Solaris", cassette=Cassette.record(path))
        # The other item is held back this time, so they reach the tool in the other order.
        replayed = self._run(tmp_path / "rep", hold_back="Ubik", cassette=Cassette.replay(path))

        assert recorded == {"Ubik": "value-1", "Solaris": "value-2"}
        assert replayed == recorded

    def test_the_entries_say_which_item_recorded_them(self, tmp_path):
        path = tmp_path / "c.jsonl"
        self._run(tmp_path / "rec", hold_back="Solaris", cassette=Cassette.record(path))

        entries = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

        assert sorted(e["item_index"] for e in entries) == [0, 1]


class TestTheTwoBudgetsAFanOutDeclares:
    def test_the_per_item_budget_bounds_each_item(self, envelope, trajectory):
        pipeline = agent_over(budget_per_item=ITEM_BUDGET)
        client = FakeModelClient(answer=_asks_for_a_tool)

        pipeline.run({"documents": ["a", "b", "c"]}, envelope=envelope, model=client, run_id=RUN_ID)

        calls = [r for r in read_trajectory(trajectory) if r["record_type"] == "model_call"]
        assert len(calls) == 9  # three items, three steps each

    def test_the_node_budget_bounds_the_items_together(self, envelope, trajectory):
        pipeline = agent_over(
            budget_per_item=ITEM_BUDGET,
            budget=Budget(max_steps=7, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        client = FakeModelClient(answer=_asks_for_a_tool)

        result = pipeline.run(
            {"documents": ["a", "b", "c", "d"]},
            envelope=envelope,
            model=client,
            run_id=RUN_ID,
        )

        calls = [r for r in read_trajectory(trajectory) if r["record_type"] == "model_call"]
        # Seven across the fan-out rather than seven for each of the four items.
        assert len(calls) == 7
        # The items that never ran say so, and the result still has one outcome per item.
        assert len(result.output) == 4
        assert [o.ok for o in result.output] == [True, True, False, False]
        assert "Node budget exhausted" in result.output.failures[0].error["message"]

    def test_the_node_budget_binds_what_the_items_tools_spend(self, envelope, trajectory):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def rewrite(text: str, model: ModelHandle) -> str:
            """Rewrite text with a model. Returns the rewritten text."""
            model.complete([{"role": "user", "content": text}])
            model.complete([{"role": "user", "content": text}])
            return "done"

        def ask(inputs, ctx):
            return f"{inputs['documents']} {ctx.describe_tools()}"

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SimpleAgentsWarning)
            node = AgentNode(
                ask,
                tools=[rewrite],
                output_schema=Answer,
                over="documents",
                node_id="read",
                budget_per_item=Budget(
                    max_steps=20, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                ),
                budget=Budget(max_steps=9, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
            )
        pipeline = Pipeline(
            [Deterministic(load), node],
            budget=Budget(max_steps=1000, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        client = FakeModelClient(
            answer=lambda request: fake_response(
                tool_calls=[ToolCallRequest(id="c", name="rewrite", arguments={"text": "a"})]
            )
        )

        pipeline.run(
            {"documents": ["a", "b", "c", "d"]},
            envelope=envelope,
            model=client,
            run_id=RUN_ID,
        )

        calls = [r for r in read_trajectory(trajectory) if r["record_type"] == "model_call"]
        # A turn is one call by the node and two inside the tool. The node's total has to see
        # all three, or it bounds a third of what the fan-out actually spends.
        assert len(calls) == 9

    def test_a_node_budget_gone_does_not_end_the_run(self, envelope):
        pipeline = agent_over(
            budget_per_item=ITEM_BUDGET,
            budget=Budget(max_steps=1, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        client = FakeModelClient(answer=_asks_for_a_tool)

        result = pipeline.run(
            {"documents": ["a", "b"]}, envelope=envelope, model=client, run_id=RUN_ID
        )

        # The run has 500 steps left; it is the node that ran out, so the run completes and
        # the result says what happened to both items.
        assert result.output is not None
        # The node's total is the tighter of the two for the first item as well, so it stops
        # on a budget it can see rather than being cut off part-way.
        assert result.output.outcomes[0].termination == "max_steps"
        assert not result.output.outcomes[1].ok


class TestWhatAFanOutRefusesToBeConstructedAs:
    def test_a_per_item_budget_without_a_fan_out(self):
        with pytest.raises(ConfigurationError) as caught:
            AgentNode(
                read_one,
                tools=[look_up],
                output_schema=Answer,
                budget=ITEM_BUDGET,
                budget_per_item=ITEM_BUDGET,
                node_id="read",
            )

        assert "sets budget_per_item without over=" in str(caught.value)

    def test_a_fan_out_with_neither_budget(self):
        with pytest.raises(ConfigurationError) as caught:
            AgentNode(
                read_one,
                tools=[look_up],
                output_schema=Answer,
                over="documents",
                node_id="read",
            )

        assert "without a Budget" in str(caught.value)
        assert "budget_per_item=Budget(...)" in str(caught.value)

    def test_a_node_that_runs_once_still_needs_a_budget(self):
        with pytest.raises(ConfigurationError) as caught:
            AgentNode(read_one, tools=[look_up], output_schema=Answer, node_id="read")

        assert "was constructed without a Budget" in str(caught.value)

    @pytest.mark.parametrize(
        "given,left_open",
        [
            ({"budget_per_item": ITEM_BUDGET}, "the node as a whole"),
            (
                {
                    "budget": Budget(
                        max_steps=9,
                        max_tokens=None,
                        max_cost=None,
                        max_wall_clock_ms=None,
                    )
                },
                "one item",
            ),
        ],
    )
    def test_declaring_one_budget_warns_and_names_the_axis_left_open(self, given, left_open):
        with pytest.warns(SimpleAgentsWarning) as caught:
            AgentNode(
                read_one,
                tools=[look_up],
                output_schema=Answer,
                over="documents",
                node_id="read",
                **given,
            )

        assert f"nothing bounds {left_open} except the run" in str(caught[0].message)

    def test_declaring_both_warns_about_nothing(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", SimpleAgentsWarning)
            AgentNode(
                read_one,
                tools=[look_up],
                output_schema=Answer,
                over="documents",
                budget=ITEM_BUDGET,
                budget_per_item=ITEM_BUDGET,
                node_id="read",
            )


class TestAnLLMNodeCallsATool:
    """A model call at a fixed point whose prompt is built from a tool's result.

    The node decides that the call happens, so it is recorded like any other tool call and
    nothing about it is the model's choice.
    """

    def test_the_prompt_function_reaches_its_tools(self, envelope, trajectory):
        def build(inputs, ctx):
            return f"summarise: {ctx.call_tool('look_up', name=inputs['documents'])}"

        pipeline = Pipeline(
            [
                Deterministic(load),
                LLMNode(build, output_schema=Answer, tools=[look_up], over="documents"),
            ],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        client = FakeModelClient(responses=[fake_response(content=FOUND) for _ in range(2)])

        pipeline.run({"documents": ["a", "b"]}, envelope=envelope, model=client, run_id=RUN_ID)

        records = list(read_trajectory(trajectory))
        tool_calls = [r for r in records if r["record_type"] == "tool_call"]
        assert [r["tool_name"] for r in tool_calls] == ["look_up", "look_up"]
        # The prompt the model was sent is the one the tool's result built.
        calls = [r for r in records if r["record_type"] == "model_call"]
        assert "York" in calls[0]["inputs"]["messages"][0]["content"]

    def test_a_node_with_no_tools_refuses_the_call(self, envelope):
        """A misconfiguration inside an item ends the run, rather than being collected.

        It was wrong before the run started, so it is the node's failure and not this
        item's, and an evaluation over a fanned-out node would otherwise pay for every
        rollout to be told the same thing k x n times.
        """

        def build(inputs, ctx):
            return ctx.call_tool("look_up", name="a")

        pipeline = Pipeline(
            [Deterministic(load), LLMNode(build, output_schema=Answer, over="documents")],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        client = FakeModelClient(responses=[fake_response(content=FOUND)])

        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({"documents": ["a"]}, envelope=envelope, model=client, run_id=RUN_ID)

        assert "declared no tools" in str(exc.value)

    def test_one_item_of_many_failing_its_schema_is_still_collected(self, envelope):
        """The narrower rule: a bare CallerFacingError is one item's, and stays collected."""
        client = FakeModelClient(
            responses=[
                fake_response(content="not json"),
                fake_response(content=FOUND),
            ]
        )

        result = pipeline_over().run(
            {"documents": ["a", "b"]},
            envelope=envelope,
            run_id=RUN_ID,
            model=client,
            seed=41,
        )

        assert [outcome.ok for outcome in result.output.outcomes] == [False, True]

    def test_a_tool_taking_a_model_handle_is_refused_at_construction(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def rewrite(text: str, model: ModelHandle) -> str:
            """Rewrite text. Returns the rewritten text."""
            return text

        with pytest.raises(ConfigurationError) as caught:
            LLMNode(summarise, output_schema=Answer, tools=[rewrite])

        assert "which takes a ModelHandle" in str(caught.value)
        assert "LLMNode node" in str(caught.value)

    def test_a_tool_whose_parameter_is_called_name_is_reachable(self, envelope):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def greet(name: str) -> str:
            """Greet someone by name. Returns the greeting."""
            return f"hello {name}"

        def build(inputs, ctx):
            # The tool's name is positional, so `name=` is the tool's own argument.
            return ctx.call_tool("greet", name=inputs["documents"])

        pipeline = Pipeline(
            [
                Deterministic(load),
                LLMNode(build, output_schema=Answer, tools=[greet], over="documents"),
            ],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        client = FakeModelClient(responses=[fake_response(content=FOUND)])

        result = pipeline.run(
            {"documents": ["ada"]}, envelope=envelope, model=client, run_id=RUN_ID
        )

        assert result.output.outcomes[0].ok


class TestWatchingAFanOutItemByItem:
    """A fan-out hands its whole result on when the last item is done.

    Without a per-item event a caller writing each item as it lands has nothing to write on,
    and a serial pass over a long sequence runs for minutes having written nothing.
    """

    def test_each_item_announces_itself_as_it_finishes(self, envelope):
        seen: list[tuple[str, int | None, bool]] = []

        def watch(event):
            seen.append((event.phase, event.item_index, event.error is not None))

        pipeline = Pipeline(
            [Deterministic(load), Deterministic(parse_one, over="documents")],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

        pipeline.run({"documents": ["a", "b"]}, envelope=envelope, run_id=RUN_ID, on_progress=watch)

        items = [e for e in seen if e[0] == "item"]
        assert items == [("item", 0, False), ("item", 1, False)]
        # A caller counting nodes still counts nodes.
        assert [e[1] for e in seen if e[0] == "completed"] == [None, None]

    def test_a_failed_item_announces_its_error(self, envelope):
        seen = []

        def watch(event):
            if event.phase == "item":
                seen.append((event.item_index, event.error is not None))

        def parse_or_raise(inputs, ctx):
            if inputs["documents"] == "b":
                raise ValueError("no")
            return inputs["documents"]

        pipeline = Pipeline(
            [Deterministic(load), Deterministic(parse_or_raise, over="documents")],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

        pipeline.run(
            {"documents": ["a", "b", "c"]},
            envelope=envelope,
            run_id=RUN_ID,
            on_progress=watch,
        )

        assert seen == [(0, False), (1, True), (2, False)]

    def test_a_node_that_does_not_fan_out_announces_no_items(self, envelope):
        seen = []

        def count_them(inputs, ctx):
            return {"seen": len(inputs["documents"])}

        pipeline = Pipeline(
            [Deterministic(load), Deterministic(count_them)],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

        pipeline.run(
            {"documents": ["a"]},
            envelope=envelope,
            run_id=RUN_ID,
            on_progress=lambda e: seen.append(e.phase),
        )

        assert "item" not in seen
