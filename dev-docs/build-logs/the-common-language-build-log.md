# Build log — The common language

`plan.md` §1 P3-35. Started 2026-08-26, built overnight the same day on Thilina's
instruction to take it to the end; two prototypes and the reframe that rejected them are in
[`design/view.md`](../design/view.md#L1), which was this item's record. Design of record for
the subsystem lives there; this is how the build went.

## 1. Before any design

- [`recording.py` `_node_entries`](../../src/simple_agents/pipeline/recording.py#L458) already computes
  the manifest's declared half without running, and
  [`graph_fingerprint`](../../src/simple_agents/pipeline/core.py#L2055) `graph_fingerprint` digests
  shape alone, so introspection reuses the manifest's own vocabulary rather than inventing one.
- `agent.py` is the layout's fixed home for the pipeline (`docs/procedure.md`), so discovery
  needed a registration convention and not a search.
- The conformance suite reads only files; nothing in the library imported project code before
  this item, and [`taxonomy.py`](../../src/simple_agents/conformance/taxonomy.py#L28) `_ENTRY`
  `_ENTRY` parses check messages out of `docs/failure-taxonomy.md`, so a new check is a doc
  entry plus one function.
- `source_version` returns `{"version", "source"}` dicts and digests are `sha256:` with 12 hex
  characters, which `NotBuilt`'s entry matches.
- FT-38 already pins brief confirmations to `behaviour_fingerprint`, so the view's "changed
  since" ledger did not need a new confirmation mechanism; it anchors on the newest run.

## 2. Design

The design was settled in conversation with Thilina before the build and is recorded in
[`design/view.md`](../design/view.md#L1): the subject is the design across the project's
whole life and runs are one overlay; skeleton-first with brief ghosts; `touches=`;
four adaptive levels; the comment record with the builder's gate toggle; validation across
five project shapes plus the frozen dogfood. Weighed and not taken during the build:

- **A `--no-view` flag on `check`** for tests that run gates over committed fixtures; copying
  the fixture to `tmp_path` keeps the gate's behaviour universal instead.
- **File-based FT-40 versus importing the project in conformance.** The manifest now records
  `planned`, so the ship-gate check stays file-surface like every other check, and importing
  stays the view's own behaviour.
- **Merging run groups by node-id signature.** Groups key on `graph_fingerprint` first and
  fall back to name-overlap (≥ half the ids shared) only to attach history to a declared
  pipeline whose code moved; two fingerprints of one signature stay two rows in the history.

## 3. Build

Shipped, in order: `NotBuilt` in [`nodes.py`](../../src/simple_agents/nodes/base.py#L17)
`NotBuilt` with constructor wiring in all three node kinds and execute-time refusals;
`touches=` on [`tools.py` `Tool`](../../src/simple_agents/tools.py#L688) and on
`Deterministic`; manifest `0.31` → `0.32` (node entries gain `planned` and `touches`, tool
entries gain `touches`); [`registry.py`](../../src/simple_agents/registry.py#L1)
`pipeline_factory`; [`comments.py`](../../src/simple_agents/records/comments.py#L153) `read_comments`;
FT-39 and FT-40 in [`checks.py`](../../src/simple_agents/conformance/checks.py#L1724) `ft_39`
with taxonomy entries, and `comments_block_gates` on
[`brief.py` `Brief`](../../src/simple_agents/conformance/brief.py#L108); the view package
([`assemble.py`](../../src/simple_agents/view/assemble.py#L666) `assemble`,
[`discovery.py`](../../src/simple_agents/view/discovery.py#L49) `load_project`,
[`runs_overlay.py`](../../src/simple_agents/view/runs_overlay.py#L724) `read_runs`,
`render.py`, `template.html`); the `view` subcommand, with `check` rewriting the page at
every gate. Five fixture projects under `tests/fixtures/view_projects/`, one per shape.
3,171 tests.

What the build found that the design did not know:

- **Findings compute server-side.** The first prototype computed its sentences in page
  JavaScript; moving them into `assemble` made every sentence a pytest assertion, which is
  how the wrong money-cap claim and two wrong plural forms were caught.
- **`Budget.to_record` keys are `max_*`** where `Spend`'s are bare, and the page read the
  wrong ones: a $0.10 cap reported as "no cost cap". A screenshot found it; the suite had not.
- **A paid call has no direction.** `touches` direction follows the side-effect class, and
  `SPENDS_MONEY` deliberately maps to neither reader nor writer: a paid search reads the web,
  a paid order writes it, and the class cannot say which.
- **The record-only shape is the migration path.** `dogfood-5-frozen` renders with an empty
  picture and 2,393 runs; the page now says registering each pipeline is what lights it,
  which is the instruction at the point a pre-convention project meets the tool.
- **The gate writing `view.html` pollutes committed fixture projects** when tests run `check`
  in place; the two tests that did now copy to `tmp_path` first.
- **`procedure.md`'s word budget moved 2550 → 2600**, on the precedent of P3-28, P3-34 and
  P3-36: the view, the skeleton at `shape` and the comment record are new content, and the
  comment on `WORD_BUDGET` records it.

**The second act, 2026-08-27, on Thilina's morning instruction**: *"Implement the live
version. the actual tool that we want. not a half assed version."* Shipped the same day:
`comments.toml` grew into a thread record (format `1`: `by`, `kind`, snapshot fields,
replies, `withdrawn`, atomic writers); `simple-agents view --serve` on stdlib
`http.server` with `/data`, `/version` and three POST routes; the page became a live
application that re-renders as the project changes under it, with everything selectable
(steps, edges, pipelines, resources, questions, decisions) bound to one composer;
questions answerable and answers amendable in place, shown as "with the coding agent"
until recorded; `simple-agents comments` as the agent's inbox; and the whole brief made
legible on the page (every answer, every decision, each with amend and comment). 3,186
tests.

**The third act, later the same morning, from Thilina's feedback on the live page**: run
watching (a not-yet-closed manifest whose trajectory still moves is the running run; the
page banners it, marks steps done as their records land, and draws the moving step), the
stage-grouped questions list, and the polish pass his list named: one rail panel with the
composer attached to the selection, one button language, sentence case throughout, the page
speaking to the builder as "you", collapsible groups on the step card and in the sections,
clipped quotes that end on a word, and the findings' show buttons fixed (they pointed at a
section id that no longer existed). His first real thread through the served page ("Is this
fixed now?" on the fixture's judge) was answered in the thread, as the loop intends.

## 4. Verification

- **Live Gemini**: `tests/fixtures/view_projects/one-pipeline` holds a real
  `gemini-3.1-flash-lite` run made during the build ($0.000031 under a declared
  `PriceBasis`); the overlay tests read its manifest, and the first attempt surfaced the
  honest-`unknown` cost path (no cache-write rate declared prices the run at `null`).
- **A real deterministic run** of the `many-pipelines` fixture's `ingest`, after which the
  fixture gained a `NotBuilt` step, so the change ledger and `code_moved_since` are tested
  against a real manifest forever.
- **Run watching, end to end in a real browser**: a simulated mid-flight run (manifest
  without `ended_at`, trajectory with one finished step) showed the banner and the moving
  step; appending the next step's record moved the page to "2 steps done" within one poll,
  asserted from the page's own text.
- **The live loop, end to end in a real browser**: Playwright against a served fixture
  copy did what a builder does, and each step was asserted in the record: a comment on the
  planned step landed with its snapshot (`about`, `stage`, `shape`); an answer typed on
  `what_it_does` landed as `kind=answer` carrying the question's own ask text; the coding
  agent's `append_reply` appeared on the open page within one poll; an edit to `agent.py`
  under the open page appeared the same way; an amendment on `purpose` landed as
  `kind=amendment`. Eight HTTP-level tests drive the same server in the suite.
- **Headless Chrome screenshots** of all five shapes plus `dogfood-5-frozen`, light and dark,
  with Playwright driving selections. Screenshots caught what the suite could not: the
  system map ballooning on a one-pipeline project, the wrong budget keys, `Union` leaking as
  a field type, sub-cent spend rendering as `$0`, and the frozen project's page opening with
  "nothing is drawn yet" over 2,393 runs. Each was fixed and re-shot.
- vLLM was not started; Gemini was the live backend, and Mistral is out of credits
  (`handoff.md`).

## 5. Doc consequences

`docs/view.md` is new and `docs/index.md` gained its row (eighteen documents).
`docs/procedure.md`: the layout gained `comments.toml` and `view.html`, "what to keep doing"
gained showing the view, and `shape` gained the skeleton. `docs/tools.md` gained the
`touches=` contract row; `docs/run-envelope.md` §2.6 gained `planned` and `touches` and its
current version line moved to `0.32`; `docs/failure-taxonomy.md` gained FT-39 and FT-40 and
its counts moved to 40; `docs/conformance.md` counts moved to twenty-three and its §4 sample
report was regenerated from the fixture. `CHANGELOG.md` records all of it under "The common
language". `README.md` gained the `docs/view.md` row and its counts moved. One rule moved:
`prose_check.py`'s `ADDRESSES_THE_READER` gained `assemble.py`, because the page addresses the
builder the way the README addresses its reader. **Approved by Thilina 2026-08-27**, at
`P3-40`, which moved the exemption to `findings.py` along with the sentences it covers.

## 6. Left open

- **The product level is folded into the others rather than drawn as its own panel.** The
  design names four levels; the page shows where a person is asked and where money leaves as
  badges and findings on the system and step levels, and no fixture yet carries enough
  product surface (`used_through`, a kept artifact) to make a dedicated panel more than
  furniture. When a project with a real product surface meets the view, this is the first
  thing to revisit. Destination: nothing, until one does.
- ~~The comment path back is still one-way~~ **closed 2026-08-27**: the served page
  writes threads, answers and amendments, and the coding agent replies and addresses them
  in the same file. What remains one-way is the brief itself, by design: the page relays
  and the coding agent records ([`design/view.md`](../design/view.md#L1) decision 5).
  Destination: nothing.
- **Ghost pipelines wait on `P3-29`**: a decision that produced nothing yet in code cannot be
  drawn until `produces` lands; the name-match join is the interim and every card says so.
  Destination: [`plan.md` §1](../plan.md#L17), the `P3-29` row.
- **Two fingerprints of one signature render as two history rows** for a record-only
  project; merging shape-versions under one name with a version count would read better.
  Cheap, cosmetic, undecided. Destination: nothing.
- ~~The live view~~ **built later the same morning** (the third act above): a run in
  progress banners its pipeline and moves through the graph as records land.
  Destination: nothing.
- **The `measure` overlay is thin**: results presence is noted and `judged_steps` coverage
  is not yet drawn, and dogfood #6 is where it would be exercised. Destination: nothing.
