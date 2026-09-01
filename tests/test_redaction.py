"""Redaction happens on the record path, and says what it changed.

FT-16 is `prototype` tier: a secret in a trajectory propagates further than it looks, because
trajectories get committed, attached to bug reports, and reused as eval and training data.
These tests cover the three rule kinds and the thing that makes the result readable later,
which is the `redactions` array.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import SecretStr

from simple_agents.redaction import BUILTIN_PATTERNS, Redaction
from simple_agents.records.trajectory import Record, TrajectoryWriter


def record(**fields: object) -> Record:
    base = Record(
        format_version="0.4",
        record_type="tool_call",
        record_id="r1",
        run_id="run_1",
        parent_id="r0",
        sequence=1,
        started_at="2026-07-26T09:00:00.000Z",
        ended_at="2026-07-26T09:00:01.000Z",
        error=None,
        redactions=[],
    )
    base.update(fields)
    return base


class TestEnvironmentValues:
    def test_declared_env_value_is_removed_wherever_it_appears(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROJECT_API_KEY", "correct-horse-battery-staple")
        redaction = Redaction(secret_env=["PROJECT_API_KEY"])

        out = redaction(
            record(
                inputs={"url": "https://x/?token=correct-horse-battery-staple"},
                outputs={"note": "used correct-horse-battery-staple to authenticate"},
            )
        )

        assert "correct-horse-battery-staple" not in str(out)
        assert out["redactions"] == ["inputs.url", "outputs.note"]

    def test_unset_variable_is_recorded_rather_than_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NEVER_SET_KEY", raising=False)
        redaction = Redaction(secret_env=["NEVER_SET_KEY"])

        # A declared secret that was unset means the run was redacted more weakly than the
        # project declared. Nothing else in the manifest would show it.
        assert redaction.unusable_env == (("NEVER_SET_KEY", "unset"),)
        assert redaction.to_manifest()["secret_env_unusable"] == [
            {"name": "NEVER_SET_KEY", "reason": "unset"}
        ]

    def test_short_value_is_refused_as_a_rule(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Redacting every occurrence of "1" would empty the trajectory.
        monkeypatch.setenv("DEBUG", "1")
        redaction = Redaction(secret_env=["DEBUG"])

        out = redaction(record(inputs={"page": "1 of 12"}))

        assert out["inputs"] == {"page": "1 of 12"}
        assert redaction.unusable_env == (("DEBUG", "too_short"),)

    def test_longer_secret_wins_over_one_that_is_its_prefix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SHORT_SECRET", "abcdefghij")
        monkeypatch.setenv("LONG_SECRET", "abcdefghijklmnop")
        redaction = Redaction(secret_env=["SHORT_SECRET", "LONG_SECRET"])

        out = redaction(record(inputs={"v": "abcdefghijklmnop"}))

        assert out["inputs"]["v"] == "[redacted:env:LONG_SECRET]"


class TestSensitiveKeys:
    def test_value_is_removed_whatever_its_shape(self) -> None:
        out = Redaction()(
            record(inputs={"headers": {"Authorization": "anything at all", "Accept": "json"}})
        )

        assert out["inputs"]["headers"]["Authorization"] == "[redacted:sensitive_key]"
        assert out["inputs"]["headers"]["Accept"] == "json"
        assert out["redactions"] == ["inputs.headers.Authorization"]

    def test_matching_is_on_the_whole_name_not_a_substring(self) -> None:
        out = Redaction()(record(inputs={"secret_santa": "Dave", "secret": "s3kr1t"}))

        assert out["inputs"]["secret_santa"] == "Dave"
        assert out["inputs"]["secret"] == "[redacted:sensitive_key]"

    def test_nested_value_under_a_sensitive_key_is_removed_entirely(self) -> None:
        out = Redaction()(record(inputs={"cookie": {"session": ["a", "b"]}}))

        assert out["inputs"]["cookie"] == {"session": ["[redacted:sensitive_key]"] * 2}

    def test_null_under_a_sensitive_key_stays_null(self) -> None:
        # A field that was already absent was not redacted, and claiming otherwise would put a
        # path in `redactions` that no reader can act on.
        out = Redaction()(record(inputs={"api_key": None}))

        assert out["inputs"]["api_key"] is None
        assert out["redactions"] == []


class TestPatterns:
    @pytest.mark.parametrize(
        ("name", "sample"),
        [
            ("sk_prefixed_key", "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv"),
            ("github_token", "ghp_" + "a" * 36),
            ("aws_access_key_id", "AKIAIOSFODNN7EXAMPLE"),
            ("huggingface_token", "hf_" + "b" * 34),
            ("google_api_key", "AIza" + "c" * 35),
            ("slack_token", "xoxb-1234567890-abcdefghij"),
            ("bearer_token", "Bearer abcdefghijklmnopqrst"),
            ("jwt", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K"),
        ],
    )
    def test_builtin_pattern_fires(self, name: str, sample: str) -> None:
        out = Redaction()(record(inputs={"text": f"call it with {sample} please"}))

        assert sample not in out["inputs"]["text"]
        assert f"[redacted:{name}]" in out["inputs"]["text"]
        assert out["redactions"] == ["inputs.text"]

    def test_private_key_block_is_removed_across_lines(self) -> None:
        block = "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
        out = Redaction()(record(outputs={"file": block}))

        assert out["outputs"]["file"] == "[redacted:private_key_block]"

    def test_declared_pattern_is_named_in_the_output(self) -> None:
        redaction = Redaction(patterns={"internal_ticket": r"TKT-\d{6}"})

        out = redaction(record(inputs={"body": "see TKT-004417 for context"}))

        assert out["inputs"]["body"] == "see [redacted:internal_ticket] for context"
        assert redaction.to_manifest()["declared_rules"] == ["internal_ticket"]

    def test_invalid_pattern_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="not a valid regular expression"):
            Redaction(patterns={"broken": r"("})

    def test_ordinary_text_survives(self) -> None:
        # A false positive replaces real data, which in a trajectory is also training data.
        prose = "The inseam is 32 inches. See https://example.com/product/1234 for details."
        out = Redaction()(record(inputs={"page": prose}))

        assert out["inputs"]["page"] == prose
        assert out["redactions"] == []


class TestScope:
    def test_identifiers_and_timestamps_are_left_alone(self) -> None:
        # The library generates these, so scanning them could only produce a false positive.
        out = Redaction()(record(record_id="sk-abcdefghijklmnopqrst", inputs={"a": 1}))

        assert out["record_id"] == "sk-abcdefghijklmnopqrst"
        assert out["redactions"] == []

    def test_a_field_the_scanner_has_never_heard_of_is_still_scanned(self) -> None:
        """The scan skips a named set and covers everything else.

        A field added later carries whatever the backend or the builder put in it, and a
        scanner that only looked at a list of known fields would write it out untouched. That
        is how a response header holding a session cookie reached a trajectory.
        """
        out = Redaction()(record(some_field_added_later={"set-cookie": "session=abc123"}))

        assert out["some_field_added_later"]["set-cookie"] == "[redacted:sensitive_key]"
        assert out["redactions"] == ["some_field_added_later.set-cookie"]

    def test_an_error_message_is_scanned(self) -> None:
        """A failure carrying a credential in its text is the reason a run gets shared."""
        out = Redaction()(
            record(error={"class": "caller_facing", "message": "401 for key AKIAIOSFODNN7EXAMPLE"})
        )

        assert "AKIAIOSFODNN7EXAMPLE" not in out["error"]["message"]

    def test_list_paths_carry_their_index(self) -> None:
        out = Redaction()(
            record(inputs={"messages": [{"content": "fine"}, {"content": "AKIAIOSFODNN7EXAMPLE"}]})
        )

        assert out["redactions"] == ["inputs.messages[1].content"]

    def test_consultation_prompt_and_response_are_walked(self) -> None:
        out = Redaction()(
            record(
                record_type="consultation",
                prompt="confirm with AKIAIOSFODNN7EXAMPLE",
                options=None,
                response={"answer": "AKIAIOSFODNN7EXAMPLE"},
                resolution="answered",
                blocking=True,
            )
        )

        assert out["redactions"] == ["prompt", "response.answer"]

    def test_existing_redactions_are_preserved_and_not_duplicated(self) -> None:
        out = Redaction()(
            record(inputs={"text": "AKIAIOSFODNN7EXAMPLE"}, redactions=["inputs.text", "other"])
        )

        assert out["redactions"] == ["inputs.text", "other"]

    def test_the_input_record_is_not_mutated(self) -> None:
        original = record(inputs={"text": "AKIAIOSFODNN7EXAMPLE"})

        Redaction()(original)

        assert original["inputs"]["text"] == "AKIAIOSFODNN7EXAMPLE"


class TestNone:
    def test_none_changes_nothing(self) -> None:
        out = Redaction.none()(record(inputs={"authorization": "Bearer abcdefghijklmnopqrst"}))

        assert out["inputs"]["authorization"] == "Bearer abcdefghijklmnopqrst"
        assert out["redactions"] == []

    def test_none_is_visible_in_the_manifest(self) -> None:
        # An unredacted run has to be identifiable as one later. Otherwise a clean trajectory
        # is ambiguous between "nothing to redact" and "nothing was looked for".
        manifest = Redaction.none().to_manifest()

        assert manifest["enabled"] is False
        assert manifest["builtin_rules"] == []

    def test_default_manifest_lists_every_builtin_rule(self) -> None:
        assert Redaction().to_manifest()["builtin_rules"] == sorted(BUILTIN_PATTERNS)


class TestValuesThatAreNotPlainData:
    """The rules walk dicts, lists and strings. Everything else has to be reduced to those
    before they run, or a credential one field inside an object is written in full while the
    same credential in a dict is replaced."""

    def test_credential_inside_an_object_is_scrubbed(self) -> None:
        @dataclass
        class FetchArgs:
            url: str
            bearer: str

        out = Redaction()(
            record(inputs=FetchArgs(url="https://x", bearer="sk-live-51H8xQwErTyUiOpAsDfGhJkL"))
        )

        assert out["inputs"] == {"url": "https://x", "bearer": "[redacted:sk_prefixed_key]"}
        assert out["redactions"] == ["inputs.bearer"]

    def test_an_object_keeps_its_structure(self) -> None:
        # Reducing an object to text would lose the fields, and a trajectory is training data.
        @dataclass
        class Query:
            terms: list[str]
            limit: int

        out = Redaction()(record(inputs=Query(terms=["inseam", "34"], limit=5)))

        assert out["inputs"] == {"terms": ["inseam", "34"], "limit": 5}

    def test_secret_typed_value_is_replaced_and_listed(self) -> None:
        out = Redaction()(record(inputs={"user_token": SecretStr("sk-live-abc123456789")}))

        assert out["inputs"]["user_token"] == "[redacted:secret_type]"
        assert out["redactions"] == ["inputs.user_token"]

    def test_secret_typed_value_is_not_written_even_with_redaction_off(
        self, tmp_path: Path
    ) -> None:
        # `Redaction.none()` turns off the rules. The type is the value's own declaration and
        # is not a rule, so it still never reaches the file.
        path = tmp_path / "trajectory.jsonl"
        with TrajectoryWriter(path, redactor=Redaction.none()) as writer:
            writer.write(record(inputs={"user_token": SecretStr("sk-live-abc123456789")}))

        assert "sk-live-abc123456789" not in path.read_text()
        assert json.loads(path.read_text())["inputs"]["user_token"] == "[redacted:secret_type]"

    def test_plain_data_is_unchanged(self) -> None:
        value, paths = Redaction().redact({"a": [1, 2.5, True, None, "x"], "b": {"c": "y"}})

        assert value == {"a": [1, 2.5, True, None, "x"], "b": {"c": "y"}}
        assert paths == []

    def test_a_cycle_does_not_hang_the_writer(self) -> None:
        @dataclass
        class Node:
            child: object = None

        first = Node()
        first.child = first

        value, _ = Redaction().redact({"inputs": first})

        assert "child" in str(value)


class TestCassetteReuse:
    def test_redact_returns_paths_for_a_bare_value(self) -> None:
        # The cassette redacts its stored requests with the same rules, and needs the paths
        # back rather than a record.
        value, paths = Redaction().redact(
            {"headers": {"authorization": "tok"}, "body": "AKIAIOSFODNN7EXAMPLE"},
            path="request",
        )

        assert value["headers"]["authorization"] == "[redacted:sensitive_key]"
        assert paths == ["request.headers.authorization", "request.body"]
