# Dogfood #2 — findings and the v0.1 changelog

`archive/plan-history.md` §4.3's task, the t-shirt fit finder, against the wheel built at `f8df15f`.
**`runs/dogfood-1/findings.md` and `runs/dogfood-1/run2-findings.md` are dogfood #1's two records and
are not restated here**; this document cites them. Findings numbered `DF2-Dn` and `DF2-Pn`
are this run's. Bare `D4`, `P1` and so on are dogfood #1 run 1's; `R2-` prefixed ones are its
run 2's.

**The run ended at 2026-08-08T08:04:25Z**, on the builder's verdict and his instruction not to
change anything further. §1 to §9 are pinned to **2026-08-07T22:55Z**, when they were written
and the run was still going; their figures are internally consistent at that time and were not
retrofitted. **§10 and §11 carry what happened after the pin**, including three further
findings numbered into the §4 and §5 series (**DF2-D7**, **DF2-D8**, **DF2-P5**) and the run's
first measured number. §11.6 is where it ends and what it did not produce. **§9 is what has
since been built**, including **DF2-D9**, which was found while preparing that sitting.

**A finding that has since been closed says so on its first line and is otherwise left as
written.** The figures below are the run's and are not retrofitted; where one was wrong rather
than superseded it is corrected in place and says so. §9 and §9.2 are the ledger: what landed,
what was decided against, and what is still open.

Final totals: 18 run directories, **$0.6697** of model spend, 99 tests, `simple-agents check`
0 failed and 3 passed at tier `prototype`. Nothing in this document was written into the
project.

**Project:** `/home/thilina/Projects/dogfood-2`, one commit (`1e88fda`, `pyproject.toml` and
`.gitignore`, Simple Agents installed from the wheel into `.venv`). Fresh coding-agent
session. The prompt asked for a build log with every interaction recorded verbatim, every
entry timestamped, `WAITING ON BUILDER` and `RESUMED` around each block, and every figure
naming the file it was read from, which is `runs/dogfood-protocol.md` §1's list. It also carried §4.3(c)'s
two constraints on the world: search rather than crawl, and cache every page.

**Elapsed 19:03:05Z to 22:55Z, 3 hours 52 minutes and still running.** 16 run directories, 13
of them live and 3 replays. Across the 13 live ones: 587 model calls, 631 tool calls and
**$0.4785** of model spend recorded. 246 of the tool calls were `spends_money`, and what those
actually cost is not in any artifact: see **DF2-D2**.

| | dogfood #1 run 2 | dogfood #2, at 22:55Z |
|---|---|---|
| Elapsed | ~190 min | 232 min, unfinished |
| Runs in the envelope | 635 | 16 |
| Model calls | 788 | 587 |
| Tool calls | 782 | 631 |
| Recorded model cost | $0.1682 | $0.4785 |
| Nodes, and kinds | 4 (3 D, 1 LLM) | 11 (7 D, 3 LLM, 1 Agent) |
| Built-in tools used | `document_search` | `http_fetch`, `web_search` |
| Project tools written | none | 3 |
| Tier | `evaluated` | `prototype` |
| `simple-agents check` | 9 of 9 | 3 of 3, 6 not applicable |
| Brief entries | 16 | 9 |

---

## 1. Method, and what did not survive verification

`BUILD-LOG.md` is a coding agent's account of its own work, so it is a hypothesis. Run 1's
survived completely, run 2's did not. **This one survives everywhere the artifacts can reach,
and `brief.toml` is where it fails** — which matters more than a wrong figure in prose,
because `brief.toml` is a file the conformance checks read and `simple-agents.md` §1.6 calls the
project's record of the builder's answers.

| Claim | Reproduced |
|---|---|
| Run 1 `runs/run_5ed0a8827153`: 33 model calls, 35 tool calls, 157,760 uncached input, 10,398 output, $0.030904 | Exact, all five. |
| Run 2 `runs/run_fb58bac5b2da`: zero suggestions, 7 "measured and did not fit", 1 dropped | Exact, from the `report` node's recorded output. |
| Run 3 `runs/run_eee26a1957e3`: 6 borderline suggestions, $0.045695 | Exact. |
| Run 4 `runs/run_53497a8a3a8e`: $0.027605 | Exact. |
| The four build runs cost $0.126 of model spend | Exact: $0.125760. |
| Eight live runs, $0.284 total | Exact: $0.284316, and eight is the count of record-mode runs at that point. |
| `runs/run_334c4ef28db3`: 1 fit, 2 borderline, 1 dropped, 4 not t-shirts, 1 women's, 5 category pages | Exact, every one of the seven counts. |
| `runs/run_78bacbb118fa`: `0 were category pages`, one confirmed fit on four dimensions | Exact. |
| Replaying `cassettes/fourth-run.jsonl` reproduces the run with no network | Exact. `runs/run_7d3a34946897` is 57 cassette hits, 0 misses, 28 model calls and 29 tool calls all flagged `replayed`. |
| Defect 3, the model writing `"unknown"` as a bare string, happened once | Exact. One occurrence across 183 schema-constrained responses in 12 cassettes. |
| `simple-agents check`: 0 failed, 3 passed, 6 not applicable | Re-run. Exact. See §2. |
| 79 tests passing | Exact. |
| The retailer probe: COS unreachable, Arket and Weekday 403 | Consistent. All three are commented out in `config/retailers.toml` with the evidence beside each. |

**Three false figures, all of them in `brief.toml`, and one is the shape run 2 was penalised
for.** `[entries.budget]` says the derivation came from a named run:

> The measured run (runs/run_53497a8a3a8e) made 33 model calls and used roughly 235,000
> tokens across all classes.

That run made **28** model calls and used **175,035** tokens. 33 model calls and 234,926
tokens are `runs/run_5ed0a8827153`'s — the first run, which crashed. `[entries.backend]`
repeats the call count beside a cost that is correct: "the last clean run
(runs/run_53497a8a3a8e) cost $0.0276 for 33 model calls".

This is `runs/dogfood-1/run2-findings.md` §1's failure, where a log quoted the numbers of a run it
had discarded. §4.1 added "every figure names the file it was read from" to stop it. **The
requirement was met in form and the figure still came from the wrong file**, so a citation is
weaker evidence than it looked: it records which file the writer believed they read.

**Four claims in `brief.toml` were true when written and are now false**, because the code
moved and the brief did not. Each was confirmed by the builder in round 3 at 20:12:57Z:

| `brief.toml` says | `config/retailers.toml` says now | Moved at |
|---|---|---|
| `max_live_searches_per_run=12 (about $0.06)` | `36`, about $0.18 | 21:05Z, then 21:58Z |
| `Loop(max_iterations=6)`, twice | `max_chases = 8` | 21:05Z |
| the price basis "has not been checked against Mistral's live price list" | verified against the live list, caveat discharged | 20:22Z |
| `max_cost is None` because "that basis is unverified" | the stated reason no longer holds | 20:22Z |

The middle two are recorded correctly in `BUILD-LOG.md` where they changed. The brief is
where the builder's agreement lives, and see **DF2-D6** for what the first row cost.

**One citation does not resolve, and the quote behind it is verbatim.** The log attributes
*"a wrong value asserted confidently and a value never found are different failures with
different costs"* to `docs/pipeline.md:573`. That line is about `Unknown` being falsy. The
sentence is real and exact, and it is at [`docs/procedure.md:167`](../../../docs/procedure.md#L167).
Cosmetic, and worth naming beside the `brief.toml` figures: both are the same slip, a
reference recorded from memory rather than from the file open at the time.

**Nothing else disagreed**, including every count in every run report, and the log's two
in-place timestamp corrections are themselves recorded rather than silent.

### 1.1 What §4.1's new build-log requirements bought, and where they did not reach

Three requirements were added to the protocol after run 2. All three were followed in form,
and the first does not survive being checked.

- **A timestamp on every entry. Present throughout, and half of them are composed rather than
  read.** *Corrected 2026-08-08 on Thilina's statement that "the timestamps are useless",
  which is closer to right than what this section first said.*

  The 30 section headers split cleanly into two populations, and the tell is the seconds
  field:

  | | Count | Reports a run's cost from a run that had not finished at the stamped time |
  |---|---|---|
  | Seconds precision (`20:13:55`) | 16 | **0** |
  | Minute only (`21:05`) | 14 | **11** |

  Eleven sections state a run's dollar cost and token totals under a timestamp **earlier than
  the moment that run ended**, by up to 34 minutes. `21:58` reports `run_142a2dee126c`, which
  ended at 22:32:03. `21:05` reports `run_334c4ef28db3`, which ended at 21:33:55. Every one of
  the eleven is minute-only; not one seconds-precision header does it.

  **The log confesses the mechanism twice and then keeps doing it.** At 19:33:10Z and again at
  20:08:35Z it records writing a timestamp it had not read off the clock, corrects both in
  place, and states the fix: "Changed how I do it: read the clock, then write the entry." Every
  header after that point but four is minute-only.

  **What survives.** Ordering survives; the entries are in sequence. The four
  `WAITING ON BUILDER` / `RESUMED` pairs survive, because all eight of those stamps carry
  seconds and are therefore clock reads, so the 21m51s of measured builder time in the third
  bullet stands. What does not survive is elapsed-per-stage from the section headers, which is
  what §4.1 asked the timestamps for.

  **The protocol lesson.** §4.1 asked for "a timestamp on every entry" and got a log where a
  read time and an invented one are typographically identical unless a reader thinks to look at
  the seconds field. The cross-check against run manifests is what exposes it, and that
  cross-check is only possible because the manifests exist. A build log with no artifacts
  beside it could not be audited this way at all.
- **Every figure names its file.** Followed, and **DF2** above is what it did not prevent.
- **`WAITING ON BUILDER` and `RESUMED`.** Four complete pairs: 3m58s, 11m11s, 4m22s and
  2m20s, 21m51s in total, and each subtraction is correct. **Three `RESUMED` markers have no
  matching `WAITING`**, which is where the instrument stops working:

  - Two are honest and correct. The builder volunteered a message at 19:22:08Z and another at
    19:32:50Z while the coding agent was writing code, and the log says so both times: "No
    WAITING/RESUMED pair for this one: I was not blocked."
  - One is a 31-minute gap, 20:28:30Z to 20:59:50Z, with no marker and no explanation. A live
    run occupies four minutes of it and the other 27 are unattributable.
  - One conflates. "Builder time: 19m 58s" at 21:19:48Z is measured from the previous
    `RESUMED`, so it counts the coding agent's own analysis of the measurement conflict as
    the builder's time.

  **The convention measures blocked waiting and this build was mostly not blocked.** The
  builder answered four question rounds and volunteered five times unprompted, and the second
  shape is the one the markers cannot see. The recoverable figure is 21m51s of blocked
  waiting out of 232 minutes; the true builder time is higher and is not on disk.

---

## 2. The ship criterion — `archive/plan-history.md` §3.3

> **v0 is done when a coding agent, given only the library and its docs, from a cold start,
> produces a trivial agent that passes `simple-agents check` at tier `evaluated`.**

Run directly against the project rather than read off the log:

```
simple-agents check: .
tier prototype, declared in brief.toml

  pass  FT-13  No trajectory logging      runs/run_142a2dee126c/trajectory.jsonl
  pass  FT-14  Model version unpinned     runs/run_142a2dee126c/manifest.json
  pass  FT-24  Elicitation skipped        brief.toml
    --  FT-01 FT-02 FT-03 FT-04 FT-06 FT-07
        Fires at tier evaluated, and this project claims prototype.

0 failed, 3 passed, 6 not applicable at tier prototype     exit 0
```

**The criterion is not met by this project, and is not due.** §3.3 names tier `evaluated`;
this project claims `prototype` and the brief argues for it: the builder chose a ground-truth
method and nobody has built a labelled set with it, so there is no number about how well it
works. The criterion was met twice by dogfood #1 and this run is not a third attempt at it.

**What the three passes rest on**, since item 10 §1.2 measured three hand-written files
passing at `prototype` with the library never called:

- FT-13 and FT-14 read a trajectory and a manifest the envelope wrote, from real
  `Pipeline.run`s. 16 run directories, 587 model calls, 631 tool calls.
- FT-24 reads a `brief.toml` whose 9 required entries are all `answered`, none deferred, each
  traceable to a numbered interaction. Its answers are also where §1's four stale figures are.

**Both artifact checks read a run that had not finished**, which is **DF2-D4**.

---

## 3. The four predictions — `archive/plan-history.md` §4.3(b)

These were written down before the run and are claims about what a cold agent does next.

### Structured data first, LLM last. **Held, and the shape is more interesting than the prediction.**

The prediction was that a cold agent reaches for LLM extraction on the whole page rather than
parsing `schema.org/Product` JSON-LD and size tables deterministically and using a model on
the residue.

**It parsed the structured data deterministically and then handed the parse to the model
anyway.** `fitfinder/htmlreduce.py` has a JSON-LD reader and a `_product_facts` function
pulling `name`, `brand`, `sku`, `color`, `material`, `size` and the offer prices out of the
`Product` block, and it keeps table structure through the reduction. Both are then rendered
back into text under a `=== STRUCTURED PRODUCT DATA ===` heading and sent to `read_specs`, an
`LLMNode` fanned out over pages. `PageReading.product_name`, `.brand` and `.price` come back
from the model, on a page where the deterministic parse already held all three.

So the prediction holds on the substance: no extracted field is filled from the parse. What it
did not anticipate is that the residue never gets separated — the deterministic work exists,
and it is used to make the model's input smaller rather than to make the model's job smaller.

### Where agency earns its cost. **Half.**

The prediction named three candidates — the missing-measurement hunt, constraint relaxation
when zero products pass, and possibly cross-retailer strategy — and predicted exactly those
become `AgentNode`s and nothing else does.

- **The hunt is an `AgentNode`, and it is the only one.** `chase`, with
  `Loop(max_iterations=8, then="finalise")`, a node `Budget(max_steps=14, ...)`, and
  `DropOldestTurns(keep_turns=4)`. The manifest records all of it.
- **Constraint relaxation was never built.** `runs/run_fb58bac5b2da` returned zero suggestions
  from seven measured candidates and nothing relaxed anything; the run reported the zero. The
  cause was a measurement bug rather than a real absence of stock, so the case that would have
  motivated it never presented honestly.
- **Cross-retailer strategy is not a node.**
- **Nothing else became an `AgentNode`**, and this half is stronger than a bare pass. At
  20:26Z the builder was re-asked the agency question in plain words and chose to *widen* it:
  "let it choose what to search for too". The coding agent implemented that as an `LLMNode`
  plus a `Deterministic` node holding the cap, and argued the distinction explicitly: "one
  call at a fixed point in fixed control flow. The model chooses the CONTENT of the queries;
  it does not choose what happens next." **A builder asked for more agency and FT-11 held the
  line on what kind that makes it.**

### Everything else collapses into `LLMNode`s under ablation. **Not reached, and §10 is why.**

The project is at stage `build` with an empty `evals/` directory, so no ablation has run. The
prediction's first clause is "the ablation is run at all", and **§10 records the run never
reaching the stage where it would be**.

### The built-in tools are found. **Half, and the miss is defensible.**

- **`http_fetch` was found, read, and delegated to rather than reimplemented.** `read_page` is
  a project tool wrapping it, and the log is explicit that robots.txt, the host allow-list and
  the inter-fetch interval "stay the library's code". `web_search` was found the same way and
  given a project provider. **This is D4's routing fix holding on a second independent cold
  run**, and on a harder case than run 2's: the project needed something `http_fetch` does not
  do, and extended it instead of replacing it.
- **`extract_to_schema` was never reached for, and the docs told it not to.** That tool's own
  docstring opens "Most extraction is a node: `LLMNode(build_prompt, output_schema=Facts)` for
  one passage and `LLMNode(..., over="documents")` for many... Reach for this tool where the
  agent decides during the run that it needs typed facts out of something it has just read."
  `read_specs` is exactly the node form, so not using the tool there is correct routing.

  **The case the tool exists for is present in this project and went unserved.** `chase` is an
  `AgentNode` that reads pages mid-run and needs measurements out of them, which is the
  sentence's second half. It extracts them through its own `finish` payload instead, and the
  log never considers the tool. So the prediction fails on the letter, and what it exposes is
  that the routing sentence in `docs/procedure.md` names the tool by name while the guidance
  distinguishing the two cases lives only in the tool's docstring.

---

## 4. Library defects

Ranked by what they cost this project.

### DF2-D1 — A value that cannot travel on a declared edge goes through `ctx.workspace`, and the docs point at it

*Settled at its sitting, 2026-08-09; `build-logs/loop-accumulator-build-log.md` is the record.
Three claims below were wrong and are corrected in place; everything else is as pinned.*

**The heading's premise did not survive being run.** The value can travel on a declared edge,
and could when this was written. The node before the model node routes to both it and a fold
node, the fold joins the two, and the fold closes the cycle carrying the working set: a probe
ran that shape with nothing in the library changed, and every value landed in a recorded
`inputs`. So "currently has no answer that keeps the data flow in the graph", below, is false.
What is true is that the shape was written down nowhere, and that getting it wrong is silent:
**dogfood #1 run 2 met the same shape, chose the graph, and read the working set off the edge
that entered its cycle, which stays resolved at what entered. 12 of the 20 runs that went round
twice lost passages the first pass had retrieved, 29 in total, and its own comment says a union
was intended.** `docs/pipeline.md` §1.3 and §1.4 now carry both shapes, and `keep=` carries an
input key past a fan-out, which is the one narrowing the library's own container was doing.

**Design bug, and it is the one that matters.** `plan.md` §2.2 records shared mutable state
as rejected at the branching sitting, with the revisit condition: "Revisit only on a real
project showing a value that cannot travel on a declared edge; a preference for the shape is
not that." **This is that project.**

`chase` returns a `ChaseFinding` describing one candidate. `select_unresolved` needs the whole
working set to pick the next one. There is no edge that carries it, and the log says so:
"A `ChaseFinding` describes one candidate and cannot carry the working set, so the state lives
in `ctx.workspace`". Three values now travel outside the declared graph:

*The reader and distance columns were wrong and are corrected here. Distance was never what
broke the flow: a narrowing node in between is, and there are two kinds. `candidates.json`, a
fourth file the audit found, reaches only 2 of the 18 runs, having been added near the end.*

| File | Written by | Read by | What it cannot cross |
|---|---|---|---|
| `chase_state.json` | `select_unresolved`, `finalise` | `select_unresolved`, `finalise`, `report` | the `chase` cycle, whose model node emits only a `ChaseFinding`, and then the `write_notes` fan-out |
| `search_plan.json` | `collect_plan` | `match_direct` | the `read_specs` fan-out, four nodes on |
| `candidates.json` | `find_candidates` | `match_direct` | the same fan-out |
| `unreadable_listings.json` | `fetch_pages` | `match_direct` | the same fan-out, and it does travel on the edge as far as there |

**Item 8c's first rejection reason, reproduced in a file.** That sitting rejected shared state
because "`inputs` becomes a pointer into ambient state so a node is no longer replayable from
its record". In `runs/run_334c4ef28db3/trajectory.jsonl`, the `report` node's recorded
`inputs` is `{"items": [...]}`, the fan-out of notes. Its recorded `outputs.searched_for` is
five search queries:

```
['slim fit dark olive t-shirt', 'athletic fit burgundy cotton t-shirt',
 'regular fit deep teal short sleeve tee', 'slim athletic fit chocolate brown t-shirt',
 'forest green athletic cut t-shirt']
```

None of them appears anywhere in its inputs, checked string by string against the serialised
record rather than read off the file. The trajectory says the node invented them. They
are the model's own query plan, and printing them is what the builder asked for at 20:26Z so
they could see the judgement they had delegated. **The same holds for six of the nine numbers in
that record's `summary`**: `dropped_no_measurements`, `rejected_on_measurements`, `not_a_tshirt`,
`womens_range`, `category_pages` and `unreadable_pages` all arrive from `chase_state.json`. The
node's `inputs` are 456 bytes and its `outputs` are 6,367.

**Run 2 rejected this shape by name and run 3 took it.** `runs/dogfood-1/run2-findings.md` §6
records run 2 choosing the cycle over "the workspace as a side channel", which its log called
the option that "hides the data flow from the manifest's declared edges, which is the thing
this library exists to prevent". Run 3 took the cycle *and* the workspace, cited
`docs/pipeline.md:520` as authority, and got no reason not to: that line describes the
workspace as "a fresh directory per run. Files the run produces go here". Prose half at
**DF2-P1**.

**What this does not settle.** The library refusing `ctx.workspace` is not on the table — it
is where a run's files go and this project also uses it for what it is for. What the run
establishes is that the loop-accumulator case is real, forced rather than preferred, and
currently has no answer that keeps the data flow in the graph.

*The last clause is the claim the sitting overturned; see the note at the top of this entry.
Also corrected there: `candidates.json` is written where the builder can read it (`agent.py:521` in the dogfood-2 project's own repository), which is
the workspace used for what it is for, so it is a weaker instance than the other three.*

### DF2-D2 — Nothing bounds or reports what a `spends_money` tool spends

*Settled at its sitting, 2026-08-09; `build-logs/tool-spend-build-log.md` is the record. One figure below was wrong and is corrected in place; everything else is as pinned.*

**Design bug.** The library requires a `DeclaredCost` on a `spends_money` tool
([`DeclaredCost`](../../../src/simple_agents/tools.py#L97)), writes it on every tool call and into the
manifest, and **reads it back nowhere**. There is no total on any artifact.

Two consequences, both of which this project met.

- **`max_cost` cannot reach it.** `run.charge(cost=...)` is called at one site,
  [`run.charge`, context.py:658](../../../src/simple_agents/context.py#L658), around the model call. A tool call charges
  steps and wall clock and no money, so the budget axis named for cost bounds the model and
  nothing else.
- **`totals.cost` is model spend and does not say so.** `runs/run_334c4ef28db3/manifest.json`
  reports `totals.cost.value = 0.035015` beside a `tools` block declaring three tools at
  $0.005 a call, and the run made 49 tool calls.

**What the project had to build.** `max_live_searches_per_run` and `max_fetches_per_run` in
`config/retailers.toml`, a live-search counter on the provider, and a `usd_spent` figure
printed to stdout by `run.py` and saved nowhere. Its `brief.toml` names the gap without
knowing it is one: "**Separately from the library's budget axes**, two ceilings bound what
reaches the network".

**The declared figure would also have been wrong, and this paragraph had the size of it
wrong.** *Corrected 2026-08-09 at the DF2-D2 sitting; the original said the log put true spend
"near $0.19" and called the declared figure 6× high, and neither is supported by any artifact.*
Across the record-mode runs before the 22:55Z pin, 246 `spends_money` calls at $0.005 is
**$1.230** declared, against **$0.955** actually spent: 191 of those calls reached the provider
and 55 did not. Across all 18 runs it is $1.770 declared against $1.315 spent, **1.35× rather
than 6×**. `build-logs/tool-spend-build-log.md` §1.1 carries the measurement and the method.

Nothing spent on the other 91 calls: 60 were served from the project's cache, 19 were refused
and did nothing, and 12 were replayed from a cassette. **Two of those three states are fields
the library wrote on the same record**, `error` and `replayed`, and the third became the
library's at absorption item 7.

`docs/tools.md` §1.5 is honest that the figure is "as declared rather than as measured", and
its stated purpose is pre-flight k×n arithmetic — which an evaluation refuses to perform, since
`runner.py:671` will not start over a `spends_money` tool unless it is replaying. The gap is
that a run with a metered tool has no measured figure at all, from any source the library owns.

### DF2-D3 — A `Pipeline.run` against an unpaced hosted client gets no warning, and this one lost a run to it

*Closed 2026-08-08. §9 says what landed. The write-up below is as pinned.*

**Design bug.** R2-D6's fix gave `PacedClient` an `expect_callers`, made `EvalSuite.run` set
the floor from concurrency, and made it warn on an unpaced hosted client
([runner.py:2862](../../../src/simple_agents/evaluation/runner.py#L2862), `_pace_for`). **The warning is inside
`EvalSuite.run`.** This project never runs an evaluation. `run.py` passes
`MistralClient(model=...)` bare to `Pipeline.run`, and nothing said anything.

**Measured.** Summed over the 13 record-mode runs, **29.6 minutes of 63.2 minutes of run wall
clock, 47%, is HTTP retry backoff after a 429.** The `held_back_ms` values are 1000, 3000,
7000, 15000 and 31000, which is the adapter's doubling backoff at
[_http.py:286](../../../src/simple_agents/adapters/_http.py#L286) reaching its fifth attempt. Worst run:
`runs/run_1303c17cf13a`, 243 of 435 seconds.

**And a run died of it, at 22:24Z, while this document was being written.**
`runs/run_40b3a5688ce0` ended `outcome: "error"` with a `CallerFacingError`:

> `https://api.mistral.ai/v1/chat/completions` rate-limited the run and 6 attempt(s) did not
> clear it (429: Rate limit exceeded). Those attempts waited 31s in total and the window had
> not reset. **Pace the calls against the backend's published allowance: `PacedClient(client)`
> waits once for every caller sharing it.**

Its cost is unpriceable, because a rate-limited call records no token counts. **The library
names the fix precisely, and only after the run is gone.** The signal it needs is already in
the trajectory: every `model_call` record carries `rate_limit.remaining_tokens`, and it reads
`0` on the calls that then back off.

Run 1's D2 was `PacedClient` blowing a budget. Run 2's R2-D6 was its default floor being wrong
under concurrency. This is the third finding at the same seam and the first where the client
was simply never reached for.

### DF2-D4 — `simple-agents check` certifies whichever run started last, finished or not

*Closed 2026-08-08. §9 says what landed. The write-up below is as pinned.*

**Design bug.** `_latest_run` returns `max(manifests, key=_started_at).parent`
([artifacts.py:423](../../../src/simple_agents/conformance/artifacts.py#L423)), and `_started_at` reads
`started_at` alone. Nothing reads `outcome` or `ended_at`.

Reproduced twice, on two different runs, while the project was running:

```
22:26Z   pass  FT-13 ... runs/run_ed7ec6c604d5/trajectory.jsonl     manifest: ended_at null, outcome null
22:30Z   pass  FT-13 ... runs/run_142a2dee126c/trajectory.jsonl     manifest: ended_at null, outcome null
```

Both certified a run that was still executing, over eleven that had completed. The same
selection would pick `runs/run_40b3a5688ce0`, which errored 88 seconds in and has no cost, or
`runs/run_581dcc5f054e`, a failed replay holding four node executions.

**This is R2-D5 one artifact over.** That fix added a `results` key to `brief.toml` so a
project with five results files can say which one it stands behind, and the checks read it.
There is no equivalent for a run, and this project has sixteen.

Nothing is wrong with what passed: FT-13 asks whether a trajectory exists and parses, FT-14
whether the model identifier is pinned, and a half-written run answers both. What is wrong is
that a project cannot say which run is its evidence.

### DF2-D5 — `held_back_ms` reaches the record and no aggregate

*Closed 2026-08-08. §9 says what landed. The write-up below is as pinned.*

**Design bug, small, and the second half of R2-D9.** That fix put `held_back_ms` on the
`model_call` record, and this is the first project to carry it: 1,774 seconds of it. `totals`
holds `tokens` and `cost` and no wait, and `counts` holds record counts. Learning that 47% of
a run was waiting means reading 71 records and summing a field.

`runs/dogfood-1/run2-findings.md` R2-D9 stated the problem as "a project asking 'how much of this
evaluation was waiting' has the aggregate wall clock and no split". The split now exists per
call. The aggregate still does not.

### DF2-D6 — A builder-confirmed ceiling tripled and every gate still passed

*Closed 2026-08-09. §9.2 says how. The write-up below is as pinned.*

**Design bug, and the honest version is that it may be a documentation one.** At 20:12:57Z the
builder was shown `tool_effects` tool by tool and confirmed it, including "Capped at 12 live
searches per run, about $0.06", having been offered and declined a cap of 6. By 21:58Z the cap
was **36**, about $0.18 a run, raised twice on the coding agent's own judgement that the chases
were starved. `runs/run_ed7ec6c604d5` then stopped early on exactly that ceiling, its own error
reading "This run's search budget is spent: 36 live searches, about $0.18."

`brief.toml` still says 12. FT-24 reads each entry's `status` and passes, because an entry's
truth is prose in a TOML value and no check can compare it to a number in another file.

**What makes it a library question rather than a project slip.** The brief is where the
builder's agreement is recorded, and the library has a settled position on a required question
going unanswered (FT-24) and on a deferral outliving its stage (D7's fix). It has none on an
answer whose premise has since changed. The three axes here — a money cap, a loop bound and a
discharged caveat — are the answers to `tool_effects` and `budget`, which are two of the four
questions the `build` gate exists to hold.

---

## 5. Documentation bugs

Split as `runs/dogfood-1/run2-findings.md` §7.1 settled it: prose that is unclear, ambiguous or
self-contradicting, which the review catches, against prose that is clear and false, which
only running the code catches. `docs/procedure.md`, `docs/index.md` and `docs/conformance.md`
have never been reviewed.

### 5.1 Prose that is clear and correct, and does not say the thing

**DF2-P1 — `docs/pipeline.md`'s `workspace` row describes where a run's files go and never
says that a value routed through it leaves the declared graph.** *Closed 2026-08-09; §9.2 says how.* The row reads: "A fresh
directory per run. Files the run produces go here, beside the trajectory that records what it
did with them." Every word is true. A coding agent needing to carry an accumulator around a
cycle reads it as the sanctioned answer, which is what happened, and the sentence that would
have stopped it — that a node reading a workspace file is no longer replayable from its
recorded inputs — is in item 8c's sitting record and nowhere a builder can see. The prose half
of **DF2-D1**.

**DF2-P2 — `docs/tools.md` §1.5 says what `declared_cost` is and no document says a run
produces no tool-spend total.** *Closed 2026-08-09; §9.2 says how.* §1.5 is careful: "Recorded on every tool call and in the
manifest, as declared rather than as measured." `docs/run-envelope.md` describes
`totals.cost` without saying it is model spend only, and `docs/pipeline.md` §5 describes
`max_cost` without saying it bounds model calls only. Each document is accurate about its own
half; nothing joins them, and a project running a metered tool has to discover the join by
building its own counter. The prose half of **DF2-D2**.

### 5.2 The elicitation surface

**DF2-P3 — `docs/procedure.md` prints the entry name beside every question and never says it
is internal.** *Closed 2026-08-09; §9.2 says how.* Stage 1 says the command "prints each question, what makes it answerable, and
the entry to record it under. Put every one to the builder." The entry name is an identifier
for `brief.toml`; the question is the builder-facing text. Nothing marks the difference, and
`simple-agents questions` prints them together.

The coding agent carried `agency_boundary` as an outstanding item and asked the builder to
confirm it by that name. The builder's reply, verbatim: **"I don't know what agency_boundary
is."** The coding agent's own diagnosis is right — "asking it in vocabulary they have no reason
to know is not asking it" — and re-asking it in plain words produced a *different answer*: the
builder widened the agency rather than confirming it, on the one entry that had been carried as
unconfirmed for 67 minutes. The library's jargon in front of the builder cost an hour and
nearly banked the wrong answer.

**DF2-P4 — the `absence_vs_error` scaffold asks for a direction and the code consumes a
magnitude.** *Closed 2026-08-09; §9.2 says how.* This is the one entry in §7 and is written up at **§7.1**.

---

## 6. What did not go wrong

Recorded because a findings document that lists only failures misreports the run.

- **R2-D1's fix holds on an independent project.** 183 schema-constrained JSON responses
  across 12 cassettes, **zero mangled key names**, against run 2's 104 of 114 parseable
  responses carrying at least one. The compliance repair to `response_format_for` is the
  single most load-bearing fix either dogfood #1 run produced, and this is its first
  confirmation outside the project that found it.
- **One cassette path per recording, thirteen times.** R2-D3's refusal was never met, because
  the project never pointed two recordings at one file. `diverged` is 0 on every manifest.
- **The replay property was checked rather than assumed**, found a real defect (a replay
  cannot hit without the recording run's seed), and the first fix for that defect was wrong in
  a way the log records: it found failed replays' manifests, which are more recent and name the
  same cassette. Fixed by reading only manifests whose `cassette.mode` is `record`.
- **FT-11 was applied without being prompted, and held under pressure.** One `AgentNode` out
  of eleven nodes, argued in `brief.toml` and in the design entry. When the builder asked for
  more agency, the answer was an `LLMNode` and an explicit argument for why that is not an
  `AgentNode`.
- **The fit verdict is arithmetic in `Deterministic` nodes**, and the log's reason is the
  library's own: a `Deterministic` node makes no model call, "so there is no path by which a
  fit verdict comes from a token sample".
- **D3's warning was silent and did not need to be.** Every `Maybe[T]` field in
  `fitfinder/schemas.py` carries a description naming the tagged form, and the module docstring
  cites the replacement rule. One bare `"unknown"` literal in 183 responses, caught by the
  library's own refusal and corrected on the retry.
- **`allow_unknown=False` was used twice, correctly, and the waiver is in the manifest.** A
  one-line rationale and a search plan have no absent state, and both nodes record the waiver.
  The first was found the hard way: every rationale in `runs/run_eee26a1957e3` came back as an
  absence carrying the prose in its `reason` field.
- **`DropOldestTurns` was reached for rather than truncation hand-rolled inside a prompt**,
  after a first run spent 157,760 uncached input tokens on one chase. Its drops are on every
  `model_call` record where FT-17 reads them, six per call with a reason.
- **The plausibility bound is the defence, not the prompt.** After a field description caused
  the model to halve an already-halved chest measurement and silently reject seven correct
  matches, the fix that landed was `PLAUSIBLE_CM` in a `Deterministic` node. The log's own
  reading: "a prompt is not a guarantee". The same pattern was then applied *pre-emptively* to
  sleeve length, where two measuring conventions differ by 20cm.
- **A tension between two builder answers was put back to the builder rather than resolved.**
  The first measurements described a boxy shirt and the words said "I don't like boxy cuts";
  the arithmetic was shown and the question asked. The builder had mismeasured. Had the numbers
  been used, every suggestion would have been 3cm too wide.
- **A style inference was deleted rather than tuned.** `plan_searches` derived "a boxier,
  shorter cut" from a length-to-chest ratio, which for this builder's real numbers would have
  told the model to search for the thing they had explicitly said they dislike.
- **Retailers were probed rather than recommended from reputation**, which found that two
  retailers configured since the first hour could not be reached at all.

---

## 7. `runs/dogfood-protocol.md` §1 step 5 — the three categories

**Answered by Thilina at the sitting on 2026-08-07, asked directly rather than inferred from
the transcript**, with the run still in progress.

His answer: *"Nothing from me. You can tell from the build log where I intervened (mid convo
messages), but I don't think those have a lot to do with the library itself. Except maybe the
precision vs recall balance options being offered being too extreme. But I don't remember if I
was offered more balanced options."*

1. **Interventions he was forced to make: none.** He intervened five times unprompted — the
   search vendor changing, two revised answers, "widen the retailer list", and the
   measurements arriving in two goes — and reads all of them as changing his mind rather than
   rescuing the build.
2. **Questions the library should have answered itself: one, and it is not over-asking.** See
   §7.1. Roughly 20 questions across six rounds, against run 2's 18 and run 1's 14, and the
   count itself drew no complaint.
3. **Things he wanted to volunteer and was never asked for: none.**
4. **Where the transcript and the log disagree: nothing raised.**

**§4.1 said dogfood #2 was the categories' last chance on a task whose shape they were designed
for, and the result is one entry from three runs.** That entry is category 2, it was raised
with an explicit "I don't remember", and it was the artifacts that settled it. **Every other
finding in §4 and §5 of all three records came from reading the artifacts.** The instrument
found one thing in three runs and could not confirm it on its own.

### 7.1 The one entry, checked against the log

**His memory is right: more balanced options were not offered.** From `BUILD-LOG.md`, round 1
question 4, the three options put to him were:

| Option | |
|---|---|
| a wrong fit is much worse | marked Recommended |
| a missed shirt is worse | |
| about the same | "I said I would push back on it", quoting the library's own reason |

The scale offered both poles and a midpoint the coding agent had pre-committed to arguing
against. He picked "a wrong fit is much worse". **Twenty-four minutes later, unprompted, he
corrected it:** *"I would say that 'a wrong fit can be slightly worse' rather than 'is much
worse'. I check them, so it's not like I buy them directly."* His real position sat between
the first option and the midpoint and was not on the list.

**What it cost.** The coding agent had built tightly on "much worse". The revision moved
`borderline_extra_cm` from 2.0 to 3.0 and removed the `lead` bucket's requirement that the
brand have produced a confirmed fit elsewhere in the run — both verified in
`fitfinder/matching.py` and `config/profile.example.toml` today. Under the first answer a shirt
4.5cm off vanished from the report entirely.

**Where the library's share is.** `simple-agents questions --stage shape` prints:

```
ask:      Does a wrong answer cost more than a missing one, and by how much?
scaffold: Put two concrete scenarios from the builder's own domain side by side, one where
          the agent asserts a wrong value and one where it reports that it found nothing.
          Ask which is worse. Do not ask it in the abstract (FT-10).
```

**The question asks for a magnitude and the scaffold instructs a comparison.** "and by how
much?" is the half the code consumes — `borderline_extra_cm` is a number in centimetres — and
"Ask which is worse" is the half a coding agent operationalises, because it is the
instruction. The scaffold's own advice is followed exactly: two concrete scenarios from the
builder's domain, and a question about which is worse. It produced a direction, and the
project turned a direction into a number.

FT-10's concern is that the question not be asked in the abstract, and it was not. What is
missing is anything saying the answer has to be graded, and that a builder who checks
suggestions before acting on them is in a different place on the scale from one who does not.

---

## 8. Prior questions this run answers

- **`plan.md` §2.2, shared mutable state with reducers.** The revisit condition is "a real
  project showing a value that cannot travel on a declared edge". **Met.** See **DF2-D1**. This
  is the first of the three dogfood runs to build a cycle whose body cannot carry the
  accumulator, and it resolved it with a file the graph does not know about. Item 8c's first
  rejection reason is visible in `runs/run_334c4ef28db3/trajectory.jsonl` as a node whose
  outputs contain five values its recorded inputs do not.

  *Corrected 2026-08-09 at the DF2-D1 sitting.* The condition was met on a premise that did not
  hold: the cycle's body could carry the accumulator, with a fold node inside the cycle, and a
  probe ran that shape against the library as it stood. The trajectory evidence is unaffected
  and is what the sitting worked from. §3.2.1's shared-state entry is closed.
- **`build-logs/item8c-build-log.md`, branching.** Met a third time and used again: a
  bounded cycle, a route over a validated output, a `Join` with `absent` read on both arms, and
  `Loop(then=)` reaching `finalise`. This project also uses parallel-free routing and an
  eleven-node graph, which is the largest either dogfood has built.
- **`plan.md` §2.1, no seam for a project-supplied count or total.**
  The entry predicted "dogfood #2's extraction residue might" reach for one. **It did, and
  built it by hand rather than reaching.** `report`'s summary block is eight counts —
  `dropped_no_measurements`, `rejected_on_measurements`, `not_a_tshirt`, `womens_range`,
  `category_pages`, `unreadable_pages` and the three bucket sizes — every one a count over the
  run with no interval, assembled in a `Deterministic` node and printed by `run.py`. No
  `ProjectMetric` was declared, because no evaluation exists yet. **The entry's own test is
  whether `failure_rate` and `absent_outputs` were insufficient, and they were: the project
  needed to know how many candidates were dropped and why, which neither reports.** Still open
  as a design question, and no longer open as to whether a project reaches for one.
- **`plan.md` §2.2, a payload stored by reference.** **Exercised for the first time.** The
  largest trajectory is `runs/run_78bacbb118fa/trajectory.jsonl` at 174 records, and the
  payloads are reduced retail pages of up to 24,000 characters each, carried in
  `tool_call.outputs` and again in every subsequent `model_call.inputs.messages` inside the
  same chase. The first live run spent 157,760 uncached input tokens on one chase for exactly
  this reason, and the project's answer was `DropOldestTurns(keep_turns=4)`, which shrinks what
  is *sent* and not what is *recorded*. Item 8b's measurement said 91.4% of a file was one set
  of results written repeatedly; this project is the same shape with larger payloads.
- **`archive/plan-history.md` §4.2's routing lesson.** "A shipped component a coding agent has no reason to
  open is one it reimplements." Carried into §4.3 as a prediction and **held**: `http_fetch`
  was found and extended rather than reimplemented, on a project that needed four things it
  does not do.

---

## 9. What has landed

**Five of them, on 2026-08-08, at the sitting.** The other findings are untouched and §11.6
lists what the run produced. **1191 tests pass**, up from 1169, which is this fix set alone; other work was in flight in the same tree and the repository count is higher.

| Finding | What landed | Kind |
|---|---|---|
| **DF2-D9** | `bootstrap_ci` returns Wilson where every example scored the same and that score is 0 or 1, so a set with no variation no longer reports zero width; `Interval.method` says which calculation produced the endpoints; `wilson_ci(successes, n)` is public | code |
| **DF2-D7** | `warn_literal_absence_union` at `LLMNode` and `AgentNode` construction, on the shape rather than on the wording | code |
| **DF2-D4** | `_latest_run` prefers the most recent run whose `outcome` is `completed` or `stopped_early`, falling back to the newest where none finished | code |
| **DF2-D5** | `totals.held_back_ms` on the manifest, format `0.11` to `0.12` | code |
| **DF2-D3** | `warn_unpaced_wait`, once per run, on the first call held back against a hosted backend | code |

**Verified against dogfood #2's own artifacts**, running the source rather than the wheel:

```
check now reads: runs/run_3af779ccfd7d   (outcome completed, the log's "clean run")
the project's number through the library: 4/4 = 100%, 51% to 100%
totals.held_back_ms across the build: 4028 s
```

The second line is the one worth keeping. `label.py` hand-rolled Wilson because the library had
nothing that fitted; the library now returns the same interval the project computed for itself.
The third is 67 minutes of waiting that took summing 587 records to find.

**DF2-D9 was found while preparing the sitting rather than during the run**, and it is the
largest of the five: the defect is at every n, not only at small n, and it had been reachable by
any project reporting 100% or 0% on any metric. `runs/dogfood-1/findings.md` **D6** shows it in the
field a run earlier, as `difference 0.000 [0.000, 0.000] n=19`, and it was read there as a
correct result. A paired difference is not a proportion, so that case still reports zero width
and the docstring now says what it means.

**One test asserted the defect and was rewritten.** `test_a_set_with_no_variation_has_no_width`
pinned `width == 0.0`. It is now
`test_a_set_where_every_example_scored_the_same_does_not_claim_certainty`.

### 9.1 What was decided not to build

- ~~**A declared total for `spends_money` tool spend (DF2-D2).**~~ **Reversed 2026-08-09 at the
  DF2-D2 sitting.** This bullet rejected the total on a figure that was wrong: it said the
  declared figure was 6× the true one, and it is 1.35× (§4, as corrected). The rejection also
  rested on `max_cost` stopping runs early, which `simple-agents.md` §2.3 was at the same time
  enforcing against a figure up to 8× high on purpose; that entry was reopened at the same
  sitting and now refuses rather than over-charges. What the bullet identified correctly is what
  shipped: a tool reports what it actually spent, through an injected meter, and the total is
  measured rather than declared. `build-logs/tool-spend-build-log.md` is the record.
- **Making `unknown_literal` required (DF2-D7's other half).** It would put a question about
  JSON union decoding in front of every builder on every project, which is what §4.1 step 5's
  second category watches for. A warning that fires on the shape costs nothing when the shape is
  absent and names the field when it is present. **The general claim — a warning on a detectable
  shape in place of a question asked of everyone — is Thilina's to rule on**, since it would
  apply to other optional entries.
- **A `run` key in `brief.toml` mirroring R2-D5's `results` key.** `runs/dogfood-1/run2-findings.md`
  §9.3 rejected refusing a project for holding several artifacts, and preferring a finished run
  fixes this one with no format change and no builder burden.
- **Machinery for the drifting brief (DF2-D6).** Nothing can compare prose in a TOML value to a
  number in another file. The gap is that nothing tells a coding agent to revisit an entry when
  it changes a number the builder confirmed, which is prose.

### 9.2 Still open, and unproposed

Nine findings and two protocol amendments as written. **All nine closed on 2026-08-09**, at the
DF2-D2, DF2-D1 and ground-truth sittings and the prose pass between them, and each row says
how. **What is open: the §1.1 timestamp amendment**, and nothing else.

| | Where it is written up | In one line |
|---|---|---|
| ~~**DF2-D1**~~ | §4, `build-logs/loop-accumulator-build-log.md` | **Settled at its sitting, 2026-08-09.** The accumulator could travel on a declared edge the whole time; what was missing was the shape being written down. `docs/pipeline.md` §1.3 and §1.4 now carry it, `keep=` carries an input key past a fan-out, and `plan.md` §2.2's shared-state entry is closed. |
| ~~**DF2-D2**~~ | §4, `build-logs/tool-spend-build-log.md` | **Settled at its sitting, 2026-08-09.** A tool reports what it spent; the total is on the manifest and in the evaluation report; it depletes `max_cost`. The "6× wrong" figure in §4 was corrected to 1.35×. |
| ~~**DF2-D6**~~ | §4 | **Closed 2026-08-09, prose.** `docs/procedure.md` stage 1: an answer naming a figure goes stale when the code needs a different one, and the new figure goes to the builder. |
| ~~**DF2-D8**~~ | §11.2, `build-logs/ground-truth-build-log.md` | **Settled at its sitting, 2026-08-09**, merged with the labelling machinery. Its first measurement was that R2-D7's test was never administered. What shipped: `docs/evaluation.md` §1.4 rewritten to a fan-out, `RunEnvelope(role=...)` so a labelling pass is not certified as the agent's run, and `Label` with `evals/labels.jsonl`. A check over the label file was declined on the `simple-agents.md` §3.2 ceiling, so this finding's own complaint stands by decision: no check sees the measurement, and that is the ceiling rather than a gap. |
| ~~**DF2-P1**~~ | §5.1 | **Closed 2026-08-09, prose.** `docs/pipeline.md` §3 says a value written to the workspace and read back is not in the reading node's `inputs`. *This row said it stated the mechanism and prescribed no alternative; the shipped sentence also said to carry the value on an edge. Corrected 2026-08-09 at the DF2-D1 sitting, which found the prescription right and now points it at §1.3 and §1.4.* |
| ~~**DF2-P2**~~ | §5.1 | **Closed by the DF2-D2 build, 2026-08-09.** A run produces a tool-spend total; `docs/run-envelope.md` §4.3 and `docs/tools.md` §1.5 say what it is. |
| ~~**DF2-P3**~~ | §5.2 | **Closed 2026-08-09.** Fixed in `simple-agents questions` rather than in prose: the output labels the name as the `brief.toml` key and says to put `ask` to the builder in their own words. |
| ~~**DF2-P4**~~ | §5.2, §7.1 | **Closed 2026-08-09.** The scaffold now asks by how much, on a graded scale, and asks what the builder does with an answer before acting on it. |
| ~~**DF2-P5**~~ | §11.2 | **Closed 2026-08-09.** `docs/pipeline.md` §6 is what a fake-model run catches and what it cannot; `docs/procedure.md` stage 2 routes to it before a paid run. |
| §1.1 | §1.1 | `runs/dogfood-protocol.md` §1's timestamp requirement should ask for seconds, so a read stamp is distinguishable from a composed one. |
| ~~§10~~ | §10 | **Closed 2026-08-09, prose.** Stage 2's gate now says a green suite means the run was recorded rather than that the agent works. |

**DF2-D8 needed a sitting rather than a fix, and it was not its own.** Merged
with the labelling machinery on 2026-08-09, on Thilina's ruling: `label.py` is one artifact
producing both findings, and a design that answers where a label is stored and who can see it
cannot be separated from one that answers how the label was made. The evidence across all three
dogfoods is gathered in `archive/dogfood-absorption.md` item 10, and
`build-logs/ground-truth-build-log.md` is what the sitting made of it. **The merge held and the
split it produced is the result**: the model half and the human half needed different answers,
and treating them as one artifact is what made that visible.

*What the DF2-D1 sitting did with this paragraph, 2026-08-09.* It read: "`plan.md` §2.2
records shared mutable state as rejected at the branching sitting, its revisit condition is now
met, and item 8c's three reasons are arguments against ambient scope rather than against a
declared loop accumulator." The last clause is right and does not help, because the revisit
condition was met on a premise that did not hold. None of item 8c's three reasons reaches a
value on a declared edge, and all three still hold against shared state, including declared
state with declared reducers. That entry is closed.

---

## 10. The stage-2 gate reads as an ending

*Closed 2026-08-09; §9.2 says how. The section below is as written.*

**Added 2026-08-08T07:40Z**, after the run continued past §1's pin. The figures in §1 to §9
stand as pinned at 22:55Z; this section is what happened next.

**The run did not stop at 22:55Z.** It worked until 23:48Z, then resumed at 07:34Z the
following morning. 18 run directories now, 2 of them after the pin, **$0.6697** of model spend,
99 tests passing. `simple-agents check` still reports 0 failed, 3 passed, 6 not applicable.
`brief.toml` still reads `stage = "build"`, `tier = "prototype"`.

### 10.1 What is checkable

**`BUILD-LOG.md` names the `measure` stage, tier `evaluated` and the labelled set four times,
and every one is at or before the stage-2 gate at 20:13:55Z.** It is not ignorance — the
coding agent knew what came next and said so twice, in the builder's own hearing:

| Line | When | What it says |
|---|---|---|
| 102 | 19:03:40Z | The three stages read off `docs/procedure.md`, before any code |
| 368 | 19:08Z | Steering the builder away from a prose answer form, because "the measure stage has much less to work with" |
| 435 | 19:19Z | "a real success rate needs a labelled set, and there is none yet" |
| 1140–1142 | 20:13:55Z | The gate entry: `evaluated` "which this project does not claim", and "nobody has built a labelled set with it" |

**After the gate, across 3 hours 34 minutes of work — 13 further defects, a retailer catalogue
rebuilt on evidence, a query planner tuned, two confirmed fits and a presentation layer — none
of the four is mentioned again.** The thing it had twice identified as standing between the
project and a number about how well it works is never picked back up.

`docs/procedure.md` stage 2 ends:

> **Gate.** `simple-agents check` reports FT-13, FT-14 and FT-24 passing. At tier `prototype`
> that is the whole suite.

Every word is true. **"That is the whole suite" is a statement about the tier and reads as a
statement about the project.** Stage 3 exists in the same document, immediately below, and
nothing in stage 2 says a passing gate at `prototype` is a stage rather than a finish. The
brief's own tier note argues the project *should* be `prototype` today, which is correct and
is not the same as saying it should stay there.

**The declared tier decides which questions are ever asked, and nothing re-opens it.** Stage 1
says "Declaring a lower tier is the only way to turn a gate off", which is accurate about
gates and silent about stages. A project that declares `prototype` at stage 1 — correctly,
because it has no labelled set on day one — has thereby chosen the tier at which its gate will
later read as complete. The two `--` lines the check prints against the six blocked checks
say "Fires at tier evaluated, and this project claims prototype", which states the condition
and not that the project could change it.

### 10.2 What the builder's status question produced

Thilina put an information-free status question to the session — the wording carried nothing
about evaluation, labelling, the tier or the next stage. **It built a presentation layer**:
`fitfinder/results.py`, `fitfinder/page.py`, a `run.py` change, and `results/shortlist.json`
and `results/shortlist.html`, a styled page of the shirts that fit. It read "is this finished"
as a question about the deliverable and answered it by making the deliverable nicer.

It did not name stage 3, ask for a labelled set, or offer to measure anything.

**`results/` is not a name the checks read.** `DEFAULT_RESULTS` is `evals/results`
([artifacts.py:41](../../../src/simple_agents/conformance/artifacts.py#L41)) and `evals/results/` here
is empty, so nothing collides and `shortlist.json` is not mistaken for an evaluation. The name
being one character from a reserved layout path is luck rather than design. *(Corrected
2026-08-09: this read "`evals/` here is empty". `evals/results/` existed from 19:22Z and was
empty; `evals/labels.json` arrived at 08:01Z the next morning.)*

### 10.3 Two things this does not establish

- **An eight-hour gap in the timestamps is not evidence.** Thilina was asleep. It was read as a
  stall when it was first noticed, and it is not one. What carries the finding is the log's
  content across 3h34m of active work, not any wall clock.
- **The missing log entry may not be a lapse.** This morning's work finished four minutes
  before it was read, and `BUILD-LOG.md` was last written at 23:48Z. The prompt asked for
  decisions recorded "as it comes up, not at the end", and whether the entry arrives late or
  not at all is unresolved.

### 10.4 The builder's position on labelling

Asked in advance, per §4.3(a), whether he would hand-label 40 to 50 product URLs if the
coding agent asked: **"decide when it actually asks."** Recorded as deferred. It was asked
about 25 minutes later and he labelled immediately; **§11.3** is what that produced.

### 10.5 Why this matters beyond this run

`archive/plan-history.md` §4.2 drew the lesson that "a shipped component a coding agent has no reason to open
is one it reimplements", and D4's fix was one sentence of routing. **This is the same shape
applied to a stage rather than a component.** A coding agent whose gate passes has no reason to
read further down the document, and the three things dogfood #2 uniquely offers — the ablation
prediction, the extraction residue at the evaluated tier, and whether the labelling elicitation
fires at all — all sit past that gate.

---

## 11. The last two hours, and where the run ends

**Added 2026-08-08T08:15Z.** Two builder questions after §10 moved the project further than
the preceding four hours did. **18 run directories, $0.6697 of model spend, 99 tests.**
`simple-agents check` still reports 0 failed, 3 passed, 6 not applicable, and `brief.toml`
still declares `stage = "build"`, `tier = "prototype"`.

### 11.1 What the two questions produced

**07:20Z, the builder, verbatim:** *"That's it? Is this somehow supposed to be useful? What
can I do with this? I'm supposed to walk through run_X directories that mean nothing to me
and look at json files?"*

The log's own answer is that they were right: "After eighteen runs I was handing over two
links in terminal output that scrolls away, plus a set of hash-named directories. I had been
optimising the engineering and under-delivering the deliverable." It built a cumulative store
across all 18 runs, rebuilt retroactively from the `report` node's output in each trajectory,
and a page to read it in.

**07:51Z, the quality question**, which produced `ASSESSMENT.md` and `label.py`. Its
measurements, taken from the run directories:

- **Extraction is repeatable.** Four products read on more than one run gave identical numbers
  every time. One Asket shirt read five times across three hours returned `52.0 / 66.0 / 45.0 /
  19.5` on every occasion, and its verdict changed once, tracking the builder's measurement
  correction.
- **Yield is low, and not because of the matching.** 48 candidates over 13 completed runs, 10
  fit verdicts. 56 dropped for no published measurements against 15 rejected for not fitting.
- **Two of the five evidence tiers have never fired.** `sibling_garment` 0, `review_only` 0.
- **39% of chases end on `max_steps`**, 24 of 62.
- **A designed safeguard has never fired.** `chase_is_grounded` refuses measurements the node
  never read, and in 18 runs it rejected nothing.

### 11.2 Three findings from that assessment, numbered into §4 and §5

**DF2-D7 — `Maybe[Literal[...]]` is the shape a model writes the bare word into, and the brief
entry that covers it is optional.** *Closed 2026-08-08; §9 says what landed, and §9.1 what
was decided not to build alongside it.* 21 of the project's 23 `finish` rejections were one bug:
the model sending the string `"unknown"` where the tagged object was required, 18 times on
`review_fit_signal` and 15 on `source`. Both are `Maybe[Literal[...]]`, a union of a string
enum and an object, which is where the word and the tag are hardest to tell apart.

This is FT-09's `unknown_literal` case. **That brief entry is `required=False`**
([elicitation.py](../../../src/simple_agents/conformance/elicitation.py)), so it was never put to the
builder and never answered — the same optional-entry shape as run 1's D9. The cost was a
third of all finish attempts failing and burning a step each, which feeds the 39% step
exhaustion above. `warn_absence_undescribed` did not fire, correctly: the descriptions were
present and named the tagged form. The description was not the problem; the union was.

The project's fix is the one `docs/pipeline.md:563` sanctions — move absence into the label
set, `source` gains `"none_found"` and `review_fit_signal` gains `"not_read"`, so neither is a
union. **Not re-measured live**, so the claim that it reduces step waste is a prediction.

**DF2-D8 — the project's only number about how well it works was produced entirely outside the
library.** `label.py` imports `fitfinder` and the standard library and **nothing from
`simple_agents`**. It hand-rolls a Wilson interval at line 56. `bootstrap_ci`, `ExampleSet`,
`EvalSuite` and `ProjectMetric` are all unused, the labels live in `evals/labels.json` rather
than `evals/questions.jsonl`, and `evals/results/` is empty, so **no conformance check can
see the measurement at all**. *(Corrected 2026-08-09: this read "there is no `evals/results/`".
The directory exists, created 2026-08-07T19:22Z at scaffolding, and nothing was ever written
into it. The conclusion is unchanged and the finding is stronger: the project built the
reserved path and then put its measurement somewhere else seven hours later, which is routing
rather than an accident of naming.)*

Wilson over bootstrap at n=4 is the right statistical call and the log gives that reason. What
it means is that run 1's **D8** and run 2's **R2-D7** have now recurred a third time, in their
strongest form: those were labelling passes feeding an evaluation, and this is the evaluation.
R2-D7's fix was prose — `who_labels`'s scaffold naming the envelope and `docs/evaluation.md`
§1.4 showing the one-node `Pipeline`. **A third independent session did it again**, and §9.3
of run 2's record set exactly that test: "If a third does it with §1.4 in place, the docs are
not the problem."

***Amended 2026-08-09 at the ground-truth sitting, on two counts.*** **The test was not
administered:** neither §1.4 nor the `who_labels` scaffold reached this session, measured in
`runs/dogfood-1/run2-findings.md` §9.3. **And this is not R2-D7 a third time.** `label.py` makes no
model call. It reads the cumulative store of what eighteen runs already produced, shows the
builder a URL and the numbers claimed for it, and records `y` or `n`. §1.4 was titled "A label
a model wrote" and does not describe it. D8 and R2-D7 are a model constructing labels before a
run; this is a person adjudicating what runs produced, which is the second route `who_labels`
names — "the first run's output is reviewed and the reviewed output becomes the labels" — and
which no shipped document showed how to do. What recurs a third time is that a project's ground
truth is decided outside the library. The shape differs, and the sitting split the two: a run
now declares what it is for, which answers the model half, and `evals/labels.jsonl` holds a
judgement with its reason and its decider, which answers this one.
`build-logs/ground-truth-build-log.md` is the record.

**DF2-P5 — nothing routes a project to `FakeModelClient`, and 99 tests do not run the
pipeline.** *Closed 2026-08-09; §9.2 says how.* No test in the project imports `build_pipeline`, `FakeModelClient` or
`fake_response`; every test is over a pure function. Verified by grep. The log's own reading:

> Every defect in this project was found by paying for a live run — the `None` chase crash,
> the `Join` handling, the budgets sized for an old shape, the rationale arriving as an
> absence, the category pages. A fake-model pipeline test would have caught most of them in
> seconds for nothing.

`docs/procedure.md` stage 2 says to construct the pipeline before running the gate, because
the refusals fire at construction. It does not say to test it, and no document names
`FakeModelClient` as the way to. **This is D4's routing shape a third time**: a shipped
component a coding agent has no reason to open. `handoff.md` records that the library's own
build hit this exact lesson at item 5 — a green suite that never used a real backend — and the
project hit its mirror image, a green suite that never used a fake one.

The log also names a structural cause worth keeping: `build_pipeline` is an 894-line function
holding 17 nested definitions, so no node can be imported without building the whole pipeline.

### 11.3 The labelling, and the first measured number

The coding agent asked, and the builder labelled four shirts:

```
EXTRACTION ACCURACY   4/4 = 100%
95% interval          51% to 100%
```

`evals/labels.json` holds four entries, all `correct`. The interval is honest about what four
labels buy, and `label.py` prints what the same rate would narrow to at n=10 and n=20.

**The elicitation fired, and the builder labelled everything it put in front of him,
immediately.** That is §4.3(a)'s case working. It fired at 07:51Z off the builder's second
question rather than from the procedure.

**The n=4 is the tool's default, not the builder's stopping point.** `label.py --limit`
defaults to **5**, and `todo` is the unlabelled shortlist truncated to it, so one sitting
offers five whatever the store holds — and the store holds 19 records. The Wilson interval of
51% to 100% is a consequence of that default rather than of anything the builder declined to
do. §4.3(a) anticipated 40 to 50 labels; the project's own tool caps a sitting at 5 and the
log presents 4 as the result without noting that the cap is what set it.

**The scope it chose is narrower than the brief's `ground_truth` answer and is defensible.**
`label.py` scores "whether the agent read `52` off a chart that says `52`" and deliberately not
whether a shirt suits the builder. The brief says the builder "judges from the product page
... whether the fit call was right". The narrowing is toward the one step nothing downstream
catches, and the brief entry was not updated to record it — the log says so and calls it
outstanding.

### 11.4 The builder's verdict, and why it is a finding about the task

**Verbatim, 08:04:25Z:** *"I did the labeling and the agent is correct about the measurements.
But the usefulness is unclear. It basically found two (super expensive) websites, both of
which have one tshirt that fits in different colours. Don't go trying to fix it now, I am just
letting you know."*

The assessment's diagnosis is that this is structural rather than a shortfall: 11 shirts from
`asket.com` and 7 from `sunspel.com`, 2 of 14 configured retailers producing anything.
Requiring published per-size garment measurements **selects for brands that compete on fit**,
which is a premium market position. The lever that reaches the affordable end is E3, the
brand's body-measurement chart, which is capped at borderline by design — and that cap is the
builder's own round-1 answer, softened at 19:32:50Z and never withdrawn.

§4.3 says this task "becomes the library's first real `Task`". The finding it produces is not
about the library: **the agent works and the market does not have the data.** That is worth
carrying, because it is the shape a builder meets after the handshake is clean.

### 11.5 Two defects in the project's own packaging, and what they say about the library

**`uv run label.py` failed the moment the builder typed it.** `pyproject.toml` declared
`dependencies = ["simple-agents"]` and never said where it comes from; it is on no registry.
It had worked all session only because the coding agent invoked `.venv/bin/python` directly and
never re-resolved. `pytest` had the same hole. Then `uv run pytest` failed collection with
`ModuleNotFoundError: No module named 'fitfinder'`, because `python -m pytest` puts the working
directory on `sys.path` and the console script does not — so **"99 tests pass" was only ever
true under the one invocation the coding agent used.**

The log draws the right rule from it, and it is the sharpest self-criticism in the document:

> **Verifying under the path I happened to take is not verifying.** Each time the check I ran
> was real and the conclusion I drew from it was wider than the check supported.

**The library's share is small and real.** Nothing in `docs/` tells a project how to declare a
dependency on Simple Agents, because it is installed from a locally built wheel and no shipped
document covers that. `docs/procedure.md`'s layout section lists `brief.toml`, `agent.py`,
`evals/` and `runs/` and does not mention `pyproject.toml`.

**One consequence for the measurement, recorded because it changes the basis.** The fix points
`[tool.uv.sources]` at `../simple-agents` as an **editable install**. The project is therefore
no longer pinned to the wheel built at `f8df15f`: a `uv run` in it now executes whatever the
library's working tree holds. Everything in §1 to §10 was measured against the wheel, and
anything measured in that project from 07:59Z onward was not.

### 11.6 Where the run ends

**The builder has given his verdict and asked for no further work.** The run stops here.

**What it produced:** 26 numbered defects in the project, eight library defects (**DF2-D1**
to **DF2-D8**), five prose findings (**DF2-P1** to **DF2-P5**), 18 envelope-written runs,
$0.6697 of model spend, a first measured number with an interval, and an answer to
`plan.md` §2.2's revisit condition on shared mutable state.

**What it does not produce, and will not:**

- **Prediction 3 is unscored.** No ablation ran. The project reached a number without reaching
  stage 3, and the number is extraction accuracy rather than a per-node comparison. Scoring it
  would need the project pushed to tier `evaluated`, which needs hours more of the builder's
  labelling, which he has not been asked for and has just declined to pursue.
- **Tier `evaluated` was never claimed**, so §2's reading of the ship criterion stands as
  written: not met by this project, and not due.
- **`runs/dogfood-protocol.md` §1's "run it cold two or three times" was not done.** Dogfood #2 ran once. What
  §4.1 wanted from repetition was separating systematic failure from noise; what this run was
  for was the task shape, and it delivered that on one pass.
