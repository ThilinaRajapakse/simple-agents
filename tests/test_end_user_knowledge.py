"""What an example says about who the agent is answering, and what that person knows.

The stand-in answers with what the description carries and nothing else, measured on
2026-08-17 against `gemini-3.1-flash-lite`: a cost centre absent from the description was
supplied in 0 of 5 rollouts and one written into it in 5 of 5. So a value the agent has to
obtain is data on the example rather than something the model can be prompted into inventing,
and `disclose` decides which of those the model is told.
"""

from __future__ import annotations

import json

import pytest

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    FakeModelClient,
    Pipeline,
    RunEnvelope,
    ToolRegistry,
    read_trajectory,
)
from simple_agents.builtins import consult, unattended
from simple_agents.errors import ConfigurationError
from simple_agents.evaluation import (
    DEFAULT_INSTRUCTIONS,
    EndUser,
    EvalSuite,
    Example,
    ExampleSet,
    Fact,
    SimulatedEndUser,
)
from simple_agents.models import (
    ModelIdentity,
    ModelRequest,
    ModelResponse,
    TokenUsage,
    ToolCallRequest,
    fake_response,
)

from schemas import Answer

BUDGET = Budget(max_steps=6, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


class Reader:
    """A stand-in's model: answers as asked, and keeps every request for inspection."""

    def __init__(self, replies=None, chose=None):
        self.replies = list(replies or ["Under 400 pages."])
        self.chose = chose
        self.requests: list[ModelRequest] = []

    def identity(self) -> ModelIdentity:
        return ModelIdentity(backend="hosted_api", request_model="reader-1")

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        reply = self.replies[min(len(self.requests) - 1, len(self.replies) - 1)]
        body: dict = {"reply": reply}
        if request.output_schema and "chose" in request.output_schema["properties"]:
            body["chose"] = self.chose
        return ModelResponse(
            content=json.dumps(body),
            tool_calls=[],
            finish_reason="end_turn",
            backend="hosted_api",
            request_model="reader-1",
            response_model="reader-1",
            model_revision=None,
            tokens=TokenUsage(
                input_uncached=40,
                input_cache_read=0,
                input_cache_write=0,
                cache_ttl=None,
                output=12,
            ),
            concurrent_requests=None,
            reasoning=None,
        )

    @property
    def systems(self) -> list[str]:
        return [str(r.messages[0]["content"]) for r in self.requests]


def _prompt(inputs, ctx):
    return Prompt.user("go")


def _ask(question="Which cost centre?", options=None, call_id="c1", name="consult"):
    arguments = {"question": question}
    if options is not None:
        arguments["options"] = options
    return ToolCallRequest(id=call_id, name=name, arguments=arguments)


def _finish(answer="done"):
    return ToolCallRequest(id="f", name="finish", arguments={"answer": answer, "source": None})


def _pipeline(*tools) -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                _prompt,
                tools=ToolRegistry(list(tools) or [consult(unattended(), name="consult")]),
                output_schema=Answer,
                budget=BUDGET,
                node_id="hunt",
            )
        ],
        budget=BUDGET,
    )


def _suite(pipeline=None, examples=None) -> EvalSuite:
    return EvalSuite(
        pipeline or _pipeline(),
        examples or _examples(),
        answer="answer",
        matches=lambda s: s.answer == s.expected,
    )


def _examples(end_user=None) -> ExampleSet:
    return ExampleSet(
        [
            Example(
                id="q1",
                inputs={},
                expected="done",
                split="held_out",
                end_user=end_user if end_user is not None else "An operations manager.",
            )
        ]
    )


def _agent(calls=None) -> FakeModelClient:
    calls = calls or [_ask()]
    return FakeModelClient(
        responses=[fake_response(tool_calls=[c]) for c in calls]
        + [fake_response(tool_calls=[_finish()])]
    )


class TestWhatTheExampleCarries:
    def test_prose_becomes_an_end_user(self):
        example = Example(
            id="q1", inputs={}, expected="x", split="dev", end_user="An operations manager."
        )
        assert example.end_user == EndUser("An operations manager.")

    def test_prose_still_stores_as_prose(self):
        """An example set written before `knows` existed hashes to what it always did."""
        example = Example(
            id="q1", inputs={}, expected="x", split="dev", end_user="An operations manager."
        )
        assert example.to_json()["end_user"] == "An operations manager."

    def test_facts_round_trip_through_the_file(self, tmp_path):
        person = EndUser(
            "An operations manager.",
            knows={
                "cc": Fact("the cost centre is CC-4471", value="CC-4471"),
                "cap": Fact("over 5000 needs her director", value=5000, disclose="hidden"),
            },
        )
        path = tmp_path / "examples.jsonl"
        _examples(person).to_jsonl(path)

        [read] = list(ExampleSet.from_jsonl(path))
        assert read.end_user == person
        assert read.end_user.knows["cap"].value == 5000

    def test_a_fact_is_part_of_what_the_examples_hash_to(self):
        """Widening what the end user knows is a change to the example set."""
        one = _examples(EndUser("A manager.", knows={"cc": Fact("it is CC-4471")}))
        two = _examples(EndUser("A manager.", knows={"cc": Fact("it is CC-9000")}))
        assert one.content_hash() != two.content_hash()

    def test_bare_text_is_a_fact_with_the_default_disclosure(self):
        person = EndUser("A manager.", knows={"cc": "the cost centre is CC-4471"})
        assert person.knows["cc"] == Fact("the cost centre is CC-4471", disclose="on_ask")

    def test_a_fact_written_as_something_else_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            EndUser("A manager.", knows={"cc": 4471})
        assert "where a fact was expected" in str(exc.value)

    def test_an_end_user_with_no_description_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            EndUser("   ")
        assert "FT-24" in str(exc.value)

    def test_answerers_round_trip_by_name(self, tmp_path):
        example = Example(
            id="q1",
            inputs={},
            expected="x",
            split="dev",
            end_user={
                "requester": "A junior analyst.",
                "approver": EndUser("Her director.", knows={"cap": Fact("5000 cap")}),
            },
        )
        rebuilt = Example.from_json(example.to_json())
        assert rebuilt.end_user["requester"] == EndUser("A junior analyst.")
        assert rebuilt.end_user["approver"].knows["cap"].text == "5000 cap"


class TestWhatTheModelIsTold:
    def _played(self, person, question="Which cost centre?", options=None):
        reader = Reader()
        channel = SimulatedEndUser(model=reader).playing(person, seed=41)
        channel(question, options)
        return reader

    def test_a_volunteered_fact_is_in_the_prompt(self):
        reader = self._played(
            EndUser("A manager.", knows={"d": Fact("this is due today", disclose="volunteer")})
        )
        assert "this is due today" in reader.systems[0]
        assert "without being asked" in reader.systems[0]

    def test_an_on_ask_fact_is_in_the_prompt_with_its_condition(self):
        reader = self._played(
            EndUser("A manager.", knows={"cc": Fact("the cost centre is CC-4471")})
        )
        assert "the cost centre is CC-4471" in reader.systems[0]
        assert "only when the agent asks" in reader.systems[0]

    def test_a_hidden_fact_never_reaches_the_model(self):
        """The barrier is that the model is never given it, rather than told to withhold it."""
        reader = self._played(
            EndUser(
                "A manager.", knows={"cap": Fact("over 5000 needs her director", disclose="hidden")}
            )
        )
        assert "5000" not in reader.systems[0]
        assert "director" not in reader.systems[0]

    def test_a_hidden_fact_is_still_on_the_example_for_a_scoring_rule(self):
        person = EndUser("A manager.", knows={"cap": Fact("cap", value=5000, disclose="hidden")})
        assert person.hidden["cap"].value == 5000


class TestWhatItRemembers:
    def test_the_first_question_carries_no_history_and_no_rule(self):
        reader = Reader()
        channel = SimulatedEndUser(model=reader).playing(EndUser("A manager."), seed=41)
        channel("How much?", None)

        assert len(reader.requests[0].messages) == 2
        assert "whole record of it" not in reader.systems[0]

    def test_a_later_question_carries_what_was_already_said(self):
        reader = Reader(replies=["Under fifty pounds.", "No."])
        channel = SimulatedEndUser(model=reader).playing(EndUser("A manager."), seed=41)
        channel("How much?", None)
        channel("Shall I order the 45 pound one?", None)

        second = reader.requests[1].messages
        assert any(m["role"] == "assistant" and "fifty" in m["content"] for m in second)
        assert "whole record of it" in reader.systems[1]

    def test_a_refusal_is_not_added_to_the_record(self):
        """Nothing was said, so there is nothing for a later answer to be consistent with."""
        reader = Reader(replies=[None, "Fine."])
        channel = SimulatedEndUser(model=reader).playing(EndUser("A manager."), seed=41)
        channel("How much?", None)
        channel("Shall I proceed?", None)

        assert len(reader.requests[1].messages) == 2

    def test_the_seed_comes_from_the_question_rather_than_the_order(self):
        """Two live runs at one seed answer the same question the same way, whatever the
        order the questions arrived in."""
        first = Reader()
        SimulatedEndUser(model=first).playing(EndUser("A manager."), seed=41)("B?", None)

        second = Reader()
        channel = SimulatedEndUser(model=second).playing(EndUser("A manager."), seed=41)
        channel("A?", None)
        channel("B?", None)

        assert second.requests[1].seed == first.requests[0].seed
        assert second.requests[0].seed != second.requests[1].seed


class TestThePromptSeam:
    def test_the_project_can_replace_the_instructions(self):
        reader = Reader()
        stand_in = SimulatedEndUser(
            model=reader,
            instructions="Reply as the system below.\n\nThe system:\n{end_user}\n\n",
        )
        stand_in.playing(EndUser("A billing API."), seed=41)("Value?", None)

        assert reader.systems[0].startswith("Reply as the system below.")
        assert "A billing API." in reader.systems[0]

    def test_the_format_is_appended_whatever_the_prompt_says(self):
        reader = Reader()
        SimulatedEndUser(model=reader, instructions="Be {end_user}.").playing(
            EndUser("terse"), seed=41
        )("Value?", None)

        assert '"reply"' in reader.systems[0]

    def test_instructions_without_the_placeholder_are_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            SimulatedEndUser(model=Reader(), instructions="Reply as a busy manager.")
        assert "{end_user}" in str(exc.value)

    def test_the_prompt_is_part_of_the_evaluations_identity(self):
        """Two evaluations differing only in it resolve to different directories."""
        default = SimulatedEndUser(model=Reader()).identity()
        other = SimulatedEndUser(
            model=Reader(), instructions=DEFAULT_INSTRUCTIONS + " Be terse."
        ).identity()
        assert default["instructions"] != other["instructions"]


class TestWhatTheRecordSays:
    def _run(self, tmp_path, options=None, chose=None, examples=None):
        reader = Reader(replies=["Just get The Will of the Many."], chose=chose)
        suite = _suite(examples=examples)
        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=_agent([_ask(options=options)]),
            split="held_out",
            k=1,
            seed=41,
            end_user=SimulatedEndUser(model=reader),
        )
        [rollout] = results.rollouts
        consulted = [
            r for r in read_trajectory(rollout.trajectory) if r["record_type"] == "consultation"
        ]
        return results, consulted

    def test_the_declared_choice_is_recorded_beside_what_the_rule_read(self, tmp_path):
        options = ["Crossroads of Ravens", "The Will of the Many"]
        _, [record] = self._run(tmp_path, options=options, chose="The Will of the Many")

        assert record["declared_choice"] == "The Will of the Many"
        assert record["chose"] is None

    def test_a_rule_that_read_a_different_answer_is_counted(self, tmp_path):
        """Whole-answer equality reads no option out of prose, and the count says so."""
        options = ["Crossroads of Ravens", "The Will of the Many"]
        results, _ = self._run(tmp_path, options=options, chose="The Will of the Many")

        assert results.nodes["hunt"].consultation_misreadings == 1

    def test_an_agreeing_rule_is_not_counted(self, tmp_path):
        results, [record] = self._run(
            tmp_path,
            options=["Just get The Will of the Many."],
            chose="Just get The Will of the Many.",
        )
        assert record["chose"] == record["declared_choice"]
        assert results.nodes["hunt"].consultation_misreadings == 0

    def test_a_channel_that_says_nothing_declares_nothing(self, tmp_path):
        _, [record] = self._run(tmp_path, options=None)
        assert record["declared_choice"] is None


class TestQuestionsNobodyAnswered:
    def test_a_rollout_counts_the_questions_that_got_nothing_back(self, tmp_path):
        suite = _suite()
        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path).with_end_user(unattended()),
            model=_agent(),
            split="held_out",
            k=1,
            seed=41,
        )
        [rollout] = results.rollouts
        assert rollout.unanswered_consultations == 1

    def test_an_answered_rollout_counts_none(self, tmp_path):
        results = _suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=_agent(),
            split="held_out",
            k=1,
            seed=41,
            end_user=SimulatedEndUser(model=Reader()),
        )
        assert results.rollouts[0].unanswered_consultations == 0

    def test_a_channel_that_says_nobody_is_there_leaves_the_rollout_inside(self, tmp_path):
        """`unattended()` is the designed path, so what the agent did without an answer counts.

        A project that ships unattended is measured on how it behaves with no answer, and
        a rate that dropped those rollouts would measure nothing it cares about.
        """
        results = _suite().run(
            envelope=RunEnvelope(run_dir=tmp_path).with_end_user(unattended()),
            model=_agent(),
            split="held_out",
            k=1,
            seed=41,
        )

        [rollout] = results.rollouts
        assert rollout.unanswered_consultations == 1
        assert rollout.left_out == ()
        assert results.metrics["accuracy"].left_out == {}
        assert results.metrics["accuracy"].interval.n == 1

    def test_a_question_to_someone_who_was_meant_to_answer_leaves_it_out(self, tmp_path):
        """The agent asked correctly and the answer never arrived, which is not its failure."""

        def nobody_replies(question, options=None, about=None):
            return None

        nobody_replies.answered_by = "end_user"
        results = _suite(
            pipeline=_pipeline(consult(nobody_replies, name="consult", answered_by="end_user"))
        ).run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=_agent(),
            split="held_out",
            k=1,
            seed=41,
            # The questions are meant to reach this channel, which is what passing it says.
            end_user=nobody_replies,
        )

        [rollout] = results.rollouts
        assert rollout.unanswered_consultations == 1
        assert rollout.left_out == ("unanswered_consultation",)
        assert results.metrics["accuracy"].left_out == {"unanswered_consultation": 1}
        # Outside every rate, and the interval says so rather than the figure moving quietly.
        assert results.metrics["accuracy"].interval is None
        assert "1 rollout(s) whose question went unanswered" in results.metrics["accuracy"].reason

    def test_it_survives_a_round_trip_through_the_results_file(self, tmp_path):
        results = _suite().run(
            envelope=RunEnvelope(run_dir=tmp_path).with_end_user(unattended()),
            model=_agent(),
            split="held_out",
            k=1,
            seed=41,
        )
        written = json.loads(json.dumps(results.to_json()))
        assert written["rollouts"][0]["unanswered_consultations"] == 1


class TestMoreThanOneAnswerer:
    def _pipeline_asking_two(self) -> Pipeline:
        return _pipeline(
            consult(unattended(), name="ask_requester", reaches="requester"),
            consult(unattended(), name="ask_approver", reaches="approver"),
        )

    def _examples_for_two(self) -> ExampleSet:
        return _examples(
            {
                "requester": EndUser("A junior analyst filing the invoice."),
                "approver": EndUser("Her director.", knows={"cap": Fact("5000 cap")}),
            }
        )

    def test_each_tool_is_answered_by_the_person_it_reaches(self, tmp_path):
        requester, approver = Reader(replies=["CC-4471."]), Reader(replies=["Approved."])
        suite = _suite(self._pipeline_asking_two(), self._examples_for_two())

        suite.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=_agent([_ask(name="ask_requester"), _ask(name="ask_approver")]),
            split="held_out",
            k=1,
            seed=41,
            end_user={
                "requester": SimulatedEndUser(model=requester),
                "approver": SimulatedEndUser(model=approver),
            },
        )

        assert "A junior analyst filing the invoice." in requester.systems[0]
        assert "Her director." in approver.systems[0]

    def test_the_record_says_which_answerer_it_reached(self, tmp_path):
        suite = _suite(self._pipeline_asking_two(), self._examples_for_two())
        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=_agent([_ask(name="ask_approver")]),
            split="held_out",
            k=1,
            seed=41,
            end_user={
                "requester": SimulatedEndUser(model=Reader()),
                "approver": SimulatedEndUser(model=Reader()),
            },
        )
        [record] = [
            r
            for r in read_trajectory(results.rollouts[0].trajectory)
            if r["record_type"] == "consultation"
        ]
        assert record["reaches"] == "approver"

    def test_an_example_missing_one_of_them_is_refused_before_any_rollout(self, tmp_path):
        reader = Reader()
        suite = _suite(
            self._pipeline_asking_two(), _examples({"requester": EndUser("A junior analyst.")})
        )

        with pytest.raises(ConfigurationError) as exc:
            suite.run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=_agent(),
                split="held_out",
                k=1,
                seed=41,
                end_user={
                    "requester": SimulatedEndUser(model=reader),
                    "approver": SimulatedEndUser(model=reader),
                },
            )

        assert "approver" in str(exc.value)
        assert reader.requests == []

    def test_a_tool_that_does_not_say_who_it_asks_is_refused_before_any_rollout(self, tmp_path):
        reader = Reader()
        suite = _suite(_pipeline(consult(unattended(), name="consult")), self._examples_for_two())

        with pytest.raises(ConfigurationError) as exc:
            suite.run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=_agent(),
                split="held_out",
                k=1,
                seed=41,
                end_user={
                    "requester": SimulatedEndUser(model=reader),
                    "approver": SimulatedEndUser(model=reader),
                },
            )

        assert "does not say which of them it asks" in str(exc.value)
        assert reader.requests == []

    def test_the_manifest_records_which_answerer_each_tool_asks(self, tmp_path):
        from simple_agents.envelope import MANIFEST_NAME

        result = self._pipeline_asking_two().run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=_agent(), seed=41
        )
        manifest = json.loads((result.trajectory_path.parent / MANIFEST_NAME).read_text())
        assert {t["name"]: t["reaches"] for t in manifest["tools"]} == {
            "ask_requester": "requester",
            "ask_approver": "approver",
        }

    def test_each_answerer_is_part_of_the_evaluations_identity(self):
        """Two evaluations differing in one of them are two evaluations."""
        from simple_agents.evaluation.runner import _end_user_identity

        one = _end_user_identity(
            {
                "requester": SimulatedEndUser(model=Reader()),
                "approver": SimulatedEndUser(model=Reader()),
            }
        )
        two = _end_user_identity(
            {
                "requester": SimulatedEndUser(model=Reader()),
                "approver": SimulatedEndUser(model=Reader(), instructions="Be {end_user}."),
            }
        )
        assert one != two


class TestConsultationsThatOverlap:
    """A stand-in answers in the process that asked, so its calls can run together.

    The refusal this replaces was made when the node was built, which is before the channel
    that will answer is known: `SimulatedEndUser` never suspends and a terminal may.
    """

    def _node(self, tool):
        return AgentNode(
            _prompt,
            tools=ToolRegistry([tool]),
            output_schema=Answer,
            budget=BUDGET,
            concurrent_tools=[tool],
            node_id="hunt",
        )

    def test_a_channel_that_never_suspends_may_overlap(self):
        assert self._node(consult(unattended(), name="consult")).concurrent_tools == ("consult",)

    def test_a_channel_that_does_not_say_is_refused(self):
        def ask_somebody(question, options=None, about=None):
            return "yes"

        with pytest.raises(ConfigurationError) as exc:
            self._node(consult(ask_somebody, name="consult", answered_by="builder"))

        assert "may_suspend = False" in str(exc.value)

    def test_the_run_decides_it_rather_than_the_node(self):
        """A node built around a stand-in runs its consultations one at a time in front of a
        person, because the channel the run supplied is the one that answers."""

        node = self._node(consult(unattended(), name="consult"))
        [tool] = node.tools

        def a_terminal(question, options=None, about=None):
            return "yes"

        a_terminal.answered_by = "builder"

        class Run:
            end_user = a_terminal

        assert node._answers_in_process(tool, Run()) is False
        assert node._answers_in_process(tool, None) is True


class TestOneDescriptionCannotPlayTwoPeople:
    """The defect this item exists to close, tested from both sides.

    A run that asks a requester and an approver and an example that describes one person would
    play both from that description, record `simulated` for both, and report nothing saying the
    two answerers were one.
    """

    def _pipeline_asking_two(self) -> Pipeline:
        return _pipeline(
            consult(unattended(), name="ask_requester", reaches="requester"),
            consult(unattended(), name="ask_approver", reaches="approver"),
        )

    def test_one_description_against_two_answerers_is_refused(self, tmp_path):
        reader = Reader()
        suite = _suite(
            self._pipeline_asking_two(), _examples("A junior analyst filing the invoice.")
        )

        with pytest.raises(ConfigurationError) as exc:
            suite.run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=_agent(),
                split="held_out",
                k=1,
                seed=41,
                end_user={
                    "requester": SimulatedEndUser(model=reader),
                    "approver": SimulatedEndUser(model=reader),
                },
            )

        assert "requester" in str(exc.value) and "approver" in str(exc.value)
        assert reader.requests == []

    def test_named_answerers_against_one_channel_are_refused(self, tmp_path):
        reader = Reader()
        suite = _suite(
            self._pipeline_asking_two(),
            _examples(
                {"requester": EndUser("A junior analyst."), "approver": EndUser("Her director.")}
            ),
        )

        with pytest.raises(ConfigurationError) as exc:
            suite.run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=_agent(),
                split="held_out",
                k=1,
                seed=41,
                end_user=SimulatedEndUser(model=reader),
            )

        assert "Which of those people it plays is undeclared" in str(exc.value)
        assert reader.requests == []


class TestAReplaySaysWhatTheLiveRunSaid:
    """The declared choice is stored with the answer rather than derived from the call.

    Held on the call's provenance it was lost on replay, so the same run reported
    `consultation_misreadings` of 1 live and 0 replayed.
    """

    OPTIONS = ["Crossroads of Ravens", "The Will of the Many"]

    def _run(self, tmp_path, label, cassette):
        reader = Reader(replies=["Just get The Will of the Many."], chose="The Will of the Many")
        results = _suite().run(
            envelope=RunEnvelope(run_dir=tmp_path / label, cassette=cassette),
            model=_agent([_ask(options=self.OPTIONS)]),
            split="held_out",
            k=1,
            seed=41,
            end_user=SimulatedEndUser(model=reader),
        )
        [record] = [
            r
            for r in read_trajectory(results.rollouts[0].trajectory)
            if r["record_type"] == "consultation"
        ]
        return record, results.nodes["hunt"].consultation_misreadings, len(reader.requests)

    def test_a_replay_reports_the_same_reading(self, tmp_path):
        from simple_agents import Cassette

        path = tmp_path / "cassette.jsonl"
        live, live_count, _ = self._run(tmp_path, "live", Cassette.record(path))
        replayed, replay_count, calls = self._run(tmp_path, "replay", Cassette.replay(path))

        assert (replayed["chose"], replayed["declared_choice"]) == (
            live["chose"],
            live["declared_choice"],
        )
        assert replay_count == live_count == 1
        assert calls == 0

    def test_the_record_still_holds_what_the_person_said(self, tmp_path):
        """Storing the declaration beside the answer must not change the answer."""
        from simple_agents import Cassette

        path = tmp_path / "cassette.jsonl"
        live, _, _ = self._run(tmp_path, "live", Cassette.record(path))
        replayed, _, _ = self._run(tmp_path, "replay", Cassette.replay(path))

        assert live["response"] == "Just get The Will of the Many."
        assert replayed["response"] == live["response"]


class TestAnAnswerThatDidNotFinish:
    """A reasoning model spends the output ceiling on its chain of thought as well.

    Found on Qwen3-1.7B through vLLM: the reply came back empty and the refusal sent the
    builder to change models, when the fix is the ceiling.
    """

    class Truncated(Reader):
        def complete(self, request):
            from dataclasses import replace as _replace

            return _replace(super().complete(request), content="", finish_reason="length")

    class Garbled(Reader):
        def complete(self, request):
            from dataclasses import replace as _replace

            return _replace(super().complete(request), content="Sure, happy to help!")

    def test_a_truncated_answer_names_the_ceiling(self):
        channel = SimulatedEndUser(model=self.Truncated()).playing(EndUser("A manager."), seed=41)
        with pytest.raises(Exception) as exc:
            channel("Which one?", None)

        assert "max_output_tokens" in str(exc.value)
        assert "output ceiling" in str(exc.value)

    def test_an_answer_that_is_not_json_still_names_the_schema(self):
        channel = SimulatedEndUser(model=self.Garbled()).playing(EndUser("A manager."), seed=41)
        with pytest.raises(Exception) as exc:
            channel("Which one?", None)

        assert "honours output_schema" in str(exc.value)
        assert "max_output_tokens" not in str(exc.value)
