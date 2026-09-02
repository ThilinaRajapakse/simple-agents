# Build log — refining the view

`plan.md` §1 `P3-42`. Started 2026-08-28. Written while building, not afterwards.

The item was five named threads with nothing designed, and it closes with four built and one
rejected. Threads 2 and 3 went together because 2's measurement is what settles 3.

## 1. Before any design

Read before anything was decided, and one of these is why the item took the shape it did.

- **[`template.html`](../../src/simple_agents/view/template.html#L708) `drawSystem`.** Every
  pipeline is a fixed 190×64 box in a grid and every resource link is a 1.4px hairline. The run
  count is text at 10.5px inside the box, so a pipeline that ran 2,393 times and one that ran
  twice draw identically. Thread 1's whole complaint, confirmed at the source.
- **[`checks.py`](../../src/simple_agents/conformance/checks.py#L1791) `ft_40`.** Reads
  `manifest.json` for `planned: true` and returns `Outcome.PASSED` where the run directory is
  absent. [`ft_14`](../../src/simple_agents/conformance/checks.py#L394) returns
  `Outcome.BLOCKED` on the identical input, and so do `ft_15` and `ft_25`.
- **[`elicitation.py`](../../src/simple_agents/conformance/elicitation.py#L34) `Question`.**
  Its own docstring: the name *"is not text to put to the builder"*. The page was printing it
  as a heading in four places.
- **[`claims.py`](../../src/simple_agents/view/claims.py#L57) `_scored_on_their_own`.**
  `judged_steps` resolves its code side through `coverage["scored"]`, which comes from the
  evaluation results file. The other five rows read the pipeline.
- **`scripts/view_at_stage.py`.** Its own docstring already said the derived `shape` stage is
  *"a built pipeline nobody has run"*, and that a real project at that gate is a different
  `agent.py`. What nobody had done was look at the difference.
- **Thilina's uncommitted pass**, 12 files, read before touching anything: the intent card, the
  four record groups, the `record-group` markup, the vocabulary move from *hands on* to
  *produces*, and the Google Fonts removal.

## 2. Design

The item's record was [`design/view.md`](../design/view.md#L1); its content is here
now and in `design/view.md` decisions 17 to 20.

**Thread 2 was a measurement before it was a build.** The record asked whether the derived
`shape` page and a real skeleton differ enough to matter. `branching` was rewritten with every
callable a `NotBuilt` marker and both pages read side by side. They differ: the derived page
says *"12 steps built, 1 still to build"* with full source on every card, a real skeleton says
*"0 steps built, 13 still to build"* with intent text. Every read of the `shape` page before
this was a reading of a finished pipeline with the runs subtracted. **Weighed and not taken:**
generating the skeleton in a test by walking `branching` and swapping each callable, which
makes drift impossible but tests the transform rather than the page, and would never produce
the case that actually occurs, where the routes are real code and everything else is a marker.

**Thread 3 was decided by that measurement rather than by the record's assumption.**
`design/view.md` had assumed expected/counted/failed since `P3-35`. Measured, it was worse:
`n/a` at three gates and `pass` at `ship`. **Weighed and not taken:** the one-line
`PASSED` → `BLOCKED` fix alone, which is honest and leaves the check unable to see any project
that has not run. Thilina took the larger option knowing it moves a stated rule.

**Thread 1's options and what chose between them**, all Thilina's, are `design/view.md`
decision 19. The deciding argument was `shape`: an encoding keyed on run count draws every box
the same size at the stage the view most matters, and the chosen one degrades to the box that
was already there.

**Thread 4 was rejected**, and `design/view.md`'s "Considered and rejected" carries it.

**Thread 5's question names** were Thilina's instruction mid-build. **Weighed and not taken:**
using `ask` as the heading, which needs no new field and turns 32 answered entries into 32 full
question sentences.

## 3. Build

**Surfaces touched.** `conformance/elicitation.py`, `conformance/checks.py`,
`conformance/run.py`, `cli.py`, `nodes.py` (a docstring), `view/assemble.py`, `view/claims.py`,
`view/findings.py`, `view/template.html`. No format moved: `Question` is not serialised, and
`flow` is computed rather than recorded.

- **`Question.title`**, required, written for all 47. Required so the 48th cannot ship without
  one. `title_of` and `ask_of` in `claims.py` are the join, and `assemble` carries both onto
  every brief entry. Reaches the answered list, the due-questions rows, the decisions list, the
  findings bodies, the composer's "to" line, each comment thread's meta line and
  `simple-agents questions`. The brief key stays the address in `comments.toml`.
- **`ft_40`** reads `agent.py` through `_pipelines_in_the_code` in `run.py`, guarded, and falls
  back to the manifest. It counts at every stage and fails from `ship`. `FT-40` no longer names
  a stage in `docs/failure-taxonomy.md`.
- **`view_projects/skeleton`**, two files, and `tests/test_view_at_shape.py` pinning it to
  `branching`.
- **`read_claims`** takes `measured`; `_CHECKED` records which artifact each row's other side
  comes from; a comparison against one the project has not produced carries `unread`.
- **The system level**: `flow` on each resource card, `flowBetween`, `systemLinks`,
  `pipelineMeasure`, `drawSystemDials`, and a bar and weighted links in `drawSystem`.
- **`_never_agreed_to`** in `findings.py`, and the "Proposed" badge on the pipeline meta line.
- **`tests/view_harness.mjs`** and `tests/test_view_runs.py`, added after the build on
  Thilina's call, and `actions/setup-node` in CI.
- **The readability pass**, added after that: five palettes and a picker, an 11px floor in the
  drawings, `--edge`/`--edge-soft`, the map's own width, the label placer, and
  `tests/test_view_readability.py`. Its own section below.
- **Thilina's duplicate**: `recordGroup` printed `description` in the summary and again inside;
  the inner copy and `.groupintro` are gone.

**3398 tests, from 3308**, 24 of them the page's script executed under `node` and 19 the
page's colours and type sizes parsed out of its own stylesheet.

**What the build found that the design did not know**, in the order it was found.

1. **The derived `shape` page holds up structurally far better than the record predicted.**
   With nothing built, the drawing still derives the joins, the error edge, the schemas on the
   edges, the nested frame and the fan-out. The structural half of the page needs no run, so
   what a skeleton page lacks is narrower than "most of it".
2. **`FT-40` reported `pass` on a project whose every step was a placeholder.** Assumed to be
   half-built; measured, it was wrong in the other direction.
3. **The `shape` page's only urgent finding was an artefact of the stage.** `judged_steps`
   against an evaluation that does not exist yet.
4. **`dogfood-5-frozen` imports and declares zero pipelines**, because it predates the factory
   convention. The first `ft_40` reported `pass` citing `agent.py` on a reading it never got,
   which is the same defect it was closing.
5. **`str.capitalize` lowercases the rest**, so the blocked message read *"which ft-13
   reports"*.
6. **`many-pipelines` was hiding the one measure it had.** Its single run's only figure is
   `ms`; the system dial only rendered where more than one measure was fillable, so the bar
   never drew. The pipeline level already snapped the measure to a fillable one and the system
   level did not.
7. **The page says nothing where a design was never agreed to.** `shape_moved` is `null` then
   and both branches tested `true`/`false`. That is the normal state at `shape`.

## 4. Verification

**No live backend run, and the reason is that nothing here reaches one.** The item changed the
elicitation catalogue, one conformance check, and the view's assembly and drawing. No node
executes, no prompt is built, no client is called. `branching`'s committed live Gemini run and
its evaluation are what the view reads, and both are replayed unchanged.

What was run instead, because a green suite is not verification:

- **`simple-agents check` over `/home/thilina/Projects/dogfood-5-frozen`**, a real project with
  2,393 runs and 2.54 GB of trajectories. This is what found defect 4. It completes in 10.9s
  including the view regeneration, and `load_project` costs 14ms cold and 1ms warm, so the
  second import `check` now makes is not a cost. That project's own venv was re-synced by a
  `uv run` inside it and was checked afterwards: version `0.0.0`, its own wheel, `view` module
  absent, which is correct for a frozen snapshot.
- **`FT-40` over all four gates on `skeleton`**, and over all seven view fixtures. `day-zero`
  has no `agent.py` and reports having declared no step; the six with code all read `agent.py`.
- **The page's own script executed in `node`** against `branching`, `skeleton` and
  `many-pipelines`, under a stub DOM, calling `renderAll` on each. This is what found defect 6,
  and Thilina's answer to it was *"just add node in the test suite then"*, so the throwaway
  became [`tests/view_harness.mjs`](../../tests/view_harness.mjs#L1) and
  [`tests/test_view_runs.py`](../../tests/test_view_runs.py#L1). It renders each of the seven
  fixtures, drives every control on it, and reports what was drawn. **The harness was checked
  against three deliberate regressions** rather than trusted because it passed: the measure
  dial reverted to `usable.length > 1` fails the test named for it; a property read on
  `undefined` inside `flowBetween` fails every shape with the `TypeError` and its stack; and
  a brief key put back as a heading fails the naming test. `node` is pinned in CI, and the
  tests skip without it the way the cassette tests skip without a recording.

### The readability audit, added 2026-08-27 on Thilina's instruction

*"Some text is miniscule. Some are overlapping. Some arrows are barely visible. And that's not
all. Do a full audit."* Measured in headless Chrome rather than read off the source, at four
viewport widths and in both themes, with a probe injected into the rendered page reporting
computed font sizes, contrast ratios, intersecting text boxes and stroke visibility.

**What it found, all three of his and more.** The graph scaled to 0.78 on a 1440 screen, so
9.5px labels rendered at 7.4px, and a wider window never helped because `.wrap` capped at
1500px. Four label pairs intersected, one of them (`more +` against a step's name)
deterministically above 20 characters. Lines a reader follows were drawn in `--line-strong` at
1.3:1 where 3:1 is the floor for a shape. `--faint` failed as text in both themes, 3.85:1 dark
and 2.61:1 light. Five labels truncated mid-word. A pipeline with no runs drew an empty bar
track that read as broken. `[data-theme]` was supported in CSS with nothing on the page to set
it. **Three suspicions measured clean**: nothing clipped by overflow, no control under 24px,
and the 1:1 strokes are the transparent hit areas.

**What shipped**, and `design/view.md` decisions 22 to 24 carry the reasoning: the map breaks
out of the text measure and the rail moves under it below 1720px, so the drawing is unscaled at
every common width; an 11px floor in both drawings and a scale that stops at 0.9; five palettes
and a picker; `--edge`/`--edge-soft` for every line a reader follows; a label placer that
records what it has written; name budgets computed from the box; word-boundary truncation with
the whole text on a `title`; and branch arms labelled by what tells them apart rather than by
the schema every one of them carries.

**Two mistakes of my own, both caught by measuring rather than by looking.** The first
light-mode reading was taken by stamping `data-theme` after the page had drawn, so it measured
dark colours against a light background and reported 1.21:1; SVG fills are literals resolved at
draw time, which is the same fact decision 23 turns into a requirement. The second was worse:
the theme audit stamped the attribute before boot, and `applyTheme(savedTheme())` removed it
again, so five "passing" palettes were all one palette. Seeding the reader's own storage is
what actually selects a theme. **A rendered screenshot is what showed both.**

**Verified against reintroduction.** Each floor was checked by putting the defect back: the
old `--faint`, a 9.5px label, an edge on the border colour, the 0.72 scale threshold and a
10.5px badge each fail the test named for them, and the template was restored after each.

## 5. Doc consequences

- **`docs/failure-taxonomy.md`** FT-40: the `· Stage: ship` field is gone, the **Check.**
  paragraph is rewritten, and the failure message says *"in this project's pipelines"* rather
  than *"in the newest run's pipeline"*.
- **`docs/conformance.md`**: FT-40's surface row, the staged-entries sentence (six to five),
  the `simple-agents questions` paragraph, and §4's sample report regenerated.
- **`docs/view.md`**: the system level's encoding, the store column, the "Design and
  discussion" group's naming rule, and a bullet for a design nobody has agreed to.
- **`docs/run-envelope.md`**: the `planned` manifest field's row.
- **`docs/nodes.md`** is unchanged; `nodes.py`'s `NotBuilt` docstring carries the same sentence
  and was updated there.
- **`CHANGELOG.md`: nothing.** No format moved and no project on disk breaks. FT-40 reports
  differently, which changes a report and not an artifact.

**Shipped statements that stopped being true**: *"from stage `ship` the checks fail while one
remains"* in three places, and *"FT-31, FT-34, FT-36, FT-37, FT-38 and FT-40 also name a
stage"*.

## 6. Left open

- **What starts a pipeline is still prose.** Thread 4's declaration was defeated rather than
  deferred, and what would reopen it is a way to observe what started a run.
  **Destination**: [`design/view.md`](../design/view.md#L358)'s open list, which now says so.
- **The harness is not a browser.** It establishes that the page runs and what it decided;
  whether the result looks right is still read by eye, and the cool-factor constraint is
  Thilina's to judge. **Destination**: nothing.
- **Everything else the five threads named is closed.** Destination: nothing.
