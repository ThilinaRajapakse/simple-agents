# Build log — The build page

`plan.md` §1 `P3-62`. Started and built 2026-08-29, second of the six pages designed at the
sitting that followed `P3-60`'s rebuild, and built after [`P3-61`](the-shape-page-build-log.md#L1).
Its `items/` record held the design and is folded into §2 here.

## 1. Before any design

- **The `build` page as it stood**, read off `view_projects/mid-build` and
  `_stages/branching-build`: the drawing with built and unbuilt steps, the change ledger, what
  moved between runs, the step card, and a banner of open decisions. Progress was legible only
  by counting boxes in the drawing.
- **The manifest has carried `constants` since format `0.33`**
  ([`manifest.py` `module_constants`](../../src/simple_agents/records/manifest.py#L830)): a `module`, a
  `name` and the `value` the run started with, for every module-level number reached from the
  node callables. The view read none of it.
- **A `constant` decision names the numbers it settled and a `prompt_rule` decision the nodes
  whose prompts carry the rule**, both under `produces`
  ([`decisions.py` `DECISION_KINDS`](../../src/simple_agents/conformance/decisions.py#L67)).
  Nothing joined either to what the runs recorded except FT-42, which is a count in a terminal.
- **The manifest records a `prompts` map** of `node_id` to `{version, source}`, so which steps
  have a prompt is on disk and what it says is not.
- **`constants` is project-wide, not per step.** `module_constants` walks the modules the node
  callables come from, so a number carries a module and no step. The design's wireframe drew a
  step column.
- **The fixtures the design named carry no constant.** Measured: `mid-build` has no runs at
  all, and `branching` (which `_stages/branching-build` derives from) defines no module-level
  number, so every one of its manifests records `constants: []`. `measured` records two.
- **The claims section was on the `ship` page**, and `P3-56`'s design keeps a form of it there,
  so the two had to be told apart before either was built.
- **The walk was a vertical list on the `ship` page** with a run picker over
  `walkable_runs`, which includes an evaluation's rollouts: `measured` offered six runs, five of
  them rollouts.

## 2. Design

**The design is the item's**, put as a wireframe at the 2026-08-29 sitting and ruled *"Looks
okay, but I'll need to see the final thing before I know for sure."* Five regions: progress;
the drawing; the constants beside the prompt rules; the build against the design; the last run.
Decided at the sitting: the walk moves to `build` now, and one-click Agree on an unconfirmed
constant.

**Built as drawn, with five departures, each recorded here.**

1. **The progress chip's amber is "changed since its last run", not "changed since agreed".**
   A confirmation is one fingerprint over a whole pipeline
   ([`brief.py` `confirmed_shape`](../../src/simple_agents/conformance/brief.py#L207)), so which
   *step* moved since the builder agreed is unavailable and cannot be derived. The chip carries
   what the drawing's amber already means (§6.1 of `docs/view.md`), and the pipeline-level fact
   is a badge on the counts line: still the agreed shape, changed since agreed, or not agreed to
   yet. Saying "changed since agreed" per step would have been a claim the record cannot support.
2. **A constant's third column is where it is reached from, not which step owns it.** The
   record carries a module and the design drew a step. The module alone is noise in a
   single-file project, so the column is the steps whose own source, or whose tools' source,
   writes the name, with the tool named. It is a text match over source the page already shows;
   it reports where a name is written and never that a number is unused, which the docstring
   and the region's own note both say.
3. **The unconfirmed prompt offers "Show me the rule", not "Agree".** The manifest records a
   prompt's version, not its text, so the page cannot show a builder the rule it is asking them
   to agree to. Agreeing to something unseen is not agreement. The step's own name opens the
   code that builds the prompt, and the button asks the coding agent to show the rule and record
   it. The constants keep the design's **Agree**, because the number and where it bites are both
   on the page.
4. **A departure's two resolutions are "The answer is wrong" and "The code is wrong".** The
   wireframe wrote the second as the claim's own words ("It should decide for itself"), which
   reads as broken grammar on four of the six claims (`consultation`'s phrasing is "can stop and
   ask a person"). The general pair carries the same two meanings and the comment each sends is
   built from the claim's own fields, so the words the coding agent receives are specific.
5. **`measured` is the fixture for the constants and the prompt rules.** The item named
   `mid-build` and `_stages/branching-build`, and neither carries a constant or a prompt (§1),
   so the region could not have been seen on either. Two decisions were added to `measured`'s
   brief so both states are drawn: `receipt_threshold` (a `constant` naming
   `RECEIPT_REQUIRED_OVER`) and `refuse_before_escalating` (a `prompt_rule` naming `decide`).
   `mid-build` stays the fixture for progress, the departures and the empty-state notes.

**Where the claims live.** The `build` page's region carries the departure and its two
resolutions, which is actionable while the code is being written. `P3-56` gives the `ship` page
the compact pass-and-fail board its own design draws, over the same data. One reader is
choosing what to change; the other is deciding whether to let other people in.

## 3. Build

What shipped:

- [`constants.py`](../../src/simple_agents/view/constants.py#L1), new:
  `read_constants` and `read_prompt_rules`, the join between what a run recorded and what a
  decision names. `assemble` hangs them on `data["constants"]` and `data["prompt_rules"]`.
- [`walk.py` `walk_run`](../../src/simple_agents/view/walk.py#L127): a walk says whether it is
  a rollout, which is what keeps the build page's picker to the project's own runs.
- [`template.html`](../../src/simple_agents/view/template.html#L1): `progressRegion`,
  `constantsRegion`, `promptRulesRegion`, `departuresRegion` and `lastRunRegion`; `walkSection`
  and `claimsSection` retired; the walk's captions sentence-cased.
- Tests: [`test_view_runs.py`](../../tests/test_view_runs.py#L222) `TestTheBuildPage` holds every region against
  both fixtures, including the two empty-state notes and the rollout that is not offered.

3,999 tests, from 3,990. No format moves.

**One defect found and fixed, and it is a shipped statement that stopped being true.**
[`claims.py` `_spends_or_cannot_be_undone`](../../src/simple_agents/view/claims.py#L53) counted
a step as reaching outside the run only where it held a `SPENDS_MONEY` or `IRREVERSIBLE` tool.
The question it compares against asks *"what may this agent do that reaches outside the run:
spend money, write somewhere permanent, or take an action that cannot be undone?"*, and a
`WRITES` tool writes somewhere permanent. The build page drew the consequence on its first
read: `measured`'s answer says *"only book writes the ledger"*, which is true, and the page
reported it as the loudest kind of disagreement. `WRITES` is counted now, the two phrasings
read "spends money or writes somewhere permanent", and the `shape` page's seam row moved with
it. **Nothing but this page would have shown it**: `_the_brief_disagrees` has fired on that
fixture since the fixture was recorded.

Found while building:

- **The run strip repeated itself.** Each chip carried its route, which names the step the
  arrow already points at, so it read `intake extract → extract policy_check → …`. The route is
  gone from the chip; what stays is which pass of a loop and which item, and only where the same
  step is in the strip more than once.
- **The picker offered five rollouts.** `walkable_runs` adds the rollouts whose examples came
  out wrong, which is right for the measure page's grid and wrong for "the last run".
- **The run's input joined every field.** The first step receives the text and its metadata;
  the strip now shows the longest of them, which is the input a person recognises.
- **A long constant name broke mid-word** (`RECEIPT_REQUIRED_OV` / `ER`) and two decision
  badges overflowed their column. The columns were rebalanced and a badge in that column wraps.

## 4. Verification

**What the page looks like, region by region, with the screenshots.** Read in headless Chrome
at 1700px on paper (`measured`) and at 1500px on slate (`mid-build`). Screenshots under
`scratchpad/shots/`: `p62-b.png` and `p62-d.png` (paper, the regions), `p62-c.png` (slate,
part-built), `p62-e.png` (a step of the strip opened).

- **Progress.** `Progress · 9 of 9 steps built · 9 proven by a run`, nine chips each with a
  filled accent square, the legend under them, and `Still the shape you agreed to` on its own
  line. On `mid-build`: `2 of 3 steps built · 0 proven by a run`, `gather_pool` and `present`
  with a grey square, `judge_books` with a dashed amber outline and amber text, and
  `Not agreed to yet: next_pick`. The four states are distinguishable without colour.
- **Constants.** Four columns. `MAX_AGE_DAYS 90 · finance, policy_check through policy_lookup ·
  [Agree]` and `RECEIPT_REQUIRED_OVER 25 · … · Receipt threshold`. The unconfirmed row's name is
  in the attention colour and carries the one button; the confirmed row carries the decision's
  title, and hovering it shows what was chosen.
- **Prompt rules.** `4 · 3 unconfirmed`. Three rows read `No rule is recorded for this prompt`
  with **Show me the rule**; `decide` carries its rule in full and the decision's name.
- **Build inconsistent with the design.** On `mid-build`, the loud form: *"The answer says
  `judge_books` decides for itself. In the code, `judge_books` is a model call."* in the
  attention colour, the builder's answer under it in serif, and **The answer is wrong** /
  **The code is wrong**. On `measured`, the quiet form: *"`finance` spends money or writes
  somewhere permanent and the answer names only `book`."* with **Add it to the answer**.
- **The last run.** `The last run · 2026-08-28 · 8 steps ran · 0.000473 USD · Completed`, the
  input in serif, then `intake → extract → policy_check → decide → audit → dispatch → finance →
  notify` as chips with arrows, then `Never reached: book.` Selecting `decide` outlines it in
  the accent and opens its record under the strip: what it received, `Then audit · Iteration 1
  of 2`, the model call and what it said.
- **A project with no run** says why both tables are empty rather than drawing empty furniture.

**Live**: nothing this item touched makes a backend call, and the fixtures it draws were
recorded live at `P3-58` and `P3-60`. The two brief decisions added to `measured` are read from
`brief.toml`, which no cassette covers, so no re-recording was needed and the committed records
are untouched.

**Offline**: `build_view_fixtures.py` replays all three recorded projects and matches.

**Full suite** 3,999 tests, `prose_check`, `shape_check`, `check_citations`, `check_docs`:
clean.

## 5. Doc consequences

[`docs/view.md`](../../docs/view.md#L436) gains §6.6, the build page region by region; §6.3
becomes the strip and its opened step; §6's preamble files progress, the constants, the
departures and the last run on `build`. **One shipped statement stopped being true and is
corrected**: §7's table said `tool_effects` compares against "steps holding a `SPENDS_MONEY` or
`IRREVERSIBLE` tool", and it now names `WRITES` too. `CHANGELOG.md` records the page, the join
and that correction.

## 5.1 Reverification, 2026-08-29

Read again after all six pages were built, against `shipped`, which has two pipelines where
`measured` has one. **One defect, and the page said something false.** The constants and the
prompt rules were read off the newest run's manifest, and `shipped`'s newest run is its
background pipeline's: the page showed one number, `RECONCILE_BATCH`, and `None recorded` for
every prompt, on a project that carries six numbers and four prompts. FT-42 had already
written the rule down for the same reason: *"Read across all of them rather than the newest: a
project with more than one pipeline runs whichever it was asked for."* Both readers gather
across the project's own runs now, newest value first, and
[`test_view_runs.py`](../../tests/test_view_runs.py#L258) `test_the_numbers_are_gathered_across_the_runs_not_off_the_newest`
`test_the_numbers_are_gathered_across_the_runs_not_off_the_newest` holds it against the
fixture that found it. `docs/view.md` §6.6 and the region's own sentence were corrected with it.

**One more, read against `many-pipelines`:** a run whose calls could not be priced records a
value of zero and no currency, and the strip's header wrote `0.00` beside the date, which
reads as a run that cost nothing rather than one nothing priced. The cost is shown where there
is a currency to show it in.

## 5.2 Read as a builder, 2026-08-29

Read again at 1440px after all six pages were built. Progress, the page's first region, came
after the drawing and a fully expanded step card, at y≈4,000 of 6,362 on `measured`; it now
sits above the drawing in its own slot. "27 decisions remain for this stage" counted every
stage's required questions under one stage's name and pointed at a section of six; the
finding counts questions, splits them by the stage that asks, and lands on the page that asks
first. "The code is wrong" sent *should decides for itself*; the claim carries a `should`
form. Two routes to one step drew the same arm twice with its count on top of itself, and a
long arm's label landed on a short one's. A list given to a run printed as JSON. Fixed the
same day, recorded in `CHANGELOG.md`.

## 6. Left open

- **`simple-agents report` prints a run's cost to six decimal places**, which the last run's
  header repeats (`0.000473 USD`). Destination: [`plan.md` §2.1](../plan.md#L1)'s existing entry
  on spend precision, which this does not widen.
- **A number reached through a helper neither the step nor its tools name is not found.** The
  region says where a name is written and never that a number is unused. Closing it would mean
  reading the project's whole module graph, which is what the manifest's own walk already does
  without recording the path. Destination: nothing.
