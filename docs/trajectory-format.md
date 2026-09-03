# Trajectory format

The trajectory is the record a run writes, and this is its schema. Evaluation, ablation, conformance checks, regression detection, and later SFT and RL read it.

---

## 1. What a trajectory is

### 1.1 JSONL, append-only, flat

One JSON object per line. Records are appended as execution proceeds, so a run that crashes halfway leaves a readable partial trajectory. A run whose envelope samples its payloads is rewritten once when it closes, to drop them (§5.4). A run that crashed is not rewritten and keeps them.

### 1.2 Seven record types, linked by id

Records are flat, of seven types, and linked by `parent_id`.

| `record_type` | Emitted | Parent |
|---|---|---|
| `run_start` | Once per run, before the first node | none |
| `node_execution` | Once per node execution. Every node kind | the `delegation` it ran inside, else none |
| `model_call` | Once per model API call | the `node_execution`, or the `tool_call` it was made inside |
| `tool_call` | Once per tool invocation | the `node_execution` |
| `consultation` | Once per consult of the end user | the `node_execution` |
| `delegation` | Once per subtask a model sent to a delegated pipeline | the `node_execution` |
| `resource_access` | Once per access a node's own code recorded to a resource it declared | the `node_execution` |

A `Deterministic` node emits exactly one record. An `LLMNode` emits a `node_execution` plus one `model_call`. An `AgentNode` emits a `node_execution` plus as many `model_call`, `tool_call` and `delegation` records as its loop performs, so each step inside the loop is separately visible. Per-node metrics (FT-08) and ablation (FT-12) both read those steps.

Every node execution emits one `node_execution` record whatever the node's kind. The kind is the `node_kind` field on that record rather than a separate record type, so the seven record types and the three node kinds are different lists. Five of the rest are things a node does: call a model, call a tool, ask the end user, hand a subtask to a pipeline, and reach a resource in its own code. `run_start` is the one that is not: it belongs to the run and says what the run was given.

Nesting children inside their parent would make a single record unbounded in size and would break line-at-a-time streaming and `wc -l`-style inspection. `parent_id` costs one field and preserves both.

**What it looks like.** One `LLMNode` that made a single model call, abridged. The field tables in §2 to §5 define everything shown:

```jsonl
{"format_version":"0.30","record_type":"node_execution","record_id":"r1","run_id":"run_7","parent_id":null,"sequence":1,"node_id":"extract_inseam","node_kind":"llm","seed":41,"inputs":{...},"outputs":{"inseam_cm":{"type":"unknown","reason":"not published"}},"budget":{"max_steps":1,"max_tokens":8000,"max_cost":null,"max_wall_clock_ms":30000},"termination":null,"route":[],"loop":null,"started_at":"2026-07-26T09:14:02.118Z","ended_at":"2026-07-26T09:14:04.902Z","error":null,"redactions":[],"omissions":[]}
{"format_version":"0.30","record_type":"model_call","record_id":"r2","run_id":"run_7","parent_id":"r1","sequence":2,"backend":"self_hosted","request_model":"Qwen/Qwen3-8B","model_revision":"a1b2c3d","response_model":"Qwen/Qwen3-8B","params":{...},"seed":41,"inputs":{...},"outputs":{...},"finish_reason":"end_turn","tokens":{"input_uncached":1200,"input_cache_read":8400,"input_cache_write":0,"cache_ttl":null,"output":512},"concurrent_requests":4,"replayed":false,"cassette_key":"ck_9f2","context":{"context_builder":"AppendAll","dropped":[],"estimate":null},"recorded_duration_ms":null,"held_back_ms":0,"rate_limit":null,"provider":{},"stream":null,"item_index":null,"started_at":"2026-07-26T09:14:02.140Z","ended_at":"2026-07-26T09:14:04.880Z","error":null,"redactions":[],"omissions":[]}
```

Absent from the example: cost, total input tokens, and duration. All three are derived (§6).

---

### 1.3 The record a run writes first

`run_start` carries what `Pipeline.run` was passed, and is written before the first node runs.

| Field | Type | Always | Notes |
|---|---|---|---|
| `inputs` | any | ✅ | What the run was given. A payload, so §5.3 and §5.4 apply to it. |
| `seed` | integer \| null | ✅ | The seed the run derived every other seed from. |

`parent_id` and `ended_at` are `null`: nothing contains a run, and the record describes a start rather than a span. The common fields of §2 are on it like any other record.

**It is written at the start, and that is the point of it.** Every other record is written when the thing it describes finishes. A `node_execution` record lands when its node returns, so a run whose process ended inside its first node recorded what it was given nowhere. An out-of-memory kill, a container eviction and a deploy restart all produce that run.

**The bytes are written twice.** The first node receives the run's inputs, so its own record holds them too, a median 4.2% of a trajectory file measured across 400 runs of one project. That is what it costs for a run's inputs to be on disk whatever happens to the process.

`Pipeline.rerun(run_dir, envelope=...)` reads this record and runs again what the dead run was given, serving its recorded calls from that run's own cassette (`docs/pipeline.md` §1.13).

---

## 2. Common fields

These fields are on all seven record types. Every record carries `format_version`, so a single line found on disk says how to interpret it. **Current version: `0.30`.**

| Field | Type | Required | Notes |
|---|---|---|---|
| `format_version` | string | ✅ | `"0.30"`. Present on every record so a single line is interpretable in isolation. |
| `record_type` | enum | ✅ | `node_execution` / `model_call` / `tool_call` / `consultation` / `delegation` |
| `record_id` | string | ✅ | Unique within the run. |
| `run_id` | string | ✅ | Identifies the run. Joins to the manifest. |
| `parent_id` | string \| null | ✅ | The record this happened inside: the `node_execution` for a call the node made itself, the `tool_call` for a model call made inside a tool, the `delegation` for a node execution inside a delegated pipeline. `null` on a `node_execution` the pipeline reached along an edge. |
| `sequence` | integer | ✅ | Monotonic within the run, in emission order. |
| `started_at` | string | ✅ | ISO 8601, UTC, millisecond precision. |
| `ended_at` | string \| null | ✅ | Same. `null` if the record was written for an operation that never completed. |
| `error` | object \| null | ✅ | See §5.2. |
| `redactions` | array | ✅ | Field paths redacted on the record path. Empty array when none. See §5.3. |
| `omissions` | array | ✅ | Field paths this run did not keep. Empty array when none. See §5.4. |

**Records are appended in `sequence` order, so a trajectory read line by line is already in order.** A reader that sorts or merges records sorts on `sequence`. Two tool calls inside one `AgentNode` can carry the same `started_at`, and a clock adjusted mid-run can stamp a later record earlier, so a sort by timestamp can invert the order records were written.

**`sequence` says which record was written first, not which thing happened first.** In a run whose work overlaps (`docs/pipeline.md` §1.10) the records of two nodes running at the same time interleave, and which interleaving a run produces is not reproducible. What is reproducible is the set of records and what each one holds. `parent_id` is what says where a record belongs: a record is resolved to its node by following `parent_id` up, never by its position in the file, and a parent is still written after everything that happened inside it, so a child's `sequence` is still lower than its parent's.

**A parent is written after its children, so a child's `sequence` is lower.** A `node_execution` record is emitted once everything inside it has finished, and a `tool_call` that contained a model call is emitted the same way. Reading a trajectory by `sequence` gives the order things happened, not the order they were entered.

**`ended_at` is `null` on an operation that never finished**, whether it crashed or a budget stopped it. The field is always present, so `null` says the operation did not finish rather than that the writer omitted it. FT-18 and debugging both read it.

---

## 3. Record type: `node_execution`

| Field | Type | Required | Notes |
|---|---|---|---|
| `node_id` | string | ✅ | Stable identifier of the node in the pipeline. Joins per-node metrics across runs. |
| `node_kind` | enum | ✅ | `deterministic` / `llm` / `agent` |
| `inputs` | object | ✅ | What the node received. Two shapes are tagged, and both are described in §3.2. |
| `outputs` | object \| null | ✅ | What it produced. `null` when it errored before producing anything, and on a node that was skipped. A node that fanned out over a sequence records `items`, one entry per input item in input order, and `kept` where it declared `keep=`; see §3.4. |
| `seed` | integer \| null | ✅ | The seed governing this node's sampling. `null` on `deterministic` nodes only. |
| `budget` | object | ✅ | The budget in force. See §3.1. |
| `termination` | enum \| null | ✅ | Why the node stopped: `finish` / `finish_rejected` / `max_steps` / `max_tokens` / `max_cost` / `max_wall_clock` / `error` / `skipped` / `max_iterations` / `suspended`. `error`, `skipped` and `suspended` apply to any node kind. `null` on a node of any kind that completed normally. |
| `route` | array | ✅ | The successors this execution handed its output to. Empty on the node the run returns from, on a skipped node, and on a failed attempt that had nowhere to send the failure. |
| `loop` | object \| null | ✅ | Which iteration of a bounded cycle this execution was, and `null` for a node in no cycle. See §3.3. |
| `resumed_from` | string \| null | ✅ | The `record_id` of the execution this one continues, on a run that stopped inside the node and was resumed. `null` otherwise. Both records describe one logical execution, so counting executions of a node means counting the ones where this is `null`. |

**The seed on a `node_execution` record and the seed on a `model_call` record are different numbers.** The node carries the run seed, which governs every call the node makes. Each `model_call` carries the seed actually sent to the backend, derived from the run seed, the node id, and the index of the call within the node. One run seed therefore reconstructs every call seed in the run, and two calls made from the same node do not sample identically.

**`seed` is always present, and `null` means the node does not sample.** A `deterministic` node records `null`, and every other kind records the run seed. FT-07 reads this field, and a missing one would leave "no seed applies" and "seed not recorded" indistinguishable.

**`termination` says why a node stopped, as one of ten values.** An agent loop ends on a `finish` tool call, on a rejected `finish`, on one of four budget axes, or on an error. A node of any kind can end on an error, or never run at all and record `skipped`. A node closing a bounded cycle records `max_iterations` when the cycle ran out and the node had no reason of its own. A node the run stopped inside records `suspended`, and the execution that continues it names that record in `resumed_from`. So "why did this run stop" is a query over a trajectory rather than a read of it.

**A node that knows why it stopped keeps its own reason.** An `agent` node closing a cycle records `finish`, not `max_iterations`, because its loop did finish. `loop.exhausted` is what says the cycle ran out, on every node kind, so a reader asking that question reads one field and never has to know which kind closed the cycle.

**A skipped node emits a record.** Nothing reached it, so its function never ran and it made no calls, and `outputs` is `null`. The record is what separates a node that ran and produced nothing from one no path reached, which is the difference `reach` counts in `docs/evaluation.md` §5.

**`route` makes the path a run took readable.** Each execution names the successors it handed its output to, so the path is read from the trajectory. The declared graph is in the manifest (`docs/run-envelope.md` §2): the manifest says what was possible and the trajectory says what happened.

### 3.1 The `budget` object

```json
{"max_steps": 12, "max_tokens": 100000, "max_cost": null, "max_wall_clock_ms": 300000}
```

All four keys are always present; `null` means unbounded on that axis. Recording the budget in force, rather than only recording violations, is what lets a reader tell a run that finished early from a run that was never constrained. `docs/pipeline.md` §5 covers setting one.

### 3.2 What `inputs` holds

Most of the time `inputs` is whatever the previous node returned. Two shapes are tagged, so a reader tells them from a node that happened to return a mapping.

**A node with more than one edge into it** records a key per declared in-edge, and names the ones that did not fire:

```json
{"type": "join",
 "edges": {"hunt": {"answer": "Kirkwall"},
           "verify": {"type": "unknown", "reason": "'hunt' routed to 'report'"}},
 "absent": ["verify"]}
```

`absent` is what separates an edge that never fired from a node whose own answer was that the value is not there. Both appear in `edges` as an `unknown` object, and only the first is listed in `absent`.

**A node reached through an error edge** records what failed:

```json
{"type": "node_failure", "node_id": "lookup", "attempts": 2,
 "error": {"class": "caller_facing", "type": "RuntimeError",
           "message": "the index is unreachable", "retryable": false}}
```

`attempts` is how many executions were made before the failure was final, which is one more than the retries. The failed node's own records are in the trajectory too, each carrying `termination: "error"`.

### 3.3 The `loop` object

```json
{"node_id": "critique", "iteration": 3, "max_iterations": 3, "exhausted": true}
```

`null` for a node in no cycle. `node_id` names the node carrying the `Loop`, which matters where one cycle is nested inside another and a node belongs to both: the object describes the innermost.

**`iteration` counts per entry to the cycle, so it is not the number of records this node wrote.** A cycle entered twice, three iterations each time, writes six records numbered 1, 2, 3, 1, 2, 3. Counting records gives the executions; this field gives the iteration.

`exhausted` is true only on the execution where the count was reached, on the node carrying the `Loop`. That execution's `route` is the `Loop`'s `then`.

### 3.4 What a fan-out records

A node that ran once per item in a sequence records one entry per input item, in input order:

```json
{"items": [{"index": 0, "value": {"summary": "..."}},
           {"index": 1, "error": {"class": "caller_facing", "type": "ValidationError",
                                  "message": "...", "retryable": false}},
           {"index": 2, "value": {"summary": {"type": "unknown", "reason": "not stated"}}}]}
```

An entry carries `value` or `error` and never both. An item whose value is `unknown` is a success: the model answered, and the answer was that the information is not there. An item with an `error` produced no answer at all. Conflating the two would make a broken call read as a correct report of absence (FT-09, FT-10).

Every item is present whether it succeeded or not, so an entry's position in `items` is its position in the input sequence.

An entry carries `termination` where the node kind decides for itself why an item stopped, which today is an `AgentNode` fanning out. It is absent on an item that ran to the end of its own work, which is every item of a fan-out that makes one call:

```json
{"items": [{"index": 0, "value": {"retailer": "Northgate"}, "termination": "finish"},
           {"index": 1, "value": {"retailer": "Kirkwall"}, "termination": "max_steps"}]}
```

An item that stopped on a budget axis is a success carrying whatever it had, on the same rule as a node that did.

A node that declared `keep=` records what it carried past the fan-out under `kept`, keyed by the input key it came from:

```json
{"items": [{"index": 0, "value": {"summary": "..."}}],
 "kept": {"question": "which retailers publish a chest measurement?"}}
```

`kept` is absent on a node that declared no `keep=`. What it holds is a copy of a value in the previous node's `outputs`, so a reader can follow it back to where it was produced.

---

## 4. Record types: `model_call`, `tool_call`, `consultation`, `delegation`, `resource_access`

### 4.1 `model_call`

| Field | Type | Required | Notes |
|---|---|---|---|
| `backend` | enum | ✅ | `hosted_api` / `self_hosted`. Determines how the model identity fields are read and which cost basis applies (`docs/run-envelope.md` §4). |
| `request_model` | string | ✅ | The fully-qualified model identifier requested. Under `self_hosted`, the hub repo ID. |
| `model_revision` | string \| null | ✅ | The exact revision the weights came from: a commit SHA for hub-hosted weights. `null` under `hosted_api`, where no provider exposes one. |
| `response_model` | string \| null | ✅ | The model that actually served the response. |
| `params` | object | ✅ | Configuration as sent: `seed`, `max_output_tokens`, `temperature`, the `extra` passthrough, and `tools_ref` and `output_schema_ref`. See §4.1.5. |
| `seed` | integer \| null | ✅ | The seed sent to the backend for this call, derived from the run seed, the node id and the index of the call within the node (`docs/run-envelope.md` §5). `null` when the call was sent no seed. |
| `inputs` | object | ✅ | The rendered request: `messages`, and `assembly` where this call was built from a prompt. See §4.1.6. |
| `outputs` | object \| null | ✅ | The response: `content`, `tool_calls`, and `reasoning`. See §4.1.4. |
| `finish_reason` | string \| null | ✅ | Provider-reported reason the generation stopped. |
| `tokens` | object | ✅ | See §4.1.2. |
| `concurrent_requests` | integer \| null | ✅ | Requests the serving backend had in flight alongside this one. Required to attribute compute-basis cost (`docs/run-envelope.md` §4). `null` under `hosted_api`, and under `self_hosted` when the backend does not report it. |
| `replayed` | boolean | ✅ | `true` if served from a cassette rather than called. |
| `cassette_key` | string \| null | ✅ | Replay key. `null` on a live call made with no cassette in force. Keyed as `docs/run-envelope.md` §3 defines. |
| `context` | object | ✅ | Which context builder produced `inputs.messages`, and what it left out. See §4.1.1. |
| `recorded_duration_ms` | integer \| null | ✅ | How long the live call took, carried over from the cassette when this call was replayed. `null` on a live call, whose duration comes from `started_at` and `ended_at`. Compute-basis cost charges this on a replay (`docs/run-envelope.md` §4). |
| `held_back_ms` | integer | ✅ | How long this call waited before the attempt the backend answered, from an adapter's retry backoff and from a `PacedClient`. The timestamps bracket the whole call, so this is what separates waiting from working within it. The waiting is elapsed time and `max_wall_clock_ms` is charged for it, so comparing this against the call's duration is what separates a throttled call from a slow one (`docs/pipeline.md` §5). `0` where nothing waited. |
| `rate_limit` | object \| null | ✅ | What the backend said was left of the current window: `remaining_requests`, `remaining_tokens`, `resets_in_s`. `null` where the backend reports no allowance. |
| `provider` | object | ✅ | What the backend sent alongside the response, less any header the adapter already parsed into `rate_limit`. `{}` where it sent nothing. Redacted like every other recorded value. |
| `stream` | object \| null | ✅ | How the response was delivered, on a call that streamed. `null` on a call that did not. See §4.1.3. |
| `item_index` | integer \| null | ✅ | Which item of a fan-out this call belongs to, counting from zero, and `null` outside one. A fan-out's items share one `parent_id` and can overlap, so this is what attributes a call to an item. `params.seed` is derived from it and from the call's position within the item, so an item is sent the same seed whatever order the items ran in. A call made underneath a node carries its item too: one a tool made, a consultation reader's, and a search's embedding or rerank. |

**`request_model` and `response_model` can differ.** A provider-side fallback or substitution serves a different model than the one asked for, so a run pinned to one identifier can be answered by another. FT-14 reads both, which is what makes a substitution visible after the fact, and answers a class of "why did the numbers move" question from the trajectory alone. `response_model` is `null` only when the call produced no response.

**`backend` says how strong the pin is.** A dated hosted-model string is the provider's promise that the identifier keeps resolving to the same weights. A commit SHA in `model_revision` is a record of which weights ran, and is available under `self_hosted` only. `backend` also says which cost basis applies, and that under `self_hosted` nothing in the path could reroute the call, so `response_model` equals `request_model`.

**`finish_reason` is the provider's own string rather than an enum.** A provider can add a value at any time, so a reader treats an unrecognized value as unrecognized rather than as an error.

#### 4.1.1 The `context` object

```json
{"context_builder": "AppendAll", "dropped": [], "estimate": null}
```

```json
{"context_builder": "AppendAll", "dropped": [],
 "estimate": {"input_tokens": 186400, "limit": 200000,
              "chars_per_token": 3.9, "measured_on_call": 3}}
```

```json
{"context_builder": "DropOldestTurns",
 "dropped": [{"index": 3, "role": "tool", "reason": "older than keep_turns"}],
 "estimate": null}
```

| Field | Type | Notes |
|---|---|---|
| `context_builder` | string | The context builder's type name, supplied by the library rather than by the context builder. |
| `dropped` | array | One entry per message left out, each with its `index` in the list the context builder was handed, its `role`, and its stated `reason`. Empty when everything was sent. |
| `estimate` | object \| null | Present when a pre-flight token limit was configured and a previous call in that node measured a prompt size. `null` otherwise. |

**`dropped` is empty rather than absent when everything was sent.** A record with no `context` object would leave a context builder that dropped nothing indistinguishable from one that dropped without recording it, and FT-17 reads this array.

**`estimate` names its own basis.** No backend counts a prompt that has not been sent, so a
pre-flight check against a token limit converts from characters. `chars_per_token` is the
ratio the call named in `measured_on_call` exhibited, so a reader can tell an estimate from a
count and can see what produced it. `docs/context.md` §2 states which quantities are
measurable.

#### 4.1.6 The `assembly` object

How the prompt behind this call was built (`docs/prompts.md`). Present on the call a prompt
function produced, absent where the messages are a conversation, which is every turn of an
`AgentNode` loop after the first. `inputs` is a payload field, so redaction applies and sampling
replaces the whole of it.

| Field | Type | Required | Notes |
|---|---|---|---|
| `messages` | array | ✅ | One entry per message, in order. |
| `templates` | array | ✅ | A digest of each distinct piece of fixed text this prompt was built from, sorted. Two calls that sent the same instruction record the same digest whatever data filled it. |

Each entry in `messages` carries `role`, and then either the fixed text and its values, or what
was carried:

| Field | Type | Notes |
|---|---|---|
| `template` | string | The fixed text, with `{name}` where each value went. |
| `values` | array | One entry per value: `name`, `chars`, `capped_from` where a `cap` cut it, and `origin` where the prompt declared one. A value built from a section carries that section's own `template` and `values`. |
| `parts` | integer | On a section built from a list: how many. `each` carries the text they share, where they share one. |
| `blocks` | array | On a message whose content is not text: the text blocks as above, and `kind` for every other block. |
| `carried` | boolean | `true` on a message carried in with `Prompt.turns`, which the project did not write. |
| `extra` | array | The names of any backend fields set on the message, such as a cache marker. |

#### 4.1.2 The `tokens` object

```json
{
  "input_uncached": 1200,
  "input_cache_read": 8400,
  "input_cache_write": 0,
  "cache_ttl": null,
  "output": 512
}
```

| Field | Meaning |
|---|---|
| `input_uncached` | Prompt tokens processed at full price. |
| `input_cache_read` | Prompt tokens served from cache. |
| `input_cache_write` | Prompt tokens written to cache this call. |
| `cache_ttl` | The cache TTL in force, or `null` when no caching was used. |
| `output` | Generated tokens. |

**`input_uncached` is not the prompt size.** Provider APIs commonly report the uncached remainder under a name like "input tokens". Total prompt tokens are `input_uncached + input_cache_read + input_cache_write`, the three are disjoint, and a token is counted once under the class it was processed as. On a workload with a large cached prefix, the uncached figure alone can be a small fraction of the prompt.

**The total is not stored.** A reader that needs it adds the three, and adds them only when all three are numbers. Storing a value derivable from three others leaves two copies to drift with no way to tell which is authoritative, which is the rule everywhere in this format.

**When a backend reports the prompt size but not the split**, the adapter records the whole prompt in `input_uncached`, and `input_cache_read` and `input_cache_write` as `unknown` (§5.1) naming what was unavailable. The total is then still recoverable and the cached share is not, which is what the backend said. A reader that meets an `unknown` sums the numbers it has and treats the rest as unmeasured.

**Under `self_hosted`, `input_cache_read` counts prompt tokens vLLM served from its prefix cache.** A cached prefix shortens the call, and a compute basis charges duration, so the saving appears there rather than in a per-token rate. `cache_ttl` is `null`. A backend that does not report cached prefix tokens leaves `input_cache_read` as `unknown` rather than `0`; `docs/model-clients/vllm.md` §2 covers which vLLM flag decides that.

#### 4.1.3 The `stream` object

```json
{"chunks": 42, "first_chunk_ms": 180, "reasoning_chunks": 599}
```

| Field | Type | Meaning |
|---|---|---|
| `chunks` | integer | How many pieces the content arrived in. |
| `first_chunk_ms` | integer \| null | Milliseconds from the request being sent to the first piece of content arriving. `null` where the call delivered no content. |
| `reasoning_chunks` | integer | How many pieces the chain of thought arrived in. `0` where the call produced none, or where the run supplied no `on_reasoning`. |

**`stream` is `null` on a call that did not stream**, which is every call made by a node that does not declare `stream=True` and every call made by a run given no `on_token`. `docs/model-clients.md` §5 covers both.

**`first_chunk_ms` measures the first piece of content, not the first piece of anything.** `started_at` and `ended_at` bracket the whole call, so nothing else in the format says when output began arriving, which is the figure streaming is adopted for. A reasoning model sends its chain of thought first, so on one of those this figure is time to first word of the answer and the gap before it is time the backend spent thinking.

**On a replayed call both figures are what the recording measured**, carried from the cassette rather than measured here, the way `recorded_duration_ms` is. `replayed` says which. A response recorded without streaming has no boundaries to replay, so a run that streams it records `stream: null` and its sink receives the content in one piece rather than in invented ones.

#### 4.1.4 The `outputs` object

```json
{"content": "22 inches", "tool_calls": [], "reasoning": {"text": "The shelf is 32...", "blocks": []}}
```

| Field | Type | Meaning |
|---|---|---|
| `content` | string \| null | The answer. `null` where the model returned only tool calls. |
| `tool_calls` | array | What the model asked to call, each `{id, name, arguments}`, and `provider` where the backend sent state with the call. |
| `reasoning` | object \| null | The chain of thought, where the backend reported one separately from the answer. `null` where it reported none. |

**`provider` on a tool call is state the backend sent with it and requires back on the next request**, in the backend's own shape. The key is absent where the backend sent none, which is every call to an OpenAI-dialect backend. `GeminiClient` fills it with the thought signature that backend refuses the following turn without, so a run resumed in another process rebuilds a conversation that backend still accepts (`docs/model-clients/gemini.md` §6).

`reasoning` carries `text`, the chain of thought as text, and `blocks`, whatever the backend sent in its own shape for an adapter to return on a later request. `text` is `null` where a backend sent only an opaque payload, and `blocks` is `[]` where it sent only text.

**A backend reporting no reasoning and a model producing none are the same record.** Both write `null`. Whether a backend separates the two is a property of that backend and, for a self-hosted server, of how it was started: `docs/model-clients/vllm.md` §2 covers what decides it. Where the chain of thought is not separated it is part of `content`, and this field is `null`.

**Reasoning is charged as output tokens either way.** A call whose `tokens.output` far exceeds the length of its `content` is explained by this field, and on a backend that does not separate the two there is nothing in the record that explains it.

#### 4.1.5 The `params` object

Configuration as sent, so its keys are the ones the call had. A chat completion carries the sampling parameters and the two references:

```json
{"seed": 41, "max_output_tokens": null, "temperature": 0.0, "extra": {},
 "tools_ref": "sha256:0a1b2c3d4e5f6789", "output_schema_ref": "sha256:9f8e7d6c5b4a3210"}
```

An embedding or a reranking call carries `call_kind` and nothing else, because it takes no sampling parameters, offers no tools and asks for no output schema:

```json
{"call_kind": "embedding"}
```

`call_kind` is `embedding` or `rerank`, and is absent on a chat completion. It is what separates the calls a search made from the calls the agent made, which are `model_call` records alike (`docs/retrieval.md` §6). Those calls also record `seed: null` on the record itself and `context.context_builder` of `null`.

`tools_ref` names the tool declarations the request offered and `output_schema_ref` the schema it asked the model to fill. Both are `null` on a call that offered neither. The blocks themselves are in the manifest under `schemas`, keyed by the same reference (`docs/run-envelope.md` §2.7).

**A tool's description is prompt text the model reads, so the offered set is part of what the model was choosing between (FT-12).** The set is the same on every call a node makes, and a five-turn agent node offering four tools writes the same block five times. The reference says which set was offered, and two calls offered different tools carry different references. Reading the descriptions means opening the manifest beside the trajectory.

**The cassette key hashes the declarations in full, not the reference.** A replay keyed on a hash of a hash would still be correct, and a key that omitted the set would serve a response recorded against other tools. `docs/run-envelope.md` §3.1 defines the key.

### 4.2 `tool_call`

**A `tool_call` carries no `node_id`.** Only `node_execution` does. To attribute a tool call to a node, join `parent_id` to the `node_execution`'s `record_id`, which is the same join for `model_call` and `consultation`:

```python
records = [json.loads(line) for line in open("runs/run_7/trajectory.jsonl")]
nodes = {r["record_id"]: r["node_id"] for r in records if r["record_type"] == "node_execution"}
calls = [(nodes[r["parent_id"]], r["tool_name"]) for r in records if r["record_type"] == "tool_call"]
```

Filtering `tool_call` records by `node_id` returns an empty list rather than an error, so a reader that gets this wrong reads it as the node having made no tool calls. `read_trajectory` says the same thing in its docstring, for a project using it rather than reading the file directly. A model call made inside a tool has that `tool_call` as its parent, so it takes two hops to reach the node.

| Field | Type | Required | Notes |
|---|---|---|---|
| `tool_name` | string | ✅ | As registered. |
| `tool_version` | string \| null | ✅ | Version of the tool implementation, when the registry tracks one. |
| `side_effect_class` | enum | ✅ | `read_only` / `writes` / `spends_money` / `irreversible`, as declared by the tool's author. |
| `inputs` | object | ✅ | Arguments as passed. |
| `outputs` | object \| null | ✅ | Return value. `null` only on error. |
| `replayed` | boolean | ✅ | `true` if served from a cassette rather than executed. |
| `re_executed` | boolean | ✅ | `true` for a tool the cassette does not store, which runs again during a replay. See `docs/tools.md` §3.2. |
| `cassette_key` | string \| null | ✅ | Replay key. `null` on a re-executed call, which has none. |
| `declared_cost` | object \| null | ✅ | The tool's declared cost and latency, as declared, not measured. All three keys present: `currency`, `per_call`, `latency_ms`. |
| `spent` | object \| null | ✅ | What this call cost. `null` where it cost nothing. Three keys when present: `currency`, `amount`, `source`. |
| `item_index` | integer \| null | ✅ | Which item of a fan-out this call was made for, counting from zero, and `null` outside one. A fan-out's items share one `parent_id` and can overlap, so this is what attributes a call to an item. |

A tool declares a price whether or not a given call pays it, so `declared_cost` appears on every call the tool made and `spent` only on the ones that bought something. A call served from a cassette, a call that failed, and a call a cache answered all carry the declaration and `spent: null`. Sum `spent` for what a run's tools cost; summing `declared_cost` counts calls that never reached a vendor.

`source` is `declared` where the figure is the tool's `per_call` and `measured` where the tool reported what the vendor charged. A tool that takes a `SpendMeter` and reports its own declared price says `declared`, which the shipped `web_search` does: the meter is what lets a cache hit report nothing, and the amount is still the declaration.

**`side_effect_class` and `declared_cost` are the declarations in force during the run.** The registry holds the current ones. FT-20 asks whether a tool reaching outside the run executed inside a rollout, which is a question about a past run, so re-declaring a tool later does not change what an old trajectory says happened (`docs/tools.md` §1.4).

**`replayed`, `re_executed` and `cassette_key` say three different things.** A key can be present on a live call that was recorded *into* a cassette, so a key does not mean the call was served from one. A tool taking a `ModelHandle` or a `Workspace` is not stored and runs again during a replay, recording `re_executed: true`, `replayed: false` and no key, inside a fully replayed run (`docs/tools.md` §3.2). FT-21 reads all three to decide whether an evaluation ran offline. `model_call` carries `replayed` and `cassette_key` with the same meanings.

### 4.3 `consultation`

Emitted when the agent asks the end user something mid-run: a preference, a disambiguation, an authorisation it cannot derive. A consultation is a designed interaction the builder plans for. Elicitation is the separate exchange at build time between the coding agent and the builder, and it lands in the brief.

| Field | Type | Required | Notes |
|---|---|---|---|
| `prompt` | string | ✅ | What the agent asked. |
| `options` | array \| null | ✅ | Offered choices, when the consultation was a selection rather than open-ended. |
| `response` | object \| null | ✅ | The end user's answer. `null` if unanswered. |
| `chose` | string \| null | ✅ | The offered option the answer was, read by the tool's own rule. `null` where the answer was none of them, and on a question offering none. |
| `declared_choice` | string \| null | ✅ | The offered option the channel itself said its answer was. `null` for a channel that cannot say, which is every channel reaching a person. |
| `read_by` | enum \| null | ✅ | What decided `chose`: `rule` for the tool's own matching over the text, `model` for a reader registered with `consult(read=...)`. `null` on a question offering no options, and on an unanswered consultation. |
| `resolution` | enum | ✅ | `pending` / `answered` / `unmatched` / `declined` / `unavailable` / `shelved` |
| `asked` | boolean | ✅ | Whether the channel was reached for this question. `false` where an earlier `unavailable` in the same run answered it from the memo without the channel seeing it. |
| `about` | string \| null | ✅ | The stable name the caller gave the subject, from `consult(about=...)`. `null` where none was given. |
| `answered_at` | string \| null | ✅ | When the person gave this answer, from `Reply(answered_at=...)`, for a channel serving an answer it stored earlier. `null` where they answered during the call. |
| `answered_by` | enum \| null | ✅ | Who the channel says answers: `end_user` / `builder` / `coding_agent` / `simulated` / `canned` / `nobody`. `null` only where the run predates the field. |
| `reaches` | string \| null | ✅ | Which answerer the tool asks, from `consult(reaches=...)`. `null` where the pipeline asks one person. |
| `reason` | string \| null | ✅ | Why nobody could be asked, from `Unavailable(reason=...)`, or where a shelved question went, from `Shelved(reason=...)`. `null` on every other resolution. |
| `answered_by_model` | object \| null | ✅ | The model that wrote the answer, with its `tokens` and derived `cost`. `null` where a person answered and where a replay served the answer. |
| `blocking` | boolean | ✅ | Whether the run halted awaiting the answer. `false` where the run suspended instead. |
| `answers` | string \| null | ✅ | The `record_id` of the question this record answers, on an answer that arrived in a later process. `null` on a question. |
| `answers_run_id` | string \| null | ✅ | The `run_id` the question it answers was asked in, where that was another run. `null` on a question, and on an answer a resume wrote, since a resume continues the run that asked. |
| `item_index` | integer \| null | ✅ | Which item of a fan-out this question was asked was for, counting from zero, and `null` outside one. |

**`resolution` says what happened and `response` says what was said.** A `null` response covers four outcomes: answered with nothing, declined, no answerer available, and the question having been shelved for somebody to answer later. `resolution` is what tells them apart. `shelved` is asked-and-outstanding: the question reached a person, the answer may arrive after the run has ended, and it never silences a later question in the run. Nothing in the conformance suite reads it; `per_node.consultation_resolutions` in a results file is what reports it (`docs/evaluation.md` §5).

**`answered_by` says who, and `resolution` alone does not.** A channel returning a fixed string, a coding agent answering during an unattended run, a model playing the end user in an evaluation, and a real person all produce `answered`, so a figure measured against none of the agent's readers reads exactly like one measured against them. `answered_by` is the channel's own declaration, made where it was registered, rather than something the library observed: it says who the project said would answer. `docs/tools.md` §4.6.2 covers the six values and which to declare. `answered_by_model` is beside it for the case a model wrote the answer, carrying what that call spent, which is charged to nothing the agent is measured on.

**`chose` routed the run and `declared_choice` did not.** `chose` is what the tool's own rule read out of the answer, which is what a `route=` branched on. `declared_choice` is the channel's own account of which option it meant, for a channel that can give one: `SimulatedEndUser` is asked for it whenever options were offered, and a channel reaching a person carries `null`. The two differing means the rule did not read that answer the way the channel meant it, and `per_node.consultation_misreadings` counts it across an evaluation (`docs/evaluation.md` §5). Whole-answer equality, which is the rule where none is passed, reads no option at all out of prose, so a project whose channel writes sentences reads that count equal to its consultations.

**`read_by` says which rule that was.** `rule` is matching over the text, either `consult(match=...)` or the default. `model` is a reader registered with `consult(read=...)`, and the call it made is a `model_call` record whose `parent_id` is this consultation, carrying the model, the tokens and the derived cost. That call is charged to the run's budget, unlike `answered_by_model`'s: a reader ships with the agent, and a stand-in playing the end user is measurement machinery. A reading that could not be made ends the run, and the record carries the answer with `chose` of `null` and the failure in `error`.

**`unavailable` is the channel reporting that it has no answerer**, and `reason` says why. `declined` is a person choosing to answer nothing, which is itself information; `unavailable` says no choice was made. The first such answer in a run is what the model is told; every later question to that tool is answered from it without the channel being reached again, and each one is recorded, so the trajectory says how many questions the run had while there was no one to ask.

**`unmatched` is an answer that was none of the offered `options`.** The end user said something and it is recorded in `response`, so it is a different event from `declined`, where they said nothing. `options` decides how an answer is read rather than what the end user may say, so the case arises whenever a question offers choices: an end user replying "make it 3 stars" to a yes-or-no question is amending rather than answering. Reading how often a run reaches it is how a project finds a question whose options were wrong.

**`asked` separates a count of records from a count of questions put to anybody.** A run whose channel reported `unavailable` answers every later question the model puts to that tool from what the first one established, without reaching the channel again, and each of those is recorded with `asked` `false` (`docs/tools.md` §4.6.3). A count of `consultation` records is therefore a count of questions asked and not of questions delivered. `answered_at` does the same for the answers: a channel serving an answer a person gave earlier sets it, so records carrying one repeated answer are distinguishable from that many answers.

**A question whose answer arrives in a later process is two records.** The first is written when the question is asked, with `resolution` `pending`, `blocking` `false`, and `response` and `ended_at` `null`. The second is written when the answer arrives, and its `answers` field names the first one's `record_id`. A run that is never resumed keeps the first, so the trajectory still says what was asked. Counting consultations means counting the records where `answers` is `null`, since the pair describes one question.

**A `consultation` record stores the end user's answer in full.** The rules in `docs/run-envelope.md` §6 match declared values, secret-carrying types and known credential formats, so a project whose end users type personal data declares patterns for it there.

### 4.4 `delegation`

Emitted when an `AgentNode`'s model hands a subtask to a pipeline declared on that node as a `Delegation`. The model chose what the subtask is and how many to send, so this record is where that choice is written down. `docs/pipeline.md` §2.5 covers declaring one.

| Field | Type | Required | Notes |
|---|---|---|---|
| `node_id` | string | ✅ | The delegated pipeline's id, prefixed by the node whose model sent the subtask. |
| `invocation` | integer | ✅ | Which subtask this was for this delegation within one execution of the calling node, counting from 1. |
| `graph_fingerprint` | string | ✅ | The shape of the pipeline that ran, so a subtask can be told from one a rewired worker answered. |
| `inputs` | object | ✅ | The subtask, as the model sent it, validated against the type the pipeline's entry node reads. |
| `outputs` | object \| null | ✅ | What the pipeline's terminal node produced. `null` where it stopped before producing anything. |
| `termination` | enum | ✅ | `completed` / `budget` / `rejected` / `suspended`. |
| `resumed_from` | string \| null | ✅ | The `record_id` of the subtask this one continues, on a run that stopped inside the delegate. `null` otherwise. |
| `item_index` | integer \| null | ✅ | Which item of a fan-out this subtask was sent was for, counting from zero, and `null` outside one. |

**A delegation carries no `side_effect_class` and no `declared_cost`.** A pipeline declares neither. What it spent is on the records its own nodes and tools wrote, each of which declares its own, and what it cost derives from those the way every other figure does.

**The node ids inside a delegated pipeline repeat across subtasks, and `parent_id` is what separates them.** Two subtasks sent to `research` both produce a `research.hunt` execution, because a node id names the node and a `record_id` names the execution. Each of those executions carries the `record_id` of the `delegation` it ran inside, so "what ran inside subtask 2" is a query rather than an inference from `sequence`. This is the same rule a node inside a bounded cycle already follows: `executions` counts them and the node id does not change.

**`termination` says how the subtask ended.** `budget` means the delegated pipeline's own budget was spent, which is returned to the model as an observation so it can send a smaller subtask or answer with what it has. `rejected` means the arguments did not satisfy the entry node's type, and the pipeline never ran. Neither ends the run; the run's own budget running out does.

**A subtask the run stopped inside is two records**, the way a consultation is. The first carries `suspended`, a `null` `outputs` and a `null` `ended_at`; the second is written when the resumed run finishes the subtask, and names the first in `resumed_from`. Counting subtasks means counting the records where `resumed_from` is `null`.

### 4.5 `resource_access`

Emitted when a node's own code calls `ctx.record_access()`. A resource reached through a tool is already a `tool_call`; this is the same account for a resource reached directly, so what a step asked for and what came back is readable from the trajectory either way. `docs/view.md` §4 covers declaring a resource and what the page draws from these.

| Field | Type | Required | Notes |
|---|---|---|---|
| `node_id` | string | ✅ | The node whose code made the access. |
| `resource` | string | ✅ | The resource name, which must be one the node declared in `touches=`. |
| `direction` | enum | ✅ | `read` / `write`. A step that does both records one access each way. |
| `inputs` | any \| null | ✅ | What was asked for. A payload field: redacted by the run's rules, dropped by sampling. |
| `outputs` | any \| null | ✅ | What came back. A payload field on the same terms. |
| `item_index` | integer \| null | ✅ | Which item of a fan-out made the access, counting from zero, and `null` outside one. |

**What `inputs` and `outputs` hold is the node's choice.** The library did not make the call, so it records what the node reports. A step that read 67,353 rows and kept 12 records `{"rows": 67353, "kept": 12}` rather than the rows:

```python
def gather(inputs, ctx):
    rows = catalogue.eligible()
    kept = rank(rows)[:12]
    ctx.record_access("catalogue", "read", inputs={"eligible": True},
                      outputs={"rows": len(rows), "kept": len(kept)})
    return kept
```

**No `side_effect_class` and no `spent`.** Both are declarations about a call the library made, and this is an observation a node volunteered. What a node's own code costs is not separable from the node, so it stays in the node's figures.

**The record says what happened; `touches=` says what was declared.** A node that declares a resource and records no access to it is a visible absence, and an access naming a resource the node did not declare is refused where the declaration is in scope, so the two always name the same thing.

**A recorded write during an evaluation is a real write.** The runner refuses non-replayable *tools* in rollouts (`docs/evaluation.md` §5), and a node writing a store in its own code is outside that guard whether or not it records. Recording makes it visible in the results rather than invisible.

---

## 5. Encoding rules

### 5.1 `unknown` is a distinct encoded value

`unknown` is a first-class return value, and it encodes as a tagged object so that it survives serialization as something distinguishable from a missing value, an empty string, and `null`.

```json
{"type": "unknown", "reason": "measurement not published on product page"}
```

`reason` may be `null`. `null`, `""`, and absence never mean `unknown`, and a sentinel string is not used because it would collide with legitimate string values. A node's `outputs` and a token count both use this encoding. `docs/pipeline.md` §4 covers `Unknown` as a value an agent returns, and where a schema has to admit it.

FT-09 and FT-10 read this encoding, which is what lets a trajectory separate "the agent said it did not know" from "the agent returned nothing".

**This is how a file stores absence, not what a reader of a value gets back.** `runs()` and an evaluation's node matcher decode it to `Unknown` wherever it sits in a node's output, so one test serves a value a node has just returned and one read out of a run (`docs/run-envelope.md` §8.1). `read_trajectory` yields records as they are here.

### 5.2 The `error` object

```json
{"class": "model_facing", "type": "SearchReturnedNothing", "message": "...", "retryable": true}
```

`class` is `model_facing`, where the model was handed the failure as an observation and continued, `caller_facing`, where infrastructure is broken and the run is invalid, or `suspended`, where the run stopped at this operation and will continue at it. `docs/tools.md` §1.3 covers which exception produces which of the first two. The class is on the record because a caller-facing failure passed to the model as data produces an agent that invents its way around a broken system, and the trajectory is where that shows up afterwards (FT-22).

**A `suspended` operation did not fail**, so a reader counting failures counts `model_facing` and `caller_facing`. It appears on a `model_call` where a model client raised `Suspend`, which is how a run waits out a token quota (`docs/pipeline.md` §1.8). The call is made again on resume, so two records describe one call: the first carries `ended_at: null`, unknown token counts, and on a streamed call the text that had already reached the end user.

### 5.3 Redaction is recorded, not silent

Redaction happens on the record path rather than as a later pass over the file, and every record carries a `redactions` array of the field paths that were altered.

```json
"redactions": ["inputs.headers.authorization"]
```

A redacted trajectory is a modified trajectory. Downstream, and especially as training data, the difference between "this field was empty" and "this field was removed" changes what the data means, so the array records which happened. `docs/run-envelope.md` §6 defines the rules that produce it.

### 5.4 A payload the run did not keep

A run that samples its payloads records the fields it dropped, rather than leaving them empty:

```json
{"inputs": {"type": "not_recorded", "reason": "sampling"},
 "outputs": {"type": "not_recorded", "reason": "sampling"},
 "omissions": ["inputs", "outputs"]}
```

`not_recorded` is a distinct value from `unknown` and from `null`. `unknown` is a value the agent produced, `null` on `outputs` says a node produced nothing or was skipped, and `not_recorded` says the run did not keep what was there. A reader counting how often a node reported an absence counts `unknown` and would count wrong if the two shared an encoding.

The payload fields are `inputs` and `outputs` on a `node_execution`, `model_call`, `tool_call` and `delegation`, and `response` on a `consultation`. A delegation's `inputs` is the subtask the model sent and its `outputs` is what came back, so both go the way a node's do. Every other field is unaffected at every rate, so counts, timings, token figures, seeds, routes, terminations and derived cost are complete on every run.

**A payload that was already `null` stays `null` and is not listed in `omissions`.** The two say different things and the sampling pass does not overwrite one with the other.

**A run that dropped its payloads has no cassette either.** The default recording holds the same requests and responses, so it is deleted with them and the manifest's `cassette.dropped` says so. A cassette the project named a path for is left alone.

`docs/run-envelope.md` §7 covers setting the rate, which runs keep their payloads, and why a run that errored keeps them whatever the rate.

### 5.5 Timestamps

ISO 8601, UTC, millisecond precision, always. No local time, no epoch integers, and no duration field derived from a record's own timestamps.

On a replayed `model_call`, `started_at` and `ended_at` describe the replay, which returns in microseconds. How long the live call took is on `recorded_duration_ms`, carried over from the cassette.

---

## 6. What is not in the format

| Not recorded | Where it comes from |
|---|---|
| Model cost | Derived from the record and the manifest's cost basis (`docs/run-envelope.md` §4). |
| Total input tokens | Derived from the three input fields (§4.1.2). |
| Duration | Derived from `started_at` and `ended_at`, except on a replayed `model_call`, which carries `recorded_duration_ms` (§5.5). |
| Prompt text templates | Versioned separately and referenced from the manifest (FT-15). Inlining them would bloat every record with identical content. |
| Tool declarations and output schemas | Stored once in the manifest's `schemas` and referenced by `params.tools_ref` and `params.output_schema_ref` (§4.1.5). |
| Model configuration defaults | The manifest's job. The trajectory records what varied. |
| Anything under `unknown` reasoning | The record carries what the agent asserted, not why it asserted it. |

**No `model_call` record carries a cost figure.** Model cost is computed at read time from `tokens`, `started_at`, `ended_at` and `concurrent_requests`, against the basis the manifest declares, so a trajectory read after a price change re-prices correctly. `docs/run-envelope.md` §4 defines the two bases, the arithmetic under each, and when a figure comes back `null` or as an upper bound. A stored figure fails FT-27.

**A `tool_call` record does carry one, in `spent` (§4.2).** What a vendor charged for a search is not a function of anything the run observed, so there is no basis to re-derive it from and the alternative is not recording it. The rate behind it is on the same record, in `declared_cost`, and a tool that reports its own charge is the source of the figure.

The trajectory records what happened and the manifest records what was configured. A value that is the same for every record in a run belongs in the manifest.

---

## 7. Exporting to other tools

Records use flat `snake_case` keys, not dotted `gen_ai.*` keys. Four fields carry the same semantics as their OpenTelemetry GenAI counterparts, so a tool reading those conventions reads them correctly:

| Field | OTel GenAI attribute | Match |
|---|---|---|
| `request_model` | `gen_ai.request.model` | Exact |
| `response_model` | `gen_ai.response.model` | Exact |
| `tokens.output` | `gen_ai.usage.output_tokens` | Exact |
| `finish_reason` | `gen_ai.response.finish_reasons` | One value per call, where the convention holds a list |

**`tokens.input_uncached` is not `gen_ai.usage.input_tokens`.** The convention's attribute means the uncached remainder on providers that report it that way, and no attribute exists for the cache split. An export that maps one onto the other silently undercounts every cached call. Export the sum of the three input fields, or nothing.

`node_kind`, `side_effect_class`, `seed` and split membership have no equivalent attributes. The record types are close in spirit to `invoke_agent`, `chat` and `execute_tool` and are not the same thing, so an export maps them rather than claiming a match.
