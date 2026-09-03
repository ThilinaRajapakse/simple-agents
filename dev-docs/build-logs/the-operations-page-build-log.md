# Build log — The operations page

`plan.md` §1 `P3-57`. Started and built 2026-08-29, fourth of the six pages designed at the
2026-08-29 sitting, after [`P3-56`](the-product-on-the-page-build-log.md#L1) whose `shipped`
fixture it builds on. Its `items/` record held the design and is folded into §2 here.

## 1. Before any design

The item's own reading of 2026-08-28 held up: six records of a live project exist on disk and
the view read none. What was verified before building:

- **A suspension is a file beside the manifest.**
  [`pipeline.py` `suspensions`](../../src/simple_agents/pipeline/core.py#L950) globs for it, and
  [`SuspensionState`](../../src/simple_agents/records/suspension.py#L52) carries `waiting_for`,
  `options` and `resume_not_before`, which is what separates waiting on a person from waiting
  on a clock.
- **`Suspend` is raised from a `Deterministic` body**, not only from a channel
  ([`errors.py`](../../src/simple_agents/errors.py#L115)), so a run that waits can be made
  without a model.
- **`liveness` is derived from the clock**, not recorded
  ([`envelope.py`](../../src/simple_agents/envelope.py#L332)): a run reads `running` until its
  own `max_wall_clock_ms` plus an hour's grace has passed, then `abandoned`.
- **A conversation reaches the manifest under `id`**, with `turn` and `carried_in`
  ([`manifest.py`](../../src/simple_agents/records/manifest.py#L83)), so the page can read them from
  the runs and needs no path to the store.
- **A throttle that is waited out records nothing.**
  [`_call_waiting_out_a_throttle`](../../src/simple_agents/context.py#L1033) sleeps and calls the tool again;
  only a call whose attempts are spent reaches the record, as an error whose `type` is
  `Throttled` ([`context.py`](../../src/simple_agents/context.py#L1033)).
- **Nothing dates a confirmation.** `understanding_confirmed_at`, `design_confirmed_at` and
  `shape_confirmed` record a stage or a fingerprint, never a day, so a confirmation cannot be
  placed on a time axis.
- **`runs()` leaves rollouts out** and `nested=True` includes them
  ([`envelope.py`](../../src/simple_agents/envelope.py#L472)), which is how the split by role
  is counted without walking directories.

## 2. Design

**The design is the item's**, put as a wireframe at the 2026-08-29 sitting and ruled *"Looks
okay, but I'll need to see the final thing before I know for sure."* Four regions and a
seventh tab. **Decided at the sitting: its own tab, and the 30-day default with a picker.**

**Built as drawn, with four departures.**

1. **The throttle mark is a call whose attempts were spent, not every throttle.** The
   wireframe said "3 throttles marked". A throttle the library waits out and then succeeds is
   not recorded anywhere: the retry loop swallows it and the successful call is what the
   trajectory holds. What the page can mark is a call that ran out of attempts, which records
   an error naming the type. The region says which it counts.
2. **The marks on the history are behaviour changes alone.** The wireframe drew "shape agreed
   14 Aug" beside "behaviour changed 8 Aug". A confirmation records the stage it was agreed at
   and not a date (§1), so it cannot be placed on a time axis without inventing one. The
   Changes region says so in a sentence rather than leaving the absence unexplained.
3. **A behaviour change is read within one graph.** Two pipelines have two behaviour
   fingerprints, so a project running both would report a change on every day it ran them in
   either order. The change is a move within one graph's own series.
4. **A conversation is drawn from the runs, not from the store.** `ConversationStore` has no
   "list every conversation", and each run's manifest already records which one it is a turn
   of. Read from the runs, a conversation whose file has moved still lists, and `carried_in`
   says whether any node has read it, which is a state worth showing: a project can declare a
   `conversation_id` and never take part in the conversation.

**The run record moves here and is split by what each run was for**, which the item owed from
`P3-51`'s sitting. It stays on the `ship` page for a project with no live run, because there
is then no operate page to move it to.

## 3. Build

What shipped:

- [`operating.py`](../../src/simple_agents/view/operating.py#L268), new: `read_operating`, the
  six records joined, and `None` for a project with no live run.
- [`template.html`](../../src/simple_agents/view/template.html#L1): `operate` appended to the
  stage set when the project has live runs, and `nowRegion`, `historyRegion`, `stuckRegion`,
  `shelvedRegion`, `conversationsRegion`, `changesRegion` and `ranRegion`.
- The fixture's background pipeline and the runs that exercise it,
  [`build_view_fixtures.py` `build_operating`](../../scripts/build_view_fixtures.py#L253).

**The fixture's states are real runs, not edited records.** `shipped` gains `reconcile`, a
nightly pass over the ledger that calls no model, which is the background half a shipped
project has and the shape `docs/product.md` §4.2 describes for a shelved question. Seven runs
of it: one raising `Suspend` for a person, one raising `Suspend` until a date, one whose
channel returns `Shelved`, one whose tool raises `Throttled` until its attempts are spent, two
turns of one conversation, and one **killed by `os._exit` in a process of its own**, which is
the only way to leave the open manifest a run reads as abandoned from. None calls a model and
none spends anything.

Found while building:

- **The channel lookup matched across pipelines.** A surface naming `consult` found
  `claims/finance` and `reconcile/settle`, because two pipelines each hold a tool of that
  name. It is scoped to the pipeline the surface names.
- **`fingerprint` is a library word.** The Changes region printed the hash; it says what
  changed in the builder's terms instead.
- **The one-day chart wasted the whole width**, drawing a single bar centred in 600 pixels
  with its spend dot hidden under it. A bar keeps a readable width, the spend is labelled
  rather than drawn as a line of one point, and the throttle mark sits above the bar.
- **A run id has no break opportunity**, so it overflowed its column until the row was told to
  break anywhere.
- **FT-41 now fails on the fixture**, correctly: two runs stopped to ask and nothing has
  continued them. The ship page's board reports it, which is the page doing its job.

4,045 tests, from 4,029. No format moves.

## 4. Verification

**What the page looks like, region by region, with the screenshots.** Read in headless Chrome
at 1500px on paper and on midnight. Screenshots under `scratchpad/shots/`: `p57-a.png` (paper,
the whole page), `p57-b.png` (midnight), `p57-c.png` (the stuck rows).

- **The tab.** `Operate` sits after `Ship` in the strip with a `◆` in the accent, and its
  title says live runs are on record. It is absent on every fixture without one.
- **Now.** Five tiles: `Running 1`, `Waiting on a person 2`, `Abandoned 0`, `Shelved questions
  1`, `Spent today 0.000634 USD`. The three that need somebody are outlined in the attention
  colour when they are not zero, so a calm morning is a calm row.
- **History.** One stacked bar for the day, finished over failed over stopped, the throttle
  triangle above it, a dashed line through it where the behaviour changed, and the day's spend
  as a dot with its figure beside it. The window picker reads `Last 7 days · 30 days · 90
  days` with 30 pressed. The legend names all four marks and the sentence under it says what
  each is.
- **Stuck.** Two rows: `Waiting on a person for 5 min · the finance desk to confirm the August
  write-off · offered write it off, chase it`, and `Waiting on a clock for 5 min · the month to
  close · not before 2026-09-01T09:00`.
- **Shelved.** `po-80115-unit · "Is the 12p line on PO-80115 per unit or for the whole order?"
  · Asked 5 min ago by run_… · the nightly run has nobody waiting on it`.
- **Conversations** and **Changes**, side by side: `finance-august-close · 2 runs · last 5 min
  ago`, with the line saying no node has read or written it; and `2026-08-29 · The behaviour
  changed`, with the sentence about confirmations carrying a stage rather than a date.
- **What has run.** `live 10 · Real traffic`, `development 2 · Made while building`,
  `evaluation 60 · Rollouts of an evaluation`, each with its spend, and the line saying the
  figures above are the live runs alone.

**Left read by eye and not screenshotted:** the `abandoned` tile at a non-zero value. The
fixture's killed run reads `running` for the hour after it is built, because `liveness` is the
clock's answer and not a recorded one; the same fixture read later reads `abandoned`. The
count and its wording were read against a scratch copy whose killed run was back-dated, and
the test asserts the invariant rather than the value.

**Live**: no backend call was made and none was needed. Every fixture run this item added is a
real run the library wrote, driven by deterministic code; the two replayed claims runs and the
evaluation behind them are `P3-58`'s and `P3-60`'s live recordings, untouched.

**Offline**: `build_view_fixtures.py` replays all three recorded projects and matches.

**Full suite** 4,045 tests, `prose_check`, `shape_check`, `check_citations`, `check_docs`:
clean.

## 5. Doc consequences

[`docs/view.md`](../../docs/view.md#L520) gains §6.8, the operate page region by region, says
in its opening that a seventh page appears once there are live runs, and files the run record
there. `CHANGELOG.md` records the page, the six records it reads, the run record's move and
what a throttle does not leave behind.

## 5.1 Read as a builder, 2026-08-29

Read again at 1440px, still and served, after all six pages were built. *Open* on the
abandoned run fetched the run and changed nothing on the page, since the walk lives on the
build page; it switches there now and lands on the walk. The history's caption and the
Changes region were clause chains and are plain sentences. Fixed the same day, recorded in
`CHANGELOG.md`.

## 6. Left open

- **A throttle the library waited out is invisible.** Nothing records it, so a project whose
  source throttles it constantly and recovers every time looks unthrottled. Recording one
  would mean a trajectory record for something that did not fail, which is a question about
  what a run's record is for. Destination: [`plan.md` §2.2](../plan.md#L1).
- **Resuming a run is not on the page.** `Pipeline.suspensions` and
  `Pipeline.answer_shelved` are the project's own worker's, and the supervisor that would drive
  them is [`plan.md` §2.2](../plan.md#L1)'s. The page says what is waiting and stops there.
  Destination: that entry.
