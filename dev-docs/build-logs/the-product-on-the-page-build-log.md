# Build log — The product on the page

`plan.md` §1 `P3-56`. Started and built 2026-08-29, third of the six pages designed at the
2026-08-29 sitting, after [`P3-61`](the-shape-page-build-log.md#L1) and
[`P3-62`](the-build-page-build-log.md#L1). Its `items/` record held the design and is folded
into §2 here.

## 1. Before any design

- **The `ship` page was a page of leftovers**: the claims, the conversation, the questions
  asked, the run history, the walk, the workspace, the notes and the problems, for a reader
  deciding whether to let other people in.
- **`used_through` is the only thing about the product on the page**, as one line of the
  header's purpose card ([`assemble.py` `_project_intent`](../../src/simple_agents/view/assemble.py#L400)).
- **`design.md` already requires a product section.**
  [`artifacts.py` `DESIGN_SECTIONS`](../../src/simple_agents/conformance/artifacts.py#L60) has
  carried `"The product"` as one of the four FT-34 requires; what FT-34 read of it was whether
  it was empty.
- **The taxonomy already says what a check cannot do here.**
  [`docs/failure-taxonomy.md`](../../docs/failure-taxonomy.md#L775): *"Whether the product's
  surface reaches the agent — the surface is the project's code in whatever form the project
  chose, and no check executes it."*
- **FT-31's rule is `SHIPPED_ANSWERERS`**
  ([`checks.py`](../../src/simple_agents/conformance/checks.py#L793)), `end_user` and
  `nobody`; the page reads that constant rather than restating it.
- **`module_constants` takes callables and walks the modules they come from**
  ([`manifest.py`](../../src/simple_agents/records/manifest.py#L830)), so the same machinery reads a
  surface's own numbers from the module that declares it.
- **`DeclaredPipelines` is the one thing a check gets from importing the project**
  ([`run.py` `_pipelines_in_the_code`](../../src/simple_agents/conformance/run.py#L663)), which
  is where a declared product can reach a check without a second import path.
- **Neither fixture the item named could show a shipped project.** `measured` is at `measure`
  and declares no product; nothing under `view_projects/` had a live run.

## 2. Design

**The design is the item's**, put as a wireframe at the 2026-08-29 sitting and ruled *"Looks
okay, but I'll need to see the final thing before I know for sure."* Three regions: the checks
as a board; the product drawn from a declaration in code; retention beside the brief against
the code. **Decided at the sitting: the product is declared in code**, a `@product_factory`
returning `Product(surfaces=[Surface(...)])`, each surface naming its kind, the pipeline it
calls and the channel it answers through.

**The declaration, as built.** `Surface(name, kind, does=, pipeline=, through=, reads=)` and
`Product(surfaces=[...])`, with `product_factory` registering one product per project. The
four kinds are `docs/product.md` §2's own. Three departures from the sketch, each recorded:

1. **A surface names the channel, not who answers.** The sketch had the surface carrying
   `answered_by`. The channel already declares it and FT-31 already reads it, so a second copy
   could disagree with the first. `through=` names the consultation tool and the page joins
   through it, which is how the surface learns who answers and whether that is a stand-in.
2. **An artifact surface names what it `reads`.** The sketch had only the kind. Without a
   name the surface joins to nothing, and the resource it shows is the one thing the code
   already knows about it.
3. **`records_a_judgement` requires nothing.** The other three each require a name; a
   judgement lands in `evals/labels.jsonl`, which is the library's own path and not the
   project's to name.

**Nothing is written into a run record, and no format moves.** A manifest describes one run of
one pipeline; the product is a project-level declaration and the view already imports the
code. Recording it in every manifest would mean every run carrying something no run uses. The
item's position ahead of `P3-31` was taken in case a format moved, and none did.

**FT-34 reads the declaration against `design.md`'s product section**, and fails where a
declared surface is not named there. Weighed against reporting it under a passing check, which
is what FT-42's complement does: a name match cannot read intent, and the entry's own text
already says it *"cannot read whether any of the file is true"*. What settles it is that the
surface's **name is the project's own word**, chosen by the same coding agent writing the
section, so a miss is a real signal rather than a vocabulary accident; and that **a project
declaring no product is untouched**, so nothing here can fail a project that has not adopted
the declaration.

**The claims are on both pages, drawn differently.** `P3-62`'s region carries each departure
with the two ways out, which is actionable while the code is being written. This page's is a
tick list, because the question here is whether the record is true before other people are let
in. One data source, two readers, and the ship page's rows say where to act.

## 3. Build

What shipped:

- [`product.py`](../../src/simple_agents/product.py#L134), new and exported: `Product`,
  `Surface`, `INTERACTION_KINDS`, `product_factory`, `registered_product`,
  `clear_registered_product`.
- [`view/product.py`](../../src/simple_agents/view/product.py#L1): the declaration joined to
  the code, and what the join could not find.
- [`view/checks.py`](../../src/simple_agents/view/checks.py#L1): the conformance suite run over
  the project, as rows the page draws.
- [`discovery.py`](../../src/simple_agents/view/discovery.py#L23) `LoadedProject`: the product, the module that
  declares it, and that module's numbers, all read while it is still imported.
- [`checks.py` `_surfaces_not_in`](../../src/simple_agents/conformance/checks.py#L667) and
  `_section_of`, with `DeclaredPipelines.surfaces` and `PRODUCT_SECTION` behind them.
- [`template.html`](../../src/simple_agents/view/template.html#L1): `checksRegion`,
  `productRegion`, `retentionRegion` and `briefBoardRegion`.
- The `shipped` fixture and its generator,
  [`build_view_fixtures.py` `build_shipped`](../../scripts/build_view_fixtures.py#L152).

**One defect found, and it was latent before this item.** Loading a project twice in one
process found its product the first time and never again: `load_project` forgets the module it
imported by name, and a module Python has already imported does not run again, so a
registration in a module *beside* `agent.py` happened once. The page and the checks both load
a project in one process, so the page's board disagreed with the terminal's about what the
project declares. `_drop_the_projects_modules` forgets every module whose file is inside the
project directory, which the library's own and every installed package are not. **This
affected `@pipeline_factory` in the same way** and had never been exercised, because every
fixture and every dogfood declared its pipelines in `agent.py` itself.

**The `shipped` fixture is derived, not recorded.** `build_shipped` copies `measured`, moves
the brief to `ship`, adds `surface.py`, `design.md`, `idea.md` and `research.md`, and then
**runs the two claims again under an envelope that says an end user was on the other end**,
against the committed cassettes. The live runs are written by the library rather than edited,
cost nothing, and spend nothing, which is why the priced records the money surfaces are tested
against stay the recorded ones under `runs/dev/`. The brief's `confirmed_against` is the
pipeline's own fingerprint, taken in the same import as the runs: importing a project twice in
one process registers its pipeline factory twice, and the registry refuses.

Found while building:

- **The product drawing collided with itself.** Two surfaces pointing at one pipeline drew
  their arrows on the same row with their labels on top of each other. Every surface keeps its
  own row now, a pipeline sits level with the mean of whatever points at it, and a link
  between two rows curves the way the system map's do.
- **The arrow said what the box said.** Labelled with the interaction's kind it repeated the
  box's own second line; it carries the channel an answer travels through, and is bare where
  there is none.
- **`conformance` and `manifest` are library words.**
  [`test_view.py`](../../tests/test_view.py#L285) holds the page to the builder's vocabulary,
  and both had reached it in a region's prose.
- **A brief key reached the page.** The brief board printed each entry's key beside its title,
  which [`design/view.md`](../design/view.md#L288) decision 18 rules out.
- **An empty panel headed "The pipeline"** was drawn on every page without a drawing. The
  board is what a drawing lives in, so a page without one has no board.

4,029 tests, from 3,990. No format moves. `shape_check` records `template.html`,
`load_project` and `_one_surface` deliberately.

## 4. Verification

**What the page looks like, region by region, with the screenshots.** Read in headless Chrome
at 1500px on paper and on dawn. Screenshots under `scratchpad/shots/`: `p56-a.png`,
`p56-b.png` (paper), `p56-c.png` (dawn, the whole page).

- **Checks.** `Checks · 24 of 25 pass`, then the failing row: a red `✗`, the entry's own title
  `The design the builder agreed to was never written down`, its id in monospace, the reason in
  the attention colour, and **Show me** at the right. Under it the one that does not apply,
  with a `–` and its reason in grey. `What passes · 24` is shut.
- **The product.** `The product · 3 surfaces`, then the drawing: `the finance inbox` (Starts a
  run) and `the finance desk` (Answers a waiting run) curving into `claims`, drawn in the
  accent as the pipeline, which curves on to `the ledger` (Reads the artifact) over the label
  `writes ledger`. The desk's arrow is labelled `consult`. Under it one row a surface, carrying
  what the end user does, `Through consult at claims/finance · answered by end user`, and
  `Written by claims/book`. Then `Parameters CLAIMS_PER_PAGE 25 · REASON_CHARS 240 ·
  STALE_AFTER_HOURS 48`, with the sentence saying they are the surface's own.
- **Retention.** Four rows, each the builder's own answer in the serif the page uses for their
  words.
- **Brief against code.** `6 of 6 agree`, a tick each, titles in the builder's words.
- **A project declaring no product** (`measured`'s ship page) says so and shows the four lines
  that declare one.

**Live**: the fixture's two live runs are real runs the library wrote, replayed from the
committed cassettes; no backend call was made and none was needed, since nothing this item
touched reaches a model. `simple-agents check` over the fixture is what the board draws, and
its verdicts were read in the terminal against the page: 24 passed, 1 failed, 1 not
applicable, the same on both.

**Offline**: `build_view_fixtures.py` replays all three recorded projects and matches.

**Full suite** 4,029 tests, `prose_check`, `shape_check`, `check_citations`, `check_docs`:
clean.

## 5. Doc consequences

[`docs/product.md`](../../docs/product.md#L28) gains §2.1, the declaration and what each kind
names. [`docs/view.md`](../../docs/view.md#L470) gains §6.7, the ship page region by region,
and §6's preamble files the four regions there. **Two shipped statements changed**:
[`docs/failure-taxonomy.md`](../../docs/failure-taxonomy.md#L689)'s FT-34 check and failure
message now say the product section names every declared surface, and the "what no check can
verify" table's product row says what the declaration does and does not settle.
`CHANGELOG.md` records the declaration, the page, the FT-34 widening and the double-load fix.

## 5.1 Reverification, 2026-08-29

Read again against `brainstorming`, a project with a brief and no code, which is the state the
board is least useful in if it is wrong. **One defect:** the count was passing out of passing
plus failing plus blocked, and a blocked check is one that could not run rather than one that
did not pass. A project at its first stage read `6 of 21 pass`, where ten of the fifteen were
waiting on an evaluation and a run it has not made yet. The count is out of what ran, the other
two are named beside it, and a blocked row shows the reason it already carried and the page was
dropping. A message whose first sentence already ended in a full stop was given a second one.

## 5.2 Read as a builder, 2026-08-29

Read again at 1440px, still and served, after all six pages were built. *Show me* on FT-31,
FT-34, FT-40 and FT-42 did nothing: `goTo` looked for a `details` and those regions are
`div`s. The checks board on a project before `measure` read five red failures for
evaluation and run checks with no sentence saying they are expected there; it says so now.
The writing panel sat above the content on every page without a drawing; it follows the
content. Fixed the same day, recorded in `CHANGELOG.md`.

## 6. Left open

- **FT-32 reads the class's own words.** `measured`'s answer said *"the supplier registry
  costs money per lookup"* and the check reported *"the answer mentions no effect of that
  kind"*, because it looks for the words of `spends_money`. The fixture says "spends money"
  now. Whether the check should read intent, or say more precisely what it matched, is a
  question about FT-32 rather than about this page. Destination:
  [`plan.md` §2.2](../plan.md#L1).
- **A surface's own numbers are read from one module.** A product whose surface spans several
  modules gets the declaring one's. Widening it would mean walking the surface's imports, which
  is what `module_constants` does for a run and what no run reaches here. Destination: nothing.
