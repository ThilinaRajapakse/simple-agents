# Build log — a pipeline exposed to a model as a tool

`archive/plan-history.md` §1.4 is the brief. Started 2026-08-10.

**What the item is for.** An `AgentNode` delegates by calling tools, so a model cannot hand work
to a sub-pipeline and choose the subtasks itself. A `Pipeline` with a `node_id` covers the case
where the builder fixes the decomposition. Nothing covers the case where the model chooses it,
which is why orchestrator-workers has no expression in the library and why research-to-report
and advisory, the two largest shapes in `items/example-projects.md`, have none either.

---

## 1. What was read, and what was checked rather than trusted

`archive/plan-history.md` §1.4 makes three claims that a design would otherwise rest on. Two of them are about
code, so they were run rather than read.

### 1.1 The eval-runner back door is real, and it exists today

`archive/plan-history.md` §1.4 does not raise this; Thilina did, and asked for it to be verified either way
before anything was designed. `simple-agents.md` §4.4 and do-not-change #5 say the eval runner
refuses a non-replayable tool before the first rollout.
[`runner.py` `_tools_of`](../../src/simple_agents/evaluation/runner.py#L2828) is what it reads,
and it walks `pipeline.declared_nodes()`.

**Measured.** A probe built the same `spends_money` tool two ways: inside a sub-pipeline used as
a *node*, and inside a sub-pipeline reached through a tool whose body calls `Pipeline.run`.

```
as a NODE, _tools_of sees: ['paid_search']
as a NODE, declared_nodes:  ['sub.inner_search', 'report']

as a TOOL, _tools_of sees: ['delegate']
as a TOOL, declared_nodes:  ['orchestrate']
as a TOOL, manifest tools:  ['delegate']
as a TOOL, manifest containers: []
```

`declared_nodes()` recurses into `self.nodes` and nothing else, so a pipeline hanging off a tool
is outside the walk. **The refusal does not fire, the manifest records neither the sub-pipeline
nor its tools, and `containers` is empty.** An evaluation of k rollouts over n examples would
execute `paid_search` k × n × (however many times the model delegated) times, and nothing in the
project's artifacts would say it had.

This is a defect in the library as it stands, not only a constraint on the design. A builder can
write that tool today. It is the reason the delegation has to be a declaration the library can
walk rather than a body the library cannot see.

### 1.2 The replay claim is right, and it is right for a reason the brief states loosely

`archive/plan-history.md` §1.4 says `simple-agents.md` §8.2 already settles replay, because "a tool whose
signature asks for a handle is not keyed in the cassette and its body runs again", and a
pipeline-as-tool is that case.

Checked against [`context.py` `call_tool`](../../src/simple_agents/context.py#L593) and
[`tools.py` `re_executed`](../../src/simple_agents/tools.py#L801). The mechanism is
`Tool.re_executed`, which is `True` for a tool holding a `ModelHandle` or a `Workspace`
(`RE_EXECUTED_HANDLE_TYPES`), and `call_tool` returns before keying anything when it is.

**The claim survives, with one correction to how it is stated.** The brief says a
pipeline-as-tool *is* the handle case. It is not: `re_executed` is derived from the signature,
and a delegation has no handle parameter, so nothing today would put it on that side of the
line. What is true is that it belongs on that side **for the same reason**, and the reason is
§8.2's: a filed tool is not run, so its nested records are never written, and a replay would
hold fewer records than the live run. A delegation writes `node_execution`, `model_call` and
`tool_call` records; serving it from one cassette entry would drop all of them.

So no new rule is needed, which is what the brief was reaching for, but a mechanism is: whatever
carries a delegation has to report `re_executed` without owning a handle.

**And the second half of §8.2's rule has to be checked, not assumed.** "Anything not replayed
through the cassette may read the run, provided everything it does externally is itself
replayed." A sub-pipeline's model calls go through `_call_model` and its tool calls through
`run.call_tool`, so both are keyed and both replay. That holds only while the sub-pipeline
reaches the outside world through those two paths, which is the same declaration a
handle-taking tool makes and cannot be detected in Python either.

### 1.3 What the trajectory can express today, and what it cannot

Two facts decide the recording question, and both are in the code rather than in the brief.

- **`node_execution` records carry no parent.**
  [`trajectory.py` `NodeRecord`](../../src/simple_agents/records/trajectory.py#L235) hard-codes
  `parent_id=None` and its docstring says so; `docs/trajectory-format.md` §1.2 and §2 both state
  it. A nested pipeline's nodes are tied to their container by the dotted `node_id` prefix and
  by nothing else.
- **A parent record is written after its children.** `sequence` is taken at emission
  (`docs/trajectory-format.md` §2), so a delegation's `tool_call` record would be written after
  every record the sub-pipeline produced.

Together these mean that with n invocations of one sub-pipeline, the n sets of sub-node records
are distinguishable only by bracketing `sequence` between consecutive delegation records. That
works and nothing documents it, which is the boundary question §1.4 asks about.

### 1.4 Repeated executions under one id are the established case, not a new problem

`archive/plan-history.md` §1.4 asks what ids stay unique across n invocations. The library already answers the
underlying question for a bounded cycle:
[`per_node.py` `NodeMetrics`](../../src/simple_agents/evaluation/per_node.py#L64) says
`executions` can exceed `reached` "where the node sits inside a bounded cycle and runs more than
once in a rollout", and `_count` increments `executions` per `node_execution` record.

So a node id names the node and a `record_id` names the execution. Making ids unique per
invocation would report n one-execution nodes where the library reports one n-execution node,
and would need a second separator beside `.`, which
[`Pipeline.__init__`](../../src/simple_agents/pipeline/core.py#L180) refuses precisely to keep the
prefix scheme unambiguous.

**One consequence to state rather than fix.**
[`runner.py` `_node_outputs`](../../src/simple_agents/evaluation/runner.py#L1805) keys node
outputs by `node_id` into a dict, so the last execution wins. That is already true of a cycle;
for a delegation invoked n times with different subtasks it makes `Example.expected_by_node` on
a delegated node meaningless rather than merely coarse.

### 1.5 `_owners` survives a parent on a node record

[`per_node.py` `_owners`](../../src/simple_agents/evaluation/per_node.py#L839) walks `parent_id`
up to the first node record. A sub-node record is itself a node record, so the walk stops at
step zero and the node keeps its own metrics whatever its parent says. Adding `parent_id` to
`node_execution` therefore does not move any existing figure.

---

## 2. The design

Put to Thilina 2026-08-10 as six decisions. All six approved the same day; D6 was approved
against my recommendation, and the recommendation was wrong.

### 2.1 The shape (D1)

`delegates=` on `AgentNode`, holding `Delegation(pipeline, description=..., max_calls=...)`.

```python
orchestrate = AgentNode(
    plan_the_work,
    tools=[read_page],
    delegates=[Delegation(research, description="Research one question ...")],
    output_schema=Report,
    budget=Budget(max_steps=20, ...),
)
```

**Not a `Tool`.** `Tool` requires `fn`, `parameters` and a declared `side_effect_class`. A
pipeline has none of the three, and its side-effect class would have to be inferred from its
tools, which [`SideEffectClass`](../../src/simple_agents/tools.py#L77) says is never done. The
deciding reason is different though: a declaration `declared_nodes()` can descend gives the
whole pre-flight spine at no cost, `_tools_of` included, and §1.1's back door closes as a
consequence rather than as a special case.

**Ids are `orchestrate.research.hunt`**, with the calling node in the prefix. Without it two
`AgentNode`s delegating to one pipeline collide, which is the duplicate-id case
`Pipeline.__init__` already refuses; with it, uniqueness falls out instead of needing a refusal.

### 2.2 The record type (D2)

A fifth record type, `delegation`. Format goes to `0.19`.

The alternative was a `tool_call`, which is materially cheaper: nothing changes in
`RECORD_TYPES`, conformance, FT-13, or the four-types statements, and `tool_version` =
the sub-pipeline's `graph_fingerprint` is honest. **The whole argument turns on one field.**
`side_effect_class` is read everywhere as a declaration by the tool's author, and it is what the
eval-safety spine reads. A pipeline has none: its effects are its tools', each separately
declared and separately recorded. A null or inferred value there is the quiet falsehood FT-19
exists to prevent.

Emitting no record at all, mirroring
[`_emit_node_record`](../../src/simple_agents/pipeline/recording.py#L29)'s early return for a pipeline
used as a node, was considered and rejected: n would not be countable and the arguments the
model chose would be recorded nowhere, and those arguments are the thing this item exists to
make the model responsible for.

**What it costs**, named so it is not discovered late: `RECORD_TYPES` in
`conformance/checks.py`, `docs/trajectory-format.md` §1.2 and §2 plus a new section,
`docs/conformance.md`, FT-13, `docs/index.md`, `simple-agents.md` §6 including the "do not infer
a fourth node kind" callout, `redaction.py`'s payload fields, and `per_node._count`.

### 2.3 `parent_id` on a node record (D3)

Needed under either D2 answer. It is hard-coded `None` today and
`docs/trajectory-format.md` §2 states that as an invariant. It becomes: the delegation record
for a node inside a delegated pipeline, `null` otherwise. Without it the boundary between n
invocations is derivable only by bracketing `sequence` between delegation records, which works,
is fragile, and is documented nowhere.

§1.5 checked that this moves no existing figure.

### 2.4 The inner budget exhausted, the outer one not (D4)

**Model-facing.** The delegation comes back as an observation naming the axis, and the model
decides what to do; the run budget stays caller-facing, which `_charge_or_stop` already
separates structurally.

The precedent is
[`_refuse_unaffordable_call`](../../src/simple_agents/runtime/metering.py#L143), which raises
`ModelFacingError` at a tool call the cost limit cannot afford and tells the model not to call
it again. A nested pipeline as a node ends the run instead, and that stays right there: the
**builder** chose that decomposition, so an overrun means the plan did not fit. Here the model
chose the subtask, and ending the run discards the delegations that succeeded.

### 2.5 What bounds n (D5)

The sub-pipeline's spend is charged to the calling node's counters, through the same accounting
a `ModelHandle`'s calls get. That is not an addition: [`_nested_call`](../../src/simple_agents/nodes/agent.py#L1151)
already states the rule as "one step is one model call, under every node kind and wherever the
call was made from". With it, `max_steps` bounds n.

**`max_calls` is required only on a sub-pipeline that makes no model call**, which is the exact
analogue of `Loop(max_iterations=)` being required on a cycle, for the same reason and detected
the same way. A delegation is a tool call from the model's point of view, and no tool carries a
call ceiling. The alternative considered was requiring it always, on the argument that a builder
should not have to reason through step accounting to answer "how many times can it delegate".

### 2.6 Suspension inside a delegated pipeline (D6)

**Built rather than refused.** I proposed refusing it on cost grounds and was overruled, and the
objection was right on both counts: the refusal would also have taken out `consult` inside a
delegated pipeline, and `simple-agents.md` §2.9 makes consultation a designed interaction rather
than a fault path.

**The one structural problem.** `SuspensionState` carries a stack of `frames` and exactly one
[`SuspensionState`](../../src/simple_agents/records/suspension.py#L51). That holds today because the nesting
chain is `Pipeline → Pipeline → ... → leaf`, so one leaf is mid-execution at most. Delegation
makes the chain `Pipeline → AgentNode → Pipeline → AgentNode → ...`, and two leaves are then
mid-execution at once: the orchestrator holding a conversation with a pending delegation, and a
node inside the delegate holding one with a pending consult.

**The fix removes a field rather than adding one.**
[`_Frame`](../../src/simple_agents/pipeline/edges.py#L34) already names `in_progress`, the node it
stopped inside; it gains what that node held, and `frames` becomes the whole stack.
`SuspensionState.node_state` goes away, and `SUSPENSION_FORMAT_VERSION` bumps. That refuses
every run suspended by the current version, which costs nothing today.

`suspend_before=True` on a delegated pipeline is refused: it is graph configuration read by
`_walk` for a node in a graph, and a delegate is in none, so it would be configuration that
does nothing.

---

## 3. The build

Built 2026-08-10. **1544 tests pass**, up from 1503; `prose_check` and `check_citations` clean.

### 3.1 What shipped

| | |
|---|---|
| API | `Delegation(pipeline, description=..., max_calls=...)`, `AgentNode(delegates=[...])`, both exported |
| Walks | `declared_nodes`, `declared_containers`, `_every_pipeline` descend into a delegate |
| Trajectory | `delegation` record type, `parent_id` on `node_execution`, format `0.19` |
| Manifest | `containers[].reached_by`, inside `graph_fingerprint` for the calling node and outside it for the prose |
| Suspension | `node_state` moved onto `_Frame`, format `0.3` |
| Metrics | `NodeMetrics.delegations` |
| Drawing | `to_mermaid()` renders the delegate and the edge reaching it |

Seven refusals, all at construction: a pipeline with no `node_id`, an empty description, an
entry node that declares no pydantic model, `max_calls` absent on a worker that makes no model
call, `max_calls` below 1, `suspend_before` on a delegate, and a name shared with a tool or with
`finish`. One is at first walk rather than construction: a pipeline that can reach itself, which
is only constructible by mutating a node after the fact and would otherwise be a stack overflow.

### 3.2 The suspension change is a deletion

[`SuspensionState`](../../src/simple_agents/records/suspension.py#L51) carried a stack of `frames` and
one `node_state`. That held while the nesting chain was `Pipeline → Pipeline → ... → leaf`;
delegation makes it `Pipeline → AgentNode → Pipeline → AgentNode → ...`, and two agent nodes are
then mid-execution at once. `node_state` moved onto
[`_Frame`](../../src/simple_agents/pipeline/edges.py#L34), which already names the node it stopped
in, and the field on `SuspensionState` was removed.

`_Suspending` gained `take_node_state`, so the first frame to collect the state claims it and a
frame further up gets whatever the agent node at *its* level attached on the way past. The test
that pins it asserts two frames both holding a conversation, which the old shape could not
represent.

### 3.3 What the live run found

Run against a local `Qwen/Qwen3-1.7B` on port 8001, `temperature=0.0`, seed 41. The orchestrator
was given one delegate over a four-topic corpus and asked a question needing two of them.

**It chose the decomposition.** Two subtasks, `weight` then `battery`, and not `screen` or
`price`. The final answer used both facts and invented nothing.

**The trajectory is a tree.** Two `delegation` records under the orchestrator's node record, and
each worker's `widen` and `answer` executions under their own delegation. The node ids repeat
across the two and the parents do not, which is the property §1.4 asked about.

**Three model calls before `finish` landed.** Two responses carried no tool call and took the
loop's correction path. A `FakeModelClient` does not produce that.

**One defect.** `to_mermaid()` drew the delegate nowhere, so an orchestrator rendered as a single
box while `docs/pipeline.md` §1.7 says the drawing is how a shape gets checked against what was
meant. A delegate declares no edge on any node, so `Graph` never saw it. Fixed in
[`Pipeline._mermaid_delegates`](../../src/simple_agents/pipeline/core.py#L245), which draws the box
and a dashed edge carrying the call ceiling.

### 3.4 Left open

**`Example.expected_by_node` on a node inside a delegate is not meaningful.**
[`runner._node_outputs`](../../src/simple_agents/evaluation/runner.py#L1805) keys node outputs by
`node_id` into a dict, so the last execution wins. Already true of a bounded cycle, and worse
here because the subtasks differ: comparing a label against "whichever subtask happened to be
last" is not a measurement. The fix is a per-invocation expectation surface, which is a larger
design than this item and has no project asking for it yet.

**A pipeline run from inside a tool body is still invisible**, which is §1.1's defect narrowed
rather than closed. Python cannot tell that body from any other, so what shipped is the rule
stated where a reader meets it: `docs/tools.md` §1 on which to reach for, and FT-20 on what the
refusal does not cover.
