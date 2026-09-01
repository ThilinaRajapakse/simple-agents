"""A tool that reads the node's own input, through the `NodeInput` handle.

Dogfood #5 withdrew an `AgentNode` because its retrieval tools needed the viewer's ranked
pool, which reaches the node on an edge and is in neither the tool's key nor a handle. Closing
over the value instead reaches whatever the closure was built with, and `EvalSuite` builds one
pipeline for every rollout, so every rollout would have searched the same thing.

`TestEveryRolloutSeesItsOwn` is the test a closure would fail. The rest is the contract
around it: the parameter is not in the schema the model is shown, the tool is re-run rather
than served from the cassette, and a key the node was not handed is refused.
"""

from __future__ import annotations

import json
import re
from typing import Annotated

import pytest
from pydantic import BaseModel

from simple_agents import (
    AgentContext,
    AgentNode,
    Budget,
    Cassette,
    ConfigurationError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    NodeContext,
    NodeInput,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    read_trajectory,
    tool,
)
from simple_agents.evaluation import Example, ExampleSet
from simple_agents.evaluation.runner import EvalSuite
from simple_agents.models import ToolCallRequest, fake_response

BUDGET = Budget(max_steps=8, max_tokens=100_000, max_cost=None, max_wall_clock_ms=60_000)


class Answer(BaseModel):
    titles: list[str]


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def rank(query: str, pool: Annotated[list[dict], NodeInput("pool")]) -> list[str]:
    """Rank this node's pool against a query. Returns the titles that match."""
    return [row["title"] for row in pool if query.lower() in row["title"].lower()]


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def keys_of(given: Annotated[dict, NodeInput]) -> str:
    """The keys the node was handed, comma separated."""
    return ",".join(sorted(given))


def tool_calls_in(path) -> list[dict]:
    return [r for r in read_trajectory(path) if r["record_type"] == "tool_call"]


# -- what the model is shown ---------------------------------------------------------------


class TestTheParameterIsNotOfferedToTheModel:
    """The model chooses the query. It is never shown the pool, and cannot pass one."""

    def test_the_schema_holds_only_what_the_model_supplies(self):
        assert sorted(rank.parameters["properties"]) == ["query"]
        assert rank.parameters["required"] == ["query"]

    def test_a_model_passing_it_is_handed_back_the_names_it_may_use(self):
        assert rank._accepts == frozenset({"query"})

    def test_the_key_is_read_off_the_annotation(self):
        assert rank.handles == {"pool": NodeInput}
        assert rank.node_inputs == {"pool": "pool"}

    def test_no_key_reads_the_whole_input(self):
        assert keys_of.handles == {"given": NodeInput}
        assert keys_of.node_inputs == {"given": None}

    def test_a_tool_built_by_hand_with_no_key_reads_the_whole_input(self, tmp_path):
        """`node_inputs` is optional on a `Tool` constructed directly, and absent means whole."""
        from simple_agents import Tool

        def body(given: Annotated[dict, NodeInput]) -> str:
            return ",".join(sorted(given))

        built = Tool(
            name="by_hand",
            description="The keys the node was handed.",
            parameters={"type": "object", "properties": {}, "required": []},
            side_effect_class=SideEffectClass.READ_ONLY,
            fn=body,
            handles={"given": NodeInput},
        )
        assert built.node_inputs == {}
        assert built.re_executed is True

        def call_it(inputs, ctx: NodeContext) -> dict:
            return {"seen": ctx.call_tool("by_hand")}

        pipeline = Pipeline(
            [Deterministic(call_it, node_id="one", tools=[built], successors=[])],
            budget=BUDGET,
        )
        result = pipeline.run({"a": 1, "b": 2}, envelope=RunEnvelope(run_dir=tmp_path))
        assert result.output == {"seen": "a,b"}


class TestWhatSectionThreeTwoSaysAboutTheSet:
    """The counts and the table in `docs/tools.md` §3.2, against the tuples they describe.

    `NodeInput` is the seventh handle and the fifth that re-runs, so both numbers moved. A
    count spelled in prose with nothing reading it is what went wrong twice before: the
    taxonomy's index tally and the skill's per-stage question counts.
    """

    SPELLED = {"five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}

    @property
    def text(self) -> str:
        from simple_agents import docs_path

        whole = (docs_path() / "tools.md").read_text(encoding="utf-8")
        return whole.split("### 3.2 A tool that takes a handle")[1].split("### 3.3")[0]

    def test_the_number_of_handles_it_names_is_the_number_there_are(self):
        from simple_agents.tools import HANDLE_TYPES

        found = re.search(r"There are (\w+)\.", self.text)

        assert found, "docs/tools.md §3.2 no longer says how many handles there are"
        assert self.SPELLED[found.group(1)] == len(HANDLE_TYPES)

    def test_the_number_it_says_are_re_run_is_the_number_that_are(self):
        from simple_agents.tools import HANDLE_TYPES, RE_EXECUTED_HANDLE_TYPES

        found = re.search(r"\*\*(\w+) of the (\w+) stop the tool being stored", self.text)

        assert found, "docs/tools.md §3.2 no longer says how many handles re-run"
        assert self.SPELLED[found.group(1).lower()] == len(RE_EXECUTED_HANDLE_TYPES)
        assert self.SPELLED[found.group(2).lower()] == len(HANDLE_TYPES)

    def test_the_table_holds_one_row_per_handle_and_says_which_re_run(self):
        from simple_agents.tools import HANDLE_TYPES, RE_EXECUTED_HANDLE_TYPES

        rows = dict(re.findall(r"^\| `(\w+)` \| .*? \| (yes|no) \|$", self.text, re.MULTILINE))

        assert set(rows) == {kind.__name__ for kind in HANDLE_TYPES}
        re_run = {kind.__name__ for kind in RE_EXECUTED_HANDLE_TYPES}
        assert {name for name, says in rows.items() if says == "yes"} == re_run


# -- the three node kinds ------------------------------------------------------------------


class TestEachNodeKindFillsItFromItsOwnInput:
    """A tool the node calls itself, and one the model chose, are filled the same way."""

    def test_a_deterministic_node(self, tmp_path):
        def body(inputs: dict, ctx: NodeContext) -> dict:
            return {"found": ctx.call_tool("rank", query=inputs["query"])}

        pipeline = Pipeline(
            [Deterministic(body, node_id="one", tools=[rank], successors=[])], budget=BUDGET
        )
        result = pipeline.run(
            {"pool": [{"title": "Blue Train"}, {"title": "Red Rock"}], "query": "blue"},
            envelope=RunEnvelope(run_dir=tmp_path),
        )
        assert result.output == {"found": ["Blue Train"]}

    def test_an_llm_node(self, tmp_path):
        def prompt(inputs: dict, ctx: NodeContext) -> str:
            return f"Found: {ctx.call_tool('rank', query=inputs['query'])}"

        model = FakeModelClient(responses=[fake_response(content='{"titles": ["Red Rock"]}')])
        pipeline = Pipeline(
            [
                LLMNode(
                    prompt,
                    output_schema=Answer,
                    node_id="one",
                    tools=[rank],
                    allow_unknown=False,
                    successors=[],
                )
            ],
            budget=BUDGET,
        )
        pipeline.run(
            {"pool": [{"title": "Blue Train"}, {"title": "Red Rock"}], "query": "red"},
            model=model,
            envelope=RunEnvelope(run_dir=tmp_path),
        )
        assert model.requests[0].messages[-1]["content"] == "Found: ['Red Rock']"

    def test_an_agent_node_where_the_model_chose_the_call(self, tmp_path):
        def prompt(inputs: dict, ctx: AgentContext) -> str:
            return f"Search it. Tools: {ctx.describe_tools()}"

        model = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="1", name="rank", arguments={"query": "red"})]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="2", name="finish", arguments={"titles": ["Red Rock"]})
                    ]
                ),
            ]
        )
        pipeline = Pipeline(
            [
                AgentNode(
                    prompt,
                    tools=[rank],
                    output_schema=Answer,
                    node_id="one",
                    allow_unknown=False,
                    budget=BUDGET,
                    successors=[],
                )
            ],
            budget=BUDGET,
        )
        result = pipeline.run(
            {"pool": [{"title": "Blue Train"}, {"title": "Red Rock"}]},
            model=model,
            envelope=RunEnvelope(run_dir=tmp_path),
        )
        assert result.output.titles == ["Red Rock"]
        called = [c for c in tool_calls_in(result.trajectory_path) if c["tool_name"] == "rank"]
        assert called[0]["outputs"] == ["Red Rock"]
        assert called[0]["inputs"] == {"query": "red"}

    def test_a_fanned_out_node_reads_the_item_under_the_over_key(self, tmp_path):
        """`over=` replaces that key with the one item, so the tool asks for the same key."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def title_of(row: Annotated[dict, NodeInput("rows")]) -> str:
            """The title of the row this item is over."""
            return row["title"]

        def body(inputs: dict, ctx: NodeContext) -> dict:
            return {"seen": ctx.call_tool("title_of")}

        pipeline = Pipeline(
            [Deterministic(body, node_id="each", over="rows", tools=[title_of], successors=[])],
            budget=BUDGET,
        )
        result = pipeline.run(
            {"rows": [{"title": "A"}, {"title": "B"}], "unrelated": 1},
            envelope=RunEnvelope(run_dir=tmp_path),
        )
        assert [outcome.value for outcome in result.output] == [{"seen": "A"}, {"seen": "B"}]


class TestTheFourShapesANodesInputTakes:
    """`docs/pipeline.md` §3: one edge, none, a `Join`, or a `NodeFailure`. Each reaches here."""

    def test_a_join_names_the_node_a_value_came_from(self, tmp_path):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def read_hunt(found: Annotated[dict, NodeInput("hunt")]) -> str:
            """What the `hunt` edge carried."""
            return found["title"]

        def hunt(inputs, ctx: NodeContext) -> dict:
            return {"title": "Red Rock"}

        def verify(inputs, ctx: NodeContext) -> dict:
            return {"checked": True}

        def report(inputs, ctx: NodeContext) -> dict:
            return {"seen": ctx.call_tool("read_hunt")}

        pipeline = Pipeline(
            [
                Deterministic(
                    hunt,
                    node_id="hunt",
                    successors=["verify", "report"],
                    route=lambda output, ctx: ["verify", "report"],
                ),
                Deterministic(verify, node_id="verify", successors=["report"]),
                Deterministic(report, node_id="report", tools=[read_hunt], successors=[]),
            ],
            budget=BUDGET,
        )
        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))
        assert result.output == {"seen": "Red Rock"}

    def test_a_node_failure_has_no_keys_and_is_read_whole(self, tmp_path):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def why(failure: Annotated[object, NodeInput]) -> str:
            """Why the node before this one failed."""
            return failure.error["message"]

        def breaks(inputs, ctx: NodeContext) -> dict:
            raise ValueError("the source was empty")

        def handle(inputs, ctx: NodeContext) -> dict:
            return {"because": ctx.call_tool("why")}

        pipeline = Pipeline(
            [
                Deterministic(breaks, node_id="breaks", successors=[], on_error="handle"),
                Deterministic(handle, node_id="handle", tools=[why], successors=[]),
            ],
            budget=BUDGET,
        )
        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))
        assert result.output == {"because": "the source was empty"}

    def test_a_key_on_a_node_failure_is_refused(self, tmp_path):
        """`has no keys` is only checkable where naming one is refused."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="named_key")
        def named(rows: Annotated[list, NodeInput("rows")]) -> str:
            """Read a key off whatever the node was handed."""
            return str(rows)

        def breaks(inputs, ctx: NodeContext) -> dict:
            raise ValueError("the source was empty")

        def handle(inputs, ctx: NodeContext) -> dict:
            return {"n": ctx.call_tool("named_key")}

        pipeline = Pipeline(
            [
                Deterministic(breaks, node_id="breaks", successors=[], on_error="handle"),
                Deterministic(handle, node_id="handle", tools=[named], successors=[]),
            ],
            budget=BUDGET,
        )
        with pytest.raises(ConfigurationError) as raised:
            pipeline.run({"rows": []}, envelope=RunEnvelope(run_dir=tmp_path))
        assert "was handed a NodeFailure, which has no keys" in str(raised.value)

    def test_an_edge_that_did_not_fire_reaches_the_tool_as_an_unknown(self, tmp_path):
        """A `Join` key is every declared in-edge, so one that did not fire is still a key."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def read_verify(found: Annotated[object, NodeInput("verify")]) -> str:
            """What the `verify` edge carried."""
            return type(found).__name__

        def hunt(inputs, ctx: NodeContext) -> dict:
            return {"title": "Red Rock"}

        def verify(inputs, ctx: NodeContext) -> dict:
            return {"checked": True}

        def report(inputs, ctx: NodeContext) -> dict:
            return {"seen": ctx.call_tool("read_verify")}

        pipeline = Pipeline(
            [
                Deterministic(
                    hunt,
                    node_id="hunt",
                    successors=["verify", "report"],
                    route=lambda output, ctx: "report",
                ),
                Deterministic(verify, node_id="verify", successors=["report"]),
                Deterministic(report, node_id="report", tools=[read_verify], successors=[]),
            ],
            budget=BUDGET,
        )
        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))
        assert result.output == {"seen": "Unknown"}

    def test_a_fanned_out_llm_node_reads_its_own_item(self, tmp_path):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def title_of(row: Annotated[dict, NodeInput("rows")]) -> str:
            """The title of the row this item is over."""
            return row["title"]

        def prompt(inputs, ctx: NodeContext) -> str:
            return f"Report {ctx.call_tool('title_of')}."

        model = FakeModelClient(
            answer=lambda request: fake_response(
                content=json.dumps({"titles": [request.messages[-1]["content"]]})
            )
        )
        pipeline = Pipeline(
            [
                LLMNode(
                    prompt,
                    output_schema=Answer,
                    node_id="each",
                    over="rows",
                    tools=[title_of],
                    allow_unknown=False,
                    successors=[],
                )
            ],
            budget=BUDGET,
        )
        result = pipeline.run(
            {"rows": [{"title": "A"}, {"title": "B"}]},
            model=model,
            envelope=RunEnvelope(run_dir=tmp_path),
        )
        assert [o.value.titles[0] for o in result.output] == ["Report A.", "Report B."]


# -- what the cassette does with it ---------------------------------------------------------


class TestTheToolIsReRunRatherThanStored:
    """The node's input is not in the call's key, so a stored answer would cross rollouts."""

    def test_it_joins_the_re_executed_handles(self):
        assert rank.re_executed is True
        assert keys_of.re_executed is True

    @staticmethod
    def _searching_then_answering() -> Pipeline:
        """A node that searches its own pool, then one whose prompt is the same every run.

        The model call is what the cassette stores, and holding its prompt constant is what
        lets the same file replay a run handed a different pool.
        """

        def search(inputs: dict, ctx: NodeContext) -> dict:
            return {"found": ctx.call_tool("rank", query="r")}

        def prompt(inputs: dict, ctx: NodeContext) -> str:
            return "Report what was found."

        return Pipeline(
            [
                Deterministic(search, node_id="search", tools=[rank], successors=["report"]),
                LLMNode(
                    prompt,
                    output_schema=Answer,
                    node_id="report",
                    allow_unknown=False,
                    successors=[],
                ),
            ],
            budget=BUDGET,
        )

    @staticmethod
    def _model() -> FakeModelClient:
        return FakeModelClient(responses=[fake_response(content='{"titles": []}')])

    def test_a_recorded_run_stores_the_model_call_and_no_entry_for_the_tool(self, tmp_path):
        path = tmp_path / "c.jsonl"
        result = self._searching_then_answering().run(
            {"pool": [{"title": "Red Rock"}]},
            model=self._model(),
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(path)),
        )
        call = tool_calls_in(result.trajectory_path)[0]
        assert call["tool_name"] == "rank"
        assert call["re_executed"] is True
        assert call["cassette_key"] is None
        kinds = [json.loads(line)["kind"] for line in path.read_text().splitlines()]
        assert kinds == ["model_call"]

    def test_a_replay_runs_the_body_over_that_runs_own_input(self, tmp_path):
        """The recorded run saw one pool, the replay another, and each answer is its own."""
        path = tmp_path / "c.jsonl"
        pipeline = self._searching_then_answering()
        recorded = pipeline.run(
            {"pool": [{"title": "Red Rock"}]},
            model=self._model(),
            envelope=RunEnvelope(run_dir=tmp_path / "live", cassette=Cassette.record(path)),
        )
        assert tool_calls_in(recorded.trajectory_path)[0]["outputs"] == ["Red Rock"]

        replayed = pipeline.run(
            {"pool": [{"title": "Green River"}]},
            model=self._model(),
            envelope=RunEnvelope(run_dir=tmp_path / "replay", cassette=Cassette.replay(path)),
        )
        call = tool_calls_in(replayed.trajectory_path)[0]
        assert call["outputs"] == ["Green River"]
        assert call["replayed"] is False

    def test_a_tool_that_spends_cannot_take_one(self):
        with pytest.raises(ConfigurationError) as raised:

            @tool(
                side_effect_class=SideEffectClass.IRREVERSIBLE,
                name="place_order",
            )
            def place(given: Annotated[dict, NodeInput]) -> str:
                """Place the order the node was handed."""
                return "placed"

        assert "NodeInput" in str(raised.value)
        assert "re-run during replay" in str(raised.value)


# -- the evaluation, which is where the closure fails ---------------------------------------


class TestEveryRolloutSeesItsOwn:
    """One pipeline, many examples. A closure would give every rollout the same pool."""

    def test_each_example_is_ranked_against_its_own_pool(self, tmp_path):
        def prompt(inputs: dict, ctx: NodeContext) -> str:
            return f"Ranked: {ctx.call_tool('rank', query='a')}"

        class Ranked(BaseModel):
            titles: list[str]

        def echo(request):
            return fake_response(content=json.dumps({"titles": [request.messages[-1]["content"]]}))

        pipeline = Pipeline(
            [
                LLMNode(
                    prompt,
                    output_schema=Ranked,
                    node_id="one",
                    tools=[rank],
                    allow_unknown=False,
                    successors=[],
                )
            ],
            budget=BUDGET,
        )
        examples = ExampleSet(
            [
                Example(
                    id="one",
                    inputs={"pool": [{"title": "Aardvark"}]},
                    expected="Ranked: ['Aardvark']",
                    split="held_out",
                ),
                Example(
                    id="two",
                    inputs={"pool": [{"title": "Anchor"}]},
                    expected="Ranked: ['Anchor']",
                    split="held_out",
                ),
            ]
        )
        results = EvalSuite(
            pipeline,
            examples,
            answer=lambda output: output.titles[0],
            matches=lambda scored: scored.answer == scored.expected,
        ).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(answer=echo),
            split="held_out",
            k=1,
            seed=7,
        )
        answered = {r.example_id: r.answer for r in results.rollouts}
        assert answered == {"one": "Ranked: ['Aardvark']", "two": "Ranked: ['Anchor']"}


# -- what it refuses -------------------------------------------------------------------------


class TestWhatItRefuses:
    """Each refusal names the call that fixes it."""

    def test_the_marker_as_the_parameters_own_type(self):
        with pytest.raises(ConfigurationError) as raised:

            @tool(side_effect_class=SideEffectClass.READ_ONLY, name="bare")
            def body(given: NodeInput) -> str:
                """Read the input."""
                return ""

        assert "Annotated[list[dict], NodeInput('pool')]" in str(raised.value)

    def test_a_key_on_an_input_with_no_keys(self, tmp_path):
        def body(inputs, ctx: NodeContext) -> dict:
            return {"found": ctx.call_tool("rank", query="blue")}

        pipeline = Pipeline(
            [Deterministic(body, node_id="one", tools=[rank], successors=[])], budget=BUDGET
        )
        with pytest.raises(ConfigurationError) as raised:
            pipeline.run([1, 2, 3], envelope=RunEnvelope(run_dir=tmp_path))
        assert "was handed a list, which has no keys" in str(raised.value)
        assert "Annotated[<type>, NodeInput]" in str(raised.value)

    def test_a_key_the_node_was_not_handed(self, tmp_path):
        def body(inputs, ctx: NodeContext) -> dict:
            return {"found": ctx.call_tool("rank", query="blue")}

        pipeline = Pipeline(
            [Deterministic(body, node_id="one", tools=[rank], successors=[])], budget=BUDGET
        )
        with pytest.raises(ConfigurationError) as raised:
            pipeline.run({"catalogue": []}, envelope=RunEnvelope(run_dir=tmp_path))
        assert "an input carrying 'catalogue'" in str(raised.value)
