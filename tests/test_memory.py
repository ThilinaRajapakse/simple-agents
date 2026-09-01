"""A store the agent reads and writes across runs.

What is checked here is that memory is reached through a recorded call and nowhere else, that
the store the library owns is the one thing a project cannot route around silently, and the
four places a store that outlives its run would otherwise break: the eval refusal, redaction,
replay and a rollout's isolation from every other rollout.

Nothing in this file makes a live model call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Budget,
    Cassette,
    ConfigurationError,
    DeclaredCost,
    Deterministic,
    FakeEmbeddingClient,
    Memory,
    MemoryStore,
    RunSuspended,
    ScopedMemory,
    Pipeline,
    Redaction,
    RunEnvelope,
    SideEffectClass,
    tool,
)
from simple_agents.builtins import Semantic, memory_search, recall, remember
from simple_agents.builtins.memory import MAX_KEYS_ON_EMPTY
from simple_agents.errors import CallerFacingError, ModelFacingError
from simple_agents.memory import ROLLOUT_SCOPE
from simple_agents.evaluation import EvalSuite, Example, ExampleSet
from simple_agents.evaluation.runner import _tools_of

A_KEY = "sk-livekey0123456789abcdefghij"


def _budget() -> Budget:
    return Budget(max_steps=20, max_tokens=100_000, max_cost=None, max_wall_clock_ms=120_000)


def _store(tmp_path: Path, scope: str = "user-1") -> ScopedMemory:
    """One scope's memory, for reading and writing directly."""
    return _declared(tmp_path).scoped(scope)


def _declared(tmp_path: Path) -> MemoryStore:
    """What an envelope declares: where memories live, and no scope."""
    return MemoryStore(tmp_path / "memory")


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class TestTheStore:
    def test_it_refuses_a_scope_that_names_nobody(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as exc:
            MemoryStore(tmp_path).scoped("")

        assert "one memory for every end user" in str(exc.value)
        assert "memory_scope=" in str(exc.value)

    def test_two_scopes_over_one_directory_share_nothing(self, tmp_path) -> None:
        store = MemoryStore(tmp_path)
        first = store.scoped("user-1")
        second = store.scoped("user-2")

        first.put("pref", "short books")

        assert second.get("pref") is None
        assert first.get("pref").value == "short books"

    def test_a_write_is_a_put(self, tmp_path) -> None:
        """Re-running has to leave the state running once left, which is what replay needs."""
        store = _store(tmp_path)

        store.put("pref", "short books")
        store.put("pref", "short books")
        store.put("pref", "long books")

        assert len(store) == 1
        assert store.get("pref").value == "long books"

    def test_the_manifest_holds_a_digest_rather_than_the_scope(self, tmp_path) -> None:
        store = MemoryStore(tmp_path).scoped("user-alice@example.com")

        recorded = store.to_manifest()

        assert "alice" not in json.dumps(recorded)
        assert recorded["scope_digest"] == store.scope_digest
        assert recorded["entries"] == 0

    def test_a_key_that_cannot_be_used_fails_model_facing(self, tmp_path) -> None:
        store = _store(tmp_path)

        with pytest.raises(ModelFacingError):
            store.put("   ", "anything")
        with pytest.raises(ModelFacingError):
            store.put("k" * 201, "anything")

    def test_rebound_seeds_the_rollout_scope_and_takes_nothing_else(self, tmp_path) -> None:
        store = MemoryStore(tmp_path / "memory")
        store.scoped("user-1").put("old", "from an earlier run")

        rollout = store.rebound(tmp_path / "rollout", seed={"seeded": "from the example"})

        assert rollout.scoped(ROLLOUT_SCOPE).keys() == ["seeded"]
        assert rollout.scoped("user-1").keys() == []
        assert store.scoped("user-1").keys() == ["old"]


class TestTheHandle:
    def test_a_memory_tool_is_re_run_rather_than_filed(self) -> None:
        """A replay rebuilds the store by making the same writes, as a Workspace tool does."""
        assert all(t.re_executed for t in (remember(), recall(), memory_search()))

    def test_a_memory_tool_cannot_declare_that_it_spends(self) -> None:
        with pytest.raises(ConfigurationError) as exc:

            @tool(
                side_effect_class=SideEffectClass.SPENDS_MONEY,
                declared_cost=DeclaredCost(currency="USD", per_call=0.005),
            )
            def spend_and_remember(memory: Memory, fact: str) -> str:
                """Store a fact after paying for it."""
                return fact

        assert "Memory" in str(exc.value)
        assert "re-run during replay" in str(exc.value)

    def test_the_handle_is_not_offered_to_the_model(self) -> None:
        assert set(remember().parameters["properties"]) == {"key", "value"}


class TestARunReachingMemory:
    def test_a_run_with_no_store_is_refused_before_it_starts(self, tmp_path) -> None:
        pipeline = Pipeline(
            [Deterministic(lambda i, ctx: i, node_id="save", tools=[remember()])],
            budget=_budget(),
        )

        with pytest.raises(ConfigurationError) as exc:
            pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))

        assert "'remember'" in str(exc.value)
        assert "MemoryStore" in str(exc.value)
        assert not any(tmp_path.glob("**/trajectory.jsonl"))

    def test_what_was_read_is_in_a_tool_call_record(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.put("pref", "short books")

        def load(inputs, ctx):
            return ctx.call_tool("recall", key="pref")

        pipeline = Pipeline(
            [Deterministic(load, node_id="load", tools=[recall()])], budget=_budget()
        )
        result = pipeline.run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "runs", memory=_declared(tmp_path)),
            memory_scope="user-1",
        )

        calls = [r for r in _records(result.trajectory_path) if r["record_type"] == "tool_call"]
        node = next(
            r for r in _records(result.trajectory_path) if r["record_type"] == "node_execution"
        )
        assert len(calls) == 1
        assert calls[0]["outputs"]["value"] == "short books"
        assert calls[0]["parent_id"] == node["record_id"]
        assert result.output["value"] == "short books"

    def test_the_store_is_recorded_in_the_manifest(self, tmp_path) -> None:
        store = _store(tmp_path)

        def save(inputs, ctx):
            return ctx.call_tool("remember", key="pref", value="short books")

        pipeline = Pipeline(
            [Deterministic(save, node_id="save", tools=[remember()])], budget=_budget()
        )
        result = pipeline.run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "runs", memory=_declared(tmp_path)),
            memory_scope="user-1",
        )

        assert result.manifest["memory"]["scope_digest"] == store.scope_digest
        assert result.manifest["memory"]["entries"] == 1

    def test_a_run_declaring_no_memory_records_none(self, tmp_path) -> None:
        pipeline = Pipeline([Deterministic(lambda i, ctx: i, node_id="pass")], budget=_budget())

        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))

        assert result.manifest["memory"] is None


class TestRedaction:
    def test_a_credential_is_redacted_before_it_is_stored(self, tmp_path) -> None:
        """The trajectory redacted it and the durable copy used to keep it."""
        store = _store(tmp_path)

        def save(inputs, ctx):
            return ctx.call_tool("remember", key="note", value=f"the key {A_KEY} was shown")

        pipeline = Pipeline(
            [Deterministic(save, node_id="save", tools=[remember()])], budget=_budget()
        )
        result = pipeline.run(
            {},
            envelope=RunEnvelope(
                run_dir=tmp_path / "runs", memory=_declared(tmp_path), redaction=Redaction()
            ),
            memory_scope="user-1",
        )

        stored = store.get("note")
        assert A_KEY not in stored.value
        assert "[redacted:sk_prefixed_key]" in stored.value
        assert A_KEY not in result.trajectory_path.read_text()

    def test_an_entry_records_the_rules_it_was_written_under(self, tmp_path) -> None:
        """A store outlives every run, so a rule added later does not reach it."""
        store = _store(tmp_path)

        store.put("note", "nothing sensitive", redaction=Redaction(patterns={"x": r"zzz"}))

        entry = store.get("note")
        assert entry.rules["declared_rules"] == ["x"]
        assert entry.rules["enabled"] is True

    def test_redaction_left_off_is_recorded_as_such(self, tmp_path) -> None:
        store = _store(tmp_path)

        store.put("note", f"the key {A_KEY}", redaction=Redaction.none())

        assert store.get("note").rules["enabled"] is False


class TestReplay:
    def test_a_replayed_run_rebuilds_the_store(self, tmp_path) -> None:
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def what_to_store() -> str:
            """A keyed call, so the cassette holds something a replay reads."""
            return "short books"

        def save_then_read(inputs, ctx):
            ctx.call_tool("remember", key="pref", value=ctx.call_tool("what_to_store"))
            return ctx.call_tool("recall", key="pref")

        pipeline = Pipeline(
            [
                Deterministic(
                    save_then_read,
                    node_id="both",
                    tools=[remember(), recall(), what_to_store],
                )
            ],
            budget=_budget(),
        )
        cassette = tmp_path / "c.jsonl"

        live = pipeline.run(
            {},
            envelope=RunEnvelope(
                run_dir=tmp_path / "live",
                memory=_declared(tmp_path / "live"),
                cassette=Cassette.record(cassette),
            ),
            memory_scope="user-1",
        )
        replayed_store = _store(tmp_path / "replay")
        replayed = pipeline.run(
            {},
            envelope=RunEnvelope(
                run_dir=tmp_path / "replay",
                memory=_declared(tmp_path / "replay"),
                cassette=Cassette.replay(cassette),
            ),
            memory_scope="user-1",
        )

        assert live.output["value"] == replayed.output["value"] == "short books"
        assert replayed.output["found"] is True
        assert replayed_store.get("pref").value == "short books"
        # The write ran again rather than being served, so the entry is stamped with the
        # replay's own time. What the run reads back is the same; when it was stored is not.
        assert replayed.output["stored_at"] != live.output["stored_at"]

    def test_no_memory_call_is_stored_in_the_cassette(self, tmp_path) -> None:
        def save(inputs, ctx):
            return ctx.call_tool("remember", key="pref", value="short books")

        pipeline = Pipeline(
            [Deterministic(save, node_id="save", tools=[remember()])], budget=_budget()
        )
        cassette = tmp_path / "c.jsonl"

        pipeline.run(
            {},
            envelope=RunEnvelope(
                run_dir=tmp_path / "runs",
                memory=_declared(tmp_path),
                cassette=Cassette.record(cassette),
            ),
            memory_scope="user-1",
        )

        assert not cassette.exists() or cassette.read_text().strip() == ""


def _answering_pipeline() -> Pipeline:
    def answer(inputs, ctx):
        stored = ctx.call_tool("recall", key="shared")
        if stored["found"]:
            return {"answer": stored["value"], "source": "memory"}
        ctx.call_tool("remember", key="shared", value=inputs["q"])
        return {"answer": inputs["q"], "source": "computed"}

    return Pipeline(
        [Deterministic(answer, node_id="answer", tools=[recall(), remember()])],
        budget=_budget(),
    )


class TestAnEvaluation:
    @staticmethod
    def _suite(pipeline: Pipeline, examples: list[Example]) -> EvalSuite:
        return EvalSuite(
            pipeline,
            ExampleSet(examples),
            answer="answer",
            matches=lambda s: s.answer.strip() == s.expected.strip(),
        )

    def test_no_rollout_reads_another_rollouts_write(self, tmp_path) -> None:
        """One store shared by k×n rollouts made the same measurement report two numbers."""
        examples = [
            Example(id=f"e{i}", inputs={"q": f"q{i}"}, expected=f"q{i}", split="held_out")
            for i in range(1, 5)
        ]
        suite = self._suite(_answering_pipeline(), examples)

        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path / "runs", memory=_declared(tmp_path)),
            split="held_out",
            k=3,
            seed=41,
        )

        sources = []
        for rollout in results.rollouts:
            last = [
                r
                for r in _records(Path(rollout.trajectory))
                if r["record_type"] == "node_execution"
            ][-1]
            sources.append(last["outputs"]["source"])
        assert sources == ["computed"] * 12
        assert results.metrics["accuracy"].interval.point == 1.0

    def test_an_example_seeds_the_rollouts_store(self, tmp_path) -> None:
        examples = [
            Example(
                id="e1",
                inputs={"q": "q1"},
                expected="from the example",
                split="held_out",
                memory={"shared": "from the example"},
            )
        ]
        suite = self._suite(_answering_pipeline(), examples)

        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path / "runs", memory=_declared(tmp_path)),
            split="held_out",
            k=2,
            seed=41,
        )

        assert results.metrics["accuracy"].interval.point == 1.0

    def test_the_store_the_project_declared_is_not_written_to(self, tmp_path) -> None:
        store = _store(tmp_path)
        examples = [Example(id="e1", inputs={"q": "q1"}, expected="q1", split="held_out")]

        self._suite(_answering_pipeline(), examples).run(
            envelope=RunEnvelope(run_dir=tmp_path / "runs", memory=_declared(tmp_path)),
            split="held_out",
            k=2,
            seed=41,
        )

        assert store.keys() == []

    def test_a_memory_tool_does_not_reach_the_eval_refusal(self, tmp_path) -> None:
        """`writes` is honest here because the runner scopes the store to the rollout."""
        found = {tool.name: tool.side_effect_class for tool in _tools_of(_answering_pipeline())}

        assert found["remember"] is SideEffectClass.WRITES
        assert not any(c.reaches_outside_the_run for c in found.values())

    def test_it_refuses_a_recording_that_answers_one_call_two_ways(self, tmp_path) -> None:
        """A tool call is keyed on its arguments, not on which rollout made it."""
        calls = iter(["first", "second"])

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def ask(question: str) -> str:
            """Answers differently each time it is called."""
            return next(calls)

        def answer(inputs, ctx):
            return {"answer": ctx.call_tool("ask", question="the same question")}

        pipeline = Pipeline(
            [Deterministic(answer, node_id="answer", tools=[ask])], budget=_budget()
        )
        examples = [
            Example(id="e1", inputs={}, expected="first", split="held_out"),
            Example(id="e2", inputs={}, expected="second", split="held_out"),
        ]
        cassette = tmp_path / "c.jsonl"
        self._suite(pipeline, examples).run(
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette)),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )

        with pytest.raises(ConfigurationError) as exc:
            self._suite(pipeline, examples).run(
                envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette)),
                split="held_out",
                k=1,
                seed=41,
            )

        assert "'ask'" in str(exc.value)
        assert "more than one way" in str(exc.value)

    def test_it_allows_a_recording_whose_identical_calls_agree(self, tmp_path) -> None:
        """19 tool calls, 4 entries: one recorded answer serving k rollouts is the point."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def look_up(topic: str) -> str:
            """A function of its arguments."""
            return f"about {topic}"

        def answer(inputs, ctx):
            return {"answer": ctx.call_tool("look_up", topic="shared")}

        pipeline = Pipeline(
            [Deterministic(answer, node_id="answer", tools=[look_up])], budget=_budget()
        )
        examples = [
            Example(id=f"e{i}", inputs={}, expected="about shared", split="held_out")
            for i in (1, 2)
        ]
        cassette = tmp_path / "c.jsonl"
        self._suite(pipeline, examples).run(
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(cassette)),
            split="held_out",
            k=2,
            seed=41,
            concurrency=1,
        )

        results = self._suite(pipeline, examples).run(
            envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette)),
            split="held_out",
            k=2,
            seed=41,
        )

        assert len(_records(cassette)) == 1
        assert results.metrics["accuracy"].interval.point == 1.0


class TestSearch:
    def test_an_empty_store_returns_no_results(self, tmp_path) -> None:
        handle = Memory(_store(tmp_path))

        assert memory_search().fn(memory=handle, query="anything") == {
            "results": [],
            "stored": 0,
        }

    def test_it_finds_a_fact_by_the_words_in_it(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.put("pref", "prefers books under 300 pages")
        store.put("city", "lives in Kirkwall")
        handle = Memory(store)

        found = memory_search().fn(memory=handle, query="books pages")

        assert found["stored"] == 2
        assert found["results"][0]["key"] == "pref"

    def test_a_query_sharing_no_words_finds_nothing(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.put("pref", "prefers books under 300 pages")

        found = memory_search().fn(memory=Memory(store), query="length preference")

        assert found["results"] == []

    def test_a_miss_over_a_store_that_holds_something_lists_its_keys(self, tmp_path) -> None:
        """Found live: the model searched, matched nothing, and never looked again."""
        store = _store(tmp_path)
        store.put("max_reading_length_pages", "never finishes books over 300 pages")

        found = memory_search().fn(memory=Memory(store), query="science fiction recommendation")

        assert found["results"] == []
        assert found["keys"] == ["max_reading_length_pages"]
        assert found["stored"] == 1

    def test_a_hit_does_not_list_the_keys(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.put("pref", "prefers books under 300 pages")

        found = memory_search().fn(memory=Memory(store), query="books pages")

        assert "keys" not in found

    def test_an_empty_store_lists_no_keys(self, tmp_path) -> None:
        found = memory_search().fn(memory=Memory(_store(tmp_path)), query="anything")

        assert found == {"results": [], "stored": 0}

    def test_the_key_listing_is_capped_and_the_count_is_not(self, tmp_path) -> None:
        """`stored` is what says a store is larger than the keys it just listed."""
        store = _store(tmp_path)
        for n in range(MAX_KEYS_ON_EMPTY + 12):
            store.put(f"fact_{n:03d}", f"the {n}th thing worth writing down")

        found = memory_search().fn(memory=Memory(store), query="zzz nothing matches")

        assert found["results"] == []
        assert len(found["keys"]) == MAX_KEYS_ON_EMPTY
        assert found["keys"] == sorted(found["keys"])
        assert found["stored"] == MAX_KEYS_ON_EMPTY + 12

    def test_embeddings_with_no_ranking_is_refused(self) -> None:
        """The same rule `DocumentIndex` applies, at the other place `embeddings=` is passed."""
        with pytest.raises(ConfigurationError) as raised:
            memory_search(embeddings=FakeEmbeddingClient())

        assert "memory_search was given embeddings= and no ranking=" in str(raised.value)
        assert "ranking=Semantic()" in str(raised.value)

    def test_a_ranking_alongside_embeddings_builds(self) -> None:
        built = memory_search(embeddings=FakeEmbeddingClient(), ranking=Semantic())

        assert set(built.handles) == {"memory", "retrieval"}


class TestWhoseMemoryARunReads:
    """The store is on the envelope and the scope is on the run, as `P3-44` settled it."""

    def _saving(self) -> Pipeline:
        def save(inputs, ctx):
            return ctx.call_tool("remember", key="pref", value=inputs["pref"])

        return Pipeline([Deterministic(save, node_id="save", tools=[remember()])], budget=_budget())

    def test_one_envelope_serves_two_end_users(self, tmp_path) -> None:
        """The shape a request handler has: one envelope built once, a scope per request."""
        env = RunEnvelope(run_dir=tmp_path / "runs", memory=_declared(tmp_path))
        pipeline = self._saving()

        pipeline.run({"pref": "short books"}, envelope=env, memory_scope="user-1")
        pipeline.run({"pref": "long books"}, envelope=env, memory_scope="user-2")

        assert _store(tmp_path, "user-1").get("pref").value == "short books"
        assert _store(tmp_path, "user-2").get("pref").value == "long books"

    def test_a_store_with_no_scope_named_is_refused_before_the_run(self, tmp_path) -> None:
        env = RunEnvelope(run_dir=tmp_path / "runs", memory=_declared(tmp_path))

        with pytest.raises(ConfigurationError) as raised:
            self._saving().run({"pref": "short books"}, envelope=env)

        assert "names no memory scope" in str(raised.value)
        assert "memory_scope=f'user-{user_id}'" in str(raised.value)
        assert not (tmp_path / "runs").exists()

    def test_a_scope_with_no_store_declared_is_refused_before_the_run(self, tmp_path) -> None:
        env = RunEnvelope(run_dir=tmp_path / "runs")

        with pytest.raises(ConfigurationError) as raised:
            self._saving().run({"pref": "short books"}, envelope=env, memory_scope="user-1")

        assert "declares no store" in str(raised.value)
        assert "MemoryStore('memory/')" in str(raised.value)

    def test_a_pipeline_reaching_no_memory_needs_neither(self, tmp_path) -> None:
        pipeline = Pipeline([Deterministic(lambda i, ctx: i, node_id="pass")], budget=_budget())

        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path))

        assert result.manifest["memory"] is None


class TestAResumedRunsMemory:
    """A resume is told the scope again, since the manifest holds a digest of it."""

    def _stopping(self) -> Pipeline:
        def save(inputs, ctx):
            return ctx.call_tool("remember", key="pref", value="short books")

        return Pipeline(
            [
                Deterministic(lambda i, ctx: i, node_id="first"),
                Deterministic(save, node_id="save", tools=[remember()], suspend_before=True),
            ],
            budget=_budget(),
        )

    def _stopped(self, tmp_path) -> tuple[Pipeline, RunEnvelope]:
        env = RunEnvelope(run_dir=tmp_path / "runs", memory=_declared(tmp_path))
        pipeline = self._stopping()
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=env, run_id="r1", memory_scope="user-1")
        return pipeline, env

    def test_a_resume_writes_into_the_scope_the_run_started_under(self, tmp_path) -> None:
        pipeline, env = self._stopped(tmp_path)

        result = pipeline.resume("r1", envelope=env, memory_scope="user-1")

        assert _store(tmp_path, "user-1").get("pref").value == "short books"
        assert result.manifest["memory"]["scope_digest"] == _store(tmp_path, "user-1").scope_digest

    def test_another_end_users_scope_is_refused(self, tmp_path) -> None:
        """A reply filed against the wrong run would write one person's facts into another's."""
        pipeline, env = self._stopped(tmp_path)

        with pytest.raises(CallerFacingError) as raised:
            pipeline.resume("r1", envelope=env, memory_scope="user-2")

        assert "another end user's memory" in str(raised.value)
        assert "user-1" not in str(raised.value)
        assert "user-2" not in str(raised.value)
        assert _store(tmp_path, "user-2").keys() == []
        # The refusal releases the claim, so a corrected retry can still continue the run.
        assert pipeline.resume("r1", envelope=env, memory_scope="user-1").outcome == "completed"

    def test_a_resume_naming_no_scope_is_refused_before_the_state_is_touched(
        self, tmp_path
    ) -> None:
        pipeline, env = self._stopped(tmp_path)

        with pytest.raises(ConfigurationError) as raised:
            pipeline.resume("r1", envelope=env)

        assert "Pipeline.resume(..., memory_scope=" in str(raised.value)
        # The suspension is still claimable, so the run can be continued once it is named.
        assert pipeline.resume("r1", envelope=env, memory_scope="user-1").outcome == "completed"


class TestWhatAScopeMayHold:
    """A scope is an identifier a project chooses, and it decides a directory name."""

    def test_a_scope_holding_a_path_separator_cannot_escape_the_directory(self, tmp_path) -> None:
        store = MemoryStore(tmp_path / "memory")

        store.scoped("../../etc/passwd").put("k", "v")

        made = [path.name for path in (tmp_path / "memory").iterdir()]
        assert made == [store.scoped("../../etc/passwd").scope_digest]
        assert all(len(name) == 12 for name in made)
        assert not (tmp_path / "etc").exists()

    def test_a_very_long_scope_is_a_directory_like_any_other(self, tmp_path) -> None:
        store = MemoryStore(tmp_path / "memory")

        store.scoped("u" * 5000).put("k", "v")

        assert store.scoped("u" * 5000).get("k").value == "v"

    def test_an_empty_scope_on_the_run_is_refused_by_name(self, tmp_path) -> None:
        """`_refuse_unreachable_memory` passes an empty string, so the store refuses it."""
        pipeline = Pipeline([Deterministic(lambda i, ctx: i, node_id="pass")], budget=_budget())
        env = RunEnvelope(run_dir=tmp_path / "runs", memory=_declared(tmp_path))

        with pytest.raises(ConfigurationError) as raised:
            pipeline.run({}, envelope=env, memory_scope="")

        assert "non-empty string" in str(raised.value)
        assert not list((tmp_path / "runs").rglob("manifest.json"))
