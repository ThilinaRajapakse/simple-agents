# Dogfood #1 — findings and the v0.1 changelog

The measurement `runs/dogfood-protocol.md` §1 asks for, analysed. `runs/dogfood-protocol.md` §1 step 5 says this log **is** the
v0.1 changelog, so every entry below was a candidate change when it was written.

**Every finding here landed at the sitting on 2026-08-07 except D8, and §9 is the ledger.** The
entries below are left as written, so the figures are the run's rather than retrofitted. **D8 is
the one still open**: a project-side model call, a labelling pass, an ablation or a judge has no
envelope, which is now part of the labelling sitting (`archive/dogfood-absorption.md` item 10). §9's one
deviation from that sitting was closed on 2026-08-09.

**Project:** `/home/thilina/Projects/dogfood-1`, one commit (`5324dff`, empty tree plus
`pyproject.toml`, `.gitignore` and Simple Agents installed from the wheel into `.venv`). A fresh
coding-agent session, three-sentence prompt, `BUILD-LOG.md` requested. Thilina answered
elicitation and volunteered nothing, per §4.1 step 3.

**Elapsed 12:37–14:07 local, about 90 minutes.** 470 runs inside the envelope, 574 model calls,
**$0.1003** recorded. The ground-truth verification pass (two rounds of 30 calls on
`mistral-medium-2604`, roughly 660k input tokens) is not in that figure, because it ran outside
the envelope — which is finding **D8**.

---

## 1. Method, and the standard §1 of a build log sets

`BUILD-LOG.md` is a coding agent's account of its own work, so it is a hypothesis. Item 8b's
entry claimed a settled design and four of its claims did not survive being run; item 13 §1 aimed
at its own entry's premise and found three defects nobody had named.

Every checkable claim in `BUILD-LOG.md` was reproduced against the artifacts before being
accepted. **All of them held.** That is the opposite of item 8b and it is worth stating plainly:

| Claim | Reproduced |
|---|---|
| BM25 `recall@1/3/5/10 = 28/29/29/29` of 30 | Re-ran `retrieval.BM25Index` over `data/candidates.jsonl`. Exact. |
| 19 of 145 v1 rollouts wrote a bare `"unknown"` literal, every one on an absence-labelled example | Exact. Literals were `unknown`, `Unknown`, `UNKNOWN`. v2: **0 of 145**. |
| Verification flagged 8 of 30, hand review kept 7 and dropped 1 | `data/verification.jsonl`, `data/hand_review.json`. Exact. |
| The `compare()` table, six metrics with intervals on the paired difference | Re-ran `compare()` over the two results files. Every figure and every verdict reproduces to three decimals. |
| Corpus 60 documents, 43,454 chars | Exact. |
| Final set 59 examples, dev n=30 absent 14, held_out n=29 absent 15 | Exact. |
| `simple-agents check`: 7 of 7, exit 0 | Re-run. Exact. See §2. |

**One error in the log, and it is cosmetic.** The "I1 — RESOLVED" section says "Final example
set: 59 examples — dev n=29 (48% absent), held_out n=30 (50% absent)". That is the pre-D28 split,
and D28 further down states the real one correctly. The log is chronological, so the numbers are
not wrong in place, but the words "Final example set" are.

**What the log does not contain is any claim about the library that turned out to be flattery.**
Where it named a library trap it had walked into (I7), the trap is real and the doc that names it
is quoted correctly.

---

## 2. The ship criterion — `archive/plan-history.md` §3.3

> **v0 is done when a coding agent, given only the library and its docs, from a cold start,
> produces a trivial agent that passes `simple-agents check` at tier `evaluated`.**

**It passed.** Run directly against the project rather than read off the log:

```
simple-agents check: .
tier evaluated, declared in brief.toml

  pass  FT-13  No trajectory logging             runs/eval_87bb1e511497/.../trajectory.jsonl
  pass  FT-14  Model version unpinned            runs/eval_87bb1e511497/.../manifest.json
  pass  FT-24  Elicitation skipped               brief.toml
  pass  FT-01  No evaluation at all              evals/results/held_out-k5-v2.json
  pass  FT-02  No held-out split                 evals/results/held_out-k5-v2.json
  pass  FT-06  Point estimate with no interval   evals/results/held_out-k5-v2.json
  pass  FT-07  Seeds uncontrolled                evals/results/held_out-k5-v2.json and 145 more

0 failed, 7 passed          exit 0
```

**What it passed on**, because item 10 §1.2 measured three hand-written files passing at tier
`prototype` with the library never called. That is not what happened here:

- FT-13 and FT-14 read a trajectory and a manifest **the run envelope wrote**, from a real
  `Pipeline.run` against `mistral-small-2603`. 470 run directories, 574 model calls.
- FT-24 reads a `brief.toml` whose twelve required entries carry answers that came from Thilina,
  each one traceable to a numbered interaction in the build log.
- FT-01, FT-02, FT-06 and FT-07 read a results file **`EvalSuite.run` wrote**: 29 held-out
  examples, k=5, seed 41, bootstrap intervals on all eight metrics, contamination clean at
  threshold 0.8, per-rollout seeds recorded.

The criterion is met. The rest of this document is what the run found on the way.

*Measured against the seven checks that shipped at `e2b277c`. The suite is nine as of the fixes
in §9, and the project passes all nine unchanged: FT-03 reads a clean contamination report and
FT-04 reads 15 of 29 held-out examples expecting absence.*

---

## 3. What only the artifacts could answer

| Question | Answer, and where it was read |
|---|---|
| Was the skill found and used, or the procedure reconstructed from the docs? | **Reconstructed, then registered.** `BUILD-LOG.md` Exploration 1 reads `simple_agents.docs_path()`, then `docs/index.md`, then `docs/procedure.md`. `simple-agents init` was run *after* (D2 in the log), creating `.agents/skills/simple-agents` as a symlink and `AGENTS.md`. The skill mechanism did not deliver the procedure. See **P3**. |
| Which stage does the brief declare, and is every required question answered? | `stage = "measure"`, `tier = "evaluated"`. **All 12 required questions `answered`.** `unknown_literal` (optional) also answered. `prices` is `deferred` — see **D7**. `context_limit`, `rerun_cost` and `reproduce` have **no entry at all**. |
| Does the held-out split hold absent-answer examples, and what does `absent_proportion` report? | Yes. `config.example_set.absent_proportion = 0.5172` (15 of 29). FT-04 satisfied — but nothing checked it. See **D5**. |
| What k, and against what? | **k=5.** D27: the answer node runs at `temperature=0.0`, so the library would permit k=1, "but 'temperature 0 is deterministic' is an assumption, and k=5 measures it instead of asserting it. At ~$0.03 for the whole split there is no reason to save the money." That is the reasoning `docs/evaluation.md` wants. |
| Was a cassette recorded? | **No. `cassette.mode` is `"off"` on all 470 manifests.** Nothing in this project is replayable. `reproduce` was never asked. See **D9**. |
| Which node kinds, and was an `AgentNode` justified? | Three `Deterministic` and one `LLMNode`. **No `AgentNode`, and the absence is argued** in `brief.toml` under `agency_boundary` and again in `agent.py`'s module docstring, both citing FT-11. The one run-time decision is a `Loop(max_iterations=2)` with the route on the pipeline, not the model. This is the library's own opinion being applied correctly without being told to. |
| Does any tool it wrote carry a contract test? | **It wrote no tool.** `manifest.tools` is `[]` on every run, `tool_call` count is 0. See **D4**, which is the largest finding in this document. |
| What did it cost, and how long? | $0.1003 and about 90 minutes, plus an unpriced ground-truth pass. |

### 3.1 The item 14 measurement

The `improvement` question was rewritten the day before this ran, to ask which number the builder
would act on, with a scaffold that prints the six rates against the project's own numbers and
points at `ProjectMetric`.

**The question was asked, and asked correctly.** `brief.toml` under `improvement`: "The builder
was shown the six rates with this project's own numbers rather than being asked in the abstract."
It was put after the first clean evaluation, with the seven-line table of this project's rates in
front of it. Thilina answered `false_confidence_rate`, paired with `recall`. The method offered
was the default one and it was taken: k=5 before and after, compared on intervals.

**The seam was not needed and was used anyway.** A project metric is not required for exact-match
question answering, and none was declared *for* `improvement`. But two `ProjectMetric`s were
declared earlier, at stage-3 groundwork (D22), for a different reason: exact match scores
`"in 911"` against gold `"911"` the same as a total miss, so `span_f1` (`Over.VALUE_EXISTS`) and
`span_f1_when_asserting` (`Over.ASSERTED`) were added beside the six rates. Both carry a
definition, a denominator and a version in the results file.

So item 14 passes on the question. It is `Over.ASSERTED` that produced a defect, in `compare()`
rather than in the metric — **D6**.

---

## 4. Library defects

Ranked by what they cost this project.

### D1 — Per-node `reach` reports the failure rate, and contradicts the count beside it

**Design bug.** `results.report()` on the shipped number prints:

```
  node        kind          reach                 runs  calls  tools  cost
  prepare     deterministic 94.5% [90%,99%]        145      0      0  unknown
  retrieve    deterministic 94.5% [90%,99%]        207      0      0  unknown
  answer      llm           94.5% [90%,99%]        207    207      0  0.038735 USD
  report      deterministic 94.5% [90%,99%]        137      0      0  unknown
```

Four nodes, one number. `prepare` ran on all 145 rollouts and `report` on 137, and the reach
column cannot tell them apart. The `runs` column carries the whole signal.

**Mechanism.** A rollout that raises builds its `RolloutOutcome` with no `nodes=` argument
([`runner.py` `EvalSuite._rollout`](../../../src/simple_agents/evaluation/runner.py#L1323)), so every node reads as not
reached — even though the trajectory on disk shows which nodes ran. `_rate` then averages
`1.0 if reached else 0.0` over rollouts, which for every node equals `1 − failure_rate`.

**The same file states both answers.** `results.nodes["prepare"]` carries `reached: 145`,
`runs: 145`, accumulated from the trajectories and correct, next to
`reach.interval.point: 0.9448`, which is 137/145. `report`'s two figures agree by coincidence.

`per_node.py`'s own docstring says reach exists because "a node in a graph does not run on every
rollout", which is the case it cannot measure.

### D2 — A paced call blows a wall-clock budget the library's own scaffold produced

**Design bug**, with a prose half at **P7**.

`budget`'s scaffold says: "Run one example, read what it consumed from the manifest's totals, and
propose the four numbers from that with headroom. They are derivable, so nothing here has to be
guessed (FT-18)." The coding agent did exactly that: measured ~2,000 ms, proposed 60,000 ms, and
recorded the 30x headroom in the brief.

`PacedClient.DEFAULT_MAX_WAIT_S` is **65.0** ([pacing.py:34](../../../src/simple_agents/pacing.py#L34)).
One paced call therefore exceeds the whole run budget, and the wait is charged to it, because
the run's wall clock is read from the clock rather than summed from call
durations, at [`RunContext._elapsed_ms`](../../../src/simple_agents/context.py#L473), so time a
call spends waiting is inside it. *(This cited `nodes.py:1376` until 2026-08-18, which was
`self._deliver(...)` and had nothing to do with the claim: the line had drifted and no symbol
was named beside it, so `check_citations.py` could not see it was wrong.)*

Read off `runs/eval_87bb1e511497/5ad243abd7d075001a428a13-2/trajectory.jsonl`:

```
5 node_execution retrieve  12:00:07.729Z -> 12:00:07.730Z
6 model_call               12:00:07.730Z -> 12:01:13.684Z     <- 65.95 s, one call
7 node_execution answer    12:00:07.730Z -> 12:01:13.684Z  termination max_iterations
```

Manifest: `outcome: "stopped_early"`, `stopped_early: "max_wall_clock"`. Error:
`limit 60000, spent 66890`.

**Cost: 8 of 145 rollouts, 5.5%.** `failure_rate 0.055 [0.014, 0.103]` is in the shipped number
and in the README, and it is the library's rate limiter tripping the library's budget. Nothing
about the agent produced it. Two of the eight had already produced an answer when the check fired.

Every ingredient of this is documented separately and nothing connects them. `docs/pipeline.md`
§5 says time spent *suspended* is charged to nothing; it does not say what pacing is charged to.
`docs/model-clients.md` §-pacing recommends `PacedClient` for exactly this workload and never
mentions the budget.

### D3 — `Maybe[T]`'s description is replaced silently, and it is detectable

**Design bug**, with a prose half at **P1**.

`Maybe[T]` supplies its own field description naming the tagged shape. A
`Field(description=...)` on the same field replaces it. The v1 schema did that, the model was
shown a union of a string and an object with nothing saying which branch an absence goes in, and
it chose the string.

**Measured cost: 19 of 145 held-out rollouts (13.1%), every one on an absence-labelled example.**
Each was the agent abstaining correctly and being recorded as confidently wrong. It moved
`false_confidence_rate` by roughly 13 points and it took a whole second evaluation to find, a
third to fix, and a `compare()` to establish. v2 spelled the shape out and reduced it to 0 of 145.

`Field(description=...)` on a field whose annotation is `Maybe[T]` is inspectable at
`LLMNode` construction. The library refuses a schema with no absence branch (FT-09); it accepts
one whose absence branch has had its only explanation removed.

### D4 — `document_search` was reimplemented by hand, line for line

**Design bug.** `archive/plan-history.md` §4.2 chose this task partly to exercise the tool surface: "Handing the
agent the question alongside its own passage collapses the pipeline to a single `LLMNode` and the
dogfood then exercises no tool at all: the tool registry and minimal tool set of item 7 ship
undogfooded, no `side_effect_class` is ever declared, and the tool-call half of the cassette is
never replayed."

**The passages were pooled, and all of that happened anyway.** `manifest.tools` is `[]` on all 470
runs. Item 7's registry, item 13's `Deterministic(fn, tools=[...])`, `side_effect_class`, the
finish check and the tool half of the cassette are all undogfooded.

The library ships `DocumentIndex` and `document_search`
([builtins/search.py](../../../src/simple_agents/builtins/search.py)) — BM25 over a project-supplied
document collection, pure Python, `K1 = 1.5`, `B = 0.75`, tie-break by `doc_id`, IDF
`log(1 + (N − df + 0.5)/(df + 0.5))`.

The project's `retrieval.py` is BM25 over a project-supplied document collection, pure Python,
`K1 = 1.5`, `B = 0.75`, tie-break by `doc_id`, IDF `log(1 + (n − df + 0.5)/(df + 0.5))`. The
regex is `[a-z0-9]+` in both files. The only differences are a stopword list and a `title` field.

**The log records the moment.** D3 in `BUILD-LOG.md`: "There is no vector store, no chunker, no
embedder anywhere in the package. `builtins/search.py` exists — needs checking, but retrieval
over the corpus is the project's job, not the library's." It saw the file, deferred reading it,
and closed the question against the library.

This is item 10 §1.11's pattern with a shipped module rather than a constructor: a prior about
what libraries provide, resolved without opening the section that answers it.

### D5 — Contamination is discoverable only after the evaluation has been paid for

**Design bug.** The split was drawn per question rather than per source document, so two questions
from one paragraph landed on opposite sides. `contamination` flagged **22 `shared_source` pairs**.

The project learned this from the results file of a completed 150-rollout evaluation. FT-03 is not
one of the seven conformance checks
([`CHECKS`](../../../src/simple_agents/conformance/checks.py#L2128)), and `contamination` is computed
inside `EvalSuite.run` and written into the results file. `ExampleSet.contamination(threshold=...)`
exists standalone and is shown in `docs/evaluation.md` §1.2, and nothing routes a coding agent to
it before spending the rollouts.

**FT-04 is the same shape and got lucky.** `absent_proportion` is recorded in `config` and
checked by nothing. FT-02 tests that a held-out split exists and is not empty. A project whose
held-out split holds zero absence examples passes all seven checks at tier `evaluated`.

**And the library ships no splitter.** `simple-agents.md` §1.6 puts "where the split falls" on the project
side, which is right for *which* examples and *what fraction*. Grouping by `source` so FT-03
cannot fire, while preserving the absence stratification FT-04 needs, is vetted methodology and
the project had to invent it — 45 lines of greedy group assignment in `build_evalset.py`, written
after the first evaluation was discarded.

### D6 — `compare()` puts two point estimates from different populations beside a paired difference

**Design bug.** Reproduced by re-running `compare()` over the two shipped results files:

```
precision_when_asserting   before 0.385   after 0.474
                           difference 0.000  [0.000, 0.000]  n=19
```

Both figures are correct and together they read as a contradiction. `precision_when_asserting` is
over rollouts that asserted a value, so its example population is decided by the agent's own
behaviour: 26 examples in v1, 19 in v2. `compare()` pairs on the intersection, and on all 19
shared examples the per-example precision is **identical** — verified by recomputing it from the
rollouts. The 9-point move is entirely the 7 examples that left the denominator, all of which
scored 0 in v1.

`span_f1_when_asserting` (`Over.ASSERTED`, item 14's seam) has it too: 14 examples then 13, point
estimates 0.839 and 0.825, paired difference −0.0016. `BUILD-LOG.md`'s "honest reading" quotes
the paired difference and the README quotes the point estimates, and a reader has no way to know
they are answering different questions.

`MetricChange` already carries `examples`, and `verdict_reason` already exists for "this many
cannot say". Nothing says "these two numbers are over different sets".

### D7 — A deferral never expires

**Design bug.** `brief.toml`:

```toml
[entries.prices]
status = "deferred"
deferred_to = "measure"
```

The brief's `stage` is `"measure"`. The question was deferred to the stage the project is already
at, and FT-24 counts it settled:
`_settled` returns true for any entry whose status is `answered` or `deferred`
([checks.py `_settled`](../../../src/simple_agents/conformance/checks.py#L534)), without comparing `deferred_to`
against the stage reached.

`prices` is optional, so nothing was skipped that a gate wanted. The shape is the problem: a
*required* question deferred to `shape` would pass a `measure` gate the same way.

`BriefEntry`'s docstring says "a deferred entry names the stage it is deferred to, so a postponed
decision is distinguishable from a forgotten one", and `CLAUDE.md`'s glossary says deferral "must
be recorded, never left blank — otherwise postponed is indistinguishable from forgotten". A
deferral to a stage already passed is exactly that state, recorded.

### D8 — A project-side model call has no envelope

**Design bug.** `verify_unanswerable.py` defines this project's ground truth for every
unanswerable example. It calls `MistralClient.complete` with a hand-built `ModelRequest`, twice
over 30 questions, on `mistral-medium-2604`, at `temperature=0.0`, `seed=20260807`.

None of it is recorded. No trajectory, no manifest, no cost, no model pin, no cassette, no
`replayed` flag. Roughly 660k input tokens and the entire label set of half the evaluation sit
outside everything the library built.

`who_labels` in `brief.toml` describes the pass in prose and the pass wrote
`data/verification.jsonl` by hand. FT-14 pins the model the *agent* ran on; nothing pins the
model that wrote the labels the agent is graded against, and the brief's own answer says using a
different model there is deliberate.

A labelling pass, an ablation and a judge are all project-side model calls, and the library has
one envelope, reachable only through `Pipeline.run`.

### D9 — `reproduce` is optional, and nothing in this project can be replayed

**Design bug**, small and cheap to argue either way.

`cassette.mode` is `"off"` on all 470 manifests. `reproduce` is `required=False`
([elicitation.py:207](../../../src/simple_agents/conformance/elicitation.py#L207)) and has no entry in the
brief, so it was never put.

`archive/plan-history.md` §4.2 assumes the opposite: "The first recording costs network and time; every replay
after it is a disk read, so running the protocol two or three times per §4.1 costs the same
whichever set was chosen." Re-running dogfood #1's evaluation today costs the API again.

FT-07 passes on seeds, and the question's own scaffold says why that is not enough: "A seed alone
does not reproduce a run against a hosted API, because the provider does not promise determinism
at a fixed seed."

---

## 5. Documentation bugs

Split as Thilina ruled at the item 14 sitting: a confusion caused by prose he would have caught
in the review is a different finding from one caused by the design. `docs/procedure.md`,
`docs/index.md`, `docs/conformance.md` and the README's quick start have never been reviewed, and
`docs/evaluation.md` carries unreviewed text from items 9, 8a, 13 and 14.

### 5.1 In documents that were reviewed — not excused by the ordering

**P1 — `docs/pipeline.md` §4 states the `Maybe[T]` replacement and stops there.**
`pipeline.md` is marked done in Thilina's Corner. Its last sentence on the subject is: "`Maybe[T]`
supplies its own description, saying to send either the value or
`{"type": "unknown", "reason": "..."}`. A model shown a union of a string and an object has no
other way to tell which one an absence goes in. A `Field(description=...)` on the field replaces
it."

Every word is true and the paragraph never says what happens next. `CLAUDE.md`'s docstring
standard puts "what happens when it is used wrongly, and what to do instead" at item 5 and calls
it one of the two that get skipped. The coding agent read this section *after* the failure, quoted
it correctly, and wrote in its own log: "The library had written down exactly this failure and I
overwrote the mitigation." It had not written down the failure; it had written down the mechanism.

**P2 — the built-in inventory is in `docs/tools.md`, and `docs/index.md` says to open that
document "before a tool is written or registered".**
`tools.md` §-builtins line 317 documents `document_search` accurately. The routing rule gates it
behind a decision the coding agent had already made the other way at Exploration 1. It asked "does
the library provide retrieval?", answered it from the package tree, and by index.md's own rule
never had a reason to open the document that says yes. See **D4** for the cost.

### 5.2 In documents that have never been reviewed

**P3 — `docs/procedure.md` never names `simple-agents init`.** The procedure *is* the skill, and
the command that registers it appears once in the library, in one sentence of `docs/index.md`.
The dogfood found the procedure by reading `docs_path()` → `index.md` → `procedure.md` and ran
`init` afterwards. It worked, and it worked by the route that does not need the skill.

**P4 — `docs/procedure.md` stage 3 names four decisions the library will not make, and the
contamination one carries no timing.** "How similar is too similar for contamination (FT-03)"
sits beside `matches`, the split and k. Three of those are needed to start an evaluation; this one
is only readable after one has finished, unless the project knows to call
`ExampleSet.contamination` first. Nothing says to. Cost: 150 discarded rollouts (**D5**).

**P5 — `docs/index.md`'s "when to open it" column routes by artifact, not by question.** Every row
is phrased as "before X is written". A coding agent deciding *whether* to write X has no row. This
is the general form of **P2**.

**P6 — `docs/evaluation.md` §1.1 and §1.2 describe what the checks report and never how to draw a
split.** §1.2 explains `shared_source` precisely — "flags a pair drawn from one `source` however
differently they are worded, because what was learned from one applies to the other" — as a
description of a report. The instruction it implies, group by `source` when assigning splits, is
not written anywhere.

**P7 — the `budget` scaffold's method does not survive the workload the library recommends.**
"Run one example, read what it consumed from the manifest's totals, and propose the four numbers
from that with headroom." A single un-paced run is not a sample of a paced, concurrent
evaluation, and on the wall-clock axis it is off by a factor the headroom cannot absorb. See
**D2**.

---

## 6. What did not go wrong

Recorded because a findings document that lists only failures misreports the run.

- **The staged procedure was followed literally**, all three stages, all three gates, with the
  stage-1 gate correctly reported as "FT-24 pass, everything else blocked, exit 1" and read as
  expected rather than as a failure.
- **No elicitation question was answered on the builder's behalf.** `brief.toml` opens with
  "Every `answered` entry below came from the builder. None were invented by the coding agent",
  and every entry traces to a numbered interaction in the build log.
- **FT-11 was applied without being prompted.** No `AgentNode`, the reason argued in two places,
  and the run-time decision routed through `Loop` with the route on the pipeline.
- **FT-18's spirit held even where its letter failed.** The four budget numbers were derived from
  three real runs and the derivation is written down. Compare item 10 §1.10, where four budget
  numbers were invented with full context on this library. The scaffold works; **D2** is a
  different problem.
- **`Join` was probed rather than guessed at.** Exploration 3 built the cycle with
  `FakeModelClient` and scripted two responses to find out what a second-pass node actually
  receives, instead of reasoning from the prose.
- **The contamination check earned its keep.** It caught a real split defect that would otherwise
  have shipped, and the project discarded the numbers rather than reporting them.
- **`compare()` was used the way `improvement` says to use it**, and the log's reading of it is
  careful: "the recall cost is real in direction but not established... saying it 'cost 11 points
  of recall' would be overclaiming."
- **A defensive scoring fix was offered and declined, and the decline is recorded** in
  `unknown_literal` with the numbers it would have moved (accuracy 0.434 → 0.566). The number was
  not allowed to flatter the agent.

---

## 7. `runs/dogfood-protocol.md` §1 step 5 — the three categories

**All three are empty.** Answered by Thilina at the sitting, 2026-08-07, asked directly rather
than inferred from the transcript.

1. **Interventions he was forced to make: none.** He answered what the coding agent raised and
   nothing else. The two moments the log records as his — the doc-054/doc-011 evidence
   correction and the call on the single genuine pooling collision — were both put to him by the
   coding agent, so they are elicitation working rather than intervention.
2. **Questions he was asked that the library should have answered itself: none.** Fourteen brief
   entries across five interactions, and none of them read as over-asking. This is the clause of
   §4.1 that watches for the library burning the builder's patience, and at this question count
   it did not.
3. **Things he wanted to volunteer and was never asked for: none.** §4.1 calls this the
   highest-value entry and the easiest to miss. It is empty here, which is the elicitation set
   covering the ground on a task of this shape.
4. **Where the transcript and the log disagree: nowhere.** Which is consistent with §1, where
   every checkable claim reproduced.

**What an empty log means, and what it does not.** The handshake §4.1 exists to measure held: a
coding agent from a cold start asked the right questions, asked no wrong ones, and left the
builder with nothing to volunteer. **None of the findings in §4 and §5 came from this instrument.**
Every one of them came from reading the artifacts, which is what item 8b's and item 13's §1
precedent asks for and is the reason that step is in the protocol at all. §4.1 step 5 defines the
log as the v0.1 changelog; on this run the changelog is the artifact reading, not the three
categories.

---

## 8. Prior questions this run answers

- **`build-logs/item8c-build-log.md`, branching.** The evidence bar is "if dogfood #1 or #2
  meets it too, that is the same pattern and it should be built". **This project met the graph
  case and used what shipped.** `Loop(max_iterations=2)`, a route over a validated output, and a
  `Join` carrying the original question round the cycle so nothing had to be smuggled through the
  answer schema. Item 8c is dogfooded and the note's original conditional-skip question is moot.
- **`plan.md` §2.1, no seam for a project-supplied count or total.** The
  entry predicted "Dogfood #1 is exact-match question answering and will not [reach for one]".
  **Correct.** Two `ProjectMetric`s were declared, both means over examples, both took intervals.
  Nothing reached for a count.
- **`plan.md` §2.2, a payload stored by reference.** Not exercised: this project's payloads are
  60 short passages and the largest trajectory is 18 KB.

---

## 9. What landed, decided at the sitting on 2026-08-07

Thilina's ruling was that every fix lands now rather than as v0.1, so the changelog in §4 and §5
is a record of what was built rather than a queue. **1147 tests pass**, up from 1127.

| Finding | What landed | Kind |
|---|---|---|
| **D1** | Both failure paths in `_rollout` read the trajectory, so a run that stopped partway counts the nodes it reached | code |
| **D2** | `ModelResponse.held_back_ms` carries retry backoff and pacing through `HttpResult` and `PacedClient`; `max_wall_clock` is charged the call without it | code |
| **D3** | `warn_absence_undescribed` at `LLMNode` and `AgentNode` construction, silent once the description names the `unknown` tag | code |
| **D4** | `docs/procedure.md` stage 2 names the built-in set before a node is written; `docs/index.md` routes `tools.md` by the decision rather than by the artifact | prose |
| **D5** | `EvalSuite.run` refuses a contaminated split before the first rollout, waived by `allow_contaminated_split`; FT-03 and FT-04 are now checks, so the suite is nine | code |
| **D6** | `MetricChange.population_note` and `Comparison.population_changed` name a metric whose denominator moved | code |
| **D7** | A deferral settles a question only until the project reaches the stage it names | code |
| **D8** | Not built. See below. | — |
| **D9** | Not built as a required question. `docs/procedure.md` stage 3 says what recording the first evaluation buys on the second | prose |
| **P1** | `docs/pipeline.md` §4 carries the consequence and the fix, not only the mechanism | prose |
| **P2, P5** | `docs/index.md`, as D4 | prose |
| **P3** | `docs/procedure.md` names `simple-agents init` | prose |
| **P4** | `docs/procedure.md` stage 3 says to assign whole sources to a split | prose |
| **P6** | `docs/evaluation.md` §1.2 says how to draw a split, not only what the check reports | prose |
| **P7** | `docs/pipeline.md` §5 and `docs/model-clients.md` say what the wall clock is charged | prose |

**Two things deliberately not built.**

- **A splitter (D5's third option).** Thilina's ruling: what makes a correct split is task
  specific, and one that works for question answering over pooled passages would be misleading
  shipped as general machinery. The pre-flight refusal and the two checks cover the failure
  without the library deciding anything about the builder's data.
- **A second dogfood requirement that the tool surface be exercised (D4's option b).** Thilina's
  ruling: telling dogfood #2 to use tools contaminates the measurement, since what is under test
  is whether a coding agent finds them. The routing fix is the change; whether it worked is what
  the next cold run measures.

**D8 stands open**, and is the one finding with no disposition. A project-side model call, a
labelling pass, an ablation or a judge still has no envelope.

**One deviation from the sitting, surfaced rather than taken. Closed 2026-08-09 on Thilina's
ruling: the deviation stands and the warning is not built.** The agreed fix for D2 was "(a),
plus the warning from (c)": charge the wait to nothing, and warn when `PacedClient.max_wait_s`
exceeds the run's `max_wall_clock_ms`. Applying (a) makes (c) vacuous, because a pacing wait can
no longer trip the budget at any setting, so the warning would fire on a combination that can no
longer do anything. What is left of the concern is that `max_wall_clock_ms` bounds what the
agent does rather than elapsed time, which `docs/pipeline.md` §5 states where a builder sets the
axis. A run that waits is not silent either: DF2-D3's fix added `warn_unpaced_wait`, which fires
once on the first call held back against a hosted backend, so the visibility (c) was for arrived
at the same seam from the other direction.
