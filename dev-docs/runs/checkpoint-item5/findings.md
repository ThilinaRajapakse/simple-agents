# Item 5 checkpoint — findings and triage

The two cold-read sessions described in `archive/plan-history.md` §3.5, analysed. This is the record of what
they produced, what was verified, what was landed, and what is held for a decision.

**Status: session A analysed and its mechanical batch landed. Session B analysed separately;
its findings append to §5 below.**

Nothing here is logged against Phase 2. Neither session is a dogfood, and §3.5's three known
gaps — no tool-authoring guide, no procedure/brief, no context builder — are not findings.

---

## 1. Method

Every claim in `coldread-report.md` was reproduced against the source before being accepted.
The installed wheel in `coldread/.venv` is byte-identical to `src/simple_agents/`, so the
report's line references land on current code. The reproductions are 13 tests; the six that
matter are now permanent tests in the suite (§3), and the rest were throwaway.

One claim did not reproduce as stated (§2, L5). Two findings came out of verifying claims
rather than out of the report (§2, L1's dangling parent link; §4, D8).

**The report's §3 is not evidence.** It is a coding agent praising a library it was told was
written for it. The load-bearing content is its §4 and §5.

---

## 2. Library defects

| | Defect | Severity | State |
|---|---|---|---|
| L1 | `LLMNode` emits no `node` record on failure | HIGH | **Landed** |
| L2 | No `model_call` record when the call raises, any node kind | HIGH | **Landed** |
| L3 | `RunResult.stopped_early` is dead | MEDIUM | **Held — §4** |
| L4 | `max_steps` binds agent-loop iterations only | HIGH | **Held — §4** |
| L5 | Duplicate `node_id`s accepted | LOW | **Held — §4** |
| L6 | `fake_response` not exported | LOW | **Landed** |

**L1, and what verifying it turned up.** `LLMNode.execute` had no `try/except` while
`Deterministic` and `AgentNode` both did. The report tested the credentials-failure path. The
schema-validation path — the most likely `LLMNode` failure, and the one `_validate` writes a
long error message for — was worse: the `model_call` record was written and the `node` record
was not, leaving a `model_call` whose `parent_id` named a record that never existed.
`trajectory-format.md` §2 defines `parent_id` as "the `node` record this belongs to" (the record type is `node_execution` from `0.8`).

Two consequences the report did not draw, and they are the reason this was the first fix:

- FT-13's own check reads "a trajectory log conforming to the format, **with one record per
  node execution**". The library was producing trajectories that fail the check it ships to
  enforce.
- Both existing error-path tests used `Deterministic` only. The error path was tested on the
  one node kind that implemented it.

**L5 did not reproduce as stated, and the real failure is worse.** The report predicts
colliding seeds. Seeds do not collide: two nodes sharing an id share one entry in
`_model_calls`, so `call_index` runs 0, 1. Sharing the counter is what prevents the
collision. The actual consequences are that per-node metrics (FT-08) and ablation (FT-12)
conflate the two nodes, and that **node B's seed depends on how many calls node A made** — so
adding a call to node A silently changes node B's sampling, with nothing in the trajectory
showing why. The refusal message, when it is written, states that reason and not the
report's.

---

## 3. Documentation bugs — the column this checkpoint exists to fill

| | Bug | State |
|---|---|---|
| D1 | `trajectory-format.md` version drift, `0.3` vs `0.4` | **Landed** |
| D8 | `trajectory-format.md` §3 says `termination` is agent-only; the code writes `error` on any kind | **Landed** |
| D5 | `__init__.py`'s example references an undefined `Answer` | **Landed** |
| D9 | The shipped `load_docs` example reads its corpus from `ctx.workspace`, which is empty | **Landed** |
| D2 | `Budget` docstring overstates its reach | **Held — §4, with L4** |
| D3 | No fan-out answer anywhere | **Held — §4** |
| D4 | No example annotates `ctx` | **Held — §4** |
| D6 | Filed as a misreading | Closed, one sentence owed |
| D7 | Filed as an API item, not a doc bug | **Held — §4** |

**D8 was found while fixing L1.** §3's `termination` row read "`agent` nodes only", and
`Deterministic` had been writing `termination: "error"` since item 3. The doc was wrong, not
the code: FT-13 wants to know that a node failed whatever kind it was. No version bump — the
record shape did not change and no `0.4` record was ever written the old way.

**D9 is the better find of the two, and it came from running the example rather than
reading it.** Both the package docstring and `Deterministic`'s docstring showed
`(ctx.workspace / inputs["corpus"]).read_text()`. The workspace is created fresh and empty
per run, so that line cannot ever find a corpus — it teaches a coding agent to read its
inputs from the run's own output directory, and it contradicts the README's description of
`workspace/` as scoped output. An undefined `Answer` is caught on sight; this one type-checks,
reads plausibly, and fails at runtime. Both examples now read from an ordinary path, and
`Deterministic`'s docstring says what the workspace is for.

**The lesson for the rest of the docs.** `prose_check` passed on both examples, and so did
254 tests. Executing a docstring example is a different check from reading it, and no
mechanism currently does it. Worth considering when D4's sweep lands.

**D6, stated precisely.** The report says the docs "never say where the variable is supposed
to come from". They do: `MistralClient`'s docstring says `api_key` "defaults to the
`MISTRAL_API_KEY` environment variable", and the refusal message names it too. What is
genuinely absent is any statement that nothing loads a `.env`. The friction was real — the
session wrote an 8-line loader — but the claim as written is a misreading. The fix is one
sentence in `model-clients.md` §3 saying environment loading is the caller's job. **Do not
add `python-dotenv`**; §10 dependency minimalism against eight lines of loader is not close.

**D7, why it is not a doc bug.** `run-envelope.md` §2.1 does document `totals.cost`, and the
session admits it did not read it. The doc is correct. What invites the mistake is that
`RunResult` hands back a bare `Path` at the end of an otherwise typed API while `Manifest`
sits in the library with no reader.

---

## 4. Held for decision — the four, and why each is held

All four want session B's evidence. None is blocked on anything else, and none should be
landed as a drive-by.

### H1 — `max_steps` (L4, and D2 with it)

**What is true.** `run.charge(steps=1)` appears once in the codebase, in `AgentNode`. Three
`LLMNode`s under `Budget(max_steps=1, ...)` make all three calls and report `completed`. For
a pipeline with no `AgentNode`, `max_steps` never fires and `max_tokens` fires only between
nodes, so such a pipeline is bounded by wall clock and cost alone.

**One correction to the report's framing.** Its own `coldread.py` set `max_steps=None` with
the comment *"Steps are unbounded because neither node kind here can loop"* — it read the
semantics correctly before it probed. "A reader will assume a step is a node execution" is
weaker than the report states. The axis not binding is a library question regardless of
whether the docs are readable.

**Recommendation.** Move `run.charge(steps=1)` from `AgentNode` into `_call_model`, so the
axis means one call, everywhere. Close to behaviour-preserving for an existing `AgentNode`,
which makes one call per iteration in the normal case. Requires an amendment to
`simple-agents.md` §2.3 either way, since a budget axis is changing meaning.

**Why held.** If session B built an `AgentNode`, its budget behaviour across 108 runs is
live evidence rather than reasoning about a hypothetical reader.

### H2 — is a budget trip an error or an outcome? (L3)

**What is true.** `pipeline.py` assigns `stopped_early` and raises `BudgetExceeded` two
statements later, so `RunResult.stopped_early` is always `None` when it is returned. The
manifest records `outcome: "stopped_early"` correctly. `Pipeline.run`'s docstring advertises
the field as a read path.

**The tension is real and predates the field.** `BudgetExceeded` subclasses
`CallerFacingError`, which §2.7 defines as "infrastructure is broken, the run is invalid".
The manifest records `stopped_early` as distinct from `error`. The docstring documents both
readings. One of the three has to give.

**Recommendation for v0.** Keep the raise — a partial `RunResult` would hand back an output
no node produced — delete the field, and point the docstring at `BudgetExceeded.axis` and the
manifest. That is a narrowing of the public API, which is why it is not a drive-by.

### H3 — fan-out (D3)

**What is true.** `pipeline.py`'s docstring says branching "goes inside a `Deterministic`
node, or in an `AgentNode`", which does not answer one model call per item over a
variable-length list: `Deterministic` structurally cannot call a model, and `LLMNode` is
exactly one call. Nothing in `docs/` or any docstring addresses it.

**The report's enumeration is incomplete.** It names `AgentNode` and N pipeline runs. A third
answer exists and is right for many cases: one `LLMNode` whose prompt packs N items into a
single call. None of the three is stated anywhere, which is the actual bug.

**Options.** (a) Document the three workarounds and say a fan-out node is not in v0. (b) A
`Map` node kind — collides with do-not-change #8 and #12. (c) `LLMNode` accepting a list of
prompts, which is (b) in disguise.

**Recommendation.** (a) for v0, and let dogfood #2 decide. This is exactly the case §2.2
argues for extraction over invention.

**Why held, and this is the strongest reason of the four.** Ten articles and fifteen
questions is precisely the shape that wants fan-out. Session B is the best evidence available
on whether documenting the workarounds is sufficient, and it is the one held item whose
answer could reach the do-not-change list.

### H4 — the API-shape batch (L5, D4, D7)

Three items that are individually cheap and collectively a decision about what the public
surface is:

- **L5.** Refuse duplicate `node_id`s. The duplicate-tool refusal in `AgentNode` is the
  template. Message states the real reason (§2), not the report's.
- **D4.** Annotate `ctx` in every example. Mechanical, touches every docstring and the
  README. The annotation is what makes "a `Deterministic` node is never handed a model
  client" visible at the call site, which is the design's central promise and is currently
  invisible where a reader looks.
- **D7.** A typed read path off `RunResult` — `result.cost`, `result.tokens`,
  `result.outcome` — or `Manifest.read(path)`.

**Why held.** Batching them is worth more than landing them one at a time, and session B's
friction section will say which of the three actually cost someone time.

### Also carried, not one of the four

**`params` omits `tools` and `output_schema` (report §4.4).** Confirmed:
`params_for_record()` returns four keys; both were sent, and the cassette key includes both,
so replay is correct. It is a recording gap, and FT-12 ablation cannot ask which decisions
the model made non-trivially from a trajectory that never says what the options were. The fix
changes the record shape, so it travels with the format's next revision rather than alone —
and item 7 is when the offered set actually starts varying per call.

**A run that fails a model call now reports its cost as unknown.** The failed call's token
counts are `unknown`, and `total_cost`'s stated rule is that one unknown call makes the total
unknown, because "a total that dropped the calls it could not price would report less than
was spent". So `totals.cost.value` is `null` on such a run rather than the partial cost of
the calls that succeeded. This is the format's own discipline applied and it is the honest
answer — a call that timed out mid-generation may have spent real tokens — but it is a
visible change to what an error-path manifest says.

**Failed calls carry no duration.** L2's record sets `ended_at: null`, per §2's "null if the
record was written for an operation that never completed". Under a compute basis that makes a
timeout's device time unattributable: `_compute` returns unknown rather than a figure. That is
the honest answer and it is what the format already specified, but a future revision may want
a duration on a call that failed after real device time. Noted, not scheduled.

---

## 5. Session B

Shape unprescribed, ten articles, fifteen questions. It wrote a report on request, after the
build, marking every claim `[verified]` / `[recalled]` / `[inferred]`. Everything below was
checked against the artifacts independently before being accepted.

### 5.1 What §3.5 asked, answered

**It reached for an `AgentNode`, and it can say why.** Two nodes: `Deterministic` for question
normalisation and the catalogue, `AgentNode` for retrieval and answering. Its stated reason is
the right one and it is specific: *"the second query's text is a value the first lookup
returned — you cannot write that query in advance."* It considered and rejected the fixed loop
with an `LLMNode` inside, naming it as the library's own example of something that looks
agentic and is not, and rejected stuffing all ten articles into one prompt while noting that
option *"is the design that would have won a scoring contest today"*. Rejecting the
higher-scoring design because it makes the corpus's property untestable is the judgement the
node-kind split exists to provoke.

**`unknown` survived end to end.** Tagged object with a reason, in the trajectory as well as
the report JSON. The session states it would have written `answer: str | None` unprompted and
that the library forced the branch: *"the single most useful thing in this agent"*.

**The four unanswerable questions, scored.** Run 6, the run it stands behind: 4/4 correct
`unknown`. Across all seven answer sets, 28 chances at questions 12 to 15, **the agent never
once invented a value**. Q13 is the deliberate trap — article 002 gives Corveth's headcount of
40, so a pattern-matcher has something plausible and wrong to reach for — and it returned
`unknown` in every run.

Three entries recorded a value rather than `unknown`, and all three are absence written as
prose in the answer field, not fabrication: *"The acquisition price was not disclosed."* The
content is correct and the branch is wrong, which is the FT-09 failure exactly — to a scorer
reading the field, a correct absence in the answer branch is indistinguishable from an
asserted answer. A fourth apparent case, run 1's Q15, is a 429 that killed the run, not a
model answer.

**Run 6 against ground truth:** 9 of 11 answerable questions fully correct, 1 partial (Q2
attributes the grant scheme's £50,000 cap to Corveth's actual grant, which the session flagged
itself), 1 recall failure (Q6, the three-hop question, returns `unknown` where the Ostley
Institute is the answer). No false confidence anywhere.

### 5.2 The determinism finding — verified, and it is the important one

**Verified exactly, and refined.** The cassette holds 603 entries over 376 distinct keys. 74
keys were recorded more than once; **30 have more than one distinct recorded response**, one
with three. All 30 are `model_call`; no tool call varies. The stored requests within each
varying key are byte-identical — 0 mismatches — at `temperature=0.0` with a fixed derived
seed.

**One correction, and it does not rescue the claim.** 7 of the 30 differ only in the
provider-generated tool-call `id`. **23 are semantically different**: different query text,
and in one case a different number of tool calls in a turn. So the magnitude is 23, not 30,
and the finding stands.

**What it defeats.** `docs/run-envelope.md` §5: *"re-running at the same seed reproduces the
same sampling, which is what makes a cassette recorded from one run replay against another."*
That is false against this provider, stated without qualification, in a document a builder
reads to decide whether to trust a replay. FT-07's value proposition — control seeds so a
surprising failure can be re-run — does not hold on a hosted API that treats a seed as
best-effort.

**A second route to the same failure, not in the report.** `cassette.py` resolves a key
recorded more than once to the *last* occurrence in the file. Session B accumulated six live
runs into one cassette, so run 4 — the only run with both Q4 and Q6 correct — cannot be
replayed from it: every key run 6 also touched now serves run 6's response. Neither seed
replay nor cassette replay recovers an earlier run. The behaviour is documented at
`cassette.py:20`; its consequence for an accumulating cassette is not, and it is the same
promise failing by a different mechanism.

**What is not defeated.** Replay determinism itself. Run 7 replayed run 6 byte-identically
with `hits: 9, misses: 0` and no network. The cassette does what §3 claims. It is §5's claim
about *seeds* that is wrong, and the two were welded together in one sentence.

### 5.3 The methodological admission, and why it is the most valuable thing here

The session tuned four prompt versions against one run each, having read
`docs/failure-taxonomy.md` in full — including FT-05, FT-06 and FT-07, which say precisely why
that does not work. It recognised the problem at v4 and stopped, about two versions late, and
states it plainly: *"three of my four prompt versions were tuned on noise"* and *"I measured
stability exactly once, by accident"*.

**This is not a finding against the library and it is not a §3.5 known gap being rediscovered.
It is behavioural evidence for `simple-agents.md` §3.1.** A capable reader read the document
describing the failure, agreed with it, and committed it anyway within the hour. That is the
argument for why a conformance suite has to be executable — *"prose instructions produce
drift; a failing test produces feedback the agent acts on without a human in the loop"* — and
it is worth more than session A's §6.2 self-report, because it is something the session did
rather than something it claimed it would have done.

Two qualifications, so this is not overclaimed. The builder had explicitly asked for a working
agent rather than a measured one, so the absence of an eval harness was instructed. What was
not instructed was comparing prompt versions on n=1, which is measurement done badly rather
than measurement declined. And a single session is an anecdote; it points at the meta-eval in
`items/meta-eval.md` rather than settling anything.

### 5.4 New findings

| | Finding | Column |
|---|---|---|
| S1 | `run-envelope.md` §5's seed claim is false for hosted APIs | Documentation |
| S2 | An accumulated cassette can only replay its most recent run | Library, by design; undocumented consequence |
| S3 | Shipped docs describe the eval runner in the present tense | Documentation |
| S4 | `Retry(max_attempts=3)` default versus the documented free tier | Library |
| S5 | The `AgentNode` loop is closed: no per-step hook, and `finish` cannot see run state | Library, design. **Per-step hook shipped at item 6**, see §6; `finish` remains item 7 |
| S6 | `totals.tokens` has no total, and nothing says so at the read site | Documentation |

**S3, precisely.** `tools.py`'s module docstring says *"The eval runner reads the declared
class and refuses to execute anything non-replayable inside a rollout"*, and FT-20's check
reads **"Enforced"**. There is no eval module in the package and no `simple-agents` binary —
verified. The taxonomy uses "Enforced" for two different states: FT-09, FT-18 and FT-19 are
enforced by construction *today* (§465 says so), and FT-20 is enforced by a component that
does not exist. A builder reading FT-20 concludes the protection is in force. This is the same
class of bug as D1: a shipped document asserting something the code does not do.

**S5 is the one that constrains the design.** The session wanted to validate citations at
finish time — *"you cited an article you never opened, try again"* — which is exactly the
correction the loop exists to deliver. `FinishTool.validate` receives only the arguments, and
a tool closure over per-run state leaks across runs because one pipeline is reused. The check
moved to after the run, where it can only report and the model never hears it. Its words:
*"the design compromise I am least happy with, and it is forced by the library."* Related, and
independently reported: the check it was forced to write post-hoc, `unverified_sources`, has
never fired in a live run, so it is unexercised end to end.

**S4.** `adapters/_http.py` defaults `max_attempts=3`; `model-clients.md` §6 documents the
free tier as 50 requests and 50,000 tokens per minute. Session B's first full run died on
question 15 of 15. The default and the documented tier are in tension, and the run that finds
out is the expensive one.

### 5.5 Not findings

- **No procedure, brief, gates, eval machinery** — `archive/plan-history.md` §3.5 known gaps. The session's
  §8.1 asks for labels and a rollout harness, which is items 8 to 12 arriving on schedule.
- **The catalogue leaking the first hop**, and `unverified_sources` being unexercised. Both
  are the session's own build decisions, reported against itself, and neither is about the
  library.
- **No `.env` loader, no `python-dotenv`.** Same as D6. It wrote its own parser and did not
  complain.
- **Redaction unverifiable.** Correct observation, wrong target: the key travels only in an
  HTTP header the adapter builds, and headers are not records. Nothing to fix; worth a
  sentence in `run-envelope.md` §6 saying what the rules do and do not see.

### 5.6 What session B says about the held four

- **H1 `max_steps`.** It set `max_steps` on both the node and the run budget and used the axis
  correctly, with a comment in `config.py` explaining what the node records on termination. It
  reported no confusion. That is a second reader getting the semantics right unprompted, which
  weakens the documentation reading of L4 further and leaves the substantive issue — the axis
  does not bind an `LLMNode`-only pipeline — untouched. **Recommendation unchanged: charge a
  step per model call.** No evidence against it, and no evidence the current naming misleads.
- **H2 `stopped_early`.** Direct evidence. `runner.py:167` reads `result.stopped_early` and
  propagates it into every entry of every report, where it is structurally always `null`. A
  builder read the docstring, believed the field, and shipped it. **Fix it.**
- **H3 fan-out.** The predicted failure, in its predicted form. Fifteen questions became
  fifteen runs, 106 run directories in total, one manifest each, and no single artifact
  describing the task. It also produced S5's leak problem: one pipeline reused across fifteen
  runs is why per-run tool state was unavailable. **The v0 answer should be written, and it
  should name the three workarounds rather than only the two the report found.**
- **H4 API shape.** Two of three confirmed. `runner._read_back` is the bespoke manifest reader
  D7 predicted, and it got `totals.tokens.total` wrong on the first attempt (S6). `ctx` is
  annotated `NodeContext` on the `Deterministic` node and falls back to `Any` on the
  `AgentNode`, so `AgentContext` was not discoverable — mild support for D4. No evidence on
  duplicate node ids; it used named functions throughout.

---

## 6. Why the loop is closed, and what may open

Recorded because it was nearly changed on the strength of session B's complaint, and the
reason not to is not obvious from the code.

**Session B's request is legitimate.** It wanted to tell the model "you cited an article you
never opened, try again" at finish time, which is exactly the correction an `AgentNode` loop
exists to deliver. It could not, and moved the check to after the run where the model never
hears it.

**Why tools cannot see run state.** A tool call is keyed in the cassette by tool name,
version and arguments. That key identifies the call only if the tool's output is a function of
its arguments alone. A tool that reads mutable run state can return two different things for
one key, and the cassette then serves whichever was recorded first for a call that should have
produced the other. Tool purity is what makes replay sound, so opening this up would trade a
correctness property for a convenience. It stays closed, and the reason belongs wherever the
tool contract is documented at item 7.

**Why `finish` is different, and can open.** `finish` does not go through the cassette at all;
`_run_tool` validates it inside the library because there is nothing external to replay. So
giving `FinishTool.validate` access to run state costs nothing in replay soundness. That is
the half of session B's request that should be granted, and item 7 is where it lands, with the
tool contract.

**The general shape of the rule:** anything replayed through the cassette must be a function
of its recorded inputs; anything the library evaluates itself may read the run. Item 6's
context builder is on the second side of that line and item 7's tools are on the first.

**What item 6 added to this, and it makes the rule exact rather than merely stated.** The
context builder's *product is the keyed material*: `messages` is in the cassette key. So a
builder that reads mutable run state does not produce a wrong replay, it produces a
`CassetteMiss`, which is loud and correct. That is the mechanical difference from a tool,
whose key is its arguments and whose state-reading therefore serves a response recorded for a
different call. The permission granted here is not a relaxation of the rule; it is the rule
producing a different outcome because the keyed surface is different.

**Half of S5 is now answered.** The context builder runs once per model call and receives the
whole accumulated conversation including tool observations, so it is the per-step hook session
B said was missing: a project can inject a reminder before any turn. What it is not is
finish-time validation, which still needs `FinishTool.validate` to read run state. That stays
at item 7 with the rest of the tool contract, so the signature changes once rather than twice
a week apart. Considered for item 6 and held for exactly that reason.

**S5 closed at item 7, and the rule above was narrowed while closing it.** `AgentNode` now
takes a `finish_check`, called after the schema validates, receiving the answer and an
`AgentContext` carrying every tool call the node has made. Session B's exact case is a test:
an answer citing a document the agent never read comes back to the model as a failed `finish`
and the loop continues.

**The wider half was answered too, against the recommendation above.** The paragraph beginning
"Why tools cannot see run state" states a rule broader than its reason. The reason is only that
**a cassette key must identify the answer**, and a tool keyed by its arguments alone does not
satisfy that whenever it can answer differently at two moments. Item 7 satisfied it two other
ways instead of banning the category: the key gained an occurrence count, which makes any
within-run impurity replay correctly; and a tool whose signature asks for a handle is not keyed
at all and runs again on replay, which is how a tool may call a model or write into the run's
own directory. `simple-agents.md` §8.2 carries the amended contract, and `archive/plan-history.md` item 7
carries the sequence. The generalised rule in the paragraph below survives unchanged; what
changed is that it now has three instances rather than two, and the third is a tool.

---

## 6b. Fan-out, built rather than documented (H3 resolved)

**Decided against the recommendation in §4/H3, and the reasoning is worth keeping.** The
proposal was to document three workarounds and defer building until dogfood #2, on §2.2's
"extraction beats invention" argument. That was overruled: fan-out is a reasonable thing to
expect, both sessions met it, and the shape turned out to be forced rather than invented.

**It is a property of a node, not a fourth kind.** `LLMNode(..., over="documents")` keeps
`node_kind` as `llm` and leaves do-not-change #8 intact. Nothing in the trajectory format
needed changing: one node record with N `model_call` children is exactly what an `AgentNode`
already emits.

**Where the line falls, and it is worth stating because it tells a builder when they have
outgrown the pipeline.** A pipeline covers a variable *number of calls*; a graph covers a
variable *set of nodes*. A chain of fan-outs whose sizes are each computed by the preceding
node is still linear, so data-dependent counts never need a graph. A data-dependent *path* is
the model deciding, which is what `AgentNode` is for. Do-not-change #12 is untouched, and the
fan-out is sequential for the same reason: concurrency would be a scheduler.

**Failures are collected, not fatal, and the `unknown` boundary is structural.** The first
proposal was fail-the-node, matching `LLMNode`'s existing rule that a schema violation ends
the run. Overruled as excessively punishing for a batch, with the correct condition attached:
a failure must never be readable as an `unknown`.

The separation is by type rather than convention. An item whose validated output *is*
`Unknown` is a **success** — the model answered, and the answer was absence — and appears in
`values`. A failed item has no schema instance at all and appears only in `failures`, with its
index, its input and its error. There is no code path that converts one into the other, which
is what FT-09 and FT-10 need: an evaluation reads the first as a recall result and the second
as a broken run, and conflating them would make a broken call score as a correct report of
absence.

Two supporting decisions:

- **`values` drops failures, so the node record carries both.** A caller that ignores
  `failures` loses them from its own data flow and cannot lose them from the trajectory. That
  is FT-13's argument applied to a new place.
- **`max_failures` is opt-in, default `None`.** Systematic failure — a wrong schema, bad
  credentials — otherwise produces N identical failures and burns the batch. `CassetteMiss`
  and `BudgetExceeded` always propagate rather than being collected: neither is the item's
  failure, and both mean the run is not the run that was asked for.

**The `max_steps` correction had to land first.** Before it, a fan-out over ten thousand items
would have been unbounded, because the axis was charged inside the agent loop rather than per
model call. The run budget is now also checked between items, so a fan-out cannot outrun the
run.

---

## 7. Elicitation questions these sessions earned

Each is a question a builder should have been asked, that nobody asked, where the absence
caused something visible. **Every one ships with a way to answer it.** A required question a
builder cannot answer cold is a wall, and a wall is how gates get disabled — session B
invented three of its four budget numbers and said so, which is what an unscaffolded question
produces.

| Question | Scaffold that makes it answerable | Evidence |
|---|---|---|
| Does a wrong answer cost more than a missing one? | Two concrete scenarios in the builder's own domain; pick which is worse. Not asked in the abstract | The corpus ground truth says to report these two rates separately. Session B never separated them, and its own §6 confidence list mixes them |
| How will you know a change helped? | Offer the default — k rollouts before and after, with the interval — and let the builder override | Four prompt versions judged on one run each, with cassette evidence that the variance exceeded the effect |
| What should the four budget numbers be? | Run one example, read what it consumed, propose numbers from that. Derivable rather than guessable | Session B §7: "three of my four numbers are invented ... the refusal produces a decision, not an informed one" |
| Who writes the correct answers, and when? | Offer the two routes: the builder writes them now, or the first run's output is reviewed and becomes the labels | Session B asked the builder this unprompted before it would start. The library should supply the question rather than relying on the coding agent's initiative |
| Is anything in what you feed the agent giving away the answer? | A checklist of the usual leaks: filenames, ids, ordering, metadata, section headings | Session B put descriptive filenames in every prompt, leaking the first hop of four questions. It also caught and fixed a heading leak in the question file, so it knew the failure class and missed its own instance |
| Do you need to reproduce a specific past run? | If yes: record a cassette, and know that the seed alone will not do it on a hosted API | `run-envelope.md` §5 promised what the provider does not deliver |
| How much of the model's context window may this node fill, and what should happen when it is exceeded? | Two derivable halves. For the number: read `max_context_length` (Mistral) or `max_model_len` (vLLM) from `GET /v1/models`, run one example, read what it consumed, and set the limit from those two with headroom for the output. For the behaviour: offer the three answers, stop the run, drop what the task can spare and record each drop, or give the node less | Added at item 6. Overflow is foreseeable rather than broken infrastructure, so the response is a builder decision. The library's default stops the run and drops nothing, which is right as a default and is not a judgement about what a shipped agent should do (FT-17) |

**The last one is the pattern to copy.** We cannot make the provider deterministic, and we can
make sure no builder discovers that after they have designed around it. That is elicitation
doing the job conformance cannot.

---

## 8. The positioning argument, against `simple-agents.md` §1

The report's §6 argues about whether the library is worth using at all. **It defeats no
rationale in §1, and it confirms two.** Recorded here because a confirmation this specific is
worth as much as the defect list.

**What it confirms.** §6.2's table — and its last row, "Refusal to run without a budget / an
`unknown` variant / a side-effect class → **Nothing**. I know about all three and I would
still have skipped all three for a first pass" — is direct support for §1.2 row 4 (not a
convenience wrapper) and §1.5 (trust audience, not accessibility). §6.5's break-even, "the
moment you intend to run the thing more than once and compare the results", is §1.3's
improve-your-agent loop restated by something that had not read §1.3.

**Why it should not be banked yet.** It is a self-report from an instance of the model the
library was written for, having just read the failure taxonomy, told it was testing a library
aimed at it. It is the weakest kind of evidence for that particular claim. **A cheap control
exists and should be run before §6.2 is cited anywhere:** a second cold session, same task,
no library, then score both artifacts against the taxonomy. One session, and it converts a
self-report into a measurement.

**Where §1 has a hole, which is more useful than the defect list.** §1.2's table names
orchestration frameworks, smolagents, training engines, and convenience wrappers. It does not
name the category everything shipped to date actually competes with: LangSmith, Langfuse,
W&B Weave. The built surface is trajectory, manifest, cassette. An evaluator will file it
under tracing first and ask why not Langfuse, and §1 has no prepared answer.

The report supplies a good one, and it is not a new argument — it is §1.3 applied: theirs is
a hosted service with a schema you reverse-engineer from the SDK, this is a local file the
project owns with a schema documented before the code was written; and theirs samples, which
§1.3's "a sampled trajectory is worthless as SFT data" already answers. **Proposed: a fifth
row in §1.2 for observability platforms, and a sixth for prompt optimizers (DSPy)** — §1.2
names training engines but not optimizers, and someone could plausibly want both. Not made;
`simple-agents.md` is the design of record and needs approval.

§6.4's "any backend other than Mistral or vLLM" is a real adoption objection and does not
defeat §2.5's dual-backend rationale, which was about what a single backend encodes silently.
Both are true at once.
