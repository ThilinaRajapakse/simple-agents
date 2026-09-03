"""A pipeline a model may hand a subtask to.

An `AgentNode` delegates by calling tools, so a model cannot choose a decomposition of its own
unless a whole pipeline is on offer. What is checked here is that the delegate is declared
rather than hidden behind a tool body: every walk that reasons about what a pipeline can reach
sees it, the eval runner's refusal included.

Nothing in this file makes a live model call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    BudgetExceeded,
    ConfigurationError,
    Delegation,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Maybe,
    Pipeline,
    RunEnvelope,
    RunSuspended,
    SideEffectClass,
    Suspend,
    ToolCallRequest,
    ToolRegistry,
    fake_response,
    tool,
)
from simple_agents.builtins import consult
from simple_agents.evaluation.runner import _tools_of
from simple_agents.tools import DeclaredCost

from conftest import run_path, RUN_ID


class Subtask(BaseModel):
    """One question to research."""

    question: str


class Notes(BaseModel):
    text: Maybe[str]


class Report(BaseModel):
    summary: Maybe[str]


def _budget(**axes) -> Budget:
    return Budget(
        **{
            "max_steps": None,
            "max_tokens": None,
            "max_cost": None,
            "max_wall_clock_ms": None,
            **axes,
        }
    )


def _widen(inputs: Subtask, ctx) -> str:
    return f"Find out: {inputs.question}"


def _research(**axes) -> Pipeline:
    """A worker: one deterministic node and one model call."""
    return Pipeline(
        [
            Deterministic(_widen, node_id="widen"),
            LLMNode(
                lambda inputs, ctx: Prompt.user("{given}", given=inputs),
                output_schema=Notes,
                node_id="hunt",
            ),
        ],
        budget=_budget(**axes),
        node_id="research",
    )


def _orchestrator(delegate: Delegation, **kwargs) -> Pipeline:
    node = AgentNode(
        lambda inputs, ctx: Prompt.user(
            "Plan the work. Available: {describe_tools}", describe_tools=ctx.describe_tools()
        ),
        tools=kwargs.pop("tools", []),
        delegates=[delegate],
        output_schema=Report,
        budget=kwargs.pop("budget", _budget(max_steps=10)),
        node_id="orchestrate",
    )
    return Pipeline([node], budget=_budget(), **kwargs)


def _delegating(*questions: str) -> list:
    """Responses for a turn delegating each question, then finishing."""
    return [
        fake_response(
            tool_calls=[
                ToolCallRequest(id=f"d{i}", name="research", arguments={"question": q})
                for i, q in enumerate(questions)
            ]
        ),
        *[fake_response(content=json.dumps({"text": f"note on {q}"})) for q in questions],
        fake_response(
            tool_calls=[ToolCallRequest(id="f", name="finish", arguments={"summary": "done"})]
        ),
    ]


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _of_type(path: Path, kind: str) -> list[dict]:
    return [r for r in _records(path) if r["record_type"] == kind]


class TestWhatTheDeclarationRefuses:
    """Every refusal is at construction, before a run has spent anything."""

    def test_a_pipeline_with_no_node_id_is_refused(self):
        worker = Pipeline([Deterministic(_widen, node_id="widen")], budget=_budget())
        with pytest.raises(ConfigurationError) as caught:
            Delegation(worker, description="Research one question.")
        assert "node_id" in str(caught.value)

    def test_an_empty_description_is_refused(self):
        with pytest.raises(ConfigurationError) as caught:
            Delegation(_research(), description="   ")
        assert "prompt text" in str(caught.value)
        assert "FT-23" in str(caught.value)

    def test_an_entry_node_that_declares_no_type_is_refused(self):
        """The model fills the arguments in, so it has to be shown a schema."""
        worker = Pipeline(
            [Deterministic(lambda inputs, ctx: inputs, node_id="widen")],
            budget=_budget(),
            node_id="research",
        )
        with pytest.raises(ConfigurationError) as caught:
            Delegation(worker, description="Research one question.", max_calls=2)
        assert "'widen'" in str(caught.value)
        assert "pydantic model" in str(caught.value)

    def test_a_worker_that_calls_no_model_needs_a_call_ceiling(self):
        """max_steps counts model calls, so it does not bound a worker that makes none."""
        worker = Pipeline(
            [Deterministic(_widen, node_id="widen")], budget=_budget(), node_id="research"
        )
        with pytest.raises(ConfigurationError) as caught:
            Delegation(worker, description="Research one question.")
        assert "max_calls" in str(caught.value)
        assert "FT-18" in str(caught.value)

    def test_a_worker_that_calls_a_model_does_not(self):
        assert Delegation(_research(), description="Research one.").max_calls is None

    def test_something_that_is_not_a_delegation_is_refused(self):
        with pytest.raises(ConfigurationError, match="Each entry is a Delegation"):
            AgentNode(
                lambda inputs, ctx: Prompt.user("plan"),
                tools=[],
                delegates=[_research()],
                output_schema=Report,
                budget=_budget(max_steps=4),
                node_id="orchestrate",
            )

    def test_two_delegations_sharing_a_name_are_refused(self):
        with pytest.raises(ConfigurationError, match="more than one delegation named"):
            AgentNode(
                lambda inputs, ctx: Prompt.user("plan"),
                tools=[],
                delegates=[
                    Delegation(_research(), description="Research one."),
                    Delegation(_research(), description="Research another."),
                ],
                output_schema=Report,
                budget=_budget(max_steps=4),
                node_id="orchestrate",
            )

    def test_a_delegation_that_may_never_be_sent_is_refused(self):
        with pytest.raises(ConfigurationError) as caught:
            Delegation(_research(), description="Research one.", max_calls=0)
        assert "max_calls=1 or more" in str(caught.value)

    def test_suspend_before_on_a_delegate_is_refused(self):
        """It is read by the walk of a graph, and a delegate is in none."""
        worker = Pipeline(
            [
                Deterministic(_widen, node_id="widen"),
                LLMNode(
                    lambda i, c: Prompt.user("{given}", given=i),
                    output_schema=Notes,
                    node_id="hunt",
                ),
            ],
            budget=_budget(),
            node_id="research",
            suspend_before=True,
        )
        with pytest.raises(ConfigurationError) as caught:
            Delegation(worker, description="Research one.")
        assert "suspend_before" in str(caught.value)

    def test_a_name_shared_with_a_tool_is_refused(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="research")
        def clash(query: str) -> str:
            """Search."""
            return ""

        with pytest.raises(ConfigurationError) as caught:
            AgentNode(
                lambda i, c: Prompt.user("go"),
                tools=[clash],
                delegates=[Delegation(_research(), description="Research one.")],
                output_schema=Report,
                budget=_budget(max_steps=4),
                node_id="orchestrate",
            )
        assert "'research'" in str(caught.value)
        assert "ambiguous" in str(caught.value)

    def test_a_pipeline_that_delegates_to_itself_is_refused(self):
        def plan(inputs: Subtask, ctx) -> str:
            return Prompt.user("go")

        node = AgentNode(
            plan,
            tools=[],
            output_schema=Report,
            budget=_budget(max_steps=4),
            node_id="orchestrate",
        )
        outer = Pipeline([node], budget=_budget(), node_id="outer")
        node.delegates = [Delegation(outer, description="Do it again.", max_calls=2)]
        with pytest.raises(ConfigurationError) as caught:
            outer.declared_nodes()
        assert "itself" in str(caught.value)


class TestTheEvalRunnerSeesInsideADelegate:
    """The eval runner's refusal reads what a rollout can reach, not what a node holds (FT-19)."""

    def _paid_worker(self) -> Pipeline:
        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=DeclaredCost(currency="USD", per_call=0.005),
        )
        def paid_search(query: str) -> str:
            """Search the web. Costs money."""
            return "results"

        def hunt(inputs: Subtask, ctx) -> str:
            return ctx.call_tool("paid_search", query=inputs.question)

        return Pipeline(
            [Deterministic(hunt, tools=[paid_search], node_id="hunt")],
            budget=_budget(),
            node_id="research",
        )

    def test_a_paid_tool_inside_a_delegate_is_reachable(self):
        pipeline = _orchestrator(
            Delegation(self._paid_worker(), description="Research one.", max_calls=2)
        )
        assert [t.name for t in _tools_of(pipeline)] == ["paid_search"]

    def test_its_nodes_record_under_ids_the_manifest_declares(self):
        pipeline = _orchestrator(
            Delegation(self._paid_worker(), description="Research one.", max_calls=2)
        )
        assert [n for n, _ in pipeline.declared_nodes()] == [
            "orchestrate",
            "orchestrate.research.hunt",
        ]

    def test_a_registry_given_to_a_delegate_reaches_the_currency_refusal(self):
        """A tool declared one level down is checked on the same terms as one at the top."""

        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=DeclaredCost(currency="JPY", per_call=1.0),
        )
        def in_yen(query: str) -> str:
            """Search."""
            return ""

        @tool(
            side_effect_class=SideEffectClass.SPENDS_MONEY,
            declared_cost=DeclaredCost(currency="USD", per_call=0.01),
        )
        def in_dollars(query: str) -> str:
            """Search."""
            return ""

        worker = Pipeline(
            [
                Deterministic(_widen, node_id="widen"),
                LLMNode(
                    lambda i, c: Prompt.user("{given}", given=i),
                    output_schema=Notes,
                    node_id="hunt",
                ),
            ],
            budget=_budget(),
            node_id="research",
            tools=ToolRegistry([in_yen]),
        )
        pipeline = _orchestrator(
            Delegation(worker, description="Research one."), tools=ToolRegistry([in_dollars])
        )
        with pytest.raises(ConfigurationError) as caught:
            pipeline.run({}, model=FakeModelClient(responses=[]))
        assert "more than one currency" in str(caught.value)


class TestWhatTheModelIsShown:
    def test_the_delegation_is_offered_under_the_pipelines_node_id(self):
        delegation = Delegation(_research(), description="Research one question.")
        assert delegation.to_wire()["name"] == "research"
        assert delegation.to_wire()["description"] == "Research one question."

    def test_the_arguments_are_the_entry_nodes_type(self):
        schema = Delegation(_research(), description="Research one.").to_wire()["input_schema"]
        assert list(schema["properties"]) == ["question"]
        assert schema["required"] == ["question"]

    def test_it_reaches_the_backend_beside_the_tools(self, tmp_path):
        client = FakeModelClient(responses=_delegating("who won?"))
        _orchestrator(Delegation(_research(), description="Research one.")).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client
        )
        offered = [t["name"] for t in client.requests[0].tools]
        assert offered == ["research", "finish"]

    def test_arguments_that_do_not_validate_come_back_to_the_model(self, tmp_path):
        """A malformed subtask is the model's to correct, not the run's to die on."""
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="d0", name="research", arguments={"topic": "x"})]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="f", name="finish", arguments={"summary": "gave up"})
                    ]
                ),
            ]
        )
        result = _orchestrator(Delegation(_research(), description="Research one.")).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client
        )
        record = _of_type(result.trajectory_path, "delegation")[0]
        assert record["termination"] == "rejected"
        assert record["outputs"] is None
        assert result.output.summary == "gave up"


class TestWhatTheTrajectoryShows:
    def _ran(self, tmp_path, *questions: str):
        client = FakeModelClient(responses=_delegating(*questions))
        return _orchestrator(Delegation(_research(), description="Research one.")).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client
        )

    def test_each_subtask_is_one_delegation_record(self, tmp_path):
        result = self._ran(tmp_path, "who won?", "when?")
        records = _of_type(result.trajectory_path, "delegation")
        assert [r["invocation"] for r in records] == [1, 2]
        assert [r["node_id"] for r in records] == ["orchestrate.research"] * 2
        assert [r["inputs"]["question"] for r in records] == ["who won?", "when?"]

    def test_the_node_ids_repeat_and_the_parent_separates_them(self, tmp_path):
        """A node id names the node; the record separating two invocations is the parent."""
        result = self._ran(tmp_path, "who won?", "when?")
        delegations = _of_type(result.trajectory_path, "delegation")
        nodes = _of_type(result.trajectory_path, "node_execution")

        inside = [n for n in nodes if n["node_id"].startswith("orchestrate.research.")]
        assert [n["node_id"] for n in inside] == [
            "orchestrate.research.widen",
            "orchestrate.research.hunt",
        ] * 2
        assert {n["parent_id"] for n in inside} == {d["record_id"] for d in delegations}

    def test_a_delegation_is_parented_to_the_node_whose_model_sent_it(self, tmp_path):
        result = self._ran(tmp_path, "who won?")
        agent = next(
            n
            for n in _of_type(result.trajectory_path, "node_execution")
            if n["node_id"] == "orchestrate"
        )
        assert agent["parent_id"] is None
        delegation = _of_type(result.trajectory_path, "delegation")[0]
        assert delegation["parent_id"] == agent["record_id"]

    def test_a_parent_is_written_after_its_children(self, tmp_path):
        result = self._ran(tmp_path, "who won?")
        delegation = _of_type(result.trajectory_path, "delegation")[0]
        inside = [
            r
            for r in _records(result.trajectory_path)
            if r.get("parent_id") == delegation["record_id"]
        ]
        assert inside
        assert all(r["sequence"] < delegation["sequence"] for r in inside)

    def test_it_carries_the_shape_it_ran(self, tmp_path):
        result = self._ran(tmp_path, "who won?")
        record = _of_type(result.trajectory_path, "delegation")[0]
        assert record["graph_fingerprint"] == _research().graph_fingerprint()

    def test_a_node_reached_along_an_edge_has_no_parent(self, tmp_path):
        """A pipeline used as a node emits no record, so its children have nothing to name."""
        worker = _research()
        pipeline = Pipeline(
            [worker, Deterministic(lambda i, c: i, node_id="write")], budget=_budget()
        )
        client = FakeModelClient(responses=[fake_response(content='{"text": "x"}')])
        result = pipeline.run(
            Subtask(question="who won?"),
            envelope=RunEnvelope(run_dir=tmp_path),
            model=client,
        )
        assert all(
            n["parent_id"] is None for n in _of_type(result.trajectory_path, "node_execution")
        )


class TestAFailedNodeStaysInsideItsDelegation:
    def test_an_errored_node_execution_names_the_delegation_that_contains_it(self, tmp_path):
        """`parent_id` is carried on an error record too, so a subtask's failed nodes group
        with it (`docs/trajectory-format.md` §2)."""

        def breaks(inputs: Subtask, ctx) -> str:
            raise ValueError("the corpus is gone")

        worker = Pipeline(
            [
                Deterministic(breaks, node_id="widen"),
                LLMNode(
                    lambda inputs, ctx: Prompt.user("{given}", given=inputs),
                    output_schema=Notes,
                    node_id="hunt",
                ),
            ],
            budget=_budget(),
            node_id="research",
        )
        client = FakeModelClient(responses=_delegating("who won?"))
        with pytest.raises(ValueError):
            _orchestrator(Delegation(worker, description="Research one.")).run(
                {}, envelope=RunEnvelope(run_dir=tmp_path), model=client
            )
        [trajectory] = Path(tmp_path).glob("**/trajectory.jsonl")
        [errored] = [
            n
            for n in _of_type(trajectory, "node_execution")
            if n["node_id"] == "orchestrate.research.widen"
        ]
        assert errored["termination"] == "error"
        # The delegation record itself is absent here: a parent is written after its
        # children, and this run died before it landed. What the record guarantees is the
        # link, which an errored execution once recorded as null.
        assert errored["parent_id"] is not None
        others = {r["record_id"] for r in _records(trajectory)}
        assert errored["parent_id"] not in others


class TestWhatBoundsIt:
    def test_what_a_delegate_spends_counts_against_the_calling_nodes_budget(self, tmp_path):
        """One step is one model call, wherever it was made."""
        client = FakeModelClient(responses=_delegating("a", "b"))
        result = _orchestrator(Delegation(_research(), description="Research one.")).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client
        )
        agent = next(
            n
            for n in _of_type(result.trajectory_path, "node_execution")
            if n["node_id"] == "orchestrate"
        )
        assert agent["termination"] == "finish"
        # Two turns of the orchestrator plus one call inside each of the two subtasks.
        assert len(_of_type(result.trajectory_path, "model_call")) == 4

    def test_max_steps_on_the_calling_node_stops_the_delegating(self, tmp_path):
        """Four steps: one turn, two subtasks, one more turn, and then it is spent."""
        client = FakeModelClient(
            responses=[
                *_delegating("a", "b")[:3],
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="d2", name="research", arguments={"question": "c"})
                    ]
                ),
                fake_response(content='{"text": "note on c"}'),
            ]
        )
        result = _orchestrator(
            Delegation(_research(), description="Research one."),
            budget=_budget(max_steps=5),
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client)
        agent = next(
            n
            for n in _of_type(result.trajectory_path, "node_execution")
            if n["node_id"] == "orchestrate"
        )
        assert agent["termination"] == "max_steps"

    def test_max_calls_is_model_facing_and_the_run_continues(self, tmp_path):
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="d0", name="research", arguments={"question": "a"})
                    ]
                ),
                fake_response(content='{"text": "note"}'),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="d1", name="research", arguments={"question": "b"})
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="f", name="finish", arguments={"summary": "one"})
                    ]
                ),
            ]
        )
        result = _orchestrator(
            Delegation(_research(), description="Research one.", max_calls=1)
        ).run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client)
        assert result.output.summary == "one"
        assert len(_of_type(result.trajectory_path, "delegation")) == 1
        refusal = client.requests[-1].messages[-1]["content"]
        assert "which is its limit" in refusal

    def test_the_delegates_own_budget_is_model_facing(self, tmp_path):
        """The model chose the subtask, so it is the one that decides what to do next."""
        client = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="d0", name="research", arguments={"question": "a"})
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="f", name="finish", arguments={"summary": "none"})
                    ]
                ),
            ]
        )
        result = _orchestrator(Delegation(_research(max_steps=0), description="Research one.")).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client
        )
        record = _of_type(result.trajectory_path, "delegation")[0]
        assert record["termination"] == "budget"
        assert result.output.summary == "none"

    def test_the_runs_budget_ends_the_run(self, tmp_path):
        """The run's budget is not the model's to work around."""
        client = FakeModelClient(responses=_delegating("a", "b"))
        node = AgentNode(
            lambda inputs, ctx: Prompt.user("Plan."),
            tools=[],
            delegates=[Delegation(_research(), description="Research one.")],
            output_schema=Report,
            budget=_budget(max_steps=10),
            node_id="orchestrate",
        )
        pipeline = Pipeline([node], budget=_budget(max_steps=1))
        with pytest.raises(BudgetExceeded) as caught:
            pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client)
        assert caught.value.axis == "max_steps"


class TestSuspensionInsideADelegate:
    """A worker consulting the end user stops the whole run and continues where it stopped."""

    def _pipeline(self, channel) -> Pipeline:
        registry = ToolRegistry([consult(channel, answered_by="end_user")])
        worker = Pipeline(
            [
                Deterministic(_widen, node_id="widen"),
                AgentNode(
                    lambda inputs, ctx: Prompt.user("Find it."),
                    tools=registry,
                    output_schema=Notes,
                    budget=_budget(max_steps=6),
                    node_id="hunt",
                ),
            ],
            budget=_budget(),
            node_id="research",
        )
        return _orchestrator(Delegation(worker, description="Research one question."))

    def _client(self) -> FakeModelClient:
        return FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="d0", name="research", arguments={"question": "fit?"})
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c1", name="consult", arguments={"question": "slim or straight?"}
                        )
                    ]
                ),
            ]
        )

    def _unavailable(self, question, options, about=None):
        raise Suspend(waiting_for=question)

    def test_it_stops_the_whole_run(self, envelope):
        with pytest.raises(RunSuspended) as caught:
            self._pipeline(self._unavailable).run(
                {}, envelope=envelope, model=self._client(), run_id=RUN_ID
            )
        assert caught.value.waiting_for == "slim or straight?"

    def test_both_agent_nodes_keep_their_own_conversation(self, envelope, tmp_path):
        """One frame per level: the orchestrator's subtask and the worker's question."""
        with pytest.raises(RunSuspended):
            self._pipeline(self._unavailable).run(
                {}, envelope=envelope, model=self._client(), run_id=RUN_ID
            )
        state = json.loads(run_path(tmp_path, RUN_ID, "suspension.json").read_text())
        # Two pipeline levels, and both hold a conversation: the outer one's orchestrator is
        # waiting on the subtask, and the worker's `hunt` is waiting on the end user. One
        # `node_state` for the whole run could carry only one of them. The state is a tree,
        # so the level below hangs off the node that stopped inside it.
        outer = state["frames"][0]
        assert list(outer["in_progress"]) == ["orchestrate"]
        assert outer["node_state"]["orchestrate"]["pending"]["name"] == "research"
        inner = outer["below"]["orchestrate"][0]
        assert list(inner["in_progress"]) == ["hunt"]
        assert inner["node_state"]["hunt"]["pending"]["name"] == "consult"

    def test_a_resume_finishes_the_subtask_and_then_the_report(self, envelope):
        pipeline = self._pipeline(self._unavailable)
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, model=self._client(), run_id=RUN_ID)

        rest = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments={"text": "slim"})]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="f", name="finish", arguments={"summary": "slim fits"})
                    ]
                ),
            ]
        )
        result = pipeline.resume(RUN_ID, envelope=envelope, model=rest, answer="slim")
        assert result.output.summary == "slim fits"

    def test_the_two_halves_of_one_subtask_are_linked(self, envelope):
        pipeline = self._pipeline(self._unavailable)
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, model=self._client(), run_id=RUN_ID)
        rest = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[ToolCallRequest(id="c2", name="finish", arguments={"text": "slim"})]
                ),
                fake_response(
                    tool_calls=[ToolCallRequest(id="f", name="finish", arguments={"summary": "ok"})]
                ),
            ]
        )
        result = pipeline.resume(RUN_ID, envelope=envelope, model=rest, answer="slim")
        records = _of_type(result.trajectory_path, "delegation")
        assert [r["termination"] for r in records] == ["suspended", "completed"]
        assert records[0]["ended_at"] is None
        assert records[1]["resumed_from"] == records[0]["record_id"]

    def test_a_rewired_delegate_is_refused_on_resume(self, envelope):
        pipeline = self._pipeline(self._unavailable)
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=envelope, model=self._client(), run_id=RUN_ID)

        moved = self._pipeline(self._unavailable)
        moved.nodes[0].delegates[0].pipeline.nodes.append(
            Deterministic(lambda i, c: i, node_id="extra")
        )
        moved.nodes[0].delegates[0].pipeline.graph = type(
            moved.nodes[0].delegates[0].pipeline.graph
        )(moved.nodes[0].delegates[0].pipeline.nodes)
        with pytest.raises(Exception) as caught:
            moved.resume(RUN_ID, envelope=envelope, model=self._client(), answer="slim")
        assert "different shape" in str(caught.value)


class TestWhatTheManifestSays:
    def test_the_delegate_is_a_container_with_no_edges(self, tmp_path):
        result = _orchestrator(Delegation(_research(), description="Research one.")).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(responses=_delegating("a")),
        )
        entry = result.manifest["containers"][0]
        assert entry["node_id"] == "orchestrate.research"
        assert entry["nodes"] == ["orchestrate.research.widen", "orchestrate.research.hunt"]
        assert entry["successors"] == []
        assert entry["route"] is None
        assert entry["reached_by"]["kind"] == "delegation"
        assert entry["reached_by"]["node_id"] == "orchestrate"

    def test_the_leaves_are_in_nodes_and_the_container_is_not(self, tmp_path):
        result = _orchestrator(Delegation(_research(), description="Research one.")).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(responses=_delegating("a")),
        )
        assert [n["node_id"] for n in result.manifest["nodes"]] == [
            "orchestrate",
            "orchestrate.research.widen",
            "orchestrate.research.hunt",
        ]

    def test_the_call_ceiling_is_recorded(self, tmp_path):
        result = _orchestrator(
            Delegation(_research(), description="Research one.", max_calls=3)
        ).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(responses=_delegating("a")),
        )
        assert result.manifest["containers"][0]["reached_by"]["max_calls"] == 3

    def test_rewording_the_description_moves_no_fingerprint(self):
        """Prompt text is traced the way a prompt is, not as a change of shape."""
        one = _orchestrator(Delegation(_research(), description="Research one."))
        two = _orchestrator(Delegation(_research(), description="Research a question."))
        assert one.graph_fingerprint() == two.graph_fingerprint()

    def test_moving_the_delegate_to_another_node_does(self):
        one = _orchestrator(Delegation(_research(), description="Research one."))
        node = AgentNode(
            lambda inputs, ctx: Prompt.user("Plan."),
            tools=[],
            delegates=[Delegation(_research(), description="Research one.")],
            output_schema=Report,
            budget=_budget(max_steps=10),
            node_id="planner",
        )
        two = Pipeline([node], budget=_budget())
        assert one.graph_fingerprint() != two.graph_fingerprint()


class TestPerNodeMetrics:
    def test_the_delegating_node_counts_its_subtasks(self, tmp_path):
        from simple_agents.evaluation.per_node import per_node

        result = _orchestrator(Delegation(_research(), description="Research one.")).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(responses=_delegating("a", "b")),
        )
        found = per_node([_records(result.trajectory_path)])
        assert found["orchestrate"].delegations == 2

    def test_a_worker_node_keeps_its_own_executions(self, tmp_path):
        """Two invocations of one node id are two executions of it, as in a bounded cycle."""
        from simple_agents.evaluation.per_node import per_node

        result = _orchestrator(Delegation(_research(), description="Research one.")).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(responses=_delegating("a", "b")),
        )
        found = per_node([_records(result.trajectory_path)])
        assert found["orchestrate.research.hunt"].executions == 2
        assert found["orchestrate.research.hunt"].model_calls == 2
        assert found["orchestrate"].model_calls == 2


class TestSeeingTheShape:
    def test_a_delegate_is_drawn_with_the_edge_that_reaches_it(self):
        drawn = _orchestrator(
            Delegation(_research(), description="Research one.", max_calls=4)
        ).to_mermaid()
        assert 'orchestrate_research[["orchestrate.research<br/><i>pipeline</i>"]]' in drawn
        assert "orchestrate -.->|delegates, up to 4x| orchestrate_research" in drawn

    def test_an_unbounded_delegation_says_so(self):
        drawn = _orchestrator(Delegation(_research(), description="Research one.")).to_mermaid()
        assert "orchestrate -.->|delegates| orchestrate_research" in drawn
