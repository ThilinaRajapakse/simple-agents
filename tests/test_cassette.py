"""Keying, storage, and what a miss reports.

The end-to-end record-then-replay test lives in `test_run_envelope.py`, where a pipeline
drives it. These cover the pieces underneath: what goes into a key, what a miss says, and how
a file that has been recorded twice resolves.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from simple_agents.records.cassette import (
    Cassette,
    CassetteEntry,
    CassetteMiss,
    describe_differences,
    miss_error,
    model_call_key,
    tool_call_key,
)
from simple_agents.errors import CallerFacingError, ConfigurationError

KEYED = {
    "backend": "self_hosted",
    "request_model": "Qwen/Qwen3-8B",
    "model_revision": "a1b2c3d",
    "messages": [{"role": "user", "content": "How long is the inseam?"}],
    "params": {
        "seed": 41,
        "temperature": 0.0,
        "max_output_tokens": None,
        "extra": {},
        "tools": [],
        "output_schema": None,
    },
}


def entry(key: str, **changes: object) -> CassetteEntry:
    base = {
        "key": key,
        "kind": "model_call",
        "node_id": "extract_inseam",
        "call_index": 0,
        "recorded_at": "2026-07-26T09:00:00.000Z",
        "request": dict(KEYED),
        "response": {"content": "32"},
    }
    base.update(changes)
    return CassetteEntry(**base)  # type: ignore[arg-type]


class TestKeying:
    def test_the_same_request_keys_the_same_way(self) -> None:
        assert model_call_key(**KEYED) == model_call_key(**KEYED)

    @pytest.mark.parametrize(
        "change",
        [
            {"request_model": "Qwen/Qwen3-32B"},
            {"model_revision": "d4e5f6a"},
            {"backend": "hosted_api"},
            {"messages": [{"role": "user", "content": "How long is the inseam, in cm?"}]},
            {"params": {**KEYED["params"], "seed": 42}},
            {"params": {**KEYED["params"], "temperature": 0.7}},
            # A tool's description is prompt text, so editing it is a different request.
            {"params": {**KEYED["params"], "tools": [{"name": "s", "description": "d"}]}},
            {"params": {**KEYED["params"], "output_schema": {"type": "object"}}},
        ],
    )
    def test_every_keyed_field_changes_the_key(self, change: dict[str, object]) -> None:
        assert model_call_key(**{**KEYED, **change}) != model_call_key(**KEYED)

    def test_key_does_not_depend_on_dict_ordering(self) -> None:
        reordered = dict(reversed(list(KEYED["params"].items())))  # type: ignore[union-attr]

        assert model_call_key(**{**KEYED, "params": reordered}) == model_call_key(**KEYED)

    def test_a_tool_call_is_keyed_by_its_arguments(self) -> None:
        one = tool_call_key(
            node_id="hunt",
            tool_name="search",
            tool_version="1",
            arguments={"q": "inseam"},
            occurrence=0,
        )
        two = tool_call_key(
            node_id="hunt",
            tool_name="search",
            tool_version="1",
            arguments={"q": "outseam"},
            occurrence=0,
        )

        assert one != two

    def test_a_tool_version_change_invalidates_its_entries(self) -> None:
        one = tool_call_key(
            node_id="hunt",
            tool_name="search",
            tool_version="1",
            arguments={"q": "inseam"},
            occurrence=0,
        )
        two = tool_call_key(
            node_id="hunt",
            tool_name="search",
            tool_version="2",
            arguments={"q": "inseam"},
            occurrence=0,
        )

        assert one != two

    def test_repeating_the_same_call_produces_a_different_key(self) -> None:
        """Otherwise a tool answering differently at two moments replays one answer twice."""
        one = tool_call_key(
            node_id="hunt", tool_name="now", tool_version=None, arguments={}, occurrence=0
        )
        two = tool_call_key(
            node_id="hunt", tool_name="now", tool_version=None, arguments={}, occurrence=1
        )

        assert one != two

    def test_the_same_call_in_two_nodes_is_two_keys(self) -> None:
        """Otherwise one node's recorded answer is served to the other, and a call added to
        one node renumbers the other's."""
        one = tool_call_key(
            node_id="hunt", tool_name="now", tool_version=None, arguments={}, occurrence=0
        )
        two = tool_call_key(
            node_id="verify", tool_name="now", tool_version=None, arguments={}, occurrence=0
        )

        assert one != two

    def test_keys_are_prefixed_and_short_enough_to_read(self) -> None:
        key = model_call_key(**KEYED)

        assert key.startswith("ck_")
        assert len(key) == 19


class TestModes:
    def test_off_stores_nothing(self, tmp_path: Path) -> None:
        cassette = Cassette.off()

        assert cassette.enabled is False
        assert cassette.path is None
        assert cassette.to_manifest() == {"mode": "off", "path": None, "dropped": None}

    def test_record_appends_and_is_readable_immediately(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")

        cassette.store(entry("ck_one"))

        assert cassette.lookup("ck_one") is not None
        assert (tmp_path / "c.jsonl").read_text().count("\n") == 1

    def test_replay_reads_what_record_wrote(self, tmp_path: Path) -> None:
        path = tmp_path / "c.jsonl"
        Cassette.record(path).store(entry("ck_one"))

        replayed = Cassette.replay(path)

        assert replayed.is_replaying is True
        assert replayed.lookup("ck_one").response == {"content": "32"}

    def test_a_differing_response_is_kept_alongside_the_first(self, tmp_path: Path) -> None:
        """Nothing is overwritten, and replay stays reproducible.

        An edited prompt hashes to a different key, so a collision means the identical request
        was made again. Keeping both is the evidence that the backend does not reproduce its
        own sampling; serving the first is what lets an earlier run still be replayed after a
        later one has been recorded into the same file.
        """
        path = tmp_path / "c.jsonl"
        recorder = Cassette.record(path)

        assert recorder.store(entry("ck_one", response={"content": "old"})).written is True
        assert recorder.store(entry("ck_one", response={"content": "new"})).written is True

        replay = Cassette.replay(path)
        assert [e.response for e in replay.variants()["ck_one"]] == [
            {"content": "old"},
            {"content": "new"},
        ]
        assert replay.lookup("ck_one").response == {"content": "old"}

    def test_an_identical_response_is_not_written_twice(self, tmp_path: Path) -> None:
        path = tmp_path / "c.jsonl"
        recorder = Cassette.record(path)

        assert recorder.store(entry("ck_one", response={"content": "same"})).written is True
        assert recorder.store(entry("ck_one", response={"content": "same"})).written is False

        assert len(Cassette.replay(path).variants()["ck_one"]) == 1

    def test_recording_over_a_file_that_already_holds_one_is_refused(self, tmp_path: Path) -> None:
        """Dogfood #1 run 2 recorded two evaluations into one file and replayed the first."""
        path = tmp_path / "c.jsonl"
        Cassette.record(path).store(entry("ck_one"))

        with pytest.raises(ConfigurationError) as raised:
            Cassette.record(path)

        message = str(raised.value)
        assert "already holds a recording" in message
        assert "Cassette.update" in message

    def test_an_empty_file_is_not_a_recording(self, tmp_path: Path) -> None:
        path = tmp_path / "c.jsonl"
        path.write_text("")

        assert Cassette.record(path).is_recording is True

    def test_replaying_a_file_that_does_not_exist_finds_nothing(self, tmp_path: Path) -> None:
        assert Cassette.replay(tmp_path / "absent.jsonl").lookup("ck_one") is None

    def test_update_serves_what_is_on_file_and_records_what_is_not(self, tmp_path: Path) -> None:
        path = tmp_path / "c.jsonl"
        Cassette.record(path).store(entry("ck_one"))

        updating = Cassette.update(path)

        assert updating.serves_hits is True
        assert updating.is_recording is True
        assert updating.is_replaying is False
        assert updating.lookup("ck_one").response == {"content": "32"}
        assert updating.lookup("ck_two") is None
        assert updating.store(entry("ck_two")).written is True
        assert Cassette.replay(path).lookup("ck_two") is not None

    def test_update_reports_its_mode_to_the_manifest(self, tmp_path: Path) -> None:
        path = tmp_path / "c.jsonl"

        assert Cassette.update(path).to_manifest() == {
            "mode": "update",
            "path": str(path),
            "dropped": None,
        }


class TestConcurrency:
    """One cassette is shared by every rollout of an evaluation, including parallel ones."""

    def test_parallel_writes_all_land_and_the_file_stays_readable(self, tmp_path: Path) -> None:
        path = tmp_path / "c.jsonl"
        cassette = Cassette.record(path)
        keys = [f"ck_{i:03d}" for i in range(120)]

        with ThreadPoolExecutor(max_workers=12) as pool:
            written = list(pool.map(lambda k: cassette.store(entry(k)).written, keys))

        assert all(written)
        assert len(Cassette.replay(path).variants()) == 120
        assert path.read_text(encoding="utf-8").strip().count("\n") == 119

    def test_a_key_written_from_several_threads_counts_its_divergences_once_each(
        self, tmp_path: Path
    ) -> None:
        """Eight distinct responses under one key: eight written, seven of them divergences."""
        path = tmp_path / "c.jsonl"
        cassette = Cassette.record(path)

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(
                pool.map(
                    lambda i: cassette.store(entry("ck_one", response={"content": str(i)})),
                    range(8),
                )
            )

        assert sum(o.written for o in outcomes) == 8
        assert sum(o.diverged for o in outcomes) == 7

    def test_reading_while_another_thread_writes_does_not_break(self, tmp_path: Path) -> None:
        path = tmp_path / "c.jsonl"
        cassette = Cassette.record(path)
        cassette.store(entry("ck_seed"))

        def write(i: int) -> bool:
            return cassette.store(entry(f"ck_{i:03d}")).written

        def read(_: int) -> int:
            return len(cassette.entries())

        with ThreadPoolExecutor(max_workers=8) as pool:
            writes = pool.map(write, range(60))
            reads = pool.map(read, range(60))
            assert all(writes)
            assert all(count >= 1 for count in reads)

    def test_a_corrupt_line_names_the_file_and_the_line(self, tmp_path: Path) -> None:
        path = tmp_path / "c.jsonl"
        path.write_text('{"key": "ck_one", "kind": "model_call"}\nnot json\n')

        with pytest.raises(CallerFacingError, match=r"c\.jsonl:2"):
            Cassette.replay(path).entries()

    def test_recording_creates_the_parent_directory(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "nested" / "deeper" / "c.jsonl")

        cassette.store(entry("ck_one"))

        assert (tmp_path / "nested" / "deeper" / "c.jsonl").exists()

    def test_an_entry_round_trips_through_json(self, tmp_path: Path) -> None:
        original = entry("ck_one", call_index=3, node_id="summarise")

        restored = CassetteEntry.from_json(json.loads(json.dumps(original.to_json())))

        assert restored == original


class TestNearest:
    def test_the_same_call_index_in_the_same_node_wins(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a", call_index=0))
        cassette.store(entry("ck_b", call_index=1))

        assert cassette.nearest("extract_inseam", 1, "model_call").key == "ck_b"

    def test_another_node_is_not_offered(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a", node_id="summarise"))

        assert cassette.nearest("extract_inseam", 0, "model_call") is None

    def test_a_tool_entry_is_not_offered_for_a_model_call(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a", kind="tool_call"))

        assert cassette.nearest("extract_inseam", 0, "model_call") is None


class TestDifferences:
    def test_a_prompt_edit_is_reported_by_length(self) -> None:
        recorded = {"messages": [{"role": "user", "content": "a" * 100}]}
        current = {"messages": [{"role": "user", "content": "a" * 140}]}

        assert describe_differences(current, recorded) == [
            "messages[0].content (recorded 100 chars, now 140 chars)"
        ]

    def test_a_short_value_is_quoted(self) -> None:
        assert describe_differences({"seed": 42}, {"seed": 41}) == ["seed (recorded 41, now 42)"]

    def test_a_changed_message_count_is_reported_as_a_count(self) -> None:
        recorded = {"messages": [{"role": "user", "content": "a"}]}
        current = {"messages": [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]}

        assert describe_differences(current, recorded) == [
            "messages (recorded 1 item, now 2 items)"
        ]

    def test_identical_requests_differ_in_nothing(self) -> None:
        assert describe_differences(dict(KEYED), dict(KEYED)) == []

    def test_the_list_is_capped(self) -> None:
        recorded = {f"f{i}": i for i in range(20)}
        current = {f"f{i}": i + 1 for i in range(20)}

        assert len(describe_differences(current, recorded)) == 6


class TestMissMessage:
    def test_it_names_the_node_the_index_and_the_file(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a"))

        error = miss_error(
            cassette=cassette,
            kind="model_call",
            node_id="extract_inseam",
            call_index=0,
            request={**KEYED, "messages": [{"role": "user", "content": "different"}]},
        )

        assert "call 0 of node 'extract_inseam'" in str(error)
        assert "c.jsonl" in str(error)

    def test_it_reports_what_changed(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a"))

        error = miss_error(
            cassette=cassette,
            kind="model_call",
            node_id="extract_inseam",
            call_index=0,
            request={**KEYED, "params": {**KEYED["params"], "temperature": 0.7}},  # type: ignore[dict-item]
        )

        assert "differs in:" in str(error)
        assert "params.temperature (recorded 0.0, now 0.7)" in str(error)

    def test_it_states_the_action_that_fixes_it(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")

        error = miss_error(
            cassette=cassette,
            kind="model_call",
            node_id="extract_inseam",
            call_index=0,
            request=dict(KEYED),
        )

        assert "Cassette.record(" in str(error)

    def test_an_unrecorded_node_says_so_rather_than_diffing(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")

        error = miss_error(
            cassette=cassette,
            kind="model_call",
            node_id="new_node",
            call_index=0,
            request=dict(KEYED),
        )

        assert "Nothing was recorded for this node" in str(error)

    def test_a_difference_that_is_a_redaction_marker_says_so(self, tmp_path: Path) -> None:
        """The replay served the marker where the recording had the value.

        Without this the message reports a length change on a message the reader never
        edited, and the cause is two records away.
        """
        cassette = Cassette.record(tmp_path / "c.jsonl")
        recorded = {
            **KEYED,
            "messages": [
                {"role": "user", "content": "How long is the inseam?"},
                {"role": "tool", "content": "{'authorization': 'Bearer [redacted:env:KEY]'}"},
            ],
        }
        cassette.store(entry("ck_a", request=recorded))

        error = miss_error(
            cassette=cassette,
            kind="model_call",
            node_id="extract_inseam",
            call_index=0,
            request={
                **KEYED,
                "messages": [
                    {"role": "user", "content": "How long is the inseam?"},
                    {
                        "role": "tool",
                        "content": "{'authorization': '[redacted:sensitive_key]'}",
                    },
                ],
            },
        )

        assert "redaction marker" in str(error)
        assert "SecretStr" in str(error)

    def test_an_ordinary_edit_is_not_reported_as_a_redaction(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a"))

        error = miss_error(
            cassette=cassette,
            kind="model_call",
            node_id="extract_inseam",
            call_index=0,
            request={**KEYED, "messages": [{"role": "user", "content": "different"}]},
        )

        assert "redaction marker" not in str(error)

    def test_a_miss_is_caller_facing(self) -> None:
        # A run that cannot replay one of its calls is not the run that was recorded, so the
        # error ends the run rather than reaching the model as an observation.
        assert issubclass(CassetteMiss, CallerFacingError)


class TestTheSeedARunReplaysAt:
    """A model call's seed derives from the run's and is part of the key, so a replay has to
    run at the seed the recording ran at. The file is where that comes from."""

    def test_the_seed_of_the_recording_run_is_on_every_entry(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a", run_seed=41))

        written = json.loads((tmp_path / "c.jsonl").read_text().splitlines()[0])

        assert written["run_seed"] == 41
        assert CassetteEntry.from_json(written).run_seed == 41

    def test_a_file_recorded_by_one_run_names_the_seed_to_replay_at(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a", run_seed=41))
        cassette.store(entry("ck_b", run_seed=41))

        assert Cassette.replay(tmp_path / "c.jsonl").recorded_seed == 41

    def test_a_file_recorded_by_several_runs_at_one_seed_still_names_it(
        self, tmp_path: Path
    ) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a", run_id="run_a", run_seed=41))
        cassette.store(entry("ck_b", run_id="run_b", run_seed=41))

        assert Cassette.replay(tmp_path / "c.jsonl").recorded_seed == 41

    def test_a_file_holding_several_seeds_names_none(self, tmp_path: Path) -> None:
        """What an evaluation writes: one rollout per seed, all into one file."""
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a", run_seed=41))
        cassette.store(entry("ck_b", run_seed=7))

        replaying = Cassette.replay(tmp_path / "c.jsonl")

        assert replaying.recorded_seed is None
        assert replaying.recorded_seeds() == {41, 7}

    def test_a_file_recorded_before_seeds_were_stored_names_none(self, tmp_path: Path) -> None:
        (tmp_path / "c.jsonl").write_text(
            json.dumps({"key": "ck_a", "kind": "model_call", "request": {}, "response": {}}) + "\n"
        )

        replaying = Cassette.replay(tmp_path / "c.jsonl")

        assert replaying.recorded_seed is None
        assert replaying.recorded_seeds() == set()
        assert replaying.lookup("ck_a") is not None

    def test_a_miss_on_the_seed_names_the_run_seed_and_not_the_derived_one(
        self, tmp_path: Path
    ) -> None:
        """The seed on a request is derived, so reporting only the difference names a number
        that cannot be passed back."""
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a", run_seed=1927391078))

        error = miss_error(
            cassette=cassette,
            kind="model_call",
            node_id="extract_inseam",
            call_index=0,
            request={**KEYED, "params": {**KEYED["params"], "seed": 102003894}},  # type: ignore[dict-item]
        )

        message = str(error)
        assert "params.seed (recorded 41, now 102003894)" in message
        assert "recorded at run seed 1927391078" in message
        assert "seed=1927391078" in message

    def test_a_miss_on_anything_else_says_nothing_about_seeds(self, tmp_path: Path) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a", run_seed=41))

        error = miss_error(
            cassette=cassette,
            kind="model_call",
            node_id="extract_inseam",
            call_index=0,
            request={**KEYED, "params": {**KEYED["params"], "temperature": 0.7}},  # type: ignore[dict-item]
        )

        assert "run seed" not in str(error)

    def test_a_miss_against_a_file_with_no_seed_recorded_reads_as_before(
        self, tmp_path: Path
    ) -> None:
        cassette = Cassette.record(tmp_path / "c.jsonl")
        cassette.store(entry("ck_a"))

        error = miss_error(
            cassette=cassette,
            kind="model_call",
            node_id="extract_inseam",
            call_index=0,
            request={**KEYED, "params": {**KEYED["params"], "seed": 102003894}},  # type: ignore[dict-item]
        )

        assert "run seed" not in str(error)


class TestWhatAnEntryStoresAndGivesBack:
    """The response half of the round trip, which the key says nothing about."""

    def test_an_unmeasured_count_comes_back_unmeasured_rather_than_as_a_mapping(self) -> None:
        # A count the backend did not report is stored as an Unknown. Decoded as the raw
        # mapping it would break every sum over the counts, so a replay of a backend that
        # reports one would fail on arithmetic rather than on anything to do with the call.
        from simple_agents.records.cassette import decode_model_response, encode_model_response
        from simple_agents.models import ModelResponse, TokenUsage
        from simple_agents.schema import Unknown

        response = ModelResponse(
            content="OK",
            tool_calls=[],
            finish_reason="STOP",
            backend="hosted_api",
            request_model="gemini-3.1-flash-lite",
            response_model="gemini-3.1-flash-lite",
            model_revision=None,
            tokens=TokenUsage(
                input_uncached=100,
                input_cache_read=0,
                input_cache_write=Unknown(reason="the backend reports no cache-write count"),
                cache_ttl=None,
                output=20,
            ),
            concurrent_requests=None,
        )

        back = decode_model_response(json.loads(json.dumps(encode_model_response(response))))

        assert isinstance(back.tokens.input_cache_write, Unknown)
        assert back.tokens.input_cache_write.reason is not None
        assert back.tokens.total == 120

    def test_a_tool_call_keeps_the_state_its_backend_requires_back(self) -> None:
        from simple_agents.records.cassette import decode_model_response, encode_model_response
        from simple_agents.models import ModelResponse, TokenUsage, ToolCallRequest

        response = ModelResponse(
            content=None,
            tool_calls=[
                ToolCallRequest(
                    id="c1",
                    name="search",
                    arguments={"query": "belmont"},
                    provider={"thought_signature": "EjQKMgERTTIP"},
                )
            ],
            finish_reason="STOP",
            backend="hosted_api",
            request_model="gemini-3.1-flash-lite",
            response_model="gemini-3.1-flash-lite",
            model_revision=None,
            tokens=TokenUsage(
                input_uncached=10,
                input_cache_read=0,
                input_cache_write=0,
                cache_ttl=None,
                output=5,
            ),
            concurrent_requests=None,
        )

        back = decode_model_response(json.loads(json.dumps(encode_model_response(response))))

        assert back.tool_calls[0].provider == {"thought_signature": "EjQKMgERTTIP"}

    def test_a_call_from_a_backend_that_sends_no_such_state_stores_no_key(self) -> None:
        # The conversation an AgentNode builds is part of every later cassette key, so an
        # empty `provider` written into it would invalidate every cassette recorded before
        # the field existed.
        from simple_agents.models import ToolCallRequest

        assert ToolCallRequest(id="c1", name="search", arguments={}).to_record() == {
            "id": "c1",
            "name": "search",
            "arguments": {},
        }
