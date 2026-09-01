"""A judgement about one thing, and the file a project keeps them in.

A label records what was decided, why, and who or what decided it. That last part is the one
a project loses: a labelling pass that turns out to have been wrong leaves nothing saying what
made the call, and a later reader has the label and no way to weigh it.

``docs/evaluation.md`` §1.5 is the surface of record. The library reads and writes the file and
holds no opinion about the verdicts in it: whether a label is right is not checkable, and
nothing here implies otherwise.

Labels are not an example set. ``ExampleSet`` holds the inputs an evaluation runs the pipeline
over; a label is a judgement about something that already exists, which is what a verification
pass over candidate examples produces and what a person reviewing a finished run produces.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..errors import ConfigurationError
from ..schema import decode_answer, encode_answer
from ..records.trajectory import utc_now

__all__ = ["Label", "read_labels", "read_every_label", "write_labels"]

HUMAN = "human"


@dataclass(frozen=True, slots=True)
class Label:
    """One judgement, and what made it.

    ``id`` names the thing judged, ``verdict`` is the judgement, and ``decided_by`` is the
    person or the model that made it::

        Label(id="q29", verdict="unanswerable", decided_by="human",
              reason="Black_Death#11 puts Marseille in France, so the pool does answer it")

    A judgement a model made through the run envelope names the run, so the model, the prompt,
    the cost and the whole exchange are recoverable from it::

        Label(id="q29", verdict="answerable", decided_by="mistral-medium-2604",
              run_id="run_20260807T140312Z_a1b3", reason="cites Black_Death#11")

    ``decided_by`` is required, because a label with no decider cannot be weighed when the pass
    that made it is questioned. Use ``"human"`` where a person decided.

    ``metadata`` carries anything else the project wants kept beside the verdict: the values
    that were checked, the page they came from, the size that was read. ``about`` is the
    library's own: on a judgement of one answer it holds the example, the rollout, the
    condition, the question and the material (``docs/evaluation.md`` §12), and it is empty on a
    label about an example.

    A verdict is anything a file can hold, including an :class:`~simple_agents.Unknown` where
    the decider reported absence, written as the tagged object
    ``docs/trajectory-format.md`` §5.1 defines and read back as ``Unknown``::

        Label(id="q29", verdict=outcome.value.answerable, decided_by="human")

    ``decided_at`` defaults to now, in UTC. Reading a file back keeps what the file says.
    """

    id: str
    verdict: Any
    decided_by: str
    reason: str = ""
    run_id: str | None = None
    decided_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)
    about: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise ConfigurationError(
                "A Label was given an empty id. The id is what joins a label to the thing it "
                "judges, so a label without one cannot be applied to anything. Pass the "
                "example's id, or whatever the project identifies the judged thing by: "
                "Label(id='q29', verdict='unanswerable', decided_by='human')."
            )
        if not str(self.decided_by).strip():
            raise ConfigurationError(
                f"Label {self.id!r} was given no decided_by. A label decides what every later "
                f"number is measured against, and one that does not say who or what made the "
                f"call cannot be weighed when it is questioned.\n"
                f"Pass decided_by='human' where a person judged it, or the model identifier "
                f"where a model did, with run_id naming the run that made the call."
            )

    def to_json(self) -> dict[str, Any]:
        """One line of the file. Keys the label does not carry are left out."""
        record: dict[str, Any] = {
            "id": self.id,
            "verdict": encode_answer(self.verdict),
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
        }
        if self.reason:
            record["reason"] = self.reason
        if self.run_id is not None:
            record["run_id"] = self.run_id
        if self.metadata:
            record["metadata"] = encode_answer(self.metadata)
        if self.about:
            record["about"] = encode_answer(self.about)
        return record

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Label:
        """Rebuild a label from one line of the file."""
        missing = [key for key in ("id", "verdict", "decided_by") if key not in raw]
        if missing:
            raise ConfigurationError(
                f"A label is missing {', '.join(missing)}. Every line needs id, verdict and "
                f"decided_by; reason, run_id, decided_at and metadata are optional. The line "
                f"read: {json.dumps(raw)[:200]}"
            )
        return cls(
            id=str(raw["id"]),
            verdict=decode_answer(raw["verdict"]),
            decided_by=str(raw["decided_by"]),
            reason=str(raw.get("reason", "")),
            run_id=raw.get("run_id"),
            decided_at=str(raw.get("decided_at") or utc_now()),
            metadata=decode_answer(dict(raw.get("metadata") or {})),
            about=decode_answer(dict(raw.get("about") or {})),
        )


def read_labels(path: str | os.PathLike[str]) -> dict[str, Label]:
    """Every label in the file, keyed by the id it judges::

        labels = read_labels("evals/labels.jsonl")
        labels["q29"].decided_by

    The last line wins where an id appears twice, so re-labelling is appending a line rather
    than editing one and the earlier judgement stays in the file. A path that does not exist
    gives an empty dict, which is what a project has before its first label.

    Raises :class:`~simple_agents.errors.ConfigurationError` on a line that is not readable,
    naming the line number.
    """
    return {label.id: label for label in _labels_in(Path(path))}


def _labels_in(target: Path) -> Iterator[Label]:
    """Every label the file holds, in the order it holds them.

    The walk both readers share. What separates them is what they do with two lines naming one
    id: a correction, or two people who disagreed.
    """
    if not target.exists():
        return
    for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                f"{target}:{number} is not a readable label: {exc}. A label file is one JSON "
                f"object per line, each with id, verdict and decided_by."
            ) from exc
        if not isinstance(raw, dict):
            raise ConfigurationError(
                f"{target}:{number} holds {type(raw).__name__} rather than an object. A label "
                f"file is one JSON object per line, each with id, verdict and decided_by."
            )
        yield Label.from_json(raw)


def read_every_label(path: str | os.PathLike[str]) -> dict[str, list[Label]]:
    """Every label in the file, keyed by the id it judges, all of them::

        by_id = read_every_label("evals/labels.jsonl")
        [label.verdict for label in by_id["q29"]]     # ['spam', 'spam', 'not_spam']

    Reach for this where several people judged one thing and the disagreement is the signal.
    :func:`read_labels` keeps the last line per id, which is a correction replacing an earlier
    judgement; this keeps them all, in the order the file holds them, which is several
    judgements standing together.

    A path that does not exist gives an empty dict.

    Raises :class:`~simple_agents.errors.ConfigurationError` on a line that is not readable,
    naming the line number.
    """
    found: dict[str, list[Label]] = {}
    for label in _labels_in(Path(path)):
        found.setdefault(label.id, []).append(label)
    return found


def write_labels(
    path: str | os.PathLike[str], labels: Iterable[Label], *, append: bool = False
) -> Path:
    """Write labels to the file, one JSON object per line::

        write_labels("evals/labels.jsonl", verdicts)
        write_labels("evals/labels.jsonl", [reviewed], append=True)

    ``append=True`` adds to what is there, which is how a session that labels five more keeps
    the ones before it. Without it the file is replaced, and a judgement the file held and the
    new labels do not is gone. Read the file first and pass what it held where the earlier
    judgements are still wanted.

    Returns the path written, and creates the parent directory where it does not exist.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(label.to_json(), ensure_ascii=False) for label in labels]
    with target.open("a" if append else "w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(line + "\n")
    return target
