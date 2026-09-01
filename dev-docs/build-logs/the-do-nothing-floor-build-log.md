# Build log — the floor a do-nothing agent sets

`plan.md` §1 `P3-52`. Started 2026-08-28, sitting 6's cheap half, out of dogfood #5's `DF5-I27`.

## 1. Before any design

Both halves of `DF5-D18` were reproduced against current source before anything was decided,
four examples at one rollout each.

| `baseline` returns | outcomes | `accuracy` floor | `failure_rate` floor |
|---|---|---|---|
| `None` | `failed` ×4 | 0.0 | **1.0** |
| `Unknown(reason="did nothing")` | `missed` ×4 | 0.0 | 0.0 |

| `avoided_share` declared | agent | floor |
|---|---|---|
| default `over` | 0.0 | **0.0** |
| `over=Over.ALL` | 0.0 | 1.0 |

**They are two independent defects, and fixing either alone leaves the other.**
[`classify`](../../src/simple_agents/evaluation/outcomes.py#L170) returns `FAILED` for
`answer is None`, which is right for a rollout and meaningless for a pseudo-rollout that ran
nothing; and [`score_of`](../../src/simple_agents/evaluation/metrics.py#L476) decides a
non-asserting rollout without calling `score` under any `over` but `ALL`.

**Checked and found already right**: the `ConfigurationError` for a non-callable `baseline` in
[`EvalSuite.__init__`](../../src/simple_agents/evaluation/runner.py#L255) already names
`Unknown(reason='did nothing')`, so the library had the shape it wanted and let a callable walk
past it. **Checked and found relevant**:
[`ProjectRatio.over`](../../src/simple_agents/evaluation/ratios.py#L124) defaults to `Over.ALL`,
which `P3-48` set for this class of figure, so the same quantity written as a ratio already got a
correct floor and written as a metric did not.

**Measured on dogfood #5's own code**: `scripts/evaluate.py` declares `avoided_over_all` with
`over=Over.ALL` for the judgement suite, with a comment explaining the trap, and the default for
the avoidance suite. Same project, same quantity, right once.

## 2. Design

Taken at sitting 6, 2026-08-28. `items/the-do-nothing-floor.md` carried it and has left `items/`.

**A baseline returning `None` is refused**, naming the example and quoting `Unknown(reason=...)`.
`classify` is untouched: `None` from a real rollout stays `FAILED`. **The baseline runs as a
preflight before the first rollout** — it calls no model and reads only the example, so this
refusal and the existing "baseline raised" refusal stop costing a paid evaluation. **A floor
whose function was never called says so**, terse, in `report()` and in the results file.

**Weighed and not taken.** *Coercing `None` to `Unknown`*: two intents become indistinguishable
and the library guesses. *Changing `ProjectMetric.over`'s default to `ALL`* to match
`ProjectRatio`: every project's numbers move, and the current default is a real service, keeping
`score` from ever meeting an absence. *Refusing the combination*: wrong, because on
`surfaced_share` the structural 0.0 **is** the right floor and the library cannot tell the two
apart. That is also why **no check reads the new field**: a check would fail a correct project as
readily as an incorrect one, and whether `Over.ALL` is right is a judgement about the task.

## 3. Build

**Two functions and one field.** [`evaluation/baseline.py`](../../src/simple_agents/evaluation/baseline.py#L28) `answers_for`
is new: `answers_for` asks the baseline once per example and refuses `None` or a raise, and
`rollouts_for` scores those answers and returns the figures no answer reached.
[`scores_this_rollout`](../../src/simple_agents/evaluation/metrics.py#L495) is the one rule that
`score_of`, `ratio_of` and the floor all read. `EvalResults.baseline_unscored` carries the result.

**Results file `0.27` to `0.28`**, additive. Manifest, trajectory and every other format
unmoved. **Surfaces touched**: `runner.py`, `metrics.py`, `ratios.py`, `results.py`, `cli.py`,
`view/evaluation.py`, four `docs/` pages, `CHANGELOG.md`, `scripts/check_citations.py`.

**3,751 tests to 3,800.**

**The module is new because of the shape ratchet.** `scripts/shape_check.py` failed on eight
units the work grew, and `plan.md` §2.1 says that baseline only shrinks. Thilina chose extraction
over recording the growth: moving the two functions out took `runner.py` from a recorded 2,708
lines to 2,687 and `EvalSuite` from 1,865 to 1,836, both **below** where they were, and confined
`--update` to five small deliberate growths. The baseline gained one entry, `metrics.py` at 802
lines.

**What the build found that the design did not know**, all from the reverification cycles in §4.

## 4. Verification

**Ten cycles**, each one reading the docs, reading the code, cross-verifying the two, testing the
pieces, the full suite, and a live vLLM run. `Qwen/Qwen3-1.7B` on port 8001, five probes: the
refusal, a metric under each `over`, a ratio under a non-`ALL` `over`, `rescore`, and a
part-scored rescore. **Seven defects, and the suite could not see any of them.**

| Cycle | Found |
|---|---|
| 1 | `baseline_unscored` missing from the results-file field table; the `docs/evaluation.md` §4.2 report block's widths and indent invented rather than captured; `EvalSuite`'s docstring silent on the refusal, and at its prose ceiling, so the paragraph was rewritten rather than extended; `against_baseline` reporting a delta against a floor its function never saw |
| 2 | **`ratio_of` reads the identical rule and its floor was silent.** Measured: a ratio's two totals are both zero, so the figure is undefined and `_floor` printed nothing at all, with no reason. `ratio_of` reads `scores_this_rollout` now, the floor covers every project figure, and the reason prints where the floor would be |
| 3 | `scores_this_rollout` imported into `runner.py` and unused after the extraction; its annotation said `ProjectMetric` while taking either kind |
| 4 | `rescore` exercised by no test; `_measurement`'s docstring claimed to be "what the text report says" and carries no floor at all; a duplicate `from typing import Any` in `cli.py`, pre-existing |
| 5 | **The floor was over the whole split on a part-scored evaluation.** A `rescore` of 4 rollouts of a 10-example split printed `n=4` on the figure and `doing nothing, over 10 example(s)` under it: two populations, two interval widths, "not separated from it" decided against the wrong one, and `against_baseline` pairing examples the agent never answered. The report's own INCOMPLETE line says every figure is over what ran |
| 6 | Six shipped statements describing the floor's population went stale with that fix; `check_citations --fix` repaired a drifted anchor and a blank-line anchor and abandoned one past the end of the file, though the subject named beside it resolves the same way |
| 7 | **The view counted a right report of absence as wrong.** `DF5-X20` |
| 8 | `docs/view.md` said "counts over the same split" and never defined right; no view fixture holds a `correct_abstention`, which is why 3,796 tests were green over cycle 7's defect |
| 9, 10 | Nothing. The gate on a fixture project, the page rendered in headless Chrome, and the wheel checked for the changed documents and the new module |

**Cycle 7 is the one worth reading.** `view/evaluation.py` held its own list of right outcomes,
`{"correct", "correct_absent", "right_abstention"}`, and the outcomes are `correct` and
`correct_abstention`. Measured on three rollouts whose `results.report()` said accuracy 100%: the
page said **1 of 3**, its floor of two right abstentions said **0 of 3**, and an example that
abstained rightly was listed among those that went wrong. The page contradicted itself in adjacent
sentences. It reads
[`Outcome.succeeded`](../../src/simple_agents/evaluation/outcomes.py#L132) now, four tests fire on
it, and the missing fixture is [`P3-51`](../design/results-visualiser.md#L1)'s.

## 5. Doc consequences

**`docs/evaluation.md`** §4.2 gains the refusal and the `Over.ALL` guidance with a verbatim report
capture; §6.4 says the floor is over what ran; §11.2 says a figure about refraining wants
`Over.ALL` and that `ProjectRatio` reads the same rule; §8's field table gains `baseline_unscored`.
**`docs/view.md`** says what right means. **`docs/index.md`** says the floor is over the examples
that ran. **`CHANGELOG.md`** carries three entries: the refusal, the new field, and the
part-scored floor, which is breaking for a part-scored evaluation and changes nothing for a
complete one.

**Shipped statements that stopped being true**, all corrected here: six saying the floor is over
"the split that ran"; `_measurement`'s docstring in `cli.py`; and the view's counts, logged as
`DF5-X20` in dogfood #5's §2 because it is a number a builder read.

## 6. Left open

- **`simple-agents report --json` carries no floor.** [`plan.md` §2.1](../plan.md#L52). The gap
  predates this item, which widened it by one field.
- **A view fixture holding a right report of absence.**
  [`design/results-visualiser.md`](../design/results-visualiser.md#L1), folded into
  `P3-51`, which already carries those fixtures.

Nothing else.
