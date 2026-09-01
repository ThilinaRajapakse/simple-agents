# Area A: pipeline, graph and concurrency

Run 2026-08-13 against commit `2f4db4c`, the commit that added concurrency. Live backend was
Gemini `gemini-3.1-flash-lite` on the paid key. Machine-readable results are in
`../runs/area-a-concurrency-live.jsonl` and `../runs/verify-flagged-contradictions.jsonl`.

The concurrency feature itself holds up. Ten live checks passed: declared overlap genuinely
reduces wall clock against a real backend, the manifest records the ceiling, elapsed time is
charged rather than the sum of the calls, `concurrent_items` overlaps a fan-out, all three
construction refusals fire and name the offending node or tool, and non-transitivity holds
(`[["a","b"],["b","c"]]` never overlapped `a` with `c` across a run instrumented to detect it).
A run recorded at `concurrency=4` replays from its own cassette, and it replays with the client
pointed at a dead address and an invalid key, which is what proves the replay serves every call
rather than quietly reaching the backend.

**One blocker was found, and after correction it is partly in the concurrency feature.** The
branch-arm half needs a declared `concurrent_nodes` group and so arrived with this commit; the
retrieval half is older. A-1 carries the corrected measurement and says plainly which claim in
this file it reverses.

---

## A-1. `max_steps` does not bound a run that branches. Blocker.

**What is claimed**, in four places, one of them a shipped docstring:

- [pipeline.md §1.11, line 513](../../../../docs/pipeline.md#L513): "`max_steps` is exact: one call
  is one step, the step is taken before the call, and a call does not start unless one remains."
- [pipeline.md §5, line 918](../../../../docs/pipeline.md#L918): "**One step is one model call, and
  `max_steps` is exact.** The step is taken before the call and a call does not start unless one
  remains, **whether or not calls overlap**."
- [budget.py:129](../../../../src/simple_agents/budget.py#L129), `Budget`: "``max_steps`` is exact:
  the step is taken before the call."
- `CHANGELOG.md` Unreleased, on the concurrency item: "`max_steps` is exact under it, because a
  step is taken before its call."

**What actually happens.** Every node in a declared `concurrent_nodes` group runs, regardless of
`max_steps`. The budget is checked only after the whole batch has executed, so `BudgetExceeded` is
raised after the calls have been made, not before.

**CORRECTED 2026-08-13.** Stream A challenged the reproduction below while implementing the fix,
and it was right. The precondition was re-measured on a git worktree at the pre-fix commit
`2f4db4c`, with `max_steps=1` and eight nodes:

| Shape | `concurrent_nodes` | concurrency | Model calls made |
|---|---|---|---|
| chain of `LLMNode` | none | 1 and 4 | 1 |
| branch arms from a route | **none** | 1 and 4 | **1** |
| branch arms from a route | **all eight grouped** | 1 and 4 | **8** |
| fan-out with `over=` | either | any | bounded |

**The precondition is membership in a declared `concurrent_nodes` group, not branching as such.**
The isolation run that produced this finding declared a group for every "arms" case and none for
every "chain" case, so the two were confounded and the wrong one was reported as the cause. The
defect is real; its statement was wrong.

**This reverses one claim made below.** `concurrent_nodes` shipped with `2f4db4c`, so a node could
not have been in a group before it, and **the branch-arm half is a concurrency regression** rather
than something that predates the item. The retrieval half in `area-de-retrieval-memory.md` D-1
still predates it: `RETR-057` is a one-node pipeline with no group, which made eight model calls
under `max_steps=1` and reported `completed`.

**The boundary, as corrected.** A chain honours `max_steps`. A fan-out with `over=` honours it at
every concurrency. Branch arms honour it too, unless they are in a declared `concurrent_nodes`
group, in which case the whole group runs at any limit including `max_steps=1` and at
`concurrency=1`. The concurrency item's own claim that the axis is exact "whether or not calls
overlap" is what drew attention to it, and that claim was false about the feature the item
shipped.

**The mechanism**, consistent with the measurements: `run.one_step` is called only from
`LLMNode._fan_out`. Every other path reaches `_call_model`, which charges the step after the
response returns, and the run budget is consulted between batches rather than inside one, so a
batch of grouped nodes never consults the remaining allowance before its calls start.

**Why it matters.** `max_steps` is the only budget axis the library documents as exact, which
makes it the one a builder reaches for as a hard stop. The other three axes are documented as
approximate, so a builder who wants a guarantee is directed here. A pipeline that fans work
across 40 arms under `max_steps=5` makes 40 calls and is billed for 40. On a paid backend that
is real money, and the run reports `BudgetExceeded` afterwards, which reads as though the bound
held.

**Reproduction**, no backend required:

```python
from pydantic import BaseModel
from simple_agents import (Budget, BudgetExceeded, Deterministic, FakeModelClient,
                           LLMNode, Maybe, Pipeline, RunEnvelope, fake_response)

class W(BaseModel):
    word: Maybe[str]

calls = {"n": 0}
def answer(request):
    calls["n"] += 1
    return fake_response('{"word":"x"}')

arms = [f"a{k}" for k in range(8)]
nodes = [Deterministic(lambda i, c: i, node_id="plan", successors=arms,
                       route=lambda o, c: arms)]
nodes += [LLMNode(lambda i, c: "go", output_schema=W, node_id=a, successors=["end"])
          for a in arms]
nodes.append(Deterministic(lambda i, c: "end", node_id="end", successors=[]))

pipeline = Pipeline(nodes, budget=Budget(max_steps=1, max_tokens=None, max_cost=None,
                                         max_wall_clock_ms=None),
                    # Without this the eight arms are eight batches with a budget check
                    # between them, and the run makes one call. The group is the precondition.
                    concurrent_nodes=[arms])
try:
    pipeline.run({}, envelope=RunEnvelope(run_dir="/tmp/qa"),
                 model=FakeModelClient(answer=answer), seed=1)
except BudgetExceeded:
    pass

print(calls["n"])   # 8, with max_steps=1
```

**Ruled and fixed.** Thilina ruled Option A on 2026-08-13: the axis is exact on every path
(`../RULINGS.md` D1). Stream A implemented it, placing the reservation at the model call rather
than at the arm, which is a deviation from the letter of the ruling made for a measured reason and
recorded in `../fixes/stream-a-build-log.md`. The four shipped statements stay and are now true.

---

## A-2. `to_mermaid()` does not draw `suspend_before`. Minor. **Fixed.**

[pipeline.md §1.8](../../../../docs/pipeline.md) states that a node declaring `suspend_before` is
drawn by `to_mermaid()`. A pipeline whose second node declares `suspend_before=True` produces
mermaid output containing no marking for it. `Graph.to_mermaid` emits node shapes, successors,
cycle labels and `on error` labels, and reads `suspend_before` nowhere.

Consequence is limited to the diagram: a reader of the drawing cannot see where a run will stop
to ask someone. **Stream A drew them rather than correcting the sentence**, labelling such a node
`stops before`.

---

## A-3. `pipeline.md` overstates what the `graph_fingerprint` covers, and contradicts `run-envelope.md`. Major.

**Two shipped documents disagree, and the code agrees with one of them.**

[pipeline.md line 297](../../../../docs/pipeline.md#L297), on a pipeline used as a node: it "takes
`tools=` and `fetch_policy=` the way the outer pipeline does. All of that is recorded under
`containers` in the manifest ... and **a change to any of it moves the `graph_fingerprint`**."

[run-envelope.md line 88](../../../../docs/run-envelope.md#L88), on the same field: "A digest of the
pipeline's shape: node ids, kinds, edges, loop bounds, error edges, retry policies and output
schemas, for the leaves and for every pipeline used as a node. ... **Budgets are outside it and
are compared separately.**"

**Measured.** Two pipelines identical except for the named part of a contained pipeline:

| What changed on the container | Fingerprint moves |
|---|---|
| `tools=ToolRegistry([alpha])` to `ToolRegistry([beta])` | **no** |
| `budget` from `max_steps=5` to `max_steps=9` | **no** |
| `fetch_policy=HostPolicy(["example.com"])` to `HostPolicy(["other.org"])` | **no** |
| `successors` (control) | yes |

`run-envelope.md` is correct and `pipeline.md` line 297 is not. The budget exclusion is stated as
deliberate in `run-envelope.md`, so that half is documented design; the `tools=` and
`fetch_policy=` half is documented in `pipeline.md` and true nowhere.

**Why it matters beyond the prose.** The fingerprint is not decorative. It gates two refusals: a
suspended run refuses to resume against a pipeline whose fingerprint differs
([core.py:858](../../../../src/simple_agents/pipeline/core.py#L858) (`_verify_against`)), and an evaluation refuses a
recording whose fingerprint moved ([runner.py:2237](../../../../src/simple_agents/evaluation/runner.py#L2237) `_refuse_an_unservable_recording`).
A builder reading `pipeline.md` believes that swapping the tools a sub-pipeline can reach
invalidates a recording. It does not. A replayed evaluation can therefore be served from a
recording made when the sub-pipeline could reach a different tool set, and both refusals stay
silent.

**Reproduction:**

```python
from simple_agents import Budget, Deterministic, LLMNode, Maybe, Pipeline, ToolRegistry
# outer pipeline containing `inner`, identical but for inner's tools=
outer_a = Pipeline([...], budget=B)   # inner tools=ToolRegistry([alpha])
outer_b = Pipeline([...], budget=B)   # inner tools=ToolRegistry([beta])
assert outer_a.graph_fingerprint() == outer_b.graph_fingerprint()   # holds today
```

**Two ways to close it, and the choice is a design decision rather than a repair.** Correcting
`pipeline.md` line 297 to match `run-envelope.md` is the smaller change and makes the documents
agree. Putting a container's `tools=` and `fetch_policy=` into the digest is the larger one and
is what would make the two refusals mean what `pipeline.md` currently promises. The second is
arguable on its merits: a sub-pipeline that can reach a different tool set is a different agent,
and an evaluation that compares the two as one graph is comparing across a change it cannot see.
No patch is proposed here for that reason.

---

## Flags raised by claim extraction that did NOT survive testing

Recorded because a dismissed flag is worth as much as a confirmed one, and because the next
reader should not re-investigate them.

- **`max_steps` charged after the call for a plain `LLMNode`.** A chain of six `LLMNode` under
  `max_steps=3` made exactly 3 calls. The defect is specific to branch arms, as A-1 sets out.
- **A cassette recorded under overlap cannot be replayed.** It replays, both at the concurrency
  it was recorded at and at `concurrency=1`, and it replays against a dead backend address.

## What was not covered in this area

Bounded cycles (`Loop`), `Join` and its `absent` set, `on_error` edges with per-node `RetryPolicy`,
delegation (`AgentNode(delegates=...)`), pipeline-as-node composition, and `ContextOverflow`. These
belong to Area A and are outstanding at the time of writing.
