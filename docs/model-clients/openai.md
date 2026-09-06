# `OpenAIClient` and `OpenAIResponsesClient`

The two adapters for OpenAI, one per API the provider serves. `docs/model-clients.md` covers the seam every adapter implements, retries and pacing, streaming, and the comparison between the shipped backends.

---

## 1. Two clients, and which to reach for

```python
from simple_agents import OpenAIClient, OpenAIResponsesClient, PriceBasis, Redaction, RunEnvelope

client = OpenAIClient(model="gpt-5.6-luna")             # Chat Completions
client = OpenAIResponsesClient(model="gpt-5.6-luna")    # Responses

env = RunEnvelope(
    run_dir="runs/",
    cost_basis=PriceBasis(
        currency="USD",
        input_uncached_per_mtok=INPUT_RATE,
        input_cache_read_per_mtok=CACHE_READ_RATE,
        input_cache_write_per_mtok=CACHE_WRITE_RATE,
        output_per_mtok=OUTPUT_RATE,
    ),
    redaction=Redaction(secret_env=["OPENAI_API_KEY"]),
)
```

The rates are the project's own figures. §3 covers where they come from.

**`OpenAIClient` speaks Chat Completions**, the dialect most hosted providers and local servers serve. It takes the seed every run has, and `base_url` points it at any endpoint that speaks the same dialect (§6). It never returns a chain of thought: a reasoning model reports how many output tokens it spent thinking, recorded as `tokens.output_reasoning`, and `outputs.reasoning` is `null` on every call.

**`OpenAIResponsesClient` speaks Responses**, the provider's own API. It returns the reasoning as a summary and as an encrypted item the next turn sends back, so an `AgentNode` continues from the model's own reasoning. It has no seed parameter: the adapter drops the run's seed and the manifest says so (§5).

| | `OpenAIClient` | `OpenAIResponsesClient` |
|---|---|---|
| API | `/v1/chat/completions` | `/v1/responses` |
| `seed` | sent | refused by the API, dropped and declared |
| Reasoning recorded | the token count | the count, the summary text, and the encrypted item |
| Serves other providers through `base_url` | yes, §6 | the provider's own endpoint |
| Function tools on GPT-5.6 | refused unless `reasoning=False` (§4) | with reasoning on |

Both were measured against `api.openai.com` on 2026-09-06. `api_key` defaults to the `OPENAI_API_KEY` environment variable on both and is held as a `SecretStr`.

## 2. Pinning a model

**A response names the dated snapshot that served it, whichever identifier was sent.** `gpt-5-mini` answered as `gpt-5-mini-2025-08-07`, and the record's `response_model` carries that, so a run made against an alias is still attributable to specific weights (FT-14). The dated identifier is still the pin, since an alias moves; a model with no dated form, such as `gpt-5.6-luna`, is its own pin. `model_revision` is whatever the constructor is given and `None` otherwise: the provider publishes no build string beyond the dated identifier.

`GET /v1/models` lists every identifier the key can call and publishes no context window. A pre-flight ceiling is taken from the provider's model page (`docs/context.md` §2.2).

## 3. Declaring prices

**The project declares the rates.** Prices change, and a basis that has gone stale prices an old trajectory wrongly, so the numbers live in the project rather than in the library.

**Read the current figures from the provider and record the date they were read**, next to where they are declared.

**GPT-5.6 and later bill a cache write, and earlier models do not.** On GPT-5.6 the provider's caching guide prices a write at 1.25× the uncached input rate, and both APIs report the count as `cache_write_tokens`. Declare `input_cache_write_per_mtok` at that rate. On an earlier model the field is absent from the usage block and the provider charges no write class, so the adapter records `input_cache_write` as `0` and the rate is not needed. The provider reports no cache TTL on a response, so `cache_ttl` is `null` on every call and `cache_write_per_mtok_by_ttl` has nothing to key on here.

**Whether the write rate replaces or adds to the uncached rate is read from the guide's wording.** The reference describes `cache_write_tokens` as the prompt tokens written to cache, and the adapter takes `input_uncached` as `prompt_tokens − cached_tokens − cache_write_tokens`, which on the captured call was 3,028 − 3,025 = 3. An invoice confirms the arithmetic against the bill; this page does not.

## 4. Reasoning

**Chat Completions returns no chain of thought.** The provider's reasoning guide says the API has no access to reasoning summaries or detailed reasoning output. What it reports is `completion_tokens_details.reasoning_tokens`, which the adapter records as `tokens.output_reasoning`, inside `tokens.output`. A call whose output count is far larger than its answer is explained by that number and by nothing else in the record.

**Responses returns it.** `OpenAIResponsesClient` asks for the summary with `reasoning: {"summary": "auto"}` and sets `store: false`, which keeps nothing on the provider's side and is what makes the encrypted item come back. The summary is recorded on `outputs.reasoning.text` and the item, with its `id` and `encrypted_content`, on `outputs.reasoning.blocks`. An `AgentNode` sends the item back ahead of the tool call it led to, which the provider's guide asks for; a turn sent without it is accepted, so a conversation recorded against another backend still runs.

**Effort is the model's default unless a node sets it.** Both clients send no effort by default. A node sets one through `extra`, and on the Responses client the setting merges over the summary request:

```python
LLMNode(build_prompt, output_schema=Answer, extra={"reasoning": {"effort": "low"}})       # Responses
LLMNode(build_prompt, output_schema=Answer, extra={"reasoning_effort": "low"})            # Chat Completions
```

The levels a model offers vary (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`), and a model refuses a level it lacks in its own words. `reasoning=False` on either client sends the `none` level. A model that does not reason refuses the `reasoning` parameter on Responses; `extra={"reasoning": None}` leaves it off.

**A reasoning model refuses `max_tokens` and any `temperature` but the default.** The adapters send a node's ceiling as `max_completion_tokens`, which every model accepts. A node's `temperature` is sent as set, and the refusal comes back with the provider's message naming the parameter.

**Chat Completions refuses function tools on GPT-5.6 while reasoning is on.** Measured 2026-09-06: "Function tools with reasoning_effort are not supported for gpt-5.6-luna in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'." An `AgentNode` on that model runs through `OpenAIResponsesClient`, or through `OpenAIClient(reasoning=False)`.

## 5. The seed this API does not take

Every run has a seed, and every sampled call is sent one (`docs/run-envelope.md` §5). Chat Completions takes it. **Responses refuses it** as an unknown parameter, so `OpenAIResponsesClient` declares `seeded = False`, drops the seed from every request, and the run's manifest lists the model under `unseeded_models`. The call record keeps `params.seed`, which is what keyed the cassette: a replay finds its entries, and what the seed did not do is pin the sampling.

## 6. Other endpoints that speak Chat Completions

`base_url` points `OpenAIClient` at any endpoint serving the same dialect, with that provider's key:

```python
OpenAIClient(model="deepseek-chat", base_url="https://api.deepseek.com/v1",
             api_key=os.environ["DEEPSEEK_API_KEY"])
```

What such an endpoint reports is its own. A usage block that carries one prompt figure and no `prompt_tokens_details` leaves `input_cache_read` and `input_cache_write` as `unknown`, a response without `x-ratelimit-*` headers leaves `rate_limit` as `None`, and an error body in another shape reaches the caller as text. The adapter was measured against `api.openai.com` alone; declare the provider's own key in `Redaction(secret_env=[...])`, since the default names only `OPENAI_API_KEY`.

## 7. Prompt caching

**Caching needs no opt-in.** A prompt long enough to qualify is cached, and a later call sharing its prefix reports the hit in `cached_tokens`, which the adapter records as `input_cache_read`. `prompt_cache_key` in `extra` routes requests sharing it to the same cache, which the provider's guide says raises the hit rate under load and guarantees nothing.

## 8. The published allowance

Both APIs publish the remaining allowance on every response, streamed or not: `x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens`, and a reset for each as a duration such as `6ms` or `1m2s`. `ModelResponse.rate_limit` carries the two counts and the later of the two resets, and `PacedClient` paces against them (`docs/model-clients.md` §4).

## 9. What these backends do not report, and what stops a run

**Not reported:** a model revision beyond the dated identifier, a cache TTL, and serving concurrency. The revision is whatever the constructor was given, the TTL and the concurrency are `None`.

**A spent allowance stops the run rather than climbing the retry ladder** (`docs/model-clients.md` §4). The provider's error page names a code beside the message, and the library matches on either: `insufficient_quota`, whose message says the current quota was exceeded, and `credit_balance_exhausted`, `organization_spend_limit_exceeded`, `project_spend_limit_exceeded` and `organization_usage_limit_exceeded`. None of these could be produced from a funded account, so they are taken from the documentation; a wording the library has not met is named with `Retry(spent_quota_phrases=...)`.

**Every error shape was captured**: 401 for a bad key, 404 `model_not_found` for an unknown model, and a 400 whose message names the maximum context length for an over-long request, which the adapter raises as `ContextOverflow`.
