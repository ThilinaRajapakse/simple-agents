"""What the prompt page reads, against the record it reads it from.

The page is the first surface that shows a builder what their project sends to a model. What
makes it possible is that a run keeps the fixed text and each value's length apart, so the
words the project wrote can be told from the data that filled them. That reconstruction is
what most of this file is about: it has to be exact, and where it cannot be it has to say so
rather than draw a prompt with no values in it.

`tests/test_view_runs.py` runs the page's own script over the same fixture, and
`tests/test_view_comments_e2e.py` drives a selection thread through a live server.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents.view.prompts import fill_of, pieces_of, read_prompts

FIXTURES = Path(__file__).parent / "fixtures" / "view_projects"
PROMPTED = FIXTURES / "prompted"


def _held():
    from simple_agents.view.assemble import assemble

    return assemble(PROMPTED)["prompts"]


@pytest.fixture(scope="module")
def held():
    return _held()


def _step(held, node_id):
    return next(s for s in held["pipelines"][0]["steps"] if s["node_id"] == node_id)


class TestTheFillIsRecovered:
    """The words the project wrote, told apart from the data that filled them."""

    def test_a_template_splits_into_its_fixed_text_and_its_gaps(self):
        assert pieces_of("Plan {days} days in {city}.") == [
            ("fixed", "Plan "),
            ("gap", "days"),
            ("fixed", " days in "),
            ("gap", "city"),
            ("fixed", "."),
        ]

    def test_a_doubled_brace_is_one_fixed_brace(self):
        """`{{` is how a JSON example is written into a prompt, and it is not a gap."""
        assert pieces_of('Return {{"city": "Paris"}}.') == [
            ("fixed", "Return "),
            ("fixed", "{"),
            ("fixed", '"city": "Paris"'),
            ("fixed", "}"),
            ("fixed", "."),
        ]

    def test_the_value_is_taken_at_the_length_the_record_kept(self):
        pieces = fill_of(
            {
                "role": "user",
                "template": "Plan {days} days.",
                "values": [{"name": "days", "chars": 1}],
            },
            "Plan 4 days.",
        )
        assert pieces == [
            {"kind": "fixed", "text": "Plan "},
            {
                "kind": "value",
                "name": "days",
                "text": "4",
                "clipped": False,
                "chars": 1,
                "capped_from": None,
                "origin": None,
                "parts": None,
                "section": False,
            },
            {"kind": "fixed", "text": " days."},
        ]

    def test_a_value_carrying_the_next_fixed_words_is_still_split_right(self):
        """The length decides where a value ends, so a value quoting the template survives."""
        pieces = fill_of(
            {
                "role": "user",
                "template": "Say {what} to the traveller.",
                "values": [{"name": "what", "chars": len(" to the traveller. Twice")}],
            },
            "Say  to the traveller. Twice to the traveller.",
        )
        assert [p for p in pieces if p["kind"] == "value"][0]["text"] == (
            " to the traveller. Twice"
        )

    def test_a_section_is_measured_from_the_values_inside_it(self):
        """A section records its own text and values rather than a length, so it is summed."""
        pieces = fill_of(
            {
                "role": "user",
                "template": "Answer.\n\n{context}\n\n{q}",
                "values": [
                    {
                        "name": "context",
                        "template": "Notes:\n{notes}",
                        "values": [{"name": "notes", "chars": 5}],
                    },
                    {"name": "q", "chars": 4},
                ],
            },
            "Answer.\n\nNotes:\nhello\n\nwhen",
        )
        values = [p for p in pieces if p["kind"] == "value"]
        assert [v["name"] for v in values] == ["context", "q"]
        assert values[0]["text"] == "Notes:\nhello"
        assert values[0]["section"] is True

    def test_a_joined_section_runs_to_the_next_fixed_words(self):
        """A list of parts records how many there are and not what they wrote."""
        pieces = fill_of(
            {
                "role": "user",
                "template": "Places:\n{places}\n\nPlan them.",
                "values": [{"name": "places", "parts": 2, "each": "- {name}"}],
            },
            "Places:\n- Vieux Lyon\n- Parc\n\nPlan them.",
        )
        held = [p for p in pieces if p["kind"] == "value"][0]
        assert held["text"] == "- Vieux Lyon\n- Parc"
        assert held["parts"] == 2

    def test_text_that_does_not_line_up_is_refused_rather_than_guessed(self):
        """The run's redaction can replace text after the lengths were recorded."""
        assert (
            fill_of(
                {
                    "role": "user",
                    "template": "Key is {key}.",
                    "values": [{"name": "key", "chars": 40}],
                },
                "Key is [redacted:secret_type].",
            )
            is None
        )

    def test_every_message_in_the_fixture_is_recovered_exactly(self):
        """The join of the pieces is the message the run sent, byte for byte."""
        read = 0
        for trajectory in sorted(PROMPTED.rglob("trajectory.jsonl")):
            for line in trajectory.open(encoding="utf-8"):
                record = json.loads(line)
                if record.get("record_type") != "model_call":
                    continue
                inputs = record.get("inputs") or {}
                assembly = inputs.get("assembly")
                if not assembly:
                    continue
                for held, sent in zip(assembly["messages"], inputs["messages"]):
                    if held.get("carried") or "blocks" in held:
                        continue
                    pieces = fill_of(held, sent["content"])
                    assert pieces is not None, held
                    assert "".join(p["text"] for p in pieces) == sent["content"]
                    read += 1
        assert read > 10, "the fixture stopped exercising the reconstruction"


class TestWhatARunDidNotKeep:
    """Redaction and sampling reach the assembly, and the page says so rather than drawing
    a prompt that looks like it has no values in it."""

    def test_a_redacted_message_is_shown_whole_and_says_why(self):
        from simple_agents.view.prompts import _message, _notes

        held = _message(
            {
                "role": "user",
                "template": "The key is {key}.",
                "values": [{"name": "key", "chars": 40}],
            },
            "The key is [redacted:secret_type].",
        )
        assert held["redacted"] is True
        assert held["pieces"] == [{"kind": "fixed", "text": "The key is [redacted:secret_type]."}]
        note = _notes({"filled": {"messages": [held]}})[0]
        assert note["kind"] == "redacted"
        assert "shown whole" in note["says"]

    def test_a_run_that_kept_no_payloads_says_that_in_place_of_the_words(self):
        from simple_agents.view.prompts import _filled, _notes

        held = _filled({"inputs": {"type": "not_recorded", "reason": "sampling"}})
        assert held == {"kept_nothing": "sampling", "messages": []}
        note = _notes({"filled": held})[0]
        assert note["kind"] == "kept_nothing"
        assert "sampling" in note["says"]

    def test_content_that_is_not_text_is_named_rather_than_drawn(self):
        """`Prompt.blocks` sends an image or a document; the page names what went."""
        from simple_agents.view.prompts import _message

        held = _message(
            {"role": "user", "blocks": [{"kind": "image"}, {"template": "Read it.", "values": []}]},
            "",
        )
        assert held["blocks"] == ["image", "text"]
        assert held["pieces"] == []
        assert held["origin"] == "written in the project's code"

    def test_a_call_built_from_a_conversation_carries_no_prompt(self):
        """Every turn of a loop after the first, which is why the page reads the first."""
        from simple_agents.view.prompts import _filled

        assert _filled({"inputs": {"messages": [{"role": "user", "content": "hi"}]}}) is None


class TestWhatEachStepSays:
    def test_only_the_steps_that_call_a_model_are_listed(self, held):
        assert [s["node_id"] for s in held["pipelines"][0]["steps"]] == [
            "read_request",
            "shortlist",
            "plan_days",
            "reply_in_voice",
            "house_style",
        ]

    def test_the_steps_with_no_prompt_between_them_are_counted(self, held):
        """A value handed on through a fixed step has not gone straight out of one prompt."""
        assert held["pipelines"][0]["gaps"] == {
            "read_request": 1,
            "shortlist": 1,
            "house_style": 1,
        }

    def test_a_capped_value_says_what_never_reached_the_model(self, held):
        step = _step(held, "read_request")
        note = next(n for n in step["notes"] if n["kind"] == "cut")
        assert "220 characters" in note["says"] and "never reached it" in note["says"]
        value = next(
            p
            for message in step["filled"]["messages"]
            for p in message["pieces"]
            if p.get("name") == "notes"
        )
        assert value["capped_from"] > value["chars"]
        assert value["origin"] == "the traveller_files store"

    def test_a_message_an_end_user_wrote_says_where_it_came_from(self, held):
        messages = _step(held, "reply_in_voice")["filled"]["messages"]
        assert messages[0]["origin"] == "set outside the code: the app's settings screen"
        assert [m["origin"] for m in messages[1:3]] == ["carried from the conversation"] * 2
        assert messages[3]["origin"] == "written in the project's code"

    def test_a_step_whose_instruction_is_data_says_how_many_it_sent(self, held):
        step = _step(held, "house_style")
        assert step["distinct"] == 2
        assert "2 different ones" in next(n["says"] for n in step["notes"] if n["kind"] == "varies")

    def test_a_step_with_more_instructions_than_the_record_lists_says_so(self):
        """A manifest lists the twenty most used and carries the true count beside them."""
        from simple_agents.view.prompts import _instruction_notes

        few = _instruction_notes({"distinct": 2, "observed": {"a": 1, "b": 1}})[0]["says"]
        assert (
            few == "The instruction comes from the run: 2 different ones across 2 recorded calls."
        )

        many = _instruction_notes({"distinct": 25, "observed": {str(i): 10 for i in range(20)}})[0][
            "says"
        ]
        assert "25 different ones" in many
        assert "the 20 the record lists were sent on 200 calls" in many

    def test_a_fan_out_is_one_step_carrying_how_many_items_ran(self, held):
        assert _step(held, "shortlist")["filled"]["items"] == 2

    def test_a_loop_carries_the_turns_after_the_prompt(self, held):
        filled = _step(held, "plan_days")["filled"]
        assert filled["answered"]["n"] == 1
        assert filled["total"] >= 1
        assert any(turn["called"] for turn in [filled["answered"], *filled["turns"]])

    def test_the_agreed_rule_is_joined_to_the_step_it_names(self, held):
        assert _step(held, "read_request")["decision"]["name"] == "what_the_reader_is_told"
        assert _step(held, "house_style")["decision"] is None

    def test_the_counts_are_what_the_page_puts_in_its_title(self, held):
        assert held["counts"] == {
            "prompts": 5,
            "pipelines": 1,
            "unagreed": 3,
            "unfilled": 0,
            "cut": 1,
            "varies": 1,
            "changed": 0,
        }


class TestWhatOneCallCost:
    def test_a_replayed_call_reports_what_the_recording_measured(self):
        """A replay is answered from a file in no time, and the timestamps bracket that."""
        from simple_agents.view.prompts import _took

        assert (
            _took(
                {
                    "replayed": True,
                    "recorded_duration_ms": 852,
                    "started_at": "2026-09-04T08:28:17.000Z",
                    "ended_at": "2026-09-04T08:28:17.001Z",
                }
            )
            == 852.0
        )

    def test_a_live_call_is_timed_by_its_own_stamps(self):
        from simple_agents.view.prompts import _took

        assert (
            _took(
                {
                    "replayed": False,
                    "started_at": "2026-09-04T08:28:17.000Z",
                    "ended_at": "2026-09-04T08:28:18.500Z",
                }
            )
            == 1500.0
        )

    def test_a_token_class_the_backend_did_not_measure_is_said_to_be_missing(self):
        """vLLM without its reporting flag records two classes as unknown, not as zero."""
        from simple_agents.view.prompts import _tokens

        assert _tokens(
            {
                "tokens": {
                    "input_uncached": 64,
                    "input_cache_read": 0,
                    "input_cache_write": {"type": "unknown"},
                    "output": 12,
                }
            }
        ) == (
            76,
            True,
        )
        assert _tokens(
            {
                "tokens": {
                    "input_uncached": 64,
                    "input_cache_read": 0,
                    "input_cache_write": 0,
                    "output": 12,
                }
            }
        ) == (76, False)


class TestAThreadOnAPromptElsewhereOnThePage:
    """`P3-79`: a prompt address reaches two other surfaces, and both read it as a step id.

    The finding on an open thread named the address raw, and its button offered to open a
    step called `reply_in_voice#words-9c1f0a2b3c4d`, which is no step.
    """

    def test_an_address_reads_as_words_rather_than_as_an_address(self):
        from simple_agents.view.findings import _address_name

        named = lambda at: _address_name({}, at)  # noqa: E731 - one call, read in place
        assert named("prompt:trip/plan") == "the prompt for plan"
        assert named("prompt:trip/plan#notes") == "the notes value in the prompt for plan"
        assert named("prompt:trip/plan#words-3f9a1c2d5e70") == "words in the prompt for plan"
        assert named("trip/plan") == "trip/plan"

    def test_a_thread_on_a_prompt_is_read_on_the_prompts_page(self):
        from simple_agents.view.findings import _thread_target

        assert _thread_target({"at": "prompt:trip/plan#words-3f9a"}) == {"section": "prompts"}
        assert _thread_target({"at": "trip/plan"}) == {"pipeline": "trip", "node": "plan"}


class TestALoopsTurns:
    def test_the_tail_is_grouped_so_a_long_loop_stays_one_line(self):
        from simple_agents.view.prompts import TURNS_SHOWN, _turns_of

        calls = [
            {
                "sequence": i,
                "outputs": {"content": f"turn {i}"},
                "tokens": {
                    "input_uncached": 10,
                    "input_cache_read": 0,
                    "input_cache_write": 0,
                    "output": 5,
                },
                "started_at": "2026-09-04T08:00:00.000Z",
                "ended_at": "2026-09-04T08:00:01.000Z",
            }
            for i in range(1, 12)
        ]
        held = _turns_of(calls, [])
        assert held["answered"]["n"] == 1
        assert len(held["turns"]) == TURNS_SHOWN
        assert held["total"] == 10
        grouped = held["grouped"]
        assert (grouped["from"], grouped["to"], grouped["turns"]) == (6, 11, 10 - TURNS_SHOWN)
        assert grouped["tokens"] == 15 * (10 - TURNS_SHOWN)
        assert grouped["ms"] == 1000.0 * (10 - TURNS_SHOWN)

    def test_a_step_with_no_calls_reports_no_turns_rather_than_raising(self):
        """Nothing reaches it with none today; an empty list is not a reason to lose a page."""
        from simple_agents.view.prompts import _turns_of

        assert _turns_of([], []) == {"answered": None, "turns": [], "grouped": None, "total": 0}

    def test_a_question_nobody_answered_says_so(self):
        """`str(None)` reached the page as the word `None` on an unanswered consultation."""
        from simple_agents.view.prompts import _turns_of

        held = _turns_of(
            [{"sequence": 1, "outputs": {}}, {"sequence": 2, "outputs": {}}],
            [{"sequence": 3, "record_type": "consultation"}],
        )
        assert held["turns"][0]["got"][0]["text"] == "no answer was recorded"

    def test_a_loop_that_asked_a_person_says_who_answered(self):
        from simple_agents.view.prompts import _turns_of

        calls = [{"sequence": 1, "outputs": {}}, {"sequence": 2, "outputs": {}}]
        answers = [
            {"sequence": 3, "record_type": "consultation", "response": "hold it for me"},
            {
                "sequence": 4,
                "record_type": "tool_call",
                "tool_name": "book",
                "error": {"message": "the source refused"},
            },
        ]
        held = _turns_of(calls, answers)
        got = held["turns"][0]["got"]
        assert got[0] == {
            "name": "the question it asked",
            "text": "hold it for me",
            "failed": False,
            "asked_a_person": True,
        }
        # A failed call produced no output, so the line carries what failed rather than the
        # word `None`.
        assert got[1] == {
            "name": "book",
            "text": "the source refused",
            "failed": True,
            "asked_a_person": False,
        }


class TestAProjectWhoseRunsPredateTheRecord:
    """A run written before the library kept what it sent fills no step.

    The page would otherwise say a step that has run many times is read from the code, with
    nothing saying why. Built here by stripping the assembly out of a real run, which is what
    a project upgrading from an older version has on disk.
    """

    def _older(self, tmp_path):
        import shutil

        root = tmp_path / "older"
        shutil.copytree(PROMPTED, root, ignore=shutil.ignore_patterns("__pycache__"))
        for trajectory in root.rglob("trajectory.jsonl"):
            kept = []
            for line in trajectory.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                (record.get("inputs") or {}).pop("assembly", None)
                kept.append(json.dumps(record))
            trajectory.write_text("\n".join(kept) + "\n", encoding="utf-8")
        return root

    def test_the_page_reads_the_code_and_says_the_runs_carry_nothing(self, tmp_path):
        from simple_agents.view.assemble import assemble

        held = assemble(self._older(tmp_path))["prompts"]
        assert held["counts"]["unfilled"] == 5
        one = held["pipelines"][0]
        assert one["runs_read"] > 0, "the runs were not read at all"
        assert one["runs_carry_nothing"] is True
        assert one["steps"][0]["written"], "the text was not read out of the code instead"

    def test_a_project_whose_runs_do_carry_it_says_nothing_of_the_kind(self, held):
        assert held["pipelines"], "nothing was read, so this would pass on an empty page"
        assert all(not one["runs_carry_nothing"] for one in held["pipelines"])


class TestAValueTooLongForThePage:
    def test_it_is_carried_to_the_limit_and_says_how_long_it_was(self):
        from simple_agents.view.prompts import VALUE_CHARS, _message

        held = _message(
            {"role": "user", "template": "{doc}", "values": [{"name": "doc", "chars": 5_000}]},
            "x" * 5_000,
        )
        piece = held["pieces"][0]
        assert len(piece["text"]) == VALUE_CHARS
        assert piece["chars"] == 5_000 and piece["clipped"] is True

    def test_a_message_that_is_one_value_with_no_origin_says_so(self):
        from simple_agents.view.prompts import _message

        held = _message(
            {"role": "user", "template": "{doc}", "values": [{"name": "doc", "chars": 3}]},
            "abc",
        )
        assert held["origin"] == "a value the run supplied"


class TestWhereTheFillComesFrom:
    def test_each_step_names_the_run_its_prompt_was_read_in(self, held):
        steps = held["pipelines"][0]["steps"]
        assert len(steps) == 5, "the fixture's steps changed; this would pass on none"
        for step in steps:
            assert step["filled"]["run"].startswith("run_")

    def test_reading_no_runs_at_all_leaves_the_text_read_from_the_code(self):
        """`most_runs=0` is the shape of a project whose steps no run has reached."""
        from simple_agents.view.assemble import assemble

        data = assemble(PROMPTED)
        declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
        held = read_prompts(PROMPTED, declared, None, most_runs=0)
        step = held["pipelines"][0]["steps"][0]
        assert step["filled"] is None
        assert held["counts"]["unfilled"] == 5
        assert held["pipelines"][0]["runs_left"] > 0

    def test_a_run_that_records_no_pipeline_name_is_matched_by_its_shape(self):
        """Every run written before manifests carried the name, and every unregistered one."""
        from simple_agents.view.prompts import _for_this_pipeline

        class Handle:
            def __init__(self, name, shape):
                self.pipeline = name
                self.manifest = {"graph_fingerprint": shape}

        card = {"name": "trip", "fingerprint": "sha256:aaa"}
        mine = _for_this_pipeline(
            [
                Handle("trip", "sha256:aaa"),
                Handle(None, "sha256:aaa"),
                Handle("other", "sha256:aaa"),
                Handle(None, "sha256:bbb"),
            ],
            card,
        )
        assert [(h.pipeline) for h in mine] == ["trip", None]

    def test_the_text_a_step_holds_is_read_from_its_source(self, held):
        """A step no run has reached still has its words in the code."""
        written = _step(held, "read_request")["written"]
        assert [m["role"] for m in written] == ["user"]
        assert written[0]["how"] == "written"
        assert any(p.get("name") == "message" for p in written[0]["pieces"])
