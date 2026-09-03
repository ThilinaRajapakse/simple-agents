# Model clients

How a run reaches a model. Three adapters ship, and a project can supply its own without modifying the library.

| | Covers |
|---|---|
| [`docs/model-clients/mistral.md`](model-clients/mistral.md) | `MistralClient`: the constructor, declaring prices, prompt caching, the published rate-limit allowance, and what the backend does not report |
| [`docs/model-clients/gemini.md`](model-clients/gemini.md) | `GeminiClient`: pinning a model, declaring prices including the rate a call cannot be priced without, prompt caching, running an evaluation against a backend that publishes no allowance, and the thought signature a tool call is refused without |
| [`docs/model-clients/vllm.md`](model-clients/vllm.md) | `VLLMClient`: the serve command and what each flag decides, pinning the revision, per-call settings through `extra`, and reading serving concurrency |

---

## 1. The seam

`ModelClient` is a Protocol with two methods:

```python
def complete(self, request: ModelRequest) -> ModelResponse: ...
def identity(self) -> ModelIdentity: ...
```

`identity` reports which model the adapter calls, before any call is made. The manifest records it as `models.configured`, which is one of the pins FT-14 reads, and the cassette key includes it, so replaying after a model change finds no entry rather than serving the previous model's responses.

**One client serves every node, unless a node declares its own.** `Pipeline.run(model=client)` is the run's client; `LLMNode(..., model=client)` and `AgentNode(..., model=client)` override it for that node, which is how a cheap model runs a reduction step and a strong one the answer (`docs/pipeline.md` §2.4). A run holding clients for two backends needs a cost basis per model (`docs/run-envelope.md` §4.1), and pacing is per client, so two clients against one hosted account each hold their own view of the allowance.

Three rules govern what belongs in the common surface:

- **Normalised** is what the library reads or what a caller needs by name: the call signature, the model identity, the five-field token breakdown, finish reason, concurrency, content, tool calls, and the remaining rate-limit allowance.
- **Passed through** is everything else, in both directions. Per-call settings travel out in `ModelRequest.extra`, which the library does not inspect and the adapter forwards unchanged; whatever the backend sent alongside its response comes back in `ModelResponse.provider`, as the adapter received it. Fixed settings go in an adapter's constructor.
- **Nothing is emulated.** A backend that cannot do something raises a caller-facing error naming the backend and the feature. A field it does not report is `None`, and a token count it did not report is `Unknown(reason=...)`, so a figure derived from it is marked unmeasured.

Every failure inside an adapter is caller-facing, and raised rather than returned to the model as data.

## 2. Choosing a backend

Rows describing what a provider does, rather than what the adapter fills in, can go stale. Verify those against the provider's documentation.

| | `MistralClient` | `GeminiClient` | `VLLMClient` |
|---|---|---|---|
| `backend` | `hosted_api` | `hosted_api` | `self_hosted` |
| Cost basis | `PriceBasis` | `PriceBasis` | `ComputeBasis` |
| `model_revision` | `None`, the provider exposes none | the build string passed to the constructor | the SHA passed to the constructor |
| Prompt caching | opt-in, per `prompt_cache_key` | automatic, no opt-in | automatic, no opt-in |
| `input_cache_write` | `0` where the response carried a cached-token count, `unknown` where it did not | `unknown`, the provider counts no such class and bills its storage by the hour | reported as `created_cache_tokens` |
| `concurrent_requests` | `None`, not applicable | `None`, not applicable | read off the server by default, `None` under `report_concurrency=False`, see `docs/model-clients/vllm.md` §5 |
| Credentials | `MISTRAL_API_KEY` | `GEMINI_API_KEY` | none, unless the server sets one |
| Published rate-limit allowance | five headers on a non-streamed response | none, on any response | none |
| Token usage on a streamed response | reported, with or without `stream_options` | reported on every chunk, cumulative | reported, with `stream_options.include_usage` |
| Prompt-token split on a streamed response | `cached_tokens` reported | `cachedContentTokenCount` reported | survives, under `--enable-prompt-tokens-details` |
| Rate-limit allowance on a streamed response | **none**, where a non-streamed response carries five headers | none either way | none either way |
| Tool calls on a streamed response | fragments joined by `index` | whole, in one chunk | fragments joined by `index`, under `--tool-call-parser hermes` |
| Reasoning reported separately | **none**, on every model the API serves | `thought` parts, asked for by default | `reasoning`, under `--reasoning-parser` |
| Suppressing reasoning | not available, `reasoning=False` is refused | `reasoning=False` sets the thinking budget to zero | `reasoning=False` sets the chat template's switch |
| State a later request must return | none | a thought signature per tool call, on `ToolCallRequest.provider` | none |

The four streaming rows were measured against Mistral and vLLM on 2026-08-04 and against
Gemini on 2026-08-12, the two reasoning rows on 2026-08-05 and 2026-08-12.

## 3. Concurrency and compute cost

Under a compute basis a call is charged `duration × device_count ÷ concurrent_requests × hourly_rate ÷ 3600`. No backend reports concurrency on the response, so `concurrent_requests` is `None`, the whole device is charged to each call, and the derived figure is flagged as an upper bound rather than presented as a cost.

For a self-hosted server the real divisor is available separately, at one local request per call. `VLLMClient` reads it unless `report_concurrency=False` turns it off, and `docs/model-clients/vllm.md` §5 covers what the reading is.

Because concurrency drifts across a call's lifetime under continuous batching, a single integer describes an instant and the cost derived from it is an estimate rather than an exact figure. An adapter for a backend that can report a time-weighted average over the call records that instead.

## 4. Retries and pacing

```python
MistralClient(model="mistral-small-2603", retry=Retry(max_attempts=5))
```

408, 429, 500, 502, 503 and 504 are retried, as is a connection that failed to open. Where the response carries `Retry-After`, in either the seconds form or the HTTP-date form, the call waits for the interval it names instead of the backoff, whether that is longer or shorter. Otherwise the backoff doubles. Anything else raises immediately with the backend's own message.

Retries happen inside one call, so the trajectory records one `model_call` whose duration covers every attempt. Under a compute basis the charge covers the whole duration, retries included.

**The remaining allowance is on the response.** `ModelResponse.rate_limit` carries
`remaining_requests`, `remaining_tokens` and `resets_in_s`, filled from whichever of them the
backend published, and is `None` on a backend that publishes none. Pace a batch against that
figure rather than an average of what previous calls consumed, which on an agent loop predicts
poorly: a question's spend grows with every turn it takes. `docs/model-clients/mistral.md` §5 covers what that backend publishes.

```python
response = client.complete(request)
if (left := response.rate_limit) and left.remaining_tokens is not None:
    if left.remaining_tokens < estimated_next_prompt:
        time.sleep(left.resets_in_s or 60)
```

**`PacedClient` is that loop, available in the library.** It wraps an adapter, delegates `identity()` unchanged, reads the allowance off each response, and holds the next call back when the window will not carry it:

```python
from simple_agents import MistralClient, PacedClient

client = PacedClient(MistralClient(model="mistral-small-2603"))
results = suite.run(envelope=env, model=client, split="held_out", k=5, concurrency=4)
```

A wait can be long: `max_wait_s` caps one at 65 seconds by default, which covers a per-minute window. `max_wall_clock_ms` is elapsed time while the run is executing, so the wait is charged to it, and a run behind a busy quota can stop on that axis having made few calls. `totals.held_back_ms` is what separates that from a run that was doing work slowly (`docs/pipeline.md` §5).

Every caller sharing the client waits for the same instant, so parallel rollouts pause once rather than once each. A backend that publishes no allowance leaves it a passthrough, and wrapping an adapter that declares it publishes none warns as the wrapper is built. Gemini is one (`docs/model-clients/gemini.md` §5).

**The two floors are what decide when a call waits.** `min_remaining_requests` is the request count at or below which the next call waits; left unset it is the number of callers sharing the client, and `EvalSuite.run` sets that from its concurrency. A window reporting one request left will carry one call, and the other three of four rollouts in flight come back rate limited. `min_remaining_tokens` is the same for tokens, and left unset it is the largest number of tokens any single call has used so far, so the floor grows to fit the work rather than being guessed at.

```python
client = PacedClient(MistralClient(model="mistral-small-2603"))
client.expect_callers(4)     # what EvalSuite.run does with its concurrency
client.request_floor         # 4
```

**A client that does not pace warns, once.** The first call held back against a hosted backend says so and names `PacedClient`. That wait is retry backoff after the backend refused the call, and the shipped defaults (`max_attempts=6`, `initial_backoff_s=1.0`, `max_backoff_s=60.0`) total 31 seconds, which covers a brief spike and not a per-minute window that has been exhausted. Each call backs off on its own, so parallel rollouts wake into the same closed window. A rate-limited call reports no token counts, so enough of them leave the run's cost `unknown`, and `totals.cost.measured` is what the calls that did report came to (`docs/run-envelope.md` §4.2).

**`Retry-After` replaces the backoff, up to `max_backoff_s`.** A backend naming when its window reopens knows better than a doubling guess, in both directions. The cap is there because a budget is checked between steps and not inside a call, so a header naming an hour would hold one call for an hour with nothing able to interrupt it; a builder who wants to wait that long raises `max_backoff_s`.

**A 429 against a spent allowance is not retried at all.** Where the backend's message says the allowance resets on a scale a retry window cannot reach, the run raises `Suspend` on the first refusal instead of climbing the ladder. The run writes its state, the process ends, and `Pipeline.resume` continues it once the allowance is back. `waiting_for` carries the backend's own message, and `resume_not_before` is unset, because a backend that says the cap is reached does not say when it lifts and a guessed date would refuse a resume that would have worked.

Only messages that have been observed are matched, and a backend phrasing it differently falls through to the ladder. A quota the backend does not announce is still the project's to predict, and a wrapper is how: it raises `Suspend` before the call rather than after the refusal, which is the only way to stop before spending anything at all. Nothing new is needed at this seam, because a `Suspend` raised from a client travels the way one raised from a tool does.

```python
class StopsWhenTheQuotaIsGone:
    def __init__(self, inner: ModelClient, monthly_tokens: int) -> None:
        self.inner = inner
        self.monthly_tokens = monthly_tokens
        if hasattr(inner, "stream"):
            self.stream = self._stream        # §6 covers why this is bound here

    def identity(self) -> ModelIdentity:
        return self.inner.identity()

    def complete(self, request: ModelRequest) -> ModelResponse:
        self._stop_if_spent()
        return self.inner.complete(request)

    def _stream(self, request: ModelRequest, on_chunk) -> ModelResponse:
        self._stop_if_spent()
        return self.inner.stream(request, on_chunk)

    def _stop_if_spent(self) -> None:
        if self.spent_this_month() >= self.monthly_tokens:
            raise Suspend(waiting_for="monthly token quota",
                          resume_not_before=self.resets_at)
```

A run stopped inside a fan-out keeps the items it had finished, and continues an item that was part-way through from what it was holding, which matters here: the reason it stopped was that tokens had run out. `docs/pipeline.md` §1.8 covers the rest.

## 5. Streaming

A node declares that its output may be delivered as it is produced; the run supplies where it goes.

```python
answer = LLMNode(reply, output_schema=Answer, stream=True)

pipeline.run(inputs, envelope=env, model=client,
             on_token=lambda event: sys.stdout.write(event.text))
```

`on_token` receives a `TokenEvent` carrying `node_id`, `node_kind`, `call_index`, `text`, and `item_index` inside a fan-out. `docs/pipeline.md` §1.9 covers the callback and how it relates to `on_progress`.

**Passing `on_token` is what turns streaming on.** A run given none makes ordinary calls whatever a node declares, so an evaluation of a streaming pipeline sends what a non-streaming one sends and its recordings are interchangeable. Declaring it on one node and not another is what confines the effects below to the calls that asked for them.

**Two refusals, both before the run starts.** `on_token` with no node declaring `stream=True` is refused, since the callback could never fire. A declaring node run against a client with no `stream` method is refused by name, rather than served an unstreamed call.

§2 carries what each backend delivers on a streamed response. Two of those rows change what a run can do. §5.1 covers a backend that reports no usage on a stream. Pacing a streamed call against an allowance the backend stops publishing is in `docs/model-clients/mistral.md` §5.

**A node with an `output_schema` streams fragments of JSON**, which is what a model emits under constrained decoding. Rendering that to an end user shows them the schema.

### 5.1 A stream with no token counts

Where a backend reports no usage on a streamed response, the call is refused and the message names both ways out:

```python
client = MistralClient(model="mistral-small-2603", stream_without_usage=True)
```

With the waiver, every count on a streamed call is `unknown` rather than a number, the reason travels onto each record, and the manifest's `stream_waivers` names the client. `max_tokens` then charges nothing for those calls; `max_steps` still counts them, so the run stays bounded. Without it, dropping `stream=True` from the node makes the call through `complete` and counts it in full.

### 5.2 What a run records

A streamed `model_call` carries `stream`, holding `chunks` and `first_chunk_ms`, which is time to first token. A call that did not stream records `null`. `docs/trajectory-format.md` §4.1.3 defines both.

A cassette entry stores where the chunks fell, so a replay hands the callback the same pieces the recording did, with no delay between them and the recorded latency on the record. An entry recorded without streaming replays as one piece. Streaming is not part of the cassette key, so a recording made while streaming replays into a run that does not, and the other way round.

**A stream interrupted part-way cannot be taken back.** A `Suspend` raised from a client mid-stream leaves the delivered text with the end user, and the resumed run makes the call again from the beginning. The record says how far the first attempt got, and its `error.class` is `suspended` rather than a failure.

**Retries cover the connection and the status, which arrive before any chunk.** Once a chunk has been delivered the request is not retried, since a second attempt would repeat text the end user has seen. A stream that breaks part-way raises, naming how many events arrived.

## 6. Reasoning output

A model may produce a chain of thought before its answer. Where the backend reports the two
separately, the call's `model_call` record carries it on `outputs.reasoning`, holding `text` and
`blocks`; `docs/trajectory-format.md` §4.1.4 defines both. Where the backend does not separate
them, the chain of thought is part of `content` and this field is `null`.

**Reasoning is charged as output tokens either way.** A call whose `tokens.output` far exceeds
the length of its `content` is explained by this field. On a backend that does not separate the
two, nothing in the record explains it.

`Pipeline.run(on_reasoning=...)` delivers it as it arrives, on its own channel:

```python
pipeline.run(inputs, envelope=env, model=client,
             on_token=lambda e: sys.stdout.write(e.text),
             on_reasoning=lambda e: status.update(e.text))
```

Both take a `TokenEvent`, whose `kind` is `"content"` or `"reasoning"`. The two are
independent, and a node still declares `stream=True` for either to fire. A reasoning model can
send its whole chain of thought before its first word of answer, so a display given only
`on_token` shows nothing for that period; `stream.first_chunk_ms` measures the first piece of
content, which on such a model is the moment the answer begins.

**An `AgentNode` gives the model its own reasoning back.** The assistant turn the loop appends
carries it, and each adapter decides what its backend accepts. This matters within a turn the
model is still working on: a chat template that renders prior reasoning is given it, and one
that ignores the field is unaffected.

### 6.1 Turning it off

`reasoning=False` on an adapter stops the model producing a chain of thought, where the backend
offers a way:

```python
VLLMClient(model="Qwen/Qwen3-8B", model_revision="<sha>", reasoning=False)
```

The default keeps whatever the model produces. An adapter whose backend offers no such setting
refuses the argument at construction rather than accepting a control that reads as applied and
changes nothing; `MistralClient` is that case today.

**Suppressing the chain of thought is not the same as not being sent it.** A backend may
generate one, bill it as output tokens, and withhold it from the response. The library never
asks for that: reasoning that was paid for is recorded.

## 7. Writing an adapter

Implement the two methods, fill every field of `ModelResponse` from what the backend reported, and take backend-specific configuration in the constructor.

**A client that answers from a script declares `scripted = True`.** `FakeModelClient` does, so a run made with it records `scripted` on its manifest and is left out of `runs()`, of `simple-agents report` and of the conformance checks unless they are asked for it. A project's own stand-in declares the same attribute and is treated the same way:

```python
class FromTheFixtures:
    scripted = True

    def identity(self) -> ModelIdentity: ...
    def complete(self, request: ModelRequest) -> ModelResponse: ...
```

One project wrote 1,846 calls through a stand-in into the same `runs/` directory as its real ones. Its report counted them as spend and read 318 of their fan-out items as work that produced nothing, beside the real import. A run is marked where every model it could call is scripted; one that could reach a stand-in and a backend called a backend, so it spent what it spent and is not marked. `FakeModelClient(scripted=False)` says a run is meant to be read back as an ordinary one, which is what a test of a project's own reporting wants.

**A third method is optional.** `stream(request, on_chunk) -> ModelResponse` delivers content as it arrives and returns the same assembled response `complete` returns, so nothing downstream reads a different shape. The pieces passed to `on_chunk` must join to the response's `content` exactly, which the library checks; anything else produces a recording whose chunk boundaries index into text a replay does not have. An adapter without the method is a complete model client, and a node asking to stream against it is refused by name rather than quietly served.

**A keyword on that method is optional too.** `stream(request, on_chunk, *, on_reasoning=None)` takes the chain of thought on its own sink, whose pieces must join to `response.reasoning.text` on the same rule. The library passes it only to a `stream` whose signature accepts it, so an adapter written with two parameters keeps working and is refused by name only when a run asks for `on_reasoning=`.

**Fill `ModelResponse.reasoning` where the backend reports one separately**, with `text` for the chain of thought and `blocks` for anything the backend needs returned verbatim on a later request, such as a signature over the text or an opaque payload. `text` is `None` where only an opaque payload arrived. `content` keeps the chain of thought where the backend returns it inline: the markers are model-specific, and a wrong split rewrites the string an output schema is validated against.

An adapter also translates an assistant turn's `reasoning` into what its backend accepts, or drops it where the backend has no field for it. `messages_to_wire(messages, reasoning_field=...)` is how the shipped adapters do it.

A wrapper standing in front of an adapter delegates `stream` the way it delegates `complete`, and offers it, and its reasoning sink, only where the wrapped client has one.

**Translate the conversation, not only the tool declarations.** An `AgentNode` appends what the model asked for as `{"id": ..., "name": ..., "arguments": {...}}`, which is the library's shape rather than any backend's. An adapter that forwards `request.messages` unchanged works for an `LLMNode`, which sends one message and never sees a tool call, and fails on the second turn of an `AgentNode`. The shipped adapters translate in `messages_to_wire`.

**Return the state a backend sends with a tool call.** Some backends attach a value to each tool call and refuse the following request without it, such as Gemini's thought signature. It arrives on `ToolCallRequest.provider`, and an adapter fills it from the response and returns it unchanged when it translates the conversation. `messages_to_wire` has no field for it, because the OpenAI dialect has none: it refuses a call carrying `provider` rather than sending a turn the backend will reject. An adapter for a backend that sends such state translates the conversation itself, the way `_gemini_wire.contents_from` returns a signature as `thoughtSignature`. `docs/model-clients/gemini.md` §6 is the worked case, and the comparison table in §2 says which of the three shipped backends sends any.

**Raise `ContextOverflow` when the backend refuses the request as too long**, rather than a
general error. Every shipped backend answers 400 with a message naming the context length, and
that is what the shipped adapters match on. A backend whose refusal cannot be told apart from any
other 400 raises the general error, and the caller still gets the backend's own message.

A count the backend did not report is `Unknown(reason=...)`, never `0`. A figure derived from an assumed concurrency, a zero token count or a guessed revision reads as measured when it was not.

```python
class MyClient:
    def identity(self) -> ModelIdentity:
        return ModelIdentity(backend="hosted_api", request_model=self.model)

    def complete(self, request: ModelRequest) -> ModelResponse:
        ...
```
