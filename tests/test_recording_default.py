"""Every run records, and the recording is sampled with the trajectory's payloads.

Before this, a cassette was something the project remembered to ask for, and a dogfood run on
2026-08-10 did not: an evaluation ended on a metric that raised and the only path back to a
number was the GPU time again. The default closes that. The linkage is the other half: a
`model_call` record already carries the whole prompt and the whole response, so a cassette that
outlived a sampled trajectory would be the only copy of what a project asked to stop keeping.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Prompt,
    Budget,
    CallerFacingError,
    Cassette,
    ConfigurationError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Pipeline,
    RunEnvelope,
    RunSuspended,
    Trajectory,
)
from simple_agents.records.cassette import CassetteEntry
from simple_agents.evaluation import evaluation_dir, EvalSuite, Example, ExampleSet
from simple_agents.models import fake_response

from conftest import run_path, RUN_ID
from schemas import Answer

BUDGET = Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def prompt(inputs, ctx) -> str:
    return Prompt.user("Answer: {question}", question=inputs["question"])


def client(reached: list[str] | None = None) -> FakeModelClient:
    class Counting(FakeModelClient):
        def complete(self, request):
            if reached is not None:
                reached.append("call")
            return super().complete(request)

    return Counting(responses=[fake_response(content='{"answer": "ok", "source": null}')] * 400)


def pipeline() -> Pipeline:
    return Pipeline([LLMNode(prompt, output_schema=Answer, node_id="extract")], budget=BUDGET)


def cassettes(root: Path) -> list[Path]:
    """Every cassette file anywhere under a run directory."""
    return sorted(root.rglob("cassette.jsonl"))


def manifest_of(root: Path, run_id: str = RUN_ID) -> dict:
    return json.loads(run_path(root, run_id, "manifest.json").read_text(encoding="utf-8"))


def run_ids_by_fate(rate: float) -> tuple[str, str]:
    """One run id whose payloads are kept at this rate, and one whose are not."""
    trajectory = Trajectory.sampled(rate)
    kept = next(f"run_k{i}" for i in range(500) if trajectory.keeps(f"run_k{i}"))
    dropped = next(f"run_d{i}" for i in range(500) if not trajectory.keeps(f"run_d{i}"))
    return kept, dropped


class TestARunRecords:
    def test_a_run_writes_a_cassette_beside_its_trajectory(self, tmp_path) -> None:
        result = pipeline().run(
            {"question": "q?"},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=client(),
            run_id=RUN_ID,
            seed=41,
        )

        recorded = Path(result.paths.root) / "cassette.jsonl"
        assert recorded.exists()
        assert manifest_of(tmp_path)["cassette"]["path"] == str(recorded)
        assert manifest_of(tmp_path)["cassette"]["recorded"] == 1

    def test_the_default_recording_replays_the_run_it_was_made_from(self, tmp_path) -> None:
        pipeline().run(
            {"question": "q?"},
            envelope=RunEnvelope(run_dir=tmp_path),
            model=client(),
            run_id=RUN_ID,
            seed=41,
        )
        reached: list[str] = []

        replayed = pipeline().run(
            {"question": "q?"},
            envelope=RunEnvelope(
                run_dir=tmp_path / "again",
                cassette=Cassette.replay(run_path(tmp_path, RUN_ID, "cassette.jsonl")),
            ),
            model=client(reached),
            seed=41,
        )

        assert reached == [], "a replayed run must not reach the backend"
        assert replayed.output.answer == "ok"

    def test_cassette_off_records_nothing(self, tmp_path) -> None:
        pipeline().run(
            {"question": "q?"},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
            model=client(),
            run_id=RUN_ID,
            seed=41,
        )

        assert cassettes(tmp_path) == []
        assert manifest_of(tmp_path)["cassette"]["mode"] == "off"

    def test_a_run_with_no_envelope_at_all_records(self, tmp_path, monkeypatch) -> None:
        """`Pipeline.run` with no envelope builds one, and it is the recording default."""
        monkeypatch.chdir(tmp_path)

        pipeline().run({"question": "q?"}, model=client(), run_id=RUN_ID, seed=41)

        assert cassettes(tmp_path / "runs") == [
            run_path(tmp_path / "runs", RUN_ID, "cassette.jsonl")
        ]

    def test_an_unresolved_recording_refuses_to_store_rather_than_dropping_the_call(self) -> None:
        """The failure a silent no-op hid: a recording with nowhere to write."""
        entry = CassetteEntry(
            key="ck_one",
            kind="model_call",
            node_id="extract",
            call_index=0,
            recorded_at="2026-08-11T00:00:00.000Z",
            request={},
            response={},
        )

        with pytest.raises(CallerFacingError) as raised:
            Cassette.into_run().store(entry)

        assert "for_run" in str(raised.value)


class TestTheCassetteSamplesWithTheTrajectory:
    def test_a_run_whose_payloads_are_dropped_loses_its_recording(self, tmp_path) -> None:
        _, dropped = run_ids_by_fate(0.5)

        pipeline().run(
            {"question": "q?"},
            envelope=RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.5)),
            model=client(),
            run_id=dropped,
            seed=41,
        )

        manifest = manifest_of(tmp_path, dropped)
        assert cassettes(tmp_path) == []
        assert manifest["recording"]["payloads"] == "omitted"
        assert manifest["cassette"]["dropped"] == "sampling"
        assert manifest["cassette"]["recorded"] == 1, "what it recorded before the drop"

    def test_a_run_whose_payloads_are_kept_keeps_its_recording(self, tmp_path) -> None:
        kept, _ = run_ids_by_fate(0.5)

        pipeline().run(
            {"question": "q?"},
            envelope=RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.5)),
            model=client(),
            run_id=kept,
            seed=41,
        )

        manifest = manifest_of(tmp_path, kept)
        assert cassettes(tmp_path) == [run_path(tmp_path, kept, "cassette.jsonl")]
        assert manifest["recording"]["payloads"] == "kept"
        assert manifest["cassette"]["dropped"] is None

    def test_sampled_zero_keeps_neither(self, tmp_path) -> None:
        """What a builder who does not want the material on disk is given."""
        result = pipeline().run(
            {"question": "q?"},
            envelope=RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.0)),
            model=client(),
            run_id=RUN_ID,
            seed=41,
        )

        records = [
            json.loads(line)
            for line in (Path(result.paths.root) / "trajectory.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        calls = [r for r in records if r["record_type"] == "model_call"]
        assert cassettes(tmp_path) == []
        assert calls and all(
            call["outputs"] == {"type": "not_recorded", "reason": "sampling"} for call in calls
        )

    def test_a_cassette_the_project_named_is_not_deleted(self, tmp_path) -> None:
        """Deleting a file the project chose the path of would be deleting its file."""
        _, dropped = run_ids_by_fate(0.5)
        chosen = tmp_path / "mine.jsonl"

        pipeline().run(
            {"question": "q?"},
            envelope=RunEnvelope(
                run_dir=tmp_path,
                trajectory=Trajectory.sampled(0.5),
                cassette=Cassette.record(chosen),
            ),
            model=client(),
            run_id=dropped,
            seed=41,
        )

        assert chosen.exists()
        assert manifest_of(tmp_path, dropped)["cassette"]["dropped"] is None

    def test_a_run_that_errored_keeps_both(self, tmp_path) -> None:
        """The trajectory keeps its payloads on a failure at any rate, and so does the file
        holding the same content."""
        _, dropped = run_ids_by_fate(0.5)

        def explode(inputs, ctx):
            raise RuntimeError("no")

        broken = Pipeline(
            [
                LLMNode(prompt, output_schema=Answer, node_id="extract", successors=["boom"]),
                Deterministic(explode, node_id="boom"),
            ],
            budget=BUDGET,
        )

        with pytest.raises(RuntimeError):
            broken.run(
                {"question": "q?"},
                envelope=RunEnvelope(run_dir=tmp_path, trajectory=Trajectory.sampled(0.5)),
                model=client(),
                run_id=dropped,
                seed=41,
            )

        assert cassettes(tmp_path) == [run_path(tmp_path, dropped, "cassette.jsonl")]
        assert manifest_of(tmp_path, dropped)["recording"]["payloads"] == "kept"


class TestARunDirectoryUsedTwice:
    def test_a_repeated_run_id_appends_the_way_the_trajectory_does(self, tmp_path) -> None:
        """`Cassette.record` refuses a used file. The default cannot, or a resumed run would
        meet that refusal on a file it wrote itself."""
        envelope = RunEnvelope(run_dir=tmp_path)

        pipeline().run(
            {"question": "q?"}, envelope=envelope, model=client(), run_id=RUN_ID, seed=41
        )
        pipeline().run(
            {"question": "q?"}, envelope=envelope, model=client(), run_id=RUN_ID, seed=42
        )

        recorded = run_path(tmp_path, RUN_ID, "cassette.jsonl").read_text().splitlines()
        trajectory = (run_path(tmp_path, RUN_ID, "trajectory.jsonl")).read_text().splitlines()
        assert len(recorded) == 2, "one entry per seed, since the seed is in the key"
        # Two records a run: the `run_start` and the node's own.
        assert len(trajectory) == 6, "the trajectory appends too"

    def test_a_resumed_run_records_into_the_file_its_first_half_wrote(self, tmp_path) -> None:
        """The case that decides it: a resume writes into the run's own directory, so a
        default going through `Cassette.record` would refuse the file it had just written."""
        stopping = Pipeline(
            [
                LLMNode(prompt, output_schema=Answer, node_id="extract", successors=["pause"]),
                Deterministic(
                    lambda inputs, ctx: {"question": "second?"},
                    node_id="pause",
                    suspend_before=True,
                    successors=["confirm"],
                ),
                LLMNode(prompt, output_schema=Answer, node_id="confirm"),
            ],
            budget=BUDGET,
        )
        envelope = RunEnvelope(run_dir=tmp_path)

        with pytest.raises(RunSuspended):
            stopping.run(
                {"question": "q?"}, envelope=envelope, model=client(), run_id=RUN_ID, seed=41
            )
        halfway = run_path(tmp_path, RUN_ID, "cassette.jsonl").read_text().splitlines()

        stopping.resume(RUN_ID, envelope=envelope, model=client())

        assert len(halfway) == 1
        assert len(run_path(tmp_path, RUN_ID, "cassette.jsonl").read_text().splitlines()) == 2


class TestAnEvaluationStillGetsOneCassette:
    """k rollouts of one example share the calls they make in common, which is what stops a
    paid tool being bought once per rollout (FT-20). One file per rollout would end that."""

    def suite(self) -> EvalSuite:
        return EvalSuite(
            pipeline(),
            ExampleSet(
                [
                    Example(
                        id=f"q{i}", inputs={"question": f"q{i}?"}, expected="ok", split="held_out"
                    )
                    for i in range(3)
                ]
            ),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
        )

    def test_the_rollouts_write_one_file_between_them(self, tmp_path) -> None:
        results = self.suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=client(),
            split="held_out",
            k=3,
            seed=41,
        )

        assert cassettes(tmp_path) == [evaluation_dir(tmp_path, results.eval_id) / "cassette.jsonl"]

    def test_record_false_writes_no_cassette_anywhere(self, tmp_path) -> None:
        self.suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=client(),
            split="held_out",
            k=3,
            seed=41,
            record=False,
        )

        assert cassettes(tmp_path) == []

    def test_an_envelope_that_says_off_stays_off(self, tmp_path) -> None:
        """`Cassette.off()` is a statement now that the default records, so an evaluation
        honours it rather than recording over it."""
        results = self.suite().run(
            envelope=RunEnvelope(run_dir=tmp_path, cassette=Cassette.off()),
            model=client(),
            split="held_out",
            k=1,
            seed=41,
        )

        assert cassettes(tmp_path) == []
        assert results.config["cassette"]["mode"] == "off"

    def test_record_refuses_the_default_and_names_a_path(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            self.suite().record(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=client(),
                split="held_out",
                k=1,
                seed=41,
            )

        assert "Cassette.record(" in str(raised.value)
