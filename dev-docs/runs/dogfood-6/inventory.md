# Dogfood #6 — inventory

Everything actionable from [`findings.md`](findings.md#L1), in one place, so `plan.md` and
`handoff.md` can point here rather than carrying it.

**Nothing here is agreed work.** `plan.md` §1's rule stands: everything agreed to be built is
scheduled there and nowhere else. This is the **input** to `plan.md` §1 `P3-71`.

**Sections are by where an item goes next.** §1 goes nowhere, §2 is already applied, §3 goes to
`plan.md`, §4 goes to the next run's `setup.md`.

**The inventory says what to do. `findings.md` says why we believe it.** Every row names its
finding rather than repeating it. A citation between the two resolves both ways: this side is
the source of truth and `check_docs.py --fix` writes the `**Acted on:**` lines in `findings.md`.

**Drafted 2026-09-02, and the sitting was taken the same day.** Every disposition is Thilina's. The nineteen went to six items, [`P3-72`](../../plan.md#L1) to `P3-77`, in the order the sitting set: the writer, the index, the runtime fixes, the pipeline identity, the procedure, and the schedule, which also took `plan.md` §2.2's scheduler entry. **19 candidates, 0 open.**

---

## 1. What we learned

Belief updates. No work attached; they change how the next thing is read.

| # | What | From |
|---|---|---|
| **DF6-L1** | **The released package held.** Installed from PyPI, upgraded mid-build, no format refused a file the earlier version wrote. Every defect this run met is inside the library | §2 |
| **DF6-L2** | **A hands-on builder takes a project to `ship` in twelve hours.** Dogfood #5 took seventy-two. The difference is eight rules the builder gave the coding agent, retrieval decisions put to him one at a time, and a paid key. What that buys is speed; what it hides is what a cold coding agent would have done alone | §2, `DF6-D17` |
| **DF6-L3** | **The research stage adopts library facilities and the build does not reach them.** Five adopted, one used, and the two the earlier runs missed (`MemoryStore`, fetching outside the tool layer) missed again. An adopted row is a claim about the build and nothing reads it against the code | `DF6-D12` |
| **DF6-L4** | **The checks do not know which pipeline a run is.** A project with six pipelines and a scheduler makes three checks fire daily and one read the wrong role, and the coding agent's answer was a paid run before every gate | `DF6-D6`, `DF6-D7`, `DF6-D4` |
| **DF6-L5** | **A hand-written timestamp is composed, wherever it is written.** The protocol retired the log's stamps for the brief's; the brief's are the local clock with a UTC suffix. The view's stamps are right because a program wrote them | `DF6-D9` |
| **DF6-L6** | **The slice mechanism's `end=` form had never run.** A documented call raises on its own example, one item after it shipped | `DF6-D1` |
| **DF6-L7** | **The product after `ship` recurred with a native app**, and the road after the last gate is now where two products have been built | `DF6-D16` |
| **DF6-L8** | **The record undercounts what the builder paid**, by a basis the project declared wrong and by a scripted client counted as spend | `DF6-D11` |

## 2. What was corrected

A statement the run disproved, and where it was written. **These are applied on sight, never
queued**, so this is a log rather than a backlog.

| # | The statement | Where it was written | Corrected |
|---|---|---|---|
| **DF6-X1** | "What replaced it is `recorded_at` on every answered brief entry and every decision, which is in a formatted file a gate reads rather than in prose" | [`dogfood-protocol.md` §2](../dogfood-protocol.md#L32) | 2026-09-02: a sentence added beside it saying the stamp is still written by hand and dogfood #6 wrote it in local time with a `Z` (`DF6-D9`) |
| **DF6-X2** | `pipeline.slice(end="select")` as a worked example | `docs/pipeline.md` §1.14, `docs/evaluation.md` §5.6 | Not applied: the example is right once the mechanism is, and the mechanism is `DF6-I01`. Logged here so the docs are not read as true meanwhile |

## 3. Candidates

One flat table, in the order to take them. **The id never changes and is never reused.**

| # | What | Evidence | Kind | Size | Blocked by | Status |
|---|---|---|---|---|---|---|
| **DF6-I01** | A slice's own end node routes to a cut successor and every run of `slice(end=)` or a `nodes=` set ending short of the terminal raises `LeftTheSlice`; the docs' example cannot run. Reproduced on three `Deterministic` nodes | `DF6-D1` | fix | cheap | — | scheduled P3-74 |
| **DF6-I02** | What an evaluation runs against when the pipeline reads back what it writes: the documented rule sends writes under `ctx.workspace`, which hides the read-back path; the project ended at a database copy per example that the docs do not describe, and the copy's path moved the example set's hash | `DF6-D2` | decide | sitting | — | scheduled P3-74 |
| **DF6-I03** | A node reached after a model node cannot read the run's inputs; `keep=` exists on fan-outs only. The project keeps a module dict keyed by `run_id`. `NodeContext` carries the run's inputs, or a pipeline-level `keep=` | `DF6-D3` | add | cheap | — | scheduled P3-74 |
| **DF6-I07** | Neither the manifest nor the results file records which registered pipeline made it, so nothing can read within one pipeline; the third run to meet this absence | `DF6-D7`, `DF6-D4` | add | item | — | scheduled P3-75 |
| **DF6-I04** | An evaluation over a pipeline the project registers nowhere passes FT-01; the primary was a one-node retrieval pipeline until the builder said otherwise. A check that the evaluated graph is a registered pipeline or a slice of one | `DF6-D4` | add | cheap | — | scheduled P3-75 |
| **DF6-I05** | FT-42 reads `role="agent"` and a `dependency` decision about the corpus names nodes and constants of a `role="corpus"` pipeline; ten of eleven reported names were recorded and the one real hit was buried | `DF6-D6` | decide | cheap | — | scheduled P3-75 |
| **DF6-I06** | FT-25, FT-37 and FT-38 read the newest agent run of any pipeline, and a project with a daily `freshen` makes all three fire on most mornings; the workaround is a paid run before every gate | `DF6-D7` | change | item | — | scheduled P3-75 |
| **DF6-I08** | The view offers a one-click on a constant no current run of its pipeline carries, and eight one-clicks wrote eight near-identical decisions | `DF6-D8` | fix | cheap | — | scheduled P3-75 |
| **DF6-I09** | `recorded_at` is written by the coding agent off its own reading of the clock and came out as local time with a `Z`; nothing writes a brief entry for it, and nothing reads a stamp against the view's or a run's | `DF6-D9` | decide | sitting | — | built `build-logs/the-brief-writer-build-log.md` |
| **DF6-I10** | `QUOTA_PHRASES` holds one Mistral phrase; Gemini's depleted-prepaid message was retried six times on every item of a 150-item fan-out, three times over, and the advice names `PacedClient` on a backend that publishes no allowance | `DF6-D10` | fix | cheap | — | scheduled P3-74 |
| **DF6-I11** | A `FakeModelClient` run is a `role="agent"` run with the model `test/model`, counted by `report` as spend and as produced-nothing work beside the real import; a scripted client is marked as one | `DF6-D11` | add | cheap | — | scheduled P3-75 |
| **DF6-I12** | An `adopted` research row naming a library facility is read against what the code imports, so five adopted and one reached is reported rather than found by grep | `DF6-D12` | add | item | — | scheduled P3-76 |
| **DF6-I13** | The coding agent built chunked checkpointing for a killed process and recorded that the library has nothing for it, with `Pipeline.rerun` documented; the resumability guidance names `rerun` where a builder asks for it | `DF6-D13` | change | cheap | — | scheduled P3-76 |
| **DF6-I14** | `DocumentIndex` has no incremental add, so the project holds its own vector store and uses the library's index for the lexical half only, rebuilt per query | `DF6-D14` | add | item | — | built `build-logs/an-index-that-grows-build-log.md` |
| **DF6-I15** | A failure inside a resumed run leaves no suspension to claim again; the claim is put back or the failure re-suspends | `DF6-D15` | fix | cheap | — | scheduled P3-74 |
| **DF6-I16** | The product after `ship` for the second project running: four design rounds, some twenty fix rounds, fourteen defects from a test suite written after the fact. The no-seventh-stage decision is re-decided on this evidence | `DF6-D16` | decide | sitting | — | scheduled P3-76 |
| **DF6-I17** | A decision kind marked `not_applicable` at brainstorm is never re-asked, and the catalogue went into the code with no `dependency` decision until the builder asked where it came from | `DF6-D17` | add | cheap | — | scheduled P3-76 |
| **DF6-I18** | A `prompt_rule` decision put to the builder carries the recorded prompt text rather than a summary of it; the builder had to ask for the text and found eighteen caps | `DF6-D17` | change | cheap | — | scheduled P3-76 |
| **DF6-I19** | `nearest_cross_split` on examples whose inputs are identifiers returns every pair at 1.0 with no word about why; it says so, or reads what it can compare | `DF6-D5` | fix | cheap | — | scheduled P3-74 |

### DF6-I02 — What an evaluation runs against when the pipeline reads back what it writes

The documented rule covers a pipeline whose last step writes into the product's artifact: the
write goes under the rollout's workspace and nothing reads it. This pipeline's never-rule is
"nothing already queued", so `exclude_first` reads the queue `store_queue` wrote, and an
evaluation that hid the write would measure a pipeline the product does not run. Three shapes
are on the table: a per-rollout store the pipeline is handed, which is what a copy per example
is by hand; a documented recipe for the copy, which is what the project built and the library
could carry as a helper; or a declaration on the node that it reads back a store, so the runner
refuses shared rollouts the way it refuses an irreversible tool. What has to be decided first is
whether the library owns any of the project's store, since every answer above touches it.

### DF6-I09 — Who writes `recorded_at`

The field is required and the CLI has no command that writes it. Three options. A command that
records an answer or a decision and stamps it, which makes the brief partly machine-written and
is the shape the view's comments already have. A check that a stamp is not ahead of the comment
or run it must precede, which catches the two-hour error here and nothing subtler. Or accept
that the stamp is the coding agent's word and say so in the protocol, which `DF6-X1` has done.

### DF6-I16 — The product after `ship`, twice

`DF5-I12` decided there is no seventh stage and that the road after the last gate is governed
by checks that read change. This run's road held four design rounds put to the builder as a
document, twenty rounds of fixes from the phone, and a defect that killed every run the app
started for a day. The checks that read change saw none of it because none of it moved the
pipeline. What is on the table is a product-design artifact the `ship` gate reads, which
`design.md`'s "The app" section is by accident, or a re-statement that the product is the
project's and the library stops at the pipeline.

## 4. What the next run must measure

| # | Question | Why it is open |
|---|---|---|
| **DF6-Q1** | **What does a cold coding agent do without a hands-on builder against the released package?** | This run's speed and its recoveries are the builder's; the library's own steering under a cold start is unmeasured since the release. `DF5-Q1`'s second cold run is still owed |
| **DF6-Q2** | **Does a coding agent find `rerun`, the memory store and the fetch tools when the task needs them?** | Five adopted at research and one reached, for the third run running; whether `DF6-I12` and `DF6-I13` change that is measurable only by a run |
| **DF6-Q3** | **Does the product reach an end user who is not the builder?** | `purpose` says other people will use it; the product is single-user by decision. Every consultation and every judgement so far is the builder's |
