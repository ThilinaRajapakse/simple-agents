# Build log — memory

`archive/plan-history.md` §1.5 is the brief. Started 2026-08-10.

**What the item is for.** The 2026 survey of agent evaluation treats memory as one of four
capability dimensions, and LangGraph ships LangMem as one of five prebuilts. The library has no
expression for it. `build-logs/memory-build-log.md`'s original note asks for "nodes being
allowed to read and write to memory", which is ambient shared state, and `archive/plan-history.md` §1.5 says a
design has to say first whether it is that or a declared edge.

---

## 1. What was measured before anything was designed

Five probes. Everything in this section is a run against the library at `ed5bc02`, not a
reading of it. The scripts are in the session scratchpad and each is described by what it did.

### 1.1 A memory store can reach a node the eval runner would refuse, by two different routes

`simple-agents.md` §4.4 and do-not-change #5 say the eval runner refuses a tool whose effects
reach outside the run before the first rollout.
[`runner.py` `_tools_of`](../../src/simple_agents/evaluation/runner.py#L2828) walks
`declared_nodes()` and reads `node.tools`.

**Measured.** The same operation, storing a fact now for a later run to read, built three ways.

```
A. memory as a WRITES tool, store is a directory outside the run
  declared_nodes : ['save', 'done']
  _tools_of      : ['remember_to_disk']
  reaches outside: {'remember_to_disk': False}
  would refuse   : False
  manifest tools : ['remember_to_disk']

B. memory as a WRITES tool, store is a process-wide dict
  _tools_of      : ['remember_in_process']
  would refuse   : False

C. memory read and written by a node function directly, no tool
  declared_nodes : ['save', 'done']
  _tools_of      : []
  would refuse   : False
  manifest tools : []
```

**Two distinct holes, and they are not the same hole.**

- **C is invisibility**, and it is `archive/plan-history.md` §1.4's tool-body defect again in a different
  costume. A `Deterministic` function closing over a store is in no walk, writes no record, and
  appears in no artifact. Python cannot detect it.
- **A and B are worse, because they are visible and still not refused.** The tool is in
  `_tools_of`, in the manifest, and in the trajectory. It is not refused because
  [`SideEffectClass.reaches_outside_the_run`](../../src/simple_agents/tools.py#L88) is false for
  `WRITES`, and `docs/tools.md` §1.4 says `WRITES` means "confined to the run's own workspace".
  A store that outlives the run is not confined to it. **There is no class that describes it**:
  `WRITES` is a false declaration, `IRREVERSIBLE` is true and refuses every evaluation, and the
  four classes were drawn before a store existed to classify.

### 1.2 §8.2's occurrence count does hold, and it holds for the intra-run case only

`archive/plan-history.md` §1.5 says the cassette question "§8.2's occurrence count and handle rule already
address". Checked rather than trusted, since the delegation item found the same §8.2 claim right
for a different reason than its brief gave.

**Measured**, on `recall` / `remember` / `recall` in one run, recorded and then replayed against
a store that had since been changed to something else:

```
live      : {'before': '', 'after': 'the-answer'}    store after: {'fact': 'the-answer'}
replayed  : {'before': '', 'after': 'the-answer'}    store after: {'fact': 'SOMETHING-ELSE'}
entries   : 3, distinct keys: 3
    recall   {'key': 'fact'}                      occurrence=0 -> ''
    remember {'key': 'fact', 'value': 'the-...'}  occurrence=0 -> 'stored'
    recall   {'key': 'fact'}                      occurrence=1 -> 'the-answer'
```

**The claim survives for one run.** Two identical `recall` calls with two different answers got
occurrence 0 and 1, stored under distinct keys, and the replay reproduced both against a store
that now says something else. This is `now()` again, which is the case §8.2 was written for.

**One fact the brief does not name: a replayed memory write does not happen.** `remember` was
served from the file and its body never ran, so the store was untouched by the replay. That is
correct for reproducing one run and it means a replayed evaluation neither grows the store nor
reports that it did not.

**What the occurrence count does not reach is the unit above a run.** Rollouts are what an
evaluation resamples, and §8.2 has nothing to say about two of them.

### 1.3 Rollouts sharing a store make one measurement produce several numbers

[`runner.py`](../../src/simple_agents/evaluation/runner.py#L244) `__init__` runs rollouts through a
`ThreadPoolExecutor` at `DEFAULT_CONCURRENCY = 4`, over `self.pipeline`, which is one object.
Anything a node closes over is therefore shared by every rollout and written concurrently.

**Measured.** Five identical evaluations, k=2 over n=4, seed 41, one store, the pathological
case where each rollout can answer out of another rollout's write:

```
attempt 1: writer=e2-0  accuracy=0.250  eval_id=eval_997750beb04f
attempt 2: writer=e2-1  accuracy=0.500  eval_id=eval_997750beb04f
attempt 3: writer=e2-1  accuracy=0.250  eval_id=eval_997750beb04f
attempt 4: writer=e1-1  accuracy=0.250  eval_id=eval_997750beb04f
attempt 5: writer=e1-0  accuracy=0.250  eval_id=eval_997750beb04f
```

**One `eval_id`, three different writers, and accuracy moved.** `eval_id` is derived from the
seed, the split, k and the model, which is the library's own statement of what identifies a
measurement. Nothing in `results.json` distinguishes attempt 2 from attempt 3. The bootstrap
interval is computed over rollouts as if they were exchangeable, and here rollout 1 is the only
one that did any work.

This is the strongest thing measured at this item. It is not an argument about ambient scope; it
is what a store outliving a rollout does to the number the library exists to produce.

### 1.4 A memory write in flight is outside the `ValueCodec`'s problem, and that is the finding

`suspension.py`'s `ValueCodec` refuses a value on an edge that cannot cross a suspend point.
A store is on no edge, so nothing refuses anything.

**Measured**, across two processes, which is the case
[`suspension.py`](../../src/simple_agents/records/suspension.py#L1) exists for:

```
process 1  suspended at: load
           store in the writing process: {'fact': 'written-before-the-suspend'}

process 2  store in the resuming process: {}
           resumed output: {'recalled': ''}
           outcome: completed
```

The write was lost, the run completed, and nothing was raised or recorded. The only mention of
the write anywhere in `suspension.json` is inside `counters.tool_occurrences`, which holds the
arguments of a call already made for cassette-key bookkeeping, not the store's content:

```
{"arguments": {"key": "fact", "value": "written-before-the-suspend"},
 "name": "remember", "version": "sha256:7e189e7f16ce"}
```

So: a value on an edge that cannot cross the point is a `CallerFacingError` naming the node,
and a store that cannot cross the point is silence and a wrong answer.

### 1.5 Redaction keeps the redacted copy and the store keeps the credential

`simple-agents.md` §10 requires the record path to fail closed, and `redaction.py`'s
`UNWALKED_FIELDS` is what implements it: the enumerated set is what gets skipped.

A tool is handed the raw arguments; the record path redacts a copy
([`context.py` `call_tool`](../../src/simple_agents/context.py#L593) redacts `keyed` into
`stored`). So a tool that writes its argument to a store of its own writes it unredacted.

**Measured**, with a key matching the built-in `sk_prefixed_key` rule:

```
secret in the trajectory : False
secret in the cassette   : False
secret in the store      : True

tool_call inputs     : {"note": "... the key [redacted:sk_prefixed_key] in a code sample"}
tool_call redactions : ['inputs.note']
store contents       : {"note": "... the key sk-livekey0123456789abcdefghij in a code sample"}
```

**The record announces that it removed something, and the durable copy kept it.** The trajectory
is the artifact that gets deleted; the store is the artifact that outlives every run and is read
back into the next one.

### 1.6 One cassette serves every rollout, and a recall is the call that collides

The cassette key is name, version, arguments and occurrence **within one run**
([`context.py` `_note_tool_occurrence`](../../src/simple_agents/context.py#L1227)). It carries no
run id and no example id, and an evaluation shares one cassette file across every rollout
(`runner.run` copies the envelope with `with_run_dir` alone). So two rollouts making the
identical call collide on one key, and `docs/run-envelope.md` §5 says replay serves the first
response recorded for a key.

**Measured**, on a tool whose answer depends on which rollout is asking, which is what a memory
seeded per rollout is, at k=1 over n=4 and concurrency 1:

```
recorded : {'e1-0': 'q1', 'e2-0': 'q2', 'e3-0': 'q3', 'e4-0': 'q4'}   accuracy 1.00
           cassette counts: recorded=4, diverged=3

cassette : 4 entries, 1 distinct key
           recall {'key': 'seed'} occurrence=0 -> 'q1'
           recall {'key': 'seed'} occurrence=0 -> 'q2'
           recall {'key': 'seed'} occurrence=0 -> 'q3'
           recall {'key': 'seed'} occurrence=0 -> 'q4'

replayed : {'e1-0': 'q1', 'e2-0': 'q1', 'e3-0': 'q1', 'e4-0': 'q1'}   accuracy 0.25
           cassette counts: hits=4, misses=0, diverged=0
```

**The recording sees it and the replay does not.** `diverged: 3` is in the recording's results,
which is the mechanism working. The replay reports four clean hits, no misses and no
divergence, and answers three of the four rollouts with a fourth rollout's value.

This is not memory's defect and it is not new. It reaches any tool whose answer varies per
example under identical arguments, which today is `now` and a `consult` asking one fixed
question. **What memory changes is the frequency**: every recall is a fixed-key call, so the
collision goes from exotic to routine.

### 1.7 Found while reading: the manifest counts four of the five record types

Not this item's, and reported rather than fixed.
[`manifest.py` `to_json`](../../src/simple_agents/records/manifest.py#L347) enumerates the per-kind
breakdown as a literal tuple of four names, and the delegation item added a fifth type.

**Measured**, on a run that emitted two `delegation` records:

```
manifest counts : {"records": 12, "node_execution": 5, "model_call": 4,
                   "tool_call": 1, "consultation": 0}
trajectory      : {"node_execution": 5, "model_call": 4, "delegation": 2, "tool_call": 1}
```

`records` is right, because it sums `_counts`. The breakdown is a hard-coded list, so
`delegation` cannot appear in it. `docs/run-envelope.md` line 92 says the field is "`records`,
and one count per record type", which is now false.

It is the same shape as the defect `simple-agents.md` §10's fail-closed rule was written about:
an enumeration in one module that has to be remembered when a field is added in another.

---

## 2. The design

Put to Thilina 2026-08-10 as six decisions and three questions. All six approved as recommended,
and two of the three questions added scope to this item rather than deferring it.

### 2.1 What memory is (D1)

**A declared resource reached through a recorded call.** Neither of the two things `archive/plan-history.md`
§1.5 names, because both are intra-run: an edge is a relation between two nodes of one pipeline
in one walk, and memory's writer and reader are in different runs, so there is no edge for a
declaration to become. §1.5 of this log is the argument; item 8c's three reasons do not move.

A node reads memory through `ctx.call_tool` and the value travels on an edge like any other:

```python
def load_preferences(inputs, ctx):
    return {"question": inputs["q"], "known": ctx.call_tool("recall", key="preferences")}
```

**No `ctx.memory`.** A context builder reading a store would be ambient by construction, since
its product is the keyed material (§8.2). Forcing it through a call puts the content in the
record twice: once where it was read, and once as the next node's `inputs`.

**Record type: `tool_call`**, parented to the reading node's `node_execution`. The delegation
item's own test decides it: a fifth type was needed there because `side_effect_class` would have
been a falsehood, and a memory call has an honest one under 2.4. A consequence of that item
worth naming: a write made inside a delegated worker is attributable to the invocation that made
it, because the node record's `parent_id` is the `delegation`.

### 2.2 The library owns the store (D2)

```python
env = RunEnvelope(run_dir="runs/", memory=MemoryStore("memory/", scope=f"user-{user_id}"))
```

A directory store, sibling to `UrlCache`, reached through a `Memory` handle: a fourth handle
type, filled by the library, left out of the schema the model sees. Only the owner can redact on
write, record the store in the manifest, and rebind the scope per rollout, which is §1.5, §1.1
and §1.3 respectively.

**`scope` is required, with no default.** A memory with no scope is one store for every end user.

### 2.3 `Memory` makes its tool re-run on replay (D3)

Like `Workspace`, not like `SpendMeter`. Nothing is keyed, so §1.6's collision cannot arise for
a recall; a replay rebuilds the store by re-running the writes, which is `Workspace`'s reason
exactly.

**What it constrains: memory is an idempotent keyed put, not an append.** Re-running has to leave
the same state, so a fact goes in under a key derived from its content. This is the cost of the
decision and it is stated wherever memory is documented.

### 2.4 An evaluation binds a fresh store per rollout, seeded from the example (D4)

`Example(inputs=..., memory={...})`, the way `Example.inputs` already works. Prior sessions
become a fixture, so cross-session memory is a controlled variable rather than an uncontrolled
one, and §1.3 cannot happen.

Under this, `WRITES` becomes an honest declaration during an evaluation: the class means "does
repeating this k×n times act on the world k×n times", and once the runner scopes the store to
the rollout it no longer does.

**What this does not cover, and is stated rather than built:** an evaluation whose unit is a
sequence of sessions, which is what LongMemEval tests.

### 2.5 Redaction on write, and each entry records the rules it was written under (D5)

The run's `Redaction` runs over a write before it lands. Refusing the write model-facing was
considered and rejected: it can loop, and it is inconsistent with a record path that redacts
rather than refusing to record.

**Rules change between runs, so a store is a mixture**, and each entry records which rules were
applied when it was written. The limit that has to be said wherever the store is documented is
`redaction.py`'s own: the rules match known formats and declared values, and the store outlives
every run, so a rule added tomorrow does not reach what is already in it.

### 2.6 The `WRITES` hole is stated, not given a fifth class (D6)

The declared path is fixed by 2.2 and 2.4. A project's own tool writing to its own persistent
store under `WRITES` cannot be detected, so the answer is the delegation item's: state it in
FT-20, narrow what `docs/tools.md` §1.4 says `WRITES` means, and make the declared path cheap.

A fifth `SideEffectClass` was named as the alternative and not taken. It is honest where the four
are not, and it touches every tool anyone has written.

### 2.7 Two things that grew this item's scope, on Thilina's instruction

- **§1.6's cassette collision is fixed here rather than deferred to `plan.md` §2.2.**
  **The mechanism changed after the design was approved; §2.9 is the record.**
- **§1.7's manifest counts are fixed here.** The per-record-type breakdown is enumerated as a
  literal tuple of four names and there are five types.

### 2.9 The cassette fix was designed wrong, and the correction is measured

**What was approved.** Scoping a tool call's cassette key by rollout, on my recommendation.

**What that would have broken, found while building it.**
[`test_an_identical_tool_call_across_rollouts_is_stored_once`](../../tests/test_adapter_integration.py#L665) pins a shipped
property with a stated rationale: 19 tool calls, 4 entries, because two rollouts making the
identical call share a key. `handoff.md` cites the same measurement. Scoping deletes it.

**And the consequence past the file size is decisive.**
[`_refuse_unsafe_tools`](../../src/simple_agents/evaluation/runner.py#L2129) instructs "Record a
cassette once with `Cassette.record(path)`, then run the evaluation with
`Cassette.replay(path)`", and for a `spends_money` tool that is the only route, since the same
refusal will not let an evaluation record one. Under scoped keys that single-run recording
carries no scope and every rollout looks up with one, so it misses on every call. **Scoping
breaks the documented workflow for exactly the tools FT-20 exists to protect.**

**The premise was wrong too.** §1.6 said memory takes the collision from exotic to routine. It
does not: a memory tool takes a handle, so it is re-run rather than keyed and never reaches the
cassette at all. §1.6's probe used a plain keyed tool, which is the shape memory takes without
this design.

**What ships instead.** The recording already knows. A tool call whose key holds more than one
recorded response is a tool that is not a function of its key, which is §8.2's rule, and the
evaluation refuses at its start rather than replaying it. Model calls are excluded: a hosted
backend answering one request two ways is what `diverged` was built to report.

Measured against three recordings:

| Recording | Tool keys with more than one recorded response |
|---|---|
| §1.6's colliding case | one, four responses: **refused** |
| Two rollouts, one identical pure call | none: allowed, and 19-to-4 is untouched |
| The committed `tests/cassettes/eval.jsonl` | none: nothing re-recorded |

**What it does not do**, since scoping would have: it catches the collision once a recording
exists rather than preventing it, and it says nothing about a `now`-style call in a run that was
never recorded.

**Put back to Thilina 2026-08-10 with the measurement, and approved.** The same sitting scheduled
`archive/plan-history.md` §1.9 off a side question it raised.

### 2.8 Held back

**The elicitation question**, on the same grounds per-node model selection held one back: dogfood
#3 is measuring the question set. Whether the agent remembers anything across sessions, and what
scope separates two end users, are builder decisions and will need asking.

**Semantic recall**, scheduled as `archive/plan-history.md` §1.8. Memory ships with lexical recall, which is the
limit `document_search` already has.

**Automatic memory formation**, noted in `items/example-projects.md` §9.2 as a candidate shape
rather than a primitive: it is a small pipeline over things the library already has.

---

## 3. The build

Built 2026-08-10. **1574 tests pass**, up from 1544; `prose_check` and `check_citations` clean.

### 3.1 What shipped

| | |
|---|---|
| API | `MemoryStore(directory, scope=...)`, `MemoryEntry`, the `Memory` handle, all exported |
| Envelope | `RunEnvelope(memory=...)`, carried by every `with_*` copy |
| Tools | `remember`, `recall`, `memory_search` in `simple_agents.builtins`, thirteen built-ins now |
| Handles | `Memory` joins `HANDLE_TYPES` and `RE_EXECUTED_HANDLE_TYPES` |
| Manifest | `memory` object holding the directory, the scope digest and the entry count; format `0.19` |
| Evaluation | `Example.memory`, and a store rebound per rollout under that rollout's run directory |
| Refusals | A memory tool with no store, at run start; an ambiguous recording, at evaluation start |
| Counts | The manifest's per-record-type breakdown reads `RECORD_TYPES` rather than a literal list |
| Docs | `docs/memory.md`, plus `index.md`, `tools.md`, `procedure.md`, `run-envelope.md`, FT-20 |

**No trajectory format change.** A memory call is a `tool_call` parented to its node, which is
what 2.1 predicted and what the live runs confirmed.

### 3.2 The manifest counts fix is a deletion

`RECORD_TYPES` was written out twice: as a `Literal` in `trajectory.py`, and as a frozenset in
`conformance/checks.py`, with `manifest.py` carrying a third copy as a four-name tuple inside a
dict comprehension. It now derives from the `Literal` with `get_args`, and both other modules
read it. The delegation item added a fifth type and the manifest kept reporting four; deriving
it is what stops the sixth doing the same.

### 3.3 What the live runs found

Run against Mistral `mistral-small-2603` and a local `Qwen/Qwen3-1.7B` on port 8001, under the
2026-08-10 amendment to `CLAUDE.md` requiring both. Two separate runs over one store: the first
is told a preference by an end user and decides for itself whether to store it, the second is a
fresh run that has to answer a question needing it.

**The mechanism works on both.** The store is written by one run and read by another, the
manifest records the digest and the count, every memory call is a `tool_call` parented to the
node record with `re_executed: true` and `cassette_key: null`, and a second scope over the same
directory reads zero entries.

**One defect, found on the first live run and fixed.** Mistral stored the preference under
`max_reading_length_pages`. The next run searched `"science fiction novel recommendation
preference"`, matched nothing, and **recommended a 900-page novel to someone who had just said
they never finish anything over 300**. The lexical limit is real and it bit on the most natural
phrasing available.

**The fix is not semantic search.** `memory_search` returned `stored: 1` and no results, so the
model knew something was there and had no way to see what. It now returns `keys` when it matches
nothing over a store that holds something. Re-run against Mistral: the search missed, the model
read the key, called `recall`, and used the preference.

```
memory_search({"query": "science fiction novel preference"})
  -> {"results": [], "stored": 1, "keys": ["preferred_reading_length_pages"]}
recall({"key": "preferred_reading_length_pages"})
  -> {"found": true, "value": "Never finishes books over 300 pages"}
```

**The two backends then differed, and that is worth recording rather than fixing.** Given the
same `keys` reply, Mistral called `recall` and the 1.7B model called `finish` and recommended
Dune. The affordance is there and a small model may not take it. A `FakeModelClient` shows
neither behaviour.

**This does not close `archive/plan-history.md` §1.8.** Listing keys recovers a miss in one extra call over a
small store. It does not rank, and `MAX_KEYS_ON_EMPTY` is 50, so a store past that size returns
a truncated list and the case semantic recall exists for is unchanged.

### 3.4 Left open

**An evaluation whose unit is a sequence of sessions.** `Example.memory` makes prior sessions a
fixture, which is what LongMemEval-shaped tasks need reduced to one rollout. A task whose answer
depends on five conversations in order has no expression, because the resampling unit is one
rollout. No project is asking for it.

**A store the library does not own is still invisible**, which is §1.1 shape C narrowed rather
than closed, and the same shape as the delegation item's tool-body defect. FT-20 states it.
