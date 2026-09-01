"""The graph run against a real backend, replayed from the cassette it recorded.

The cassettes under `tests/cassettes/` were recorded by
`scripts/record_backend_cassettes.py` against Mistral and against a local vLLM server. These
tests replay them, so they need no key, no server and no network.

What a fake client cannot show is here. Which arm runs is the model's decision, made by
filling a schema field the route reads, so the branch and the skip are properties of what a
backend answered rather than of a scripted reply. The cassette key covers the whole request,
so a change to what the library sends is a miss rather than a silently different run.
"""

from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from record_backend_cassettes import (  # noqa: E402
    GEMINI_MODEL,
    GEMINI_PRICES,
    GEMINI_REVISION,
    GRAPH_QUESTIONS,
    MISTRAL_PRICES,
    NO_THINKING,
    SEED,
    graph_loop_pipeline,
    graph_pipeline,
)

from simple_agents import (  # noqa: E402
    Cassette,
    GeminiClient,
    MistralClient,
    RunEnvelope,
    VLLMClient,
    read_trajectory,
)

CASSETTES = Path(__file__).parent / "cassettes"
VLLM_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"


def replaying(tmp_path: Path, cassette: str) -> RunEnvelope:
    return RunEnvelope(
        run_dir=tmp_path,
        cost_basis=MISTRAL_PRICES,
        cassette=Cassette.replay(CASSETTES / cassette),
    )


def client() -> MistralClient:
    """No key needed: every call is served from the file."""
    return MistralClient(model="mistral-small-2603", api_key="unused")


def nodes(trajectory: Path) -> list[dict]:
    return [
        record
        for record in read_trajectory(trajectory)
        if record["record_type"] == "node_execution"
    ]


def by_id(trajectory: Path) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for record in nodes(trajectory):
        found.setdefault(record["node_id"], []).append(record)
    return found


class TestBranchAndSkip:
    """One recording, two questions: the notes answer the first and not the second.

    Recorded against Gemini. It was Mistral until 2026-08-28, when `str(Unknown)` changed
    what a prompt built with an f-string renders, which moved two of that recording's keys.
    Mistral is out of credits, so the arm could not be re-recorded and a new one was made,
    which is what `handoff.md` says to do. Gemini takes the same route on both questions,
    so every assertion below is the one the Mistral arm carried.
    """

    def run(self, tmp_path: Path, question: str):
        return graph_pipeline().run(
            {"question": question},
            envelope=self.replaying(tmp_path),
            model=self.client(),
            seed=SEED,
        )

    def replaying(self, tmp_path: Path) -> RunEnvelope:
        return RunEnvelope(
            run_dir=tmp_path,
            cost_basis=GEMINI_PRICES,
            cassette=Cassette.replay(CASSETTES / "graph-gemini.jsonl"),
        )

    def client(self) -> GeminiClient:
        """No key needed: every call is served from the file."""
        return GeminiClient(model=GEMINI_MODEL, model_revision=GEMINI_REVISION, api_key="unused")

    def test_an_answerable_question_runs_both_arms_of_the_parallel_branch(self, tmp_path):
        result = self.run(tmp_path, GRAPH_QUESTIONS[0])

        assert result.output["fired"] == ["summarise", "cite"]
        ran = {r["node_id"] for r in nodes(result.trajectory_path) if r["termination"] != "skipped"}
        assert ran == {"classify", "hunt", "summarise", "cite", "report"}

    def test_the_arm_the_model_did_not_choose_is_absent_at_the_join(self, tmp_path):
        result = self.run(tmp_path, GRAPH_QUESTIONS[0])

        assert result.output["absent"] == ["classify"]
        recorded = by_id(result.trajectory_path)["report"][0]["inputs"]
        assert recorded["type"] == "join"
        assert sorted(recorded["edges"]) == ["cite", "classify", "summarise"]
        assert recorded["absent"] == ["classify"]

    def test_a_question_the_notes_do_not_answer_skips_three_nodes(self, tmp_path):
        result = self.run(tmp_path, GRAPH_QUESTIONS[1])

        skipped = {
            r["node_id"] for r in nodes(result.trajectory_path) if r["termination"] == "skipped"
        }
        assert skipped == {"hunt", "summarise", "cite"}
        assert result.output["fired"] == ["classify"]

    def test_a_skipped_node_records_no_output_and_no_model_call(self, tmp_path):
        result = self.run(tmp_path, GRAPH_QUESTIONS[1])

        records = list(read_trajectory(result.trajectory_path))
        hunt = by_id(result.trajectory_path)["hunt"][0]
        assert hunt["outputs"] is None
        assert hunt["route"] == []
        made = {r["parent_id"] for r in records if r["record_type"] == "model_call"}
        assert hunt["record_id"] not in made

    def test_the_route_the_model_chose_is_on_its_record(self, tmp_path):
        found = self.run(tmp_path, GRAPH_QUESTIONS[0])
        absent = self.run(tmp_path, GRAPH_QUESTIONS[1])

        assert by_id(found.trajectory_path)["classify"][0]["route"] == ["hunt"]
        assert by_id(absent.trajectory_path)["classify"][0]["route"] == ["report"]

    def test_every_call_was_served_from_the_file(self, tmp_path):
        result = self.run(tmp_path, GRAPH_QUESTIONS[0])

        calls = [
            r for r in read_trajectory(result.trajectory_path) if r["record_type"] == "model_call"
        ]
        assert calls and all(r["replayed"] for r in calls)
        assert result.manifest["cassette"]["misses"] == 0


class TestCycleAndErrorEdge:
    def run(self, tmp_path: Path):
        return graph_loop_pipeline().run(
            {}, envelope=replaying(tmp_path, "graph-loop.jsonl"), model=client(), seed=SEED
        )

    def test_the_cycle_runs_until_the_bound_stops_it(self, tmp_path):
        result = self.run(tmp_path)

        drafts = by_id(result.trajectory_path)["draft"]
        assert len(drafts) == 2
        assert [r["loop"]["iteration"] for r in drafts] == [1, 2]

    def test_the_last_iteration_says_the_bound_stopped_it(self, tmp_path):
        result = self.run(tmp_path)

        last = by_id(result.trajectory_path)["critique"][-1]
        assert last["termination"] == "max_iterations"
        assert last["loop"]["exhausted"] is True
        assert last["route"] == ["lookup"]

    def test_each_iteration_made_its_own_model_call(self, tmp_path):
        """Two drafts, two calls, two seeds. A replayed cycle is not one call served twice."""
        result = self.run(tmp_path)

        drafts = {r["record_id"] for r in by_id(result.trajectory_path)["draft"]}
        calls = [
            r
            for r in read_trajectory(result.trajectory_path)
            if r["record_type"] == "model_call" and r["parent_id"] in drafts
        ]
        assert len(calls) == 2
        assert len({r["seed"] for r in calls}) == 2
        assert len({r["cassette_key"] for r in calls}) == 2

    def test_an_exhausted_retry_takes_the_error_edge(self, tmp_path):
        result = self.run(tmp_path)

        attempts = by_id(result.trajectory_path)["lookup"]
        assert [r["termination"] for r in attempts] == ["error", "error"]
        assert attempts[0]["route"] == []
        assert attempts[1]["route"] == ["fallback"]

    def test_the_handler_receives_what_failed(self, tmp_path):
        result = self.run(tmp_path)

        recorded = by_id(result.trajectory_path)["fallback"][0]["inputs"]
        assert recorded["type"] == "node_failure"
        assert recorded["node_id"] == "lookup"
        assert recorded["attempts"] == 2
        assert result.output["absent"] == ["lookup"]

    def test_the_run_completed_despite_the_failure(self, tmp_path):
        result = self.run(tmp_path)

        assert result.outcome == "completed"
        assert result.output["fired"] == ["fallback"]


class TestAgainstVLLM:
    """The same two graphs against a self-hosted server, which answers differently."""

    def envelope(self, tmp_path: Path, cassette: str) -> RunEnvelope:
        return RunEnvelope(run_dir=tmp_path, cassette=Cassette.replay(CASSETTES / cassette))

    def client(self) -> VLLMClient:
        return VLLMClient(model="Qwen/Qwen3-1.7B", model_revision=VLLM_REVISION)

    def pipeline(self):
        return graph_pipeline(NO_THINKING)

    def test_the_branch_is_taken_on_what_this_backend_answered(self, tmp_path):
        results = [
            self.pipeline().run(
                {"question": question},
                envelope=self.envelope(tmp_path / f"q{index}", "graph-vllm.jsonl"),
                model=self.client(),
                seed=SEED,
            )
            for index, question in enumerate(GRAPH_QUESTIONS)
        ]

        for result in results:
            recorded = by_id(result.trajectory_path)["report"][0]["inputs"]
            assert recorded["type"] == "join"
            assert sorted(recorded["edges"]) == ["cite", "classify", "summarise"]
            # One of the two paths is taken, and the other's edges are absent.
            assert recorded["absent"]

    def test_this_backend_answered_a_value_to_both_questions_and_ran_every_node(self, tmp_path):
        """A 1.7B model put the word "unknown" in the string field rather than the tagged
        object, so the route read an asserted answer and no node was skipped. What is asserted
        is what this backend did, not what the larger one did."""
        result = self.pipeline().run(
            {"question": GRAPH_QUESTIONS[1]},
            envelope=self.envelope(tmp_path, "graph-vllm.jsonl"),
            model=self.client(),
            seed=SEED,
        )

        terminations = {r["node_id"]: r["termination"] for r in nodes(result.trajectory_path)}
        assert set(terminations) == {"classify", "hunt", "summarise", "cite", "report"}
        assert all(value != "skipped" for value in terminations.values())
        assert result.output["answer"] == "unknown"

    def test_the_cycle_and_the_error_edge_behave_the_same_on_a_second_backend(self, tmp_path):
        result = graph_loop_pipeline(NO_THINKING).run(
            {},
            envelope=self.envelope(tmp_path, "graph-loop-vllm.jsonl"),
            model=self.client(),
            seed=SEED,
        )

        assert len(by_id(result.trajectory_path)["draft"]) == 2
        assert by_id(result.trajectory_path)["critique"][-1]["termination"] == "max_iterations"
        assert [r["termination"] for r in by_id(result.trajectory_path)["lookup"]] == [
            "error",
            "error",
        ]
        assert result.output["fired"] == ["fallback"]
