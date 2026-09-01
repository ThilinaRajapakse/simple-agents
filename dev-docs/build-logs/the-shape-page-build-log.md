# Build log — The shape page

`plan.md` §1 `P3-61`. Started and built 2026-08-29, first of the six pages designed at the
sitting that followed `P3-60`'s rebuild. Its `items/` record held the design and is folded
into §2 here.

## 1. Before any design

The design was taken at the 2026-08-29 sitting and is in §2. What was verified about the code
before building it:

- **The `shape` page as it stood**, read in headless Chrome off
  [`view_projects/skeleton`](../../tests/fixtures/view_projects/skeleton/agent.py#L1): the
  system map, the drawing with every step dashed, the step card, and the banner saying two
  pipelines await agreement. The nearest to right of the five pages, and the item's own
  reading of it held up.
- **The data path was a table in a drawer**, filed on `shape` by
  [`template.html` `dataPathSection`](../../src/simple_agents/view/template.html#L3867), and
  its rows carry `took_in_volume` and `handed_on_volume`, which
  [`assemble.py` `_give_the_history`](../../src/simple_agents/view/assemble.py#L124) fills
  from a run. At `shape` there is no run, so both are `null` on every row.
- **Three of the four seams were already computed** and one was not.
  [`claims.py` `_CHECKED`](../../src/simple_agents/view/claims.py#L70) compares
  `agency_boundary`, `consultation` and `tool_effects` against the code; `used_through` is
  prose no code declares and has no counterpart there.
- **A consult tool is named `consult`, not for the project's channel.** The design's wireframe
  wrote `ASKS THE ROTA`; measured against the skeleton, the tool is `consult` and
  `answered_by` is `end_user`. The rota is the project's word for the person and the library
  never learns it.
- **`publish` declares `touches="outbox"` with no direction**, so the wireframe's
  `WRITES THE OUTBOX` is not what the code says. Three of the fixture's four stores are
  undirected.
- **The comment relay takes three kinds**, `comment`, `answer` and `amendment`
  ([`comments.py` `_KINDS`](../../src/simple_agents/records/comments.py#L75)); agreement to a shape is
  none of the last two, since `shape_confirmed` is not a brief entry and an amendment is a
  request to change something.
- **A `changed` decision is not a proposal.**
  [`decisions.py` `STATUSES`](../../src/simple_agents/conformance/decisions.py#L46) holds four,
  and `changed` records what the builder wanted rather than what was proposed.
- **The harness bypasses the DOM.** [`view_harness.mjs`](../../tests/view_harness.mjs#L1)
  returns `[]` from `querySelectorAll`, so anything wired through the DOM passes there
  untested. This is why the story's lighting is read in a browser and the agreement click is
  driven through the page's own function against a live server.

## 2. Design

**The design is the item's**, put as a wireframe at the 2026-08-29 sitting and ruled *"Looks
okay, but I'll need to see the final thing before I know for sure."* Six regions: what waits
on the builder with agreement on the whole design; the drawing; the story beside it; the
seams; the shared state; the decisions with agreement on each. Decided at the sitting: the
story beside the drawing, and one-click Agree.

**Built as drawn, with six departures, each recorded here and none for convenience.**

1. **A seam is a sentence-cased badge, not capitals.** The wireframe wrote `DECIDES FOR
   ITSELF`, `BRANCHES`, `WRITES THE OUTBOX`. [`design/view.md`](../design/view.md#L396)
   decision 28 names a badge as one of the things that is sentence-cased, and it is a standing
   rule rather than a preference, so the marks read `Decides for itself`, `Branches`,
   `Writes outbox`. A store keeps its spelling and is set in monospace inside the badge, which
   is the other half of the same decision. What the capitals were for, making a seam stand out
   in the rail, is done with colour instead: the accent hue for deciding and asking, the
   attention hue for a permanent change, and grey for an undeclared touch.
2. **The seams region has four rows keyed to the four answers, not the wireframe's four
   headings.** The wireframe listed *asks a person, spends money, permanent change, entry
   point*, which is four rows over three brief entries and leaves `agency_boundary` with no
   row at all, though the item names it as one of the four the stage settles. Each row is one
   answer now, and `tool_effects` holds spending and permanence as two parts under one
   comparison, because that is what the entry covers and comparing it twice would report one
   disagreement twice.
3. **A step that only reads holds no seam.** The wireframe marked no read either. Stated
   here because it is a rule and not an omission: a read changes nothing outside the run.
4. **The story numbers every step, so a loop is a row's own fact.** The wireframe wrote
   `4 draft → 5 critique up to 2×` as one line. The numbering has to stay one-to-one with the
   drawing for the cursor to mean anything, so `critique` carries `Branches` and
   `Loops back up to 2×` on its own row.
5. **Agree is offered on a proposed decision only.** The wireframe showed it on the proposed
   one. A `changed` decision already records what the builder asked for, so agreeing to it
   again says nothing; `Amend` is on every decision, since a decision they agreed to is still
   theirs to change.
6. **The data path moves to the `build` page** rather than being deleted. The story is the
   shape page's reading of it, and the table's other half, how much went through each step, is
   filled by a run and belongs where the runs are.

**What agreement is, as built.** The page relays and the coding agent records
([`design/view.md`](../design/view.md#L167) decision 5), so Agree posts a `comment` thread at
the address of the thing agreed to: `project` for the design as a whole, naming the pipelines,
and `decision:<name>` for one decision. `answer` and `amendment` were both wrong: a shape
confirmation is not a brief entry, and an amendment is a request to change something. On a
still page there is no server, so the click fills the writing panel with the words and the
address instead of dropping them.

## 3. Build

What shipped:

- [`cards.py`](../../src/simple_agents/view/cards.py#L294): `_step_intent` and `_seams_of`,
  and the data path's rows gain `intent` and `seams`. The story is a rendering of the data
  path rather than a second ordering of the same steps.
- [`claims.py`](../../src/simple_agents/view/claims.py#L323): `read_seams`, the four answers
  with their code side, what each step holds the seam through, and who answers where a step
  asks. `assemble` hangs it on `data["seams"]`.
- [`findings.py` `_never_agreed_to`](../../src/simple_agents/view/findings.py#L783): the
  finding carries `actions`, which is what puts Agree and Something is wrong in the band.
- [`template.html`](../../src/simple_agents/view/template.html#L1): the story rail in the
  right-hand column (`renderStory`, `lightStep`, `seamMarks`), `seamsRegion`, `stateRegion`,
  `decisionsRegion`, `oneClick` and `agreeToDecision`; every edge gains `data-edge` and a
  `gline` class so lighting is a class toggle rather than a redraw; the findings band renders
  a finding's own actions in place of the button that only goes and looks.
- Tests: [`test_view.py`](../../tests/test_view.py#L793) `TestTheSeamsTheShapeSettles` holds the seams and the story rows as
  data, [`test_view_runs.py`](../../tests/test_view_runs.py#L141) `TestTheShapePage` drives the rendered page's
  regions, and [`test_view_comments_e2e.py`](../../tests/test_view_comments_e2e.py#L111)
  presses both Agree buttons through the page's own function against a live server and reads
  what landed in `comments.toml`.

3,990 tests, from 3,964. No format moves. `shape_check` records `findings.py` at 952 lines,
ten more than its baseline, deliberately: the growth is the two actions on one finding.

Found while building:

- **The seams region said its own title twice.** A row whose single part is the row read
  `Decides for itself / Decides for itself answer_directly`. The part label is there to
  separate spending from permanence, which is the only row with two, so a row whose part is
  itself labels the column `In the code`.
- **Lighting on hover cannot be a redraw.** `drawGraph` builds about a thousand shapes, and
  the cursor moves with the pointer. The lit state is a class on the few elements that change,
  which is also why the visible edge paths needed an identity they did not have.
- **The skeleton had no proposed decision**, so the region's own affordance had no case to
  draw. One was added to its brief (`a_step_that_decides`, a `shape` decision, `proposed`).
  The fixture holds no runs and no cassettes, so this costs nothing to keep current, and
  [`test_view_at_shape.py`](../../tests/test_view_at_shape.py#L25)'s pin is on the pipeline
  rather than on the brief.
- **`escalation` is a `presentation` decision and stays off this page.** The wireframe drew it
  under DECISIONS; the filing rule sends `presentation` to `ship`, and the rule is right.
- **A test quoting the page's own second person fails `prose_check`.** The page says "you have
  not agreed to"; asserting on those words puts them in a source file the check reads. The
  assertion moved to `2 pipelines are drawn`.

## 4. Verification

**What the page looks like, region by region, with the screenshots.** Read in headless Chrome
at 1800px on paper and at 1500px on forest, at rest and with the story's cursor moved.
Screenshots under `scratchpad/shots/`: `p61-a.png` (paper, the whole page), `p61-b.png` (paper,
the lower regions), `p61-forest-a.png` and `p61-forest-b.png` (forest, narrow).

- **What waits on the builder.** One band, `2 pipelines are drawn that you have not agreed
  to.`, with **Agree** filled in the accent and **Something is wrong** quiet beside it, right
  of the sentence. The old `Walk the drawing` button is gone from this finding, which is the
  design's two buttons and not three.
- **The design.** The drawing as before, every step dashed, the store gutter to its right. The
  step under the story's cursor is filled in the accent and its edges are drawn accent and
  thick: `intake` lit, `intake → classify` lit with it. The lighting is visible at a glance on
  both palettes.
- **The story.** A numbered rail, ten rows for `triage`, each carrying the step in monospace
  (amber where not built), one sentence of what it is for, and its seam badges. `7
  answer_directly · Answers from the handbook, and searches the web where it cannot ·
  Decides for itself · Asks a person · Spends money · Touches web` is the row the design was
  drawn around, and it reads as drawn. The cursor row carries an accent bar down its left
  edge. At 1500px the rail sits under the drawing, which is the design's narrow-screen rule
  and comes free from the rail's existing breakpoint.
- **Seams.** Four rows: `Decides for itself`, `Asks a person`, `Spends money or makes a
  permanent change` (two parts, the second reading `None in the code`), `The entry point`.
  Each carries the steps with the tool underneath, then the builder's answer in the serif the
  page uses for their words, or `Unanswered: What it may do outside the run` in amber.
  `answer_directly through web_search` and `publish through consult · answered by end user`
  are the two lines that say what the drawing's dots only hint at.
- **Shared state.** Four rows, the store in monospace and both sides beside it:
  `handbook · Read by triage/answer_directly, triage/research.pick_sources · Written by
  reindex/file_them · Touched by reindex/read_new_notes · Direction undeclared for that step.`
  The undeclared direction is on three of the four stores, which is a true report of this
  fixture and the thing the stage is for.
- **Decisions.** `Decisions · 2 agreed · 1 changed · 1 proposed`, one row each with a filled,
  half or hollow mark, the choice in serif, the reason under it, and the buttons right. Only
  the proposed row carries **Agree**; all four carry **Amend**.

**Left to read by eye and not read here:** the pointer moving down the rail, which a
screenshot cannot show. The lit state was verified by shooting the page with the cursor on
`intake` and confirming the step and its edge changed.

**Live:** no backend call is involved in anything this item touched, and the fixtures it draws
were recorded live at `P3-58` and `P3-60`. What it does touch is the served page, and that is
verified against a real server rather than by inspection: `test_view_comments_e2e.py` starts
`build_server` on the skeleton, presses Agree through the page's own `oneClick`, and reads
`comments.toml` back: one thread, `at = "project"`, `kind = "comment"`, `said = "I agree to
the design as drawn: triage, reindex."`. Agreeing to one decision lands at
`decision:a_step_that_decides` with the snapshot naming it.

**Offline:** `build_view_fixtures.py` replays all three recorded projects and matches.

**Full suite** 3,990 tests, `prose_check`, `shape_check`, `check_citations`, `check_docs`:
clean.

## 5. Doc consequences

[`docs/view.md`](../../docs/view.md#L396) gains §6.5, the shape page region by region, and §6's
preamble now files the data path on `build`. `CHANGELOG.md` records the page's redraw, the two
new regions, one-click agreement and the data path's move. No shipped statement was found
false; §6's filing sentence was made true rather than corrected.

## 5.1 Reverification, 2026-08-29

Read again after all six pages were built, against `shipped`, whose stores have longer names
and recorded accesses. **One defect in the drawing:** a store in the gutter wrote its name and
its access count in the same place, so `claims_inbox 4` rendered as one word over another. The
name's room is what the count leaves, and the whole name is on the element for hover, which is
what the drawing does everywhere else. The harness now reports the story per page, so that it
is drawn on a real project's `shape` page and on no other is checked rather than assumed.

## 5.2 Read as a builder, 2026-08-29

Read again at 1440px, still and served, after all six pages were built. The rail sat under the
drawing on every screen narrower than 1720px, which is every laptop, and left the right half
of the page empty; the story it was designed to light sat two screens below the drawing. The
drawing now decides: the rail sits beside it from 1280px up and scrolls in its own column, and
where the drawing needs the whole width the story and the card sit side by side under it.
Agree posted a thread and stayed offered, so a second click posted a duplicate, and the
builder's own agreement then appeared as a comment waiting on them; a sent one-click reads as
sent, and a thread the builder spoke on last is listed as worth knowing. On the still page
Agree filled a draft the panel never showed. The "if it fails" label sat over the escalate arm;
*Seams · 4 to settle* counted rows; `$0.2`; the dots on a step were in no key. All fixed the
same day, recorded in `CHANGELOG.md`. The reading itself is what
[`design/view.md`](../design/view.md#L323) decision 22 now requires.

## 6. Left open

- **The rail is taller than the drawing on this page**, since the story sits above the step
  card, so a wide window shows white to the left of the card below the drawing. It is the
  map's existing two-column behaviour rather than anything new, and the rail is sticky, so a
  reader scrolling meets the story beside the drawing. Destination: nothing.
- **A store's direction is undeclared on three of the skeleton's four stores**, which the page
  now says four times in two regions. Whether the fixture should declare them is a question
  about the fixture and not about the page. Destination: nothing.
