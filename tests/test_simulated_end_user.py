"""The end user an evaluation answers with, played by a model.

Dogfood #4's evaluations answered every consultation with one fixed string, and the rates
were computed over that. The questions cannot be pre-written, because the agent builds them from
what a run happened to find: 103 of that run's 104 were distinct. So the example describes the
person and a model answers as them, and every record says a model did.
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
from simple_agents.builtins import ModelAnswer, consult, unattended
from simple_agents.errors import CallerFacingError, ConfigurationError
from simple_agents.evaluation import EvalSuite, Example, ExampleSet, SimulatedEndUser
from simple_agents.models import (
    ModelIdentity,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
    TokenUsage,
    fake_response,
)

from schemas import Answer

BUDGET = Budget(max_steps=6, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


class ScriptedReader:
    """A client that answers as the JSON the stand-in asks for, and remembers the requests."""

    def __init__(self, reply: str | None = "Under 400 pages, and skip the difficulty question."):
        self.reply = reply
        self.requests: list[ModelRequest] = []

    def identity(self) -> ModelIdentity:
        return ModelIdentity(backend="hosted_api", request_model="reader-1")

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            content=json.dumps({"reply": self.reply}),
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


class Unparseable(ScriptedReader):
    def complete(self, request: ModelRequest) -> ModelResponse:
        from dataclasses import replace

        return replace(super().complete(request), content="Sure, I'd love a shorter book!")


def _prompt(inputs, ctx):
    return Prompt.user("go")


def _ask(
    question: str = "How long a book?", options=None, about: str | None = None
) -> ToolCallRequest:
    arguments = {"question": question}
    if options is not None:
        arguments["options"] = options
    return ToolCallRequest(id="c1", name="consult", arguments=arguments)


def _finish(answer: str = "done") -> ToolCallRequest:
    return ToolCallRequest(id="f", name="finish", arguments={"answer": answer, "source": None})


def _pipeline() -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                _prompt,
                tools=ToolRegistry([consult(unattended(), name="consult")]),
                output_schema=Answer,
                budget=BUDGET,
                node_id="hunt",
            )
        ],
        budget=BUDGET,
    )


def _examples(end_user: str | None = "Reads grimdark, wants under 400 pages.") -> ExampleSet:
    return ExampleSet(
        [
            Example(
                id="q1",
                inputs={},
                expected="done",
                split="held_out",
                end_user=end_user,
            )
        ]
    )


def _agent_client() -> FakeModelClient:
    return FakeModelClient(
        responses=[fake_response(tool_calls=[_ask()]), fake_response(tool_calls=[_finish()])]
    )


class TestTheExampleDescribesThePerson:
    def test_the_description_travels_through_the_file(self, tmp_path):
        path = tmp_path / "examples.jsonl"
        _examples().to_jsonl(path)

        [example] = list(ExampleSet.from_jsonl(path))
        assert example.end_user.description == "Reads grimdark, wants under 400 pages."

    def test_it_is_part_of_what_the_examples_hash_to(self):
        """Two evaluations over different readers are not one evaluation."""
        assert _examples().content_hash() != _examples("Reads cosy mysteries.").content_hash()

    def test_an_example_without_one_still_builds(self):
        assert Example(id="q1", inputs={}, expected="x", split="dev").end_user is None


class TestWhatItSends:
    def test_the_description_and_the_question_both_reach_the_model(self):
        reader = ScriptedReader()
        channel = SimulatedEndUser(model=reader).playing("Reads grimdark.", seed=7)

        channel("How long a book?", None)
        [request] = reader.requests
        sent = " ".join(m["content"] for m in request.messages)

        assert "Reads grimdark." in sent
        assert "How long a book?" in sent

    def test_the_offered_options_are_shown(self):
        reader = ScriptedReader()
        channel = SimulatedEndUser(model=reader).playing("Reads grimdark.", seed=7)

        channel("How long?", ["short", "long"])
        sent = " ".join(m["content"] for m in reader.requests[0].messages)

        assert "short, long" in sent

    def test_each_question_takes_its_own_seed_from_the_rollouts(self):
        reader = ScriptedReader()
        channel = SimulatedEndUser(model=reader).playing("Reads grimdark.", seed=7)

        channel("First?", None)
        channel("Second?", None)

        assert reader.requests[0].seed != reader.requests[1].seed

    def test_two_rollouts_of_one_example_get_different_seeds(self):
        reader = ScriptedReader()
        stand_in = SimulatedEndUser(model=reader)

        stand_in.playing("Reads grimdark.", seed=1)("How long?", None)
        stand_in.playing("Reads grimdark.", seed=2)("How long?", None)

        assert reader.requests[0].seed != reader.requests[1].seed

    def test_the_same_rollout_seed_asks_the_same_way_twice(self):
        reader = ScriptedReader()
        stand_in = SimulatedEndUser(model=reader)

        stand_in.playing("Reads grimdark.", seed=1)("How long?", None)
        stand_in.playing("Reads grimdark.", seed=1)("How long?", None)

        assert reader.requests[0].seed == reader.requests[1].seed


class TestWhatItReturns:
    def test_the_answer_carries_the_model_that_wrote_it(self):
        channel = SimulatedEndUser(model=ScriptedReader()).playing("Reads grimdark.", seed=7)

        answer = channel("How long?", None)

        assert isinstance(answer, ModelAnswer)
        assert answer.text.startswith("Under 400 pages")
        assert answer.model["request_model"] == "reader-1"
        assert answer.tokens.output == 12

    def test_a_reader_who_would_not_answer_declines(self):
        channel = SimulatedEndUser(model=ScriptedReader(reply=None)).playing("Silent.", seed=7)

        assert channel("How long?", None).text is None

    def test_an_answer_that_does_not_parse_ends_the_run(self):
        """Recording it as the answer would put words in a person's mouth."""
        channel = SimulatedEndUser(model=Unparseable()).playing("Reads grimdark.", seed=7)

        with pytest.raises(CallerFacingError) as exc:
            channel("How long?", None)

        assert "reader-1" in str(exc.value)
        assert "output_schema" in str(exc.value)

    def test_a_client_that_is_not_one_is_refused(self):
        with pytest.raises(ConfigurationError) as exc:
            SimulatedEndUser(model="gemini-3.1-flash-lite")

        assert "is not a ModelClient" in str(exc.value)


class TestInAnEvaluation:
    def _suite(self, examples=None) -> EvalSuite:
        return EvalSuite(
            _pipeline(),
            examples if examples is not None else _examples(),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
        )

    def test_the_stand_in_answers_the_agents_questions(self, tmp_path):
        reader = ScriptedReader()
        results = self._suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=_agent_client(),
            split="held_out",
            k=1,
            seed=41,
            end_user=SimulatedEndUser(model=reader),
        )

        assert len(reader.requests) == 1
        assert results.nodes["hunt"].consultation_answered_by == {"simulated": 1}

    def test_the_consultation_records_the_model_and_keeps_it_off_the_node(self, tmp_path):
        results = self._suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=_agent_client(),
            split="held_out",
            k=1,
            seed=41,
            end_user=SimulatedEndUser(model=ScriptedReader()),
        )
        [rollout] = results.rollouts
        [consultation] = [
            r for r in read_trajectory(rollout.trajectory) if r["record_type"] == "consultation"
        ]

        assert consultation["answered_by"] == "simulated"
        assert consultation["answered_by_model"]["request_model"] == "reader-1"
        assert consultation["answered_by_model"]["tokens"]["output"] == 12
        assert results.nodes["hunt"].model_calls == 2

    def test_an_example_with_no_description_is_refused_before_any_rollout(self, tmp_path):
        reader = ScriptedReader()

        with pytest.raises(ConfigurationError) as exc:
            self._suite(_examples(end_user=None)).run(
                envelope=RunEnvelope(run_dir=tmp_path),
                model=_agent_client(),
                split="held_out",
                k=1,
                seed=41,
                end_user=SimulatedEndUser(model=reader),
            )

        assert "do not say who the agent is answering" in str(exc.value)
        assert "q1" in str(exc.value)
        assert reader.requests == []

    def test_a_pipeline_that_cannot_consult_is_not_asked_for_descriptions(self, tmp_path):
        plain = Pipeline(
            [
                AgentNode(
                    _prompt,
                    tools=ToolRegistry([]),
                    output_schema=Answer,
                    budget=BUDGET,
                    node_id="hunt",
                )
            ],
            budget=BUDGET,
        )
        suite = EvalSuite(
            plain,
            _examples(end_user=None),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
        )

        results = suite.run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=FakeModelClient(responses=[fake_response(tool_calls=[_finish()])]),
            split="held_out",
            k=1,
            seed=41,
            end_user=SimulatedEndUser(model=ScriptedReader()),
        )

        assert results.rollouts[0].answer == "done"

    def test_leaving_it_unset_uses_the_projects_own_channel(self, tmp_path):
        results = self._suite().run(
            envelope=RunEnvelope(run_dir=tmp_path),
            model=_agent_client(),
            split="held_out",
            k=1,
            seed=41,
        )

        assert results.nodes["hunt"].consultation_answered_by == {"nobody": 1}


class TestTheEvaluationsIdentity:
    def _suite(self) -> EvalSuite:
        return EvalSuite(
            _pipeline(), _examples(), answer="answer", matches=lambda s: s.answer == s.expected
        )

    def test_which_model_played_the_end_user_names_the_directory(self):
        suite = self._suite()
        one = SimulatedEndUser(model=ScriptedReader())

        class Other(ScriptedReader):
            def identity(self):
                return ModelIdentity(backend="hosted_api", request_model="reader-2")

        assert suite._eval_id(41, "held_out", 1, None, one) != suite._eval_id(
            41, "held_out", 1, None, SimulatedEndUser(model=Other())
        )

    def test_an_evaluation_with_a_stand_in_is_not_one_without(self):
        suite = self._suite()

        assert suite._eval_id(41, "held_out", 1, None, None) != suite._eval_id(
            41, "held_out", 1, None, SimulatedEndUser(model=ScriptedReader())
        )

    def test_the_same_stand_in_names_the_same_directory(self):
        suite = self._suite()

        assert suite._eval_id(
            41, "held_out", 1, None, SimulatedEndUser(model=ScriptedReader())
        ) == suite._eval_id(41, "held_out", 1, None, SimulatedEndUser(model=ScriptedReader()))
