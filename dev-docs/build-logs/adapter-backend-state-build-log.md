# Build log — An adapter's backend state, and the helper that drops it

`plan.md` §1 P3-17. Started 2026-08-18. Written while building, not afterwards.

## 1. Before any design

Dogfood #4's `DF4-N8` said the library's message shape has no field for Gemini's
`thought_signature`, so it is dropped. [`findings.md` §8.3](../runs/dogfood-4/findings.md#L1153)
answered that it was true of that run's wheel and not of the library. **That answer is about a
wheel, so the library was read again before anything was decided.**

- [`ToolCallRequest`](../../src/simple_agents/models.py#L198) holds the value on `provider`, and
  `to_record` omits it when empty, so a conversation built from a backend that sends none is
  byte-identical to one built before the field existed.
- [`tool_calls_from`](../../src/simple_agents/adapters/_gemini_wire.py#L187) reads it off the
  response and [`contents_from`](../../src/simple_agents/adapters/_gemini_wire.py#L38) returns it
  as `thoughtSignature`. The streaming assembler keeps the whole part, so it survives there.
- `tests/test_adapter_integration.py` asserts both halves against a recorded live multi-turn
  Gemini run, and 22 of those passed on the first read.
- **The failure is a hard 400 rather than degradation**, which is neither of the two outcomes the
  note offered. `tests/fixtures/wire/gemini/error_missing_signature.json` is the body, and the run
  measured it as 102 of 102 node executions lost.

**What the read found that the row did not name.**
[`messages_to_wire`](../../src/simple_agents/adapters/_openai_wire.py#L180) rebuilt each call as
`{id, type, function{name, arguments}}` and dropped `provider` with no docstring saying so, while
`docs/model-clients.md` §7 pointed an adapter author at that helper. Correct for the two shipped
adapters, which reach backends that send no such state. `plan.md` §2.2's adapters entry records
that Anthropic's thinking-block signature and OpenAI's Responses `encrypted_content` are both
state of this kind, and Google serves the OpenAI dialect as well.

## 2. Design

Decided at dogfood #4's sitting 2, 2026-08-18.
[`inventory.md` DF4-I33](../runs/dogfood-4/inventory.md#L349) is the record and is not repeated
here.

**Three options were weighed.** Close the row and ship nothing, since the round trip works; say it
in the docs; or make the helper refuse. The third was taken on the argument that the failure is
silent on turn one and fatal on turn two, and that a refusal there cannot produce a false
positive: `provider` is non-empty only where the same adapter filled it from its own response, so
a correct adapter cannot trip it.

**What was weighed and not taken:** a warning rather than a raise, which leaves a run that will
fail one request later, and a `provider_field=` parameter mirroring `reasoning_field=`, which
keeps the silent drop as the default.

## 3. Build

**[`_refuse_provider_state`](../../src/simple_agents/adapters/_openai_wire.py#L245)**, called on
every tool call before the turn is translated. Private, and not in `__all__`.

**What the build changed about the design.** The sitting said `ConfigurationError` and the build
shipped `CallerFacingError`: that class's own docstring says it is raised at construction, and
this fires at run time on the second request, which is the layer `_gemini_wire.tool_calls_from`
already raises at.

**What the build found that the design did not know.**

- **One translation point per adapter covers streaming too.** Both `MistralClient` and
  `VLLMClient` route `complete` and `stream` through one `_payload`, so the single refusal covers
  every request either can make.
- **`_openai_wire.tool_calls_from` fills no `provider`**, so neither shipped adapter can reach the
  refusal, and no fixture or cassette had to move.
- **The docstring hit the 20-line prose limit.** The explanation moved onto
  `_refuse_provider_state`, where it belongs, rather than a `prose-ok` marker being asked for.

No format moved. Four tests added, 2659 to 2663. Surfaces touched: `_openai_wire.py`,
`docs/model-clients.md` §7, `CHANGELOG.md`, `tests/test_adapters.py`.

## 4. Verification

**Live, 2026-08-18**, one `AgentNode` tool loop over the same question on both backends. Mistral
is out of credits, so the hosted arm is Gemini.

| Arm | Model calls | Turns with tool calls | `provider` recorded | Answer |
|---|---|---|---|---|
| vLLM `Qwen/Qwen3-1.7B`, the dialect carrying the refusal | 2 | 2 | absent on every call | correct |
| Gemini `gemini-3.1-flash-lite`, the native dialect | 2 | 2 | a real signature on every call | correct |

**What it shows.** The refusal sits on the hot path of every assistant turn carrying tool calls,
and the vLLM arm is the working case surviving it: `provider` is absent, the helper returns early,
and the loop is unchanged. The Gemini arm answered a second turn, which is only possible if the
signature went back and was accepted, so the two paths have not crossed. A preflight call was made
before the run, per `handoff.md`, and returned `finish_reason=stop` at `max_output_tokens=4000`.

## 5. Doc consequences

- **`docs/model-clients.md` §7** gains *"Return the state a backend sends with a tool call"*,
  placed after the paragraph that introduces conversation translation rather than before it.
- **`CHANGELOG.md`** gains an entry. No format moved, so no version line changed.
- **No shipped statement stopped being true.** §7 said what an adapter owes and was silent on this
  field; `docs/model-clients.md` §2's comparison row and `docs/model-clients/gemini.md` §6 were
  both already correct.

## 6. Left open

- **`Reasoning.blocks` is still filled by nothing.** It exists for Anthropic's thinking-block
  signature and OpenAI's Responses payload, and this item touched neither. Destination:
  [`plan.md`](../plan.md#L1) §2.2, *Adapters for OpenAI and Anthropic*, which now names what
  `P3-17` closed ahead of it.
- **The refusal is unmeasured against a backend that would trip it**, since no shipped adapter can
  reach it. Whichever of those two adapters lands first is what measures it. Destination:
  `nothing`, because that entry already owns the work.
