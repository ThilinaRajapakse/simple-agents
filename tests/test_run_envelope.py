"""The run envelope end to end: manifest, seeds, cassette, redaction, cost.

A run leaves a directory that a later reader can interpret without the code that produced it.
These tests drive a real pipeline and read what it wrote.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import ANY

import pytest

from simple_agents import (
    AgentNode,
    Budget,
    Cassette,
    CassetteMiss,
    ComputeBasis,
    ConfigurationError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Loop,
    ModelIdentity,
    PriceBasis,
    Pipeline,
    Redaction,
    RetryPolicy,
    RunEnvelope,
    SideEffectClass,
    Tool,
    ToolRegistry,
    Unknown,
    read_trajectory,
)
from simple_agents.records.manifest import Manifest, source_version
from simple_agents.models import ToolCallRequest, fake_response

from conftest import run_path, RUN_ID
from schemas import Answer

PRICE = PriceBasis(currency="USD", input_uncached_per_mtok=3.00, output_per_mtok=15.00)


def build_prompt(inputs, ctx):
    return f"Answer the question: {inputs.get('question', 'how long?')}"


def one_llm_pipeline() -> Pipeline:
    return Pipeline(
        [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None),
    )


def two_llm_pipeline() -> Pipeline:
    return Pipeline(
        [
            LLMNode(build_prompt, output_schema=Answer, node_id="extract"),
            LLMNode(lambda inputs, ctx: "Confirm it.", output_schema=Answer, node_id="confirm"),
        ],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None),
    )


def client_with(*payloads: str) -> FakeModelClient:
    return FakeModelClient(responses=[fake_response(content=p) for p in payloads])


ANSWER = '{"answer": "32 inches", "source": "size chart"}'


def read_manifest(path: Path) -> dict:
    return json.loads(path.read_text())


class TestRunDirectory:
    def test_a_run_writes_a_manifest_a_trajectory_and_a_workspace(self, envelope, run_root) -> None:
        result = one_llm_pipeline().run(
            {}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER)
        )

        assert result.paths.root == run_root
        assert result.paths.manifest.exists()
        assert result.paths.trajectory.exists()
        assert result.paths.workspace.is_dir()

    def test_the_workspace_is_what_a_node_receives(self, envelope, run_root) -> None:
        seen: list[Path] = []

        def look(inputs, ctx):
            seen.append(ctx.workspace)
            return inputs

        Pipeline([Deterministic(look)]).run({}, envelope=envelope, run_id=RUN_ID)

        assert seen == [run_root / "workspace"]

    def test_two_runs_do_not_share_a_directory(self, envelope) -> None:
        first = one_llm_pipeline().run({}, envelope=envelope, model=client_with(ANSWER))
        second = one_llm_pipeline().run({}, envelope=envelope, model=client_with(ANSWER))

        assert first.paths.root != second.paths.root

    def test_running_without_an_envelope_still_records(self, tmp_path, monkeypatch) -> None:
        # The default envelope writes under `runs/`, so a first run records without the
        # builder configuring anything.
        monkeypatch.chdir(tmp_path)

        result = one_llm_pipeline().run({}, model=client_with(ANSWER))

        assert result.paths.manifest.exists()
        assert result.paths.root.resolve().parent.parent.parent == (tmp_path / "runs").resolve()


class TestManifest:
    def test_restore_keeps_the_recording_rate(self) -> None:
        """A resumed run's manifest states the envelope's rate, not the default."""
        manifest = Manifest(
            run_id="run_x",
            started_at="t",
            seed=1,
            budget={},
            library_version="0",
            trajectory_path="t.jsonl",
            workspace_path="ws",
            recording={"payload_rate": 0.01, "payloads": "kept"},
        )

        restored = Manifest.restore(manifest.to_json())

        assert restored.recording == {"payload_rate": 0.01, "payloads": "kept"}

    def test_it_records_the_pin_the_client_reports(self, envelope, manifest_path) -> None:
        client = client_with(ANSWER)
        client.model_identity = ModelIdentity(
            backend="self_hosted", request_model="Qwen/Qwen3-8B", model_revision="a1b2c3d"
        )

        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client)

        configured = read_manifest(manifest_path)["models"]["configured"]
        assert configured == {
            "backend": "self_hosted",
            "request_model": "Qwen/Qwen3-8B",
            "model_revision": "a1b2c3d",
        }

    def test_it_records_what_actually_served_each_call(self, envelope, manifest_path) -> None:
        # A provider can substitute. A manifest showing only the request would not say so.
        client = FakeModelClient(
            responses=[fake_response(content=ANSWER, request_model="asked-for")]
        )
        client.responses[0].response_model = "served-instead"

        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client)

        observed = read_manifest(manifest_path)["models"]["observed"]
        assert observed[0]["request_model"] == "asked-for"
        assert observed[0]["response_model"] == "served-instead"
        assert observed[0]["calls"] == 1

    def test_it_records_the_node_shape_and_the_unknown_waivers(
        self, envelope, manifest_path
    ) -> None:
        pipeline = Pipeline(
            [
                Deterministic(lambda inputs, ctx: inputs, node_id="load"),
                LLMNode(build_prompt, output_schema=Answer, node_id="extract"),
            ],
            budget=Budget(max_steps=None, max_tokens=1000, max_cost=None, max_wall_clock_ms=None),
        )

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        nodes = read_manifest(manifest_path)["nodes"]
        versioned = nodes[0].pop("fn")
        assert nodes[0] == {
            "node_id": "load",
            "node_kind": "deterministic",
            "successors": ["extract"],
            "route": None,
            "consultation_route": None,
            "loop": None,
            "on_error": None,
            "retry": None,
            "schema": None,
            "accepts": None,
            "tools": [],
            "planned": False,
            "touches": [],
        }
        # A `Deterministic` node's whole behaviour is its function, so the manifest versions it
        # the way it versions a prompt. Nothing else on the entry moves when the body is edited.
        assert versioned["source"] == "derived"
        assert versioned["version"].startswith("sha256:")
        assert nodes[1] == {
            "node_id": "extract",
            "node_kind": "llm",
            "successors": [],
            "route": None,
            "consultation_route": None,
            "loop": None,
            "on_error": None,
            "retry": None,
            "schema": ANY,
            "accepts": None,
            "planned": False,
            "touches": [],
            "allow_unknown": True,
            "context_builder": {"name": "AppendAll", "config": {"max_input_tokens": None}},
            "stream": False,
            # Null because this node declares no client of its own and takes the run's.
            "model": None,
            "sampling": {"temperature": None, "max_output_tokens": None, "extra": {}},
            "tools": [],
            "finish_check": None,
            "node_budget": None,
            "node_budget_per_item": None,
            "fan_out": {"over": None, "keep": [], "max_failures": None},
        }

    def test_it_records_what_a_node_declared_beyond_its_shape(
        self, envelope, manifest_path
    ) -> None:
        """The sampling parameters, the tools and the budget one node offered.

        A pipeline-wide tool list cannot say a tool was removed from one node while another
        still declares it, and nothing recorded a temperature before this.
        """
        pipeline = Pipeline(
            [
                AgentNode(
                    build_prompt,
                    tools=[
                        Tool(
                            name="look_up",
                            description="Search the catalogue. Returns matching entries.",
                            parameters={
                                "type": "object",
                                "properties": {"query": {"type": "string"}},
                                "required": ["query"],
                            },
                            side_effect_class=SideEffectClass.READ_ONLY,
                            fn=lambda query: "nothing",
                        )
                    ],
                    output_schema=Answer,
                    budget=Budget(
                        max_steps=4, max_tokens=500, max_cost=None, max_wall_clock_ms=None
                    ),
                    node_id="hunt",
                    temperature=0.2,
                    max_output_tokens=64,
                    finish_check=lambda answer, ctx: None,
                ),
            ],
            budget=Budget(max_steps=None, max_tokens=1000, max_cost=None, max_wall_clock_ms=None),
        )

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=_agent_client())

        entry = read_manifest(manifest_path)["nodes"][0]
        assert entry["sampling"] == {
            "temperature": 0.2,
            "max_output_tokens": 64,
            "extra": {},
        }
        assert entry["tools"] == ["look_up"]
        assert entry["node_budget"]["max_steps"] == 4
        assert entry["finish_check"]["version"].startswith("sha256:")

    def test_it_records_the_declared_graph(self, envelope, manifest_path) -> None:
        """A routing change moves which nodes run, so the manifest carries the edges."""
        pipeline = Pipeline(
            [
                Deterministic(
                    lambda inputs, ctx: inputs,
                    node_id="load",
                    successors=["extract", "give_up"],
                    route=lambda output, ctx: "extract",
                    on_error="give_up",
                    retry=RetryPolicy(attempts=2, backoff_ms=5),
                ),
                LLMNode(build_prompt, output_schema=Answer, node_id="extract"),
                Deterministic(lambda inputs, ctx: inputs, node_id="give_up", successors=[]),
            ],
            budget=Budget(max_steps=None, max_tokens=1000, max_cost=None, max_wall_clock_ms=None),
        )

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        load = read_manifest(manifest_path)["nodes"][0]
        assert load["successors"] == ["extract", "give_up"]
        assert load["on_error"] == "give_up"
        assert load["retry"] == {"attempts": 2, "backoff_ms": 5}
        assert load["route"]["source"] == "derived"
        assert load["route"]["version"].startswith("sha256:")

    def test_it_records_a_bounded_cycle(self, envelope, manifest_path) -> None:
        pipeline = Pipeline(
            [
                Deterministic(lambda inputs, ctx: inputs, node_id="draft"),
                Deterministic(
                    lambda inputs, ctx: inputs,
                    node_id="critique",
                    successors=["draft", "publish"],
                    route=lambda output, ctx: "publish",
                    loop=Loop(max_iterations=3, then="publish"),
                ),
                Deterministic(lambda inputs, ctx: inputs, node_id="publish", successors=[]),
            ],
            budget=Budget.unbounded(),
        )

        pipeline.run({}, envelope=envelope, run_id=RUN_ID)

        critique = read_manifest(manifest_path)["nodes"][1]
        assert critique["loop"] == {"max_iterations": 3, "then": "publish"}

    def test_a_declared_prompt_version_is_recorded_as_declared(
        self, envelope, manifest_path
    ) -> None:
        pipeline = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract", prompt_version="v3")],
            budget=Budget(max_steps=None, max_tokens=1000, max_cost=None, max_wall_clock_ms=None),
        )

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        recorded = read_manifest(manifest_path)["prompts"]["extract"]
        assert recorded["version"] == "v3"
        assert recorded["source"] == "declared"
        # The hash is recorded under a declared version too, so an edit made without moving the
        # declaration is visible to anything comparing two runs. Only `version` is digested.
        assert recorded["derived"].startswith("sha256:")

    def test_an_undeclared_prompt_version_is_derived_from_the_source(
        self, envelope, manifest_path
    ) -> None:
        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        recorded = read_manifest(manifest_path)["prompts"]["extract"]
        assert recorded["source"] == "derived"
        assert recorded["version"].startswith("sha256:")

    def test_it_records_the_tools_and_their_side_effect_classes(
        self, envelope, manifest_path
    ) -> None:
        pipeline = _agent_pipeline(_search_tool([]))

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=_finishing_client())

        tools = read_manifest(manifest_path)["tools"]
        assert tools[0].pop("derived").startswith("sha256:")
        assert tools == [
            {
                "name": "look_up",
                "version": "1",
                "side_effect_class": "read_only",
                "declared_cost": None,
                "touches": [],
                "re_executed": False,
                "offered": True,
                "answered_by": None,
                "reaches": None,
                "permission": None,
                "reader": None,
                "mcp": None,
            }
        ]

    def test_it_records_a_tool_the_project_declared_and_no_node_was_given(
        self, envelope, manifest_path
    ) -> None:
        """`offered: false` is a tool that was declared and cannot be called.

        The registry is where a project states its whole tool surface, and a tool no node
        holds reaches the manifest through it and through nothing else.
        """
        offered, spare = _search_tool([]), _search_tool([], name="spare")
        pipeline = _agent_pipeline(offered, registry=ToolRegistry([offered, spare]))

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=_finishing_client())

        tools = read_manifest(manifest_path)["tools"]
        assert [(t["name"], t["offered"]) for t in tools] == [
            ("look_up", True),
            ("spare", False),
        ]

    def test_it_counts_the_records_written(self, envelope, manifest_path) -> None:
        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        counts = read_manifest(manifest_path)["counts"]
        assert counts == {
            "records": 3,
            "run_start": 1,
            "node_execution": 1,
            "model_call": 1,
            "tool_call": 0,
            "consultation": 0,
            "delegation": 0,
            "resource_access": 0,
        }

    def test_it_totals_the_token_breakdown(self, envelope, manifest_path) -> None:
        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        assert read_manifest(manifest_path)["totals"]["tokens"] == {
            "input_uncached": 10,
            "input_cache_read": 0,
            "input_cache_write": 0,
            "output": 5,
        }

    def test_it_totals_the_time_the_run_spent_held_back(self, envelope, manifest_path) -> None:
        """Retry backoff and pacing are on each call; a run that mostly waited needs the sum."""
        held = [fake_response(content=ANSWER), fake_response(content=ANSWER)]
        for response, waited in zip(held, (1000, 7000)):
            response.held_back_ms = waited

        two_llm_pipeline().run(
            {}, envelope=envelope, run_id=RUN_ID, model=FakeModelClient(responses=held)
        )

        assert read_manifest(manifest_path)["totals"]["held_back_ms"] == 8000

    def test_a_run_that_never_waited_reports_zero_rather_than_nothing(
        self, envelope, manifest_path
    ) -> None:
        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        assert read_manifest(manifest_path)["totals"]["held_back_ms"] == 0

    def test_an_unknown_token_count_makes_that_total_unknown(self, envelope, manifest_path) -> None:
        # A backend that does not report cached prefix tokens leaves the total unknown rather
        # than reporting a figure lower than what was consumed.
        response = fake_response(content=ANSWER)
        response.tokens = _UnreportedCacheTokens()  # type: ignore[assignment]

        one_llm_pipeline().run(
            {}, envelope=envelope, run_id=RUN_ID, model=FakeModelClient(responses=[response])
        )

        totals = read_manifest(manifest_path)["totals"]["tokens"]
        assert totals["input_cache_read"] == {
            "type": "unknown",
            "reason": "not reported by the backend",
        }

    def test_it_names_the_trajectory_it_belongs_to(self, envelope, manifest_path) -> None:
        result = one_llm_pipeline().run(
            {}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER)
        )

        manifest = read_manifest(manifest_path)
        assert manifest["run_id"] == RUN_ID
        assert manifest["paths"]["trajectory"] == str(result.paths.trajectory)
        assert manifest["trajectory_format_version"] == "0.29"

    def test_it_records_a_completed_run_as_completed(self, envelope, manifest_path) -> None:
        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        manifest = read_manifest(manifest_path)
        assert manifest["outcome"] == "completed"
        assert manifest["ended_at"] is not None

    def test_a_crashed_run_still_leaves_a_manifest(self, envelope, manifest_path) -> None:
        def explode(inputs, ctx):
            raise RuntimeError("no")

        with pytest.raises(RuntimeError):
            Pipeline([Deterministic(explode)]).run({}, envelope=envelope, run_id=RUN_ID)

        assert read_manifest(manifest_path)["outcome"] == "error"


class TestVersioningAFunctionBuiltByAFactory:
    """A closure has the source of whatever its factory returns, which never varies.

    Versioning on source alone gave two routes sending a run to different nodes one version,
    so an edit to the mapping was traced to nothing (FT-15). What it closed over counts too.
    """

    @staticmethod
    def _road(mapping):
        def route(output, ctx):
            return mapping[output]

        return route

    def test_two_closures_over_different_data_get_different_versions(self):
        one = source_version(self._road({"yes": "apply"}))
        other = source_version(self._road({"yes": "stop"}))

        assert one["source"] == "derived"
        assert one != other

    def test_the_same_data_gets_the_same_version(self):
        assert source_version(self._road({"yes": "apply"})) == source_version(
            self._road({"yes": "apply"})
        )

    def test_a_plain_function_is_versioned_on_its_source_alone(self):
        def route(output, ctx):
            return "verify"

        assert source_version(route)["version"].startswith("sha256:")

    def test_closing_over_an_object_stays_stable(self):
        """`repr` of most objects carries a memory address, which differs every process.

        Including one would make a version that changes when nothing did, which is worse than
        the defect being fixed, so only data whose text its value fixes is counted.
        """

        class Client:
            pass

        def over(client):
            def route(output, ctx):
                return client

            return route

        assert source_version(over(Client())) == source_version(over(Client()))

    def test_two_closures_over_different_paths_get_different_versions(self):
        """A `Path` is data whose text its value fixes, and it was rendered as its type name.

        Two lookups reading different files recorded one version, so an edit that changed which
        file a rule read was traced to nothing. A `str` path was already counted, so the same
        two lookups versioned apart or together depending on the type they were handed.
        """
        from pathlib import Path

        def lookup(path):
            def check(scoring):
                return path

            return check

        assert source_version(lookup(Path("evals/a.jsonl"))) != source_version(
            lookup(Path("evals/b.jsonl"))
        )

    def test_a_path_and_the_same_path_as_a_string_agree(self):
        """They name one file, so a rule reading it is the same rule either way."""
        from pathlib import Path

        def lookup(path):
            def check(scoring):
                return path

            return check

        assert source_version(lookup(Path("evals/a.jsonl"))) == source_version(
            lookup("evals/a.jsonl")
        )

    def test_a_consultation_route_is_versioned_by_what_it_maps(self):
        from simple_agents.builtins import on_reply

        one = on_reply({"yes": "apply", "no": "stop"}, exhaustive=True)
        other = on_reply({"yes": "stop", "no": "apply"}, exhaustive=True)

        assert source_version(one) != source_version(other)


class TestSeeds:
    def test_a_seed_is_generated_and_recorded_when_none_is_given(
        self, envelope, manifest_path
    ) -> None:
        result = one_llm_pipeline().run(
            {}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER)
        )

        assert isinstance(result.seed, int)
        assert read_manifest(manifest_path)["seed"] == result.seed

    def test_the_call_seed_is_derived_from_the_run_seed(self, envelope, trajectory) -> None:
        one_llm_pipeline().run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41, model=client_with(ANSWER)
        )

        calls = [r for r in read_trajectory(trajectory) if r["record_type"] == "model_call"]
        assert calls[0]["seed"] != 41
        assert isinstance(calls[0]["seed"], int)

    def test_the_same_run_seed_reproduces_the_same_call_seeds(self, envelope) -> None:
        seeds = []
        for _ in range(2):
            result = one_llm_pipeline().run(
                {}, envelope=envelope, seed=41, model=client_with(ANSWER)
            )
            seeds.append(
                [
                    r["seed"]
                    for r in read_trajectory(result.trajectory_path)
                    if r["record_type"] == "model_call"
                ]
            )

        assert seeds[0] == seeds[1]

    def test_calls_within_one_node_get_distinct_seeds(self, envelope, trajectory) -> None:
        pipeline = _agent_pipeline(_search_tool([]))

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, seed=41, model=_searching_client())

        seeds = [r["seed"] for r in read_trajectory(trajectory) if r["record_type"] == "model_call"]
        assert len(seeds) == len(set(seeds)) == 2

    def test_a_deterministic_node_still_records_no_seed(self, envelope, trajectory) -> None:
        Pipeline([Deterministic(lambda inputs, ctx: inputs, node_id="load")]).run(
            {}, envelope=envelope, run_id=RUN_ID, seed=41
        )

        node = next(r for r in read_trajectory(trajectory) if r["record_type"] == "node_execution")
        assert node["seed"] is None


class TestCassette:
    def test_recording_then_replaying_reproduces_the_run(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        recording = RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path))
        live = one_llm_pipeline().run({}, envelope=recording, seed=41, model=client_with(ANSWER))

        replaying = RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path))
        replayed = one_llm_pipeline().run(
            {}, envelope=replaying, seed=41, model=FakeModelClient(responses=[])
        )

        assert replayed.output.answer == live.output.answer

    def test_a_run_recorded_at_a_generated_seed_replays_without_being_given_one(
        self, tmp_path
    ) -> None:
        """The seed a run generates is part of every model-call key, so a replay that cannot
        reach it cannot replay anything the run recorded."""
        cassette_path = tmp_path / "cassette.jsonl"
        live = one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            model=client_with(ANSWER),
        )

        replayed = one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)),
            model=FakeModelClient(responses=[]),
        )

        assert replayed.seed == live.seed
        assert replayed.output.answer == live.output.answer

    def test_a_seed_that_is_passed_is_the_one_used(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )

        with pytest.raises(CassetteMiss) as raised:
            one_llm_pipeline().run(
                {},
                envelope=RunEnvelope(
                    run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)
                ),
                seed=7,
                model=FakeModelClient(responses=[]),
            )

        assert "run seed 41" in str(raised.value)

    def test_a_cassette_holding_several_seeds_is_refused_rather_than_guessed_at(
        self, tmp_path
    ) -> None:
        """One file per evaluation holds a rollout per seed, and no one of them is the run."""
        cassette_path = tmp_path / "cassette.jsonl"
        for seed in (41, 7):
            one_llm_pipeline().run(
                {},
                envelope=RunEnvelope(
                    run_dir=tmp_path / f"rec{seed}", cassette=Cassette.update(cassette_path)
                ),
                seed=seed,
                model=client_with(ANSWER),
            )

        with pytest.raises(ConfigurationError) as raised:
            one_llm_pipeline().run(
                {},
                envelope=RunEnvelope(
                    run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)
                ),
                model=FakeModelClient(responses=[]),
            )

        message = str(raised.value)
        assert "2 runs at different seeds" in message
        assert "seed=" in message

    def test_updating_takes_the_seed_the_file_was_recorded_at(self, tmp_path) -> None:
        """The mode re-runs only what changed, which needs the unchanged calls to hit."""
        cassette_path = tmp_path / "cassette.jsonl"
        live = one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            model=client_with(ANSWER),
        )

        offline = FakeModelClient(responses=[])
        updated = one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "upd", cassette=Cassette.update(cassette_path)),
            model=offline,
        )

        assert updated.seed == live.seed
        assert offline.requests == []

    def test_a_run_that_records_nothing_still_generates_a_seed(self, tmp_path) -> None:
        first = one_llm_pipeline().run(
            {}, envelope=RunEnvelope(run_dir=tmp_path / "a"), model=client_with(ANSWER)
        )
        second = one_llm_pipeline().run(
            {}, envelope=RunEnvelope(run_dir=tmp_path / "b"), model=client_with(ANSWER)
        )

        assert first.seed != second.seed

    def test_replay_makes_no_call_on_the_client(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )

        # No scripted responses: the client raises if the run reaches it.
        offline = FakeModelClient(responses=[])
        one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)),
            seed=41,
            model=offline,
        )

        assert offline.requests == []

    def test_the_trajectory_says_which_calls_were_replayed(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        live = one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )
        replayed = one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)),
            seed=41,
            model=FakeModelClient(responses=[]),
        )

        recorded_call = _first_model_call(live.trajectory_path)
        replayed_call = _first_model_call(replayed.trajectory_path)

        # A key is present on both: the live call was recorded into the cassette.
        assert recorded_call["cassette_key"] == replayed_call["cassette_key"]
        assert recorded_call["replayed"] is False
        assert replayed_call["replayed"] is True

    def test_a_prompt_edit_between_record_and_replay_is_reported(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        one_llm_pipeline().run(
            {"question": "how long?"},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )

        with pytest.raises(CassetteMiss) as exc:
            one_llm_pipeline().run(
                {"question": "how long is it, in centimetres?"},
                envelope=RunEnvelope(
                    run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)
                ),
                seed=41,
                model=FakeModelClient(responses=[]),
            )

        message = str(exc.value)
        assert "node 'extract'" in message
        assert "messages[0].content" in message
        assert "Cassette.record(" in message

    def test_a_different_seed_does_not_replay_the_recorded_response(self, tmp_path) -> None:
        # The seed is part of the key, so a rollout at another seed is a different call.
        cassette_path = tmp_path / "cassette.jsonl"
        one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )

        with pytest.raises(CassetteMiss):
            one_llm_pipeline().run(
                {},
                envelope=RunEnvelope(
                    run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)
                ),
                seed=99,
                model=FakeModelClient(responses=[]),
            )

    def test_a_model_change_does_not_replay_the_previous_model(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )

        upgraded = FakeModelClient(responses=[])
        upgraded.model_identity = ModelIdentity(
            backend="self_hosted", request_model="Qwen/Qwen3-32B", model_revision="ffffff"
        )

        with pytest.raises(CassetteMiss):
            one_llm_pipeline().run(
                {},
                envelope=RunEnvelope(
                    run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)
                ),
                seed=41,
                model=upgraded,
            )

    def test_tool_calls_replay_too(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        executions: list[str] = []

        live = _agent_pipeline(_search_tool(executions)).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=_searching_client(),
        )
        assert executions == ["inseam"]

        replayed = _agent_pipeline(_search_tool(executions)).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)),
            seed=41,
            model=_searching_client(),
        )

        # The tool did not run a second time, and the answer is the same.
        assert executions == ["inseam"]
        assert replayed.output.answer == live.output.answer
        tool_call = next(
            r
            for r in read_trajectory(replayed.trajectory_path)
            if r["record_type"] == "tool_call" and r["tool_name"] == "look_up"
        )
        assert tool_call["replayed"] is True

    def test_replaying_a_cassette_that_does_not_exist_is_refused(self, tmp_path) -> None:
        envelope = RunEnvelope(
            run_dir=tmp_path, cassette=Cassette.replay(tmp_path / "absent.jsonl")
        )

        with pytest.raises(ConfigurationError, match="does not exist"):
            one_llm_pipeline().run({}, envelope=envelope, model=client_with(ANSWER))

    def test_the_manifest_counts_hits_and_recordings(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        live = one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )
        replayed = one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette_path)),
            seed=41,
            model=FakeModelClient(responses=[]),
        )

        assert read_manifest(live.manifest_path)["cassette"]["recorded"] == 1
        assert read_manifest(replayed.manifest_path)["cassette"]["hits"] == 1


class TestUpdateMode:
    """Served where there is an entry, called live and recorded where there is not.

    What separates this from the ordinal fallback rejected at item 4 is that a recorded
    response is never served for a request it was not recorded against. An edited prompt
    hashes to a key with no entry, so it is answered live rather than from the old entry.
    """

    def test_an_entry_on_file_is_served_without_reaching_the_client(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )

        offline = FakeModelClient(responses=[])
        result = one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "upd", cassette=Cassette.update(cassette_path)),
            seed=41,
            model=offline,
        )

        assert offline.requests == []
        assert result.output.answer == "32 inches"
        assert _first_model_call(result.trajectory_path)["replayed"] is True

    def test_an_edited_prompt_is_answered_live_rather_than_from_the_old_entry(
        self, tmp_path
    ) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        one_llm_pipeline().run(
            {"question": "how long?"},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )

        fresh = client_with('{"answer": "34 inches", "source": "size chart"}')
        result = one_llm_pipeline().run(
            {"question": "how wide?"},
            envelope=RunEnvelope(run_dir=tmp_path / "upd", cassette=Cassette.update(cassette_path)),
            seed=41,
            model=fresh,
        )

        assert result.output.answer == "34 inches"
        assert len(fresh.requests) == 1
        assert _first_model_call(result.trajectory_path)["replayed"] is False

    def test_the_new_call_joins_the_file_and_the_old_entry_stays(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        one_llm_pipeline().run(
            {"question": "how long?"},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )
        one_llm_pipeline().run(
            {"question": "how wide?"},
            envelope=RunEnvelope(run_dir=tmp_path / "upd", cassette=Cassette.update(cassette_path)),
            seed=41,
            model=client_with('{"answer": "34 inches", "source": "size chart"}'),
        )

        assert len(Cassette.replay(cassette_path).variants()) == 2

    def test_the_manifest_says_the_mode_and_counts_the_hit_and_the_miss(self, tmp_path) -> None:
        """A run that made live calls under this mode is visible in both counts."""
        cassette_path = tmp_path / "cassette.jsonl"
        one_llm_pipeline().run(
            {"question": "how long?"},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )

        hit = one_llm_pipeline().run(
            {"question": "how long?"},
            envelope=RunEnvelope(run_dir=tmp_path / "u1", cassette=Cassette.update(cassette_path)),
            seed=41,
            model=FakeModelClient(responses=[]),
        )
        miss = one_llm_pipeline().run(
            {"question": "how wide?"},
            envelope=RunEnvelope(run_dir=tmp_path / "u2", cassette=Cassette.update(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )

        assert hit.manifest["cassette"]["mode"] == "update"
        assert (hit.manifest["cassette"]["hits"], hit.manifest["cassette"]["misses"]) == (1, 0)
        assert (miss.manifest["cassette"]["hits"], miss.manifest["cassette"]["misses"]) == (0, 1)
        assert miss.manifest["cassette"]["recorded"] == 1

    def test_a_file_that_does_not_exist_yet_records_from_nothing(self, tmp_path) -> None:
        """Unlike replay, which is refused before the run starts."""
        cassette_path = tmp_path / "absent.jsonl"

        result = one_llm_pipeline().run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "upd", cassette=Cassette.update(cassette_path)),
            seed=41,
            model=client_with(ANSWER),
        )

        assert result.output.answer == "32 inches"
        assert cassette_path.exists()

    def test_tool_calls_are_served_from_the_file_too(self, tmp_path) -> None:
        cassette_path = tmp_path / "cassette.jsonl"
        calls: list[str] = []

        def look_up(query: str) -> str:
            calls.append(query)
            return "The Belmont trouser has a 34 inch inseam."

        pipeline = _agent_pipeline_with(look_up)
        pipeline.run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette_path)),
            seed=41,
            model=_agent_client(),
        )
        assert calls == ["inseam"]

        _agent_pipeline_with(look_up).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "upd", cassette=Cassette.update(cassette_path)),
            seed=41,
            model=_agent_client(),
        )

        assert calls == ["inseam"]


def _agent_pipeline_with(fn) -> Pipeline:
    tool = Tool(
        name="look_up",
        description="Search the catalogue. Returns matching entries.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        side_effect_class=SideEffectClass.READ_ONLY,
        fn=fn,
    )
    return Pipeline(
        [
            AgentNode(
                build_prompt,
                tools=[tool],
                output_schema=Answer,
                node_id="hunt",
                budget=Budget(
                    max_steps=4, max_tokens=10_000, max_cost=None, max_wall_clock_ms=None
                ),
            )
        ],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None),
    )


def _agent_client() -> FakeModelClient:
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
        ]
    )


class TestRedaction:
    def test_a_declared_secret_reaches_neither_artifact(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("PROJECT_API_KEY", "sekrit-value-not-for-disk")
        cassette_path = tmp_path / "cassette.jsonl"

        def leaky_prompt(inputs, ctx):
            import os

            return f"Use key {os.environ['PROJECT_API_KEY']} to answer."

        pipeline = Pipeline(
            [LLMNode(leaky_prompt, output_schema=Answer, node_id="extract")],
            budget=Budget(max_steps=None, max_tokens=1000, max_cost=None, max_wall_clock_ms=None),
        )

        result = pipeline.run(
            {},
            envelope=RunEnvelope(
                run_dir=tmp_path,
                redaction=Redaction(secret_env=["PROJECT_API_KEY"]),
                cassette=Cassette.record(cassette_path),
            ),
            seed=41,
            model=client_with(ANSWER),
        )

        assert "sekrit-value-not-for-disk" not in result.trajectory_path.read_text()
        assert "sekrit-value-not-for-disk" not in cassette_path.read_text()

    def test_the_redacted_path_is_named_on_the_record(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("PROJECT_API_KEY", "sekrit-value-not-for-disk")

        def leaky_prompt(inputs, ctx):
            import os

            return f"Use key {os.environ['PROJECT_API_KEY']} to answer."

        pipeline = Pipeline(
            [LLMNode(leaky_prompt, output_schema=Answer, node_id="extract")],
            budget=Budget(max_steps=None, max_tokens=1000, max_cost=None, max_wall_clock_ms=None),
        )

        result = pipeline.run(
            {},
            envelope=RunEnvelope(
                run_dir=tmp_path, redaction=Redaction(secret_env=["PROJECT_API_KEY"])
            ),
            model=client_with(ANSWER),
        )

        call = _first_model_call(result.trajectory_path)
        assert call["redactions"] == ["inputs.messages[0].content"]

    def test_a_redacted_run_still_replays(self, tmp_path, monkeypatch) -> None:
        # The key is computed before redaction, so the entry is found even though what was
        # stored has the secret removed.
        monkeypatch.setenv("PROJECT_API_KEY", "sekrit-value-not-for-disk")
        cassette_path = tmp_path / "cassette.jsonl"

        def leaky_prompt(inputs, ctx):
            import os

            return f"Use key {os.environ['PROJECT_API_KEY']} to answer."

        def make() -> Pipeline:
            return Pipeline(
                [LLMNode(leaky_prompt, output_schema=Answer, node_id="extract")],
                budget=Budget(
                    max_steps=None, max_tokens=1000, max_cost=None, max_wall_clock_ms=None
                ),
            )

        redaction = Redaction(secret_env=["PROJECT_API_KEY"])
        make().run(
            {},
            envelope=RunEnvelope(
                run_dir=tmp_path / "rec",
                redaction=redaction,
                cassette=Cassette.record(cassette_path),
            ),
            seed=41,
            model=client_with(ANSWER),
        )

        replayed = make().run(
            {},
            envelope=RunEnvelope(
                run_dir=tmp_path / "rep",
                redaction=redaction,
                cassette=Cassette.replay(cassette_path),
            ),
            seed=41,
            model=FakeModelClient(responses=[]),
        )

        assert replayed.output.answer == "32 inches"

    def test_the_manifest_records_the_rules_without_the_values(
        self, envelope, manifest_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("PROJECT_API_KEY", "sekrit-value-not-for-disk")
        envelope.redaction = Redaction(secret_env=["PROJECT_API_KEY"])

        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        recorded = read_manifest(manifest_path)["redaction"]
        assert recorded["secret_env"] == ["PROJECT_API_KEY"]
        assert "sekrit-value-not-for-disk" not in manifest_path.read_text()


class TestCost:
    def test_the_manifest_carries_the_basis_and_the_total(self, tmp_path, manifest_path) -> None:
        envelope = RunEnvelope(run_dir=tmp_path, cost_basis=PRICE)

        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        manifest = read_manifest(manifest_path)
        assert manifest["cost_basis"]["kind"] == "price"
        # 10 uncached at 3.00/Mtok plus 5 output at 15.00/Mtok.
        assert manifest["totals"]["cost"]["value"] == pytest.approx(
            10 / 1e6 * 3.00 + 5 / 1e6 * 15.00
        )

    def test_no_basis_means_the_total_is_unknown(self, envelope, manifest_path) -> None:
        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER))

        cost = read_manifest(manifest_path)["totals"]["cost"]
        assert cost["value"] is None
        assert "no cost basis" in cost["reason"]

    def test_max_cost_without_a_basis_is_refused(self, envelope) -> None:
        pipeline = Pipeline(
            [LLMNode(build_prompt, output_schema=Answer, node_id="extract")],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=1.0, max_wall_clock_ms=None),
        )

        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({}, envelope=envelope, model=client_with(ANSWER))

        assert "FT-27" in str(exc.value)
        assert "cost_basis=PriceBasis" in str(exc.value)

    def test_max_cost_stops_an_agent_loop(self, tmp_path, trajectory) -> None:
        # Every call costs more than the whole budget, so the loop stops after the first.
        expensive = PriceBasis(
            currency="USD", input_uncached_per_mtok=1_000_000.0, output_per_mtok=0.0
        )
        envelope = RunEnvelope(run_dir=tmp_path, cost_basis=expensive)
        pipeline = _agent_pipeline(
            _search_tool([]),
            budget=Budget(max_steps=None, max_tokens=None, max_cost=0.5, max_wall_clock_ms=None),
        )

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=_searching_client())

        node = next(r for r in read_trajectory(trajectory) if r["record_type"] == "node_execution")
        assert node["termination"] == "max_cost"

    def test_an_upper_bound_total_says_so(self, tmp_path, manifest_path) -> None:
        # A self-hosted backend that does not report concurrency gives a bound, not a figure.
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=ComputeBasis(
                currency="USD", device="H100-80GB", device_count=1, hourly_rate=3.60
            ),
        )
        client = FakeModelClient(
            responses=[fake_response(content=ANSWER, concurrent_requests=None)]
        )

        one_llm_pipeline().run({}, envelope=envelope, run_id=RUN_ID, model=client)

        assert read_manifest(manifest_path)["totals"]["cost"]["is_upper_bound"] is True


# -- helpers ------------------------------------------------------------------------------


class _UnreportedCacheTokens:
    """What an adapter reports when its backend does not expose cached prefix tokens."""

    total = 15
    # One input class went unmeasured, so the prompt size is unknown rather than the sum of
    # the classes that were reported. A context builder extrapolating from it needs that.
    measured_input = Unknown(reason="not reported by the backend")

    def to_record(self) -> dict:
        return {
            "input_uncached": 10,
            "input_cache_read": {"type": "unknown", "reason": "not reported by the backend"},
            "input_cache_write": 0,
            "cache_ttl": None,
            "output": 5,
        }


def _first_model_call(path: Path) -> dict:
    return next(r for r in read_trajectory(path) if r["record_type"] == "model_call")


def _search_tool(executions: list[str], *, name: str = "look_up") -> Tool:
    def look_up(query: str) -> str:
        executions.append(query)
        return f"the inseam is 32 inches ({query})"

    return Tool(
        name=name,
        description="Look a measurement up. Returns the passage that mentions it.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        side_effect_class=SideEffectClass.READ_ONLY,
        fn=look_up,
        version="1",
    )


def _agent_pipeline(
    tool: Tool, *, budget: Budget | None = None, registry: ToolRegistry | None = None
) -> Pipeline:
    node_budget = budget or Budget(
        max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None
    )
    return Pipeline(
        [
            AgentNode(
                build_prompt,
                tools=[tool],
                output_schema=Answer,
                budget=node_budget,
                node_id="hunt",
            )
        ],
        budget=node_budget,
        tools=registry,
    )


def _searching_client() -> FakeModelClient:
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
        ]
    )


def _finishing_client() -> FakeModelClient:
    return FakeModelClient(
        responses=[
            fake_response(
                tool_calls=[
                    ToolCallRequest(
                        id="c1",
                        name="finish",
                        arguments={"answer": "32 inches", "source": "size chart"},
                    )
                ]
            )
        ]
    )


class TestBackendDivergence:
    """A backend answering the same request two ways is counted, not hidden.

    A seed is best-effort on a hosted API. The count is what tells a reader whether a run is
    repeatable because the sampling is stable, or only because the cassette makes it so.
    """

    def test_a_differing_response_to_a_repeated_request_is_counted(
        self, tmp_path, manifest_path
    ) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        envelope = RunEnvelope(run_dir=tmp_path, cassette=cassette)
        pipeline = one_llm_pipeline()

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER), seed=41)
        first = read_manifest(manifest_path)["cassette"]
        assert (first["recorded"], first["diverged"]) == (1, 0)

        # The identical request, answered differently.
        other = json.dumps({"answer": "37 inches"})
        pipeline.run({}, envelope=envelope, run_id="run_two", model=client_with(other), seed=41)
        second = read_manifest(run_path(tmp_path, "run_two", "manifest.json"))["cassette"]
        assert (second["recorded"], second["diverged"]) == (1, 1)

        # Both are on file, and replay still serves the first.
        assert len(cassette.variants()) == 1
        assert len(next(iter(cassette.variants().values()))) == 2

    def test_a_repeated_identical_response_is_not_counted_as_divergence(
        self, tmp_path, manifest_path
    ) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        envelope = RunEnvelope(run_dir=tmp_path, cassette=cassette)
        pipeline = one_llm_pipeline()

        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=client_with(ANSWER), seed=41)
        pipeline.run({}, envelope=envelope, run_id="run_two", model=client_with(ANSWER), seed=41)

        second = read_manifest(run_path(tmp_path, "run_two", "manifest.json"))["cassette"]
        assert (second["recorded"], second["diverged"]) == (0, 0)
