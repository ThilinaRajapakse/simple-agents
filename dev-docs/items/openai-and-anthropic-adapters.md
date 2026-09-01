# Adapters for OpenAI and Anthropic

`plan.md` §1 P3-69's record, scheduled 2026-09-01 out of §2.2 on Thilina's call at the release sitting, behind `P3-31`. **Nothing is built.**

## Where it came from

Named 2026-08-05 at the model-clients review; deferred the same day. The deferred entry, moved here verbatim:

**Adapters for OpenAI and Anthropic.** *Deferred 2026-08-05.* ~~Gemini~~ **built 2026-08-12**, [`build-logs/gemini-adapter-build-log.md`](../build-logs/gemini-adapter-build-log.md#L1); two of this entry's claims did not survive being measured and are corrected at the end of it. Named 2026-08-05 at the model-clients review, where the shipped document had been edited to claim five adapters against the two that ship. The line is back to two and follows the wheel. **OpenAI is the cheap one and covers the most ground.** `_openai_wire.py` is already that dialect, so the work is authentication, that provider's usage-block field names, its error shape, and a `base_url` on the constructor, which makes one adapter serve every OpenAI-compatible endpoint rather than one backend. **Anthropic and Gemini each need a sibling of `_openai_wire.py`**: neither speaks that dialect, and the message shape, the tool-call representation, the usage block and the streaming event format all differ. That sizing is asserted rather than measured, and item 5's twenty-minute probe against the live backends is what settles it, having corrected three assumptions the last time. **What a priced hosted backend beyond Mistral would buy, past coverage:** `input_cache_write` has never carried a number from one, since Mistral bills no cache-write class and vLLM runs under a compute basis, so a backend billing that class separately is the first exercise of the five-field breakdown and of `PriceBasis`. **What item 8f left them, 2026-08-05.** Reasoning output is recorded, and `Reasoning.blocks` exists for exactly these two: Anthropic's thinking block carries a `signature` that has to be returned verbatim and a `redacted_thinking` variant with no text, and OpenAI's Responses item carries an `id` and `encrypted_content`. That shape rests on their published SDK types rather than on a call, since no key for either exists on this machine and neither provider has a free tier. **Measuring it is part of whichever adapter lands first.** One sizing correction falls out of the same reading: `ChatCompletionMessage` has no reasoning field, so an OpenAI adapter reaches reasoning only through the Responses API, which is work the "nearly free against `_openai_wire.py`" estimate above does not cover.

## What the problem is

The entry above carries it, with the measurements.

## What has to be decided

The sizing is asserted rather than measured, so a twenty-minute probe against each live backend opens whichever adapter lands first. No key for either exists on this machine.

## What it waits on

`P3-31`, the release.
