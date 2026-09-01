"""Questions a finished run left for somebody to answer later.

A run whose channel returns :class:`~simple_agents.builtins.Shelved` finishes with the question
on record and no answer. The question is written here, beside the run's manifest, so a surface
can list what is outstanding without reading every trajectory under the run directory.

``Pipeline.shelved`` reads these and ``Pipeline.answer_shelved`` files an answer against one.
Those two are the whole surface, so putting the shelf somewhere other than the run directory is
a change to this module and to nothing else.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import CallerFacingError

__all__ = [
    "SHELF_FORMAT_VERSION",
    "SHELF_NAME",
    "ShelvedQuestion",
    "Shelf",
    "read_shelf",
    "write_shelf",
    "claim_shelf",
    "release_shelf",
    "settle_shelf",
]

SHELF_FORMAT_VERSION = "0.1"

SHELF_NAME = "shelved.json"
_CLAIMED_NAME = "shelved.claimed.json"


@dataclass(frozen=True)
class ShelvedQuestion:
    """One question a run left outstanding, and where it was asked.

    ``about`` is the stable name the caller gave the subject, which is what an answer arriving
    later is matched on, and is ``None`` where the call named none. ``record_id`` and ``run_id``
    name the consultation that asked, so the answering record can point back at it.
    """

    run_id: str
    record_id: str
    node_id: str
    prompt: str
    asked_at: str
    about: str | None = None
    options: list[str] | None = None
    reason: str | None = None
    item_index: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "record_id": self.record_id,
            "node_id": self.node_id,
            "prompt": self.prompt,
            "asked_at": self.asked_at,
            "about": self.about,
            "options": self.options,
            "reason": self.reason,
            "item_index": self.item_index,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> ShelvedQuestion:
        return cls(
            run_id=str(raw["run_id"]),
            record_id=str(raw["record_id"]),
            node_id=str(raw.get("node_id") or ""),
            prompt=str(raw.get("prompt") or ""),
            asked_at=str(raw.get("asked_at") or ""),
            about=raw.get("about"),
            options=raw.get("options"),
            reason=raw.get("reason"),
            item_index=raw.get("item_index"),
        )


@dataclass(frozen=True)
class Shelf:
    """Everything one run left outstanding."""

    run_id: str
    questions: list[ShelvedQuestion] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "format_version": SHELF_FORMAT_VERSION,
            "run_id": self.run_id,
            "questions": [q.to_json() for q in self.questions],
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Shelf:
        return cls(
            run_id=str(raw.get("run_id") or ""),
            questions=[ShelvedQuestion.from_json(q) for q in (raw.get("questions") or [])],
        )

    def without(self, record_id: str) -> Shelf:
        """This shelf with one question answered and taken off it."""
        return Shelf(
            run_id=self.run_id,
            questions=[q for q in self.questions if q.record_id != record_id],
        )


def write_shelf(run_root: Path, shelf: Shelf, redaction: Any = None) -> Path | None:
    """Write what a run left outstanding, or remove the file where nothing is.

    The question is text a node composed, so it goes through the run's redaction rules like
    every other recorded value. Returns where it went, or ``None`` where nothing was written.
    """
    path = Path(run_root) / SHELF_NAME
    if not shelf.questions:
        path.unlink(missing_ok=True)
        return None
    body: Any = shelf.to_json()
    if redaction is not None:
        body, _ = redaction.redact(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written beside and renamed into place. A surface lists what is outstanding while answers
    # are being filed, and a reader that caught a write half done would fail on the JSON rather
    # than on anything the caller did.
    beside = path.with_name(f"{path.name}.writing")
    beside.write_text(
        json.dumps(body, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    os.replace(beside, path)
    return path


def read_shelf(run_root: Path) -> Shelf | None:
    """What one run left outstanding, or ``None`` where it left nothing.

    Read rather than tested first: another worker claiming this shelf renames it away, and a
    reader that had already decided it was there would fail on the open.
    """
    try:
        raw = (Path(run_root) / SHELF_NAME).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return Shelf.from_json(json.loads(raw))


HELD_ATTEMPTS = 20
"""How many times a caller looks again for a shelf another worker is holding."""

HELD_INTERVAL_S = 0.01
"""How long to wait between those attempts."""


def claim_shelf(run_root: Path) -> Shelf:
    """Take this run's shelf, so nothing else answers the same question.

    The file is renamed before anything runs. A rename is atomic on one filesystem, so two
    workers reading the same run directory cannot both answer one question and both write a
    record saying they did.

    One run's shelf holds every question that run left, and it is renamed away while a worker
    holds it, so a caller looking for a different question on it finds nothing and looks again.
    """
    path = Path(run_root) / SHELF_NAME
    claimed = Path(run_root) / _CLAIMED_NAME
    try:
        os.rename(path, claimed)
    except FileNotFoundError:
        raise CallerFacingError(
            f"There are no shelved questions in {run_root}. Either the run shelved nothing, or "
            f"every question it shelved has been answered, or another worker holds the shelf.\n"
            f"Pipeline.shelved(run_dir) lists what is outstanding."
        ) from None
    try:
        return Shelf.from_json(json.loads(claimed.read_text(encoding="utf-8")))
    except Exception:
        release_shelf(run_root)
        raise


def release_shelf(run_root: Path) -> None:
    """Put a claimed shelf back, for an answer that was refused before anything ran."""
    try:
        os.replace(Path(run_root) / _CLAIMED_NAME, Path(run_root) / SHELF_NAME)
    except FileNotFoundError:
        return


def settle_shelf(run_root: Path, shelf: Shelf, redaction: Any = None) -> None:
    """Write what is left of a claimed shelf and drop the claim."""
    write_shelf(run_root, shelf, redaction)
    Path(run_root, _CLAIMED_NAME).unlink(missing_ok=True)
