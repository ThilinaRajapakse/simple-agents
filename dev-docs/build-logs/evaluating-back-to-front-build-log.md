# Build log — evaluating back to front

`plan.md` §1 `P3-53`. Started 2026-08-28. Written while building, not afterwards.

Built on branch `p3-53`, in a worktree of its own, because `P3-52` was being built uncommitted in
the main tree at the same time and a branch in one working tree would have taken its commits.

## 1. Before any design

Every claim the item rests on, checked against the code before anything was decided.

- **The refusal the item measured, reproduced.** A terminal node lifted into its own `Pipeline`
  runs; any node behind it is refused with *"names 'judge' in its successors, and this pipeline
  has no node with that id"*.
- **The graph checks cannot catch a cut `Join` arm.** A two-node pipeline whose second node
  annotates `Join` and whose predecessor declares no output type **builds**, then fails on the
  first rollout with *"Node 'merge' reads its input as Join, and what arrived from 'judge' is
  dict"*. [`shapes.py` `refuse_disagreements`](../../src/simple_agents/shapes.py#L148) skips a
  node when one arriving type cannot be named, and an unannotated predecessor is exactly that.
  Unannotated on both sides, it builds and runs and reports a wrong figure. **This is why a slice
  decides at construction rather than leaving it to the graph.**
- **A cassette carries no pipeline identity.** A key is the node id, the call index within the
  node, the request material and the seed
  ([`cassette.py` `tool_call_key`](../../src/simple_agents/records/cassette.py#L594)), and a seed is
  `run_seed:node_id:call_index`
  ([`context.py` `derive_seed`](../../src/simple_agents/context.py#L91)). Nothing needed building
  for the item's open cassette question; §4 measures it.
- **`graph_fingerprint` distinguishes rungs and names nothing.** Two rungs get two digests, so
  they do not collide, and a reader holding two results files cannot tell one is a rung of the
  other. That is what decided the manifest block rather than reusing the fingerprint.
- **FT-08 has no check.** It is in `docs/failure-taxonomy.md` and not in
  [`checks.py` `CHECKS`](../../src/simple_agents/conformance/checks.py#L2084), so there was
  nothing to weaken and the note is new.
- **The per-node ratio's shape was settled by precedent.**
  [`outcomes.py` `RolloutOutcome`](../../src/simple_agents/evaluation/outcomes.py#L271) already
  stores an end-to-end ratio as `{name: (numerator, denominator)}` per rollout.
- **§9 item 12 was read and is not near this.** It rules out a second syntax for *declaring* a
  graph. `slice()` derives a pipeline from one declared in Python.

## 2. Design

Five decisions were taken at sitting 6 and nine more at the design sitting on the branch, all in
the record this file replaces. The two that shaped everything else:

**`nodes=` exists because two bounds cannot describe a branching graph.** The sitting first
proposed a computed span with a refusal for any branch leaving it. Thilina: *"is it enough to
provide just a start and a end for a branchy pipeline? Or do we need to provide the option to
select nodes by name and refuse disconnected selections?"* — and, on the separate question of
what a span excludes, *"I guess this is basically the question I asked for D2?"* It was. Naming
the set answers both.

**A cut edge is one concept and works in both directions**, which replaced a refusal. An in-edge
whose source is outside stays declared and never fires, so a node that took a `Join` still
receives one with that arm in `absent` — which is what it receives in the whole pipeline whenever
the route went the other way. An out-edge whose target is outside stays declared too, so a route
selects the arm it would have selected and the run ends at the boundary rather than being sent
down a surviving arm. **Rejected:** dropping the arm and the route, which would have sent every
rollout to the surviving arm and measured a path the agent does not always take; and refusing,
which breaks the ladder at the first join in the tail, the shape `Join` exists for.

**A run that reaches a cut out-edge is left out rather than failed.** `Outcome.LEFT_THE_SLICE`
and a `left_the_slice` cause in
[`metrics.py` `LEFT_OUT_CAUSES`](../../src/simple_agents/evaluation/metrics.py#L72), so every
figure prints the count beside the number the way it already does for an unanswered consultation.
No new run outcome: `stopped_early` already carries a reason.

**`EVAL_FORMAT_FLOOR` was pulled in on Thilina's ask** after the sitting noted in passing that
[`simple-agents.md` §9 item 7](../simple-agents.md#L1) makes the results file additive by default
while `EvalResults.read` refused any version mismatch, so an additive bump destroyed a held file
anyway: *"Is there a soluton to the additive changes destroying a held file? Ideally, one we can
pull in here?"*

**FT-08's note clears on a current slice.** The first proposal was that a slice never clears it,
which Thilina rejected on the ground that *"we can't have a project seeing this note for ever when
it thinks it already did what was asked"*. It clears while `slice.of` matches the pipeline's
`graph_fingerprint`, which is the comparison FT-37 already makes.

## 3. Build

**Formats.** Manifest `0.38` to `0.39` for the `slice` block; results file `0.28` to `0.29` for
per-node ratios and `config.slice`, with `EVAL_FORMAT_FLOOR` at `0.28`. Both pre-assigned so this
and `P3-52` could not collide. **3825 tests**, from 3751.

**Surfaces touched.** `graph.py` gains `CutEdge`, `cut_in`, `cut_out` and `routable`;
`pipeline.py` gains `SliceOf` and `Pipeline.slice`; `errors.py` gains `LeftTheSlice`;
`examples.py` gains `ExampleSet.entering`; `ratios.py` loses `refuse_a_ratio_per_node` and gains a
node-scoped comparison; `per_node.py`, `outcomes.py`, `runner.py`, `results.py`, `compare.py`,
`reporting.py`, `conformance/run.py` and `conformance/produced.py` all move.

**What the build found that the design did not know**, each fixed and each with a test:

- **The entry's cut in-edges have to leave the graph.** Recording them made the slice's first node
  a node with one in-edge that never fires, and `arriving_at` raised `KeyError` on a source
  outside `by_id`. The entry receives what `run` was passed, which is the point of the operation;
  they stay on the slice's record because what was cut is provenance either way.
- **Cut in-edges are collected from the nodes outside the slice**, not from the ones inside. The
  first pass walked only the kept nodes, so the headline case — `present` keeping its arm from
  `apologise` — silently lost the edge it exists to keep.
- **A slice whose every exit is cut is refused.** A cycle held without its loop's `then` has no
  node ending it, and `Graph`'s message for that tells the builder to leave `successors` off the
  final node, which is meaningless here.
- **`_edges_of` and `routable` treat `on_error` differently**, found by cycle 4 and recorded there.

## 4. Verification

Live against **vLLM**, `Qwen/Qwen3-1.7B` on port 8001, two runs on 2026-08-28. Mistral is out of
credits, so no Mistral arm.

**The item's open cassette question, answered by measurement.** A three-node pipeline
(`gather` → `shortlist` → `judge`) ran live and recorded; `judge` produced `chosen='Dune'` from two
real calls of 15 and 10 output tokens.

- **Rung one on the ideal input replayed the full run's recording**: `judge` alone, handed the
  value `shortlist` produced, at the same run seed. **1 cassette hit, 0 misses**, `replayed=True`
  on the call record, and byte-identical output. Nothing needed building for this.
- **The same rung on a different ideal input missed**, with the message naming the difference:
  *"messages[1].content (recorded 67 chars, now 80 chars)"*.
- **Rung two ran live** and reproduced the full pipeline's output.

**An evaluation over a rung whose examples include one the rung does not hold.** Three examples,
one routed to the arm the rung leaves out:

```
outcomes: {'q1': 'correct', 'q2': 'correct', 'q3': 'left_the_slice'}
accuracy  100.0%  [34.2%, 100.0%]  n=2 over all rollouts, less 1 that took a path this
                                   slice does not hold
gather terminations: {'left_the_slice': 1}
```

That sentence is what decision 9 asked for: the figure is over the rollouts that stayed inside,
and what left is counted beside it with the reason.

**Seven reverification cycles**, four of which found something. Cycles 5, 6 and 7 were clean.

- **Cycle 1 — a ratio compared as though it were a mean.** Two defects, both by reading. A
  per-node ratio was paired on `nodes[].scores`, where a ratio records nothing, so `compare()`
  reported *"No shared example falls under the denominator on both sides"* with every example on
  both sides; measured, a figure that went 6.0 to 18.0 got no verdict and a false reason. And a
  ratio's scoring rule could move unseen **end to end as well** — `_version` read the `version`
  key, which a `ProjectRatio` does not write; measured, a figure that tripled reported
  `rule_moved=None`. The second predates this item and is `P3-48`'s.
- **Cycle 2 — clean.** A slice holding a pipeline used as a node, `concurrent_nodes` narrowing, a
  cut in-edge across a suspension, `rerun` of a rung, and a slice of a slice. All five are tests.
- **Cycle 3 — a rung's runs read as the agent's.** `simple-agents report runs/` listed a rung's
  nodes with nothing separating them: a rung runs under the role the agent does and keeps its node
  ids, so the roles line cannot show it, and the node it starts at ran on every one of its
  rollouts and on some share of the agent's. Counted on its own line now.
- **Cycle 4 — an error edge read as a route arm.** `routable()` counted a cut `on_error` handler
  among the arms, so a slice holding a node whose handler was outside was refused with *"declares
  2 successors and no route"*. And `_edges_of` appended a handler the pipeline did not hold, so
  `_invert` raised `KeyError` on it. Both fixed; measured, the node fails, the run ends at the
  boundary with `kind: on_error`, and a slice holding the handler still recovers.
- **Cycle 5 — clean.** Fan-out, tools, budget, `fetch_policy`, `node_id`.
- **Cycle 6 — clean**, and it is the live evaluation above.
- **Cycle 7 — clean.** Every example in the new doc sections executed, which `prose_check` parses
  and never runs.

**Three more cycles after the rebase onto `P3-52`**, over the tree holding both.

- **Cycle 8 — `against_baseline` had cycle 1's defect in a second function**, which was left
  alone while `P3-52` was building that function and is fixed now the collision is gone. Measured
  on the merged tree: a ratio whose floor scored 3.0 and whose agent scored 1.0 reported
  `examples=0` and *"No shared example falls under words's denominator on both sides"*, over five
  examples that were on both sides. A baseline over a rung, a baseline where every rollout left
  the slice, and a per-node ratio beside a baseline were all already right.

## 5. Doc consequences

- **`docs/evaluation.md` §5.6**, new: the strategy, the three forms, what a rung is run on, what
  the slice does at its edges, and reading the rungs together. §5.3 and §11.5 gain the per-node
  ratio; §8 gains the format floor, `format_version` and `carries`.
- **`docs/pipeline.md` §1.14**, new: `slice` as a `Pipeline` operation.
- **`docs/run-envelope.md`**: the manifest's `slice` key, `stopped_early` gaining
  `left_the_slice`, and the runs report counting rungs on their own line.
- **`docs/failure-taxonomy.md`**: FT-08 gains the note and a paragraph on evaluating a step alone.
- **`CHANGELOG.md`**: one entry, six paragraphs.
- **The `improvement` scaffold at `measure`** now asks which step the number was lost at and names
  all three answers.

**Statements that stopped being true.** `refuse_a_ratio_per_node`'s message said a ratio per node
*"would be declared and never reported"*; it is reported. `ProjectRatio`'s docstring and
`NodeMetrics.metrics` both said the figures per node were means.

**`docs/procedure.md` stage 5 gains the paragraph, and the skill's word budget moved to let
it.** The file stood at **2999 of 3000 words**, so the addition needed either a cut or a raise,
and neither is a build decision. Thilina raised it to 3200 on 2026-08-28: what the budget is
against is a skill restating the documents, and paying for a new instruction in one stage by
cutting one from another is not that. The file is at 3085 words.

## 6. Left open

- **A slice of a slice names the one it came from**, so a rung of a rung does not join back to
  the original and FT-08's note would not clear on one. The natural way to build a ladder slices
  the original each time. Destination: `nothing`.
- **Whether the results visualiser draws a ladder** is `P3-51`'s, and its record carries the row,
  a seventh open decision and the pointer.
  [`design/results-visualiser.md`](../design/results-visualiser.md#L1).
