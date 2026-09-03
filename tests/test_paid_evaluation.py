"""Evaluating an agent that spends money: the ceiling, and the recording an evaluation replays.

Two halves. `TestTheCeiling` covers `max_spend`, which is what lets a `spends_money` tool run
in rollouts at all: it is checked before the first rollout against `examples × k × max_cost`,
so nothing binds part-way through an evaluation.

`TestTheRecording` covers `EvalSuite.record`, the live runs a replayed evaluation serves from.
Before it, the documented instruction was to record once and replay, and a recording made that
way misses on every rollout but the one whose seed it holds: an evaluation replaying it
completes and reports a rate over rollouts that all failed. `TestAnUnservableRecording` is that
case refused.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from simple_agents import (
    Prompt,
    AgentNode,
    Budget,
    Cassette,
    ConfigurationError,
    DeclaredCost,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Pipeline,
    PriceBasis,
    RunEnvelope,
    SideEffectClass,
    SpendMeter,
    tool,
)
from simple_agents.evaluation import EvalSuite, Example, ExampleSet, Recording
from simple_agents.models import ToolCallRequest, fake_response

from schemas import Answer

PAID = DeclaredCost(currency="USD", per_call=0.005)
BASIS = PriceBasis(currency="USD", input_uncached_per_mtok=0.1, output_per_mtok=0.3)
EXACT = lambda s: s.answer == s.expected

N, K, MAX_COST = 4, 3, 0.02
AFFORDABLE = N * K * MAX_COST


class Bought(BaseModel):
    answer: str


class Subtask(BaseModel):
    task: str


def examples() -> ExampleSet:
    return ExampleSet(
        [
            Example(id=f"q{i}", inputs={"topic": f"t{i}"}, expected="ok", split="held_out")
            for i in range(N)
        ]
    )


def paid_tool(log: list[str]):
    @tool(side_effect_class=SideEffectClass.SPENDS_MONEY, declared_cost=PAID)
    def buy(meter: SpendMeter, topic: str) -> str:
        """Buy one report on a topic. Costs money."""
        log.append(topic)
        meter.spend(0.005)
        return f"report on {topic}"

    return buy


def emailing_tool():
    @tool(side_effect_class=SideEffectClass.IRREVERSIBLE)
    def send_report(to: str) -> str:
        """Email the report. Cannot be undone."""
        raise AssertionError("a rollout must never execute this")

    return send_report


def prompt(inputs, ctx) -> str:
    return Prompt.user("research {topic}", topic=inputs["topic"])


def subtask_prompt(inputs: Subtask, ctx) -> str:
    """The entry node of a delegated pipeline, which has to declare what it reads."""
    return Prompt.user("work on {task}", task=inputs.task)


def buy_then_finish() -> FakeModelClient:
    """One purchase, then done. Long enough to serve every rollout in a test."""
    return FakeModelClient(
        responses=[
            fake_response(
                tool_calls=[ToolCallRequest(id="b", name="buy", arguments={"topic": "t"})]
            ),
            fake_response(
                tool_calls=[ToolCallRequest(id="f", name="finish", arguments={"answer": "ok"})]
            ),
        ]
        * 200
    )


def greedy() -> FakeModelClient:
    """Never finishes: four purchases every turn, so only the budget stops it."""
    return FakeModelClient(
        responses=[
            fake_response(
                tool_calls=[
                    ToolCallRequest(id=f"b{i}", name="buy", arguments={"topic": f"x{i}"})
                    for i in range(4)
                ]
            )
        ]
        * 500
    )


def spending_suite(tools, *, max_cost: float | None = MAX_COST) -> EvalSuite:
    return EvalSuite(
        Pipeline(
            [
                AgentNode(
                    prompt,
                    node_id="research",
                    tools=tools,
                    output_schema=Bought,
                    allow_unknown=False,
                    budget=Budget(
                        max_steps=6, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=Budget(max_steps=12, max_tokens=None, max_cost=max_cost, max_wall_clock_ms=None),
        ),
        examples(),
        answer=lambda out: out.answer,
        matches=EXACT,
    )


def env(path: Path, cassette: Cassette | None = None) -> RunEnvelope:
    return RunEnvelope(
        run_dir=str(path),
        cassette=cassette if cassette is not None else Cassette.off(),
        cost_basis=BASIS,
    )


def charged_over(results) -> float:
    """What every rollout's manifest says it was charged, summed."""
    total = 0.0
    for rollout in results.rollouts:
        manifest = Path(rollout.trajectory).parent / "manifest.json"
        total += json.loads(manifest.read_text())["totals"].get("charged_cost") or 0.0
    return total


class TestTheCeiling:
    def test_a_paid_tool_with_no_ceiling_is_refused(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            spending_suite([paid_tool([])]).run(
                envelope=env(tmp_path),
                model=buy_then_finish(),
                split="held_out",
                k=K,
                seed=41,
            )

        message = str(raised.value)
        assert "spends_money" in message
        assert "max_spend" in message
        assert "suite.record" in message

    def test_the_refusal_does_not_claim_one_call_per_rollout(self, tmp_path) -> None:
        """`examples × k` counts rollouts, and one rollout can call a paid tool any number of
        times, so the message says rollouts rather than executions."""
        with pytest.raises(ConfigurationError) as raised:
            spending_suite([paid_tool([])]).run(
                envelope=env(tmp_path),
                model=buy_then_finish(),
                split="held_out",
                k=K,
                seed=41,
            )

        message = str(raised.value)
        assert f"{N * K} rollout(s) ({N} examples × {K})" in message
        assert "may call it more than once" in message
        assert f"{N * K} times" not in message

    def test_an_irreversible_tool_is_refused_even_with_a_ceiling(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            spending_suite([emailing_tool()]).run(
                envelope=env(tmp_path),
                model=buy_then_finish(),
                split="held_out",
                k=K,
                seed=41,
                max_spend=1000.0,
            )

        message = str(raised.value)
        assert "irreversible" in message
        assert "no ceiling for this class" in message
        assert "max_spend" not in message

    def test_a_ceiling_over_an_unbounded_rollout_is_refused(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            spending_suite([paid_tool([])], max_cost=None).run(
                envelope=env(tmp_path),
                model=buy_then_finish(),
                split="held_out",
                k=K,
                seed=41,
                max_spend=AFFORDABLE,
            )

        message = str(raised.value)
        assert "max_cost=None" in message
        assert "one rollout is unbounded" in message
        # The per-rollout figure that would make this ceiling hold.
        assert f"{AFFORDABLE / (N * K):.6f}" in message

    def test_a_ceiling_under_the_bound_is_refused_with_both_figures(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            spending_suite([paid_tool([])]).run(
                envelope=env(tmp_path),
                model=buy_then_finish(),
                split="held_out",
                k=K,
                seed=41,
                max_spend=AFFORDABLE / 2,
            )

        message = str(raised.value)
        assert f"{N} examples × {K} rollouts at max_cost={MAX_COST} USD" in message
        assert f"can cost {AFFORDABLE:.6f} USD" in message
        assert f"max_spend is {AFFORDABLE / 2} USD" in message

    def test_a_greedy_agent_stays_under_the_declared_ceiling(self, tmp_path) -> None:
        """A model that never stops buying is held by the per-rollout budget the ceiling was
        computed from, which is what makes the pre-flight arithmetic a bound."""
        log: list[str] = []
        results = spending_suite([paid_tool(log)]).run(
            envelope=env(tmp_path),
            model=greedy(),
            split="held_out",
            k=K,
            seed=41,
            max_spend=AFFORDABLE,
        )

        assert len(log) > N * K, "the probe needs an agent buying more than once per rollout"
        assert charged_over(results) <= AFFORDABLE

    def test_the_ceiling_reaches_a_paid_tool_inside_a_delegate(self, tmp_path) -> None:
        """`declared_nodes()` descends into a delegation, so the refusal fires on a tool no
        node of the outer pipeline declares."""
        from simple_agents import Delegation

        worker = Pipeline(
            [
                AgentNode(
                    subtask_prompt,
                    node_id="shop",
                    tools=[paid_tool([])],
                    output_schema=Bought,
                    allow_unknown=False,
                    budget=Budget(
                        max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
            node_id="worker",
        )
        outer = Pipeline(
            [
                AgentNode(
                    prompt,
                    node_id="orchestrate",
                    tools=[],
                    delegates=[Delegation(worker, description="Hand a subtask over.")],
                    output_schema=Bought,
                    allow_unknown=False,
                    budget=Budget(
                        max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None
                    ),
                )
            ],
            budget=Budget(max_steps=8, max_tokens=None, max_cost=MAX_COST, max_wall_clock_ms=None),
        )
        suite = EvalSuite(outer, examples(), answer=lambda out: out.answer, matches=EXACT)

        with pytest.raises(ConfigurationError) as raised:
            suite.run(
                envelope=env(tmp_path),
                model=buy_then_finish(),
                split="held_out",
                k=K,
                seed=41,
            )

        assert "spends_money" in str(raised.value)

    def test_the_ceiling_is_recorded_in_the_results(self, tmp_path) -> None:
        results = spending_suite([paid_tool([])]).run(
            envelope=env(tmp_path),
            model=buy_then_finish(),
            split="held_out",
            k=K,
            seed=41,
            max_spend=AFFORDABLE,
        )

        assert results.config["max_spend"] == AFFORDABLE

    def test_a_replay_needs_no_ceiling(self, tmp_path) -> None:
        """A served call makes no request and spends nothing, so refusing a free replay for a
        budget reason would be over-refusal."""
        log: list[str] = []
        suite = spending_suite([paid_tool(log)])
        made = suite.record(
            envelope=env(tmp_path / "rec", Cassette.record(str(tmp_path / "c.jsonl"))),
            model=buy_then_finish(),
            split="held_out",
            k=K,
            seed=41,
            max_spend=AFFORDABLE,
        )
        log.clear()

        results = suite.run(
            envelope=env(tmp_path / "eval", Cassette.replay(made.cassette)),
            model=buy_then_finish(),
            split="held_out",
            k=K,
            seed=made.seed,
        )

        assert log == []
        assert results.config["max_spend"] is None


class TestTheRecording:
    def test_it_records_every_rollout_and_the_evaluation_replays_all_of_them(
        self, tmp_path
    ) -> None:
        log: list[str] = []
        suite = spending_suite([paid_tool(log)])

        made = suite.record(
            envelope=env(tmp_path / "rec", Cassette.record(str(tmp_path / "c.jsonl"))),
            model=buy_then_finish(),
            split="held_out",
            k=K,
            seed=41,
            max_spend=AFFORDABLE,
        )
        recorded_paid = len(log)
        log.clear()

        results = suite.run(
            envelope=env(tmp_path / "eval", Cassette.replay(made.cassette)),
            model=buy_then_finish(),
            split="held_out",
            k=K,
            seed=made.seed,
        )

        assert isinstance(made, Recording)
        assert made.runs == N * K
        assert made.failed == ()
        assert results.metrics["failure_rate"].value == 0.0
        assert results.metrics["accuracy"].value == 1.0
        assert log == [], "a replayed rollout must not reach the tool body"
        assert recorded_paid > 0

    def test_it_buys_a_repeated_call_once(self, tmp_path) -> None:
        """A tool call's key carries no seed, so the k rollouts of one example that make the
        same call share one recorded answer. This is what makes the recording cost less than
        the same rollouts run live."""
        recorded: list[str] = []
        spending_suite([paid_tool(recorded)]).record(
            envelope=env(tmp_path / "rec", Cassette.record(str(tmp_path / "c.jsonl"))),
            model=buy_then_finish(),
            split="held_out",
            k=K,
            seed=41,
            max_spend=AFFORDABLE,
        )

        live: list[str] = []
        spending_suite([paid_tool(live)]).run(
            envelope=env(tmp_path / "live"),
            model=buy_then_finish(),
            split="held_out",
            k=K,
            seed=41,
            max_spend=AFFORDABLE,
        )

        assert len(recorded) < len(live)

    def test_it_reports_what_it_cost(self, tmp_path) -> None:
        log: list[str] = []
        made = spending_suite([paid_tool(log)]).record(
            envelope=env(tmp_path / "rec", Cassette.record(str(tmp_path / "c.jsonl"))),
            model=buy_then_finish(),
            split="held_out",
            k=K,
            seed=41,
            max_spend=AFFORDABLE,
        )

        assert made.paid_calls == len(log)
        assert made.currency == "USD"
        assert made.spend is not None and made.spend >= 0.005 * made.paid_calls
        assert made.entries > 0
        assert made.to_record()["seed"] == 41

    def test_it_refuses_an_envelope_that_records_nothing(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            spending_suite([paid_tool([])]).record(
                envelope=env(tmp_path),
                model=buy_then_finish(),
                split="held_out",
                k=K,
                max_spend=AFFORDABLE,
            )

        assert "Cassette.record(" in str(raised.value)

    def test_it_refuses_a_paid_tool_with_no_ceiling(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            spending_suite([paid_tool([])]).record(
                envelope=env(tmp_path, Cassette.record(str(tmp_path / "c.jsonl"))),
                model=buy_then_finish(),
                split="held_out",
                k=K,
            )

        message = str(raised.value)
        assert "refused to record" in message
        assert "max_spend" in message

    def test_it_refuses_an_irreversible_tool(self, tmp_path) -> None:
        """Recording performs the tool once per rollout, which is what the class rules out."""
        with pytest.raises(ConfigurationError) as raised:
            spending_suite([emailing_tool()]).record(
                envelope=env(tmp_path, Cassette.record(str(tmp_path / "c.jsonl"))),
                model=buy_then_finish(),
                split="held_out",
                k=K,
                max_spend=AFFORDABLE,
            )

        assert "irreversible" in str(raised.value)

    def test_a_failed_run_is_named_rather_than_raised(self, tmp_path) -> None:
        """One example that cannot run does not discard the calls the others paid for."""
        suite = EvalSuite(
            Pipeline(
                [LLMNode(prompt, output_schema=Answer, node_id="extract")],
                budget=Budget(max_steps=2, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
            ),
            examples(),
            answer="answer",
            matches=EXACT,
        )

        made = suite.record(
            envelope=env(tmp_path, Cassette.record(str(tmp_path / "c.jsonl"))),
            # No responses at all, so every run fails.
            model=FakeModelClient(responses=[]),
            split="held_out",
            k=1,
            seed=41,
        )

        assert len(made.failed) == N


class TestAnUnservableRecording:
    def recorded(self, tmp_path, *, k: int = K, seed: int = 41):
        suite = spending_suite([paid_tool([])])
        made = suite.record(
            envelope=env(tmp_path / "rec", Cassette.record(str(tmp_path / "c.jsonl"))),
            model=buy_then_finish(),
            split="held_out",
            k=k,
            seed=seed,
            max_spend=AFFORDABLE,
        )
        return suite, made

    def test_a_replay_at_another_seed_is_refused(self, tmp_path) -> None:
        suite, made = self.recorded(tmp_path)

        with pytest.raises(ConfigurationError) as raised:
            suite.run(
                envelope=env(tmp_path / "eval", Cassette.replay(made.cassette)),
                model=buy_then_finish(),
                split="held_out",
                k=K,
                seed=made.seed + 1,
            )

        message = str(raised.value)
        assert f"cannot serve {N * K} of {N * K} rollout(s)" in message
        assert "suite.record(" in message

    def test_a_replay_at_a_larger_k_is_refused(self, tmp_path) -> None:
        """The rollouts the recording does hold are not enough: k=5 needs indices 3 and 4."""
        suite, made = self.recorded(tmp_path, k=K)

        with pytest.raises(ConfigurationError) as raised:
            suite.run(
                envelope=env(tmp_path / "eval", Cassette.replay(made.cassette)),
                model=buy_then_finish(),
                split="held_out",
                k=K + 2,
                seed=made.seed,
            )

        assert f"cannot serve {N * 2} of {N * (K + 2)} rollout(s)" in str(raised.value)

    def test_a_replay_at_a_smaller_k_is_not(self, tmp_path) -> None:
        suite, made = self.recorded(tmp_path, k=K)

        results = suite.run(
            envelope=env(tmp_path / "eval", Cassette.replay(made.cassette)),
            model=buy_then_finish(),
            split="held_out",
            k=K - 1,
            seed=made.seed,
        )

        assert results.metrics["failure_rate"].value == 0.0

    def test_a_replay_with_no_seed_names_the_one_it_generated(self, tmp_path) -> None:
        suite, made = self.recorded(tmp_path)

        with pytest.raises(ConfigurationError) as raised:
            suite.run(
                envelope=env(tmp_path / "eval", Cassette.replay(made.cassette)),
                model=buy_then_finish(),
                split="held_out",
                k=K,
            )

        assert "was given no seed and generated" in str(raised.value)

    def test_a_pipeline_with_no_model_call_is_not_checked(self, tmp_path) -> None:
        """A tool call's key carries no seed, so a recording of tool calls alone serves
        whatever seed the rollouts run at. Refusing it would be over-refusal."""
        log: list[str] = []

        def look_up(inputs, ctx):
            return Answer(answer=ctx.call_tool("buy", topic=inputs["topic"])[:2])

        pipeline = Pipeline(
            [
                Deterministic(
                    look_up,
                    node_id="search",
                    tools=[paid_tool(log)],
                    output_schema=Answer,
                )
            ],
            budget=Budget(
                max_steps=None, max_tokens=None, max_cost=MAX_COST, max_wall_clock_ms=None
            ),
        )
        suite = EvalSuite(pipeline, examples(), answer="answer", matches=lambda s: True)
        cassette = str(tmp_path / "c.jsonl")
        made = suite.record(
            envelope=env(tmp_path / "rec", Cassette.record(cassette)),
            model=None,
            split="held_out",
            k=1,
            seed=41,
            max_spend=AFFORDABLE,
        )
        log.clear()

        results = suite.run(
            envelope=env(tmp_path / "eval", Cassette.replay(made.cassette)),
            model=None,
            split="held_out",
            k=K,
            seed=999,
        )

        assert results.metrics["failure_rate"].value == 0.0
        assert log == []
