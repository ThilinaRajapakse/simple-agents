"""A model declared on the node rather than on the run.

Every test here uses a fake client whose identity is set to a real backend's shape, because
what the library does with two clients turns on `identity()` and not on what came back.
`test_adapter_integration.py` holds the recording of Mistral and vLLM answering one pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    Cassette,
    CassetteMiss,
    ComputeBasis,
    ConfigurationError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    PacedClient,
    Pipeline,
    PriceBasis,
    RunEnvelope,
    fake_response,
)
from simple_agents.errors import CallerFacingError, RunSuspended
from simple_agents.evaluation import ablate, plan_variant
from simple_agents.evaluation.runner import _clients_of
from simple_agents.models import ModelIdentity, ToolCallRequest, TokenUsage

from conftest import RUN_ID
from schemas import Answer

BUDGET = Budget(max_steps=8, max_tokens=100_000, max_cost=None, max_wall_clock_ms=120_000)

ANSWER = json.dumps({"answer": "32 inches", "source": "spec"})


def client(
    backend: str = "hosted_api",
    request_model: str = "mistral-large-2512",
    model_revision: str | None = None,
    responses: int = 4,
) -> FakeModelClient:
    """A fake client reporting the identity of a real one, with room to be called."""
    fake = FakeModelClient(
        responses=[
            fake_response(
                content=ANSWER,
                backend=backend,
                request_model=request_model,
                model_revision=model_revision,
                tokens=TokenUsage(
                    input_uncached=1000,
                    input_cache_read=0,
                    input_cache_write=0,
                    cache_ttl=None,
                    output=100,
                ),
            )
            for _ in range(responses)
        ]
    )
    fake.model_identity = ModelIdentity(
        backend=backend, request_model=request_model, model_revision=model_revision
    )
    return fake


def hosted(**kwargs) -> FakeModelClient:
    return client(**kwargs)


def local(**kwargs) -> FakeModelClient:
    defaults = {
        "backend": "self_hosted",
        "request_model": "Qwen/Qwen3-1.7B",
        "model_revision": "a1b2c3d4e5f",
    }
    return client(**{**defaults, **kwargs})


def reduce_notes(inputs, ctx) -> str:
    return Prompt.user("reduce these notes")


def answer(inputs, ctx) -> str:
    return Prompt.user("answer the question")


class TestWhichClientACallGoesTo:
    def test_a_node_declaring_one_calls_it_and_the_run_client_serves_the_rest(
        self, envelope
    ) -> None:
        cheap, strong = local(), hosted()
        pipeline = Pipeline(
            [
                LLMNode(reduce_notes, output_schema=Answer, model=cheap),
                LLMNode(answer, output_schema=Answer),
            ],
            budget=BUDGET,
        )

        pipeline.run({}, envelope=envelope, model=strong, run_id=RUN_ID)

        assert len(cheap.requests) == 1
        assert len(strong.requests) == 1

    def test_the_node_wins_over_the_run(self, envelope) -> None:
        """A run client is a default, so passing one does not move a declared node."""
        declared, run_client = local(), hosted()
        pipeline = Pipeline([LLMNode(answer, output_schema=Answer, model=declared)], budget=BUDGET)

        pipeline.run({}, envelope=envelope, model=run_client, run_id=RUN_ID)

        assert len(declared.requests) == 1
        assert run_client.requests == []

    def test_a_run_needs_no_client_when_every_node_declares_one(self, envelope) -> None:
        cheap = local()
        pipeline = Pipeline([LLMNode(answer, output_schema=Answer, model=cheap)], budget=BUDGET)

        pipeline.run({}, envelope=envelope, run_id=RUN_ID)

        assert len(cheap.requests) == 1

    def test_an_agent_node_takes_one_too(self, envelope) -> None:
        cheap = local(responses=1)
        cheap.responses = [
            fake_response(
                tool_calls=[
                    ToolCallRequest(id="c1", name="finish", arguments={"answer": "32 inches"})
                ],
                backend="self_hosted",
                request_model="Qwen/Qwen3-1.7B",
                model_revision="a1b2c3d4e5f",
            )
        ]
        pipeline = Pipeline(
            [AgentNode(answer, tools=[], output_schema=Answer, budget=BUDGET, model=cheap)],
            budget=BUDGET,
        )

        pipeline.run({}, envelope=envelope, model=hosted(), run_id=RUN_ID)

        assert len(cheap.requests) == 1

    def test_a_deterministic_node_takes_no_model(self) -> None:
        with pytest.raises(TypeError):
            Deterministic(reduce_notes, model=hosted())  # type: ignore[call-arg]


class TestWhatIsRefusedBeforeTheRun:
    def test_a_calling_node_with_no_client_from_either_source(self, envelope) -> None:
        """Refused before anything runs, rather than when that node is reached."""
        spent = []

        def note(inputs, ctx):
            spent.append(1)
            return "loaded"

        pipeline = Pipeline(
            [Deterministic(note), LLMNode(answer, output_schema=Answer)], budget=BUDGET
        )

        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({}, envelope=envelope, run_id=RUN_ID)

        assert "'answer'" in str(exc.value)
        assert "LLMNode(..., model=client)" in str(exc.value)
        assert spent == [], "the node before it should not have run"

    def test_only_the_nodes_with_no_client_are_named(self, envelope) -> None:
        pipeline = Pipeline(
            [
                LLMNode(reduce_notes, output_schema=Answer, model=local()),
                LLMNode(answer, output_schema=Answer),
            ],
            budget=BUDGET,
        )

        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({}, envelope=envelope, run_id=RUN_ID)

        assert "'answer'" in str(exc.value)
        assert "reduce_notes" not in str(exc.value)


class TestWhatTheManifestRecords:
    def read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def test_a_node_records_what_it_declared_and_null_where_it_takes_the_runs(
        self, envelope, manifest_path
    ) -> None:
        pipeline = Pipeline(
            [
                LLMNode(reduce_notes, output_schema=Answer, model=local()),
                LLMNode(answer, output_schema=Answer),
            ],
            budget=BUDGET,
        )

        pipeline.run({}, envelope=envelope, model=hosted(), run_id=RUN_ID)

        nodes = {n["node_id"]: n for n in self.read(manifest_path)["nodes"]}
        assert nodes["reduce_notes"]["model"] == {
            "backend": "self_hosted",
            "request_model": "Qwen/Qwen3-1.7B",
            "model_revision": "a1b2c3d4e5f",
        }
        assert nodes["answer"]["model"] is None

    def test_configured_holds_the_runs_client_and_is_null_without_one(
        self, envelope, manifest_path
    ) -> None:
        pipeline = Pipeline([LLMNode(answer, output_schema=Answer, model=local())], budget=BUDGET)

        pipeline.run({}, envelope=envelope, run_id=RUN_ID)

        assert self.read(manifest_path)["models"]["configured"] is None

    def test_observed_carries_both_models(self, envelope, manifest_path) -> None:
        pipeline = Pipeline(
            [
                LLMNode(reduce_notes, output_schema=Answer, model=local()),
                LLMNode(answer, output_schema=Answer),
            ],
            budget=BUDGET,
        )

        pipeline.run({}, envelope=envelope, model=hosted(), run_id=RUN_ID)

        observed = {
            entry["request_model"]: entry["calls"]
            for entry in self.read(manifest_path)["models"]["observed"]
        }
        assert observed == {"Qwen/Qwen3-1.7B": 1, "mistral-large-2512": 1}

    def test_a_deterministic_node_carries_no_model_field(self, envelope, manifest_path) -> None:
        pipeline = Pipeline(
            [Deterministic(reduce_notes), LLMNode(answer, output_schema=Answer)],
            budget=BUDGET,
        )

        pipeline.run({}, envelope=envelope, model=hosted(), run_id=RUN_ID)

        nodes = {n["node_id"]: n for n in self.read(manifest_path)["nodes"]}
        assert "model" not in nodes["reduce_notes"]

    def test_the_graph_fingerprint_ignores_it(self) -> None:
        """A changed model is a waivable resume difference, not a changed shape."""
        one = Pipeline([LLMNode(answer, output_schema=Answer, model=local())], budget=BUDGET)
        other = Pipeline([LLMNode(answer, output_schema=Answer, model=hosted())], budget=BUDGET)

        assert one.graph_fingerprint() == other.graph_fingerprint()


class TestTheCassetteKeysPerNode:
    def test_a_replay_after_a_node_changed_model_finds_no_entry(self, tmp_path) -> None:
        """The key covers model identity, so the previous model's response is not served."""
        cassette = tmp_path / "calls.jsonl"
        recording = RunEnvelope(run_dir=tmp_path, cassette=Cassette.record(cassette))
        Pipeline([LLMNode(answer, output_schema=Answer, model=local())], budget=BUDGET).run(
            {}, envelope=recording, run_id=RUN_ID
        )

        replaying = RunEnvelope(run_dir=tmp_path / "again", cassette=Cassette.replay(cassette))
        moved = Pipeline([LLMNode(answer, output_schema=Answer, model=hosted())], budget=BUDGET)

        with pytest.raises(CassetteMiss) as exc:
            moved.run({}, envelope=replaying, run_id=RUN_ID)

        assert "mistral-large-2512" in str(exc.value)


class TestStreamingIsCheckedPerNode:
    def test_a_node_whose_own_client_cannot_stream_is_named(self, envelope) -> None:
        class Unstreamable(FakeModelClient):
            pass

        cannot = Unstreamable(responses=[fake_response(content=ANSWER)])
        cannot.model_identity = ModelIdentity(
            backend="self_hosted", request_model="local/model", model_revision="abc1234"
        )
        pipeline = Pipeline(
            [LLMNode(answer, output_schema=Answer, stream=True, model=cannot)],
            budget=BUDGET,
        )

        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({}, envelope=envelope, on_token=lambda e: None, run_id=RUN_ID)

        assert "'answer'" in str(exc.value)
        assert "Unstreamable" in str(exc.value)

    def test_the_waivers_gather_from_every_client(self, envelope, manifest_path) -> None:
        class Waived(FakeModelClient):
            stream_without_usage = True

        waived = Waived(responses=[fake_response(content=ANSWER)])
        waived.model_identity = ModelIdentity(
            backend="hosted_api", request_model="mistral-small-2603", model_revision=None
        )
        pipeline = Pipeline(
            [
                LLMNode(reduce_notes, output_schema=Answer, model=waived),
                LLMNode(answer, output_schema=Answer),
            ],
            budget=BUDGET,
        )

        pipeline.run({}, envelope=envelope, model=hosted(), run_id=RUN_ID)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["stream_waivers"] == ["Waived"]


class TestCostAcrossTwoModels:
    def two_node_pipeline(self) -> tuple[Pipeline, FakeModelClient, FakeModelClient]:
        cheap, strong = local(), hosted()
        return (
            Pipeline(
                [
                    LLMNode(reduce_notes, output_schema=Answer, model=cheap),
                    LLMNode(answer, output_schema=Answer),
                ],
                budget=BUDGET,
            ),
            cheap,
            strong,
        )

    def test_one_basis_over_two_backends_is_refused(self, tmp_path) -> None:
        pipeline, _, strong = self.two_node_pipeline()
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=PriceBasis(currency="USD", input_uncached_per_mtok=2.0, output_per_mtok=6.0),
        )

        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({}, envelope=envelope, model=strong, run_id=RUN_ID)

        assert "hosted and a self-hosted backend" in str(exc.value)
        assert "cost_basis={" in str(exc.value)

    def test_one_price_basis_over_two_hosted_models_is_refused(self, tmp_path) -> None:
        pipeline = Pipeline(
            [
                LLMNode(
                    reduce_notes,
                    output_schema=Answer,
                    model=hosted(request_model="mistral-small-2603"),
                ),
                LLMNode(answer, output_schema=Answer),
            ],
            budget=BUDGET,
        )
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=PriceBasis(currency="USD", input_uncached_per_mtok=2.0, output_per_mtok=6.0),
        )

        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({}, envelope=envelope, model=hosted(), run_id=RUN_ID)

        assert "Per-token rates are one model's" in str(exc.value)

    def test_one_compute_basis_over_two_self_hosted_models_is_allowed(self, tmp_path) -> None:
        """A device rate belongs to the deployment, so it covers both models on it."""
        pipeline = Pipeline(
            [
                LLMNode(
                    reduce_notes,
                    output_schema=Answer,
                    model=local(request_model="Qwen/Qwen3-8B"),
                ),
                LLMNode(answer, output_schema=Answer),
            ],
            budget=BUDGET,
        )
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=ComputeBasis(
                currency="USD", device="RTX3090", device_count=1, hourly_rate=0.22
            ),
        )

        result = pipeline.run({}, envelope=envelope, model=local(), run_id=RUN_ID)

        assert result.cost["currency"] == "USD"

    def test_a_basis_per_model_prices_each_call_on_its_own_terms(
        self, tmp_path, manifest_path
    ) -> None:
        pipeline, _, strong = self.two_node_pipeline()
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis={
                "Qwen/Qwen3-1.7B": ComputeBasis(
                    currency="USD", device="RTX3090", device_count=1, hourly_rate=0.22
                ),
                "mistral-large-2512": PriceBasis(
                    currency="USD", input_uncached_per_mtok=2.0, output_per_mtok=6.0
                ),
            },
        )

        result = pipeline.run({}, envelope=envelope, model=strong, run_id=RUN_ID)

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["cost_basis"]["kind"] == "by_model"
        assert sorted(manifest["cost_basis"]["bases"]) == [
            "Qwen/Qwen3-1.7B",
            "mistral-large-2512",
        ]
        # 1000 input at 2.0/Mtok and 100 output at 6.0/Mtok is the hosted call; the
        # self-hosted one is device time, which is near zero against a fake client.
        assert result.cost["value"] == pytest.approx(0.0026, abs=1e-4)
        assert result.cost["basis"] == "by_model"

    def test_a_model_the_basis_does_not_name_prices_as_unknown(self, tmp_path) -> None:
        pipeline, _, strong = self.two_node_pipeline()
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis={
                "mistral-large-2512": PriceBasis(
                    currency="USD", input_uncached_per_mtok=2.0, output_per_mtok=6.0
                )
            },
        )

        result = pipeline.run({}, envelope=envelope, model=strong, run_id=RUN_ID)

        assert result.cost["value"] is None
        assert "Qwen/Qwen3-1.7B" in result.cost["reason"]

    def test_max_cost_with_an_unpriced_model_is_refused(self, tmp_path) -> None:
        cheap, strong = local(), hosted()
        pipeline = Pipeline(
            [
                LLMNode(reduce_notes, output_schema=Answer, model=cheap),
                LLMNode(answer, output_schema=Answer),
            ],
            budget=Budget(max_steps=8, max_tokens=None, max_cost=1.0, max_wall_clock_ms=None),
        )
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis={
                "mistral-large-2512": PriceBasis(
                    currency="USD", input_uncached_per_mtok=2.0, output_per_mtok=6.0
                )
            },
        )

        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({}, envelope=envelope, model=strong, run_id=RUN_ID)

        assert "'Qwen/Qwen3-1.7B'" in str(exc.value)
        assert "FT-27" in str(exc.value)

    def test_two_currencies_across_two_bases_are_refused(self, tmp_path) -> None:
        pipeline, _, strong = self.two_node_pipeline()
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis={
                "Qwen/Qwen3-1.7B": ComputeBasis(
                    currency="EUR", device="RTX3090", device_count=1, hourly_rate=0.22
                ),
                "mistral-large-2512": PriceBasis(
                    currency="USD", input_uncached_per_mtok=2.0, output_per_mtok=6.0
                ),
            },
        )

        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({}, envelope=envelope, model=strong, run_id=RUN_ID)

        assert "more than one currency" in str(exc.value)


class TestResumeAgainstAChangedNodeModel:
    def test_it_is_named_per_node_and_waivable(self, tmp_path) -> None:
        """The same tier as a changed prompt: refused unless named, then recorded."""
        envelope = RunEnvelope(run_dir=tmp_path)

        def stop_here(inputs, ctx):
            return "stopped"

        started = Pipeline(
            [
                LLMNode(answer, output_schema=Answer, model=local()),
                Deterministic(stop_here, suspend_before=True),
            ],
            budget=BUDGET,
        )
        with pytest.raises(RunSuspended):
            started.run({}, envelope=envelope, run_id=RUN_ID)

        moved = Pipeline(
            [
                LLMNode(answer, output_schema=Answer, model=local(request_model="Qwen/Qwen3-8B")),
                Deterministic(stop_here, suspend_before=True),
            ],
            budget=BUDGET,
        )

        with pytest.raises(CallerFacingError) as exc:
            moved.resume(RUN_ID, envelope=envelope)

        assert "model.answer" in str(exc.value)


class TestEvaluationSeesThePerNodeModel:
    def test_a_changed_node_model_taints_the_replay(self) -> None:
        baseline = Pipeline([LLMNode(answer, output_schema=Answer, model=hosted())], budget=BUDGET)
        variant = Pipeline([LLMNode(answer, output_schema=Answer, model=local())], budget=BUDGET)

        plan = plan_variant(baseline, variant, name="answer on the 1.7B")

        assert plan.differs_at == ("answer",)
        assert [n.calls for n in plan.nodes] == ["live"]

    def test_ablate_carries_the_nodes_client_into_the_flattened_node(self) -> None:
        """Without it the arm measures the loop coming out and the model changing at once."""
        cheap = local()
        pipeline = Pipeline(
            [
                AgentNode(answer, tools=[], output_schema=Answer, budget=BUDGET, model=cheap),
                LLMNode(reduce_notes, output_schema=Answer),
            ],
            budget=BUDGET,
        )

        arms = ablate(pipeline)
        flattened = arms["answer as one call"]
        node = dict(flattened.declared_nodes())["answer"]

        assert node.model is cheap

    def test_every_distinct_client_is_paced(self) -> None:
        cheap, strong = local(), hosted()
        pipeline = Pipeline(
            [
                LLMNode(reduce_notes, output_schema=Answer, model=cheap),
                LLMNode(answer, output_schema=Answer),
            ],
            budget=BUDGET,
        )

        assert _clients_of(pipeline, strong) == [cheap, strong]

    def test_a_paced_client_on_a_node_is_reached(self) -> None:
        paced = PacedClient(local())
        pipeline = Pipeline([LLMNode(answer, output_schema=Answer, model=paced)], budget=BUDGET)

        assert _clients_of(pipeline, None) == [paced]
