# Build log — `over=` on every node kind, and tools on `LLMNode`

`plan.md` §1 P3-15. Started 2026-08-18. Written while building, not afterwards.

## 1. Before any design

**The constraint, read off the constructors rather than off `DF4-N6`.** It is not one hole: three
of six cells were filled, and `Deterministic` having no `over=` is the one the candidate never
named.

| Node kind | Tools | `over=` |
|---|---|---|
| [`Deterministic`](../../src/simple_agents/nodes/deterministic.py#L29) | `tools=`, through `ctx.call_tool` | no |
| [`LLMNode`](../../src/simple_agents/nodes/llm.py#L36) | no | `over=` |
| [`AgentNode`](../../src/simple_agents/nodes/agent.py#L138) | `tools=`, the model choosing | no |

**The mechanism was already generic in all but two lines.** About 200 lines sat inside `LLMNode`
and only `self._one` and `self.output_schema` were specific to it.

**Three of the six questions the item recorded were sized wrong, and reading the code is what said
so.**

- **`spends_money`'s proof needed nothing.**
  [`_refuse_an_unaffordable_ceiling`](../../src/simple_agents/evaluation/runner.py#L2187) computes
  `examples × k × pipeline.budget.max_cost` and reads no node budget at all, and
  [`Budget.narrowed_by`](../../src/simple_agents/budget.py#L185) is a per-axis minimum, so a node
  can only narrow what the run allows. The item had recorded this as open.
- **`Deterministic` with no schema follows a rule that already existed**, which is that plain data
  crosses a suspend point.
- **Numbering a call was recorded as documentation and is a correctness problem.** `call_index` is
  keyed per `node_id` and feeds [`derive_seed`](../../src/simple_agents/context.py#L91); the seed
  is part of the cassette key; and `AgentNode` took the default path,
  `run.next_model_call(node_id)`, a monotonic per-node counter. Sound only because the node runs
  once. Under `over=` with `concurrent_items`, a call's number would depend on thread scheduling,
  so its seed would, so a re-run would miss the cassette.

**Two budget mechanisms, and only one is thread-safe.** The run budget is enforced in
[`RunContext.one_step`](../../src/simple_agents/context.py#L603) under a lock. The node budget is
enforced inside `AgentNode` against four plain local variables, checked by
[`_budget_tripped`](../../src/simple_agents/runtime/budgets.py#L101) at the top of each turn, with no lock
because a node runs once.

## 2. Design

Six decisions, taken at the sitting of 2026-08-18. `items/fan-out-and-node-shape.md` carried them
while the item was open and is superseded by this section.

**1. Both budgets, and `budget_per_item=` is refused on a node that runs once.** Thilina's
principle: *"The behaviour of one parameter probably shouldn't change based on whether another
parameter is set."* `budget=` keeps its single reading. **What was weighed and not taken:** making
`budget=` mean per-item under `over=`, which was the first recommendation and was withdrawn once
the two mechanisms above were read; and refusing `budget=` on a fan-out entirely, which was the
first version of Thilina's proposal and would have left no way to bound a fan-out as a whole.
**The estimate that was wrong:** a node total across concurrent items was put to him as costing a
hand-rolled locked accumulator. `RunContext` already holds the library's only locked spend
accumulator, so it was a scope in that one place instead.

**2. Capture the in-flight item's state rather than running it again.** Thilina, with the
constraint attached: *"Concurrency is tricky at the best of times, and suspension thrown in the
mix makes it a minefield. A re-run is probably better than an incorrect resume, so make bloody
well sure that (b) does what it's supposed to."* **Weighed and not taken:** discarding the item,
which was the cheap option and makes one node kind behave two ways depending on a keyword; and
refusing a suspend inside a fanned-out `AgentNode`, which forbids the case dogfood #4 produced.

**3. `call_index` becomes an item and a step.** **Weighed and not taken, and this reverses the
recommendation put to him:** keying the counter and the seed on `f"{node_id}#{item_index}"`, which
reuses every mechanism unchanged. Thilina: *"(c) only if it's the better option compared to (b).
If the reason to go (c) over (b) is the trajectory format bump, that's not a good reason."*
Re-argued with the bump off the scales it is not: it creates two identifiers for one node with
nothing keeping them straight, since `_model_calls`, `_last_input`, `CassetteEntry.node_id` and the
trajectory's own `node_id` are all one string today. A composite integer is the same objection with
the pair hidden inside an int, plus a stride that collides silently.

**4. Nothing.** Closed by measurement, §1.

**5. A `Deterministic` fan-out dumps against `output_schema` where one is declared and requires
plain data where none is**, which is the rule `_captured` already applies to a tool result.

**6. `ItemOutcome` gains `termination`.** `DF4-I21` and `DF4-I22` read that field and after this
read it per item, which is why they sit behind this item.

**What the sitting also declined.** [`findings.md` §8.3](../runs/dogfood-4/findings.md#L1153)
checked `DF4-N6` against the artifacts and returned that the constraint produced the better shape,
taking per-book agreement from 0.867 to 1.0. That was put as the case for shipping nothing.
Thilina: *"I wouldn't read too much into what improved a dogfood or not."*

## 3. Build

**2650 tests, from 2629.** Trajectory `0.24` to `0.25`, manifest `0.26` to `0.27`, suspension
`0.4` to `0.5`.

**Surfaces touched.** `nodes.py`, `context.py`, `cassette.py`, `context_builder.py`,
`trajectory.py`, `budget.py`, `pipeline.py`, `manifest.py`; `docs/pipeline.md`,
`docs/trajectory-format.md`, `docs/run-envelope.md`, `CHANGELOG.md`;
`scripts/record_backend_cassettes.py`.

**The fan-out mechanism moved out of `LLMNode` to module level**, as
[`_declare_fan_out`](../../src/simple_agents/nodes/fanout.py#L126) beside the `_declare_edges` it is
modelled on, and [`_fan_out`](../../src/simple_agents/nodes/fanout.py#L216) taking a `one` callback that
is what a single item means for that kind. `_declared_tools` is the same shape for the tool
checks, which `Deterministic` and `LLMNode` now share.

**Four things the build found that the design did not know.**

1. **Keying `_last_input` per item removes the overflow estimate from every fan-out item.** That
   map feeds the context builder's tokens-per-char ratio. Per item, every item of an `LLMNode`
   fan-out has no previous call, so the pre-flight silently stops working for the node kind most
   likely to overflow. It is a property of the node and the backend and any call measures it, so
   it stays per node. `test_the_first_item_has_no_estimate_and_later_items_do` is what caught it.
2. **The measurement still has to name its item even though the map does not.** With every item's
   only call at `call_index=0`, `Estimate.measured_on_call` pointed at three different calls.
   `measured_on_item` is the fix, and `NodeContext.last_item_index` carries it. Keyed per node,
   recorded per call: different questions, and the first pass collapsed them.
3. **`AgentNode` never passed `item_index` to `_call_model`**, so a live three-item fan-out
   recorded `item_index: null` on all six calls and seeded them by interleaving. The record added
   for §2's decision 3 is what surfaced it, on the first live run.
4. **A delegated pipeline suspending inside a fan-out item would have been collected as an item
   failure.** `_ends_the_run` and the item's own `except` both name `Suspend`, and a delegate
   raises the pipeline's `_Suspending`, which is not one. New with this item, because only an
   `AgentNode` can delegate and only now can one fan out.

**One defect found at the reverification pass, in the node total this item added.** The scope
was charged by [`_call_model`](../../src/simple_agents/runtime/calls.py#L35) alone, so it saw a node's
own turn calls and not what its tools and delegates spent. The agent loop already picks those up
into `node_calls` at three points, with the rule written beside one of them: *"A model call made
inside a tool is charged to the run by `_call_model`; the node's own totals have to pick it up
too, or a node budget would not bind what its tools spend."* The scope is a node total and was
not following it. `RunContext.charge_scope` is the fix, charging the scope alone for spend the
run was already charged for. Measured: a four-item fan-out whose every turn costs three calls
made **9** against `budget=Budget(max_steps=9)`, where before the fix the scope saw three of every
nine.

**One behaviour change that came with the numbering, found at the reverification pass.** A
retried fan-out now re-attempts with a fresh seed. Numbering a call by its item's index meant
both attempts sent one seed and so were one cassette entry, and the entry holds the failure that
caused the retry, so a replay served it again and the retry could not succeed. A retried node
that does not fan out has always had a fresh number per attempt, so this is the fan-out joining
the rule rather than a new one.

**One defect fixed outside the six decisions.** `ctx.call_tool(self, name, **arguments)` made a
tool with a parameter called `name` unreachable. One character, and this item doubled the surface
that reaches a tool that way.

## 4. Verification

**Live against vLLM `Qwen/Qwen3-1.7B` on port 8001**, `--gpu-memory-utilization 0.6`, with one
call preflighted at `max_output_tokens=4000` before any run (1.4s, `finish_reason=stop`, 242
output tokens).

| What it had to show | Result |
|---|---|
| An `AgentNode` fans out, each item running its own loop with tools | two items, both `termination="finish"`, `keep=` carried through |
| A call names the item it belongs to | `item 0 call 0`, `item 1 call 0`, `item 2 call 0` |
| An item's seeds hold across two runs | identical per item across two runs |
| The node total bounds the items together | 7 calls against 15 unbounded, over five items |
| An item that never ran says why | `NodeBudgetExceeded` on the items left, run still `completed` |
| A concurrent fan-out suspends and resumes | `asked: 0`, state held for item 0, both items finished after the resume |
| The single-budget warning fires and names the axis | *"nothing bounds the node as a whole except the run"* |

**The `context` cassette was re-recorded against vLLM**, since `context.jsonl` was a Mistral
recording and Mistral is out of credits. `context-vllm` is the new arm and the old file is gone.
**That move found a latent bug in a shipped test**: `test_the_estimate_is_close_to_what_the_backend_reported`
summed `input_uncached + input_cache_read`, two of three disjoint classes. Mistral bills no
cache-write class so the sum happened to be the whole prompt; against a backend with a prefix
cache the recorded split put 32 of a 44-token prompt in `input_cache_write`, and the assertion
compared an estimate of the whole against a quarter of it.

## 5. Doc consequences

| | |
|---|---|
| `docs/pipeline.md` | §2's table gains a column for who chooses a tool call and a paragraph saying `over=` is on all three; §1.2's flattening rule is no longer `LLMNode`-only; §1.8 says what a stopped fan-out holds; §1.10's `concurrent_items` row says an item is a loop on an `AgentNode`; §2.1 and §2.2 cover the other two kinds; **§2.3 gains the two budgets**; §5 is three places rather than two |
| `docs/trajectory-format.md` | `item_index` on the `model_call` record, the sample line, and the version in three places |
| `docs/run-envelope.md` | `node_budget_per_item` in §2.6's table and in the `nodes` row; manifest version |
| `CHANGELOG.md` | Seven entries under one heading, and the three format moves |

**Five shipped statements stopped being true, and four were found at the reverification pass
rather than while writing the docs.** `docs/pipeline.md` §5 read *"A budget is set in two
places"*. [`pipeline.py`](../../src/simple_agents/pipeline/__init__.py#L1)'s module docstring said a node
running once per item *"is still an `LLMNode` with `over=`"*, which is the sentence this item
moved. Two overflow messages told a builder to *"fan out over it with `LLMNode(..., over=...)`"*,
advice that named one kind only because `over=` lived there. `docs/context.md`'s table of what
each kind is handed had no row for a fanned-out `AgentNode`. And `AgentNode`'s own docstring
documented neither `over=` nor `budget_per_item=`.

## 6. Left open

- **Nothing bounds calls per unit of time.** `concurrent_items` and `Pipeline.run(concurrency=)`
  bound calls in flight, and after this an item is a loop rather than a call, so the one knob that
  looked like pacing stops approximating it. [`plan.md`](../plan.md#L88) §2.1's *A ceiling on how
  much reaches one model client*, which this item's fourth instance promoted there.
- **A ceiling on a fan-out as a whole, distinct from the run and from one item**, for a project
  that wants to cap a fan-out without capping the run. `budget=` is that ceiling for an
  `AgentNode`; `Deterministic` and `LLMNode` take no budget argument, so for them there is none.
  Owed to [`plan.md`](../plan.md#L91) §2.2.
- **`DF4-I10` and `DF4-I32`** are the two defects in the mechanism this moved, and both now land in
  its final home. [`runs/dogfood-4/inventory.md`](../runs/dogfood-4/inventory.md#L64) §3, sitting 1.
