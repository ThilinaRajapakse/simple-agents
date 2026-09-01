"""Suspend and resume run against real backends, replayed from the cassettes they recorded.

`suspend-gemini.jsonl` and `suspend-vllm.jsonl` were recorded by
`scripts/record_backend_cassettes.py` against Gemini and against a local vLLM server. Each
recording ran until the agent asked the buyer a question, stopped, and was continued as a
second process would be, with the conversation rebuilt from `suspension.json`. These tests
replay them, so they need no key, no server, no network and nobody to answer.

**A replay of a suspended run does not suspend**, because the answer is on file and the channel
is never reached. That is what makes an evaluation over a consulting agent possible, and it is
why these tests replay a completed run rather than a stop.

What a fake client cannot show is here. The third recorded request is the one the resumed
process sent, and its message list was assembled from a file rather than held in memory. A
cassette key covers the whole request, so the replay finding that entry is what says the
conversation rebuilt from the file is the one the backend answered.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from record_backend_cassettes import (  # noqa: E402
    GEMINI_MODEL,
    GEMINI_PRICES,
    GEMINI_REVISION,
    NO_THINKING,
    SEED,
    SUSPEND_QUESTION,
    suspend_pipeline,
)

from simple_agents import (  # noqa: E402
    Cassette,
    GeminiClient,
    RunEnvelope,
    Unknown,
    VLLMClient,
    read_trajectory,
)

CASSETTES = Path(__file__).parent / "cassettes"
RUN_ID = "replayed-suspend"
VLLM_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"


def replaying(tmp_path: Path) -> RunEnvelope:
    return RunEnvelope(
        run_dir=tmp_path,
        cost_basis=GEMINI_PRICES,
        cassette=Cassette.replay(CASSETTES / "suspend-gemini.jsonl"),
    )


def client() -> GeminiClient:
    """No key needed: every call is served from the file."""
    return GeminiClient(model=GEMINI_MODEL, model_revision=GEMINI_REVISION, api_key="unused")


@pytest.fixture
def replayed(tmp_path: Path):
    result = suspend_pipeline().run(
        {"question": SUSPEND_QUESTION},
        envelope=replaying(tmp_path),
        model=client(),
        seed=SEED,
        run_id=RUN_ID,
    )
    return result, list(read_trajectory(result.paths.trajectory))


def _calls_after_the_answer(records: list[dict]) -> list[dict]:
    """The model calls the resumed run made, which is every one after the consultation."""
    answered = next(
        r["sequence"]
        for r in records
        if r["record_type"] == "consultation" and r["resolution"] == "answered"
    )
    return [r for r in records if r["record_type"] == "model_call" and r["sequence"] > answered]


class TestAgainstARealBackend:
    def test_nothing_suspends_when_the_answer_is_on_file(self, replayed):
        """k rollouts replay the recorded answer rather than asking a person k times."""
        result, records = replayed
        assert result.outcome == "completed"
        assert result.manifest["suspensions"] == []
        consultations = [r for r in records if r["record_type"] == "consultation"]
        assert [r["resolution"] for r in consultations] == ["answered"]

    def test_the_conversation_the_resumed_run_rebuilt_is_what_the_backend_answered(self, replayed):
        """Every request after the stop came from a message list read back from a file.

        A cassette key covers the whole request, so serving these here says the round trip
        through `suspension.json` produced the same conversation the live run held.
        """
        _, records = replayed
        calls = [r for r in records if r["record_type"] == "model_call"]
        assert len(calls) > 1
        assert all(r["replayed"] for r in calls)
        assert len(calls[-1]["inputs"]["messages"]) > len(calls[0]["inputs"]["messages"])

    def test_the_answer_reached_the_model(self, replayed):
        _, records = replayed
        after = _calls_after_the_answer(records)
        assert after
        assert "slim" in json.dumps(after[0]["inputs"])

    def test_the_agent_asked_before_it_answered(self, replayed):
        """The recording is only worth anything if the model chose to consult."""
        _, records = replayed
        consultations = [r for r in records if r["record_type"] == "consultation"]
        assert len(consultations) == 1
        assert consultations[0]["prompt"]
        assert consultations[0]["answered_by"] == "end_user"

    def test_the_run_produced_an_answer(self, replayed):
        result, _ = replayed
        assert result.output is not None
        assert result.tokens["output"] > 0

    def test_every_record_hangs_from_one_that_was_written(self, replayed):
        _, records = replayed
        written = {r["record_id"] for r in records}
        parents = {r["parent_id"] for r in records if r["parent_id"] is not None}
        assert parents <= written


class TestAgainstASelfHostedBackend:
    """The same shape on vLLM, whose 1.7B model decides for itself whether to ask.

    Recorded with `--enable-auto-tool-choice --tool-call-parser hermes`, without which a
    request carrying tools is refused before any of this can happen.
    """

    def envelope(self, tmp_path: Path) -> RunEnvelope:
        return RunEnvelope(
            run_dir=tmp_path, cassette=Cassette.replay(CASSETTES / "suspend-vllm.jsonl")
        )

    def client(self) -> VLLMClient:
        return VLLMClient(model="Qwen/Qwen3-1.7B", model_revision=VLLM_REVISION)

    def replayed(self, tmp_path: Path):
        result = suspend_pipeline(NO_THINKING).run(
            {"question": SUSPEND_QUESTION},
            envelope=self.envelope(tmp_path),
            model=self.client(),
            seed=SEED,
            run_id="replayed-suspend-vllm",
        )
        return result, list(read_trajectory(result.paths.trajectory))

    def test_this_backend_also_accepted_the_rebuilt_conversation(self, tmp_path):
        _, records = self.replayed(tmp_path)
        calls = [r for r in records if r["record_type"] == "model_call"]
        after = _calls_after_the_answer(records)
        assert all(r["replayed"] for r in calls)
        assert after
        assert len(after[0]["inputs"]["messages"]) > len(calls[0]["inputs"]["messages"])

    def test_the_smaller_model_asked_and_used_the_answer(self, tmp_path):
        result, records = self.replayed(tmp_path)
        consultations = [r for r in records if r["record_type"] == "consultation"]
        assert [r["resolution"] for r in consultations] == ["answered"]
        assert result.outcome == "completed"

    def test_it_reported_absence_rather_than_guessing(self, tmp_path):
        """What this recording caught that the hosted one did not."""
        result, _ = self.replayed(tmp_path)
        assert isinstance(result.output.returns_policy, Unknown)
