"""What an agent that did nothing would have scored, and the floor it sets.

A baseline answers each example without calling a model, so a figure it reaches is the number
the agent has to clear. Two things are computed here: the answers, asked before the first
rollout so a bad baseline costs none of them, and the pseudo-rollouts those answers score as.

``docs/evaluation.md`` §4.2 is what a builder reads.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from ..errors import ConfigurationError
from .examples import Example
from .judgements import Judgements
from .metrics import scores_this_rollout
from .outcomes import RolloutOutcome, classify
from .ratios import figures_for

if TYPE_CHECKING:  # pragma: no cover - import cycle, and only the annotation needs it
    from .runner import EvalSuite

__all__ = ["answers_for", "rollouts_for"]


def answers_for(
    baseline: Callable[[Example], Any] | None, chosen: Sequence[Example]
) -> dict[str, Any]:
    """What the baseline answers on each example, keyed by example id.

    Asked before anything runs. The baseline calls no model and reads nothing but the example,
    so a baseline that raises or that answers ``None`` is a refusal costing no rollouts::

        answers_for(lambda example: "shelve", chosen)   # {'q1': 'shelve', ...}

    Raises :class:`~simple_agents.errors.ConfigurationError` naming the example, for either.
    Empty where no baseline was declared.
    """
    if baseline is None:
        return {}
    answers: dict[str, Any] = {}
    for example in chosen:
        try:
            answer = baseline(example)
        except Exception as exc:
            raise ConfigurationError(
                f"baseline raised {type(exc).__name__} on example {example.id!r}: "
                f"{exc}\n"
                f"It is called once per example and takes one argument, the Example, so "
                f"the answer it gives can depend on the question and on nothing else. "
                f"Nothing has run yet, so fixing it costs no rollouts."
            ) from exc
        if answer is None:
            raise ConfigurationError(
                f"baseline answered None on example {example.id!r}. None is what a "
                f"rollout produces when the pipeline returned nothing, so the floor "
                f"would report an agent that did nothing as one that failed, and every "
                f"figure over rollouts that asserted a value would leave it out.\n"
                f"An agent that never answers gives that as an answer: "
                f"baseline=lambda example: Unknown(reason='did nothing'). One that "
                f"answers the majority class gives the value: "
                f"baseline=lambda example: 'shelve'."
            )
        answers[example.id] = answer
    return answers


def rollouts_for(
    suite: "EvalSuite",
    examples: Sequence[Example],
    judgements: Judgements | None,
    answers: Mapping[str, Any],
) -> tuple[tuple[RolloutOutcome, ...], tuple[str, ...]]:
    """One pseudo-rollout per example, and the figures no baseline answer reached.

    ``examples`` is what the evaluation scored rather than the whole split, so the floor sits
    under a figure computed at the same n. Scored by the suite's own ``matches`` and
    ``criteria``; no model is called and no trajectory is written, and ``answers`` is what
    :func:`answers_for` already asked for::

        rollouts, unscored = rollouts_for(suite, examples, judgements, answers)

    The second value names the project figures whose own function no baseline rollout reached,
    because ``over`` decided them without it. A figure measuring what the agent refrained from
    is one of those under any ``over`` but ``Over.ALL``, and its floor describes the declaration
    rather than the answers.
    """
    if suite.baseline is None:
        return (), ()
    produced: list[RolloutOutcome] = []
    scored: set[str] = set()
    for example in examples:
        answer = answers[example.id]
        scoring = suite._scoring(
            example=example, answer=answer, rollout=0, seed=0, judgements=judgements
        )
        outcome, verdict = classify(scoring, matches=suite.matches, criteria=suite.criteria)
        rollout = RolloutOutcome(
            example_id=example.id,
            rollout=0,
            seed=0,
            outcome=outcome,
            answer=answer,
            verdict=verdict,
        )
        if suite.metrics:
            for_metrics = suite._scoring_for(rollout, example, judgements)
            scores, ratios = figures_for(
                suite.metrics,
                for_metrics,
                asserted=rollout.asserted,
            )
            scored.update(
                metric.name
                for metric in suite.metrics
                if scores_this_rollout(metric, for_metrics, asserted=rollout.asserted)
            )
            rollout = replace(rollout, scores=scores, ratios=ratios)
        produced.append(rollout)
    unscored = tuple(sorted(metric.name for metric in suite.metrics if metric.name not in scored))
    return tuple(produced), unscored
