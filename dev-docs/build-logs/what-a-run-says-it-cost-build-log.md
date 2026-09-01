# Build log — what a run says it cost, and what it says it is doing

`plan.md` §1 `P3-50`. Started and finished 2026-08-28. Written while building.

## 1. Before any design

Everything the sitting rested on was measured on dogfood #5's frozen copy or against the code as
it stood, before anything was decided.

- **The four cost surfaces disagreed, and each was read.**
  `evals/results/eval_b7c83906be49.json` `totals.cost` held `value: null` with `measured: null`
  and `unpriced_nodes: ["judge_candidates", "survey_pool"]`. `simple-agents report`, run against
  that directory, printed `3.9744 USD, 11 run(s) whose cost could not be measured`.
  [`view/runs_overlay.py` `_cost_of`](../../src/simple_agents/view/runs_overlay.py#L384) returned
  `0.0, "", False` for an unpriced run, and
  [`findings.py` `_one_step_costs_most`](../../src/simple_agents/view/findings.py#L992) reads
  those zeros. Pricing all 994 calls individually with `cost_of` came to **$5.5024** over 940 of
  them, which is the same figure the 24 rollout manifests' `charged_cost` sum to.
- **Two adders, opposite policies, both correct for their own purpose.**
  [`Cost.plus`](../../src/simple_agents/cost.py#L187) makes a total unknown where one input is;
  [`Spend.plus`](../../src/simple_agents/budget.py#L82) skips an unmeasured cost and keeps
  counting. Only the first reaches a reader.
- **`measured` already existed and failed on granularity.**
  [`totals_of`](../../src/simple_agents/evaluation/results.py#L861) sums per node, and this
  project's two model-calling nodes were both hit.
- **The 429s were counted, not assumed.** All 54 recorded `held_back_ms` of exactly 31,000, which
  is the bare 1+2+4+8+16 ladder, so no `Retry-After` was present on any. A live probe of Gemini
  the same day returned 200 and **no rate-limit headers of any kind**, confirming `PacedClient` is
  a passthrough for that backend and the message was the only signal.
- **[`_wait`](../../src/simple_agents/adapters/_http.py#L319) capped nothing**, by a decision
  stated in [`Retry`](../../src/simple_agents/adapters/_http.py#L83)'s own docstring.
- **All 13 killed runs declared a wall clock**, 3,600,000 ms or 900,000 ms, so their own bound
  dates every one. The trajectory's last record covers 8 of the 13.
- **A run recorded nothing about what it was given.** `node_execution.inputs` lands when the node
  ends; `run_20260821T042437Z_d9f02b83` holds 37 `model_call` records and zero `node_execution`.
  The manifest holds seed, cassette path, budget, cost basis and model configuration, and no
  inputs. [`SuspensionState`](../../src/simple_agents/records/suspension.py#L51) holds `inputs`.
- **Sized before choosing a home for them**: over 400 runs, a run's inputs are a median 31,886
  bytes against a mean whole manifest of 9,733, p90 168,513, max 500,007; as a share of the
  trajectory they are a median 4.2%, p90 18.5%.

## 2. Design

`items/what-a-run-says-it-cost.md` carried the eight decisions and left `items/` when this log was
written. What it said stands; this section records only what the sitting rejected and why, and the
one argument that changed.

**Rejected on the cost figure:** summing the rollout manifests in the results file alone, which
returns $3.9744 and leaves three surfaces disagreeing; and printing `charged_cost` in the cost
slot, which conflates model spend with tool spend where
[`docs/run-envelope.md` §4.3](../../docs/run-envelope.md#L595) separates them.

**Rejected on the 429:** refusing to retry any 429 from a backend that publishes no headers, which
is Gemini's per-minute case too. **And dropped at the sitting:** a cross-call circuit breaker,
proposed as the half that recovers the 28 minutes and then measured to recover none of them, since
not retrying removes all 1,674 seconds by itself. It is [`plan.md` §2.2](../plan.md#L212).

**Rejected on liveness:** a heartbeat rewritten into the manifest, which turns "written at start
and rewritten at end" into a continuous write for a state that can be derived; and pid plus boot
id, which is wrong on another machine, in a container and after a reboot.

**The argument for recording the run's inputs was made twice from the wrong evidence.** The first
was that three of dogfood #5's four inputs-missing runs were its most expensive to redo; the
second was that only 14 unfinished runs exist across four dogfoods and 6,141 runs. Thilina
rejected both as designing for the dogfood, in both directions. What decided it is the record's
own completeness, and it is in
[`design/trajectory-format-changelog.md` `0.29`](../design/trajectory-format-changelog.md#L18).

## 3. Build

**Three formats moved**: trajectory `0.28` to `0.29`, manifest `0.37` to `0.38`, results file
`0.26` to `0.27`. **3,749 tests**, from 3,701 at the start.

**The cost floor.** `Cost` gains `measured`, `priced_calls` and `unpriced_calls`, accumulated per
call by `cost_of` and summed by `plus`, with `to_record`/`from_record` so one definition serves the
manifest and the results file. `totals_of` reads them off the figure instead of recomputing by
node. `report` sums the floor where a run has one and says `at least`; the view's `_cost_of` reads
`measured` where `value` is absent, and both view cards say how many calls are missing.

**Three things the build found that the design did not know.**

1. **Removing the synthetic identity from `total_cost` lost the declared basis kind.** The old zero
   carried `_basis_kind(basis)` and `plus` preferred it, so a per-model basis reported `by_model`;
   summing real calls alone reported whichever kind came first. The kind is now stamped on the
   result, which is what the field means.
2. **A run under a device basis that made no model call reported `0.0` with no unit.** 676 of
   dogfood #5's runs are that shape. `currencies_in` excludes device time deliberately, so the
   zero had nothing to name itself in while a run with one call said `device_seconds`. `_unit_of`
   fixes it at the source, and `report` gained the same reading for manifests written before it.
3. **A manifest written before the field made `report` print `0 call(s) in 11 run(s) could not be
   priced`.** The old wording is kept where the call count is unknown.

**The refusal.** `QUOTA_PHRASES` holds the one phrase that was observed, matched by
`_is_spent_quota` on the precedent `OVERFLOW_PHRASES` set. `_stop_if_spent` runs in both request
paths and raises `Suspend` carrying the backend's message, with `resume_not_before` unset.
`Retry-After` is capped at `max_backoff_s`. **A second phrase was written from memory and removed**
when `prose_check` caught its second person: the module's own convention is observed phrases only,
and an unmeasured one had no business there.

**Liveness.** `RunHandle.liveness` and `last_activity_at`, derived because a killed process writes
nothing. `report`'s outcome line, the conformance coverage sentence and `progress_of` all read it.

**The record.** `run_start`, a seventh record type carrying `inputs` and `seed`, written before the
first node. `RECORD_TYPES` and `PAYLOAD_FIELDS` were the whole of the wiring: the manifest's
counters and `conformance/checks.py` both read off `RecordType`, and each carries a comment saying
they do so for exactly this. `Pipeline.rerun` reads it and replays the dead run's cassette.

**Two units were recorded over the shape baseline**, both one branch: `unfinished_across` and
`progress_of`, each for counting one more state. Everything else the item touched came out smaller,
and `Cost.plus` left the baseline entirely.

## 4. Verification

**Seven reverification cycles.** A cycle is: read the docs, read the code, cross-verify the two,
test the pieces, run the suite, run live. Cycles 1, 2, 4 and 6 found defects, 3 found a coverage
gap, and **5 and 7 found nothing new**.

| Found | Cycle | What it was |
|---|---|---|
| `rerun` replayed nothing | 1 | The default envelope carries a *default recording* rather than `OFF`, so the dead run's cassette was never wired. **The feature was inert and a probe over a `Deterministic` pipeline could not see it**, because it made no calls. |
| The grace scaled with the budget | 1 | A 4× multiplier gave a run declaring four hours sixteen hours of slack. What a run can overshoot by is one call, so it is a fixed margin now. Found by killing a real run. |
| `unfinished_across` still said "still running" | 1 | Two counting sites; only the nothing-finished one had been changed. Found by checking a sentence I had already written into `docs/run-envelope.md` §8.3. |
| `progress_of` conflated the two | 1 | Its own docstring had named the ambiguity since it was written. |
| A call-less device run had no unit | 2 | §3 above. |
| `rerun(seed=)` raised `TypeError` | 2 | `run` takes `seed=` too. An explicit seed now overrides. |
| The view's cost lines had no test | 3 | In either direction, before or after. `tests/test_view_runs.py` now drives both through the page's own script. |
| A non-run directory raised `OSError` | 4 | `FileNotFoundError` with no guidance, for the likeliest mistake a caller makes here. |
| A doubled directory replayed the **first** run | 4 | One directory used twice appends into one trajectory. The last `run_start` wins now. |
| The silence path needed `started_at` | 6 | The trajectory dates itself, so a manifest whose start cannot be read is still answerable. |
| The documented `report` example predated the field | 6 | Kept as a real capture, with the current form stated beside it. |

**Live, against real backends.**

- **Gemini `gemini-3.1-flash-lite`**, a priced call end to end: manifest `0.38`, trajectory `0.29`,
  `measured == value`, `priced_calls: 1`, `run_start` first carrying the inputs and seed, and the
  key absent from everything the run wrote.
- **vLLM `Qwen/Qwen3-1.7B`** on port 8001 under a compute basis: a run that died after paying for a
  model call, then `rerun` from its directory alone — 1 cassette hit, 0 misses, **0.00 s**, and the
  answer the dead run had computed. The 1.7B model degenerated into whitespace until decoding was
  constrained, which is what the schema refusal itself recommends.
- **A process actually `SIGKILL`ed** mid-run against vLLM. It read `running` while inside its own
  hour-long bound, which is the honest answer and the limit of the reading; past the bound it read
  `abandoned` with `last_activity_at` set. It was then rerun from nothing but its directory in
  **3 ms**, replaying its model call.
- **A live mixed run**, one priced call and one to a dead port: `value: null`, `measured` set,
  `priced_calls: 1`, `unpriced_calls: 1`, and `report` printing the floor and the missing call.
- **An evaluation over 9 rollouts** where every third response reported no usage: the results file
  carried `measured: 6.0, priced_calls: 6, unpriced_calls: 3`, and the report printed
  `at least 6.0000 USD, and 3 of 9 call(s) in say could not be priced` — **the exact defect this
  item started from, on a fresh evaluation**.
- **An evaluation meeting a spent allowance stopped at the first refusal**, 3 requests rather than
  6 rollouts' worth, leaving `suspension.json`. **And a suspended run resumed** once the allowance
  returned: `outcome: completed`, `resumed_at` set, and the floor accumulated across the
  suspension from 1 priced call to 2.
- **An `AgentNode` loop** meeting the same refusal suspended inside the loop with the node named.
- **8 rollouts at `concurrency=4`** each wrote exactly one `run_start`, first in its own file.
- **Redaction** reaches the new record: a secret in the run's inputs is replaced and named in
  `redactions`, and does not appear anywhere the run wrote.
- **`simple-agents check`** on `tests/fixtures/projects/conforming` at the new formats: 0 failed,
  23 passed, 3 not applicable.
- **`compare()`** across two results files at `0.27`.
- The documented `docs/pipeline.md` §1.13 loop was executed against a killed run and produced its
  output.

### Reverifying what dogfood #5 has landed

Four cycles across everything built from this run (`P3-29`, `P3-33` to `P3-39`, `P3-44` to
`P3-50`), on Thilina's instruction, after this item's own seven. **Cycle D found nothing new.**

- **The claims earlier items shipped still hold at the new formats**, checked against a live
  vLLM run: `conversation.id` (`P3-49`), `behaviour_fingerprint` and `role` (`P3-34`), the
  fingerprint stable across two runs of one pipeline (`P3-45`), `constants` (`P3-29`), `memory`
  (`P3-44`) and the `mcp` block (`P3-38`).
- **Every fixture project still fails exactly its one intended check**, and `conforming` and
  `prototype` still pass everything.
- **The view reads a project written at `0.29` and `0.38`**, ignoring the record type it does not
  name, which is how the walk is written.
- **A `§n` reference into a document with no numbered sections passed silently.** One shipped
  pointer was wrong because of it (`DF5-X15`), and the rule that should have caught it had a hole
  that has been closed with a fixture on both sides.
- **A test passed or failed on whether `GEMINI_API_KEY` was exported** (`DF5-X17`). The suite is
  now the same with both keys set, with neither, under `TZ=Pacific/Kiritimati` and
  `TZ=Pacific/Niue`, and run from outside the repository.
- **The view's fixtures are behind and nothing keeps them current.** `tests/fixtures/projects/` is
  generated and guarded and all 18 are current; `tests/fixtures/view_projects/` has neither and
  sits at manifest `0.32` against `0.38`. Deferred overnight, then ruled a gap by Thilina and
  folded into [`plan.md` §1](../plan.md#L30) `P3-51`, which works on the viewer anyway. The
  measurement and the one design question it leaves are in
  [`design/results-visualiser.md`](../design/results-visualiser.md#L1).

## 5. Doc consequences

- **`docs/trajectory-format.md`**: §1.2 is seven record types, §1.3 is the new one. It went in §1.3
  rather than as a section of its own because a new `## 3` would have renumbered four sections
  behind about 130 citations, some of which name a section with the document implied.
- **`docs/run-envelope.md`**: §4.2 gains the floor and its example; the `runs()` field table gains
  `liveness` and `last_activity_at`; **§8.3 is new** and §8.2 became §8.4, which moved two
  citations. §4.3's example gains `measured`.
- **`docs/pipeline.md` §1.13** is new: `rerun`, and the three things it is honest about.
- **`docs/model-clients.md` §4** gains the `Retry-After` cap and the refusal that raises `Suspend`,
  with the measurement behind it. The wrapper pattern stays, as what a project uses for a quota the
  backend does not announce.
- **`docs/conformance.md`** now says an abandoned run is counted apart from one still executing.
- **Counts corrected in five files**: `six record types` became seven in `README.md`,
  `docs/index.md`, `docs/conformance.md`, `docs/failure-taxonomy.md` and `docs/trajectory-format.md`.
- **`CHANGELOG.md`** carries the three format moves and the two behaviour changes.
  `design/trajectory-format-changelog.md` carries `0.29` and its table row.

**A shipped statement that stopped being true:** `docs/run-envelope.md` §8's `outcome` row read
"`None` on a run still executing, or on one whose process ended before it wrote its outcome",
which named the ambiguity and left it. `DF5-X1` had already corrected that row once on sight; this
is the mechanism it was waiting for.

## 6. Left open

- **A report prints `at least 0.0000 USD` where the floor rounds to zero at four decimal places**,
  and the node column prints six. The precision predates this item and a fully-priced tiny run
  reads the same way. → [`plan.md` §2.1](../plan.md#L38), with the report's number formatting.
- **A cross-call circuit breaker** for a 429 the library cannot classify. →
  [`plan.md` §2.2](../plan.md#L212), deferred with its decider named.
- **A payload stored by reference** would remove the 4.2% the `run_start` record duplicates. →
  [`plan.md` §2.2](../plan.md#L419), where it already sits, unchanged by this.
- **The results visualiser** the scoping question produced, **and the view's fixtures**, which the
  reverification found and Thilina ruled a gap. → [`plan.md` §1](../plan.md#L30) `P3-51`, which
  waited on this item and now waits on nothing.
