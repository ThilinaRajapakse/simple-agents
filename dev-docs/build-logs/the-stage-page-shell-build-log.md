# Build log — The stage-page shell

`plan.md` §1 `P3-59`, the second stage of [`P3-51`](../plan.md#L28), shipped under its own
id. Started and built 2026-08-28. The stage is the sitting's shell: a page per stage in one
file, the homepage anchored to the project's stage, the ruled section mapping, the
live-watch surfaces the record can honestly fill, and the comments loop verified end to end.

## 1. Before any design

- [`template.html`](../../src/simple_agents/view/template.html) at 3,591 lines: one page,
  every section in four fixed record groups (`design`, `evidence`, `run-detail`, `checks`),
  built by `renderSections` and orchestrated by `renderAll`.
- `stages_for(tier)` existed in [`stages.py`](../../src/simple_agents/conformance/stages.py#L63)
  and reached the view nowhere; the assembled data carried `stage` and `tier` and no page
  set. Brief entries carried no stage; the elicitation `Question` declares one, and
  `asked_at` covers an entry the library never asked. Decisions already carried `kind`.
- [`runs_overlay.py` `live_run`](../../src/simple_agents/view/runs_overlay.py#L476) already
  followed a run's trajectory (steps done, calls in flight); nothing named the evaluation a
  live rollout belongs to.
- **A rollout's outcome exists only in the runner's memory until the results file is
  written.** Nothing on disk carries a scored verdict mid-evaluation, and the eval's
  denominator (examples × k) is declared nowhere a page can read while it runs. This is
  what decided how much of decision 10 the shell can carry (§2).

## 2. Design

- **One artifact, many pages.** The file stays one self-contained HTML; a page is what
  `renderSections` renders for `shownStage`, and the strip switches it. The homepage is the
  brief's stage, clamped into the tier's set; `#stage/<name>` in the address deep-links a
  page, kept up by `history.replaceState`. On a served page a stage change in the brief
  never yanks the builder off the page they are reading.
- **The filing rules**, where the ruled mapping named sections and the elicitation record
  needed a rule: a question and its answer file under the stage that asks it (the entry's
  `asked_at` where the library never asked; an entry with neither files under the project's
  current stage); a decision files by its `kind` (`dependency` → research, `shape` → shape,
  `constant` and `prompt_rule` → build, `measurement` → measure, `presentation` → ship, a
  kind the page does not know → shape); a section whose home page the tier does not have
  lands on `ship`, which every tier keeps. The run-record sections (walk, history,
  workspace, asked, conversation, checks) sit on `ship` until `P3-57`.
- **A page without the drawing keeps the writing surface.** The rail becomes the panel
  alone, addressed to the project unless something on that page was selected; the step card
  never renders where no map is. Findings and walk links that point at another page's
  section switch pages first.
- **Decision 10, cut to what the record can honestly fill.** The shell ships: intermediate
  outputs as records land, **the full record on request** (a `/record/<run>/<sequence>`
  endpoint that scans the trajectory and serves the line raw, never parsing the file), and
  the evaluation a live rollout belongs to with **how many rollouts have finished and no
  invented total**. What it does not ship is live figures over completed rollouts and an
  evaluation's remaining-time estimate: both need the runner to put scored per-rollout
  state and the declared denominator on disk while it runs, which is measurement machinery
  and moves with the measure page (§6).

## 3. Build

What shipped: the stage strip and page state in `template.html` (the four record groups
removed), `stages` and per-entry `stage` in `assemble`, `stage_of` in `claims`, the
`/record/` endpoint in `serve.py`, `_evaluation_around` in `runs_overlay.py`, the full-record
affordance in the walk, the harness refactored into an importable `runPage` that drives
every stage page, [`tests/view_comments_e2e.mjs`](../../tests/view_comments_e2e.mjs) and
[`tests/test_view_comments_e2e.py`](../../tests/test_view_comments_e2e.py#L1) driving the
comment loop over real HTTP both directions, and the `docs/view.md` amendments.

Found while building:

- The e2e driver's fetch wrapper recursed: `runPage` replaces the global `fetch` with the
  wrapper itself, so the wrapper's own `fetch` reference resolved to itself. Captured before.
- The words I chose for the e2e comment were the fixture's own: `mid-build/comments.toml`
  carries the documentation's example thread verbatim, so the first assertion found two.
- A day-zero test assumed the graph draws on the homepage; the homepage at day zero is now
  the brainstorm page, and the nothing-to-draw sentence lives on the shape page.
- **The served open-another-run control 404s on the role-filed layout**, a live defect
  since runs moved under `runs/dev/<date>/`: a page names a run by its bare directory name
  and `/run/<name>` resolved `runs/<name>` literally. Both endpoints resolve a bare name by
  searching every manifest now, rollouts included, and refuse a path that leaves `runs/`.
  Found because the full-record button is addressed the same way; nothing had exercised the
  fetch since the layout moved.

3,933 tests, from 3,923. No format moves.

## 4. Verification

- The harness drives every stage page of all eight fixture projects; a page that throws on
  switching cannot ship. Per-page section placement, board visibility, tier-derived page
  sets and the day-zero anchor are pinned in
  [`test_view_runs.py` `TestTheStagePages`](../../tests/test_view_runs.py#L89).
- The comments loop ran end to end over a real socket: the page's script posted a comment,
  `comments.toml` held it with its snapshot, the thread rendered after the page's own
  refresh; `append_reply` as the coding agent, and a fresh page load showed the reply in
  the thread. The `/record/` endpoint served a real record by sequence, refused a missing
  one and a path that leaves `runs/`.
- Read by eye in headless Chrome: branching's ship page (strip, boardless rail, ship
  sections), day-zero's homepage (five-page strip, no measure page, no drawing), skeleton's
  build page. The full suite, `prose_check`, `check_docs` and `check_citations` are clean.

## 5. Doc consequences

`docs/view.md`: the intro states the page-per-stage shape, the strip, the anchor, deep
links and tier-derived page sets; §5 says where the conversation section sits and that the
writing panel is on every page; §6 opens with where each section sits; the running bullet
gains the evaluation line; §6.3 gains the full record on request. Section numbering is
unchanged, so nothing citing it moved. No CHANGELOG entry: no format a project holds moved.

## 6. Left open

- **Live figures over completed rollouts, and an evaluation's remaining time.** Both need
  the runner to write scored per-rollout state and the declared denominator to disk during
  the evaluation, which is measure-page machinery: the measure page stage of
  [`P3-51`](../plan.md#L28) takes it, and its design should decide what the runner writes
  incrementally and under which format.
- The brainstorm and research pages render thin (their questions and answers, and the
  empty-page sentence): [`P3-55`](../plan.md#L29) is scheduled to fill them.
