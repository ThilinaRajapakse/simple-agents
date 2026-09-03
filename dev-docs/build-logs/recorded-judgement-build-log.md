# Build log — A judgement the scoring code did not compute, stage 1

`plan.md` §4 P3-13, the scoring-time stage of `P3-12`. Started 2026-08-18. Written while building.

Stage 2, the run-time consultation reading, is not built. The design for both is in this file's
§2, moved here from `items/a-recorded-judgement.md`.

## 1. Before any design

Five things were checked against the code before the sitting, and two of the record's own claims
did not survive.

- **`RunEnvelope(role="labelling")` exists and nothing routes a scoring call through it.**
  Confirmed: `role` is set by `with_role` and read by `runs(role=...)`, and no scoring seam
  constructs an envelope at all.
- **`_criteria_record`** ([runner.py:1476](../../src/simple_agents/evaluation/runner.py#L1476))
  writes `source_version(check)` and
  [`_rules`](../../src/simple_agents/evaluation/compare.py#L696) reads exactly that. Confirmed
  by reading both.
- **`source_version` does not version a `Path` a function closed over.** Measured by running
  it: two lookup functions closing over different files produced `sha256:6f331d63b95b` both
  times, and the same functions closing over `str` paths versioned apart.
  [`_stable_text`](../../src/simple_agents/records/manifest.py#L557) renders anything outside the JSON
  scalars as its type name, so a `Path` became `<PosixPath>`. **This contradicts
  [`source_version`](../../src/simple_agents/records/manifest.py#L605)'s own docstring**, which says
  only captured data whose text is fixed by its value counts, and a `Path`'s text is.
- **The item record said a missing judgement ends the evaluation "after every rollout has been
  run and paid for". It does not.** Measured by running six examples at `k=2` with nothing
  judged: it ended after **7 of 12 rollouts**, because scoring runs as each rollout finishes and
  `DEFAULT_CONCURRENCY` is 4, so the failure cancels what has not started. Every completed
  rollout's directory was on disk.
- **`simple-agents.md` §10's offline requirement was never in the way**, which is what decision
  1 turned on. It names the conformance suite, and the conformance suite reads artifacts:
  `docs/conformance.md` §1 says it executes nothing, and nothing in `conformance/` imports
  `EvalSuite`, calls `matches` or reaches a model.

## 2. Design

Eight decisions, settled 2026-08-18 with Thilina. Decisions 1 to 7 are stage 1; decision 8 is
stage 2 and is not built.

### 1. A scoring rule reads judgements and never makes one

**`simple-agents.md` §10 gained a constraint rather than losing one**, at
[§10](../simple-agents.md#L612). The sitting expected to defeat the offline requirement and
found nothing to defeat: what that requirement protects is FT-21, an evaluation that needs live
network and live spend and so stops being run, and `docs/evaluation.md` §6.4's promise that
`rescore` calls no model. A judge that records its judgements meets both.

**Rejected: a judge callable from inside scoring, with a cassette opened for the scoring
phase.** It satisfies §10's substance and costs four things. `rescore`'s promise moves. Scoring
becomes a phase with an envelope, so a check may do arbitrary model work rather than a
judgement. **A person cannot fill a cassette**, so `P3-5` decision 7 would need a second
mechanism and one thing would have two. And a judgement in a cassette cannot be read, disagreed
with and corrected, which is what a project does when a judge is wrong, and what HealthBench's
design of record depends on ([`design/answer-shapes.md`](../design/answer-shapes.md#L545) S5.1).

### 2. `Label` is the record, in a file of its own

`Label` already carried `id`, `verdict`, `decided_by`, `reason`, `run_id`, `decided_at` and
`metadata`, and `verdict` round-trips an `Unknown`. What it lacked is the join, which a project
flattened into the id by hand. It gains `about`.

**Two files, one format, one record type.** `evals/labels.jsonl` stays a judgement about an
**example**; `evals/judgements.jsonl` is a judgement about an **answer**. Different lifecycles:
one is written when the example set is built, the other every time an evaluation runs, at
n × k × judged conditions.

**Rejected: one file**, whose lines would mean two things. **Rejected: a separate `Judgement`
type**, which reopens `P3-5` decision 7 for no gain.

### 3. A judgement is keyed on what was judged

**The key is a digest of `(example.id, the question, the material)`.** For a condition the
question is the criterion's text and the material is the answer. The slot travels in the record
as provenance and is what the refusal message reads.

`rollout` is out, so the k rollouts of one example that produced the same answer share one
judgement. `example.id` is in, because the project writes its own judging prompt and the library
cannot see whether the question was in it.

**A stale judgement becomes an absent one**, which is the point: there is no path where a
verdict made against an older answer is silently applied to a newer one.

*Generalised at the sitting, on Thilina's note that one agent may need several judgements over
several examples in several places.* The digest was first specified as
`(example.id, criterion.id, criterion.text, the answer)`, which only fits a condition on the
answer key. `criterion.id` drops out: two conditions with identical text over one answer are the
same question about the same material.

### 4. The results file records what the numbers rest on

`config.criteria[id]` carries `decided`, and for a judged condition the deciders and their
counts, the judging run ids and a digest of the judgements **that condition** rested on.
`config.judgements` carries the same over every judgement any figure used.
[`_rules`](../../src/simple_agents/evaluation/compare.py#L696) reads both, so a move withholds
the verdict on every rate.

**The judging prompt stays the project's and is recoverable through `run_id`.** It is not in the
digest: putting it there would invalidate every judgement on a one-word edit, and a human
judgement has no prompt at all.

**A condition's text is not compared, and the build is why.** The sitting settled that it would
be compared where a condition is judged. Building it showed the comparison is unreachable: the
text is inside the key each judgement is filed under, so a reworded condition leaves every
judgement unfindable, the evaluation cannot be scored until they are made again, and the new set
has a different digest. There is no pair of results files whose judgements agree and whose
question does not. The decision's intent holds and its mechanism is decision 3's.

**`_stable_text` was corrected ahead of the item**, on Thilina's ruling of 4b-i.

### 5. The judging pass, and one refusal

**The library hands over a worklist and takes back judgements**, and never calls a project
function once per judgement. Thilina, 2026-08-18: ship the seam and no default judge, make it
easy to set one up, and do not get in the way of whatever technique a project wants. Calling per
judgement would fix the granularity at one model call per answer and make a panel, a batch and a
cheap pre-filter either impossible or wasteful.

**Any scoring rule asks for a judgement, and the library never learns what kind it was.**
`Judged()` is sugar for a condition on the answer key; `Scoring.judgement(question, over=...)`
is the general seam and is reachable from `matches`, `node_matches`, a criterion's check and a
`ProjectMetric`.

**Three surfaces, one mechanism.** `suite.judge(run_dir=, split=, using=)` is the primitive;
`suite.unjudged(run_dir=, split=)` exposes the worklist for a person; `run(..., judge=)` calls
the primitive.

**A condition declares it is judged on the suite**, in the map that already says how each
condition is decided. **Rejected: `Criterion(judged=True)`**, which puts "how this is decided"
into the file that says what is true, and moves `content_hash` again.

**The refusal is a gate between the rollouts and the scoring**, naming every answer waiting, the
run directory, and the calls that judge and score them. Neither supported route reaches it.
**Rejected: scoring an unjudged answer as absent**, which would merge "nobody has decided" with
stage 3's `Unknown` and report a wrong number in place of a refusal.

### 6. A judged figure says so in the report

The decider and its counts print under whichever figure rests on judgements.

### 7. The store keeps every judgement and the copy pins a number

In the store, last-in-file wins, so a correction is a later line and the model's original stays.
In the run directory's copy nothing ever changes, so a correction made in May does not move what
March reported. **H1 stays deferred**; every judgement is already in the store, so a reader
returning the spread is what would change.

### 8. The consultation reading (stage 2, not built)

Live, once, through a [`ModelHandle`](../../src/simple_agents/tools.py#L162) inside the consult
call, with the verdict stored on the consultation record. The cost is the agent's, which is the
opposite of the stand-in's, because a reader ships with the agent. What the build has to settle:
[`_delivered_answer`](../../src/simple_agents/runtime/consultation.py#L29) applies `read_answer` outside
`run.call_tool`, so a handle is not reachable on the resume path as the code stands.

## 3. Build

**Results file `0.16` to `0.17`. 2571 tests**, 41 of them new in `tests/test_judgements.py`.
No other format moved.

**New**: `evaluation/judgements.py`, holding `Judged`, `JudgementRequest`, `Judgements`,
`judgement_key` and the refusal.

**Changed**: `Label` gains `about`; `Scoring` gains `judgements` and `judgement()`;
`_criteria_verdict` resolves `Judged()`; `_call` and `_scored` catch the collect signal;
`EvalSuite` gains `judgements=`, `judge()`, `unjudged()` and `run(judge=)`; `_rules` compares
the deciders and the whole-evaluation digest; `report()` prints the decider.

**Eight things the build and the verification pass found that the design did not know.** Four
of the eight came only from a live run or from the verification, after the suite was green.

1. **The text comparison decision 4 specified is unreachable**, because decision 3's key already
   covers it. §2 decision 4 carries it.
2. **Both judged conditions recorded the whole evaluation's judgements.** Found by the live run:
   two conditions over three examples each reported `n: 6` and one shared digest, so a
   per-condition figure claimed judgements that were another condition's. `Judgements` now
   records per site and `to_record(site)` filters. `test_each_condition_records_its_own_judgements`.
3. **A judged figure that is not a condition had nothing comparing it.** `_rules` compares each
   criterion's entry and each metric's source version, and a metric whose figure comes from a
   judgement has an unchanged source version, so re-judging moved the number silently.
   `config.judgements` and the comparison over it close it.
   `test_a_judged_figure_that_is_not_a_condition_is_still_covered`.
4. **A judging pass that answers none of what it was asked was re-asked eight times.** Found
   on the live vLLM run. A round that resolves nothing now ends the loop and the refusal says
   the pass was asked and did not answer, which is a different fault from nothing having been
   asked. A round that answers *some* still rounds, because that is what a rule reaching a
   second judgement needs.
5. **`Judgements` is written from several threads.** Rollouts score at `DEFAULT_CONCURRENCY`,
   and what a judgement was read for is a dict write per rollout. Both records are under a lock;
   a lost write would be a count and a digest no re-run reproduces.

**Three more from the verification pass, after all of the above was green.**

6. **Two failure paths built a `Scoring` carrying no judgements.** A rollout that raised still
   reached the nodes before the one that stopped it, so `node_matches` runs on it, and a node
   judgement there raised "this Scoring carries no judgements" rather than collecting the
   request. One agent failure became an evaluation failure.
   `test_a_node_judgement_survives_a_rollout_that_failed`.
7. **`rescore` overwrote the copy that pinned an earlier number.** Measured: a rescore reading
   one condition where the run had two shrank `runs/eval_<id>/judgements.jsonl` from 2 to 1, so
   the first results file named judgements its own run directory no longer held. The copy is
   written once and never replaced now, and a directory without one still gets one.
   `test_a_rescore_does_not_overwrite_what_pinned_an_earlier_number`.
8. **`compare_variants` had no `judge=`, so a judged condition could not be swept at all.**
   Every arm produces its own answers, so none can be judged before the sweep runs, and each arm
   reached the gate and refused. `test_a_sweep_passes_its_judge_to_every_arm`.

**How the collect pass works, which the design left to the build.** A rule asking for a
judgement nothing has made raises inside `Scoring.judgement`, and the seam that called the rule
catches it and leaves that rule undecided. So one pass over the rollouts collects every missing
judgement rather than stopping at the first. A rule reaching a second judgement only once the
first is answered is why `_through_judging` rounds, bounded at `JUDGE_ROUNDS = 8`.

**One vacuous assertion was written and caught.** `test_an_unjudged_answer_is_not_scored_as_an_absence`
first asserted `not list(...)[0:0]`, which is true of everything. It now runs both states and
compares them.

**Every mechanism was mutation-checked**: the key ignoring the material or the question, the
gate never firing, the frozen copy never written, the comparison ignoring the judgements, the
report dropping the decider, and both defects above. Each is caught by at least one test.

## 4. Verification

**Live against Gemini (`gemini-3.1-flash-lite`) and vLLM (`Qwen/Qwen3-1.7B`, port 8001).** The
script is a real agent writing customer replies and a real judging pass under
`RunEnvelope(role="labelling")` deciding two prose conditions.

**Gemini, what it showed.**

- The judging pass is one fan-out run, `role: labelling` in its manifest, priced at
  `0.0001279 USD` with `is_upper_bound: false`.
- **The judge discriminates**: `offers_a_next_step` scored 33.3%, one of three met, with a
  reason per verdict. The first live run had every condition met by every reply, which would
  have passed had the judge always returned `True`; a second condition the agent is not
  instructed to meet is what made it a test.
- `run_id` on every judgement names the labelling run; the frozen copy holds six; `rescore`
  reproduces the reported figure.
- **Two defects came out of this run**, §3 items 2 and 3.

**Two things the live run corrected in the harness rather than the library.** An output schema
with no `unknown` variant was refused (FT-09), correctly, and the waiver is right for a reply
that always exists. And a `PriceBasis` without `input_cache_write_per_mtok` left the run
unpriced, with the report naming the field to declare; that is the Gemini behaviour
`plan.md` §2.2's adapters entry already records.

**vLLM (`Qwen/Qwen3-1.7B`), and it found more than Gemini did.**

**The first two attempts wasted about twelve minutes and neither was the server's fault.** The
harness set no `max_output_tokens` on either node, and a run budget is checked between steps
rather than inside a call, so nothing bounded one generation: the server showed `Running: 1 reqs`
for 108 consecutive samples with KV cache usage climbing 6.6% to 15.9%, which is one request
generating to the context limit. Capped at 1200 tokens, a preflight call returned in **1.4s at
255 output tokens with `finish_reason=stop`**, and the whole twelve-call run then finished in
well under a minute. **A preflight that proves one call terminates belongs before any live run
on a reasoning model**, and it costs one call.

**A third defect came out of the run**, and it is §3 item 5. `Qwen3-1.7B` failed schema
validation on some judge calls; the harness dropped those, so the pass returned fewer judgements
than it was asked for, `_through_judging` re-asked eight times, the model failed again each
time, and the refusal blamed the missing judgement rather than the pass that had been asked and
had not answered. Eight judging passes to reach one refusal.

**And a semantics trap the harness fell into.** Recording `Unknown` as the verdict for a judge
that failed reports it as **the answer** asserting nothing, and it is counted in
`results.criteria[id].absent` beside the agent's own silences. The library is right and the
refusal message invited the confusion; it now says a pass raises where it cannot decide, and
that `Unknown` is a claim about the answer.

**What it showed once it ran.** `offers_a_next_step` at 33.3% with two absences, the labelling
run priced at `0.0017249 USD` with `is_upper_bound: false`, and `rescore` reproducing. **vLLM at
`temperature=0.0` is not deterministic across rollouts**: `c1`'s two rollouts produced different
answers and were judged separately, which is decision 3's key doing what it is for.

## 5. Doc consequences

- **`docs/evaluation.md` §12 is new**, six subsections: declaring a condition as judged, running
  it, what a judgement is keyed on, what happens when one is missing, the two files, and what
  the results file records.
- **`CHANGELOG.md`** carries the results file `0.16` to `0.17` entry and what a project has to
  do, which is nothing unless it registers `Judged()`.
- **Four shipped statements stopped being true and were corrected**, all one root cause: that a
  value a function closes over is not in `source_version`'s hash. `docs/evaluation.md` §11.6,
  `ProjectMetric`'s docstring and `WithinTolerance`'s said it; `docs/run-envelope.md` §2.6 gave
  a stale reason for `consultation_route`. The true sentence belongs to `tools.py`'s
  [`derived_version`](../../src/simple_agents/tools.py#L1054), which hashes source alone, and
  `docs/tools.md` §3.1 states it correctly. `design/answer-shapes.md` S3.6 carried the same
  claim and is corrected there.
- **Fourteen conformance fixtures regenerated** for the results file bump.
- **A fifth false statement, in `CHANGELOG.md` and written by this build.** It said a results
  file written by `0.16` "is read as before". `EvalResults.read` refuses any file whose version
  is not the current one, which every results-file bump has always done, so the entry now says
  what a project does instead: `rescore` produces a `0.17` file from rollouts already on disk.
- **`docs/model-clients/vllm.md` §2 gains the output ceiling**, which is what §4 cost twelve
  minutes over. A builder meets the same thing.

## 6. Left open

- **Stage 2, the consultation reading.** **Destination:** [`plan.md` §1](../plan.md#L25) P3-12,
  which stays open for it, with the design at
  [`archive/a-recorded-judgement.md`](../archive/a-recorded-judgement.md#L1) decision 8.
- **A judged figure has no per-site entry outside `config.criteria`.** A judged `ProjectMetric`
  or node label is covered by `config.judgements` and by nothing narrower, so a comparison says
  the judgements moved without saying which figure's did. Naming the metric would mean
  threading it into `Scoring`. **Destination:** [`plan.md` §2.2](../plan.md#L101), to be raised
  when a project has a judged metric; no dogfood has one.
- **A judge is a model client nothing paces.**
  [`_pace_for`](../../src/simple_agents/evaluation/runner.py#L2862) paces
  `_clients_of(self.pipeline, model)` and a judging client is in neither. **Destination:**
  [`plan.md` §2.2](../plan.md#L226)'s ceiling-on-one-client entry, where it is recorded.
- **`compare_variants` over a pipeline that makes no model calls raises `FileNotFoundError`
  looking for a cassette nothing wrote.** Reproduced against the code as it stood before this
  sitting, so it predates this item and is not its doing. **Destination:**
  [`runs/dogfood-4/inventory.md`](../runs/dogfood-4/inventory.md#L1) as a candidate, since
  `plan.md` §1 P3-1 is the queue for defects with no item of their own.
- **The shipped example set owes a judge and a panel.** **Destination:**
  [`items/example-projects.md` §19.9](../items/example-projects.md#L1739), where it is recorded.
