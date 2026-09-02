# Dogfood #6 — findings

`lost-the-plot`, a TV Time replacement with a native app, built by Thilina against the public
package on 2026-09-01 and 2026-09-02. [`setup.md`](setup.md#L1) beside this file says how it
differs from a protocol run and §4 there is the list of questions this record answers first.
Findings numbered `DF6-Dn` are this run's; `DF5-` prefixed ones are dogfood #5's and are cited,
not restated.

**The run ran 2026-09-01 12:23Z to 2026-09-02 10:33Z and this record was written 2026-09-02**,
against a frozen copy at `/home/thilina/Projects/lost-the-plot-frozen`, taken from commit
`1d92f0b` with two uncommitted files copied as they stood. Nothing in this document was written
into the project.

**Project:** `/home/thilina/Projects/lost-the-plot`. Not a fresh cold start in the protocol's
sense: the builder steered, and the coding agent carried eight rules of his between sessions in
its memory file. What that changes is said in §1.

Final totals across **585 run directories** (498 agent runs including 175 evaluation rollouts,
87 corpus runs): **7,977 model calls, 735 tool calls, at least $14.81 recorded against $24.45
billed**, 5,897 calls in 101 runs unpriced. `simple-agents check` on 2026-09-02: **2 failed, 23
passed, 1 not applicable** at tier `evaluated`, stage `ship`.

| | dogfood #5 | dogfood #6 |
|---|---|---|
| Elapsed, brainstorm to `ship` | ~72h of a ~102h run | **~12h** (12:23Z on 09-01 to ~00:40Z on 09-02), and ~22h to the last commit |
| Library | wheel from `9b8e96c` | **PyPI `0.1.1`, then `0.1.2`** |
| Runs in the envelope | 2,669 | 585, 87 of them under `role="corpus"` |
| Model calls | 52,318 | 7,977, of which 1,846 to `FakeModelClient` |
| Recorded cost | $7.65 plus 36.8 GPU-hours | **at least $14.81; the provider billed $24.45** (`DF6-D11`) |
| Pipelines, nodes | 7, 28 | **6, 26** (import, discover, recommend, rank, freshen, fill), 2 `AgentNode` |
| Tier, stage | `evaluated`, `ship` | `evaluated`, `ship` |
| `simple-agents check` | 19 of 19 at the freeze | 23 of 25, FT-37 and FT-42 failing, one of them a library defect (`DF6-D6`) |
| Brief entries, decisions | 42, 31 | 39 entries, **27 decisions**, 8 of them one-click constants (`DF6-D8`) |
| Evaluations | 15 identities | 21 results files, 8 evaluation directories, 13 variant directories |
| Build log | 396KB, not asked for | 88KB, 32 dated sections, kept live from `build`, not asked for |
| Commits | 116 | 12, the first at `ship` |
| Product | a website, a JSON API, a Flutter app | a FastAPI service on the builder's machine, a scheduler thread, and a Flutter app installed on his Pixel over adb, with a local store, an outbox and cursor sync |
| Primary figure | a recommender that recommended nothing (`DF5-D5`) | 23.8% [9.5, 42.9], 5 of 21 held-out shows in the final fifteen; the builder's own pairwise number 20 of 29 |

---

## 1. Method, and what did not survive verification

Every figure below is read from the frozen copy's own artifacts and names its file. Where a
library defect is claimed it is checked in the source at `main` on 2026-09-02, which is `0.1.2`
plus uncommitted view edits, and the largest one is reproduced against the library on its own
(`DF6-D1`).

**What was read.** `BUILD-LOG.md` whole, 1,342 lines and 32 dated sections; `brief.toml` whole,
2,117 lines; `idea.md`, `research.md`, `design.md`, `HANDOFF.md`, `comments.toml`; `agent.py`
and the evaluation, API and channel modules; the coding agent's memory file for the project,
ten rules under `~/.claude/projects/-home-thilina-Projects-lost-the-plot/memory/`; a census over
all 585 manifests for role, model, outcome, cost basis and unpriced calls; `simple-agents check`
and `simple-agents report runs/` run once each on the frozen copy; and the library source
wherever a mechanism was claimed.

**What this run is not.** The protocol's asymmetry was not applied. The builder corrected the
coding agent's retrieval design six times in one stage (`BUILD-LOG.md:350-357`), told it to
print every prompt whole (`:467`, `:483-490`), to build nodes rather than hand scripts (`:566`),
and what the primary figure is about (`:541`). So the third protocol category, what the builder
wanted and was never asked for, is here mostly what he said unprompted; §3.5 reads it that way.

**Two readings that did not survive.**

1. **"The project runs against the working tree."** `uv pip show` from the project directory
   reported the editable install in this repository's own `.venv`, because the shell carried
   `VIRTUAL_ENV` for it. The project's own `.venv/lib/python3.13/site-packages/` holds
   `simple_llm_agents-0.1.2.dist-info` from the registry, and every traceback in
   `evals/overnight-20260902.log` runs through it. The project ran the public wheel.
2. **"FT-42's misses are a change of role reading."** The first reading was that `DF5-I13`'s
   join over every run had been narrowed by accident. [`produced.py`](../../../src/simple_agents/conformance/produced.py#L70) `produced_across`
   narrows it on purpose and its docstring says why, and
   `docs/conformance.md` §2.2 says the same. The finding is a design tension and not a
   regression, and `DF6-D6` is written that way.

---

## 2. What the run met

**The ship criterion, [`plan.md`](../../plan.md#L7)**: v0.1 ends "when a dogfood run produces no
library defect worth building." Not met. §3 carries nineteen findings, and the first of them
means a documented call cannot run.

**The tier.** `evaluated`, all six stages reached, the primary figure at
`evals/results/recommend-held-out-v5-ship.json` named by the brief's `results` key. Two checks
fail on the frozen copy: FT-37, rightly, because `exclude_first` changed after v5 was measured
(`BUILD-LOG.md:1312`); and FT-42, ten of whose eleven names are recorded under a role it does
not read (`DF6-D6`).

**The release held.** The package installed from PyPI, was upgraded from `0.1.1` to `0.1.2`
mid-build with every pipeline still importing (`BUILD-LOG.md:343-345`), and no on-disk format
refused a file the earlier version wrote. Nothing in the run met a packaging defect.

**The questions [`setup.md` §4](setup.md#L44) named, in its order.**

| Question | Answer, and where |
|---|---|
| The released package, cold | Installed, upgraded and ran. What broke was inside the library and not around it |
| Six pipelines against the checks | Three checks key off the newest run of any pipeline and one reads a role that decisions legitimately name. The coding agent's workaround was a paid run before every gate. `DF6-D6`, `DF6-D7` |
| An evaluation over a stateful pipeline | The evaluation contaminated itself, the documented rule did not fit, and the slice that would have avoided the write cannot run. `DF6-D1`, `DF6-D2`, `DF6-D3` |
| The product after `ship` | Recurred. The app was designed at `ship` in four rounds and fixed over some twenty more from the phone. `DF6-D16` |
| Adopted facilities reached | Five adopted at `research`, one reached. `DF6-D12` |
| What the builder said himself | Eight rules; three name something the library carries or could. §3.5, `DF6-D13`, `DF6-D17` |

---

## 3. Findings

Library findings first, grouped by what they are about, then the procedure. Each names its
evidence and what it cost this project.

### 3.1 What an evaluation runs on

### DF6-D1 — `Pipeline.slice(end=)` never produces output

**Acted on:** `DF6-I01`.

**Library.** The project's first end-to-end evaluation sliced `recommend` at `rank_and_reason`,
which is the documented way to keep an evaluation from writing into the product's store.
`evals/results/recommend-held-out-v1.json` records 23 of 23 rollouts as `left_the_slice` and the
accuracy figure with no denominator, each rollout's error reading "Node 'rank_and_reason' went
to 'store_queue', which is outside this slice of the pipeline, so the run ended there and
produced no output" (`BUILD-LOG.md:631`).

**Reproduced 2026-09-02** on a three-node linear pipeline of `Deterministic` nodes, against the
source at `main`: `p.slice(end="b")` and `p.slice(nodes=["a", "b"])` both raise `LeftTheSlice`
on the first run. The sliced node's `successors` is narrowed to `[]`, but the cut edge stays
declared in the sliced graph so a route can still select it, and
[`edges.py`](../../../src/simple_agents/pipeline/edges.py#L280) `note_the_boundary` marks any
chosen cut successor as leaving, the slice's own terminal included. `P3-53`'s tests exercised
`start=` and sets ending at the real terminal; a slice ending at a node with a successor has never
run. `docs/pipeline.md` §1.14 and `docs/evaluation.md` §5.6 both carry
`pipeline.slice(end="select")` as the example, and it raises.

**What it cost.** The evaluation was rebuilt to run the whole pipeline against a database copy,
which is what let the rollouts contaminate each other (`DF6-D2`), and `store_queue` now carries
the picks out with its receipt so a figure has a denominator (`agent.py:938-945`).

### DF6-D2 — The evaluation contaminated itself, and the rule for a pipeline that writes does not cover one that reads back

**Acted on:** `DF6-I02`.

**Library, and a document.** Twenty-three rollouts ran the whole `recommend` pipeline against
one shared database copy. Each rollout's `store_queue` wrote fifteen picks and every later
rollout's `exclude_first` blocked them: `already_queued` went 45 to 279 across the run, the last
rollout searched a corpus 234 shows smaller than the first, and the primary figure of 52.4%
was measured on an evaluation interfering with itself (`BUILD-LOG.md:686-699`). The
retrieval node's figure moved between two runs of the same code for the same reason, which had
first been explained as fp16 batching (`:711`).

`docs/product.md` §5 and `docs/evaluation.md` §6 carry the rule for a pipeline that writes: an
evaluation's write goes under `ctx.workspace`. This pipeline reads back what it writes, because
excluding what is already queued is production behaviour and the builder's never-rule, so a
write under the workspace would have hidden the exclusion path the evaluation exists to measure.
The project ended at one database copy per example, made by `scripts/evaluate.py:53-63`, ~51MB
each, and the docs say nothing about that shape. The copies' paths then sat in the examples'
inputs and moved the example set's hash, so `compare()` refused to pair v3 with v4 until the
paths were fixed per example (`:805-809`).

### DF6-D3 — A node after a model node cannot read the run's inputs

**Acted on:** `DF6-I03`.

**Library.** `store_queue` receives `rank_and_reason`'s output, a `Queue`, and has to know which
database its run is on. `NodeContext` carries `run_id`, `node_id`, `workspace`, `seed` and
`budget` and no inputs
([`context.py`](../../../src/simple_agents/context.py#L1364) `NodeContext`), and `keep=` exists
on a fan-out only. The project keeps a module-level dict from `run_id` to database path, written
by the first node and read by the last (`agent.py:948-959`), with a comment saying why: "keep=
only travels through a fan-out". Two evaluation rollouts at `concurrency=2` in one process is the
case a module default cannot serve, which is how the shared-copy contamination in `DF6-D2` got
its first fix.

### DF6-D4 — FT-01 passed on a pipeline the project registers nowhere, and the primary was a per-node figure until the builder said so

**Acted on:** `DF6-I07`, `DF6-I04`.

**Library.** The first evaluation measured retrieval alone: a one-node pipeline built inside
`plot/evaluation.py:192-194`, not registered under `@pipeline_factory`, whose node `retrieve`
appears in no pipeline of `agent.py`. FT-01 through FT-07 passed on it and the brief's
`improvement` entry recorded its recall as the project's number, until the builder said the
primary figure is about the final recommendation and retrieval recall is a per-node metric
(`BUILD-LOG.md:541-546`; the memory file's `primary-metric-is-end-to-end`). Nothing asks whether
the pipeline an evaluation ran is one the project registers, or a slice of one, and the results
file records a `graph_fingerprint` and no pipeline name (`DF6-D7`). `DF5-D5` is the same gap from
the other side: there the headline's pipeline recommended nothing; here it was a component.

### DF6-D5 — `nearest_cross_split` reports 1.0 for every pair when inputs are identifiers

**Acted on:** `DF6-I19`.

**Library.** [`examples.py`](../../../src/simple_agents/evaluation/examples.py#L607) `nearest_cross_split`
compares `Example.text`, every string in `inputs` joined. This project's
examples are a user id and integer show ids, so every text was the same word and every pair
scored 1.0 (`brief.toml:2032-2035`, `HANDOFF.md:315`). The builder answered `too_similar` from
similarities the project computed off show embeddings instead. The tool returned a full table
of identical ones and said nothing about why.

### 3.2 What the checks read on a project with six pipelines

### DF6-D6 — FT-42 reads `role="agent"` runs, and a decision about the corpus names another role's nodes

**Acted on:** `DF6-I05`.

**Library.** `simple-agents check` on the frozen copy fails FT-42 with eleven names "never
recorded by any run of this project". Ten of them are recorded: `summarise`,
`embed_and_store`, `fill_from_catalogue` and `embed_new` are nodes of the corpus and fill
pipelines, and `FETCH_CONCURRENCY`, `SUMMARISE_CONCURRENCY`, `RETRY_ATTEMPTS`,
`FIRST_BACKOFF_S`, `MAX_BACKOFF_S` and `RERANK_DEPTH` are constants those pipelines' modules
define; 87 manifests under `runs/corpus/` carry them. [`produced.py`](../../../src/simple_agents/conformance/produced.py#L70)
`produced_across` reads `runs(run_dir, nested=True, role="agent")` and its docstring says a
labelling pass or a judge is not the agent's work. The corpus pipeline declares
`role="corpus"` because `DF5-D4` found corpus passes being read as the agent's runs, and
`decisions.candidate_corpus`, a `dependency` the builder agreed to, names what that pipeline
built. The eleventh name, `show_state` under `decisions.deliberate_tick`, is a function and not
a node, which is the project's mistake and the one the check was for.

**What it cost.** The coding agent could not see why the check disagreed with the manifests it
had just read (`BUILD-LOG.md:1058-1062`), left it failing through the `ship` gate, and the real
hit sits in the same list as the ten false ones.

### DF6-D7 — Three checks key off the newest run of any pipeline, and nothing records which pipeline a run is

**Acted on:** `DF6-I07`, `DF6-I06`.

**Library.** FT-25, FT-37 and FT-38 read "the newest agent run":
[`artifacts.py`](../../../src/simple_agents/conformance/artifacts.py#L423) `_latest_run` filters
by role and liveness and by nothing else, and
[`checks.py`](../../../src/simple_agents/conformance/checks.py#L1605) `current_fingerprint`
reads its `behaviour_fingerprint`. On a project whose scheduler runs `freshen` daily, `rank`
after every corpus change and `recommend` on demand, the newest run is usually a pipeline the
results file did not measure and the brief's ten pipeline entries were not confirmed against,
so all three fire on most mornings (`BUILD-LOG.md:1053-1062`, `HANDOFF.md:198-201`). The
standing workaround is a paid `recommend` run made last before every gate (`:1066`, `:1292`,
$0.11 each). The manifest records `graph_fingerprint` and `behaviour_fingerprint` and no
registered pipeline name, and so does the results file's `config`, so the checks have nothing
to select the same pipeline by. `DF5-D5` and `DF5-D17` asked what joins a results file to the
pipeline that made it; this is the same absence one project later.

### DF6-D8 — The view offered a one-click on a constant the code no longer had, and eight one-clicks became eight decisions of boilerplate

**Acted on:** `DF6-I08`.

**Library.** [`constants.py`](../../../src/simple_agents/view/constants.py#L33) `_across_the_runs`
gathers every constant the newest 200 runs recorded, keeping each name's
newest value, with no mark for a name the newest run of its pipeline no longer carries. `PRIMARY`
had been removed from the code when the builder's rulings made the primary "in the final
fifteen"; a 2026-09-01 manifest still held it, the page offered "PRIMARY should be 10. Record it
as a constant decision", the builder clicked it (`comments.toml`, `c6`), and
`decisions.primary_k` (`brief.toml:1148-1163`) is a `changed` decision written to answer a
constant nothing had. The check's own trailer says "PRIMARY (last seen 2026-09-01)".

The other seven one-clicks (`c3` to `c10`) each produced a decision whose `considered` is one
sentence quoting the click and whose `because` opens with the same two lines
(`brief.toml:1030-1146`). Every one confirmed a value the code already had. The mechanism is
cheap for the builder, which is its point, and what it writes into the brief is seven near-copies.

### DF6-D9 — `recorded_at` is composed by hand, in local time, with a `Z`

**Acted on:** `DF6-I09`.

**Library.** `P3-47` made `recorded_at` required on every answered entry and every decision, and
[`dogfood-protocol.md` §2](../dogfood-protocol.md#L32) retired the build log's timestamps on the
ground that a stamp in a formatted file a gate reads beats one in prose. The CLI has no command
that writes an entry, `docs/conformance.md` §2.1 says the coding agent reads the clock and writes
the value, and this brief shows what that produces. `decisions.app` says `agreed_at =
"2026-09-02T02:25:00Z"` (`brief.toml:985`). Comment `c3`, stamped by the served view at
`2026-09-02T01:15:26Z` (`comments.toml:48`), already says "At the ship stage" (`:46`), and
`ship` opened after the app was agreed (`BUILD-LOG.md:891-893`). The stamp is the local clock,
two hours ahead of UTC, with a UTC suffix. About twenty of the brief's thirty-three distinct
stamps are round-minute values of the same kind; the sixteen at `01:27:31Z` were written by the
comment flow and are right. A gate reading `recorded_at` against a run's `started_at` would be
reading two clocks.

### 3.3 Money, and stopping

### DF6-D10 — A depleted prepaid balance is retried as a burst limit, and the advice names a wrapper this backend cannot use

**Acted on:** `DF6-I10`.

**Library.** At 06:48 UTC on 2026-09-02 every Gemini call began answering `429: Your prepayment
credits are depleted`. The `summarise` fan-out retried each of 150 items six times, waited 31
seconds per item, and raised at the end with "Pace the calls against the backend's published
allowance: PacedClient(client) waits once for every caller sharing it"
(`evals/overnight-20260902.log`, tail). The chain's two resumed attempts paid the same again.
`P3-50` built a `Suspend` for a 429 whose allowance will not reset inside a retry window, keyed on
[`_http.py`](../../../src/simple_agents/adapters/_http.py#L62) `QUOTA_PHRASES`, which holds one
phrase, Mistral's "monthly spending cap". Gemini's message is not in it, so the stop never fired.
And the advice is wrong for this backend: Gemini publishes no allowance on a response
(`gemini.py:170`), so `PacedClient` has nothing to pace. The coding agent's memory file records
the workaround as a rule of its own: "when a run reports the 429 above, stop retrying and tell the
builder the balance is the blocker" (`gemini-keys-limits`).

### DF6-D11 — The record prices $14.81 of a $24.45 day, and counts a scripted client's calls as spend

**Acted on:** `DF6-I11`.

**Library and task.** `simple-agents report runs/` on the frozen copy: "at least 14.8094 USD,
5,897 call(s) in 101 run(s) could not be priced", against $24.45 on the provider's dashboard for
the day (`BUILD-LOG.md:1285-1286`). The census over the manifests says where the unpriced calls
are. 2,903 corpus calls in 26 runs ran under a basis that declared no cache-write rate, and each
manifest's reason says what to declare ("Declare input_cache_write_per_mtok, at 0.0 where the
provider bills nothing for it"); the project did, in `plot/pricing.py`, after those runs. 452
corpus calls raised before a response, correctly unpriced. And 1,846 calls in 17 runs went to
`FakeModelClient`, recorded under `role="agent"` with the model `test/model`, which the report
counts in its totals and reads as 318 fan-out items that "produced nothing" over 1,905 model
calls (`report.txt`, node `resolve_show`), beside the real import. Nothing in `runs()`, the
report or the checks separates a scripted run from a paid one except the model name.

### 3.4 What the project rebuilt by hand, and what it never reached

### DF6-D12 — Research adopted five library facilities and the build reached one

**Acted on:** `DF6-I12`.

**Library.** `research.md`'s survey adopts `extract_to_schema` (`:45`), `http_fetch` and
`read_page` with `HostPolicy` and `UrlCache` (`:49`), `remember`, `recall` and `memory_search`
for the taste model (`:54`), the conversation that outlives a run for argue-back (`:55`), and
`consult` with `Shelved` (`:56`). Grepping the frozen code for each: only `consult` and `Shelved`
appear. Fetching is `urllib` inside `Deterministic` nodes (`plot/enterprise.py:26-28`,
`plot/catalogue.py:24-26`), outside policy, cassette and record, which is `DF5-D13` again, with
its own retry ladder whose three constants the builder then agreed as `constant` decisions
(`plot/enterprise.py:33-35`, `decisions.retry_attempts`, `first_backoff_s`, `max_backoff_s`).
The taste model is SQLite tables and the shelved questions are a table, so `MemoryStore` is
named and unbuilt for the third project running (`DF5-D11`). Argue-back is a new run with a note
as input (`design.md`, "The app" §4). FT-36 checks that every candidate carries an outcome and
nothing reads an `adopted` row that names a library facility against what the code imports.

### DF6-D13 — `Pipeline.rerun` is what a killed import needed, and the coding agent built chunked runs instead

**Acted on:** `DF6-I13`.

**Library, a document.** The builder required every long run to survive a reboot
(`BUILD-LOG.md:285`). The import was rebuilt as one pipeline run per chunk of twelve groups with
a checkpoint table (`:284-295`), and the memory file's rule `long-runs-must-be-resumable` says:
"`simple_agents` gives `Pipeline.resume` for a run that suspended, which is a different case; a
killed process needs the project's own checkpointing." `Pipeline.rerun`
([`core.py`](../../../src/simple_agents/pipeline/core.py#L612) `rerun`) runs again what a dead
run was given and serves its recorded calls from its own cassette, which is the case exactly;
`docs/pipeline.md` §1.13 documents it and the feature index in `docs/procedure.md` names it. It
was not found. The chunking is a reasonable design in its own right, and it is one the library
already had.

### DF6-D14 — `DocumentIndex` cannot be added to, so the project wrote its own vector store

**Acted on:** `DF6-I14`.

**Library.** `DocumentIndex` has `from_texts`, `save` and `load` and no incremental add
([`search.py`](../../../src/simple_agents/builtins/search.py#L344) `load` is the last of them). The
builder's rule was that the index persists and is additive (`BUILD-LOG.md:356`), so the project
holds vectors in SQLite with a text hash per row (`plot/vectors.py`), and its first search loop
recomputed every norm per query at 134.7ms against the library's 22.3ms before a cached matrix
took it to 3.3ms (`:527-531`, `research.md:114`). The library's index is used for the lexical
half only, rebuilt on every query.

### DF6-D15 — A failed resume consumes the suspension

**Acted on:** `DF6-I15`.

**Library.** `BUILD-LOG.md:435`: a resume that failed part-way could not be tried again and the
run was restarted. [`core.py`](../../../src/simple_agents/pipeline/core.py#L659) `resume`
releases the claim on a refusal before anything runs and discards it once the run is driving, so
a failure inside the resumed run leaves no suspension to claim. `HANDOFF.md:311` carries it as an
operational fact.

### 3.5 The procedure

### DF6-D16 — The product was built after `ship`, and the procedure has no shape there

**Acted on:** `DF6-I16`.

**Library.** `DF5-D19` recurring with a native app. `stored_output` at `ship` came back "I want
to discuss a design before you build it" (`brief.toml:2083-2092`); the first draft was rejected
(`BUILD-LOG.md:866`); the agreed spec is a section of `design.md` around four hundred lines long
written in four rounds; then five rounds of changes from the phone (`:1072-1129`), fourteen
defects found by an API test suite written the next day, among them every run the app started
dying on `RunEnvelope(role=None)` since the API was written (`:1175`), and four more rounds. The
`ship` stage asks four questions and none of them is about the product's design, and the
sitting that closed `DF5-I12` decided there is no seventh stage; this run is the second product
built on the road after the last gate.

### DF6-D17 — What the builder said himself, and which of it the library could have carried

**Acted on:** `DF6-I17`, `DF6-I18`.

**Task and library.** The coding agent's memory file holds eight standing rules from this builder.
Read against the library:

| Rule, in the memory file | Where it came from | What the library has |
|---|---|---|
| no silent caps; print the prompts | 18 truncation sites, every measurement downstream of them (`BUILD-LOG.md:483-490`) | The trajectory records every prompt whole and the build page shows them (`P3-62`); the `prompt_rules` decision was put to the builder as a summary until he asked for the text (`:467`). A `[:220]` inside a prompt function is invisible to anything |
| pipeline nodes, not hand scripts | the standing ranking as a bare function for a stage (`:566-568`) | FT-42 fired on the missing `score_corpus` and the coding agent read it as noise (`DF6-D6`) |
| the primary metric is end to end | `:541` | `DF6-D4` |
| long runs must be resumable | `:285` | `Pipeline.rerun`, not found (`DF6-D13`) |
| sample before concluding; estimate long tasks; run them in the background; ask before designing retrieval | the builder's | Not the library's to carry |

And one the memory file does not hold, which the checks should have: the catalogue went into
the code with no `dependency` decision because every kind but one had been marked
`not_applicable` at brainstorm and nothing re-asked them (`:222-228`, `brief.toml:385-390`).
FT-30 passed throughout. The builder found it by asking where the catalogue came from.

### What worked

**Library.** Recorded so the next run's reading starts from it. The `0.1.1` asking rule fired
once at brainstorm, when a guess put in prose came back unanswered, and was followed from then
on (`BUILD-LOG.md:70-76`). Comments through the served view carried ten threads; the first sat
unread for four hours because `simple-agents comments` was not run (`:338-344`), the builder set
`comments_block_gates` against exactly that, and the gate surfaced the next comment at once
(`:444-447`). Four construction refusals each named their fix, and one exposed a design error
rather than a wiring one: `ask_about_a_bounce` drawn last could never have affected the
recommendation it asked about (`:253-262`). FT-25 caught a consultation designed and never
registered (`:278-281`). `compare()` refused a verdict on fourteen examples and gave one on
twenty-one (`brief.toml:1972-1976`, `decisions.mainstream_facet`). And the builder's own
instrument, pairwise labels over the queue and the ranking, ran through `paired_figure`
(`evals/results/pairwise-1.json`).

### 3.6 The protocol's three categories

Read loosely, as [`setup.md` §4](setup.md#L58) says. **Interventions**: every retrieval decision
(`ask-before-designing-retrieval` in the memory file), the caps, the scripts, the metric, the
catalogue, the app design, and the queue holding shows he had rated (`:1301`). **Questions the
library should have answered**: the eight constants offered as one-clicks were answers to
questions the code already held (`DF6-D8`). **Wanted and never asked**: resumability, time
estimates, background execution, caching everything a source returns (`:230`), and a product
design to discuss before building (`DF6-D16`).

---

## 4. What is open

- **What a slice's terminal is** (`DF6-D1`): whether a cut successor edge out of the slice's
  own end node is the boundary or the end.
- **An evaluation over a pipeline that reads back what it writes** (`DF6-D2`, `DF6-D3`): a
  per-rollout store seam, a documented per-example copy, or both.
- **What joins a run and a results file to a registered pipeline** (`DF6-D4`, `DF6-D7`), which
  `DF5-D5` and `DF5-D17` left open and this run met from three sides.
- **What FT-42 reads when a decision names another role's work** (`DF6-D6`).
- **Who writes `recorded_at`** (`DF6-D9`), and whether the protocol's premise about it survives.
- **A product-design step after `ship`** (`DF6-D16`), decided once as no seventh stage.
- **The second cold run** (`DF5-Q1`), still not taken; this run was not it.
- **The scan pass.** The frozen copy and `runs/` hold the builder's viewing history, and this
  record quotes none of it. This repository is the private archive, so nothing here goes public.
