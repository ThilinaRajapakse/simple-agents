# Build log — What a figure is reported against

`plan.md` §1 P3-27. Started 2026-08-19, built 2026-08-20. Written while building.

Dogfood #4's sitting 5, closing `DF4-I17` and `DF4-I18`, with `plan.md` §2.2's entry for an
answer that left a `required` condition empty pulled in as a fifth stage.

## 1. Before any design

Everything below was measured against dogfood #4's artifacts and the library as it stood, not
argued. The item record carried them and this log is where they end up.

- **[`bootstrap_ci`](../../src/simple_agents/evaluation/intervals.py#L134) resamples examples and
  holds each example's mean over its own rollouts fixed**, so run-to-run movement at fixed
  examples is outside every interval the library prints.
- **The results file's per-example entry was `split`, `expects_absence`, `absent_parts` and
  `source`.** [`examples.py`, `Example`](../../src/simple_agents/evaluation/examples.py#L53)
  stated that `metadata` is "anything else the project wants carried through to the results",
  and nothing carried it. The project's own `compare_arms.py` re-opened `evals/queue-questions.jsonl`
  and joined on example id because of it.
- **All 30 of the project's results files carried one frozen baseline sentence**, naming a
  `held_out` split of 20/14/2 at 0.56. The set as it stands is 22/6/1 at **0.759** on `held_out`
  and 23/10/1 at **0.676** on `dev`, and 15 of the 30 are `dev` runs carrying the `held_out`
  sentence. `brief.toml` reports 0.82 [0.68, 0.94] against 0.76, so the interval contains the
  true floor and clears the stale one by 26 points.
- **`required` moved a rollout between denominators.** Reproduced through
  [`classify`](../../src/simple_agents/evaluation/outcomes.py#L170): a record asserting
  `vendor="Acme"` and silent on a `required` `po_number` is `missed`, counted in
  `abstention_rate` ("rollouts that reported absence") and excluded from
  `precision_when_asserting` ("over rollouts that asserted anything"). Both contradict the
  figures' own definitions, and the exclusion **raises** the second, since a `missed` rollout
  scores 0.0 in it.
- **`_eval_id` does not cover `matches`**
  ([`runner.py`, `_eval_id`](../../src/simple_agents/evaluation/runner.py#L1162)), so a scoring
  rule is not part of what names a run directory. That is the precedent the baseline follows.

## 2. Design

`items/what-a-figure-is-reported-against.md` was the record and its design is here now.

**Five stages, built 5 → 1 → 2 → 3 → 4** so the denominators every later stage computes over were
corrected first. Four of them move the results file, taken as **one bump, 0.22 to 0.23**.

| # | What | Decided |
|---|---|---|
| 1 | `Example.metadata` and `label` into the results file; `grouped()` readers | Read-time grouping over run-time `group_by=` |
| 2 | `Metric.rollout_noise` from the k rollouts each example already ran | Estimated from one run rather than measured by repeats |
| 3 | `compare()` withholds `moved` inside that noise | Withhold rather than qualify |
| 4 | `EvalSuite(baseline=...)` and `against_baseline()` | Computed, not written into a prose field |
| 5 | `asserted` reads the verdict | A correction, not a per-project toggle |

**Grouping is read-time.** The dogfood decided to report per class *after* seeing its null
result, so a run-time `group_by=` would have made that unavailable on runs already paid for. What
that costs: a grouping key added later changes the set's `content_hash`, since
[`content_hash`](../../src/simple_agents/evaluation/examples.py#L518) hashes each example's full
`to_json()`, so a comparison against earlier evaluations needs `allow_different_sets=True`. Stated
in `docs/evaluation.md` §8.2 rather than left to be discovered.

**The label is stored, not only `metadata`.** The dogfood's case is grouping by the right answer,
and requiring the project to duplicate its label into `metadata` reproduces the friction the item
exists to remove. `label` is `expected` where it is a single value, so it is bounded by
construction and a key with parts carries none.

**The cap omits at write rather than refusing at construction.** The library never reads
`metadata`; only project scoring rules do. A construction-time refusal would take away a
legitimate use the library itself created, so `METADATA_CEILING` (64 KiB encoded, per key) leaves
an oversized value out of the file and names it in `metadata_omitted`. Thilina, 2026-08-19: *"be
generous. Don't tunnel vision on just the dogfoods, the library is for the general case."*

**`compare()` needed no new pairing rule.** It already pairs per example, which is finer than per
cell, so the paired difference is free of the mix; the mix problem is in the marginal `before` and
`after`, which [`population_note`](../../src/simple_agents/evaluation/compare.py#L195) is the
precedent for. What grouping adds is a paired difference **per cell**.

**Stage 5 is a correction rather than a declaration.** A per-project flag was §2.2's shape and was
rejected: it makes two results files incomparable on a denominator, `_rules` would have to learn
about it, and most builders cannot answer the question. Rewording the two definitions to match the
shipped behaviour was the other option and leaves the inflation in place.

**No repeat-runs surface and no new `FT-nn`.** Repeats are a documented recipe in
`docs/evaluation.md` §4.1. A check was considered and left out: stage 3 puts the right answer in
the artifact, and `DF3-D1` closed on the finding that asking the `measurement` decision kind was
enough.

**What §2.2 said, and why one entry moved.** Two deferred entries name evaluation figures. The
`required`-condition entry came in as stage 5 on Thilina's decision against its own decider
(*"Waiting for a project to hit something before deciding it's needed is backwards for a
pre-release library"*), which became `P3-28`. The six-answer-shapes entry is touched through
**G2**, whose stated blocker is "the resampling unit is the score's input, which nothing
supports": stage 2's figure is that shape, so G2's seam now exists. Not scheduled, and recorded
so the session that takes G2 is not surprised.

## 3. Build

**2880 tests**, from 2831. Results file `0.22` to `0.23`. Three new test files:
`test_grouped_figures.py`, `test_rollout_noise.py`, `test_do_nothing_baseline.py`.

Surfaces added: `Verdict.asserted`, `RolloutOutcome.asserted`, `Example.results_entry`,
`METADATA_CEILING`, `EvalResults.groups/groupable/grouped/baseline/baseline_metrics`, `Group`,
`Metric.rollout_noise`, `rollout_noise()`, `metrics_over()`, `criteria_over()`,
`MetricChange.rollout_noise/inside_the_noise/noise_half_width`, `Comparison.groups`,
`compare(group_by=)`, `report(group_by=)`, `EvalSuite(baseline=)`, `against_baseline()`.

**What the build found that the design did not know.**

1. **A second case fell out of stage 5.** A record silent on every condition whose silence met a
   criterion declaring `expects_absence` is `partially_correct` and was counted as an assertion.
   `verdict_of` folds silence into a met part, so `Verdict.asserted` is computed **before** that
   fold, in `_criteria_verdict`, where the raw check result is still in hand.
2. **A partial-with-required-empty rollout is now in no rate's numerator.** It is in three
   denominators as a zero and in the outcome tally `report()` prints, so it is not invisible; it
   is named as `missed` rather than counted as an abstention. `test_answer_keys.py`'s
   "every measured outcome is in some numerator" was building rollouts `classify` cannot produce
   and now attaches a verdict only where one exists.
3. **The first noise guard erased a correct negative.** Withholding whenever the difference was
   inside the noise made two identical runs `undecided` rather than `moved=False`. The guard
   belongs only in the branch where the interval **excludes** zero; a difference whose interval
   already includes zero is `False`, and the noise is why rather than a doubt about it.
4. **The threshold arithmetic was wrong first.** `max(noise) × √2` was a conservative fudge. The
   paired difference between two independent runs has variance `before² + after²`, so
   `MetricChange.rollout_noise` is the root of that sum and the test is `|point| ≤ z × it`.
5. **Two refusal messages were misleading**, found by probing edges rather than by a test. A
   grouping key whose values are lists said "no example carries it" when every example did, and a
   grouping that silently dropped examples said nothing. Both fixed and both now tested.
6. **`verdict_reason` named a reason that did not decide.** Found on the first live run: a
   comparison over 13 examples whose difference was also inside the noise reported the noise
   reason, so the reader was told to raise k when no k would have helped. `verdict_reason` now
   walks the same order `moved` does.
7. **The floor line assumed higher is better.** "the interval reaches it" read wrongly on
   `false_confidence_rate` and `failure_rate`. It is `not separated from it` now, which is the
   finding either way.
8. **A baseline that raises gave a bare traceback** after the rollouts were paid for, unlike every
   other scoring rule, which goes through `_call`. It now raises a `ConfigurationError` naming the
   example and pointing at `rescore`.

## 4. Verification

**vLLM, `Qwen/Qwen3-1.7B` on port 8001**, `--enable-prompt-tokens-details --enable-auto-tool-choice
--tool-call-parser hermes --reasoning-parser qwen3`, `--gpu-memory-utilization 0.6`. Mistral is out
of credits. One call preflighted before the run, per `handoff.md`: 14.0s, valid schema object.

Thirteen books, ten fiction to three reference, one `required` condition and one that a partial
answer can leave alone, k=3, two arms of one configuration, and a majority-class baseline.

**What it showed.**

- **The grouped report separated what the pooled figure hid**: accuracy 61.5% overall, **56.7% on
  fiction and 77.8% on reference**. The agent is worse on the majority class and the headline
  does not say so.
- **`rerun ±15.9%`** on accuracy at k=3 with a 1.7B model, printed on the figure's own line.
- **The floor printed under every figure**, and `not separated from it` fired on four of the eight
  rates.
- **The noise guard fired on real data and was right**: two runs of one configuration differed by
  **-0.205** on accuracy against a noise half-width of **±0.225**, and `moved` was withheld.
  Without it that pair reads as a real regression.
- **FT-09 refused the first attempt**, correctly: a classification over a fixed label set needs
  `allow_unknown=False` rather than an `unknown` variant.
- Two defects came out of the live run and nothing else found them: §3 items 6 and 7.

**Re-run after the fixes**, same configuration, to confirm the reason ordering and the floor
wording on real output.

**Against dogfood #4's own artifacts.** The library's `rollout_noise` on each of the three
identical `dev` runs is **0.0175**; the three repeats spread at sd **0.0210**. One run reports for
free what that project paid three evaluations to measure.

**The false-positive rate, measured over 300 pairs of runs of one configuration**, each sampled
from a fixed per-example rate:

| Shape | Interval excluded zero | Guard withheld |
|---|---|---|
| Dogfood #4's: mostly settled, a few uncertain | 12 of 300 | 5 |
| Every example uncertain | 20 of 300 | 7 |
| Nearly deterministic | 0 of 300 | — |

**That rate is what a 95% interval means and is not a defect**, which corrects what the sitting
claimed. What the guard costs on the other side, over 300 pairs where the change is real: nothing
at a true effect of +0.061 (0 of 183 detections withheld), 10% at +0.030, 20% at +0.012.

**Cost.** `report()` with a baseline over 200 examples at k=5 is 0.06s; `grouped()` over two cells
is 0.27s.

## 5. Doc consequences

`docs/evaluation.md` gained **§4.1** (what moves when nothing changes, and the repeat recipe),
**§4.2** (the do-nothing baseline), and **§8.2** (grouping, and what a key added later costs).
§3 gained the paragraph on which denominator an incomplete answer falls in, §8's table gained
`metadata`, `label`, `metadata_omitted` and `baseline`, and `docs/index.md` gained a feature row.
`CHANGELOG.md` carries the bump and five bullets.

**Shipped statements that stopped being true.**

- [`examples.py`, `Example`](../../src/simple_agents/evaluation/examples.py#L53) said `metadata`
  is carried through to the results and it was not. Stage 1 made it true.
- [`answer_key.py`, `Criteria`](../../src/simple_agents/evaluation/answer_key.py#L269) said an
  unmet `required` condition makes the answer `false_confidence` whatever the grade. It returns
  `missed` where the answer asserted nothing wrong, and has since the per-field-absence build.
  Corrected here.

## 6. Left open

- ~~**A named symbol that does not exist disables its own citation check.**~~ **Closed 2026-08-20**,
  on Thilina's decision that an internal tool is just fixed. `check_citations.py` gained a sixth
  rule, `no-such-symbol`, and `tests/test_check_citations.py` a class for it. **The definition test
  was the wrong one**: it reported nine citations here and seven were locals, class attributes and
  string ids, which is the noise that module's own docstring says stops it being read. The test is
  whether the file holds the word at all, which leaves the two real defects it found: `node_state`
  where the class is `SuspensionState`, and `_verdict` where the function is `_criteria_verdict`.
  Both fixed. **Destination:** `nothing`, closed inside this item.
- **G2, self-consistency**, whose seam stage 2 now provides. Stays in
  [`plan.md` §2.2](../plan.md#L136)'s six-answer-shapes entry, which `P3-28` is re-reading.
- **No check reads any of this.** No `FT-nn` fails an evaluation whose figure does not clear its
  floor, or a reported comparison inside its own noise. Deliberate, §2: `DF3-D1` closed on asking
  being enough, and a gate here would fire on an early measurement honestly reported as
  not-yet-separated. **Destination:** `nothing`, until a run produces one that should have failed.
