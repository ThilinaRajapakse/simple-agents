"""Reading run directories back, which is the other half of writing them.

Most of these build a run directory by hand, because a reader can only be verified against
files whose contents the test already knows. The last one drives a real pipeline and reads
what it wrote, so a hand-built fixture drifting from what the envelope produces is caught.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from simple_agents import (
    Budget,
    Cassette,
    ConfigurationError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Pipeline,
    Redaction,
    RunEnvelope,
    Trajectory,
    Unknown,
    runs,
)
from simple_agents.envelope import RunHandle
from simple_agents.models import fake_response

from schemas import Answer

from conftest import run_path


def write_run(
    root: Path,
    run_id: str,
    *,
    started_at: str = "2026-08-09T01:42:33.000Z",
    outcome: str | None = "completed",
    nodes: list[dict] | None = None,
    manifest: str | None = None,
) -> Path:
    """One run directory, with only the fields a reader of it looks at."""
    directory = root / run_id
    directory.mkdir(parents=True, exist_ok=True)
    if manifest is None:
        manifest = json.dumps({"run_id": run_id, "started_at": started_at, "outcome": outcome})
    (directory / "manifest.json").write_text(manifest, encoding="utf-8")
    records = [
        {
            "record_type": "node_execution",
            "run_id": run_id,
            "node_id": entry["node_id"],
            "outputs": entry.get("outputs"),
            "termination": entry.get("termination"),
        }
        for entry in (nodes or [])
    ]
    (directory / "trajectory.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    return directory


# -- what is listed, and in what order -----------------------------------------------------


def test_runs_come_back_newest_first_by_the_manifest_s_own_start_time(tmp_path: Path) -> None:
    write_run(tmp_path, "run_b", started_at="2026-08-09T02:00:00.000Z")
    write_run(tmp_path, "run_a", started_at="2026-08-09T01:00:00.000Z")
    write_run(tmp_path, "run_c", started_at="2026-08-09T03:00:00.000Z")

    assert [run.run_id for run in runs(tmp_path)] == ["run_c", "run_b", "run_a"]
    assert [run.run_id for run in reversed(runs(tmp_path))] == ["run_a", "run_b", "run_c"]


def test_an_evaluation_s_rollouts_are_not_listed_beside_the_runs_a_project_launched(
    tmp_path: Path,
) -> None:
    write_run(tmp_path, "run_a")
    write_run(tmp_path / "eval_e5a1bbef5a22", "e1-0", started_at="2026-08-09T02:00:00.000Z")
    write_run(tmp_path / "eval_e5a1bbef5a22", "e1-1", started_at="2026-08-09T01:00:00.000Z")

    assert [run.run_id for run in runs(tmp_path)] == ["run_a"]
    assert len(runs(tmp_path, nested=True)) == 3
    assert [run.run_id for run in runs(tmp_path / "eval_e5a1bbef5a22")] == ["e1-0", "e1-1"]


def test_a_directory_with_no_runs_in_it_is_not_an_error(tmp_path: Path) -> None:
    assert runs(tmp_path) == []
    assert runs(tmp_path / "nothing-here") == []


def test_a_run_whose_manifest_cannot_be_parsed_is_still_a_run(tmp_path: Path) -> None:
    write_run(tmp_path, "run_broken", manifest="{not json")

    (found,) = runs(tmp_path)

    assert found.run_id == "run_broken"
    assert found.manifest == {}
    assert found.outcome is None
    assert found.finished is False
    assert "is not JSON" in str(found.unreadable)


def test_a_readable_run_says_nothing_was_unreadable(tmp_path: Path) -> None:
    write_run(tmp_path, "run_a")

    assert runs(tmp_path)[0].unreadable is None


# -- what a handle says --------------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome, finished",
    [
        ("completed", True),
        ("stopped_early", True),
        ("suspended", False),
        ("error", False),
        (None, False),
    ],
)
def test_finished_covers_the_two_outcomes_that_reached_an_end(
    tmp_path: Path, outcome: str | None, finished: bool
) -> None:
    write_run(tmp_path, "run_a", outcome=outcome)

    assert runs(tmp_path)[0].finished is finished


def test_the_paths_come_from_the_directory_rather_than_from_the_manifest(
    tmp_path: Path,
) -> None:
    """A run directory that was moved still resolves, which a recorded path would not."""
    directory = write_run(tmp_path, "run_a")
    moved = tmp_path / "archive" / "run_a"
    moved.parent.mkdir()
    directory.rename(moved)

    (found,) = runs(tmp_path / "archive")

    assert found.trajectory_path == moved / "trajectory.jsonl"
    assert found.manifest_path == moved / "manifest.json"
    assert found.path == moved


# -- reading a node's output ---------------------------------------------------------------


def test_a_node_answers_for_its_last_execution(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run_a",
        nodes=[
            {"node_id": "draft", "outputs": {"text": "first"}},
            {"node_id": "draft", "outputs": {"text": "second"}},
            {"node_id": "draft", "outputs": {"text": "third"}},
        ],
    )

    assert runs(tmp_path)[0].outputs_of("draft") == {"text": "third"}


def test_node_ids_are_in_the_order_each_node_first_ran(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run_a",
        nodes=[
            {"node_id": "hunt", "outputs": {}},
            {"node_id": "verify", "outputs": {}},
            {"node_id": "hunt", "outputs": {}},
        ],
    )

    assert runs(tmp_path)[0].node_ids == ("hunt", "verify")


def test_a_skipped_node_did_not_run(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run_a",
        nodes=[
            {"node_id": "hunt", "outputs": {"answer": "Kirkwall"}},
            {"node_id": "verify", "outputs": None, "termination": "skipped"},
        ],
    )

    (found,) = runs(tmp_path)

    assert found.node_ids == ("hunt",)
    with pytest.raises(LookupError):
        found.outputs_of("verify")


def test_a_node_that_produced_nothing_answers_none(tmp_path: Path) -> None:
    write_run(tmp_path, "run_a", nodes=[{"node_id": "report", "outputs": None}])

    assert runs(tmp_path)[0].outputs_of("report") is None


def test_a_node_that_never_ran_raises_and_names_the_ones_that_did(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run_a",
        nodes=[{"node_id": "hunt", "outputs": {}}, {"node_id": "chase", "outputs": {}}],
    )

    with pytest.raises(LookupError) as raised:
        runs(tmp_path)[0].outputs_of("report")

    message = str(raised.value)
    assert "'report' did not run" in message
    assert "hunt, chase" in message
    assert "run.node_ids" in message


def test_a_run_with_no_trajectory_says_so_rather_than_naming_no_nodes(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "run_a")
    (directory / "trajectory.jsonl").unlink()

    with pytest.raises(LookupError) as raised:
        runs(tmp_path)[0].outputs_of("report")

    assert "wrote no trajectory" in str(raised.value)


def test_a_recorded_absence_comes_back_as_unknown_wherever_it_sits(tmp_path: Path) -> None:
    write_run(
        tmp_path,
        "run_a",
        nodes=[
            {
                "node_id": "chase",
                "outputs": {
                    "source": {"type": "unknown", "reason": "no size chart"},
                    "evidence_url": "https://example.test/tee",
                    "rows": [{"chest_cm": {"type": "unknown", "reason": "not listed"}}],
                },
            }
        ],
    )

    output = runs(tmp_path)[0].outputs_of("chase")

    assert isinstance(output["source"], Unknown)
    assert output["source"].reason == "no size chart"
    assert isinstance(output["rows"][0]["chest_cm"], Unknown)
    assert output["evidence_url"] == "https://example.test/tee"


def test_a_payload_dropped_by_sampling_comes_back_as_the_record_holds_it(
    tmp_path: Path,
) -> None:
    write_run(
        tmp_path,
        "run_a",
        nodes=[
            {
                "node_id": "report",
                "outputs": {"type": "not_recorded", "reason": "sampling"},
            }
        ],
    )

    assert runs(tmp_path)[0].outputs_of("report") == {
        "type": "not_recorded",
        "reason": "sampling",
    }


def test_the_trajectory_is_read_once_however_many_nodes_are_asked_for(
    tmp_path: Path,
) -> None:
    write_run(tmp_path, "run_a", nodes=[{"node_id": "hunt", "outputs": {"a": 1}}])
    (found,) = runs(tmp_path)
    found.outputs_of("hunt")

    found.trajectory_path.unlink()

    assert found.outputs_of("hunt") == {"a": 1}


# -- against a real run --------------------------------------------------------------------


def test_a_real_run_reads_back_through_the_same_surface(tmp_path: Path) -> None:
    """The fixtures above are hand-built, so one run through the writer holds them honest."""
    pipeline = Pipeline(
        [
            Deterministic(lambda inputs, ctx: inputs["question"], node_id="prepare"),
            LLMNode(
                lambda question, ctx: f"Answer: {question}",
                output_schema=Answer,
                node_id="extract",
            ),
        ],
        budget=Budget(max_steps=4, max_tokens=1000, max_cost=None, max_wall_clock_ms=10_000),
    )
    client = FakeModelClient(
        responses=[
            fake_response(
                content=json.dumps({"answer": {"type": "unknown", "reason": "not in the text"}})
            )
        ]
    )

    result = pipeline.run(
        {"question": "How long is the sleeve?"},
        envelope=RunEnvelope(run_dir=tmp_path),
        model=client,
    )

    (found,) = runs(tmp_path)
    assert found.run_id == result.run_id
    assert found.finished is True
    assert found.outcome == "completed"
    assert found.node_ids == ("prepare", "extract")
    assert found.outputs_of("prepare") == "How long is the sleeve?"
    assert isinstance(found.outputs_of("extract")["answer"], Unknown)
    assert found.manifest["totals"]["tokens"] == result.tokens


def test_a_generated_run_id_carries_the_time_the_run_started(tmp_path: Path) -> None:
    """Fixed width and zero padded, so a directory listing reads in the order runs happened."""
    pipeline = Pipeline([Deterministic(lambda inputs, ctx: inputs, node_id="echo")])

    run_id = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path)).run_id

    assert re.fullmatch(r"run_\d{8}T\d{6}Z_[0-9a-f]{8}", run_id), run_id
    started = json.loads((run_path(tmp_path, run_id, "manifest.json")).read_text())["started_at"]
    assert run_id[4:12] == started[:4] + started[5:7] + started[8:10]


def test_two_runs_inside_one_second_are_ordered_by_the_manifest_rather_than_the_name(
    tmp_path: Path,
) -> None:
    """The id holds seconds, so two runs inside one can carry it in either order.

    `started_at` is what orders them, and it holds milliseconds. The earlier run's manifest is
    aged by hand here because two runs of this pipeline can land in one millisecond too, which
    no key separates.
    """
    pipeline = Pipeline([Deterministic(lambda inputs, ctx: inputs, node_id="echo")])
    envelope = RunEnvelope(run_dir=tmp_path)

    first = pipeline.run({}, envelope=envelope).run_id
    second = pipeline.run({}, envelope=envelope).run_id

    manifest_path = run_path(tmp_path, first, "manifest.json")
    aged = json.loads(manifest_path.read_text())
    aged["started_at"] = "2020-01-01T00:00:00.000Z"
    manifest_path.write_text(json.dumps(aged))

    assert [run.run_id for run in runs(tmp_path)] == [second, first]


def test_a_handle_is_what_runs_returns(tmp_path: Path) -> None:
    write_run(tmp_path, "run_a")

    assert isinstance(runs(tmp_path)[0], RunHandle)


# -- what a run says it was for --------------------------------------------------------------


def test_a_run_is_the_agent_s_unless_the_envelope_said_otherwise(tmp_path: Path) -> None:
    pipeline = Pipeline([Deterministic(lambda inputs, ctx: inputs, node_id="echo")])

    pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))

    (found,) = runs(tmp_path)
    assert found.role == "agent"
    assert found.manifest["role"] == "agent"


def test_a_run_carries_the_role_the_envelope_declared(tmp_path: Path) -> None:
    pipeline = Pipeline([Deterministic(lambda inputs, ctx: inputs, node_id="echo")])

    pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path, role="labelling"))

    (found,) = runs(tmp_path)
    assert found.role == "labelling"
    assert found.manifest["role"] == "labelling"


def test_a_manifest_written_before_the_field_existed_reads_as_the_agent(
    tmp_path: Path,
) -> None:
    """A run directory holding no `role` is one this library wrote at manifest 0.15 or before."""
    write_run(tmp_path, "run_a")

    assert "role" not in runs(tmp_path)[0].manifest
    assert runs(tmp_path)[0].role == "agent"


def test_role_narrows_what_is_listed(tmp_path: Path) -> None:
    pipeline = Pipeline([Deterministic(lambda inputs, ctx: inputs, node_id="echo")])
    envelope = RunEnvelope(run_dir=tmp_path)

    agent_run = pipeline.run({}, envelope=envelope).run_id
    label_run = pipeline.run({}, envelope=envelope.with_role("labelling")).run_id

    assert [run.run_id for run in runs(tmp_path, role="agent")] == [agent_run]
    assert [run.run_id for run in runs(tmp_path, role="labelling")] == [label_run]
    assert {run.run_id for run in runs(tmp_path)} == {agent_run, label_run}


def test_with_role_keeps_everything_else_the_envelope_was_configured_with() -> None:
    envelope = RunEnvelope(run_dir="runs/", redaction=Redaction(secret_env=["MISTRAL_API_KEY"]))

    labelling = envelope.with_role("labelling")

    assert labelling.role == "labelling"
    assert labelling.run_dir == envelope.run_dir
    assert labelling.redaction is envelope.redaction
    assert labelling.cassette is envelope.cassette
    assert envelope.role == "agent"


def test_the_other_copies_carry_the_role_forward(tmp_path: Path) -> None:
    """`with_run_dir` is what an evaluation uses, so a role set once is not lost by it."""
    labelling = RunEnvelope(run_dir=tmp_path, role="labelling")

    assert labelling.with_run_dir(tmp_path / "nested").role == "labelling"
    assert labelling.with_trajectory(Trajectory.full()).role == "labelling"
    assert labelling.with_cassette(Cassette.off()).role == "labelling"


@pytest.mark.parametrize("bad", ["", "   ", None, 3])
def test_a_role_that_names_nothing_is_refused(bad: object) -> None:
    with pytest.raises(ConfigurationError) as caught:
        RunEnvelope(run_dir="runs/", role=bad)  # type: ignore[arg-type]

    assert "role='labelling'" in str(caught.value)


def test_a_run_says_whether_an_end_user_was_on_the_other_end(tmp_path: Path) -> None:
    """Nothing infers it: a project that never marks a run has none, like the tier."""
    pipeline = Pipeline([Deterministic(lambda inputs, ctx: inputs, node_id="echo")])
    envelope = RunEnvelope(run_dir=tmp_path)

    building = pipeline.run({}, envelope=envelope).run_id
    real = pipeline.run({}, envelope=envelope.with_live()).run_id

    assert [run.run_id for run in runs(tmp_path, live=True)] == [real]
    assert [run.run_id for run in runs(tmp_path, live=False)] == [building]
    assert runs(tmp_path, live=True)[0].manifest["live"] is True
    assert runs(tmp_path, live=False)[0].manifest["live"] is False


def test_a_run_written_before_the_field_existed_is_not_live(tmp_path: Path) -> None:
    write_run(tmp_path, "run_a")

    assert "live" not in runs(tmp_path)[0].manifest
    assert runs(tmp_path)[0].live is False


def test_with_live_goes_both_ways_and_keeps_everything_else() -> None:
    envelope = RunEnvelope(run_dir="runs/", redaction=Redaction(secret_env=["GEMINI_API_KEY"]))

    real = envelope.with_live()

    assert real.live is True
    assert real.with_live(False).live is False
    assert real.redaction is envelope.redaction
    assert real.cassette is envelope.cassette
    assert envelope.live is False


def test_the_other_copies_carry_live_forward(tmp_path: Path) -> None:
    """One field forgotten by one copy method is how a live run stops being one."""
    real = RunEnvelope(run_dir=tmp_path, live=True)

    assert real.with_run_dir(tmp_path / "nested").live is True
    assert real.with_trajectory(Trajectory.full()).live is True
    assert real.with_cassette(Cassette.off()).live is True
    assert real.with_role("agent").live is True


def test_a_live_run_that_is_not_the_agent_is_refused() -> None:
    """A labelling pass has no end user, so the two declarations contradict each other."""
    with pytest.raises(ConfigurationError) as caught:
        RunEnvelope(run_dir="runs/", role="labelling", live=True)

    assert "A live run is a run of the agent" in str(caught.value)
