"""Who the `no_one_to_ask` memo is allowed to silence, and a suspension that was swallowed.

Dogfood #5's product asked one distinct question per stale show from a `Deterministic` node.
The first `Unavailable` set a per-run, per-tool memo and every later question in the run was
answered from it without reaching the channel: 109 distinct questions, 5 on the shelf, and
1,640 records carrying the channel's own words about questions it never saw.

The rule is right for the case it was built for, a model in a loop asking a person who is not
there, and the line between the two is who chose the call. The same project wrapped its
`ctx.call_tool` in `except Exception: continue`, which is why `Suspend` is a `BaseException`
here and why a run that finishes after one was raised is refused.
"""

from __future__ import annotations

import pytest

from simple_agents import (
    AgentNode,
    Budget,
    Deterministic,
    FakeModelClient,
    Pipeline,
    RunEnvelope,
    RunSuspended,
    Suspend,
    ToolRegistry,
    read_trajectory,
)
from simple_agents.builtins import Unavailable, consult
from simple_agents.errors import CallerFacingError
from simple_agents.models import ToolCallRequest, fake_response

from conftest import RUN_ID
from schemas import Answer

QUESTIONS = ["Keep Shameless?", "Keep The Wire?", "Keep Deadwood?"]


def _budget() -> Budget:
    return Budget(max_steps=8, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


class _CountingChannel:
    """A channel that shelves every question and remembers which ones reached it."""

    answered_by = "end_user"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def __call__(self, question, options=None, about=None):
        self.seen.append(question)
        return Unavailable(reason="the site is unattended; the question is shelved for later")


def _asking_node(channel, questions=QUESTIONS):
    """A `Deterministic` node that asks one question per item, which is the measured case."""

    def ask_about_each(inputs, ctx):
        return {
            "replies": [
                str(ctx.call_tool("consult", question=q, options=["keep", "drop"]))
                for q in questions
            ]
        }

    return Deterministic(
        ask_about_each,
        tools=[consult(channel, answered_by="end_user")],
        node_id="ask",
        output_schema=None,
    )


def _consultations(result) -> list[dict]:
    return [
        r for r in read_trajectory(result.paths.trajectory) if r["record_type"] == "consultation"
    ]


class TestANodeBodysQuestionsAllReachTheChannel:
    @pytest.fixture
    def channel(self) -> _CountingChannel:
        return _CountingChannel()

    @pytest.fixture
    def result(self, tmp_path, channel):
        pipeline = Pipeline([_asking_node(channel)], budget=_budget())
        return pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)

    def test_every_question_reaches_it(self, result, channel):
        """The measured failure: 3 asked, 1 delivered, before this."""
        assert channel.seen == QUESTIONS

    def test_each_one_is_recorded(self, result):
        assert len(_consultations(result)) == len(QUESTIONS)

    def test_the_records_carry_the_questions_that_were_asked(self, result):
        assert [c["prompt"] for c in _consultations(result)] == QUESTIONS

    def test_they_are_all_unavailable(self, result):
        assert {c["resolution"] for c in _consultations(result)} == {"unavailable"}


class TestTheModelIsStillToldOnce:
    def _pipeline(self, channel):
        return Pipeline(
            [
                AgentNode(
                    lambda inputs, ctx: "go",
                    tools=ToolRegistry([consult(channel, answered_by="end_user")]),
                    output_schema=Answer,
                    budget=_budget(),
                    node_id="hunt",
                )
            ],
            budget=_budget(),
        )

    def _asking(self, question: str) -> ToolCallRequest:
        return ToolCallRequest(id=f"c_{question}", name="consult", arguments={"question": question})

    @pytest.fixture
    def channel(self) -> _CountingChannel:
        return _CountingChannel()

    @pytest.fixture
    def result(self, tmp_path, channel):
        client = FakeModelClient(
            responses=[
                *[fake_response(tool_calls=[self._asking(q)]) for q in QUESTIONS],
                fake_response(
                    tool_calls=[
                        ToolCallRequest(
                            id="f",
                            name="finish",
                            arguments={"answer": "done", "source": None},
                        )
                    ]
                ),
            ]
        )
        return self._pipeline(channel).run(
            {}, envelope=RunEnvelope(run_dir=tmp_path), model=client, run_id=RUN_ID
        )

    def test_the_channel_is_reached_once(self, result, channel):
        """The model read `Do not ask again` on the first answer; the memo is for the rest."""
        assert channel.seen == QUESTIONS[:1]

    def test_every_question_is_still_recorded(self, result):
        assert len(_consultations(result)) == len(QUESTIONS)

    def test_the_later_records_carry_the_first_calls_reason(self, result):
        reasons = {c["reason"] for c in _consultations(result)}
        assert reasons == {"the site is unattended; the question is shelved for later"}


class TestSuspendIsNotAnException:
    def test_it_does_not_derive_from_exception(self):
        assert issubclass(Suspend, BaseException)
        assert not issubclass(Suspend, Exception)

    def test_a_blanket_except_exception_does_not_catch_it(self):
        caught = None
        try:
            try:
                raise Suspend(waiting_for="an answer")
            except Exception as exc:  # noqa: BLE001 - the point of the test
                caught = exc
        except Suspend:
            pass
        assert caught is None

    def test_run_suspended_is_still_an_exception(self):
        """The caller called `run` and is expected to handle what it raises."""
        assert issubclass(RunSuspended, Exception)


class TestASwallowedSuspensionEndsTheRun:
    def _pipeline(self):
        def swallow(inputs, ctx):
            try:
                ctx.call_tool("consult", question="Keep Shameless?")
            except BaseException:  # noqa: BLE001 - what a project wrote, with Exception
                pass
            return {"answer": "carried on"}

        def channel(question, options=None, about=None):
            raise Suspend(waiting_for=question, options=options)

        channel.answered_by = "end_user"
        return Pipeline(
            [
                Deterministic(
                    swallow,
                    tools=[consult(channel, answered_by="end_user")],
                    node_id="ask",
                    output_schema=None,
                )
            ],
            budget=_budget(),
        )

    @pytest.fixture
    def refusal(self, tmp_path) -> CallerFacingError:
        with pytest.raises(CallerFacingError) as exc:
            self._pipeline().run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)
        return exc.value

    def test_the_run_does_not_report_as_finished(self, refusal):
        assert "finished" in str(refusal)

    def test_it_names_what_the_run_had_stopped_for(self, refusal):
        assert "Keep Shameless?" in str(refusal)

    def test_it_names_the_construct_that_causes_it(self, refusal):
        assert "except Exception" in str(refusal)
        assert "ctx.call_tool" in str(refusal)

    def test_it_offers_the_channel_that_does_not_stop_the_run(self, refusal):
        assert "Unavailable(reason=...)" in str(refusal)

    def test_a_suspension_that_is_let_out_still_suspends(self, tmp_path):
        def ask(inputs, ctx):
            return ctx.call_tool("consult", question="Keep Shameless?")

        def channel(question, options=None, about=None):
            raise Suspend(waiting_for=question, options=options)

        pipeline = Pipeline(
            [
                Deterministic(
                    ask,
                    tools=[consult(channel, answered_by="end_user")],
                    node_id="ask",
                    output_schema=None,
                )
            ],
            budget=_budget(),
        )
        with pytest.raises(RunSuspended):
            pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)
