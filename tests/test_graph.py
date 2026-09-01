"""The declared graph: resolved edges, cycles, the terminal node, and the rendering.

The refusals this analysis raises are in `test_refusals.py`, with the rest of the
construction-time refusals and asserted on their messages. What is here is the shape the
scheduler reads.
"""

from __future__ import annotations

import pytest

from simple_agents import Budget, Deterministic, LLMNode, Loop, Pipeline, RetryPolicy
from simple_agents.graph import Graph, Join

from schemas import Answer


def _plain(inputs, ctx):
    return inputs


def _prompt(inputs, ctx):
    return "irrelevant"


def _node(node_id: str, **edges) -> Deterministic:
    return Deterministic(_plain, node_id=node_id, **edges)


def _budget() -> Budget:
    return Budget(max_steps=None, max_tokens=1000, max_cost=None, max_wall_clock_ms=1000)


class TestDefaultEdges:
    """A node declaring nothing hands its output to the next in the list."""

    def test_a_list_resolves_to_a_chain(self):
        graph = Graph([_node("a"), _node("b"), _node("c")])
        assert graph.successors == {"a": ("b",), "b": ("c",), "c": ()}
        assert graph.terminal == "c"
        assert graph.entry == "a"

    def test_the_last_node_ends_the_run(self):
        graph = Graph([_node("only")])
        assert graph.successors == {"only": ()}
        assert graph.terminal == "only"

    def test_an_explicit_empty_list_also_ends_the_run(self):
        # `successors=[]` says so where `None` would have taken the next node in the list.
        graph = Graph([_node("a", successors=["b"]), _node("b", successors=[])])
        assert graph.terminal == "b"

    def test_declared_edges_need_not_follow_the_list_order(self):
        graph = Graph(
            [
                _node("a", successors=["c"]),
                _node("b", successors=[]),
                _node("c", successors=["b"]),
            ]
        )
        assert graph.successors["a"] == ("c",)
        assert graph.terminal == "b"

    def test_a_duplicate_successor_is_declared_once(self):
        graph = Graph([_node("a", successors=["b", "b"]), _node("b")])
        assert graph.successors["a"] == ("b",)


class TestPredecessorsAndJoins:
    def test_a_node_fed_by_two_arms_is_a_join(self):
        graph = Graph(
            [
                _node("split", successors=["left", "right"], route=lambda o, c: "left"),
                _node("left", successors=["end"]),
                _node("right", successors=["end"]),
                _node("end", successors=[]),
            ]
        )
        assert graph.joins("end") is True
        assert graph.in_edges("end") == ("left", "right")
        assert graph.joins("left") is False

    def test_in_edges_are_in_declaration_order(self):
        graph = Graph(
            [
                _node("split", successors=["right", "left"], route=lambda o, c: "left"),
                _node("left", successors=["end"]),
                _node("right", successors=["end"]),
                _node("end", successors=[]),
            ]
        )
        # Ordered by where the source sits in the list, not by where it sits in `successors`.
        assert graph.in_edges("end") == ("left", "right")

    def test_the_entry_node_has_no_in_edges(self):
        graph = Graph([_node("a"), _node("b")])
        assert graph.in_edges("a") == ()


class TestErrorEdges:
    """An `on_error` target is an edge for reachability and for the terminal check."""

    def _rescued(self) -> Graph:
        return Graph(
            [
                _node("work", successors=["end"], on_error="rescue"),
                _node("rescue", successors=["end"]),
                _node("end", successors=[]),
            ]
        )

    def test_a_handler_is_reachable_through_its_error_edge(self):
        graph = self._rescued()
        assert graph.in_edges("rescue") == ("work",)
        assert graph.in_edges("end") == ("work", "rescue")
        assert graph.terminal == "end"

    def test_an_error_edge_is_not_a_routing_successor(self):
        # Two edges leave `work` and only one of them is chosen by a route, so `work` needs no
        # route and declaring none is not refused.
        graph = self._rescued()
        assert graph.successors["work"] == ("end",)
        assert graph.edges["work"] == ("end", "rescue")


class TestCycles:
    def test_a_bounded_cycle_names_its_members(self):
        graph = Graph(
            [
                _node("draft", successors=["critique"]),
                _node(
                    "critique",
                    successors=["draft", "publish"],
                    route=lambda o, c: "draft",
                    loop=Loop(max_iterations=3, then="publish"),
                ),
                _node("publish", successors=[]),
            ]
        )
        cycle = graph.loop_at("critique")
        assert cycle is not None
        assert cycle.back == ("draft",)
        assert cycle.body == frozenset({"draft", "critique"})
        assert graph.is_back_edge("critique", "draft") is True
        assert graph.is_back_edge("critique", "publish") is False

    def test_a_node_outside_the_cycle_is_in_no_cycle(self):
        graph = Graph(
            [
                _node("draft", successors=["critique"]),
                _node(
                    "critique",
                    successors=["draft", "publish"],
                    route=lambda o, c: "draft",
                    loop=Loop(max_iterations=2, then="publish"),
                ),
                _node("publish", successors=[]),
            ]
        )
        assert graph.cycle_around("publish") is None
        assert graph.cycle_around("draft") is not None

    def test_the_innermost_cycle_is_the_smaller_one(self):
        # `inner` closes a two-node cycle; `outer` closes one that contains it.
        graph = Graph(
            [
                _node("start", successors=["a"]),
                _node("a", successors=["b"]),
                _node(
                    "b",
                    successors=["a", "c"],
                    route=lambda o, c: "c",
                    loop=Loop(max_iterations=2, then="c"),
                ),
                _node(
                    "c",
                    successors=["a", "end"],
                    route=lambda o, c: "end",
                    loop=Loop(max_iterations=3, then="end"),
                ),
                _node("end", successors=[]),
            ]
        )
        # The inner body holds the inner members alone. Measuring it over the full graph would
        # put `c` in it, because `c` reaches `b` through the outer loop's own back edge.
        assert graph.loop_at("b").body == frozenset({"a", "b"})
        assert graph.loop_at("c").body == frozenset({"a", "b", "c"})
        assert graph.cycle_around("b").node_id == "b"
        assert graph.cycle_around("c").node_id == "c"

    def test_an_exit_that_the_outer_loop_re_enters_is_not_refused(self):
        # `b`'s `then` leaves `b`'s cycle. That the outer loop can bring the run back is the
        # outer loop's business, and it carries its own bound.
        graph = Graph(
            [
                _node("start", successors=["a"]),
                _node("a", successors=["b"]),
                _node(
                    "b",
                    successors=["a", "c"],
                    route=lambda o, c: "c",
                    loop=Loop(max_iterations=2, then="c"),
                ),
                _node(
                    "c",
                    successors=["a", "end"],
                    route=lambda o, c: "end",
                    loop=Loop(max_iterations=3, then="end"),
                ),
                _node("end", successors=[]),
            ]
        )
        assert graph.back_edges == frozenset({("b", "a"), ("c", "a")})


class TestMermaid:
    def test_it_renders_every_node_and_edge(self):
        pipeline = Pipeline(
            [
                Deterministic(_plain, node_id="load"),
                LLMNode(_prompt, output_schema=Answer, node_id="answer"),
            ],
            budget=_budget(),
        )
        rendered = pipeline.to_mermaid()
        assert rendered.startswith("flowchart TD")
        assert "load" in rendered and "answer" in rendered
        assert "load --> answer" in rendered
        assert "deterministic" in rendered and "llm" in rendered

    def test_a_routed_edge_renders_differently_from_a_fixed_one(self):
        pipeline = Pipeline(
            [
                _node("split", successors=["left", "right"], route=lambda o, c: "left"),
                _node("left", successors=["end"]),
                _node("right", successors=["end"]),
                _node("end", successors=[]),
            ],
            budget=_budget(),
        )
        rendered = pipeline.to_mermaid()
        assert "split -.-> left" in rendered
        assert "left --> end" in rendered

    def test_an_error_edge_is_labelled(self):
        pipeline = Pipeline(
            [
                _node("work", on_error="rescue"),
                _node("rescue", successors=["end"]),
                _node("end", successors=[]),
            ],
            budget=_budget(),
        )
        assert "|on error|" in pipeline.to_mermaid()

    def test_an_id_a_diagram_cannot_hold_is_made_safe(self):
        pipeline = Pipeline(
            [_node("load docs", successors=["end"]), _node("end", successors=[])],
            budget=_budget(),
        )
        rendered = pipeline.to_mermaid()
        assert "load_docs" in rendered
        # The readable id survives in the label even where the identifier cannot hold it.
        assert '"load docs' in rendered

    def test_a_declared_stop_is_labelled(self):
        """A reader of the drawing can see where a run will stop to ask someone."""
        pipeline = Pipeline(
            [
                _node("load", successors=["review"]),
                LLMNode(
                    _prompt,
                    output_schema=Answer,
                    node_id="review",
                    suspend_before=True,
                ),
            ],
            budget=_budget(),
        )
        rendered = pipeline.to_mermaid()
        assert "stops before" in rendered
        assert rendered.count("stops before") == 1
        assert "stops before" in [line for line in rendered.splitlines() if "review(" in line][0]


class TestWhatIsNotANode:
    def test_a_join_in_the_node_list_is_refused(self):
        """`Join` is exported and takes `node_id=`, so listing one is a plausible mistake."""
        with pytest.raises(Exception) as exc:
            Pipeline(
                [_node("hunt", successors=["report"]), Join({}, node_id="report")],
                budget=_budget(),
            )
        message = str(exc.value)
        assert "Join is not a node" in message
        assert "successors=" in message

    def test_something_else_in_the_node_list_is_refused(self):
        with pytest.raises(Exception) as exc:
            Pipeline([_node("hunt", successors=[]), "report"], budget=_budget())
        assert "not a node" in str(exc.value)
        assert "Deterministic(fn, node_id='step')" in str(exc.value)


class TestPolicyArguments:
    def test_a_loop_needs_a_positive_count(self):
        with pytest.raises(Exception) as exc:
            Loop(max_iterations=0, then="publish")
        assert "at least 1" in str(exc.value)

    def test_a_loop_needs_somewhere_to_go(self):
        with pytest.raises(Exception) as exc:
            Loop(max_iterations=3, then="")
        assert "Loop(max_iterations=3, then='publish')" in str(exc.value)

    def test_retry_counts_executions_rather_than_retries(self):
        assert RetryPolicy(attempts=1).attempts == 1
        with pytest.raises(Exception) as exc:
            RetryPolicy(attempts=0)
        assert "attempts=1 is no retry" in str(exc.value)

    def test_a_negative_backoff_is_refused(self):
        with pytest.raises(Exception) as exc:
            RetryPolicy(attempts=2, backoff_ms=-1)
        assert "milliseconds" in str(exc.value)
