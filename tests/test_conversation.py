"""A conversation that outlives the run: what carries between turns, and what records it.

One turn is one run. These fix the decisions of `P3-39`: what a stored turn is, where the
store lives, when messages go on, what compaction does, and what the manifest says.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from simple_agents import (
    AgentNode,
    Budget,
    ConversationStore,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Maybe,
    Pipeline,
    RunEnvelope,
)
from simple_agents.builtins import compact_conversation
from simple_agents.records.conversation import new_to_the_thread
from simple_agents.errors import ConfigurationError, RunSuspended, Suspend
from simple_agents.models import ToolCallRequest, fake_response

SYSTEM = "Answer as the bookshop's assistant."


class Answer(BaseModel):
    answer: Maybe[str]


def build_prompt(inputs, ctx):
    return [
        {"role": "system", "content": SYSTEM},
        *ctx.conversation,
        {"role": "user", "content": inputs["question"]},
    ]


def _budget() -> Budget:
    return Budget(max_steps=12, max_tokens=99_999, max_cost=None, max_wall_clock_ms=60_000)


def _pipeline() -> Pipeline:
    return Pipeline(
        [LLMNode(build_prompt, output_schema=Answer, node_id="reply")], budget=_budget()
    )


def _client(count: int = 6) -> FakeModelClient:
    return FakeModelClient(
        responses=[fake_response(content=f'{{"answer": "a{i}"}}') for i in range(count)]
    )


@pytest.fixture
def env(tmp_path: Path) -> RunEnvelope:
    return RunEnvelope(
        run_dir=tmp_path / "runs",
        conversations=ConversationStore(tmp_path / "conversations"),
    )


class TestWhatCarriesBetweenRuns:
    def test_a_second_run_is_sent_what_the_first_one_said(self, env) -> None:
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="c1")
        pipeline.run({"question": "q2"}, envelope=env, model=client, conversation_id="c1")

        roles = [m["role"] for m in client.requests[-1].messages]
        assert roles == ["system", "user", "assistant", "user"]
        assert client.requests[-1].messages[1]["content"] == "q1"
        assert client.requests[-1].messages[-1]["content"] == "q2"

    def test_two_conversations_do_not_see_each_other(self, env) -> None:
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="c1")
        pipeline.run({"question": "q2"}, envelope=env, model=client, conversation_id="c2")

        assert [m["content"] for m in client.requests[-1].messages] == [SYSTEM, "q2"]

    def test_a_run_naming_no_thread_carries_nothing(self, env) -> None:
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="c1")

        def alone(inputs, ctx):
            assert ctx.conversation.id is None
            return [*ctx.conversation, {"role": "user", "content": inputs["question"]}]

        Pipeline([LLMNode(alone, output_schema=Answer, node_id="reply")], budget=_budget()).run(
            {"question": "q2"}, envelope=env, model=client
        )

        assert [m["content"] for m in client.requests[-1].messages] == ["q2"]

    def test_the_system_message_is_supplied_each_turn_and_never_stored(self, env) -> None:
        """A system prompt carrying today's date has to be able to change."""
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="c1")
        pipeline.run({"question": "q2"}, envelope=env, model=client, conversation_id="c1")

        stored = env.conversations.thread("c1").messages()
        assert [m["role"] for m in stored] == ["user", "assistant", "user", "assistant"]
        assert [m["role"] for m in client.requests[-1].messages].count("system") == 1


class TestWhatEnrolsANode:
    def test_a_node_that_never_reads_it_writes_nothing(self, env) -> None:
        """A middle step that summarises a document does not join the chat."""

        def aside(inputs, ctx):
            return [{"role": "user", "content": "unrelated"}]

        client = _client()
        Pipeline([LLMNode(aside, output_schema=Answer, node_id="aside")], budget=_budget()).run(
            {"question": "q1"}, envelope=env, model=client, conversation_id="c1"
        )

        assert env.conversations.thread("c1").messages() == []
        assert env.conversations.thread("c1").turn_count == 0

    def test_a_fan_out_reads_the_conversation_and_adds_nothing(self, env) -> None:
        """There is no order for many items at once to go on one sequence of turns in."""
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="c1")
        before = env.conversations.thread("c1").messages()

        def per_item(inputs, ctx):
            # A fanned-out node is handed the whole input with the fanned key holding one
            # item, rather than the item alone.
            assert list(ctx.conversation) == before
            return [*ctx.conversation, {"role": "user", "content": inputs["items"]["q"]}]

        Pipeline(
            [LLMNode(per_item, output_schema=Answer, node_id="each", over="items")],
            budget=_budget(),
        ).run({"items": [{"q": "a"}, {"q": "b"}]}, envelope=env, model=client, conversation_id="c1")

        assert env.conversations.thread("c1").messages() == before
        assert env.conversations.thread("c1").turn_count == 1


class TestWhatIsStored:
    def test_the_wire_messages_are_what_is_kept(self, env) -> None:
        """D1: a stored turn is the node's messages, so the agent's working carries."""

        def looked_up(query: str) -> str:
            "Look something up."
            return "Le Guin"

        from simple_agents import SideEffectClass, tool

        look_up = tool(side_effect_class=SideEffectClass.READ_ONLY)(looked_up)
        client = FakeModelClient(
            responses=[
                fake_response(
                    content="",
                    tool_calls=[
                        ToolCallRequest(id="c1", name="looked_up", arguments={"query": "x"})
                    ],
                ),
                fake_response(
                    content="",
                    tool_calls=[
                        ToolCallRequest(id="c2", name="finish", arguments={"answer": "Le Guin"})
                    ],
                ),
            ]
        )
        node = AgentNode(
            build_prompt,
            tools=[look_up],
            output_schema=Answer,
            budget=_budget(),
            node_id="reply",
        )
        Pipeline([node], budget=_budget()).run(
            {"question": "q1"}, envelope=env, model=client, conversation_id="c1"
        )

        roles = [m["role"] for m in env.conversations.thread("c1").messages()]
        assert "tool" in roles, "the observation the agent read is part of the conversation"
        assert roles[0] == "user"

    def test_compact_leaves_out_the_working(self, env) -> None:
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="c1")

        assert [m["role"] for m in env.conversations.thread("c1").compact()] == [
            "user",
            "assistant",
        ]

    def test_without_provider_state_drops_what_one_backend_needs_back(self, env) -> None:
        thread = env.conversations.thread("c1")
        turn = thread.open_turn(run_id="r1", node_id="reply", carried_in=0)
        thread.add(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "reasoning": "thinking",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "name": "x",
                            "arguments": {},
                            "provider": {"thought_signature": "Er0B"},
                        }
                    ],
                }
            ],
            turn=turn,
        )

        [held] = thread.without_provider_state()
        assert "reasoning" not in held
        assert "provider" not in held["tool_calls"][0]
        assert "provider" in thread.messages()[0]["tool_calls"][0]


class TestWhenMessagesGoOn:
    def test_a_turn_is_on_the_thread_before_the_run_finishes(self, env) -> None:
        """D3: what was asked survives a run that never got to answer."""
        seen: list[int] = []

        def watching(inputs, ctx):
            seen.append(len(env.conversations.thread("c1").messages()))
            raise RuntimeError("killed mid-turn")

        pipeline = Pipeline(
            [
                LLMNode(build_prompt, output_schema=Answer, node_id="reply"),
                Deterministic(watching, node_id="after"),
            ],
            budget=_budget(),
        )
        with pytest.raises(RuntimeError):
            pipeline.run({"question": "q1"}, envelope=env, model=_client(), conversation_id="c1")

        assert seen == [2], "the question and the answer were on before the next node ran"

    def test_a_run_that_errored_closes_its_turn_saying_so(self, env) -> None:
        def blow_up(request):
            raise RuntimeError("backend down")

        with pytest.raises(RuntimeError):
            _pipeline().run(
                {"question": "q1"},
                envelope=env,
                model=FakeModelClient(answer=blow_up),
                conversation_id="c1",
            )

        [turn] = env.conversations.thread("c1").turns()
        assert turn.outcome == "error"
        assert turn.said == "q1"


class TestWhatTheManifestSays:
    def test_it_names_the_thread_the_turn_and_what_was_carried_in(self, env) -> None:
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="chat-8817")
        result = pipeline.run(
            {"question": "q2"}, envelope=env, model=client, conversation_id="chat-8817"
        )

        held = json.loads(result.paths.manifest.read_text())["conversation"]
        assert held["id"] == "chat-8817"
        assert held["turn"] == 2
        assert held["carried_in"] == 2
        assert held["node_id"] == "reply"

    def test_the_thread_id_is_recorded_as_it_was_given(self, env) -> None:
        """D7: it names a conversation the project minted, so it is not digested."""
        result = _pipeline().run(
            {"question": "q1"}, envelope=env, model=_client(), conversation_id="chat-8817"
        )

        assert json.loads(result.paths.manifest.read_text())["conversation"]["id"] == ("chat-8817")

    def test_carried_in_is_zero_where_nothing_read_it(self, env) -> None:
        """The failure this field exists for: written correctly and never read."""

        def never_reads(inputs, ctx):
            return [{"role": "user", "content": inputs["question"]}]

        pipeline = Pipeline(
            [LLMNode(never_reads, output_schema=Answer, node_id="reply")], budget=_budget()
        )
        client = _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="c1")
        result = pipeline.run({"question": "q2"}, envelope=env, model=client, conversation_id="c1")

        held = json.loads(result.paths.manifest.read_text())["conversation"]
        assert held["carried_in"] == 0

    def test_a_run_outside_a_conversation_records_null(self, env) -> None:
        result = _pipeline().run({"question": "q1"}, envelope=env, model=_client())

        assert json.loads(result.paths.manifest.read_text())["conversation"] is None


class TestTheStore:
    def test_a_thread_with_nowhere_to_go_is_refused(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as refusal:
            _pipeline().run(
                {"question": "q1"},
                envelope=RunEnvelope(run_dir=tmp_path),
                model=_client(),
                conversation_id="c1",
            )

        assert "ConversationStore" in str(refusal.value)
        assert "outlives the run" in str(refusal.value)

    def test_the_file_is_named_by_a_digest_and_the_id_is_inside_it(self, env) -> None:
        _pipeline().run(
            {"question": "q1"}, envelope=env, model=_client(), conversation_id="chat/8817"
        )

        [path] = list(Path(env.conversations.directory).glob("*.jsonl"))
        assert "chat" not in path.name
        assert env.conversations.conversation_ids() == ["chat/8817"]

    def test_forget_removes_one_conversation(self, env) -> None:
        _pipeline().run({"question": "q1"}, envelope=env, model=_client(), conversation_id="c1")

        assert env.conversations.thread("c1").forget() is True
        assert env.conversations.thread("c1").messages() == []

    def test_an_empty_id_is_refused(self, env) -> None:
        with pytest.raises(ConfigurationError) as refusal:
            env.conversations.thread("  ")

        assert "names one conversation" in str(refusal.value)


class TestWhatATurnAdded:
    def test_a_splatted_history_records_only_the_new_message(self) -> None:
        carried = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        produced = [
            {"role": "system", "content": "S"},
            *carried,
            {"role": "user", "content": "c"},
        ]

        assert new_to_the_thread(produced, carried) == [{"role": "user", "content": "c"}]

    def test_a_copied_history_records_only_the_new_message(self) -> None:
        carried = [{"role": "user", "content": "a"}]
        produced = [dict(carried[0]), {"role": "user", "content": "c"}]

        assert new_to_the_thread(produced, carried) == [{"role": "user", "content": "c"}]


class TestCompaction:
    def _compacting(self) -> Pipeline:
        def shrink(inputs, ctx):
            if len(ctx.conversation) > 4:
                ctx.call_tool("compact_conversation", summary="They asked about Le Guin.")
            return inputs

        return Pipeline(
            [
                Deterministic(shrink, node_id="compact", tools=[compact_conversation(keep_last=2)]),
                LLMNode(build_prompt, output_schema=Answer, node_id="reply"),
            ],
            budget=_budget(),
        )

    def test_it_replaces_the_older_messages_and_keeps_the_newest(self, env) -> None:
        pipeline, client = self._compacting(), _client(8)
        for i in range(4):
            pipeline.run({"question": f"q{i}"}, envelope=env, model=client, conversation_id="c1")

        held = env.conversations.thread("c1").messages()
        assert held[0]["content"].startswith("Earlier in this conversation:")
        assert len(held) < 8

    def test_what_it_dropped_is_still_in_the_file(self, env) -> None:
        pipeline, client = self._compacting(), _client(8)
        for i in range(4):
            pipeline.run({"question": f"q{i}"}, envelope=env, model=client, conversation_id="c1")

        path = env.conversations.thread("c1").path
        records = [json.loads(line) for line in path.read_text().splitlines()]
        written = [r for r in records if r.get("record") == "message"]
        assert len(written) > len(env.conversations.thread("c1").messages())
        assert any(r.get("record") == "compaction" for r in records)

    def test_the_call_is_on_the_trajectory(self, env) -> None:
        pipeline, client = self._compacting(), _client(8)
        result = None
        for i in range(4):
            result = pipeline.run(
                {"question": f"q{i}"}, envelope=env, model=client, conversation_id="c1"
            )

        records = [json.loads(line) for line in result.paths.trajectory.read_text().splitlines()]
        calls = [r for r in records if r["record_type"] == "tool_call"]
        assert calls and all(r["re_executed"] for r in calls)

    def test_a_conversation_short_enough_is_left_alone(self, env) -> None:
        thread = env.conversations.thread("c1")
        turn = thread.open_turn(run_id="r1", node_id="n", carried_in=0)
        thread.add([{"role": "user", "content": "a"}], turn=turn)

        before = thread.messages()
        tool = compact_conversation(keep_last=4)
        from simple_agents.records.conversation import Conversation

        got = tool.fn(conversation=Conversation(_thread=thread, _turn=1), summary="x")

        assert got == {"replaced": 0, "messages": 1}
        assert thread.messages() == before


class TestInAnEvaluation:
    def _suite(self, examples, seen):
        def answer(request):
            seen.append([m["content"] for m in request.messages])
            return fake_response(content='{"answer": "The Left Hand of Darkness"}')

        from simple_agents import EvalSuite, ExampleSet

        return (
            EvalSuite(
                _pipeline(),
                ExampleSet(examples),
                answer="answer",
                matches=lambda s: str(s.expected).lower() in str(s.answer).lower(),
            ),
            FakeModelClient(answer=answer),
        )

    def test_an_example_carries_what_was_already_said(self, env) -> None:
        from simple_agents import Example

        seen: list = []
        suite, client = self._suite(
            [
                Example(
                    id="q4",
                    inputs={"question": "What else did she write?"},
                    expected="The Left Hand of Darkness",
                    split="held_out",
                    conversation=[
                        {"role": "user", "content": "Who wrote The Dispossessed?"},
                        {"role": "assistant", "content": "Ursula K. Le Guin"},
                    ],
                )
            ],
            seen,
        )
        suite.run(envelope=env, model=client, split="held_out", k=1)

        assert seen[0] == [
            SYSTEM,
            "Who wrote The Dispossessed?",
            "Ursula K. Le Guin",
            "What else did she write?",
        ]

    def test_each_rollout_starts_from_its_own_conversation(self, env) -> None:
        from simple_agents import Example

        seen: list = []
        suite, client = self._suite(
            [
                Example(
                    id="q4",
                    inputs={"question": "again"},
                    expected="The Left Hand of Darkness",
                    split="held_out",
                    conversation=[{"role": "user", "content": "seeded"}],
                )
            ],
            seen,
        )
        suite.run(envelope=env, model=client, split="held_out", k=3)

        assert len(seen) == 3
        assert all(sent == [SYSTEM, "seeded", "again"] for sent in seen)

    def test_turns_run_in_order_against_one_conversation(self, env) -> None:
        from simple_agents import Example

        seen: list = []
        suite, client = self._suite(
            [
                Example(
                    id="q9",
                    inputs={"question": "I need a book"},
                    expected="The Left Hand of Darkness",
                    split="held_out",
                    turns=["Under 400 pages", "Not grimdark"],
                )
            ],
            seen,
        )
        results = suite.run(envelope=env, model=client, split="held_out", k=1)

        assert len(seen) == 3, "one run per turn"
        assert seen[0][-1] == "I need a book"
        assert seen[1][-1] == "Under 400 pages"
        assert seen[2][-1] == "Not grimdark"
        assert seen[2][1] == "I need a book", "turn 3 was sent turn 1"
        assert results.metrics["accuracy"].interval.point == 1.0

    def test_each_turn_is_its_own_run(self, env) -> None:
        from simple_agents import Example
        from simple_agents.envelope import runs

        seen: list = []
        suite, client = self._suite(
            [
                Example(
                    id="q9",
                    inputs={"question": "start"},
                    expected="The Left Hand of Darkness",
                    split="held_out",
                    turns=["next"],
                )
            ],
            seen,
        )
        suite.run(envelope=env, model=client, split="held_out", k=1)

        ids = sorted(r.run_id for r in runs(env.run_dir, nested=True))
        assert ids == ["q9-0-t1", "q9-0-t2"]


class TestWhatIsScrubbedOnTheWayIn:
    def test_a_declared_secret_does_not_reach_the_conversation(self, tmp_path, monkeypatch) -> None:
        """The conversation outlives every run, so a credential in it outlives them too."""
        from simple_agents import Redaction

        monkeypatch.setenv("FAKE_TOKEN", "swordfish-not-a-real-secret")
        env = RunEnvelope(
            run_dir=tmp_path / "runs",
            conversations=ConversationStore(tmp_path / "conversations"),
            redaction=Redaction(secret_env=["FAKE_TOKEN"]),
        )
        _pipeline().run(
            {"question": "the token is swordfish-not-a-real-secret"},
            envelope=env,
            model=_client(),
            conversation_id="c1",
        )

        stored = env.conversations.thread("c1").messages()
        assert "swordfish-not-a-real-secret" not in stored[0]["content"]
        assert "[redacted:env:FAKE_TOKEN]" in stored[0]["content"]

    def test_a_known_credential_format_is_caught_without_being_declared(self, env) -> None:
        _pipeline().run(
            {"question": "use ghp_abcdefghijklmnopqrstuvwxyz0123456789 for it"},
            envelope=env,
            model=_client(),
            conversation_id="c1",
        )

        [turn] = env.conversations.thread("c1").turns()
        assert "ghp_" not in str(turn.said)

    def test_the_message_says_which_field_was_changed(self, tmp_path, monkeypatch) -> None:
        from simple_agents import Redaction

        monkeypatch.setenv("FAKE_TOKEN", "swordfish-not-a-real-secret")
        env = RunEnvelope(
            run_dir=tmp_path / "runs",
            conversations=ConversationStore(tmp_path / "conversations"),
            redaction=Redaction(secret_env=["FAKE_TOKEN"]),
        )
        _pipeline().run(
            {"question": "swordfish-not-a-real-secret"},
            envelope=env,
            model=_client(),
            conversation_id="c1",
        )

        path = env.conversations.thread("c1").path
        records = [json.loads(line) for line in path.read_text().splitlines()]
        [first] = [r for r in records if r.get("record") == "message"][:1]
        assert first["redactions"] == ["content"]


class TestAnAbsentConversation:
    def test_the_same_prompt_serves_a_chat_and_a_one_shot(self, env) -> None:
        client = _client()
        _pipeline().run({"question": "q1"}, envelope=env, model=client, conversation_id="c1")
        _pipeline().run({"question": "q2"}, envelope=env, model=client)

        assert [m["content"] for m in client.requests[-1].messages] == [SYSTEM, "q2"]

    def test_id_is_none_where_the_run_names_no_conversation(self, env) -> None:
        seen: list = []

        def looking(inputs, ctx):
            seen.append(ctx.conversation.id)
            return [*ctx.conversation, {"role": "user", "content": inputs["question"]}]

        pipeline = Pipeline(
            [LLMNode(looking, output_schema=Answer, node_id="reply")], budget=_budget()
        )
        client = _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="c1")
        pipeline.run({"question": "q2"}, envelope=env, model=client)

        assert seen == ["c1", None]


class TestTheDocumentedPatterns:
    """The examples in `docs/conversation.md`, run rather than read.

    An example that parses and resolves can still be wrong, and `prose_check.py` cannot see
    that. `docs/conversation.md` §5's two-node pattern was missing `allow_unknown=False`
    and did not run.
    """

    def test_the_two_node_compaction_pattern_runs(self, env) -> None:
        class Summary(BaseModel):
            summary: str

        def summarise(inputs, ctx):
            older = ctx.conversation.messages()[:-6]
            return "Summarise this conversation for whoever continues it:\n" + str(older)

        def file_it(summary, ctx):
            ctx.call_tool("compact_conversation", summary=summary.summary)
            return summary

        pipeline = Pipeline(
            [
                LLMNode(summarise, output_schema=Summary, node_id="summarise", allow_unknown=False),
                Deterministic(file_it, node_id="compact", tools=[compact_conversation()]),
            ],
            budget=_budget(),
        )
        thread = env.conversations.thread("c1")
        turn = thread.open_turn(run_id="seed", node_id="x", carried_in=0)
        thread.add([{"role": "user", "content": f"m{i}"} for i in range(10)], turn=turn)
        thread.close_turn(turn=turn, run_id="seed", outcome="completed")

        pipeline.run(
            {},
            envelope=env,
            model=FakeModelClient(
                responses=[fake_response(content='{"summary": "they wanted a book"}')]
            ),
            conversation_id="c1",
        )

        held = thread.messages()
        assert len(held) < 10
        assert held[0]["content"].startswith("Earlier in this conversation:")

    def test_a_fresh_store_reads_a_conversation_back(self, env) -> None:
        """`docs/conversation.md` §4 opens a store the run never used and reads it back."""
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="chat-8817")
        pipeline.run({"question": "q2"}, envelope=env, model=client, conversation_id="chat-8817")

        reopened = ConversationStore(env.conversations.directory).thread("chat-8817")

        assert reopened.turn_count == 2
        assert len(reopened.messages()) == 4
        assert reopened.run_ids() == [
            turn.run_id for turn in env.conversations.thread("chat-8817").turns()
        ]


class TestRescoringAMultiTurnEvaluation:
    """A rollout that ran as several turns is read from what it recorded, not from its name.

    `rescore` parsed `<example>-<index>` out of the directory name, which a three-turn rollout
    writing `<example>-<index>-t<n>` broke. That is the same defect the run directory itself
    had: identity in a path rather than in the manifest.
    """

    def _suite(self, examples):
        from simple_agents import EvalSuite, ExampleSet

        return EvalSuite(
            _pipeline(),
            ExampleSet(examples),
            answer="answer",
            matches=lambda s: "ok" in str(s.answer),
        )

    def test_rescore_reproduces_the_number(self, env) -> None:
        from simple_agents import Example
        from simple_agents.evaluation import evaluation_dir

        suite = self._suite(
            [
                Example(
                    id="multi",
                    inputs={"question": "a"},
                    expected="ok",
                    split="held_out",
                    turns=["b", "c"],
                ),
                Example(id="single", inputs={"question": "z"}, expected="ok", split="held_out"),
            ]
        )
        client = FakeModelClient(answer=lambda request: fake_response(content='{"answer": "ok"}'))
        first = suite.run(envelope=env, model=client, split="held_out", k=2)
        again = suite.rescore(run_dir=evaluation_dir(env.run_dir, first.eval_id), split="held_out")

        assert again.metrics["accuracy"].interval.point == (
            first.metrics["accuracy"].interval.point
        )

    def test_the_last_turn_is_the_one_scored(self, env) -> None:
        from simple_agents import Example
        from simple_agents.envelope import runs

        answers = iter(['{"answer": "wrong"}', '{"answer": "wrong"}', '{"answer": "ok"}'])
        suite = self._suite(
            [
                Example(
                    id="multi",
                    inputs={"question": "a"},
                    expected="ok",
                    split="held_out",
                    turns=["b", "c"],
                )
            ]
        )
        results = suite.run(
            envelope=env,
            model=FakeModelClient(answer=lambda r: fake_response(content=next(answers))),
            split="held_out",
            k=1,
        )

        assert results.metrics["accuracy"].interval.point == 1.0
        turns = {
            r.run_id: r.evaluation.turn for r in runs(env.run_dir, nested=True) if r.evaluation
        }
        assert turns == {"multi-0-t1": 1, "multi-0-t2": 2, "multi-0-t3": 3}


class TestLookingAtAConversationIsNotJoiningIt:
    """A node that renders the conversation into a string is not a turn of it.

    Found live: the summarising node in `docs/conversation.md` §5 read every message to build
    its prompt, which enrolled it, so the summariser's own prompt and answer were appended to
    the conversation it was about to summarise. The compaction then reported eight messages
    replaced over a conversation of six.
    """

    def test_a_node_that_renders_it_into_a_string_adds_nothing(self, env) -> None:
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "q1"}, envelope=env, model=client, conversation_id="c1")
        before = env.conversations.thread("c1").messages()

        def looking(inputs, ctx):
            rendered = "\n".join(str(m.get("content")) for m in ctx.conversation.messages())
            return [{"role": "user", "content": f"Summarise this:\n{rendered}"}]

        Pipeline(
            [LLMNode(looking, output_schema=Answer, node_id="summarise")], budget=_budget()
        ).run({}, envelope=env, model=client, conversation_id="c1")

        assert env.conversations.thread("c1").messages() == before
        assert env.conversations.thread("c1").turn_count == 1

    def test_the_compaction_replaces_what_the_conversation_actually_held(self, env) -> None:
        class Summary(BaseModel):
            summary: str

        def summarise(inputs, ctx):
            older = ctx.conversation.messages()[:-2]
            return "Summarise:\n" + "\n".join(str(m.get("content")) for m in older)

        def file_it(summary, ctx):
            ctx.state = ctx.call_tool("compact_conversation", summary=summary.summary)
            return summary

        held = []

        def file_and_keep(summary, ctx):
            held.append(ctx.call_tool("compact_conversation", summary=summary.summary))
            return summary

        thread = env.conversations.thread("c1")
        turn = thread.open_turn(run_id="seed", node_id="x", carried_in=0)
        thread.add([{"role": "user", "content": f"m{i}"} for i in range(8)], turn=turn)
        thread.close_turn(turn=turn, run_id="seed", outcome="completed")

        Pipeline(
            [
                LLMNode(summarise, output_schema=Summary, node_id="summarise", allow_unknown=False),
                Deterministic(
                    file_and_keep, node_id="compact", tools=[compact_conversation(keep_last=2)]
                ),
            ],
            budget=_budget(),
        ).run(
            {},
            envelope=env,
            model=FakeModelClient(responses=[fake_response(content='{"summary": "s"}')]),
            conversation_id="c1",
        )

        assert held == [{"replaced": 6, "messages": 3}], "eight held, two kept, six replaced"


class TestARunThatStoppedAndContinued:
    def _suspending_once(self):
        state = {"stop": True}

        def answer(request):
            if state["stop"]:
                state["stop"] = False
                raise Suspend(waiting_for="the backend is down")
            return fake_response(content='{"answer": "ok"}')

        return FakeModelClient(answer=answer)

    def test_the_question_is_on_the_conversation_while_the_run_waits(self, env) -> None:
        with pytest.raises(RunSuspended):
            _pipeline().run(
                {"question": "hello"},
                envelope=env,
                model=self._suspending_once(),
                run_id="s1",
                conversation_id="c1",
            )

        thread = env.conversations.thread("c1")
        assert [m["content"] for m in thread.messages()] == ["hello"]
        assert [turn.outcome for turn in thread.turns()] == [None]

    def test_the_answer_lands_in_the_turn_that_asked(self, env) -> None:
        """A resume continues its own turn rather than opening a second and orphaning one."""
        pipeline, client = _pipeline(), self._suspending_once()
        with pytest.raises(RunSuspended):
            pipeline.run(
                {"question": "hello"}, envelope=env, model=client, run_id="s1", conversation_id="c1"
            )

        pipeline.resume("s1", envelope=env, model=client)

        thread = env.conversations.thread("c1")
        assert thread.turn_count == 1
        assert [turn.outcome for turn in thread.turns()] == ["completed"]
        assert [m["content"] for m in thread.messages()] == ["hello", '{"answer": "ok"}']

    def test_the_next_turn_carries_what_the_resumed_one_answered(self, env) -> None:
        pipeline, client = _pipeline(), self._suspending_once()
        with pytest.raises(RunSuspended):
            pipeline.run(
                {"question": "hello"}, envelope=env, model=client, run_id="s1", conversation_id="c1"
            )
        pipeline.resume("s1", envelope=env, model=client)
        pipeline.run(
            {"question": "second"}, envelope=env, model=client, run_id="s2", conversation_id="c1"
        )

        thread = env.conversations.thread("c1")
        assert thread.turn_count == 2
        assert [turn.outcome for turn in thread.turns()] == ["completed", "completed"]
        assert len(thread.messages()) == 4


class TestReplay:
    def test_replaying_into_a_fresh_store_reproduces_the_conversation(self, tmp_path) -> None:
        from simple_agents import Cassette

        cassette = tmp_path / "cassette.jsonl"
        live = RunEnvelope(
            run_dir=tmp_path / "live",
            conversations=ConversationStore(tmp_path / "c1"),
            cassette=Cassette.record(cassette),
        )
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "hello"}, envelope=live, model=client, conversation_id="c1")

        replayed = RunEnvelope(
            run_dir=tmp_path / "replayed",
            conversations=ConversationStore(tmp_path / "c2"),
            cassette=Cassette.replay(cassette),
        )
        pipeline.run({"question": "hello"}, envelope=replayed, model=client, conversation_id="c1")

        assert replayed.conversations.thread("c1").messages() == (
            live.conversations.thread("c1").messages()
        )

    def test_replaying_onto_a_conversation_that_moved_on_is_a_miss(self, tmp_path) -> None:
        """The messages are in the call's key, so drift is loud rather than served wrong."""
        from simple_agents import Cassette, CassetteMiss

        cassette = tmp_path / "cassette.jsonl"
        env = RunEnvelope(
            run_dir=tmp_path / "runs",
            conversations=ConversationStore(tmp_path / "c"),
            cassette=Cassette.record(cassette),
        )
        pipeline, client = _pipeline(), _client()
        pipeline.run({"question": "hello"}, envelope=env, model=client, conversation_id="c1")

        again = RunEnvelope(
            run_dir=tmp_path / "again",
            conversations=env.conversations,
            cassette=Cassette.replay(cassette),
        )
        with pytest.raises(CassetteMiss):
            pipeline.run({"question": "hello"}, envelope=again, model=client, conversation_id="c1")


class TestAnAgentNodeThatStoppedAndContinued:
    """The resumed branch does not run the prompt, so nothing there reads the conversation."""

    def _node(self):
        from simple_agents.builtins import consult

        def ask(question, options=None, about=None):
            raise Suspend(waiting_for=question)

        ask.answered_by = "end_user"
        return AgentNode(
            build_prompt,
            tools=[consult(ask)],
            output_schema=Answer,
            budget=_budget(),
            node_id="chat",
        )

    def _client(self):
        from simple_agents.models import ToolCallRequest

        return FakeModelClient(
            responses=[
                fake_response(
                    content="",
                    tool_calls=[
                        ToolCallRequest(id="c1", name="consult", arguments={"question": "which?"})
                    ],
                ),
                fake_response(
                    content="",
                    tool_calls=[
                        ToolCallRequest(id="c2", name="finish", arguments={"answer": "ok"})
                    ],
                ),
            ]
        )

    def test_the_resumed_loop_closes_the_turn_it_stopped_in(self, env) -> None:
        pipeline = Pipeline([self._node()], budget=_budget())
        client = self._client()
        with pytest.raises(RunSuspended):
            pipeline.run(
                {"question": "hello"}, envelope=env, model=client, run_id="s1", conversation_id="c1"
            )
        thread = env.conversations.thread("c1")
        assert thread.turn_count == 1 and [t.outcome for t in thread.turns()] == [None]

        pipeline.resume("s1", envelope=env, model=client, answer="the second")

        assert thread.turn_count == 1, "one turn, not two"
        assert [t.outcome for t in thread.turns()] == ["finish"]
        assert [m["role"] for m in thread.messages()] == [
            "user",
            "assistant",
            "tool",
            "assistant",
        ], "what the agent did while answering is part of the conversation"

    def test_a_later_turn_builds_on_the_resumed_one(self, env) -> None:
        from simple_agents.models import ToolCallRequest

        pipeline = Pipeline([self._node()], budget=_budget())
        client = self._client()
        with pytest.raises(RunSuspended):
            pipeline.run(
                {"question": "hello"}, envelope=env, model=client, run_id="s1", conversation_id="c1"
            )
        pipeline.resume("s1", envelope=env, model=client, answer="the second")
        pipeline.run(
            {"question": "next"},
            envelope=env,
            run_id="s2",
            conversation_id="c1",
            model=FakeModelClient(
                responses=[
                    fake_response(
                        content="",
                        tool_calls=[
                            ToolCallRequest(id="c3", name="finish", arguments={"answer": "y"})
                        ],
                    )
                ]
            ),
        )

        assert env.conversations.thread("c1").turn_count == 2
        assert len(env.conversations.thread("c1").messages()) == 6


class TestWhichConversationARunIsATurnOf:
    """The keyword is `conversation_id`, and a manifest written before that still resumes."""

    def test_the_old_keyword_is_gone(self, env) -> None:
        """A bare `thread=` read as the thread the run executes on, beside `concurrency=`."""
        with pytest.raises(TypeError):
            _pipeline().run({"question": "q"}, envelope=env, model=_client(), thread="chat-1")

    def test_a_manifest_written_before_the_rename_resumes_into_its_conversation(
        self, tmp_path
    ) -> None:
        """`conversation.thread` is what `0.36` called `id`, and resume reads both."""
        from simple_agents.records.manifest import Manifest
        from simple_agents.pipeline.core import _restored_conversation

        envelope = RunEnvelope(
            run_dir=tmp_path / "runs", conversations=ConversationStore(tmp_path / "c")
        )
        base = {
            "run_id": "r1",
            "started_at": "2026-08-28T00:00:00Z",
            "seed": 1,
            "budget": {},
            "library_version": "0",
            "paths": {"trajectory": "t", "workspace": "w"},
        }

        for key in ("id", "thread"):
            manifest = Manifest.restore(
                {**base, "conversation": {"directory": "c", key: "chat-1", "turn": 2}}
            )
            assert _restored_conversation(envelope, manifest).conversation_id == "chat-1"

        no_key = Manifest.restore({**base, "conversation": {"directory": "c", "turn": 2}})
        assert _restored_conversation(envelope, no_key) is None

    def test_a_store_written_before_the_rename_still_reads_its_conversations(
        self, tmp_path
    ) -> None:
        """Only the header key moved, so the messages under it are read as they were."""
        store = ConversationStore(tmp_path / "c")
        thread = store.thread("chat-1")
        thread.add([{"role": "user", "content": "hello"}], turn=1)
        path = next((tmp_path / "c").glob("*.jsonl"))
        lines = path.read_text(encoding="utf-8").splitlines()
        head = json.loads(lines[0])
        path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "record": "thread",
                            "format_version": "0.1",
                            "thread": head["conversation_id"],
                            "started_at": head["started_at"],
                        }
                    )
                ]
                + lines[1:]
            )
            + "\n",
            encoding="utf-8",
        )

        reopened = ConversationStore(tmp_path / "c")
        assert [m["content"] for m in reopened.thread("chat-1").messages()] == ["hello"]
        assert reopened.conversation_ids() == []
