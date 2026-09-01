# Area G: model clients

**Written by the lead from recorded evidence.** The area agent was terminated by a session limit at
05:28, after running its checks and before writing this file. Every statement here is backed by a
row in `../runs/area-g-model-clients.jsonl`. **Coverage is partial**; the gaps are at the end.

**125 checks recorded: 118 pass, 2 fail, 1 error, 4 skip.** As in area F, a passing row on a
`FLAG-n` check means *the flagged defect was confirmed to exist*, because each verification was
written to assert the flagged behaviour.

Backends: Gemini `gemini-3.1-flash-lite` on both keys, and the shared vLLM server on port 8002
serving `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit`. **Mistral is out of credits**, so its live
claims were covered by cassette replay or recorded as untested.

---

## G-1. Ten documented statements that are false. Confirmed, mostly minor, one major.

Each row is a recorded check that passed, meaning the defect is present.

| Check | The defect |
|---|---|
| `FLAG-4` | **`Retry-After` loses to a longer backoff.** `_http._wait` takes `max(backoff, retry_after)`, so a backend asking for a shorter wait is ignored and the run waits longer than the provider requires. The docs say the backoff "waits for the interval it names". |
| `FLAG-4b` | An **HTTP-date** `Retry-After` is ignored rather than parsed. Only the delta-seconds form is honoured. |
| `FLAG-1/10` | The **vLLM concurrency default is documented inverted.** `model-clients.md` §2 says `concurrent_requests` is "`None` by default, filled under `report_concurrency=True`", and `report_concurrency` defaults to `True`. §3 calls reading the divisor "opt-in" where it is opt-out. |
| `FLAG-5` | Mistral's `input_cache_write` is `0` **only when** `prompt_tokens_details.cached_tokens` arrived, and `Unknown` otherwise. Both the comparison table and `mistral.md` §6 state `0` unconditionally. |
| `FLAG-9` | **`PacedClient.waits` counts `_wait` loop iterations, not calls held back.** One capped-then-recapped wait increments it twice, so the figure a project reads to size its pacing is inflated. |
| `FLAG-2` | The FT-13 failure message in `checks.py` says "and the four are" and then lists **five** record types. |
| `FLAG-3` | `brief.py`'s deferral message says "the three stages are" and lists **four**. |
| `FLAG-6` | The sample conformance report in `conformance.md` §3 shows **four** `pass` rows and counts "3 passed", and omits FT-30 entirely (ten of eleven checks shown). |
| `FLAG-7` | FT-04's message sends the reader to the **manifest** for `allow_unknown=False`; `_absent_waived` reads `results.config.nodes`. |
| `FLAG-8` | `simple-agents questions --stage` help names "shape, build or measure", omitting **brainstorm**, which has 13 questions. |

`FLAG-4` is the one with a runtime cost rather than a reading cost: a run against a backend that
asks for a short retry waits the library's longer backoff instead, and that time is charged to
`max_wall_clock_ms`.

---

## G-2. `input_cache_read=0` is written as a literal where every other adapter records `Unknown`. Minor.

`MC-133b` records
[embeddings_openai.py:60](../../../../src/simple_agents/adapters/embeddings_openai.py#L60) writing
`input_cache_read=0`. `docs/trajectory-format.md` is explicit that an unmeasured count is
`Unknown` with a reason rather than a zero, because a zero is a measurement. This adapter reports a
count it did not measure.

---

## G-3. Two vLLM concurrent calls each read the same serving divisor. Minor.

`VLLM-29/30/31` expected two overlapping calls to read `2` and both read `3`. The divisor is read
from the server's own reported running count at the moment of the call, so it includes whatever
else the server was doing. On a shared server that is arguably correct behaviour and not a defect;
on a dedicated one it would read `2`. **Recorded as observed rather than as a defect**, because the
server was genuinely shared with another project during the run and the reading cannot be
attributed cleanly.

---

## What passed, and is worth stating

- **A real tool-calling turn over the wire on vLLM** (`VLLM-08/MC-59`): three model calls, tool
  calls to `shelf_width` and `book_width` with well-formed arguments, then `finish`. The schema the
  library sends is one a real backend accepts and a real model uses. Independently confirmed by the
  lead's composite run (`../runs/composite-vllm.jsonl`), where a 30B model called two hand-written
  tools and answered from their results.
- **A two-backend run declaring one `PriceBasis` is refused**, naming both models and explaining
  that a hosted call is priced on tokens and a self-hosted one on device time (`MC-05b`, recorded
  as ERROR because the agent's test expected it to proceed; the refusal is correct behaviour).
- Token accounting, model identity, revision pinning, streaming, and the reasoning channel are
  covered across the passing rows.

---

## Closed later the same day, after dogfood #4 finished

Four of the gaps below were blocked only because the vLLM server was shared overnight. Dogfood #4
finished at 04:59, and at 13:35 the server was reconfigured twice and then restored. The log is
`../logs/vllm-restarts.md` and the checks are in `../runs/vllm-reasoning-overflow.jsonl`. **All
five passed.**

| Check | Result |
|---|---|
| `VLLM-REASON-1` | with `--reasoning-parser qwen3` the chain of thought is recorded at `outputs.reasoning` with `text` and `blocks`, and does not reach the validated output |
| `VLLM-REASON-2` | `reasoning=False` stops the model producing one |
| `VLLM-REASON-3` | `on_reasoning` receives it as produced, on a streaming node |
| `VLLM-OVERFLOW-1` | a prompt beyond `--max-model-len` raises `ContextOverflow` |
| `VLLM-TOOLREFUSAL-1` | a server started without the tool flags refuses a node offering tools, and the adapter raises the server's own 400 naming both `--enable-auto-tool-choice` and `--tool-call-parser`, exactly as `docs/model-clients/vllm.md` §2 says |

The entries for these in the list below are superseded and are kept so the reasoning behind the
original gap is legible.

## What could not be tested, and why

- **Mistral, live.** The account is out of credits (the credential answers 402). Four checks are
  recorded SKIP against it. Cassette replay covers the streamed-response-has-no-allowance claim
  directly; it does **not** cover prompt caching (every recorded entry has `input_cache_read: 0`),
  the model-list and alias claims, the five rate-limit header names, or the `prompt_mode` refusal.
- **The vLLM chain-of-thought-inside-`content` warning, live** (`VLLM-12/14-live`): the server runs
  without `--reasoning-parser`, and on the probe the model did not open with `<think>`, so the
  warning path was not reached. The adapter's condition is covered without a backend.
- **An `AgentNode` returning the model's own reasoning on the next turn** (`MC-116`): needs a server
  started **with** `--reasoning-parser`. The server was shared with a running dogfood and was not
  restarted.
- **The vLLM tool refusal when the server lacks the tool flags** (`VLLM-07/09`): needs a restart
  without `--enable-auto-tool-choice`, same reason.
- **Gemini prompt caching** (`GEM-19/20`): the provider reported no cache hit on a repeated
  4631-token prompt. Caching is provider-side and there is no library behaviour to assert.
- **`ContextOverflow` provoked for real**: two checks reference it (`MC-13`, `MC-132`) and no
  recorded row shows it raised against a live backend. **Untested.**
- **A deliberate live 429 handled by the retry** was in the brief and was instead measured by the
  lead: see `RATE-1` in `../runs/area-a-graph-mechanics.jsonl`. A fan-out at `concurrent_items=12`
  against the free tier lost 13 of 14 items, with the adapter raising a clear `CallerFacingError`
  naming the URL, the 429 body, and that six attempts did not clear it. That is correct, documented
  behaviour rather than a defect: the library's own warning says retries do not clear a per-minute
  quota. It is recorded here because it is what a free-tier builder will actually meet.
