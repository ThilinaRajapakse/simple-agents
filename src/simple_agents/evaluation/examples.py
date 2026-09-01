"""Labeled examples, the splits they fall into, and the checks over both.

The library ships the container and the checks. The project supplies the examples, their
labels, and where the split falls, because what counts as ground truth is task-specific. No
dataset ships with the library.

An example whose ``expected`` is ``Unknown`` is one where the information is genuinely absent.
A set with none of those scores an agent that always guesses higher than one that stops when
the value is not there, because abstaining costs it a rollout and no example rewards it
(FT-04).

Two examples cannot share an identifier: :class:`ExampleSet` refuses that at construction, so
the same example appearing in two splits is impossible rather than checked for. What is left
for :meth:`ExampleSet.contamination` is the same content under two identifiers.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..builtins.search import tokens
from ..errors import ConfigurationError
from ..schema import Unknown, encode_answer
from .answer_key import Criteria, decode_answer_key
from .end_user import EndUser, Fact, decode_end_user, encode_end_user

__all__ = [
    "Example",
    "ExampleSet",
    "NearestPair",
    "Overlap",
    "ContaminationReport",
    "EndUser",
    "Fact",
    "METADATA_CEILING",
]

METADATA_CEILING = 64 * 1024
"""How large one metadata value may be, encoded, before a results file leaves it out.

Metadata travels into the results file so any key in it can group a figure, which copies it
once per example into every file an evaluation writes. A value above this is named in that
example's ``metadata_omitted`` instead. Nothing about the example changes, and a scoring rule
still reads the value: this bounds what is written, not what is held.
"""


@dataclass(frozen=True, slots=True)
class Example:
    """One labeled input, and the split it belongs to.

    ``inputs`` is what the pipeline is run on. ``expected`` is the correct answer, or
    ``Unknown`` where the information is genuinely absent::

        Example(id="q1", inputs={"question": "Who founded Kirkwall?"},
                expected="Alan Reid", split="dev")

        Example(id="q29", inputs={"question": "When did Kirkwall open its Leeds depot?"},
                expected=Unknown(reason="the collection does not give a date"),
                split="held_out", source="collection:kirkwall-history")

    ``expected_by_node`` labels the output of a named node, keyed by ``node_id``, and needs no
    entry for every node::

        Example(id="q1", inputs={"question": "Who founded Kirkwall?"},
                expected="Alan Reid", split="dev",
                expected_by_node={"hunt": "Alan Reid"})

    ``memory`` is what the agent already remembers when this example starts. Each rollout gets
    its own store holding exactly this, so what it remembers is part of the example::

        Example(id="q4", inputs={"question": "Find me something to read"},
                expected="The Left Hand of Darkness", split="held_out",
                memory={"preferred_length": "prefers books under 300 pages"})

    ``conversation`` is what has already been said when this example starts, and ``turns`` is
    what the end user says next, one run each, scored on the last (`docs/evaluation.md` §13)::

        Example(id="q4", inputs={"question": "What else did she write?"},
                expected="The Left Hand of Darkness", split="held_out",
                conversation=[{"role": "user", "content": "Who wrote The Dispossessed?"},
                              {"role": "assistant", "content": "Ursula K. Le Guin"}])

        Example(id="q9", inputs={"question": "I need a book"},
                expected="The Left Hand of Darkness", split="held_out",
                turns=["Something under 400 pages", "Not grimdark"])

    ``end_user`` is who the agent is answering, and
    ``EvalSuite.run(end_user=SimulatedEndUser(...))`` gives it to a model that answers as them.
    A value the agent has to obtain goes in ``knows``, where a scoring rule reads it too
    (:class:`EndUser`)::

        Example(id="q4", inputs={"question": "Find me something to read"},
                expected="The Left Hand of Darkness", split="held_out",
                end_user="Reads a lot of grimdark, has read all of Abercrombie, wants "
                         "something under 400 pages, and finds questions about difficulty "
                         "useless and says so.")

        Example(id="inv-12", inputs={"invoice": "..."}, expected="CC-4471", split="held_out",
                end_user=EndUser(
                    "An operations manager. Brusque, and short of time.",
                    knows={"cost_centre": Fact("the cost centre is CC-4471",
                                               value="CC-4471", disclose="on_ask")}))

        Example(id="inv-13", inputs={"invoice": "..."}, expected="CC-4471", split="held_out",
                end_user={"requester": EndUser("A junior analyst filing the invoice."),
                          "approver": EndUser("Her director. Signs off, asks one question.")})

    The third form is one per answerer, keyed by what each ``consult`` tool declares in
    ``reaches``. A plain string means ``EndUser(it)``.

    ``source`` is where the example came from, which a contamination check reads. ``metadata``
    is anything else the project carries, and every key in it can group a figure::

        Example(id="q1", inputs={...}, expected="shelve", split="dev",
                metadata={"genre": "fantasy", "reader": "r14"})

        results.grouped("genre")["fantasy"].metrics["accuracy"].interval.point
    """

    id: str
    inputs: Any
    expected: Any
    split: str
    source: str | None = None
    expected_by_node: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, str] = field(default_factory=dict)
    conversation: list[dict] = field(default_factory=list)
    turns: list = field(default_factory=list)
    end_user: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "end_user", decode_end_user(self.end_user))
        if not str(self.id).strip():
            raise ConfigurationError(
                "An Example was given an empty id. Results are keyed on the id, and a "
                "regression is traced back to a specific example through it. Pass "
                "id='q1' or whatever the project's own identifier is."
            )
        if not str(self.split).strip():
            raise ConfigurationError(
                f"Example {self.id!r} was given no split. Every prompt change made after "
                f"looking at an example fits the agent to that example, so a number reported "
                f"over those same examples measures memorization (FT-02).\n"
                f"Pass split='dev' for examples that may be inspected freely, and "
                f"split='held_out' for the ones that may not."
            )

    @property
    def expects_absence(self) -> bool:
        """Whether the correct answer to this example is that the information is not there."""
        return isinstance(self.expected, Unknown)

    @property
    def absent_parts(self) -> tuple[str, ...]:
        """The conditions in this example's answer key whose right answer is absence.

        Empty unless ``expected`` is a :class:`~simple_agents.evaluation.Criteria` key with a
        criterion declaring ``expects_absence``. An example carrying one holds an absent case
        in part of a record, which is what FT-04 reads where the whole answer is a value.
        """
        return self.expected.absent_parts if isinstance(self.expected, Criteria) else ()

    def results_entry(self) -> dict[str, Any]:
        """What a results file records about this example, beside the rollouts that ran.

        ``label`` is ``expected`` where it is a single value, so a figure can be grouped by the
        right answer without the example set beside the results file. A key with parts, an
        admissible set, or a tolerance has no single value and carries no ``label``::

            results.examples["q1"]              # {'split': 'dev', 'label': 'shelve', ...}
            results.grouped("label")["shelve"]

        ``metadata`` is what the project carried, less any value over
        :data:`METADATA_CEILING` when encoded, whose key is named in ``metadata_omitted``.
        """
        metadata: dict[str, Any] = {}
        omitted: list[str] = []
        for key, value in self.metadata.items():
            try:
                encoded = json.dumps(value, default=str)
            except (TypeError, ValueError):
                encoded = str(value)
            if len(encoded.encode("utf-8")) > METADATA_CEILING:
                omitted.append(str(key))
            else:
                metadata[str(key)] = value
        entry: dict[str, Any] = {
            "split": self.split,
            "expects_absence": self.expects_absence,
            "absent_parts": list(self.absent_parts),
            "source": self.source,
            "metadata": metadata,
            "metadata_omitted": sorted(omitted),
        }
        if isinstance(self.expected, (str, int, float, bool)):
            entry["label"] = self.expected
        return entry

    @property
    def text(self) -> str:
        """The example's own words, for comparing one example against another.

        Every string anywhere in ``inputs``, in order, joined by spaces. Keys and structure
        are left out, so two examples phrased alike compare alike whatever shape the inputs
        have.
        """
        return " ".join(_strings(self.inputs))

    def to_json(self) -> dict[str, Any]:
        """One line of the JSONL file. ``Unknown`` encodes as its tagged object."""
        record: dict[str, Any] = {
            "id": self.id,
            "split": self.split,
            "inputs": self.inputs,
            "expected": encode_answer(self.expected),
        }
        if self.source is not None:
            record["source"] = self.source
        if self.expected_by_node:
            record["expected_by_node"] = {
                node_id: encode_answer(value) for node_id, value in self.expected_by_node.items()
            }
        if self.memory:
            record["memory"] = dict(self.memory)
        if self.conversation:
            record["conversation"] = [dict(message) for message in self.conversation]
        if self.turns:
            record["turns"] = list(self.turns)
        if self.end_user:
            record["end_user"] = encode_end_user(self.end_user)
        if self.metadata:
            record["metadata"] = self.metadata
        return record

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Example:
        """Rebuild an example from one line of the file."""
        missing = [key for key in ("id", "inputs", "expected", "split") if key not in raw]
        if missing:
            raise ConfigurationError(
                f"An example is missing {', '.join(missing)}. Every example needs an id, its "
                f"inputs, its expected answer, and the split it belongs to. An answer that is "
                f'genuinely absent is written {{"type": "unknown", "reason": "..."}}.'
            )
        return cls(
            id=str(raw["id"]),
            inputs=raw["inputs"],
            expected=decode_answer_key(raw["expected"]),
            split=str(raw["split"]),
            source=raw.get("source"),
            expected_by_node={
                str(node_id): decode_answer_key(value)
                for node_id, value in (raw.get("expected_by_node") or {}).items()
            },
            memory={str(key): str(value) for key, value in (raw.get("memory") or {}).items()},
            conversation=[dict(message) for message in (raw.get("conversation") or [])],
            turns=list(raw.get("turns") or []),
            end_user=decode_end_user(raw.get("end_user")),
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass(frozen=True, slots=True)
class Overlap:
    """Two examples in different splits that a contamination check flagged.

    ``similarity`` is the word overlap between them, between 0 and 1. A ``shared_source`` pair
    carries it too, and it is below the threshold there: the pair was flagged for its source
    rather than for its wording.
    """

    left: str
    right: str
    left_split: str
    right_split: str
    kind: str
    detail: str
    similarity: float | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "left_split": self.left_split,
            "right_split": self.right_split,
            "kind": self.kind,
            "similarity": self.similarity,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class NearestPair:
    """Two examples in different splits, and how much of their wording they share.

    What a builder is shown when they are asked what makes two examples the same example
    twice. It carries both texts, since the question is about the requests rather than about
    their identifiers::

        for pair in examples.nearest_cross_split(n=5):
            print(pair.describe())

    ``shared_source`` names the ``source`` both sides came from, and is ``None`` where they
    came from different ones or declared none.
    """

    left: str
    right: str
    left_split: str
    right_split: str
    left_text: str
    right_text: str
    similarity: float
    shared_source: str | None = None

    def describe(self) -> str:
        """The pair as one block of text, for putting in front of the builder."""
        source = f", both from {self.shared_source!r}" if self.shared_source else ""
        return (
            f"{self.similarity:.0%} of their words in common{source}\n"
            f"  {self.left} ({self.left_split}): {self.left_text}\n"
            f"  {self.right} ({self.right_split}): {self.right_text}"
        )


@dataclass(frozen=True, slots=True)
class ContaminationReport:
    """What a contamination check found, and the threshold it was run at.

    ``clean`` is true when nothing was flagged. The threshold is recorded because it decides
    what counts as a near-duplicate, and that is a task decision rather than a library
    default::

        report = examples.contamination(threshold=0.8)
        if not report.clean:
            for overlap in report.pairs:
                print(overlap.detail)
    """

    threshold: float
    pairs: tuple[Overlap, ...]
    compared: int

    @property
    def clean(self) -> bool:
        return not self.pairs

    def to_record(self) -> dict[str, Any]:
        """What the results artifact stores: the finding, never the example text."""
        return {
            "threshold": self.threshold,
            "compared": self.compared,
            "clean": self.clean,
            "pairs": [pair.to_record() for pair in self.pairs],
        }


class ExampleSet:
    """The labeled examples a project evaluates against, and the splits over them.

    Construct one from examples in memory, or read the project's own file::

        examples = ExampleSet([
            Example(id="q1", inputs={"question": "..."}, expected="Leeds", split="dev"),
            Example(id="q2", inputs={"question": "..."}, expected="Alan Reid",
                    split="held_out"),
        ])
        examples = ExampleSet.from_jsonl("evals/examples.jsonl")

        examples.splits()                      # {'dev': 1, 'held_out': 1}
        examples.absent_proportion("held_out") # share whose answer is Unknown
        examples.contamination(threshold=0.8)  # near-duplicates across splits

    ``held_out`` names the split that may not be inspected, and defaults to ``"held_out"``.
    A project whose splits are called something else says so once, here::

        examples = ExampleSet(examples, held_out="test")
        examples = ExampleSet.from_jsonl("evals/examples.jsonl", held_out="test")

    The name is recorded in the results file, so a conformance check reads which split the
    reported number came from rather than guessing from the name (FT-02).

    Construction refuses an empty set and a repeated identifier, so no example is in two
    splits and results keyed on the id are unambiguous.
    """

    def __init__(self, examples: Iterable[Example], *, held_out: str = "held_out") -> None:
        self.held_out = held_out
        self._examples: list[Example] = list(examples)
        if not self._examples:
            raise ConfigurationError(
                "An ExampleSet was constructed with no examples. An evaluation over nothing "
                "reports a number computed from nothing. Pass the labeled examples, or read "
                "them with ExampleSet.from_jsonl('evals/examples.jsonl')."
            )
        wrong = [e for e in self._examples if not isinstance(e, Example)]
        if wrong:
            raise ConfigurationError(
                f"An ExampleSet was given {type(wrong[0]).__name__}, not an Example. Wrap each "
                f"one: Example(id='q1', inputs={{'question': '...'}}, expected='Leeds', "
                f"split='dev')."
            )
        ids = [e.id for e in self._examples]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        if repeated:
            raise ConfigurationError(
                f"This example set has more than one example called "
                f"{', '.join(repeated)}. Results and per-example metrics are keyed on the id, "
                f"so a repeat reports as one example, and the same id in two splits is the "
                f"contamination a split exists to prevent (FT-03).\n"
                f"Give each example a distinct id."
            )
        self._by_id = {e.id: e for e in self._examples}

    # -- reading --------------------------------------------------------------------------

    def __iter__(self) -> Iterator[Example]:
        return iter(self._examples)

    def __len__(self) -> int:
        return len(self._examples)

    def __contains__(self, example_id: object) -> bool:
        return example_id in self._by_id

    def get(self, example_id: str) -> Example:
        """The example with this id, or a refusal saying how many there are."""
        try:
            return self._by_id[example_id]
        except KeyError:
            raise ConfigurationError(
                f"No example called {example_id!r} in this set of {len(self._examples)}. "
                f"Check the id against the file the set was read from."
            ) from None

    def entering(self, sliced: Any) -> ExampleSet:
        """This set with each example's ``inputs`` replaced by what the slice's first node takes.

        A rung of a back-to-front evaluation runs one step on ideal inputs, and the ideal input
        to a step is the correct output of the step before it, which
        ``Example.expected_by_node`` already carries::

            rung = pipeline.slice(start="judge")
            suite = EvalSuite(rung, examples.entering(rung), answer="answer", matches=exact)

        An example carrying no label for the node before it is left out, the way one carrying
        no label for a node is left out of that node's accuracy. Where the first node has more
        than one predecessor, ``inputs`` is a :class:`~simple_agents.graph.Join` of their
        labels, which is what that node receives in the whole pipeline.

        A slice starting at the pipeline's own first node cut nothing off it, so every
        example's ``inputs`` is what it already was.

        Raises :class:`~simple_agents.errors.ConfigurationError` for a pipeline that is not a
        slice, and for a set where no example carries a label for what was cut.
        """
        from ..graph import Join

        cut = _cut_before(sliced)
        if not cut:
            return ExampleSet(list(self._examples), held_out=self.held_out)

        found = [
            replace(example, inputs=_ideal_input(example, cut, Join, sliced.graph.entry))
            for example in self._examples
            if all(node_id in example.expected_by_node for node_id in cut)
        ]
        if not found:
            raise ConfigurationError(
                f"This slice starts at {sliced.graph.entry!r}, which takes its input from "
                f"{', '.join(repr(c) for c in cut)} in the pipeline it was sliced out of, and "
                f"no example in this set carries a label for "
                f"{'that node' if len(cut) == 1 else 'all of those nodes'}.\n"
                f"Label them with Example(expected_by_node={{{cut[0]!r}: ...}}), which is what "
                f"the rung is run on, or build the example set for this rung by hand and pass "
                f"it instead."
            )
        return ExampleSet(found, held_out=self.held_out)

    def splits(self) -> dict[str, int]:
        """How many examples are in each split, in the order the splits first appear."""
        counts: dict[str, int] = {}
        for example in self._examples:
            counts[example.split] = counts.get(example.split, 0) + 1
        return counts

    def in_split(self, split: str) -> list[Example]:
        """The examples in one split, in the order they were declared."""
        found = [e for e in self._examples if e.split == split]
        if not found:
            raise ConfigurationError(
                f"This example set has no split called {split!r}. It has: "
                f"{', '.join(f'{name} ({n})' for name, n in self.splits().items())}."
            )
        return found

    def absent_proportion(self, split: str) -> float:
        """The share of one split whose expected answer is ``Unknown``.

        A held-out split with none of these scores a careful agent and one that always
        guesses identically, because there is no example where guessing is wrong and
        abstaining is right (FT-04). An absent case living in one condition of an answer key is
        :attr:`Example.absent_parts` and is not counted here, and FT-04 reads both.
        """
        examples = self.in_split(split)
        return sum(1 for e in examples if e.expects_absence) / len(examples)

    def content_hash(self) -> str:
        """An identifier for exactly this set of examples and labels.

        Recorded in a results file, so a comparison between two evaluations can tell whether
        they were computed over the same examples. Changing any example changes it; reordering
        the set does not.
        """
        canonical = json.dumps(
            [e.to_json() for e in sorted(self._examples, key=lambda e: e.id)],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
        return "ex_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    # -- contamination --------------------------------------------------------------------

    def contamination(self, *, threshold: float) -> ContaminationReport:
        """Examples in different splits that are the same example twice.

        ``threshold`` is the word overlap at or above which two examples count as
        near-duplicates, between 0 and 1, and has no default: what counts as too similar
        depends on the task
        (FT-03). Start at 0.8 and read what it flags::

            report = examples.contamination(threshold=0.8)
            report.clean          # False when anything was flagged
            report.pairs          # each with both ids, both splits, and the similarity

        Compares every pair of examples in different splits on the words in their inputs, and
        flags any pair sharing a ``source``. Examples inside one split are not compared: a
        repeated dev example is waste rather than contamination.

        A pair can be flagged for both reasons, and is then reported once per reason. The two
        take different fixes: a ``near_duplicate`` is the same content under two ids, so one
        side goes, and a ``shared_source`` pair needs the whole source assigned to one split.
        """
        if not 0.0 <= threshold <= 1.0:
            raise ConfigurationError(
                f"contamination(threshold={threshold}) takes a word-overlap fraction between "
                f"0 and 1. 1.0 flags only identical wording and 0.0 flags every pair. Start "
                f"at 0.8 and read what it flags."
            )

        vocabulary = {e.id: set(tokens(e.text)) for e in self._examples}
        pairs: list[Overlap] = []
        compared = 0

        for i, left in enumerate(self._examples):
            for right in self._examples[i + 1 :]:
                if left.split == right.split:
                    continue
                compared += 1
                similarity = _jaccard(vocabulary[left.id], vocabulary[right.id])
                if similarity >= threshold:
                    pairs.append(
                        Overlap(
                            left=left.id,
                            right=right.id,
                            left_split=left.split,
                            right_split=right.split,
                            kind="near_duplicate",
                            similarity=round(similarity, 4),
                            detail=(
                                f"{left.id} ({left.split}) and {right.id} ({right.split}) "
                                f"share {similarity:.0%} of their words, at or above the "
                                f"threshold of {threshold:.0%}."
                            ),
                        )
                    )
                if left.source is not None and left.source == right.source:
                    pairs.append(
                        Overlap(
                            left=left.id,
                            right=right.id,
                            left_split=left.split,
                            right_split=right.split,
                            kind="shared_source",
                            similarity=round(similarity, 4),
                            detail=(
                                f"{left.id} ({left.split}) and {right.id} ({right.split}) "
                                f"were both drawn from {left.source!r}, so what was learned "
                                f"from one applies to the other."
                            ),
                        )
                    )

        return ContaminationReport(threshold=threshold, pairs=tuple(pairs), compared=compared)

    # -- files ----------------------------------------------------------------------------

    def nearest_cross_split(self, *, n: int = 5) -> tuple[NearestPair, ...]:
        """The examples in different splits whose wording is closest, ranked, with their text.

        ``contamination`` answers whether anything crosses a threshold, and returns nothing at
        all on a set that is clean. This returns the closest pairs whatever their similarity,
        which is what a builder reads when they are asked which of them are the same example
        twice::

            for pair in examples.nearest_cross_split(n=5):
                print(pair.describe())

        Compares every pair of examples in different splits, as ``contamination`` does.
        Examples inside one split are not compared. A set with one split returns nothing.
        """
        if n < 1:
            raise ConfigurationError(
                f"nearest_cross_split(n={n}) returns the n closest pairs and n is at least 1."
            )

        vocabulary = {e.id: set(tokens(e.text)) for e in self._examples}
        pairs: list[NearestPair] = []
        for i, left in enumerate(self._examples):
            for right in self._examples[i + 1 :]:
                if left.split == right.split:
                    continue
                shared = (
                    left.source if left.source is not None and left.source == right.source else None
                )
                pairs.append(
                    NearestPair(
                        left=left.id,
                        right=right.id,
                        left_split=left.split,
                        right_split=right.split,
                        left_text=left.text,
                        right_text=right.text,
                        similarity=round(_jaccard(vocabulary[left.id], vocabulary[right.id]), 4),
                        shared_source=shared,
                    )
                )
        pairs.sort(key=lambda pair: (-pair.similarity, pair.left, pair.right))
        return tuple(pairs[:n])

    @classmethod
    def from_jsonl(cls, path: str | os.PathLike[str], *, held_out: str = "held_out") -> ExampleSet:
        """Read a set from the project's own file, one JSON object per line.

        ``held_out`` names the split that may not be inspected, as on the constructor. The
        file records each example's split and not which of them is held out.
        """
        target = Path(path)
        if not target.exists():
            raise ConfigurationError(
                f"No example set at {target}. An evaluation needs labeled examples, and the "
                f"library ships none: what counts as a correct answer is a decision about the "
                f"task. Write the file, one JSON object per line, or build the set in code "
                f"with ExampleSet([Example(...), ...])."
            )
        examples: list[Example] = []
        for number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                examples.append(Example.from_json(json.loads(line)))
            except json.JSONDecodeError as exc:
                raise ConfigurationError(
                    f"{target}:{number} is not a readable example: {exc}. An example set is "
                    f"one JSON object per line, each with id, inputs, expected and split."
                ) from exc
        return cls(examples, held_out=held_out)

    def to_jsonl(self, path: str | os.PathLike[str]) -> Path:
        """Write the set out, one JSON object per line, sorted by id."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            json.dumps(e.to_json(), ensure_ascii=False, default=str)
            for e in sorted(self._examples, key=lambda e: e.id)
        ]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target


def _jaccard(left: set[str], right: set[str]) -> float:
    """Shared words over total distinct words. 0 when both are empty."""
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _strings(value: Any) -> Iterator[str]:
    """Every string anywhere inside a value, in order."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _cut_before(sliced: Any) -> tuple[str, ...]:
    """The nodes that fed the slice's first node in the pipeline it was sliced out of."""
    sliced_from = getattr(sliced, "slice_of", None)
    if sliced_from is None:
        raise ConfigurationError(
            "entering() was given a pipeline that is not a slice, so there is nothing it was "
            "cut off from and no node to take the examples' inputs from.\n"
            "Pass a slice: examples.entering(pipeline.slice(start='judge'))."
        )
    entry = sliced.graph.entry
    return tuple(edge.source for edge in sliced_from.cut_edges if edge.target == entry)


def _ideal_input(example: Example, cut: tuple[str, ...], join: Any, entry: str) -> Any:
    """What the slice's first node is handed for one example, from the labels for what fed it."""
    if len(cut) == 1:
        return example.expected_by_node[cut[0]]
    return join({node_id: example.expected_by_node[node_id] for node_id in cut}, node_id=entry)
