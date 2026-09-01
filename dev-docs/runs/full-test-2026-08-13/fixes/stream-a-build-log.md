# Stream A build log — pipeline, graph, budgets, concurrency, suspension

Files owned: `src/simple_agents/nodes.py`, `pipeline.py`, `budget.py`, `graph.py`,
`suspension.py`, `concurrency.py`, `docs/pipeline.md`, tests over graph execution, budgets,
concurrency and suspension, and the `suspensions` field of `manifest.py`.

Baseline at start: HEAD is [`2f4db4c`](../../../), the commit the checkpoint tested. The full
suite was 1878 passed, 1 failed (`test_procedure.py::TestInit`, another stream's, fixed by them
during the pass).

---

## 1. D1. `max_steps` is exact on every path

**Ruling:** Option A, [RULINGS.md §D1](../RULINGS.md#L9). Branch arms from a route and the
embedding/rerank calls inside a search reserve the step before dispatching, under the lock, the
way [`nodes.py`](../../../../src/simple_agents/nodes/__init__.py#L1) `LLMNode._fan_out` already did through
`run.one_step`.

### What the finding's written reproduction actually needs

[A-1's reproduction](../findings/area-a-pipeline-graph.md#L73) does not reproduce on
`2f4db4c`: it makes 1 call under `max_steps=1`, not 8. `_batch` takes the first ready node plus
any node a `concurrent_nodes` group says may overlap it, and the reproduction declares no
group, so the eight arms are eight batches and `_charge_or_stop` runs between them.

The measured row that *is* real is `VERIFY-maxsteps-concurrent` in
[`runs/verify-flagged-contradictions.jsonl`](../runs/verify-flagged-contradictions.jsonl):
`max_steps=3 at concurrency=4 but 8 model calls were made`. Adding `concurrent_nodes=[arms]`
to the reproduction reproduces it at every concurrency including 1:

| `max_steps` | concurrency | calls before | calls after |
|---|---|---|---|
| 1 | 1, 2, 4, 8 | 8 | 1 |
| 3 | 1, 2, 4, 8 | 8 | 3 |
| 5 | 1, 2, 4, 8 | 8 | 5 |

**So the defect is one batch, not one arm.** Every node in a `concurrent_nodes` group runs
without the allowance being consulted, whether or not the run overlaps them. The finding's
"branch arms ignore it completely, including at `concurrency=1`" is right about the symptom and
its reproduction understates what has to be declared to see it. Worth carrying into the A-1
entry so the next reader does not conclude the defect is gone.

### Where the reservation went, and why not at the arm

The ruling names two dispatch sites. I put the reservation at the model call instead, in
`_call_model` and `_call_retrieval_model`, and removed the now-duplicate one from `_fan_out`.

A branch arm is a node, not a call, and a per-arm reservation is wrong in both directions:

- An arm that makes no model call (a `Deterministic` node in the group) would hold a step it
  never spends. Under overlap that step refuses a sibling arm that would have fitted.
- An arm that makes several (an `AgentNode`, or an `LLMNode` with `over=`) would reserve one and
  spend many. Measured on the `over=` case: an arm holding one phantom step turns `max_steps=3`
  into 2 calls, because the fan-out's own reservation sees the arm's.

Reserving where the call is made says exactly what the four shipped statements say — "one call
is one step, the step is taken before the call, and a call does not start unless one remains" —
and it covers the paths the ruling names plus the chain, delegation, and a `ModelHandle` call
made inside a tool. The reservation is held until `run.charge(steps=1, ...)` lands, because
releasing it before the charge leaves a window in which two threads both see the last step free.

`run.one_step` already takes `RunContext._lock`, which is the lock the ruling asks for.

### What this does not change

The `AgentNode` loop checks `_budget_tripped(effective, steps=node_calls, ...)` before each
call, where `effective` is `run.remaining_budget().narrowed_by(node.budget)` snapshotted at node
entry. Sequentially that trips at the same point the reservation would, so an agent node whose
own budget runs out still terminates gracefully with `termination="max_steps"` rather than
raising. The reservation fires ahead of it only where the run's spend moved underneath the node,
which is the overlap case, and there `BudgetExceeded` propagating is what the ruling accepted.

### Verified live

vLLM `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit`, eight real arms:

```
max_steps=1 concurrency=1: model_calls=1  outcome=stopped_early stopped_early=max_steps
max_steps=3 concurrency=1: model_calls=3  outcome=stopped_early stopped_early=max_steps
max_steps=3 concurrency=4: model_calls=3  outcome=stopped_early stopped_early=max_steps
max_steps=5 concurrency=4: model_calls=5  outcome=stopped_early stopped_early=max_steps
max_steps=8 concurrency=4: model_calls=8  outcome=stopped_early stopped_early=max_steps
```

Gemini `gemini-3.1-flash-lite`, six real arms at concurrency 2: 1, 2 and 3 calls under
`max_steps` 1, 2 and 3.

A real `SentenceTransformerEmbeddings` index searched four times from one `Deterministic` node:
1, 2 and 4 embedding calls under `max_steps` 1, 2 and 4, where before the fix the same node made
8 calls and the run reported `completed`.

The vLLM figures above were first taken before the machine crashed. The lead restarted the
server afterwards, and the same script re-run against it reproduces them exactly, so they are
post-change rather than pre-crash.

---

## 2. The resume claim is discarded before the validation that can refuse

Findings [L-5](../findings/lead-verified.md#L84), [H-2](../findings/area-hb-suspension-envelope.md#L95),
[H-4](../findings/area-hb-suspension-envelope.md#L190).

Two separate causes, both fixed:

- `pipeline.py` evaluated `codec.decode(state.inputs, ...)` and `self._answers_for(...)` as
  arguments to `_drive`, after `discard_claim(root)`. They are now evaluated inside the `try`
  that calls `release_claim`, and bound to locals.
- `claim_state` renames before it parses, so a version refusal left the file as
  `suspension.claimed.json` and the run stopped being listed. It now releases the claim before
  re-raising anything `from_json` or `json.loads` throws.

**The claim is still discarded before `_drive` runs**, so a resumed run that fails partway is
not resumable — the same position a fresh run that fails is in. Moving the discard past `_drive`
would leave the claim held whenever `_drive` raises anything other than a suspension, which the
finding's own fix direction warns against.

Measured after: `answer=` against two stops, a typo in `answers=`, and a `format_version` this
version does not read all leave `suspension.json` in place, `Pipeline.suspensions()` listing the
run, and the corrected call succeeding.

---

## 3. `resume(answer=...)` now reaches a `Deterministic` node

Findings [J-1](../findings/area-j-docs-implementability.md#L45),
[H-3](../findings/area-hb-suspension-envelope.md#L146),
[area-c 3](../findings/area-c-tools.md#L104).

`_fixed_point_caller` became `_FixedPointCaller`, a callable object, because the delivery needs
state the closure had nowhere to keep. It numbers the calls the node function makes. When a call
suspends it writes that number, the tool name, the `asked_at` timestamp, the asked record id and
the tool occurrence onto `Suspend.node_state`. On the way back the node runs again from the
beginning and the call at the same number is handed the answer instead of being made.

`_attempt` now includes `Deterministic` in the kinds handed `resume_state` and `answer`.

**Two refusals were added rather than letting the answer be dropped silently.** A resumed
function is not guaranteed to take the same path:

- Call *n* going to a different tool than the one recorded is refused, naming both.
- The function returning without having reached call *n* is refused, naming the node and how
  many calls it did make.

Both point at `AgentNode` as the kind that is resumed from its conversation rather than by
running again.

The answering record is emitted through `_delivered_answer`, extracted from `AgentNode._deliver`
so both kinds file the answer under the cassette key the call would have had and write a
consultation record naming the pending one. Verified: the trajectory holds `pending` then
`answered` with `answers` pointing at the first, which is what
`trajectory-format.md` §4.3's counting rule reads.

Live on Gemini: a `Deterministic` node holding `consult`, exactly the configuration
`docs/tools.md` §4.6.1 shows, stops, is resumed with `answer="Slim"`, and the following
`LLMNode` writes its sentence from that answer.

### H-1 came with it, and had to

[H-1](../findings/area-hb-suspension-envelope.md#L27) is a blocker that was not on my list. It
had to be fixed here, because the delivery fix above turns its failure mode from bad to worse.

Before: a `Deterministic` node inside a pipeline used as a node re-suspended forever, which is
visible. After the delivery fix on its own, that node was handed `answer=None`, recorded the
consultation `declined`, and the run **completed on a null answer**: `closed on None`. That is
the shape H-1 already described for an `AgentNode`, and my change extended it to a second kind
rather than leaving it where it was.

Both halves the finding names are now closed, and the fix is smaller than the finding expected:

- `_attempt` dispatched a `Pipeline` node without passing anything a resume carries.
  `Pipeline.execute` takes `answers=` and `_attempt` passes it.
- The key did not match, because the outer walk popped `answers[node_id]` under the container's
  id while `_answers_for` had keyed by the leaf. A container did not stop — one of its nodes
  did — so what is keyed by node now travels down whole rather than being looked up under the
  container. The inner walk copies before popping, so nothing is consumed at the wrong level.

`answer=` still means one delegated subtask's answer, which is the `_delegate` path.
`stop.stops` is untouched, so **[H-6](../findings/area-hb-suspension-envelope.md#L351) is still
open**: the id on a nested stop is the bare leaf, and everything else in the run uses
`research.ask_inner`. Two nested pipelines each holding a node called `ask_inner` still produce
two indistinguishable stops. Fixing that changes a shipped surface and no ruling covers it.

Measured after, both kinds: `closed on slim`, and the consultation records read `pending` then
`answered` with `response: slim`.

---

## 4. Every stop is recorded in the manifest

Finding [H-5](../findings/area-hb-suspension-envelope.md#L228). `_drive` called
`manifest.note_suspension` once with `exc.node_id`; it now iterates `exc.stops`.

`note_resumption` closed the last open entry and now closes every open entry, because a resume
continues all the nodes the run stopped in, not one of them.

Two arms stopping together now produce two entries, each with its own `waiting_for`, and both
gain `resumed_at` on the resume.

**For the lead:** `docs/run-envelope.md` §2.1 line 91 describes `suspensions` as "one entry per
time the run stopped and was continued". It is now one entry per *node* that stopped. That file
is not mine.

---

## 5. `pipeline.md:297`

Ruling [D2](../RULINGS.md#L27) keeps the behaviour and corrects the sentence. It now says the
fingerprint is a digest of shape, that a container's edges move it and its `tools=`,
`fetch_policy=` and budget do not, and points at `run-envelope.md` §2.1, which was already
right.

---

## 6. A `Join` in the node list

`Join` is exported, takes `node_id=`, and constructed without complaint until the walk died on
`AttributeError: 'Join' object has no attribute 'node_kind'`. `Pipeline.__init__` now refuses it
by name, saying what a `Join` is and showing the three-node shape that declares a join with
edges. Anything else in the list with no `node_kind` is refused too, naming its type.

---

## 7. `to_mermaid()` and a declared stop

Findings [A-2](../findings/area-a-pipeline-graph.md#L113),
[H-7](../findings/area-hb-suspension-envelope.md#L372). **Decision: draw it.**

Two shipped statements claim the drawing shows it — `pipeline.md` §1.7 by implication and the
§1.8 code comment "a stop planned in advance, and drawn by `to_mermaid()`" — and the diagram is
read to check the shape against what was meant. Where a run stops to ask someone is part of that
shape. Correcting the prose instead would have removed the only place the stop is visible
without reading the node list.

A node declaring `suspend_before` renders `review(["review<br/><i>llm</i><br/><i>stops
before</i>"])`. `Graph.to_mermaid`'s docstring and `pipeline.md` §1.7 both name it.

---

## 8. An embedding parented to the node rather than to the search

Finding [D-3](../findings/area-de-retrieval-memory.md#L180). The `Deterministic` path built its
handles from the node's `parent_id` before any tool call record existed. The handles are now
built inside the `make_handles` callback `_run_tool` already passes the tool call's `record_id`
to, which is what the `AgentNode` path does.

Before: three `model_call` records and two `tool_call` records all hanging off the
`node_execution`. After: each embedding hangs off the search that made it.

**For Stream C or the lead:** `docs/memory.md` §2.1 recommends this pattern and §2.4 states the
parenting. Both are now true and need no change. `docs/retrieval.md` §6 line 234 likewise.

---

## 9. `held_back_ms`, the two lines Stream D could not write

Stream D fixed this at the source and left two gaps in `nodes.py`, which is mine. Both are
closed, and both were measured wrong before and right after.

**A call that exhausted its retries.** `_emit_failed_call_record` built the record and never
read the figure off the exception, so the wait was recorded as `0` and added nothing to
`totals.held_back_ms`. It now calls `held_back_ms_of(exc)` once, puts it on the record and
observes it.

Measured behind a local server answering 429 to everything, through the real `VLLMClient` at
`Retry(max_attempts=4, initial_backoff_s=1.0)`:

```
outcome            : error
totals.held_back_ms: 7000        (was 0)
 record: model_call | held_back_ms: 7000 | error: CallerFacingError
```

**The figure is 7000, not the 3000 Stream D's log reports at 7.1 and in its results table.**
Backoff doubles, so four attempts wait 1 + 2 + 4 seconds, which is what
[`Retry`](../../../../src/simple_agents/adapters/_http.py#L83) documents. One record, one
observation, no double counting. Worth reconciling with whatever their harness measured.

**An embedding or rerank call.** The retrieval path put `held_back_ms` on the record and never
observed it, so a completed run under-reported its wait. The value is bound once and used for
both. Measured with two searches waiting 1.5s each: records `[1500, 1500]`, total `3000`, where
the total read `0` before.

Two tests added to `tests/test_pacing.py`, which is Stream D's file and finished. They are
run-level, so they belong there rather than in `test_manifest_totals.py`, which exercises
`Manifest` directly and would not reach either path.

**`docs/run-envelope.md` §2.1 is now wrong** and is Stream D's to revise: it states that a
failed call contributes nothing, that the wall-clock comparison therefore reads a run that
finished, and that a run a rate limit ended carries its wait on the exception with
`held_back_ms: 0` on the record. All three are false as of this change.

## Tests

New: `tests/test_exact_steps.py` (19) and `tests/test_resume_recovery.py` (10). Added to
`tests/test_graph.py`: the declared stop in the drawing, and the two node-list refusals. Added
to `tests/test_pacing.py`: the two `held_back_ms` paths at 9.

**No existing test had to change.** The ruling expected some, on the grounds that a branching
pipeline under a tight `max_steps` now stops partway through its arms. Nothing in the suite
asserted that arms complete under a limit they exceed: `test_concurrency.py` runs its arms under
`UNBOUNDED`, and `test_loop_and_budgets.py::TestStepsBindEveryNodeKind` already asserted the
exact behaviour for a chain. The accepted cost is real, and it lands on projects rather than on
the suite.

## Cross-stream

Failures present with my source files reverted, so not mine:

- `tests/test_suspension_integration.py`, 3 failed and 6 errored. `tests/cassettes/suspend.jsonl`
  and `suspend-vllm.jsonl` no longer match: `tool_name (recorded 'document_search', now
  'consult')` at call 1 of node `outfit`, which is a tool version moving under the L-1
  `Annotated` fix in `tools.py`. Confirmed by stashing `nodes.py`, `pipeline.py`, `graph.py` and
  `suspension.py` and seeing the identical failure. **Both cassettes need re-recording by
  whoever lands L-1.**
- Earlier in the pass, and since fixed by their streams: `test_semantic_search.py` (18),
  `test_builtin_tools.py` (11), `test_url_cache.py` (2), `test_adapters.py`,
  `test_context_builder.py`.

Final state of the suite, after the cassettes were re-recorded and every stream landed:
**2050 passed, 2 skipped, 0 failed.** `scripts/prose_check.py` is clean across the whole
repository.

`scripts/check_citations.py` reports 174 problems, against 97 with every `src/` change stashed.
The rest are anchors into files all five streams moved. `--fix` rewrites `dev-docs/plan.md`
and the checkpoint inventory, which needs Thilina's sign-off and would be undone by the streams
still moving code. **One run of `--fix` after everything lands is the right point.**

## Crash

The machine hardware-crashed at 16:16 and rebooted at 16:37. Everything on disk survived. The
only loss was an in-flight write to `docs/pipeline.md` §1.8, salvaged from the editor's temp
file and reapplied.
