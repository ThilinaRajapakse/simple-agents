# Build log — a Gemini adapter

**Built 2026-08-12.** Third built-in model client, second hosted backend. `runs/dogfood-protocol.md` is the
outcome; `plan.md` §2.2's adapter entry is what it half closes.

---

## 1. What was measured before anything was written

Nothing here is taken from the provider's SDK types or from memory. Every figure is from the
model list, the published pricing page, or a live call made from this machine on 2026-08-12.

### 1.1 The model

The cheapest model on the pricing page is not callable by this key.

| Model | in $/Mtok | out $/Mtok | cached in | tools + schema |
|---|---|---|---|---|
| `gemini-2.5-flash-lite` | **0.10** | **0.40** | 0.01 | **404** |
| `gemini-3.1-flash-lite` | **0.25** | **1.50** | 0.025 | yes |
| `gemini-3.5-flash-lite` | 0.30 | 2.50 | 0.03 | yes |
| `gemini-3-flash-preview` | 0.50 | 3.00 | 0.05 | yes |
| `gemini-3.6-flash` | 1.50 | 7.50 | 0.15 | yes |

`gemini-2.5-flash-lite` and `gemini-2.5-flash` are both in the listing `GET /v1beta/models`
returns for this account, and both answer every call with
`404: This model is no longer available to new users`, on `v1beta`, on `v1` and on the
OpenAI-compatible path. **The listing describes the catalogue and the call describes the
account**, which is now stated in `docs/model-clients/gemini.md` §2 because a builder reading a
model list has no other way to learn it.

So the pick is **`gemini-3.1-flash-lite`**, the cheapest that answers, at 0.25 / 1.50 / 0.025
with cache storage at 1.00 per million tokens per hour. It served a `functionCall` from a
`functionDeclarations` request and filled a nested schema through `responseJsonSchema`.

**There is no dated snapshot to pin.** `gemini-3.1-flash-lite-05-2026` is 404; that string is
the `version` field on the model list, metadata rather than an identifier. It goes in
`model_revision` the way vLLM's SHA does: recorded, not verified, and FT-14 judges it.

### 1.2 The fork, and why the shared module could not serve it

`plan.md` §2.2 said "Anthropic and Gemini each need a sibling of `_openai_wire.py`: neither
speaks that dialect". **The premise is wrong and the conclusion is right.** Google serves that
dialect at `/v1beta/openai/chat/completions`, and it works: tools, `tool_choice`,
`response_format` with a nested schema, and a multi-turn tool result all answered 200.

Three measurements decided it anyway.

**The seed is refused.** `400: Invalid JSON payload received. Unknown name "seed"`. Every
rollout derives a seed, the cassette key includes it, and every record carries it. An adapter
on that endpoint drops the field the run is keyed by.

**Thinking tokens are billed and not itemised.** One call at `reasoning_effort=high`:

| | prompt | completion | total |
|---|---|---|---|
| OpenAI-compatible | 43 | 327 | 1489 |
| native, same prompt | 43 | 327 candidates + **1119 thoughts** | 1489 |

1,119 of 1,446 output tokens are invisible on that path, as a low number rather than as
`unknown`. That is FT-27 reached by a route no test would catch, since the arithmetic is
internally consistent.

**The chain of thought is not returned there at all.** The native API returns it as a
`thought: true` part, which is what `ModelResponse.reasoning` exists for.

**And neither endpoint can serve an `AgentNode` through `messages_to_wire`.** Each
`functionCall` arrives with a `thoughtSignature`, and the following request is refused without
it:

```
400: Function call is missing a thought_signature in functionCall parts.
     This is required for tools to work correctly.
```

`messages_to_wire` rebuilds an assistant turn as `{id, type, function}` and the signature is
gone, so the second turn of every agent loop would fail. This reproduces on both endpoints, so
reuse was never the cheap option it looked like. It is item 5's finding again: a conversation
shape no backend accepts, invisible to `FakeModelClient`.

Thilina chose the native path on this evidence.

### 1.3 What else the probes settled

- **Caching needs no opt-in**, and a hit is reported as `cachedContentTokenCount`. A
  6,129-token prompt repeated reported 4,076 cached, with nothing configured. It survives
  streaming: the same body streamed and unstreamed reported the same 4,076.
- **No response carries a rate-limit header.** 30 concurrent calls in 1.4s, no 429, nothing to
  pace against. The provider's rate-limit page directs to its own console rather than
  publishing per-model figures. `PacedClient` in front of this adapter is a passthrough, and
  `concurrency` is what bounds an evaluation.
- **A bad key answers 400**, not 401, with `API key not valid`.
- **Over-length answers 400** with `input token count exceeds the maximum number of tokens
  allowed`, which is a phrase `_http.OVERFLOW_PHRASES` did not hold.
- **`$defs` and `$ref` are refused by `parameters` and by `responseSchema`**, and accepted by
  `parametersJsonSchema` and `responseJsonSchema`. Every schema the library derives from a
  model carries them, so the newer fields are the only ones that work.
- **Thinking is opt-in per model.** `gemini-3.1-flash-lite` reported no thinking tokens at its
  defaults; `gemini-3-flash-preview` reported 165 on the same prompt, and `thinkingBudget: 0`
  took it to none. `thinkingLevel: "off"` and `"none"` are both 400.
- **A streamed tool call arrives whole**, in one chunk, rather than as fragments joined by
  index. Usage is on every chunk and cumulative.

`scripts/probe_gemini_wire.py` captures all of it into `tests/fixtures/wire/gemini/`,
including the two refusals that carry the argument: `openai_seed_refused.json` and
`error_missing_signature.json`.

---

## 2. What shipped

- **`adapters/_gemini_wire.py`** — the dialect: `contents` and parts, `functionDeclarations`,
  `generationConfig`, `usageMetadata`, and a stream assembler over whole-body chunks. Nothing
  is shared with `_openai_wire`; the two agree on no field.
- **`adapters/gemini.py`** — `GeminiClient`, exported from `simple_agents`. The key travels in
  `x-goog-api-key` rather than the query string, so it stays out of any URL a refusal quotes.
- **`ToolCallRequest.provider`**, and the trajectory format at `0.20`. §3 is the cost.
- **`docs/model-clients/gemini.md`**, a row in `docs/index.md`, a third column in
  `docs/model-clients.md` §2, and the `docs/trajectory-format.md` §4.1.4 entry for `provider`.
- **Five recording arms** — `gemini`, `agent-gemini`, `tools-gemini`, `eval-gemini` and
  `stream-gemini` — and their cassettes.

### 2.1 Three decisions taken inside the build

**`extra` merges into `generationConfig` rather than replacing it.** Both other adapters put
`extra` at the top level of the body, and most of this backend's per-call knobs live under
`generationConfig`. A top-level update would let `extra={"generationConfig": {"topK": 5}}`
delete the seed and the output schema, which is a footgun with no signal. Everything else in
`extra` still reaches the body untouched.

**Reasoning is asked for by default.** `simple-agents.md` §2.5 says reasoning that was paid for
is recorded and the library never asks a backend to withhold it, so the request carries
`includeThoughts: true`. `reasoning=False` sets `thinkingBudget: 0`, measured to work on a
model that thinks and to be accepted by one that does not.

**`finish_reason` is passed through as the backend's own string.** This one answers `STOP` for
a turn of tool calls, with `finishMessage: "Model generated function call(s)."` beside it.
Nothing in the library compares the value, and both other adapters pass theirs through, so
normalising here would invent a vocabulary no reader asked for.

---

## 3. What the library had to gain, and what that cost

### 3.1 `ToolCallRequest.provider`, and format `0.20`

The signature is per function-call part, and the library had nowhere to put it: the loop
carries `reasoning.text` into the assistant turn and drops `Reasoning.blocks`, and a tool call
is `{id, name, arguments}` everywhere it travels.

Three options went to Thilina. An adapter-private map keyed by tool-call id needs no format
change and breaks on resume, because a second process rebuilds the conversation from
`suspension.json` with an empty map. Carrying `Reasoning.blocks` through the loop costs the
same bump and puts a per-call value on a per-turn field. **He took the opaque field.**

**The key is absent where the backend sent none.** That is what kept the bump cheap: a
conversation built from either OpenAI-dialect adapter is byte-identical to one built before the
field existed, so no cassette key over a message list moved and nothing had to be re-recorded.
`ToolCallRequest.to_record` and `from_record` are the one pair every site now goes through:
the assistant turn, the `model_call` record, the cassette entry, and the suspension state's
`pending` and `remaining`.

### 3.2 Two defects the adapter found in code that predates it

**A cassette could not replay an unmeasured token count.** `decode_model_response` rebuilt
every count with `tokens.get(name, 0)`, so an `Unknown` came back as a plain mapping and the
first sum over the counts raised `TypeError: unsupported operand type(s) for +: 'int' and
'dict'`. It was unreachable until now: vLLM only reports an unknown count without
`--enable-prompt-tokens-details`, and no cassette had been recorded that way. Gemini writes one
on every call.

**An adapter given `http_client=` sent no credentials.** `HTTPBackend` applied its headers only
to the client it built itself, and `docs/model-clients.md` documents supplying one for a proxy
or a custom transport. Such a client went out unauthenticated. Found by writing a test that
asserts the key is in a header rather than in the URL, which is a thing worth asserting only
because this adapter authenticates that way.

Neither is Gemini's. Both are what a third backend exercising a different corner of the same
code turns up.

### 3.3 The cost change, which the first live run forced

The first live `AgentNode` run answered correctly and reported **no cost at all**. Every call
prices as `null` when any count is `unknown`, and `input_cache_write` is `unknown` on every
Gemini call: the provider counts no such class and bills its storage per token-hour rather than
per token written.

Reporting `0` for the count instead, as `MistralClient` does, was available and is not honest
here. Mistral has no cache-write class at all; this backend writes to a cache and does not say
how much. **What changed is the arithmetic, not the count**: an unmeasured count whose rate is
declared `0.0` contributes zero, because no value of it changes the total. Every other
unmeasured count still leaves the call unpriced.

Without it a builder on this backend has a `max_cost` that can never fire, which is the FT-18
failure §2.3's amendments exist to prevent, reached by a third route. The rate has to be
declared for the exemption to apply, so a basis that omits it still refuses loudly and names
the field.

---

## 4. Verified live

Against `gemini-3.1-flash-lite`, on 2026-08-12. A green suite over a fake client is what
`CLAUDE.md` warns about, and the first live run is what found §3.3.

| Run | What it exercised | Result | Cost |
|---|---|---|---|
| `gemini` | one `LLMNode`, schema-constrained | `answer='Paris'` | $0.000037 |
| `agent-gemini` | `AgentNode`, one tool, 3 turns | `retailer='Kirkwall'` | $0.000622 |
| `tools-gemini` | `document_search`, `extract_facts`, `workspace_write`, `now` | ran to `finish` | $0.001620 |
| `eval-gemini` | 9 rollouts over 3 examples, k=3, two nodes | accuracy 1.0 | $0.003972 |
| `stream-gemini` | one node streaming, one not | 2 chunks, rebuilt exactly | $0.000132 |

**$0.006383 in all**, over 18,670 input and 1,142 output tokens. The probes before it cost
about $0.02 more.

**What the live runs showed that the fixtures could not.** The signature round trip works
across three turns of a real loop, and it is in the recorded requests rather than only in the
responses: `test_the_signature_went_back_on_the_following_request` reads the conversation the
backend was sent out of the cassette. The evaluation ran unpaced by choice, since there is no
allowance to pace against, and finished 9 rollouts with no 429.

**One thing the evaluation surfaced that is not about this backend.** The unpaced-client
warning named `PacedClient(MistralClient(model='mistral-small-2603'))` as the fix, hard-coded,
whichever client was in use. It now names the client it was given, and says that a backend
publishing no allowance leaves the wrapper a passthrough.

---

## 5. What is left open

- **`input_cache_write` still has no number from any backend.** `plan.md` §2.2 expects a
  third hosted backend to be the first exercise of that class, and this one is not it: it
  reports no count, and the class it bills is storage per token-hour. What it does exercise is
  the honest-`unknown` path and the zero-rate exemption.
- **`Reasoning.blocks` is still filled by nothing.** This backend's opaque state belongs to the
  tool call rather than to the chain of thought, so it went to `ToolCallRequest.provider`
  instead. `simple-agents.md` §2.5's note that `blocks` is to be measured against Anthropic and
  OpenAI stands unchanged.
- **`gemini-3.1-pro-preview` answers this key**, which is how the account was established to be
  on a paid tier. Nothing in the library reads a tier, and the free tier's limits are not
  published per model, so the rate-limit allowance stays a thing this backend does not report
  rather than a thing the adapter could estimate.
- **Streaming is covered by fixtures and by one captured stream, not by a recorded pipeline
  run.** `stream-gemini` has no recording arm. The two shipped backends each have one.
