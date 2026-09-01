# Build log — The view before there is code

`plan.md` §1 `P3-55`. Started and built 2026-08-29, last of the six pages designed at the
2026-08-29 sitting. Its `items/` record held the design and is folded into §2 here.

## 1. Before any design

- **The `brainstorm` page was a sentence and a drawer**, read off `view_projects/day-zero`: a
  purpose card, a banner counting the decisions that remain, an empty pipeline frame, and the
  questions shut in a section. The `research` page was the stage's questions and nothing else.
- **The ghost was decided at `P3-42` and built nowhere.**
  [`design/view.md`](../design/view.md#L138) decision 1, 2026-08-26: a thing decided and still
  shapeless appears as a ghost. Checked again here: `src/simple_agents/view/` and `docs/view.md`
  carried none.
- **The brief has three states and the page needs four.**
  [`brief.py` `BriefEntry`](../../src/simple_agents/conformance/brief.py#L62) records
  `answered`, `deferred` and `unanswered`, and a question a later stage asks is `unanswered`
  in exactly the way one nobody has answered is. Only one of the two is anybody's business
  today.
- **`research.md`'s survey is already machine-read.**
  [`artifacts.py`](../../src/simple_agents/conformance/artifacts.py#L69) `RESEARCH_SECTIONS` names the section and
  the `Outcome` column FT-36 reads, and `_tables_under` parses it, so the material was
  structured and the page drew none of it.
- **A `dependency` decision names the tools it became under `produces`**
  ([`decisions.py`](../../src/simple_agents/conformance/decisions.py#L69)) and nothing joins it
  to the candidate it was chosen over.
- **`questions_at(stage, tier)` gives what each stage asks**
  ([`elicitation.py`](../../src/simple_agents/conformance/elicitation.py#L967) `questions_at`), cumulatively,
  so a stage's own questions are the ones whose `stage` is that stage.

## 2. Design

**The design is the item's**, put as a wireframe at the 2026-08-29 sitting and ruled *"Looks
okay, but I'll need to see the final thing before I know for sure."* Four regions on
`brainstorm` and four on `research`. **Decided at the sitting: five boxes; one-click
Confirmed; columns per part.**

**Built as drawn, with four departures.**

1. **The fifth box is what the end user gets, read from `presentation`.** The wireframe drew
   "Output" and the item named "the output". No `brainstorm` question asks it: the nearest is
   `presentation`, "What a result looks like", which is a `shape` question. So the box is a
   ghost at `brainstorm` by construction, which is what the design wanted of it, and it fills
   in at `shape` without the page changing.
2. **The material and the failure mode are shown once, not per part.** The wireframe put
   "Material: the handbook, answered tickets" and "Failure mode: …" under each column.
   `available_material` and `what_goes_wrong` are one answer each for the whole project, so a
   copy under every column would be the same sentence three times claiming to be about three
   different parts. They are on the same page, in the Questions region, where they are answers.
3. **A part is the survey's own first column, not the `parts` answer.** The item said one
   column per part, citing `parts`, which is a sentence. The survey's rows already carry a part
   each, and grouping by what the table says keeps the page and the file in step.
4. **An adopted candidate does not become a ghost resource on the drawings.** The sitting's
   note said it would. A candidate is a sentence in a markdown table, and a resource on the
   drawing is a string a tool declares; joining them would mean guessing which words name a
   store. Left undone deliberately, and recorded in §6.

## 3. Build

What shipped:

- [`elicitation.py`](../../src/simple_agents/view/elicitation.py#L34), new: `read_stages`, every
  stage's questions in the four states with answered-of-asked, and `read_idea`, `idea.md`'s
  sections with the stage it was confirmed at.
- [`research.py`](../../src/simple_agents/view/research.py#L77), new: `read_research`, the
  deciding factor, the survey grouped by part with each candidate's outcome and reason, and the
  `dependency` decisions joined to the candidates their own words reach.
- [`template.html`](../../src/simple_agents/view/template.html#L1): `ideaRegion`,
  `questionsRegion`, `stagesRegion`, `ideaFileRegion` on `brainstorm`, and
  `decidingFactorRegion`, `candidatesRegion`, `restingRegion`, `saidRegion` on `research`. The
  generic questions section is skipped on both, since each draws every question of its own
  stage rather than the ones still outstanding.
- A new fixture, `view_projects/brainstorming`: the same project as `skeleton` part way through
  its first conversation, with seven answers, one entry deferred to `shape`, and an `idea.md`.
  No code and no runs, so it costs nothing to keep current.
- `shipped`'s `research.md` gains the two supplier candidates, so the join to its `dependency`
  decision has something to light.

Found while building:

- **The box text overflowed the box.** The wrap was computed at 6.4 pixels a character and the
  drawing sets its text in the monospace at 12px, which is 7.3. The line length is the box's
  width in characters of the type it is set in, and a fourth line is folded into the third
  with the clip the drawing already uses.
- **An escaped quotation mark inside a template literal broke the page**, and the harness
  caught it before a browser did: `Missing } in template expression`.
- **`day-zero`'s research page is no longer empty**, which is the point of the item, so the
  test for a page with nothing filed moved to its `shape` page, which at day zero genuinely
  holds nothing.

4,072 tests, from 4,045. No format moves.

## 4. Verification

**What the pages look like, region by region, with the screenshots.** Read in headless Chrome
at 1500px on paper and on forest. Screenshots under `scratchpad/shots/`: `p55-a.png` (paper,
brainstorm), `p55-c.png` (forest, the idea), `p55-d.png` (paper, research).

- **The idea.** Four boxes across and one below: `Who uses it`, `Entry point`, `The agent`,
  `What they get`, with `What it receives` under the agent and an arrow up into it. On
  `brainstorming`, `Entry point` is amber-outlined and reads `Put off to shape`, `What they
  get` is dashed amber and reads `Unanswered`, and the other three carry the builder's words
  clipped to three lines. On `day-zero` all five are dashed and the count reads `5 of 5
  unanswered`. Under it: `Tier evaluated · Finished … · First version …`.
- **Questions.** `7 of 15 answered`, one row a question, open first: a hollow amber mark, the
  title, the question itself, and **Answer**; then the deferred one reading `Put off to shape`;
  then the answered ones with a filled accent mark, their answer, and **Amend**. Optional and
  re-asked questions carry that beside the title.
- **Stages.** Six boxes with `7/15`, `0/5` and so on, the project's own in the accent, the ones
  ahead dashed, arrows between.
- **The idea file.** Five sections read back with their bodies, and **This is right** beside
  **Something is wrong**.
- **The deciding factor.** One sentence in the serif at `--s2`, which is the largest text on
  the page below the header.
- **Parts and candidates.** Four columns, `Reading the fields`, `Applying the policy`,
  `Deciding`, `Checking the supplier`. Under each, a filled square for what was adopted with
  its reason, an outline for what was rejected, a ring for what nobody looked at, and
  `the_supplier_registry rests on it` in the accent under the candidate it names.
- **Decisions resting on it** and **What the builder said about it**: the decision with what it
  chose, the two candidates it weighed, and the builder's quotation at the foot.

**Live**: nothing this item touched reaches a model, and its two fixtures hold no run. The
`shipped` fixture it reads was rebuilt by its own generator and its records are unchanged.

**Offline**: `build_view_fixtures.py` replays all three recorded projects and matches.

**Full suite** 4,072 tests, `prose_check`, `shape_check`, `check_citations`, `check_docs`:
clean.

## 5. Doc consequences

[`docs/view.md`](../../docs/view.md#L570) gains §6.9, the two pages region by region, and §6's
preamble files them. `CHANGELOG.md` records the idea as five boxes, the four question states,
the survey drawn and `idea.md` read back with one click to confirm it. No shipped statement was
found false.

## 5.1 Reverification, 2026-08-29

Read again with the other five. **The type floor was checked on two drawings and there are
now six.** [`test_view_readability.py`](../../tests/test_view_readability.py#L105) `test_nothing_in_either_drawing_is_written_below_the_floor` read the
`font-size` an `el()` call passes and not the one a drawing written as markup carries, which
is how the trend, the rungs, the product, the idea and the history are all written. Every one
of them is at or above the 11px floor and none of it was checked; the check reads both forms
now. The floor itself caught a 10px mark in the stage strip while `P3-57` was being built,
which is what the stylesheet half of it is for.

## 5.2 Read as a builder, 2026-08-29

Read again at 1440px, still and served, after all six pages were built. *Answer it*, the
day-one page's only call to action, did nothing: the brainstorm page draws its questions as a
region and `goTo` looked for a `details`. An answer typed on the served page left the row
open with its Answer button; the row reads *Answer sent* now. The fifth box read
*Unanswered* and counted as such for `presentation`, a `shape` question; it reads *Asked at
shape*, is not counted, and is not offered. The research page of a pre-research project read
"This stage does not ask it" five times, which says the wrong thing; it reads "Not asked
yet". The answered questions were listed twice on both pages. Fixed the same day, recorded
in `CHANGELOG.md`. Thilina, on the wording that was left: *"Write this like a human"*, with
three rewrites and a rule against "Nobody does…"; [`design/view.md`](../design/view.md#L412)
decision 29 records them.

## 6. Left open

- **An adopted candidate does not become a ghost resource on the drawings.** The sitting noted
  it would. A candidate is a sentence and a resource is a string a tool declares, and joining
  them means guessing which words name a store. Destination:
  [`plan.md` §2.2](../plan.md#L1).
- **A candidate described in other words is not joined to the decision that chose it.** The
  same limit the brief-against-code comparison has, stated on the page where it applies.
  Destination: nothing.
