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
from ..records.trajectory import utc_now
from ..schema import encode_answer
from .intervals import DEFAULT_CONFIDENCE, DEFAULT_RESAMPLES
from .labels import Label
from .metrics import RATE, Metric
from .ratios import RatioShape, ratio_metric
from .results import EvalResults

__all__ = ["Pair", "pairs_from_arms", "unjudged_pairs", "paired_figure", "paired_results"]


@dataclass(frozen=True, slots=True)
class Pair:
    """Two things a judge is asked to choose between, and what each of them is.

    ``a`` and ``b`` are what the judge sees. ``a_arm`` and ``b_arm`` name what each side is an
    instance of, which is what a counting rule reads, so the order a judge was shown can be
    randomised without the figure changing meaning::

        Pair(id="p001", a=variant_answer, b=baseline_answer,
             a_arm="variant", b_arm="baseline", example_id="q29")

    Two things from one arm may be put side by side, ``a_arm == b_arm``, to rank within it.
    Such a pair falls outside a figure whose counting rule reads the arms, and the measure page
    counts it apart from the pairs decided between two arms.

    ``example_id`` is the resampling unit the interval is taken over. Where several pairs come
    from one example they travel together, as k rollouts of one example do. A pair belonging to
    no example is its own unit.

    ``metadata`` carries whatever the project wants kept beside the pair: which band each side
    was drawn from, which round of a bracket it is, who was asked.
    """

    id: str
    a: Any
    b: Any
    a_arm: str = "a"
    b_arm: str = "b"
    example_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise ConfigurationError(
                "A Pair was given an empty id. The id is what joins a pair to the verdict "
                "somebody recorded about it, so a pair without one cannot be scored.\n"
                "Pass the id the labelling surface used: Pair(id='p001', a=first, b=second)."
            )

    @property
    def unit(self) -> str:
        """What the interval resamples: the example this pair came from, or the pair itself."""
        return self.example_id if self.example_id is not None else self.id

    @property
    def arms(self) -> tuple[str, str]:
        """The two arms, as ``(a_arm, b_arm)``."""
        return (self.a_arm, self.b_arm)


def pairs_from_arms(
    before: Any,
    after: Any,
    *,
    before_arm: str = "before",
    after_arm: str = "after",
    seed: int | None = None,
) -> list[Pair]:
    """One pair per rollout the two evaluations share, each holding both arms' answers.

    The one pairing the library can build itself, because it holds both results files::

        pairs = pairs_from_arms(before, after, before_arm="baseline",
                                after_arm="variant", seed=41)

    Rollout *i* of each arm is paired with rollout *i* of the other, which are the same draw:
    a sweep runs every arm at one seed. An example or a rollout index only one side has is left
    out.

    ``seed`` randomises which arm is shown as ``a``, recording what each side is in ``a_arm``
    and ``b_arm``. A judge shown one arm first prefers it more often than chance,
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
    return [_one_pair(left[key], right[key], before_arm, after_arm, rng) for key in shared]


def _one_pair(
    earlier: Any, later: Any, before_arm: str, after_arm: str, rng: random.Random | None
) -> Pair:
    """One rollout from each arm, in an order the judge cannot read anything into."""
    example_id, rollout = earlier.example_id, earlier.rollout
    flip = rng.random() < 0.5 if rng is not None else False
    first, second = (later, earlier) if flip else (earlier, later)
    first_arm, second_arm = (after_arm, before_arm) if flip else (before_arm, after_arm)
    return Pair(
        id=f"{example_id}#{rollout}",
        a=first.answer,
        b=second.answer,
        a_arm=first_arm,
        b_arm=second_arm,
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
    and both rules read ``pair.a_arm`` and ``pair.b_arm`` to tell which side a verdict
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


MEANINGS = ("a", "b", "both", "neither")
"""What a verdict can mean to the page that draws a session: side ``a`` was preferred, side
``b`` was, both were wanted, or neither was."""


def paired_results(
    pairs: Sequence[Pair],
    verdicts: Mapping[str, Any],
    *,
    figures: Sequence[Metric],
    eval_id: str,
    blind: bool,
    verdicts_mean: Mapping[str, str] | None = None,
    decided_by: str | None = None,
    created_at: str | None = None,
    config: Mapping[str, Any] | None = None,
    totals: Mapping[str, Any] | None = None,
) -> EvalResults:
    """A session of judged pairs as a results file: the pairs, their verdicts and the figures.

    The file is what ``simple-agents view`` draws head to head and what the gates read beside
    every other results file, so a session filed this way is on the record rather than in a
    project's own notes::

        labels = read_labels("evals/labels.jsonl")
        results = paired_results(
            pairs, labels,
            figures=[win_rate, nothing_wanted],
            eval_id="pairwise-gemini-v-glm", blind=True,
            verdicts_mean={"a": "a", "b": "b", "both_good": "both", "both_bad": "neither"},
        )
        results.write("evals/results/pairwise-gemini-v-glm.json")

    ``figures`` are what :func:`paired_figure` returned. ``blind`` says whether the judge saw
    what each side was an instance of, which the page reports beside the session.

    ``verdicts_mean`` says what each of the project's verdicts means, so the page can draw the
    decided pairs between the arms: ``"a"`` and ``"b"`` are the side preferred, ``"both"`` and
    ``"neither"`` the two kinds of tie. A verdict outside the mapping is drawn under its own
    name; the figures read the counting rules and are unaffected.

    ``verdicts`` is what :func:`~simple_agents.evaluation.read_labels` returns, and each
    :class:`~simple_agents.evaluation.Label` supplies who decided and when. A plain mapping
    says neither, so ``decided_by`` is required with one. ``created_at`` defaults to the
    latest ``decided_at`` on file.

    Raises :class:`~simple_agents.errors.ConfigurationError` for a mapping with no decider, a
    meaning outside the four, or a figure named twice.
    """
    _refuse_unusable(pairs, name=eval_id)
    meanings = _refuse_bad_session(eval_id, verdicts_mean, figures)
    rows, deciders, latest = _pair_rows(pairs, verdicts, decided_by, eval_id)
    judged = sum(1 for r in rows if r["decided_by"] is not None)
    filed: dict[str, Any] = {
        "kind": "pairs",
        "contest": sorted({arm for pair in pairs for arm in pair.arms}),
        "blind": bool(blind),
        "decided_by": sorted(deciders),
        "verdicts": meanings,
        "n": judged,
        "k": 1,
        "units": len({pair.unit for pair in pairs}),
        "unjudged": len(rows) - judged,
    }
    filed.update(dict(config or {}))
    return EvalResults(
        eval_id=eval_id,
        created_at=created_at or latest or utc_now(),
        config=filed,
        metrics={f.name: f for f in figures},
        nodes={},
        rollouts=(),
        totals=dict(totals or {}),
        pairs=tuple(rows),
    )


def _refuse_bad_session(
    eval_id: str, verdicts_mean: Mapping[str, str] | None, figures: Sequence[Metric]
) -> dict[str, str]:
    """The verdict mapping, checked against the four meanings, and the figures named once."""
    meanings = dict(verdicts_mean or {})
    wrong = {k: v for k, v in meanings.items() if v not in MEANINGS}
    if wrong:
        raise ConfigurationError(
            f"paired_results({eval_id!r}) was told verdict {wrong!r}, and a meaning is one of "
            f"{', '.join(MEANINGS)}: which side was preferred, or which kind of tie it was.\n"
            f"Map each of the project's verdicts to one of the four, and leave out a verdict "
            f"that means none of them."
        )
    names = [f.name for f in figures]
    if len(set(names)) != len(names):
        raise ConfigurationError(
            f"paired_results({eval_id!r}) was given two figures named "
            f"{sorted({n for n in names if names.count(n) > 1})!r}. A results file holds one "
            f"figure per name.\nName each figure once."
        )
    return meanings


def _pair_rows(
    pairs: Sequence[Pair], verdicts: Mapping[str, Any], decided_by: str | None, eval_id: str
) -> tuple[list[dict[str, Any]], set[str], str]:
    """One record per pair, who decided across them, and the latest ``decided_at``."""
    rows: list[dict[str, Any]] = []
    deciders: set[str] = set()
    latest = ""
    for pair in pairs:
        row: dict[str, Any] = {
            "id": pair.id,
            "a": encode_answer(pair.a),
            "b": encode_answer(pair.b),
            "a_arm": pair.a_arm,
            "b_arm": pair.b_arm,
            "example_id": pair.example_id,
            "verdict": None,
            "decided_by": None,
            "decided_at": None,
            "reason": "",
        }
        held = verdicts.get(pair.id)
        if isinstance(held, Label):
            row.update(
                verdict=encode_answer(held.verdict),
                decided_by=held.decided_by,
                decided_at=held.decided_at,
                reason=held.reason,
            )
        elif held is not None:
            if not decided_by:
                raise ConfigurationError(
                    f"paired_results({eval_id!r}) was given a plain verdict for pair "
                    f"{pair.id!r} and no decided_by. A session on the record says who "
                    f"judged it.\n"
                    f"Pass what read_labels() returns, or decided_by='human' for the "
                    f"whole mapping."
                )
            row.update(verdict=encode_answer(held), decided_by=decided_by)
        if row["decided_by"] is not None:
            deciders.add(str(row["decided_by"]))
            latest = max(latest, str(row["decided_at"] or ""))
        rows.append(row)
    return rows, deciders, latest


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
            f"recorded about it. Read pair.a_arm and pair.b_arm to tell which side a "
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
