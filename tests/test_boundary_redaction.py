"""What the model reads of a tool result that carried a credential.

A tool result is stored redacted, so a replay served the marker where the live run had the
value, and every model call built on it afterwards missed. Keying on the redacted form cannot
fix it: a pattern replaces a substring and a key name replaces a whole value, so the two sides
never produce one string. A tool declaring `redact_result=True` is handed to the model through
the boundary rules instead, which makes the two sides equal.

`at_boundary` is what keeps that from costing the model content it needs. A project's own
pattern, such as an employee id it wants out of the trajectory, still reaches the model.
"""

from __future__ import annotations

import json

import pytest

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    Cassette,
    ConfigurationError,
    FakeModelClient,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    ToolCallRequest,
    tool,
)
from simple_agents.records.cassette import CassetteMiss
from simple_agents.models import fake_response
from simple_agents.redaction import DEFAULT_AT_BOUNDARY, Redaction

from schemas import Answer

UNBOUNDED = Budget.unbounded()

SECRET = "tok_abcdefghijklmnopqr"


@pytest.fixture()
def declared(monkeypatch) -> Redaction:
    monkeypatch.setenv("SUPPLIER_TOKEN", SECRET)
    return Redaction(
        secret_env=["SUPPLIER_TOKEN"],
        patterns={"employee_id": r"EMP-\d{6}", "internal": r"itk_[a-z0-9]{8}"},
    )


PAGE = {
    "authorization": "Bearer sk-abcdef0123456789ABCDEF",
    "body": f"Raised by EMP-402281 using {SECRET}. Bearer responsibilities apply. itk_abcd1234",
}


class TestWhatReachesTheModel:
    def test_a_declared_secret_and_a_sensitive_field_do_not(self, declared) -> None:
        seen, paths = declared.redact_for_model(PAGE)

        assert seen["authorization"] == "[redacted:sensitive_key]"
        assert SECRET not in seen["body"]
        assert "[redacted:env:SUPPLIER_TOKEN]" in seen["body"]
        assert "authorization" in paths

    def test_a_project_pattern_does(self, declared) -> None:
        """An agent acting on an employee id needs to read it; the file still does not hold it."""
        seen, _ = declared.redact_for_model(PAGE)

        assert "EMP-402281" in seen["body"]
        assert "EMP-402281" not in declared.redact(PAGE)[0]["body"]

    def test_a_credential_format_does_not_by_default(self, declared) -> None:
        """A marked tool is one whose result carries a credential, so the formats apply."""
        seen, _ = declared.redact_for_model(PAGE)

        assert "sk-abcdef0123456789ABCDEF" not in json.dumps(seen)
        assert "Bearer responsibilities" not in seen["body"]

    def test_dropping_builtin_lets_a_false_positive_through(self, monkeypatch) -> None:
        """`bearer_token` matches "Bearer responsibilities", which is ordinary text."""
        monkeypatch.setenv("SUPPLIER_TOKEN", SECRET)
        rules = Redaction(
            secret_env=["SUPPLIER_TOKEN"], at_boundary=("secret_env", "sensitive_keys")
        )

        seen, _ = rules.redact_for_model(PAGE)

        assert "Bearer responsibilities" in seen["body"]

    def test_one_pattern_can_be_named_on_its_own(self, monkeypatch) -> None:
        monkeypatch.setenv("SUPPLIER_TOKEN", SECRET)
        rules = Redaction(
            secret_env=["SUPPLIER_TOKEN"],
            patterns={"employee_id": r"EMP-\d{6}", "internal": r"itk_[a-z0-9]{8}"},
            at_boundary=("secret_env", "sensitive_keys", "internal"),
        )

        seen, _ = rules.redact_for_model(PAGE)

        assert "itk_abcd1234" not in seen["body"]
        assert "EMP-402281" in seen["body"]

    def test_the_record_is_redacted_by_every_rule_whatever_at_boundary_says(self, declared) -> None:
        stored, _ = declared.redact(PAGE)

        assert SECRET not in stored["body"]
        assert "EMP-402281" not in stored["body"]
        assert "itk_abcd1234" not in stored["body"]
        assert stored["authorization"] == "[redacted:sensitive_key]"

    def test_a_disabled_redaction_changes_nothing(self) -> None:
        assert Redaction.none().redact_for_model(PAGE)[0] == PAGE


class TestTheDeclaration:
    def test_the_default_is_every_rule_that_matches_a_credential(self) -> None:
        """A project's own patterns are not credentials, so they are not in it."""
        assert DEFAULT_AT_BOUNDARY == ("secret_env", "sensitive_keys", "builtin")
        assert Redaction().at_boundary == DEFAULT_AT_BOUNDARY

    def test_a_name_that_is_neither_a_kind_nor_a_rule_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            Redaction(patterns={"employee_id": r"EMP-\d{6}"}, at_boundary=("employee",))

        assert "'employee'" in str(raised.value)
        assert "employee_id" in str(raised.value)

    def test_a_bare_string_is_refused(self) -> None:
        with pytest.raises(TypeError) as raised:
            Redaction(at_boundary="secret_env")

        assert "sequence" in str(raised.value)

    def test_a_tool_declares_it_and_defaults_to_off(self) -> None:
        @tool(side_effect_class=SideEffectClass.READ_ONLY, redact_result=True)
        def fetch_page(url: str) -> dict:
            """Fetch one page from the supplier portal. Returns its body and headers."""
            return PAGE

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def read_policy(name: str) -> str:
            """Read one policy document. Returns its text."""
            return "text"

        assert fetch_page.redact_result is True
        assert read_policy.redact_result is False


class TestARecordedRunReplays:
    """What the model read and what the file holds are one string, so the keys match."""

    def _tools(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY, redact_result=True)
        def fetch_page(url: str) -> dict:
            """Fetch one page from the supplier portal. Returns its body and headers."""
            return {"authorization": f"Bearer {SECRET}", "plain": f"the page at {url}"}

        @tool(side_effect_class=SideEffectClass.READ_ONLY, name="fetch_page")
        def fetch_plain(url: str) -> dict:
            """Fetch one page from the supplier portal. Returns its body and headers."""
            return {"authorization": f"Bearer {SECRET}", "plain": f"the page at {url}"}

        return fetch_page, fetch_plain

    def _pipeline(self, which):
        return Pipeline(
            [
                AgentNode(
                    lambda i, c: Prompt.user("fetch the page, then answer"),
                    output_schema=Answer,
                    tools=[which],
                    budget=UNBOUNDED,
                    node_id="hunt",
                )
            ],
            budget=UNBOUNDED,
        )

    def _model(self):
        return FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="t1",
                            name="fetch_page",
                            arguments={"url": "https://supplier.example/1"},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(id="t2", name="finish", arguments={"answer": "fetched"})
                    ]
                ),
            ]
        )

    def _run(self, pipeline, path, tmp_path, *, recording: bool, name: str):
        return pipeline.run(
            {},
            envelope=RunEnvelope(
                run_dir=tmp_path / name,
                cassette=Cassette.record(path) if recording else Cassette.replay(path),
                redaction=Redaction(secret_env=["SUPPLIER_TOKEN"]),
            ),
            model=self._model(),
            seed=41,
        )

    def test_a_declared_result_replays(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("SUPPLIER_TOKEN", SECRET)
        marked, _ = self._tools()
        path = tmp_path / "c.jsonl"
        pipeline = self._pipeline(marked)

        self._run(pipeline, path, tmp_path, recording=True, name="live")
        replayed = self._run(pipeline, path, tmp_path, recording=False, name="again")

        assert replayed.output.answer == "fetched"
        assert SECRET not in path.read_text()

    def test_an_undeclared_one_still_misses(self, tmp_path, monkeypatch) -> None:
        """The model read the credential and the file holds a marker, so the keys differ."""
        monkeypatch.setenv("SUPPLIER_TOKEN", SECRET)
        _, unmarked = self._tools()
        path = tmp_path / "c.jsonl"
        pipeline = self._pipeline(unmarked)

        self._run(pipeline, path, tmp_path, recording=True, name="live")

        with pytest.raises(CassetteMiss) as raised:
            self._run(pipeline, path, tmp_path, recording=False, name="again")

        assert "redaction marker" in str(raised.value)
