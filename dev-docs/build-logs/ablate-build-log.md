# Build log — `ablate()` on a pipeline it did not generate (`archive/plan-history.md` §1.6)

Written while building, not afterwards. Newest section last.

---

## 1. What the code actually does today, read 2026-08-10

Read before designing anything. `archive/plan-history.md` §1.6 was written while designing the model item and
names two failures; the machine is the authority on both, and on what else is there.

### 1.2 The two failures §1.6 names, reproduced

Both reproduce. The script is in this session's scratchpad and its two cases are transcribed
below.

**A nested pipeline is flattened and its nodes renamed.** Baseline `research` = [`hunt`,
`verify`] with `node_id="research"` and its own budget, inside an outer pipeline with `write`:

```
baseline declared_nodes: ['research.hunt', 'research.verify', 'write']
arms: ['research.hunt as one call', 'research.verify removed', 'write removed']
  'research.hunt as one call': ['hunt', 'verify', 'write'], budget={... the OUTER budget ...}
  'research.verify removed':   ['hunt', 'write'],           budget={... the OUTER budget ...}
  'write removed':             ['hunt', 'verify'],          budget={... the OUTER budget ...}

  plan 'research.verify removed': differs_at=('hunt', 'research.hunt', 'research.verify')
    statuses={'hunt': 'added', 'write': 'unchanged',
              'research.hunt': 'removed', 'research.verify': 'removed'}
  plan 'write removed': REFUSED -- shares no node id with the baseline
```

Three things beyond the rename. The sub-pipeline's `budget` is gone and the arm runs under the
outer one alone. The arm named for removing one node reports two removed and one added. And
`_refuse_incomparable` catches only the arm that happens to share nothing, so the two arms that
share `write` run and report a comparison that cannot be attributed.

**A node named in another node's `successors=` cannot be removed.** Same three nodes, edges
declared rather than defaulted:

```
ablate() RAISED ConfigurationError:
    Node 'hunt' names 'verify' in its successors, and this pipeline has no node with that id.
    This pipeline holds 'hunt', 'write'. Add a node with node_id='verify', or correct the name.
```

**What §1.6 does not say, and it matters for the fix:** the same three nodes with the edges left
to the default generate both arms and both are correct.

```
Same graph with the edges left to the default (no successors=):
arms: ['verify removed', 'write removed']
  'verify removed': ['hunt', 'write']
  'write removed':  ['hunt', 'verify']
```

[graph.py `_successors_of`](../../src/simple_agents/graph.py#L617) resolves `successors=None`
to the next node in the list, so dropping a middle node out of the list re-points its
predecessor at what followed it. **The library already rewires; it does it by accident, in one
of the two spellings of the same graph.** The other spelling raises, and raises out of
`ablate()` itself, so one unbuildable arm costs the whole standard set rather than one entry.

### 1.3 A third failure, found by reading: a sub-pipeline's terminal node

Not in §1.6, and independent of the flattening.
[variants.py `_removable`](../../src/simple_agents/evaluation/variants.py#L980) returns `True`
for any node with no successors, without checking what its removal hands anyone:

```python
    if not entry.get("successors"):
        return True
```

That is right at the top level, where the removed node's consumer is the caller. It is wrong
inside a container: a nested pipeline's `output_schema` is its terminal node's
([pipeline.py `Pipeline.output_schema`](../../src/simple_agents/pipeline/core.py#L225)), so removing
that node changes what the container produces and what the next node in the outer graph
receives. `manifest_nodes()` holds no containers, so nothing in `variants.py` can see it.

Measured, with `research` = [`hunt`→`Notes`, `verify`→`Answer`] inside an outer pipeline whose
`write` node consumes the container's output:

```
--- write annotated `inputs: Answer`
   research produces: Answer
   _removable('research.verify'): True
   ablate() RAISED: Node 'write' reads its input as Answer, and what reaches it from 'hunt'
                    is Notes. Every run would call this node with a value it does not describe.
--- write unannotated
   research produces: Answer
   _removable('research.verify'): True
   arms: ['research.verify removed', 'write removed']
```

Annotated, `refuse_disagreements` catches it and `ablate()` raises out of the whole call.
Unannotated, nothing catches it and the arm runs, failing at `write` on every rollout. That is
the case the docstring promises is left out: "A node whose removal would feed its successors a
different declared shape is left out, since that variant would fail on every rollout rather than
measure anything."

### 1.4 `tools=` and `fetch_policy=`, checked rather than assumed

`_replacing` and `_without` pass `budget` and `node_id` to the rebuilt `Pipeline` and nothing
else, so a baseline's `tools=` registry and `fetch_policy=` are dropped from every arm. The
brief's belief was that both are recording-only. **One is; the other is not.**

`fetch_policy=` **is recording-only.** Its two enforcement points, `HostPolicy.in_scope` and
`HostPolicy.spend_fetch`, are called by the fetch tool, which was handed the policy object at
construction (`read_page(policy=policy)`) and travels on the node. The only reader of
`Pipeline.fetch_policy` is [pipeline.py
`_close_manifest`](../../src/simple_agents/pipeline/core.py#L1485). The arm's ceiling still binds;
its manifest carries no `fetch_policy` block saying what it was allowed to reach.

`tools=` **has a second reader, and it is a refusal.**
[pipeline.py `_declared_tools`](../../src/simple_agents/pipeline/core.py#L1942) feeds
[`_refuse_mixed_currencies`](../../src/simple_agents/pipeline/core.py#L1942), which runs before the
first call. A registry tool no node holds is in that set. Measured, with a `spends_money` tool
in the registry declaring EUR and a `PriceBasis` in USD:

```
baseline manifest tools: [{"name": "paid_lookup", ..., "offered": false}]
arm      manifest tools: []

baseline: _refuse_mixed_currencies REFUSED -- This run declares money in more than one currency
arm:      _refuse_mixed_currencies PASSED (no refusal)
```

**How far the divergence reaches.** Inside `compare_variants` it does not: the baseline runs
first and holds the registry, so the sweep dies on the baseline and never reaches the arm.
Dropping `tools=` can only ever make an arm more permissive, never less. It is reachable through
the other door `ablate()` opens, which is a builder taking an arm out of the returned dict and
running it on its own.

**Everything else that reads a tool reads the node's, not the registry's.**
[runner.py `_tools_of`](../../src/simple_agents/evaluation/runner.py#L2828) walks
`declared_nodes()` and deliberately excludes registry-only tools, so the eval-safety refusal
(§4.4) and the results file's `config.tools` are untouched. Nothing in
`conformance/checks.py` reads the manifest's `tools` array or `fetch_policy` at all; the reader
named at `simple-agents.md` §8.3 is the `tool_effects` elicitation question, which a builder
answers.

So the loss is: an arm's manifest missing its `offered: false` rows and its `fetch_policy`
block, plus one refusal that an arm run on its own would not make. Both disappear as a
consequence of the nesting fix rather than needing a decision of their own, since a rebuild that
preserves a container has to carry every constructor argument to reconstruct it.

### 1.5 The root cause under §1.3, and a fourth failure: the entries are a disconnected graph

`manifest_nodes()` renders a nested pipeline's internal edges and **not the edge from the
container to what follows it**. The container is not an entry
([run-envelope.md §2.5](../../docs/run-envelope.md#L181) says so deliberately), and the outer
graph's `successors['research'] = ('write',)` is therefore recorded nowhere:

```
  research.hunt:   successors=['research.verify']
  research.verify: successors=[]
  write:           successors=[]

who names 'write' as a successor: NOBODY
```

Two entries claim to end the run. `Graph._terminal` refuses a pipeline with two such nodes in
the same sentence a builder reads at [pipeline.md
§1](../../docs/pipeline.md#L77), so the manifest describes a graph the library would not
construct.

Every function in `variants.py` that walks `successors` stops at that boundary. **`_removable`'s
early return is one consequence** (§1.3): `research.verify` is not terminal, it only reads that
way. **A fourth is `_taint`**, which decides what an arm has to call live. The same edit to the
same three-node chain, nested and flat:

```
nested: calls per node: {'research.hunt': 'live', 'research.verify': 'live', 'write': 'replayed'}
flat:   calls per node: {'hunt': 'live', 'verify': 'live', 'write': 'live'}
live_calls: nested 2 vs flat 3
```

`write` reads whatever `research` produced, and `research.hunt` changed, so `write`'s request
can differ and the recording may not answer it. The arm still runs correctly, because the
cassette is in `update` mode and a miss records rather than raises. What is wrong is the
estimate, and the estimate is what `max_live_calls` is checked against
([`_refuse_over_ceiling`](../../src/simple_agents/evaluation/variants.py#L705)), so a sweep over
a nested pipeline can be admitted under a ceiling it then exceeds. That is the failure the
ceiling exists to prevent.

`_schemas_feeding` and `_refuse_reshaped_inputs` stop at the same boundary: nothing feeds
`write` according to the entries, so the refusal skips it.

### 1.6 The same root cause, three more places

Once the question is "where is a container read only for its leaves", the answer is: everywhere.

**The manifest names a node it does not hold.** A node before a container records
`successors: ['research']`, and `research` is in no entry:

```
   prep:            successors=['research']
   research.hunt:   successors=['research.verify']
   research.verify: successors=[]
```

So the manifest's graph has a dangling edge as well as two terminal nodes, and `_taint`'s
`if successor in after` guard stops there. A change before a container taints nothing inside it,
which is the mirror of §1.5.

**`graph_fingerprint()` does not move when a sub-pipeline's own configuration changes.**
[`_STRUCTURAL`](../../src/simple_agents/pipeline/recording.py#L106) reads leaf entries, and a container
has none. Measured:

```
sub-pipeline budget max_steps 2 -> 200 : fingerprint moved: False
sub-pipeline gains retry=RetryPolicy(attempts=3) : fingerprint moved: False
sub-pipeline gains on_error='fallback' : fingerprint moved: False
```

[`_verify_against`](../../src/simple_agents/pipeline/core.py#L858) says a change of shape "is refused
outright, because the stored state is keyed on node ids and a different graph makes it
meaningless rather than stale". A container gaining an error edge is a change of shape, and it
resumes. The nested budget is not in the manifest at all.

**A nested pipeline's `tools=` and `fetch_policy=` are read nowhere.**
[`_node_entries`](../../src/simple_agents/pipeline/recording.py#L458) and
[`_declared_tools`](../../src/simple_agents/pipeline/core.py#L1942) read `self.tools` of the top
pipeline; `_close_manifest` reads `self.fetch_policy` of the top pipeline. Measured, with an
EUR-declaring `spends_money` tool in a **sub-pipeline's** registry under a USD `PriceBasis`:

```
manifest tools[] of the outer pipeline: []
_refuse_mixed_currencies: PASSED (EUR tool inside the sub-pipeline's registry unseen)
```

The same tool in the **top** pipeline's registry refuses (§1.4). So the argument is accepted at
every level and honoured at one.

**And two views of one graph disagree.** `to_mermaid()` renders `research --> write`; the
manifest renders two nodes that end the run and one edge to a node that is not there.

### 1.7 What the six failures have in common

| # | Where | What it costs |
|---|---|---|
| 1 | `_replacing`/`_without` flatten | Ids renamed, sub-pipeline budget lost, comparison unattributable |
| 2 | `_without` leaves a dangling edge | `ablate()` raises, losing the whole standard set for one arm |
| 3 | `_removable` early-returns on a container's terminal | An arm that fails on every rollout, which the docstring promises is left out |
| 4 | `_taint` stops at a container boundary | `max_live_calls` admits a sweep it should refuse |
| 5 | `graph_fingerprint` reads no container | A suspension resumes against a rewired sub-pipeline |
| 6 | Nested `tools=`/`fetch_policy=` unread | A currency refusal that fires at one level and not another |

**`Pipeline` as a container is read only for its leaves.** `declared_nodes()` returns leaves and
`manifest_nodes()` renders leaves, so every reader downstream of them sees a flat list that is
not a graph. Failures 1 and 2 are `ablate()`'s own; 3 to 6 are that list being treated as one.

---

## 2. The design, proposed 2026-08-10

Put to Thilina before building. His ruling on the first pass: "Fix things properly. No excuses
or handwaving. I don't care about bumping or what's shipped (NO USERS). What's the RIGHT fix?"
So the manifest is in scope and a format bump is not an argument against anything.

### 2.1 The manifest records containers

`nodes[]` stays leaf-only, because that is what it is for: `Pipeline.execute` writes no
`node_execution` record for a container ([pipeline.py `Pipeline.execute`](../../src/simple_agents/pipeline/core.py#L1271)),
so `nodes` naming what the trajectory holds and what per-node metrics key on stays true.

A sibling `containers[]` array, one entry per nested pipeline:

```json
{"node_id": "research",
 "node_kind": "pipeline",
 "nodes": ["research.hunt", "research.verify"],
 "successors": ["write"],
 "route": null, "loop": null, "on_error": null, "retry": null,
 "suspend_before": false,
 "budget": {"max_steps": 6, "max_tokens": 20000, "max_cost": null, "max_wall_clock_ms": null}}
```

`nodes` is the container's direct children in declaration order, under the ids they record
under; a container nested inside another appears there under its own id. That makes the tree
reconstructible and the entry node unambiguous, since `Graph.entry` is the first node in the
list.

**What is deliberately not on the entry.** No `schema`: a container's `output_schema` is its
terminal child's, so recording it is a second source for one value. No `tools`: a nested
registry merges into the manifest's one `tools[]` array, which is what `tool_effects` reads and
which already distinguishes `offered`.

**Why the container's edges are not folded onto its terminal leaf**, which was the first thing
tried. Three of the four edge fields would survive it: `successors`, `route` and `loop` all
travel with the value the terminal leaf produced. `on_error` does not. A container's error edge
fires from wherever inside it the failure happened, so attributing it to the terminal leaf says
the failure was there. And `retry` collides outright, since a terminal leaf may declare its own
and so may its container, and they mean different things: one re-executes a node, the other
re-executes the sub-pipeline.

`fetch_policy` becomes a list rather than one object, each entry naming the pipeline that
declared it, with `null` for the top-level one. A nested pipeline may be given one today and it
is silently dropped, and "the top pipeline's only" is not a meaning a field should carry.

### 2.2 Everything that reads a container reads it at every level

`_declared_tools` and `_node_entries` walk nested registries, so `_refuse_mixed_currencies` and
the manifest's `tools[]` cover a tool declared in a sub-pipeline. `graph_fingerprint()` digests
`containers[]` beside `nodes[]`, with a container's structural fields being `node_id`,
`node_kind`, `nodes`, `successors`, `loop`, `on_error` and `retry`. `budget` stays out of the
digest, which keeps it consistent with a leaf's `node_budget`: a budget change is recorded and
is not a change of shape.

### 2.3 `variants.py` walks a stitched edge map

One function over `nodes` and `containers` produces the resolved run-time successors of every
leaf id, and `_predecessors`, `_taint`, `_schemas_feeding` and `_removable` read it instead of
`entry["successors"]`. Two rules:

- An edge naming a container resolves to that container's first child, recursively.
- A leaf that ends its container takes that container's resolved successors, recursively.

`_removable` then loses its early return. A node that ends the whole run is removable; a node
that only ends its container is subject to the schema rule, and the map is what tells them
apart.

### 2.4 Removal splices the edge, and the graph judges the arm

Every edge `P -> R` becomes `P -> each successor of R`; where `R` ends its pipeline, `P -> R` is
deleted so `P` ends it instead; `on_error=R` and `Loop(then=R)` rewrite the same way. The result
goes to `Pipeline`, and **an arm its checks refuse is not generated** rather than raising out of
`ablate()`.

**Why splice rather than call every such variant ungenerable.** The library already rewires:
[graph.py `_successors_of`](../../src/simple_agents/graph.py#L617) resolves `successors=None` to
the next node in the list, so dropping a middle node out of the list re-points its predecessor
at what followed it (§1.2). Calling the explicit spelling ungenerable would make `ablate()`'s
output depend on how a builder typed a graph rather than on what the graph is.

**Why the graph judges rather than a check in `variants.py`.** `_removable` is a partial
re-implementation of the graph rules, and §1.3's defect is exactly that it and `Graph` disagree
about what terminal means. The cases where a splice is undefined are all cases `Graph` already
refuses: `R` routes over two successors so `P` inherits two edges and no route, and copying R's
route to `P` would be wrong because a route is a function of R's output; `R` closes a cycle, so
the bound goes with it; `R` has two predecessors and one successor `S`, so `S` starts receiving
a `Join` keyed on `P1`/`P2` where the project reads `inputs["R"]`.

The rebuild asserts its own result: an arm's `declared_nodes()` ids must equal the baseline's
minus the removed one. Anything else is this code's bug rather than the builder's graph, and
raises.

### 2.5 The rebuild preserves nesting

`_replacing` and `_without` walk the container tree and rebuild only the pipelines on the path
to the target, carrying every constructor argument: `budget`, `node_id`, `tools`,
`fetch_policy`, `successors`, `route`, `loop`, `on_error`, `retry`, `suspend_before`. Ids stay
stable, the sub-pipeline keeps its budget, and §1.4's `tools=`/`fetch_policy=` loss goes with
it.

### 2.6 `ablate()` says what it skipped

Returns a `Mapping[str, Pipeline]` that also carries `skipped`, a mapping from node id to the
reason no arm was generated for it. The return type is what `compare_variants` already declares
it takes, so `compare_variants(suite, ablate(pipeline), ...)` is unchanged.

**The precedent is `Join`**, which is a `Mapping` that also carries `absent`, "the in-edges that
did not fire, each holding why" ([graph.py `Join`](../../src/simple_agents/graph.py#L128)). Same
shape, same reason, already documented to builders.

A warning was considered and rejected: it would fire on most routed graphs, and one that always
fires is one a builder configures away. Silence was considered and rejected because FT-12 is
"agency never ablated", and a thin set with nothing to read is how that happens quietly.

### 2.7 `_refuse_incomparable` is left alone

The prefix hardening proposed on the first pass is withdrawn. Un-nesting a node is a legitimate
variant, the end-to-end metric still pairs across it, and `differs_at` with the per-node
`status` already reports which nodes did not pair. Refusing it is the over-refusal
`simple-agents.md` §4.4 and §8.2 name as what gets suites disabled. §1.6's symptom was the
rebuild lying about the ids, which §2.5 fixes at source.

### 2.8 Out of scope, stated

No arms for a container itself. "research as one call" has no definition, since a container is
not an `AgentNode`; "research removed" is a new kind of arm rather than a repair to a broken
one, and the demand for it comes from `items/example-projects.md`, which is not
scheduled.

---

## 3. What was built, 2026-08-10

Thilina's ruling on §2: "Sounds like you know what the right fix is and it covers everything. Go
for it." §2.4's "file the manifest separately" option was already overruled at §2's opening.

### 3.1 An eighth defect, found while building the stitch

`manifest_nodes()` prefixed `successors` and left `on_error` and `loop.then` bare. A node inside
`research` declaring `on_error="rescue"` recorded `successors: ["research.verify"]` beside
`on_error: "rescue"`, which names an id no entry in the manifest holds. The stitch reads both,
which is what surfaced it.

Fixed by computing the prefix once per entry and applying it to all three, in
[recording.py `_node_entries`](../../src/simple_agents/pipeline/recording.py#L458) and in
[`_container_entry`](../../src/simple_agents/pipeline/recording.py#L315).

### 3.2 And a ninth: the prefix scheme was ambiguous

Everything built here keys on the recorded node id, and the id scheme could not tell
`Pipeline([LLMNode(..., node_id="research.hunt")])` from `hunt` inside `research`. Nothing
refused the dotted id, so `containers[].nodes`, the stitch and `_rebuilt`'s descent could all
have been silently wrong on it.

`Pipeline.__init__` now refuses a `node_id` containing a dot, beside the duplicate check that
was already there. `docs/pipeline.md` §1.1 carries it.

### 3.2b A tenth: the results file had the same hole as the manifest

Found on the sync pass after the build, from
[`_config`](../../src/simple_agents/evaluation/runner.py#L2401)'s own comment beside
`config.nodes`: "The same entries the manifest records, because a difference `compare()` cannot
see is a moved number with no candidate cause (FT-15), and two shapes for one thing is how they
came to differ." Adding `containers` to the manifest and not to the results file is exactly the
two shapes that comment warns about.

`compare()` diffs the whole `config` dict, so a sub-pipeline rewired or rebudgeted between two
evaluations produced a moved number with nothing in `changed` to trace it to.
`config.containers` now sits beside `config.nodes`. Results format `0.6` to `0.7`.

### 3.3 What shipped, against §2

Everything in §2, unchanged by building it, plus the three above. Manifest format `0.17` to
`0.18`, results file `0.6` to `0.7`.

| §2 | Built as |
|---|---|
| 2.1 containers[] | `Pipeline.manifest_containers()`, `Manifest.containers`, `docs/run-envelope.md` §2.5 |
| 2.1 fetch_policy as a list | `_close_manifest` over `_pipelines_by_id()`, `docs/tools.md` §4.4 |
| 2.2 read at every level | `_declared_tools` and `_node_entries` over `_every_pipeline()`; `graph_fingerprint` over `_CONTAINER_STRUCTURAL` |
| 2.3 stitched edge map | `_Shape` and `_shape_of` in `variants.py`; `_removable` returns a reason rather than a bool |
| 2.4 splice, graph judges | `_spliced`, `_with_edges`, `_collect` |
| 2.5 nesting preserved | `_rebuilt`, `_same_but`, `_refuse_own_defect` |
| 2.6 skipped | `Ablations`, `docs/evaluation.md` §10.2 |
| 2.7 `_refuse_incomparable` left alone | Unchanged |
| 2.8 no container arms | Unchanged |

**Two things widened past §2 while building.**

**`_taint` follows error edges.** It read `successors` only, so a handler downstream of a
changed node was planned as `replayed` while the `NodeFailure` it receives names a node that
changed. `_Shape` keeps two maps for this: `carries` for where an output travels, which is what
a declared shape is read along, and `reaches` which adds the error edges. `_schemas_feeding`
reads the first, because what travels an error edge is a `NodeFailure` rather than an output.

**Two refusal messages stopped naming schema digests.** `_refuse_reshaped_inputs` said "its
input came from a node declaring 'sha256:bf9a2c476a120490'", which is not something a builder
can act on. Both it and the skip reason now name the nodes: "'research.hunt' feeds it and
declares a different output_schema, so removing it would hand 'write' a value of a different
declared shape".

**A third thing widened past §2**: `config.containers` in the results file, at §3.2b.

### 3.4 What the reproductions say now

Every probe in §1, re-run:

```
FAILURE 1 — the nested arms
  'research.hunt as one call': ['research.hunt', 'research.verify', 'write']
  plan: differs_at=('research.hunt',)
    statuses={'research.hunt': 'changed', 'research.verify': 'unchanged', 'write': 'unchanged'}

FAILURE 2 — the declared-edge spelling
  arms: ['verify removed', 'write removed']        (was: raised, losing the whole set)
  and the defaulted spelling generates the same two.

§1.3 — a container's terminal node
  skipped['research.verify removed'] = "'research.hunt' feeds it and declares a different
    output_schema, so removing it would hand 'write' a value of a different declared shape..."

§1.5 — the taint walk
  nested: {'research.hunt': 'live', 'research.verify': 'live', 'write': 'live'}
  flat:   {'hunt': 'live', 'verify': 'live', 'write': 'live'}
  live_calls: nested 3 vs flat 3                   (was: 2 vs 3)

§1.6 — the fingerprint and the nested registry
  sub-pipeline gains on_error / retry: fingerprint moved: True
  _refuse_mixed_currencies over a nested registry: REFUSED

§1.4 — what an arm carries
  arm pipeline.tools:  <the baseline's registry>   (was: None)
  arm fetch_policy:    <the baseline's policy>     (was: None)
  arm _refuse_mixed_currencies: REFUSED            (was: PASSED)
```

**1503 tests pass**, from 1475. `prose_check` and `check_citations` clean.

### 3.5 What is not built, and why

**No arm for a container itself** (§2.8), unchanged. **`VARIANT_FORMAT_VERSION` stays `0.2`**:
`plan.changed` gains `containers.*` keys, and the format states that `changed` is
`{path: [before, after]}`, which both versions satisfy. **A container's budget stays out of
`graph_fingerprint`**, matching a leaf's `node_budget`: a budget that changed is a run that may
stop somewhere else, not stored state that has stopped meaning anything.
