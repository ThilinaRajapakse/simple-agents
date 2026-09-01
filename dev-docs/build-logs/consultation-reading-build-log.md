# Build log — A judgement the scoring code did not compute, stage 2

`plan.md` §4 P3-12, the run-time stage. Started 2026-08-18. Written while building.

Stage 1 is [`recorded-judgement-build-log.md`](recorded-judgement-build-log.md#L1), shipped the
same day as `P3-13`, and its §2 is the design for decisions 1 to 7. This file is decision 8, the
run-time consultation reading, and it closes the item.

## 1. Before any design

Three probes against the running code, because decision 8 named a mechanism and the mechanism is
what had to be checked. The script is in the session scratchpad; each is one run of a real
pipeline.

- **`Deterministic` refuses a tool taking a `ModelHandle`.** Confirmed by construction:
  `Deterministic(fn, tools=[a tool taking one])` raised, naming FT-07 and per-node accounting.
  The refusal is at [`nodes.py` `Deterministic.__init__`](../../src/simple_agents/nodes/deterministic.py#L74).
- **`consult()` today is served from the cassette.** Measured over a record-then-replay pair:
  the channel was asked **1 time live and 0 times on replay**.
- **A tool holding a `ModelHandle` runs its body again on replay.** Measured the same way: the
  body ran **1 time live and 1 time again on replay**.
  [`context.py` `RunContext.call_tool`](../../src/simple_agents/context.py#L1057) returns
  `tool.call(...)` for a re-executed tool in every mode, cassette or not.

**Two more, prompted by Thilina's question at the sitting about what happens when the question
changes.** The first probe written for it was wrong and said there was no miss: the question came
back from the model, and on replay the model call was served from the cassette too, so the
question never changed. Redone at both places a question can change:

- **A question a node's own code holds is in the tool call's cassette key.** Changing it missed,
  and the miss named the field: `arguments.question (recorded 'Which fit?', now 'Which size?')`.
- **A question the model writes misses one level earlier.** An edited prompt missed on the model
  call, naming `messages[0].content`.
- **`Cassette.update` is how the new answer is got.** In both shapes the channel was asked
  exactly once more, with the new question, and the answer was recorded. That is the mode
  [`runner.py`](../../src/simple_agents/evaluation/runner.py#L636) `EvalSuite.record` already documents as filling
  in what an earlier recording does not hold.

## 2. Design

### 8. The consultation reading is made live, through a handle, and recorded

**Decision 8's stated mechanism could not be built as written.** It said the reading is *"a model
call made through `ModelHandle` inside the consult call"*. Probes 2 and 3 together say what that
does: a `ModelHandle` makes the tool re-executed, and a re-executed tool's body is
`channel(question, options)`, so the person would be asked again on every replay and on every one
of an evaluation's k rollouts. `docs/tools.md` §4.6 promises the opposite. Probe 1 is the second
wall: a consultation that routes lives in a `Deterministic` node, and that node kind refuses a
tool taking one. **The intent held and the mechanism changed**, which is stage 1's §3 item 1
happening in a different place.

**The ask stays what it was.** A cassette-stored tool call, the channel asked once,
`read_answer` applied wherever an answer arrives, its contract untouched.

**The reading is a separate library-owned step**, run wherever an answer first arrives: the live
tool return, the cassette replay ([`nodes.py` `_run_tool`](../../src/simple_agents/runtime/tooling.py#L151)),
and the resume path
([`nodes.py` `_delivered_answer`](../../src/simple_agents/runtime/consultation.py#L29)), which the item record
had already named as what the build would have to settle. It calls the project's reader through
a [`Reading`](../../src/simple_agents/tools.py#L359) handle, which emits a `model_call` parented
to the **consultation record**, charges the run's budget, and goes through the cassette.

That gives both halves decision 8 wanted. The reading re-runs on replay at the price of a
cassette hit, so k rollouts pay for one; and an edited reader prompt is a **miss on the reading's
own model call**, with the recorded answer untouched.

**Decision A: where the model comes from.** The project passes the client to the reader, which is
[`Retrieval.embed`](../../src/simple_agents/tools.py#L287)'s precedent applied:
which model reads an end user's prose is a property of the reader, not of the node that asked.
It needs nothing on `Deterministic` and nothing on the resume path, and it lets a cheap model read
answers while the agent runs on something else. **Rejected: the node's model**, absent on
`Deterministic`, which is where a routing consultation lives. **Rejected: the run's default
model**, which would have to be threaded to the resume path for no gain.

**Decision B: a `Deterministic` node can carry this one model call.** `simple-agents.md` §9 item
8 is amended rather than defeated, and the amendment is written there. The node's function is
still handed no client, `ctx` still exposes none, and a tool it calls may still take no
`ModelHandle`. **Rejected: refusing a model-backed reader on `Deterministic`**, which pushes a
project that only wants to ask and branch into an agentic node it does not otherwise need.
**Rejected: keeping the reading's cost off the node**, the way
[`_answering_model`](../../src/simple_agents/runtime/consultation.py#L188) keeps the stand-in's off, which
contradicts decision 8's ruling that the cost is the agent's.

**Decision C: the library ships a reader.** Thilina, 2026-08-18: ship it, and let a project edit
the prompt and choose the backend. This is not stage 1's *ship the seam and no default judge*
reversed: the library owns the reader's question, since `options` is its concept and `chose` is
what it routes on, and it does not own a judge's, which is the project's criterion.
`ModelReader` is the shipped one and `consult(read=...)` also takes a bare function of
`(reading, answer, options)`, so a reader that short-circuits an exact match without a model call,
or makes two calls, or pre-filters cheaply, is still the project's to write.

**`ModelReader` mirrors `SimulatedEndUser`'s shape**: a client, `instructions` with placeholders
it refuses to lose, a temperature, an output ceiling, and an `identity()`. The two are adjacent
and must not be joined: the stand-in writes the answer and its cost is measurement machinery, the
reader decides which option that answer was and its cost is the agent's. A reader that took the
stand-in's `declared_choice` would make `per_node.consultation_misreadings` zero by construction
and a broken reader undetectable, which is `Reply`'s own shipped rule about `chose`.

**Decision D: a reading that cannot be made ends the run**, with `attempts` bounding a retry that
states the failure back. Thilina asked for the retry at the sitting. `LLMNode` refuses to do this
([`nodes.py` `_validate`](../../src/simple_agents/builtins/extract.py#L104): *"an `LLMNode` makes exactly
one call, so there is no step in which the model can correct this"*), and the distinction is that
an `LLMNode`'s schema is the project's while the reader's output is a one-of-N choice the library
defines, so a model naming a non-option is recoverable by being handed the list again.
**Rejected: a new `unread` resolution**, which every `on_reply` route would need a branch for.
The consultation is recorded either way, carrying the answer, `chose` of `null` and the error, and
`resolution` stays `answered`: `unmatched` is a claim about what the end user said, and a broken
reader is not that claim. This is stage 1's vLLM semantics trap in a second place.

**The reader is out of the tool's `version`.** The version is part of a consultation's cassette
key, so covering the reader there would miss every recorded answer on a prompt edit and ask a
person again for nothing, which is what
[`_derived_version`](../../src/simple_agents/builtins/consult.py#L905) already documents for the
library's own function. What the run used is on the tool's manifest entry instead, as the model
and a digest of the prompt. Thilina's question at the sitting is what surfaced this: without the
manifest entry, changing which model reads answers would change routing behaviour and be
recorded nowhere.

## 3. Build

**Trajectory `0.23` to `0.24`. 2614 tests**, 44 of them new in
`tests/test_consultation_reading.py`. No other format moved.

**New**: `Reading` in `tools.py`; `ModelReader`, `DEFAULT_READING_INSTRUCTIONS`,
`READING_SCHEMA` and `_choice_in` in `builtins/consult.py`; `_read_the_answer`,
`_reading_handle` and `_call_reading_model` in `nodes.py`.

**Changed**: `ConsultTool` gains `reader`; `consult()` gains `read=` and refuses it beside
`match=`; `ConsultationRecord` gains `read_by`; `_tool_entry` gains `reader` through
`_reader_entry`; `Deterministic`'s docstring and its `ModelHandle` refusal; fourteen conformance
fixtures regenerated for the format bump.

**Five things the build found that the design did not know.**

1. **The preflight paid for itself on the first call.** A reading prompt at
   `max_output_tokens=1200` returned `finish_reason=length` with **empty content**, the whole
   ceiling spent on the chain of thought. At 4000 it returned in 7.1s at 1261 output tokens.
   This is the handoff's own row, met before any run rather than after twelve minutes.
2. **`ModelReader`'s default ceiling of 300 was unusable**, and 300 is what `SimulatedEndUser`
   declares. Measured: the three readings spent **404, 432 and 827** output tokens. The default
   is **1500** now. An unreached token costs nothing, so a ceiling tight around the verdict buys
   nothing and refuses every reasoning model.
3. **The shipped prompt is what makes the condition case right, and it was measured.** A
   stripped preflight prompt carrying only the reply format read *"Only if it is under 400 pages;
   otherwise, no"* as **`"no"`**, which is the wrong answer and the exact failure `P3-9`'s third
   row names. `DEFAULT_READING_INSTRUCTIONS`, which teaches that case explicitly, read it as
   `null` on both backends.
4. **Two of the first eleven mutations were not caught, and both tests were vacuous.** The
   version test compared two `ModelReader` instances, which have no readable source, so
   `derived_version` returned `None` either way and putting the reader into
   `_derived_version` changed nothing; it uses two functions with different source now. The
   charge test read the manifest's model-call count rather than the budget, so removing
   `run.charge` passed; a run bounded at `max_steps=1` asking twice is what catches it.
5. **Four citations in `dev-docs` broke and `--fix` could not repair them.** Moving lines in
   `tools.py`, `nodes.py` and `trajectory.py` left them on blank lines, and they name no symbol
   in backticks, which is the only thing `check_citations` can re-resolve. Repaired by hand with
   the names added, so the next edit is maintainable.

**Four more from the verification pass, after all of the above was green.** Each is a case the
suite did not reach, found by reading the diff back against what the sitting decided.

6. **`ConsultTool.reader`'s docstring was false.** It said the verdict *"is stored on the
   consultation and is what a replay and a resumed run take"*, which is decision 8's original
   wording and not what shipped: a replay reads again, with the model call served from the
   cassette. `ModelReader`'s *"the call is made once per answer"* was loose in the same way,
   since a retry makes two. Both corrected, and `plan.md` §4 with them.
7. **A reader raising an undeclared exception lost the consultation.** Measured: a reader
   raising `ValueError` reached `_run_tool`'s undeclared-failure handler, which wrote a
   `tool_call` record for an event that was a consultation and reported *"Tool 'consult'
   raised ValueError"*, naming the channel when the channel had worked. Nothing between the
   tool call and the record could raise that way before this item. `_read_the_answer` wraps a
   non-caller-facing failure now, so the consultation is recorded with the answer on it and
   the message names the reader.
   `test_a_reader_that_raises_still_records_the_consultation`.
8. **A prompt carrying any other brace constructed fine and raised at run time.** A project
   writing `Reply like {"chose": "yes"}` into `instructions` passed every construction check
   and raised `KeyError` on the first `.format`, **after the end user had been asked**. It is
   refused where it is written now, with the fix being to double the brace.
   `test_a_prompt_that_cannot_be_filled_in_is_refused_where_it_is_written`.
9. **A reader whose `identity()` raised would have lost the manifest.** It is read while the
   manifest is written, at the end of a run that has already happened, so the failure is
   recorded in the entry rather than raised.
   `test_a_reader_that_cannot_describe_itself_does_not_lose_the_manifest`.

**Eleven mechanisms were mutation-checked**, each broken in turn and each caught: the reading not
happening, the call parented to the node, `read_by` dropped, a failed reading resolving as
`unmatched`, the retry not rounding, the reader entering the tool version, the run not charged,
the manifest forgetting the reader, a failed reading writing no record, the resume path not
reading, and a question with no options still being read.

**One harness bug worth recording, because it is not the library's.** A test asserting the route
read `amended` where `apply` was right. A node with no declared `successors` falls through to the
next node in the list, so `apply` ran and then fell through to `stop` and `amend`, and the
pipeline's output was the last one's. The route a node took is read off its `node_execution`
record's `route` field, and that is what the test asserts now.

## 4. Verification

**Live against vLLM (`Qwen/Qwen3-1.7B`, port 8001) and Gemini (`gemini-3.1-flash-lite`).** The
script is a real agent: an `LLMNode` drafts a pitch, a `Deterministic` node consults the reader
about which of two titles to order, and `on_reply` routes on what the reading decided.
`max_output_tokens` is set on every node and a preflight call was made first, per the handoff.

**All three kinds `P3-9` measured were read correctly, on both backends.**

| The answer | `chose` | Route taken |
|---|---|---|
| *"Anything but The Witch of Whispervale."* | `The Will of the Many` | `order` |
| *"I have no strong feeling either way, go ahead."* | `null` | `hold` |
| *"Only if it is under 400 pages; otherwise, no."* | `null` | `hold` |

The default rule reads **none** of these, which is what `P3-9` measured and what
`docs/tools.md` §4.6.1 tabulates.

**What else the runs showed.**

- One `model_call` per consultation, parented to it, `read_by: "model"` on the record.
- Priced under a `ComputeBasis` at `0.0004` to `0.0006 USD` per run with
  `is_upper_bound: false` on vLLM.
- **Replay served every reading** (`replayed: true`, identical token counts) with the channel
  replaced by a string that must not be reached, and every verdict came back unchanged.
- Per-node accounting attributes the reading to the node that asked: `model_calls: 1` with its
  tokens on a `deterministic` node, which is decision 8's "the cost is the agent's" where a
  project would read it.
- **The ceiling refusal fires with the reader named**, and its instruction is a concrete call.

**The retry was exercised live**, with a prompt that forces a first reply naming no option.
At `attempts=2` the first reading returned `"A Book Nobody Offered"`, the retry stated that back
with the list, the second named an option, and both readings are recorded. At `attempts=1` the run
ended, and the consultation was recorded carrying the answer with `resolution: "answered"`,
`chose: null` and `read_by: null`.

**Two shapes the suite covers and the live runs did not**: a consultation the model chose to make
inside an `AgentNode`, and a replay of a **resumed** run, where the answer and the reading were
both filed in the later process and the replay needs neither.

**Everything above was run again after §3's items 6 to 9 were fixed**, since those changed the
code the first runs exercised. Both backends, all three answers, both replays, both retry paths
and the ceiling refusal came back the same.

## 5. Doc consequences

- **`docs/tools.md` §4.6.1 gains the reading**: `read=` and `ModelReader`, where the call lands
  and what it costs, why an edited prompt misses on the reading rather than on the answer, the
  prompt's placeholders, `attempts`, a reader of the project's own taking a `Reading`, and the
  one model call a `Deterministic` node can carry.
- **`docs/trajectory-format.md` §4.3 gains `read_by`**, in the field table and in the paragraph
  beside `chose` and `declared_choice`, and the current version moves to `0.24` in three places.
- **`docs/evaluation.md` §5.4 gains the distinction** between the stand-in and the reader, since
  both run in an evaluation and joining them would make `consultation_misreadings` zero.
- **`docs/index.md`** names the reading in its `docs/tools.md` row.
- **`CHANGELOG.md`** carries the `0.23` to `0.24` entry and what a project has to do, which is
  nothing unless it registers `consult(read=...)`.
- **One shipped statement stopped being true**: `Deterministic`'s *"No model call, and
  structurally no way to make one"*. It reads *"The function makes no model call, and is handed
  nothing that can make one"* now, and the fact that a reader is the one exception moved into the
  `ModelHandle` refusal, which is where a builder meets it.

## 6. Left open

- **A reader client is a model client nothing paces.** Confirmed by reading
  [`_clients_of`](../../src/simple_agents/evaluation/runner.py#L2846): it walks `llm` and `agent`
  nodes only, so a client held on a `ConsultTool` is in neither.
  **Destination:** [`plan.md` §2.2](../plan.md#L226)'s ceiling-on-one-client entry, where it is
  recorded as the third instance. Stage 1 logged the second.
- **A judging pass has no shipped way to survive a model that fails schema validation.**
  *This entry overstated the fault when it was first written and is corrected here.* It said
  `_through_judging` re-asks the same pass eight times. It does not: stage 1 closed that, and
  `test_a_pass_that_answers_nothing_stops_rather_than_asking_again` measures one round, not
  eight. Each round also asks only what is still missing.

  What is left is narrower and is not the round loop. **The library never calls the judge
  model**, by stage 1's decision 5: `using` is the project's function, handed the whole
  worklist and returning a `Label` each. So there is no model response the library could state
  a failure back into, and `ModelReader`'s shape does not reach a judge, which owns its own
  calls. What silently dropped the schema-invalid responses on the `Qwen3-1.7B` run was the
  verification harness, our code, and every project writes that code itself.
  **Destination:** [`plan.md` §1](../plan.md#L26) `P3-14`, scheduled behind `P3-1` on Thilina's
  decision of 2026-08-18, with [`items/a-shipped-judge.md`](../items/a-shipped-judge.md#L1) as
  its record. He took a shipped `ModelJudge` over a documented pattern or a wrapper, and its
  shape is six open questions.
- **Nothing else: nothing.** `P3-12` is closed, and [`plan.md` §4](../plan.md#L282) carries it.
