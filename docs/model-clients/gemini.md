# `GeminiClient`

The adapter for Gemini models from Google. `docs/model-clients.md` covers the seam every adapter implements, retries and pacing, streaming, and the comparison between the shipped backends.

---

## 1. The client

```python
from simple_agents import GeminiClient, PriceBasis, Redaction, RunEnvelope

client = GeminiClient(model="gemini-3.1-flash-lite")

env = RunEnvelope(
    run_dir="runs/",
    cost_basis=PriceBasis(
        currency="USD",
        input_uncached_per_mtok=INPUT_RATE,
        input_cache_read_per_mtok=CACHE_READ_RATE,
        input_cache_write_per_mtok=0.0,
        output_per_mtok=OUTPUT_RATE,
    ),
    redaction=Redaction(secret_env=["GEMINI_API_KEY"]),
)
```

These prices are the project's own figures. §3 covers where they come from, and why the
cache-write rate is declared as `0.0`.

`api_key` defaults to the `GEMINI_API_KEY` environment variable and is held as a `SecretStr`. It travels in a header rather than in the query string, so it stays out of any URL a refusal quotes back.

**The adapter calls the provider's own API rather than its OpenAI-compatible endpoint.**

## 2. Pinning a model

**Pin a versioned identifier.** `gemini-flash-lite-latest`, `gemini-flash-latest` and `gemini-pro-latest` resolve to different weights over time, and a response echoes back the identifier that was sent, so a run made against one cannot be attributed to specific weights afterwards (FT-14). `gemini-3.1-flash-lite` is a pin; `gemini-flash-lite-latest` is not.

**A model's build string comes from the model list, not from a response.** `GET /v1beta/models` publishes a `version` on each entry, such as `3.1-flash-lite-05-2026`. It is metadata rather than a callable identifier: a request naming it is refused with 404. Pass it to record it, and the adapter records what it is given without checking it:

```python
GeminiClient(model="gemini-3.1-flash-lite", model_revision="3.1-flash-lite-05-2026")
```

The same listing publishes the context window, as `inputTokenLimit`. A pre-flight ceiling is read off that rather than picked (`docs/context.md` §2.2).

## 3. Declaring prices

**The project declares the rates.** Prices change, and a basis that has gone stale prices an old trajectory wrongly, so the numbers live in the project rather than in the library.

**Read the current figures from the provider and record the date they were read**, next to where they are declared.

**`input_cache_write_per_mtok=0.0` is what makes a call priceable at all.** This backend bills no per-token cache-write class, and it reports no count for one either, so `tokens.input_cache_write` is `unknown` on every call. An unmeasured count normally leaves a call unpriced; a rate declared as `0.0` prices it, because no value of that count changes the total (`docs/run-envelope.md` §4.2). A basis that omits the rate reports every Gemini call as `null` cost, and `max_cost` then never fires.

**Explicit context caching is billed by the hour and lands outside the run.** The published storage price is per million tokens per hour, which no per-call token count expresses. A project that creates a cache through the provider's own API and passes `cachedContent` in `extra` pays for the storage there, and the run's derived cost covers the tokens alone.

## 4. Prompt caching

**Caching needs no opt-in.** A prompt long enough to qualify is cached, and a later call sharing its prefix reports the hit in `cachedContentTokenCount`, which the adapter records as `input_cache_read`.

`input_uncached` is the remainder, since the reported prompt count includes the cached tokens.

## 5. The allowance, and what an evaluation does without one

**No Gemini response carries a rate-limit header.** `ModelResponse.rate_limit` is `None` on every call, so there is no published allowance to pace against and `PacedClient` in front of this adapter is a passthrough, which it warns about as it is built. The provider's rate-limit page directs to its own console for the figures rather than publishing them per model.

`docs/model-clients.md` §4 covers the retry policy and what a per-minute quota does to a batch. An evaluation running rollouts at once through a client that does not pace warns. Against this backend the remedy is `concurrency` on the evaluation, since the wrapper has no allowance to read.

## 6. What this backend does not report, and what it requires back

**What this backend does not report:** a model revision, a cache-write count, a cache TTL, serving concurrency, and a rate-limit allowance. The first is whatever the constructor was given, the second is `unknown` with the reason on the record, and the rest are `None`.

**A tool call arrives with a thought signature, and the next turn is refused without it.** The provider sends an opaque string with each `functionCall`, and a following request whose function-call part carries none is answered:

```
400: Function call is missing a thought_signature in functionCall parts.
     This is required for tools to work correctly.
```

The adapter records it on `ToolCallRequest.provider` and returns it unchanged on the next request, so an `AgentNode` runs and a run resumed in another process rebuilds a conversation this backend still accepts. It reaches the trajectory as `outputs.tool_calls[].provider` (`docs/trajectory-format.md` §4.1.4).

**Reasoning is asked for by default.** A model that thinks bills those tokens as output whether or not it returns them, so the request asks for them to be returned and the adapter records them on `model_call.outputs.reasoning`. `tokens.output` includes them, which is what makes a derived cost match the bill.

```python
GeminiClient(model="gemini-3.1-flash-lite", reasoning=False)
```

`reasoning=False` stops the model producing a chain of thought. A model that does not think is unaffected by either setting.
