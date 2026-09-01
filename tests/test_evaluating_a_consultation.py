"""What an evaluation does about a tool that asks a person, and what FT-25 can and cannot see.

`consult` is declared `read_only`, and one project's registry docstring reasoned from that to
"nothing here spends money or writes anywhere permanent, which is what lets an evaluation run k
rollouts over n examples without refusing to start". The class was right and the conclusion was
not: nothing refused it, so 50 examples at k=5 over a channel that emails somebody would have
sent 250 emails. `consult` stays `read_only` and the refusal lives here instead.

FT-25 certified that same project's consult tool while its one evaluated call site was
unreachable. It still passes on registration, which is what it verifies, and says so on the
pass rather than failing a project whose consultation triggers rarely.
"""

from __future__ import annotations

import pytest

from simple_agents import (
    AgentNode,
    Budget,
    Cassette,
    Deterministic,
    FakeModelClient,
    Pipeline,
    RunEnvelope,
    ToolRegistry,
)
from simple_agents.builtins import consult, unattended
from simple_agents.errors import ConfigurationError
from simple_agents.evaluation import EvalSuite, Example, ExampleSet, SimulatedEndUser

from schemas import Answer

BUDGET = Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None)


def _channel(answered_by: str):
    def ask(question, options=None, about=None):
        return "yes"

    ask.answered_by = answered_by
    return ask


def _pipeline(tool) -> Pipeline:
    return Pipeline(
        [
            Deterministic(
                lambda inputs, ctx: {"answer": str(ctx.call_tool("consult", question="Fit?"))},
                tools=[tool],
                node_id="ask",
                output_schema=None,
            )
        ],
        budget=BUDGET,
    )


def _suite(tool) -> EvalSuite:
    return EvalSuite(
        _pipeline(tool),
        ExampleSet(
            [
                Example(
                    id="e1",
                    inputs={},
                    expected="yes",
                    split="held_out",
                    end_user="Answers quickly.",
                ),
            ]
        ),
        answer="answer",
        matches=lambda s: s.answer == s.expected,
    )


class TestARolloutOverALiveChannelIsRefused:
    @pytest.mark.parametrize("answered_by", ["end_user", "builder", "coding_agent"])
    def test_every_channel_that_reaches_a_person_is_refused(self, answered_by, tmp_path):
        tool = (
            consult(_channel(answered_by), answered_by=answered_by, permission="agreed")
            if answered_by == "coding_agent"
            else consult(_channel(answered_by), answered_by=answered_by)
        )
        with pytest.raises(ConfigurationError) as exc:
            _suite(tool).run(envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=1, seed=41)
        assert "asks a person" in str(exc.value)

    def test_the_refusal_counts_the_rollouts(self, tmp_path):
        with pytest.raises(ConfigurationError) as exc:
            _suite(consult(_channel("end_user"), answered_by="end_user")).run(
                envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=5, seed=41
            )
        assert "5 rollout(s) (1 examples × 5)" in str(exc.value)

    def test_it_names_the_tool_and_what_it_declared(self, tmp_path):
        with pytest.raises(ConfigurationError) as exc:
            _suite(consult(_channel("end_user"), answered_by="end_user")).run(
                envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=1, seed=41
            )
        assert "'consult' (answered_by 'end_user')" in str(exc.value)

    def test_it_offers_the_stand_in(self, tmp_path):
        with pytest.raises(ConfigurationError) as exc:
            _suite(consult(_channel("end_user"), answered_by="end_user")).run(
                envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=1, seed=41
            )
        assert "SimulatedEndUser(model=cheap)" in str(exc.value)
        assert "unattended()" in str(exc.value)

    def test_the_escape_it_offers_is_one_that_works(self, tmp_path):
        """A channel handed back has to carry its own declaration, and the message says so."""
        with pytest.raises(ConfigurationError) as exc:
            _suite(consult(_channel("end_user"), answered_by="end_user")).run(
                envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=1, seed=41
            )
        assert "ask_in_chat.answered_by = 'end_user'" in str(exc.value)

    def test_recording_is_refused_too(self, tmp_path):
        """The recording pass makes the live calls, so it is where the questions would go."""
        with pytest.raises(ConfigurationError) as exc:
            _suite(consult(_channel("end_user"), answered_by="end_user")).record(
                envelope=RunEnvelope(
                    run_dir=tmp_path, cassette=Cassette.record(tmp_path / "c.jsonl")
                ),
                split="held_out",
                k=1,
                seed=41,
            )
        assert "refused to record" in str(exc.value)


class TestWhatIsAllowedThrough:
    def _ran(self, tool, tmp_path, **kwargs):
        return _suite(tool).run(
            envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=1, seed=41, **kwargs
        )

    def test_a_stand_in_end_user_is_the_waiver(self, tmp_path):
        results = self._ran(
            consult(_channel("end_user"), answered_by="end_user"),
            tmp_path,
            end_user=SimulatedEndUser(model=FakeModelClient(responses=[])),
        )
        assert results.rollouts

    def test_the_registered_channel_handed_back_is_also_the_waiver(self, tmp_path):
        channel = _channel("end_user")
        results = self._ran(consult(channel, answered_by="end_user"), tmp_path, end_user=channel)
        assert results.rollouts

    def test_unattended_needs_no_waiver(self, tmp_path):
        assert self._ran(consult(unattended()), tmp_path).rollouts

    def test_a_canned_channel_needs_no_waiver(self, tmp_path):
        assert self._ran(consult(_channel("canned"), answered_by="canned"), tmp_path).rollouts

    def test_a_pipeline_with_no_consultation_is_untouched(self, tmp_path):
        suite = EvalSuite(
            Pipeline(
                [Deterministic(lambda i, c: {"answer": "yes"}, node_id="a", output_schema=None)],
                budget=BUDGET,
            ),
            ExampleSet([Example(id="e1", inputs={}, expected="yes", split="held_out")]),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
        )
        assert suite.run(
            envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=1, seed=41
        ).rollouts

    def test_a_replay_reaches_no_channel_so_it_is_allowed(self, tmp_path):
        channel = _channel("end_user")
        tool = consult(channel, answered_by="end_user")
        path = tmp_path / "c.jsonl"
        _suite(tool).record(
            envelope=RunEnvelope(run_dir=tmp_path / "rec", cassette=Cassette.record(path)),
            split="held_out",
            k=1,
            seed=41,
            end_user=channel,
        )
        results = _suite(tool).run(
            envelope=RunEnvelope(run_dir=tmp_path / "rep", cassette=Cassette.replay(path)),
            split="held_out",
            k=1,
            seed=41,
        )
        assert results.rollouts


class TestConsultKeepsItsClass:
    def test_it_is_still_read_only(self):
        """The class describes the effect; the refusal above is what bounds the rollouts."""
        from simple_agents.tools import SideEffectClass

        tool = consult(_channel("end_user"), answered_by="end_user")
        assert tool.side_effect_class is SideEffectClass.READ_ONLY

    def test_an_agent_node_reaches_the_same_refusal(self, tmp_path):
        suite = EvalSuite(
            Pipeline(
                [
                    AgentNode(
                        lambda inputs, ctx: "go",
                        tools=ToolRegistry([consult(_channel("end_user"), answered_by="end_user")]),
                        output_schema=Answer,
                        budget=BUDGET,
                        node_id="hunt",
                    )
                ],
                budget=BUDGET,
            ),
            ExampleSet([Example(id="e1", inputs={}, expected="yes", split="held_out")]),
            answer="answer",
            matches=lambda s: s.answer == s.expected,
        )
        with pytest.raises(ConfigurationError):
            suite.run(envelope=RunEnvelope(run_dir=tmp_path), split="held_out", k=1, seed=41)
