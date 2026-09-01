"""The label store: what a judgement records, and what happens to one that records too little.

The file is the whole surface, so most of these read and write one and assert on its contents.
Nothing here asserts that a verdict is right; the library holds no opinion about that.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import ConfigurationError, Unknown
from simple_agents.evaluation import Label, read_labels, write_labels


def test_a_label_records_what_decided_it() -> None:
    label = Label(
        id="q29",
        verdict="answerable",
        decided_by="mistral-medium-2604",
        run_id="run_20260807T140312Z_a1b3",
        reason="Black_Death#11 puts Marseille in France",
    )

    assert label.to_json()["decided_by"] == "mistral-medium-2604"
    assert label.to_json()["run_id"] == "run_20260807T140312Z_a1b3"


def test_a_label_with_no_decider_is_refused() -> None:
    """The field whose absence makes a questioned judgement unweighable."""
    with pytest.raises(ConfigurationError) as caught:
        Label(id="q29", verdict="answerable", decided_by="")

    assert "decided_by='human'" in str(caught.value)
    assert "run_id" in str(caught.value)


def test_a_label_with_no_id_is_refused() -> None:
    with pytest.raises(ConfigurationError) as caught:
        Label(id="  ", verdict="answerable", decided_by="human")

    assert "Label(id='q29'" in str(caught.value)


def test_decided_at_is_filled_in_and_kept_across_a_round_trip(tmp_path: Path) -> None:
    path = write_labels(
        tmp_path / "labels.jsonl", [Label(id="q1", verdict=True, decided_by="human")]
    )

    written = json.loads(path.read_text(encoding="utf-8").strip())
    assert written["decided_at"].endswith("Z")
    assert read_labels(path)["q1"].decided_at == written["decided_at"]


def test_the_optional_fields_are_left_out_rather_than_written_empty(tmp_path: Path) -> None:
    path = write_labels(
        tmp_path / "labels.jsonl", [Label(id="q1", verdict=True, decided_by="human")]
    )

    written = json.loads(path.read_text(encoding="utf-8").strip())
    assert set(written) == {"id", "verdict", "decided_by", "decided_at"}


def test_a_verdict_is_whatever_the_project_judges_with(tmp_path: Path) -> None:
    """A boolean, a string and a structure all survive the file."""
    path = write_labels(
        tmp_path / "labels.jsonl",
        [
            Label(id="a", verdict=True, decided_by="human"),
            Label(id="b", verdict="drop", decided_by="human"),
            Label(id="c", verdict={"chest_cm": 52.0}, decided_by="human"),
        ],
    )

    read = read_labels(path)
    assert read["a"].verdict is True
    assert read["b"].verdict == "drop"
    assert read["c"].verdict == {"chest_cm": 52.0}


def test_metadata_carries_what_the_project_checked(tmp_path: Path) -> None:
    path = write_labels(
        tmp_path / "labels.jsonl",
        [
            Label(
                id="https://example.test/shirt",
                verdict="correct",
                decided_by="human",
                metadata={"size": "M", "claimed": {"chest (pit-to-pit)": 52.0}},
            )
        ],
    )

    assert read_labels(path)["https://example.test/shirt"].metadata["size"] == "M"


def test_the_last_line_wins_so_relabelling_leaves_the_earlier_judgement_in_the_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "labels.jsonl"
    write_labels(path, [Label(id="q1", verdict="wrong", decided_by="human")])
    write_labels(
        path,
        [Label(id="q1", verdict="correct", decided_by="human", reason="misread the chart")],
        append=True,
    )

    assert len(path.read_text(encoding="utf-8").strip().splitlines()) == 2
    assert read_labels(path)["q1"].verdict == "correct"


def test_writing_without_append_replaces_what_was_there(tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"
    write_labels(path, [Label(id="q1", verdict="correct", decided_by="human")])
    write_labels(path, [Label(id="q2", verdict="correct", decided_by="human")])

    assert set(read_labels(path)) == {"q2"}


def test_the_parent_directory_is_created(tmp_path: Path) -> None:
    path = write_labels(
        tmp_path / "evals" / "labels.jsonl",
        [Label(id="q1", verdict=True, decided_by="human")],
    )

    assert path.exists()


def test_no_file_is_no_labels_rather_than_an_error(tmp_path: Path) -> None:
    assert read_labels(tmp_path / "labels.jsonl") == {}


def test_a_blank_line_is_skipped(tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"
    path.write_text(
        '{"id":"q1","verdict":true,"decided_by":"human"}\n\n'
        '{"id":"q2","verdict":false,"decided_by":"human"}\n',
        encoding="utf-8",
    )

    assert set(read_labels(path)) == {"q1", "q2"}


def test_an_unreadable_line_names_its_number(tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"
    path.write_text('{"id":"q1","verdict":true,"decided_by":"human"}\nnot json\n', encoding="utf-8")

    with pytest.raises(ConfigurationError) as caught:
        read_labels(path)

    assert "labels.jsonl:2" in str(caught.value)


def test_a_line_missing_a_required_field_says_which(tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"
    path.write_text('{"id":"q1","verdict":true}\n', encoding="utf-8")

    with pytest.raises(ConfigurationError) as caught:
        read_labels(path)

    assert "decided_by" in str(caught.value)


def test_a_line_that_is_not_an_object_says_what_it_holds(tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"
    path.write_text('["q1", true]\n', encoding="utf-8")

    with pytest.raises(ConfigurationError) as caught:
        read_labels(path)

    assert "list" in str(caught.value)


def test_an_absent_verdict_round_trips_as_unknown(tmp_path: Path) -> None:
    """`docs/evaluation.md` §1.5 labels a `Maybe[bool]`, so a verdict can be an absence."""
    path = tmp_path / "labels.jsonl"

    write_labels(
        path,
        [
            Label(
                id="q29",
                verdict=Unknown(reason="the pool does not say"),
                decided_by="human",
                metadata={"checked": Unknown(reason="no figure on the page")},
            )
        ],
    )

    stored = json.loads(path.read_text(encoding="utf-8").strip())
    assert stored["verdict"] == {"type": "unknown", "reason": "the pool does not say"}

    back = read_labels(path)["q29"]
    assert isinstance(back.verdict, Unknown)
    assert back.verdict.reason == "the pool does not say"
    assert isinstance(back.metadata["checked"], Unknown)


def test_an_ordinary_verdict_is_stored_as_itself(tmp_path: Path) -> None:
    path = tmp_path / "labels.jsonl"

    write_labels(path, [Label(id="q30", verdict=True, decided_by="human")])

    stored = json.loads(path.read_text(encoding="utf-8").strip())
    assert stored["verdict"] is True
    assert read_labels(path)["q30"].verdict is True
