# `AnthropicClient`

The adapter for Claude models over Anthropic's Messages API. `docs/model-clients.md` covers the seam every adapter implements, retries and pacing, streaming, and the comparison between the shipped backends.

---

## 1. The client

```python
from simple_agents import AnthropicClient, PriceBasis, Redaction, RunEnvelope

client = AnthropicClient(model="claude-sonnet-5")

env = RunEnvelope(
    run_dir="runs/",
    cost_basis=PriceBasis(
        currency="USD",
        input_uncached_per_mtok=INPUT_RATE,
        input_cache_read_per_mtok=CACHE_READ_RATE,
        cache_write_per_mtok_by_ttl={"5m": WRITE_5M_RATE, "1h": WRITE_1H_RATE},
        output_per_mtok=OUTPUT_RATE,
    ),
    redaction=Redaction(secret_env=["ANTHROPIC_API_KEY"]),
)
```

The rates are the project's own figures. §3 covers where they come from, and why the cache-write rate is declared per TTL.

`api_key` defaults to the `ANTHROPIC_API_KEY` environment variable and is held as a `SecretStr`. The adapter was measured against `api.anthropic.com` on 2026-09-06 and read against the provider's documentation the same day.

**Every request carries an output ceiling, which the API requires.** A node's `max_output_tokens` is sent where the node sets one; where it does not, the client's own is sent:

```python
AnthropicClient(model="claude-sonnet-5", max_output_tokens=4000)
```

The default is 16,000. Thinking tokens count against the ceiling, so a reasoning-heavy call needs room for both.

## 2. Pinning a model

**The identifier is the pin.** `claude-sonnet-5`, `claude-opus-5` and `claude-haiku-4-5` have no dated form, and a response echoes the identifier that was sent. `GET /v1/models` publishes `created_at` for each, which is metadata rather than a callable identifier; pass it to record it, and the adapter records what it is given without checking it:

```python
AnthropicClient(model="claude-sonnet-5", model_revision="2026-06-29")
```

The same listing publishes the context window, as `max_input_tokens`, and the output ceiling, as `max_tokens`. A pre-flight ceiling is read off the first (`docs/context.md` §2.2).

## 3. Declaring prices

**The project declares the rates.** Prices change, and a basis that has gone stale prices an old trajectory wrongly, so the numbers live in the project rather than in the library.

**Read the current figures from the provider and record the date they were read**, next to where they are declared.

**A cache write is billed per TTL, which is what `cache_write_per_mtok_by_ttl` is for.** The provider's pricing page puts a 5-minute write at 1.25× the base input rate and a 1-hour write at 2×, and a response reports which it was under `cache_creation.ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens`. The adapter records the count as `input_cache_write` and the TTL as `cache_ttl`, and the basis prices it at the rate declared for that TTL. A call whose TTL has no declared rate prices as unknown rather than as zero (`docs/run-envelope.md` §4.2).

`input_tokens` on this backend excludes both cache counts, so `input_uncached` is that figure as reported, and the three input classes add up to the prompt the provider's own arithmetic gives.

## 4. Prompt caching

**A prompt asks for caching with a mark on the message**, which the adapter moves onto the content block this backend reads it from:

```python
Prompt.system("{voice}", voice=persona).marked(cache_control={"type": "ephemeral"})
Prompt.system("{voice}", voice=persona).marked(cache_control={"type": "ephemeral", "ttl": "1h"})
```

The first call carrying the mark reports the write, and a later call sharing the prefix reports `cache_read_input_tokens`, recorded as `input_cache_read`. A prompt shorter than the model's minimum is processed without caching and reports nothing. The provider's guide has the minimum per model and the rule that the mark goes on the last block that stays identical across requests (`docs/prompts.md` §4 for the mark itself).

**One TTL per request.** A call's record holds one `cache_ttl`, so a prompt whose marks name two TTLs is refused with a `ConfigurationError` before it is sent. A request-level mark, the provider's automatic caching, goes through `extra={"cache_control": {"type": "ephemeral"}}` and reaches the body unchanged.

## 5. Reasoning, and what has to go back

**Reasoning is asked for by default**, as `thinking: {"type": "adaptive", "display": "summarized"}`. The tokens are billed as output whether or not the text comes back, and the default display on the current models returns none of it, so the adapter asks for the summary. It is recorded on `outputs.reasoning.text`, and `tokens.output_reasoning` carries `output_tokens_details.thinking_tokens`, the reasoning share of the output count. The text is a summary: no setting returns the raw chain of thought.

**A thinking block carries a `signature`, and the next turn sends the block back unchanged.** The adapter records each block on `outputs.reasoning.blocks` and an `AgentNode` returns them ahead of the tool calls they led to, which is the order the model produced them in. The provider rejects a turn whose thinking blocks were edited, reordered or partly dropped, and on accounts created from 2026-08-31 also one whose earlier history changed. A `reasoning` string carried from another backend has no block to travel in and is left out. Under the default display the block's text is empty and the signature still carries the reasoning, so a block with no text is still returned.

**Adaptive thinking decides per call whether to think.** A call that did not is recorded with `reasoning: null` and `output_reasoning: 0`, and the next turn has no block to send back, which the provider accepts. `output_config: {"effort": ...}` in `extra` sets how much the model thinks; the effort levels a model offers are in its `capabilities` on the model list.

**`reasoning=False` sends `thinking: {"type": "disabled"}`.** Claude Fable models refuse it, since thinking is always on there, and the refusal names the parameter. A model that takes the older form with a token budget, such as Claude Haiku 4.5, is called with a `thinking` in `extra`, which replaces the computed one:

```python
AnthropicClient(model="claude-haiku-4-5")
LLMNode(build_prompt, output_schema=Answer,
        max_output_tokens=4000,
        extra={"thinking": {"type": "enabled", "budget_tokens": 2048}})
```

**`temperature` is refused while thinking is on**, on the current models at any value but the default, and refused on Claude Sonnet 5 outright as deprecated. A node's `temperature` is sent as set and the refusal comes back with the provider's message.

## 6. The seed this API does not take

Every run has a seed, and every sampled call is sent one (`docs/run-envelope.md` §5). **The Messages API has no seed parameter.** `AnthropicClient` declares `seeded = False`, drops the seed from every request, and the run's manifest lists the model under `unseeded_models`. The call record keeps `params.seed`, which is what keyed the cassette: a replay finds its entries, and what the seed did not do is pin the sampling.

## 7. The published allowance

Every response carries the allowance: `anthropic-ratelimit-requests-remaining`, `anthropic-ratelimit-tokens-remaining` for the most restrictive token limit in force, and a reset for each as an RFC 3339 instant. `ModelResponse.rate_limit` carries the two counts and the later of the two resets measured from the response's arrival, and `PacedClient` paces against them (`docs/model-clients.md` §4). Input and output tokens are limited separately as well, and those headers pass through on `provider`.

## 8. Tools and structured output

A tool call arrives as a `tool_use` block with its arguments as an object, so nothing is parsed, and a tool result goes back as a `tool_result` block in a `user` turn. The results of parallel calls go back in one turn, which is how this backend takes them. An output schema goes in `output_config.format`, in the form every property required and `additionalProperties` false, which is the form the structured output was measured to accept.

## 9. What this backend does not report, and what stops a run

**Not reported:** a model revision, which is whatever the constructor was given, and serving concurrency, which is `None`.

**A spent allowance stops the run rather than climbing the retry ladder** (`docs/model-clients.md` §4). The provider documents three refusals, and the library matches each: the tier's monthly cap, a 429 carrying `error.details.error_code: enforced_spend_limit_reached` and no `retry-after`; a spend limit the organisation set itself, a 400 whose message says the specified API usage limits were reached; and a spent prepaid balance, a 400 whose message says the credit balance is too low. The two 400s are read as a spent allowance and not as a bad request. None could be produced from a funded account, so they are taken from the documentation.

**Every error shape was captured**: 401 `authentication_error` for a bad key, 404 `not_found_error` for an unknown model, and a 400 reading "prompt is too long: 230024 tokens > 200000 maximum" for an over-long request, which the adapter raises as `ContextOverflow`. A 529 `overloaded_error` is retried like a 503, and one that arrives inside a stream raises with its message.
