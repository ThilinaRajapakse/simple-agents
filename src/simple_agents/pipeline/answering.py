"""A shelved question answered later: claiming it, reading the answer in, recording it."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from ..context import RunContext
from ..errors import CallerFacingError
from ..records.shelf import (
    HELD_ATTEMPTS,
    HELD_INTERVAL_S,
    SHELF_NAME,
    Shelf,
    ShelvedQuestion,
    claim_shelf,
    read_shelf,
)
from ..grounding import normalise_text
from ..records.trajectory import PENDING_SEQUENCE, ConsultationRecord, utc_now
from .events import RunResult


@dataclass(frozen=True)
class Answered:
    """What a shelved question's answer hands the pipeline that acts on it.

    The input the entry node of an ``answer_shelved(pipeline=...)`` pipeline reads::

        def drop_from_up_next(inputs: Answered, ctx) -> dict:
            if inputs.answer.chose == "gave up on it":
                queue.remove(inputs.about)
            return {"about": inputs.about}
    """

    about: str | None
    prompt: str
    options: list[str] | None
    answer: Any
    """What the person said, as a ``Reply``, or ``None`` where they declined."""
    asked_at: str
    asking_run_id: str
    asking_record_id: str


@dataclass(frozen=True)
class AnsweredQuestion:
    """What :meth:`Pipeline.answer_shelved` did: the run it wrote and what that run produced."""

    run_id: str
    """The run the answer was recorded in, which is not the run that asked."""
    record_id: str
    question: ShelvedQuestion
    result: RunResult


def _claim_the_question(
    run_dir: Any, *, about: str | None, record_id: str | None
) -> tuple[ShelvedQuestion, Path, Shelf]:
    """Find the question this answer is for and take the shelf it is on.

    A shelf another worker holds is renamed away, so a question on it is neither listed nor
    answerable until they are done. Two people answering two different questions from one
    background run reach for that one file and neither is a conflict with the other, so a
    lookup that finds nothing is tried again for up to ``HELD_ATTEMPTS * HELD_INTERVAL_S``
    seconds. A question that really is not outstanding costs that wait before the refusal.

    A call naming no question, and one whose name matches two, are refused straight away:
    looking again cannot change either.
    """
    _refuse_an_unnamed_question(about, record_id)
    for remaining in range(HELD_ATTEMPTS - 1, -1, -1):
        matches = _outstanding_matching(run_dir, about=about, record_id=record_id)
        if matches:
            _refuse_an_ambiguous_question(matches, about=about, record_id=record_id)
            found, root = matches[0]
            try:
                return found, root, claim_shelf(root)
            except CallerFacingError:
                # Taken between the look and the claim, which is the race this waits out.
                pass
        if not remaining:
            named = f"record_id={record_id!r}" if record_id else f"about={about!r}"
            raise CallerFacingError(
                f"No question is outstanding under {run_dir} for {named}. Either it was never "
                f"shelved, or it has already been answered.\n"
                f"Pipeline.shelved(run_dir) lists what is outstanding, and each one carries "
                f"the `about` and the `record_id` to answer it by."
            )
        time.sleep(HELD_INTERVAL_S)
    raise AssertionError("unreachable")


def _refuse_an_unnamed_question(about: str | None, record_id: str | None) -> None:
    """Refuse a call that does not say which question is being answered."""
    if about is not None or record_id is not None:
        return
    raise CallerFacingError(
        "Pipeline.answer_shelved() was given neither about= nor record_id=, so nothing says "
        "which question is being answered.\n"
        "Pass the `about` the question was asked under: "
        "Pipeline.answer_shelved(run_dir, about='show:1421', answer='gave up on it'). "
        "Pipeline.shelved(run_dir) lists what is outstanding."
    )


def _refuse_an_ambiguous_question(
    matches: list[tuple[ShelvedQuestion, Path]], *, about: str | None, record_id: str | None
) -> None:
    """Refuse an ``about`` two outstanding questions share, rather than taking the first."""
    if len(matches) < 2 or record_id is not None:
        return
    where = ", ".join(f"{q.run_id}/{q.record_id}" for q, _ in matches[:4])
    raise CallerFacingError(
        f"{len(matches)} questions are outstanding for about={about!r}, so this answer would "
        f"be filed against whichever was found first: {where}.\n"
        f"Name one exactly: Pipeline.answer_shelved(run_dir, record_id=..., answer=...)."
    )


def _outstanding_matching(
    run_dir: Any, *, about: str | None, record_id: str | None
) -> list[tuple[ShelvedQuestion, Path]]:
    """Every outstanding question under ``run_dir`` that this answer could be for."""
    found: list[tuple[ShelvedQuestion, Path]] = []
    for child in sorted(Path(run_dir).glob(f"**/{SHELF_NAME}")):
        shelf = read_shelf(child.parent)
        for question in shelf.questions if shelf is not None else []:
            named = record_id is None or question.record_id == record_id
            subject = about is None or question.about == about
            if named and subject:
                found.append((question, child.parent))
    return found


def _read_a_filed_answer(answer: Any, options: list[str] | None) -> Any:
    """What the person said, as the ``Reply`` a record and a route both read."""
    from ..builtins.consult import Reply

    if answer is None or isinstance(answer, Reply):
        return answer
    text = str(answer)
    folded = normalise_text(text)
    chose = next((o for o in options or () if normalise_text(o) == folded), None)
    return Reply(text, chose=chose, options=options or ())


def _record_the_answer(run: RunContext, question: ShelvedQuestion, reply: Any) -> str:
    """Write the answering consultation, naming the question and the run that asked it."""
    record_id = run.new_record_id()
    now = utc_now()
    run.emit(
        ConsultationRecord(
            record_id=record_id,
            run_id=run.run_id,
            parent_id=run.run_id,
            sequence=PENDING_SEQUENCE,
            started_at=question.asked_at,
            ended_at=now,
            prompt=question.prompt,
            options=question.options,
            about=question.about,
            asked=True,
            response=reply,
            chose=getattr(reply, "chose", None),
            resolution="declined" if reply is None else "answered",
            blocking=False,
            answers=question.record_id,
            answers_run_id=question.run_id,
            item_index=question.item_index,
        )
    )
    return record_id
