# Item 8d — build log

**Kept while building, not reconstructed at the end.** On the precedent of
`item8c-build-log.md`. The end-of-item report and the shipped-document rewrites are reads of
this file.

The design of record is `archive/plan-history.md` item 8d as rewritten at the sitting. Nothing here
reopens it. §2 records where building it sharpened a decision, §3 where it turned out not to
hold, and §4 what the build found that is nobody's design.

**Status: built, and the shipped documents written.** 2026-08-04. Baseline 691 tests at
`6b1be38`; **767 tests** now. Trajectory `0.12`, manifest `0.6`, suspension `0.1`, results
unchanged at `0.2`. Cassettes recorded against live Mistral and live vLLM.

---

## 1. The sitting, and what it settled

Held 2026-08-04, before any code. The plan entry named four open questions; the sitting
answered six, because two more were open and unnamed.

| Question | Settled |
|---|---|
| What may cross a suspend point | A codec derived from the producing node's declared `output_schema`. `Deterministic` gains an optional `output_schema=`. Library types tagged. Anything else refused at the suspend point. |
| How an `AgentNode` is captured mid-loop | Full capture, to a versioned `suspension.json` in the run directory, through the same `Redaction` the trajectory uses. |
| How a resume verifies the graph | Two tiers. Structural differences never waivable; version differences waivable through `accept_changed=` and recorded. A `graph_fingerprint` compares in one string and a mismatch reports the diff. |
| What a `consultation` record says | Two records joined by a new `answers` field, and `resolution` gains `pending`. |
| **What a suspend point is** (unnamed in the plan entry) | Three triggers sharing one capture and one `resume()`: a raised `Suspend`, `suspend_before=` on a node, and `stop_when=` on `run()`. |
| **Waiting on a clock** (raised by Thilina at the sitting) | `resume_not_before` on `Suspend`. `resume()` refuses before it; `resume(wait=True)` blocks. The library owns no timer. |

### 1.1 The three triggers were costed wrong, and the correction is the sitting's main result

They were presented as three designs to choose between, with a recommendation to build one and
defer the others. That was wrong: **the expensive part is the state capture and all three share
it.** `suspend_before=` and `stop_when=` are the same check in the same place in `_walk`, so
each costs a handful of lines once the capture exists. Thilina rejected the framing and asked
for all three.

Two cases he named that the costing had missed, both real and neither reachable from a raised
`Suspend` alone:

- **An end user pausing a session and coming back next week.** Mechanically this is
  `stop_when=`, driven from the application. The costing had classified `stop_when=` as an
  infrastructure feature for parking work before a redeploy, which is one of its uses and not
  the one a builder meets first.
- **Waiting for a token quota to reset**, which is a suspension with a time on it rather than a
  question. It composes with what item 8 already built: `PacedClient` is a `ModelClient`
  wrapper, so a wrapper raising `Suspend` propagates like any other and needs no new concept.

### 1.2 What a fan-out does was found by asking where a `ModelClient` can raise

An `LLMNode` was assumed atomic with respect to suspension, on the ground that only an
`AgentNode` calls tools. A `Suspend` raised from a `ModelClient` wrapper defeats that: it lands
three items into a ten-item fan-out. The finished `ItemOutcome`s are captured and the resume
continues from the next index, which matters most in the case that suspended, where the quota
was the reason.

---

## 2. What building it changed about the design

### 2.1 A resumed node's inputs are derived, not stored

`_EdgeState.inputs_for` rebuilds what a node receives from its resolved in-edges, and the
frame already carries those. So the node's inputs are reconstructed rather than held twice,
and only the run's own `inputs`, which the entry node receives and no edge carries, are stored
at run level. The sitting had listed the node's inputs as part of the capture.

### 2.2 Whether a resumed node was already entered is derivable

The design had one notion of "the node the run stopped at". Building it needs two, because the
three triggers do not stop in the same place. A raised `Suspend` stops *inside* a node whose
budget was charged and whose loop entry was counted; `suspend_before=` and `stop_when=` stop
*before* one that has had neither.

No extra field was needed: `edges.done` already holds the nodes that have been entered, so
`in_progress and node_id in edges.done` tells the two apart. Getting this wrong in either
direction is silent — a double charge, or a bounded cycle losing an iteration to a suspension.

### 2.3 A suspending tool is sorted last in its turn, beside `finish`

Item 8c's rule was that every other tool runs before `finish`, so a finish check sees the reads
made in the turn it judges. The same sort now puts a tool that can suspend after the ordinary
ones and before `finish`, so a stop lands on a turn boundary wherever the model asked for other
work alongside the question. The remaining calls are still captured, because a project tool
that raises `Suspend` is not recognisable in advance the way a `ConsultTool` is.

### 2.4 A tool result has to be plain data to cross a suspend point, and the refusal names the tool

`ctx.tool_calls` carries what each tool returned, and a finish check reads it. A tool declares
no output schema, so the codec has nothing to rebuild an object from. The refusal fires at the
suspend point and names the tool rather than the node, because the tool is what has to change.

### 2.5 `Suspend` carries the node's capture, and `_Suspending` carries the frames

Two carriers rather than one, and the split is what the exception path already does. `Suspend`
travels from the raise site out through the node, and the node fills in its own loop state on
the way past. `_Suspending` is raised by the pipeline once the node has been left, and each
enclosing walk inserts its frame in front. `run` sees a complete stack, outermost first.

### 2.6 `Suspend` had to be added to `_run_tool`'s pass-through list

`_run_tool` treats an undeclared exception as caller-facing, so the first suspending tool
produced *"Tool 'consult' raised Suspend ... raise ModelFacingError from within the tool"*. It
now passes through beside `CallerFacingError`, and writes no `tool_call` record: the tool did
not fail, and the call is recorded when its answer arrives.

---

## 3. What in the settled design turned out to be wrong

### 3.1 An `LLMNode` is not atomic with respect to a stop

The sitting's first framing had only an `AgentNode` able to stop mid-node, on the ground that
only an `AgentNode` calls tools. A `Suspend` raised from a `ModelClient` defeats it, and a
`ModelClient` wrapper is exactly how a quota wait is expressed. Corrected at the sitting before
any code, and recorded here because the reasoning that produced it was wrong rather than
incomplete: "which node kinds call tools" is not the same question as "where can a stop land".

### 3.2 Nothing else

The rest of the design held as written. Where building it added something the sitting had not
named, it is in §2 rather than here.

---

## 4. Findings

### 4.1 A settled rule was invoked instead of argued, twice, and both times it was wrong

`simple-agents.md` §9 do-not-change #12, "no scheduler", was cited against building a timer for
`resume_not_before`. Thilina pushed back and was right: #12's own amendment defines what it
means by scheduler, which is the shape of the walk, and a sleep before continuing is not
concurrent, not queued and does not change the topological order. The rule was being used as a
substitute for an argument, which is what `CLAUDE.md` forbids.

The same mistake was then made one paragraph after conceding it, citing `plan.md` §2.2's
conclusion — "that is Temporal, and it is a different product" — as the reason a supervisor
stays out. The argument that stands on its own is that **a supervisor cannot reconstruct the
caller's `Pipeline`, hold their envelope or hold their model client**, so it has to be handed a
factory for the caller's program, at which point it is a loop the caller writes in five lines
and the library carries the operations for it.

**What ships as a result of the concession:** `resume(wait=True)` blocks until
`resume_not_before` rather than the library refusing and making the builder write the sleep.

### 4.2 §9 #12 had outlived two of its three clauses, and the first repair was already false

The first proposed amendment said the rule forbids "an engine that decides which node runs
when". Thilina asked whether that is not exactly what 8c built. It is: `_walk` picks the next
ready node, resolves edges and reopens cycles. **The wording would have been false on the day it
was written**, and it was one approval away from entering the do-not-change list.

Working out what #12 still forbids after 8c, rather than patching the phrasing, found that the
three clauses do not fare the same against §9's own test, which is whether changing it means the
project is no longer the thing that was designed:

- **No DSL.** Holds. A YAML-configured pipeline is a different product for a different audience.
- **Nothing concurrent.** Does not hold, and is now false as a forward statement. `plan.md`
  §2.2 commits to concurrency in principle while §9 forbids it, so **the two documents
  contradict each other today** and §9 is the out-of-date one. Scope belongs in `plan.md` §3.
- **The library owns no execution outside a call the caller made.** Holds, and was never in #12;
  it was derived at this sitting. Its home is §2.1, whose decision already reads "every component
  runs inside a run envelope that records by construction" and whose corollary is that nothing
  runs outside one.

Thilina's call: split it. Recorded in §5 below as a doc consequence owed.

### 4.3 A replayed suspension would have been unreplayable, found by tracing the cassette path

`builtins/consult.py`'s module docstring promises that a consultation "is served from the
cassette like any other tool, so an evaluation replays the recorded answer rather than asking a
person once per rollout". Tracing `RunContext.call_tool` confirms the replay half: a served
entry means `ask` is never invoked, so **a replay of a suspended run never suspends** and an
evaluation over a consulting agent stays possible.

The recording half does not hold without work. On the run that suspended, the tool *raised*
rather than returned, so nothing was stored under that key and the promise would be false for
exactly the runs 8d creates. **The resume writes the delivered answer into the cassette under
the pending call's key**, which is why the suspension captures the call's tool name, version,
arguments and occurrence rather than only the question text.

### 4.4 Pydantic serializes a model of the wrong class to `{}` and does not warn

The codec's first version guarded the encode with `TypeAdapter(schema).dump_python(value,
mode="json", warnings="error")`, on the reading that `warnings="error"` turns a type mismatch
into an exception. It does not, for the case that matters:

```
TypeAdapter(Notes).dump_python(Other(n=1), mode="json", warnings="error")
# {}
```

Two models with no field in common produce an empty object and no warning. `warnings="error"`
does fire for a container mismatch (`list[Notes]` against a bare `Other`), which is what made
the guard look as though it worked. Where `Notes` has a required field the decode then fails,
which is loud but blames the wrong thing; where every field has a default, `Other(n=1)` written
by the live run comes back as `Notes()` in the resumed one. **That is the silent type change the
codec exists to prevent, arriving through the codec.**

What ships is a strict validation before the dump, `validate_python(value, strict=True)`, which
refuses a model of another class, refuses a string where a `Maybe[int]` is declared, and accepts
an `Unknown` where the schema admits one. `warnings="error"` stays on the dump as a second
guard rather than the only one.

**Found by writing the refusal's test and watching it not raise.** Nothing else in the suite
would have caught it, and reading the code would not have: the call looks like it is checked.

### 4.5 A suspension cannot be replayed, and that is the property working

The integration test was first written to replay the recorded stop: run, expect `RunSuspended`,
resume. It does not stop. Under replay the consultation is served from the cassette, so the
channel is never reached and nothing raises.

**That is the promise `docs/tools.md` makes, observed.** It also means the live suspend path has
no replayed test of its own, and what the replay proves instead is better: the recording's third
request is the one the *resumed* process sent, and its message list was assembled from
`suspension.json` rather than held in memory. A cassette key covers the whole request, so the
replay serving that entry says the round trip through the file produced the same conversation
the live run held. `tests/test_suspension_integration.py` says so at the top, because a reader
would otherwise expect the file to test a stop.

### 4.6 What the live Mistral recording showed

`scripts/record_backend_cassettes.py suspend` ran against `mistral-small-2603`. Three model
calls and two tool calls: a search, a `consult` that stopped the run, and one call made by the
second process. **The backend accepted the rebuilt conversation**, which is the specific thing a
fake client cannot show, and the one the context sitting's `400 invalid_request_message_order`
made worth checking.

The model offered four options with its question (`regular`, `slim`, `relaxed`, `straight`)
without being asked to, which is `consult`'s `options` parameter being used as intended by a
model that was only told the tool existed.

**The vLLM recording needed two flags the first attempt did not have.** `vllm serve` without
`--enable-auto-tool-choice --tool-call-parser hermes` refuses any request carrying tools with a
400 naming both, so the recording never reached a consultation. `docs/model-clients.md` §4
already says this; the server had been started from memory rather than from the document.

With them, Qwen3-1.7B produced the same three-call shape as Mistral and **answered
`returns_policy` as `unknown` rather than guessing**, which the hosted model did not do on the
same corpus. `tests/test_suspension_integration.py` asserts what each backend did rather than
what the other one did.

### 4.7 The conformance check covers three record types, not four

`tests/test_trajectory_conformance.py` transcribes each record type's fields from the document
and compares them with what the writer produced. Item 8c made the `node_execution` comparison a
symmetric difference, which is what caught `resumed_from` here.

There was no `consultation` check at all, and the `model_call` and `tool_call` ones were
one-directional. So `answers` could have been added to the writer with the document naming
nothing, and nothing would have failed.

**All four types are now symmetric**, with a `consultation` fixture that suspends and resumes,
since the pair is the only place such a record is written with every field filled. Each was
broken once in each direction, eight cases, and all eight failed.

**Making `model_call` symmetric found four fields immediately.** `context`,
`recorded_duration_ms`, `rate_limit` and `provider` are all named in
`docs/trajectory-format.md` §4.1 and none of them was in the test's transcription. The
transcription had drifted four fields behind the document, across items 5 to 8c, and the
one-directional check could not say so by construction. Nothing was wrong with the writer or
the document; the thing meant to hold them together had quietly stopped covering half its job.

The file's own docstring also still said it tested format `0.4`.

### 4.8 A fan-out is not atomic, and the second capture is smaller than the first

The sitting decided a fan-out keeps its finished items. Building it showed the capture is
almost nothing: `_fan_out` already collects `ItemOutcome`s in a list, so the state is that list
plus the next index. Two things it does need:

- **The value is dumped against the node's own `output_schema`**, which `_fan_out` has in hand,
  rather than through `ValueCodec`. The codec resolves a schema from a node id and lives in
  `suspension.py`, which imports `nodes.py`; reaching back the other way would be a cycle. The
  rule applied is the same one.
- **The item has to be plain data**, because it came from the run's input and no schema
  describes it. The refusal names the node and what it was fanning out over.

`LLMNode.execute` gained the same `resume_state` argument `AgentNode.execute` has, and the
pipeline hands state to either kind. A `Deterministic` node holds nothing and runs again.

### 4.9 A shipped document says something untrue, and it is not this item's

`docs/model-clients.md` was edited during this session, outside this item: its opening line now
says "Five adapters ship" against two that do, with an HTML comment saying Gemini, Anthropic and
OpenAI are wanted. Left alone, since it is a review comment on a document whose sitting has not
happened. Recorded here so the doc pass does not adopt the claim.

---

## 5. Doc consequences

**All rows are done**, written after the build on the instruction item 8c followed. The table is
kept as the record of what moved and why. Every example added to `docs/pipeline.md` §1.8 and
`docs/tools.md` §4.1 was executed against the library before it was written down.

| Document | Section | What it says now | What it had to say |
|---|---|---|---|
| `dev-docs/simple-agents.md` | §9 #12 | ~~"No DSL and no scheduler in v0"~~ | **Done.** "No DSL", with what a DSL is and what forbidding it buys. The concurrency clause is gone, and the amendment records why. |
| `dev-docs/simple-agents.md` | §2.1 | ~~half the containment claim~~ | **Done.** The run-boundary property: no thread, no process, no timer the library owns. |
| `dev-docs/plan.md` | §3.2.1 | ~~three deferred entries, one arguing from a product name~~ | **Done.** A supervisor entry with what 8d must not foreclose, and the distributed-execution entry rewritten to give a reason. |
| `dev-docs/plan.md` | §3.1 item 8d | ~~four open questions~~ | **Done.** The settled design. |
| `docs/pipeline.md` | §1.1, §1.8, §5 | ~~no suspension anywhere~~ | **Done.** §1.8 is new: the three triggers, what a resumed node picks up, what may cross, waiting on a clock, and resuming against the right pipeline. §1.1 gained the run-time checks, §5 the rule that suspended time is charged to nothing. |
| `docs/trajectory-format.md` | §3, §4.3 | ~~`0.11`; nine `termination` values; four `resolution` values~~ | **Done.** `0.12`, `resumed_from`, ten `termination` values, `answers`, five `resolution` values, and the two-record rule. |
| `docs/run-envelope.md` | §2 | ~~`0.5`~~ | **Done.** `0.6`, `outcome: suspended`, `graph_fingerprint`, `suspensions`, `resume_waivers`, and `schema` on a node entry. |
| `docs/tools.md` | §4.1 | ~~a channel that blocks~~ | **Done.** A channel that raises `Suspend`, the two records, and why the replay promise still holds. |
| `docs/evaluation.md` | §7.3 | ~~nothing on suspension~~ | **Done.** An evaluation replaying a recording never suspends, and one running live raises rather than scoring an absence. |
| `docs/model-clients.md` | §6 | ~~pacing only~~ | **Done.** A window measured in days is waited out rather than paced, with the wrapper that does it. |
| `docs/index.md`, `README.md` | the tables | ~~`pipeline.md`'s one-liner~~ | **Done.** One line each. |
| `CHANGELOG.md` | Unreleased | ~~`0.11` / `0.5` / `0.2`~~ | **Done.** What each break costs a project. |
| `dev-docs/design/trajectory-format-changelog.md` | — | ~~through `0.11`~~ | **Done.** `0.12`, and what it settled. |

**Not touched, and deliberately.** `docs/context.md` was checked and owes nothing: a resumed
`AgentNode` rebuilds its message list before the context builder sees it, so the four build
sites and what a call records are unchanged. `docs/failure-taxonomy.md` owes nothing either;
FT-25 is about an agent guessing rather than asking, and suspension does not change what that
check reads.

---

## 6. Existing tests that had to change

Kept apart from §2 and §3 so nothing is quietly folded into a design note. **An existing test
needing a change is a finding to report, not a test to edit.**

### 6.1 Four, all of them the format bumps landing where they should

None is a behaviour break, and nothing else in the suite needed touching.

| Test | What changed |
|---|---|
| `test_trajectory_conformance.py::test_format_version_is_declared_on_every_record` | `0.11` becomes `0.12`. |
| `test_trajectory_conformance.py::test_node_records_have_their_type_specific_fields` | `NODE_FIELDS` gains `resumed_from`. The check is a symmetric difference since item 8c, so it failed until `docs/trajectory-format.md` §3 named the field. |
| `test_run_envelope.py::test_it_names_the_trajectory_it_belongs_to` | `trajectory_format_version` is `0.12`. |
| `test_run_envelope.py::test_it_records_the_node_shape_and_the_unknown_waivers` | A manifest `nodes` entry gains `schema`. Manifest `0.6`. |
| `test_trajectory_conformance.py::test_model_call_has_its_type_specific_fields` | `MODEL_CALL_FIELDS` gains four fields the document already named, once the check became symmetric. See §4.7. |
| `test_trajectory_conformance.py::test_tool_call_records_have_their_fields` | Made symmetric. The field list was already correct. |

`test_packaging.py::test_the_manifest_document_lists_every_key_the_manifest_writes` also failed,
and needed no test change: it reads `docs/run-envelope.md`, so adding `graph_fingerprint`,
`suspensions` and `resume_waivers` to the manifest table fixed it. **That check is the one that
noticed the manifest had grown**, before the doc pass reached it.

### 6.2 The checkpoint: none

**The whole suite passed with the walk made re-enterable and its state serializable, before
anything could suspend.** 691 green, then 697 with the checkpoint's own six. Nothing existing
was touched. This is item 8c's checkpoint in its 8d form: there, the executor was replaced
before a graph feature was added; here, `_walk` was restructured to run from a `_Frame` it can
be handed rather than from locals it creates.

What the checkpoint moved:

- `_EdgeState.snapshot()` / `.restored()` and `_Frame.snapshot()` / `.restored()`. An edge is
  stored as an entry naming its source and target rather than a joined string key, because a
  node id may contain any character a delimiter could use.
- `RunContext.counters()` / `.restore_counters()`, covering `_sequence`, `_model_calls`,
  `_tool_calls`, `_tool_occurrences` and `_last_input`.
- `Spend.to_record()` / `.from_record()`, which did not exist. `Budget` had `to_record` and
  `Spend` did not, so the frame snapshot had nowhere to put the spend it opened with.
- `_walk(frame=)`, and `_Frame.in_progress` naming the node that was executing. A resumed node
  runs again without being charged or counted, so a suspension inside a bounded cycle does not
  consume a second iteration.

**The three re-entry tests were watched to fail**, with `resumed` forced to `False`: the walk
starts from the entry node and the run ends with `CallerFacingError: No path through this
pipeline reached 'b'`. Without that check they would have passed against a walk that ignored
the restored frame entirely.

### 6.3 A simplification the checkpoint found

**A resumed node's inputs do not need storing.** `_EdgeState.inputs_for` derives them from the
resolved in-edges, which the frame already carries, so the values are reconstructed rather than
held twice. Only the run's own `inputs`, which the entry node receives and no edge carries, are
stored at run level.
