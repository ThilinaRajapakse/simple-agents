"""Two things put side by side, and a figure over what was preferred.

Some tasks have no correct answer. Which of two shortlists is better, which of two summaries
reads well, whether a reordering helped: nothing can be written in an answer key. What a person
can say is which of the two they would rather have.

**How the pairs are formed is where the instrument's quality comes from, and the library fixes
nothing about it.** Pairing across a wide quality gap produces mostly pairs where neither side
is wanted, which says little about either. A bracket, where winners meet winners and losers meet
losers, resolves that by position rather than by asking a person to express it.

``docs/evaluation.md`` §11.9 is the surface of record. :func:`pairs_from_arms` builds the pairs for the
one case the library holds both sides of, two versions of a pipeline over one example set.

Nothing here calls a model. A verdict is decided by a judging pass or by a person and read back,
the way every other judgement is, so a figure over pairs is computed with no network.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from ..errors import ConfigurationError
from .intervals import DEFAULT_CONFIDENCE, DEFAULT_RESAMPLES
from .labels import Label
from .metrics import RATE, Metric
from .ratios import RatioShape, ratio_metric

__all__ = ["Pair", "pairs_from_arms", "unjudged_pairs", "paired_figure"]


@dataclass(frozen=True, slots=True)
class Pair:
    """Two things a judge is asked to choose between, and what each of them is.

    ``this`` and ``that`` are what the judge sees. ``this_is`` and ``that_is`` name what each
    side holds, which is what a counting rule reads, so the order a judge was shown can be
    randomised without the figure changing meaning::

        Pair(id="p001", this=variant_answer, that=baseline_answer,
             this_is="variant", that_is="baseline", example_id="q29")

    ``example_id`` is the resampling unit the interval is taken over. Where several pairs come
    from one example they travel together, as k rollouts of one example do. A pair belonging to
    no example is its own unit.

    ``metadata`` carries whatever the project wants kept beside the pair: which band each side
    was drawn from, which round of a bracket it is, who was asked.
    """

    id: str
    this: Any
    that: Any
    this_is: str = "this"
    that_is: str = "that"
    example_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise ConfigurationError(
                "A Pair was given an empty id. The id is what joins a pair to the verdict "
                "somebody recorded about it, so a pair without one cannot be scored.\n"
                "Pass the id the labelling surface used: Pair(id='p001', this=a, that=b)."
            )
        if self.this_is == self.that_is:
            raise ConfigurationError(
                f"Pair {self.id!r} says both sides are {self.this_is!r}. A counting rule reads "
                f"these to tell which side a verdict picked, so two the same makes every "
                f"verdict ambiguous.\n"
                f"Name what each side holds: this_is='variant', that_is='baseline'."
            )

    @property
    def unit(self) -> str:
        """What the interval resamples: the example this pair came from, or the pair itself."""
        return self.example_id if self.example_id is not None else self.id


def pairs_from_arms(
    before: Any,
    after: Any,
    *,
    before_is: str = "before",
    after_is: str = "after",
    seed: int | None = None,
) -> list[Pair]:
    """One pair per rollout the two evaluations share, each holding both arms' answers.

    The one pairing the library can build itself, because it holds both results files::

        pairs = pairs_from_arms(before, after, before_is="baseline",
                                after_is="variant", seed=41)

    Rollout *i* of each arm is paired with rollout *i* of the other, which are the same draw:
    a sweep runs every arm at one seed. An example or a rollout index only one side has is left
    out.

    ``seed`` randomises which arm is shown as ``this``, recording what each side holds in
    ``this_is`` and ``that_is``. A judge shown one arm first prefers it more often than chance,
    so a figure built without this measures the order as well as the arms. Leaving ``seed``
    unset puts ``before`` first in every pair, which is what a coded rule wants and what a
    person or a model should not be given.

    Raises :class:`~simple_agents.errors.ConfigurationError` where the two share no rollout.
    """
    left = {(r.example_id, r.rollout): r for r in before.rollouts}
    right = {(r.example_id, r.rollout): r for r in after.rollouts}
    shared = sorted(set(left) & set(right))
    if not shared:
        raise ConfigurationError(
            f"These two evaluations share no rollout: {len(left)} in the earlier one and "
            f"{len(right)} in the later one, with no (example, rollout) in both. There is "
            f"nothing to pair.\n"
            f"Pair evaluations run over the same split at the same k, which is what "
            f"compare_variants does for every arm of a sweep."
        )
    rng = random.Random(seed) if seed is not None else None
    return [_one_pair(left[key], right[key], before_is, after_is, rng) for key in shared]


def _one_pair(
    earlier: Any, later: Any, before_is: str, after_is: str, rng: random.Random | None
) -> Pair:
    """One rollout from each arm, in an order the judge cannot read anything into."""
    example_id, rollout = earlier.example_id, earlier.rollout
    flip = rng.random() < 0.5 if rng is not None else False
    first, second = (later, earlier) if flip else (earlier, later)
    first_is, second_is = (after_is, before_is) if flip else (before_is, after_is)
    return Pair(
        id=f"{example_id}#{rollout}",
        this=first.answer,
        that=second.answer,
        this_is=first_is,
        that_is=second_is,
        example_id=example_id,
        metadata={"rollout": rollout},
    )


def unjudged_pairs(pairs: Sequence[Pair], verdicts: Mapping[str, Any]) -> list[Pair]:
    """The pairs nothing has decided yet, in the order they were given::

        waiting = unjudged_pairs(pairs, read_labels("evals/labels.jsonl"))

    A figure over pairs is computed from verdicts already recorded, so this is what a judging
    pass or a labelling surface is handed.
    """
    return [pair for pair in pairs if pair.id not in verdicts]


def paired_figure(
    pairs: Sequence[Pair],
    verdicts: Mapping[str, Any],
    *,
    name: str,
    definition: str,
    numerator: Callable[[Pair, Any], float],
    denominator: Callable[[Pair, Any], float] | None = None,
    unit: str | None = RATE,
    no_interval: str | None = None,
    confidence: float = DEFAULT_CONFIDENCE,
    resamples: int = DEFAULT_RESAMPLES,
    seed: int = 0,
) -> Metric:
    """A figure over judged pairs, reported the way every other figure is.

    ``numerator`` and ``denominator`` are given the pair and the verdict recorded about it, and
    return that pair's contribution to the two totals. ``verdicts`` is what
    :func:`~simple_agents.evaluation.read_labels` returns, or a plain mapping of pair id to
    verdict; a :class:`~simple_agents.evaluation.Label` is unwrapped to the verdict inside it::

        win_rate = paired_figure(
            pairs, read_labels("evals/labels.jsonl"),
            name="win_rate",
            definition="times the variant was preferred, of pairs with a preference",
            numerator=lambda p, v: chose(p, v) == "variant",
            denominator=lambda p, v: chose(p, v) in ("variant", "baseline"),
        )
        win_rate.numerator, win_rate.denominator     # 7, 14
        win_rate.interval.point                      # 0.5

    **The library holds no opinion about what a verdict says.** A project decides its own set,
    and both rules read ``pair.this_is`` and ``pair.that_is`` to tell which side a verdict
    picked. Recording a fourth verdict for "neither of these was wanted" separates it from "both
    were good and I could not choose", which one figure cannot.

    The interval resamples ``pair.unit``, so pairs from one example travel together. Pairs with
    no verdict are outside both totals and counted in ``left_out`` under ``unjudged``, so a
    figure computed while some are outstanding says how many.

    ``no_interval`` declares the figure a count over this set rather than an estimate, as it
    does on :class:`~simple_agents.evaluation.ProjectRatio`.

    Raises :class:`~simple_agents.errors.ConfigurationError` for no pairs, for two pairs sharing
    an id, and for a rule returning something other than a number.
    """
    _refuse_unusable(pairs, name=name)
    shape = RatioShape(
        name=name,
        definition=definition,
        population="pairs a verdict was recorded for",
        unit=unit,
        no_interval=no_interval,
        has_denominator=denominator is not None,
    )
    grouped: dict[str, list[tuple[float, float]]] = {}
    outstanding = 0
    for pair in pairs:
        recorded = verdicts.get(pair.id)
        if recorded is None:
            outstanding += 1
            continue
        # `read_labels` hands back the Label, and a counting rule is written against the
        # verdict inside it. A project keeping raw verdicts passes them straight through.
        verdict = recorded.verdict if isinstance(recorded, Label) else recorded
        grouped.setdefault(pair.unit, []).append(
            (
                _counted(numerator, pair, verdict, name, "numerator"),
                _counted(denominator, pair, verdict, name, "denominator")
                if denominator is not None
                else 0.0,
            )
        )
    return ratio_metric(
        declared=shape,
        grouped=list(grouped.values()),
        confidence=confidence,
        resamples=resamples,
        seed=seed,
        left_out={"unjudged": outstanding} if outstanding else {},
    )


def _refuse_unusable(pairs: Sequence[Pair], *, name: str) -> None:
    """That there are pairs at all, and that no id names two of them."""
    if not pairs:
        raise ConfigurationError(
            f"paired_figure({name!r}) was given no pairs. A figure over nothing is not a wide "
            f"interval, it is no measurement.\n"
            f"Form the pairs first: pairs_from_arms(before, after) builds them from two "
            f"evaluations."
        )
    seen: set[str] = set()
    for pair in pairs:
        if pair.id in seen:
            raise ConfigurationError(
                f"paired_figure({name!r}) was given two pairs with id {pair.id!r}. A verdict "
                f"is joined to a pair by its id, so one of the two would be scored against a "
                f"verdict recorded about the other.\n"
                f"Give every pair an id of its own."
            )
        seen.add(pair.id)


def _counted(
    rule: Callable[[Pair, Any], float] | None,
    pair: Pair,
    verdict: Any,
    name: str,
    role: str,
) -> float:
    """One pair's contribution, refused unless it is a number."""
    assert rule is not None
    try:
        value = rule(pair, verdict)
    except Exception as exc:
        raise ConfigurationError(
            f"Figure {name!r} raised {type(exc).__name__} in its {role} on pair {pair.id!r}: "
            f"{exc}\n"
            f"Both rules are called once per judged pair and are given the pair and the verdict "
            f"recorded about it. Read pair.this_is and pair.that_is to tell which side a "
            f"verdict picked."
        ) from exc
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not isinstance(value, (int, float)):
        raise ConfigurationError(
            f"Figure {name!r} returned {value!r} from its {role} on pair {pair.id!r}. Each rule "
            f"contributes a number, summed over the pairs and then divided.\n"
            f"Return a count, or True and False where the pair either counts or does not."
        )
    return float(value)
