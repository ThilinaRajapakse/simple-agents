"""What a node accepts: the type it reads, and the values that can reach it.

A node declares what it produces as `output_schema`. What it accepts is read off its
function's first parameter. Nothing has to be annotated, so every test that asserts a refusal
has a sibling asserting that the correct pipeline is built.

The refusals fire in two places and they see different things. Construction compares
declarations, so it catches an edge no run would satisfy before anything is spent. The run
compares the value itself, so it catches a predecessor that declared nothing and returned
something the node cannot read, which is the case item 8a measured completing silently.
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from simple_agents import (
    Budget,
    Deterministic,
    FakeModelClient,
    FanOutResult,
    Join,
    LLMNode,
    Loop,
    Maybe,
    NodeContext,
    NodeFailure,
    Pipeline,
    Unknown,
)
from simple_agents.errors import CallerFacingError, ConfigurationError
from simple_agents.models import fake_response
from simple_agents.shapes import accepted_by, produced_by, refutation

from conftest import RUN_ID
from schemas import Answer


class Notes(BaseModel):
    notes: Maybe[str]


class Count(BaseModel):
    how_many: int


class Docs(BaseModel):
    documents: list[str]


def _budget() -> Budget:
    return Budget(max_steps=8, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def _client() -> FakeModelClient:
    return FakeModelClient(responses=[fake_response(content='{"answer": "32 inches"}')] * 8)


def notes(inputs, ctx) -> Notes:
    return Notes(notes="the inseam is 32 inches")


def count(inputs, ctx) -> Count:
    return Count(how_many=1)


def reads_notes(inputs: Notes, ctx: NodeContext) -> str:
    return f"Check this: {inputs.notes}"


def reads_join(inputs: Join, ctx: NodeContext) -> str:
    return f"{sorted(inputs.fired)}"


def reads_failure(inputs: NodeFailure, ctx: NodeContext) -> str:
    return inputs.node_id


def unannotated(inputs, ctx):
    return {"passed": True}


class TestWhatIsRead:
    """The declaration is the annotation, and nothing else is required."""

    def test_the_first_parameter_is_what_a_node_accepts(self) -> None:
        assert accepted_by(LLMNode(reads_notes, output_schema=Answer)) is Notes

    def test_a_function_with_no_annotation_declares_nothing(self) -> None:
        assert accepted_by(Deterministic(unannotated)) is None

    def test_a_lambda_declares_nothing_rather_than_failing(self) -> None:
        assert accepted_by(Deterministic(lambda inputs, ctx: inputs, node_id="l")) is None

    def test_an_annotation_naming_something_unimportable_declares_nothing(self) -> None:
        source = (
            "from __future__ import annotations\n"
            "def fn(inputs: NotImportedAnywhere, ctx):\n"
            "    return inputs\n"
        )
        namespace: dict = {}
        exec(compile(source, "<probe>", "exec"), namespace)
        assert accepted_by(Deterministic(namespace["fn"], node_id="fn")) is None

    def test_output_schema_is_what_a_node_produces(self) -> None:
        assert produced_by(LLMNode(reads_notes, output_schema=Answer)) is Answer

    def test_a_deterministic_node_falls_back_to_its_return_annotation(self) -> None:
        assert produced_by(Deterministic(notes)) is Notes

    def test_a_prompt_function_s_return_annotation_is_not_what_the_node_produces(self) -> None:
        """It is the prompt. An `LLMNode` produces what its output schema describes."""
        assert produced_by(LLMNode(reads_notes, output_schema=Answer)) is Answer

    def test_a_pipeline_accepts_what_its_entry_node_accepts(self) -> None:
        inner = Pipeline(
            [LLMNode(reads_notes, output_schema=Answer, node_id="v", successors=[])],
            budget=_budget(),
            node_id="inner",
        )
        assert accepted_by(inner) is Notes
        assert produced_by(inner) is Answer


class TestRefutation:
    """Only a proven disagreement is one. Everything else passes."""

    @pytest.mark.parametrize(
        "expected, arriving",
        [
            (Notes, Count),
            (Notes, dict),
            (dict, Notes),
            (NodeFailure, Answer),
            (FanOutResult, Answer),
        ],
    )
    def test_a_disagreement_is_reported(self, expected, arriving) -> None:
        assert refutation(expected, arriving) is not None

    @pytest.mark.parametrize(
        "expected, arriving",
        [
            (None, Count),
            (Notes, None),
            (Notes, Notes),
            (dict, Join),
            (Notes | Count, Count),
            (Notes, Notes | Count),
        ],
    )
    def test_anything_not_shown_to_disagree_passes(self, expected, arriving) -> None:
        assert refutation(expected, arriving) is None

    def test_a_node_reading_a_join_as_a_dict_is_not_refused(self) -> None:
        """A `Join` is a Mapping and reads by key, which is what a dict annotation asks of it."""
        assert refutation(dict, Join) is None


class TestRefusedAtConstruction:
    def test_a_successor_reading_what_its_predecessor_does_not_produce(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            Pipeline(
                [
                    Deterministic(count, node_id="count"),
                    LLMNode(reads_notes, output_schema=Answer, node_id="verify", successors=[]),
                ],
                budget=_budget(),
            )
        assert "'verify'" in str(raised.value)
        assert "Notes" in str(raised.value) and "Count" in str(raised.value)

    def test_the_same_pipeline_with_the_shapes_agreeing_is_built(self) -> None:
        Pipeline(
            [
                Deterministic(notes, node_id="notes"),
                LLMNode(reads_notes, output_schema=Answer, node_id="verify", successors=[]),
            ],
            budget=_budget(),
        )

    def test_a_node_with_two_in_edges_reading_one_predecessor_s_type(self) -> None:
        with pytest.raises(ConfigurationError, match="Join"):
            Pipeline(self._two_arms(reads_notes), budget=_budget())

    def test_a_node_with_two_in_edges_reading_a_join_is_built(self) -> None:
        Pipeline(self._two_arms(reads_join), budget=_budget())

    def test_a_node_reading_a_failure_nothing_can_fail_into(self) -> None:
        with pytest.raises(ConfigurationError, match="NodeFailure"):
            Pipeline(
                [
                    Deterministic(notes, node_id="notes"),
                    Deterministic(reads_failure, node_id="handler", successors=[]),
                ],
                budget=_budget(),
            )

    def test_an_error_handler_reading_a_failure_is_built(self) -> None:
        Pipeline(
            [
                Deterministic(notes, node_id="notes", successors=["report"], on_error="handler"),
                Deterministic(reads_failure, node_id="handler", successors=["report"]),
                Deterministic(reads_join, node_id="report", successors=[]),
            ],
            budget=_budget(),
        )

    def test_a_node_that_is_both_a_successor_and_a_handler_is_not_refused(self) -> None:
        """It receives the output or a `NodeFailure`, decided by what happened, so neither
        annotation can be refuted."""
        for reader in (reads_notes, reads_failure):
            Pipeline(
                [
                    Deterministic(notes, node_id="notes", successors=["report"], on_error="report"),
                    Deterministic(reader, node_id="report", successors=[]),
                ],
                budget=_budget(),
            )

    def test_the_entry_node_is_not_checked_against_the_graph(self) -> None:
        """Nothing in the pipeline declares what was passed to `run`."""
        Pipeline(
            [LLMNode(reads_notes, output_schema=Answer, node_id="verify", successors=[])],
            budget=_budget(),
        )

    def test_an_entry_node_a_cycle_returns_to_is_not_checked_either(self) -> None:
        """It receives the run's inputs on its first execution, so one of the two things that
        can reach it is a type nothing here declares."""
        Pipeline(
            [
                Deterministic(reads_notes, node_id="draft", successors=["critique"]),
                Deterministic(
                    count,
                    node_id="critique",
                    successors=["draft", "publish"],
                    route=lambda output, ctx: "publish",
                    loop=Loop(max_iterations=2, then="publish"),
                ),
                Deterministic(unannotated, node_id="publish", successors=[]),
            ],
            budget=_budget(),
        )

    def test_a_predecessor_whose_every_declared_member_disagrees_is_refused(self) -> None:
        """Nothing the union admits is what the node reads, so no run could satisfy it."""

        def either(inputs, ctx) -> Count | dict:
            return {}

        with pytest.raises(ConfigurationError, match="Count \\| dict"):
            Pipeline(
                [
                    Deterministic(either, node_id="either"),
                    LLMNode(reads_notes, output_schema=Answer, node_id="verify", successors=[]),
                ],
                budget=_budget(),
            )

    def test_a_predecessor_declaring_a_union_is_not_refused(self) -> None:
        """One member of it is what the node reads, and which arrives is undeclared."""

        def either(inputs, ctx) -> Notes | Count:
            return Notes(notes="n")

        Pipeline(
            [
                Deterministic(either, node_id="either"),
                LLMNode(reads_notes, output_schema=Answer, node_id="verify", successors=[]),
            ],
            budget=_budget(),
        )

    def test_a_node_declaring_nothing_refuses_nothing(self) -> None:
        Pipeline(
            [
                Deterministic(unannotated, node_id="a"),
                Deterministic(unannotated, node_id="b", successors=[]),
            ],
            budget=_budget(),
        )

    def _two_arms(self, reader) -> list:
        return [
            Deterministic(
                unannotated,
                node_id="start",
                successors=["a", "b"],
                route=lambda output, ctx: ["a", "b"],
            ),
            Deterministic(notes, node_id="a", successors=["report"]),
            Deterministic(notes, node_id="b", successors=["report"]),
            Deterministic(reader, node_id="report", successors=[]),
        ]


class TestFanOut:
    """`over=` reads a key off a plain dict, which is a contract on what reaches the node."""

    def test_a_predecessor_declaring_a_model_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as raised:
            Pipeline(
                [
                    Deterministic(
                        lambda inputs, ctx: Docs(documents=["d"]),
                        node_id="load",
                        output_schema=Docs,
                    ),
                    LLMNode(
                        unannotated,
                        output_schema=Answer,
                        node_id="summarise",
                        over="documents",
                        successors=[],
                    ),
                ],
                budget=_budget(),
            )
        assert "over" in str(raised.value) and "Docs" in str(raised.value)

    def test_more_than_one_in_edge_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="Join"):
            Pipeline(
                [
                    Deterministic(
                        unannotated,
                        node_id="start",
                        successors=["a", "b"],
                        route=lambda output, ctx: ["a", "b"],
                    ),
                    Deterministic(
                        lambda inputs, ctx: {"documents": ["d"]},
                        node_id="a",
                        successors=["summarise"],
                    ),
                    Deterministic(unannotated, node_id="b", successors=["summarise"]),
                    LLMNode(
                        unannotated,
                        output_schema=Answer,
                        node_id="summarise",
                        over="documents",
                        successors=[],
                    ),
                ],
                budget=_budget(),
            )

    def test_a_predecessor_declaring_nothing_is_built(self) -> None:
        Pipeline(
            [
                Deterministic(lambda inputs, ctx: {"documents": ["d"]}, node_id="load"),
                LLMNode(
                    unannotated,
                    output_schema=Answer,
                    node_id="summarise",
                    over="documents",
                    successors=[],
                ),
            ],
            budget=_budget(),
        )

    def test_a_fan_out_node_that_is_the_entry_node_is_built(self) -> None:
        """It receives what was passed to `run`, which nothing here declares."""
        Pipeline(
            [
                LLMNode(
                    unannotated,
                    output_schema=Answer,
                    node_id="summarise",
                    over="documents",
                    successors=[],
                ),
            ],
            budget=_budget(),
        )

    def test_the_successor_of_a_fan_out_receives_a_fan_out_result(self) -> None:
        with pytest.raises(ConfigurationError, match="FanOutResult"):
            Pipeline(
                [
                    Deterministic(lambda inputs, ctx: {"documents": ["d"]}, node_id="load"),
                    LLMNode(
                        unannotated,
                        output_schema=Answer,
                        node_id="summarise",
                        successors=["report"],
                        over="documents",
                    ),
                    Deterministic(reads_notes, node_id="report", successors=[]),
                ],
                budget=_budget(),
            )


class TestRefusedAtRunTime:
    """What construction cannot see: a predecessor that declares nothing."""

    def test_a_predecessor_declaring_nothing_and_producing_the_wrong_thing(self, envelope) -> None:
        pipeline = Pipeline(
            [
                Deterministic(lambda inputs, ctx: Count(how_many=1), node_id="count"),
                LLMNode(reads_notes, output_schema=Answer, node_id="verify", successors=[]),
            ],
            budget=_budget(),
        )
        with pytest.raises(CallerFacingError) as raised:
            pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=_client())
        assert "'verify'" in str(raised.value) and "'count'" in str(raised.value)
        assert "Count" in str(raised.value)

    def test_the_run_inputs_are_checked_against_the_entry_node(self, envelope) -> None:
        pipeline = Pipeline(
            [LLMNode(reads_notes, output_schema=Answer, node_id="verify", successors=[])],
            budget=_budget(),
        )
        with pytest.raises(CallerFacingError, match="the run's inputs"):
            pipeline.run({"question": "x"}, envelope=envelope, run_id=RUN_ID, model=_client())

    def test_a_node_declaring_nothing_takes_whatever_arrives(self, envelope) -> None:
        pipeline = Pipeline(
            [
                Deterministic(lambda inputs, ctx: Count(how_many=1), node_id="count"),
                Deterministic(unannotated, node_id="report", successors=[]),
            ],
            budget=_budget(),
        )
        assert pipeline.run({}, envelope=envelope, run_id=RUN_ID).output == {"passed": True}

    def test_the_value_that_agrees_runs(self, envelope) -> None:
        pipeline = Pipeline(
            [
                Deterministic(lambda inputs, ctx: Notes(notes="n"), node_id="notes"),
                LLMNode(reads_notes, output_schema=Answer, node_id="verify", successors=[]),
            ],
            budget=_budget(),
        )
        assert pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=_client()).outcome == (
            "completed"
        )


class TestTheEntryNodeReceivesTheRunInputs:
    """Including where a cycle returns to it, which is the one shape that had no path to
    them at all."""

    def _cycle(self) -> Pipeline:
        def draft(inputs, ctx):
            return inputs if isinstance(inputs, int) else inputs["start"]

        return Pipeline(
            [
                Deterministic(draft, node_id="draft", successors=["critique"]),
                Deterministic(
                    lambda inputs, ctx: inputs + 1,
                    node_id="critique",
                    successors=["draft", "publish"],
                    route=lambda output, ctx: "draft",
                    loop=Loop(max_iterations=2, then="publish"),
                ),
                Deterministic(lambda inputs, ctx: inputs, node_id="publish", successors=[]),
            ],
            budget=_budget(),
        )

    def test_the_first_execution_reads_them(self, envelope, trajectory) -> None:
        result = self._cycle().run({"start": 10}, envelope=envelope, run_id=RUN_ID)
        assert result.output == 12

    def test_the_executions_after_it_read_the_cycle(self, envelope, trajectory) -> None:
        self._cycle().run({"start": 0}, envelope=envelope, run_id=RUN_ID)
        drafts = [
            json.loads(line)
            for line in trajectory.read_text().splitlines()
            if json.loads(line).get("node_id") == "draft"
        ]
        assert [record["inputs"] for record in drafts] == [{"start": 0}, 1]

    def test_a_node_a_cycle_returns_to_that_is_not_the_entry_receives_a_join(
        self, envelope
    ) -> None:
        """Two in-edges, so it is the join case rather than a shape of its own."""
        seen: list = []

        def draft(inputs, ctx):
            seen.append(type(inputs).__name__)
            return 0 if isinstance(inputs.get("critique"), Unknown) else inputs["critique"]

        pipeline = Pipeline(
            [
                Deterministic(lambda inputs, ctx: inputs, node_id="plan"),
                Deterministic(draft, node_id="draft", successors=["critique"]),
                Deterministic(
                    lambda inputs, ctx: inputs + 1,
                    node_id="critique",
                    successors=["draft", "publish"],
                    route=lambda output, ctx: "draft",
                    loop=Loop(max_iterations=2, then="publish"),
                ),
                Deterministic(lambda inputs, ctx: inputs, node_id="publish", successors=[]),
            ],
            budget=_budget(),
        )
        pipeline.run({}, envelope=envelope, run_id=RUN_ID)
        assert seen == ["Join", "Join"]


class TestEveryNodeCanReadTheRunInputs:
    """`ctx.run_inputs` is what the run was given, for a node that did not receive it.

    A node reads what the node before it produced, so a step after a model call had no path
    to the run's own inputs and `keep=` travels through a fan-out only. Dogfood #6's project
    kept a module-level dict from `run_id` to a database path, written by its first node and
    read by its last, which two rollouts at `concurrency=2` in one process cannot serve.
    """

    def test_a_node_after_another_reads_what_the_run_was_given(self, envelope) -> None:
        seen: list = []

        def last(inputs, ctx: NodeContext):
            seen.append(ctx.run_inputs)
            return {"db": ctx.run_inputs["database"]}

        pipeline = Pipeline(
            [
                Deterministic(unannotated, node_id="first", successors=["last"]),
                Deterministic(last, node_id="last", successors=[]),
            ],
            budget=_budget(),
        )
        result = pipeline.run({"database": "shows.db"}, envelope=envelope, run_id=RUN_ID)

        assert result.output == {"db": "shows.db"}
        assert seen == [{"database": "shows.db"}]

    def test_a_fan_out_item_reads_the_runs_inputs_and_the_item_stays_the_argument(
        self, envelope
    ) -> None:
        def per_item(item, ctx: NodeContext):
            return {"item": item["pages"], "db": ctx.run_inputs["database"]}

        pipeline = Pipeline(
            [
                Deterministic(
                    lambda inputs, ctx: {"pages": [1, 2]}, node_id="list", successors=["read"]
                ),
                Deterministic(per_item, node_id="read", over="pages", successors=[]),
            ],
            budget=_budget(),
        )
        result = pipeline.run({"database": "shows.db"}, envelope=envelope, run_id=RUN_ID)

        assert [o.value for o in result.output.outcomes] == [
            {"item": 1, "db": "shows.db"},
            {"item": 2, "db": "shows.db"},
        ]

    def test_an_llm_node_reads_them_in_its_prompt(self, envelope) -> None:
        seen: list = []

        def prompt(inputs, ctx: NodeContext) -> str:
            seen.append(ctx.run_inputs)
            return "answer it"

        pipeline = Pipeline(
            [
                Deterministic(unannotated, node_id="first", successors=["ask"]),
                LLMNode(prompt, node_id="ask", output_schema=Answer, successors=[]),
            ],
            budget=_budget(),
        )
        pipeline.run({"question": "how long?"}, envelope=envelope, model=_client(), run_id=RUN_ID)

        assert seen == [{"question": "how long?"}]

    def test_a_pipeline_used_as_a_node_reads_the_outer_runs_inputs(self, envelope) -> None:
        """The same rule as `run_id`: it describes the run, not the step."""
        seen: list = []

        def inner_last(inputs, ctx: NodeContext):
            seen.append(ctx.run_inputs)
            return {"done": True}

        inner = Pipeline(
            [Deterministic(inner_last, node_id="step", successors=[])],
            budget=_budget(),
            node_id="inner",
        )
        outer = Pipeline(
            [
                Deterministic(unannotated, node_id="first", successors=["inner"]),
                inner,
            ],
            budget=_budget(),
        )
        outer.run({"database": "shows.db"}, envelope=envelope, run_id=RUN_ID)

        assert seen == [{"database": "shows.db"}]

    def test_a_run_given_nothing_reads_none(self, envelope) -> None:
        seen: list = []

        def only(inputs, ctx: NodeContext):
            seen.append(ctx.run_inputs)
            return {"ok": True}

        pipeline = Pipeline([Deterministic(only, node_id="only")], budget=_budget())
        pipeline.run(None, envelope=envelope, run_id=RUN_ID)

        assert seen == [None]


class TestTheOrderOfWhatANodeContextCarries:
    """A project that builds one to test its own node function may pass positionally, so a
    field inserted among these silently lands where another was. `run_inputs` went in after
    them for that reason."""

    def test_the_fields_a_caller_passes_positionally_keep_their_places(self) -> None:
        held = list(NodeContext.__dataclass_fields__)

        assert held[:8] == [
            "run_id",
            "node_id",
            "workspace",
            "seed",
            "budget",
            "item_index",
            "conversation",
            "fetch_policy",
        ]

    def test_the_four_a_context_builder_reads_are_still_the_last_four(self) -> None:
        """`NodeContext`'s own docstring says so."""
        public = [f for f in NodeContext.__dataclass_fields__ if not f.startswith("_")]

        assert public[-4:] == [
            "last_input_tokens",
            "last_input_chars",
            "last_call_index",
            "last_item_index",
        ]


class TestTheNoteOnAnExceptionFromANode:
    """Where nothing was declared, the failure is still the node's and says so."""

    def test_it_names_the_node_and_what_it_was_reading(self, envelope) -> None:
        pipeline = Pipeline(
            [
                Deterministic(lambda inputs, ctx: Count(how_many=1), node_id="count"),
                Deterministic(
                    lambda inputs, ctx: inputs["how_many"], node_id="report", successors=[]
                ),
            ],
            budget=_budget(),
        )
        with pytest.raises(TypeError) as raised:
            pipeline.run({}, envelope=envelope, run_id=RUN_ID)
        assert raised.value.__notes__ == [
            "Node 'report' raised this while reading the Count it received."
        ]

    def test_the_exception_keeps_its_own_type(self, envelope) -> None:
        """A caller catching what the node raised still catches it."""

        def raises(inputs, ctx):
            raise ValueError("the index is unreachable")

        pipeline = Pipeline(
            [Deterministic(raises, node_id="lookup", successors=[])], budget=_budget()
        )
        with pytest.raises(ValueError, match="the index is unreachable"):
            pipeline.run({}, envelope=envelope, run_id=RUN_ID)

    def test_a_failure_travelling_an_error_edge_gets_no_note(self, envelope) -> None:
        """It is not propagating, so there is no traceback for a note to appear under."""
        seen: list = []

        def raises(inputs, ctx):
            raise ValueError("down")

        def handler(inputs: NodeFailure, ctx):
            seen.append(inputs.error["message"])
            return "handled"

        pipeline = Pipeline(
            [
                Deterministic(raises, node_id="lookup", successors=["report"], on_error="handler"),
                Deterministic(handler, node_id="handler", successors=["report"]),
                Deterministic(reads_join, node_id="report", successors=[]),
            ],
            budget=_budget(),
        )
        pipeline.run({}, envelope=envelope, run_id=RUN_ID)
        assert seen == ["down"]


class TestTheManifestRecordsWhatANodeReads:
    def test_a_node_that_declares_it_records_a_digest(self, envelope, manifest_path) -> None:
        pipeline = Pipeline(
            [
                Deterministic(notes, node_id="notes"),
                LLMNode(reads_notes, output_schema=Answer, node_id="verify", successors=[]),
            ],
            budget=_budget(),
        )
        pipeline.run({}, envelope=envelope, run_id=RUN_ID, model=_client())

        entries = {n["node_id"]: n for n in json.loads(manifest_path.read_text())["nodes"]}
        assert entries["notes"]["accepts"] is None
        assert entries["verify"]["accepts"].startswith("sha256:")

    def test_it_is_outside_the_graph_fingerprint(self) -> None:
        """A resumed run rebuilds values in flight from what produced them, so what a node
        reads leaves the stored state as valid as it was."""
        before = Pipeline(
            [
                Deterministic(notes, node_id="notes"),
                Deterministic(unannotated, node_id="report", successors=[]),
            ],
            budget=_budget(),
        )
        after = Pipeline(
            [
                Deterministic(notes, node_id="notes"),
                Deterministic(reads_notes, node_id="report", successors=[]),
            ],
            budget=_budget(),
        )
        assert before.graph_fingerprint() == after.graph_fingerprint()
        assert before.manifest_nodes()[1]["accepts"] != after.manifest_nodes()[1]["accepts"]
