"""`simple_agents.mcp`: what a server's hints propose, and what a run records and replays.

The live tests need `npx`, which fetches the reference MCP server. They skip without it, on
the pattern `tests/test_view_runs.py` uses for a JS engine. The whole module needs the `mcp`
extra, and skips without it the same way; CI installs the extra so the skip never hides the
coverage there.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from _mcp_fixture import reference_server_over_http
from simple_agents import (
    Budget,
    Cassette,
    Deterministic,
    Pipeline,
    RunEnvelope,
    SideEffectClass,
    ToolRegistry,
)
from simple_agents.records.cassette import CassetteMiss
from simple_agents.errors import ConfigurationError, ModelFacingError
from simple_agents.mcp import (
    MCPHints,
    MCPServer,
    MCPTool,
    mcp_listing_key,
    proposed_side_effect_class,
    servers_of,
)

pytest.importorskip("mcp", reason="the mcp extra is not installed: uv sync --extra mcp")

EVERYTHING = ["-y", "@modelcontextprotocol/server-everything", "stdio"]
BUDGET = Budget(max_steps=20, max_tokens=None, max_cost=None, max_wall_clock_ms=180_000)

needs_npx = pytest.mark.skipif(
    shutil.which("npx") is None, reason="the reference MCP server is fetched with npx"
)


def offline(name: str = "test-server", **listing: tuple[str, dict, MCPHints]) -> MCPServer:
    """A server whose listing is already known, so nothing is connected."""
    server = MCPServer.stdio("this-command-does-not-exist", [], name=name)
    server._listing = dict(listing)
    return server


class TestWhatTheHintsPropose:
    """The mapping, and the case that gets no proposal."""

    def test_read_only_proposes_read_only(self) -> None:
        assert proposed_side_effect_class(MCPHints(read_only=True)) is SideEffectClass.READ_ONLY

    def test_additive_updates_propose_writes(self) -> None:
        hints = MCPHints(read_only=False, destructive=False)

        assert proposed_side_effect_class(hints) is SideEffectClass.WRITES

    def test_destructive_updates_propose_irreversible(self) -> None:
        hints = MCPHints(read_only=False, destructive=True)

        assert proposed_side_effect_class(hints) is SideEffectClass.IRREVERSIBLE

    def test_the_specs_default_applies_where_some_annotations_were_sent(self) -> None:
        """`destructiveHint` defaults to true, so a tool that sent only `readOnlyHint: false`
        is claiming a destructive update."""
        assert proposed_side_effect_class(MCPHints(read_only=False)) is SideEffectClass.IRREVERSIBLE

    def test_no_annotations_at_all_propose_nothing(self) -> None:
        """The defaults would read as `irreversible`, and an evaluation refuses every tool in
        that class, so a server publishing no annotations would import unusable."""
        assert proposed_side_effect_class(MCPHints(present=False)) is None

    def test_spends_money_is_never_proposed(self) -> None:
        """MCP publishes no cost hint, so that class is always the project's own."""
        every = [
            proposed_side_effect_class(MCPHints(read_only=r, destructive=d))
            for r in (True, False, None)
            for d in (True, False, None)
        ]

        assert SideEffectClass.SPENDS_MONEY not in every


class TestReadingTheHints:
    def test_the_wire_spelling_is_read(self) -> None:
        hints = MCPHints.from_annotations(
            {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
        )

        assert (hints.read_only, hints.destructive, hints.open_world) == (True, False, False)
        assert hints.present

    def test_an_sdk_object_is_read(self) -> None:
        class Annotations:
            read_only_hint = False
            destructive_hint = True
            idempotent_hint = None
            open_world_hint = True

        hints = MCPHints.from_annotations(Annotations())

        assert hints.read_only is False and hints.destructive is True

    def test_absent_annotations_are_not_the_same_as_empty_ones(self) -> None:
        assert MCPHints.from_annotations(None).present is False
        assert MCPHints.from_annotations({}).present is True

    def test_a_tool_with_no_annotations_records_null(self) -> None:
        assert MCPHints(present=False).to_record() is None


class TestDeclaringTools:
    def test_effects_is_the_selection(self) -> None:
        server = offline(
            wanted=("", {}, MCPHints(read_only=True)),
            ignored=("", {}, MCPHints(read_only=True)),
        )

        built = server.tools(effects={"wanted": SideEffectClass.READ_ONLY})

        assert [tool.name for tool in built] == ["wanted"]
        assert server.undeclared() == ("ignored",)

    def test_nothing_declared_refuses_with_one_line_per_tool(self) -> None:
        server = offline(
            look=("", {}, MCPHints(read_only=True)),
            file=("", {}, MCPHints(read_only=False, destructive=False)),
            wipe=("", {}, MCPHints(read_only=False, destructive=True)),
            plain=("", {}, MCPHints(present=False)),
        )

        with pytest.raises(ConfigurationError) as raised:
            server.tools()

        said = str(raised.value)
        assert "'look': SideEffectClass.READ_ONLY,  # readOnlyHint: true" in said
        assert "'file': SideEffectClass.WRITES," in said
        assert "'wipe': SideEffectClass.IRREVERSIBLE," in said
        assert "'plain': ...,  # no annotations: declare it" in said
        assert "what the server claims, not what it guarantees" in said
        assert "tool_effects" in said

    def test_a_class_that_is_not_one_is_refused_by_name(self) -> None:
        server = offline(look=("", {}, MCPHints(read_only=True)))

        with pytest.raises(ConfigurationError) as raised:
            server.tools(effects={"look": "read_only"})

        assert "effects['look']='read_only'" in str(raised.value)
        assert "FT-19" in str(raised.value)

    def test_a_declared_tool_the_server_does_not_offer_is_refused(self) -> None:
        server = offline(look=("Look at it.", {}, MCPHints(read_only=True)))
        server.tools(effects={"gone": SideEffectClass.READ_ONLY})

        with pytest.raises(ConfigurationError) as raised:
            server.resolve()

        assert "does not offer 'gone'" in str(raised.value)
        assert "It offers: look" in str(raised.value)

    def test_declaring_reaches_no_server(self) -> None:
        """The names and the classes are enough to build the registry, so a project
        constructs its pipeline with no network."""
        server = MCPServer.stdio("this-command-does-not-exist", [], name="unreachable")

        built = server.tools(effects={"look": SideEffectClass.READ_ONLY})

        assert built[0].resolved is False and built[0].version is None


class TestTheVersion:
    def make(self, description: str, schema: dict) -> MCPTool:
        server = offline(look=(description, schema, MCPHints(read_only=True)))
        built = server.tools(effects={"look": SideEffectClass.READ_ONLY})
        server.resolve()
        return built[0]

    def test_the_same_declaration_versions_the_same(self) -> None:
        first = self.make("Look at it.", {"type": "object"})
        second = self.make("Look at it.", {"type": "object"})

        assert first.version == second.version and first.version.startswith("sha256:")

    def test_a_reworded_description_moves_the_version(self) -> None:
        """The description is prompt text, so a server that reworded one changed what the
        model was shown."""
        assert self.make("Look.", {}).version != self.make("Look at it.", {}).version

    def test_a_changed_schema_moves_the_version(self) -> None:
        first = self.make("Look.", {"type": "object", "required": []})
        second = self.make("Look.", {"type": "object", "required": ["at"]})

        assert first.version != second.version


class TestUnresolved:
    def test_calling_before_the_server_is_read_names_where_it_is_read(self) -> None:
        server = MCPServer.stdio("this-command-does-not-exist", [], name="unreachable")
        built = server.tools(effects={"look": SideEffectClass.READ_ONLY})

        with pytest.raises(ConfigurationError) as raised:
            built[0].call({})

        assert "has not been read from its MCP server" in str(raised.value)

    def test_the_function_is_never_called_directly(self) -> None:
        server = offline(look=("Look.", {}, MCPHints(read_only=True)))
        built = server.tools(effects={"look": SideEffectClass.READ_ONLY})

        with pytest.raises(ConfigurationError) as raised:
            built[0].fn()

        assert "goes to the server through MCPServer.call" in str(raised.value)


class TestRestoreAndDrift:
    def recorded(self) -> dict:
        server = offline(
            "held",
            look=("Look at it.", {"type": "object"}, MCPHints(read_only=True)),
            file=("File it.", {"type": "object"}, MCPHints(read_only=False, destructive=False)),
        )
        server.tools(effects={"look": SideEffectClass.READ_ONLY})
        return server.resolve()

    def test_restoring_reaches_no_server_and_lands_the_same_version(self) -> None:
        live = offline("held", look=("Look at it.", {"type": "object"}, MCPHints(read_only=True)))
        built_live = live.tools(effects={"look": SideEffectClass.READ_ONLY})
        live.resolve()

        replayed = MCPServer.stdio("this-command-does-not-exist", [], name="held")
        built_replayed = replayed.tools(effects={"look": SideEffectClass.READ_ONLY})
        replayed.restore(self.recorded())

        assert built_replayed[0].resolved
        assert built_replayed[0].version == built_live[0].version
        assert built_replayed[0].description == "Look at it."

    def test_no_difference_is_no_drift(self) -> None:
        was = self.recorded()
        server = offline(
            "held",
            look=("Look at it.", {"type": "object"}, MCPHints(read_only=True)),
            file=("File it.", {"type": "object"}, MCPHints(read_only=False, destructive=False)),
        )

        assert server.drift(was) == []

    def test_each_kind_of_difference_is_named(self) -> None:
        was = self.recorded()
        server = offline(
            "held",
            look=("Look at it differently.", {"type": "object"}, MCPHints(read_only=True)),
            added=("New.", {}, MCPHints(read_only=True)),
        )

        found = {(one["tool"], one["difference"]) for one in server.drift(was)}

        assert ("look", "description") in found
        assert ("added", "added") in found
        assert ("file", "withdrawn") in found

    def test_a_changed_schema_is_named_on_its_own(self) -> None:
        was = self.recorded()
        server = offline(
            "held",
            look=("Look at it.", {"type": "object", "required": ["at"]}, MCPHints(read_only=True)),
            file=("File it.", {"type": "object"}, MCPHints(read_only=False, destructive=False)),
        )

        assert {"tool": "look", "difference": "schema"} in server.drift(was)


class TestWhatTheRunRecords:
    def test_the_manifest_entry_holds_the_claim_beside_the_declaration(self) -> None:
        server = offline("held", wipe=("Wipe it.", {}, MCPHints(read_only=False, destructive=True)))
        built = server.tools(effects={"wipe": SideEffectClass.WRITES})
        server.resolve()

        entry = built[0].mcp_entry

        assert entry["proposed"] == "irreversible" and entry["declared"] == "writes"
        assert entry["agrees"] is False
        assert entry["hints"]["destructive"] is True

    def test_a_declaration_matching_the_claim_agrees(self) -> None:
        server = offline("held", look=("Look.", {}, MCPHints(read_only=True)))
        built = server.tools(effects={"look": SideEffectClass.READ_ONLY})
        server.resolve()

        assert built[0].mcp_entry["agrees"] is True

    def test_a_tool_whose_server_sent_no_annotations_records_null_hints(self) -> None:
        server = offline("held", plain=("Plain.", {}, MCPHints(present=False)))
        built = server.tools(effects={"plain": SideEffectClass.WRITES})
        server.resolve()

        assert built[0].mcp_entry["hints"] is None
        assert built[0].mcp_entry["proposed"] is None
        assert built[0].mcp_entry["agrees"] is True


class TestFindingServers:
    def test_one_entry_per_distinct_server_in_declaration_order(self) -> None:
        first = offline("first", a=("A.", {}, MCPHints(read_only=True)))
        second = offline("second", b=("B.", {}, MCPHints(read_only=True)))
        tools = [
            *first.tools(effects={"a": SideEffectClass.READ_ONLY}),
            *second.tools(effects={"b": SideEffectClass.READ_ONLY}),
            *first.tools(effects={"a": SideEffectClass.READ_ONLY}),
        ]

        assert [one.name for one in servers_of(tools)] == ["first", "second"]

    def test_a_tool_that_is_not_an_mcp_tool_names_no_server(self) -> None:
        from simple_agents import tool

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def look() -> str:
            """Look at it."""
            return "looked"

        assert servers_of([look]) == []

    def test_the_listing_key_is_the_servers_name(self) -> None:
        assert mcp_listing_key("one") == mcp_listing_key("one")
        assert mcp_listing_key("one") != mcp_listing_key("two")


# -- against the reference server ---------------------------------------------------------------


def a_pipeline(server: MCPServer) -> tuple[ToolRegistry, Pipeline]:
    registry = ToolRegistry()
    registry.add_all(
        server.tools(
            effects={"echo": SideEffectClass.READ_ONLY, "get-sum": SideEffectClass.READ_ONLY}
        )
    )

    def work(inputs, ctx):
        return {
            "said": ctx.call_tool("echo", message=inputs["word"]),
            "total": ctx.call_tool("get-sum", a=2, b=40),
        }

    node = Deterministic(work, node_id="work", tools=registry)
    return registry, Pipeline([node], budget=BUDGET, tools=registry)


@pytest.fixture(scope="module")
def over_http():
    """The reference server on its HTTP transport, for the duration of this module.

    The stdio path is exercised everywhere else here and shares nothing with this one below
    `_Session`: a different SDK entry point, a different HTTP client, and three stream values
    where stdio yields two. A rename in the SDK broke this path with every other test passing.
    """
    yield from reference_server_over_http()


@needs_npx
class TestOverStreamableHTTP:
    def test_the_hints_arrive_and_a_call_answers(self, over_http) -> None:
        with MCPServer.http(over_http, name="everything-http") as server:
            registry = ToolRegistry()
            registry.add_all(server.tools(effects={"echo": SideEffectClass.READ_ONLY}))
            server.resolve()
            echo = registry.get("echo")

            assert echo.hints.read_only is True
            assert echo.version.startswith("sha256:")
            assert echo.call({"message": "over http"}) == "Echo: over http"

    def test_headers_reach_the_server(self, over_http) -> None:
        """Headers, authentication and timeouts go on the HTTP client the SDK takes, so a
        server built with them still connects."""
        with MCPServer.http(
            over_http, headers={"X-Team": "logistics"}, timeout_s=20.0, name="with-headers"
        ) as server:
            registry = ToolRegistry()
            registry.add_all(server.tools(effects={"echo": SideEffectClass.READ_ONLY}))
            server.resolve()

            assert registry.get("echo").call({"message": "hi"}) == "Echo: hi"

    def test_a_recorded_http_run_replays_against_an_unreachable_url(
        self, over_http, tmp_path: Path
    ) -> None:
        cassette = tmp_path / "mcp.jsonl"
        with MCPServer.http(over_http, name="everything-http") as server:
            _, pipeline = a_pipeline(server)
            live = pipeline.run(
                {"word": "hello"},
                envelope=RunEnvelope(
                    run_dir=str(tmp_path / "runs"), cassette=Cassette.record(str(cassette))
                ),
            )

        unreachable = MCPServer.http("http://127.0.0.1:9/mcp", name="everything-http")
        _, replayed_pipeline = a_pipeline(unreachable)
        replayed = replayed_pipeline.run(
            {"word": "hello"},
            envelope=RunEnvelope(
                run_dir=str(tmp_path / "replayed"), cassette=Cassette.replay(str(cassette))
            ),
        )

        assert replayed.output == live.output


@needs_npx
class TestAgainstTheReferenceServer:
    """The reference server over stdio, and the recording that replays with it unreachable."""

    def test_the_hints_arrive_and_a_call_answers(self) -> None:
        with MCPServer.stdio("npx", EVERYTHING, name="everything") as server:
            registry = ToolRegistry()
            registry.add_all(server.tools(effects={"echo": SideEffectClass.READ_ONLY}))
            server.resolve()
            echo = registry.get("echo")

            assert echo.hints.read_only is True
            assert echo.description
            assert echo.parameters["properties"]["message"]["type"] == "string"
            assert echo.call({"message": "hello"}) == "Echo: hello"

    def test_a_failing_call_is_handed_to_the_model(self) -> None:
        with MCPServer.stdio("npx", EVERYTHING, name="everything") as server:
            registry = ToolRegistry()
            registry.add_all(server.tools(effects={"echo": SideEffectClass.READ_ONLY}))
            server.resolve()

            with pytest.raises(ModelFacingError):
                registry.get("echo").call({})

    def test_a_recorded_run_replays_with_the_server_unreachable(self, tmp_path: Path) -> None:
        """The offline requirement, exercised rather than asserted: the replay is pointed at a
        command that cannot run, and reaches nothing."""
        cassette = tmp_path / "mcp.jsonl"
        with MCPServer.stdio("npx", EVERYTHING, name="everything") as server:
            _, pipeline = a_pipeline(server)
            live = pipeline.run(
                {"word": "hello"},
                envelope=RunEnvelope(
                    run_dir=str(tmp_path / "runs"), cassette=Cassette.record(str(cassette))
                ),
            )

        unreachable = MCPServer.stdio("this-command-does-not-exist", [], name="everything")
        _, replayed_pipeline = a_pipeline(unreachable)
        replayed = replayed_pipeline.run(
            {"word": "hello"},
            envelope=RunEnvelope(
                run_dir=str(tmp_path / "replayed"), cassette=Cassette.replay(str(cassette))
            ),
        )

        assert replayed.output == live.output
        manifest = json.loads(
            next((tmp_path / "replayed").glob("**/manifest.json")).read_text(encoding="utf-8")
        )
        assert manifest["mcp"] == [
            {"server": "everything", "read": "replayed", "drift": [], "undeclared": []}
        ]
        assert manifest["cassette"]["hits"] == 2 and manifest["cassette"]["misses"] == 0
        versions = {tool["name"]: tool["version"] for tool in manifest["tools"]}
        assert all(version and version.startswith("sha256:") for version in versions.values())

    def test_a_live_run_records_the_listing_and_what_it_did_not_declare(
        self, tmp_path: Path
    ) -> None:
        cassette = tmp_path / "mcp.jsonl"
        with MCPServer.stdio("npx", EVERYTHING, name="everything") as server:
            _, pipeline = a_pipeline(server)
            pipeline.run(
                {"word": "hello"},
                envelope=RunEnvelope(
                    run_dir=str(tmp_path / "runs"), cassette=Cassette.record(str(cassette))
                ),
            )

        kinds = {json.loads(line)["kind"] for line in cassette.read_text().splitlines()}
        manifest = json.loads(
            next((tmp_path / "runs").glob("**/manifest.json")).read_text(encoding="utf-8")
        )
        entry = manifest["mcp"][0]

        assert "mcp_tools" in kinds
        assert entry["read"] == "live" and entry["drift"] == []
        assert "get-env" in entry["undeclared"]
        assert [tool["mcp"]["agrees"] for tool in manifest["tools"]] == [True, True]

    def test_a_replay_whose_recording_holds_no_listing_names_the_re_record(
        self, tmp_path: Path
    ) -> None:
        cassette = tmp_path / "mcp.jsonl"
        with MCPServer.stdio("npx", EVERYTHING, name="everything") as server:
            _, pipeline = a_pipeline(server)
            pipeline.run(
                {"word": "hello"},
                envelope=RunEnvelope(
                    run_dir=str(tmp_path / "runs"), cassette=Cassette.record(str(cassette))
                ),
            )
        kept = [
            line
            for line in cassette.read_text().splitlines()
            if json.loads(line)["kind"] != "mcp_tools"
        ]
        cassette.write_text("\n".join(kept) + "\n", encoding="utf-8")

        unreachable = MCPServer.stdio("this-command-does-not-exist", [], name="everything")
        _, replayed = a_pipeline(unreachable)

        with pytest.raises(CassetteMiss) as raised:
            replayed.run(
                {"word": "hello"},
                envelope=RunEnvelope(
                    run_dir=str(tmp_path / "replayed"),
                    cassette=Cassette.replay(str(cassette)),
                ),
            )

        assert "holds no tool listing" in str(raised.value)
        assert "everything" in str(raised.value)

    def test_a_server_that_moved_records_the_drift(self, tmp_path: Path) -> None:
        """The recording is edited to look like an older server, and the run is updated
        against the live one."""
        cassette = tmp_path / "mcp.jsonl"
        with MCPServer.stdio("npx", EVERYTHING, name="everything") as server:
            _, pipeline = a_pipeline(server)
            pipeline.run(
                {"word": "hi"},
                envelope=RunEnvelope(
                    run_dir=str(tmp_path / "runs"), cassette=Cassette.record(str(cassette))
                ),
            )

        rewritten = []
        for line in cassette.read_text().splitlines():
            entry = json.loads(line)
            if entry["kind"] == "mcp_tools":
                tools = entry["response"]["tools"]
                tools["echo"]["description"] = "Echoes back whatever it is given"
                tools["since-withdrawn"] = {"description": "gone", "schema": {}, "hints": None}
                del tools["get-sum"]
            rewritten.append(json.dumps(entry))
        cassette.write_text("\n".join(rewritten) + "\n", encoding="utf-8")

        with MCPServer.stdio("npx", EVERYTHING, name="everything") as server:
            _, again = a_pipeline(server)
            again.run(
                {"word": "hi"},
                envelope=RunEnvelope(
                    run_dir=str(tmp_path / "again"), cassette=Cassette.update(str(cassette))
                ),
            )

        manifest = json.loads(
            next((tmp_path / "again").glob("**/manifest.json")).read_text(encoding="utf-8")
        )
        found = {(one["tool"], one["difference"]) for one in manifest["mcp"][0]["drift"]}

        assert ("echo", "description") in found
        assert ("since-withdrawn", "withdrawn") in found
        assert ("get-sum", "added") in found
