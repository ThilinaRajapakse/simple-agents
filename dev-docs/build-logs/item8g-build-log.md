# Item 8g — build log

**Kept while building, not reconstructed at the end.** On the precedent of
`item9-build-log.md` and `item8a-build-log.md`.

The design of record is `archive/plan-history.md` §3.1 item 8g and `build-logs/item8a-build-log.md` §5.3. §1
records what was measured before the sitting, §2 the sitting, §3 where building sharpened a
decision, §4 where it turned out not to hold, §5 what the build found that is nobody's design,
§6 doc consequences, §7 existing tests that had to change.

**Status: built 2026-08-06.** Baseline 929 tests at `893c182`; 978 now.

---

## 1. What was measured, before any design

Item 9 §1 is the standard: what an artifact holds is a measurement, and it disagreed with the
document describing it in four places. This item is about what a node receives at run time, so
every claim below is read off a run of a real `Pipeline` or off the library's own shipped code.
Nothing is read off a document.

The probes are `scratchpad/probe_inputs.py`, `probe_inputs2.py`, `probe_dual.py`,
`probe_silent.py`, `probe_suspend/` and `probe_edges.py`. Every pipeline in them is built from
the shipped constructors and run through `Pipeline.run` with a `FakeModelClient` where a node
makes a call.

### 1.1 Item 8a §5.3 reproduces exactly, and neither node in the reproduction declares a schema

Two pipelines, identical but for a node inserted in the middle.

| Arm | outcome | what the model was actually asked |
|---|---|---|
| `gather -> verify` | `completed` | `Check this: {'notes': 'the inseam is 32 inches', 'question': 'what is the inseam'}` |
| `gather -> count -> verify` | `completed` | `Check this: {'how_many': 23}` |

Both runs return `answer='32 inches'`. There is no exception, no error record, and no
difference in the manifest's `outcome`.

**Both `gather` and `count` are `Deterministic` nodes declaring no `output_schema`**, which is
what the reproduction needed to be realistic. A construction-time check comparing declared
schemas sees `None` on both sides of the changed edge and has nothing to compare.

### 1.2 The node kind the failure was measured on is the kind that declares nothing

| Surface | `Deterministic(...)` constructions | of those, declaring `output_schema` |
|---|---|---|
| `docs/` and `scripts/record_backend_cassettes.py` | 11 | **1** |
| whole repository, including `tests/` | 90 | 9 |

The one in the shipped surface is `docs/pipeline.md` §1.8's suspension example, where it is
required rather than chosen. Five of the nine in the repository are in `tests/test_suspension.py`,
for the same reason.

`LLMNode` and `AgentNode` both require `output_schema` at construction. So the declaration this
item would compare against is present on two kinds and absent on the third, and the third is
where the silent failure was measured.

### 1.3 What every node in every shipped pipeline receives, and what it declares

Read off the seven pipelines in `scripts/record_backend_cassettes.py` by `probe_edges.py`:
18 nodes, 13 edges.

| Pipeline | Node | In-edges | First-parameter annotation | `output_schema` |
|---|---|---|---|---|
| context | `describe` | `load` | none | `Answer`, `over="documents"` |
| eval | `verify` | `hunt` | none | `Answer` |
| graph | `report` | `classify`, `summarise`, `cite` | **`Join`** | none |
| graph-loop | `draft` | `critique` | none | `Answer` |
| graph-loop | `fallback` | `lookup` (error edge) | **`NodeFailure`** | none |
| graph-loop | `report` | `lookup`, `fallback` | **`Join`** | none |

Every other node function takes an unannotated first parameter.

**Where an annotation exists it is exact, and it exists exactly where the shape is surprising.**
Three of the twenty-one node functions in that file annotate the first parameter, and the three
are the two joins and the error handler.

The shipped documentation is the other way round. In `docs/` and `README.md`, **9 of 9** node
functions annotate the first parameter and **9 of 9** annotate the return type. The surface a
builder's coding agent copies from is fully annotated; the surface the library maintainer wrote
for the library's own recordings is not.

### 1.4 The four shapes the document lists, measured

`docs/pipeline.md` §3 gives four shapes. All four occur, and each was produced by a run.

| Edges into the node | What the document says | What was measured |
|---|---|---|
| None, the first node | what was passed to `run` | `dict` — the run's inputs, as documented |
| One | what that node returned | the predecessor's return value, or its `output_schema` type where it declared one |
| More than one | a `Join` | `Join({'a': {...}, 'b': Unknown(reason="'b' was skipped")})` |
| An `on_error` that fired | a `NodeFailure` | `NodeFailure(node_id='lookup', inputs=..., error=..., attempts=1)` |

### 1.5 The entry node does not always receive the run's inputs

`Pipeline` allows the first node to be the node a cycle returns to. Measured on a three-node
pipeline `draft -> critique -> {draft, publish}`, run with `{"question": "how long"}`:

```
draft        receives Unknown        Unknown(type='unknown', reason="'critique' did not run")
critique     receives dict           {'from': 'draft'}
draft        receives dict           {'from': 'critique'}
```

**The run's inputs reach no node at all.** `_EdgeState.inputs_for` returns `run_inputs` only when
the node has no in-edges (`pipeline.py:1533`), and a back edge is an in-edge.

Two things say otherwise. `docs/pipeline.md` §3's table gives the first row as "None, which is
the first node". And `_EdgeState.all_absent`'s docstring at `pipeline.py:1511` states the
behaviour the code does not have:

> The first node receives the run's own inputs and always runs, including where it is also the
> node a cycle returns to and so has an in-edge that has not fired yet.

The first clause is false in that case; the second is true.

**The library's own recording already works around it.** `graph_loop_pipeline`'s entry node is
`draft`, inside the cycle `critique -> draft`, and `loop_draft` opens
`previous = "" if isinstance(inputs, Unknown) else ...` and reads its corpus from module scope
rather than from `inputs`. No test covers a cycle returning to the entry node.

### 1.6 A node inside a loop is not a separate case

Item 8g's fourth listed case is "a node inside a loop, whose predecessor can be a later node".
Measured on `plan -> draft -> critique -> {draft, publish}`:

```
draft        receives Join   Join({'plan': {...}, 'critique': Unknown(reason="'critique' did not run")})
critique     receives dict   {'from': 'draft'}
draft        receives Join   Join({'plan': {...}, 'critique': {'from': 'critique'}})
```

A node a cycle returns to has two in-edges, so it receives a `Join` and is §1.4's third row. The
back edge holds an `Unknown` on the first entry and a value afterwards. Where the loop returns to
the entry node instead, it is §1.5. **The case list has this one wrong: it is not a fourth shape,
it is the join case and the entry case seen from inside a cycle.**

### 1.7 A fan-out node's prompt function receives something no edge carries

`over=` substitutes the item into the inputs before calling the prompt function
(`nodes.py:573`). Measured on `load -> summarise(over="documents") -> report`, with `load`
returning `{"documents": ["d1", "d2"]}`:

```
load                receives dict           {'corpus': 'corpus/'}
summarise(prompt)   receives dict           {'documents': 'd1'}
summarise(prompt)   receives dict           {'documents': 'd2'}
report              receives FanOutResult   FanOutResult(outcomes=(ItemOutcome(index=0, ...
```

So one node has two input shapes: the node receives what the edge carried, and its prompt
function is called once per item with the item substituted under the same key. A declaration
read off that function's annotation describes the second, and a predecessor's `output_schema`
describes the first.

The successor receiving a `FanOutResult` is the item's third listed case, and it is confirmed.

### 1.8 Two fan-out shapes cannot run at all, and the refusal fires at run time

`_sequence_for` requires `isinstance(inputs, dict)` (`nodes.py:645`). Two consequences, each
measured by running the pipeline.

| Pipeline | outcome |
|---|---|
| `load(output_schema=Docs) -> summarise(over="documents")` | `ConfigurationError: Node 'summarise' fans out over 'documents', and its input has no such key ... Found: Docs` |
| `{a, b} -> summarise(over="documents")`, two in-edges | same refusal, `Found: Join` |

A predecessor that declares an `output_schema` produces a pydantic model, and a node with more
than one in-edge receives a `Join`, which is a `Mapping` and not a `dict`. Either way the node
raises on every rollout.

**The error is a `ConfigurationError` raised during the run.** Everything it names is known when
the pipeline is built: `over=` is on the node, and the predecessor's `output_schema` and in-edge
count are on the graph.

### 1.9 A node can be both a successor and an error handler, and then its shape depends on the run

`_edges_of` appends an `on_error` target only where it is not already a successor
(`graph.py:547`), so `successors=["report"], on_error="report"` is one edge. Measured, same
pipeline run twice:

| `lookup` | `report` receives |
|---|---|
| succeeds | `dict` — `{'ok': True}` |
| raises | `NodeFailure(node_id='lookup', ...)` |

`docs/pipeline.md` §1 says "The shape a node receives follows the edges declared into it and
never what happened on a given run." For this shape that is false, and §3's table lists the two
as separate rows, which reads as two edges.

### 1.10 An error edge puts an `Unknown` into the join downstream of it

Measured on `start -> lookup -> report` with `on_error="fallback"` and `fallback -> report`:

```
fallback     receives NodeFailure    NodeFailure(node_id='lookup', inputs={'from': 'start'}, ...)
report       receives Join           Join({'lookup': Unknown(reason="'lookup' failed after 1 attempt(s)"),
                                            'fallback': {'from': 'fallback'}})
```

So declaring `on_error=` on a node adds an in-edge at whatever node the two paths rejoin, and
that node receives a `Join` rather than the value it received before the handler existed.

### 1.11 A nested pipeline chains, and its entry node receives the outer predecessor's output

```
before        receives dict   {'question': 'how long'}
inner_first   receives dict   {'from': 'before'}
inner_last    receives dict   {'from': 'inner_first'}
after         receives dict   {'from': 'inner_last'}
```

A `Pipeline` used as a node has no input shape of its own: what it accepts is what its entry node
accepts, and what it produces is what its terminal node produces. `_node_entries` expands nested
nodes into the manifest under prefixed ids and gives the container no entry of its own.

### 1.12 What a resume already refuses when a node's declaration changes

Built by suspending a run at `suspend_before=True`, editing one function on disk, and resuming
against the edited pipeline. Each arm gets its own suspension, because a resume claims one.

| Change while the run is suspended | Resume |
|---|---|
| nothing | resumed, `completed` |
| first-parameter annotation added to a `Deterministic` function | **resumed, `completed`** |
| first-parameter annotation added to an `LLMNode` prompt function | refused: `Run ... was suspended under a different prompts.answer` |
| `LLMNode` prompt body changed | refused, same message |

The middle two are the same edit to two node kinds. An `LLMNode`'s prompt function is versioned
by source hash in `manifest_prompts()`, so any edit to it, including one to an annotation, is
refused unless named in `accept_changed=`. **A `Deterministic` node's function is not versioned
at all**: `_node_entries` fills `prompts[node_id]` only for the kinds that are not
`Deterministic` (`pipeline.py:1231`), so nothing records what its body was.

`_STRUCTURAL` is `node_id`, `node_kind`, `successors`, `loop`, `on_error`, `retry`, `schema`
(`pipeline.py:1683`). A change to one of those is refused outright and cannot be waived.

### 1.13 A mistyped input fails three different ways, and only one of them is loud

Measured across the probes.

| What the successor does with the value | What happens |
|---|---|
| interpolates it, `f"Check this: {inputs}"` | nothing. `outcome: "completed"`, wrong prompt (§1.1) |
| subscripts a pydantic model, `inputs["answer"]` | `TypeError: 'Answer' object is not subscriptable`, no node named |
| fans out over it | `ConfigurationError` naming the node and the key (§1.8) |

The first is item 8a §5.3. The second names neither the node nor the edge, and the shape every
shipped example uses is the first.

---

## 2. The sitting, and what it settled

Held 2026-08-06, after §1's measurements. Seven questions were put and all seven were answered,
which is the first sitting in this series where none dissolved. Two of them were not in
`plan.md`'s entry.

### 2.1 The declaration is the annotation, and there is no new constructor argument

**Settled: what a node accepts is read off its function's first parameter.** `plan.md` item 8g
proposed `input_schema=` on the node, and that was the argument to beat rather than the answer.

Item 7's precedent decided it: a tool's replay behaviour is read off its signature "the same way
it already reads the JSON schema off the annotations, so nothing is declared and nothing is
judged" (`simple-agents.md` §8.2). `tools.py` already calls `get_type_hints`, so the mechanism
exists rather than being invented here.

The argument put against `input_schema=` was two sources for one value: a node annotated `Notes`
and declaring `input_schema=Count` has no rule saying which wins. `output_schema=` is not the
symmetric precedent it looks like, because it is sent to the backend for constrained decoding and
validated against; an input declaration is read by nothing else.

**The cost accepted:** a lambda carries no annotation, and neither does a callable object. Both
are read as undeclared, which §2.2 makes safe.

### 2.2 The check refutes and never requires

**Settled: a disagreement is refused only where both sides are declared and no value could
satisfy both.** Nothing has to be annotated, and a pipeline that annotates nothing is refused
nothing.

The argument is that an unannotated node function is a legitimate thing to write: Python does not
require annotations and the library has never asked for one, so treating absence as a fault
refuses correct code. That is item 8's over-refusal, which is how a suite gets switched off.

**Thilina's correction, and it changed what counts as evidence.** The measurement offered for
this was §1.3's, that our own recording script annotates 3 of 21. He ruled that our scripts and
examples are output of the design and not input to it, and that changing them costs nothing. The
argument above survives without them; §1.3 is now an illustration rather than a reason.

### 2.3 The check fires at construction and again at run time, and this is what the
Deterministic measurement decided

**Settled: one rule read at two moments.** Construction compares declarations. The run compares
the value handed over.

`plan.md`'s entry put the check at construction. §1.2 is what moved it: on the node kind where
the silent failure was measured, 1 of 11 shipped constructions declares an `output_schema`, so
construction has nothing to compare. The run has the value itself whatever the node before
declared.

Measured against §1.1's reproduction, with the verifier annotated:

| The inserted node | What happens now |
|---|---|
| declares `-> Count` | **refused at construction**, naming both nodes |
| declares nothing | **refused at run time**, naming both nodes |
| declares nothing, and the verifier is unannotated too | completes, as it did before |

The third row is the honest boundary and `docs/pipeline.md` §3.1 states it.

The run-time half is a comparison and never a validation. Validating would coerce a `dict` into a
model, which is the silent conversion this item exists to stop.

### 2.4 `over=` is an input contract that already existed, and it fired at run time

**Settled, and it was not in the item entry.** §1.8 measured two shapes that raise
`ConfigurationError` on every rollout: a fan-out node whose predecessor declares an
`output_schema`, and one with more than one in-edge. Both are refused at construction now.

**Over-refusal here is zero and provable rather than estimated.** `_sequence_for` requires
`isinstance(inputs, dict)`; a pydantic model is not a dict and neither is a `Join`, so the
refused set is exactly the set that cannot run.

### 2.5 The entry node receives the run's inputs, including where a cycle returns to it

**Settled: fixed here rather than noted.** §1.5 measured the run's inputs reaching no node at
all in that shape, with `docs/pipeline.md` §3 and `pipeline.py:1511` both saying otherwise.

Two options were put against it. Refusing the shape at construction was rejected because the
library's own `graph_loop_pipeline` uses it deliberately. Documenting it was rejected because the
run's inputs being silently unreachable is the failure class this item exists to close.

### 2.6 A node that is both a successor and an error handler keeps the shape, and the document
changes

**Settled: accept it, correct `docs/pipeline.md`.** §1.9 measured one edge carrying either the
predecessor's output or a `NodeFailure`, decided by what happened, against §1's sentence that the
shape "follows the edges declared into it and never what happened on a given run".

Refusing the shape was rejected: a builder has a reason to write it, since the alternative of a
separate handler that rejoins puts an `Unknown` into a `Join` at the rejoin node (§1.10).

The check accepts either annotation there, because neither can be refuted.

### 2.7 `accepts` is recorded, and it is a version rather than a shape

**Settled: the manifest node entry gains `accepts`, manifest `0.8` to `0.9`, outside
`_STRUCTURAL`.**

Thilina's question was whether this is about changing a pipeline while it is suspended, and
whether that should simply break. It is, and the library already has two tiers: a shape change is
refused and cannot be waived, and a version change is refused unless named in `accept_changed=`.
Both break by default; the difference is whether a builder can override.

The measured argument for the version tier is §1.12: adding an annotation to an `LLMNode` prompt
function is **already** refused there, as `prompts.<node>`, because the prompt is versioned by
source hash. Putting `accepts` in `_STRUCTURAL` would make the same edit un-waivable on a
`Deterministic` node and waivable on an `LLMNode`, which is stricter than the prompt itself gets
for a weaker reason. Nothing stored is invalidated either way: a value in flight is rebuilt from
the **output** schema of the node that produced it.

**The second reason to record it, and it is independent.** §1.12 also found that a
`Deterministic` node's function is versioned nowhere, so its body can change across a suspension
and between two runs a `compare()` reads. `accepts` is the only trace such a change would have.
Closing that gap properly is not this item's.

### 2.8 A node's exception says which node raised and what it was reading

**Settled: folded in, on Thilina's instruction that an improvement needing no sitting of its own
goes in.**

§1.13 measured the failure a builder sees when nothing is declared:
`TypeError: 'Answer' object is not subscriptable`, naming neither the node nor the edge.

Raising a new exception type was rejected on two counts: it breaks a caller's `except ValueError`
around `run()`, and it contradicts `docs/pipeline.md` §1, which says a node that raises
propagates its exception. The note goes on the original exception with `add_note`, so the type,
the identity and every `except` clause are unchanged and the note renders under the message.

### 2.9 A taxonomy entry, decided against the scope this item was given

The item's scope said no taxonomy entry. Thilina reopened it: the taxonomy changes where a change
is an improvement.

**Settled: a new entry, FT-28, rather than an expansion of FT-09.** Three reasons, and the third
decided it. The failures differ: FT-09 is a value that cannot express absence, FT-28 is two nodes
disagreeing on a type. An id is a permanent citation target, and `schema.py:162`,
`docs/pipeline.md` §4 and `docs/trajectory-format.md` already cite FT-09 for the first of those.
And §1's own rule is that each entry maps to one check, so two failures with different checks
cannot share a row. FT-28 joins §10's list of entries enforced by construction, beside FT-09,
FT-18 and FT-19.

---

## 3. What building it changed about the design

### 3.1 The entry node stopped being a special case in the check

The first implementation had `arriving_at` return `None` for the entry node, meaning "the graph
cannot say". §4.1 found the test written against that exemption did not exercise it, and chasing
why showed the exemption was a second mechanism for a rule the function already had: **an
arriving set with one member nothing declares cannot be refuted.**

It now returns `None` as one *member* of the arriving tuple, and the ordinary rule handles it.
One branch fewer, one rule instead of two, and the entry node inside a cycle is covered by the
same line as a node fed by an undeclared predecessor.

### 3.2 The fan-out refusal lost its own entry-node exemption for the same reason

`_refuse_fan_out_over_a_shape_it_cannot_read` began with `if node.node_id == graph.entry: return`.
With §3.1's change, a fan-out entry node's arriving set is `(None,)` and the existing
`if one is None: continue` covers it. The exemption was deleted.

The multi-in-edge branch keeps no exemption, deliberately: a fan-out node with two in-edges
receives a `Join` on some execution whatever else reaches it, so the refusal is right for the
entry node too.

### 3.3 The graph-loop cassettes did not have to be re-recorded, and that is a measurement

§2.5's change alters what `graph_loop_pipeline`'s entry node receives, so `loop_draft` changed
with it. Written so the first pass produces the prompt it produced before, the recorded requests
key identically and all six `TestCycleAndErrorEdge` tests replay unchanged, misses zero.

Re-recording is free and was not the constraint. What this says is narrower and worth keeping: the
behaviour change reaches what a node is *handed* and not what the library *sends*, so no cassette
in the repository is invalidated by it.

---

## 4. What in the settled design turned out to be wrong

### 4.1 Seventeen guards, disabled one at a time, and three stayed quiet

Fourteen of seventeen failed the test named against them on the first pass. All three quiet ones
were the test being wrong rather than the guard being redundant, which is item 8a §4.1's shape
three times over.

| Disabled | Why the test still passed | What it was |
|---|---|---|
| the entry node exempt from the graph check | the fixture was a single node with no in-edges, so `not incoming` exempted it anyway | a redundant mechanism, deleted in §3.1 |
| a union on the arriving side not refuted | the fixture tested the permission, which `_as_class` returning `None` for a union already grants | the guard is the *refusal* side: a union every member of which disagrees |
| only refusing where every arriving type is refuted | the fixture had one arriving type, where `any` and `all` agree | needed the two-type shape, which is §2.6's |

New fixtures for all three: an entry node a cycle returns to, a predecessor declaring
`Count | dict` feeding a node that reads `Notes`, and the successor-and-handler shape.
**17 of 17 now fire.**

### 4.2 The guard pass was reporting on stale bytecode, and two unrelated tests failed after it

The first clean 17-of-17 run left two tests in `test_node_inputs.py` failing, reproducibly, with
the working tree byte-identical to before the run. `md5sum` against a backup confirmed the source
was restored.

**The cause is the harness, not the library.** The pass swaps a token for one of the same length
(`any(` for `all(`) and restores within the same second, so the `.pyc` written from the modified
source still matches the restored file on both mtime and size and is reused. Every test that
depended on the `any` semantics then failed against bytecode compiled from `all`.

The pass now runs each case with `PYTHONDONTWRITEBYTECODE=1` and removes `__pycache__` after
restoring. **A guard-disabling pass that reports on a stale cache reports nothing**, and the
symptom is unrelated tests failing after it rather than during it.

---

## 5. Findings

### 5.1 The item's six special cases, measured: one is wrong, four hold, and four are missing

`plan.md` item 8g lists six cases where a naive check refuses a correct pipeline, derived by
reading code and never run. Every one was run.

| # | The case as listed | What running it found |
|---|---|---|
| 1 | the entry node, which receives run inputs and has no predecessor | Holds, and **it was false in one shape**: where a cycle returns to the entry node, the run's inputs reached nothing (§1.5). Fixed at §2.5 |
| 2 | a node with several in-edges receiving a `Join` | Holds exactly (§1.4) |
| 3 | a fan-out successor receiving a `FanOutResult` | Holds (§1.7) |
| 4 | a node inside a loop, whose predecessor can be a later node | **Wrong: not a case.** It has two in-edges and receives a `Join`, so it is case 2 (§1.6) |
| 5 | a predecessor declaring no `output_schema` | Holds, and is the common case rather than an edge one (§1.2) |
| 6 | an `on_error` handler receiving the failure | Holds (§1.4) |

Four the list does not have, all measured:

| Missing case | What it is |
|---|---|
| a fan-out node's own prompt function | Called once per item with the item substituted under the `over=` key, so one node has two input shapes (§1.7) |
| a fan-out node whose input is not a plain dict | Cannot run at all. `ConfigurationError` on every rollout (§1.8) |
| a node that is both a successor and an error handler | One edge carrying either, decided by the run (§1.9) |
| a nested `Pipeline` | No input shape of its own: it accepts what its entry node accepts (§1.11) |

### 5.2 Over-refusal on the library's own code is zero, measured rather than estimated

All seven pipelines in `scripts/record_backend_cassettes.py` still construct: 18 nodes, 13 edges,
three annotated. Every annotation that exists is correct, and every unannotated node is silent.

Live against Mistral `mistral-small-2603`, `graph_loop_pipeline`, seed 41, `outcome: completed`,
the cycle running twice, the retry exhausted, the error edge taken and the join reporting
`{'fired': ['fallback'], 'absent': ['lookup']}`. The entry node's records read
`inputs={'question': ...}` on iteration 1 and the critique's `Answer` on iteration 2, which is
§2.5 on a live backend rather than in a fixture.

### 5.3 A `Deterministic` node's function is versioned nowhere

Found while measuring §1.12 rather than while building. `_node_entries` fills `prompts[node_id]`
only for the kinds that are not `Deterministic`, so a `Deterministic` node's body can be rewritten
and:

- a suspended run resumes across it with no refusal and no waiver,
- `compare()` reports a moved metric with nothing in `changed` to attribute it to,
- and `graph_fingerprint` is unaffected, since the function is not in it.

`accepts` closes the part of this that is about what the node reads and nothing else. **The whole
gap is worth a decision later** and is nobody's design today. FT-15 is about prompts and this node
kind has none.

---

## 6. Doc consequences

Written after the build.

| Document | What it said | What it says now |
|---|---|---|
| `docs/pipeline.md` §1 | the shape a node receives "never" depends on what happened on a run | Plus the one exception, a node named as both a successor and the `on_error` handler of one node |
| `docs/pipeline.md` §1.1 | the construction refusals | Three more: a node reading what nothing reaching it can be, and the two fan-out shapes |
| `docs/pipeline.md` §1.4 | bounded cycles, with nothing on what the node a cycle returns to receives | Plus the `Join` it receives, and the run's inputs where that node is the first in the list |
| `docs/pipeline.md` §3 | four shapes, the first row "None, which is the first node" | The first row covers a cycle returning to the first node, and the dual successor-and-handler edge is named |
| `docs/pipeline.md` §3.1 | did not exist | **New.** How a node says what it reads, when it is refused, what is compared, and what it does not see |
| `docs/run-envelope.md` §2.1, §2.6 | the node entry's fields | `accepts`, and why it is outside `graph_fingerprint` |
| `docs/run-envelope.md` §2 | manifest `0.8` | `0.9`. Edited during the build, because the packaging test that pins it would otherwise hold the suite red, which is item 8a §7's precedent |
| `docs/failure-taxonomy.md` | 27 entries | **28.** FT-28 in Group C, the index, the counts, the ID-ordering note, and §10's list of entries enforced by construction |
| `CHANGELOG.md` | manifest `0.8` | `0.9`, the declaration and both refusals, the note on an exception, and the entry-node change with what a project does about it |

**Not touched, and deliberately.** `docs/evaluation.md`, which is next in Thilina's review and
already carries unreviewed text from two items. `docs/trajectory-format.md`, `docs/tools.md`,
`docs/context.md`, `docs/conformance.md`, `docs/index.md` and the model-client pages own nothing
this item changed. No public name was added to `__init__.py`: deriving the declaration is what
makes the API surface unchanged.

---

## 7. Existing tests that had to change

Ten, and none is a defect. Four are exact-equality assertions on records that widened, and six
are fixtures encoding the behaviour §2.5 changed.

| Test | What it asserted | Why it failed |
|---|---|---|
| `test_run_envelope.py::test_it_records_the_node_shape_and_the_unknown_waivers` | the manifest node entry, field for field | `accepts` added |
| `test_eval_runner.py::test_the_config_says_what_was_measured` | `config["nodes"]`, field for field | the same entry |
| `test_packaging.py::test_every_format_version_is_pinned_to_a_literal` | manifest `0.8` | bumped to `0.9` |
| `test_conformance.py::test_every_entry_parses_out_of_the_shipped_document` | 27 taxonomy entries | FT-28 |
| `test_graph_execution.py::TestBoundedCycle`, five tests | a fixture whose entry node read `isinstance(inputs, Unknown)` | it now receives what `run` was given |
| `test_graph_execution.py::TestProgressEvents::test_each_iteration_of_a_cycle_is_numbered` | the same shape inline | the same reason |

Two more failed and were fixed **outside** `tests/`, which is the better fix in each case:

- `test_packaging.py::test_the_run_envelope_document_states_the_manifest_version_the_writer_writes`
  was fixed by editing `docs/run-envelope.md`, which is what the test exists to force.
- `test_graph_integration.py::TestCycleAndErrorEdge`, six tests, was fixed by editing
  `scripts/record_backend_cassettes.py`. The cassettes replay unchanged (§3.3).

**Total: 10 existing tests changed, 49 added. 978 tests.**

### 5.4 The `Unknown` in `docs/pipeline.md` §3 was a record's field, not a node's input

Found while editing §3's table, which said a node with one in-edge receives "what that node
returned, or an `Unknown` saying why the edge did not fire". Removing that clause needed proof
rather than reasoning, so the branch was made to raise and the suite run.

| Where `inputs_for` returns an `Unknown` through a single edge | Tests reaching it |
|---|---|
| any node about to execute | **0 of 978** |
| the record written for a node that was skipped | 21 |

A node whose only in-edge did not fire is skipped, so its function is never called. The value is
what `_emit_skip` puts in the skipped node's `node_execution.inputs`. §3 is about what a node
function is handed and the clause did not belong there; `docs/pipeline.md` §1.2 now carries it,
beside the rest of what a skip record holds.
