# Areas H and B: suspension, and the run envelope

Run 2026-08-13 against commit `2f4db4c`. Suite `area-hb-suspension-envelope`, rows in
[`runs/area-hb-suspension-envelope.jsonl`](../runs/area-hb-suspension-envelope.jsonl).
Backends: vLLM `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit` on `localhost:8002` for every
suspension check and for the self-hosted cost and cassette work, and live Gemini
`gemini-3.1-flash-lite` on the paid key for the token-accounting and per-model-basis checks.
Spend on the paid key was $0.035. Scripts are in `scratchpad/qa/area_h_suspension.py`,
`area_b_envelope.py`, `repro_nested.py`, `repro_claim.py` and `repro_redact_replay.py`.

## Summary

102 checks: 90 pass, 11 fail, 1 skip. **Area H: 36 checks, 27 pass, 9 fail.** **Area B: 66
checks, 63 pass, 2 fail, 1 skip.** The run envelope is in good shape: the directory layout, the
manifest's 31 fields, `counts` over every record type including the zeros, `graph_fingerprint`,
`role`, seeds and their derivation, all four cassette modes, both miss messages, `runs()`,
`read_trajectory`, sampling and its interaction with the default recording, and live token
accounting against Gemini all hold. Suspension does not. The 0.4 format itself is sound and the
tree of frames is written correctly, but two paths through `Pipeline.resume` destroy or discard
what the run stopped holding: a stop inside a pipeline used as a node loses the answer silently,
and every refusal raised after the claim deletes the suspension file. Both are new surface: the
existing unit tests cover the nested case with `suspend_before` only, which needs no answer, and
cover no refusal after the claim.

---

## H-1. A resume into a pipeline used as a node discards the answer. Blocker.

**What is claimed.**
[pipeline.md §1.8, line 359](../../../../docs/pipeline.md#L359): "`answer` is what the call that
suspended returns."
[pipeline.md §1.8, line 363](../../../../docs/pipeline.md#L363): "**What a resumed node picks up.**
An `AgentNode` continues its loop with the conversation, the tool calls it had made and its own
spend intact."
[pipeline.md §1.6, line 284](../../../../docs/pipeline.md#L284) and the composition
section make a pipeline used as a node the declared way to nest work.

**What actually happens.** The answer never reaches the node. The consultation is recorded as
`declined` with a `null` response, and the agent is handed a refusal it was never given. The run
then either completes on that (a wrong answer, silently) or asks again and re-suspends forever.

**Minimal reproduction** (`scratchpad/qa/repro_nested.py`):

```python
inner = Pipeline([prep, AgentNode(..., tools=[consult(ask)], node_id="ask_inner")],
                 budget=B, node_id="research")
outer = Pipeline([open_node, inner, close_node], budget=B)

try:
    outer.run({}, envelope=env, model=client, run_id="n1", seed=41)
except RunSuspended as stop:
    stop.stops            # [{'node_id': 'ask_inner', 'waiting_for': 'Which fit ...'}]

outer.resume("n1", envelope=env, model=client, answer="slim").output   # 'closed'
```

The trajectory of that resumed run:

```
NODE research.ask_inner suspended
{"prompt": "Which fit do you recommend?", "response": null, "resolution": "pending",
 "answers": null}
{"prompt": "Which fit do you recommend?", "response": null, "resolution": "declined",
 "answers": "rec_992c53691cdf"}
NODE research.ask_inner finish {"text": "unknown"}
NODE close "closed"
```

`answer="slim"` is nowhere. On the vLLM run recorded in the suite the model asked a second time
instead, and the resume raised `RunSuspended` again, so the run cannot be finished either way.

**Where it goes wrong.** Two places, and both have to move.

1. [core.py:1690](../../../../src/simple_agents/pipeline/core.py#L1690), `_attempt`, dispatches a
   `Pipeline` node as `node.execute(inputs, run, model, execution, on_progress, frames=frames,
   stop_when=stop_when, parent_id=parent_id)`. `answer=` is not passed, so
   [`Pipeline.execute`](../../../../src/simple_agents/pipeline/core.py#L1271) builds its `answers` from a
   parameter that is always `None` and hands the inner walk nothing.
2. Even with that fixed, the key would not match. The outer walk pops
   `answers.pop(node_id)` at [core.py:1018](../../../../src/simple_agents/pipeline/core.py#L1018)
   with `node_id` being the container, `research`, while
   [`_answers_for`](../../../../src/simple_agents/pipeline/core.py#L786) built `{"ask_inner": "slim"}`
   from the stop.

`answers={"research.ask_inner": ...}` and `answers={"research": ...}` are both refused as nodes
that did not stop, and `answers={"ask_inner": ...}` is accepted and dropped. There is no spelling
that works.

**Why the unit tests do not catch it.** `TestSuspensionInsideANestedPipeline` in
`tests/test_suspension.py:427` nests a `Deterministic` node with `suspend_before=True`, which
takes no answer. No test resumes a nested pipeline with `answer=`.

---

## H-2. Every refusal raised after the claim destroys the suspension. Blocker.

**What is claimed.**
[pipeline.md §1.11, line 531](../../../../docs/pipeline.md#L531): "passing `answer=` to a run that
stopped in several is refused, because nothing says which node it is for." The refusal is
presented as a correction to make, and
[pipeline.md §1.8, line 424](../../../../docs/pipeline.md#L424) says a resume claims its suspension
"before running anything", which implies an unclaim when nothing ran.

**What actually happens.** The refusal fires, and the suspended run is gone. The state file is
unlinked, `Pipeline.suspensions()` no longer lists the run, and no later `resume` can reach it.

**Minimal reproduction** (`scratchpad/qa/repro_claim.py`):

```python
try:
    pipeline.run({}, envelope=env, model=client, run_id="c1", seed=41, concurrency=4)
except RunSuspended:
    pass
# ['cassette.jsonl', 'manifest.json', 'suspension.json', 'trajectory.jsonl', 'workspace']

try:
    pipeline.resume("c1", envelope=env, model=client, answer="slim")
except CallerFacingError as exc:
    ...  # "This run stopped in 'left', 'right' at once, and resume(answer=...) is one answer"
# ['cassette.jsonl', 'manifest.json', 'trajectory.jsonl', 'workspace']

Pipeline.suspensions(root)                                      # []
pipeline.resume("c1", ..., answers={"left": "slim", "right": "medium"})
# CallerFacingError: There is no suspended run in .../c1.
```

Three refusals reach this way, all of them ordinary user error:

| Refusal | Check |
|---|---|
| `answer=` against a stop in several nodes | H-03b |
| `answers=` naming a node that did not stop (a typo) | H-03d |
| A value tagged by a kind this version does not read | H-03e |

**Where it goes wrong.** [core.py:610](../../../../src/simple_agents/pipeline/core.py#L610) (`discard_claim`) calls
`discard_claim(root)`, which unlinks the file, and the two things that can still refuse are
evaluated afterwards, as arguments to `_drive`:
[`codec.decode(state.inputs, ...)`](../../../../src/simple_agents/pipeline/core.py#L1150) and
[`self._answers_for(state, answer, answers)`](../../../../src/simple_agents/pipeline/core.py#L1150). The
`try/except Exception: release_claim(root)` above them ends at line 592.

The messages are good; a caller who follows them finds the run has been deleted.

---

## H-3. A `Deterministic` node that suspends can never be resumed. Major.

**What is claimed.**
[pipeline.md §1.8, line 342](../../../../docs/pipeline.md#L342): "`Suspend` may be raised from a
tool, from a `Deterministic` function, from an `LLMNode` prompt function, or from a
`ModelClient`."
[Line 359](../../../../docs/pipeline.md#L359): "`answer` is what the call that suspended returns."
[Line 365](../../../../docs/pipeline.md#L365): "Every other node runs again from the beginning,
which is why a `Deterministic` node has nothing to lose."

**What actually happens.** The last sentence is true and is the problem. A `Deterministic` node
runs again from the beginning, calls the same tool again, and the tool raises `Suspend` again.
`answer=` is never delivered to it, so the only `Deterministic` suspension that can be continued
is one whose function stops itself from raising a second time by holding state outside the run.

**Minimal reproduction:**

```python
def quota(question, options):
    raise Suspend(waiting_for="monthly token quota", resume_not_before=when)

pipeline = Pipeline([Deterministic(lambda i, ctx: ctx.call_tool("consult", question="ready?"),
                                   node_id="gate", tools=[consult(quota)])], budget=B)

pipeline.run({}, envelope=env, model=client, run_id="r8", seed=41)   # RunSuspended
pipeline.resume("r8", envelope=env, model=client, answer="go", wait=True)
# RunSuspended: Run r8 suspended at node 'gate', waiting for: monthly token quota
```

**Where it goes wrong.**
[`node_resume`](../../../../src/simple_agents/pipeline/core.py#L1611) builds `resume_state` and
`answer` only `if node_state is not None and isinstance(node, (AgentNode, LLMNode))`.

`TestWaitingOnAClock` in `tests/test_suspension.py:1112` works around this with a `park` function
that raises once, and its docstring names the reason: "A node that raised every time would
suspend again on resume." That is the behaviour a builder meets. Either the docs should say a
`Deterministic` node that suspends is never handed the answer and has to make itself idempotent,
or the answer should reach it.

H-08e confirms the workaround path does resume, and that `wait=True` blocks for the declared
time before continuing.

---

## H-4. A version-mismatch refusal leaves the run unfindable. Major.

**What is claimed.**
[suspension.py:109](../../../../src/simple_agents/records/suspension.py#L109) `from_json`, the refusal itself: "Resume
it with the library version that wrote it, or start the run again."
[pipeline.md §1.8, line 401](../../../../docs/pipeline.md#L401): `for state in
Pipeline.suspensions("runs/")` is the documented worker loop.

**What actually happens.** The refusal is correct and names both versions. It also leaves the
state renamed to `suspension.claimed.json`, so the run is no longer suspended as far as anything
that looks reads it: `Pipeline.suspensions()` returns `[]` and a second `resume` reports "There
is no suspended run". Following the instruction requires knowing to rename the file back by hand.

**Minimal reproduction:**

```python
body = json.loads((root / "c3" / "suspension.json").read_text())
body["format_version"] = "0.3"
(root / "c3" / "suspension.json").write_text(json.dumps(body))

pipeline.resume("c3", envelope=env, model=client, answer="slim")   # CallerFacingError, correct
sorted(p.name for p in (root / "c3").iterdir())
# ['cassette.jsonl', 'manifest.json', 'suspension.claimed.json', 'trajectory.jsonl', 'workspace']
Pipeline.suspensions(root)                                          # []
```

**Where it goes wrong.**
[`claim_state`](../../../../src/simple_agents/records/suspension.py#L172) renames before it parses, and
[`pipeline.py` `Pipeline.resume`](../../../../src/simple_agents/pipeline/core.py#L659) calls it outside the `try` that
would `release_claim`.

**Related, and separate.** `Pipeline.suspensions()` raises on the first file it cannot read, so a
worker loop over a directory holding one stale file reaches none of the runs it could resume. The
refusal names the two format versions and **names neither the run id nor the path**, so the
operator cannot tell which of the runs under the directory is the bad one (H-06c).

---

## H-5. A run that stopped in several nodes records one of them in the manifest. Major.

**What is claimed.**
[run-envelope.md §2.1, line 91](../../../../docs/run-envelope.md#L91): "`suspensions` | array | One
entry per time the run stopped and was continued: `suspended_at`, `node_id`, `waiting_for`, and
`resumed_at`."

**What actually happens.** A run that stopped in `left` and `right` at once records:

```json
"suspensions": [
  {"suspended_at": "2026-08-13T03:25:06.088Z", "node_id": "left",
   "waiting_for": "Which fit would you like?", "resumed_at": null}
]
```

The second node and its question are in `suspension.json` and in the `RunSuspended` that was
raised, and nowhere in the manifest. The manifest is the durable record of what a run was waiting
on, and half of it is missing. `resumed_at` closes the one entry, so the interval no budget was
charged for is attributed to one arm.

**Where it goes wrong.**
[core.py:1205](../../../../src/simple_agents/pipeline/core.py#L1205) calls `note_suspension`
once with `exc.node_id` and `exc.suspend.waiting_for`, the first stop only, where
`suspended.stops` holds them all.

`RunSuspended.stops`, `SuspensionState.stops`, the state file and `resume(answers=)` all handle
several stops correctly (H-02, H-02b, H-03, H-03c pass). This is the one surface that did not
move to the plural.

---

## B-1. A redacted tool result stops a run replaying its own cassette. Major.

**What is claimed.**
[run-envelope.md §6, line 544](../../../../docs/run-envelope.md#L544): "**A cassette key is computed
before redaction and the stored entry after it.** A redacted recording still replays, and the
file carries no secret."
[Line 507](../../../../docs/run-envelope.md#L507) gives the motivating case: "a tool call carrying
an auth header writes that header to disk". The same section calls the cassette out by name: "The
same rules apply to the cassette, which a project keeps so its evaluation can run offline
(FT-21)."

**What actually happens.** The second half holds and the first does not. The entry is stored
redacted, so a replay serves the redacted value back into the conversation where the live run had
the real one. Every model call after that tool call is keyed on different messages and misses.

**Minimal reproduction** (`scratchpad/qa/repro_redact_replay.py`):

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY)
def echo_header(term: str) -> dict:
    """Look a term up against the supplier API. Returns what came back."""
    return {"authorization": "Bearer sk_live_...", "plain": f"the term was {term}"}

rules = Redaction(secret_env=["QA_FAKE_SECRET"])
pipeline.run("x", envelope=RunEnvelope(cassette=Cassette.record(path), redaction=rules), ...)
pipeline.run("x", envelope=RunEnvelope(cassette=Cassette.replay(path), redaction=rules), ...)
```

```
CassetteMiss: No recorded response for call 1 of node 'hunt' in .../echo_header.jsonl.

The nearest recorded request for this node differs in:
  messages[2].content (recorded 119 chars, now 120 chars)
```

The stored entry:

```json
"response": {"ok": true, "value": {
  "authorization": "[redacted:sensitive_key]",
  "env_value": "[redacted:env:QA_FAKE_SECRET]",
  "plain": "the term was tee"}}
```

The same agent shape with a tool whose result carries nothing to redact replays clean, 3 hits and
0 misses (B-07g), so it is the substitution and not the shape. A single-turn `LLMNode` also
replays clean, because there is no call after the redacted one.

**Scope.** Any project whose tool returns a credential, a declared secret value or anything
matching a built-in pattern, and whose agent takes another turn after that tool call. Redaction
is on by default, so the project does not have to have asked for it.

---

## B-2. `charged_cost` adds device-seconds to money. Major.

**What is claimed.**
[run-envelope.md §4.1, line 409](../../../../docs/run-envelope.md#L409): device-seconds are "a unit
rather than a currency, so nothing adds it to a figure in money and it fixes no currency for the
run."
[Line 461](../../../../docs/run-envelope.md#L461): "`charged_cost` is the two together, which is
what `max_cost` bounds."
[Line 465](../../../../docs/run-envelope.md#L465): "a tool whose `DeclaredCost` names a currency
other than the cost basis' is refused before the run starts."

**What actually happens.** A run under a `DeviceBasis` with a tool declaring `per_call` in USD is
not refused, and the two figures are added:

```json
"cost":         {"value": 0.387, "currency": "device_seconds", "basis": "device"},
"tool_spend":   {"amount": 0.01, "currency": "USD", "calls": 1, "source": "declared"},
"charged_cost": 0.397
```

0.387 device-seconds plus $0.01 is 0.397 of nothing. `max_cost` cannot be set against a device
basis (B-06c passes, and the refusal names `max_wall_clock_ms` as documented), so nothing is
enforced against this number, but it is what the manifest reports the run cost.

**Where it goes wrong.** [`Cost.plus`](../../../../src/simple_agents/cost.py#L187) takes
`currency=self.currency or other.currency` and adds the values with no currency check, and the
currency-agreement refusal at run start compares against a basis whose `currency` is the unit
name `device_seconds` rather than treating a device basis as having none.

**Related observation, not a failure.** The doc says a device basis "fixes no currency for the
run", and the manifest reports `"currency": "device_seconds"`.
[`cost.py:652`](../../../../src/simple_agents/cost.py#L652) states that intent plainly: "`currency` is
`device_seconds`, which names the unit rather than a currency". The code and its docstring agree;
`run-envelope.md` L409 reads as though the field would be absent. Worth one sentence in the doc.

---

## H-6. The stop names a node id nothing else uses. Minor.

**What is claimed.**
[pipeline.md §1.11, line 519](../../../../docs/pipeline.md#L519): "**A run that stopped in more than
one node at once is continued with `answers`**, keyed by the node each answer belongs to", with
the example `{each["node_id"]: ask_someone(...) for each in stop.stops}`.

**What actually happens.** For a stop inside a nested pipeline, `stops[0]["node_id"]` is the bare
leaf id, `ask_inner`. The trajectory, the manifest's `nodes`, `containers`, per-node metrics and
`accept_changed` all use `research.ask_inner`. So the key a caller reads off `stop.stops` joins to
nothing else in the run, and two nested pipelines each holding a node called `ask_inner` would
produce two indistinguishable stops.

**Where it goes wrong.**
[pipeline.py `_up_to_a_declared_stop`](../../../../src/simple_agents/pipeline/core.py#L1594), at
the `raise` inside it, used the unprefixed id, and `_collect_stop` carries it up unchanged.

This is the same code path as H-1 and would be fixed alongside it.

---

## H-7. `to_mermaid()` does not draw a declared stop. Cosmetic.

**What is claimed.** [pipeline.md §1.8, line 335](../../../../docs/pipeline.md#L335), in the code
block listing the three ways a run stops:

```python
# 2  a stop planned in advance, and drawn by to_mermaid()
LLMNode(review, output_schema=Verdict, suspend_before=True)
```

**What actually happens.** Nothing in the output marks it:

```
flowchart TD
    load["load<br/><i>deterministic</i>"]
    review(["review<br/><i>llm</i>"])
    load --> review
```

[`Graph.to_mermaid`](../../../../src/simple_agents/graph.py#L368) reads `node_kind`, `successors`,
`loop_at` and `on_error`, and never `suspend_before`. Its own docstring lists what it draws and
does not claim this one, so the fix is either two lines in `to_mermaid` or dropping four words
from the comment.

---

## B-3. Two error messages read poorly. Cosmetic.

**A null cost interpolates the whole unknown object into its reason** (B-10d, live Gemini under a
basis declaring no cache-write rate):

```
the call wrote {'type': 'unknown', 'reason': 'the backend reports no cache-write count. It
bills cache storage per token per hour rather than per token written, and a response says
nothing about what a request cached'} tokens to cache at TTL None, and the price basis
declares no cache-write rate for it
```

The behaviour is right and matches [run-envelope.md §4.2, line 442](../../../../docs/run-envelope.md#L442).
"an unknown number of tokens" would read as the sentence it is trying to be.

**The multi-seed replay refusal does not name the seeds** (B-04e). It says the file "holds calls
recorded by 2 runs at different seeds" and to "pass the seed of the run to replay", without
saying which seeds are on file or naming `Cassette.replay(path).recorded_seeds()`, which is what
reports them. [run-envelope.md line 328](../../../../docs/run-envelope.md#L328) does not promise the
list, so this is a suggestion rather than a failed claim.

---

## What held, in detail

**Area H, 27 passing.** The 0.4 file itself is right. A single stop writes `format_version 0.4`
with `stops`, `frames`, `inputs`, `spend` and `counters`, and `RunSuspended` carries `run_id`,
`node_id`, `waiting_for`, `options`, `resume_not_before` and `stops` (H-01). Two arms stopping at
once produce two entries in `stops`, in the exception and in the file, each with its own
`waiting_for` and `options`, and both arms keep their own held state (H-02). `answers=` keyed by
node continues both and both consultations resolve `answered` (H-02b). The refusals themselves
are correct and name the nodes: `answer=` against two stops names `answers=` and both node ids
(H-03), and an answer for a node that did not stop names it (H-03c). A single stop resumes with
`answer=`, keeps its run id, and writes the question and the answer as the two consultation
records §4.3 describes, the first `pending` and `blocking: false`, the second naming it in
`answers` (H-04, H-04b), and the suspension file is gone once the run finishes (H-04c). The tree
of frames is written correctly for a nested stop: the outer frame is in progress at `research`
and holds the inner frame under `below["research"]`, with its own prefix, `in_progress` and
`node_state` (H-05). A 0.3 file is refused naming both versions (H-06). `suspend_before=True`
stops before the node runs and resumes with no answer (H-07, H-07b), and it is refused on a
delegated pipeline at `Delegation()` construction with a message naming the fix (H-07d).
`resume_not_before` travels onto the stop and the file, a resume before it is refused naming the
time and `wait=True`, `state.ready` and `state.wait_seconds()` report the wait, and `wait=True`
blocks and continues (H-08, H-08b, H-08c, H-08e). The manifest of a suspended run records
`outcome: suspended` and an open entry (H-09). A changed shape is refused and says it cannot be
waived, including when `accept_changed` names it; a changed prompt is refused naming
`accept_changed`, and the waiver lands in `resume_waivers` with `resumed_at` filled in; a changed
model pin is refused; a claimed suspension refuses a second worker and points at
`Pipeline.suspensions` (H-10 through H-10f). A value with no schema behind it is refused at the
stop naming `output_schema=`, and a typed value crosses and comes back as its model (H-11, H-12).

**Area B, 63 passing.** Every run writes its own directory with the four documented entries and a
fixed-width sortable id (B-01, B-01b). The manifest carries all 31 documented fields and no
undocumented ones (B-02). `counts` reports every entry in `RECORD_TYPES` including the ones this
run wrote none of, and `records` agrees with both the per-type counts and the file's line count
(B-02b). A nested pipeline is expanded into `nodes` under prefixed ids and declared in
`containers` with all nine documented keys (B-02c). `models`, `prompts`, `schemas` (every
reference on a record resolves), `tools` and `totals` are as specified (B-02d through B-02h).
`graph_fingerprint` is stable across a reconstruction, unmoved by a prompt edit, and moved by an
added node (B-02i). `role` defaults to `agent`, `with_role` copies rather than mutates, an empty
role is refused, `runs(role=...)` reads one kind back, and a resume through an envelope declaring
another role keeps the role the manifest recorded (B-03 through B-03d). All four cassette modes
behave: record then replay reproduces the output with 0 misses, a second record into a non-empty
file is refused naming `update`, `update` serves what is on file and records what is not,
`off()` leaves no file, `into_run()` is the default, and a replay from a missing file is refused
before the run starts (B-04 through B-04l). Both miss messages are as documented, including the
seed miss naming the run seed to pass (B-04g, B-04h). The cassette carries its seed, a replay
with no `seed=` takes it from the file, a file at two seeds is refused, and naming one replays it
(B-04c through B-04f). A generated seed is recorded, a call's seed matches
`sha256(f"{run_seed}:{node_id}:{call_index}")[:4] & 0x7FFFFFFF` exactly, and a `Deterministic`
node records `seed: null` (B-05 through B-05d). Cost: a price basis prices a live call, a device
basis reports device-seconds, `max_cost` against it is refused naming `max_wall_clock_ms`, a
compute basis prices against reported concurrency, a per-model mapping records `by_model` with
`bases` and totals across two backends, an unmapped model prices `null` with a reason, `max_cost`
with no basis is refused, one `PriceBasis` over a hosted and a self-hosted model is refused, no
record stores a cost, and `total_cost` re-derives the manifest's figure and doubles when every
rate doubles (B-06 through B-06j). Redaction replaces declared env values, sensitive key names
and both built-in and declared patterns while leaving `secrets_path` alone; it reaches the
cassette; a `SecretStr` is replaced under `Redaction.none()`; an undeclared national id is kept,
as documented; the manifest holds names and never values; and unusable `secret_env` names are
listed with reasons (B-07 through B-07f). `runs()` lists newest first, reports `finished`,
`node_ids` and `outputs_of`, raises `LookupError` naming the nodes that did run, returns a
recorded absence as `Unknown`, and lists a directory whose manifest will not parse with
`unreadable` set (B-08 through B-08f). `Trajectory.sampled(0.0)` drops every payload and the
default recording while keeping `cassette.recorded`, leaves counts, tokens, seeds, finish reasons
and cost complete, returns the `not_recorded` object from `outputs_of`, decides the same way
twice for one run id, and keeps everything on a run that errored (B-09 through B-09f). Live
Gemini reports `input_uncached`, `input_cache_read` and `output` as separate counts and
`input_cache_write` as `{"type": "unknown", "reason": ...}` with a reason naming why the backend
reports none; a declared rate of `0.0` prices that call anyway, and a basis declaring no
cache-write rate prices it `null` with a reason (B-10 through B-10d).

---

## What I could not test, and why

- **Two workers racing for one suspension on the same filesystem.** H-10f claims the second
  worker by calling `claim_state` directly and then resuming, which proves the rename is what
  refuses. It does not prove the rename is atomic under a real race, and it says nothing about
  two workers on an NFS mount, which the docstring's "atomic on one filesystem" excludes anyway.
- **A suspension resumed by a different library version.** H-06 fakes the version by editing
  `format_version` in the file. A state file actually written by an older release would differ in
  its frame shape as well, and the refusal fires on the version field before anything reads the
  frames, so the fake exercises the same branch. What is untested is whether a genuine 0.3 file
  from before commit `2f4db4c` reaches that branch at all rather than a `KeyError` on `stops`,
  which `from_json` reads unconditionally.
- **`stop_when=` as a third way to stop.** The suspension paths I drove were `Suspend` and
  `suspend_before`. `stop_when` shares `_stop_before` with the latter, so the file format is the
  same, but a run stopped by the caller's own predicate was not run end to end.
- **Suspension inside a fan-out (`over=`) and inside a delegation.** Both are separate resume
  paths with their own state (`LLMNode` continuing at the item it stopped on, and an `AgentNode`
  handed `frames` for a delegate). `tests/test_suspension.py` covers both; I did not, and given
  H-1 the delegation path deserves the same live check, since it is the one place `_attempt` does
  pass `frames` to an `AgentNode`.
- **`cassette.diverged`.** Every recording I made came back with `diverged: 0`. Producing a
  non-zero count needs a backend that answers the same request differently across two recordings
  into one file, which is a property of the backend rather than something a test can force.
- **`memory` and `fetch_policy` in the manifest.** Both were present and `null`/empty on every
  run I made. Their populated shapes are areas of their own.
- **Sampling at a rate between 0 and 1 over enough runs to check the rate.** B-09d checks that the
  decision is a function of the run id and stable across readings, not that the fraction of runs
  kept approaches the rate.
- **Redaction's reach into a suspension file.** `write_state` passes the state through
  `envelope.redaction`, which I read but did not exercise with a secret in flight across a stop.

## What I might have missed

- **The interaction of H-1 and H-2.** A nested run that re-suspends writes a fresh state each
  time, so it is recoverable; a nested run that completes on the discarded answer is not, and
  nothing in the manifest says the answer was dropped. I did not look for a surface that would
  make the drop visible after the fact, and there may not be one.
- **Whether the redacted-replay break (B-1) also reaches an evaluation.** An evaluation replays
  from a cassette and refuses `update`, so a project whose tool results get redacted would see
  every rollout fail with `CassetteMiss` rather than a wrong number. I did not run an evaluation
  to confirm which of the two it is, and that distinction changes the severity.
- **Whether `Cost.plus` mixing units (B-2) reaches anywhere other than `charged_cost`.** Per-node
  cost, evaluation totals and `describe()` all go through the same type.
- **The manifest's `concurrency` field under a resume.** I checked `resume(concurrency=4)`
  continues both arms but did not check what the resumed manifest records for the axis, or what
  happens when a run suspends at `concurrency=4` and resumes at `concurrency=1`.
- **`held_back_ms` and `stream_waivers`.** Both were present and zero or empty; neither was
  driven to a non-trivial value.
- **Whether the second-worker refusal in H-2 and the destroyed state interact.** If one worker's
  refusal deletes the file while another is mid-claim, the second gets "no suspended run" for a
  run that was suspended a moment earlier, and the two failures are indistinguishable from the
  message.
