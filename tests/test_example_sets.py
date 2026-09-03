"""The example-set container, and the contamination check over it.

Every set here is handcrafted with a property the test already knows, which is the only way a
check over example sets can be verified: over real data the assertion would be that the code
agrees with itself.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from simple_agents import ConfigurationError, Unknown, decode_answer
from simple_agents.evaluation import Example, ExampleSet


def example(
    example_id: str,
    question: str,
    expected: object = "Leeds",
    split: str = "dev",
    source: str | None = None,
) -> Example:
    return Example(
        id=example_id,
        inputs={"question": question},
        expected=expected,
        split=split,
        source=source,
    )


# -- construction -------------------------------------------------------------------------


def test_splits_are_counted_in_declaration_order() -> None:
    examples = ExampleSet(
        [
            example("q1", "Where does Kirkwall ship from?"),
            example("q2", "Who founded Kirkwall?", split="held_out"),
            example("q3", "What does Northgate charge?", split="held_out"),
        ]
    )

    assert examples.splits() == {"dev": 1, "held_out": 2}
    assert len(examples) == 3
    assert "q2" in examples
    assert [e.id for e in examples.in_split("held_out")] == ["q2", "q3"]


def test_an_unknown_split_is_refused_naming_the_splits_that_exist() -> None:
    examples = ExampleSet([example("q1", "Where does Kirkwall ship from?")])

    with pytest.raises(ConfigurationError) as raised:
        examples.in_split("test")

    assert "no split called 'test'" in str(raised.value)
    assert "dev (1)" in str(raised.value)


def test_a_repeated_identifier_is_refused() -> None:
    """The same id in two splits is the contamination a split exists to prevent."""
    with pytest.raises(ConfigurationError) as raised:
        ExampleSet(
            [
                example("q1", "Where does Kirkwall ship from?"),
                example("q1", "Where does Kirkwall ship from?", split="held_out"),
            ]
        )

    assert "more than one example called q1" in str(raised.value)
    assert "FT-03" in str(raised.value)


def test_an_empty_set_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        ExampleSet([])

    assert "no examples" in str(raised.value)


def test_an_example_with_no_split_is_refused() -> None:
    with pytest.raises(ConfigurationError) as raised:
        Example(id="q1", inputs={"question": "..."}, expected="Leeds", split="")

    assert "FT-02" in str(raised.value)


def test_a_missing_example_reports_the_size_of_the_set() -> None:
    examples = ExampleSet([example("q1", "Where does Kirkwall ship from?")])

    with pytest.raises(ConfigurationError) as raised:
        examples.get("q9")

    assert "set of 1" in str(raised.value)


# -- absence ------------------------------------------------------------------------------


def test_absent_proportion_counts_the_examples_whose_answer_is_unknown() -> None:
    examples = ExampleSet(
        [
            example("q1", "Where does Kirkwall ship from?", split="held_out"),
            example("q2", "Who founded Northgate?", split="held_out"),
            example(
                "q3",
                "When did Kirkwall open its Leeds depot?",
                expected=Unknown(reason="the collection gives no date"),
                split="held_out",
            ),
            example(
                "q4",
                "What is Northgate's annual revenue?",
                expected=Unknown(reason="the collection gives no figure"),
                split="held_out",
            ),
        ]
    )

    assert examples.absent_proportion("held_out") == 0.5
    assert examples.get("q3").expects_absence is True
    assert examples.get("q1").expects_absence is False


# -- contamination ------------------------------------------------------------------------


def test_the_same_question_in_two_splits_is_flagged() -> None:
    examples = ExampleSet(
        [
            example("dev1", "Which retailer ships from Leeds?"),
            example("held1", "Which retailer ships from Leeds?", split="held_out"),
        ]
    )

    report = examples.contamination(threshold=0.8)

    assert report.clean is False
    assert len(report.pairs) == 1
    pair = report.pairs[0]
    assert {pair.left, pair.right} == {"dev1", "held1"}
    assert pair.kind == "near_duplicate"
    assert pair.similarity == 1.0


def test_a_rephrasing_is_flagged_and_an_unrelated_question_is_not() -> None:
    """Two examples of nine words sharing eight of them, against one sharing none."""
    examples = ExampleSet(
        [
            example("dev1", "Which retailer ships trousers from the Leeds depot on Monday"),
            example(
                "held1",
                "Which retailer ships trousers from the Leeds depot today",
                split="held_out",
            ),
            example("held2", "How much does Northgate charge for returns", split="held_out"),
        ]
    )

    flagged = {p.left for p in examples.contamination(threshold=0.7).pairs} | {
        p.right for p in examples.contamination(threshold=0.7).pairs
    }

    assert flagged == {"dev1", "held1"}


def test_the_threshold_decides_and_is_reported() -> None:
    examples = ExampleSet(
        [
            example("dev1", "Which retailer ships trousers from the Leeds depot on Monday"),
            example(
                "held1",
                "Which retailer ships trousers from the Leeds depot today",
                split="held_out",
            ),
        ]
    )

    loose = examples.contamination(threshold=0.7)
    strict = examples.contamination(threshold=0.95)

    assert loose.clean is False
    assert strict.clean is True
    assert strict.threshold == 0.95
    assert strict.compared == 1


def test_two_examples_drawn_from_one_source_are_flagged_however_they_are_worded() -> None:
    examples = ExampleSet(
        [
            example("dev1", "Where does Kirkwall ship from?", source="doc:kirkwall"),
            example(
                "held1",
                "How long does Kirkwall allow for returns?",
                split="held_out",
                source="doc:kirkwall",
            ),
        ]
    )

    report = examples.contamination(threshold=0.8)

    assert [p.kind for p in report.pairs] == ["shared_source"]
    assert "doc:kirkwall" in report.pairs[0].detail


def test_examples_inside_one_split_are_not_compared() -> None:
    """A repeated dev example is waste, not contamination."""
    examples = ExampleSet(
        [
            example("dev1", "Which retailer ships from Leeds?"),
            example("dev2", "Which retailer ships from Leeds?"),
            example("held1", "How much does Northgate charge for returns?", split="held_out"),
        ]
    )

    report = examples.contamination(threshold=0.8)

    assert report.clean is True
    assert report.compared == 2


def test_a_threshold_outside_zero_to_one_is_refused() -> None:
    examples = ExampleSet([example("q1", "Where does Kirkwall ship from?")])

    with pytest.raises(ConfigurationError) as raised:
        examples.contamination(threshold=80)

    assert "between 0 and 1" in str(raised.value)


def test_the_report_records_the_threshold_it_ran_at() -> None:
    """What counts as a near-duplicate is a task decision, so the figure travels with it."""
    examples = ExampleSet(
        [
            example("dev1", "Which retailer ships from Leeds?"),
            example("held1", "Which retailer ships from Leeds?", split="held_out"),
        ]
    )

    record = examples.contamination(threshold=0.8).to_record()

    assert record["threshold"] == 0.8
    assert record["clean"] is False
    assert record["pairs"][0]["left_split"] != record["pairs"][0]["right_split"]


# -- identity and files -------------------------------------------------------------------


def test_the_content_hash_survives_reordering_and_changes_with_a_label() -> None:
    first = ExampleSet([example("q1", "Where from?"), example("q2", "Who founded it?")])
    reordered = ExampleSet([example("q2", "Who founded it?"), example("q1", "Where from?")])
    relabelled = ExampleSet(
        [example("q1", "Where from?", expected="Bristol"), example("q2", "Who founded it?")]
    )

    assert first.content_hash() == reordered.content_hash()
    assert first.content_hash() != relabelled.content_hash()


def test_a_set_round_trips_through_a_file_with_absence_intact(tmp_path: Path) -> None:
    original = ExampleSet(
        [
            example("q1", "Where does Kirkwall ship from?", source="doc:kirkwall"),
            example(
                "q2",
                "When did it open the Leeds depot?",
                expected=Unknown(reason="the collection gives no date"),
                split="held_out",
            ),
        ]
    )
    path = original.to_jsonl(tmp_path / "examples.jsonl")

    read_back = ExampleSet.from_jsonl(path)

    assert read_back.content_hash() == original.content_hash()
    assert isinstance(read_back.get("q2").expected, Unknown)
    assert read_back.get("q2").expected.reason == "the collection gives no date"
    assert read_back.get("q1").source == "doc:kirkwall"


def test_absence_is_written_as_the_tagged_object(tmp_path: Path) -> None:
    """`null` and the bare word never mean unknown, in a file as on a record."""
    path = ExampleSet([example("q1", "When?", expected=Unknown(reason="no date given"))]).to_jsonl(
        tmp_path / "examples.jsonl"
    )

    written = json.loads(path.read_text(encoding="utf-8").splitlines()[0])

    assert written["expected"] == {"type": "unknown", "reason": "no date given"}


def test_a_node_label_holding_an_absence_in_one_field_round_trips(tmp_path: Path) -> None:
    """A node is labelled with a whole output, so its absence sits in a field of one.

    The recorded output it is compared against is decoded the same way, so a matcher written
    as `output == expected` meets one shape on both sides.
    """
    original = ExampleSet(
        [
            Example(
                id="q1",
                inputs={"question": "How long is the sleeve?"},
                expected=Unknown(reason="not published"),
                split="held_out",
                expected_by_node={
                    "chase": {"source": Unknown(reason="not published"), "confirmed": False}
                },
            )
        ]
    )
    path = original.to_jsonl(tmp_path / "examples.jsonl")

    written = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert written["expected_by_node"]["chase"]["source"] == {
        "type": "unknown",
        "reason": "not published",
    }

    label = ExampleSet.from_jsonl(path).get("q1").expected_by_node["chase"]
    assert isinstance(label["source"], Unknown)
    assert label == decode_answer(
        {"source": {"type": "unknown", "reason": "not published"}, "confirmed": False}
    )


def test_a_missing_file_says_the_library_ships_no_dataset(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as raised:
        ExampleSet.from_jsonl(tmp_path / "absent.jsonl")

    assert "the library ships none" in str(raised.value)


def test_an_example_missing_a_field_names_the_field(tmp_path: Path) -> None:
    path = tmp_path / "examples.jsonl"
    path.write_text(json.dumps({"id": "q1", "inputs": {}, "split": "dev"}) + "\n")

    with pytest.raises(ConfigurationError) as raised:
        ExampleSet.from_jsonl(path)

    assert "missing expected" in str(raised.value)


def test_comparison_reads_every_string_in_the_inputs_whatever_their_shape() -> None:
    nested = Example(
        id="q1",
        inputs={"question": "Which depot", "context": ["ships from Leeds", {"note": "Monday"}]},
        expected="Leeds",
        split="dev",
    )

    assert nested.text == "Which depot ships from Leeds Monday"


def test_a_pair_at_exactly_the_threshold_is_flagged() -> None:
    """`docs/evaluation.md` §1.2 says at or above, so `threshold=1.0` flags identical wording."""
    examples = ExampleSet(
        [
            example("dev1", "Which retailer ships from Leeds?"),
            example("held1", "Which retailer ships from Leeds?", split="held_out"),
        ]
    )

    report = examples.contamination(threshold=1.0)

    assert [p.kind for p in report.pairs] == ["near_duplicate"]
    assert report.pairs[0].similarity == 1.0


def test_a_shared_source_pair_carries_the_overlap_it_measured() -> None:
    """It sits below the threshold: the pair was flagged for its source, not its wording."""
    examples = ExampleSet(
        [
            example(
                "dev1",
                "Which retailer ships from Leeds?",
                source="doc:kirkwall",
            ),
            example(
                "held1",
                "How long does Kirkwall allow for returns?",
                split="held_out",
                source="doc:kirkwall",
            ),
        ]
    )

    report = examples.contamination(threshold=0.8)

    assert [p.kind for p in report.pairs] == ["shared_source"]
    assert report.pairs[0].similarity is not None
    assert report.pairs[0].similarity < 0.8


def test_a_pair_flagged_for_both_reasons_is_reported_once_per_reason() -> None:
    """The fixes differ, so a count by kind counts each reason the split has to be redrawn."""
    examples = ExampleSet(
        [
            example("dev1", "Which retailer ships from Leeds?", source="doc:kirkwall"),
            example(
                "held1",
                "Which retailer ships from Leeds?",
                split="held_out",
                source="doc:kirkwall",
            ),
        ]
    )

    report = examples.contamination(threshold=0.8)

    assert sorted(p.kind for p in report.pairs) == ["near_duplicate", "shared_source"]
    assert {(p.left, p.right) for p in report.pairs} == {("dev1", "held1")}


# -- comparing examples whose inputs are identifiers ---------------------------------------


def _ids(example_id: str, user: str, shows: list[int], split: str) -> Example:
    """An example of the shape a recommender's are: a user and some item ids."""
    return Example(id=example_id, inputs={"user": user, "shows": shows}, expected="ok", split=split)


def test_comparison_reads_numbers_and_booleans_as_well_as_strings() -> None:
    """One project's inputs were a user id and integer item ids. Dropping the numbers left
    one word, and every pair scored 1.0 with nothing saying why."""
    example = Example(
        id="q1",
        inputs={"user": "u1", "shows": [12, 43], "seen": True, "note": None},
        expected="ok",
        split="dev",
    )

    assert example.text == "u1 12 43 True"


def test_identifier_inputs_no_longer_all_score_the_same() -> None:
    left = _ids("dev1", "u1", [12, 43, 7], "dev")
    right = _ids("held1", "u1", [12, 99], "held_out")

    (pair,) = ExampleSet([left, right]).nearest_cross_split(n=3)

    assert pair.similarity == pytest.approx(0.4)
    assert pair.measured_by == "word_overlap"


def test_a_ranking_where_every_pair_scored_alike_says_so() -> None:
    from simple_agents.errors import SimpleAgentsWarning

    same = [_ids(f"e{i}", "u1", [], "dev" if i % 2 else "held_out") for i in range(4)]

    with pytest.warns(SimpleAgentsWarning, match="Every compared pair scored"):
        ExampleSet(same).nearest_cross_split(n=3)
    with pytest.warns(SimpleAgentsWarning, match="render to the same text"):
        ExampleSet(same).contamination(threshold=0.8)


def test_a_set_where_nothing_is_alike_says_nothing() -> None:
    """Every pair at zero over texts that differ is what a clean set looks like, and is the
    answer a contamination check exists to give."""
    from simple_agents.errors import SimpleAgentsWarning

    unrelated = [
        example("dev1", "Which depot ships to Leeds"),
        example("held1", "How long is the warranty", split="held_out"),
        example("held2", "What size fits a Morris", split="held_out"),
    ]

    with warnings.catch_warnings():
        warnings.simplefilter("error", SimpleAgentsWarning)
        ExampleSet(unrelated).contamination(threshold=0.8)


def test_a_ranking_that_discriminates_says_nothing() -> None:
    from simple_agents.errors import SimpleAgentsWarning

    varied = [
        _ids("dev1", "u1", [12, 43], "dev"),
        _ids("held1", "u1", [12, 99], "held_out"),
        _ids("held2", "u1", [55, 66], "held_out"),
    ]

    with warnings.catch_warnings():
        warnings.simplefilter("error", SimpleAgentsWarning)
        ExampleSet(varied).nearest_cross_split(n=3)


def _by_position(left: Example, right: Example) -> float:
    """A measure of the project's own: how close the two users' ids are."""
    return 1.0 - abs(int(left.inputs["user"][1:]) - int(right.inputs["user"][1:])) / 10


def test_a_flat_project_measure_warns_without_blaming_the_words() -> None:
    """The measure is what produced the figure, so the text is not the explanation."""
    from simple_agents.errors import SimpleAgentsWarning

    varied = [
        _ids("dev1", "u1", [12, 43], "dev"),
        _ids("held1", "u2", [12, 99], "held_out"),
        _ids("held2", "u3", [55, 66], "held_out"),
    ]

    with pytest.warns(SimpleAgentsWarning) as raised:
        ExampleSet(varied).nearest_cross_split(n=3, similarity=lambda a, b: 0.5)

    message = str(raised[0].message)
    assert "under the similarity= this was given" in message
    assert "words" not in message


def test_a_project_measure_replaces_the_word_comparison() -> None:
    pairs = ExampleSet(
        [_ids("dev1", "u1", [1], "dev"), _ids("held1", "u4", [2], "held_out")]
    ).nearest_cross_split(n=1, similarity=_by_position)

    assert pairs[0].similarity == pytest.approx(0.7)
    assert pairs[0].measured_by == "custom"


def test_the_same_measure_is_read_by_the_gate() -> None:
    report = ExampleSet(
        [_ids("dev1", "u1", [1], "dev"), _ids("held1", "u2", [2], "held_out")]
    ).contamination(threshold=0.8, similarity=_by_position)

    assert report.measured_by == "custom"
    assert [p.kind for p in report.pairs] == ["near_duplicate"]
    assert report.to_record()["measured_by"] == "custom"


def test_a_measure_outside_zero_to_one_is_refused_naming_the_pair() -> None:
    """`threshold` is read against it and `describe()` renders it as a percentage."""
    examples = ExampleSet([_ids("dev1", "u1", [1], "dev"), _ids("held1", "u2", [2], "held_out")])

    with pytest.raises(ConfigurationError) as refusal:
        examples.nearest_cross_split(similarity=lambda a, b: 4.2)

    assert "'dev1', 'held1'" in str(refusal.value)
    assert "(cosine + 1) / 2" in str(refusal.value)


def test_a_measure_returning_something_that_is_not_a_number_is_refused() -> None:
    examples = ExampleSet([_ids("dev1", "u1", [1], "dev"), _ids("held1", "u2", [2], "held_out")])

    with pytest.raises(ConfigurationError):
        examples.nearest_cross_split(similarity=lambda a, b: "very")


def test_describe_says_what_the_figure_counts() -> None:
    examples = ExampleSet([_ids("dev1", "u1", [1], "dev"), _ids("held1", "u2", [2], "held_out")])

    (shipped,) = examples.nearest_cross_split(n=1)
    (custom,) = examples.nearest_cross_split(n=1, similarity=_by_position)

    assert "of their words in common" in shipped.describe()
    assert "similar" in custom.describe().splitlines()[0]
    assert "words" not in custom.describe().splitlines()[0]
