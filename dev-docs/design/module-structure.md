# What lives in the two largest modules

**Status: measured 2026-08-17, re-measured 2026-08-31, decided 2026-08-31.** This is the
evidence behind the pre-release refactor, scheduled as `P3-63`
([`build-logs/pre-release-refactor-build-log.md`](../build-logs/pre-release-refactor-build-log.md#L1) holds the decisions and
the target hierarchy). It holds the measurement and the method so the record can stay a pointer,
and so the split can be argued from figures rather than from an impression that two files are
long.

**The re-measurement, 2026-08-31.** Both files grew about 30% after 2026-08-17 while `P3-33` to
`P3-62` landed consultation, MCP, conversation, cost stops, slices and throttling:
[`nodes.py`](../../src/simple_agents/nodes/__init__.py#L1) 3,349 → 4,613 lines and
[`pipeline.py`](../../src/simple_agents/pipeline/__init__.py#L1) 2,922 → 4,183, with the `Pipeline` class
at 2,686 lines across 65 methods and `AgentNode` at 1,121 with
[`AgentNode._one`](../../src/simple_agents/nodes/agent.py#L375) (`_one`) at 430. The clusters below
are the same clusters at larger sizes, so the tables keep their 2026-08-17 figures and the
argument stands.

The finding in one line: [`nodes.py`](../../src/simple_agents/nodes/__init__.py#L1) and
[`pipeline.py`](../../src/simple_agents/pipeline/__init__.py#L1) are each about half the abstraction they
are named for, and the other half is the same two subsystems in both files.

## How it was measured

Spans come from `ast`, one row per top-level construct and per method of any class over 300 lines.
**A span is the construct itself, so spans do not sum to the file**: the module docstring, imports
and the blank lines between constructs sit outside every span. Percentages below are against the
file's total line count, not against the sum of spans.

The split between "central" and "lodger" is a judgement, and it is the contestable part. The test
applied was: **would this code still have to exist if the file's named abstraction were the only
thing in it?** `_captured` is central to `nodes.py` because suspension state is a property of the
node that suspends. `_Metered` is a lodger because metering a tool call is the same problem
wherever the call is made from, and nothing about it is specific to a node.

## `nodes.py`, 3,349 lines

| Cluster | Lines | Share | |
|---|---:|---:|---|
| The node types: `AgentNode` 959, `LLMNode` 377, `Deterministic` 138, `Delegation` 132 | 1,606 | 48% | central |
| Value types: `FanOutResult` 63, `Execution` 24, `ItemOutcome` 18, `Node` 17, `NodeOutcome` 10 | 132 | 4% | central |
| Small helpers: `_declare_edges` 45, `_Failures` 28, `_kept_for` 17, `_sequence_for` 17, and three more | 137 | 4% | central |
| Model-call plumbing: [`_call_model`](../../src/simple_agents/runtime/calls.py#L35) 162, [`_emit_failed_call_record`](../../src/simple_agents/runtime/calls.py#L327) 65, `_locate_missing_usage` 55, `_token_sink` 37, message and validation helpers 107 | 426 | 13% | lodger |
| Tool execution: [`_run_tool`](../../src/simple_agents/runtime/tooling.py#L151) 206, [`_FixedPointCaller`](../../src/simple_agents/runtime/tooling.py#L30) 103, refusals 41, `_ToolOutcome` 8 | 358 | 11% | lodger |
| Consultation answers: `_delivered_answer` 84, `_no_one_answered` 38, `_answering_model` 18, `_cost_entry` 15 | 155 | 5% | lodger |
| Cost metering: [`_Metered`](../../src/simple_agents/runtime/metering.py#L12) | 133 | 4% | lodger |
| Tool handles: `_call_retrieval_model` 66, `_retrieval_handle` 42, `_memory_handle` 11, `_deterministic_handle` 9 | 128 | 4% | lodger |
| Suspension capture: `_captured` | 60 | 2% | central |

Central 1,935, lodging 1,200.

[`AgentNode.execute`](../../src/simple_agents/nodes/agent.py#L297) is 397 lines and is not counted as a
problem. It is an interpreter loop over the agent protocol, holding eleven pieces of mutable state
across a `while True` that dispatches four call kinds. Splitting it distributes that state across
methods. **The only duplication found in it** is `_captured(...)` invoked twice with near-identical
eighteen-line argument blocks (folded into one `captured_here` closure at `P3-63` stage 4,
[`agent.py:453`](../../src/simple_agents/nodes/agent.py#L453)) and
[`AgentNode._one`](../../src/simple_agents/nodes/agent.py#L375), and the `node_calls` / `node_tokens` / `node_cost`
accumulation written out four times.

## `pipeline.py`, 2,922 lines

The `Pipeline` class is 1,995 of them, 68%.

| Cluster | Lines | Share | |
|---|---:|---:|---|
| Graph executor: [`_walk`](../../src/simple_agents/pipeline/core.py#L1327) 155, [`_attempt`](../../src/simple_agents/pipeline/core.py#L1690) 128, `_drive` 104, `_settle` 64, `execute` 55, and eleven smaller | 713 | 24% | central |
| Edge and frame state: [`_EdgeState`](../../src/simple_agents/pipeline/edges.py#L92) 220, `_Frame` 53, `_Suspending` 30, `_Edge` 6, `_Stop` 5 | 314 | 11% | central |
| Entry points: `__init__` 113, `run` 113, `resume` 112 | 338 | 12% | central |
| Manifest writer: [`_node_entries`](../../src/simple_agents/pipeline/core.py#L659) 121, `_close_manifest` 52, `_new_manifest` 41, fingerprints 36, `manifest_*` 27 | 277 | 9% | lodger |
| Pre-flight validators: `_refuse_unauditable_cost` 67, `_refuse_unstreamable` 58, `_refuse_unpriceable` 37, and six more | 278 | 10% | lodger |
| Manifest entry helpers: `_container_entry` 49, `_tool_entry` 23, `_stream_waivers` 22, and eleven more | 194 | 7% | lodger |
| Resume support: `_verify_against` 97, `_answers_for` 31, and three smaller | 182 | 6% | central |
| Introspection: `declared_containers` 32, `_declared_with_graph` 30, `to_mermaid` 10, `node_kinds` 6, and five more | 128 | 4% | central |
| Record emission: `_emit_node_record` 42, `_recorded` 13 | 55 | 2% | lodger |

Central 1,675, lodging 804.

## What says the lodgers would move

**Nothing outside either file references any of them.** The entire cross-module surface of the two
files is `Pipeline`, `RunResult`, `NodeEvent` and the node classes through
[`__init__.py`](../../src/simple_agents/__init__.py#L1), `FanOutResult` and `ItemOutcome` into
`suspension.py` and `shapes.py`, and `_digest` and `_schema_digest` into `shapes.py`. Two test
modules reach in further, for `_budget_tripped`, `_EdgeState`, `_Frame` and
`MAX_IDENTICAL_FINISH_REJECTIONS`. Every cluster marked lodger above has zero callers outside the
file it sits in, so moving one touches no caller.

## What says they would not

**A model call cannot be metered from outside itself.** The token and cost figures exist only at
the moment the response comes back, and a node budget has to bind what a tool spends, which is why
[`AgentNode.execute`](../../src/simple_agents/nodes/agent.py#L297) folds a tool's spend into the node's
own totals. That argues the metering **call** stays at the call site. It does not argue the
metering **implementation** stays in the same file, and the two have not been separated in any
proposal yet.

## The cost already being paid

The two files imported each other. `pipeline.py` imported `nodes` at module level, so `nodes.py`
deferred its side into function bodies (`_suspending`,
[`announce`](../../src/simple_agents/nodes/fanout.py#L304),
[`Delegation`](../../src/simple_agents/nodes/delegation.py#L12)'s `__post_init__` and
[`_delegate`](../../src/simple_agents/nodes/agent.py#L976)), with
`_suspending`'s own docstring saying why. *(This listed three sites and named one that no
longer exists; re-read against the code on 2026-08-20.)* `_Suspending`,
`_refuse_over_budget` and `_spent_since` were defined in `pipeline.py` and raised from `nodes.py`,
and `Delegation` needs `Pipeline`. That was one subsystem living in two files, a cost the
old structure paid every day. *(Resolved 2026-08-31 at `P3-63` stage 1: the three moved to
`runtime/`, the `_suspending` helper is deleted, and the one deferred import left is
[`delegation.py`](../../src/simple_agents/nodes/delegation.py#L12)'s.)*

## What this revises

`evaluation/` and `conformance/` are 12,649 lines of 36,514, which reads as an instrument layered
under the runtime. **A further 2,004 lines of the same work sit inside the runtime's two largest
modules**: 1,200 in `nodes.py` and 804 in `pipeline.py`, all of it accounting, validation or
record emission. The instrument is interleaved with the engine rather than layered under it, and
any statement about how much of the library is evaluation machinery has to count these.

## What was undecided, decided 2026-08-31

1. Whether tool execution, model-call plumbing and cost metering become one module or three:
   **three**, `runtime/tooling.py`, `runtime/calls.py` and `runtime/metering.py`.
2. Whether the manifest writer leaves `Pipeline` entirely or only its entry helpers do:
   **entirely**, into `pipeline/recording.py`.
3. Whether the pre-flight validators are a module or belong beside the subsystems they check
   (`_refuse_unstreamable` and `_refuse_unauditable_cost` read a `RunEnvelope` and the rest read
   the graph): **one module**, `pipeline/preflight.py`, grouped by when they run.
4. Whether the two-way import is resolved by the split or needs its own move: **by the split**,
   with one deferred import surviving in `delegation.py`.

The rationale for each is in
[`build-logs/pre-release-refactor-build-log.md`](../build-logs/pre-release-refactor-build-log.md#L1), with the target
hierarchy.
