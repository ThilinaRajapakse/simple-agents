# Build log — The measure page

`plan.md` §1 `P3-60`, the third and last stage of the results visualiser item, shipped under
its own id. Started and built 2026-08-28. The stage is the sitting's decisions 2 to 8, 10 and
11: the page that answers how good it is, where it loses it, and whether the last change
helped, with every figure opening to its numbers and every drill-down opening into the
example browser.

## 1. Before any design

- The results file carries everything the browser needs per rollout (`outcome`, `answer`,
  `verdict` with `parts`, `unmet_required`, `left_out`, `trajectory`) and per example
  (`split`, `source`, `label`, `expects_absence`); nothing on the page read any of it beyond
  the outcomes counter and a six-example "went wrong" list.
- [`Comparison.to_record`](../../src/simple_agents/evaluation/compare.py#L416) carries per
  metric a delta with an interval, a three-way verdict with its reason, `changed` as the
  candidate cause, per-node reach and accuracy movement, and per-cell groups. A written
  comparison is a `VariantComparison` under `evals/variants/`, keyed by arm; a plain
  `compare()` is not written anywhere. `EvalResults.grouped` and `groupable` compute cells
  from the rollouts on file.
- The runner's `_Progress` already held the declared total, the outcomes scored so far, the
  cost and a remaining-time estimate, and reached only the `on_rollout` callback. The view
  could not read any of it (the shell's build log §6).
- `compare_variants` had no `max_spend`, so a suite whose pipeline reaches a `spends_money`
  tool was refused by every arm: a project with a paid tool could not sweep at all.

## 2. Design

- **The data is read once, in the view's evaluation reader**, and the page draws it: an
  example browser sorted wrong-first with one row per rollout; the examples behind each
  outcome and each unmet criterion; grouped figures over every groupable key through
  `EvalResults`, with a problem sentence where the file is outside the reader's window; the
  evaluation's cost per rollout and per example; every written variant comparison; the
  history rows widened with the behaviour and the shape each file measured; and ladders,
  which are results files related through `config.slice` to one pipeline, the whole
  pipeline first.
- **The hub.** `browserFilter` is the one piece of state: an outcome segment, a criterion
  row and a group cell each set it to the examples behind their number, the browser renders
  those, and "show all" clears it. A rollout's row opens the walk. Nothing on the page is a
  dead end.
- **Chart or number, as ruled.** A rate with an interval draws a bar; a declared census draws
  a number and its reason; a delta draws a bar around zero with the interval on the
  difference and no bar where there is no interval; the trend joins only points whose
  headline has the same name and definition over the same behaviour, breaks with a dashed
  line where the behaviour moved, and leaves rungs out; nothing is summed across bases.
- **The ladder is a graph overlay plus a table.** A rung shades the drawing to its node
  set, nested steps included through their container's name; the sentence per adjacent
  pair says where the figure falls and which steps entered, as an observation.
- **The live half of decision 10.** `_Progress` moved into
  [`evaluation/progress.py`](../../src/simple_agents/evaluation/progress.py#L101) and writes
  `progress.json` beside the rollouts at the start and after every landing, replaced whole.
  The view reads it into the banner: rollouts scored of the total declared, the share right
  so far marked provisional with its n, the spend, and the runner's own remaining-time
  estimate. Nothing is invented; an older evaluation shows a count and no total.
- **The served pick-two** computes `compare()` on the server, so the verdict and any refusal
  are the library's own words.

## 3. Build

What shipped: the reader's new sections in [`view/evaluation.py`](../../src/simple_agents/view/evaluation.py#L1);
the measure page's sections, the numbers drawer, the delta row, the outcome bar, the
criteria table, the group control, the trend drawing, the ladder and the pre-measure state
in `template.html`; `/compare` in `serve.py`, with the handler's resolution and comparison
moved to module functions; `progress.json` in the runner and its reader in the view;
`max_spend` on `compare_variants`; the branching fixture's rung (`triage().slice(start=
"classify")` over `examples.entering(rung)`, with `intake` labelled in every example) and
its variant arm (the revision loop bounded at one pass, written under `evals/variants/`),
recorded live; the brief naming the results file it reports; tests for all of it.

Found while building:

- **`compare_variants` could not be used by a project with a paid tool** (§1). It takes
  `max_spend` now and passes it to every arm; the documentation says so.
- **The conformance fixtures regenerate with `progress.json` in every evaluation
  directory**, which carries wall-clock figures and would differ on every regeneration.
  `build_conformance_fixtures.py` drops it: it is live progress, and no check reads it.
- **`compare()` accepts a rung against its whole pipeline** where the rung ran over the same
  example ids, so the refusal I expected to test did not come; the pair is legitimately
  comparable, and the test uses a file below the format floor instead.
- **A variable named `held` shadowed the browser's accumulator** when the rollout row became
  its own function; every view test failed at once, which is what a suite is for.
- The results reader's history rows named fingerprints, and the page's own text may not
  carry the word: they name the behaviour and the shape now.
- The brief named no results file, so the page reported whichever file was newest, which
  became the variant's the moment the sweep wrote it. The fixture's brief names its file,
  and the rule that a brief should is what `docs/conformance.md` §3 already says.

**Read back with Thilina in a browser, 2026-08-29**, which found what the harness cannot:
the measure page opened on the drawing with the results at the bottom in shut cards, so the
record now comes first on that page and every page has an explicit section order; "8
rollouts of 4 examples" reads as "4 examples × 2 rollouts"; the trend was drawn at a fixed
height that scaled its labels away and named nothing, and is now labelled per point with its
value and file, inset from the axis, with the numbers under it; the comparison repeated one
three-line explanation under every figure, which is said once with the per-figure count kept
on its row; a sweep's baseline arm is named as the sweep's own and not the reported
evaluation; the facts line carried an example-set hash and a cassette mode, both library
vocabulary; configuration differences are named on the Python side so the page never carries
the word the internals rule refuses; the ship page's rollouts sentence printed paths from the
flat layout; and two plurals. The deeper pass Thilina asked for read every page opened.

3,951 tests, from 3,935. No format moves.

## 4. Verification

- Live: the branching fixture re-recorded against Gemini with the rung and the variant
  arm, ~0.006 USD. The rung reads `correct 4, correct_abstention 2, missed 2` against the
  whole pipeline's `5, 2, 1`, and the ladder sentence says accuracy falls when `intake`
  enters. The variant comparison is undecided on every figure with the reason the library
  gives: four examples carry the metric and a verdict needs twenty.
- The harness drives the drill-downs through the page's own functions: an outcome and a
  group cell filter the browser to the examples behind them, and a rung shades `intake` and
  nothing from `classify` on. The page renders every fixture on every stage page.
- `/compare` over a real socket: two files compared in the library's words; a file below
  the format floor refused with its reason; a path leaving `evals/results/` refused.
- The runner's `progress.json`: written at the start with the declared total and after
  every rollout, read back by the view with the right count and the remaining time.
- Read by eye in headless Chrome with every section opened: the figures and their numbers,
  the outcome bar, the browser (the missed rollout first, its absence answer readable), the
  grouped figures, and the comparison.
- The full suite, `prose_check`, `shape_check` (the `compare_variants` growth recorded
  deliberately: three lines for the parameter), `check_docs` and `check_citations` clean.

## 5. Doc consequences

`docs/view.md` §11 describes the numbers drawer, the browser, the outcome bar, the criteria
table, the grouped figures, the comparison, the trend, the ladder and the pre-measure state,
and the live banner's figures. `docs/evaluation.md` §6.6 says the evaluation keeps
`progress.json`, and §10 shows `max_spend` on `compare_variants`. `CHANGELOG.md` records the
two additions a project meets. The results visualiser item's record moved to
[`design/results-visualiser.md`](../design/results-visualiser.md#L1) as the design of record
for the stage-page architecture and the measure page.

## 6. Left open

- **`progress_of` does not read `progress.json`.** It takes `expected=` from the caller,
  which the file now carries; reading it there is one function and removes the argument's
  reason to exist. Destination: [`plan.md` §2.1](../plan.md#L38).
- **The served pick-two control is exercised at the endpoint and not through the page's
  button**, which the harness DOM cannot click. Destination: nothing; the button calls the
  endpoint the test covers.
