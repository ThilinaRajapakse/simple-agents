# Evaluating an agent that spends money — the build

`archive/plan-history.md` §1.9 is the brief. Started 2026-08-10.

**vLLM was not run at this item.** Dogfood #3 holds the GPU (`plan.md` §1, `handoff.md`), so
the live verification `CLAUDE.md` requires ran against Mistral alone. §6 says what that leaves
unverified. Nothing was rebuilt into `dist/` either, for the same reason.

---

## 1. What was measured, before any design

Six probes, in `scratchpad/paid_eval_probe{1..6}.py`. Three of them check a claim §1.9 asserts;
the other three measure the detour §1.9 says the refusal is.

### 1.1 `max_cost` is depleted by what a tool meters, and the overshoot is one call

Probe 1. A `Deterministic` node calling a `SPENDS_MONEY` tool that takes a `SpendMeter`, five
times, under a run `max_cost`.

| declared | metered | `max_cost` | calls that reached the body | `charged_cost` |
|---|---|---|---|---|
| 0.005 | 0.005 | 0.02 | 4 | 0.020 |
| 0.005 | **0.05** | 0.02 | 1 | **0.050** |
| 0.005 | 0.005 | none | 5 | 0.025 |

**Row 1 confirms §1.9's first claim.** The limit is depleted by the measured figure, and the
fifth call is refused before it is made, model-facing:

```
This run's cost limit leaves 0.000000 USD, and one call to 'buy' costs up to 0.005000.
Do not call it again. Answer with what has already been found, and say what is still
unverified.
```

**Row 2 is the case §1.9 names**, a tool declaring 0.005 and metering 0.05. The pre-flight
passes, because it is checked against `DeclaredCost.ceiling`, and the run ends 2.5× over its
limit having made one call. The next call is refused. So the overshoot is bounded by one call's
excess over its declaration, and unbounded in size, because a tool holding a meter is
authoritative about what it was charged.

`docs/tools.md` §1.5 already states this for the no-`max_per_call` case: "Without it a run can
pass the limit by whatever one call cost beyond `per_call`." What it does not say is that
declaring `max_per_call` does not close it either, since nothing checks the reported figure
against the declared ceiling.

### 1.2 A metered tool is filed in the cassette, and a replayed rollout spends nothing

Probe 2, recording and replaying one pipeline over three paid calls.

| | tool body executed | `spent` per call | `charged_cost` | cassette |
|---|---|---|---|---|
| record | 3 | 0.005 measured ×3 | 0.015 | 3 recorded |
| replay | **0** | `null` ×3 | `null` | 3 hits |

Confirmed, and it is what `RE_EXECUTED_HANDLE_TYPES` says: a `SpendMeter` does not put a tool on
the re-executed side, so the call is served from the file. **A run-time spend check therefore
never fires during a replay**, which is the mode §4.4 exempts. Any ceiling would bind only in
the modes §4.4 currently refuses.

### 1.3 `_tools_of` reaches a paid tool inside a delegate, and the figure at the refusal is wrong

Probe 3. An orchestrator whose only node delegates to a worker pipeline holding the paid tool.

```
declared_nodes: ['orchestrate', 'orchestrate.worker.shop']
_tools_of:      ['buy']
```

**The delegation item's claim holds**: `declared_nodes()` descends into a `Delegation`, so
`_tools_of` reaches inside one and the refusal fires.

**The figure it fires with does not.** The message says the evaluation "would execute it up to
12 times (4 examples × 3 rollouts)". `examples × k` is the number of *rollouts*, and one rollout
can call a paid tool any number of times. Probe 4 measures it, with a scripted model asking for
the tool several times per turn:

| node `max_steps` | tool calls per turn | run `max_cost` | paid executions in **one** rollout | charged |
|---|---|---|---|---|
| 3 | 3 | none | 9 | 0.045 |
| 3 | 3 | 0.02 | 3 | 0.015 |
| 6 | 4 | none | **24** | 0.120 |

So "up to 12 times" is not an upper bound, and neither is §1.9's proposed
`DeclaredCost.ceiling × k × n`: at row 3 the true figure for one rollout is 24 calls where the
arithmetic predicts one. **The only thing that bounds paid calls in a rollout is
`Budget.max_cost`** (row 2), and it bounds them to within one call's overshoot.

This is not specific to delegation. An `AgentNode` reaches it, and so does a `Deterministic`
node calling a tool in a loop (probe 1, five calls in one run).

### 1.4 The detour is a wall on any pipeline that calls a model

§1.9 measured "4 paid calls buying twelve rollouts" and concluded the refusal is a detour.
Probe 5 re-runs that measurement on a pipeline whose node calls a model, which is the shape the
refusal is met on.

```
1. live evaluation                 refused
2. record-mode evaluation          refused
3. one live run per example        4 runs, 4 paid calls, 12 cassette entries
4. replayed evaluation at k=3      ran: 12 rollouts, 0 paid calls
                                   accuracy 0.0, failure_rate 1.0, 12 of 12 FAILED
```

Every rollout raised `CassetteMiss`:

```
No recorded response for call 0 of node 'research' in .../cassette.jsonl.
The nearest recorded request for this node differs in:
  params.seed (recorded 1162146020, now 642011056)
```

**A model call's cassette key carries the request's seed** (`models.py` `params_for_key`), and a
rollout's run seed is `derive_seed(eval_seed, example.id, index)` (`runner.py` `_rollout`). One
run per example records one seed per example, so rollouts 1 and 2 of every example miss. The
evaluation does not raise. It completes and reports a number.

**The loop that works is k×n runs, not n.** Probe 6 records at the seeds the runner will derive:

```
recording loop: 12 live runs, 4 paid calls, 28 cassette entries
replay at k=3:  0 paid calls, 12 of 12 correct, accuracy 1.00
```

Four paid calls, not twelve, because a tool call's key is name, version, arguments and
occurrence with **no seed in it**, so the k rollouts of one example share one recorded answer
and `Cassette.update` serves it. §1.9's money figure is right. Its run count is not.

**What a builder has to know to write that loop**: that the seed is
`derive_seed(eval_seed, example.id, index)`; that `derive_seed` lives in
`simple_agents.context` and is exported from neither `simple_agents` nor
`simple_agents.evaluation`; and that run 2 onward needs `Cassette.update`, because
`Cassette.record` refuses a file that already holds a recording. `docs/evaluation.md` §7.2
instructs `Cassette.record(path)` once and then `Cassette.replay(path)`, which is unfollowable
for n > 1 and, followed as far as it goes, produces the 0.0 above.

### 1.5 The seed set is a pre-flight check that would have caught it

`Cassette.recorded_seeds()` returns every run seed a file names, and the seeds an evaluation
will use are computable before it starts. Over the two cassettes above, against a k=3
evaluation at seed 41 over the same four examples:

```
probe 5's cassette covers  0 of 12
probe 6's cassette covers 12 of 12
```

---

## 2. The argument put to Thilina, 2026-08-10

*§2.1 and §2.2 are the argument as put. §3 is what he decided, which is not what §2.1
recommended.*

### 2.1 §4.4's rationale is satisfied by a ceiling, and the ceiling is not worth having

§1.9 names the argument that is available: `simple-agents.md` §4.4's stated reason is "if a tool
sends an email or places an order, k rollouts is a catastrophe", which is the `irreversible`
case; what it protects is that no rollout performs an action nobody agreed to; and a declared
ceiling checked before the run is agreement. §1.9 also names the condition the argument fails
on: the ceiling has to bind.

**Half of the proposed ceiling cannot be made to bind and the other half can.**
`DeclaredCost.ceiling × k × n` is not an upper bound on anything (§1.3: 24 paid calls in one
rollout against an arithmetic that predicts one), so the pre-flight half fails outright. A
metered running total checked before each paid call does bind, because that is what
`Budget.max_cost` already does per rollout (§1.1 row 1), to within one call's excess over its
declaration (§1.1 row 2).

**So the argument holds mechanically and its premise does not.** What the ceiling would buy is
permission to run a live evaluation over a paid tool. Measured against the path that already
exists:

- **Money.** A live evaluation performs every paid call. The recording loop serves every call
  whose name, version, arguments and occurrence are already on file, because no seed is in a
  tool key. It is therefore never more expensive than the live evaluation it replaces, and it
  was 3× cheaper at k=3 in §1.4 (4 paid calls against 12).
- **What the measurement contains.** The recording loop makes k×n live runs, so every model call
  is live and the variance across rollouts is the real one. Only the paid tool is shared.
- **What is lost by sharing it.** Nothing the library permits. A tool that answers one request
  two ways has to take a handle (`docs/tools.md` §3.2), a paid tool may not take one
  (`Tool.__post_init__` refuses `re_executed` beside `SPENDS_MONEY`), and a recording holding
  two answers under one key is already refused at
  [`runner.py` `_refuse_an_ambiguous_recording`](../../src/simple_agents/evaluation/runner.py#L2050).
  A paid tool is a function of its arguments by the library's own rules.

A ceiling would therefore license something strictly more expensive than the existing path, to
buy a measurement that is the same one. **Do-not-change #5 does not need to move**, and the
recommendation is that it does not.

### 2.2 What is wrong is that the detour is not shipped, and what it instructs does not work

§1.9's first bullet is the whole item. The refusal instructs a loop the library does not ship;
the loop it names cannot be run for n > 1; and the loop a builder writes from the instruction
produces a completed evaluation reporting accuracy 0.0 over 12 failed rollouts (§1.4).

---

## 3. What Thilina decided, 2026-08-10

| | Decision |
|---|---|
| **1** | **Ship the ceiling.** §2.1's recommendation is rejected: *"it's starting to feel like us trying to impose arbitrary doctrine on a builder. If they are fine with a paid evaluation run, why would we stop it?"* |
| **2** | `EvalSuite.record(..., max_spend=)` is the recording loop, a method rather than a function |
| **3** | The seed refusal ships, as a third pre-flight refusal |
| **4** | The FT-20 message splits by class, and its count is corrected. A tool metering above its own declaration is **not** refused |
| **5** | `max_spend` bounds all money in a rollout, model calls and paid calls together, because that is what `max_cost` covers |
| **6** | Both surfaces take it: the ceiling permits a live evaluation and bounds the recording loop |

**Decision 1 is the one that mattered, and the argument that carried it is not the one §2.1
answered.** §2.1 is about cost, and shows the detour dominates on every axis measured. It does
not show a builder is wrong to want the live run. Over-refusal is the failure this codebase has
named at four separate sittings, and refusing to spend a builder's money on their behalf is an
instance of it. §2.1's measurements survive as the thing the refusal now tells them, rather
than as a reason to keep refusing.

**He also asked whether the live path is literally the same work paid for twice.** It mostly
is, and the answer given was: the recording loop makes every model call live, so the agent
varies exactly as much; every *different* tool call is still bought; only an identical repeat
is served from the file. It stops being the same thing only where the tool's answer changes
minute to minute, which is a case the library already refuses to replay
(`_refuse_an_ambiguous_recording`) and cannot support, since a paid tool may not take a handle.
Whether that case is worth measuring is the builder's call, which is decision 1.

---

## 4. What was built

### 4.1 The ceiling binds before the first rollout, not against a running ledger

**§1.9's design does not survive §1.3.** It proposes `DeclaredCost.ceiling × k × n` before the
run plus a metered figure during it. The first is not a bound. The second already exists one
level down: `Budget.max_cost` binds per rollout, on the metered figure, inside a delegate as
well as outside one. Probe 7:

```
delegate's paid spend, run max_cost=None : 12 calls, charged 0.060
delegate's paid spend, run max_cost=0.02 :  3 calls, charged 0.015
```

So `examples × k × max_cost` bounds the whole evaluation, and the ceiling is a **pre-flight
check with nothing behind it**:

- `max_spend` with a budget declaring `max_cost=None` is refused, naming the per-rollout figure
  that would make the ceiling hold.
- `examples × k × max_cost > max_spend` is refused, naming both figures and three ways out.
- Nothing is checked during the evaluation.

**This dissolves §1.9's fourth bullet**, "what happens when it binds mid-evaluation". It does
not bind mid-evaluation. There is no shared ledger across concurrent rollouts, no reserve and
settle, and no question about discarding rollouts already paid for. It also keeps §4.4's built
shape, which is that the check runs before the first rollout.

**Verified against a greedy agent** that never stops buying, at n=4, k=3, `max_cost=0.02`:

```
declared ceiling   0.240000
charged, summed    0.166250
paid calls         33
worst rollout      0.015125   against max_cost 0.02
```

The worst rollout stops at 0.0151 rather than 0.02 because `_refuse_unaffordable_call` refuses
the call whose declared ceiling the remaining limit cannot cover, before it is made.

**Two limits are stated rather than closed**, both in the refusal text. A rollout can pass
`max_cost` by one model call, since a call's cost is known only after it returns; the loop
checks the budget before each call, so the overshoot is one call and no more. And a tool
metering above its own `DeclaredCost` passes it by that call's excess, which §1.1 row 2
measured at 2.5×. Decision 4 leaves that unrefused, so it is documented at every surface where
`max_spend` appears.

### 4.2 `EvalSuite.record`

One live run per rollout, at `derive_seed(eval_seed, example.id, index)`, into one cassette
opened as `Cassette.update` so every run after the first serves what the ones before it
recorded. Returns a `Recording`: the cassette path, the seed to pass to `run`, the run and
example counts, `paid_calls`, `spend` and `currency` measured rather than declared, the entry
count, and the runs that failed.

**A failed run is named rather than raised**, so one bad example does not discard the calls the
others paid for.

**Runs go to `<run_dir>/<eval_id>-recording/`**, where `eval_id` is the same one `run` derives.
The recording that produced an evaluation is therefore findable beside it, and
`_refuse_a_used_directory` does not fire on the pair.

### 4.3 The three refusals, read together

A builder meets these in one minute, so they are worded against each other.

| | Fires on |
|---|---|
| `_refuse_unsafe_tools` | An `irreversible` tool, outright. A `spends_money` tool with no `max_spend`, naming both paths and their prices |
| `_refuse_an_unaffordable_ceiling` | A `max_spend` the pipeline's budget cannot be shown to hold to |
| `_refuse_an_unservable_recording` | A replay whose recording was made at other seeds |
| `_refuse_an_ambiguous_recording` | Unchanged, from the memory item |

**The corrected count.** The old message said an evaluation "would execute it up to `examples ×
k` times", which claims an upper bound it does not have. It now says
`12 rollout(s) (4 examples × 3), each of which may call it more than once`. A test pins the
absence of the old form.

**The seed refusal is narrow on purpose.** It is skipped where the pipeline makes no model call,
since a tool call's key carries no seed and such a recording serves any seed; and skipped where
the cassette names no seeds, which is one recorded before seeds were stored.

### 4.4 What else moved

- `EvalResults.config` gains `max_spend`. Results file `0.7` to `0.8`.
- `docs/tools.md` §1.5 no longer presents `DeclaredCost` as the arithmetic for what an
  evaluation costs. It is the price of a call; `max_cost × rollouts` is the bound.
- FT-20 carries the class split, the count correction, and the recording loop.
- `docs/evaluation.md` gains §6.3 (the recording loop) and §7.7 (the seed refusal), and §7.2 is
  rewritten around `max_spend`.

---

## 5. Tests

**1574 to 1595.** `tests/test_paid_evaluation.py`, 21 in three classes.

`TestTheCeiling` (9): the paid refusal names `max_spend` and `suite.record`; the message no
longer claims a call count; `irreversible` refused even with a ceiling, and its message names
no ceiling; a ceiling over `max_cost=None`; a ceiling under the bound, with both figures; a
greedy agent held under the declared ceiling; the ceiling reaching a paid tool inside a
delegate; `max_spend` in the results; and a replay needing none.

`TestTheRecording` (6): record then replay at the returned seed, 12 of 12 correct with the tool
body never reached; a repeated call bought once, asserted against the same rollouts run live;
what the `Recording` reports; the three refusals; and a failed run named rather than raised.

`TestAnUnservableRecording` (6): a replay at another seed; at a larger k; at a smaller k, which
is allowed; the message naming a generated seed; and a tool-only pipeline not checked.

Two existing assertions in `tests/test_eval_runner.py` asserted `"15 times"`, which is the
claim §1.3 measured false. They now assert the rollout count and the absence of the old form.

---

## 6. Live verification, 2026-08-10

**Mistral only. vLLM was not run**, because dogfood #3 holds the GPU
(`archive/plan-history.md` §1.9, `handoff.md`). What that leaves unverified is stated at the end of this
section. `dist/` was not rebuilt either, for the same reason.

`scratchpad/paid_eval_live.py`: a shopping agent over a paid price-lookup tool, four items,
k=3, against `mistral-small-2603` under a `PacedClient`, `max_cost=0.02` per rollout and
`max_spend=0.24`.

```
1. live evaluation, no ceiling            refused
2. suite.record(max_spend=0.24)           12 live runs, 4 paid calls, 0.021590 USD
3. replay at the recording's seed          12 of 12 correct, accuracy 1.00, 0 paid calls
4. replay at another seed                 refused, "cannot serve 12 of 12 rollout(s)"
5. live evaluation, ceiling 0.06          refused, both figures named
6. live evaluation, max_spend=0.24        12 of 12 correct, accuracy 1.00,
                                          12 paid calls, charged 0.060745
```

**The two paths priced against each other, on a real backend, for the same number:**

```
recording then replay : 12 live runs, 4 paid calls, 0.021590 USD, accuracy 1.00
live evaluation       : 12 rollouts, 12 paid calls, 0.060745 USD, accuracy 1.00
```

2.8× for the identical accuracy, which is §2.1's argument measured rather than reasoned. It is
now what the refusal tells a builder rather than a reason to refuse them.

**What the replay's `charged_cost` is, since 0.0015902 on a run that spent nothing looks
wrong.** `charged_cost` is what depleted `max_cost`, not what left the bank, and a replayed
model call still charges the budget so that a replay behaves like the run it reproduces.
`tool_spend` is the money figure and is `null` across the replay. `Recording.spend` reads
`charged_cost` because in a recording every model call is live, which the arithmetic confirms:
0.020 of paid calls plus the 0.0015902 of model cost the replay reproduces.

**What Mistral alone does not verify.** A `ComputeBasis` run, where `max_cost` is enforced
against a figure that can be an upper bound (`_refuse_bounded_cost`) and where the ceiling's
arithmetic rests on device time rather than token prices. Nothing in this item touches that
path, and `runs/dogfood-protocol.md` already carries the single-backend basis mismatch as open, but the
combination of `max_spend` and a compute basis has not been run.
