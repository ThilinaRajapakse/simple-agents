# `MistralClient`

The hosted-API adapter for Mistral. `docs/model-clients.md` covers the seam every adapter implements, retries and pacing, streaming, and the comparison between the shipped backends.

---

## 1. The client

```python
from simple_agents import MistralClient, PriceBasis, Redaction, RunEnvelope

client = MistralClient(model="mistral-small-2603")

env = RunEnvelope(
    run_dir="runs/",
    cost_basis=PriceBasis(
        currency="USD",
        input_uncached_per_mtok=INPUT_RATE,
        input_cache_read_per_mtok=CACHE_READ_RATE,
        output_per_mtok=OUTPUT_RATE,
    ),
    redaction=Redaction(secret_env=["MISTRAL_API_KEY"]),
)
```

The rates are the project's own figures. §3 covers where they come from.

## 2. Pinning a dated snapshot

**Pin a dated snapshot.** `GET /v1/models` lists every identifier the account can call, with an `aliases` array on each. The array is symmetric: `mistral-small-2603` lists `mistral-small-latest` and `mistral-small-latest` lists `mistral-small-2603`, and neither is marked as the canonical one. The dated form is the pin. A response echoes back the identifier that was sent, so a run made against an alias records the alias and cannot be attributed to specific weights afterwards.

The same listing publishes the context window, as `max_context_length`. A pre-flight ceiling is read off that rather than picked (`docs/context.md` §2.2).

## 3. Declaring prices

**The project declares the rates.** Prices change, and a basis that has gone stale prices an old trajectory wrongly, so the numbers live in the project rather than in the library.

**Read the current figures from the provider and record the date they were read**, next to where they are declared.

## 4. Prompt caching

**Prompt caching is opt-in, and the provider may also cache on its own.** Sending `prompt_cache_key` in `extra` turns it on for requests sharing that key. This behaviour is provider-dependent, and should be verified. `input_cache_read` records whatever the response reported, so cost derives correctly whether or not a key was sent.

## 5. The published allowance

Mistral publishes the remaining allowance on every response, in `x-ratelimit-remaining-req-minute` and `x-ratelimit-remaining-tokens-minute`. `docs/model-clients.md` §4 covers `ModelResponse.rate_limit` and the client that paces against it.

**A streamed Mistral response carries no `x-ratelimit-*` headers.** `ModelResponse.rate_limit` is `None` on those calls, so a `PacedClient` in front of the adapter has nothing to pace them against and lets them through. It warns once when an allowance it was reading stops arriving. Where a batch has to be paced, leave `stream=True` off the nodes it runs.

## 6. What this backend does not report

**What this backend does not report:** a model revision, a cache-write count, a cache TTL, and serving concurrency. The revision is `None` and the TTL and the concurrency are `None`.

`input_cache_write` is `0` on a response carrying `prompt_tokens_details.cached_tokens`, because the provider bills no cache-write class and the prompt split is then known. A response carrying no such count records `unknown` with that as the reason, alongside an `input_cache_read` of `unknown`: how the prompt divided is unknown, and a zero there would read as a measurement.

**`model_call.outputs.reasoning` is `null` on every call this adapter makes**: the API returns `content` as a single string, refuses `prompt_mode: "reasoning"`, and reports no separate reasoning field. `MistralClient(..., reasoning=False)` is refused at construction rather than sending a setting the API rejects. `docs/model-clients.md` §6 covers the field.
