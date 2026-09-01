# `VLLMClient`

The self-hosted adapter, for open-weight models served by vLLM. `docs/model-clients.md` covers the seam every adapter implements, retries and pacing, streaming, and the comparison between the shipped backends.

---

## 1. The client

```python
from simple_agents import ComputeBasis, RunEnvelope, VLLMClient

client = VLLMClient(model="Qwen/Qwen3-8B", model_revision="<sha>")

env = RunEnvelope(
    run_dir="runs/",
    cost_basis=ComputeBasis(
        currency="USD", device="RTX-3090", device_count=1, hourly_rate=0.22
    ),
)
```

## 2. The serve command

Start the server with the revision pinned and both reporting flags on:

```
vllm serve Qwen/Qwen3-8B --revision <sha> \
    --enable-prompt-tokens-details \
    --enable-auto-tool-choice --tool-call-parser hermes
```

**`--enable-prompt-tokens-details` decides whether the token split is recorded.** With it, `usage.prompt_tokens_details` carries `cached_tokens` and `created_cache_tokens`; those two and the uncached remainder are disjoint and sum to `prompt_tokens`. Without it the server reports the prompt size alone, and the adapter warns once per client and records both cache counts as `unknown` with the flag named in the reason. Prefix caching still works; only the reporting of it is missing. The total stays recoverable, so a `max_tokens` budget is unaffected.

**The tool-call flags are required before tools can be offered at all.** vLLM does not extract tool calls from a model's output unless the server was started for it. `--enable-auto-tool-choice` turns tool calling on, and `--tool-call-parser` names the parser that reads the syntax the model was trained to emit and fills the response's `tool_calls` field. The parser is model-specific: it has to match the syntax the model's chat template produces, and vLLM's documentation lists the ones it ships. `hermes` matches Qwen. A request carrying tools against a server started without both returns 400, and the message names them. The adapter raises that refusal as it stands: nothing in the library prompts the model to emit tool calls in text and parses them back, so a node offering tools needs the server restarted with both flags.

`--max-model-len` sets the context window, and `max_model_len` on the model list reports it. A pre-flight ceiling is read off that rather than picked (`docs/context.md` §2.2).

**`--reasoning-parser` decides whether a chain of thought is separated from the answer.** With it, the server returns `reasoning` alongside `content` and the adapter records the two separately. Without it, the chain of thought is inside `content`: an output schema is validated against text beginning with `<think>`, and that text goes back to the model as though it were the answer. The parser is model-specific in the same way the tool-call parser is, and `qwen3` matches Qwen3.

The server publishes nothing about which parsers it was started with, so the adapter cannot check the flag. It warns once per client instead, when a response opens with a `<think>` block and carries no reasoning field.

```
vllm serve Qwen/Qwen3-8B --revision <sha> \
    --enable-prompt-tokens-details \
    --enable-auto-tool-choice --tool-call-parser hermes \
    --reasoning-parser qwen3
```

## 3. Pinning the revision

**The revision comes from the constructor.** Nothing in a response carries the commit the weights came from, so a `VLLMClient` built without `model_revision` reports `None` and fails FT-14. The adapter records what it is given rather than refusing, because what counts as a pin is one check's judgement rather than each adapter's.

## 4. Per-call settings through `extra`

**`extra` carries per-call settings the library does not read.** The adapter forwards it to the server unchanged, so anything the vLLM OpenAI endpoint accepts can be set on the node that needs it. A setting that applies to every call goes in the constructor instead. `extra` is part of a model call's cassette key, so a pipeline recorded with it and replayed without it is a miss rather than a different run.

`chat_template_kwargs` is one such setting. A reasoning model emits a chain of thought before its answer, which on an open-ended prompt can run to the context window and take minutes. `VLLMClient(..., reasoning=False)` sets the switch for every call the client makes; a node that needs it for one call sets it directly:

```python
LLMNode(summarise, output_schema=Summary,
        extra={"chat_template_kwargs": {"enable_thinking": False}})
```

A setting on the node wins over the client's. A chat template that defines no such switch ignores it, and the server accepts the request either way, so this neither fails nor takes effect on a model that does not think.

## 5. Serving concurrency

For a self-hosted server the real divisor is available separately: `/metrics` publishes `vllm:num_requests_running`. Reading it costs one local request per call and samples an instant rather than the call's lifetime. `docs/model-clients.md` §3 carries the formula it feeds.

```python
VLLMClient(model="Qwen/Qwen3-8B", model_revision="<sha>", report_concurrency=False)
```

**Reading it is on by default**, because a figure derived without it is an upper bound and
`max_cost` ends a run rather than enforcing a limit against one (`docs/run-envelope.md` §4.4).
Turn it off for a server whose metrics endpoint cannot be reached; every compute-basis figure
from that run is then a bound.

With it on, each call records how many requests the server had running while it ran, and cost divides by it instead of charging the whole device. The reading is taken a moment after the request is sent. Sampled before, a batch of calls issued together each see a server with nothing running, every one records 1, and the reported cost is several times the real figure.
An idle reading never reports fewer than one, since this call is in flight while it is taken. A metric the server does not publish, or an endpoint that cannot be read, leaves the field `null` and the call itself unaffected.
