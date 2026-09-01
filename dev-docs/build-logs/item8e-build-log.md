# Item 8e — build log

**Kept while building, not reconstructed at the end.** On the precedent of
`item8d-build-log.md`. The end-of-item report and the shipped-document rewrites are reads of
this file.

The design of record is `archive/plan-history.md` item 8e as rewritten at the sitting. Nothing here
reopens it. §2 records where building it sharpened a decision, §3 where it turned out not to
hold, and §4 what the build found that is nobody's design.

**Status: built, and the shipped documents written.** 2026-08-04. Baseline 770 tests at
`4109b02`; **810 tests** now. Trajectory `0.13`, manifest `0.7`, suspension unchanged at `0.1`,
results unchanged at `0.2`. Cassettes recorded against live Mistral and live vLLM.

---

## 1. The sitting, and what it settled

Held 2026-08-04, before any code. The plan entry named three open questions and the three
things item 8d left it. Seven decisions came out, because the framing question was not one of
the six and had to be settled first.

**The framing.** The library's own control flow cannot use a partial response: a node validates
an output schema, dispatches a tool call and charges a budget only against an assembled one. So
streaming is an additional delivery channel for bytes the call was going to produce anyway, and
every option was judged on how little it disturbs what exists. That is what made the seam
question answerable.

| Question | Settled |
|---|---|
| A third method or a flag on `complete` | Neither. A second Protocol, `StreamingModelClient(ModelClient)`, adding `stream(request, on_chunk) -> ModelResponse`. `ModelClient` is unamended. |
| What a cassette stores, and what a replay re-emits | Chunk cut offsets into `content` plus `first_chunk_ms`, on the entry beside `duration_ms`. A replay re-emits the same pieces with no simulated timing. Streaming is not in the key. |
| What a `model_call` says | A `stream` object carrying `chunks` and `first_chunk_ms`, `null` when the call did not stream. Trajectory `0.13`. |
| A `Suspend` mid-stream (8d) | The delivered tokens cannot be recalled and the call is made again from the start on resume. `error.class` gains `suspended`. |
| A token event against `on_progress` (8d) | A second callback, `run(on_token=)`, with the relationship stated: a `TokenEvent` falls between its node's `started` and `completed`/`failed` `NodeEvent` and carries the same `node_id`. |
| Composing with a wrapper that does not implement it (8d) | Presence of `stream` is the capability declaration. A wrapper without it is refused by name at run start, never emulated. `PacedClient` gains a delegation. |
| **Which calls stream** (not in the plan entry) | The node declares `stream=True`; the run supplies the sink. Forced by Thilina, and the correction that produced it is §1.1. |

### 1.1 Streaming was costed per run and the cost is per call

The recommendation taken into the sitting was a run-level `on_token=` that streams every model
call, with the builder filtering events by `node_id`. Filtering after the fact is free only
while streaming is free.

Thilina's objection was to the refusal in §1.2, and it exposed this instead: on a backend that
does not report usage on a stream, a run with a five-turn `AgentNode` and one answer node would
lose token counts on **six** calls to buy visible output on one. The library has to know which
calls to stream before it makes them, and only a node declaration can tell it that. The
run-level answer had already been given and was revised at his confirmation rather than
quietly amended.

### 1.2 A refusal was designed so the builder chooses and then took the choice back

The recommendation was that a streamed response with no usage block refuses, waivable through
`stream_without_usage=` on the adapter, so the builder decides between losing token accounting
and dropping streaming. The same document then said a backend that *never* reports usage on a
stream may ship without `stream` at all.

Thilina rejected it: the builder can still decide the trade, and a backend that never reports
usage and one that sometimes fails to are the same trade. The measurement in step 4 does not
gate whether the method exists; it decides what the shipped document tells a builder before
they wire it up.

### 1.3 A claim about backends was asserted rather than checked, for the second time in this project

The plan said the sink receives content deltas only and reasoning deltas are not forwarded,
offered as a fact. It was not checked, which is the failure the context sitting recorded as
*inference about a backend is not a measurement of one*.

Checking found the rule is right for a reason that was not given, and found something else:
`grep -rn "reasoning" src/simple_agents/adapters/` returns nothing, so **neither adapter reads
a reasoning field and the library has been discarding reasoning output since item 5**. The rule
therefore rests on consistency with the non-streamed path rather than on any backend's
behaviour, and what each backend puts on a streamed delta stops deciding anything. It is still
measured at step 4, for the document.

Two gaps recorded as work that has to exist, at Thilina's instruction, as `plan.md` §2.2
entries: reasoning output is not recorded anywhere, and one model client serves a whole run so
a pipeline cannot use two backends. §5 carries them.

---

## 2. What building it changed about the design

### 2.1 The chunk recorder is held by the caller, not created inside the call

The sitting had the library wrapping the sink and handing the wrapper to the adapter, which is
what `stream_call` did first. That works until a call raises part-way: the wrapper lives inside
the frame that raised, so what had already been delivered goes with it.

`ChunkRecorder` is now built in `_call_model` and passed down, so a `Suspend` mid-stream still
has the text and the boundaries in hand when it writes the record. Nothing else moved; it is the
same object one level up.

### 2.2 A wrapper's `stream` has to be an instance attribute, not a class method

`PacedClient.stream` was written as an ordinary method delegating to the inner client. The
refusal that checks `hasattr(model, "stream")` then passes for every `PacedClient`, including
one wrapping an adapter that cannot stream, and the loud refusal before the run becomes an
`AttributeError` during it.

It is bound in `__init__` only where the inner client has one. The comment written above the
first version claimed the behaviour the code did not have, which is what made it visible.

### 2.3 The refusal is split across two layers, on `locate_overflow`'s precedent

The message the sitting drafted names the node, the node kind, and which of the run's limits the
missing counts affect. The adapter knows none of those: it holds a `ModelRequest` and nothing
else. `_http.py` already had this shape, raising `ContextOverflow` with the backend's fact and
letting `locate_overflow` add the node and the call index.

`StreamUsageMissing` carries `model`, `adapter` and a `summary`, and `_locate_missing_usage`
rewrites the message around the summary. The adapter's own message keeps both fixes it can state,
so a project calling `stream()` directly is not handed a bare complaint.

### 2.4 Every consequence in that message is conditional, and that was Thilina's catch

The drafted message named `max_tokens`, cost and FT-27 unconditionally. `Budget` permits any axis
to be `None`, so a pipeline with no token limit and no cost basis would have been told three
things that are not true of it. Each clause now appears only where the run has it, and a run with
none of them is told what is true instead.

---

## 3. What in the settled design turned out to be wrong

### 3.1 Nothing in the design. One measurement changed what the documents say

The seven things §4 measured came back as the design assumed on six of them. The seventh is
§4.3, which is a defect the design did not create and could not have predicted, and it changed
`docs/model-clients.md` §7 rather than the design.

---

## 4. Findings

### 4.1 A `Suspend` from a `ModelClient` is recorded as a caller-facing failure, at HEAD

Found by tracing the path item 8d opened, and verified by running it rather than by reading it:

```
model_call | error: {"class": "caller_facing", "type": "Suspend", ...} | ended_at: None
node_execution | error: null
```

`_call_model` catches `Exception` and calls `_emit_failed_call_record` before re-raising
(`nodes.py:1260`), and `Suspend` is an `Exception`. Item 8d decided the opposite for the tool
path deliberately: `call_tool` stores nothing on `Suspend` because the tool did not fail
(`context.py:324`), and `Suspend`'s own docstring says the node did not fail. Anything counting
caller-facing failures over a trajectory over-counts every suspension.

Nothing is lost: the node record already carries `termination: "suspended"`. The label is
wrong, not the information. `error.class` gains a third value, `suspended`, which is 8e's to
land because a stream stopped part-way is exactly this record.

### 4.2 Retries mean something different once a call streams

`_http.py` retries on status, and a status arrives before any chunk, so an HTTP-level retry is
unaffected and `docs/model-clients.md` §6's "retries happen inside one call" holds up to the
first chunk. A transport failure *after* the first chunk cannot be retried, because retrying
would re-deliver text an end user has already seen. Nothing in the current contract said which
of those it was describing; `post_stream` now raises there, naming how many events arrived, and
§7 says so.

### 4.3 Mistral publishes no rate-limit allowance on a streamed response, and `PacedClient` goes quiet

The headline finding, and one only a live call could produce. Measured 2026-08-04 against
`mistral-small-2603`, same request, same account, minutes apart:

```
NON-STREAMED headers: [..., x-ratelimit-limit-req-minute, x-ratelimit-limit-tokens-minute,
                       x-ratelimit-remaining-req-minute, x-ratelimit-remaining-tokens-minute,
                       x-ratelimit-tokens-query-cost]
STREAMED     headers: [...]        # none of them
```

`PacedClient` reads `ModelResponse.rate_limit`, which is built from exactly those headers. So a
node declaring `stream=True` hands it nothing, and it pauses for nothing while the account walks
into a 429. **This is the same shape as the finding that put `rate_limit` on the response in the
first place** at the item 7 checkpoint: both sessions estimated an allowance the backend was
already publishing, and here the library reads the published figure and then stops receiving it.

`PacedClient` warns once when an allowance it *was* reading stops arriving. A backend that never
publishes one stays a silent passthrough, which is the existing documented behaviour and is
correct: there is nothing to report. What is new is a control that was working and quietly went
dead, which is the `AppendAll(max_input_tokens=...)`-that-can-never-bind shape item 6 shipped a
warning for.

The recorded cassette holds both calls, so the difference is visible in one file:

```
call 0 (streamed):     rate_limit=None
call 1 (not streamed): rate_limit={'remaining_requests': 48, 'remaining_tokens': 49741}
```

### 4.4 What the rest of the live measurement showed

Six of the seven came back as the design assumed, and two of them are worth recording because
they were open questions rather than confirmations.

| Measured | Mistral | vLLM (Qwen3-1.7B) |
|---|---|---|
| Usage on a streamed response | reported, **even without `stream_options`** | reported, with `stream_options.include_usage` |
| `prompt_tokens_details` | `cached_tokens` present | survives streaming, `input_cache_write: 128` |
| `finish_reason` | on the last event, alongside `usage` | on the last event |
| Chunks / time to first token | 8 / 361ms | 26 / 271ms |
| `"".join(chunks) == content` | true | true |
| Tool-call fragments | not exercised | 17 fragments, two parallel calls, joined by `index` |

**Mistral reports usage on a stream without being asked**, which means refusal 3 cannot fire
against either shipped backend today. Its evidence is a fixture rather than a recording, and the
build log says so rather than letting a green suite imply the refusal was seen against a real
backend.

**The tool-call assembly was worth measuring.** vLLM sends the `id` and `name` on the first
fragment of each call and the arguments in pieces afterwards, with `index` the only thing joining
them. Two parallel calls interleave nothing but would be indistinguishable without it.
`StreamAssembler` keyed on `index` from the start; the measurement is what turned that from an
assumption into a fact.

### 4.5 `rate_limit` does not survive a cassette round trip, and that is not this item's

Found while writing an integration test that could not be written. `encode_model_response` stores
content, tool calls, finish reason, identity, tokens and concurrency, and not `rate_limit`, so a
replayed `model_call` records `rate_limit: null` whatever the live run saw. **A replayed
trajectory therefore differs from the live one on a field the format declares required.**

It is the same shape as the duration gap the context sitting found and fixed as
`recorded_duration_ms`. **Reported rather than fixed at first**, on the ground that nothing reads
the field and the scope is the deliverable; Thilina asked what fixing it would cost and then
called it, so it is fixed.

**The `recorded_duration_ms` precedent does not argue against it, and that is what settled it.**
That field is separate because `started_at` and `ended_at` *are* measured on a replay, so writing
the recording's duration into them would be a lie. There is no replay-time allowance at all: no
call is made, so nothing measures one. Carrying the recorded figure into `rate_limit` fills a
field that would otherwise be null, which is exactly what `tokens` and `concurrent_requests`
already do. It was omitted rather than decided against.

**The one real cost, and it is in the changelog.** `store()` detects divergence by comparing
whole responses, so appending to a cassette written before the change counts old entries against
new ones as the backend answering differently. Re-recording the file avoids it, which is what
the recording script does.

**It paid for itself immediately.** `tests/cassettes/stream.jsonl` was re-recorded against live
Mistral, and the integration test that could not be written now exists: one recording holding
both calls, the non-streamed one carrying `remaining_requests: 48` and the streamed one `null`.
The claim in §4.3 is now asserted at the envelope layer over real recorded data, not only at the
adapter layer over a fixture.

### 4.6 A stated rationale in `plan.md` was false, and reading the letters as an order is why

`archive/plan-history.md` item 8a said "the heading sits here because that is the build order". The headings
run 8c, item 9, 8d, 8e, 8a, 8b, so item 9's entry sits in the middle of the lettered ones and the
document order is neither build order nor alphabetical. **Thilina read the letters as a sequence
and asked whether part of item 8 had been skipped**, which is what found it.

Nothing had been skipped: item 8 was built 2026-07-29, and 8a and 8b were created the next day at
the document review and scheduled deliberately after item 9. The build order is
**8 → 8c → 8d → 8e → 9 → 8a → 8b → 10**. It is now stated at the top of §3.1 rather than left to
be inferred from where a heading landed, and the false sentence is corrected with a note saying
what it used to claim.

**The lesson is not about the letters.** A rationale sentence was written to explain a layout
decision, was wrong on the day it was written, and survived because nobody had reason to check a
claim about heading placement. It is the same shape as `simple-agents.md` §9 #12's first repair
at the 8d sitting, which was one approval away from entering the do-not-change list while being
false.

---

## 5. Doc consequences

Written after the build, on the instruction items 8c and 8d followed. **The `docs/` rows are
done; the three `dev-docs/` rows are drafted and awaiting approval**, since that tree is the
design of record.

| Document | Section | What it said | What it says now |
|---|---|---|---|
| `docs/model-clients.md` | new §7; §7 → §8 | no streaming | **Done.** §7 Streaming: the node declaration and the sink, what each backend delivers as a measured table, the waiver, and what a run records. `Writing an adapter` renumbered to §8, with the optional third method. The inbound citation at `docs/context.md:59` traced by hand. Every HTML comment untouched. |
| `docs/pipeline.md` | §1.1, new §1.9 | node events only | **Done.** §1.9 is new: the node declaration, the sink, how a `TokenEvent` relates to a `NodeEvent`, and that a node with an `output_schema` streams JSON fragments. §1.1 gained the two refusals. |
| `docs/trajectory-format.md` | §4.1, §4.1.3, §5.2 | `0.12`; two error classes | **Done.** `0.13`, the `stream` object with its own subsection, and `suspended` as a third error class with what a reader counting failures does about it. |
| `docs/run-envelope.md` | §2 | `0.6` | **Done.** `0.7`, `stream` on a node entry, and `stream_waivers`. |
| `docs/evaluation.md` | §7.4 | nothing on streaming | **Done.** An evaluation supplies no sink, so nothing needs turning off and a streaming pipeline is measured making the same requests. |
| `docs/index.md`, `README.md` | the tables | — | **Done.** One line each. |
| `CHANGELOG.md` | Unreleased | `0.12` / `0.6` | **Done.** What each break costs a project. |
| `dev-docs/design/trajectory-format-changelog.md` | — | through `0.12` | **Done.** `0.13`, what it settled, and what it cost. |
| `dev-docs/simple-agents.md` | §2.5 | "the interface is two methods" | **Drafted, approval needed.** The optional second Protocol, and that two was the count that fell out rather than the principle. |
| `dev-docs/plan.md` | §3.1 item 8e | three open questions | **Drafted, approval needed.** The settled design. |
| `dev-docs/plan.md` | §3.2.1 | four deferred entries | **Drafted, approval needed.** Two more: reasoning output is not recorded, and one client serves a whole run. Each with what 8e must not foreclose. |

**Two present-tense truths went into `docs/`, and no promise about either.** Reasoning output is
not recorded, and one model client serves a run. A builder-facing document describes the library
as released, so the forward-looking entries stay in `plan.md`.

**Not touched, and deliberately.** `docs/tools.md` owes nothing: streaming changes nothing about
what a tool is or how one replays. `docs/context.md` owes only the renumbered citation, since a
context builder runs before anything is sent and cannot tell how the response will arrive.
`docs/failure-taxonomy.md` owes nothing; no entry reads `stream`, and FT-27 reads cost, which the
waiver's `unknown` counts already express through the existing unmeasured-figure rule.

---

## 6. Existing tests that had to change

Kept apart from §2 and §3 so nothing is quietly folded into a design note. **An existing test
needing a change is a finding to report, not a test to edit.**

### 6.1 Four, all of them the format bumps landing where they should

None is a behaviour break, and nothing else in the suite needed touching.

| Test | What changed |
|---|---|
| `test_trajectory_conformance.py::test_format_version_is_declared_on_every_record` | `0.12` becomes `0.13`. |
| `test_trajectory_conformance.py::test_model_call_has_its_type_specific_fields` | `MODEL_CALL_FIELDS` gains `stream`. The check is a symmetric difference since item 8d, so it failed until `docs/trajectory-format.md` §4.1 named the field. |
| `test_run_envelope.py::test_it_names_the_trajectory_it_belongs_to` | `trajectory_format_version` is `0.13`. |
| `test_run_envelope.py::test_it_records_the_node_shape_and_the_unknown_waivers` | A manifest `nodes` entry gains `stream`. Manifest `0.7`. |

`test_packaging.py::test_the_manifest_document_lists_every_key_the_manifest_writes` also failed
and needed no test change: adding `stream_waivers` to `docs/run-envelope.md` §2 fixed it. **That
check noticed the manifest had grown before the doc pass reached it**, for the second item
running.

### 6.2 The checkpoint: none

**The whole suite passed at 770 with the seam restructured and nothing able to stream.** The sink
threaded from `Pipeline.run` through `RunContext` to `_call_model`, `call_model` rebuilt around
`_invoke` and `_replay_chunks`, `stream=` accepted on both node kinds and plumbed, and every
client still going through `complete()`. Nothing existing was touched.

The `stream` field on `model_call` was written, then **backed out to prove the checkpoint on its
own terms**, then put back as the first thing after it. It is a format change, so it belongs to
the feature rather than to the restructure, and leaving it in would have made "770 green" a
claim about a suite with a failing conformance check in it.

### 6.3 Every refusal watched to fail

Six, each disabled once and its test run:

| Disabled | Test that failed |
|---|---|
| the sink-no-node-can-reach check | `test_a_sink_no_node_can_reach_is_refused` |
| the client-cannot-stream check | `test_a_client_that_cannot_stream_is_refused` |
| the usage-missing refusal in `MistralClient.stream` | `test_a_response_with_no_usage_is_refused_by_default` |
| `_locate_missing_usage` | both run-built-message tests |
| the chunks-rebuild-content check | `test_an_adapter_whose_pieces_do_not_rebuild_its_content_is_refused` |
| `error.class` gaining `suspended` | `test_the_record_is_not_a_caller_facing_failure` |
| `PacedClient`'s conditional `stream` binding | `test_wrapping_a_client_that_cannot_stream_leaves_it_unable_to` |
| the allowance-stopped warning | `test_it_says_so_when_the_allowance_it_paces_against_stops_arriving` |
