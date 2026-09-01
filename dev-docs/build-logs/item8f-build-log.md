# Item 8f — build log

**Kept while building, not reconstructed at the end.** On the precedent of
`item8e-build-log.md`. The end-of-item report and the shipped-document rewrites are reads of
this file.

The design of record is `archive/plan-history.md` item 8f. §1 records what was measured before the
sitting, §2 the sitting, §3 where building sharpened a decision, §4 where it turned out not to
hold, §5 what the build found that is nobody's design, §6 doc consequences, §7 existing tests
that had to change.

**Status: built, and the shipped documents written.** 2026-08-05. Baseline 814 tests at
`de3c8e1`; **845 tests** now. Trajectory `0.14`; manifest, suspension and results unchanged.
All fifteen committed cassettes re-recorded against live Mistral and live vLLM.

---

## 1. What was measured, before any design

The plan entry says the OpenAI dialect carries reasoning as `reasoning_content` on the message
and on the delta, and marks it an assertion needing a measurement. It was measured first, on
the rule item 8e recorded at its §1.3. **The assertion is false against both shipped
backends**, for two different reasons.

### 1.1 Mistral returns no reasoning field at all, on any model this account can reach

Measured 2026-08-05 against `https://api.mistral.ai/v1/chat/completions`. Fourteen models are
flagged `capabilities.reasoning: true` on `/v1/models`. Every one of the twelve reachable ones
answered with the same message shape:

```
message keys: ['role', 'tool_calls', 'content']      content type: str
```

No `reasoning`, no `reasoning_content`, no structured content list. Streamed, the deltas carry
`role` and `content` and nothing else. `mistral-small-2603`, the model every committed Mistral
cassette is recorded against, is one of the fourteen.

`prompt_mode: "reasoning"`, which is the documented switch, is refused on all twelve:

```
400 {"message": "Reasoning prompt mode is not enabled for this model", "code": "3051"}
```

The two `labs-leanstral-*` models answer 403, needing an admin to enable Labs models.

**So `MistralClient` has nothing to fill a reasoning field with**, and the shipped document
cannot claim the field is filled on both backends.

### 1.2 vLLM calls it `reasoning`, not `reasoning_content`

Measured against a live server on this machine, started for this purpose:

```
vllm serve Qwen/Qwen3-1.7B --revision 70d244cc86ccca08cf5af4e1e306ecf908b1ad5e \
    --port 8001 --gpu-memory-utilization 0.6 \
    --enable-prompt-tokens-details \
    --enable-auto-tool-choice --tool-call-parser hermes \
    --reasoning-parser qwen3
```

vLLM 0.26.0. The response field is `reasoning` on both the assembled message and the streamed
delta. `reasoning_content` is the deprecated spelling and survives only on the *request*, where
a validator renames it to `reasoning` before anything reads it
(`vllm/entrypoints/openai/chat_completion/protocol.py`).

The repository already held evidence of this and nobody had read it:
`tests/fixtures/wire/vllm/minimal.json` carries `"reasoning": null` on the message, captured at
item 5.

### 1.3 The measurements

One question, one model, `temperature=0.0`, `max_tokens=900`.

| Measured | Result |
|---|---|
| Non-streamed message keys | `role, content, refusal, annotations, audio, function_call, reasoning` |
| Reasoning / content, non-streamed | 2,295 chars of reasoning, 492 chars of content |
| `completion_tokens` for that call | 745 |
| Streamed events | 745 total: 599 carrying `reasoning`, then 144 carrying `content` |
| Streamed delta key order | `role`, `content` (empty), `reasoning` ×599, `content` ×144 |
| Same call with tools offered | `reasoning` filled, `content: null`, `tool_calls` present, `finish_reason: tool_calls` |
| Streamed with tools | 142 events: 130 `reasoning`, 8 `tool_calls` fragments, 2 chars of content |
| `include_reasoning: false` | `reasoning: null`, content unchanged, **`completion_tokens` still 745** |
| `chat_template_kwargs: {"enable_thinking": false}` | no reasoning generated at all, 172 completion tokens |

**Reasoning is billed whether or not it is returned.** That is the `include_reasoning: false`
row: the model generated the same chain of thought, the server dropped it, and the account was
charged for 745 output tokens either way.

### 1.4 Through the shipped seam, today

`VLLMClient` against the same server, same request:

```
complete():  content 492 chars   tokens.output 745
stream():    143 chunks to the sink, first chunk after 3,346 ms, 492 chars total
```

Two facts follow, and neither is a design opinion.

**A `model_call` record today reports 745 output tokens for 492 characters of content, and
nothing in the record explains the gap.** The 2,295 characters that account for it are read off
the wire and discarded, in `StreamAssembler.feed` and in both `complete` methods.

**`stream.first_chunk_ms` is time to first *answer* token, not time to first token.** On this
model the sink is silent for 3.3 seconds and 599 events while the backend is sending
continuously. `docs/trajectory-format.md` §4.1.3 calls the field time to first token.

### 1.5 Sending reasoning back, measured twice because the first measurement was of the wrong shape

**First measurement, and the wrong conclusion drawn from it.** A three-message conversation
`user / assistant / user` was sent with the assistant turn carrying nothing, carrying
`reasoning`, and carrying `reasoning_content`. All three rendered to 61 prompt tokens, and the
conclusion offered at the sitting was that vLLM accepts the field and renders nothing from it.

**That is true of the shape that was sent and false of the shape an `AgentNode` builds.** Qwen3's
chat template renders an assistant turn's reasoning only where the turn falls after the last
user message, which is the guard `loop.index0 > ns.last_query_index` in the template shipped
with the weights. A completed turn's reasoning is dropped by design; a turn inside the exchange
the model is still working on is rendered.

**Second measurement, of the shape the library actually sends.** `user / assistant with a tool
call / tool reply`, which is what an `AgentNode`'s second call carries, against
`/chat/completions`:

| Assistant turn carries | `prompt_tokens` |
|---|---|
| content only, which is what the library sends today | **58** |
| `reasoning` | **100** |
| `reasoning_content` | **100** |
| `<think>` inside `content`, which is what today's recordings hold | **100** |

The rendered prompt confirms it: with `reasoning` present the turn comes back as
`<|im_start|>assistant\n<think>\n...\n</think>\n\n<tool_call>...`, and without it the `<think>`
section is absent.

**So the chain of thought is wanted back within the turn, and the library drops it.** Both
spellings work on `/chat/completions`. `/tokenize` disagrees, scoring `reasoning_content` as 54
rather than 100, because the two endpoints do not run the same request normalisation; the
completions figure is the one that counts, since it is the path the library calls.

Mistral has no field to return it in at all (§1.1).

### 1.6 A claim shipped at item 8e was unmeasured and is true

`src/simple_agents/adapters/vllm.py:155` says a server started with a reasoning parser reports
the chain of thought separately and one started without it has the chain inside the content.
That was written at 8e without a call behind it. Both halves now have one: §1.3 is the parser
case, and `tests/cassettes/tools-vllm.jsonl` holds two model calls whose `content` carries
`<think>` tags, recorded against a server started without one.

### 1.7 Starting the server with a reasoning parser degrades an `AgentNode`, and that is a library defect

`nodes.py:919` and `nodes.py:932` rebuild the assistant turn from `response.content`. Without a
reasoning parser the content holds the whole `<think>` block, so the model's own reasoning goes
back to it. With the parser on, the content holds the answer alone, or is empty on a
tool-calling turn, so it does not.

§1.5 measures what that costs: 58 prompt tokens where the model's own chat template expects
100, with the `<think>` section absent from the turn the model is still working on. **The
defect is the library's rather than vLLM's.** The parser splits the output correctly, and the
template renders reasoning back correctly when it is given any; what is missing is the library
carrying the field between the response and the next request.

### 1.8 State of the committed cassettes

70 `model_call` entries across 15 files. Every one was recorded against a server started
without a reasoning parser, so **an absent reasoning field on a replay is what the live run
also had**, and the `rate_limit` defect at `item8e-build-log.md` §4.5 does not bite the files
that exist. 19 of the 70 carry an assistant turn in the keyed request, which is the set a
change to the conversation shape would invalidate.

### 1.9 The other two providers, read from their published SDK types rather than measured

No Anthropic or OpenAI key exists on this machine, so these are type definitions the provider
publishes, not calls. `anthropic` 0.120.2 and `openai` 2.53.0, installed into a scratch
environment and read.

| Surface | Where reasoning lives | Shape |
|---|---|---|
| Mistral chat completions | nowhere | measured, §1.1 |
| vLLM chat completions | `message.reasoning`, `delta.reasoning` | `str`, measured, §1.2 |
| OpenAI chat completions | nowhere | `ChatCompletionMessage` is `content, refusal, role, annotations, audio, function_call, tool_calls` |
| OpenAI Responses | `ResponseReasoningItem` | `id: str`, `summary: [{type, text}]`, `content: [{type, text}] \| None`, `encrypted_content: str \| None` |
| Anthropic Messages | a content block | `{type: "thinking", thinking: str, signature: str}` and `{type: "redacted_thinking", data: str}`; streamed as `thinking_delta` then `signature_delta` |

Three structural facts follow, and each one is fatal to a bare string.

- **Anthropic carries a `signature` beside the text.** It is returned verbatim on the next
  request or the provider rejects the conversation.
- **Anthropic has a block with no text at all.** `redacted_thinking` carries `data` and nothing
  readable.
- **OpenAI's Responses item carries an `id` and `encrypted_content`**, and the readable part may
  be a summary rather than the chain of thought itself.

**`ChatCompletionMessage` has no reasoning field**, so an OpenAI adapter written against
`_openai_wire.py` reaches reasoning only by moving to the Responses API. That is a sizing fact
for the `plan.md` §2.2 entry, which currently calls OpenAI the cheap one.

### 1.10 The same agent run in four configurations, before any fix

The shipped agent recording's pipeline and question (`scripts/record_backend_cassettes.py`,
`agent_pipeline`, one `AgentNode` with a `search` tool over a four-entry catalogue), run live in
each configuration. Every conversation below is `inputs.messages` read out of the trajectory,
so it is what the library sent rather than a reconstruction.

| Configuration | Calls | Answer | Reasoning in the conversation |
|---|---|---|---|
| vLLM, parser on, thinking on | 2 | `retailer='Belmont'` | **absent, dropped by the library** |
| vLLM, parser on, thinking off | 2 | `retailer='Kirkwall'` | none generated |
| vLLM, parser off, thinking on | 3 | `retailer=Unknown(reason='Kirkwall')` | present, inside `content` |
| Mistral, no reasoning on any model | 3 | `retailer='Kirkwall'`, policy filled | not applicable |

`Kirkwall` is the retailer and `Belmont` is the trouser, so the first row's answer names the
garment where the question asked for the seller.

**One run each, one 1.7B model, `temperature=0.0`. This is not an accuracy measurement and must
not be reported as one**, which is the FT-06 trap the `tools.md` sitting recorded. What it shows
is the mechanism, and the mechanism is visible in the token counts rather than in the answer.

**Parser on, thinking on.** Call 0 spends 251 output tokens and returns a tool call worth about
26 of them; the rest is the chain of thought. The conversation call 1 sends back is:

```
---- user
    Which retailer sells the trouser with a 34 inch inseam, and what is its returns policy? ...
---- assistant
    (empty content)
    [tool call] search({"query": "trouser 34 inch inseam"})
---- tool
    trousers-ashford: ... Sold by Northgate.  trousers-belmont: The Belmont trouser has a
    34 inch inseam. Sold by Kirkwall.
```

**The assistant turn is empty.** 225 tokens of the model's own reasoning were generated, paid
for, read off the wire and discarded, and the turn the model is still working on carries no
trace of them.

**Parser off, same model, same question.** The identical turn carries the whole chain of
thought, because it rode inside `content`:

```
---- assistant
    <think> Okay, let's tackle this user query... I need to use the search function to find
    products with a 34-inch inseam... </think>
    [tool call] search({"query": "trouser 34 inch inseam"})
```

That is the 58-versus-100 prompt-token difference of §1.5, in the library's own output.

**Parser off is not the correct configuration either.** Its `content` holds the chain of
thought, so an `LLMNode` validates an output schema against text that begins with `<think>`, and
in this run the model's second call produced a malformed `finish` argument, was rejected by the
schema, and recovered into `Unknown(reason='Kirkwall')`. The reasoning was preserved and the
answer still came out mangled.

**The two configurations that must not change** are rows two and four: a reasoning model with
thinking turned off, and a model that has no reasoning at all. Both complete correctly today,
and both are the acceptance check for the fix.

---

## 2. The sitting, and what it settled

Held 2026-08-05, after §1's measurements and before any code. §1 is why: three of the seven
questions turn on what the backends do, and the plan entry's claim about that was marked as
needing a measurement.

| Question | Settled |
|---|---|
| What shape the field is | `Reasoning(text, blocks)`. `text` for the record and the reader, `blocks` for state a backend needs returned verbatim. |
| Whether an `AgentNode` sends it back | Yes. The loop keeps it on the assistant turn in the library's own shape; `messages_to_wire` decides what goes on the wire per adapter. |
| What a cassette does | Stores it. Every vLLM cassette is re-recorded under a reasoning parser, after the fix. |
| Calling a sink an adapter may not accept | Keyword-only `on_reasoning`, passed only where the signature accepts it, with a loud refusal rather than silence. |
| What item 8b inherits | Nothing new: reasoning goes inside `outputs`, which 8b already samples. |
| Asking for reasoning, not just recording it | An adapter-level `reasoning` flag meaning "do not suppress", defaulting to `True`. |
| A reasoning token count | No. Neither shipped backend reports one. |

### 2.1 `blocks` ships unexercised, by explicit exception

`text` is filled by vLLM and by nothing else today. `blocks` is filled by neither, and the
library's own rule is that a field no adapter can fill should not exist. §1.9 is why it ships
anyway: Anthropic's `signature` has to be returned verbatim, its `redacted_thinking` block has
no text at all, and OpenAI's Responses item carries an `id` and `encrypted_content`. A string
cannot hold any of the three, and both providers are named in `plan.md` §2.2 as next.

**Thilina granted the exception**, and asked that it be measured with real keys when the
adapters are built rather than deferred indefinitely. There is no free API tier for either
provider, and no key on this machine, so the shape rests on published SDK types until then.

### 2.2 A measurement was presented, and the conclusion drawn from it was wrong

§1.5 records it. The first measurement of "does sending reasoning back change anything" used a
conversation shape Qwen3's template renders without thinking, so the answer came back "no
effect" and was reported that way at the sitting. Thilina's Q3 asked whether the parser was
implemented incorrectly, which is what sent the question back for a second look, and the second
measurement reversed the conclusion.

**The lesson is not the template.** A measurement was made of a shape the library does not
build, and reported as though it were a measurement of the library's behaviour. Choosing the
shape under test is part of the measurement.

### 2.3 The knob was over-complicated, and the correction was his

Two switches were presented as needing separate treatment because their cost differs by 4×:
`include_reasoning: false` still generates and bills the chain of thought and only withholds it,
while `enable_thinking: false` stops it being generated. Thilina's reading is simpler and is the
one that shipped: `enable_thinking` controls whether thinking happens, `include_reasoning`
controls whether it is delivered, and turning the first off makes the second moot. One flag
controls generation. **The library never sets `include_reasoning: false`**, because paying for a
chain of thought and discarding it is the failure this item exists to end.

### 2.4 The construction-time check is at the adapter, not the server

Thilina's objection to detecting the misconfiguration only from a response: the library should
know at construction time whether reasoning and a reasoning parser contradict each other.
Measured against the live server, vLLM 0.26.0 publishes nothing about its parsers on
`/version`, `/v1/models`, `/health`, `/load` or `/metrics`, so the library cannot ask.

What his objection did settle is where the free check lives:

> **The adapter knows whether it has a mechanism at all. Only a response knows whether the
> mechanism bound.**

`MistralClient(reasoning=False)` is refused at construction with no traffic, because no model
that API serves accepts the switch. The vLLM case has a mechanism whose effect depends on
server configuration, so it is a warning on the first response that shows it.

### 2.5 The library does not split `<think>` out of content

Raised by Thilina after §1's transcripts, and settled against doing it. It would fix the
unparsed case outright, and it reverses `docs/model-clients.md` §1's rule that a backend which
cannot do something raises rather than the library substituting an implementation. The tag is
model-specific rather than standard, and a false positive would rewrite `content`, which is the
string an output schema validates and the string that goes back into the conversation. A
warning cannot damage a record; a split can.

---

## 3. What building it changed about the design

### 3.1 Either sink turns streaming on, and the content recorder is built either way

The design had `on_reasoning` as a second sink beside `on_token`, and the first implementation
gated streaming on `on_token` alone, because that is what `_call_model` already checked. A run
given only `on_reasoning` then made an ordinary `complete()` call and delivered nothing.

Either sink now turns it on. The content recorder is built even where the run supplied no
`on_token`, delivering to nothing, because the chunk boundaries it captures are what a cassette
stores and a replay re-emits. The reasoning recorder is built only where the run asked for one,
since there is nothing to record for a channel nobody is watching.

Found by a test written for the two-channel case, not by reading the code.

---

## 4. What in the settled design turned out to be wrong

### 4.1 The unparsed-chain-of-thought detector, on its first contact with a committed fixture

The rule as designed was "content contains `</think>` and no reasoning field arrived". The suite
failed immediately on `tests/fixtures/wire/vllm/stream_minimal.json`, whose content is
`<think>\n\n</think>\n\nOK.`.

**That is the configuration Thilina asked to have protected**: a reasoning model with thinking
turned off. Qwen3's chat template opens the answer with an empty think block when
`enable_thinking` is false, so a correctly configured project would have been warned on every
call it made.

The rule now requires the content to *open* with the tag and the block to be non-empty. A
response cut off by `max_tokens` part-way through thinking has an opening tag and no closing
one, and is still a chain of thought; a response that mentions the tag in the middle of its
prose is not one.

**The fixture caught it, and no reasoning about the design would have.** It was captured at item
5 for an unrelated purpose.

---

## 5. Findings

### 5.1 The fix makes the two vLLM configurations agree, which is the property to check

The four-configuration run of §1.10, repeated against the fixed library:

| Configuration | Before | After |
|---|---|---|
| parser on, thinking on | 2 calls, reasoning dropped, `retailer='Belmont'` | 3 calls, reasoning carried, `retailer=Unknown(reason='Kirkwall')` |
| parser on, thinking off | 2 calls, 26 and 43 output tokens, `Kirkwall` | unchanged |
| parser off, thinking on | 3 calls, `<think>` inside content, `Unknown(reason='Kirkwall')` | unchanged, plus one warning naming `--reasoning-parser` |
| Mistral | 3 calls, `Kirkwall` and the policy | unchanged, no reasoning key anywhere |

**Row one now matches row three.** Turning the reasoning parser on and off stops changing what
the agent is told about its own previous turns, which is the whole of the defect. The assistant
turn carries 970 characters of reasoning where it carried an empty string.

**Rows two and four are byte-identical**, which is what the fix had to be: a backend that
reports no reasoning builds the conversation it built before, because the key is absent rather
than null.

**The answers are not the measurement and must not be read as one.** One run each, one 1.7B
model. Row one's answer improved and row three's did not change; both were single runs, and the
FT-06 trap is reading a difference off two point estimates.

### 5.2 Every committed cassette was re-recorded, and five recorded figures moved

All fifteen, both backends, the vLLM ones against a server started with `--reasoning-parser
qwen3`. `dev-docs/design/trajectory-format-changelog.md` under `0.14` carries why the recording
configuration rather than the format is what forced it.

`tools-vllm.jsonl` was the one the context sitting had deliberately left alone, on the ground
that a 1.7B model would re-decide its tool calls. It did, and the new recording is better:
`retailer='Kirkwall'` where the old one carried a chain of thought inside `content`.

Five figures in `test_adapter_integration.py::TestEvaluation` moved with the eval recording, and
§7 lists them. Each was checked against the property its test exists to demonstrate before the
number was updated.

### 5.3 A cited section moved and the checker could not see it

`docs/model-clients.md` gained §6 for reasoning, so `Writing an adapter` became §7.
`docs/context.md:59` cited §6 for what an adapter has to raise, and `prose_check` passes either
way because a §6 exists. Traced by hand, which is the fourth sitting running that this hole has
been found the same way.

---

## 6. Doc consequences

Written after the build, on the instruction items 8c, 8d and 8e followed. **The `docs/` rows are
done; the `dev-docs/` row is drafted and awaiting approval**, since that tree is the design
of record.

| Document | Section | What it said | What it says now |
|---|---|---|---|
| `docs/model-clients.md` | new §6; §6 → §7 | nothing about reasoning | **Done.** §6 Reasoning output: what is recorded, the sink, the `AgentNode` turn, and §6.1 on turning it off. Two rows added to the §2 comparison. `Writing an adapter` renumbered to §7, with the optional keyword and what an adapter fills. The inbound citation at `docs/context.md:59` traced by hand. |
| `docs/model-clients/vllm.md` | §2, §4 | one sentence on the parser | **Done.** What `--reasoning-parser` decides, the serve command carrying it, why the adapter cannot check the flag, and the client-level `reasoning=False` beside the per-node one. |
| `docs/model-clients/mistral.md` | §6 | — | **Done.** No model this API serves separates it, measured, and why `reasoning=False` is refused. |
| `docs/pipeline.md` | §1.1, §1.9 | two refusals | **Done.** `on_reasoning=`, `kind` on a `TokenEvent`, and a third refusal. |
| `docs/trajectory-format.md` | §4.1, §4.1.3, new §4.1.4 | `0.13` | **Done.** `0.14`, the `outputs` object with its own subsection, `reasoning_chunks` on `stream`, and what `first_chunk_ms` measures on a reasoning model. |
| `docs/evaluation.md` | §7.4 | streaming does not arise | **Done.** One sentence: reasoning is recorded during an evaluation, since it comes off the response rather than the stream. |
| `docs/index.md`, `README.md` | the tables | — | **Done.** One line each. |
| `CHANGELOG.md` | Unreleased | `0.13` | **Done.** What each change costs a project. |
| `dev-docs/design/trajectory-format-changelog.md` | — | through `0.13` | **Done.** `0.14`, what it settled, and what it cost. |
| `dev-docs/plan.md` | §3.1 item 8f | the design as scheduled | **Drafted, approval needed.** The settled design, and the two claims §1 found false. |

**Not touched, and deliberately.** `docs/tools.md` owes nothing: reasoning changes nothing about
what a tool is or how one replays. `docs/context.md` owes only the renumbered citation, since a
context builder runs before anything is sent. `docs/run-envelope.md` owes nothing: no manifest
field changed, and the trajectory version it names is read from the code. `docs/failure-taxonomy.md`
owes nothing; no entry reads `reasoning`.

---

## 7. Existing tests that had to change

Kept apart from §3 and §4 so nothing is quietly folded into a design note. **An existing test
needing a change is a finding to report, not a test to edit.**

### 7.1 Two, both the format bump landing where it should

| Test | What changed |
|---|---|
| `test_trajectory_conformance.py::test_format_version_is_declared_on_every_record` | `0.13` becomes `0.14`. |
| `test_run_envelope.py::test_it_names_the_trajectory_it_belongs_to` | `trajectory_format_version` is `0.14`. |

`test_packaging.py::test_the_trajectory_format_document_states_the_version_the_writer_writes`
also failed and needed no test change: the document moving to `0.14` fixed it.
`test_trajectory_conformance.py::test_model_call_has_its_type_specific_fields` did **not** fail,
because `reasoning` went inside `outputs` rather than beside it, which is the §2 decision
showing up as one fewer thing to change.

### 7.2 Five figures in the evaluation integration tests, from the re-recording

Not behaviour changes. A fresh recording is a fresh set of answers from a 1.7B model.

| Assertion | Was | Now | Property it demonstrates |
|---|---|---|---|
| `metrics["accuracy"]` | `4/9` | `5/9` | that the number is what the live run produced |
| `metrics["recall"]` | `1/6` | `2/6` | the same |
| `nodes["hunt"].tool_calls` | 20 | 22 | 22 calls against 5 stored entries, which is FT-20's mechanism |
| model-call entries and distinct seeds | 27 | 31 | the seed is in the key, so no two rollouts share a response |
| e2's three outcomes | `correct, missed, missed` | `missed, missed, correct` | that one rollout hides run-to-run variance |

**The last one was checked before it was updated**, on the `tools.md` sitting's precedent, where
a migration silently left a rollout-variance test with no variance to demonstrate. This
recording has variance on **both** examples that have a value to find, so the test now asserts
it over `e1` and `e2` rather than `e2` alone.

### 7.3 The checkpoint: none

The whole suite passed at 814 with the seam restructured, `Reasoning` added to `ModelResponse`,
both adapters filling it, the cassette storing it and the sink threaded from `Pipeline.run`
through `RunContext` to `_call_model`. Only the format version had to move.

### 7.4 Every refusal and warning watched to fail

Nine, each disabled once and its test run.

| Disabled | Test that failed |
|---|---|
| the reasoning-sink refusal | `test_a_client_that_takes_no_reasoning_sink_is_refused_by_name` |
| the reasoning-pieces rebuild check | `test_an_adapter_whose_pieces_do_not_rebuild_its_reasoning_is_refused` |
| `MistralClient`'s `reasoning=False` refusal | `test_mistral_refuses_a_control_it_cannot_apply` |
| the unparsed-chain-of-thought warning | `test_it_warns_once_when_the_chain_arrives_inside_the_content` |
| the empty-think-block exemption | `test_an_empty_think_block_is_not_a_missing_parser` |
| the assistant turn carrying reasoning | `test_the_assistant_turn_carries_the_reasoning_back` |
| Mistral dropping reasoning from the wire | `test_mistral_drops_it_because_it_has_no_field_for_it` |
| `PacedClient` republishing the capability | `test_paced_client_republishes_what_it_wraps` |
| reasoning stored in the cassette | `test_a_replayed_call_reports_the_reasoning_the_recording_held` |

**The seventh took two attempts, and the first attempt is the finding.** Removing the
`reasoning_field is not None` guard left `messages_to_wire` writing the field under a `None`
key, which the test's `"reasoning" not in sent` check passed. The mutation that binds is making
Mistral pass `reasoning_field="reasoning"`, which is the decision the test is about. **A
disabled guard that still passes means the test was checking the wrong thing.**
