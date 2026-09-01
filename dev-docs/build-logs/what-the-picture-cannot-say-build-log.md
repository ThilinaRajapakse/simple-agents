# Build log — What the picture cannot say

`plan.md` §1 P3-41. Sitting taken and built 2026-08-28. Its record was
[`build-logs/what-the-picture-cannot-say-build-log.md`](../build-logs/what-the-picture-cannot-say-build-log.md#L1), whose
seven strands are settled here; the subsystem's design of record stays in
[`design/view.md`](../design/view.md#L1).

## 1. Before any design

Every "what decides the shape" in the item record was measured rather than reasoned about.

- **Per-node cost is not in the manifest.** [`manifest.py` `to_json`](../../src/simple_agents/records/manifest.py#L347) writes `totals.cost` for the whole run and `cost_basis`; nothing per node. So the
  run-record half is a trajectory read, which settles strand 1's stated question.
- **The evaluation half is on disk and unread.**
  [`per_node.py:250`](../../src/simple_agents/evaluation/per_node.py#L250) `NodeMetrics.to_record`
  writes `cost` per node, and [`evaluation.py:72`](../../src/simple_agents/view/evaluation.py#L72) `_node_figures`
  `_node_figures` read `tool_spend` and skipped it. On the `branching` fixture that field says
  `answer_directly` costs ten times what any other step costs.
- **`report_over_runs` cannot serve this.** Measured on `dogfood-5-frozen`: 32 seconds, and it
  returns `cost=None` anyway, because
  [`reporting.py:384`](../../src/simple_agents/cli/reporting.py#L384) `_shared_basis` refuses a
  per-node figure over runs written against more than one basis. **That project has five**, and
  2,318 of its 2,393 runs are priced in device-seconds rather than money.
- **Branch counts are already on disk.** `node_execution.route` names the successors an
  execution handed to. Measured over the whole `dogfood-5-frozen` record, 2.54 GB and 12,421
  executions: **1.95 seconds** with the field lifted out of the line rather than the record
  parsed, and it produced `attempt_fetch → fold_resolution 2,423` against
  `attempt_fetch → validate_match 1,848` immediately.
- **Per-edge truth is on disk from the receiving end.** A step with several in-edges records a
  `Join` holding one entry per declared edge. Verified on `branching`: `publish` records four,
  one carrying the verdict and three carrying `'answer_directly' was skipped`.
- **Cost per fan-out item is exact and cost per payload key is not.** `item_index` has been on
  `model_call` since `0.13` and on the rest since `0.26`, so a fan-out's unit is declared and
  attributed. Verified: `read_source`'s two calls carry `item_index` 0 and 1. Nothing declares
  which key of a multi-part volume line is the unit.
- **`touches=` was on `Deterministic` alone.** [`deterministic.py:29`](../../src/simple_agents/nodes/deterministic.py#L29).
  Found while building, not before, and it made `record_access` unreachable from two node kinds.
- **The library already believes an unrecorded store read is a defect.**
  [`memory.py:3`](../../src/simple_agents/memory.py#L3): *"There is no `ctx.memory`: a value read
  from a store that no record names cannot be explained from the trajectory, and per-node numbers
  would be computed over inputs that are not the real inputs."* `touches=` names the hole that
  sentence describes without closing it.
- **Box height was already spoken for.** `P3-40` made a step expand in place, so height cannot
  also carry a quantity: opening a step would read as it costing more. The item record does not
  mention this and it removes one of the three encodings it proposed.
- **`design_confirmed_at` is a stage name, not a fingerprint.**
  [`brief.py:148`](../../src/simple_agents/conformance/brief.py#L148). `design/view.md`'s
  "confirmations record what they were shown against" was written at `P3-35` and never built, so
  "changed since you agreed" had no measurement and at `shape`, where there are no runs, nothing
  to measure against at all.

## 2. Design

**Seven decisions, put to Thilina on 2026-08-28 with options and measured costs.** What he
decided, and what it rules out.

1. **Per-node cost: the whole record, per basis** (option C of four). The evaluation-side join
   is free and ships regardless. Cost per fan-out item ships and is exact; **cost per payload
   key does not ship at all**, because the denominator would be the page choosing one.
2. **No describe callable** (c), with (b) reframed. Thilina: *"I don't get why b is
   hand-maintained. Can't we get it from the code?"* He was right and the framing was wrong: a
   tool's signature, its return type expanded into fields, its docstring, its file and line and
   its body are all readable from the module the page already imports, and none of it is written
   twice. (a) stays declined because it is empty at `shape`, which is the stage he named as
   needing it most, and by `build` a recorded access says what actually came out.
3. **Both** the served endpoint and a `report` mode, on his call. Two readers.
4. **Rethought from scratch on his instruction**, which was right: the first answer picked
   between height, border weight and a bar instead of asking what the drawing is for. The
   allocation that came out: **edge width is how often an edge was taken**, which is the one
   encoding that is genuinely geometric and makes the spine of the system draw itself; **a bar
   inside each step carries one selectable figure**; and **two controls** say what the drawing is
   over and what the bar shows.
5. **His shape language, not the first one.** Thilina: *"The shapes for the three node kinds are
   chosen pretty arbitrarily."* One frame and a glyph tile, three related marks (code, a model, a
   model that loops), which frees the outline to mean status alone. Drawn SVG rather than emoji,
   on his answer: emoji carry their own colour, render differently per platform, and this page is
   printed and screenshotted.
6. **Record the access, and record the value.** Trajectory `0.28`.
7. **C + Z**, built assuming the per-edge entry lands: *"even if it appears over-engineered right
   now, that is fine."* The edge card holds a per-edge slot that today is filled with the one
   shared object and says so.

**And the confirmation fingerprint, built here on his answer to a question the sitting raised**:
`shape_confirmed` in the brief, one `graph_fingerprint` per pipeline.

Weighed and not taken:

- **A `unit=` declaration** for cost per payload item. `over=` covers the exact cases and a
  recorded access covers the store case; a new parameter would exist to make the inexact ones
  look exact.
- **Writing a `resource_access` as a `tool_call`**, which needed no format bump. It would land in
  `counts.tool_call`, be summed by `tool_spend()`, and put an undeclared tool in front of the
  FT-19 checks. The same argument `0.14` made for `delegation`, plus two of its own.
- **Storing the confirmed step list beside the fingerprint**, which would make "new since you
  agreed" exact per step. It puts a copy of the graph in the brief, which is the drift the view
  exists to remove. Per-step change comes from the run ledger, which already computes it.
- **Giving the graph the page's full width when it overflows**, which `P3-40` also weighed and
  declined. The drawing scales to fit down to 72% instead and says what it scaled to.

## 3. Build

Shipped: `ctx.record_access` and the `resource_access` record (trajectory `0.27` → `0.28`);
`touches=` on all three node kinds; `resource_reads`/`resource_writes` per node (results
`0.24` → `0.25`); `shape_confirmed` in the brief; three new view modules,
[`record.py`](../../src/simple_agents/view/record.py#L1),
[`callables.py`](../../src/simple_agents/view/callables.py#L1) and
[`walk.py`](../../src/simple_agents/view/walk.py#L1); the drawing rebuilt in `template.html`;
`/run/<id>` on the served page and `simple-agents report <run> --walk`. **3,308 tests**, 64 of
them new.

What the build found that the design did not know:

- **`record_access` was unreachable from two node kinds.** `touches=` was on `Deterministic`
  alone, so an `LLMNode` or `AgentNode` whose prompt function reads a store could declare nothing
  and therefore record nothing. Extending it is additive and the view already read `touches` off
  any node, but it is an API change the sitting did not foresee.
- **An edge with no count is not an edge never taken.** A nested pipeline's last step routes
  inside its own graph and the container writes no record of its own, so the drawing read
  `read_source → draft` as never taken on a run that took it. An edge is countable only where its
  source recorded a route at all, and the drawing shows no count rather than a false "never".
- **A pipeline whose code moved lost every figure at the moment its history matters most.** The
  record was joined on the fingerprint alone, and the run overlay had already resolved which
  recorded shape a moved pipeline used to be. `_held_for` follows that choice now, which is what
  gives `many-pipelines` its edge counts.
- **`web` had no accesses until tool calls counted as accesses.** The first data view showed only
  `record_access` records, which made the card's completeness depend on the same implementation
  detail the item exists to remove. A tool call and a recorded access are both an access, and the
  card shows them together with a direction derived from the side-effect class.
- **Three edge labels leaving one step landed on each other.** They were placed midway between
  the two boxes, which for three arms of one route is the same point. Each label sits on its own
  curve now, at a fraction that varies by arm.
- **A container's name landed on whichever edge entered it.** It was drawn above the frame, which
  is where the edge labels are. It runs up the frame's left edge instead.
- **The rail forced the page wider than the window.** A signature in `white-space: pre` inside a
  grid column with no `min-width: 0` grows the column rather than scrolling.
- **`Deterministic` was the only kind whose `publish` could reach the draft.** Writing the
  fixture's outbox access the obvious way recorded `characters: 0`, because `publish` joins from
  `critique`, which produces a `Verdict` and not the `Reply`. The access records the value that
  actually arrived.
- **The shape ratchet fired on eighteen units.** Six were new and were decomposed:
  `_one_run`, `_absorb_call`, `walk_run`, `walkable_runs`, `_give_resources_the_record` and
  `assemble`. **Twelve were pre-existing units one argument or one field wider** — `AgentNode._one`
  at 413 lines gained one line from a keyword argument — and the baseline records those rather
  than an unrelated decomposition being done inside this item.
- **`docs/procedure.md` was 4 words under its budget.** The skill's word budget is what stops it
  becoming a second copy of the documents, so the addition was cut to the key name and its
  citation rather than the budget being raised.

### What the reverification cycles found after the build was green

Each was found by re-reading the code against the decision it was meant to serve, not by a test.

- **Decision 1's free half was never built.** The sitting settled that the evaluation's per-node
  `cost` is already on disk and the page should join it, and the build did the expensive half and
  forgot the cheap one. `_node_figures` now reads `cost`, `resource_reads` and `resource_writes`,
  and the step card shows what a step's model calls cost beside what its tools spent.
- **Items handled counted the highest index, not how many there were.** Two runs of a two-item
  fan-out reported two items, so cost per item was double. Counted as a set of run and index now.
- **The fast path could read a payload as a record's own field.** A `node_execution` holding the
  text `"route": ["wrong"]` inside its inputs would have been read as the route the run took, and
  a wrong `node_id` misattributes cost. The head now stops at the first payload and the tail takes
  each field's last match, which costs 0.9 seconds over `dogfood-5-frozen` and is worth it.
- **The walk's cap on calls per step said nothing.** A step with twenty tool calls showed twelve
  and read as a step that made twelve, which is the shape of a loop that ran away. It says how
  many it left out.
- **A step that counts what it moved read as "2 fields".** `_volume` named collections and text
  and not numbers, so `{"rows": 67_353, "kept": 12}` — the shape `ctx.record_access` invites, and
  `DF5-N3`'s own — reported the record's size rather than what moved. It names them now.
- **The new facts did not reach the findings.** Everything this item computed was behind a click,
  so a builder who did not go looking saw none of it. Four families were added: a declared way on
  no run has taken, the step most of the money goes to, a store only the evaluation reaches, and a
  store nothing records. The first two fire on the fixture and read as the sharpest lines there.
- **Two findings became false.** `touches=` carrying no direction was reported for `inbox` and
  `outbox`, which now record which way they went. A recorded access settles the direction the
  declaration never carried, and the card says where the answer came from. This closes
  `P3-40`'s Left open entry rather than deferring it.
- **A store card told a project reached only by tools that its accesses came from
  `ctx.record_access`.** Three cases now, and each says which it is.

### Reading the same pipeline at each stage, added on Thilina's question

*"How can I check what a builder will see in a complex pipeline at different stages?"* He could
not: the six fixtures are one project per **shape**, and stage is confounded with complexity.
The only complex one is 13 steps at `measure`, and everything else is 2 to 6 steps. What a
builder sees at `build`, on a pipeline with a route, a loop, a fan-out, a failure path and a
nested pipeline, was viewable nowhere.

`scripts/view_at_stage.py` renders one project at each stage. **Every stage is the project's own
directory with something taken away** — the evaluation, then the runs — so no second copy of the
graph is maintained and nothing can drift from `agent.py`. `tests/test_view_at_stage.py` asserts
all three draw the same 13 steps.

**It found a claim the page made with no record behind it.** At `shape` the loop edge read
`up to 2× · never`, and "never" is a fact about a record that does not exist yet. The bound is
all the line has to say until something has run.

**What it deliberately does not do** is stand a step down to `NotBuilt`. A real project at
`shape` has most of its steps as placeholders, which is a different `agent.py` and a second copy
of the graph to keep in step. What this shows is the same built pipeline with nothing to overlay,
which is what the drawing does at `build` before the first run. Destination: nothing, unless
reading the two side by side shows the difference matters.

### The page described absence in negatives, and now cannot

Thilina, 2026-08-28, on reading the copy this item wrote: *"Do not describe absence using
chains of negative constructions. State the positive conclusion directly. Prefer 'X is
unknown' over 'nothing says X'."* The finding heads and the card copy were rewritten to lead
with the subject and state the conclusion: `Nothing says which way outbox is touched.` became
`outbox: writers only.`, and `No tool names it and no step has recorded reaching it, so
nothing here says what it holds` became `Contents and direction unknown.`

**The rule is enforced rather than remembered.** `prose_check` gained `negation_cascade` and
`tests/test_prose.py` fires both sides of it: the epistemology form, the cascade reaching a
conclusion, and reasoning written out, against a positive statement, a bare absence and a
mechanism with a consequence.

**It found the pattern in 40 more places** across the shipped surface, including the error
messages in `runner.py`, `envelope.py`, `checks.py`, `answer_key.py` and `search.py`, and text
in four documents. All rewritten.

**The first rule was too broad and caught 111.** It flagged any `so nothing`, which reads a
mechanism and its consequence as the disease: *"the number comes from inside the writer's
lock, so nothing is out of order"* is what the writing rules ask for. The rule requires the
negation chain, and a test pins that distinction. `CLAUDE.md`'s writing rules carry his
wording and three worked examples.

## 4. Verification

- **Live Gemini, twice, re-recording the whole fixture.** `branching`'s two runs and its
  evaluation over three held-out examples at k=2 were made again against
  `gemini-3.1-flash-lite` so the `resource_access` records are real: $0.00014 and $0.00013 for
  the runs, $0.0010 for the evaluation, accuracy 83.3% [50.0%, 100.0%] against a do-nothing floor
  of 0 of 3.
- **The independent cost join agrees with the library's own.** `read_record` computes
  `classify` 4,848 ms and $0.0001764, `read_source` 5,795 ms and $0.0001257,
  `answer_directly` $0.0004515 with $0.004 of tool spend — every figure matching what
  `per_node` wrote into `held-out.json` from the same trajectories by a different path. And the
  per-step costs sum to the manifests' own totals, asserted in the suite.
- **Read against a real project.** `read_record` over `dogfood-5-frozen`: **4.3 seconds** for
  2,393 runs and 2.54 GB, 18 shapes, per-node cost in device-seconds, and 45 distinct edges with
  their counts. The whole page takes **6.5 seconds** to build for that project against 1.4
  before, of which `read_record` is 4.3, `read_runs` 0.7, the walks 0.6 and the evaluation 0.6.
  A project at the `shape` gate pays 0.02.
- **The served page, driven.** `GET /` 200, `/version`, `/run/<id>` returning a walk of the
  newest run and of a rollout under the evaluation directory. Three path-traversal attempts
  (`../../../etc`, percent-encoded, and an unknown name) all refused with 404.
- **The page, driven in a browser.** Chrome over the generated file with the population switched
  to the evaluation and the measure to time: every step's reach appeared, the edge widths
  redrew to the rollouts' counts, the bars became milliseconds and the key said so, and the walk
  section opened and read as one run's story. Screenshots of `branching`, `mid-build`,
  `many-pipelines` and `day-zero` were read at each step, and the label collisions, the missing
  store, the rail overflow and the ragged row heights above were all found that way.
- **`simple-agents report <run> --walk`** against the fixture's newest run: ten steps, three of
  them never reached, with the inbox read, both handbook lookups, five model calls, the question
  put to the rota and the outbox write each under the step that made it.
- **A live run recording from all three node kinds.** The fixture records from a `Deterministic`
  step alone, and `touches=` moved to `LLMNode` and `AgentNode` here, so a separate live Gemini
  pipeline exercised all three: three `resource_access` records, `counts.resource_access: 3` in
  the manifest, and `per_node` attributing a read to each of the first two and a write to the
  third. $0.000052.
- **The fixture's conformance position is unchanged**, checked rather than assumed: the same
  seven checks fail as before this item, `FT-04`, `FT-24`, `FT-29`, `FT-30`, `FT-32`, `FT-34`
  and `FT-36`. `simple-agents check` regenerates the page in all six fixtures.
- **`simple-agents report <run> --walk`**, as text and as `--json`, and a directory holding no
  trajectory refused with exit 2 and a message naming what `--walk` reads.
- vLLM was not started; Mistral is out of credits (`handoff.md`). Nothing in this item touches a
  model client, and the device-basis cost path is exercised by `dogfood-5-frozen`'s 2,318
  device-priced runs.

## 5. Doc consequences

`docs/trajectory-format.md` §1.2 counts six record types and gains §4.5; `docs/pipeline.md` §3's
`NodeContext` table gains `call_tool` and `record_access` with the store example;
`docs/view.md` gains §4.1, §6.1 to §6.4 and a rewritten §10; `docs/evaluation.md` §5 gains the
two resource counts; `docs/conformance.md` §3 gains `shape_confirmed`; `docs/procedure.md`'s
`shape` stage records it; `docs/index.md`'s row for the view is rewritten. `README.md`,
`docs/index.md`, `docs/conformance.md` and `docs/failure-taxonomy.md` say six record types.
`CHANGELOG.md` records all of it, and
[`design/trajectory-format-changelog.md`](../design/trajectory-format-changelog.md#L1) says what
`0.28` cost and why a sixth type rather than a `tool_call`.

## 6. Left open

- **Cost per unit of data, for a unit nobody declares.** Exact for a fan-out and for a recorded
  access; a guess for a key inside a payload, and not shipped. Destination: nothing, unless a
  project asks for it, in which case the answer is a declaration and not a heuristic in the view.
- **The per-edge value entry.** The edge card is built for it and says the honest thing until it
  lands. Destination: [`plan.md` §2.2](../plan.md#L475), unchanged.
- **A describe callable for a resource.** Declined here for stated reasons, and the two deferred
  storage entries are the other side of the same question. Destination:
  [`plan.md` §2.2](../plan.md#L230), unchanged.
- **`AgentNode._one` is 413 lines** and the ratchet has asked about it for several items. Nothing
  in this item touched what it does. Destination: nothing.
- **A wide graph scrolls below 72%.** It scales to fit above that and says what it scaled to.
  Destination: nothing.
- **The product level is still folded into the others**, unchanged from `P3-35`. Destination:
  nothing, until a project with a real product surface meets the view.
