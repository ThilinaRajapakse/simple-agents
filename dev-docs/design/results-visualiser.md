# The results visualiser

The design of record for the stage-page architecture of `simple-agents view` and its measure
page. It was `P3-51`'s item record; the item was built in three stages on 2026-08-28 and
2026-08-29 ([fixtures](../build-logs/the-view-fixtures-build-log.md#L1),
[shell](../build-logs/the-stage-page-shell-build-log.md#L1),
[measure page](../build-logs/the-measure-page-build-log.md#L1)), and the sitting's rulings
below are what the page does.

## Where it came from

Thilina, in Thilina's Corner on 2026-08-28, under his common-language thoughts:

> Do we have a good results viewer feature? Overall, stats, per-node, graphs, charts, the works.

Scoped at dogfood #5's sitting 5, 2026-08-28, when the sitting asked whether it could be pulled
into `P3-50`. His answer, which is what this item is:

> Pull in what you can, create the item for the rest. And what I meant was an actual results
> visualiser view, not just the things I named somehow having a presence in the system view.

**So the subject is a dedicated surface for what an evaluation measured**, not results figures
distributed through the system view. `P3-50` takes the correctness half, which is the cost figures
reaching the view at all; no presentation work went with it, because a chart added to the system
view now would be designing a fragment of what this item exists to design.

## What the problem is

**Most of the figures already exist and are computed twice.** Read before designing anything:

| | Where it is today |
|---|---|
| Overall figures with intervals, populations, and the rollouts left out by cause | [`docs/view.md` §11](../../docs/view.md#L444), and `results.report()` |
| Per-step cost, tool spend, call counts, time inside itself, fan-out items, runs that never reached it | [`docs/view.md` §6.2](../../docs/view.md#L331), and `simple-agents report`'s table |
| Walking one run in the order it happened | [`docs/view.md` §6.3](../../docs/view.md#L342), and `simple-agents report <run> --walk` |
| Charts | An interval bar per figure, edge thickness by traffic. [`view/template.html`](../../src/simple_agents/view/template.html) `figureRow` |
| The last twelve results files with their headline figures | [`view/evaluation.py` `_history`](../../src/simple_agents/view/evaluation.py#L183), rendered as a list under a `<details>` |
| A rung's figures, and the ladder they form | **Nowhere.** `P3-53` makes `pipeline.slice()` return a real `Pipeline`, so a project evaluates the last step alone, then the last two, and so on. Each rung writes an ordinary results file whose `config.slice` names the source pipeline's `graph_fingerprint`, the node set and the cut edges, so four rungs of one pipeline are relatable rather than four unrelated evaluations |

**What is absent entirely: the variant comparison.** `compare_variants` writes a `Comparison`, and
`P3-48` gave it a format version of its own and made `criteria` and `groups` survive the write, so
as of 2026-08-28 there is a complete versioned comparison record and nothing draws it. Dogfood #4's
whole four-arm model comparison, four arms and twenty rollouts, lived in `compare_arms.py` and
printed to a terminal.

**And no trend.** The history is read and listed; nothing draws a headline figure over time.

## What it carries: the view's fixtures, which nothing keeps current

**Folded in on Thilina's call, 2026-08-28**: *"Just add it to `P3-51`. That'll work on the viewer
anyway."* Found while reverifying what dogfood #5 had landed, and deferred to `plan.md` §2.2 for a
night until he ruled it a gap: *"Sounds like a gap if all the fixtures are behind and there's
nothing in place to keep them current."* The §2.2 entry is deleted.

**The two fixture directories are governed differently, and only one is governed.**
`tests/fixtures/projects/` holds 18 projects built by
[`build_conformance_fixtures.py`](../../scripts/build_conformance_fixtures.py#L1), which replays the
committed cassette and applies one named mutation each, and
[`test_conformance.py` `TestTheFixturesAreCurrent`](../../tests/test_conformance.py#L2933) fails
when they drift. All 18 are current. `tests/fixtures/view_projects/` has no generator and no check.

**And what they do not cover cost a live defect.** Found 2026-08-28 in `P3-52`'s seventh
reverification cycle, logged as [`DF5-X20`](../runs/dogfood-5/inventory.md#L79): the view held its
own list of right outcomes naming two that do not exist, so every right report of absence counted
as wrong on the agent's line, on its floor's, and in the list of examples that went wrong. A
report saying accuracy 100% showed as 1 of 3 on the page. **3,796 tests were green over it**,
because **no view fixture holds a `correct_abstention`** and only two hold a baseline block at
all. The code reads `Outcome.succeeded` now, and what this item owes is the fixture: an
evaluation whose examples include one whose right answer is absence, and whose baseline reaches
it, so the page's counts are checked against a report on the same data.

**How far behind, measured 2026-08-28**, across the four directories there that hold runs:

| | Committed | Current |
|---|---|---|
| Manifest | `0.32` | `0.38` |
| Trajectory | `0.27` and `0.28` | `0.29` |
| Results file | `0.25` | `0.27` |

**What that costs, and it is two paths rather than the whole surface.** Those manifests predate
`constants` (`0.33`), `mcp` (`0.34`), `evaluation` (`0.35`), `conversation` (`0.36` and `0.37`) and
`totals.cost.measured` (`0.38`). The view reads two of the five:

- **`evaluation`**, which separates a run from a rollout.
  [`RunHandle.evaluation`](../../src/simple_agents/envelope.py#L304) documents a depth fallback for
  manifests written before `0.35`, and the view's tests take that fallback every time. The field is
  exercised nowhere.
- **`measured`**, the cost floor, read by
  [`runs_overlay.py` `_cost_of`](../../src/simple_agents/view/runs_overlay.py#L384). No fixture
  manifest carries it, so the only coverage is a test that injects the value into assembled data
  rather than reading it off a manifest.

`constants` and `mcp` the view does not read, so they cost nothing today. **The property that is
missing is that the next field the view comes to read starts out unexercised and says nothing.**

**What makes it tractable, checked rather than assumed.** Every fixture project holding runs also
holds its cassettes, so regeneration replays offline against no backend. All three projects still
import and build their pipelines against the current library, six manifest versions of drift
notwithstanding: `one-pipeline` one pipeline, `many-pipelines` three, `branching` two. And no test
names a run id or an evaluation id, so fresh ids cost nothing. *(Corrected 2026-08-28 at the
build: replay works and is the verification path, and it cannot be the regeneration path,
because a served call spends nothing and a replay-regenerated record cannot carry a tool spend.
The committed records are live recordings;
[`build-logs/the-view-fixtures-build-log.md` §2](../build-logs/the-view-fixtures-build-log.md#L28)
is the reasoning.)*

**This section is built, 2026-08-28, as `P3-58`**, the item's first stage under its own id:
[`build-logs/the-view-fixtures-build-log.md`](../build-logs/the-view-fixtures-build-log.md#L1).

## The stage-page architecture, and the family scheduled behind it

**Added 2026-08-28.** A lifecycle read of the view, taken at Thilina's request ahead of this
sitting, mapped a project's life against the page: idea and elicitation, shape, build, measure,
ship and the product, operation, evolution. Shape and build are covered, measure is this item,
and the other areas were thin. The first recommendation deferred them pending evidence from a
future project. Thilina, verbatim:

> Stop tunnel visioning and dogmatic doctrine following. Sometimes we need to build things
> BEFORE somebody demands it. That's what makes a good library or a product, rather than
> playing whack-a-mole

Three items were scheduled behind this one the same day, all ahead of `P3-31`:
[`P3-55`](../build-logs/the-view-before-there-is-code-build-log.md#L1) the view before there is code,
[`P3-56`](../build-logs/the-product-on-the-page-build-log.md#L1) the product on the page, and
[`P3-57`](../build-logs/the-operations-page-build-log.md#L1) the operations page. And on the architecture, verbatim:

> I would place all of them in the queue before P3-31. And given that the plan is to support
> all the stages, maybe we need to think beyond a one pager. Maybe a page per stage, with the
> ability to switch freely of course, with the "homepage" anchored to the current stage?

**So this sitting takes the stage-page architecture first, and the results surface is designed
as the `measure` page under it.** What the shell has to settle:

1. **One artifact, many pages.** The reader gets a page per stage; the file stays one
   self-contained HTML, so offline, shareable-from-a-directory and rewritten-at-every-gate all
   survive. Splitting into real files makes "share the view" mean "share a directory".
2. **Stage and level are orthogonal, so pages share components.** The pipeline graph matters at
   `shape`, `build`, `measure` and in operation; four drawings would drift. One graph component,
   rendered per stage with that stage's overlay: agreement at `shape`, the change ledger at
   `build`, per-node figures at `measure`, live state in operation. A stage page selects the
   question and the overlay, never a second drawing.
3. **A passed stage's page is the standing record plus drift, never a snapshot.** The `shape`
   page after `ship` is the agreed shape and "changed since you agreed", which finally gives
   that ledger an obvious home.
4. **The page set derives from the tier**, as the levels already derive from the project's
   shape (decision 3 of [`design/view.md`](view.md#L152)): a tier without `measure`
   has no `measure` page.
5. **The homepage anchors to the current stage**, read from `brief.toml`'s `stage`, so the
   anchor is read and never guessed.
6. **The shell is separable from the results content.** Per `plan.md` §1's convention a stage
   that ships takes its own id, so the shell may ship first under its own id with the `measure`
   page behind it.

## The measure page as built, 2026-08-29

**The page's design of record is
[`build-logs/the-measure-page-as-a-visualisation-build-log.md` §2](../build-logs/the-measure-page-as-a-visualisation-build-log.md#L64).**
Thilina reopened `P3-60` on 2026-08-29 after reading the first build: every number right, and
eight accordion cards of tables. The page was redesigned at a sitting, region by region as
wireframes, and rebuilt the same day against a new fixture (`view_projects/measured`): a
headline strip answering how good it is on one axis; the outcomes as one diverging bar beside
the example grid, which every drill-down lights; every figure on one axis with a split-by
control; the comparison as a before-and-after chart beside the trend; and the rungs as
brackets under the steps. Of the rulings below, **decision 2's presentation half (expandable
tables, a figure opening to its numbers on click), decision 3's delta rows, decision 5's table
and decision 11's browser as stacked rows are superseded by that build**; their data rules
(what is drawn from the written record, a census as a number, the trend's comparability, a
rung's denominator, the browser as the hub) stand and are what the rebuilt page draws.

## Decided at the sitting, 2026-08-28

Nine decisions put and ruled the same day, in session; the questions they answer are the
numbered list below this section, plus the shell's six points above.

1. **The shell and the mapping, ratified as proposed.** The six architecture points stand. The
   re-homing: `shape` takes the graph with the agreement overlay, the skeleton, what each step
   receives and the data path; `build` takes the build overlay, the change ledger, "what the
   code says", the to-done panel and what moved between runs; `measure` takes `docs/view.md`
   §11 and everything this item adds; `ship` takes the brief-vs-code claims, the threads and
   the checks, and **holds the run record and the walk until `P3-57`**; every page keeps the
   stage strip with free switching, "what waits on you", the palettes and the comment
   mechanism. The shell ships first under its own id, and the `docs/view.md` rewrite rides
   with it.
2. **The page's question, named:** how good is it, where does it lose it, and did the last
   change help. Everything on the page serves one of the three. **Amended by Thilina at the
   ruling: figures first and the numbers always reachable**, a figure opening to its numbers
   on click, expandable tables rather than charts alone.
3. **The comparison, drawn from the written record.** Delta rows around zero with the interval
   on the difference; `moved` sorts first; `undecided` states its reason in words; `changed`
   sits beside the verdict as the candidate cause; `moved_nodes` lands on the shared graph
   component; a group cell is surfaced where the cell moved and the pool did not. The served
   page gets a pick-two control over the history running the same `compare()`; the still page
   draws written records. Before any record exists the section says what one needs and nothing
   more.
4. **Chart or number.** An interval draws a bar with both totals beside the share; a declared
   census is a number with its reason and no bar (`P3-48`, restated); a delta is a bar around
   zero, and no interval means no bar; a trend is a line only over points comparable by the
   decider's own rules, with a visible break where `behaviour_fingerprint` moved; nothing is
   summed across two bases.
5. **The ladder of rungs: graph overlay plus table.** The shared graph shades each rung's node
   set; the table holds one row per rung over its own examples; one sentence per adjacent pair
   says where the figure falls ("falls when `verify` enters"), stated as an observation and
   never as a paired delta, because a rung's denominator is its own examples.
6. **The trend ships here**; the system's history across confirmations goes to
   [`the-operations-page.md`](../build-logs/the-operations-page-build-log.md#L1) as a note, on subject grounds: it is
   design evolution rather than measurement, and its actionable case is already drawn.
7. **Before anything is measured**, the page shows what will be measured from what exists (the
   example file's counts and splits, `judged_steps` where the brief answers it) and the command
   that produces the first number. It never renders empty chart furniture.
8. **The fixtures.** A generator and currency check mirroring
   [`build_conformance_fixtures.py`](../../scripts/build_conformance_fixtures.py#L1);
   `many-pipelines`' drifted run **frozen by name with the reason recorded** and the check
   exempting it, because its staleness is the property under test; and the `DF5-X20` fixture,
   an evaluation holding an example whose right answer is absence with a baseline that reaches
   it, checked against `report` on the same data.
9. **Build order: fixtures, then the shell under its own id, then the measure page.**
   **The fixtures are built as `P3-58` and the shell as `P3-59`, both 2026-08-28**
   ([fixtures](../build-logs/the-view-fixtures-build-log.md#L1),
   [shell](../build-logs/the-stage-page-shell-build-log.md#L1)), **and the measure page as
   `P3-60`, 2026-08-29** ([build log](../build-logs/the-measure-page-build-log.md#L1)), which
   took decision 10's live-figures half with it. Two of
   Thilina's Corner entries folded in at his ruling, the Corner cleaned with no tombstones:
   the results-viewer thought is this item, and **the comments verification is scoped into the
   shell** as an end-to-end browser test: a comment typed on the served page lands in
   `comments.toml`, the coding agent's reply renders back in the thread.
10. **Added by Thilina at the sitting: the builder watches runs live from the viewer.**
    Verbatim: *"the ability to watch runs progress, see what they are doing, watch progress
    and estimates (time, metrics, whatever) live, check intermediate outputs etc. directly
    from the viewer. Right now, the builder is blind to anything the system does live, since
    the coding agent is the one on the terminal."* What exists (`docs/view.md` §6: the
    in-progress banner, steps marked done as records land, in-flight call count) and what this
    adds: **intermediate outputs as their records land** (clipped inline by the 220-character
    rule, and **the served page returns the full record on request**, ruled 2026-08-28: *"a
    full record on request makes more sense than clipping"*; a record too large to parse is
    served raw by the streaming constraint the first prototype recorded),
    **live figures over an evaluation's completed rollouts**, and **estimates only
    where a denominator is declared**: examples × k gives an evaluation one, `over=` gives a
    fan-out one, and a lone run's graph declares none, so the page shows elapsed and does not
    invent a remaining. A live figure over an evaluation's completed rollouts is drawn as
    provisional with its current n, never as the figure. Lands with the shell, because
    watching is cross-stage.
11. **Five surfaces added at the sitting's completeness question** ("are we forgetting
    anything important?"), all agreed 2026-08-28, all read from records that already exist:
    an **example-level browser** (every example × its k rollouts with verdict, grade, and
    answered-against-expected, opening into the walk); a **per-criterion table** for a
    decomposed key (which condition fails most, the rates the comparison's `criteria` deltas
    are computed from); **the evaluation's own cost beside its quality**, per rollout and per
    example, complete since `P3-50`; **the outcome distribution drawn** as one bar; and a
    **group-by control on one run** ([`results.py`](../../src/simple_agents/evaluation/results.py#L229)
    `groups` and `report(group_by=)` exist, the page offers the same). **The browser is the
    hub**: a criterion's rate, an outcome segment and a group cell each open it filtered to
    the examples behind the number, and every row opens into the walk, so no figure is a dead
    end.

## What has to be decided

**All seven were put at the 2026-08-28 sitting and ruled; the section above holds the
rulings.** Kept as written, because they are the questions the rulings answer.

1. **Whether it is a surface of `simple-agents view` or its own page.** The view is the common
   language between builder and coding agent and is about the system; this is about what was
   measured. Whether that is a second view in one file, a second command, or a section of the
   existing page is the first question and it governs everything below. **Reframed 2026-08-28:
   the stage-page architecture above supersedes the either/or.** The question is now the shell's
   shape, and this surface is the `measure` page under it.
2. **What a builder is trying to answer with it.** `P3-35`'s history is the warning: its second
   prototype was rejected as "an audit mirror", built for a finished project rather than for the
   gap. The question this surface answers has to be named before anything is drawn.
3. **What the comparison looks like** when a project has run two arms, and what it looks like
   before it has run any.
4. **Which figures get a chart and which get a number.** `P3-48` settled that a count over one run
   is drawn as a number with its reason and no bar, because a census is not an estimate of a rate.
   That rule extends here and probably is not the only one.
5. **What it says when the project has measured nothing yet**, which is every project before
   `measure` and some after.
6. **How a regenerated fixture keeps a drift that is the point of it.** Two fixtures assert
   opposite states on purpose: `one-pipeline` asserts `not code_moved_since`, which regenerates
   trivially, and `many-pipelines` asserts `code_moved_since` on `ingest`, which cannot be
   regenerated from the current `agent.py` because the step that made that run was replaced by a
   `NotBuilt` afterwards and its code is gone. Three ways out, and the sitting picks one:
   **freeze that one run deliberately and have the currency check exempt it by name with the
   reason recorded**, which is the recommendation and is the only fixture whose staleness is the
   property under test; keep a pre-drift `agent.py` beside the current one, which is a second copy
   of a graph that can drift itself; or test `code_moved_since` another way and drop the assertion.

7. **What a ladder of rungs looks like.** A project evaluating back to front produces one
   results file per rung, each over a different node set and a different example set, and
   `config.slice` is what says they belong together (`P3-53`). The headline figures are not
   comparable across rungs, since a rung's denominator is its own examples, and the shape of
   the loss across them is what the strategy exists to show. Whether that is one chart, a
   table, or a per-node overlay on the graph is open, and it is the first figure on this
   surface that no terminal command already prints.

## What it waits on

`P3-50`, which is ahead of it in §1 and which moves the cost figures every one of these surfaces
reads. Taking this first means drawing figures that are about to change.

[`P3-53`](../plan.md#L1) is above this in §1 and lands the slice provenance both surfaces
read, so the sitting reads a tree that already holds it.

**And it needs a sitting before it can be built.** `P3-35` went through three prototypes and two
rejections, both on framing rather than on mechanics, and "it needs to look the part" is recorded
there as a requirement rather than a preference.
