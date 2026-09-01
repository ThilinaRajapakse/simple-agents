# Item 8a — build log

**Kept while building, not reconstructed at the end.** On the precedent of
`item9-build-log.md`.

The design of record is `simple-agents.md` §4.3 and `archive/plan-history.md` item 8a. §1 records what was
measured before the sitting, §2 the sitting, §3 where building sharpened a decision, §4 where it
turned out not to hold, §5 what the build found that is nobody's design, §6 doc consequences, §7
existing tests that had to change.

**Status: sitting held 2026-08-06, building.** Baseline 899 tests at `bc43e02`.

---

## 1. What was measured, before any design

Item 9 §1 is the standard: what an artifact contains is a measurement, and it disagreed with the
document describing it in four places. Ablation reads trajectories and writes a comparison, so
every claim below is read off a file the library produced or off a run made against the live
backend, never off a document.

**How the artifacts were produced.** Three sources.

1. The committed recording `runs/record-eval/eval_bc0422400e88`: 3 examples × 3 rollouts of
   `scripts/record_backend_cassettes.py::eval_pipeline`, seed 41, two nodes, `hunt` an
   `AgentNode` with one tool and `verify` an `LLMNode`. Nine trajectories and nine manifests.
2. Replays of modified pipelines against `tests/cassettes/eval.jsonl`.
3. Live runs against Mistral `mistral-small-2603` on 2026-08-06, `Cassette.record`, same
   examples, same seed, same k. Total spend across every live arm below is under one cent.

### 1.1 An `AgentNode`'s steps are reachable, and the node record is written last

Every `model_call` and `tool_call` inside a node carries `parent_id` equal to that node's
`record_id`, so one execution's steps are collected without reading `sequence` ranges. The
`node_execution` record is written **after** its children: `hunt` on `e1-0` is `sequence` 5,
its calls are 1 to 4.

`node_execution.outputs` holds the value the node returned. `tool_call.inputs` holds the
arguments. `finish` appears as a `tool_call` like any other, so the terminating decision is a
record rather than an absence.

### 1.2 What "a decision" resolves to depends on the definition, and the definitions disagree

Five candidate readings of "which decisions it makes non-trivially versus which it makes
identically every time" (`simple-agents.md` §4.3), each computed over the nine `hunt` executions
and the nine `verify` executions. `within-example` counts the examples whose k=3 rollouts agree;
`across-example` counts distinct values over all nine.

| Candidate | `hunt` (agent) within | `hunt` across | `verify` (llm) within | `verify` across |
|---|---|---|---|---|
| node output, exact | 2 of 3 | 4 | **0 of 3** | 8 |
| tool-name sequence | 2 of 3 | 3 | 3 of 3 | 1 |
| tool calls with arguments | 2 of 3 | 5 | 3 of 3 | 1 |
| step count (model calls) | 2 of 3 | 3 | 3 of 3 | 1 |
| termination reason | **3 of 3** | **1** | 3 of 3 | 1 |

Read off `scripts/`-produced trajectories by
`scratchpad/probe_decisions.py`. Three things fall out of it.

**No two candidates agree on the same node.** On `hunt`, `termination` is invariant over all nine
executions and `tool calls with arguments` takes five distinct values. A single scalar answer to
"is this decision trivial" does not exist; the answer is a property of which decision is asked
about.

**`within-example` and `across-example` are different questions.** Within-example disagreement is
variance, which is what k rollouts exist to measure. Across-example agreement is
input-independence, which is what licenses freezing the node. §4.3's "identically every time"
reads as the second. The first cannot be computed at all when k=1.

**The unstable node here is the `LLMNode`.** `verify` agrees with itself on 0 of 3 examples;
`hunt` agrees on 2 of 3. FT-12's check covers `AgentNode`s only.

### 1.3 A frozen node does not shift any other node's cassette keys

`derive_seed(run_seed, node_id, call_index)` (`context.py:64`) keys a seed on the node and the
index of the call within that node. Replacing `hunt` with a `Deterministic` that makes no calls
therefore leaves `verify`'s call index at 0 and its derived seed unchanged.

Measured: `hunt` frozen to the value it produced on rollout 0 of each example, replayed against
`tests/cassettes/eval.jsonl`. **Seven of nine `verify` calls hit.** The two misses are the
rollouts of `e3` where the frozen value differs from what that rollout recorded, and the miss
names the reason:

```
messages[0].content (recorded 383 chars, now 491 chars)
```

So the cassette misses when the ablation changes the request, and only then. A miss becomes a
failed rollout, which lands in `failure_rate` rather than being reported as a gap in coverage.

### 1.4 An evaluation refuses `Cassette.update`, so an ablated arm cannot top up the recording

`runner.py:347`. The message is item 8's decision, and it applies here unchanged:

> This evaluation runs with `Cassette.update`, which serves the calls already on file and makes
> live calls for the rest. A reported number would then come partly from responses recorded
> earlier and partly from responses produced now, with no way to say which rollouts were which.

An ablated arm is therefore entirely replayed or entirely re-recorded. There is no arm that
reuses the recording for the unchanged nodes and calls live for the rest.

### 1.5 Re-running the same pipeline against the live backend moves accuracy by 0.222

The strongest measurement here, and it decides the shape of the comparison.

| Arm | Source | accuracy | outcomes |
|---|---|---|---|
| oracle | replayed from the committed cassette | 0.556 | missed, missed, correct, missed, missed, correct, correct_abstention ×3 |
| oracle | **the same pipeline, same seed, run live** | 0.778 | correct, missed, correct, correct, correct, missed, correct_abstention ×3 |

`compare(oracle_replayed, oracle_live)` reports **`moved: ['recall']`**, 0.333 → 0.667. That is a
comparison of a pipeline against itself reporting a moved metric.

A second live run of the same pipeline minutes later gave a different outcome vector at the same
0.778, and the frozen arm of §1.6 gave 0.667 on the first run and 0.778 on the second. So the
backend answers the same request differently at a fixed seed, which is
`runs/checkpoint-item5/findings.md`'s result arriving inside a comparison.

**The consequence for ablation.** A freshly recorded ablated arm compared against the committed
oracle cassette attributes provider drift to the ablation. Every measured ablation delta below is
smaller than or equal to this null delta.

### 1.6 Three ablations of the same pipeline, live, with their costs

Same 3 × 3, seed 41, `Cassette.record`, all in one session as the live oracle above.

| Arm | `hunt` becomes | accuracy | cost | model calls | tool calls |
|---|---|---|---|---|---|
| oracle, live | unchanged `AgentNode` | 0.778 | $0.001548 | 28 | 19 |
| ablate to a single call | `LLMNode`, same prompt, no tools | **0.333** | $0.000795 | 18 | 0 |
| freeze to the recorded value | `Deterministic` returning the oracle's per-example output | 0.778 | $0.000350 | 9 | 0 |

`compare()` against the replayed oracle reports `moved: ['recall']` for **both** arms, with the
same 0.333 magnitude as the null comparison in §1.5. Nothing in the output separates the
ablation's effect from the drift.

**The freeze arm is not an ablation.** Its frozen value came from the oracle's own trajectories
and differs per example, so it feeds the node the answer rather than removing its agency. It
measures a ceiling: what the rest of the pipeline does when this node is right. That is a useful
operation and it is a different one.

### 1.7 Removing the terminal node costs nothing and is the largest effect measured

`verify` deleted, `hunt` alone, replayed against the committed cassette.

| Arm | accuracy | cost | calls served from the file |
|---|---|---|---|
| oracle | 0.556 | $0.001927 | 31 of 31 |
| `verify` removed | **1.000** | $0.001477 | 22 of 22 |

Nothing upstream of a removed node changes, so every remaining call keys the same and the arm
runs with no network at all. `compare()` reports `moved: ['recall']`, 0.333 → 1.000, and
`changed: ['nodes', 'prompts.verify']`.

**On the library's own shipped recording the node worth removing is the `LLMNode`, and removing
it makes the agent perfectly accurate on this set.** `verify` was written to check `hunt`'s
answer against the notes and it rejects correct answers. This is item 9 §5.1's shape: the
operation fires correctly on the library's own recording, and the recording is not what a project
should copy.

**The rule the two measurements together give.** An ablated arm is fully replayable exactly when
the ablation changes no request, which is when the ablated node makes no calls in its new form
and every node downstream of it makes none either. Otherwise the arm is a full re-recording.
There is no partial case, by §1.4.

### 1.8 The results file carries no `graph_fingerprint`

FT-12's check reads "produced after the most recent change to the pipeline shape". The digest
that answers that is `graph_fingerprint` (`pipeline.py:1150`), covering node ids, kinds, edges,
loop bounds, error edges, retry policies and output schemas.

It is in **`manifest.json`** and not in `results.json`. What `results.json` `config` holds
instead is `nodes`, a reduced entry per node of `node_id`, `node_kind`, `successors` and `route`,
plus `prompts` and `tools`. So a reader with the results file alone cannot ask whether the shape
changed, and has to open a run directory whose path in the file is absolute (item 9 §5.3).

### 1.9 `compare()` reports no cost and no token difference

`Comparison` carries `metrics`, `shared`, `only_before`, `only_after`, `changed` and `nodes`
(reach and accuracy). `to_record` writes those and nothing else.

The question §4.3 puts is "where does agency actually pay for itself". The three arms in §1.6
span $0.000350 to $0.001548, a factor of 4.4, and `compare()` reports none of it. Every figure it
does report is a rate over `Outcome`.

### 1.10 `changed` carries two keys that are noise in an ablation comparison

`compare(oracle_replayed, ablate_llm).changed` is
`['nodes', 'tools', 'cassette.mode', 'cassette.path']`. The last two differ because the two arms
were run against different cassette files, which is forced by §1.4 and says nothing about the
agent. `docs/evaluation.md` §9 tells a reader that `changed` is where a moved metric finds its
candidate cause.

---

## 2. The sitting, and what it settled

Held 2026-08-06, after §1's measurements and before any code. It did not go the way the
questions were written, and the reason is recorded first because it changed the item.

### 2.1 The item was reframed twice, both times by Thilina, and it is smaller for it

**The design as brought in was `simple-agents.md` §4.3's: read the traces for the decisions an
`AgentNode` makes identically every time, and freeze those.** Two objections landed against it in
order.

**First: inferring "this node does not need agency" from "this node behaved simply on n
examples" is an inference the sample cannot support.** A node that took one search on three
questions may take four on the fourth, and a builder may have chosen an `AgentNode` anticipating
exactly that. The asymmetry is what makes it worse than an ordinary eval-set limitation:
accuracy reports a number and leaves the judgement to the builder, while §4.3's operation
**recommends an action** on the same evidence. A recommendation to remove capacity is a stronger
claim than a number.

This kills the trace-invariance half as a basis for action. What survives is the measurement
half: build the variant, run it, compare. It carries the same eval-set limit as every other
number the library reports and adds no new one. **So the trace reading is demoted to
description**, useful for choosing which variant to try, never a verdict, and the artifact never
says "freeze this node".

That collapsed the sitting's central question. "What is a decision" (§1.2's five candidate
definitions, none agreeing with another) was load-bearing only while something was being inferred
from it. With nothing inferred, it reduces to which facts to print beside a result.

**Second: ablation is one direction of a general operation.** Downgrade and upgrade are the same
comparison with the arms swapped, and so are adding or removing a tool at a node, swapping the
model at a node, changing a prompt, and changing the graph. Thilina asked for both directions and
named three of the axes.

**So the operation is a variant comparison, and ablation is one use of it.**

### 2.2 A variant is another `Pipeline`, and that is what makes an arbitrary graph work

The design brought in assumed the library would take an edit instruction and construct the
modified pipeline. That is what does not generalise: every axis needs its own case, and a
per-node model swap needs a feature that does not exist (`plan.md` §2.2).

The builder writes both pipelines. The library refuses a pair that cannot be compared, predicts
which calls replay, runs both arms in one session, reports the delta with an interval alongside
cost and tokens, and records what structurally differed. Composition, joins, loops, routes and
error edges come for free, because both arms are runs. Nothing is foreclosed: when per-node model
clients land, a variant uses them and this operation needs no amendment.

`ablate()` ships as a convenience that generates the downgrade variants over an existing
pipeline. Thilina's call, and it is thin.

**Comparability refusals, three of them.** Node ids that do not overlap, since per-node figures
key on `node_id` and nothing pairs. Different example sets, which `compare()` already refuses. And
a removed middle node whose successor no longer receives a value matching its declared
`output_schema`: **the graph validates ids, edges, loops and retries and never checks that a
successor accepts its predecessor's type**, so today that fails at run time on every rollout.

### 2.3 The plan is computed before the first call, and a ceiling refuses

§1.3's guarantee is what makes a preview possible: `derive_seed` keys on `node_id` and the call
index within that node, so a node's requests do not shift when another node's call count changes.

> A node whose own configuration is unchanged, and all of whose declared ancestors are unchanged,
> issues byte-identical requests at identical seeds. Every one of its calls replays.

Everything else is "may be live", which is an over-estimate: §1.3 predicted nine live `verify`
calls and seven of them hit, because the frozen value happened to equal what those rollouts
recorded. So the plan is an exact lower bound on the free half and an upper bound on the bill,
with the live half's cost estimated from what the baseline spent on the same nodes. This is item
6's pre-flight-estimate shape.

**Settled: the plan is always computed, always recorded, and the operation refuses to start when
the live half exceeds a ceiling the builder declared.** Rejected: a `dry_run=` flag and a separate
preview call, both of which are things the caller has to remember to use, and the primary caller
is a coding agent. The item 7 checkpoint measured a session reading the taxonomy in full and
tuning four prompt versions on one run each anyway. The library's existing shape for this is a
declared bound plus a refusal that fires before the first rollout (`Budget(max_cost=...)`, and
§4.4's eval-safety refusal).

Two details inside it. **The ceiling counts live requests rather than money**, because cost needs
a configured price basis and a project on a compute basis has no dollar figure. **No default
ceiling**, because a default refuses a legitimate large sweep and teaches a builder to override
reflexively, which is the over-refusal that gets suites switched off. The plan is on the returned
object and in the artifact whether or not a ceiling was set, so a builder who wants to look before
spending gets it without running anything.

### 2.4 An item 8 rule is narrowed, with Thilina's approval

**Settled: the variant arm serves the calls that are provably identical from the baseline's
recording and calls live for the rest**, with the per-rollout split recorded beside the numbers.
This narrows the evaluation's refusal of `Cassette.update` (`runner.py:347`).

The refusal's stated reason was that a reported number would come *"partly from responses recorded
earlier and partly from responses produced now, with no way to say which rollouts were which."*
**For this operation there is a way to say which.** §2.3's guarantee names the calls exactly,
`replayed` is already a field on both call record types, and the manifest already counts hits,
misses and recorded.

The positive argument, which was not anticipated: what this operation reports is a **paired
difference**. Calls served from the baseline's recording are literally identical between the two
arms, so they contribute zero variance to the difference. Re-recording both arms live instead puts
backend drift on both sides, and §1.5 measured that drift at +0.222 accuracy on this recording,
larger than any ablation effect measured.

The cost accepted: the variant arm's absolute accuracy is a mixture figure. It is marked as such
where it is read rather than withheld, since refusing to print a number the file contains is the
kind of thing that gets worked around.

### 2.5 What `changed` cannot say, which is the work this item did not expect

The design approved above is "the builder picks the differences", so the artifact has to be able
to say which difference they picked. `compare().changed` is built by diffing the two `config`
blocks. A variant differing in something `config` does not record produces a real difference with
no cause attached, which is exactly what `docs/evaluation.md` §9 tells a reader to treat as
"moved for a reason the results do not record".

Three holes, measured against `results-oracle.json` and `runs/record-eval/.../manifest.json`.

1. **`changed` cannot name a node.** `_walk` (`compare.py:392`) recurses into dicts and not lists,
   and `config.nodes` is a list. Changing `hunt` from an `AgentNode` to an `LLMNode` reports the
   single key `nodes` carrying the whole before-list and the whole after-list. Fix: key the walk
   on `node_id`.
2. **`config.nodes` carries four fields; the manifest's node entry carries eleven.** Absent from
   the results file: the output schema digest, the context builder, `allow_unknown`, `stream`, and
   the node's budget.
3. **Recorded nowhere the comparison can reach:** `temperature`, `max_output_tokens`, `extra`,
   `over` and `max_failures` (declared on the node, present only on `model_call.params` in the
   trajectory for the first two and nowhere at all for the rest), `finish_check`, and **which
   tools are attached to which node**. `config.tools` and the manifest's `tools` are both flat
   pipeline-wide lists, so removing a tool from one node is invisible when another node declares
   it.

**Tools-per-node is in on its own merit**, Thilina's call, independent of what the comparison
needs it for.

### 2.6 Four judgement calls taken rather than put

Presented as decisions being made rather than questions, and open to veto.

| Call | Why |
|---|---|
| `config.nodes` reuses `Pipeline.manifest_nodes()` rather than keeping its own shape | The two are built in different places and one is a subset of the other, which is how they drifted |
| The missing per-node config goes on the **manifest** node entry, not only in the results file | Every field is declared on the node and recorded nowhere today |
| `finish_check` is versioned by source hash | `route` already is, same precedent, same reason |
| The pipeline-wide `tools` list stays beside the per-node lists | It answers FT-20's question, which is not the union of the node lists |

### 2.7 What was measured and is not being built

`AgentNode`-only coverage. FT-12's check reads "covering each `AgentNode`", and §1.2 measured
that on this library's own recording the unstable node is the `LLMNode` and deleting it takes
accuracy from 0.556 to 1.000. The operation covers every node; **FT-12's check text is not
touched**, and FT-12 is not built here. The taxonomy edit is Thilina's if he wants it.

### 2.8 Scope, unchanged

FT-12 stays unbuilt and there is no seventh check. Format versions move where they have to:
results `0.3` to `0.4`, manifest `0.7` to `0.8`, and a fifth versioned artifact for the
comparison. Each gets a test pinning the literal and a packaging test that its document states
it, which is item 9 §5.2's gap.

---

## 3. What building it changed about the design

### 3.1 Per-node tool sets were never a missing feature, only a missing record

Checked at Thilina's question. `AgentNode(tools=...)` has declared tools per node since item 7,
and the executor has always offered that node's set and no other. What no artifact recorded was
which set. §2.5's third hole is a recording gap, and nothing about how a builder declares a tool
changes.

### 3.4 The node entry gained five fields rather than a flat list of them

`sampling`, `tools`, `finish_check`, `node_budget` and `fan_out`, on the manifest node entry
(`pipeline.py:_node_entries`), and from there into `config.nodes`. Grouped rather than flat
because `_walk` now reports a path: a changed temperature reads as
`nodes.hunt.sampling.temperature` rather than `nodes.hunt.temperature`, which says what kind of
thing moved.

`graph_fingerprint` is unaffected. `_structure` reads a fixed tuple of seven keys
(`pipeline.py:1673`), so widening the entry does not invalidate a suspended run.

---

## 7. Existing tests that had to change

Three at the first increment, and all three are exact-equality assertions on a record shape that
widened. None is a behaviour change.

| Test | What it asserted | Why it failed |
|---|---|---|
| `test_eval_runner.py::test_the_config_says_what_was_measured` | `config["nodes"]` equals a four-field entry | `config.nodes` is now the manifest's own entry |
| `test_run_envelope.py::test_it_records_the_node_shape_and_the_unknown_waivers` | the manifest node entry, field for field | five fields added |
| `test_packaging.py::test_the_evaluation_document_states_the_results_version_the_writer_writes` | `docs/evaluation.md` states the version the writer writes | results `0.3` to `0.4` |

The third is item 9 §5.2's gap doing its job on the first bump after it was closed: nothing
pinned the results version before that test existed, and a bump passed the whole suite. The
document's version literal was edited now rather than with the rest of the doc consequences,
because leaving the suite red through the build is worse; nothing else in `docs/` is touched yet.

One test added: `test_it_records_what_a_node_declared_beyond_its_shape`, over a node declaring a
temperature, a tool, a node budget and a finish check.

### 3.5 The taint rule reads the fields that reach the backend, not the whole entry

The first implementation seeded the taint from any node whose manifest entry differed. On the
first run against the library's own pipeline it planned `verify removed` as **six live calls per
rollout**, and §1.7 had measured that variant at 22 of 22 replayed and zero network.

The cause: deleting a terminal node changes its predecessor's `successors`, so `hunt`'s entry
differed and `hunt` was called changed. `successors` says where the output goes and changes
nothing the backend is sent.

`_REQUEST_FIELDS` is now the ten that decide what a node sends: `node_kind`, `schema`,
`allow_unknown`, `context_builder`, `stream`, `sampling`, `tools`, `finish_check`,
`node_budget`, `loop`. `route`, `on_error` and `retry` are outside it, `retry` because a retried
call repeats the request it failed on and so keys the same.

**A node's status and its calls are reported separately** for this reason. `hunt` in
`verify removed` reads `status: changed, calls: replayed`, which says its entry differs and
none of the difference reaches the backend.

### 3.6 A prompt is versioned outside the node entry, and two guards were wrong about it

Found by a test written for the plan rather than for the refusal. Two pipelines differing only
in the wording of a prompt were **refused as identical**, which is the comparison a builder
makes most often, and the plan called every node replayable.

`Pipeline.manifest_prompts()` is new, beside `manifest_nodes()`, and `plan_variant` compares
both. The identical-pipeline refusal compares both too.

### 3.7 The operation removes the difference it creates itself

Each arm records to its own cassette file, so `cassette.mode` and `cassette.path` differ in
every variant comparison. `changed` is where a builder looks for the cause of a moved metric,
so two entries that are always there are two entries to learn to ignore. `compare()` is
untouched; the variant layer drops them, because it is what created them.

---

## 4. What in the settled design turned out to be wrong

### 4.1 Sixteen guards, disabled one at a time, and one stayed quiet

Fifteen failed the test named against them. The one that did not:

| Disabled | Why the test still passed |
|---|---|
| the predecessor rule, which makes a node fed by a different node live | the fixture removed a middle node whose schema differed, so the reshaped-input refusal fired first |

**Item 9 §4.1's shape exactly**, and item 8f §7.4's before it: the test exercised a path an
earlier guard already covered, so the guard under test never made it pass. The fixture it needed
is a middle node whose declared schema **matches** its predecessor's, so the removal is allowed
and the successor is left unchanged and fed by something else. **16 of 16 now fire.**

---

## 5. Findings

### 5.1 The plan matched the run exactly, in both directions

Run live against Mistral, 3 examples × 3 rollouts, seed 41, the sweep `ablate()` generated over
the library's own eval pipeline.

| Variant | planned | actual |
|---|---|---|
| `verify removed` | 0 live per rollout | **19 of 19 calls served from the baseline recording** |
| `hunt as one call` | 3 live per rollout | 0 of 18 served |

| Arm | accuracy | cost |
|---|---|---|
| baseline | 0.778 | $0.001509 |
| `hunt as one call` | 0.333 | $0.000699 |
| `verify removed` | **1.000** | $0.001165 |

§1.7's finding reproduces through the shipped operation: the node worth removing from the
library's own recording is the `LLMNode`, and the sweep costs nothing to discover it.

### 5.2 `moved` reports `recall` on every arm, including ones that changed nothing

Every comparison above reports `moved: ['recall']`, and so did §1.5's comparison of the baseline
against itself. At n=3 the interval on a paired difference spans a third of the range, and
`recall` has three examples with one absent, so its denominator is two.

The operation reports the interval and the delta and does not editorialise. **A sweep at this n
cannot separate its arms**, which is FT-06's question arriving inside FT-12's, and it is what
`max_live_calls` makes visible: a sweep large enough to conclude anything is a sweep whose cost
a builder should see before paying it.

### 5.3 Nothing checks that a successor accepts its predecessor's type

`Graph` validates ids, edges, loops, retries and reachability, and never compares a node's
declared `output_schema` with what its successors expect. Outside a variant comparison this
surfaces as a run-time failure on every rollout. `_refuse_reshaped_inputs` catches it for a
rewiring; **the general case is untouched and is worth a decision later.**

### 5.4 `moved` reported `True` from a single example, and had since item 8

Found while explaining §5.2 rather than while building. Measured directly on `bootstrap_ci`,
over paired per-example differences:

| n | differences | interval | `moved` |
|---|---|---|---|
| 1 | `[1.0]` | `[1.000, 1.000]` | **True** |
| 2 | `[1.0, 1.0]` | `[1.000, 1.000]` | **True** |
| 2 | `[1.0, -1.0]` | `[-1.000, 1.000]` | False |
| 3 | `[0.34, 0.34, 0.34]` | `[0.340, 0.340]` | **True** |
| 10 | 9 of 10 up | `[0.400, 1.000]` | True |
| 24 | 19 of 24 up | `[0.250, 0.917]` | True |

Where every example moves the same way the resample has no variation to draw on, the interval
has zero width, and `moved` reads that as certainty. **This is `compare()` as shipped at item 8**,
so every regression comparison a project runs could report a verdict off two examples.

**Settled: `moved` is `None` below 20 examples**, the metric is named in `Comparison.undecided`,
and `verdict_reason` says how many carried it. The delta and the interval are still reported. The
shape is item 9's for FT-06: a figure that cannot be supported reports null with a stated reason
rather than a number. **Twenty is Thilina's number**, offered against a proposed 10, and the count
is of examples rather than rollouts, since k rollouts of one example resample together.

Rejected: a small-sample correction on the interval, against `simple-agents.md` §4.2's "nothing
cleverer in v0"; and documenting it, since FT-06 exists because a documented statistical caveat
does not survive contact with a builder in a hurry.

---

## 6. Doc consequences

Written after the build, on the instruction items 8c through 9 followed.

| Document | What it said | What it says now |
|---|---|---|
| `docs/evaluation.md` §10 | did not exist | **New.** `compare_variants()`, `plan_variant()` and what the plan guarantees, `max_live_calls`, `ablate()`, what a variant arm's numbers are made of, and the written comparison. |
| `docs/evaluation.md` §8 | `config` lists four fields per node | The manifest's node entry, plus `config.graph_fingerprint` and what a reader does with it. |
| `docs/evaluation.md` §9 | `moved` is the question of whether the interval excludes zero | **Plus the 20-example floor**, `undecided`, `verdict_reason`, and that the count is of examples. `changed` keys down to the node. |
| `docs/run-envelope.md` §2.1, §2.6 | the node entry's eight fields; no §2.6 | Five more fields, and a new §2.6 saying what each holds. Numbered 2.6 so §3 onward is untouched. |
| `docs/run-envelope.md` §3.4 | "An evaluation refuses this mode" | Plus the one exception and where it is documented. |
| `CHANGELOG.md` | three versioned artifacts | Five. The operation, the verdict floor, and both format bumps with what a project has to do. |
| `docs/index.md`, `README.md` | evaluation covers comparing two versions | Plus comparing two variants of the pipeline. |
| `docs/failure-taxonomy.md` FT-12 | ablation as replaying trajectories with a decision fixed, and freezing what came out identical | **Rewritten on Thilina's instruction, 2026-08-06.** What the library provides, which variants are the project's to choose, the 20-example floor, a check reading a written variant comparison against the current `graph_fingerprint`, and a message per node naming `compare_variants()` and why both arms run together. |
| `dev-docs/simple-agents.md` §4.3 | `oracle → ablate`, trace invariance as a verdict | **Amended with Thilina's approval.** The trace half demoted to description, ablation as one direction of a variant comparison, and the measurement that decided the shape. The original text is kept above it. |
| `dev-docs/plan.md` §3.1 | item 8a not built; no item 8g | Item 8a built and what shipped; **item 8g created and scheduled next**, with its six special cases. Build order updated. |
| `dev-docs/handoff.md` | item 9 built, 8a next | Item 8a built, 8g next, the decisions closed, and the two findings that are nobody's design. |

**FT-12 was rewritten at the end of the item**, on Thilina's instruction, after being flagged and
held. Four things changed. The trace-invariance sentence is gone, since §2.1 demoted that half
from a verdict. "Run the ablation over the trajectories the evaluation already recorded" is gone,
since it is true only for a variant that changes no downstream request. A `What the library
provides` paragraph was added, as 19 of 27 entries carry. And the message takes `<node>` rather
than `<n>`, so the runner emits one finding per untested `AgentNode`, which is FT-06's singular
precedent.

**The check still covers `AgentNode`s only**, which is what the entry is named for and what pairs
it with FT-11. That the node worth removing from this library's own recording is an `LLMNode` is
recorded in the entry as a boundary rather than as a widened gate: `ablate()` produces a starting
set, and which variants matter is the project's. FT-12 remains unbuilt and is not in the v0 seven.

**Not touched, and deliberately.** `docs/trajectory-format.md`, `docs/pipeline.md`, `docs/tools.md`, `docs/context.md`,
`docs/conformance.md` and the model-client pages own nothing this item changed.

**`docs/evaluation.md` is next in Thilina's document review and now carries unreviewed text from
two items**, item 9's and this one's. The version literal in §8 was edited during the build rather
than after it, because the packaging test that pins it would otherwise have held the suite red.

---

## 7 (continued). Existing tests that had to change

Six more at the verdict floor, all in `tests/test_eval_compare.py`, and all because their
fixtures sit below 20 examples.

| Test | Examples | Why it failed |
|---|---|---|
| `test_a_small_change_on_few_examples_does_not_count_as_moved` | 6 | asserted `moved is False`, now `None` |
| `test_the_record_carries_the_interval_and_what_moved` | 12 | asserted `accuracy` in `moved` |
| `test_a_node_that_stopped_being_reached_reports_a_moved_reach` | 10 | asserted `reach.moved is True` |
| `test_a_node_reached_as_often_reports_nothing_moved` | 10 | asserted `reach.moved is False` |
| `test_reach_is_reported_beside_accuracy_so_a_moved_number_has_a_named_cause` | 10 | asserted both verdicts |
| `test_the_record_carries_the_per_node_changes` | 5 | asserted `moved_nodes` |

**Every test in the library demonstrating a moved metric was demonstrating it on a sample that
cannot carry the verdict**, which is the finding rather than an inconvenience. The fixtures move
to 21 to 24 examples, and `test_the_same_agent_twice_reports_nothing_moved` moved from 4 to 24
too: it passed unchanged, because `moved` filters on `is True` and `None` is not `True`, so it
had quietly stopped testing what it names. Two tests were added for the floor itself, one at
n=3 and one at n=1.

**Total: nine existing tests changed across the item, 29 added. 928 tests.**

### 4.2 A test asserted the converse of a rule stated as one-directional

A single failure of `test_a_changed_node_is_called_live` in one full-suite run, clean on the
next six, and clean on 25 consecutive runs of its own file. Chasing it found two things, and the
second is the real one.

**The immediate cause.** `compare_variants` takes `concurrency` from `EvalSuite.run`'s default of
4, and the fixture never pinned it. Rollouts on separate threads share one `FakeModelClient`,
which hands out scripted responses in order without reading the request, so which response an arm
sees is a matter of scheduling. Every sweep fixture now pins `concurrency=1`.

**What that exposed.** With the order deterministic, the arm's behaviour splits cleanly:

| `concurrency` | `verify.replayed_calls` in the `hunt as one call` arm |
|---|---|
| 4 | 0 |
| 1 | 1 |

**The test asserted `0`, and the design says that is not guaranteed.** `NodePlan` documents
`live` as an over-estimate: a changed node upstream can still produce the value it produced
before, and then the request downstream is the one on file and replays. The guarantee runs one
way only, that an unchanged node with unchanged ancestors **will** replay. The test asserted the
converse.

Split in two: the changed node itself always misses, which is guaranteed because its own request
changed; and a node planned `live` may replay, which is now a test naming the over-estimate
rather than a fixture that happened to satisfy it.

**The flake was the symptom and the wrong assertion was the defect**, which is why a test failing
once is worth the hour rather than a re-run.
