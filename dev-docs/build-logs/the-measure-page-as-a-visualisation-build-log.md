# Build log — The measure page, as a visualisation

`plan.md` §1 `P3-60`, reopened. Started and built 2026-08-29, in one session, after a design
sitting the same day. The first build is
[`the-measure-page-build-log.md`](the-measure-page-build-log.md#L1): every number on that
page was right and the page was eight accordion cards of tables. This build is the page as a
visualisation, and the fixture it was designed against.

## Where it came from

Thilina, 2026-08-29, after reading the shipped page in a browser:

> And is this results viewer a good UI in your opinion? Is this really what you think a good
> visualization of results looks like? Or is this something half baked that could fit into
> the existing expandable cards format?

The answer was no: it was built inside the page's existing machinery (the `<details>` cards,
the figure row with a thin bar, key/value lists) because that was fast, consistent and
testable. He reopened the item and set the process for it and for every other page:

> The same process of actually discussing the design should be followed for the other pages
> as well. And when I say design, I mean what the thing will look like. It's a visualization
> tool. Visuals are the most important part.

And at the sitting, on the fixture and on mockups:

> I can't judge based on these. Record a second fixture so we do it properly. Make it a
> complex pipeline with multiple metrics and stuff. And show me the actual rendered mock.

> Don't waste your time and mine with the mockups. Just do it in the tool we have. No point
> doing it twice.

## 1. Before any design

- **What the shipped page did that a results page does not**, read off it in headless
  Chrome: the three questions were answered in a sentence inside the third card; the outcome
  bar, the most informative object on the page, was a 22-pixel strip inside a sub-drawer;
  eight full-width figure rows each carried a 0–100% axis and a "the numbers" drawer; the
  example browser was stacked expandable rows with chips; the comparison was eight delta rows
  each with an axis and a paragraph; the ladder was a table.
- **The `dataviz` skill had not been loaded** before the first build drew anything. It was
  loaded first here; its form heuristic put the outcome share on a diverging bar, the
  per-figure comparison on a dumbbell, and every figure on one shared axis.
- **The one fixture with a ladder and a comparison had four examples**
  ([`view_projects/branching`](../../tests/fixtures/view_projects/branching/record.py#L1)),
  so every range was wide and every verdict undecided, and a page designed against it could
  not be judged. Every other view fixture holds no evaluation.
- **The page's rung drill-down never worked in a browser.** Its key is
  `<fingerprint>:<file>` and the wiring split it on the first colon, which a fingerprint
  carries; the harness test passed because [`view_harness.mjs`](../../tests/view_harness.mjs#L1)
  builds the key itself and bypasses the wiring.
- **Lowercase clauses on the page were never decided.** The first prototype set identifiers
  and badge fragments in lowercase and every slot that inherited the style was later filled
  with clauses. [`design/view.md`](../design/view.md#L1) decision 28 is the rule Thilina
  approved.
- **The reader filed every whole-pipeline evaluation of one shape as a rung.**
  [`evaluation.py` `_ladders`](../../src/simple_agents/view/evaluation.py#L551) grouped by
  `graph_fingerprint`, so a project with four whole evaluations showed four "whole pipeline"
  rungs; `branching` has one and never showed it.
- **A results file carries no answer key in words.** `Example.results_entry` records a
  single-valued `label` and nothing for a key with parts, so the browser could say only
  "a key with parts" for what an example expects.

## 2. Design

**The sitting, region by region, in the builder's words.** Seven regions were put as ASCII
wireframes with the choice under each, and Thilina's ruling was to build them in the tool
rather than judge them on a mock. The recommendations were taken as built:

1. **The headline strip.** The headline figure large, and one 0–100% axis under it carrying
   the plausible range, the do-nothing floor as a hollow marker and the previous evaluation
   as a diamond, so where the agent sits between doing nothing and perfect, and where it was,
   is one line. Four tiles beside it: since last time, doing nothing, what measuring cost,
   steps reached. One line of facts under. The alternative, three plain stat tiles, lost
   the "where between" read.
2. **The outcomes as one diverging bar** beside the example grid: the right arm (right,
   right by reporting absence), the wrong arm (partly right, missed, confidently wrong), a
   neutral centre for a rollout that measured nothing. The first design was a five-colour
   ordered scale; the `dataviz` validator found no set passing its adjacent-pair checks on
   any of the five palettes (a grey has no chroma, and two ambers sit too close), and the
   skill's form for an ordered share is a diverging bar. The arms were searched as ordinal
   ramps per palette (two steps on the accent hue, three on the attention hue, the dimmest
   step at the skill's 2.15:1 dark floor) and validated with `--ordinal`; the hexes are the
   `--o-*` tokens in the stylesheet.
3. **The example grid as the hub**: examples down, rollouts across, a square per rollout.
   **Highlight, not filter**: a drill-down lights the rollouts behind a number and dims the
   rest, so the grid keeps its shape and the reader sees where in the set the misses are.
   The shipped page removed rows, and the reader lost their place.
4. **All the figures on one axis**, one row each; a row opens to its numbers. **The
   group-by is a mode of the table**: split by a property of the example and each figure
   grows one row per group on the same axis. The shipped page had a separate section.
5. **The comparison as a dumbbell**, before and after per figure on one axis, moved rows
   first, the verdict in words, the reason once. What differed comes first as the candidate
   cause. The shipped delta bars around zero showed the size of a move and hid where it
   started.
6. **The trend** as before, moved beside the comparison, with the hover layer, and value
   labels only on the reported point and the first.
7. **The rungs as brackets under the steps**, each spanning the steps it ran with its figure
   at the end; selecting one shades the drawing. The alternative, figures written into the
   step boxes, implied each step owns a number.

**The page grid**: strip; outcomes beside grid; figures; comparison beside trend; rungs. On a
narrow screen the regions stack in that order. Nothing that is a chart collapses.

**The fixture, `view_projects/measured`.** An expense-claims project built to be measured:
`intake → extract → policy_check → decide ⇄ audit → dispatch → finance | book → notify`, nine
steps with a bounded revision loop, a step that decides for itself with a paid registry
lookup and a consult, a ledger write, and a claim finance cannot settle unattended parked
as an absence. Thirty-six claims (30 held-out, 6 dev) written by hand with their facts, and
every label derived from the policy by
[`examples.py`](../../tests/fixtures/view_projects/measured/examples.py#L1), so a label cannot
disagree with the rules it is scored under. A `Criteria` key of five conditions, `expected_by_node`
labels on `extract` and `decide` (which also make the two rungs), a `ProjectMetric` in pounds,
a `ProjectRatio`, a per-node ratio, and `category` as a group key beside `source`.
[`record.py`](../../tests/fixtures/view_projects/measured/record.py#L1) is the spec: two live
runs, three earlier evaluations (two of the decide prompt as first written, one of the
current), the reported one at k=2, two rungs, and a sweep of two variants.

**The variant that removed the audit was refused** by `plan_variant`: without the audit
`decide` has one in-edge and receives a dict where it received a `Join`, and a variant
reshaping a step's input is not comparable. It became "audit cannot send back" (the loop
bound at one), which keeps every shape and holds on every figure; "finance without the
registry" moves two.

**The size.** 302 runs and 27MB as recorded, against 2.6MB for `branching`. **Pruned on
Thilina's ruling, 2026-08-29**: `record.py` keeps the reported evaluation's run directories
(the walk opens them) and the two dev runs, and drops the eight other evaluations' run
directories and the sweep's own cassettes, which the page reads only through their results
files. 9.5MB committed. `--sweep-only` re-records the sweep alone against the reported
evaluation on disk, clearing the last sweep's arms first, which is the re-record after a
change that moves only what a comparison writes.

## 3. Build

What shipped:

- [`template.html`](../../src/simple_agents/view/template.html#L1): `measureSection` and the
  region functions replace the accordion (`browserSection`, `outcomeBar`, `criteriaTable`,
  `groupsSection`, `comparisonSection`, `trendSection`, `ladderSection`, `figureRow`,
  `deltaRow` retired); `--o-*` outcome tokens on all five palettes and the system block; a
  page-level tooltip on everything carrying `data-tip`; the sort, search, cell, figure and
  comparison-pick wiring; and the rung key split at its last colon.
- [`evaluation.py`](../../src/simple_agents/view/evaluation.py#L290): `_expects` reads
  `evals/examples.jsonl` beside the results and `_key_words` says each key in words, so the
  grid's "expects" column reads "the decision is approve; …" or "An absence: …"; `_ladders`
  keeps one whole rung through `_one_top_rung`; `_difference_words` names a tool, a step's
  tools, a loop bound and a step's model for the builder, and a fingerprint is `derived` so
  the page lists it last and in words.
- The `measured` fixture, registered in
  [`build_view_fixtures.py`](../../scripts/build_view_fixtures.py#L52) `RECORDED`, so
  `--record` remakes it and the offline default replays it.
- Tests follow the design: [`test_view_runs.py`](../../tests/test_view_runs.py#L1)'s measure
  tests pin the regions and the drill-downs (a figure's numbers, a rollout's answer, the lit
  grid), the harness handle gains `openFigure` and `openCell`, and
  [`test_view_fixtures.py`](../../tests/test_view_fixtures.py#L1) checks the page's counts
  against `measured`'s record too and that the fixture holds every surface (a moved and a held
  verdict, one whole rung and two cut, a behaviour break, an expects on every row).

3,964 tests, from 3,951. No format moves. `shape_check` records `variants.py`'s two-line growth
deliberately.

Found while building:

- **A variant arm lost the suite's floor.** `compare_variants` built each variant's suite
  without `baseline=` and `judgements=`, so a variant's results file carried no do-nothing
  floor and every written comparison listed `baseline: declared → none` under what differed,
  which the page then showed a builder as if the floor were something the variant took away.
  Fixed in [`variants.py` `_with_pipeline`](../../src/simple_agents/evaluation/variants.py#L1012)
  and recorded in `CHANGELOG.md`; the sweep was re-recorded and now names only the tool and
  the loop bound.
- **The served compare control looked dead.** A comparison it made became a third entry in
  the picker while the page kept showing the first, and both dropdowns reset to the same file
  on every redraw. The picks are kept across redraws, they default to the two newest whole
  evaluations, and a comparison just made is the one shown.
- **What differed is a list.** One line per difference, capitalised, with a fingerprint that
  moved as a consequence left out where a cause is named.
- **The shared chrome took the sentence-case rule in one pass**, on Thilina's ruling: the
  stage strip, the header chips, the dials' options, the drawing's key, the step card's
  labels and badges, the thread and question badges. The walk's captions go with the ship
  page's redesign.
- `figureText` returns markup, and a cell that escaped it printed the tags; `figureWords`
  is the plain form for cells and tooltips.
- Six evaluations on one day put three "The behaviour changed" labels on top of each other
  and six file names on top of each other; past four points the break keeps its line and
  loses its label, and the names alternate heights.
- A segment label that does not fit ("Confidently wrong 12" at 20%) is the count alone; the
  legend carries the words.
- Chrome's `--screenshot` ignores a script appended after `</body>`, because the template's
  body never closes; the headless reads here append it after the whole file.

## 4. Verification

- **Live**: the fixture recorded three times against `gemini-3.1-flash-lite` (the first two
  passes found the rung's `node_matches` naming a cut step and the refused variant), about
  0.03 USD a pass, 300 rollouts each, 7 seconds per six claims at concurrency 6. The reported
  evaluation: accuracy 70.0% (53.3% to 85.0%) over 30 × 2, floor 0 of 30, `correct 34,
  correct_abstention 8, false_confidence 12, missed 4, partially_correct 2`; `extract` right
  95%, `decide` 97%; the history climbs 63 → 63 → 67 → 70; the rung from `policy_check`
  reads 76.7%; "finance without the registry" moves `false_confidence_rate` down 20 points
  and `abstention_rate` up 20, "audit cannot send back" holds everywhere.
- **Offline**: `build_view_fixtures.py` replays all three recorded projects from their
  cassettes and matches the committed outcomes.
- **In a browser**: the page read in headless Chrome at 1500px and 800px, on forest, paper
  and dawn, at rest and with an outcome lit, a rollout open, a figure's numbers open, split
  by category, the second variant picked, a rung selected, and a tooltip shown. Each region
  was read before the next was written, and eleven defects were found that way and fixed
  (§3).
- **The harness** runs every fixture's page including `measured`, smallest drawn type 11px,
  and drives the drill-downs through the page's own functions.
- Full suite, `prose_check`, `shape_check`, `check_citations`, `check_docs`: clean.

## 5. Doc consequences

`docs/view.md` §11 rewritten to the page as built: the strip, the diverging bar, the grid as
hub, one axis for every figure with split-by, the dumbbell, the trend, the brackets, and the
pre-measure strip. `CHANGELOG.md` records the variant arm's floor.
[`design/results-visualiser.md`](../design/results-visualiser.md#L98) says which of its
rulings the rebuild superseded and points here for the page's design of record.
[`design/view.md`](../design/view.md#L1) decision 28 records the sentence-case rule.

## 5.1 Reverification, 2026-08-29

Read again while the other five pages were built. **One defect:** every rollout in the grid
offered **Walk this rollout**, and a still page carries only the newest run of each shape and
the rollouts that came out wrong, so on every other rollout the button did nothing. It is
offered where it works: the still page says `Not in this file` with what to run instead, and
the served page fetches the rollout on demand. The walk itself moved to the `build` page at
`P3-62`, and a rollout opened from here says which it is and offers the way back.

## 5.2 Read as a builder, 2026-08-29

Read again at 1440px, still and served, after all six pages were built. The rung sentence
said *rises* where the figure fell: `a` is the rung holding the entered step, and the sign
was backwards. A comparison row over two different example sets said 0.0% beside a dumbbell
that moved, with the reason in a hover; the row says why under itself, and each undecided row
carries its own reason. The trend drew a sweep's arms as the project's behaviour changing;
they are left out and counted. *Walk this rollout* on a rollout the served page fetched
loaded it and changed nothing visible. The grid's *expects* column clipped every row to the
same first clause. Fixed the same day, recorded in `CHANGELOG.md`.

## 6. Left open

- **The harness bypasses the wiring.** Its DOM returns no elements from `querySelectorAll`,
  so a handler that never fires in a browser passes there; the rung key was one. A browser
  read is what caught it and stays the check. Destination: nothing.
- **The walk's captions are still lowercase** ("the run did not reach it", "then …"). They
  go with the walk to the build page. Destination: `P3-62` in [`plan.md` §1](../plan.md#L1).
