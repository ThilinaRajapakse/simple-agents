"""A real run against each backend, replayed from the cassette it recorded.

The cassettes under `tests/cassettes/` were recorded by
`scripts/record_backend_cassettes.py` against Mistral and against a local vLLM server. These
tests replay them, so they need no key, no server and no network, which is what FT-21 asks of
a project's own evaluation.

What this covers that `test_adapters.py` does not is the whole envelope over real data: the
manifest's pin, the trajectory records, the derived cost, and the cassette key computed from
the same request the recording was made against. A key that differs by one field is a miss,
so these tests fail if an adapter changes what it sends.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from schemas import Answer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from record_backend_cassettes import (  # noqa: E402
    AGENT_QUESTION,
    CONTEXT_DOCUMENTS,
    EVAL_K,
    EVAL_SEED,
    GEMINI_PRICES,
    MISTRAL_PRICES,
    NO_THINKING,
    STREAM_QUESTION,
    TOOLS_QUESTION,
    MIXED_NOTES,
    VLLM_DEVICE,
    agent_pipeline,
    context_pipeline,
    eval_suite,
    mixed_pipeline,
    search,
    stream_pipeline,
    tools_pipeline,
)

from simple_agents.cost import duration_seconds  # noqa: E402
from simple_agents.evaluation import EvalResults  # noqa: E402

from simple_agents import (
    Prompt,
    Budget,
    Cassette,
    ComputeBasis,
    GeminiClient,
    LLMNode,
    MistralClient,
    Pipeline,
    PriceBasis,
    RunEnvelope,
    VLLMClient,
    read_trajectory,
    total_cost,
)

CASSETTES = Path(__file__).parent / "cassettes"
QUESTION = "What is the capital of France? Answer in one word."
SEED = 41
VLLM_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"


def build_prompt(inputs, ctx):
    """Byte-identical to the recording script's prompt. The cassette key covers it."""
    return Prompt.user(
        "{question}\n\nReport the answer, or `unknown` if it is not known.",
        question=inputs["question"],
    )


def pipeline() -> Pipeline:
    return Pipeline(
        [LLMNode(build_prompt, output_schema=Answer, node_id="answer", temperature=0.0)],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=120_000),
    )


def replay(tmp_path: Path, backend: str, client, basis):
    cassette = CASSETTES / f"{backend}.jsonl"
    if not cassette.exists():
        pytest.skip(f"no recorded cassette for {backend}; run scripts/record_backend_cassettes.py")
    envelope = RunEnvelope(run_dir=tmp_path, cost_basis=basis, cassette=Cassette.replay(cassette))
    result = pipeline().run({"question": QUESTION}, envelope=envelope, model=client, seed=SEED)
    manifest = json.loads(Path(result.paths.manifest).read_text())
    records = list(read_trajectory(result.paths.trajectory))
    return result, manifest, records


class TestMistral:
    @pytest.fixture
    def run(self, tmp_path: Path):
        client = MistralClient(model="mistral-small-2603", api_key="not-used-in-replay")
        return replay(
            tmp_path,
            "mistral",
            client,
            PriceBasis(
                currency="USD",
                input_uncached_per_mtok=0.15,
                input_cache_read_per_mtok=0.015,
                output_per_mtok=0.60,
            ),
        )

    def test_the_recorded_answer_comes_back_through_the_schema(self, run) -> None:
        result, _, _ = run

        assert isinstance(result.output, Answer)
        assert result.output.answer == "Paris"

    def test_nothing_was_called(self, run) -> None:
        _, manifest, records = run

        assert manifest["cassette"]["hits"] == 1
        assert manifest["cassette"]["misses"] == 0
        assert [r["replayed"] for r in records if r["record_type"] == "model_call"] == [True]

    def test_the_manifest_pins_the_dated_snapshot(self, run) -> None:
        _, manifest, _ = run

        assert manifest["models"]["configured"] == {
            "backend": "hosted_api",
            "request_model": "mistral-small-2603",
            "model_revision": None,
        }

    def test_the_token_split_survives_the_round_trip(self, run) -> None:
        _, _, records = run
        call = next(r for r in records if r["record_type"] == "model_call")

        assert call["tokens"]["input_cache_read"] == 0
        assert call["tokens"]["input_uncached"] > 0
        assert call["tokens"]["cache_ttl"] is None

    def test_cost_derives_under_the_price_basis(self, run) -> None:
        _, manifest, records = run
        cost = total_cost(
            records,
            PriceBasis(
                currency="USD",
                input_uncached_per_mtok=0.15,
                input_cache_read_per_mtok=0.015,
                output_per_mtok=0.60,
            ),
        )

        assert cost.known
        assert cost.is_upper_bound is False
        assert manifest["totals"]["cost"]["value"] == pytest.approx(cost.value)


class TestAgentLoop:
    """The multi-turn path, replayed from a recorded run against a real backend.

    Nothing else covers it. A `FakeModelClient` ignores the messages it is sent, so the loop
    can build a conversation no backend accepts and every test still passes. That is what
    happened: the assistant messages carrying tool calls were in the library's own shape, and
    the first live run was rejected with a 422.
    """

    @pytest.fixture
    def run(self, tmp_path: Path):
        cassette = CASSETTES / "agent.jsonl"
        if not cassette.exists():
            pytest.skip("no recorded agent cassette; run scripts/record_backend_cassettes.py")
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=PriceBasis(
                currency="USD", input_uncached_per_mtok=0.15, output_per_mtok=0.60
            ),
            cassette=Cassette.replay(cassette),
        )
        result = agent_pipeline().run(
            {"question": AGENT_QUESTION},
            envelope=envelope,
            model=MistralClient(model="mistral-small-2603", api_key="not-used-in-replay"),
            seed=SEED,
        )
        return result, list(read_trajectory(result.paths.trajectory))

    def test_the_loop_reached_an_answer_through_the_schema(self, run) -> None:
        result, _ = run

        assert result.output.retailer == "Kirkwall"

    def test_it_took_more_than_one_turn(self, run) -> None:
        # An LLMNode makes one call. The reason to reach for an AgentNode is that the number
        # of calls is not knowable in advance, and this question needs a second lookup that
        # depends on what the first returned.
        _, records = run
        calls = [r for r in records if r["record_type"] == "model_call"]

        assert len(calls) > 1

    def test_every_tool_call_records_the_class_it_ran_under(self, run) -> None:
        _, records = run
        tool_calls = [r for r in records if r["record_type"] == "tool_call"]

        assert tool_calls
        assert {r["side_effect_class"] for r in tool_calls} == {"read_only"}

    def test_the_search_calls_replay_and_finish_does_not(self, run) -> None:
        # `finish` is schema validation inside the library, with nothing external to replay,
        # so it runs for real on a replayed run. Every call that left the process is served
        # from the cassette (`docs/run-envelope.md` §3.3).
        _, records = run
        by_name = {
            r["tool_name"]: r["replayed"] for r in records if r["record_type"] == "tool_call"
        }

        assert by_name["search"] is True
        assert by_name["finish"] is False

    def test_the_node_records_why_it_stopped(self, run) -> None:
        _, records = run
        node = next(r for r in records if r["record_type"] == "node_execution")

        assert node["node_kind"] == "agent"
        assert node["termination"] == "finish"

    def test_the_tool_was_offered_with_its_derived_schema(self, run) -> None:
        # The model can only call a tool correctly if it was told what the tool takes. An
        # empty schema is what produced a call with no arguments at all.
        offered = search.to_wire()["input_schema"]

        assert offered["required"] == ["query"]
        assert offered["properties"]["query"]["type"] == "string"


class TestVLLM:
    @pytest.fixture
    def run(self, tmp_path: Path):
        # The revision is part of the cassette key, so it has to match the recording. A
        # different SHA is a miss, which is the attribution failure FT-14 guards against
        # arriving through the replay layer.
        client = VLLMClient(model="Qwen/Qwen3-1.7B", model_revision=VLLM_REVISION)
        return replay(
            tmp_path,
            "vllm",
            client,
            ComputeBasis(currency="USD", device="RTX-3090", device_count=1, hourly_rate=0.22),
        )

    def test_the_recorded_answer_comes_back_through_the_schema(self, run) -> None:
        result, _, _ = run

        assert isinstance(result.output, Answer)

    def test_the_manifest_pins_a_revision(self, run) -> None:
        _, manifest, _ = run
        configured = manifest["models"]["configured"]

        assert configured["backend"] == "self_hosted"
        assert configured["model_revision"] is not None

    def test_the_three_input_counts_are_disjoint(self, run) -> None:
        _, _, records = run
        tokens = next(r for r in records if r["record_type"] == "model_call")["tokens"]

        assert all(
            isinstance(tokens[k], int)
            for k in ("input_uncached", "input_cache_read", "input_cache_write")
        )
        assert tokens["cache_ttl"] is None

    def test_compute_cost_is_charged_on_the_recorded_device_time(self, run) -> None:
        # The replay returns in microseconds, so a cost derived from this run's timestamps
        # would be near zero. It is charged on what the live call took, carried in the
        # cassette. Only a real recording can show this: a fake client returns instantly.
        _, manifest, records = run
        call = next(r for r in records if r["record_type"] == "model_call")
        cost = manifest["totals"]["cost"]

        assert call["replayed"] is True
        assert call["recorded_duration_ms"] > 0
        # Wall clock across the replayed call, which is what the old figure was charged on.
        replay_ms = duration_seconds(call) * 1000
        assert replay_ms < call["recorded_duration_ms"]

        # 0.22 USD/hour on one device, for the recorded milliseconds.
        expected = call["recorded_duration_ms"] / 1000 * 0.22 / 3600
        assert cost["basis"] == "compute"
        assert cost["value"] == pytest.approx(expected)
        # vLLM reports no concurrency unless report_concurrency is on, so the whole device is
        # charged to this call and the figure is a bound rather than a measurement.
        assert cost["is_upper_bound"] is True


class TestTwoBackendsInOneRun:
    """Per-node model selection, recorded against Mistral and a local vLLM at once.

    A fake client returns a scripted response without reading the request, so it cannot show
    two adapters coexisting: that each node's calls key separately in the cassette, that the
    manifest records a different model per node, and that a hosted call priced on tokens and a
    self-hosted one priced on device time sum to one figure.
    """

    @pytest.fixture
    def run(self, tmp_path: Path):
        cassette = CASSETTES / "mixed.jsonl"
        if not cassette.exists():
            pytest.skip("no recorded mixed cassette; run scripts/record_backend_cassettes.py")
        local = VLLMClient(model="Qwen/Qwen3-1.7B", model_revision=VLLM_REVISION)
        hosted = MistralClient(model="mistral-small-2603", api_key="not-used-in-replay")
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis={
                "Qwen/Qwen3-1.7B": VLLM_DEVICE,
                "mistral-small-2603": MISTRAL_PRICES,
            },
            cassette=Cassette.replay(cassette),
        )
        # No run client: both nodes declare their own, which is the case that used to be
        # impossible to express.
        result = mixed_pipeline(local, hosted).run(
            {"notes": MIXED_NOTES}, envelope=envelope, seed=SEED
        )
        manifest = json.loads(Path(result.paths.manifest).read_text())
        return result, manifest, list(read_trajectory(result.paths.trajectory))

    def test_each_node_called_the_model_it_declared(self, run) -> None:
        _, _, records = run
        calls = [r for r in records if r["record_type"] == "model_call"]

        assert [c["request_model"] for c in calls] == [
            "Qwen/Qwen3-1.7B",
            "mistral-small-2603",
        ]

    def test_the_manifest_records_a_model_per_node_and_no_run_client(self, run) -> None:
        _, manifest, _ = run
        nodes = {n["node_id"]: n for n in manifest["nodes"]}

        assert manifest["models"]["configured"] is None
        assert nodes["reduce"]["model"]["request_model"] == "Qwen/Qwen3-1.7B"
        assert nodes["reduce"]["model"]["model_revision"] == VLLM_REVISION
        assert nodes["answer"]["model"]["request_model"] == "mistral-small-2603"

    def test_both_models_are_observed(self, run) -> None:
        _, manifest, _ = run
        served = {
            entry["request_model"]: entry["calls"] for entry in manifest["models"]["observed"]
        }

        assert served == {"Qwen/Qwen3-1.7B": 1, "mistral-small-2603": 1}

    def test_every_call_replayed_so_the_keys_separated_the_two(self, run) -> None:
        """One cassette, two model identities. A key that collided would miss."""
        _, _, records = run
        calls = [r for r in records if r["record_type"] == "model_call"]

        assert all(c["replayed"] for c in calls)

    def test_the_two_bases_sum_to_one_figure(self, run) -> None:
        _, manifest, records = run
        calls = {r["request_model"]: r for r in records if r["record_type"] == "model_call"}
        cost = manifest["totals"]["cost"]

        hosted = calls["mistral-small-2603"]
        priced = (
            hosted["tokens"]["input_uncached"] / 1_000_000 * MISTRAL_PRICES.input_uncached_per_mtok
            + hosted["tokens"]["input_cache_read"]
            / 1_000_000
            * MISTRAL_PRICES.input_cache_read_per_mtok
            + hosted["tokens"]["output"] / 1_000_000 * MISTRAL_PRICES.output_per_mtok
        )
        local = calls["Qwen/Qwen3-1.7B"]
        device = local["recorded_duration_ms"] / 1000 * VLLM_DEVICE.hourly_rate / 3600

        assert manifest["cost_basis"]["kind"] == "by_model"
        assert cost["currency"] == "USD"
        assert cost["value"] == pytest.approx(priced + device)
        # The server reported one request in flight, so the compute half is a measurement
        # rather than a bound, and the total carries no bound from either side.
        assert local["concurrent_requests"] == 1
        assert cost["is_upper_bound"] is False

    def test_the_answer_came_from_the_facts_the_cheap_node_kept(self, run) -> None:
        result, _, _ = run

        assert isinstance(result.output, Answer)
        assert "1.4" in str(result.output.answer)

    def test_ft_14_reads_both_pins(self, run) -> None:
        """The revision pins the local weights and the dated string pins the hosted model."""
        from simple_agents.conformance.checks import _serving_models

        _, manifest, _ = run
        serving = _serving_models(manifest, manifest["models"]["configured"] or {})

        assert sorted(at for _, at in serving) == ["answer", "reduce"]


class TestContextBuilderOverARealBackend:
    """The recorded fan-out, where the pre-flight estimate has a real measurement to use.

    `FakeModelClient` returns a scripted token count without reading the request, so the ratio
    a fake run measures is one the test chose. Only a live recording says whether the
    extrapolation resembles what a backend actually charges.
    """

    @pytest.fixture
    def run(self, tmp_path: Path):
        cassette = CASSETTES / "context-vllm.jsonl"
        if not cassette.exists():
            pytest.skip(
                "no recorded context-vllm cassette; run scripts/record_backend_cassettes.py"
            )
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=VLLM_DEVICE,
            cassette=Cassette.replay(cassette),
        )
        result = context_pipeline().run(
            {"documents": CONTEXT_DOCUMENTS},
            envelope=envelope,
            model=VLLMClient(model="Qwen/Qwen3-1.7B", model_revision=VLLM_REVISION),
            seed=SEED,
        )
        records = list(read_trajectory(result.paths.trajectory))
        return result, records

    def test_every_call_records_the_builder_that_produced_it(self, run) -> None:
        _, records = run
        calls = [r for r in records if r["record_type"] == "model_call"]

        assert len(calls) == len(CONTEXT_DOCUMENTS)
        for call in calls:
            assert call["context"]["context_builder"] == "AppendAll"
            assert call["context"]["dropped"] == []

    def test_the_first_item_has_no_estimate_and_later_items_do(self, run) -> None:
        _, records = run
        estimates = [r["context"]["estimate"] for r in records if r["record_type"] == "model_call"]

        # Nothing has been measured before the first call, so no ratio exists for it.
        assert estimates[0] is None
        assert all(e is not None for e in estimates[1:])

    def test_the_estimate_is_close_to_what_the_backend_reported(self, run) -> None:
        _, records = run
        calls = [r for r in records if r["record_type"] == "model_call"]

        for call in calls[1:]:
            estimated = call["context"]["estimate"]["input_tokens"]
            # All three classes. They are disjoint and sum to the prompt the backend was
            # sent, so leaving one out compares an estimate of the whole prompt against part
            # of it.
            reported = (
                call["tokens"]["input_uncached"]
                + call["tokens"]["input_cache_read"]
                + call["tokens"]["input_cache_write"]
            )
            # Within half again either way. This is the only assertion in the suite about how
            # good the estimate is, and it is only meaningful because both numbers came from
            # a real backend.
            assert 0.5 * reported <= estimated <= 1.5 * reported

    def test_the_ratio_names_the_call_it_was_measured_on(self, run) -> None:
        _, records = run
        calls = [r for r in records if r["record_type"] == "model_call"]

        # Inside a fan-out `call_index` counts within its item, so every item's only call is
        # call 0 and the item is what tells them apart. Each estimate was measured on the item
        # before it, which is not the item being estimated: the ratio is a property of the node
        # and the backend, and any of the node's calls measures it.
        estimates = [c["context"]["estimate"] for c in calls[1:]]
        assert [e["measured_on_call"] for e in estimates] == [0, 0]
        assert [e["measured_on_item"] for e in estimates] == [0, 1]


class TestToolSurface:
    """The tool surface over a real backend, replayed from a recorded run.

    Cassettes cannot show what a backend accepts, so what this covers is the envelope over
    requests a real backend answered: a tool whose schema hides a handle parameter, a model
    call made inside a tool, and a tool the cassette does not store running again on replay.
    A `FakeModelClient` returns a scripted response without reading what was sent, so none of
    those is testable against it. `TestGeminiTools` is the second backend.

    **The Mistral arm retired on 2026-08-19**, when a tool's version came to cover what its
    function closed over and that key could not be re-recorded against a backend out of credits.
    """

    @pytest.fixture(params=["tools-vllm"])
    def run(self, request, tmp_path: Path):
        name = request.param
        cassette = CASSETTES / f"{name}.jsonl"
        if not cassette.exists():
            pytest.skip(f"no recorded {name} cassette; run scripts/record_backend_cassettes.py")
        client = VLLMClient(
            model="Qwen/Qwen3-1.7B",
            model_revision=VLLM_REVISION,
            base_url="http://127.0.0.1:8001/v1",
        )
        basis = ComputeBasis(currency="USD", device="RTX-3090", device_count=1, hourly_rate=0.22)
        envelope = RunEnvelope(
            run_dir=tmp_path, cost_basis=basis, cassette=Cassette.replay(cassette)
        )
        result = tools_pipeline().run(
            {"question": TOOLS_QUESTION}, envelope=envelope, model=client, seed=SEED
        )
        return result, list(read_trajectory(result.paths.trajectory))

    def test_a_model_call_made_inside_a_tool_hangs_off_that_tool(self, run) -> None:
        _, records = run
        by_id = {r["record_id"]: r for r in records}
        extraction = next(r for r in records if r.get("tool_name") == "extract_facts")
        nested = [r for r in records if r["parent_id"] == extraction["record_id"]]

        assert [r["record_type"] for r in nested] == ["model_call"]
        assert by_id[extraction["parent_id"]]["record_type"] == "node_execution"

    def test_a_nested_call_is_written_before_the_tool_that_made_it(self, run) -> None:
        _, records = run
        extraction = next(r for r in records if r.get("tool_name") == "extract_facts")
        nested = next(r for r in records if r["parent_id"] == extraction["record_id"])

        assert nested["sequence"] < extraction["sequence"]

    def test_every_model_call_replayed_including_the_nested_one(self, run) -> None:
        # No key and no server are present, so a call that was not served would have raised.
        _, records = run
        calls = [r for r in records if r["record_type"] == "model_call"]

        assert len(calls) > 1
        assert all(r["replayed"] for r in calls)

    def test_a_handle_taking_tool_runs_again_rather_than_being_served(self, run) -> None:
        _, records = run
        by_name = {r["tool_name"]: r for r in records if r["record_type"] == "tool_call"}

        for name in ("extract_facts", "workspace_write"):
            assert by_name[name]["re_executed"] is True
            assert by_name[name]["replayed"] is False
            assert by_name[name]["cassette_key"] is None

    def test_a_filed_tool_is_served_from_the_cassette(self, run) -> None:
        _, records = run
        search_call = next(r for r in records if r.get("tool_name") == "document_search")

        assert search_call["re_executed"] is False
        assert search_call["replayed"] is True

    def test_the_replayed_run_wrote_its_own_workspace_file(self, run) -> None:
        # The write re-runs, so the replay's own directory holds what the live run wrote
        # there. A served write would have left the directory empty.
        result, records = run
        written = next(r for r in records if r.get("tool_name") == "workspace_write")

        assert (result.paths.workspace / written["inputs"]["path"]).is_file()

    def test_the_backend_was_offered_the_tool_without_its_handle(self, run) -> None:
        # Read from the recorded request rather than from the declaration, so this says what
        # the backend actually accepted rather than what the library meant to send.
        backends = [r["backend"] for r in run[1] if r["record_type"] == "model_call"]
        name = "tools" if "mistral" in str(backends[0]) else "tools-vllm"
        entries = [
            json.loads(line) for line in (CASSETTES / f"{name}.jsonl").read_text().splitlines()
        ]
        offered = next(
            t
            for entry in entries
            if entry["kind"] == "model_call"
            for t in entry["request"]["params"]["tools"]
            if t["name"] == "extract_facts"
        )

        assert set(offered["input_schema"]["properties"]) == {"text"}


class TestEvaluation:
    """k rollouts of a two-node pipeline, recorded against Mistral and replayed offline.

    This is what a `FakeModelClient` cannot show. It returns a scripted response without
    reading the request, so it cannot demonstrate that k rollouts at derived seeds produce k
    distinct cassette keys through the real wire path, that a two-node pipeline's records
    separate by node when a real backend produced them, or that the same question answered at a
    fixed seed and temperature 0 comes back differently on different rollouts.
    """

    @pytest.fixture
    def run(self, tmp_path: Path):
        cassette = CASSETTES / "eval.jsonl"
        if not cassette.exists():
            pytest.skip("no recorded eval cassette; run scripts/record_backend_cassettes.py eval")
        envelope = RunEnvelope(
            run_dir=tmp_path,
            cost_basis=MISTRAL_PRICES,
            cassette=Cassette.replay(cassette),
        )
        client = MistralClient(model="mistral-small-2603", api_key="not-used-in-replay")
        return eval_suite().run(
            envelope=envelope,
            model=client,
            split="held_out",
            k=EVAL_K,
            seed=EVAL_SEED,
            concurrency=1,
        )

    def entries(self, kind: str) -> list[dict]:
        return [
            json.loads(line)
            for line in (CASSETTES / "eval.jsonl").read_text().splitlines()
            if json.loads(line)["kind"] == kind
        ]

    def test_every_call_was_served_from_the_file(self, run) -> None:
        """No key, no network. The api_key above would fail a live call."""
        assert len(run.rollouts) == 9
        assert run.nodes["hunt"].replayed_calls == run.nodes["hunt"].model_calls
        assert run.nodes["verify"].replayed_calls == run.nodes["verify"].model_calls

    def test_the_two_nodes_report_separately(self, run) -> None:
        hunt, verify = run.nodes["hunt"], run.nodes["verify"]

        assert (hunt.node_kind, verify.node_kind) == ("agent", "llm")
        assert hunt.executions == verify.executions == 9
        assert hunt.tool_calls == 19
        assert verify.tool_calls == 0
        assert hunt.terminations == {"finish": 9}

    def test_the_same_question_answered_differently_across_rollouts(self, run) -> None:
        """At a fixed seed and temperature 0, which is what k rollouts exist to measure.

        Both examples with a value to find reported absence once and came back correct twice.
        A single rollout of either would have reported 1.0 or 0.0 for that example and looked
        equally authoritative.
        """
        for example_id in ("e1", "e2"):
            rollouts = sorted(
                (r for r in run.rollouts if r.example_id == example_id),
                key=lambda r: r.rollout,
            )

            assert [r.outcome.value for r in rollouts] == ["missed", "correct", "correct"]
            assert len({r.seed for r in rollouts}) == 3

    def test_the_metrics_are_what_the_live_run_produced(self, run) -> None:
        assert run.metrics["accuracy"].value == pytest.approx(7 / 9)
        assert run.metrics["recall"].value == pytest.approx(4 / 6)
        assert run.metrics["false_confidence_rate"].value == 0.0
        assert run.metrics["precision_when_asserting"].value == 1.0

    def test_every_interval_carries_the_n_and_k_it_was_computed_over(self, run) -> None:
        accuracy = run.metrics["accuracy"].interval

        assert (accuracy.n, accuracy.k) == (3, 3)
        assert accuracy.low < accuracy.point <= accuracy.high
        # Two of the three examples have a value to find, so recall is over those.
        assert run.metrics["recall"].interval.n == 2

    def test_each_rollout_is_its_own_request_to_the_backend(self, run) -> None:
        """The seed is in the key, so k rollouts of one example never share a response."""
        calls = self.entries("model_call")

        assert len({entry["key"] for entry in calls}) == len(calls) == 28
        assert len({entry["request"]["params"]["seed"] for entry in calls}) == 28

    def test_an_identical_tool_call_across_rollouts_is_stored_once(self, run) -> None:
        """19 tool calls, 4 entries. Repeating a rollout does not repeat the tool's work.

        A tool call is keyed on its name, version, arguments and occurrence within the run, and
        the seed is not in it, so two rollouts searching for the same words are one call. This
        is the mechanism FT-20 relies on to keep k rollouts from acting k times.
        """
        assert run.nodes["hunt"].tool_calls == 19
        assert len(self.entries("tool_call")) == 4

    def test_cost_derives_over_the_whole_evaluation(self, run) -> None:
        cost = run.totals["cost"]

        assert cost["currency"] == "USD"
        assert cost["basis"] == "price"
        assert cost["value"] > 0
        assert run.totals["tokens"]["input_uncached"] > 0

    def test_the_results_file_round_trips(self, run, tmp_path) -> None:
        path = run.write(tmp_path / "results.json")

        read_back = EvalResults.read(path)

        assert read_back.scores_by_example() == run.scores_by_example()
        assert read_back.config["model"]["request_model"] == "mistral-small-2603"
        assert read_back.config["cassette"]["mode"] == "replay"
        assert read_back.contamination.clean is True


class TestStreaming:
    """The streamed recordings, replayed. What each backend delivered is asserted per backend.

    Recorded 2026-08-04 against `mistral-small-2603` and against Qwen3-1.7B on a local vLLM
    server, each running one node that streams and one that does not.
    """

    @pytest.fixture(params=["stream", "stream-vllm", "stream-gemini"])
    def replayed(self, request, tmp_path):
        backend = request.param
        cassette = CASSETTES / f"{backend}.jsonl"
        if not cassette.exists():
            pytest.skip(f"no recorded {backend} cassette; run the recording script")

        if backend == "stream":
            client = MistralClient(model="mistral-small-2603", api_key="not-used")
            basis, extra = MISTRAL_PRICES, None
        elif backend == "stream-gemini":
            client = GeminiClient(
                model="gemini-3.1-flash-lite",
                api_key="not-used-in-replay",
                model_revision="3.1-flash-lite-05-2026",
            )
            basis, extra = GEMINI_PRICES, None
        else:
            client = VLLMClient(model="Qwen/Qwen3-1.7B", model_revision=VLLM_REVISION)
            basis, extra = VLLM_DEVICE, NO_THINKING

        pieces: list[str] = []
        result = stream_pipeline(extra).run(
            {"question": STREAM_QUESTION},
            envelope=RunEnvelope(
                run_dir=tmp_path, cost_basis=basis, cassette=Cassette.replay(cassette)
            ),
            model=client,
            seed=SEED,
            on_token=lambda event: pieces.append(event.text),
        )
        calls = [
            r for r in read_trajectory(result.paths.trajectory) if r["record_type"] == "model_call"
        ]
        return backend, result, pieces, calls

    def test_the_replay_re_emits_the_boundaries_the_backend_delivered(self, replayed) -> None:
        backend, _, pieces, calls = replayed
        streamed = calls[0]

        assert len(pieces) == streamed["stream"]["chunks"]
        assert "".join(pieces) == streamed["outputs"]["content"]
        assert len(pieces) > 1, f"{backend} delivered its answer in one piece"

    def test_the_recorded_time_to_first_token_survives_the_replay(self, replayed) -> None:
        _, _, _, calls = replayed

        assert calls[0]["replayed"] is True
        assert calls[0]["stream"]["first_chunk_ms"] > 0, (
            "a replay measures no real latency, so the recorded figure is carried"
        )

    def test_the_node_that_does_not_declare_it_records_no_stream(self, replayed) -> None:
        _, _, _, calls = replayed

        assert calls[1]["stream"] is None

    def test_the_token_counts_survive_streaming(self, replayed) -> None:
        backend, _, _, calls = replayed
        tokens = calls[0]["tokens"]

        assert isinstance(tokens["output"], int) and tokens["output"] > 0
        assert isinstance(tokens["input_uncached"], int)
        if backend == "stream-vllm":
            assert isinstance(tokens["input_cache_write"], int), (
                "--enable-prompt-tokens-details survives a streamed response"
            )
        if backend == "stream-gemini":
            assert tokens["input_cache_write"]["type"] == "unknown", (
                "a count this backend does not report stays unmeasured through a stream"
            )

    def test_mistral_publishes_no_allowance_on_the_streamed_call(self, replayed) -> None:
        """Both calls of one recording: the non-streamed one carries it, the streamed one not.

        Measured 2026-08-04. `PacedClient` reads this field, so a node declaring `stream=True`
        leaves it nothing to pace against.
        """
        backend, _, _, calls = replayed
        if backend != "stream":
            pytest.skip("vLLM publishes no allowance either way")

        assert calls[0]["rate_limit"] is None
        assert calls[1]["rate_limit"]["remaining_requests"] is not None

    def test_the_answer_came_back_through_the_schema(self, replayed) -> None:
        _, result, _, _ = replayed

        assert result.output.retailer == "Kirkwall"


GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_REVISION = "3.1-flash-lite-05-2026"


def gemini_client() -> MistralClient | VLLMClient | GeminiClient:
    """The same identity the recording was made under. A different one is a cassette miss."""
    return GeminiClient(
        model=GEMINI_MODEL, api_key="not-used-in-replay", model_revision=GEMINI_REVISION
    )


class TestGemini:
    @pytest.fixture
    def run(self, tmp_path: Path):
        return replay(tmp_path, "gemini", gemini_client(), GEMINI_PRICES)

    def test_the_recorded_answer_comes_back_through_the_schema(self, run) -> None:
        result, _, _ = run

        assert isinstance(result.output, Answer)
        assert result.output.answer == "Paris"

    def test_nothing_was_called(self, run) -> None:
        _, manifest, records = run

        assert manifest["cassette"]["hits"] == 1
        assert manifest["cassette"]["misses"] == 0
        assert [r["replayed"] for r in records if r["record_type"] == "model_call"] == [True]

    def test_the_manifest_pins_the_model_and_the_build_string(self, run) -> None:
        _, manifest, _ = run

        assert manifest["models"]["configured"] == {
            "backend": "hosted_api",
            "request_model": GEMINI_MODEL,
            "model_revision": GEMINI_REVISION,
        }

    def test_the_cache_write_count_stays_unknown_through_the_round_trip(self, run) -> None:
        # A count the backend does not report is written as unknown rather than as 0, and it
        # survives being recorded and read back rather than decoding as a number.
        _, _, records = run
        tokens = next(r for r in records if r["record_type"] == "model_call")["tokens"]

        assert tokens["input_cache_write"]["type"] == "unknown"
        assert tokens["input_uncached"] > 0
        assert tokens["cache_ttl"] is None

    def test_cost_derives_despite_the_unknown_count(self, run) -> None:
        # The rate for that class is declared 0.0, so no value of the count changes the total.
        # Without the rate every Gemini call prices as null and `max_cost` never fires.
        _, manifest, records = run
        cost = total_cost(records, GEMINI_PRICES)

        assert cost.known
        assert cost.is_upper_bound is False
        assert manifest["totals"]["cost"]["value"] == pytest.approx(cost.value)

    def test_a_basis_with_no_cache_write_rate_reports_no_cost(self, run) -> None:
        _, _, records = run
        no_rate = PriceBasis(
            currency="USD",
            input_uncached_per_mtok=0.25,
            input_cache_read_per_mtok=0.025,
            output_per_mtok=1.50,
        )

        cost = total_cost(records, no_rate)

        assert cost.known is False
        assert "cache-write" in str(cost.reason)


class TestGeminiAgentLoop:
    """The multi-turn path against a backend that refuses the turn after a dropped signature.

    Nothing else covers it. The conversation the loop builds carries each tool call back to the
    backend, and this one answers 400 unless the opaque string it sent with that call comes
    back verbatim. A `FakeModelClient` ignores the messages it is sent, so every test would
    pass over a conversation no backend accepts.
    """

    @pytest.fixture
    def run(self, tmp_path: Path):
        cassette = CASSETTES / "agent-gemini.jsonl"
        if not cassette.exists():
            pytest.skip("no recorded agent-gemini cassette; run the recording script")
        envelope = RunEnvelope(
            run_dir=tmp_path, cost_basis=GEMINI_PRICES, cassette=Cassette.replay(cassette)
        )
        result = agent_pipeline().run(
            {"question": AGENT_QUESTION},
            envelope=envelope,
            model=gemini_client(),
            seed=SEED,
        )
        return result, list(read_trajectory(result.paths.trajectory))

    def test_the_loop_reached_an_answer_through_the_schema(self, run) -> None:
        result, _ = run

        assert result.output.retailer == "Kirkwall"

    def test_it_took_more_than_one_turn(self, run) -> None:
        _, records = run
        calls = [r for r in records if r["record_type"] == "model_call"]

        assert len(calls) > 1

    def test_every_tool_call_records_the_signature_it_arrived_with(self, run) -> None:
        _, records = run
        calls = [
            call
            for r in records
            if r["record_type"] == "model_call"
            for call in r["outputs"]["tool_calls"]
        ]

        assert calls
        for call in calls:
            assert call["provider"]["thought_signature"]

    def test_the_signature_went_back_on_the_following_request(self, run) -> None:
        # Read from the recorded request rather than from the response, so this says what the
        # backend was sent and accepted. Sent without it, the same turn is answered with the
        # 400 captured as `tests/fixtures/wire/gemini/error_missing_signature.json`.
        entries = [
            json.loads(line) for line in (CASSETTES / "agent-gemini.jsonl").read_text().splitlines()
        ]
        later = [
            entry
            for entry in entries
            if entry["kind"] == "model_call" and len(entry["request"]["messages"]) > 1
        ]

        assert later
        for entry in later:
            for message in entry["request"]["messages"]:
                for call in message.get("tool_calls") or []:
                    assert call["provider"]["thought_signature"]


class TestGeminiTools:
    """The built-in tools against Gemini, replayed from a recording made against it."""

    @pytest.fixture
    def run(self, tmp_path: Path):
        cassette = CASSETTES / "tools-gemini.jsonl"
        if not cassette.exists():
            pytest.skip("no recorded tools-gemini cassette; run the recording script")
        envelope = RunEnvelope(
            run_dir=tmp_path, cost_basis=GEMINI_PRICES, cassette=Cassette.replay(cassette)
        )
        result = tools_pipeline().run(
            {"question": TOOLS_QUESTION}, envelope=envelope, model=gemini_client(), seed=SEED
        )
        return result, list(read_trajectory(result.paths.trajectory))

    def test_a_model_call_made_inside_a_tool_hangs_off_that_tool(self, run) -> None:
        _, records = run
        extraction = next(r for r in records if r.get("tool_name") == "extract_facts")
        nested = [r for r in records if r["parent_id"] == extraction["record_id"]]

        assert [r["record_type"] for r in nested] == ["model_call"]

    def test_a_handle_taking_tool_runs_again_rather_than_being_served(self, run) -> None:
        _, records = run
        by_name = {r["tool_name"]: r for r in records if r["record_type"] == "tool_call"}

        for name in ("extract_facts", "workspace_write"):
            assert by_name[name]["re_executed"] is True
            assert by_name[name]["cassette_key"] is None

    def test_the_backend_was_offered_the_tool_without_its_handle(self, run) -> None:
        # Read from the recorded request rather than from the declaration, so this says what
        # the backend actually accepted rather than what the library meant to send.
        entries = [
            json.loads(line) for line in (CASSETTES / "tools-gemini.jsonl").read_text().splitlines()
        ]
        offered = next(
            t
            for entry in entries
            if entry["kind"] == "model_call"
            for t in entry["request"]["params"]["tools"]
            if t["name"] == "extract_facts"
        )

        assert set(offered["input_schema"]["properties"]) == {"text"}


class TestGeminiEvaluation:
    """k rollouts of a two-node pipeline, recorded against Gemini and replayed offline.

    The hosted arm of the evaluation machinery. It runs without a paced client, because this
    backend publishes no allowance to pace against.
    """

    @pytest.fixture
    def run(self, tmp_path: Path):
        cassette = CASSETTES / "eval-gemini.jsonl"
        if not cassette.exists():
            pytest.skip("no recorded eval-gemini cassette; run the recording script")
        envelope = RunEnvelope(
            run_dir=tmp_path, cost_basis=GEMINI_PRICES, cassette=Cassette.replay(cassette)
        )
        return eval_suite().run(
            envelope=envelope,
            model=gemini_client(),
            split="held_out",
            k=EVAL_K,
            seed=EVAL_SEED,
            concurrency=1,
        )

    def test_every_call_was_served_from_the_file(self, run) -> None:
        assert len(run.rollouts) == 9
        assert run.nodes["hunt"].replayed_calls == run.nodes["hunt"].model_calls
        assert run.nodes["verify"].replayed_calls == run.nodes["verify"].model_calls

    def test_each_rollout_is_its_own_request_to_the_backend(self, run) -> None:
        calls = [
            json.loads(line)
            for line in (CASSETTES / "eval-gemini.jsonl").read_text().splitlines()
            if json.loads(line)["kind"] == "model_call"
        ]

        assert len({entry["key"] for entry in calls}) == len(calls)
        assert len({entry["request"]["params"]["seed"] for entry in calls}) == len(calls)

    def test_cost_derives_over_the_whole_evaluation(self, run) -> None:
        cost = run.totals["cost"]

        assert cost["basis"] == "price"
        assert cost["value"] > 0
        assert run.totals["tokens"]["input_uncached"] > 0

    def test_the_metrics_are_what_the_live_run_produced(self, run) -> None:
        assert run.metrics["accuracy"].value == pytest.approx(1.0)
        assert run.metrics["false_confidence_rate"].value == 0.0
