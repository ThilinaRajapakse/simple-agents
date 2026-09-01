"""What happens between a question being shelved and its answer arriving.

A run whose channel shelves finishes with the question on record and the run unattended. The
answer comes at an arbitrary later moment, through the project's own surface, and has to
reach whatever the project would do about it then rather than at the next scheduled run
(`DF5-N6`).

The run that asked has ended, so there is nothing to resume. Filing an answer starts a run of
its own: the answering record is its first record and names the question and the run that
asked it, and nothing already written is touched.
"""

from __future__ import annotations

import json

import pytest

from simple_agents import (
    Budget,
    Deterministic,
    Pipeline,
    RunEnvelope,
    read_trajectory,
)
from simple_agents.builtins import Reply, Shelved, consult
from simple_agents.errors import CallerFacingError
from simple_agents.records.shelf import SHELF_NAME, claim_shelf

from conftest import run_path

BUDGET = Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def _shelving(question, options=None, about=None):
    return Shelved(reason="the site is unattended; the question is on the questions page")


_shelving.answered_by = "end_user"


def _asking(subjects=("show:1421",)) -> Pipeline:
    def ask(inputs, ctx):
        return {
            "asked": [
                str(
                    ctx.call_tool(
                        "consult",
                        question=f"Keep {subject}?",
                        options=["keep", "drop"],
                        about=subject,
                    )
                )
                for subject in subjects
            ]
        }

    return Pipeline(
        [
            Deterministic(
                ask,
                tools=[consult(_shelving, answered_by="end_user")],
                node_id="ask",
                output_schema=None,
            )
        ],
        budget=BUDGET,
    )


def _acting(seen: list) -> Pipeline:
    def act(inputs, ctx):
        seen.append(inputs)
        return {"about": inputs.about}

    return Pipeline([Deterministic(act, node_id="act", output_schema=None)], budget=BUDGET)


def _consultations(trajectory) -> list[dict]:
    return [r for r in read_trajectory(trajectory) if r["record_type"] == "consultation"]


@pytest.fixture
def asked(tmp_path):
    """One shelved question, from a run that finished on Monday."""
    env = RunEnvelope(run_dir=tmp_path)
    _asking().run({}, envelope=env, run_id="monday")
    return env


class TestTheInbox:
    def test_the_question_is_listed(self, asked, tmp_path):
        [question] = Pipeline.shelved(tmp_path)
        assert (question.about, question.prompt) == ("show:1421", "Keep show:1421?")

    def test_it_names_the_run_and_the_record_that_asked(self, asked, tmp_path):
        [question] = Pipeline.shelved(tmp_path)
        [record] = _consultations(run_path(tmp_path, "monday", "trajectory.jsonl"))
        assert (question.run_id, question.record_id) == ("monday", record["record_id"])

    def test_it_carries_the_options_and_the_reason(self, asked, tmp_path):
        [question] = Pipeline.shelved(tmp_path)
        assert question.options == ["keep", "drop"]
        assert "questions page" in question.reason

    def test_a_run_that_shelved_nothing_writes_no_file(self, tmp_path):
        def answering(question, options=None, about=None):
            return "keep"

        answering.answered_by = "end_user"
        env = RunEnvelope(run_dir=tmp_path)
        Pipeline(
            [
                Deterministic(
                    lambda inputs, ctx: ctx.call_tool("consult", question="Keep it?"),
                    tools=[consult(answering, answered_by="end_user")],
                    node_id="ask",
                    output_schema=None,
                )
            ],
            budget=BUDGET,
        ).run({}, envelope=env, run_id="quiet")
        assert not (tmp_path / "quiet" / SHELF_NAME).exists()
        assert Pipeline.shelved(tmp_path) == []

    def test_it_is_read_from_the_file_rather_than_the_trajectories(self, asked, tmp_path):
        """A surface lists open questions per page load, and cannot read every trajectory."""
        (run_path(tmp_path, "monday", "trajectory.jsonl")).unlink()
        assert len(Pipeline.shelved(tmp_path)) == 1


class TestFilingAnAnswer:
    @pytest.fixture
    def acted(self, asked, tmp_path):
        seen: list = []
        answered = Pipeline.answer_shelved(
            tmp_path,
            about="show:1421",
            answer="drop",
            pipeline=_acting(seen),
            envelope=asked,
            run_id="wednesday",
        )
        return answered, seen

    def test_the_work_runs_with_the_answer(self, acted):
        _, seen = acted
        assert [(one.about, one.answer.chose) for one in seen] == [("show:1421", "drop")]

    def test_it_starts_a_run_of_its_own(self, acted):
        answered, _ = acted
        assert answered.run_id == "wednesday" and answered.question.run_id == "monday"

    def test_the_answering_record_names_the_question(self, acted, tmp_path):
        answered, _ = acted
        [record] = _consultations(run_path(tmp_path, "wednesday", "trajectory.jsonl"))
        assert record["answers"] == answered.question.record_id
        assert record["answers_run_id"] == "monday"

    def test_it_records_what_was_said_and_which_option_it_was(self, acted, tmp_path):
        [record] = _consultations(run_path(tmp_path, "wednesday", "trajectory.jsonl"))
        assert (record["resolution"], record["chose"]) == ("answered", "drop")

    def test_the_run_that_asked_is_not_touched(self, acted, tmp_path):
        [record] = _consultations(run_path(tmp_path, "monday", "trajectory.jsonl"))
        assert record["resolution"] == "shelved" and record["answers"] is None

    def test_the_question_leaves_the_inbox(self, acted, tmp_path):
        assert Pipeline.shelved(tmp_path) == []

    def test_answering_it_twice_is_refused(self, acted, tmp_path, asked):
        with pytest.raises(CallerFacingError) as exc:
            Pipeline.answer_shelved(tmp_path, about="show:1421", answer="keep", envelope=asked)
        assert "already been answered" in str(exc.value)


class TestFilingWithNoWorkToDo:
    @pytest.fixture
    def answered(self, asked, tmp_path):
        return Pipeline.answer_shelved(
            tmp_path, about="show:1421", answer="keep", envelope=asked, run_id="just_recorded"
        )

    def test_the_answer_is_still_a_run(self, answered, tmp_path):
        assert (run_path(tmp_path, "just_recorded", "manifest.json")).exists()

    def test_the_record_is_written(self, answered, tmp_path):
        [record] = _consultations(run_path(tmp_path, "just_recorded", "trajectory.jsonl"))
        assert record["chose"] == "keep" and record["answers_run_id"] == "monday"

    def test_it_leaves_the_inbox(self, answered, tmp_path):
        assert Pipeline.shelved(tmp_path) == []


class TestWhichQuestionIsBeingAnswered:
    def test_naming_neither_is_refused(self, asked, tmp_path):
        with pytest.raises(CallerFacingError) as exc:
            Pipeline.answer_shelved(tmp_path, answer="keep", envelope=asked)
        assert "neither about= nor record_id=" in str(exc.value)

    def test_a_question_that_was_never_shelved_is_refused(self, asked, tmp_path):
        with pytest.raises(CallerFacingError) as exc:
            Pipeline.answer_shelved(tmp_path, about="show:9", answer="keep", envelope=asked)
        assert "No question is outstanding" in str(exc.value)

    def test_two_outstanding_under_one_name_are_refused(self, tmp_path):
        env = RunEnvelope(run_dir=tmp_path)
        _asking().run({}, envelope=env, run_id="monday")
        _asking().run({}, envelope=env, run_id="tuesday")

        with pytest.raises(CallerFacingError) as exc:
            Pipeline.answer_shelved(tmp_path, about="show:1421", answer="keep", envelope=env)
        assert "2 questions are outstanding" in str(exc.value)

    def test_the_record_id_names_one_exactly(self, tmp_path):
        env = RunEnvelope(run_dir=tmp_path)
        _asking().run({}, envelope=env, run_id="monday")
        _asking().run({}, envelope=env, run_id="tuesday")
        wanted = next(q for q in Pipeline.shelved(tmp_path) if q.run_id == "tuesday")

        Pipeline.answer_shelved(tmp_path, record_id=wanted.record_id, answer="keep", envelope=env)
        assert [q.run_id for q in Pipeline.shelved(tmp_path)] == ["monday"]

    def test_a_run_asking_about_several_things_shelves_each(self, tmp_path):
        env = RunEnvelope(run_dir=tmp_path)
        _asking(("show:1", "show:2", "show:3")).run({}, envelope=env, run_id="monday")
        assert [q.about for q in Pipeline.shelved(tmp_path)] == ["show:1", "show:2", "show:3"]

    def test_answering_one_leaves_the_others(self, tmp_path):
        env = RunEnvelope(run_dir=tmp_path)
        _asking(("show:1", "show:2", "show:3")).run({}, envelope=env, run_id="monday")
        Pipeline.answer_shelved(tmp_path, about="show:2", answer="keep", envelope=env)
        assert [q.about for q in Pipeline.shelved(tmp_path)] == ["show:1", "show:3"]


class TestWhatTheAnswerIs:
    def test_a_refusal_is_recorded_declined(self, asked, tmp_path):
        Pipeline.answer_shelved(
            tmp_path, about="show:1421", answer=None, envelope=asked, run_id="w"
        )
        [record] = _consultations(run_path(tmp_path, "w", "trajectory.jsonl"))
        assert record["resolution"] == "declined" and record["response"] is None

    def test_an_answer_that_is_none_of_the_options_keeps_what_was_said(self, asked, tmp_path):
        Pipeline.answer_shelved(
            tmp_path, about="show:1421", answer="ask me next month", envelope=asked, run_id="w"
        )
        [record] = _consultations(run_path(tmp_path, "w", "trajectory.jsonl"))
        assert record["chose"] is None and "next month" in str(record["response"])

    def test_a_reply_the_project_built_is_taken_as_it_is(self, asked, tmp_path):
        Pipeline.answer_shelved(
            tmp_path,
            about="show:1421",
            answer=Reply("gave up", chose="drop", answered_at="2026-08-23T18:14:00Z"),
            envelope=asked,
            run_id="w",
        )
        [record] = _consultations(run_path(tmp_path, "w", "trajectory.jsonl"))
        assert record["chose"] == "drop"


class TestTwoWorkersCannotBothAnswerOne:
    def test_a_held_shelf_refuses_the_second(self, asked, tmp_path):
        claim_shelf(run_path(tmp_path, "monday"))

        with pytest.raises(CallerFacingError) as exc:
            Pipeline.answer_shelved(tmp_path, about="show:1421", answer="keep", envelope=asked)
        assert "No question is outstanding" in str(exc.value)

    def test_a_refusal_before_anything_ran_puts_the_shelf_back(self, asked, tmp_path):
        """An acting pipeline whose node needs a model refuses while the claim can go back."""
        from simple_agents import LLMNode

        from schemas import Answer

        acting = Pipeline(
            [LLMNode(lambda i, c: "x", output_schema=Answer, node_id="act", max_output_tokens=10)],
            budget=BUDGET,
        )
        with pytest.raises(CallerFacingError):
            Pipeline.answer_shelved(
                tmp_path,
                about="show:1421",
                answer="keep",
                pipeline=acting,
                envelope=asked,
                run_id="w",
            )
        assert [q.about for q in Pipeline.shelved(tmp_path)] == ["show:1421"]
        assert not (run_path(tmp_path, "w", "trajectory.jsonl")).exists()

    def test_work_that_fails_does_not_put_the_question_back(self, asked, tmp_path):
        """The answer is recorded, so a shelf saying it is outstanding would contradict it."""
        acting = Pipeline(
            [
                Deterministic(
                    lambda inputs, ctx: (_ for _ in ()).throw(RuntimeError("no")),
                    node_id="act",
                    output_schema=None,
                )
            ],
            budget=BUDGET,
        )
        with pytest.raises(RuntimeError):
            Pipeline.answer_shelved(
                tmp_path,
                about="show:1421",
                answer="keep",
                pipeline=acting,
                envelope=asked,
                run_id="w",
            )
        assert Pipeline.shelved(tmp_path) == []
        [record] = _consultations(run_path(tmp_path, "w", "trajectory.jsonl"))
        assert record["chose"] == "keep"

    def test_the_failed_run_says_so_in_its_own_manifest(self, asked, tmp_path):
        acting = Pipeline(
            [
                Deterministic(
                    lambda inputs, ctx: (_ for _ in ()).throw(RuntimeError("no")),
                    node_id="act",
                    output_schema=None,
                )
            ],
            budget=BUDGET,
        )
        with pytest.raises(RuntimeError):
            Pipeline.answer_shelved(
                tmp_path,
                about="show:1421",
                answer="keep",
                pipeline=acting,
                envelope=asked,
                run_id="w",
            )
        body = json.loads((run_path(tmp_path, "w", "manifest.json")).read_text())
        assert body["outcome"] == "error"


class TestAnsweringSeveralAtOnce:
    """One run's shelf holds every question it left, so two answers reach for one file."""

    def test_four_answers_to_four_questions_all_land(self, tmp_path):
        import threading

        env = RunEnvelope(run_dir=tmp_path)
        subjects = ["a1", "a2", "a3", "a4"]
        _asking(tuple(subjects)).run({}, envelope=env, run_id="monday")

        filed: list[str] = []

        def file_one(n: int, subject: str) -> None:
            Pipeline.answer_shelved(
                tmp_path, about=subject, answer="keep", envelope=env, run_id=f"w{n}"
            )
            filed.append(subject)

        threads = [threading.Thread(target=file_one, args=(n, s)) for n, s in enumerate(subjects)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(filed) == subjects
        assert Pipeline.shelved(tmp_path) == []

    def test_one_answering_record_each(self, tmp_path):
        import threading

        env = RunEnvelope(run_dir=tmp_path)
        subjects = ["a1", "a2", "a3"]
        _asking(tuple(subjects)).run({}, envelope=env, run_id="monday")
        threads = [
            threading.Thread(
                target=Pipeline.answer_shelved,
                args=(tmp_path,),
                kwargs={"about": s, "answer": "keep", "envelope": env, "run_id": f"w{n}"},
            )
            for n, s in enumerate(subjects)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(
            len(_consultations(run_path(tmp_path, f"w{n}", "trajectory.jsonl"))) == 1
            for n in range(len(subjects))
        )
        assert not (tmp_path / "monday" / "shelved.claimed.json").exists()


class TestWhatIsOnDisk:
    def test_the_shelf_names_its_format(self, asked, tmp_path):
        body = json.loads(run_path(tmp_path, "monday", SHELF_NAME).read_text())
        assert body["format_version"] and body["run_id"] == "monday"

    def test_the_file_goes_when_the_last_question_is_answered(self, asked, tmp_path):
        Pipeline.answer_shelved(tmp_path, about="show:1421", answer="keep", envelope=asked)
        assert not run_path(tmp_path, "monday", SHELF_NAME).exists()
