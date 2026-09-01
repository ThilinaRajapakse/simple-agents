"""Construction-time refusals.

Each test asserts on the *message*, not only the exception type. The failure string is what a
coding agent reads at the moment it is deciding what to do next, so a refusal that fires with
an unhelpful message has only half worked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

import pytest
from pydantic import BaseModel

from simple_agents import (
    AgentNode,
    Budget,
    ConfigurationError,
    Deterministic,
    LLMNode,
    Loop,
    ModelFacingError,
    Pipeline,
    SideEffectClass,
    tool,
)
from simple_agents.schema import schema_admits_unknown

from schemas import Answer, Total


@dataclass
class PlainVerdict:
    verdict: str


def _prompt(inputs, ctx):
    return "irrelevant"


def _plain(inputs, ctx):
    return inputs


class Filter(BaseModel):
    colour: str


class TestBudgetRefusal:
    def test_agent_node_without_budget_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            AgentNode(_prompt, tools=[], output_schema=Answer, budget=None)  # type: ignore[arg-type]
        message = str(exc.value)
        assert "without a Budget" in message
        assert "FT-18" in message
        # The message must name the fix, not just the sin.
        assert "budget=Budget(" in message
        # And it must say the escape hatch exists, or a coding agent will invent a value.
        assert "None" in message

    def test_pipeline_with_model_node_and_no_budget_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            Pipeline([LLMNode(_prompt, output_schema=Answer)])
        message = str(exc.value)
        assert "without a budget" in message
        assert "FT-18" in message
        assert "Budget.unbounded()" in message

    def test_deterministic_only_pipeline_needs_no_budget(self):
        # Nothing here can call a model, so there is nothing to bound. Refusing would be a
        # gate firing on a project that never claimed the risk, which is the failure mode
        # that gets conformance suites disabled.
        pipeline = Pipeline([Deterministic(_plain)])
        assert pipeline.budget.is_unbounded

    def test_all_axes_none_is_a_valid_budget(self):
        """The refusal is about the absence of a decision, not the presence of a limit."""
        node = AgentNode(
            _prompt,
            tools=[],
            output_schema=Answer,
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        )
        assert node.budget.is_unbounded

    def test_budget_requires_every_axis_explicitly(self):
        """No defaults on Budget: an axis cannot be omitted by accident."""
        with pytest.raises(TypeError):
            Budget(max_steps=5)  # type: ignore[call-arg]


class TestASchemaTheModelIsShown:
    """A schema shown to a model has to be one the model can be shown.

    Measured 2026-08-19: a plain dataclass constructed, the model was offered a `finish` whose
    parameters were `{"type": "object", "properties": {}}`, and `finish({"answer": "nope"})`
    was accepted as the answer against a schema whose only field was `verdict`. `Delegation`
    already refused the same thing for the type its entry node reads.
    """

    def test_a_dataclass_is_refused_on_an_llm_node(self):
        with pytest.raises(ConfigurationError) as exc:
            LLMNode(_prompt, output_schema=PlainVerdict, allow_unknown=False)

        message = str(exc.value)
        assert "output_schema=PlainVerdict" in message
        # Must say what goes wrong at run time, since nothing else would.
        assert "no properties" in message
        assert "without being validated" in message
        # Must name the fix, and the node kind that takes one.
        assert "pydantic model" in message
        assert "Deterministic(output_schema=...)" in message

    def test_a_dataclass_is_refused_on_an_agent_node(self):
        with pytest.raises(ConfigurationError) as exc:
            AgentNode(
                _prompt,
                tools=[],
                output_schema=PlainVerdict,
                allow_unknown=False,
                budget=Budget(max_steps=1, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
            )

        assert "pydantic model" in str(exc.value)

    def test_a_typed_dict_is_refused_too(self):
        class Shape(TypedDict):
            verdict: str

        with pytest.raises(ConfigurationError):
            LLMNode(_prompt, output_schema=Shape, allow_unknown=False)

    def test_extract_to_schema_refuses_it_at_construction(self):
        """It failed at run time with a model-facing error, so the run continued badly."""
        from simple_agents.builtins import extract_to_schema

        with pytest.raises(ConfigurationError) as exc:
            extract_to_schema(PlainVerdict, allow_unknown=False)

        assert "schema=PlainVerdict" in str(exc.value)

    @pytest.mark.parametrize("schema", [dict, list[str], "a string"])
    def test_the_example_it_prints_is_valid_python(self, schema):
        """`class dict(BaseModel):` instructs the builder to write something that will not run."""
        with pytest.raises(ConfigurationError) as exc:
            LLMNode(_prompt, output_schema=schema, allow_unknown=False)

        shown = [line.strip() for line in str(exc.value).splitlines() if "(BaseModel)" in line]
        assert shown == ["class Answer(BaseModel):"]

    def test_a_deterministic_node_still_takes_one(self):
        """Nothing is shown to a model there, and `TypeAdapter` already validated it."""
        node = Deterministic(lambda inputs, ctx: PlainVerdict("yes"), output_schema=PlainVerdict)

        assert node.output_schema is PlainVerdict


class TestUnknownBranchRefusal:
    def test_schema_without_unknown_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            LLMNode(_prompt, output_schema=Total)
        message = str(exc.value)
        assert "no `unknown` variant" in message
        assert "FT-09" in message
        # Must warn against the two wrong fixes explicitly, since both are the obvious ones.
        assert "empty string" in message
        assert "null" in message
        # Must name the opt-out, and say it is recorded.
        assert "allow_unknown=False" in message
        assert "manifest" in message

    def test_schema_with_unknown_is_accepted(self):
        node = LLMNode(_prompt, output_schema=Answer)
        assert node.allow_unknown is True

    def test_opt_out_is_retained_for_the_manifest(self):
        """An invisible opt-out is an opt-out that becomes the default."""
        node = LLMNode(_prompt, output_schema=Total, allow_unknown=False)
        assert node.allow_unknown is False

    def test_agent_node_enforces_the_same_rule(self):
        with pytest.raises(ConfigurationError):
            AgentNode(_prompt, tools=[], output_schema=Total, budget=Budget.unbounded())

    @pytest.mark.parametrize(
        "schema, expected",
        [
            (Answer, True),
            (Total, False),
        ],
    )
    def test_schema_admits_unknown(self, schema, expected):
        assert schema_admits_unknown(schema) is expected


class TestPipelineConstruction:
    def test_empty_pipeline_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            Pipeline([])
        assert "no nodes" in str(exc.value)


class TestToolSchema:
    """What the model is told a tool takes.

    The schema is derived from the signature. An empty one is not a neutral default: the model
    is then told the tool takes nothing, calls it with nothing, and the call fails inside the
    library rather than in anything the model can see (FT-23).
    """

    def test_required_and_optional_parameters_are_distinguished(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def search(query: str, limit: int = 5) -> str:
            """Search the catalogue."""
            return query

        assert search.parameters["required"] == ["query"]
        assert search.parameters["properties"]["query"]["type"] == "string"
        assert search.parameters["properties"]["limit"]["default"] == 5

    def test_a_nested_model_keeps_its_definition(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def browse(filters: Filter) -> str:
            """Browse with a filter."""
            return filters.colour

        assert "Filter" in browse.parameters["$defs"]
        assert browse.parameters["$defs"]["Filter"]["required"] == ["colour"]

    def test_an_annotation_that_cannot_be_resolved_says_so(self):
        # Annotations resolve against the module the function was defined in, so a type
        # declared inside a function is not visible. The refusal names the way round it.
        class Local(BaseModel):
            colour: str

        with pytest.raises(ConfigurationError) as exc:

            @tool(side_effect_class=SideEffectClass.READ_ONLY)
            def browse(filters: Local) -> str:
                """Browse with a filter."""
                return filters.colour

        assert "cannot be resolved" in str(exc.value)
        assert "parameters=" in str(exc.value)

    def test_a_tool_taking_nothing_gets_an_empty_property_set(self):
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def now() -> str:
            """The current time."""
            return "12:00"

        assert now.parameters == {"properties": {}, "type": "object"}

    def test_an_unannotated_parameter_refuses(self):
        with pytest.raises(ConfigurationError) as exc:

            @tool(side_effect_class=SideEffectClass.READ_ONLY)
            def search(query) -> str:
                """Search the catalogue."""
                return query

        assert "unannotated parameter 'query'" in str(exc.value)
        assert "parameters=" in str(exc.value)

    def test_var_keyword_refuses(self):
        with pytest.raises(ConfigurationError) as exc:

            @tool(side_effect_class=SideEffectClass.READ_ONLY)
            def search(**kwargs: str) -> str:
                """Search the catalogue."""
                return ""

        assert "no JSON schema equivalent" in str(exc.value)

    def test_an_explicit_schema_is_used_as_given(self):
        schema = {"type": "object", "properties": {"q": {"type": "string"}}}

        @tool(side_effect_class=SideEffectClass.READ_ONLY, parameters=schema)
        def search(**kwargs: str) -> str:
            """Search the catalogue."""
            return ""

        assert search.parameters == schema

    def test_a_call_that_does_not_match_is_returned_to_the_model(self):
        # The model can correct a malformed call if it is told. A TypeError from calling the
        # function would end the run instead.
        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def search(query: str) -> str:
            """Search the catalogue."""
            return query

        with pytest.raises(ModelFacingError) as exc:
            search.call({})

        assert "query: Field required" in str(exc.value)


class TestGraphRefusals:
    """The construction refusals the declared graph adds.

    Each asserts on the message. Each was broken once, and watched to fail, before it was
    trusted: a check that has never been seen to fire is no evidence that it can.
    """

    def _budget(self):
        return Budget(max_steps=None, max_tokens=1000, max_cost=None, max_wall_clock_ms=1000)

    def _node(self, node_id, **edges):
        return Deterministic(_plain, node_id=node_id, **edges)

    def _build(self, *nodes):
        return Pipeline(list(nodes), budget=self._budget())

    def test_a_successor_naming_no_node_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(self._node("a", successors=["typo"]), self._node("b", successors=[]))
        message = str(exc.value)
        assert "'a' names 'typo' in its successors" in message
        assert "'a', 'b'" in message
        assert "node_id='typo'" in message

    def test_an_on_error_naming_no_node_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(self._node("a", on_error="nowhere"), self._node("b", successors=[]))
        assert "names 'nowhere' in its on_error" in str(exc.value)

    def test_a_loop_then_naming_no_node_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node("a", successors=["b"]),
                self._node(
                    "b",
                    successors=["a", "c"],
                    route=lambda o, c: "c",
                    loop=Loop(max_iterations=2, then="gone"),
                ),
                self._node("c", successors=[]),
            )
        assert "names 'gone' in its loop's then" in str(exc.value)

    def test_an_unreachable_node_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node("a", successors=["c"]),
                self._node("orphan", successors=["c"]),
                self._node("c", successors=[]),
            )
        message = str(exc.value)
        assert "No path from 'a' reaches 'orphan'" in message
        assert "reach of zero" in message
        assert "Execution starts at 'a'" in message

    def test_two_nodes_with_no_successor_refuse(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node("a", successors=["left", "right"], route=lambda o, c: "left"),
                self._node("left", successors=[]),
                self._node("right", successors=[]),
            )
        message = str(exc.value)
        assert "2 nodes with no successor" in message
        assert "'left', 'right'" in message
        assert "receives a Join" in message

    def test_no_node_without_a_successor_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node("a", successors=["b"]),
                self._node(
                    "b",
                    successors=["a"],
                    loop=Loop(max_iterations=2, then="a"),
                ),
            )
        message = str(exc.value)
        assert "no node ends the run" in message
        assert "successors=[]" in message

    def test_more_than_one_successor_with_no_route_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node("a", successors=["left", "right"]),
                self._node("left", successors=["end"]),
                self._node("right", successors=["end"]),
                self._node("end", successors=[]),
            )
        message = str(exc.value)
        assert "declares 2 successors" in message
        assert "nothing decides" in message
        assert "route=lambda output, ctx:" in message

    def test_a_route_with_one_successor_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node("a", successors=["b"], route=lambda o, c: "b"),
                self._node("b", successors=[]),
            )
        message = str(exc.value)
        assert "nothing to choose between" in message
        assert "successors=['verify', 'report']" in message

    def test_a_route_with_no_successors_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node("a", successors=["b"]),
                self._node("b", successors=[], route=lambda o, c: "a"),
            )
        assert "0 successors" in str(exc.value)

    def test_an_unbounded_cycle_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node("draft", successors=["critique"]),
                self._node("critique", successors=["draft", "publish"], route=lambda o, c: "draft"),
                self._node("publish", successors=[]),
            )
        message = str(exc.value)
        assert "cycle with no bound on it" in message
        assert "draft -> critique -> draft" in message
        assert "FT-18" in message
        assert "loop=Loop(max_iterations=3, then=...) to node 'critique'" in message

    def test_a_loop_closing_no_cycle_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node(
                    "a",
                    successors=["b", "c"],
                    route=lambda o, c: "b",
                    loop=Loop(max_iterations=2, then="c"),
                ),
                self._node("b", successors=["c"]),
                self._node("c", successors=[]),
            )
        message = str(exc.value)
        assert "declares a Loop, and none of its successors leads back" in message
        assert "drop loop=" in message

    def test_a_then_outside_the_declared_successors_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node("start", successors=["draft"]),
                self._node("draft", successors=["critique"]),
                self._node(
                    "critique",
                    successors=["draft", "publish"],
                    route=lambda o, c: "draft",
                    loop=Loop(max_iterations=2, then="start"),
                ),
                self._node("publish", successors=[]),
            )
        message = str(exc.value)
        assert "loop=Loop(then='start')" in message
        assert "not one of its successors" in message

    def test_a_then_inside_the_cycle_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            self._build(
                self._node("draft", successors=["critique"]),
                self._node(
                    "critique",
                    successors=["draft", "publish"],
                    route=lambda o, c: "draft",
                    loop=Loop(max_iterations=2, then="draft"),
                ),
                self._node("publish", successors=[]),
            )
        message = str(exc.value)
        assert "is inside the cycle it bounds" in message
        assert "re-enter the cycle" in message


class TestNodeEdgeArguments:
    """One node's own graph arguments, which are checkable without the other nodes."""

    def test_a_bare_string_of_successors_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            Deterministic(_plain, node_id="a", successors="verify")
        message = str(exc.value)
        assert "read one character at a time" in message
        assert "successors=['verify']" in message

    def test_a_route_that_is_not_callable_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            Deterministic(_plain, node_id="a", route="verify")
        assert "is not callable" in str(exc.value)

    def test_a_loop_that_is_not_a_loop_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            Deterministic(_plain, node_id="a", loop=3)
        assert "loop=Loop(max_iterations=3, then='publish')" in str(exc.value)

    def test_a_retry_that_is_not_a_policy_refuses(self):
        with pytest.raises(ConfigurationError) as exc:
            LLMNode(_prompt, output_schema=Answer, node_id="a", retry=3)
        assert "retry=RetryPolicy(attempts=3)" in str(exc.value)
