"""The third way a consultation ends, and what a consultation is identified by.

Dogfood #5's product needed *ask, publish the question, do not wait, finish the run, and let
the answer reach a later run*. The library had two modes, engaged and unavailable, so the
project spelled the third as `Unavailable` and every downstream mechanism then did the right
thing for the wrong meaning: the memo fired, the resolution said nobody could be asked, and
`on_reply(unavailable=...)` routed asked-and-outstanding as the absence of a choice.

The same product asked about the same show under two wordings a day apart, because a question
had no identity but its text, and the artifact reported fourteen answers where a person gave
two.
"""

from __future__ import annotations

import pytest

from simple_agents import (
    Prompt,
    Budget,
    Deterministic,
    Pipeline,
    RunEnvelope,
    read_trajectory,
)
from simple_agents.builtins import Reply, Shelved, Unavailable, consult, on_reply
from simple_agents.errors import CallerFacingError, ConfigurationError

from conftest import RUN_ID

SHOWS = ["The Wire", "Deadwood", "Shameless"]


def _budget() -> Budget:
    return Budget(max_steps=8, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def _asking(channel, tools=None, **node):
    """A node that asks about each show by name, which is the measured shape."""

    def ask_about_each(inputs, ctx):
        return {
            "replies": [
                str(
                    ctx.call_tool(
                        "consult",
                        question=f"Keep {show}?",
                        options=["keep", "drop"],
                        about=f"show:{show}",
                    )
                )
                for show in SHOWS
            ]
        }

    return Pipeline(
        [
            Deterministic(
                ask_about_each,
                tools=tools or [consult(channel, answered_by="end_user")],
                node_id="ask",
                output_schema=None,
                **node,
            )
        ],
        budget=_budget(),
    )


def _consultations(result) -> list[dict]:
    return [
        r for r in read_trajectory(result.paths.trajectory) if r["record_type"] == "consultation"
    ]


class _Shelf:
    """A channel that puts a question on a page and serves an answer it stored earlier."""

    answered_by = "end_user"

    def __init__(self, answers: dict[str, tuple[str, str]] | None = None) -> None:
        self.answers = answers or {}
        self.seen: list[str | None] = []

    def __call__(self, question, options=None, about=None):
        self.seen.append(about)
        if about in self.answers:
            text, at = self.answers[about]
            return Reply(text, chose=None, options=options or (), answered_at=at)
        return Shelved(reason="the site is unattended; the question is on the questions page")


class TestShelvedIsItsOwnOutcome:
    @pytest.fixture
    def result(self, tmp_path):
        return _asking(_Shelf()).run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)

    def test_the_run_finishes(self, result):
        """A run fired by cron is unattended and cannot stop."""
        assert result.output["replies"]

    def test_every_question_is_recorded_shelved(self, result):
        assert [c["resolution"] for c in _consultations(result)] == ["shelved"] * len(SHOWS)

    def test_it_is_not_unavailable(self, result):
        """Asked-and-outstanding is a different event from there being nobody to ask."""
        assert "unavailable" not in {c["resolution"] for c in _consultations(result)}

    def test_the_reason_says_where_the_question_went(self, result):
        assert all("questions page" in c["reason"] for c in _consultations(result))

    def test_it_never_silences_a_later_question(self, tmp_path):
        shelf = _Shelf()
        _asking(shelf).run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)
        assert shelf.seen == [f"show:{show}" for show in SHOWS]

    def test_the_channel_was_reached_for_each_one(self, result):
        assert all(c["asked"] for c in _consultations(result))

    def test_a_shelved_reason_is_required(self):
        with pytest.raises(ConfigurationError) as exc:
            Shelved(reason="  ")
        assert "where the question went" in str(exc.value)

    def test_the_text_tells_the_model_the_answer_may_come_later(self):
        assert "may arrive after this run has finished" in str(Shelved(reason="on the page"))


class TestAConsultationHasAnIdentity:
    @pytest.fixture
    def result(self, tmp_path):
        return _asking(_Shelf()).run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)

    def test_the_channel_is_given_it(self, tmp_path):
        shelf = _Shelf()
        _asking(shelf).run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)
        assert shelf.seen == [f"show:{show}" for show in SHOWS]

    def test_it_is_recorded(self, result):
        assert [c["about"] for c in _consultations(result)] == [f"show:{show}" for show in SHOWS]

    def test_a_question_asked_without_one_records_null(self, tmp_path):
        def ask(inputs, ctx):
            return ctx.call_tool("consult", question="Which fit?")

        pipeline = Pipeline(
            [
                Deterministic(
                    ask,
                    tools=[consult(_Shelf(), answered_by="end_user")],
                    node_id="ask",
                    output_schema=None,
                )
            ],
            budget=_budget(),
        )
        result = pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)
        assert [c["about"] for c in _consultations(result)] == [None]


class TestAnAnswerGivenEarlierSaysSo:
    """Fourteen records carrying one answer are distinguishable from fourteen answers."""

    @pytest.fixture
    def result(self, tmp_path):
        shelf = _Shelf({"show:The Wire": ("keep", "2026-08-23T18:14:00Z")})
        return _asking(shelf).run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)

    def test_the_stored_answer_is_recorded_answered(self, result):
        [answered] = [c for c in _consultations(result) if c["resolution"] == "answered"]
        assert answered["about"] == "show:The Wire"

    def test_it_carries_when_the_person_said_it(self, result):
        [answered] = [c for c in _consultations(result) if c["resolution"] == "answered"]
        assert answered["answered_at"] == "2026-08-23T18:14:00Z"

    def test_an_answer_given_now_carries_none(self, tmp_path):
        def channel(question, options=None, about=None):
            return "keep"

        channel.answered_by = "end_user"
        result = _asking(channel).run({}, envelope=RunEnvelope(run_dir=tmp_path), run_id=RUN_ID)
        assert {c["answered_at"] for c in _consultations(result)} == {None}


class TestTheMemoedRecordSaysTheChannelWasNotReached:
    """1,640 of one project's 1,654 records were written without the channel seeing them."""

    @pytest.fixture
    def result(self, tmp_path):
        from simple_agents import AgentNode, FakeModelClient, ToolRegistry
        from simple_agents.models import ToolCallRequest, fake_response

        from schemas import Answer

        def channel(question, options=None, about=None):
            return Unavailable(reason="the desk is closed")

        channel.answered_by = "end_user"
        asks = [
            fake_response(
                tool_calls=[ToolCallRequest(id=f"c{n}", name="consult", arguments={"question": q})]
            )
            for n, q in enumerate(SHOWS)
        ]
        client = FakeModelClient(
            responses=[
                *asks,
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
                    lambda inputs, ctx: Prompt.user("go"),
                    tools=ToolRegistry([consult(channel, answered_by="end_user")]),
                    output_schema=Answer,
                    budget=_budget(),
                    node_id="hunt",
                )
            ],
            budget=_budget(),
        )
        return pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path), model=client, run_id=RUN_ID)

    def test_the_first_one_reached_the_channel(self, result):
        assert _consultations(result)[0]["asked"] is True

    def test_the_rest_did_not(self, result):
        assert [c["asked"] for c in _consultations(result)[1:]] == [False] * (len(SHOWS) - 1)

    def test_a_reader_can_count_questions_put_to_anybody(self, result):
        records = _consultations(result)
        assert len(records) == len(SHOWS) and sum(c["asked"] for c in records) == 1


class TestRoutingOnAShelvedQuestion:
    def test_the_branch_is_required(self):
        with pytest.raises(ConfigurationError) as exc:
            on_reply({"keep": "apply"}, unmatched="amend", declined="stop", unavailable="proceed")
        assert "no branch for shelved" in str(exc.value)

    def test_the_refusal_says_why_it_is_not_the_unavailable_branch(self):
        with pytest.raises(ConfigurationError) as exc:
            on_reply({"keep": "apply"}, unmatched="amend", declined="stop", unavailable="proceed")
        assert "a shelved question has reached somebody" in str(exc.value)

    def test_it_takes_its_own_branch(self):
        route = on_reply(
            {"keep": "apply"},
            unmatched="amend",
            declined="stop",
            unavailable="proceed",
            shelved="carry_on",
        )
        assert route(Shelved(reason="on the page"), None) == "carry_on"

    def test_the_manifest_carries_it(self):
        route = on_reply(
            {"keep": "apply"},
            unmatched="amend",
            declined="stop",
            unavailable="proceed",
            shelved="carry_on",
        )
        assert route.consultation_route["shelved"] == "carry_on"

    def test_exhaustive_without_a_branch_ends_the_run_naming_the_reason(self):
        route = on_reply({"keep": "apply"}, exhaustive=True)
        with pytest.raises(CallerFacingError) as exc:
            route(Shelved(reason="it is on the questions page"), None)
        assert "it is on the questions page" in str(exc.value)


class TestWhatAReplayServes:
    """A recorded shelving replays as shelved rather than as an answer with that text."""

    def test_shelved_round_trips(self):
        stored = Shelved(reason="on the questions page").to_json()
        assert Shelved.stored_in(stored)
        assert Shelved.from_json(stored).reason == "on the questions page"

    def test_it_is_not_mistaken_for_an_unavailable(self):
        assert not Unavailable.stored_in(Shelved(reason="on the page").to_json())
        assert not Shelved.stored_in(Unavailable(reason="the desk is closed").to_json())

    def test_a_reply_carries_when_it_was_answered_through_the_cassette(self):
        stored = Reply("keep", chose="keep", answered_at="2026-08-23T18:14:00Z").to_json()
        assert stored["answered_at"] == "2026-08-23T18:14:00Z"
