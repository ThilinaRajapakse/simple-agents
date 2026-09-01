"""The stages a project moves through, and which one it is at.

A stage is a point in the procedure `docs/procedure.md` describes. Each one ends at a gate, and
the gate reads the artifacts the stage was supposed to produce.

    brainstorm  what the builder is trying to build, who for, and on what
    research    what the parts are, and what is already known about each
    shape       what the agent is for, what counts as an answer, where agency sits
    build       the pipeline exists and has run once inside the run envelope
    measure     the labeled set, the split, the scoring rule, and the evaluation
    ship        somebody other than the builder uses it, and the runs say which those are

**The tier decides which stages a project has.** ``prototype`` has five, since a project
claiming no number does not measure. ``evaluated`` and ``trained`` have six. ``ship`` belongs
to all three, because shipping is not a tier::

    from simple_agents.conformance import STAGES, reached, stages_for

    stages_for("prototype")     # every stage but 'measure'
    reached("shape", has_run=True, has_results=False)     # 'build'

A project declares its stage in ``brief.toml``, and the artifacts it has produced can only move
it forward. Nothing moves it back. A brief declaring ``measure`` is at ``measure`` whatever it
has produced, which is what makes the questions of the earlier stages required rather than
skipped.

A project that has declared nothing and produced nothing is at ``brainstorm``, where the
questions are about what it is for rather than about how it works.
"""

from __future__ import annotations

__all__ = [
    "STAGES",
    "STAGES_BY_TIER",
    "FIRST_STAGE",
    "reached",
    "stages_for",
    "up_to",
    "is_stage",
]

# Ordered. `up_to` and `reached` both index into this, so the order is the procedure's.
STAGES: tuple[str, ...] = ("brainstorm", "research", "shape", "build", "measure", "ship")

FIRST_STAGE = STAGES[0]

# `prototype` claims no number, so `measure` is not part of that project's road. Every tier
# keeps `ship`, and a tier this does not name is held to all six.
STAGES_BY_TIER: dict[str, tuple[str, ...]] = {
    "prototype": ("brainstorm", "research", "shape", "build", "ship"),
    "evaluated": STAGES,
    "trained": STAGES,
}


def is_stage(name: str) -> bool:
    """Whether a name is one of the six stages."""
    return name in STAGES


def stages_for(tier: str | None) -> tuple[str, ...]:
    """The stages a project claiming ``tier`` has, in order.

    ::

        stages_for("prototype")     # every one but 'measure'
        stages_for("evaluated")     # every one of the six

    A tier of ``None``, and any name that is not a tier, gives all six, so a caller that
    cannot say what the project claims is held to everything rather than to less.
    """
    if tier is None:
        return STAGES
    return STAGES_BY_TIER.get(str(tier), STAGES)


def up_to(stage: str, tier: str | None = None) -> tuple[str, ...]:
    """Every stage from the first through ``stage`` that ``tier`` includes.

    ::

        up_to("build")                      # 'brainstorm' through 'build'
        up_to("ship", tier="prototype")     # every stage but 'measure'
        up_to("ship", tier="evaluated")     # the same, with 'measure' between the last two

    This is what a gate holds a project to. The requirement is cumulative, so a project that
    declares a later stage is held to the earlier ones as well and cannot skip a question by
    claiming to be past it. It is cumulative over the stages the tier includes, so a project
    claiming no number is not asked what its held-out split is.
    """
    if stage not in STAGES:
        return ()
    included = stages_for(tier)
    return tuple(name for name in STAGES[: STAGES.index(stage) + 1] if name in included)


def reached(
    declared: str | None,
    *,
    has_run: bool,
    has_results: bool,
    has_live_run: bool = False,
    tier: str | None = None,
) -> str:
    """The stage a project is at: what it declared, or what its artifacts show, whichever is later.

    ::

        reached(None, has_run=False, has_results=False)          # 'brainstorm'
        reached("shape", has_run=True, has_results=False)         # 'build'
        reached("build", has_run=True, has_results=False,
                has_live_run=True)                                # 'ship'

    A run directory shows the project reached ``build``, a results file that it reached
    ``measure``, and a run marked live that it reached ``ship``. Declaring an earlier stage does
    not reduce what the project is held to. Declaring a later one is taken at its word, since
    the library cannot know what the builder intends.

    A stage the tier excludes is never returned, so a results file on a project claiming
    ``prototype`` leaves it where it was. ``Brief.read`` refuses a brief that declares such a
    stage, so the combination arrives here only from a direct call, and a declaration of
    ``measure`` at ``prototype`` reads as ``build``.
    """
    included = stages_for(tier)
    candidates = [FIRST_STAGE]
    if declared in STAGES:
        candidates.append(_within(str(declared), included))
    for produced, stage in ((has_run, "build"), (has_results, "measure"), (has_live_run, "ship")):
        if produced and stage in included:
            candidates.append(stage)
    return max(candidates, key=STAGES.index)


def _within(stage: str, included: tuple[str, ...]) -> str:
    """``stage``, or the latest included stage before it where the tier excludes that one."""
    if stage in included:
        return stage
    earlier = [name for name in included if STAGES.index(name) < STAGES.index(stage)]
    return earlier[-1] if earlier else FIRST_STAGE
