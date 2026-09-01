# The loop accumulator — the DF2-D1 sitting, and the build

Held 2026-08-09, on `runs/dogfood-2/findings.md` **DF2-D1** and the revisit condition `plan.md`
§2.2 recorded against "shared mutable state with reducers". The finding is that a loop
accumulator went through `ctx.workspace` because no edge could carry it. The question put to the
sitting was whether item 8c's three rejection reasons reach a value that travels on a declared
edge and lands in `inputs`.

**What it settled.** The shape was already expressible, measured rather than argued. Two of the
three things that went wrong across the dogfoods were failures of a shape nobody had written
down, and the third is a real narrowing the library owns. So what ships is documentation, one
keyword on the fan-out, and two closed entries in `plan.md` §2.2.

---

## 1. What was measured, before any design

### 1.1 The base rate: one project of three, and never in the other two

`workspace` does not appear in dogfood-1's or dogfood-1-run2's Python, and **0 of their 103 runs
wrote a workspace file**. Dogfood-2 wrote `chase_state.json` in 16 of its 18 runs,
`search_plan.json` and `unreadable_listings.json` in 11, and `candidates.json` in 2.

### 1.2 Two of DF2-D1's three table rows named the wrong reader

| DF2-D1 said | The file says |
|---|---|
| `search_plan.json` read by `report` | Read by `match_direct`, `agent.py:710` in the dogfood-2 project's own repository. `report` gets the queries from `chase_state.json` |
| "none, eight nodes apart" | `collect_plan` to `match_direct` is four nodes, and distance is not what breaks it |
| Four workspace files | Four in the code; `candidates.json` reaches only 2 of 18 runs, having been added near the end |

### 1.3 What narrows the flow is a node, not a distance

Three facts about the executor, each confirmed in source:

1. **A model node's output is its validated schema.** `chase` returns a `ChaseFinding` and
   nothing passes through it.
2. **A fan-out node's input keeps the surrounding mapping and its output does not.**
   [`_fan_out`](../../src/simple_agents/nodes/fanout.py#L216) builds each item's input as
   `{**inputs, self.over: item}`; the node's output is the outcomes.
3. **One output, one value, to every successor.**
   [`_EdgeState.advance`](../../src/simple_agents/pipeline/edges.py#L264) resolves every out-edge with
   the same object, so a node cannot send a small thing one way and a large thing another.

Three of dogfood-2's four files cross the `read_specs` fan-out and are read at `match_direct`,
the node straight after it. The fourth is the cycle.

### 1.4 The record sizes, which priced every option

`runs/run_334c4ef28db3/trajectory.jsonl`, 1,355,524 bytes:

| node | inputs | outputs |
|---|---:|---:|
| collect_plan | 614 | 814 |
| find_candidates | 814 | 11,080 |
| fetch_pages | 11,080 | 146,305 |
| **read_specs** (`over="pages"`) | **146,305** | **11,980** |
| match_direct | 11,980 | 3,681 |
| select_unresolved ×4 | 3,102 / 3,912 / 5,183 / 3,762 | 880 / 917 / 608 / 178 |
| chase ×4 | 880 / 917 / 608 / 73 | 869 / 2,140 / 719 / 4 |
| finalise | 312 | 5,950 |
| write_notes (`over="suggestions"`) | 5,950 | 456 |
| **report** | **456** | **6,367** |

`report`'s inputs are 456 bytes and its outputs carry the run's deliverable. **Six of the nine
numbers in its `summary`** — `dropped_no_measurements`, `rejected_on_measurements`,
`not_a_tshirt`, `womens_range`, `category_pages`, `unreadable_pages` — and all five search
queries appear in no input of any node. Each query string was checked against the serialised
`inputs` rather than read off the finding.

**The number that decided against building a per-edge value now.** Carrying `unreadable`
(2,762 bytes) from `fetch_pages` to `match_direct` on an edge means forking that node's whole
output: 146,305 bytes, because the unreadables share an output with the pages. Splitting
`fetch_pages` in two does not help, since the second node's `inputs` hold the same 146KB. The
trajectory already holds those pages twice, so a fork writes them a third time and adds 10.8%.

### 1.5 The shape was already expressible, and a probe ran both halves

Against `FakeModelClient`, with nothing in the library changed. **A value forked past a fan-out
and joined back** works: the later node receives a `Join` carrying both. **An accumulator round
a cycle containing an `AgentNode`** works: the node before the model node routes to both it and
a fold node, the fold joins the two, and the fold closes the cycle carrying the working set.
Every value is on a declared edge and in a recorded `inputs`.

So `plan.md` §2.2's revisit condition, "a real project showing a value that cannot travel on a
declared edge", **is not met on its letter**. It was written on the belief that the shape was
inexpressible and DF2-D1 repeats that belief. What is true is weaker: the shape is expressible,
non-obvious, and getting it wrong is silent.

### 1.6 Dogfood-1 run 2 got it wrong silently, and that is the highest-cost measurement

`runs/dogfood-1/run2-findings.md` §6 records the cycle and `Join` as used for what they are for. The
routing decision was right. What it did with the `Join` was not:
[agent.py:206](../../../dogfood-1-run2/agent.py#L206) reads the working set off the edge that
*entered* the cycle, and that edge stays resolved at what entered.

Measured over all 95 runs: **20 went round the cycle twice. `retrieve`'s recorded
`inputs.prepare.passages` is 0 on both executions in every one. 12 runs lost passages the first
pass had retrieved, 29 passages in total.** The union its comment claims never happened.

This did not demonstrably change the score: those passages had already failed to produce an
answer on the first pass. What it demonstrates is the mechanism failing with nothing raised,
nothing recorded and no check firing.

---

## 2. The sitting, 2026-08-09

**Item 8c's three reasons, tested against a value on a declared edge.** Verbatim from
`archive/plan-history.md:160`:

| 8c's reason | Does it reach such a value? |
|---|---|
| "`inputs` becomes a pointer into ambient state so a node is no longer replayable from its record" | No. The value is in `inputs`, verbatim |
| "a change in node A reaches node C with no edge between them, so `compare()._changed` has nothing to key a cause on" | No. There is an edge, in `config.nodes[].successors`, which `compare()` already walks |
| "reachability and successor checks become undecidable because the data dependency is not in the graph" | No. It is in the graph |

All three argue against ambient scope and none reaches a declared edge. **They hold in full
against shared state with reducers, including declared state**, because reasons 2 and 3 are only
answered once the declaration names a writer and a reader, and at that point the declaration is
an edge.

**One fact that locates who reason 1 protects.** No library code reads a `node_execution`
record's `inputs` back; `evaluation/` and `conformance/` were grepped and the only `inputs`
reader is `Example.inputs`. Its consumers are a person or a coding agent reading a trajectory,
and later training data (`simple-agents.md` §5).

**Ruled by Thilina at the sitting.** Documentation and `keep=` now; a per-edge value named in
§3.2.1 with a revisit condition; shared state with reducers closed.

---

## 3. What shipped

### 3.1 `keep=` on a fan-out

`LLMNode(over=..., keep=[...])` names input keys that travel on with the outcomes, arriving as
`FanOutResult.kept`. The fan-out's output container is a library invention, so widening it does
not blur what the model produced, which is why the same move was not made on a model node's
`output_schema`.

**A missing key is refused rather than dropped**, `CallerFacingError` naming the keys that are
there. Dropping it silently would reproduce exactly the failure `keep=` exists to prevent.
Naming the key the node fans out over is refused at construction, since every item of it is
already in the result.

Applied to dogfood-2's `read_specs`, `keep=` delivers 3,726 bytes where the blanket alternative
of keeping the whole input costs 146,305.

### 3.2 The two shapes, written down

`docs/pipeline.md` §1.3 gains what narrows a node's output and how a value reaches a node
further on. §1.4 gains **the edge from outside a cycle keeps the value that entered**, and the
fold shape that accumulates. §2.2 gains `keep=`. FT-28's failure message ended "has to be handed
it" with no pointer, and now cites §1.3.

### 3.3 Formats

Trajectory `0.17` to `0.18`: a fan-out's `outputs` gain `kept`, present only where the node
declared `keep=`, so a record written without one is unchanged. Manifest `0.14` to `0.15`:
`fan_out` gains `keep`, beside `over` and `max_failures`, because adding or removing a kept key
changes what the next node is handed without changing any prompt (FT-15).

### 3.4 Tests

Eleven added, 1380 passing. Eight cover `keep=`: what it carries, what a record holds, that a
record without one is unchanged, the missing-key refusal, and the three construction refusals.
One covers `kept` crossing a suspend point, which it does as any edge value does. Two are in
`test_graph_execution.py` and pin what §1.4 now claims: that the entry edge never carries what
accumulated, and that the fold shape does.

**Both `docs/pipeline.md` examples were run as written** before being pinned, against the
concern `CLAUDE.md` records about unverified examples.

---

## 4. What did not ship, and what would reopen it

**A per-edge value** — a node saying what each out-edge carries, so a fork does not duplicate
what travels with it. It is the only proposal that reaches the third narrowing, and its measured
cost is 146,305 bytes in one run of one project. Against that: `ValueCodec` rebuilds a value in
flight from the schema its node declared, and a projection has none, so suspend and resume would
need a schema per projected edge or a refusal across one; FT-28's arriving-type check would
compare the projection rather than `output_schema`; and the manifest and `to_mermaid()` both
have to show it. Named in `plan.md` §2.2 with the revisit condition.

**Shared mutable state with reducers** — closed, with the three reasons now tested rather than
asserted.

**Recording what a node read and wrote in the workspace** — considered and not built. It makes
the side channel visible without making the right thing easy, it would have fired on dogfood-2
and stayed silent on dogfood-1-run2 whose failure was on-graph, and closing the channel entirely
means taking `ctx.workspace` off a `Path`, which breaks every project for a case that is now
documented.
