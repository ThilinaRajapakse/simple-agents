# Stream D: adapters, pacing, cost, cassettes, the trajectory and envelope formats

Fixes for the fourteen items in the stream brief, drawn from
[`area-g-model-clients.md`](../findings/area-g-model-clients.md) G-1 and G-2,
[`area-hb-suspension-envelope.md`](../findings/area-hb-suspension-envelope.md) B-1 and B-2,
[`area-de-retrieval-memory.md`](../findings/area-de-retrieval-memory.md), and the "Statements
that look false" section of
[`claims-envelope-trajectory.md`](../inventory/claims-envelope-trajectory.md).

Files touched: `src/simple_agents/adapters/{_http,embeddings_openai}.py`,
`src/simple_agents/{pacing,manifest,cassette,cost,models}.py`, `docs/model-clients.md`,
`docs/model-clients/mistral.md`, `docs/run-envelope.md`, `docs/trajectory-format.md`,
`tests/{test_adapters,test_pacing,test_cost,test_cassette}.py`, and a new
`tests/test_manifest_totals.py`.

`redaction.py`, `trajectory.py` and `envelope.py` were read and not changed. Stream A's
`suspensions` field in `manifest.py` was not touched.

**Two exports are offered for `__init__.py`**, which this stream does not own: `held_back_ms_of`
and `note_held_back` from `models.py` (7.1). They are the seam an adapter and a wrapper use to
report a wait on a call that failed, so a project writing its own client needs them by name.
Neither is required for the library's own code to work, since both `_http.py` and `pacing.py`
import from `.models` directly.

**No format version needs bumping.** Nothing changed the shape of a record, a manifest field or
a cassette entry. `charged_cost` reports a different *value* under a device basis and the same
field with the same type; `params` on an embedding record is unchanged and was only documented.
Trajectory stays `0.21`, manifest stays `0.21`.

---

## 1. `Retry-After` lost to a longer backoff, and an HTTP-date was ignored

`_wait` took `max(backoff, retry_after)`, so a backend asking for a shorter wait was overridden
and the run waited the library's guess instead. That time is charged to `max_wall_clock_ms`.
`Retry`'s own docstring already said the header wins, so the code contradicted itself as well as
the documents.

[`_http.py` `_wait`](../../../../src/simple_agents/adapters/_http.py#L319) now replaces the backoff
with what the header names, in either direction, and
[`retry_after_seconds`](../../../../src/simple_agents/adapters/_http.py#L458) reads both forms RFC
9110 allows:

```python
retry_after_seconds("30")                              # 30.0
retry_after_seconds("Wed, 13 Aug 2026 07:28:00 GMT")   # seconds until that instant
retry_after_seconds("soon")                            # None, and the backoff stands
```

A date already past reads as `0.0` rather than as a negative sleep. `now=` is a parameter so the
date form can be tested without a clock.

**Why a module-level function rather than a method.** It is pure, it takes a header value and
returns seconds, and both `_attempt` and `_attempt_stream` reach it through `_wait`. It is in
`__all__` of a private module so the tests can import it by name rather than reaching for
`HTTPBackend._wait`.

`docs/model-clients.md` §4 said "`Retry-After` is honored where the response carries it" in two
places, which read as true and was half true. Both now say the call waits for the interval it
names *instead of* the backoff, shorter or longer, and name the two forms.

## 2. `PacedClient.waits` counted sleeps, not calls

`_wait` incremented inside its loop. With a monotonic clock and no other caller the loop runs
once, so the ordinary case was right; a wait extended by another caller's response while this
call was asleep sent it round again and counted the same call twice. The figure a project reads
to size its pacing was inflated exactly when pacing was under load, which is when it is read.

[`pacing.py` `_wait`](../../../../src/simple_agents/pacing.py#L168) counts once per call, and the
attribute's docstring says so: one call counts once however many windows it waited through.

## 3. `embeddings_openai` wrote `input_cache_read=0` for a count it did not measure

`TokenUsage`'s own docstring states the rule the adapter broke: "Where a backend reports the
prompt size but not the split, the whole prompt goes in `input_uncached` and the two cache
counts are `Unknown`." The Mistral chat adapter already does exactly that.

[`embeddings_openai.py` `_tokens_from`](../../../../src/simple_agents/adapters/embeddings_openai.py#L50)
now reads `prompt_tokens_details.cached_tokens` where the endpoint sends it and records both
cache counts as `Unknown` where it does not.

**A second bug fell out of the same read.** `embed()` batches, and it was summing only
`input_uncached` across batches and then writing fresh zeros for the rest. It now folds the
per-batch breakdowns through
[`_summed`](../../../../src/simple_agents/adapters/embeddings_openai.py#L87), where a class left
unmeasured by any batch is unmeasured for the call.

**The cost consequence, which is documented behaviour and worth stating.** An `Unknown`
`input_cache_write` with no declared cache-write rate prices the call `null`
(`docs/run-envelope.md` §4.2, and the Gemini adapter already reaches it). A project pricing an
embedding model under a `PriceBasis` declares `input_cache_write_per_mtok=0.0`, which is true for
every embeddings endpoint. `input_cache_read_per_mtok` defaults to `0.0`, so that class prices
exactly with no change from the project. The refusal message that fires here interpolated the
whole unknown object into a sentence (B-3 in the findings); it now reads "an unknown number of
tokens" and names the rate to declare.

## 4. `Manifest.restore` dropped `counts.delegation` on a resume

`to_json` reads `RECORD_TYPES` with a comment saying why; `restore` iterated a hardcoded
four-type tuple written before `delegation` existed. A resumed run's `counts.delegation` and
`counts.records` both understated, which falsifies `run-envelope.md` §2.1 and `restore`'s own
docstring.

[`manifest.py` `restore`](../../../../src/simple_agents/records/manifest.py#L455) now reads `RECORD_TYPES`
too, with the same comment. A type added to the format is carried across a resume without anyone
remembering this module.

## 5. `charged_cost` added device-seconds to money

A run under a `DeviceBasis` with a tool declaring `per_call` in USD reported
`0.387 device_seconds + 0.01 USD = 0.397` of nothing.

**Two changes, at two levels.**

[`Cost.plus`](../../../../src/simple_agents/cost.py#L187) refuses to add across units. Two figures in
different currencies now sum to unknown naming both, so a `by_model` basis mixing a `DeviceBasis`
and a `PriceBasis` reports `totals.cost` as unknown rather than as a number in neither unit.

[`Manifest._money_charged`](../../../../src/simple_agents/records/manifest.py#L276) derives what
`charged_cost` reports rather than passing the run's running total through:

| The run's basis | `charged_cost` |
|---|---|
| any basis in money | the running total, as before |
| a device basis | the tool spend alone: the device is owned, so model calls cost no money |
| a mixture of the two | `null`, because the money part of a total the two were added into cannot be recovered |

It is derived in `to_json` rather than in `set_charged_cost` so that it does not depend on the
order the two setters are called in.

**What was not changed, and why.** The addition itself happens inside
[`_call_model`](../../../../src/simple_agents/runtime/calls.py#L35), as `run.charge(cost=cost.value)`,
which hands a device-seconds figure to the same float the tool spend is added to. *(This cited
`nodes.py:2174` until 2026-08-18, which was a `stream=` argument: the line had drifted and no
symbol was named beside it, so `check_citations.py` could not see it was wrong.)* `nodes.py` is
Stream A's. Nothing is enforced against that float under a device basis, because `max_cost` is
refused against one, so the manifest was the only surface reporting it and it is now right. **If
`max_cost` ever becomes settable under a mixed `by_model` basis, the charge site has to move
too.**

`run-envelope.md` §4.1 already says device-seconds "fixes no currency for the run" while the
manifest reports `"currency": "device_seconds"`. That reads as though the field would be absent
and was left as it is, since it is the finding's "related observation, not a failure".

## 6. A redacted tool result stops a run replaying its own cassette (**decision needed**)

Reproduced live against vLLM. The run records, the tool result is stored redacted, and the
replay serves the marker where the live run had the credential. Every model call the agent makes
after that in the same conversation is keyed on different messages and misses.

**This one is not fully fixed, and the remaining half is a design decision rather than a
repair.** What the fix costs depends on which rule moves, and all three candidates are settled
statements:

1. **Key on the redacted form.** Does not work. The live run's message is redacted by *pattern*
   (`Bearer [redacted:bearer_token]`) and the replayed one carries what key-name redaction wrote
   into the tool result (`[redacted:sensitive_key]`). Two rules at two levels leave two different
   strings, so hashing the redacted form matches nothing. Normalising the markers does not help
   either: pattern redaction replaces a substring and key-name redaction replaces the whole
   value.
2. **Redact the tool result once, at the boundary, so the model is given what the file holds.**
   This makes the replay exact. It also stops a tool handing a credential to the model, which is
   arguably what should happen anyway, since a credential in a message is a credential in the
   provider's logs. It changes what a run does, and the change lives in `context.py`, which this
   stream does not own.
3. **Say the run is not replayable past that call**, which is what has been done for now.

**What landed.** [`cassette.py` `_redaction_note`](../../../../src/simple_agents/records/cassette.py#L696)
diagnoses it, so a miss that reported "recorded 129 chars, now 120 chars" and nothing else now
says which of the differences is a redaction marker, why the replay differs, and what to change.
Measured against a live vLLM agent; the message is in the report.

`run-envelope.md` §6 said "A redacted recording still replays". It now says what the system
does: the key is computed before redaction so two requests differing only in a credential are
two entries, and a redacted value that goes back into a later request stops the replay there.

**For Thilina.** Option 2 is the one that keeps the original promise. It is a behaviour change
with a security argument behind it and belongs to whoever owns `context.py`.

## 7. The two documents said opposite things about `held_back_ms`

`trajectory-format.md` §4.1 said `max_wall_clock_ms` is charged the call *without* the waiting.
`run-envelope.md` §2.1, `budget.py` and the CHANGELOG all say it *is* charged for it. The
trajectory document was not updated when the concurrency item changed the axis; it now agrees
with the other three.

### 7.1 Retry backoff on a call that fails: measured, and now counted

**Measured** with a local HTTP server answering 429 to everything, behind the real `VLLMClient`
and a real run at `Retry(max_attempts=4, initial_backoff_s=1.0)`:

```
raised after 3.0 s and 4 attempts
outcome            : error
totals.held_back_ms: 0
 record: model_call | held_back_ms: 0 | error: caller_facing
```

So the lead's 62-second run reporting `0` reproduces exactly. **A `model_call` record *is*
written for the failed call** by `_emit_failed_call_record`, with `held_back_ms` left at its
default. The figure was destroyed at the source: `HTTPBackend` knew `waited` and raised without
it, and a `PacedClient` in front lost its own wait the same way.

**What landed.** The wait now travels on the exception.
[`models.py` `note_held_back`](../../../../src/simple_agents/models.py#L74) and
[`held_back_ms_of`](../../../../src/simple_agents/models.py#L59) are the pair, in `models.py`
because this is a property of the model-client seam and both `_http.py` and `pacing.py` reach
it. `_classify` and a new `_unreachable` attach it in
[`_http.py`](../../../../src/simple_agents/adapters/_http.py#L237), and
[`pacing.py` `_waiting_reported`](../../../../src/simple_agents/pacing.py#L263) adds this client's
wait to whatever the adapter already put there. Re-measured: `exception held_back_ms attribute:
3000` where it was absent.

**What was left went to Stream A, and has landed.** `_emit_failed_call_record` in `nodes.py`
built the record and never read the figure; it now reads it at
[`nodes.py` `_emit_failed_call_record`](../../../../src/simple_agents/runtime/calls.py#L327) and puts it
on both the record and the run total. Re-measured on the same always-429 server:

```
raised after 3.0 s and 4 attempts | exception carries: 3000
totals.held_back_ms: 3000
  record: model_call | held_back_ms: 3000
```

**A second gap in the same file, reported alongside it.** The success path calls
`run.manifest.observe_held_back` and the retrieval path set `held_back_ms` on the record without
calling it, so an embedding or rerank call's wait reached its record and not the run total on a
run that completed. Stream A has taken that one too, and the line as it stands raises: see the
regression at the end of this log.

**`run-envelope.md` §2.1 was revised to match**, as this log said it would have to be. It now
says a call that exhausted its retries counts in the total, on the run its failure ended,
because the run waited and the wait is what explains its wall clock.

## 8. `run-envelope.md` §3.1 documented the old tool-call cassette key

`docs/tools.md` §3.1 was updated when the key gained `node_id` and the occurrence count moved
inside the node; this section was missed. It now names all five keyed fields, says the count
belongs to the node and why, and points at `docs/tools.md` §3.1 and §3.2 rather than at §3.

## 9. `consultation_route` was undocumented, and `tools` was documented as model-only

`_node_entries` writes both on every node entry. §2.1 read as a complete field list and did not
name `consultation_route` at all; §2.6's table put `tools` among the fields "a `deterministic`
node carries none of". A `Deterministic` node takes `tools=` and calls them through
`ctx.call_tool`, so the difference is not vacuous.

§2.6 now separates the two groups: the model-calling fields, which a deterministic node does not
carry, and the two every kind carries. §2.1's `nodes` row lists both in the right group.
Confirmed live: an `AgentNode` entry carries `tools: ['price_check']` and a `consultation_route`
key.

## 10. `PAYLOAD_FIELDS` covers `delegation` and §5.4 did not list it

A subtask's inputs and its result are dropped by sampling and the format did not say so. §5.4
now names `delegation` alongside the other three and says what its two payload fields hold.

## 11. §4.1.5's `params` spec described one shape and the format has two

Six documented keys are absent on an embedding or rerank record, and an undocumented `call_kind`
is present. Found by a coding agent building from the docs alone, which is the reader this
document exists for.

§4.1.5 now carries both shapes, and names the two other fields such a record differs on: `seed`
is `null` and `context.context_builder` is `null`. Verified against a live vLLM run with a real
`all-mpnet-base-v2` embedding call:

```
params: {'call_kind': 'embedding'} | seed: None | context_builder: None
```

**A second half of this item belongs to another stream.**
[`retrieval.md` §3, line 100](../../../../docs/retrieval.md#L100) says "A self-hosted embedding
model with no `model_revision` fails that check the same way an unpinned chat model does". That
is true of `OpenAIEmbeddings` and false of `SentenceTransformerEmbeddings`, which resolves the
commit itself and records it
([`embeddings_local.py` `_load`](../../../../src/simple_agents/adapters/embeddings_local.py#L99)).
The adapter's own docstring is correct. `docs/retrieval.md` is not this stream's file; the
suggested edit is in the report.

## 12. `decode_model_response`'s docstring was stale

It said a compute-basis cost derived from a replay is "close to zero", which was true before
`duration_ms` was stored on the entry. It now says where duration is carried and what an entry
written before that field replays as.

## 13. The vLLM concurrency default was documented inverted

`model-clients.md` §2 said `concurrent_requests` is "`None` by default, filled under
`report_concurrency=True`", and the flag defaults to `True`. §3 called reading the divisor
"opt-in" where it is opt-out. `docs/model-clients/vllm.md` §5 was already right, so the two
documents disagreed. Both statements in `model-clients.md` now match the source.

## 14. Mistral's `input_cache_write` is `0` only conditionally

`0` where the response carried `prompt_tokens_details.cached_tokens`, `Unknown` where it did
not. The comparison table and `mistral.md` §6 both stated `0` unconditionally. Both now say
which case is which, and §6 says why: with no split reported, nothing in the response says how
the prompt divided, and a zero would be a measurement.

---

## Tests

| File | What was added |
|---|---|
| `tests/test_adapters.py` | a shorter `Retry-After` beating the backoff, an HTTP-date one, `TestRetryAfterHeader` over both forms and an unreadable one, `TestEmbeddingTokenCounts` over the four cases the embeddings adapter now distinguishes, and three over what a failed call carries |
| `tests/test_pacing.py` | one call held through two windows counts as one wait, and a wait before a call that failed travels on the exception |
| `tests/test_cost.py` | two units do not add, and a `by_model` basis mixing them totals unknown |
| `tests/test_cassette.py` | a miss whose difference is a redaction marker says so, and an ordinary edit does not |
| `tests/test_manifest_totals.py` (new) | every record type survives a restore, a delegation is still counted after a stop, and the four `charged_cost` cases |

## Live verification

Against vLLM `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit` on `localhost:8002`, live Gemini
`gemini-3.1-flash-lite`, local HTTP servers for the retry work, and cassette replay for Mistral,
which is out of credits.

**The machine hardware-crashed at 16:16.** The vLLM server was restarted afterwards at revision
`84455dc68ee6574b9f43659e32588d0bf0ca3a21`, and **every vLLM row below was re-run against it**,
so the figures are post-change. The Gemini column is what the same check reported on a hosted
backend, kept because it was measured while vLLM was down and because it covers a second
backend.

| Check | Backend | Result |
|---|---|---|
| `charged_cost` under a `DeviceBasis` beside a `SPENDS_MONEY` tool | vLLM, and Gemini | `cost` 0.751 device_seconds on vLLM and 0.993 on Gemini, `tool_spend` $0.01, `charged_cost` **0.01** on both, where it was their sum before |
| an embedding record's `params` | vLLM + `all-mpnet-base-v2` | `{'call_kind': 'embedding'}`, `seed: None`, `context_builder: None`, as §4.1.5 now says |
| `nodes[].tools` and `consultation_route` on an agent node | vLLM, and Gemini | both present on both, as §2.1 and §2.6 now say |
| the redacted-replay miss message | vLLM | names the marker and the fix, on a two-turn agent |
| `Retry-After: 1` and an HTTP-date, over a real socket, against a 30s backoff | local server | waited 1.0s and 1.2s, where the backoff would have been 30 |
| a rate-limited run that never got an answer | local server | 3.0s waited over 4 attempts, `held_back_ms` **3000** on the exception, on the record, and in `totals` |
| token accounting and totals | Gemini | `input_cache_write` unknown with its reason, cost $0.0000067, `charged_cost` equal to it |
| the whole adapter surface | Mistral, by cassette replay | `tests/test_adapter_integration.py`, 82 passed |

**The embedding row was read twice.** The first reading came out of a run that then died on a
regression in `nodes.py`, `run.manifest.observe_held_back(record.held_back_ms)` against a
`Record`, which is `class Record(dict[str, Any])`
([`trajectory.py` `Record`](../../../../src/simple_agents/records/trajectory.py#L158)) and raises
`AttributeError`. Stream A landed that line and then fixed it while this log was being written.
The check was re-run against the fixed tree and the run completes.

## Closed since this log was first written

- **7.1's two lines landed** in `nodes.py`, and the item is complete end to end: a run
  rate-limited for 3.0s now reports `totals.held_back_ms: 3000` and carries `3000` on its
  `model_call` record, where both read `0`. `docs/run-envelope.md` §2.1's sentence was revised
  to match, as this log said it would have to be.
- **`docs/run-envelope.md` §2.1's `suspensions` row** now says one entry per node that stopped,
  with an entry each where overlapping arms stopped together and every open entry closed by a
  resume, which is what Stream A's H-5 fix makes it.

## What the lead has to carry

1. **`docs/retrieval.md` §3, one sentence**, at item 11 above. Not this stream's file.
2. **`scripts/check_citations.py --fix`** over `dev-docs/`, once every stream has stopped
   moving code. Three anchors in `plan.md` point into files this stream shifted. This log is
   already clean.

Both escalations, B-1 at item 6 and the `retrieval.md` sentence, are with Thilina and the lead
rather than open here.
