"""Who answered a consultation, and what a run does when no answer is possible.

Dogfood #4 ran 104 consultations and 97 of them read `answered`. Every one went to a channel
returning a fixed string, and nothing in a trajectory, a manifest or a results file said so, so
two days of measurements read as an agent measured against its readers.

These cover the two halves of that: a channel declaring who it reaches, recorded on every
consultation and on the manifest entry, and `Unavailable` for a run with nobody at the other end,
which is a different event from an end user who declined.
"""

from __future__ import annotations

import json

import pytest

from simple_agents import (
    AgentNode,
    Budget,
    Deterministic,
    FakeModelClient,
    Pipeline,
    RunEnvelope,
    ToolRegistry,
    read_trajectory,
)
from simple_agents.builtins import (
    ModelAnswer,
    Reply,
    Unavailable,
    ask_on_stdin,
    consult,
    on_reply,
    unattended,
)
from simple_agents import RunSuspended, Suspend
from simple_agents.errors import CallerFacingError, ConfigurationError
from simple_agents.models import ToolCallRequest, fake_response

from conftest import RUN_ID
from schemas import Answer


def _prompt(inputs, ctx):
    return "go"


def _ask(name: str, question: str = "Which fit?", options=None) -> ToolCallRequest:
    arguments = {"question": question}
    if options is not None:
        arguments["options"] = options
    return ToolCallRequest(id=f"c_{name}", name=name, arguments=arguments)


def _finish() -> ToolCallRequest:
    return ToolCallRequest(id="f", name="finish", arguments={"answer": "done", "source": None})


def _consulting_pipeline(channel, **kwargs) -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                _prompt,
                tools=ToolRegistry([consult(channel, **kwargs)]),
                output_schema=Answer,
                budget=Budget(max_steps=6, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
                node_id="hunt",
            )
        ],
        budget=Budget(max_steps=6, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
    )


def _consultations(result) -> list[dict]:
    return [
        r for r in read_trajectory(result.paths.trajectory) if r["record_type"] == "consultation"
    ]


# -----------------------------------------------------------------------------------------
# A channel says who answers
# -----------------------------------------------------------------------------------------


class TestDeclaringWhoAnswers:
    def test_a_channel_with_no_declaration_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            consult(lambda q, o, a=None: "slim")

        assert "no answered_by" in str(exc.value)
        assert "answered_by='end_user'" in str(exc.value)

    def test_the_refusal_names_the_case_the_field_exists_for(self):
        """A fixed string and a person both record `answered`, which is the whole finding."""
        with pytest.raises(ConfigurationError) as exc:
            consult(lambda q, o, a=None: "slim")

        assert "fixed string" in str(exc.value)

    def test_a_value_outside_the_set_is_refused_and_the_set_is_named(self):
        with pytest.raises(ConfigurationError) as exc:
            consult(lambda q, o, a=None: "slim", answered_by="the_user")

        assert "'the_user'" in str(exc.value)
        assert "end_user" in str(exc.value) and "canned" in str(exc.value)

    def test_a_shipped_channel_declares_its_own(self):
        assert consult(unattended()).answered_by == "nobody"

    def test_ask_on_stdin_does_not_declare_one(self):
        """A terminal is the builder's while building and the end user's once it ships."""
        with pytest.raises(ConfigurationError):
            consult(ask_on_stdin)

        assert consult(ask_on_stdin, answered_by="builder").answered_by == "builder"

    def test_a_coding_agent_answering_needs_the_builders_permission(self):
        with pytest.raises(ConfigurationError) as exc:
            consult(lambda q, o, a=None: "slim", answered_by="coding_agent")

        assert "no permission" in str(exc.value)
        assert "unattended()" in str(exc.value)

    def test_the_permission_is_kept_on_the_tool(self):
        tool = consult(
            lambda q, o, a=None: "slim", answered_by="coding_agent", permission="agreed 2026-08-15"
        )

        assert tool.permission == "agreed 2026-08-15"

    def test_permission_is_not_asked_for_from_any_other_answerer(self):
        assert consult(lambda q, o, a=None: "slim", answered_by="canned").permission is None


class TestWhatTheRecordsSay:
    @pytest.fixture
    def result(self, tmp_path):
        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_ask("consult")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        return _consulting_pipeline(lambda q, o, a=None: "slim", answered_by="canned").run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client, run_id=RUN_ID
        )

    def test_the_consultation_says_who_answered(self, result):
        [consultation] = _consultations(result)

        assert consultation["resolution"] == "answered"
        assert consultation["answered_by"] == "canned"

    def test_a_person_answered_nothing_so_no_model_is_recorded(self, result):
        [consultation] = _consultations(result)

        assert consultation["answered_by_model"] is None
        assert consultation["reason"] is None

    def test_the_manifest_entry_says_it_too(self, result):
        manifest = json.loads(result.paths.manifest.read_text())
        [tool] = [t for t in manifest["tools"] if t["name"] == "consult"]

        assert tool["answered_by"] == "canned"
        assert tool["permission"] is None

    def test_an_ordinary_tool_declares_neither(self, result):
        manifest = json.loads(result.paths.manifest.read_text())

        assert all(t["answered_by"] is None for t in manifest["tools"] if t["name"] != "consult")

    def test_the_metrics_count_them_by_answerer(self, result):
        from simple_agents.evaluation.per_node import per_node

        nodes = per_node([list(read_trajectory(result.paths.trajectory))])

        assert nodes["hunt"].consultation_answered_by == {"canned": 1}
        assert nodes["hunt"].consultation_resolutions == {"answered": 1}


# -----------------------------------------------------------------------------------------
# Nobody to ask
# -----------------------------------------------------------------------------------------


class TestUnavailable:
    def test_a_reason_is_required(self):
        with pytest.raises(ConfigurationError) as exc:
            Unavailable(reason="")

        assert "no reason" in str(exc.value)

    def test_it_reads_to_the_model_as_an_instruction_to_stop(self):
        text = str(Unavailable(reason="the desk is closed"))

        assert "the desk is closed" in text
        assert "Do not ask again" in text

    def test_it_survives_the_cassette_as_itself_rather_than_as_its_text(self):
        """A replay that read it back as a string would record `answered`."""
        stored = Unavailable(reason="the desk is closed").to_json()

        assert json.loads(json.dumps(stored)) == stored
        assert Unavailable.stored_in(stored)
        assert Unavailable.from_json(stored).reason == "the desk is closed"

    def test_a_channel_that_returns_it_records_unavailable_with_the_reason(self, tmp_path):
        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_ask("consult")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        result = _consulting_pipeline(unattended("the run is unattended")).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client, run_id=RUN_ID
        )
        [consultation] = _consultations(result)

        assert consultation["resolution"] == "unavailable"
        assert consultation["reason"] == "the run is unattended"
        assert consultation["response"] is None
        assert consultation["answered_by"] == "nobody"

    def test_a_second_question_is_answered_without_reaching_the_channel(self, tmp_path):
        asked = []

        def channel(question, options, about=None):
            asked.append(question)
            return Unavailable(reason="the run is unattended")

        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_ask("consult", "Which fit?")]),
                fake_response(tool_calls=[_ask("consult", "Which colour?")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        result = _consulting_pipeline(channel, answered_by="end_user").run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client, run_id=RUN_ID
        )

        assert asked == ["Which fit?"]
        assert [c["resolution"] for c in _consultations(result)] == [
            "unavailable",
            "unavailable",
        ]

    def test_both_questions_are_still_recorded(self, tmp_path):
        """How many times a run tried to reach someone who was not there is the figure."""
        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_ask("consult", "Which fit?")]),
                fake_response(tool_calls=[_ask("consult", "Which colour?")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        result = _consulting_pipeline(unattended()).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client, run_id=RUN_ID
        )

        assert [c["prompt"] for c in _consultations(result)] == [
            "Which fit?",
            "Which colour?",
        ]

    def test_the_run_completes_rather_than_failing(self, tmp_path):
        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_ask("consult")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        result = _consulting_pipeline(unattended()).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client, run_id=RUN_ID
        )

        assert result.output.answer == "done"


class TestAReplayRecordsWhatTheLiveRunDid:
    """The defect class `ConsultTool.read_answer` exists to prevent, over the new resolution."""

    def _run(self, tmp_path, cassette, asked):
        def channel(question, options, about=None):
            asked.append(question)
            return Unavailable(reason="the run is unattended")

        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_ask("consult", "Which fit?")]),
                fake_response(tool_calls=[_ask("consult", "Which colour?")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        return _consulting_pipeline(channel, answered_by="end_user").run(
            {},
            envelope=RunEnvelope(run_dir=tmp_path, cassette=cassette),
            model=client,
            run_id=RUN_ID,
        )

    def test_a_replayed_run_is_unavailable_where_the_live_one_was(self, tmp_path):
        from simple_agents import Cassette

        path = tmp_path / "recorded.jsonl"
        live = []
        recorded = self._run(tmp_path / "live", Cassette.record(path), live)
        replay = []
        replayed = self._run(tmp_path / "replay", Cassette.replay(path), replay)

        def shape(result):
            return [
                (r["resolution"], r["answered_by"], r["reason"], r["response"])
                for r in _consultations(result)
            ]

        assert shape(recorded) == shape(replayed)
        assert shape(replayed)[0][0] == "unavailable"

    def test_the_replay_never_reaches_the_channel(self, tmp_path):
        from simple_agents import Cassette

        path = tmp_path / "recorded.jsonl"
        live = []
        self._run(tmp_path / "live", Cassette.record(path), live)
        replay = []
        self._run(tmp_path / "replay", Cassette.replay(path), replay)

        assert live == ["Which fit?"]
        assert replay == []


class TestRoutingOnUnavailable:
    def test_it_takes_its_own_branch(self):
        route = on_reply(
            {"slim": "apply"},
            unmatched="amend",
            declined="stop",
            unavailable="proceed",
            shelved="proceed",
        )

        assert route(Unavailable(reason="the run is unattended"), None) == "proceed"

    def test_declining_and_being_unavailable_go_where_each_was_sent(self):
        """Someone who will not answer has made a choice; nobody at all has made none."""
        route = on_reply(
            {"slim": "apply"},
            unmatched="amend",
            declined="stop",
            unavailable="proceed",
            shelved="proceed",
        )

        assert route(None, None) == "stop"
        assert route(Unavailable(reason="the run is unattended"), None) == "proceed"

    def test_under_exhaustive_it_ends_the_run_naming_the_reason(self):
        route = on_reply({"slim": "apply"}, exhaustive=True)

        with pytest.raises(CallerFacingError) as exc:
            route(Unavailable(reason="the desk is closed"), None)

        assert "the desk is closed" in str(exc.value)
        assert "unavailable=" in str(exc.value)


# -----------------------------------------------------------------------------------------
# The run says who answers, without the pipeline being rebuilt
# -----------------------------------------------------------------------------------------


class TestTheEnvelopeSaysWhoAnswers:
    def _run(self, envelope, tmp_path):
        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_ask("consult")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        return _consulting_pipeline(lambda q, o, a=None: "slim", answered_by="end_user").run(
            {}, envelope=envelope, model=client, run_id=RUN_ID
        )

    def test_the_registered_channel_answers_by_default(self, tmp_path):
        result = self._run(RunEnvelope(run_dir=tmp_path), tmp_path)
        [consultation] = _consultations(result)

        assert consultation["response"] == "slim"
        assert consultation["answered_by"] == "end_user"

    def test_the_envelope_replaces_it_for_one_run(self, tmp_path):
        result = self._run(RunEnvelope(run_dir=tmp_path).with_end_user(unattended()), tmp_path)
        [consultation] = _consultations(result)

        assert consultation["resolution"] == "unavailable"
        assert consultation["answered_by"] == "nobody"

    def test_the_record_says_who_actually_answered(self, tmp_path):
        """The manifest keeps the declaration; the trajectory says what this run did."""
        result = self._run(RunEnvelope(run_dir=tmp_path).with_end_user(unattended()), tmp_path)
        manifest = json.loads(result.paths.manifest.read_text())
        [tool] = [t for t in manifest["tools"] if t["name"] == "consult"]

        assert tool["answered_by"] == "end_user"
        assert _consultations(result)[0]["answered_by"] == "nobody"

    def test_the_manifest_names_the_channel_this_run_was_given(self, tmp_path):
        """A live run that asked nothing would otherwise look like the registered channel.

        FT-31 reads it, so a project swapping the channel per run has to be readable without a
        consultation having happened to be recorded.
        """
        result = self._run(RunEnvelope(run_dir=tmp_path).with_end_user(unattended()), tmp_path)
        manifest = json.loads(result.paths.manifest.read_text())

        assert manifest["end_user"] == {"answered_by": "nobody"}

    def test_a_run_using_the_registered_channel_names_none(self, tmp_path):
        result = self._run(RunEnvelope(run_dir=tmp_path), tmp_path)

        assert json.loads(result.paths.manifest.read_text())["end_user"] is None

    def test_a_copy_carries_everything_else_over(self, tmp_path):
        env = RunEnvelope(run_dir=tmp_path, role="labelling")

        assert env.with_end_user(unattended()).role == "labelling"
        assert env.with_role("agent").end_user is None


class TestASuspendedQuestionAndItsAnswer:
    """Two records for one question, so they have to name the same answerer."""

    def _pipeline(self, channel):
        def ask(inputs, ctx):
            return ctx.call_tool("consult", question="Which fit?")

        return Pipeline(
            [
                Deterministic(
                    ask,
                    tools=[consult(channel, answered_by="end_user")],
                    node_id="ask",
                    output_schema=None,
                )
            ],
            budget=Budget(max_steps=2, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )

    def _stopping(self):
        def channel(question, options, about=None):
            raise Suspend(waiting_for=question, options=options)

        return channel

    def test_both_records_name_the_registered_channel(self, tmp_path):
        env = RunEnvelope(run_dir=tmp_path)
        pipeline = self._pipeline(self._stopping())
        with pytest.raises(RunSuspended) as stop:
            pipeline.run({}, envelope=env, run_id=RUN_ID)

        result = self._pipeline(self._stopping()).resume(
            stop.value.run_id, envelope=env, answer="slim"
        )
        records = [
            r
            for r in read_trajectory(result.paths.trajectory)
            if r["record_type"] == "consultation"
        ]

        assert [r["resolution"] for r in records] == ["pending", "answered"]
        assert {r["answered_by"] for r in records} == {"end_user"}

    def test_a_run_that_says_who_it_asks_names_them_on_both(self, tmp_path):
        """The question was recorded against the run's own channel; so is its answer."""
        env = RunEnvelope(run_dir=tmp_path).with_end_user(self._stopping(), answered_by="builder")
        pipeline = self._pipeline(self._stopping())
        with pytest.raises(RunSuspended) as stop:
            pipeline.run({}, envelope=env, run_id=RUN_ID)

        result = self._pipeline(self._stopping()).resume(
            stop.value.run_id, envelope=env, answer="slim"
        )
        records = [
            r
            for r in read_trajectory(result.paths.trajectory)
            if r["record_type"] == "consultation"
        ]

        assert [r["resolution"] for r in records] == ["pending", "answered"]
        assert {r["answered_by"] for r in records} == {"builder"}


class TestAChannelThatReportsItsModel:
    def test_the_model_and_its_cost_land_on_the_record(self, tmp_path):
        def channel(question, options, about=None):
            return ModelAnswer(
                "slim",
                model={"backend": "hosted_api", "request_model": "m", "model_revision": None},
                tokens={"input_uncached": 12, "output": 4},
                cost={"value": 0.0001, "currency": "USD"},
            )

        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_ask("consult")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        result = _consulting_pipeline(channel, answered_by="simulated").run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client, run_id=RUN_ID
        )
        [consultation] = _consultations(result)

        assert consultation["answered_by"] == "simulated"
        assert consultation["response"] == "slim"
        assert consultation["answered_by_model"]["request_model"] == "m"
        assert consultation["answered_by_model"]["cost"]["value"] == 0.0001

    def test_a_derived_cost_is_stored_as_a_figure_rather_than_as_its_repr(self, tmp_path):
        """`Cost` carries no serialiser and holds slots, so an object reaches the file as text."""
        from simple_agents.cost import Cost

        def channel(question, options, about=None):
            return ModelAnswer(
                "slim",
                model={"backend": "hosted_api", "request_model": "m"},
                cost=Cost(value=0.0002, currency="USD", basis="price"),
            )

        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_ask("consult")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        result = _consulting_pipeline(channel, answered_by="simulated").run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client, run_id=RUN_ID
        )
        cost = _consultations(result)[0]["answered_by_model"]["cost"]

        assert cost == {
            "value": 0.0002,
            "currency": "USD",
            "basis": "price",
            "is_upper_bound": False,
            "reason": None,
        }

    def test_its_calls_are_not_the_nodes_own(self, tmp_path):
        """The model playing an end user is not the model under measurement."""

        def channel(question, options, about=None):
            return ModelAnswer("slim", model={"backend": "hosted_api", "request_model": "m"})

        client = FakeModelClient(
            responses=[
                fake_response(tool_calls=[_ask("consult")]),
                fake_response(tool_calls=[_finish()]),
            ]
        )
        result = _consulting_pipeline(channel, answered_by="simulated").run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client, run_id=RUN_ID
        )
        calls = [
            r for r in read_trajectory(result.paths.trajectory) if r["record_type"] == "model_call"
        ]

        assert [c["request_model"] for c in calls] == ["test/model", "test/model"]

    def test_two_overlapping_consultations_do_not_share_their_provenance(self):
        """The tool is bound per call, so one answer's model cannot land on another's."""
        tool = consult(
            lambda q, o, a=None: ModelAnswer("slim", model={"request_model": q}),
            answered_by="simulated",
        )
        first = tool.for_one_call(None)
        second = tool.for_one_call(None)
        first.fn("a")
        second.fn("b")

        assert first.provenance["model"] == {"request_model": "a"}
        assert second.provenance["model"] == {"request_model": "b"}
        assert tool.provenance is None


class TestTheAnswerStillReadsTheSameWayTwice:
    """`read_answer` runs from the channel, from a resume and from the cassette."""

    def test_an_unavailable_read_back_from_a_cassette_is_unavailable_again(self):
        tool = consult(unattended("the run is unattended"))
        stored = tool.for_one_call(None).fn("Which fit?")

        assert isinstance(tool.read_answer(stored, None), Unavailable)
        assert tool.resolve(tool.read_answer(stored, None), failed=False) == "unavailable"

    def test_an_answer_read_back_from_a_cassette_keeps_which_option_it_was(self):
        tool = consult(lambda q, o, a=None: "Slim.", answered_by="end_user")
        stored = tool.for_one_call(None).fn("Which fit?", ["slim", "regular"])

        again = tool.read_answer(str(stored), ["slim", "regular"])
        assert isinstance(again, Reply)
        assert again.chose == "slim"

    def test_reading_it_a_third_time_gives_the_same_answer(self):
        tool = consult(lambda q, o, a=None: "Slim.", answered_by="end_user")
        once = tool.read_answer("Slim.", ["slim"])

        assert tool.read_answer(once, ["slim"]).chose == "slim"


class TestADeterministicNodeAsking:
    def test_it_gets_the_unavailable_back_and_can_route_on_it(self, tmp_path):
        def ask(inputs, ctx):
            return ctx.call_tool("consult", question="Which fit?")

        pipeline = Pipeline(
            [
                Deterministic(
                    ask,
                    tools=[consult(unattended("the run is unattended"))],
                    node_id="ask",
                    successors=["apply", "proceed"],
                    route=on_reply(
                        {"slim": "apply"},
                        unmatched="proceed",
                        declined="proceed",
                        unavailable="proceed",
                        shelved="proceed",
                    ),
                ),
                Deterministic(lambda inputs, ctx: {"answer": "chosen"}, node_id="apply"),
                Deterministic(lambda inputs, ctx: {"answer": "done"}, node_id="proceed"),
            ],
            budget=Budget(max_steps=2, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)

        assert result.output == {"answer": "done"}
        assert _consultations(result)[0]["resolution"] == "unavailable"
