"""Reading what an end user said into the option they meant, with a model.

Whole-answer equality read an option out of **0 of 24** answers written by `SimulatedEndUser`,
so every consultation routed to `unmatched` and the branches under `chose` were never taken.
No rule over the text alone reads the three kinds that defeat it: a negation, an option's word
used as a determiner, and a condition.

`consult(read=...)` is the rule that reads them. These cover what the reading is worth only if
it is recorded, priced and replayable, so most of them are about where the call lands rather
than about what it returns.
"""

from __future__ import annotations

import json
import time

import pytest

from simple_agents import (
    AgentNode,
    Budget,
    Cassette,
    Deterministic,
    FakeModelClient,
    ModelHandle,
    Pipeline,
    Reading,
    RunEnvelope,
    ToolRegistry,
    read_trajectory,
)
from simple_agents.builtins import (
    DEFAULT_READING_INSTRUCTIONS,
    ModelReader,
    consult,
    on_reply,
    unattended,
)
from simple_agents.errors import CallerFacingError, ConfigurationError
from simple_agents.models import ToolCallRequest, fake_response

from conftest import run_path, RUN_ID
from test_run_envelope import read_manifest
from schemas import Answer

BUDGET = Budget(max_steps=8, max_tokens=None, max_cost=None, max_wall_clock_ms=None)

CONDITION = "Only if it is under 400 pages; otherwise, no."
OPTIONS = ["yes", "no"]


def _verdict(chose: str | None, reason: str = "because") -> str:
    return json.dumps({"chose": chose, "reason": reason})


def _reader(*verdicts: str) -> FakeModelClient:
    return FakeModelClient(responses=[fake_response(content=v) for v in verdicts])


def _channel(said: str = CONDITION, asked: list[str] | None = None):
    def ask(question, options, about=None):
        if asked is not None:
            asked.append(question)
        return said

    ask.answered_by = "end_user"
    ask.may_suspend = False
    return ask


def _asking_node(tool, node_id="ask", question="Ship it?", options=OPTIONS):
    def ask_them(inputs, ctx):
        reply = ctx.call_tool("consult", question=question, options=options)
        return {"chose": getattr(reply, "chose", None), "text": str(reply)}

    return Deterministic(ask_them, node_id=node_id, tools=[tool], output_schema=dict)


def _run(tool, tmp_path, *, node=None, cassette=None, run_dir=None, model=None, **kwargs):
    pipeline = Pipeline([node or _asking_node(tool, **kwargs)], budget=BUDGET)
    envelope = RunEnvelope(run_dir=run_dir or tmp_path)
    if cassette is not None:
        envelope = envelope.with_cassette(cassette)
    return pipeline.run(
        {},
        envelope=envelope,
        run_id=RUN_ID,
        seed=41,
        model=model or FakeModelClient(responses=[]),
    )


def _records(result, kind):
    return [r for r in read_trajectory(result.paths.trajectory) if r["record_type"] == kind]


# -----------------------------------------------------------------------------------------
# What the reading decides
# -----------------------------------------------------------------------------------------


class TestWhatTheReadingDecides:
    def test_a_condition_the_default_rule_cannot_read_is_read_as_none_of_them(self, tmp_path):
        """The measured case: an answer stating terms is `unmatched`, not a choice."""
        tool = consult(
            _channel(),
            answered_by="end_user",
            read=ModelReader(
                model=_reader(_verdict(None, "states a page limit rather than choosing"))
            ),
        )

        result = _run(tool, tmp_path)

        assert result.output["chose"] is None
        assert _records(result, "consultation")[0]["resolution"] == "unmatched"

    def test_the_reading_decides_the_option_where_the_default_rule_reads_nothing(self, tmp_path):
        """Without the reader this same answer routes to `unmatched`, which is the finding."""
        answer = "I have no strong feeling either way, go ahead."
        read = _run(
            consult(
                _channel(answer),
                answered_by="end_user",
                read=ModelReader(model=_reader(_verdict("yes"))),
            ),
            tmp_path,
        )
        unread = _run(
            consult(_channel(answer), answered_by="end_user"),
            tmp_path / "no-reader",
            run_dir=tmp_path / "no-reader",
        )

        assert read.output["chose"] == "yes"
        assert unread.output["chose"] is None

    def test_the_answer_itself_is_unchanged_by_the_reading(self, tmp_path):
        """`Reply` is the text the end user typed; the reading only decides `chose`."""
        result = _run(
            consult(
                _channel(), answered_by="end_user", read=ModelReader(model=_reader(_verdict("no")))
            ),
            tmp_path,
        )

        assert result.output["text"] == CONDITION

    @pytest.mark.parametrize(
        "verdict, taken", [("yes", ["apply"]), ("no", ["stop"]), (None, ["amend"])]
    )
    def test_a_reading_routes_the_run(self, tmp_path, verdict, taken):
        """`on_reply` branches on `chose`, so the reading is what picks the successor."""

        def ask_them(inputs, ctx):
            return ctx.call_tool("consult", question="Ship it?", options=OPTIONS)

        tool = consult(
            _channel(), answered_by="end_user", read=ModelReader(model=_reader(_verdict(verdict)))
        )
        pipeline = Pipeline(
            [
                Deterministic(
                    ask_them,
                    node_id="ask",
                    tools=[tool],
                    successors=["apply", "stop", "amend"],
                    route=on_reply(
                        {"yes": "apply", "no": "stop"},
                        unmatched="amend",
                        declined="stop",
                        unavailable="stop",
                        shelved="stop",
                    ),
                ),
                Deterministic(lambda i, c: "applied", node_id="apply"),
                Deterministic(lambda i, c: "stopped", node_id="stop"),
                Deterministic(lambda i, c: "amended", node_id="amend"),
            ],
            budget=BUDGET,
        )

        result = pipeline.run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path),
            run_id=RUN_ID,
            model=FakeModelClient(responses=[]),
        )

        asked = [r for r in _records(result, "node_execution") if r["node_id"] == "ask"]
        assert asked[0]["route"] == taken

    def test_a_reader_that_raises_still_records_the_consultation(self, tmp_path):
        """Left alone this reaches the undeclared-tool-failure path, which writes a `tool_call`
        record for an event that was a consultation and names the channel, not the reader."""

        def broken(reading, answer, options):
            raise ValueError("the project's reader blew up")

        with pytest.raises(CallerFacingError) as exc:
            _run(consult(_channel(), answered_by="end_user", read=broken), tmp_path)

        assert "reader registered on 'consult'" in str(exc.value)
        assert "ValueError" in str(exc.value)
        assert CONDITION in str(exc.value)

        records = [
            r
            for r in read_trajectory(run_path(tmp_path, RUN_ID, "trajectory.jsonl"))
            if r["record_type"] in ("consultation", "tool_call")
        ]
        assert [r["record_type"] for r in records] == ["consultation"]
        assert records[0]["response"] == CONDITION
        assert records[0]["resolution"] == "answered"

    def test_a_reader_naming_something_that_is_not_an_option_is_refused(self, tmp_path):
        """It decides a branch, so a value that is no option routes nowhere."""
        with pytest.raises(ConfigurationError) as exc:
            _run(
                consult(
                    _channel(),
                    answered_by="end_user",
                    read=lambda reading, answer, options: "maybe",
                ),
                tmp_path,
            )

        assert "'maybe'" in str(exc.value)
        assert "'yes'" in str(exc.value) and "'no'" in str(exc.value)


# -----------------------------------------------------------------------------------------
# Where the call lands
# -----------------------------------------------------------------------------------------


class TestWhereTheCallLands:
    @pytest.fixture
    def result(self, tmp_path):
        return _run(
            consult(
                _channel(), answered_by="end_user", read=ModelReader(model=_reader(_verdict("no")))
            ),
            tmp_path,
        )

    def test_the_reading_is_a_model_call_parented_to_the_consultation(self, result):
        consultation = _records(result, "consultation")[0]
        calls = _records(result, "model_call")

        assert len(calls) == 1
        assert calls[0]["parent_id"] == consultation["record_id"]

    def test_the_record_says_a_model_read_the_answer(self, result):
        assert _records(result, "consultation")[0]["read_by"] == "model"

    def test_the_reading_is_charged_to_the_run(self, result):
        """A reader ships with the agent, so what it spends is the agent's."""
        assert result.tokens["output"] > 0
        assert result.manifest["counts"]["model_call"] == 1

    def test_the_reading_depletes_the_run_budget(self, tmp_path):
        """One step per reading, taken before the call, like every other model call."""

        def ask_twice(inputs, ctx):
            ctx.call_tool("consult", question="Ship it?", options=OPTIONS)
            ctx.call_tool("consult", question="Ship it now?", options=OPTIONS)
            return "done"

        tool = consult(
            _channel(),
            answered_by="end_user",
            read=ModelReader(model=_reader(_verdict("no"), _verdict("no"))),
        )
        one_step = Budget(max_steps=1, max_tokens=None, max_cost=None, max_wall_clock_ms=None)
        pipeline = Pipeline(
            [Deterministic(ask_twice, node_id="ask", tools=[tool])], budget=one_step
        )

        with pytest.raises(Exception) as exc:
            pipeline.run(
                {},
                envelope=RunEnvelope(run_dir=tmp_path),
                run_id=RUN_ID,
                model=FakeModelClient(responses=[]),
            )

        assert "max_steps" in str(exc.value)

    def test_the_reading_carries_a_seed(self, result):
        """FT-07 reads this field on every record that sampled."""
        assert _records(result, "model_call")[0]["seed"] is not None

    def test_a_rule_read_answer_says_so(self, tmp_path):
        result = _run(consult(_channel("yes"), answered_by="end_user"), tmp_path)

        assert _records(result, "consultation")[0]["read_by"] == "rule"

    def test_a_question_offering_no_options_records_nothing_read_it(self, tmp_path):
        result = _run(
            consult(
                _channel("a sentence"), answered_by="end_user", read=ModelReader(model=_reader())
            ),
            tmp_path,
            options=None,
        )

        assert _records(result, "consultation")[0]["read_by"] is None
        assert _records(result, "model_call") == []

    def test_a_consultation_nobody_answered_reads_nothing(self, tmp_path):
        result = _run(
            consult(unattended(), read=ModelReader(model=_reader())),
            tmp_path,
        )

        assert _records(result, "consultation")[0]["read_by"] is None
        assert _records(result, "model_call") == []


# -----------------------------------------------------------------------------------------
# A deterministic node carries it
# -----------------------------------------------------------------------------------------


class TestInsideAFanOut:
    """A reading belongs to the item whose loop asked the question.

    Without the item, two items' readings share one call counter, so the seed each is sent
    depends on which item asked first and that seed is in the cassette key. Measured at
    `P3-22`'s verification pass, which is where the same defect in a tool's `ModelHandle` was
    found.
    """

    def _fan_out(self, tmp_path, *, hold_back: str) -> list[dict]:
        def ask_about(inputs, ctx):
            if hold_back in inputs["book"]:
                time.sleep(0.2)
            reply = ctx.call_tool("consult", question=f"Ship {inputs['book']}?", options=OPTIONS)
            return {"chose": getattr(reply, "chose", None)}

        node = Deterministic(
            ask_about,
            node_id="ask",
            over="book",
            tools=[
                consult(
                    _channel(),
                    read=ModelReader(model=_reader(*[_verdict("yes")] * 4)),
                )
            ],
            output_schema=dict,
        )
        result = Pipeline([node], budget=BUDGET).run(
            {"book": ["Ubik", "Solaris"]},
            envelope=RunEnvelope(run_dir=tmp_path),
            run_id=RUN_ID,
            seed=41,
            concurrency=2,
        )
        return [
            r for r in read_trajectory(result.paths.trajectory) if r["record_type"] == "model_call"
        ]

    def test_each_reading_names_the_item_that_asked(self, tmp_path) -> None:
        calls = self._fan_out(tmp_path, hold_back="Ubik")

        assert sorted(call["item_index"] for call in calls) == [0, 1]

    def test_its_seed_does_not_depend_on_which_item_asked_first(self, tmp_path) -> None:
        first = {
            c["item_index"]: c["seed"] for c in self._fan_out(tmp_path / "a", hold_back="Ubik")
        }
        second = {
            c["item_index"]: c["seed"] for c in self._fan_out(tmp_path / "b", hold_back="Solaris")
        }

        assert first == second


class TestUnderADeterministicNode:
    def test_the_node_function_is_still_handed_no_model(self, tmp_path):
        seen = []

        def ask_them(inputs, ctx):
            seen.append(ctx)
            return str(ctx.call_tool("consult", question="Ship it?", options=OPTIONS))

        _run(
            consult(
                _channel(), answered_by="end_user", read=ModelReader(model=_reader(_verdict("no")))
            ),
            tmp_path,
            node=Deterministic(
                ask_them,
                node_id="ask",
                tools=[
                    consult(
                        _channel(),
                        answered_by="end_user",
                        read=ModelReader(model=_reader(_verdict("no"))),
                    )
                ],
            ),
        )

        assert not hasattr(seen[0], "model")

    def test_the_node_record_still_says_it_does_not_sample(self, tmp_path):
        """`seed` of null on a `deterministic` node is what FT-07 reads."""
        result = _run(
            consult(
                _channel(), answered_by="end_user", read=ModelReader(model=_reader(_verdict("no")))
            ),
            tmp_path,
        )
        node = _records(result, "node_execution")[0]

        assert node["node_kind"] == "deterministic"
        assert node["seed"] is None

    def test_a_tool_taking_a_model_handle_is_still_refused(self):
        from simple_agents.tools import SideEffectClass, tool as as_tool

        @as_tool(side_effect_class=SideEffectClass.READ_ONLY)
        def reads(model: ModelHandle, text: str) -> str:
            """Read something."""
            return model.complete(text).content or ""

        with pytest.raises(ConfigurationError) as exc:
            Deterministic(lambda i, c: "x", node_id="n", tools=[reads])

        assert "ModelHandle" in str(exc.value)
        assert "consult(read=" in str(exc.value)


# -----------------------------------------------------------------------------------------
# Replay
# -----------------------------------------------------------------------------------------


class TestReplay:
    def test_a_replay_does_not_ask_the_person_again(self, tmp_path):
        asked: list[str] = []
        cassette = tmp_path / "c.jsonl"

        # One tool for both runs: `asked` grows during the recording, and what a channel closed
        # over is in its version, so a second `consult` built after it is a second tool.
        asking = consult(
            _channel(asked=asked),
            answered_by="end_user",
            read=ModelReader(model=_reader(_verdict("no"), _verdict("no"))),
        )

        _run(asking, tmp_path, cassette=Cassette.record(cassette), run_dir=tmp_path / "live")
        live = len(asked)
        _run(asking, tmp_path, cassette=Cassette.replay(cassette), run_dir=tmp_path / "rep")

        assert live == 1
        assert len(asked) == 1

    def test_the_reading_is_served_from_the_cassette(self, tmp_path):
        cassette = tmp_path / "c.jsonl"

        def build():
            return consult(
                _channel(), answered_by="end_user", read=ModelReader(model=_reader(_verdict("no")))
            )

        _run(build(), tmp_path, cassette=Cassette.record(cassette), run_dir=tmp_path / "live")
        # A client with nothing queued: a call that reached it would raise.
        replayed = _run(
            consult(_channel(), answered_by="end_user", read=ModelReader(model=_reader())),
            tmp_path,
            cassette=Cassette.replay(cassette),
            run_dir=tmp_path / "rep",
        )

        call = _records(replayed, "model_call")[0]
        assert call["replayed"] is True
        assert replayed.output["chose"] == "no"

    def test_an_edited_reader_prompt_is_a_miss_on_the_reading(self, tmp_path):
        """The recorded answer is untouched: what changed is the rule that reads it."""
        cassette = tmp_path / "c.jsonl"
        _run(
            consult(
                _channel(), answered_by="end_user", read=ModelReader(model=_reader(_verdict("no")))
            ),
            tmp_path,
            cassette=Cassette.record(cassette),
            run_dir=tmp_path / "live",
        )

        edited = ModelReader(
            model=_reader(_verdict("no")),
            instructions="Which of these did they mean?\n{options}\n\n{answer}",
        )
        with pytest.raises(Exception) as exc:
            _run(
                consult(_channel(), answered_by="end_user", read=edited),
                tmp_path,
                cassette=Cassette.replay(cassette),
                run_dir=tmp_path / "rep",
            )

        assert "No recorded response" in str(exc.value)
        assert "messages" in str(exc.value)

    def test_an_edited_reader_does_not_move_the_consultation_key(self, tmp_path):
        """A reader edit must not invalidate a recorded answer and ask a person again.

        Two readers with different source, so a version that covered them would differ.
        """

        def read_one(reading, answer, options):
            return options[0]

        def read_the_other(reading, answer, options):
            return options[1]

        channel = _channel()
        first = consult(channel, answered_by="end_user", read=read_one)
        second = consult(channel, answered_by="end_user", read=read_the_other)

        from simple_agents.tools import derived_version

        assert derived_version(read_one) != derived_version(read_the_other)
        assert first.version == second.version


# -----------------------------------------------------------------------------------------
# Retry, and a reading that cannot be made
# -----------------------------------------------------------------------------------------


class TestRetry:
    def test_a_reply_naming_no_option_is_stated_back_and_the_second_stands(self, tmp_path):
        reader = _reader(_verdict("maybe"), _verdict("no"))
        result = _run(
            consult(_channel(), answered_by="end_user", read=ModelReader(model=reader, attempts=2)),
            tmp_path,
        )

        assert result.output["chose"] == "no"
        assert len(_records(result, "model_call")) == 2

    def test_the_retry_states_what_was_wrong(self, tmp_path):
        reader = _reader(_verdict("maybe"), _verdict("no"))
        _run(
            consult(_channel(), answered_by="end_user", read=ModelReader(model=reader, attempts=2)),
            tmp_path,
        )

        retried = reader.requests[1].messages[-1]["content"]
        assert "'maybe'" in retried
        assert "- yes" in retried and "- no" in retried

    def test_one_attempt_is_no_retry(self, tmp_path):
        with pytest.raises(CallerFacingError):
            _run(
                consult(
                    _channel(),
                    answered_by="end_user",
                    read=ModelReader(model=_reader(_verdict("maybe")), attempts=1),
                ),
                tmp_path,
            )

    def test_attempts_exhausted_ends_the_run(self, tmp_path):
        with pytest.raises(CallerFacingError) as exc:
            _run(
                consult(
                    _channel(),
                    answered_by="end_user",
                    read=ModelReader(
                        model=_reader(_verdict("maybe"), _verdict("also no")), attempts=2
                    ),
                ),
                tmp_path,
            )

        assert CONDITION in str(exc.value)
        assert "'yes'" in str(exc.value) and "'no'" in str(exc.value)

    def test_the_answer_is_recorded_even_though_the_reading_failed(self, tmp_path):
        """The person answered. Losing that because a reader broke would lose the event."""
        with pytest.raises(CallerFacingError):
            _run(
                consult(
                    _channel(),
                    answered_by="end_user",
                    read=ModelReader(model=_reader(_verdict("maybe")), attempts=1),
                ),
                tmp_path,
            )

        records = [
            r
            for r in read_trajectory(run_path(tmp_path, RUN_ID, "trajectory.jsonl"))
            if r["record_type"] == "consultation"
        ]
        assert records[0]["response"] == CONDITION
        assert records[0]["chose"] is None
        assert records[0]["read_by"] is None
        assert records[0]["error"]["class"] == "caller_facing"

    def test_a_failed_reading_is_not_reported_as_the_end_user_saying_something_off_the_list(
        self, tmp_path
    ):
        """`unmatched` is a claim about the answer. A broken reader is not that claim."""
        with pytest.raises(CallerFacingError):
            _run(
                consult(
                    _channel(),
                    answered_by="end_user",
                    read=ModelReader(model=_reader(_verdict("maybe")), attempts=1),
                ),
                tmp_path,
            )

        records = [
            r
            for r in read_trajectory(run_path(tmp_path, RUN_ID, "trajectory.jsonl"))
            if r["record_type"] == "consultation"
        ]
        assert records[0]["resolution"] == "answered"

    def test_a_reply_that_is_not_json_is_stated_back(self, tmp_path):
        reader = FakeModelClient(
            responses=[
                fake_response(content="I think they meant yes"),
                fake_response(content=_verdict("yes")),
            ]
        )
        result = _run(
            consult(_channel(), answered_by="end_user", read=ModelReader(model=reader, attempts=2)),
            tmp_path,
        )

        assert result.output["chose"] == "yes"
        assert "not the" in reader.requests[1].messages[-1]["content"]

    def test_an_output_ceiling_is_named_rather_than_retried(self, tmp_path):
        """Retrying at the same ceiling fails the same way, so the ceiling is what is said."""
        reader = FakeModelClient(
            responses=[
                fake_response(content='{"chose": "y', finish_reason="length"),
            ]
        )
        with pytest.raises(CallerFacingError) as exc:
            _run(
                consult(
                    _channel(), answered_by="end_user", read=ModelReader(model=reader, attempts=3)
                ),
                tmp_path,
            )

        assert "max_output_tokens" in str(exc.value)
        assert len(reader.requests) == 1


# -----------------------------------------------------------------------------------------
# A reading made in a later process
# -----------------------------------------------------------------------------------------


class TestAResumedRun:
    def test_an_answer_delivered_to_a_resumed_run_is_read_there(self, tmp_path):
        from simple_agents import RunSuspended, Suspend

        def ask_by_email(question, options, about=None):
            raise Suspend(waiting_for=question, options=options)

        ask_by_email.answered_by = "end_user"

        def build():
            tool = consult(
                ask_by_email,
                answered_by="end_user",
                read=ModelReader(model=_reader(_verdict("no"))),
            )
            return Pipeline([_asking_node(tool)], budget=BUDGET)

        envelope = RunEnvelope(run_dir=tmp_path)
        with pytest.raises(RunSuspended):
            build().run({}, envelope=envelope, run_id=RUN_ID, model=FakeModelClient(responses=[]))

        result = build().resume(
            RUN_ID, envelope=envelope, model=FakeModelClient(responses=[]), answer=CONDITION
        )

        assert result.output["chose"] == "no"
        answering = [r for r in _records(result, "consultation") if r["answers"] is not None]
        assert answering[0]["read_by"] == "model"
        calls = _records(result, "model_call")
        assert [c["parent_id"] for c in calls] == [answering[0]["record_id"]]

    def test_replaying_a_resumed_run_neither_suspends_nor_reads_again(self, tmp_path):
        """The answer and the reading were both filed, so the replay needs neither."""
        from simple_agents import RunSuspended, Suspend

        def ask_by_email(question, options, about=None):
            raise Suspend(waiting_for=question, options=options)

        ask_by_email.answered_by = "end_user"

        def build(reader):
            tool = consult(ask_by_email, answered_by="end_user", read=ModelReader(model=reader))
            return Pipeline([_asking_node(tool)], budget=BUDGET)

        cassette = tmp_path / "c.jsonl"
        live = RunEnvelope(run_dir=tmp_path / "live", cassette=Cassette.record(cassette))
        with pytest.raises(RunSuspended):
            build(_reader(_verdict("no"))).run(
                {}, envelope=live, run_id=RUN_ID, model=FakeModelClient(responses=[])
            )
        build(_reader(_verdict("no"))).resume(
            RUN_ID, envelope=live, model=FakeModelClient(responses=[]), answer=CONDITION
        )

        # A reader with nothing queued: a call reaching it would raise.
        replayed = build(_reader()).run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(cassette)),
            run_id=RUN_ID,
            model=FakeModelClient(responses=[]),
        )

        assert replayed.output["chose"] == "no"
        assert replayed.output["text"] == CONDITION
        assert [c["replayed"] for c in _records(replayed, "model_call")] == [True]


class TestUnderAnAgentNode:
    def test_a_consultation_the_model_chose_to_make_is_read_the_same_way(self, tmp_path):
        tool = consult(
            _channel(), answered_by="end_user", read=ModelReader(model=_reader(_verdict("no")))
        )
        agent = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c",
                            name="consult",
                            arguments={"question": "Ship it?", "options": OPTIONS},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="f", name="finish", arguments={"answer": "done", "source": None}
                        )
                    ]
                ),
            ]
        )
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda i, c: "go",
                    tools=ToolRegistry([tool]),
                    output_schema=Answer,
                    budget=BUDGET,
                    node_id="hunt",
                )
            ],
            budget=BUDGET,
        )

        result = pipeline.run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID, seed=41, model=agent
        )

        consultation = _records(result, "consultation")[0]
        assert consultation["chose"] == "no"
        assert consultation["read_by"] == "model"
        reading = [
            m for m in _records(result, "model_call") if m["parent_id"] == consultation["record_id"]
        ]
        assert len(reading) == 1

    def test_the_reading_is_not_counted_as_a_step_the_agent_took(self, tmp_path):
        """The agent's own loop is bounded by its calls, and a reading is not one of them."""
        tool = consult(
            _channel(), answered_by="end_user", read=ModelReader(model=_reader(_verdict("no")))
        )
        agent = FakeModelClient(
            responses=[
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="c",
                            name="consult",
                            arguments={"question": "Ship it?", "options": OPTIONS},
                        )
                    ]
                ),
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="f", name="finish", arguments={"answer": "done", "source": None}
                        )
                    ]
                ),
            ]
        )
        pipeline = Pipeline(
            [
                AgentNode(
                    lambda i, c: "go",
                    tools=ToolRegistry([tool]),
                    output_schema=Answer,
                    budget=BUDGET,
                    node_id="hunt",
                )
            ],
            budget=BUDGET,
        )

        result = pipeline.run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID, seed=41, model=agent
        )

        node = _records(result, "node_execution")[0]
        assert node["termination"] == "finish"
        assert len(agent.requests) == 2


# -----------------------------------------------------------------------------------------
# What the project declares
# -----------------------------------------------------------------------------------------


class TestWhatIsDeclared:
    def test_the_manifest_records_which_model_read_the_answers(self, tmp_path):
        _run(
            consult(
                _channel(), answered_by="end_user", read=ModelReader(model=_reader(_verdict("no")))
            ),
            tmp_path,
        )

        entry = read_manifest(run_path(tmp_path, RUN_ID, "manifest.json"))["tools"][0]
        assert entry["reader"]["kind"] == "model"
        assert entry["reader"]["model"]["request_model"] == "test/model"
        assert entry["reader"]["instructions"].startswith("sha256:")

    def test_a_tool_with_no_reader_records_none(self, tmp_path):
        _run(consult(_channel("yes"), answered_by="end_user"), tmp_path)

        assert (
            read_manifest(run_path(tmp_path, RUN_ID, "manifest.json"))["tools"][0]["reader"] is None
        )

    def test_a_reader_that_cannot_describe_itself_does_not_lose_the_manifest(self, tmp_path):
        """The manifest is written at the end, over a run that has already happened."""

        class Undescribable:
            def identity(self):
                raise RuntimeError("no identity here")

            def __call__(self, reading, answer, options):
                return options[0]

        _run(consult(_channel(), answered_by="end_user", read=Undescribable()), tmp_path)

        entry = read_manifest(run_path(tmp_path, RUN_ID, "manifest.json"))["tools"][0]
        assert entry["reader"]["identity_error"].startswith("RuntimeError")

    def test_a_reader_written_as_a_function_is_recorded_as_its_source(self, tmp_path):
        def pick_the_first(reading, answer, options):
            return options[0]

        _run(consult(_channel(), answered_by="end_user", read=pick_the_first), tmp_path)

        entry = read_manifest(run_path(tmp_path, RUN_ID, "manifest.json"))["tools"][0]
        assert entry["reader"] == {"kind": "function", "version": entry["reader"]["version"]}
        assert entry["reader"]["version"].startswith("sha256:")

    def test_two_rules_for_one_job_are_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            consult(
                _channel(),
                answered_by="end_user",
                match=lambda a, o: None,
                read=ModelReader(model=_reader()),
            )

        assert "match=" in str(exc.value) and "read=" in str(exc.value)

    def test_a_reader_that_is_not_callable_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            consult(_channel(), answered_by="end_user", read="a model")

        assert "ModelReader(model=cheap)" in str(exc.value)


class TestModelReaderRefusals:
    def test_a_client_is_required(self):
        with pytest.raises(ConfigurationError) as exc:
            ModelReader(model="gpt")

        assert "not a ModelClient" in str(exc.value)

    def test_a_prompt_with_nowhere_for_the_answer_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            ModelReader(model=_reader(), instructions="Pick one of {options}.")

        assert "{answer}" in str(exc.value)

    def test_a_prompt_with_nowhere_for_the_options_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            ModelReader(model=_reader(), instructions="They said {answer}.")

        assert "{options}" in str(exc.value)

    def test_a_prompt_that_cannot_be_filled_in_is_refused_where_it_is_written(self):
        """Left to run time it raises after the end user has already been asked."""
        with pytest.raises(ConfigurationError) as exc:
            ModelReader(
                model=_reader(),
                instructions=(
                    'Options:\n{options}\n\nAnswer:\n{answer}\n\nReply like {"chose": "yes"}.'
                ),
            )

        assert "KeyError" in str(exc.value)
        assert "Double any other brace" in str(exc.value)

    def test_the_shipped_prompt_fills_in(self):
        """The refusal above has to not fire on the default."""
        assert ModelReader(model=_reader()).instructions is DEFAULT_READING_INSTRUCTIONS

    def test_attempts_below_one_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            ModelReader(model=_reader(), attempts=0)

        assert "attempts=2" in str(exc.value)

    def test_the_reading_goes_through_the_handle_it_was_given(self, tmp_path):
        """A call made on the client directly is charged to nothing and replayed never."""
        seen: list[object] = []

        def read_it(reading, answer, options):
            seen.append(reading)
            return options[1]

        _run(consult(_channel(), answered_by="end_user", read=read_it), tmp_path)

        assert isinstance(seen[0], Reading)
