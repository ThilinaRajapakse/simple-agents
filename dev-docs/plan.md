# Plan

**This is the only queue. Everything agreed to be built is here and nowhere else**, and this file
holds items and nothing else. A rule that governs is in `simple-agents.md`; how we work is in
`CLAUDE.md`; a record is in `items/`, `build-logs/` or `runs/`.

**Where we are.** v0 was met on 2026-08-07, when a coding agent given only the library and its
docs produced a passing agent from a cold start. **`0.1.0` is the first public release**, decided
2026-08-20 at `P3-31`.

**Reorganised 2026-08-15**, out of chapters-by-phase and into items only.
[`archive/plan-history.md`](archive/plan-history.md#L1) maps the old section numbers to where each
one went.

---

## 1. Scheduled

Ordered. **`P3-n` is assigned when an item joins this table, never changes and is never reused**,
and it is what another file cites. **A stage that ships takes its own id**, as `P3-5`'s first two
took `P3-10` and `P3-12`'s first took `P3-13`, because an id is never in §1 and §4 at once. A row
says what the item is, its state, and links its record. Anything that restates a section of that
record belongs in the record, and this section is the header above and the table below.

| Id | Item | State | What it is, and the record |
|---|---|---|---|
| P3-71 | **Working through dogfood #6's findings** | scheduled 2026-09-02; **the sitting was taken the same day** and scheduled `P3-72` to `P3-77`; 19 candidates, 0 open | `lost-the-plot`, a TV Time replacement with a Flutter app, built 2026-09-01 to 02 on PyPI `0.1.1` and `0.1.2`. [`runs/dogfood-6/findings.md`](runs/dogfood-6/findings.md#L1) is the evidence, [`inventory.md`](runs/dogfood-6/inventory.md#L1) §3 the queue. Done when the six are built |
| P3-73 | **An index that grows, on the CPU or the GPU** | scheduled 2026-09-02 at `P3-71`'s sitting | `DocumentIndex.add`, numpy as the default store, FAISS with GPU as an optional extra, a binary save format, and the store on the record. [`items/an-index-that-grows.md`](items/an-index-that-grows.md#L1) |
| P3-74 | **Dogfood #6's runtime fixes** | scheduled 2026-09-02 at `P3-71`'s sitting; the evaluation-isolation half ruled the same day, both halves | The slice terminal, run inputs on `NodeContext`, quota phrases per backend, a failed resume, `nearest_cross_split`, and an evaluation over a pipeline that reads back what it writes. [`items/dogfood-6-runtime-fixes.md`](items/dogfood-6-runtime-fixes.md#L1) |
| P3-75 | **Which pipeline a run is** | scheduled 2026-09-02 at `P3-71`'s sitting | The registered name on the manifest and the results file, the three checks reading within it, FT-42 across roles, scripted runs marked, the view's constants. [`items/which-pipeline-a-run-is.md`](items/which-pipeline-a-run-is.md#L1) |
| P3-76 | **What the procedure reaches** | scheduled 2026-09-02 at `P3-71`'s sitting | Adopted facilities read against the code, `rerun` where resumability is asked for, `not_applicable` re-asked, prompt text with a `prompt_rule`, and the product design section at `ship`. [`items/what-the-procedure-reaches.md`](items/what-the-procedure-reaches.md#L1) |
| P3-77 | **A declared schedule** | scheduled 2026-09-02 out of §2.2 (deferred 2026-08-20), its decider met by dogfood #6; the tick-the-host-calls shape agreed by Thilina the same day, so §2.1 stands as read in the record | A `Schedule` declared beside the pipelines, a `tick()` the host calls, the last runs and fired triggers on disk, and the trigger on the manifest. [`items/a-declared-schedule.md`](items/a-declared-schedule.md#L1) |
| P3-43 | **What an MCP server may ask of the client** | scheduled 2026-08-27 at `P3-38`, **after `P3-31`**: nothing here moves a format a project holds, so it does not have to precede the release. Nothing designed | Our client declares no `elicitation`, `sampling` or `roots` capability, so a server that gates tools on them hides those tools from us. **Measured 2026-08-27**: the reference server offers 13 tools to this library and 16 to a capable client. Each maps onto something the library already owns, and each carries a design question. [`items/what-a-server-may-ask.md`](items/what-a-server-may-ask.md#L1) |
| P3-68 | **A per-edge value** | scheduled 2026-09-01 out of §2.2 (deferred 2026-08-09), behind the release. The deciding arithmetic is named in the record | A node saying what each out-edge carries, weighed against a narrowing `Deterministic` on the edge, on dogfood #2's measured numbers. [`items/per-edge-value.md`](items/per-edge-value.md#L1) |
| P3-69 | **Adapters for OpenAI and Anthropic** | scheduled 2026-09-01 out of §2.2 (deferred 2026-08-05), behind the release. No key for either exists on this machine, and measuring is part of whichever lands first | OpenAI rides `_openai_wire.py`, and `base_url` makes one adapter serve every compatible endpoint; Anthropic needs a sibling wire module. The first exercise of a billed cache-write class. [`items/openai-and-anthropic-adapters.md`](items/openai-and-anthropic-adapters.md#L1) |
| P3-70 | **A payload stored by reference** | scheduled 2026-09-01 out of §2.2 (deferred 2026-08-06), behind the release. The deciding measurement runs on trajectories already on disk | 91.4% of a measured run was one set of results written repeatedly. A reference where the bytes match a payload already written in the run, the full render where they do not. [`items/payload-by-reference.md`](items/payload-by-reference.md#L1) |
| P3-14 | **A judge the library ships** | scheduled 2026-08-18, **nothing designed and the shape undecided** | Every project writes the judging pass itself, and the library ships no worked example of one surviving a model that fails schema validation: ours dropped the failures silently and wasted a live run. It reverses half of `P3-13`'s decision 5, so that rationale has to be defeated in writing. [`items/a-shipped-judge.md`](items/a-shipped-judge.md#L1) |
| P3-2 | **A set of example projects** | reframed 2026-08-12, nothing designed | [`items/example-projects.md` §19.9](items/example-projects.md#L1662) is the decision and the six tasks |
| P3-4 | **The meta-eval of the documentation** | pending; unblocked 2026-08-20 when P3-1 closed | [`items/meta-eval.md`](items/meta-eval.md#L1) |

## 2. Not scheduled

### 2.1 Accepted

Worth doing, no slot yet. Each says what it waits on. An entry here has been agreed; it is not a
candidate.

- **`progress_of` does not read the `progress.json` the runner now writes.** Found 2026-08-29
  building `P3-60`. `progress_of` takes `expected=` from the caller, and the evaluation now
  keeps the declared total, the outcomes scored so far and its own time estimate in
  `progress.json` beside the rollouts. **What it would cost:** one function reading the file
  where it exists, and `expected=` becoming optional. **Waits on:** nothing but a slot.
  [`build-logs/the-measure-page-build-log.md`](build-logs/the-measure-page-build-log.md#L1) §6.
- **`simple-agents report` prints a figure to four decimal places and a node's to six.** Found
  2026-08-28 while verifying `P3-50`. A run costing fractions of a cent reads `at least 0.0000 USD`
  on the headline and `0.000010 USD` in the node column of the same report, and the headline form
  now claims to be a floor while rounding to something that reads as nothing. **What it would
  cost:** one decision about what precision a spend line carries, applied to both, and
  [`docs/run-envelope.md` §8.4](../docs/run-envelope.md#L836)'s example capture reads at the
  current precision. **The precision predates the floor**: a fully-priced run of the same size
  already printed `0.0000 USD`. **Waits on:** nothing but a slot.
  [`build-logs/what-a-run-says-it-cost-build-log.md`](build-logs/what-a-run-says-it-cost-build-log.md#L1) §6.
- **`simple-agents report --json` carries no floor.** Found 2026-08-28 in `P3-52`'s fourth
  reverification cycle. The text report prints, under every figure, what an agent that did
  nothing would have scored, and now also says where the project's own function never saw that
  floor. [`_measurement`](../src/simple_agents/cli/main.py#L391) carries `metrics`, `criteria`,
  `nodes`, `totals` and `outcomes`, and neither the floor nor `baseline_unscored`, so a gate
  reading the JSON cannot ask the question the report answers: whether the agent beat not
  trying. **The gap predates `P3-52`** and that item widened it by one field. Its docstring
  claimed to be "what the text report says" and was corrected on sight to say what it omits.
  **What it would cost:** `baseline_metrics()` and `baseline_unscored` in the returned object,
  and a decision about whether `against_baseline`'s per-figure deltas belong there too, since a
  gate wanting "did it beat doing nothing" wants the paired figure rather than the two points.
  **Waits on:** nothing but a slot.
  [`build-logs/the-do-nothing-floor-build-log.md`](build-logs/the-do-nothing-floor-build-log.md#L1) §6.
- **A `considered = 5` in the brief raises `TypeError` rather than naming what the field takes.**
  Found 2026-08-27 while building `P3-29`, which fixed the same crash on `produces` and on `from`.
  [`decisions_from`](../src/simple_agents/conformance/decisions.py#L307) reads `considered` as
  `tuple(str(item) for item in value.get("considered") or ())`, so any non-iterable raises where
  it is used and a table iterates its keys. **What it would cost:** one guard, and its own message,
  because `considered` holds prose alternatives rather than names and
  [`_a_list_of_names`](../src/simple_agents/conformance/decisions.py#L360)'s text would be wrong
  for it. **Waits on:** nothing but a slot.
- **A shipped comment names one of our own runs.** Accepted 2026-08-25, found while reading the
  code back at `P3-34`. [`artifacts.py`](../src/simple_agents/conformance/artifacts.py#L65)
  opens *"empty outcome is what dogfood #4's four-source table recorded against award
  shortlists"*, which is development history in the source a builder reads, and `CLAUDE.md`
  puts that in this tree rather than in a comment. **Nothing sees it**: `prose_check.py` reads
  references to `dev-docs`, `plan.md`, `handoff.md` and `simple-agents.md` from shipped
  files, and the internal-id rule reads `P3-n` and `DF5-Inn`, so a run named in prose passes
  both. **What it would cost:** one comment rewritten, and a decision about whether the rule is
  worth checking, which turns on whether a second one has appeared since.
  **Two more have appeared, 2026-08-28**, which answers that: `view/record.py` opens *"Measured
  2026-08-28 over `dogfood-5-frozen`"*, written at `P3-52`; and `P3-54` shipped *"dogfood #5 met
  736 of them and reported no article"* into `docs/tools.md` §1.3, a document a builder reads,
  and caught it only while preparing sitting 8. Three instances, none of them seen by anything.
  **Waits on:** nothing but a slot. The rule is a pattern over `dogfood #n` and `dogfood-n` in
  `docs/` and `src/`, and the two comments are one rewrite each.
- **The analyzer in front of BM25 does nothing but lowercase.** Accepted 2026-08-19, raised by
  Thilina at the `docs/retrieval.md` review: *"BM25 should be implemented properly, not this
  half assed whole word match."* **The scoring is not the gap.**
  [`lexical_scores`](../src/simple_agents/builtins/search.py#L421) is textbook BM25, with the
  smoothed Robertson IDF, `K1 = 1.5` and `B = 0.75` and length normalisation against the mean.
  **What does nothing is [`tokens`](../src/simple_agents/builtins/search.py#L93)**, which is
  `[a-z0-9]+` over lowercased text: no stemming, no lemmatisation, no subword fallback. Measured
  2026-08-19 over a two-document index, `"books"` returns only the document saying *books* and
  `"book"` only the one saying *book*, so a plural does not find its singular. `docs/retrieval.md`
  now states that, which is the behaviour and not the intent.
  **What it would cost:** a stemmer, which is a language decision the library has half-made
  already, since `ENGLISH_STOPWORDS` ships as the default. It changes every lexical result, so
  every cassette holding a `document_search` re-records. And
  [`DocumentIndex.save`](../src/simple_agents/builtins/search.py#L306) records which model made
  the vectors and says nothing about how the text was tokenised, so an index file written under
  one analyzer and loaded under another would mix silently, the way two embedding models are
  refused from doing.
  **Waits on:** a decision about whether the index file records the analyzer, since that is the
  same shape as the embedding-model refusal it already has, and nothing should ship a second
  analyzer before a stored index can say which one built it.

- **What elicitation does not ask.** Accepted 2026-09-01 out of Thilina's 2026-08-29 audit,
  findings 1 to 4: the baseline evaluation API, the four kinds of multi-run state, the
  concurrency and pacing settings, and abandoned-run recovery are each documented in their
  reference document and absent from the procedure and elicitation that route a coding agent to
  them. Four design sittings, one per finding.
  [`items/elicitation-gaps.md`](items/elicitation-gaps.md#L1) carries the audit verbatim.
  **Waits on:** `P3-31`, the release, on Thilina's 2026-09-01 ruling that the release does not
  wait on design sittings.
- **A ceiling on how much reaches one model client.** **Promoted from §2.2 on 2026-08-18**,
  having been deferred there since 2026-08-13. Named at the concurrency sitting, where the run
  total and a per-node count were built and this was not, on Thilina's decision. A node declares
  its own model, so `concurrent_items=` bounds what reaches an expensive backend from the node
  that names it, and `Pipeline.run(concurrency=)` bounds the run. **Neither bounds a client shared
  by several nodes that overlap each other**: three nodes at `concurrent_items=2`, all on one
  hosted model, all listed in one group of `concurrent_nodes`, is six calls against that backend
  and nothing refuses it. **What it would cost:** a wrapper the builder has to know exists,
  `PacedClient(client, max_in_flight=2)` or a sibling of it, and a decision about whether a client
  reached without one is bounded by anything but the run total. `_clients_of` already enumerates
  the distinct clients for pacing
  ([runner.py:2846](../src/simple_agents/evaluation/runner.py#L2846), `_clients_of`), so the
  enumeration is not new work.

  **What promoted it is that its own decider was met by a different mechanism.** The entry said it
  waited on *"a project where several nodes share one paid client and overlap. Dogfood #4 has one
  model and will not show it."* [`DF4-D3`](runs/dogfood-4/findings.md#L305) is one node against one
  client: 15 rollouts, 14 of them 429s, `failure_rate` 0.00, and the arm reported the run's highest
  figure. The variable was **rate**. Removing the `look_closer` spin took an evaluation from 25
  minutes to 2, which compressed 102 Gemini calls into a window the free key would not carry.
  `concurrent_items` and `Pipeline.run(concurrency=)` bound calls **in flight**; nothing bounds
  calls **per unit of time**, so whether that is this entry or a sibling of it is the first thing a
  design says.

  **Five instances now.** The three above, and `P3-15`: once an `AgentNode` takes `over=`, one item
  is a loop rather than a call, so `concurrent_items=8` is eight loops and an unknown number of
  calls. *(The second arrived with `P3-12`, 2026-08-18: a judging pass is a model client that
  [`_pace_for`](../src/simple_agents/evaluation/runner.py#L2862) never sees, since it paces
  `_clients_of(self.pipeline, model)` and a judge is in neither. **The third is the same item's
  stage 2**: a consultation's `read=` reader holds its own client, and `_clients_of` walks `llm`
  and `agent` nodes, so a reader on a `Deterministic` node is in neither list. It is the first of
  them a shipped agent carries into production rather than only into an evaluation.)* **The fifth
  arrived with `P3-30`, 2026-08-20**: overlapping `run()` calls, which a product serving requests
  makes routine, and [`expect_callers`](../src/simple_agents/pacing.py#L224) overwrites rather
  than accumulates, so a run starting mid-flight resets the floor the first run paces against and
  N overlapping runs under-pace by a factor of N. A `min_remaining_requests` passed to the
  constructor is not overridden, which is the escape `docs/product.md` states.
  [`build-logs/the-product-build-log.md`](build-logs/the-product-build-log.md#L1) §1.
  **Waits on:** `P3-15`, which changes what `concurrent_items` bounds and owes this entry the
  sentence saying so. Building the ceiling inside that item is not the plan.

### 2.2 Deferred

Not decided whether to own at all. Each names what would decide it. **An entry carries the date it
was deferred**, and `check_docs.py` reports one older than 21 days as due for re-decision.

- *Deferred 2026-09-02.* **The view's answer flow writing the brief through the writer.** Left open by `P3-72`. An answer given on the served page lands as a thread in `comments.toml` and the coding agent records it into the brief afterwards, now through `simple-agents record`. **What it would be:** the page writing the entry itself, stamped, with the thread kept as the record of the exchange. **What would settle it:** whether the coding agent's reading of an answer before it is recorded is worth keeping, which is `docs/view.md` §5's stated reason for the thread; one project where a builder's inline answer was recorded unchanged every time is the evidence for dropping it.
- *Deferred 2026-08-29.* **`research.md`'s section heading is "What this turns on, having
  looked".** Noted while applying [`design/view.md`](design/view.md#L412) decision 29, which struck
  the phrase from the page. The heading is what
  [`artifacts.py`](../src/simple_agents/conformance/artifacts.py#L69) `RESEARCH_SECTIONS` and FT-36 parse, so
  renaming it moves an artifact every project holds and needs a read of both spellings.
  **What would settle it:** the release, since the format is cheapest to move before it.

- *Deferred 2026-08-29.* **An adopted candidate does not become a ghost resource on the
  drawings.** Noted at `P3-55`'s sitting and not built. A candidate is a sentence in
  `research.md`'s survey and a resource on the drawing is a string a tool declares, so joining
  them means guessing which words name a store. **What would settle it:** whether a builder
  reading the `shape` drawing misses the sources the research adopted, which one project taken
  from `research` to `shape` would show. **What it would cost:** either a naming convention the
  survey has to follow, or a match nobody can check.
  [`build-logs/the-view-before-there-is-code-build-log.md`](build-logs/the-view-before-there-is-code-build-log.md#L1) §6.
- *Deferred 2026-08-29.* **A throttle the library waited out leaves no record.** Found
  building `P3-57`. The retry loop sleeps and calls the tool again, so a source that throttles
  a project constantly and recovers every time is invisible: only a call whose attempts are
  spent reaches the record. **What would settle it:** whether an operator needs to see a
  source degrading before it fails, which one shipped project meeting a real rate limit would
  answer. **What it would cost:** a trajectory record for something that did not fail, which
  is a question about what a run's record is for.
  [`build-logs/the-operations-page-build-log.md`](build-logs/the-operations-page-build-log.md#L1) §6.
- *Deferred 2026-08-29.* **FT-32 reads the words of a side-effect class rather than what an
  answer means.** Found building `P3-56`. `measured`'s `tool_effects` answer said "the supplier registry
  costs money per lookup" and the check reported "the answer mentions no effect of that kind",
  because it looks for the words of `spends_money`. The answer describes the effect correctly
  and the failure message overstates what the check read. **What would settle it:** whether a
  builder's own wording should pass, which is a question about how strict the vocabulary of an
  answer has to be, and one dogfood answer written in the builder's words rather than the
  library's is the evidence. **What it would cost:** either a softer match, which weakens the
  check, or a message saying it matched on the class's own words, which is one sentence.
  [`build-logs/the-product-on-the-page-build-log.md`](build-logs/the-product-on-the-page-build-log.md#L1) §6.
- **A retry policy a throttled tool can declare.** *Deferred 2026-08-28.* Owed to this section
  by `P3-54`. **What exists:** a `Throttled` raised by a tool is waited out and called again,
  three attempts from a module constant in `context.py`, honouring a `Retry-After` the source
  sent. **What it misses:** a project that wants more attempts, fewer, or none cannot say so, and
  a tool whose source is slow to recover is given the same ladder as one that is not.
  **What decides whether it is worth owning:** a project that meets a throttle the three
  attempts do not clear, or one where waiting at all is wrong.
  [`build-logs/dogfood-5-fixes-build-log.md`](build-logs/dogfood-5-fixes-build-log.md#L1) §6.
- **A fan-out's own refusals are retried by `retry=`.** *Deferred 2026-08-28.* Owed to this
  section by `P3-54`. **What exists:** both refusals a fan-out raises about itself, the failure
  budget being passed and every item failing the same way, reach the executor's `except Exception`
  like any other node failure, so a declared `RetryPolicy` re-runs the whole fan-out. On a node
  the library has just said is broken for every item, that is a second and third pass of
  definitely-wasted work; dogfood #5's fan-outs were 37 items. **The older refusal has behaved
  this way since it shipped**, so this is consistent rather than new, which is why `P3-54` did not
  change it on its own. **What decides whether it is worth owning:** whether either refusal should
  join `CassetteMiss` and `BudgetExceeded` as a failure a retry does not answer, which is one
  clause and a decision about the older one's shipped behaviour.
- **A throttled `robots.txt` reads as a site with no `robots.txt`.** *Deferred 2026-08-28.* Owed
  to this section by `P3-54`. **What exists:** [`_read_robots`](../src/simple_agents/builtins/http.py#L314)
  returns `None` on any status at or above 400, and the docstring says a site whose robots.txt
  cannot be read is treated as permitting everything, which is what the standard says for a site
  that has none. **What it misses:** a site rate limiting the agent will rate limit that request
  too, so a throttle there is read as permission and the fetch proceeds. Predates `P3-54`, which
  taught the fetch itself to wait out a 429 and left this request alone. **What decides whether it
  is worth owning:** whether a project meets a site whose robots.txt throttles, which is
  observable in a run's `tool_call` records.
- **A client that stops re-paying a retry ladder a previous call proved closed.** *Deferred 2026-08-28.*
  Raised at dogfood #5's sitting 5, where it was proposed as the half that recovers the 28
  minutes `DF5-I24` measured and then dropped because it does not. **What exists after `P3-50`:**
  a 429 whose message matches an observed quota phrase is not retried at all, so the ladder is
  never climbed and all 1,674 of those seconds go. **What this would be:** cross-call state, so
  that after a 429 the ladder failed to clear, later calls through the same client refuse rather
  than climbing it again. **Why it was dropped:** it buys nothing on the only case measured. What
  it would cover is a 429 the library **cannot** classify, from a backend publishing no
  `Retry-After` and no allowance headers, where retrying is right on the first call and wasteful on
  the fiftieth. **And the shipped shape for cross-call policy is a wrapper the project composes**,
  which is what `PacedClient` is, so a project can write this today.
  **What decides whether it is worth owning:** a project that repeatedly meets a 429 the library
  cannot classify, and pays a ladder per call for it. **Re-decided and kept deferred 2026-08-28**
  at sitting 7, where `P3-54` put a second retry ladder in the library on the tool side, so what
  this would hold is cross-call state shared by both. The decider is unmet either way: dogfood
  #5's 736 throttles were a 429 the library **can** classify, since Wikipedia publishes
  `Retry-After`.
  [`build-logs/what-a-run-says-it-cost-build-log.md`](build-logs/what-a-run-says-it-cost-build-log.md#L1).
- **A cap on the manifest's `constants` array.** *Deferred 2026-08-27.* Owed to this section by
  `P3-29`. **What exists:** every module-level number the project's own modules define is written
  into every manifest, and an evaluation writes one per rollout. Measured on dogfood #5: 48
  entries, about 3KB, against a 3.6GB `runs/` directory. **What it would be:** a bound with the
  count of what it dropped, since a silent cap reads as coverage. **What decides whether it is
  worth owning:** a project whose module count makes the array a measurable share of a manifest.
  Nothing has measured one.
  [`build-logs/what-a-decision-produced-build-log.md`](build-logs/what-a-decision-produced-build-log.md#L1).
- **A prompt edited through a module constant moves nothing.** *Deferred 2026-08-27.* Found while verifying `P3-34`. **Measured**, on a two-line module reloaded between two
  readings: editing the module-level string a prompt function interpolates changes what the model
  is sent, and the prompt's recorded `version` and the pipeline's `behaviour_fingerprint` are
  byte-identical before and after. **What that costs:** FT-15 passes, FT-37 stays silent, FT-38
  stays silent, and `confirmed_against` still matches, so the one failure FT-37 exists for, a
  reported number produced by a pipeline the project no longer has, is invisible for this shape of
  edit. [`source_version`](../src/simple_agents/records/manifest.py#L596) hashes a function's source and
  what it closed over, and a module global is neither.
  **Why it is not already closed:** `P3-29`'s decision 4, 2026-08-27, put constants outside the
  fingerprint, and the reason holds for the other 47 of dogfood #5's 48, which are thresholds and
  rate limits that no prompt reads. This one is different in kind: the constant *is* the prompt.
  **Two ways to close it, both with a cost.** Digest the module globals a prompt function reads,
  which is an AST read of its body and reaches only names it names, so a prompt assembled from a
  dict lookup still escapes. Or put the whole `constants` array in the fingerprint, which is what
  decision 4 refused and which would move every stamp on an unrelated edit. **What decides whether
  it is worth owning:** Thilina's call between those two, or a third; a builder has not met this
  yet, and the measurement above is the whole of the evidence.
- **A starting plan that pre-answers elicitation.** *Deferred 2026-08-20.* Raised by Thilina in
  the inbox on 2026-08-18: providing a plan or document as a starting point for a build, which
  may contain all, most, or some of the answers to the questions that are elicited. **What
  exists:** nothing reads a document into the brief; every entry arrives through the coding
  agent asking, and `source` distinguishes the builder's answers from the coding agent's since
  `P3-28`. A builder with a written plan today pastes it into conversation, and what happens to
  it is whatever the coding agent does unprompted. **What it would be:** a documented way to
  start from a plan, with the stages reading answers out of it and asking only what it leaves
  open, each pre-answered entry recording where it came from. **Why it is not in dogfood #5,
  decided 2026-08-20 at that run's setup:** a seeded start pre-answers exactly what the
  research and product stages elicit, and that run is the only cold start `P3-28` and `P3-30`
  will ever get. **What decides whether it is worth owning:** a seeded-start run read against
  dogfood #5's cold start, which that run provides as the baseline arm for free: which
  questions the plan answered, which it answered wrongly with no gate catching it, and what
  the elicitation still had to ask.
  [`runs/dogfood-5/setup.md`](runs/dogfood-5/setup.md#L1).
- **One `Criteria` object shared across examples.** *Deferred 2026-08-17.*
  Owed to this section by P3-5's stage 3. It declares absence for all of them. **What exists:**
  `Criterion(expects_absence=True)` says the right answer to a condition is that the value is
  not there, and silence meets it. The declaration is per example on purpose, so the example
  whose document states the field and the one whose document does not share a registered check.
  **What is left unbuilt** is any protection against a project building one `Criteria` object
  and handing it to every example: the declaration then applies where the value does exist, and
  silence is credited rather than counted as a shortfall. `docs/evaluation.md` §1.6 says to
  declare per example and `content_hash` covers the declaration, so it is visible in the
  artifact. **What it would cost:** object identity is the wrong place to look. The shipped
  layout writes examples to JSONL and each row decodes into its own object, so two examples that
  shared one `Criteria` in memory hold two equal ones by the time anything scores them. Sharing
  is legitimate wherever the field is absent throughout, so a check over the example set has
  nothing to key on either. **What decides whether it is worth
  owning:** whether the scorer's own discarded answer is the signal.
  [`_criteria_verdict`](../src/simple_agents/evaluation/scoring.py#L288) calls the check and then reduces
  it to `met = met is None`, so under an absence declaration a check returning `True` says the
  answer stated a value the check itself judged correct, which is what a declaration written for
  a different example looks like, and every silent rollout on that same example was credited for
  a field that is there. Computing it costs nothing and needs nothing about how the key was
  built. What is left to decide is whether it is reported at all, and whether it is a warning or
  a `ConfigurationError`.
  [`build-logs/per-field-absence-build-log.md`](build-logs/per-field-absence-build-log.md#L328)
  §6.
- **A check that a link inside `dev-docs` names a file that exists.** *Deferred 2026-08-17.*
  Deferred on Thilina's decision that the backlog is not worth taking on now. **What exists:**
  `check_citations.py` reads a citation's anchor, whether it lands on a blank line, and whether
  the symbol named beside it has drifted. `check_docs.py` reads this tree's own conventions.
  **Neither asks whether a relative path resolves to a file**, which is how five links broke
  silently when `answer-shapes.md` moved from `items/` to `design/` and both checks reported
  clean. **What it would cost: measured 2026-08-20, and the backlog is not what this
  entry recorded.** `dev-docs/` holds 3,476 relative links and 2,444 of them do not resolve,
  which is the "thousands" above. **2,413 are in `runs/full-test-2026-08-13/`, they are 29
  distinct paths, and every one of the 2,413 resolves by adding a single `../`**: those files
  sit one directory deeper than their links assume, and each names a document in `docs/`. That
  is one substitution per depth. **Overtaken 2026-08-26**: `P3-31`'s scan pass at `2b774e8` deleted part of
  `runs/full-test-2026-08-13/docs-test/`, so the 2,413 and the 2,444 are both stale and the
  measurement is due again before this is decided. **Thirty-one are in the whole of the rest of the tree.** Four
  name a file that exists nowhere in the repository, which is a dogfood project's `agent.py`
  outside it. Seven are repository-relative paths to `docs/` or `src/` written from a file that
  is not at the root, which is the failure `CLAUDE.md` records for 2026-08-10. The other twenty
  name a file the repository does have at a different path: the wrong `../` depth, or an
  `items/` file that moved when its item was built. **What decides whether it is worth owning:**
  whether a link that can never resolve is allowed to exist. Four point outside the repository
  by design, so a rule has to give them a way to say so, and that is the only design question
  here: an ignore list, a marker beside the link, or a rule scoped to paths that stay inside the
  repository. The rest is one substitution and thirty-one edits.
  [`build-logs/per-field-absence-build-log.md`](build-logs/per-field-absence-build-log.md#L328)
  §6.
- **A scoring rule whose input is an example's rollouts together.** *Deferred 2026-08-28.* Owed
  to this section by `P3-48`. **What exists:** `ProjectMetric.score` is given one `Scoring`, so a
  rule cannot compare an example's k rollouts. G2, agreement across the agent's own rollouts, was
  the shape that wanted this and **it came out expressible without it**: the k rollouts of one
  example are pairs, so `paired_figure` computes it with the example as the resampling unit and no
  label anywhere. **What is left unbuilt** is the general form, a rule handed the group. **What it
  would cost:** a second `score` signature, or a declaration saying which of the two a figure
  takes, and a decision about what `over` means when the unit is the example rather than the
  rollout. **What decides whether it is worth owning:** a figure a project wants that the pair
  form cannot express. G2 was the one instance anybody named and it no longer needs this.
  [`build-logs/a-figure-that-is-not-a-mean-build-log.md`](build-logs/a-figure-that-is-not-a-mean-build-log.md#L1) §6.
- **A graded `AnyOf`.** *Deferred 2026-08-28.* Owed to this section by `P3-48`, whose decider pass
  measured it. **What exists:** B2, several right answers not worth the same, is expressible as a
  `Criteria` list: measured 2026-08-28, a two-criterion key grades "Kirkwall" 0.5 against
  "Kirkwall Retail Ltd" and reports `partially_correct`. **What is not expressible** is grading the
  alternatives of an `AnyOf` directly. Measured the same day: `AnyOf(["Kirkwall", "Kirkwall Retail
  Ltd"])` scored the half-right answer `correct` with grade 1.0, because `AnyOf` is a membership
  test. **What it would cost:** a weight per alternative and `Verdict`'s arithmetic over it, which
  is the same change [`§2.2`](plan.md#L331)'s negative-weights entry asks for from the other side,
  so the two should be taken together or not at all. **What decides whether it is worth owning:**
  whether a project finds the two-criterion encoding worse than a weighted list, which is a
  question about authoring rather than about what can be measured.
  [`build-logs/a-figure-that-is-not-a-mean-build-log.md`](build-logs/a-figure-that-is-not-a-mean-build-log.md#L1) §6.
- **Negative weights, and a criterion that penalises.** *Deferred 2026-08-17.* Owed to this
  section by `P3-10` and approved at the `P3-11` sitting. **What exists:** weights are positive,
  and a condition the answer must not meet is written as a criterion whose check returns true when
  the thing is absent. `required` already makes one unmet condition sink an answer that met
  everything else, as `false_confidence` carrying its grade. **What is left unbuilt** is the
  penalty between those two, where a violation costs more than the condition is worth without
  being fatal, and a per-example score that can go negative. That is HealthBench's −10 to 10 form,
  with the denominator `Σ max(0, p)`. **What it would cost:** `Verdict`'s arithmetic, the
  denominator, and a decision about whether `graded_accuracy` may be negative for one example.
  **What decides whether it is worth owning:** two readings, both on paper, and the
  first is done here. **Whether the positive encoding the library already prescribes is
  faithful: it is not.** [`Criterion`](../src/simple_agents/evaluation/answer_key.py#L193)
  refuses a weight at or below
  zero and its error tells the author to write the condition as a check returning true when the
  thing is absent. Under `grade = weight_met / weight_declared` that criterion adds its own
  weight to the denominator, so the violation costs exactly what the condition is worth, and
  decoupling those two is the whole of what this entry asks for. The workaround cannot express
  it. **What a negative grade means to every figure reading it is the part still open.**
  [`Verdict.empty`](../src/simple_agents/evaluation/scoring.py#L191) is `grade <= 0.0` and reads
  as the answer having met none of the key, so an answer meeting most conditions and tripping
  one penalty would report as having met nothing. Listing the figures the grade feeds and saying
  what each of them means below zero is the decision, and every one of them is on disk.
  [`build-logs/answer-key-build-log.md`](build-logs/answer-key-build-log.md#L310) §6 is where it
  was raised.
- **A criteria set declared once and referenced.** *Deferred 2026-08-17.* Named at the `P3-11`
  sitting, owed to this section by `P3-10`. An example carries its own `Criteria([...])`, so
  conditions shared across rows are written once per row into the JSONL. **The duplication is in
  the artifact and not in the authoring, measured 2026-08-17:** `evals/questions.jsonl` is the
  example set the shipped layout names, and every project that built one generated that file with
  a script, dogfood #3's computing its shared 30-title label once and writing it into all 24 rows.
  What it costs is the file's size and a diff that cannot show what changed, since editing one
  condition rewrites every row carrying it. **What a design has to solve:** once an example names
  a set instead of carrying it, the criterion text leaves `expected` and so leaves `content_hash`,
  and [`_rules`](../src/simple_agents/evaluation/compare.py#L696) compares each check's `version`
  alone and never the text it records beside it, so widening a condition would move every rate with
  nothing recording it. That is [`design/answer-shapes.md` S3.6](design/answer-shapes.md#L410)'s
  tolerance finding in a fourth place, fixable by comparing the text as well and only inside the
  design. *(Half of that is taken by `P3-12`, decided 2026-08-18: `_rules` compares a condition's
  text where the condition is **judged**, since the text is the instruction handed to the model.
  The coded half stays here, because there the text is documentation and the check is the rule, so
  comparing it would withhold a verdict over a typo.*
  [`archive/a-recorded-judgement.md`](archive/a-recorded-judgement.md#L1)*.)*
  **What decides whether it is worth owning:** whether the reference reaches the
  hash at all. [`content_hash`](../src/simple_agents/evaluation/examples.py#L518) is computed in
  memory over each example's `to_json()`, so a design that resolves the reference before
  encoding keeps every criterion's text inside the hash and the loss described above does not
  happen, while a design that stores the reference unresolved gives it up. That is a decision
  about one encoder and it can be taken now. What survives either way is
  [`_decider`](../src/simple_agents/evaluation/compare.py#L780), which returns a coded check's
  `version` and never the text recorded beside it. So the second question is whether a coded
  condition's text belongs in the comparison at all, given that `content_hash` already withholds
  a verdict when the text moves and the reference form is what would stop it. Answering that
  closes the tolerance finding's fourth instance without the reference existing.
- **Turning trajectories off, and storing them so they cannot be read.** *Deferred 2026-08-15.*
  Raised by Thilina. Two questions in one: whether there is a mechanism to disable trajectory
  recording at any point and whether it should stay on in production, and whether encryption or
  hashing helps, storing trajectories and cassettes in a form that does not expose sensitive data
  while verification and perhaps evaluation still work. **What exists today:** `Trajectory.keeps`
  decides per run whether payloads and the cassette are kept, and boundary redaction removes
  declared secrets and known credential formats before anything is written. Neither is an off
  switch, and neither protects a file already on disk. **What it would cost:** an encrypted
  trajectory has to stay readable by the conformance checks, per-node metrics and `runs()`, so the
  key has to reach every reader, which is key management the library would then own. **What
  decides whether it is worth owning:** what is left on disk when a project keeps nothing.
  [`Trajectory.sampled`](../src/simple_agents/records/trajectory.py#L704) at `0.0` keeps no payloads at
  all, and counts, timings, tokens, seeds and cost stay complete at every rate, so the residue
  is the run's shape: node ids, prompt ids, tool names, and whatever a redaction rule did not
  know to remove. Reading one trajectory written at `0.0` says whether that residue is
  sensitive, and it is ten minutes against a run already on disk. If it is not, the two
  questions separate: the off switch exists and is called `sampled(0.0)`, what is missing is a
  sentence in `docs/` saying so, and encryption is then about payloads a project can already
  decline to keep. If it is, the entry has a scope nobody has written down, and that scope is
  what a design starts from.

- **An evaluation over a tool that cannot be undone.** *Deferred 2026-08-15.* Named 2026-08-15 at the `ship` sitting, on
  Thilina's objection: *"Evaluation shouldn't refuse an irreversible tool. What it should do is
  make sure everything is in place to handle what an irreversible tool will do."*
  `simple-agents.md` §9 item 5 and FT-20 refuse a rollout over an `irreversible` tool and offer
  record-then-replay instead, so the effect happens once rather than `examples × k` times:
  [`runner.py`, `_refuse_unsafe_tools`](../src/simple_agents/evaluation/runner.py#L2129) returns
  immediately when the cassette is replaying, and the refusal message names that path. **Three
  things the refusal does not do.** The recording pass performs the action for real and nothing
  says what should be in place first. A replayed rollout is served the recorded result, so a call
  whose arguments the recording never covered is a cassette miss rather than an effect, which
  makes the behaviour most worth measuring the one replay structurally cannot reach. And one
  class covers effects needing different handling: an email to a customer, a deleted row, a
  placed order. **What it would cost:** the survey first, which is the common kinds of
  irreversible tool, what each does, and what "in place" means for each — a sandbox target, a dry
  run, an idempotency key, a consultation before the call, a cap per run — and then a mechanism,
  which is more than the class flag carries. **What decides whether it is worth owning:** the
  survey, which is reading rather than waiting. For each kind of irreversible effect, say
  whether what has to be in place is something the library can carry in a declaration or is
  configuration only the project holds. If every one is the project's, what is owed is an
  elicitation question and a page in `docs/`, decidable now against a mechanism nobody has to
  build; if any is the library's, the survey names it and the entry has a scope. **The second of
  the three defects separates and settles on its own**: a replayed rollout cannot reach a call
  the recording never covered, so whether the refusal message should say that the path it offers
  omits the behaviour most worth measuring is one edit. **It moves `simple-agents.md` §9 item 5 only by defeating that entry's rationale in
  writing.** [`build-logs/ship-stage-build-log.md`](build-logs/ship-stage-build-log.md#L1) §5.1 is where it was raised, with the
  correction to what was put to him.
- **A supervisor for suspended runs.** *Deferred 2026-08-04, re-decided and kept 2026-08-26.* Committed to a discussion rather than to a design, 2026-08-04 at the item 8d sitting. A loop that reads a run directory, finds the suspensions whose `resume_not_before` has passed, and resumes them. `Pipeline.suspensions(run_dir)` publishes exactly what such a loop reads, so a project writes it in about five lines today; what the library would be adding is the operations around it, which is a store other than the local filesystem and a guarantee that two workers never resume one run. **What 8d must not foreclose, and does not:** all suspension state goes through one narrow read/write pair, so a store seam later replaces two functions rather than being threaded through the executor; and a resume claims its suspension by an atomic rename before running it, so two workers reading one directory cannot both resume a run and both write into the same trajectory. **What decides whether it is worth owning** is whether a run can name what rebuilds it. A resume needs three things and only one of them is hard. [`resume`](../src/simple_agents/pipeline/core.py#L659) takes `envelope=` and `model=`, and a resume already compares both against what the run recorded, so the manifest holds enough to say when they differ and whether it holds enough to rebuild them is the smaller half of one reading. The pipeline is the half that is not: a manifest records the graph's shape and never the callables inside its nodes. So this is one question, and it is whether a project registers its pipeline factory under a name the run records, which is a registry the library would own and a name in the manifest. Answer it and the entry is decided either way, with no supervisor built and no store chosen; answer it no and [`Pipeline.suspensions`](../src/simple_agents/pipeline/core.py#L950) is the whole seam. **Re-decided and kept 2026-08-26, and the one question is answered:** `P3-35` built [`registry.py`](../src/simple_agents/registry.py#L37) `pipeline_factory` the same day, so a project registers each pipeline under a name and `simple-agents view` finds and introspects them without running anything ([`design/view.md`](design/view.md#L1)). The registry exists with a second customer; recording the name in the manifest at run time, the non-filesystem store and the two-workers guarantee are what is left to decide here.


    **What the Gemini build measured against this entry, 2026-08-12.** Two claims fell. **Google does serve the OpenAI dialect**, so "neither speaks that dialect" is wrong on the premise; the conclusion held for reasons nobody had measured, since that endpoint refuses `seed`, itemises no thinking tokens while billing them, returns no chain of thought, and refuses the turn after a tool call whose signature `messages_to_wire` drops. **And a third priced hosted backend was not the first exercise of `input_cache_write`**: this one reports no write count and bills cache storage per token-hour, so that class is `unknown` on every call and the five-field breakdown is still short a number from anywhere. What it did exercise is the honest-`unknown` path, and a cost rule that had never been reached: an unmeasured count at a rate declared `0.0` prices exactly. `Reasoning.blocks` is also still filled by nothing, because this backend's opaque state belongs to the tool call rather than to the chain of thought.

    **`P3-17` closes one thing this entry would otherwise walk into**, scheduled 2026-08-18.
    `messages_to_wire`, which both planned adapters would build on, discards
    `ToolCallRequest.provider` without saying so, and §7 of the shipped document points an adapter
    author straight at it. That is the failure dogfood #4 measured as 102 of 102 node executions
    lost, on a backend whose state the library now carries correctly by its native path.

    **What decides whether it is worth owning**, one answer for each adapter. **OpenAI: whether
    it can be built without a key at all.** `_openai_wire.py` already speaks the dialect and a
    `base_url` points it at the vLLM server on this machine, so everything except
    authentication, that provider's usage-block field names and its error shape is exercisable
    here for nothing. Naming those three off the published SDK is a reading, and what it
    produces is either an adapter that ships unverified against the hosted endpoint or a short
    list of exactly what a key would buy. **Anthropic: the cost of a key against what only it
    produces.** Two things in the library have never been filled by anything: `input_cache_write`
    has never carried a count from any backend, and `Reasoning.blocks` has never held a value.
    This is the backend that bills a cache write separately and returns a signed thinking block,
    so pricing the smallest run that fills both fields gives a number, and that number is the
    decision.

## 3. Out of scope

Not now. **This list means out for now rather than out forever**, on Thilina's ruling of
2026-08-10, when long-term memory came off it and was built.

- **Training, RL, the improvement ladder, and Tinker/SkyRL/OpenEnv backends.** These are the parts
  most likely to be redesigned by what dogfooding teaches, and "just the training backend" is how
  this project dies.
- **MCP tasks.** *Declined 2026-08-27, at `P3-38`, on the evidence below rather than on a
  preference.* A task is a `tools/call` that returns a handle the client polls, added at protocol
  revision `2025-11-25`. **Four findings, each measured that day.** The protocol **removed them at
  `2026-07-28`**: every task type in `mcp_types` is annotated *"2025-11-25 only"* and
  `Tool.execution` says *"removed in 2026-07-28"*. What replaced them is a stateless retry, an
  `InputRequiredResult` the client fulfils and retries. **The TypeScript SDK ships them under
  `experimental/`.** **The Python SDK carries no client-side support**: grepping the installed
  `mcp` for `TaskMetadata|tasks/get|CreateTaskResult` hits only `mcp/server/extension.py`, and
  `ClientSession.call_tool` has no `task=` parameter, so supporting them means hand-rolling a
  removed revision over `send_request`. **And nothing uses them**: across `everything`,
  `filesystem`, `memory` and `sequentialthinking`, 36 of 37 tools declare
  `execution.taskSupport: forbidden`, the exception being `simulate-research-query` on the server
  whose purpose is demonstrating every feature. **What happens today, and it is the safe
  failure:** a tool declaring `required` returns
  `MCP error -32601: requires task augmentation` as `isError: true`, which
  [`mcp.py` `MCPServer.call`](../src/simple_agents/mcp.py#L442) raises as `ModelFacingError`, so an
  `AgentNode`'s model is told and gets a turn. **What would reverse this:** a server worth
  connecting to that declares `required`, which is one row of the survey above run again.
  **What this is not:** the three client capabilities are a separate thing that outlived tasks and
  are scheduled as `P3-43`.
- **Browser tooling, and sandboxed code execution.**
- **Anything multi-agent.** May follow memory off this list.
- **A DSL.** *Amended 2026-08-03 at the branching sitting*: "a graph engine or DSL" was one entry
  and is now one. `Pipeline` became a directed graph at item 8c, with the argument in
  [`simple-agents.md` §2.2](simple-agents.md#L91). The graph is declared in Python on the node.
- **Distributed and durable execution across machines.** A run would have to be placed onto a
  machine that does not hold the caller's process, which means the library owning a store, a work
  queue, leases and crash recovery, and it would still need the caller's `Pipeline`, envelope and
  model client to execute anything once it got there. Item 8d's suspend and resume covers the case
  this library actually has, which is a run waiting on a person or a clock.

## 4. Done

Newest first. **One line each: what shipped, what it cost, and a link to the build log**, and
`check_docs.py` fails an entry over 450 characters, link targets aside. What an item found is its
build log's job.
- **The brief writer** (P3-72), 2026-09-02, out of `DF6-I09`. `simple-agents record answer` and `record decision` write one table of `brief.toml` stamped from the clock and leave the rest byte for byte, and `record set`, `confirmed`, `read-against` and `shape` cover the keys above the tables; FT-44 fails a stamp ahead of the clock. Twenty-seven checks, 44 taxonomy entries; no format moved; 4,165 tests. [`build-logs/the-brief-writer-build-log.md`](build-logs/the-brief-writer-build-log.md#L1)
- **Going public** (P3-31), 2026-09-02. `0.1.0` to `0.1.2` on PyPI as `simple-llm-agents` by trusted publishing off a `v*` tag, the public repository from the scanned tree with this one kept as the archive, the scan gated in CI, and dogfood #6 installed from it cold. No format moved; 4,134 tests. [`build-logs/going-public-build-log.md`](build-logs/going-public-build-log.md#L1)
- **The undocumented APIs** (P3-67), 2026-09-01. `OpenAIReranker` and the fakes into `docs/retrieval.md`, re-pricing as `docs/run-envelope.md` §4.5, `answer_shelved`'s return in `docs/product.md`; the §4.5 example is executed by a test, which failed its first two drafts. 4,115 tests. [`build-logs/the-undocumented-apis-build-log.md`](build-logs/the-undocumented-apis-build-log.md#L1)
- **The feature index** (P3-66), 2026-09-01. The skill, `docs/procedure.md`, gained thirteen lines naming every capability the library ships; `WORD_BUDGET` to 3,800. **Closes `P3-3`**: the post-review read found twenty-plus stale `runs/<eval_id>/` path shapes, all corrected. 4,114 tests. [`build-logs/the-feature-index-build-log.md`](build-logs/the-feature-index-build-log.md#L1)
- **The builder quickstart** (P3-65), 2026-09-01. `README.md`'s Quick start became the builder's walkthrough: install, then a four-step map through the staged build, the first-agent example, `simple-agents view` and measuring, each step pointing at the README's own sections. Ruled mid-build to live in the README, so no twentieth document ships. No code changed; 4,114 tests. [`build-logs/the-builder-quickstart-build-log.md`](build-logs/the-builder-quickstart-build-log.md#L1)
- **Working the ratchet down** (P3-64), 2026-08-31. The lint and format gates at zero tolerance, four record-machinery rules, and eight sittings over the recorded units: three modules split out of the runner, six duplications shared, a `parent_id` defect fixed, and all 141 keeps reasoned in the baseline, held by the suite. Live Gemini runs; 4,102 tests. [`build-logs/ratchet-down-build-log.md`](build-logs/ratchet-down-build-log.md#L1)
- **The pre-release refactor** (P3-63), 2026-08-31. `nodes.py` and `pipeline.py` became `nodes/`, `pipeline/` and a new `runtime/`; the preflight validators and manifest writer left the `Pipeline` class; `records/` holds the seven versioned on-disk formats; the recorded graph is read one way. Public surface unchanged, citations retargeted, live Gemini and vLLM runs. No format moves; 4,084 tests. [`build-logs/pre-release-refactor-build-log.md`](build-logs/pre-release-refactor-build-log.md#L1)
- **The view before there is code** (P3-55), 2026-08-29. The `brainstorm` page (the idea as five boxes, dashed where nobody has answered; every question in four states; the six stages with answered-of-asked; `idea.md` read back with one click to confirm it) and the `research` page (the deciding factor, the survey by part, the decisions resting on it). No format moves; 4,072 tests. [`build-logs/the-view-before-there-is-code-build-log.md`](build-logs/the-view-before-there-is-code-build-log.md#L1)
- **The operations page** (P3-57), 2026-08-29. A seventh page, shown once a project has live runs: what is running, waiting, abandoned or shelved; a bar a day with what it cost; the conversations and the behaviour changes; and the run record split by what each run was for. Six records that existed on disk and nothing read. No format moves; 4,045 tests. [`build-logs/the-operations-page-build-log.md`](build-logs/the-operations-page-build-log.md#L1)
- **The product on the page** (P3-56), 2026-08-29. `Product`, `Surface` and `product_factory` declare what the end user meets, and the `ship` page draws it beside the checks as a board, retention and the brief against the code. FT-34 reads the declaration against `design.md`; loading a project twice now finds what a module beside `agent.py` registers. No format moves; 4,029 tests. [`build-logs/the-product-on-the-page-build-log.md`](build-logs/the-product-on-the-page-build-log.md#L1)
- **The build page** (P3-62), 2026-08-29. Progress per step, every number and prompt the runs carry against the decision that names it, the departures with both ways out, and the last run as a strip. It found `tool_effects` counting no `WRITES` tool. No format moves; 3,999 tests. [`build-logs/the-build-page-build-log.md`](build-logs/the-build-page-build-log.md#L1)
- **The shape page** (P3-61), 2026-08-29. The `shape` page redrawn around its own question: the story beside the drawing, the seams the stage settles, the shared state, and agreement in one click. No format moves; 3,990 tests. [`build-logs/the-shape-page-build-log.md`](build-logs/the-shape-page-build-log.md#L1)
- **The measure page, as a visualisation (`P3-60`, reopened)**, 2026-08-29. The page rebuilt as a grid of drawings against a new 30-example fixture, `measured`, recorded live for ~0.10 USD. [`build-logs/the-measure-page-as-a-visualisation-build-log.md`](build-logs/the-measure-page-as-a-visualisation-build-log.md#L1)
[`archive/plan-history.md`](archive/plan-history.md#L1) holds the longer entries this section
carried until 2026-08-15 under "Phase 3 as run", and the paragraphs it carried until 2026-08-29
under "The §4 Done entries".

- **Working through dogfood #5's findings** (P3-32), 2026-08-28. 40 candidates over eight sittings, every one disposed of: `P3-33`, `P3-34`, `P3-36`, `P3-37`, `P3-44` to `P3-48`, `P3-50` and `P3-52` to `P3-54` built out of them, and `DF5-X1` to `DF5-X21` corrected on sight. [`runs/dogfood-5/inventory.md`](runs/dogfood-5/inventory.md#L1) holds every disposition.
- **The results visualiser, and the fixtures it draws against** (P3-51), 2026-08-29, built as `P3-58` and `P3-59`; its third stage, the measure page, shipped the same day and is reopened in §1 as built and not done. Design of record at [`design/results-visualiser.md`](design/results-visualiser.md#L1).
- **The stage-page shell** (P3-59), 2026-08-28. `view.html` holds a page per stage, the page set derived from the tier and every section filed on one stage's page; `/record/<run>/<sequence>` serves the full record behind a walked step. No format moved; 3,933 tests. [`build-logs/the-stage-page-shell-build-log.md`](build-logs/the-stage-page-shell-build-log.md#L1)
- **The view fixtures, and what keeps them current** (P3-58), 2026-08-28. `scripts/build_view_fixtures.py` re-records the three runs-holding view fixtures live and verifies the committed cassettes offline, and `tests/test_view_fixtures.py` fails on format drift. No format moved; 3,923 tests. [`build-logs/the-view-fixtures-build-log.md`](build-logs/the-view-fixtures-build-log.md#L1)
- **Four surfaces that read as working** (P3-54), 2026-08-28, dogfood #5's sitting 7, `DF5-I32` to `DF5-I35`. A fan-out raises where every item failed the same way, a configuration error inside an item ends the run, a `Maybe` field is always told how to send an absence, and `Throttled` waits out a throttled source. No format moved; the `graph` Mistral arm retired for `graph-gemini`; 3,911 tests. [`build-logs/dogfood-5-fixes-build-log.md`](build-logs/dogfood-5-fixes-build-log.md#L1)
- **Evaluating back to front** (P3-53), 2026-08-28. `Pipeline.slice(start=, end=, nodes=)` returns part of a graph as a real `Pipeline`, `ExampleSet.entering` builds what a rung runs on, and a rollout that leaves the slice is out of every figure under `left_the_slice`. Manifest `0.39`, results file `0.29`. [`build-logs/evaluating-back-to-front-build-log.md`](build-logs/evaluating-back-to-front-build-log.md#L1)
- **The floor a do-nothing agent sets** (P3-52), 2026-08-28, closing `DF5-I27`. A `baseline=` returning `None` is refused, the baseline is asked once per example before the first rollout, and the floor is over the examples that ran. Results file `0.28`; 3,800 tests. [`build-logs/the-do-nothing-floor-build-log.md`](build-logs/the-do-nothing-floor-build-log.md#L1)
- **What a run says it cost, and what it says it is doing** (P3-50), 2026-08-28. `Cost` carries `measured`, `priced_calls` and `unpriced_calls`; a 429 that will not reset inside the retry window raises `Suspend`; `RunHandle.liveness`; `Pipeline.rerun` replays a dead run from its cassette. Trajectory `0.29`, manifest `0.38`, results file `0.27`; 3,749 tests. [`build-logs/what-a-run-says-it-cost-build-log.md`](build-logs/what-a-run-says-it-cost-build-log.md#L1)
- **A figure that is not a mean over examples, and a win rate** (P3-48), 2026-08-28. `ProjectRatio` reports one total over another, `Pair` and `paired_figure` do the same over judged pairs, and `Metric.denominator` is renamed `population`. Results file `0.26`, variant comparison `0.3`; 3,701 tests. [`build-logs/a-figure-that-is-not-a-mean-build-log.md`](build-logs/a-figure-that-is-not-a-mean-build-log.md#L1)
- **Which conversation a run is a turn of is `conversation_id`** (P3-49), 2026-08-28. `thread=` on `run()` renamed, the classes unchanged. Manifest `0.37`, conversation `0.2`; 3,622 tests. [`build-logs/what-a-store-is-for-build-log.md` §6](build-logs/what-a-store-is-for-build-log.md#L1)
- **When a decision was made** (P3-47), 2026-08-27. `recorded_at` on every answered brief entry and every decision. The brief format moves: a brief without it is refused when read. 3,607 tests. [`build-logs/when-a-decision-was-made-build-log.md`](build-logs/when-a-decision-was-made-build-log.md#L1)
- **Absence declared where it is enforced** (P3-46), 2026-08-27. FT-04's waiver narrows to the node producing the scored answer, read out of the recorded graph. No format moved; 3,599 tests. [`build-logs/absence-declared-where-it-is-enforced-build-log.md`](build-logs/absence-declared-where-it-is-enforced-build-log.md#L1)
- **What a stored result is stamped with** (P3-45), 2026-08-27. The consultation channel leaves `behaviour_fingerprint` and stays on the cassette key and the resume comparison. Every stamp moves once; 3,595 tests. [`build-logs/what-a-stored-result-is-stamped-with-build-log.md`](build-logs/what-a-stored-result-is-stamped-with-build-log.md#L1)
- **What a store is for, and the two lifetimes on the memory store** (P3-44), 2026-08-27, `DF5-I20` and `DF5-I21`. `MemoryStore(directory)` on the envelope, `memory_scope=` on `run`, `resume` and `answer_shelved`, and `ScopedMemory` for one end user's memory. No format moved; 3,591 tests. [`build-logs/what-a-store-is-for-build-log.md`](build-logs/what-a-store-is-for-build-log.md#L1)
- **A conversation that outlives the run** (P3-39), 2026-08-27. A conversation carried across runs, a node continuing it, compaction as a built-in, and an evaluation over what was said or the turns a rollout goes through; runs filed by what they are. Manifest `0.36`, conversation `0.1`, `docs/conversation.md` new; 3,582 tests. [`build-logs/a-conversation-that-outlives-the-run-build-log.md`](build-logs/a-conversation-that-outlives-the-run-build-log.md#L1)
- **Connecting to an MCP server** (P3-38), 2026-08-27. The `mcp` SDK as an optional extra, both transports, tools declared in Python, and a replay reading schemas from the cassette. Manifest `0.34`, `FT-43` new. [`build-logs/an-mcp-server-build-log.md`](build-logs/an-mcp-server-build-log.md#L1)
- **What a decision produced** (P3-29), 2026-08-27. `produces` on a `dependency`, `shape`, `constant` or `prompt_rule` decision, and FT-42 reads it against every run under `runs/`. Manifest `0.33`; 3487 tests. [`build-logs/what-a-decision-produced-build-log.md`](build-logs/what-a-decision-produced-build-log.md#L1)
- **The build is a conversation** (P3-37), 2026-08-27, dogfood #5's sitting 3. The rule for how a question is put sits where questions are composed, five `ask` strings are rewritten, and FT-41 reads a run that stopped to ask and was never continued. 3415 tests. [`build-logs/the-build-is-a-conversation-build-log.md`](build-logs/the-build-is-a-conversation-build-log.md#L1)
- **Refining the view** (P3-42), 2026-08-28. A project at `shape` is viewable, FT-40 reads `agent.py`, the page's script runs under `node` in the suite, and a readability audit set floors of 11px, 4.5:1 for text and 3:1 for a line. No format moved; 3398 tests. [`build-logs/refining-the-view-build-log.md`](build-logs/refining-the-view-build-log.md#L1)
- **What the picture cannot say** (P3-41), 2026-08-28. A node records what its own code did to a store (`ctx.record_access`, `touches=`), every run is read for cost, traversal and access, a run walks step by step, and `shape_confirmed` dates the agreed picture. Trajectory `0.28`, results `0.25`; 3,308 tests. [`build-logs/what-the-picture-cannot-say-build-log.md`](build-logs/what-the-picture-cannot-say-build-log.md#L1)
- **The data in the view** (P3-40), 2026-08-27. The view says what each step is handed and how much moved, carries the reported evaluation figure by figure, the brief checked against the code, and what moved between the last two runs. The two view prototypes deleted; 3,230 tests. [`build-logs/the-data-in-the-view-build-log.md`](build-logs/the-data-in-the-view-build-log.md#L1)
- **The common language** (P3-35), 2026-08-26, `DF5-I22`. `simple-agents view` writes one builder-facing page of the project as it stands, `--serve` makes it live with comments both ways, `comments.toml`, FT-39, FT-40 and `@pipeline_factory`. Manifest `0.32`; 3,186 tests. [`build-logs/the-common-language-build-log.md`](build-logs/the-common-language-build-log.md#L1)
- **What an agent may do alone** (P3-36), 2026-08-26, `DF5-I14` and `DF5-I15`. `NodeInput` fills a tool with the node's own input, hidden from the model, and `anything_else` is a required question put again at every stage. No format moved; 3132 tests. [`build-logs/what-an-agent-may-do-alone-build-log.md`](build-logs/what-an-agent-may-do-alone-build-log.md#L1)
- **What the checks read** (P3-34), 2026-08-25, dogfood #5's sitting 2. FT-37 fails a reported number from a pipeline the project no longer has, FT-38 a brief nobody re-read against the code, and the results file records `behaviour_fingerprint`. Results file `0.24`; 3086 tests. [`build-logs/what-the-checks-read-build-log.md`](build-logs/what-the-checks-read-build-log.md#L1)
- **Consultation met a product** (P3-33), 2026-08-25, dogfood #5's sitting 1. A channel may return `Shelved` and an answer filed later starts its own run, a consultation takes an identity, and an evaluation is refused over a channel that reaches a person. Trajectory `0.27`, shelf `0.1`, the channel contract broken across 77 definitions. [`build-logs/consultation-met-a-product-build-log.md`](build-logs/consultation-met-a-product-build-log.md#L1)
- **The product** (P3-30), 2026-08-20, dogfood #4's sitting 7. `docs/product.md` is new, `used_through` is required at brainstorm, `design.md` gains the product section and FT-34 reads it, and `HostPolicy` binds per run. The brief and `design.md` move for every project on disk; 2933 tests. [`build-logs/the-product-build-log.md`](build-logs/the-product-build-log.md#L1)
- **Dogfood #4 worked through** (P3-1), 2026-08-20. 41 candidates over seven sittings: 36 built as `P3-6` to `P3-9` and `P3-15` to `P3-28`, 3 declined, and sitting 7's two scheduled. [`runs/dogfood-4/inventory.md`](runs/dogfood-4/inventory.md#L1) §3 holds every disposition.
- **The research stage** (P3-28), 2026-08-20, dogfood #4's sitting 6. A sixth stage between `brainstorm` and `shape`: five questions, `research.md`, FT-36, `source` on a brief entry, and `ExampleSet.nearest_cross_split(n=)`. The brief's shape moved and every project past `research` gains six keys; 2927 tests. [`build-logs/research-stage-build-log.md`](build-logs/research-stage-build-log.md#L1)
- **What a figure is reported against** (P3-27), 2026-08-20, dogfood #4's sitting 5. Any figure grouped by a property of the example, `Metric.rollout_noise`, `EvalSuite(baseline=...)`, and `asserted` reading the verdict. Results file `0.23`; 2880 tests. [`build-logs/what-a-figure-is-reported-against-build-log.md`](build-logs/what-a-figure-is-reported-against-build-log.md#L1)
- **A gate on a loop that spent its budget without acting** (P3-26), 2026-08-19. FT-35 reads the `unfinished` block of every run the pipeline as it now stands has made, and `allow_unfinished=True` waives it. Manifest `0.31`, results file `0.22`; 2831 tests. [`build-logs/unfinished-work-build-log.md` §3.7](build-logs/unfinished-work-build-log.md#L1)
- **What every run did, without writing code** (P3-25), 2026-08-19. `simple-agents report <path>` over runs, an evaluation or a results file, with `basis_from_manifest` and `runs(since=, last=)`. No format moved; 2817 tests. [`build-logs/unfinished-work-build-log.md` §3.6](build-logs/unfinished-work-build-log.md#L1)
- **What a rate is over, and what leaves it** (P3-24), 2026-08-19. A rollout is inside a denominator when what it returned is attributable to the agent, so an unanswered consultation and an unreached item leave every rate. Results file `0.20`; 2750 tests. [`build-logs/unfinished-work-build-log.md`](build-logs/unfinished-work-build-log.md#L1)
- **What a run spent and produced nothing with** (P3-23), 2026-08-19. Four figures per node for an execution that stopped on a budget axis, `node_metrics(run_dir)`, and each manifest carrying its own. Trajectory `0.26`, manifest `0.30`, results file `0.19`; 2741 tests. [`build-logs/unfinished-work-build-log.md`](build-logs/unfinished-work-build-log.md#L1)
- **A version is taken when the thing is declared, and FT-15 has a check** (P3-21), 2026-08-19. Versions are taken at declaration, for tools as well, and `ft_15` is registered. The Mistral `tools` arm retired; no format moved; 2713 tests. [`build-logs/a-version-when-it-is-declared-build-log.md`](build-logs/a-version-when-it-is-declared-build-log.md#L1)
- **What an evaluation is filed under, and what the prompts show** (P3-20), 2026-08-19, dogfood #4's sitting 3. `Deterministic` records and declares a version, a declared version keeps the source hash, and `prompt_differences()` reads prompts out of trajectories. Manifest `0.29` and every evaluation directory renamed; 2711 tests. [`build-logs/evaluation-identity-build-log.md`](build-logs/evaluation-identity-build-log.md#L1)
- **Progress a builder can see** (P3-19), 2026-08-18, dogfood #4's sitting 2. `ProgressBar`, `NodeEvent.item_total` and `simple-agents watch`. `tqdm` is a new dependency; 2682 tests. [`build-logs/progress-display-build-log.md`](build-logs/progress-display-build-log.md#L1)
- **What `behaviour_fingerprint` leaves out** (P3-18), 2026-08-18, dogfood #4's sitting 2. The stamp takes `model=`, covers every tool's version and a consultation reader, and refuses a stamp it knows is partial. Manifest `0.28`, 134 fixtures regenerated; 2670 tests. [`build-logs/what-the-stamp-covers-build-log.md`](build-logs/what-the-stamp-covers-build-log.md#L1)
- **An adapter's backend state, and the helper that drops it** (P3-17), 2026-08-18, dogfood #4's sitting 2. Gemini's thought signature rides on `ToolCallRequest.provider`, and `messages_to_wire` refuses a call carrying state it cannot express. No format moved; 2663 tests. [`build-logs/adapter-backend-state-build-log.md`](build-logs/adapter-backend-state-build-log.md#L1)
- **The two defects in the fan-out mechanism** (P3-16), 2026-08-18, dogfood #4's sitting 1. `RolloutOutcome.unreached_items` counts the items that died on a call the backend never answered, and `NodeEvent` gains an `item` phase. Results file `0.18`; 2659 tests. [`build-logs/fan-out-defects-build-log.md`](build-logs/fan-out-defects-build-log.md#L1)
- **`over=` on every node kind, and tools on `LLMNode`** (P3-15), 2026-08-18, dogfood #4's sitting 1. `over=`, `keep=`, `max_failures=` and `concurrent_items=` on all three kinds, `budget_per_item=` on a fanned-out `AgentNode`, `LLMNode(tools=)`, and a stopped fan-out keeps what each item held. Trajectory `0.25`, manifest `0.27`, suspension `0.5`; 2650 tests. [`build-logs/fan-out-and-node-shape-build-log.md`](build-logs/fan-out-and-node-shape-build-log.md#L1)
- **A judgement the scoring code did not compute** (P3-12), 2026-08-18, the run-time stage. `consult(read=ModelReader(model=cheap))` reads a prose answer into the option meant, live and on resume, recorded as a `model_call` and served from the cassette on replay. Trajectory `0.24`, fourteen fixtures regenerated; 2614 tests. [`build-logs/consultation-reading-build-log.md`](build-logs/consultation-reading-build-log.md#L1)
- **A judgement the scoring code did not compute** (P3-13), 2026-08-18, the scoring-time stage. `Judged()` and `Scoring.judgement(question, over=...)`, a judging pass through `suite.judge`, `run(judge=)` and `compare_variants(judge=)`, `evals/judgements.jsonl` as the store, and `UnjudgedAnswers` gating the numbers. Results file `0.17`; 2571 tests. [`build-logs/recorded-judgement-build-log.md`](build-logs/recorded-judgement-build-log.md#L1)
- **What a correct answer can be** (P3-5), 2026-08-17, built as `P3-10` and per-field absence under this id. A criterion's check may return `Unknown`, and `Criterion(expects_absence=True)` is what FT-04 reads. Results file `0.16`, `content_hash` moves for any set carrying criteria; 2528 tests. [`build-logs/per-field-absence-build-log.md`](build-logs/per-field-absence-build-log.md#L1), survey at [`design/answer-shapes.md`](design/answer-shapes.md#L1)
- **The end user an evaluation answers with** (P3-9), 2026-08-17. `EndUser` carries a `Fact` per thing they know, with `disclose` of `volunteer`, `on_ask` or `hidden`; `instructions=` replaces the prompt; `consult(reaches=)`. `example.end_user` is an `EndUser` after construction; trajectory `0.23`, manifest `0.26`, results file `0.15`; 2403 tests. [`build-logs/end-user-in-an-evaluation-build-log.md`](build-logs/end-user-in-an-evaluation-build-log.md#L1)
- **What elicitation asks about the answer** (P3-11), 2026-08-17. `answer_form` is the answer key question, `ground_truth` asks which answers are acceptable, and `judged_steps` and `judged_path` are new; a project on disk fails FT-24 until it answers the two. No format moved; 2361 tests. [`build-logs/eliciting-the-answer-shape-build-log.md`](build-logs/eliciting-the-answer-shape-build-log.md#L1)
- **An answer key that says what it is** (P3-10), 2026-08-17. Four answer keys in the `expected` position, `Criteria`, `Outcome.PARTIALLY_CORRECT`, eight rates, and one `Scoring` at every scoring seam, which breaks `matches(predicted, expected)` and `score(predicted, expected, rollout)` for every project on disk. Results file `0.14`; 2348 tests. [`build-logs/answer-key-build-log.md`](build-logs/answer-key-build-log.md#L1)
- **The design the builder agreed to** (P3-8), 2026-08-16. `design.md` at stage `shape`, FT-34 reads it, and a `shape` or `presentation` decision records `from`. No format moved; 2276 tests. [`build-logs/agreed-design-build-log.md`](build-logs/agreed-design-build-log.md#L1)
- **The brief against the code** (P3-7), 2026-08-16. FT-25 registered, FT-32 reads `tool_effects` against the manifest's tools, FT-33 reads a build log that stopped before the runs did, and `confirmed_against` in the brief. No format moved; 2262 tests. [`build-logs/brief-against-code-build-log.md`](build-logs/brief-against-code-build-log.md#L1)
- **What the end user sees** (P3-6), 2026-08-16. `Pipeline.behaviour_fingerprint()` stamps a stored result and the manifest records it, `stored_output` is a required `ship` question, and `docs/shipping.md` §6 is new. Manifest `0.25`; 2241 tests. [`build-logs/end-user-artifact-build-log.md`](build-logs/end-user-artifact-build-log.md#L1)
- **The `ship` stage**, 2026-08-15. A fifth stage after `measure`, the tier deciding which stages a project has, `RunEnvelope(live=True)`, FT-31 and `docs/shipping.md`. Manifest `0.24`; 2230 tests. [`build-logs/ship-stage-build-log.md`](build-logs/ship-stage-build-log.md#L1)
- **Dogfood #4's cheap fixes**, 2026-08-15. Four surfaces that read as working and were not, plus a check that a package `__init__` exports what it imports. No format moved; 2193 tests. [`build-logs/dogfood-4-fixes-build-log.md`](build-logs/dogfood-4-fixes-build-log.md#L1)
- **Consultation: who answers, and what the record says**, 2026-08-15. A channel declares `answered_by`, `Unavailable(reason=...)` and `unattended()`, `RunEnvelope(end_user=...)` and `EvalSuite.run(end_user=SimulatedEndUser(model=...))`. Trajectory `0.22`, manifest `0.23`, results file `0.13`; 2176 tests. [`build-logs/consultation-build-log.md`](build-logs/consultation-build-log.md#L1)
- **The full-test QA pass**, 2026-08-13, run outside this queue against `2f4db4c`. Five blockers and every other finding fixed. Results file `0.12`, manifest `0.22`. [`build-logs/full-test-checkpoint-build-log.md`](build-logs/full-test-checkpoint-build-log.md#L1)
- **Concurrency: independent branches, and a fan-out that runs together**, 2026-08-13. `concurrent_nodes`, `concurrent_items` and `concurrent_tools` under `Pipeline.run(concurrency=N)`; drain on stop, `max_wall_clock_ms` becomes elapsed, `DeviceBasis`, and a suspended run becomes a tree. Suspension `0.4`; 1879 tests. [`build-logs/concurrency-build-log.md`](build-logs/concurrency-build-log.md#L1)
- **A consultation answer the library can read**, 2026-08-12. `consult` returns a `Reply`, `on_reply` routes on it with a required branch for an unmatched answer. Trajectory `0.21`, manifest `0.21`; 1827 tests. [`build-logs/typed-consultation-build-log.md`](build-logs/typed-consultation-build-log.md#L1)
- **A Gemini adapter**, 2026-08-12. [`build-logs/gemini-adapter-build-log.md`](build-logs/gemini-adapter-build-log.md#L1)
- **A design decision the coding agent proposes rather than makes**, 2026-08-11. Six decision kinds, `[decisions]` in the brief, FT-30, and three elicitation questions. 1737 tests. [`build-logs/decision-surface-build-log.md`](build-logs/decision-surface-build-log.md#L1)
- **The dogfood #3 fixes, and an evaluation that can be watched and re-entered**, 2026-08-11. `DF3-D2`, `D4` to `D7` and `P1`, plus `EvalSuite.run(resume_from=...)`, `on_rollout=` and `progress_of()`. Results file `0.10`; 1721 tests. [`build-logs/dogfood-3-fixes-build-log.md`](build-logs/dogfood-3-fixes-build-log.md#L1)
- **Dogfood #3's findings record**, 2026-08-11. Ten findings over the book-recommendation task. [`runs/dogfood-3/findings.md`](runs/dogfood-3/findings.md#L1)
- **Semantic recall**, 2026-08-11. `DocumentIndex(embeddings=)`, `memory_search(embeddings=)` and `docs/retrieval.md`. 1683 tests. [`build-logs/semantic-recall-build-log.md`](build-logs/semantic-recall-build-log.md#L1)
- **A run records by default**, 2026-08-11. `RunEnvelope.cassette` defaults to `Cassette.into_run()`. Manifest `0.20`; 1635 tests. [`build-logs/recording-default-build-log.md`](build-logs/recording-default-build-log.md#L1)
- **Scoring rollouts that already ran**, 2026-08-10. A raising project metric cancels the rest, and `EvalSuite.rescore(run_dir=...)` scores what is on disk. Results file `0.9`; 1619 tests. [`build-logs/rescore-build-log.md`](build-logs/rescore-build-log.md#L1)
- **Evaluating an agent that spends money**, 2026-08-10. `EvalSuite.run(max_spend=...)` and `EvalSuite.record(...)`. Do-not-change #5 moved; results file `0.8`; 1595 tests. [`build-logs/paid-eval-build-log.md`](build-logs/paid-eval-build-log.md#L1)
- **Memory**, 2026-08-10. `RunEnvelope(memory=MemoryStore(directory, scope=...))`, reached through recorded tool calls. Manifest `0.19`; 1574 tests. [`build-logs/memory-build-log.md`](build-logs/memory-build-log.md#L1)
- **A pipeline exposed to a model as a tool**, 2026-08-10. `AgentNode(delegates=[Delegation(...)])`. Trajectory `0.19`, suspension `0.3`; 1544 tests. [`build-logs/pipeline-as-tool-build-log.md`](build-logs/pipeline-as-tool-build-log.md#L1)
- **`ablate()` on a pipeline it did not generate**, 2026-08-10. Ten defects with one cause, a container read only for its leaves. Manifest `0.18`, results file `0.7`; 1503 tests. [`build-logs/ablate-build-log.md`](build-logs/ablate-build-log.md#L1)
- **Per-node model selection**, 2026-08-10. `LLMNode(model=)` and `AgentNode(model=)`, resolving node-first then run. Manifest `0.17`. [`build-logs/per-node-model-build-log.md`](build-logs/per-node-model-build-log.md#L1)
- **The `brainstorm` stage and FT-29**, 2026-08-10. A fourth stage before `shape`, eleven questions of which six are required, and `idea.md`. [`design/brainstorm-stage.md`](design/brainstorm-stage.md#L1)
- **The three sittings**, 2026-08-09. DF2-D2 measured tool spend, DF2-D1 the loop accumulator, and the ground-truth sitting the labelling machinery with DF2-D8. [`build-logs/tool-spend-build-log.md`](build-logs/tool-spend-build-log.md#L1), [`build-logs/loop-accumulator-build-log.md`](build-logs/loop-accumulator-build-log.md#L1) and [`build-logs/ground-truth-build-log.md`](build-logs/ground-truth-build-log.md#L1)
- **Nine absorption build items**, 2026-08-09, with `load_env` dropped as outside the library. [`archive/dogfood-absorption.md`](archive/dogfood-absorption.md#L1) carries the dispositions; the builds are [`build-logs/absorption-item1-build-log.md`](build-logs/absorption-item1-build-log.md#L1), [`-item2-`](build-logs/absorption-item2-build-log.md#L1), [`-item3-`](build-logs/absorption-item3-build-log.md#L1), [`-items4-7-`](build-logs/absorption-items4-7-build-log.md#L1) and [`-items8-9-`](build-logs/absorption-items8-9-build-log.md#L1)
- **Ten library-analysis fixes**, 2026-08-08. [`archive/library-analysis-2026-08-08.md`](archive/library-analysis-2026-08-08.md#L1)
- **Five prose findings, DF2-D6 and the §10 protocol amendment**, 2026-08-09. [`runs/dogfood-2/findings.md`](runs/dogfood-2/findings.md#L1) §9.2 says how each closed.
